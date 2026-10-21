"""Decoded UNORM16 movie/PNG acceptance using synthetic numeric test signals.

These signals are not production footage. The checks inspect delivered samples,
including transformed fractional coverage; successful encoder startup alone is
not evidence of retained precision. No optional Python imaging package is used.
"""
from __future__ import annotations

import array
import copy
import hashlib
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

from engine import RenderCancelled, get_capabilities, probe_media, render_project, validate_project
from frame_preview import render_frame


WIDTH, HEIGHT, FPS, FRAMES = 64, 32, 12, 3
MAX = 65535


def rgba16_bytes(pixels):
    values = array.array("H", (channel for pixel in pixels for channel in pixel))
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def decode_rgba16(path):
    result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-threads", "1",
        "-i", str(path), "-map", "0:v:0", "-an", "-threads", "1", "-pix_fmt", "rgba64le",
        "-f", "rawvideo", "pipe:1"], check=True, capture_output=True, timeout=30)
    values = array.array("H", result.stdout)
    if sys.byteorder != "little":
        values.byteswap()
    return list(zip(*(iter(values),) * 4))


def write_fixture(path, pixels, *, width=WIDTH, height=HEIGHT, frames=FRAMES):
    """Encode explicit source samples, without a renderer-generated oracle."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = list(pixels)
    if len(pixels) != width * height:
        raise ValueError("Fixture pixel count does not match its dimensions.")
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", "1",
        "-f", "rawvideo", "-pixel_format", "rgba64le", "-video_size", f"{width}x{height}",
        "-framerate", str(FPS), "-i", "pipe:0", "-an", "-c:v", "ffv1", "-level", "3",
        "-pix_fmt", "gbrap16le", "-threads", "1", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-colorspace", "rgb", "-color_range", "pc", str(path)],
        input=rgba16_bytes(pixels) * frames, check=True, capture_output=True, timeout=15)
    return path


def numeric_ramp():
    # 1,024 distinct code values; they cannot survive an eight-bit bottleneck.
    return [(4096 + 32 * (i % 1024), 12288 + 16 * (i % 1024),
             49152 - 24 * (i % 1024), MAX) for i in range(WIDTH * HEIGHT)]


def alpha_sprite(hidden=(0, 0, 0)):
    pixels = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            edge = min(x - 11, WIDTH - 12 - x, y - 5, HEIGHT - 6 - y)
            alpha = min(MAX, max(0, edge * 9001 + 3703)) if edge >= 0 else 0
            pixels.append((60013, 11009, 23117, alpha) if alpha else (*hidden, 0))
    return pixels


def source_over(background, foreground):
    """Independent straight-alpha Porter–Duff oracle in real-valued arithmetic."""
    ab, af = background[3] / MAX, foreground[3] / MAX
    alpha = af + ab * (1 - af)
    if not alpha:
        return (0, 0, 0, 0)
    colors = [round((foreground[c] * af + background[c] * ab * (1 - af)) / alpha)
              for c in range(3)]
    return (*colors, round(alpha * MAX))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe are required")
class HighPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not get_capabilities().get("master16"):
            raise unittest.SkipTest("This FFmpeg build cannot execute the 16-bit master graph.")
        cls.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-HIGH16-ENGINE-TEST-")
        cls.root = Path(cls.temporary.name)
        cls.fixtures = {
            "ramp": numeric_ramp(),
            "sprite": alpha_sprite(),
            "hidden": alpha_sprite((27183, MAX, 37011)),
            "half": [(60013, 11009, 23117, 32749)] * (WIDTH * HEIGHT),
            "background": [(9007, 47101, 17003, 34857)] * (WIDTH * HEIGHT),
            "foreground": [(53213, 18017, 33121, 19731)] * (WIDTH * HEIGHT),
        }
        cls.assets = {}
        cls.source_hashes = {}
        for name, pixels in cls.fixtures.items():
            path = write_fixture(cls.root / "media" / f"ENGINE_TEST_ONLY_{name}.mkv", pixels)
            cls.assets[name] = {"id": name, "name": "ENGINE TEST " + name,
                               "path": str(path.relative_to(cls.root)), **probe_media(path)}
            cls.source_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            if decode_rgba16(path)[:WIDTH * HEIGHT] != pixels:
                raise AssertionError("The independent fixture encoder changed numeric input samples.")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def project(self, *names):
        return {"version": 1, "id": "high_precision_test", "name": "ENGINE TEST — 16-bit SDR",
                "fps": FPS, "width": WIDTH, "height": HEIGHT,
                "assets": [copy.deepcopy(self.assets[name]) for name in names], "clips": [], "titles": [],
                "settings": {"image_precision": "high16", "transparent_background": True}}

    @staticmethod
    def clip(asset, ident="picture", **values):
        return {"id": ident, "asset_id": asset, "track": 0, "start": 0, "in": 0,
                "duration": FRAMES, **values}

    def render(self, project, name, profile="master16"):
        path = self.root / "exports" / (name + (".mkv" if profile == "master16" else ".mp4"))
        receipt = render_project(project, self.root, path, profile)
        return path, receipt, decode_rgba16(path)

    def test_1024_distinct_values_survive_movie_and_16bit_paused_png(self):
        project = self.project("ramp")
        project["clips"] = [self.clip("ramp")]
        movie, receipt, pixels = self.render(project, "opaque_ramp")
        self.assertEqual(pixels, self.fixtures["ramp"] * FRAMES)
        self.assertEqual(len({pixel[0] for pixel in pixels}), 1024)
        self.assertEqual(receipt["pixel_format"], "gbrap16le")
        self.assertEqual(receipt["processing_bits"], 16)
        self.assertEqual(receipt["encoding"], "ffv1")
        self.assertEqual(receipt["alpha_mode"], "straight")
        self.assertEqual(receipt["color_space"], "SDR Rec.709")
        self.assertEqual(receipt["packet_verification"],
                         {"video_packets": FRAMES, "pcm_samples": FRAMES * 4000, "pcm_bytes": FRAMES * 16000})
        png = self.root / "ramp_frame1.png"
        preview = render_frame(project, self.root, 1, png)
        data = png.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">IIBBBBB", data[16:29]), (WIDTH, HEIGHT, 16, 6, 0, 0, 0))
        self.assertEqual(preview["processing_bits"], 16)
        self.assertEqual(decode_rgba16(png), self.fixtures["ramp"])
        self.assertEqual(hashlib.sha256(movie.read_bytes()).hexdigest(), receipt["sha256"])

    def test_nonidentity_grade_has_16bit_numeric_precision(self):
        project = self.project("ramp")
        project["clips"] = [self.clip("ramp", grade={"exposure": .5, "contrast": .75,
            "saturation": .65, "temperature": .1})]
        _, _, pixels = self.render(project, "graded_ramp")
        errors = []
        for actual, source in zip(pixels, self.fixtures["ramp"]):
            graded = [(c / MAX * math.sqrt(2) - .5) * .75 + .5 for c in source[:3]]
            luminance = sum(c * w for c, w in zip(graded, (.2126, .7152, .0722)))
            expected = [round(MAX * min(1, max(0, luminance + (c - luminance) * .65 + warmth)))
                        for c, warmth in zip(graded, (.012, 0, -.012))]
            errors.extend(abs(a - b) for a, b in zip(actual[:3], expected))
            self.assertEqual(actual[3], MAX)
        self.assertLessEqual(max(errors), 2)
        self.assertGreater(len({pixel[0] for pixel in pixels}), 1000)

    def test_two_fractional_alpha_layers_match_independent_source_over(self):
        project = self.project("background", "foreground")
        project["clips"] = [self.clip("background", "under"), self.clip("foreground", "over", track=1)]
        _, _, pixels = self.render(project, "fractional_composite")
        expected = source_over(self.fixtures["background"][0], self.fixtures["foreground"][0])
        self.assertLessEqual(max(abs(a - b) for pixel in pixels for a, b in zip(pixel, expected)), 5)
        self.assertTrue(0 < pixels[0][3] < MAX)
        self.assertNotEqual(pixels[0][3] % 257, 0, "Alpha must not be quantized to eight bits.")

    def test_scale_rotation_and_translation_do_not_bleed_hidden_rgb(self):
        outputs = []
        for name in ("sprite", "hidden"):
            project = self.project(name)
            project["clips"] = [self.clip(name, scale=.73, rotation=27, x=.071, y=-.093)]
            _, _, pixels = self.render(project, "transformed_" + name)
            outputs.append(pixels)
        self.assertEqual(*outputs, "Fully transparent source RGB must not contaminate filtered visible edges.")
        visible = [p for p in outputs[0] if p[3] > 8192]
        partial = [p for p in outputs[0] if 0 < p[3] < MAX]
        self.assertGreater(len(visible), FRAMES * 100)
        self.assertGreater(len({p[3] for p in partial}), 100)
        self.assertTrue(all(p == (0, 0, 0, 0) for p in outputs[0] if p[3] == 0))

    def test_constant_fractional_color_survives_transformed_alpha_edges(self):
        # The constant plateau avoids Lanczos's intentional ringing/clipping at
        # an alpha=1 discontinuity. The independent color oracle is therefore
        # valid throughout the transformed semitransparent rectangle, including
        # its filtered edge. Hidden-color invariance above covers varying alpha.
        project = self.project("half")
        project["clips"] = [self.clip("half", scale=.73, rotation=27, x=.071, y=-.093)]
        _, _, pixels = self.render(project, "constant_fractional_transform")
        visible = [p for p in pixels if p[3] > 8192]
        self.assertGreater(len(visible), FRAMES * 100)
        self.assertTrue(any(8192 < p[3] < 32000 for p in visible))
        self.assertLessEqual(max(abs(c - e) for p in visible for c, e in zip(p[:3], (60013, 11009, 23117))), 64)

    def test_transformed_coverage_over_background_matches_straight_alpha_oracle(self):
        layer = self.project("sprite")
        layer["clips"] = [self.clip("sprite", scale=.69, rotation=-19, x=-.063, y=.107, opacity=.71)]
        _, _, layer_pixels = self.render(layer, "coverage_layer")
        composite = self.project("background", "sprite")
        composite["clips"] = [self.clip("background", "under"), {**layer["clips"][0], "track": 1}]
        _, _, composite_pixels = self.render(composite, "coverage_over_background")
        background = self.fixtures["background"][0]
        expected = [source_over(background, p) for p in layer_pixels]
        errors = [abs(a - b) for p, q in zip(composite_pixels, expected) for a, b in zip(p, q)]
        self.assertLessEqual(max(errors), 9)
        self.assertEqual(len(composite_pixels), WIDTH * HEIGHT * FRAMES)

    def test_animated_geometry_and_trim_preserve_movie_paused_frame_identity(self):
        project = self.project("sprite")
        project["clips"] = [self.clip("sprite", keyframes=[{"frame": 0, "scale": .5, "rotation": -8},
            {"frame": 2, "scale": .9, "rotation": 31}], x=.08)]
        _, _, full = self.render(project, "animated_transform")
        size = WIDTH * HEIGHT
        self.assertNotEqual(full[:size], full[2 * size:])
        png = self.root / "animated_frame1.png"
        render_frame(project, self.root, 1, png)
        self.assertEqual(decode_rgba16(png), full[size:2 * size])
        trimmed = copy.deepcopy(project)
        trimmed["clips"][0].update({"in": 1, "duration": 2, "animation_offset": 1, "animation_duration": FRAMES})
        _, _, cut = self.render(trimmed, "animated_transform_trimmed")
        self.assertEqual(cut, full[size:], "A head trim must retain the original scale/rotation domain.")

    def test_non_alpha_delivery_flattens_hidden_pixels_against_black(self):
        project = self.project("hidden")
        project["clips"] = [self.clip("hidden")]
        _, receipt, pixels = self.render(project, "opaque_delivery", "h264")
        self.assertEqual(receipt["alpha_mode"], "opaque")
        self.assertEqual(receipt["processing_bits"], 16)
        for frame in range(FRAMES):
            first = pixels[frame * WIDTH * HEIGHT]
            self.assertLess(max(first[:3]), 1024)
            self.assertEqual(first[3], MAX)

    def test_master_policy_and_cancel_preserve_existing_output_and_sources(self):
        project = self.project("ramp")
        project["clips"] = [self.clip("ramp")]
        output = self.root / "exports" / "preserved.mkv"
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"existing verified master")
        cancelled = threading.Event(); cancelled.set()
        with self.assertRaises(RenderCancelled):
            render_project(project, self.root, output, "master16", cancel_event=cancelled)
        self.assertEqual(output.read_bytes(), b"existing verified master")
        standard = copy.deepcopy(project)
        standard["settings"] = {"image_precision": "standard8"}
        with self.assertRaisesRegex(ValueError, "High 16-bit"):
            render_project(standard, self.root, output, "master16")
        standard["settings"]["transparent_background"] = True
        with self.assertRaisesRegex(ValueError, "transparent movie background"):
            validate_project(standard, self.root)
        for name, digest in self.source_hashes.items():
            self.assertEqual(hashlib.sha256((self.root / self.assets[name]["path"]).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()

"""Real encoder tests. All generated media below are ENGINE TEST FIXTURES ONLY.

The colored frames and tones are test signals, never production film material.
Run: python3 -m unittest discover -s scripts/studio -p 'test_engine.py' -v
"""
import array
import copy
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

from engine import RenderCancelled, get_capabilities, probe_media, render_project, validate_project


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe are required")
class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-")
        cls.root = Path(cls.directory.name)
        (cls.root / "media").mkdir()
        for name, color in (("red", "red"), ("blue", "blue"), ("gray", "0x505050"), ("green", "0x00ff00")):
            cls.run_ffmpeg(["-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=12:d=2",
                            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2",
                            "-c:v", "ffv1", "-c:a", "pcm_s16le", "-shortest", str(cls.root / "media" / f"ENGINE_TEST_ONLY_{name}.mkv")])
        cls.run_ffmpeg(["-i", str(cls.root / "media" / "ENGINE_TEST_ONLY_red.mkv"),
                        "-i", str(cls.root / "media" / "ENGINE_TEST_ONLY_blue.mkv"),
                        "-filter_complex", "[0:v]trim=duration=1,setpts=PTS-STARTPTS[r];[1:v]trim=duration=1,setpts=PTS-STARTPTS[b];[r][b]concat=n=2:v=1:a=0[v]",
                        "-map", "[v]", "-c:v", "ffv1", str(cls.root / "media" / "ENGINE_TEST_ONLY_switch.mkv")])
        # A genuine RGBA input checks transparent overlays without Pillow dependencies.
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        pixels = b"".join(b"\x00" + bytes([0, 0, 255, 128]) * 32 for _ in range(32))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
        (cls.root / "media" / "ENGINE_TEST_ONLY_alpha.png").write_bytes(png)
        pixels = b"".join(b"\x00" + b"".join(bytes([255, 255, 255, 255 if 110 <= x < 145 and 60 <= y < 80 else 0]) for x in range(160)) for y in range(90))
        raster = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 90, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
        (cls.root / "media" / "ENGINE_TEST_ONLY_title.png").write_bytes(raster)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @staticmethod
    def run_ffmpeg(arguments):
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1"] + arguments,
                       check=True, capture_output=True, timeout=45)

    def project(self, *names):
        return {"version": 1, "id": "engine_test", "name": "ENGINE TEST SIGNALS ONLY", "fps": 12, "width": 160, "height": 90,
                "assets": [{"id": n, "name": "ENGINE TEST ONLY " + n, "path": f"media/ENGINE_TEST_ONLY_{n}.mkv", **probe_media(self.root / "media" / f"ENGINE_TEST_ONLY_{n}.mkv")} for n in names],
                "clips": [], "titles": [], "settings": {}}

    def clip(self, asset, ident="clip", **kwargs):
        return {"id": ident, "asset_id": asset, "track": 0, "start": 0, "in": 0, "duration": 12, **kwargs}

    def output(self, name, suffix="mp4"):
        return self.root / "exports" / f"ENGINE_TEST_ONLY_{name}.{suffix}"

    def pixel(self, path, time, x=80, y=45):
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-ss", str(time), "-i", str(path),
                                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"],
                                check=True, capture_output=True, timeout=20)
        start = (y * 160 + x) * 3
        return tuple(result.stdout[start:start + 3])

    def audio_rms(self, path, time, duration=.15):
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-ss", str(time), "-i", str(path), "-t", str(duration),
                                 "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"],
                                check=True, capture_output=True, timeout=20)
        values = array.array("f", result.stdout)
        return math.sqrt(sum(v * v for v in values) / len(values))

    def test_trim_and_audio_gap_are_rendered_not_inferred(self):
        p = self.project("switch", "red")
        p["clips"] = [self.clip("switch", in_=12)]
        p["clips"][0].pop("in_")
        p["clips"][0]["in"] = 12
        p["clips"].append(self.clip("red", "later", start=24))
        output = self.output("trim_gap")
        updates = []
        report = render_project(p, self.root, output, "preview", updates.append)
        self.assertEqual(report["frames"], 36)
        self.assertEqual(report["duration"], 3)
        self.assertEqual(len(report["sha256"]), 64)
        self.assertEqual(updates[-1], 1)
        r, g, b = self.pixel(output, .5)
        self.assertGreater(b, r + 100, "Source trim must select second, blue half of test signal")
        self.assertLess(max(self.pixel(output, 1.4)), 8, "Timeline gap must remain black")
        self.assertGreater(self.pixel(output, 2.4)[0], 180)
        self.assertLess(self.audio_rms(output, 1.3), .001)
        self.assertGreater(self.audio_rms(output, 2.3), .03)

    def test_layer_position_opacity_and_grade_change_pixels(self):
        p = self.project("red", "blue", "gray")
        p["clips"] = [self.clip("red", duration=24), self.clip("blue", "overlay", track=1, start=12, scale=.5, x=.25, opacity=.5)]
        output = self.output("layers")
        render_project(p, self.root, output, "preview")
        left = self.pixel(output, 1.5, 20)
        right = self.pixel(output, 1.5, 120)
        self.assertGreater(left[0], 180)
        self.assertLess(left[2], 30)
        self.assertGreater(right[0], 70)
        self.assertGreater(right[2], 70)
        p["clips"] = [self.clip("gray")]
        neutral = self.output("neutral")
        render_project(p, self.root, neutral, "preview")
        p["clips"][0]["grade"] = {"exposure": 1}
        graded = self.output("graded")
        render_project(p, self.root, graded, "preview")
        self.assertGreater(sum(self.pixel(graded, .5)), sum(self.pixel(neutral, .5)) + 50)

    def test_keyframed_transform_and_opacity_are_real(self):
        p = self.project("red", "blue")
        p["clips"] = [self.clip("red"), self.clip("blue", "animated", track=1, scale=.25, opacity=0,
                                                    keyframes=[{"frame": 0, "x": -.3, "scale": .25, "opacity": 0},
                                                               {"frame": 11, "x": .3, "scale": .5, "opacity": 1}])]
        output = self.output("animation")
        render_project(p, self.root, output, "preview")
        self.assertGreater(self.pixel(output, 0, 120)[0], 180)
        red, green, blue = self.pixel(output, 11/12, 125)
        self.assertGreater(blue, red + 80)
        self.assertGreater(self.pixel(output, 11/12, 20)[0], 180)

    def test_chroma_key_preserves_underlying_picture(self):
        p = self.project("red", "green")
        p["clips"] = [self.clip("red"), self.clip("green", "keyed", track=1, effects={"chroma_key": "#00ff00"})]
        output = self.output("chroma")
        render_project(p, self.root, output, "preview")
        red, green, blue = self.pixel(output, .5)
        self.assertGreater(red, 180)
        self.assertLess(green, 40)

    def test_titles_are_literal_text_and_prores_is_decodable(self):
        if not get_capabilities()["drawtext"]:
            self.skipTest("FFmpeg drawtext unavailable")
        p = self.project("red")
        p["clips"] = [self.clip("red")]
        p["titles"] = [{"id": "title", "text": "TEST %{x}", "start": 0, "duration": 12, "size": 14}]
        output = self.output("title", "mov")
        report = render_project(p, self.root, output, "prores")
        self.assertEqual(report["frames"], 12)
        self.assertEqual(probe_media(output)["codec"], "prores")

    def test_raster_titles_work_without_drawtext_and_keep_baked_position(self):
        p = self.project("red")
        p["assets"].append({"id": "raster", "kind": "image", "path": "media/ENGINE_TEST_ONLY_title.png"})
        p["clips"] = [self.clip("red", duration=24)]
        p["titles"] = [{"id": "title", "text": "ENGINE TEST TITLE", "asset_id": "raster", "start": 6, "duration": 12,
                        "x": .35, "y": .35, "size": 14, "fade": 3}]
        output = self.output("raster_title")
        capabilities = get_capabilities()
        capabilities["drawtext"] = False
        with patch("engine.get_capabilities", return_value=capabilities):
            render_project(p, self.root, output, "preview")
        self.assertLess(self.pixel(output, .25, 125, 70)[1], 30)
        self.assertGreater(min(self.pixel(output, 1, 125, 70)), 200, "Raster title must stay at its baked pixel position")
        self.assertLess(self.pixel(output, 1, 80, 45)[1], 30, "Transparent title canvas must preserve the underlying footage")
        self.assertLess(self.pixel(output, 1.75, 125, 70)[1], 30)
        during_fade = self.pixel(output, 7/12, 125, 70)[1]
        self.assertGreater(during_fade, 35)
        self.assertLess(during_fade, 180)
        p["titles"][0]["asset_id"] = "red"
        with self.assertRaisesRegex(ValueError, "PNG"):
            validate_project(p, self.root)
        p["assets"].append({"id": "small", "kind": "image", "path": "media/ENGINE_TEST_ONLY_alpha.png"})
        p["titles"][0]["asset_id"] = "small"
        with self.assertRaisesRegex(ValueError, "match the project canvas"):
            validate_project(p, self.root)

    def test_missing_or_out_of_range_media_and_unsafe_paths_fail(self):
        p = self.project("red")
        p["clips"] = [self.clip("red", duration=60)]
        with self.assertRaisesRegex(ValueError, "beyond its source"):
            validate_project(p, self.root)
        for unsafe in ("../outside.mp4", "/tmp/outside.mp4", "media/../../outside.mp4"):
            test = self.project("red")
            test["assets"][0]["path"] = unsafe
            with self.assertRaises(ValueError):
                validate_project(test, self.root)
        test = self.project("red")
        test["clips"] = [self.clip("red", scale=float("nan"))]
        with self.assertRaises(ValueError):
            validate_project(test, self.root)
        test["clips"][0]["scale"] = 1
        test["clips"][0]["keyframes"] = [{"frame": 0, "rotation": 90}]
        with self.assertRaisesRegex(ValueError, "support"):
            validate_project(test, self.root)

    def test_cancel_does_not_publish_partial_output(self):
        p = self.project("red")
        p["clips"] = [self.clip("red")]
        output = self.output("cancelled")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(RenderCancelled):
            render_project(p, self.root, output, cancel_event=cancel)
        self.assertFalse(output.exists())
        self.assertEqual(list(output.parent.glob("*.partial.mp4")), [])

    def test_empty_project_saves_but_cannot_render(self):
        p = self.project()
        self.assertEqual(validate_project(p, self.root)["clips"], [])
        with self.assertRaisesRegex(ValueError, "Add footage"):
            render_project(p, self.root, self.output("empty"))

    def test_blender_scene_in_bin_is_not_misrepresented_as_timeline_media(self):
        (self.root / "media" / "ENGINE_TEST_ONLY_scene.blend").write_bytes(b"BLENDER-test-fixture-not-a-renderable-scene")
        p = self.project("red")
        p["assets"].append({"id": "scene", "kind": "scene", "name": "ENGINE TEST ONLY", "path": "media/ENGINE_TEST_ONLY_scene.blend"})
        self.assertEqual(validate_project(p, self.root)["assets"][1]["kind"], "scene")
        p["clips"] = [self.clip("scene")]
        with self.assertRaisesRegex(ValueError, "Render the Blender scene"):
            validate_project(p, self.root)

    def test_source_alpha_survives_color_adjustments(self):
        p = self.project("red")
        p["assets"].append({"id": "alpha", "kind": "image", "path": "media/ENGINE_TEST_ONLY_alpha.png"})
        p["clips"] = [self.clip("red"), self.clip("alpha", "transparent", track=1, grade={"contrast": 1.1, "exposure": .2})]
        output = self.output("alpha")
        render_project(p, self.root, output, "preview")
        red, green, blue = self.pixel(output, .5)
        self.assertGreater(red, 70, "Source transparency must remain through grading")
        self.assertGreater(blue, 70)


if __name__ == "__main__":
    unittest.main()

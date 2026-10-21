"""Actual codec tests for all eight EXIF rotations/reflections.

Fixtures are synthetic and deliberately asymmetric. No photograph, external
download, Pillow, or EXIF-writing package is needed. The expected pixel
permutations below are independent of the implementation's frame-matrix probe.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from media_orientation import still_display_info


def codec(argv, payload=None):
    return subprocess.run(argv, input=payload, capture_output=True, check=True, timeout=15).stdout


def exif_jpegs(directory, ffmpeg):
    width, height = 64, 40
    # Every quadrant is different; an asymmetric stripe also distinguishes
    # mirror from rotate at individual-pixel precision.
    colors = ((235, 42, 35), (40, 210, 50), (25, 55, 235), (225, 195, 30))
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend((170, 20, 190) if 5 <= x < 9 and 6 <= y < 18
                          else colors[(y >= height // 2) * 2 + (x >= width // 2)])
    jpeg = codec([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                  "-s", "%dx%d" % (width, height), "-i", "pipe:0", "-frames:v", "1", "-threads", "1",
                  "-pix_fmt", "yuvj444p", "-c:v", "mjpeg", "-q:v", "1", "-f", "image2pipe", "pipe:1"], pixels)
    paths = {}
    for orientation in range(1, 9):
        # TIFF IFD0 Orientation, big-endian SHORT, count one, inline value.
        exif = (b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x01" +
                struct.pack(">HHIH", 0x112, 3, 1, orientation) + b"\x00\x00\x00\x00\x00\x00")
        path = Path(directory) / ("orientation%d.jpg" % orientation)
        path.write_bytes(jpeg[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + jpeg[2:])
        paths[orientation] = path
    return paths, width, height


def oriented_pixels(data, width, height, orientation, channels=3):
    out_width, out_height = (height, width) if orientation >= 5 else (width, height)
    result = bytearray()
    for y in range(out_height):
        for x in range(out_width):
            sx, sy = {1: (x, y), 2: (width - 1 - x, y), 3: (width - 1 - x, height - 1 - y),
                      4: (x, height - 1 - y), 5: (y, x), 6: (y, height - 1 - x),
                      7: (width - 1 - y, height - 1 - x), 8: (width - 1 - y, x)}[orientation]
            start = (sy * width + sx) * channels
            result.extend(data[start:start + channels])
    return bytes(result)


class OrientationValidationTests(unittest.TestCase):
    def test_ffmpeg8_display_matrices_recover_all_tags_including_mirrors(self):
        axes = ((1, 0, 0, 1), (-1, 0, 0, 1), (-1, 0, 0, -1), (1, 0, 0, -1),
                (0, 1, 1, 0), (0, 1, -1, 0), (0, -1, -1, 0), (0, -1, 1, 0))
        for orientation, (a, b, c, d) in enumerate(axes, 1):
            rotation = (-90 if orientation in (5, 6) else 90 if orientation in (7, 8) else
                        -180 if orientation in (2, 3) else 0)
            matrix = "\n00000000: %d %d 0\n00000001: %d %d 0\n00000002: 0 0 1073741824\n" % tuple(x * 65536 for x in (a, b, c, d))
            frame = {"width": 80, "height": 40, "side_data_list": [
                {"side_data_type": "3x3 displaymatrix", "rotation": rotation, "displaymatrix": matrix},
                {"side_data_type": "EXIF metadata"}]}
            result = subprocess.CompletedProcess([], 0, json.dumps({"frames": [frame]}).encode(), b"")
            with self.subTest(orientation=orientation), patch("media_orientation.subprocess.run", return_value=result):
                actual = still_display_info("unused.jpg", "ffprobe", {"width": 80, "height": 40})
                self.assertEqual(actual["exif_orientation"], orientation)
                self.assertEqual((actual["width"], actual["height"]), (40, 80) if orientation >= 5 else (80, 40))

    def test_pixel_bound_precedes_frame_decode(self):
        with patch("media_orientation.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "dimensions"):
                still_display_info("unused.jpg", "ffprobe", {"width": 16384, "height": 16384}, max_pixels=33_554_432)
        run.assert_not_called()

    def test_unavailable_orientation_matrix_does_not_silently_misorient(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"frames": [{"width": 80, "height": 40,
                                              "tags": {"Orientation": "6"}}]}).encode(), b"")
        with patch("media_orientation.subprocess.run", return_value=result), self.assertRaisesRegex(ValueError, "display matrix"):
            still_display_info("unused.jpg", "ffprobe", {"width": 80, "height": 40})


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Actual FFmpeg and ffprobe are required")
class OrientationCodecTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-orientation-TEST-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "media").mkdir()
        self.ffmpeg, self.ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        self.paths, self.width, self.height = exif_jpegs(self.root / "media", self.ffmpeg)

    def pixels(self, path, pixel_format="rgb24", autorotate=True):
        return codec([self.ffmpeg, "-v", "error", "-nostdin", "-threads", "1"] +
                     ([] if autorotate else ["-noautorotate"]) + ["-i", str(path), "-frames:v", "1", "-threads", "1",
                     "-f", "rawvideo", "-pix_fmt", pixel_format, "pipe:1"])

    def test_admission_and_actual_decoder_agree_all_eight_orientations(self):
        from engine import probe_media
        baseline = self.pixels(self.paths[1], autorotate=False)
        for orientation, path in self.paths.items():
            with self.subTest(orientation=orientation):
                admitted = probe_media(path)
                dimensions = (self.height, self.width) if orientation >= 5 else (self.width, self.height)
                self.assertEqual((admitted["width"], admitted["height"]), dimensions)
                self.assertEqual(admitted["exif_orientation"], orientation)
                self.assertEqual((admitted["coded_width"], admitted["coded_height"]), (self.width, self.height))
                self.assertEqual(self.pixels(path), oriented_pixels(baseline, self.width, self.height, orientation))

    def test_imaging_decode_preserves_exact_orientation_and_integer_precision(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy is needed to exercise the optional imaging decoder")
        from image_worker import decode_image
        baseline = self.pixels(self.paths[1], "rgba64le", autorotate=False)
        for orientation, path in self.paths.items():
            with self.subTest(orientation=orientation):
                actual, metadata = decode_image(path, self.ffmpeg, self.ffprobe, np)
                width, height = (self.height, self.width) if orientation >= 5 else (self.width, self.height)
                expected_bytes = oriented_pixels(baseline, self.width, self.height, orientation, channels=8)
                expected = np.frombuffer(expected_bytes, dtype="<u2").reshape(height, width, 4).astype(np.float32) / 65535
                self.assertEqual(actual.shape, (height, width, 4))
                self.assertEqual((metadata["width"], metadata["height"]), (width, height))
                np.testing.assert_array_equal(actual, expected)

    def test_timeline_export_graph_matches_manually_oriented_pixels(self):
        from engine import probe_media
        from frame_preview import render_frame
        baseline = self.pixels(self.paths[1], autorotate=False)
        for orientation, path in self.paths.items():
            with self.subTest(orientation=orientation):
                width, height = (self.height, self.width) if orientation >= 5 else (self.width, self.height)
                asset = {"id": "picture", "path": str(path.relative_to(self.root)), **probe_media(path)}
                project = {"version": 1, "id": "orientation", "name": "ENGINE TEST — EXIF orientation",
                           "fps": 12, "width": width, "height": height, "assets": [asset], "titles": [],
                           "clips": [{"id": "clip", "asset_id": "picture", "start": 0, "in": 0, "duration": 1, "track": 0}]}
                output = self.root / ("rendered-%d.png" % orientation)
                render_frame(project, self.root, 0, output)
                expected = oriented_pixels(baseline, self.width, self.height, orientation)
                actual = self.pixels(output)
                self.assertEqual(len(actual), len(expected))
                # YUV-to-RGB rounding may differ between the direct decoder
                # and the export graph's RGBA overlay by at most one code.
                self.assertLessEqual(max(abs(a - b) for a, b in zip(actual, expected)), 1)


if __name__ == "__main__":
    unittest.main()

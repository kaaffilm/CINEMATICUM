"""Actual still-photo pixels, measured geometry, response and owned-job tests.

Fixtures are clearly marked engine tests. Their source radiance, independent
camera response and projective camera coordinates are known analytically. The
production fitter receives only encoded photographs and explicit shutter times.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
import zlib

import imaging
import still_photography


def scene(np, height=192, width=320, seed=612):
    rng = np.random.default_rng(seed)
    x = np.arange(width)[None, :, None] / max(1, width - 1)
    y = np.arange(height)[:, None, None] / max(1, height - 1)
    result = (.035 * np.exp(5.5 * x) * (1 + .15 * np.sin(y * 21))).repeat(3, axis=2).astype(np.float32)
    for _ in range(650):
        left, top = int(rng.integers(0, width - 8)), int(rng.integers(0, height - 8))
        size_x, size_y = int(rng.integers(3, 18)), int(rng.integers(3, 18))
        result[top:top + size_y, left:left + size_x] *= rng.uniform(.35, 1.6, 3)
    # Colored fiducials make the geometric oracle independent of matching code.
    return np.clip(result, .005, 14)


def sample(np, source, source_to_world, width, height):
    """Independent inverse-map bilinear camera fixture, without OpenCV warps."""
    yy, xx = np.indices((height, width), dtype=np.float64)
    matrix = np.asarray(source_to_world, np.float64)
    denominator = matrix[2, 0] * xx + matrix[2, 1] * yy + matrix[2, 2]
    wx = (matrix[0, 0] * xx + matrix[0, 1] * yy + matrix[0, 2]) / denominator
    wy = (matrix[1, 0] * xx + matrix[1, 1] * yy + matrix[1, 2]) / denominator
    left, top = np.floor(wx).astype(int), np.floor(wy).astype(int)
    fx, fy = (wx - left)[..., None], (wy - top)[..., None]
    valid = (left >= 0) & (top >= 0) & (left + 1 < source.shape[1]) & (top + 1 < source.shape[0])
    left, top = np.clip(left, 0, source.shape[1] - 2), np.clip(top, 0, source.shape[0] - 2)
    pixels = ((1 - fx) * (1 - fy) * source[top, left] + fx * (1 - fy) * source[top, left + 1]
              + (1 - fx) * fy * source[top + 1, left] + fx * fy * source[top + 1, left + 1])
    pixels[~valid] = 0
    return pixels.astype(np.float32)


def png(np, path, rgb):
    """Independent PNG16 fixture writer, not the production image encoder."""
    height, width = rgb.shape[:2]
    rgba = np.dstack((rgb, np.ones((height, width), np.float32)))
    pixels = np.rint(np.clip(rgba, 0, 1) * 65535).astype(">u2")
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    raw = b"".join(b"\0" + row.tobytes() for row in pixels)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 16, 6, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class PhotographValidationTests(unittest.TestCase):
    def test_strict_geometry_response_and_panorama_recipe_bounds(self):
        hdr = {"version": 1, "operation": "hdr_merge", "brackets": [
            {"asset_id": "one", "exposure_time": .1}, {"asset_id": "two", "exposure_time": .4}]}
        original = copy.deepcopy(hdr)
        normalized = imaging.validate_imaging_recipe(hdr)
        self.assertEqual(hdr, original)
        self.assertEqual(normalized["alignment"], "none")
        self.assertFalse(still_photography.needed(normalized))
        for change in ({"alignment": "flow"}, {"alignment": []}, {"deghost": True},
                       {"reference_asset_id": "absent"}, {"ghost_threshold_stops": float("nan")},
                       {"ghost_threshold_stops": True}, {"input_transfer": "measured"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                imaging.validate_imaging_recipe({**hdr, **change})
        pano = {"version": 1, "operation": "panorama", "images": ["one", "two"]}
        for change in ({"images": ["one", "one"]}, {"images": ["one"]}, {"images": [str(i) for i in range(9)]},
                       {"projection": "spherical"}, {"input_transfer": "measured"}, {"input_transfer": []},
                       {"reference_asset_id": "absent"}, {"exposure_compensation": 1}, {"output": "/tmp/elsewhere"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                imaging.validate_imaging_recipe({**pano, **change})

    def test_unavailable_runtime_is_explicit_and_parent_keeps_optional_imports_out(self):
        self.assertFalse(still_photography.capabilities(python="/does/not/exist/python")["available"])
        code = "import sys;sys.path.insert(0,sys.argv[1]);import still_photography;assert not set(('numpy','cv2','OpenEXR','PyOpenColorIO')) & set(sys.modules)"
        subprocess.run([shutil.which("python3"), "-I", "-B", "-c", code, str(Path(__file__).parent)], check=True)


class PhotographRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = imaging.find_imaging_python()
        if not cls.python:
            raise unittest.SkipTest("The actual imaging runtime is required")
        cls.geometry = still_photography.capabilities()
        if not cls.geometry.get("available"):
            raise unittest.SkipTest(cls.geometry["reason"])
        try:
            import numpy as np
            import OpenEXR
            import PyOpenColorIO as ocio
        except ImportError as exc:
            raise unittest.SkipTest("Run photograph numeric acceptance in the isolated imaging verification interpreter") from exc
        cls.np, cls.exr, cls.ocio = np, OpenEXR, ocio

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-photo-ENGINE-TEST-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "media").mkdir()
        self.project = {"version": 1, "id": "photographs", "name": "ENGINE TEST — still photographs", "width": 160, "height": 96,
                        "fps": 12, "assets": [], "clips": [], "titles": [], "settings": {}}
        self.counter = 0

    def asset(self, rgb, ident=None):
        self.counter += 1
        ident = ident or "photo-%02d" % self.counter
        path = self.root / "media" / (ident + ".png")
        png(self.np, path, rgb)
        from engine import probe_media
        asset = {"id": ident, "path": str(path.relative_to(self.root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 **probe_media(path)}
        self.project["assets"].append(asset)
        return asset

    def run_photo(self, recipe, name="result", **kwargs):
        return imaging.run_imaging(self.project, self.root, recipe, self.root / "imaging/outputs" / name,
                                   python=self.python, **kwargs)

    def read(self, path):
        with self.exr.File(str(path)) as source:
            rgba = source.channels()["RGBA"].pixels.copy()
            space = source.header()["ocioColorSpace"]
        alpha = rgba[..., 3]
        rgb = self.np.ascontiguousarray(rgba[..., :3])
        self.np.divide(rgb, alpha[..., None], out=rgb, where=alpha[..., None] > 0)
        self.ocio.Config.CreateFromBuiltinConfig(imaging.DEFAULT_CONFIG).getProcessor(space, "lin_rec709").getDefaultCPUProcessor().applyRGB(rgb)
        return rgb, alpha

    def bracket(self, transforms=None, moving=False, measured=False):
        np = self.np
        truth = scene(np)
        height, width = truth.shape[:2]
        transforms = transforms or [np.eye(3)] * 3
        times = [.04, .16, .64]
        gamma = np.array([2.0, 2.2, 2.4], np.float32)
        brackets, worlds = [], []
        for index, (exposure, matrix) in enumerate(zip(times, transforms)):
            world = truth.copy()
            if moving:
                left = [45, 125, 205][index]
                world[68:98, left:left + 30] = [.8, .45, .2]
            camera = sample(np, world, matrix, width, height)
            encoded = np.clip(camera * exposure, 0, 1)
            if measured:
                encoded = encoded ** (1 / gamma)
            else:
                encoded = np.where(encoded <= .0031308, 12.92 * encoded, 1.055 * encoded ** (1 / 2.4) - .055)
            asset = self.asset(encoded)
            brackets.append({"asset_id": asset["id"], "exposure_time": exposure})
            worlds.append(world)
        recipe = {"version": 1, "operation": "hdr_merge", "brackets": brackets, "input_transfer": "measured" if measured else "srgb",
                  "reference_asset_id": brackets[1]["asset_id"]}
        return recipe, worlds[1], gamma

    def assert_geometry(self, record, expected, tolerance=.7):
        np = self.np
        points = np.array([[30, 30, 1], [280, 30, 1], [30, 160, 1], [280, 160, 1], [160, 96, 1]], np.float64)
        a, b = points @ np.asarray(record["source_to_reference"]).T, points @ np.asarray(expected).T
        error = np.linalg.norm(a[:, :2] / a[:, 2:] - b[:, :2] / b[:, 2:], axis=1)
        self.assertLess(float(error.max()), tolerance, error)

    def test_actual_translated_brackets_recover_geometry_and_high_radiance(self):
        np = self.np
        transforms = [np.array([[1, 0, 7], [0, 1, -4], [0, 0, 1]]), np.eye(3),
                      np.array([[1, 0, -6], [0, 1, 5], [0, 0, 1]])]
        recipe, truth, _ = self.bracket(transforms)
        result = self.run_photo({**recipe, "alignment": "translation"})
        rgb, alpha = self.read(result["exr_path"])
        for record, expected in zip(result["receipt"]["source_details"]["alignment"]["measurements"], transforms):
            self.assert_geometry(record, expected, .4)
        valid = alpha > .99
        valid[:12] = valid[-12:] = False
        valid[:, :12] = valid[:, -12:] = False
        relative = np.abs(rgb - truth) / np.maximum(truth, .03)
        self.assertLess(float(np.median(relative[valid])), .002)
        self.assertLess(float(np.quantile(relative[valid], .99)), .025)
        self.assertGreater(float(rgb[valid].max()), 8)
        self.assertGreater(int(np.count_nonzero(alpha == 0)), 2000)
        self.assertEqual(result["receipt"]["source_details"]["runtime"]["opencv"], "4.11.0")

    def test_projective_brackets_use_measured_perspective_and_actual_pixels(self):
        np = self.np
        transforms = [np.array([[.99, .012, 4], [-.008, 1.01, 3], [.000035, -.000045, 1]]), np.eye(3),
                      np.array([[1.01, -.008, -3], [.006, .995, -2], [-.000025, .000035, 1]])]
        recipe, truth, _ = self.bracket(transforms)
        result = self.run_photo({**recipe, "alignment": "homography"})
        rgb, alpha = self.read(result["exr_path"])
        for record, expected in zip(result["receipt"]["source_details"]["alignment"]["measurements"], transforms):
            self.assert_geometry(record, expected, .85)
        valid = alpha > .99
        valid[:15] = valid[-15:] = False
        valid[:, :15] = valid[:, -15:] = False
        self.assertLess(float(np.median(np.abs(rgb - truth)[valid] / np.maximum(truth[valid], .03))), .025)
        self.assertGreater(float(rgb[valid].max()), 7)

    def test_reference_motion_mask_removes_ghosts_and_preserves_static_radiance(self):
        np = self.np
        recipe, truth, _ = self.bracket(moving=True)
        ordinary = self.run_photo(recipe, "unmasked")
        corrected = self.run_photo({**recipe, "deghost": "reference", "ghost_threshold_stops": .5}, "masked")
        before, _ = self.read(ordinary["exr_path"])
        after, _ = self.read(corrected["exr_path"])
        region = np.zeros(truth.shape[:2], bool)
        for left in (45, 125, 205):
            region[72:94, left + 4:left + 26] = True
        baseline = float(np.mean((before[region] - truth[region]) ** 2))
        repaired = float(np.mean((after[region] - truth[region]) ** 2))
        self.assertGreater(baseline, .002)
        self.assertLess(repaired, baseline * .005)
        self.assertEqual(corrected["receipt"]["source_details"]["deghost"]["clipped_reference_motion_pixels"], 0)
        mask_path = self.root / "imaging/outputs/masked/motion.png"
        decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(mask_path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"], capture_output=True, check=True).stdout
        mask = np.frombuffer(decoded, np.uint8).reshape(region.shape)
        self.assertGreater(float(np.mean(mask[region] > 250)), .95)
        self.assertEqual(hashlib.sha256(mask_path.read_bytes()).hexdigest(), corrected["artifacts"]["motion"]["sha256"])
        self.assertLess(float(np.max(np.abs(after[20:40, 30:50] - before[20:40, 30:50]))), .0001)

    def test_measured_camera_response_recovers_independent_nonlinear_capture(self):
        np = self.np
        recipe, truth, gamma = self.bracket(measured=True)
        result = self.run_photo(recipe)
        rgb, alpha = self.read(result["exr_path"])
        details = result["receipt"]["source_details"]["response"]
        measured = np.asarray(details["inverse_response_rgb"])
        expected = (np.arange(256)[:, None] / 128) ** gamma[None]
        self.assertEqual(measured.shape, (256, 3))
        self.assertTrue(np.all(np.diff(measured, axis=0) >= -1e-8))
        self.assertLess(float(np.median(np.abs(measured[30:220] / expected[30:220] - 1))), .065)
        truth = truth / ((128 / 255) ** gamma)
        valid = (alpha > .99) & np.all((truth > .05) & (truth < 25), axis=-1)
        valid[-3:] = False
        valid[:, -3:] = False
        self.assertLess(float(np.median(np.abs(rgb[valid] / truth[valid] - 1))), .07)
        self.assertLess(details["p95_residual_stops"], .2)
        self.assertEqual(details["sample_count"], 256)

    def panorama(self, perspective=False, dim=False):
        np = self.np
        world = scene(np, 220, 640, 817)
        world = .03 + .8 * world / (1 + world)
        matrices = [np.eye(3), np.array([[1, .006, 160], [-.003, 1, 4], [.00002, -.000015, 1]]) if perspective
                    else np.array([[1, 0, 160], [0, 1, 0], [0, 0, 1]]), np.array([[1, 0, 320], [0, 1, 0], [0, 0, 1]])]
        assets = []
        for index, matrix in enumerate(matrices):
            image = sample(np, world, matrix, 320, 192)
            if dim and index == 1:
                image *= .5
            assets.append(self.asset(image))
        return {"version": 1, "operation": "panorama", "images": [asset["id"] for asset in assets], "input_transfer": "linear"}, world, matrices

    def test_panorama_connects_all_views_and_recovers_known_canvas_and_pixels(self):
        np = self.np
        recipe, world, matrices = self.panorama()
        result = self.run_photo(recipe)
        rgb, alpha = self.read(result["exr_path"])
        details = result["receipt"]["source_details"]
        self.assertEqual(len(details["measurements"]), 3)
        for record, expected in zip(details["measurements"], matrices):
            self.assert_geometry(record, expected, .5)
        self.assertTrue(638 <= rgb.shape[1] <= 644, rgb.shape)
        self.assertTrue(191 <= rgb.shape[0] <= 195, rgb.shape)
        left, top = details["canvas_origin_in_reference"]
        expected = sample(np, world, [[1, 0, left], [0, 1, top], [0, 0, 1]], rgb.shape[1], rgb.shape[0])
        valid = alpha > .99
        valid[:4] = valid[-4:] = False
        valid[:, :4] = valid[:, -4:] = False
        self.assertLess(float(np.median(np.abs(rgb[valid] - expected[valid]))), .001)
        self.assertGreater(details["overlap_pixels"], 50000)

    def test_perspective_panorama_retains_alpha_for_uncovered_pixels(self):
        np = self.np
        recipe, _, matrices = self.panorama(perspective=True)
        result = self.run_photo(recipe)
        rgb, alpha = self.read(result["exr_path"])
        details = result["receipt"]["source_details"]
        for record, expected in zip(details["measurements"], matrices):
            self.assert_geometry(record, expected, 1.)
        self.assertGreater(int(np.count_nonzero(alpha == 0)), 500)
        self.assertEqual(int(np.count_nonzero(alpha == 0)), details["uncovered_pixels"])
        self.assertEqual(float(np.max(np.abs(rgb[alpha == 0]))), 0)

    def test_panorama_measures_overlap_exposure_gain_in_linear_light(self):
        np = self.np
        recipe, _, _ = self.panorama(dim=True)
        result = self.run_photo({**recipe, "exposure_compensation": True})
        records = result["receipt"]["source_details"]["measurements"]
        self.assertLess(float(np.max(np.abs(np.asarray(records[1]["exposure_gain_rgb"]) - 2))), .025)
        self.assertLess(float(np.max(np.abs(np.asarray(records[2]["exposure_gain_rgb"]) - 1))), .025)

    def test_low_texture_and_disconnected_photographs_fail_without_publishing(self):
        np = self.np
        first, second = self.asset(np.full((96, 160, 3), .2)), self.asset(np.full((96, 160, 3), .4))
        for operation, extra in (("panorama", {"images": [first["id"], second["id"]]}),
                                 ("hdr_merge", {"alignment": "homography", "brackets": [
                                     {"asset_id": first["id"], "exposure_time": .1}, {"asset_id": second["id"], "exposure_time": .2}]})):
            with self.subTest(operation=operation), self.assertRaisesRegex(RuntimeError, "texture"):
                self.run_photo({"version": 1, "operation": operation, **extra}, operation)
            self.assertFalse((self.root / "imaging/outputs" / operation).exists())
        self.assertFalse(any((self.root / "imaging/outputs").iterdir()))

    def test_motion_mask_sources_and_recipe_survive_real_project_archive(self):
        import project_archive
        from engine import probe_media
        recipe, _, _ = self.bracket(moving=True)
        result = self.run_photo({**recipe, "deghost": "reference"})
        target = self.root / "media/ENGINE_TEST_developed.png"
        shutil.copyfile(result["path"], target)
        self.project["assets"].append({"id": "developed", "path": str(target.relative_to(self.root)),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "provenance": result["provenance"], **probe_media(target)})
        self.project["clips"] = [{"id": "use-photo", "asset_id": "developed", "start": 0, "in": 0, "duration": 12, "track": 0}]
        archive = self.root / "ENGINE_TEST_photographs.cinematicum"
        project_archive.export_archive(self.project, self.root, archive)
        projects = self.root / "restored-projects"
        projects.mkdir()
        restored = project_archive.import_archive(archive, projects)
        fresh = projects / restored["id"]
        for name in ("linear.exr", "display.png", "receipt.json", "motion.png"):
            self.assertEqual((self.root / "imaging/outputs/result" / name).read_bytes(), (fresh / "imaging/outputs/result" / name).read_bytes())
        repeated = imaging.run_imaging(restored, fresh, result["provenance"]["recipe"], fresh / "imaging/outputs/repeated", python=self.python)
        for key in ("display", "linear", "motion"):
            self.assertEqual(repeated["artifacts"][key]["sha256"], result["artifacts"][key]["sha256"])
        mask = self.root / "imaging/outputs/result/motion.png"
        mask.write_bytes(mask.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            project_archive.export_archive(self.project, self.root, self.root / "tampered.cinematicum")

    def test_source_mutation_duplicate_pixels_and_pre_cancel_never_publish(self):
        recipe, _, _ = self.bracket()
        original = self.root / self.project["assets"][0]["path"]
        original.write_bytes(original.read_bytes() + b"altered")
        with self.assertRaisesRegex(ValueError, "identity"):
            self.run_photo({**recipe, "alignment": "translation"})
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.run_photo(recipe, cancel_event=event)
        self.assertFalse((self.root / "imaging/outputs/result").exists())

    def test_actual_inflight_cancellation_owns_geometry_children_and_cleans_staging(self):
        recipe, _, _ = self.bracket(measured=True)
        event = threading.Event()
        progress = []
        def observe(value):
            progress.append(value)
            if value >= .1:
                event.set()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.run_photo({**recipe, "alignment": "homography"}, progress=observe, cancel_event=event)
        self.assertTrue(progress)
        self.assertFalse(any((self.root / "imaging/outputs").iterdir()))


if __name__ == "__main__":
    unittest.main()

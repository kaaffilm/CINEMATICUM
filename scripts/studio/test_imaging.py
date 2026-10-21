"""Identity, real OCIO/EXR pixels, bracket radiance and optional camera RAW tests.

Set CINEMATICUM_IMAGING_PYTHON to the isolated interpreter. RAW acceptance also
uses CINEMATICUM_RAW_TEST_FILE: an independently obtained camera RAW fixture.
The tests never download fixtures or install packages themselves.
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
from unittest.mock import patch
import zlib

import imaging


def png16(path, rgb, width=32, height=24, alpha=1):
    """Independent standard-library fixture encoder, all rows use filter zero."""
    rgba = tuple(round(max(0, min(1, v)) * 65535) for v in (*rgb, alpha))
    row = struct.pack(">4H", *rgba) * width
    def chunk(tag, value):
        return struct.pack(">I", len(value)) + tag + value + struct.pack(">I", zlib.crc32(tag + value) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 16, 6, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress((b"\x00" + row) * height)) + chunk(b"IEND", b""))


def read_generated_png16(path):
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("not a PNG")
    offset, compressed, header = 8, bytearray(), None
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        tag, value = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + length]
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", value)
        if tag == b"IDAT":
            compressed.extend(value)
        offset += 12 + length
    if header[2:] != (16, 6, 0, 0, 0):
        raise AssertionError("not a 16-bit RGBA still")
    pixels = zlib.decompress(compressed)
    if pixels[0] != 0:
        raise AssertionError("unexpected test PNG row filter")
    return [v / 65535 for v in struct.unpack_from(">4H", pixels, 1)]


class ImagingValidationTests(unittest.TestCase):
    def test_runtime_is_optional_and_missing_is_explicit(self):
        result = imaging.imaging_capabilities(python="/does/not/exist/python")
        self.assertFalse(result["available"])
        self.assertEqual(result["operations"], [])
        self.assertIn("not installed", result["reason"])

    def test_strict_recipe_shapes_and_numeric_bounds(self):
        base = {"version": 1, "operation": "ocio", "asset_id": "one", "input_space": "ACEScg"}
        normal = imaging.validate_imaging_recipe(base)
        self.assertEqual(normal["display"], imaging.DEFAULT_DISPLAY)
        for change in ({"version": True}, {"operation": []}, {"exposure": float("nan")},
                       {"exposure": True}, {"exposure": 21}, {"asset_id": "../../elsewhere"},
                       {"input_space": ""}, {"script": "print('untrusted')"}, {"display": "Rec.2100-PQ - Display"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                imaging.validate_imaging_recipe({**base, **change})
        self.assertNotIn("config", base)

    def test_hdr_requires_distinct_exposures_and_image_identities(self):
        base = {"version": 1, "operation": "hdr_merge", "brackets": [{"asset_id": "one", "exposure_time": .01}, {"asset_id": "two", "exposure_time": .04}]}
        self.assertEqual(imaging.validate_imaging_recipe(base)["input_transfer"], "srgb")
        for brackets in ([base["brackets"][0]], [base["brackets"][0]] * 2,
                         [{"asset_id": "one", "exposure_time": 1}, {"asset_id": "two", "exposure_time": 1}],
                         [{"asset_id": "one", "exposure_time": 0}, base["brackets"][1]],
                         [{"asset_id": "one", "exposure_time": .01, "path": "/tmp/x"}, base["brackets"][1]]):
            with self.subTest(brackets=brackets), self.assertRaises(ValueError):
                imaging.validate_imaging_recipe({**base, "brackets": brackets})
        with self.assertRaises(ValueError):
            imaging.validate_imaging_recipe({**base, "input_transfer": []})

    def test_raw_parameters_are_bounded_and_no_filename_parameters_exist(self):
        base = {"version": 1, "operation": "raw", "source_id": "a" * 64}
        normal = imaging.validate_imaging_recipe(base)
        self.assertEqual(normal["white_balance"], "camera")
        for change in ({"half_size": 1}, {"user_wb": [1, 0, 1, 1]}, {"demosaic": "AMAZE"},
                       {"highlight": "arbitrary"}, {"bad_pixels": "/tmp/map"}, {"source_id": "b" * 63}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                imaging.validate_imaging_recipe({**base, **change})

    def test_parent_module_does_not_import_optional_dependencies(self):
        code = "import sys;sys.path.insert(0,sys.argv[1]);import imaging;print([x for x in ('numpy','PyOpenColorIO','rawpy','OpenEXR') if x in sys.modules])"
        result = subprocess.run([shutil.which("python3"), "-I", "-c", code, str(Path(__file__).parent)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "[]")


class ImagingRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = imaging.find_imaging_python()
        if not cls.python:
            raise unittest.SkipTest("The optional isolated imaging runtime is not installed")
        capability = imaging.imaging_capabilities(cls.python)
        if not capability["available"] or not shutil.which("ffmpeg"):
            raise unittest.SkipTest(capability.get("reason", "Imaging codecs are unavailable"))
        cls.catalog = imaging.imaging_catalog(python=cls.python)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-imaging-TEST-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "media").mkdir()
        self.project = {"assets": []}
        self.counter = 0

    def runtime(self, code, *args):
        result = subprocess.run([self.python, "-I", "-c", code, *map(str, args)], capture_output=True, text=True, timeout=30,
                                env={**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"})
        if result.returncode:
            self.fail(result.stderr + result.stdout)
        return json.loads(result.stdout)

    def asset(self, rgb=(.25, .5, .75), width=32, height=24, alpha=1):
        self.counter += 1
        ident = "fixture-%d" % self.counter
        path = self.root / "media" / (ident + ".png")
        png16(path, rgb, width, height, alpha)
        return self.admit(path, ident)

    def admit(self, path, ident):
        asset = {"id": ident, "name": path.name, "kind": "image", "path": str(path.relative_to(self.root)),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size}
        self.project["assets"].append(asset)
        return asset

    def render(self, recipe, output="result", **kwargs):
        return imaging.run_imaging(self.project, self.root, recipe, self.root / "imaging/outputs" / output,
                                   python=self.python, **kwargs)

    def recipe(self, asset, **changes):
        return {"version": 1, "operation": "ocio", "asset_id": asset["id"], "config": self.catalog["config"],
                "display": self.catalog["default_display"], "view": self.catalog["default_view"],
                "input_space": self.catalog["default_input_space"], **changes}

    def exr_sample(self, path):
        return self.runtime("import OpenEXR as E,json,sys;f=E.File(sys.argv[1]);a=f.channels()['RGBA'].pixels;h=f.header();print(json.dumps({'pixel':a[0,0].tolist(),'dtype':str(a.dtype),'shape':list(a.shape),'space':h.get('ocioColorSpace'),'alpha':h.get('cinematicumAlpha'),'chromaticities':h.get('chromaticities')}))", path)

    def test_real_builtin_catalog_and_external_config_rejection(self):
        self.assertEqual(self.catalog["scene_linear"], "ACEScg")
        self.assertIn("ARRI LogC4", [s["name"] for s in self.catalog["color_spaces"]])
        self.assertNotIn("Raw", self.catalog["displays"][0]["views"])
        for config in ("/tmp/config.ocio", "https://example.org/config.ocio", "ocio://default"):
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "built-in"):
                imaging.imaging_catalog(config, self.python)

    def test_float_exr_roundtrip_keeps_negative_superwhite_and_alpha_metadata(self):
        path = self.root / "media" / "linear.exr"
        self.runtime("import OpenEXR as E,numpy as n,json,sys;a=n.empty((24,32,4),n.float32);a[:]=[-.25,.09,2,.5];E.File({'type':E.scanlineimage},{'RGBA':a}).write(sys.argv[1]);print('{}')", path)
        asset = self.admit(path, "float-input")
        result = self.render(self.recipe(asset, input_space="ACEScg", exposure=1))
        sample = self.exr_sample(result["exr_path"])
        # Standard EXR is premultiplied. Input unassociated RGB is -.5,.18,4;
        # +1 stop followed by re-association gives -.5,.18,4 at alpha=.5.
        for actual, expected in zip(sample["pixel"], (-.5, .18, 4, .5)):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertEqual(sample["dtype"], "float32")
        self.assertEqual(sample["space"], "ACEScg")
        self.assertEqual(sample["alpha"], "premultiplied")
        self.assertAlmostEqual(sample["chromaticities"][0], .713, places=6)
        self.assertEqual(result["receipt"]["linear_statistics"]["min"], -1)
        self.assertEqual(result["receipt"]["linear_statistics"]["max"], 8)
        self.assertAlmostEqual(read_generated_png16(result["path"])[3], .5, delta=1 / 65535)

    def test_png_display_matches_independent_ocio_processor_and_view_changes_pixels(self):
        asset = self.asset((.25, .5, .75))
        result = self.render(self.recipe(asset))
        reference = self.runtime("import PyOpenColorIO as O,numpy as n,json,sys;c=O.Config.CreateFromBuiltinConfig(sys.argv[1]);p=n.array([[.25,.5,.75]],n.float32);c.getProcessor(sys.argv[2],sys.argv[3],sys.argv[4],O.TRANSFORM_DIR_FORWARD).getDefaultCPUProcessor().applyRGB(p);print(json.dumps(p[0].tolist()))", self.catalog["config"], self.catalog["default_input_space"], self.catalog["default_display"], self.catalog["default_view"])
        actual = read_generated_png16(result["path"])
        for expected, value in zip(reference, actual[:3]):
            self.assertAlmostEqual(max(0, min(1, expected)), value, delta=.00015)
        alternate = self.render(self.recipe(asset, view="Un-tone-mapped"), "alternate")
        self.assertNotEqual(result["artifacts"]["display"]["sha256"], alternate["artifacts"]["display"]["sha256"])
        self.assertEqual(result["artifacts"]["linear"]["sha256"], alternate["artifacts"]["linear"]["sha256"])

    def test_developed_display_has_same_correct_transfer_in_clip_and_compositor_source(self):
        from engine import probe_media
        from frame_preview import render_frame
        import copy

        source = self.asset((.25, .5, .75), 160, 90)
        result = self.render(self.recipe(source, view="Un-tone-mapped", exposure=.5))
        display_path = self.root / "media" / "developed.png"
        shutil.copyfile(result["path"], display_path)
        display = self.admit(display_path, "developed")
        display.update(probe_media(display_path), provenance=result["provenance"])
        host = self.asset((0, 0, 0), 160, 90)
        host.update(probe_media(self.root / host["path"]))
        clip = {"id": "edit", "asset_id": display["id"], "start": 0, "in": 0, "duration": 2, "track": 0,
                "color_pipeline": {"version": 1, "enabled": True, "input_transfer": "srgb", "input_primaries": "rec709"}}
        project = {"version": 1, "id": "imaging-transfer", "name": "ENGINE TEST — imaging transfer",
                   "width": 160, "height": 90, "fps": 12, "assets": [display, host],
                   "clips": [clip], "titles": [], "settings": {}}

        def pixels(value, filename):
            path = self.root / filename
            render_frame(value, self.root, 0, path)
            decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-i", str(path),
                                      "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"],
                                     capture_output=True, check=True, timeout=10).stdout
            return list(decoded[(45 * 160 + 80) * 3:(45 * 160 + 80) * 3 + 3])

        direct = pixels(project, "direct.png")
        through_node = copy.deepcopy(project)
        through_node["clips"][0].update(asset_id=host["id"], color_pipeline=None, compositor={
            "version": 1, "nodes": [
                {"id": "source", "type": "source", "inputs": [], "params": {}},
                {"id": "developed", "type": "media_source", "inputs": [], "params": {
                    "asset_id": display["id"], "source_in": 0, "offset": 0, "duration": 2, "outside": "hold"}}],
            "output": "developed"})
        external = pixels(through_node, "node.png")
        encoded = read_generated_png16(display_path)[:3]
        # Reference uses the standard piecewise curves, independently of the
        # production compiler/OCIO: a display view must not be run a second time.
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in encoded]
        expected = [round(255 * (4.5 * v if v < .018 else 1.099 * v ** .45 - .099)) for v in linear]
        for actual in (direct, external):
            self.assertEqual(len(actual), 3)
            self.assertLessEqual(max(abs(a - b) for a, b in zip(actual, expected)), 4, (actual, expected))
        self.assertLessEqual(max(abs(a - b) for a, b in zip(direct, external)), 2, (direct, external))
        unmarked = copy.deepcopy(through_node)
        del unmarked["assets"][0]["provenance"]
        untouched = pixels(unmarked, "unmarked.png")
        self.assertGreater(max(abs(a - b) for a, b in zip(untouched, external)), 8,
                           "Unmarked input must not acquire imaging-specific transfer conversion")

    def test_hdr_recovers_known_radiance_over_clipped_brackets(self):
        radiance = (.12, 2., 10.)
        exposures = (.025, .1, .4, 1.)
        brackets = []
        for exposure in exposures:
            encoded = []
            for value in radiance:
                linear = min(1, value * exposure)
                encoded.append(12.92 * linear if linear <= .0031308 else 1.055 * linear ** (1 / 2.4) - .055)
            asset = self.asset(encoded)
            brackets.append({"asset_id": asset["id"], "exposure_time": exposure})
        result = self.render({"version": 1, "operation": "hdr_merge", "brackets": brackets, "input_transfer": "srgb"})
        recovered = self.runtime("import OpenEXR as E,PyOpenColorIO as O,numpy as n,json,sys;f=E.File(sys.argv[1]);a=n.ascontiguousarray(f.channels()['RGBA'].pixels[...,:3]);c=O.Config.CreateFromBuiltinConfig(sys.argv[2]);c.getProcessor('ACEScg','lin_rec709').getDefaultCPUProcessor().applyRGB(a);print(json.dumps(a[0,0].tolist()))", result["exr_path"], self.catalog["config"])
        for actual, expected in zip(recovered, radiance):
            self.assertAlmostEqual(actual, expected, delta=.002)
        self.assertGreater(result["receipt"]["linear_statistics"]["max"], 8)
        self.assertEqual(result["receipt"]["source_details"]["unrecovered_pixels"], 0)
        self.assertEqual(result["receipt"]["source_details"]["radiance_units"], "relative linear Rec.709 signal per second")

    def test_exif_orientation_is_shared_by_real_ocio_and_hdr_jobs(self):
        from test_media_orientation import exif_jpegs, codec
        ffmpeg = shutil.which("ffmpeg")
        paths, width, height = exif_jpegs(self.root / "media", ffmpeg)
        tagged = self.admit(paths[6], "portrait-exif")
        normal_path, dark_path = self.root / "media/portrait-normal.png", self.root / "media/portrait-dark.png"
        for path, filters in ((normal_path, []), (dark_path, ["-vf", "lutrgb=r=val*0.5:g=val*0.5:b=val*0.5"])):
            codec([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(paths[6]), *filters,
                   "-frames:v", "1", "-pix_fmt", "rgba64be", "-threads", "1", str(path)])
        normal, dark = self.admit(normal_path, "portrait-normal"), self.admit(dark_path, "portrait-dark")
        first = self.render(self.recipe(tagged), "oriented-ocio")
        second = self.render(self.recipe(normal), "normalized-ocio")
        self.assertEqual((first["receipt"]["width"], first["receipt"]["height"]), (height, width))
        self.assertEqual(first["receipt"]["source_details"]["exif_orientation"], 6)
        comparison = "import OpenEXR as E,numpy as n,json,sys;a=E.File(sys.argv[1]).channels()['RGBA'].pixels;b=E.File(sys.argv[2]).channels()['RGBA'].pixels;print(json.dumps({'a_shape':list(a.shape),'b_shape':list(b.shape),'difference':float(n.max(n.abs(a-b)))}))"
        checked = self.runtime(comparison, first["exr_path"], second["exr_path"])
        self.assertEqual(checked["difference"], 0)
        self.assertEqual(checked["a_shape"], [width, height, 4])
        # Same displayed bracket, once encoded with EXIF and once normalized.
        # A rotated JPEG must merge in the same coordinate system as PNGs.
        hdr_results = []
        for index, source in enumerate((tagged, normal)):
            hdr_results.append(self.render({"version": 1, "operation": "hdr_merge", "input_transfer": "linear",
                "brackets": [{"asset_id": source["id"], "exposure_time": 1.0},
                             {"asset_id": dark["id"], "exposure_time": .5}]}, "hdr-orientation-%d" % index))
        checked = self.runtime(comparison, hdr_results[0]["exr_path"], hdr_results[1]["exr_path"])
        self.assertEqual(checked["difference"], 0)
        self.assertEqual(checked["a_shape"], [width, height, 4])

    def test_hdr_reports_unrecoverable_highlights_instead_of_inventing_detail(self):
        first, second = self.asset((1, .4, 0)), self.asset((1, .7, 0))
        result = self.render({"version": 1, "operation": "hdr_merge", "input_transfer": "linear", "brackets": [
            {"asset_id": first["id"], "exposure_time": .1}, {"asset_id": second["id"], "exposure_time": .2}]})
        info = result["receipt"]["source_details"]
        self.assertEqual(info["all_saturated_channels"], 32 * 24)
        self.assertEqual(info["all_dark_channels"], 32 * 24)
        self.assertEqual(info["unrecovered_channels"], 2 * 32 * 24)

    def test_hdr_dimension_and_alpha_mismatches_fail(self):
        first, second = self.asset(), self.asset(width=34)
        base = {"version": 1, "operation": "hdr_merge", "brackets": [
            {"asset_id": first["id"], "exposure_time": .1}, {"asset_id": second["id"], "exposure_time": .2}]}
        with self.assertRaisesRegex(RuntimeError, "identical image dimensions"):
            self.render(base)
        third = self.asset((.2, .3, .4), alpha=.5)
        base["brackets"][1]["asset_id"] = third["id"]
        with self.assertRaisesRegex(RuntimeError, "opaque"):
            self.render(base)

    def test_input_tamper_missing_symlink_and_duplicate_content_are_rejected(self):
        asset = self.asset()
        recipe = self.recipe(asset)
        path = self.root / asset["path"]
        original = path.read_bytes()
        path.write_bytes(original + b"tampered")
        with self.assertRaisesRegex(ValueError, "identity"):
            self.render(recipe)
        path.unlink()
        with self.assertRaises(ValueError):
            self.render(recipe)
        elsewhere = self.root / "elsewhere.png"
        elsewhere.write_bytes(original)
        path.symlink_to(elsewhere)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            self.render(recipe)
        path.unlink()
        path.write_bytes(original)
        duplicate = self.asset()
        with self.assertRaisesRegex(ValueError, "identical image content"):
            self.render({"version": 1, "operation": "hdr_merge", "brackets": [
                {"asset_id": asset["id"], "exposure_time": .1}, {"asset_id": duplicate["id"], "exposure_time": .2}]})

    def test_atomic_receipts_and_existing_output_are_immutable(self):
        asset = self.asset()
        result = self.render(self.recipe(asset))
        directory = self.root / "imaging/outputs/result"
        self.assertEqual({p.name for p in directory.iterdir()}, imaging.ARTIFACT_NAMES)
        self.assertEqual(result["receipt"]["inputs"][0]["sha256"], asset["sha256"])
        for value in result["artifacts"].values():
            self.assertEqual(hashlib.sha256((directory / value["filename"]).read_bytes()).hexdigest(), value["sha256"])
        with self.assertRaisesRegex(ValueError, "overwritten"):
            self.render(self.recipe(asset))
        self.assertFalse(any(p.name.startswith(".building-") for p in directory.parent.iterdir()))

    def test_running_job_cancellation_cleans_unpublished_artifacts(self):
        asset = self.asset(width=800, height=600)
        event = threading.Event()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.render(self.recipe(asset), cancel_event=event, progress=lambda _: event.set())
        self.assertFalse((self.root / "imaging/outputs/result").exists())
        self.assertEqual(list((self.root / "imaging/outputs").iterdir()), [])

    def test_invalid_raw_is_not_admitted(self):
        incoming = self.root / "upload.nef"
        incoming.write_bytes(b"not camera sensor data")
        with self.assertRaises(ValueError):
            imaging.import_raw_source(self.root, incoming, "invalid.nef", self.python)
        self.assertEqual(imaging.list_raw_sources(self.root), [])

    def test_genuine_camera_raw_development_and_white_balance(self):
        source = os.environ.get("CINEMATICUM_RAW_TEST_FILE")
        if not source or not Path(source).is_file():
            self.skipTest("CINEMATICUM_RAW_TEST_FILE is needed for genuine camera fixture acceptance")
        original = Path(source)
        incoming = self.root / ("upload" + original.suffix)
        shutil.copyfile(original, incoming)
        descriptor = imaging.import_raw_source(self.root, incoming, original.name, self.python)
        self.assertEqual(descriptor["sha256"], hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertEqual(imaging.list_raw_sources(self.root), [descriptor])
        recipe = {"version": 1, "operation": "raw", "source_id": descriptor["id"], "half_size": True,
                  "demosaic": "AHD", "white_balance": "daylight", "highlight": "clip"}
        developed = self.render(recipe)
        self.assertEqual(developed["receipt"]["versions"]["libraw"], descriptor["metadata"]["libraw"])
        self.assertGreater(developed["receipt"]["width"], 100)
        self.assertGreater(developed["receipt"]["linear_statistics"]["max"], .05)
        reference = self.runtime("import rawpy,PyOpenColorIO as O,numpy as n,json,sys;r=rawpy.imread(sys.argv[1]);a=r.postprocess(demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,half_size=True,use_camera_wb=False,use_auto_wb=False,output_color=rawpy.ColorSpace.sRGB,output_bps=16,gamma=(1,1),no_auto_bright=True,bright=1,no_auto_scale=False,highlight_mode=rawpy.HighlightMode.Clip).astype(n.float32)/65535;r.close();O.Config.CreateFromBuiltinConfig(sys.argv[2]).getProcessor('lin_rec709','ACEScg').getDefaultCPUProcessor().applyRGB(a);print(json.dumps(a[0,0].tolist()))", original, self.catalog["config"])
        sample = self.exr_sample(developed["exr_path"])
        for actual, expected in zip(sample["pixel"], reference):
            self.assertAlmostEqual(actual, expected, places=6)
        changed = self.render({**recipe, "white_balance": "custom", "user_wb": [3, 1, .6, 1]}, "different-white")
        self.assertNotEqual(developed["artifacts"]["display"]["sha256"], changed["artifacts"]["display"]["sha256"])
        preserved = self.root / descriptor["path"]
        with preserved.open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaisesRegex(ValueError, "identity"):
            self.render(recipe, "tampered-raw")


if __name__ == "__main__":
    unittest.main()

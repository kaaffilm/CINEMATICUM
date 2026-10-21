"""Portable project acceptance, actual decoded picture/sound and hostile ZIPs.

All media fixtures are ENGINE TEST SIGNALS ONLY. Opaque RAW/Blender transport
fixtures are deliberately never represented as a successful camera decode or
Blender render. The optional imaging test uses the actual isolated OCIO worker.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import warnings
import zipfile

import project_archive as package
from adapters import POSITIVE_MARKER
from color_pipeline import import_cube
from engine import probe_media, render_project, validate_project
from scene import default_scene, validate_scene


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def ffmpeg(args):
    return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y",
                           "-filter_complex_threads", "1", "-threads", "1"] + args,
                          capture_output=True, check=True, timeout=45).stdout


def zip_rewrite(source, output, replace=None, extra=(), compression=zipfile.ZIP_STORED):
    replace = replace or {}
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(output, "w", compression=compression) as new:
        for info in old.infolist():
            payload = replace.get(info.filename, old.read(info))
            if payload is not None:
                copied = copy.copy(info)
                copied.compress_type = compression
                new.writestr(copied, payload)
        for info, payload in extra:
            new.writestr(info, payload)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe are required")
class ProjectArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix="cinematicum-ARCHIVE-ENGINE-TEST-")
        cls.fixture = Path(cls.fixture_temp.name) / "project"
        (cls.fixture / "media").mkdir(parents=True)
        (cls.fixture / "exports").mkdir()
        ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=96x64:r=24:d=1", "-f", "lavfi", "-i", "sine=f=880:r=48000:d=1",
                "-c:v", "ffv1", "-c:a", "pcm_s16le", str(cls.fixture / "media/ENGINE_TEST_picture.mkv")])
        ffmpeg(["-f", "lavfi", "-i", "sine=f=440:r=48000:d=1", "-c:a", "pcm_s16le", str(cls.fixture / "media/ENGINE_TEST_sound.wav")])
        for name, color in (("plate", "blue"), ("parked", "lime")):
            ffmpeg(["-f", "lavfi", "-i", f"color=c={color}:s=96x64:r=24:d=1", "-an", "-c:v", "ffv1",
                    str(cls.fixture / f"media/ENGINE_TEST_{name}.mkv")])
        cls.lut = import_cube('TITLE "ENGINE TEST portable LUT"\nLUT_1D_SIZE 2\n0 0 0\n.85 .9 1\n', cls.fixture)
        graph = {"version": 1, "nodes": [
            {"id": "source", "type": "source", "inputs": [], "params": {}},
            {"id": "plate", "type": "media_source", "inputs": [], "params": {"asset_id": "plate", "duration": 8}},
            {"id": "masked", "type": "mask", "inputs": ["plate"],
             "params": {"shape": "rectangle", "x": .75, "y": .5, "width": .5, "height": 1}},
            {"id": "merge", "type": "merge", "inputs": ["source", "masked"], "params": {}},
            {"id": "parked", "type": "media_source", "inputs": [], "params": {"asset_id": "parked", "duration": 8}},
        ], "output": "merge"}
        assets = []
        for name, ext in (("picture", "mkv"), ("sound", "wav"), ("plate", "mkv"), ("parked", "mkv")):
            path = cls.fixture / f"media/ENGINE_TEST_{name}.{ext}"
            assets.append({"id": name, "path": str(path.relative_to(cls.fixture)), "sha256": digest(path), "size": path.stat().st_size})
        cls.base = validate_project({"version": 1, "id": "archive_source", "name": "ENGINE TEST portable project", "revision": 7,
            "fps": 24, "width": 96, "height": 64, "assets": assets,
            "clips": [{"id": "composite", "asset_id": "picture", "track": 0, "start": 0, "in": 0, "duration": 8,
                       "compositor": graph, "grade": {"exposure": .25},
                       "color_pipeline": {"version": 1, "enabled": True, "lut": {"sha256": cls.lut["sha256"], "interpolation": "linear"}}},
                      {"id": "audio", "asset_id": "sound", "track": -1, "start": 0, "in": 0, "duration": 8,
                       "volume": .7, "audio": {"fade_in": 2}}],
            "titles": [], "settings": {"scene": validate_scene(default_scene(96, 64)), "selected": "composite"}}, cls.fixture)
        cls.workflow = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": POSITIVE_MARKER}}}
        write_json(cls.fixture / "workflow.json", cls.workflow)
        write_json(cls.fixture / "project.json", cls.base)
        write_json(cls.fixture / "assets.json", cls.base["assets"])
        cls.reference_archive = Path(cls.fixture_temp.name) / "reference.cinematicum.zip"
        cls.reference_report = package.export_archive(cls.base, cls.fixture, cls.reference_archive)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-ARCHIVE-TEST-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(self.fixture, self.source)
        self.projects = self.root / "fresh-projects"
        self.projects.mkdir()
        self.project = copy.deepcopy(self.base)
        self.output = self.root / "package.cinematicum.zip"

    def restore(self, path=None, **kwargs):
        return package.import_archive(path or self.reference_archive, self.projects, **kwargs)

    def assert_no_import(self):
        self.assertEqual(list(self.projects.iterdir()), [])
        self.assertEqual(list(self.root.glob(".cinematicum-import-*")), [])

    def test_real_fresh_workspace_preserves_every_decoded_frame_and_audio_sample(self):
        before = copy.deepcopy(self.project)
        old_state = (self.source / "project.json").read_bytes()
        # Unrelated exports and regenerateable cache files do not enter packages.
        for relative in ("exports/unrelated.mp4", "previews/cache.mp4", "thumbnails/picture.jpg", "analysis/scopes.json", "jobs.json"):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"ENGINE TEST transient or unrelated output")
        report = package.export_archive(self.project, self.source, self.output)
        restored = self.restore(self.output)
        fresh = self.projects / restored["id"]
        self.assertNotEqual(restored["id"], self.project["id"])
        self.assertEqual(restored["revision"], 1)
        self.assertEqual(restored["assets"], self.project["assets"])
        self.assertEqual(restored["clips"], self.project["clips"])
        self.assertEqual(restored["settings"], self.project["settings"])
        self.assertEqual(self.project, before)
        self.assertEqual((self.source / "project.json").read_bytes(), old_state)
        self.assertEqual(restored["archive_restore"]["archive_sha256"], digest(self.output))
        self.assertEqual(report["sha256"], digest(self.output))
        self.assertEqual(json.loads((fresh / "workflow.json").read_text()), self.workflow)
        names = {item["path"] for item in report["manifest"]["files"]}
        self.assertIn("media/ENGINE_TEST_plate.mkv", names)
        self.assertIn("media/ENGINE_TEST_parked.mkv", names, "Disconnected editable media sources are project state")
        self.assertIn("color/luts/" + self.lut["sha256"] + ".cube", names)
        self.assertNotIn("exports/unrelated.mp4", names)
        self.assertFalse((fresh / "previews").exists())
        outputs = []
        for name, p, directory in (("source", self.project, self.source), ("restored", restored, fresh)):
            if name == "restored":
                self.source.rename(self.root / "original-source-now-offline")
            movie = self.root / ("ENGINE_TEST_" + name + ".mov")
            render_project(p, directory, movie, "prores")
            outputs.append((ffmpeg(["-i", str(movie), "-map", "0:v:0", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"]),
                            ffmpeg(["-i", str(movie), "-map", "0:a:0", "-f", "s16le", "pipe:1"])))
        self.assertEqual(len(outputs[0][0]), 8 * 96 * 64 * 3)
        self.assertGreater(len(outputs[0][1]), 0)
        self.assertEqual(outputs[0], outputs[1], "Relocation must preserve actual decoded RGB and PCM, including nested plates and LUTs")

    def test_two_restores_are_distinct_and_never_overwrite_existing_project(self):
        first, second = self.restore(), self.restore()
        self.assertNotEqual(first["id"], second["id"])
        old = (self.projects / first["id"] / "project.json").read_bytes()
        with patch.object(package.uuid, "uuid4") as identifier:
            identifier.return_value.hex = first["id"]
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.restore()
        self.assertEqual((self.projects / first["id"] / "project.json").read_bytes(), old)
        self.assertEqual(len(list(self.projects.iterdir())), 2)

    def test_empty_project_remains_empty_after_restore(self):
        project = copy.deepcopy(self.project)
        project.update(assets=[], clips=[])
        package.export_archive(project, self.source, self.output)
        restored = self.restore(self.output)
        self.assertEqual(restored["assets"], [])
        self.assertEqual(restored["clips"], [])
        self.assertTrue((self.projects / restored["id"] / "media").is_dir())

    def test_export_refuses_changed_admitted_media_and_preserves_existing_output(self):
        path = self.source / self.project["assets"][0]["path"]
        # A container comment can change without breaking the media decode.
        with path.open("ab") as output:
            output.write(b"changed")
        with self.assertRaisesRegex(ValueError, "recorded size"):
            package.export_archive(self.project, self.source, self.output)
        self.assertFalse(self.output.exists())
        self.output.write_bytes(b"existing archive")
        with self.assertRaises(ValueError):
            package.export_archive(self.base, self.fixture, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing archive")

    def test_hash_identity_is_enforced_even_when_recorded_size_still_matches(self):
        self.project["assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            package.export_archive(self.project, self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".cinematicum-archive-*")), [])

    def test_cancelled_export_and_restore_remove_partial_results(self):
        for kind in ("export", "restore"):
            with self.subTest(kind=kind):
                event = threading.Event()
                def progress(value):
                    if 0 < value < 1:
                        event.set()
                with self.assertRaises(package.ArchiveCancelled):
                    if kind == "export":
                        package.export_archive(self.project, self.source, self.output, event, progress)
                    else:
                        self.restore(cancel_event=event, progress=progress)
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.root.glob(".cinematicum-archive-*")), [])
                self.assert_no_import()

    def test_asset_and_parent_directory_symlinks_are_rejected(self):
        for parent in (False, True):
            with self.subTest(parent=parent):
                source = self.root / ("symlink-project-" + str(parent))
                shutil.copytree(self.fixture, source)
                if parent:
                    shutil.rmtree(source / "media")
                    (source / "media").symlink_to(self.fixture / "media", target_is_directory=True)
                else:
                    asset = self.project["assets"][0]["path"]
                    (source / asset).unlink()
                    (source / asset).symlink_to(self.fixture / asset)
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    package.export_archive(self.project, source, self.output)
                self.assertFalse(self.output.exists())

    def test_case_colliding_media_cannot_create_an_unrestorable_package(self):
        asset = copy.deepcopy(self.project["assets"][0])
        asset.update(id="collision", path="media/engine_test_picture.mkv")
        shutil.copyfile(self.source / self.project["assets"][0]["path"], self.source / asset["path"])
        self.project["assets"].append(asset)
        with self.assertRaisesRegex(ValueError, "case-insensitive"):
            package.export_archive(self.project, self.source, self.output)

    def test_external_workflow_paths_are_explicitly_refused_without_execution(self):
        for location in ("/Users/example/outside.png", "../outside.png", "https://example.invalid/input.png", "C:\\media\\outside.png"):
            workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": location}}}
            write_json(self.source / "workflow.json", workflow)
            with self.subTest(location=location), patch("adapters.generate_comfyui") as generation:
                with self.assertRaisesRegex(ValueError, "external path"):
                    package.export_archive(self.project, self.source, self.output)
                generation.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_media_tamper_fails_hash_before_project_publication(self):
        name = self.project["assets"][0]["path"]
        with zipfile.ZipFile(self.reference_archive) as archive:
            payload = archive.read(name)
        changed = payload[:-1] + bytes([payload[-1] ^ 1])
        zip_rewrite(self.reference_archive, self.output, {name: changed})
        with self.assertRaisesRegex(ValueError, "SHA-256/size mismatch"):
            self.restore(self.output)
        self.assert_no_import()

    def test_unsafe_duplicate_symlink_and_unlisted_members_are_rejected(self):
        names = ("../escape.txt", "/tmp/escape.txt", "media\\escape.mkv", "media/./escape.mkv", "media/../escape.mkv",
                 "media/CON.mkv", "media/trailing.mkv.", "media/ENGINE_TEST_picture.mkv", "media/engine_test_picture.mkv",
                 "media/unlisted.mkv", "exports/unrelated.mp4")
        for index, name in enumerate(names):
            output = self.root / (str(index) + ".zip")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                zip_rewrite(self.reference_archive, output, extra=((name, b"bad"),))
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.restore(output)
            self.assert_no_import()
        link = zipfile.ZipInfo("media/symlink.mkv")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zip_rewrite(self.reference_archive, self.output, extra=((link, b"../../outside"),))
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.restore(self.output)
        self.assert_no_import()

    def test_compressed_bomb_and_false_central_directory_count_are_rejected_before_extraction(self):
        zip_rewrite(self.reference_archive, self.output, compression=zipfile.ZIP_DEFLATED)
        with self.assertRaisesRegex(ValueError, "compressed"):
            self.restore(self.output)
        data = bytearray(self.reference_archive.read_bytes())
        struct.pack_into("<HH", data, len(data) - 22 + 8, 3, 3)
        self.output.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "undeclared excess"):
            self.restore(self.output)
        self.assert_no_import()

    def test_json_duplicate_keys_manifest_identity_and_missing_dependencies_fail_closed(self):
        with zipfile.ZipFile(self.reference_archive) as archive:
            manifest = json.loads(archive.read(package.MANIFEST))
        variants = []
        duplicate = json.dumps(manifest).replace('"version": 1', '"version": 1, "version": 1', 1).encode()
        variants.append({package.MANIFEST: duplicate})
        wrong = copy.deepcopy(manifest); wrong["files"][0]["path"] = []
        variants.append({package.MANIFEST: json.dumps(wrong).encode()})
        wrong = copy.deepcopy(manifest); wrong["total_bytes"] += 1
        variants.append({package.MANIFEST: json.dumps(wrong).encode()})
        wrong = copy.deepcopy(manifest); wrong["files"][0]["role"] = "unrelated-output"
        variants.append({package.MANIFEST: json.dumps(wrong).encode()})
        variants.append({"media/ENGINE_TEST_plate.mkv": None})
        for index, changes in enumerate(variants):
            output = self.root / ("malformed-" + str(index) + ".zip")
            zip_rewrite(self.reference_archive, output, changes)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.restore(output)
            self.assert_no_import()

    def test_undeclared_nested_media_is_rejected_even_if_attacker_updates_manifest(self):
        with zipfile.ZipFile(self.reference_archive) as archive:
            project = json.loads(archive.read("project.json"))
            manifest = json.loads(archive.read(package.MANIFEST))
        node = next(n for n in project["clips"][0]["compositor"]["nodes"] if n["id"] == "plate")
        node["params"]["asset_id"] = "not_admitted"
        payload = json.dumps(project).encode()
        record = next(item for item in manifest["files"] if item["path"] == "project.json")
        manifest["total_bytes"] += len(payload) - record["size"]
        record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        zip_rewrite(self.reference_archive, self.output, {"project.json": payload, package.MANIFEST: json.dumps(manifest).encode()})
        with self.assertRaisesRegex(ValueError, "missing|unknown|Unknown"):
            self.restore(self.output)
        self.assert_no_import()

    def test_inert_raw_blender_sources_and_scene_linear_masters_keep_byte_identity(self):
        # Byte-transport fixtures, explicitly not claimed to decode or render.
        raw_bytes = b"ENGINE TEST opaque RAW transport fixture\x00" * 31
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        raw_path = self.source / "imaging/sources" / (raw_hash + ".raw")
        raw_path.parent.mkdir(parents=True)
        raw_path.write_bytes(raw_bytes)
        descriptor = {"id": raw_hash, "sha256": raw_hash, "path": str(raw_path.relative_to(self.source)),
                      "size": len(raw_bytes), "name": "ENGINE TEST transport source.dng"}
        write_json(raw_path.with_suffix(".json"), descriptor)
        scene = self.source / "exports/scenejob.blend"
        scene.write_bytes(b"BLENDER ENGINE TEST inert source transport only")
        masters = self.source / "exports/scenejob.zip"
        with zipfile.ZipFile(masters, "w") as archive:
            archive.writestr("ENGINE_TEST_transport_only.txt", "This is an opaque transport identity test, not a rendered EXR.")
        rendered = self.project["assets"][0]
        rendered["provenance"] = {"backend": "blender-authored-scene", "scene_sha256": digest(scene),
                                   "scene_linear_masters": True, "masters_sha256": digest(masters)}
        receipt = {"result": {"asset": rendered, "scene_filename": scene.name, "scene_sha256": digest(scene),
                    "scene_url": "/api/projects/archive_source/exports/scenejob.blend",
                    "masters_filename": masters.name, "masters_sha256": digest(masters),
                    "masters_url": "/api/projects/archive_source/exports/scenejob.zip",
                    "masters_manifest": {"purpose": "ENGINE TEST opaque transport"}},
                   "snapshot": {"scene": self.project["settings"]["scene"]}}
        write_json(self.source / "exports/scenejob.json", receipt)
        with patch("adapters.render_blender") as blender, patch("adapters.generate_comfyui") as generation:
            report = package.export_archive(self.project, self.source, self.output)
            restored = self.restore(self.output)
            blender.assert_not_called()
            generation.assert_not_called()
        fresh = self.projects / restored["id"]
        for path in (raw_path, scene, masters):
            self.assertEqual(digest(path), digest(fresh / path.relative_to(self.source)))
        saved = json.loads((fresh / "exports/scenejob.json").read_text())
        self.assertNotIn("scene_url", saved["result"])
        self.assertNotIn("masters_url", saved["result"])
        self.assertEqual(saved["result"]["masters_manifest"], receipt["result"]["masters_manifest"])
        roles = {item["role"] for item in report["manifest"]["files"]}
        self.assertTrue({"camera-raw-source", "raw-descriptor", "authored-blender-source", "authored-scene-masters"} <= roles)
        # Re-exporting a restored recipe is independently valid.
        package.export_archive(restored, fresh, self.root / "second.cinematicum.zip")

    def test_missing_authored_scene_dependency_is_not_silently_dropped(self):
        self.project["assets"][0]["provenance"] = {"backend": "blender-authored-scene", "scene_sha256": "a" * 64}
        with self.assertRaisesRegex(ValueError, "missing its preserved"):
            package.export_archive(self.project, self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_archive_budget_is_streamed_and_exceeds_old_256_mib_upload_limit(self):
        self.assertGreater(package.MAX_BYTES, 256 * 1024 ** 2)
        path = self.source / "media/ENGINE_TEST_large.blend"
        # Sparse fixture verifies the actual >256-MiB path without allocating a
        # large Python byte string. It is copied in bounded chunks by both APIs.
        with path.open("wb") as output:
            output.write(b"BLENDER ENGINE TEST opaque transport")
            output.truncate(257 * 1024 ** 2)
        self.project["assets"].append({"id": "large_scene", "path": str(path.relative_to(self.source)),
            "kind": "scene", "size": path.stat().st_size, "sha256": digest(path)})
        package.export_archive(self.project, self.source, self.output)
        restored = self.restore(self.output)
        self.assertEqual(digest(path), digest(self.projects / restored["id"] / "media/ENGINE_TEST_large.blend"))

    def test_declared_resource_bound_is_enforced_before_large_extraction(self):
        with patch.object(package, "MAX_BYTES", 1024):
            with self.assertRaisesRegex(ValueError, "size|bounds|invalid|64 GiB"):
                self.restore()
        with patch.object(package, "MAX_FILES", 2):
            with self.assertRaisesRegex(ValueError, "count bounds"):
                self.restore()
        self.assert_no_import()

    def test_zip_metadata_overhead_counts_toward_the_actual_upload_bound(self):
        manifest = self.reference_report["manifest"]
        payload_and_manifest = manifest["total_bytes"] + len(package._json_bytes(manifest))
        self.assertGreater(self.reference_archive.stat().st_size, payload_and_manifest)
        with patch.object(package, "MAX_BYTES", payload_and_manifest):
            with self.assertRaisesRegex(ValueError, "including ZIP metadata"):
                package.export_archive(self.project, self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".cinematicum-archive-*")), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX special-file check")
    def test_special_file_sources_are_rejected_without_waiting_for_a_writer(self):
        fifo = self.root / "not-an-archive.zip"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.restore(fifo)
        asset_path = self.source / self.project["assets"][0]["path"]
        asset_path.unlink()
        os.mkfifo(asset_path)
        with self.assertRaisesRegex(ValueError, "regular files"):
            package.export_archive(self.project, self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assert_no_import()

    def test_actual_ocio_artifacts_and_recipe_survive_relocation(self):
        import imaging
        python = imaging.find_imaging_python()
        if not python or not imaging.imaging_capabilities(python).get("available"):
            self.skipTest("The optional isolated imaging runtime is not installed")
        image_path = self.source / "media/ENGINE_TEST_still.png"
        ffmpeg(["-i", str(self.source / "media/ENGINE_TEST_picture.mkv"), "-frames:v", "1", "-threads", "1", str(image_path)])
        source = {"id": "original-still", "path": str(image_path.relative_to(self.source)), "sha256": digest(image_path),
                  **probe_media(image_path)}
        self.project["assets"].append(source)
        result = imaging.run_imaging(self.project, self.source,
            {"version": 1, "operation": "ocio", "asset_id": source["id"], "input_space": "sRGB - Texture", "exposure": .5},
            self.source / "imaging/outputs/develop", python=python)
        display = self.source / "media/ENGINE_TEST_developed.png"
        shutil.copyfile(result["path"], display)
        asset = {"id": "developed", "path": str(display.relative_to(self.source)), "sha256": digest(display),
                 "provenance": result["provenance"], **probe_media(display)}
        self.project["assets"].append(asset)
        package.export_archive(self.project, self.source, self.output)
        restored = self.restore(self.output)
        fresh = self.projects / restored["id"]
        for name in ("linear.exr", "display.png", "receipt.json"):
            self.assertEqual(digest(self.source / "imaging/outputs/develop" / name), digest(fresh / "imaging/outputs/develop" / name))
        self.assertEqual(next(a for a in restored["assets"] if a["id"] == "developed")["provenance"], result["provenance"])
        # Original source and recipe remain usable by the real worker after move.
        repeated = imaging.run_imaging(restored, fresh, result["provenance"]["recipe"], fresh / "imaging/outputs/repeated", python=python)
        self.assertEqual(repeated["artifacts"]["display"]["sha256"], result["artifacts"]["display"]["sha256"])
        self.assertEqual(repeated["artifacts"]["linear"]["sha256"], result["artifacts"]["linear"]["sha256"])


if __name__ == "__main__":
    unittest.main()

"""Adversarial contract tests for project-owned Meshroom integration.

The miniature geometry is an ENGINE_TEST fixture, not an accepted real image-set.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meshroom_reconstruction as meshroom


def project(root):
    assets = []
    for number in range(3):
        path = root / "media" / f"photo{number}.png"
        path.parent.mkdir(exist_ok=True)
        payload = b"ENGINE_TEST_PHOTO_" + bytes([number])
        path.write_bytes(payload)
        assets.append({"id": f"photo{number}", "kind": "image",
                       "path": f"media/photo{number}.png", "size": len(payload),
                       "sha256": hashlib.sha256(payload).hexdigest(),
                       "width": 256, "height": 256})
    return {"assets": assets}


def fixture_results(result, graph):
    result.mkdir(exist_ok=True)
    (result / "texturedMesh.obj").write_text(
        "mtllib texturedMesh.mtl\n" +
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n" +
        "".join("f 1/1 2/2 3/3\n" for _ in range(100)), encoding="utf-8")
    (result / "texturedMesh.mtl").write_text(
        "newmtl material\nmap_Kd texture_1001.png\n", encoding="utf-8")
    (result / "texture_1001.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
        (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")
    graph.write_text('{"graph":"ENGINE_TEST"}', encoding="utf-8")


class MeshroomContractTests(unittest.TestCase):
    def test_strict_project_media_and_recipe_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = project(root)
            settings = {**meshroom.default_settings(),
                        "asset_ids": [a["id"] for a in data["assets"]]}
            recipe = {"operation": "meshroom-photogrammetry", "settings": settings}
            self.assertEqual(recipe, meshroom.validate_recipe(recipe, data))
            for change in ({"version": True}, {"asset_ids": ["photo0", "photo0"]},
                           {"max_seconds": False}, {"min_faces": 0},
                           {"asset_ids": ["../escape"]}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    meshroom.validate_settings({**settings, **change})
            with self.assertRaisesRegex(ValueError, "fixed Meshroom"):
                meshroom.validate_recipe({**recipe, "operation": "shell"}, data)
            altered = copy.deepcopy(data)
            altered["assets"][0]["kind"] = "video"
            with self.assertRaises(ValueError):
                meshroom.validate_recipe(recipe, altered)

    def test_pinning_absent_and_wrong_hash_fail_closed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(meshroom.capabilities()["dense_available"])
            with self.assertRaises(RuntimeError):
                meshroom._binary()
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "batch"
            candidate.write_bytes(b"ENGINE_TEST_NOT_AN_EXECUTABLE")
            candidate.chmod(0o755)
            with mock.patch.dict(os.environ, {
                    "CINEMATICUM_MESHROOM_BATCH": str(candidate),
                    "CINEMATICUM_MESHROOM_BATCH_SHA256": "0" * 64}):
                with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                    meshroom._binary()

    def test_surface_rejects_undersized_mesh_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture_results(root / "result", root / "graph.mg")
            report, files = meshroom._inspect_surface(root / "result", 100)
            self.assertEqual((4, 100, 1), (report["vertices"], report["faces"], report["textures"]))
            self.assertEqual(3, len(files))
            with self.assertRaisesRegex(ValueError, "nontrivial"):
                meshroom._inspect_surface(root / "result", 101)
            (root / "result" / "other.png").symlink_to(root / "result" / "texture_1001.png")
            with self.assertRaisesRegex(ValueError, "symbolic"):
                meshroom._inspect_surface(root / "result", 100)

    def test_run_is_immutable_and_preserves_source_with_engine_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = project(root)
            settings = {**meshroom.default_settings(),
                        "asset_ids": [a["id"] for a in data["assets"]]}
            recipe = {"operation": "meshroom-photogrammetry", "settings": settings}
            output = root / "meshroom" / "outputs" / ("a" * 32)
            original = copy.deepcopy(data)
            events = []

            def execute(executable, images, results, graph, scratch, seconds, cancel):
                self.assertEqual(3, len(list(images.iterdir())))
                fixture_results(results, graph)

            with mock.patch.object(meshroom, "_binary", return_value=(Path(sys.executable), "f" * 64)):
                with mock.patch.object(meshroom, "_execute", side_effect=execute):
                    result = meshroom.run(data, root, recipe, output, progress=events.append)
            self.assertEqual(original, data)
            self.assertEqual(1, events[-1])
            self.assertEqual(100, result["surface"]["faces"])
            self.assertEqual({"graph.mg", "surface.json", "meshroom-output.zip", "provenance.json"},
                             {p.name for p in output.iterdir()})
            with zipfile.ZipFile(output / "meshroom-output.zip") as archive:
                self.assertEqual(["texture_1001.png", "texturedMesh.mtl", "texturedMesh.obj"],
                                 sorted(archive.namelist()))
            for entry in result["artifacts"]:
                source = output / entry["filename"]
                self.assertEqual((entry["sha256"], entry["bytes"]),
                                 (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_size))
            with self.assertRaisesRegex(ValueError, "overwritten"):
                with mock.patch.object(meshroom, "_binary", return_value=(Path(sys.executable), "f" * 64)):
                    meshroom.run(data, root, recipe, output)

    def test_cancelled_run_never_prepares_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = project(root)
            settings = {**meshroom.default_settings(), "asset_ids": [a["id"] for a in data["assets"]]}
            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(InterruptedError):
                meshroom.run(data, root, {"operation": "meshroom-photogrammetry", "settings": settings},
                             root / "meshroom/outputs" / ("b" * 32), cancel_event=cancelled)
            self.assertEqual({"media"}, {p.name for p in root.iterdir()})


if __name__ == "__main__":
    unittest.main()

"""HTTP contracts for scene authoring, generation preflight, and editor assets.

The video fixture is a real, decoded synthetic test clip. Blender is mocked at
the scene-adapter boundary: its .blend attachment fixture is intentionally not
a working Blender scene. Actual Blender rendering is covered separately.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
import unittest
from unittest.mock import call, patch

from adapters import POSITIVE_MARKER
from scene import default_scene
from server import Store, WEB
import test_server as http_fixtures


class StudioV2Tests(unittest.TestCase):
    # Reuse the real loopback server and MP4 fixture without inheriting and
    # rerunning all of ServerTests' existing test methods.
    setUpClass = classmethod(http_fixtures.ServerTests.setUpClass.__func__)
    tearDownClass = classmethod(http_fixtures.ServerTests.tearDownClass.__func__)
    setUp = http_fixtures.ServerTests.setUp
    tearDown = http_fixtures.ServerTests.tearDown
    request = http_fixtures.ServerTests.request

    def scene_recipe(self):
        recipe = default_scene(640, 360)
        recipe["frame_end"] = 24
        recipe["objects"] = [{"id": "test_cube", "type": "cube"}]
        return recipe

    def save_scene(self):
        project = self.store.get(self.p["id"])
        project["settings"]["scene"] = self.scene_recipe()
        status, _, saved = self.request("PUT", f"/api/projects/{project['id']}", project)
        self.assertEqual(200, status, saved)
        return saved

    def finished_job(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status, _, job = self.request("GET", f"/api/jobs/{job_id}")
            self.assertEqual(200, status, job)
            if job["state"] not in {"queued", "running"}:
                return job
            time.sleep(.025)
        self.fail("Test fixture job did not finish within 15 seconds")

    def test_scene_save_reopen_and_invalid_edits_are_atomic(self):
        saved = self.save_scene()
        scene = saved["settings"]["scene"]
        self.assertEqual((160, 90), (scene["width"], scene["height"]))
        self.assertEqual([0, 0, 1], scene["objects"][0]["position"])
        self.assertEqual("#d8a85f", scene["objects"][0]["material"]["color"])
        self.assertEqual([], scene["objects"][0]["keyframes"])

        self.store.shutdown()
        self.store = Store(self.tmp.name)
        self.server.store = self.store
        status, _, reopened = self.request("GET", f"/api/projects/{saved['id']}")
        self.assertEqual(200, status, reopened)
        self.assertEqual(saved, reopened)

        invalid_scenes = [
            {**scene, "script": "unsupported executable property"},
            {**scene, "objects": [{"id": "test_cube", "type": "script"}]},
            {**scene, "objects": [{"id": "test_cube", "type": "cube", "scale": [1, 0, 1]}]},
        ]
        for invalid in invalid_scenes:
            with self.subTest(scene=invalid):
                edited = copy.deepcopy(reopened)
                edited["settings"]["scene"] = invalid
                status, _, response = self.request("PUT", f"/api/projects/{saved['id']}", edited)
                self.assertEqual(400, status, response)
                self.assertEqual(reopened, self.store.get(saved["id"]))

    def test_scene_render_owns_snapshot_and_publishes_media_and_source(self):
        saved = self.save_scene()
        scene_before = copy.deepcopy(saved["settings"]["scene"])
        entered, release = threading.Event(), threading.Event()
        captured = {}
        blend_bytes = b"BLENDER-v300\nHTTP CONTRACT TEST FIXTURE; NOT A RENDERABLE BLENDER SCENE\n"
        provenance = {"backend": "test-fixture-scene-adapter", "fixture": True,
                      "scene_sha256": hashlib.sha256(blend_bytes).hexdigest()}

        def scene_adapter(recipe, output_dir, *, fps, frame_start, frame_end,
                          progress, cancel_event):
            captured.update(scene=copy.deepcopy(recipe), fps=fps,
                            frame_start=frame_start, frame_end=frame_end)
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test did not release its scene fixture worker")
            captured["scene_after_edit"] = copy.deepcopy(recipe)
            if cancel_event.is_set():
                raise RuntimeError("Test fixture was cancelled")
            output_dir = Path(output_dir)
            movie, source = output_dir / "TEST_FIXTURE.mp4", output_dir / "TEST_FIXTURE.blend"
            shutil.copyfile(self.movie, movie)
            source.write_bytes(blend_bytes)
            progress(.9)
            return {"path": movie, "scene_path": source, "provenance": provenance}

        with patch("server.find_blender", return_value="/test-fixture/blender"), \
                patch("server.render_scene", side_effect=scene_adapter) as renderer:
            try:
                # An empty payload must use the saved scene and its end frame.
                status, _, submitted = self.request("POST", f"/api/projects/{saved['id']}/scene", {})
                self.assertEqual(202, status, submitted)
                self.assertEqual("scene", submitted["kind"])
                self.assertTrue(entered.wait(timeout=3))
                edited = copy.deepcopy(saved)
                edited["settings"]["scene"]["objects"][0]["position"][0] = 9
                edited["settings"]["scene"]["frame_end"] = 48
                edited["fps"] = 30
                edited["frame_rate"] = {"numerator": 30, "denominator": 1}
                status, _, changed = self.request("PUT", f"/api/projects/{saved['id']}", edited)
                self.assertEqual(200, status, changed)
                release.set()
                completed = self.finished_job(submitted["id"])
            finally:
                release.set()
            renderer.assert_called_once()

        self.assertEqual("completed", completed["state"], completed)
        self.assertEqual(scene_before, captured["scene"])
        self.assertEqual(scene_before, captured["scene_after_edit"])
        self.assertEqual((1, 24), (captured["frame_start"], captured["frame_end"]))
        self.assertEqual({"numerator": 24, "denominator": 1}, captured["fps"].as_dict())
        snapshot = {"scene": scene_before, "frame_start": 1, "frame_end": 24,
                    "fps": 24, "frame_rate": {"numerator": 24, "denominator": 1}, "project_revision": saved["revision"]}
        snapshot_path = self.store.root / "jobs" / (submitted["id"] + ".snapshot")
        self.assertEqual(snapshot, json.loads(snapshot_path.read_text()))

        result, movie_bytes = completed["result"], self.movie.read_bytes()
        asset = result["asset"]
        self.assertEqual(saved["revision"], result["project_revision"])
        self.assertEqual("video", asset["kind"])
        self.assertEqual((160, 90), (asset["width"], asset["height"]))
        self.assertAlmostEqual(1, asset["duration"], places=3)
        self.assertEqual(hashlib.sha256(movie_bytes).hexdigest(), asset["sha256"])
        self.assertEqual(provenance, asset["provenance"])
        status, _, received = self.request("GET", result["url"])
        self.assertEqual(200, status)
        self.assertEqual(movie_bytes, received)
        admitted_path = self.store.project_dir(saved["id"]) / asset["path"]
        decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-i",
                                  str(admitted_path), "-frames:v", "1", "-threads", "1",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                 check=True, capture_output=True, timeout=10)
        self.assertEqual(160 * 90 * 3, len(decoded.stdout))

        status, headers, received = self.request("GET", result["scene_url"])
        self.assertEqual(200, status)
        self.assertEqual(blend_bytes, received)
        self.assertEqual(f'attachment; filename="{submitted["id"]}.blend"', headers["Content-Disposition"])
        self.assertEqual(provenance["scene_sha256"], result["scene_sha256"])
        self.assertEqual(submitted["id"] + ".blend", result["scene_filename"])
        status, _, manifest = self.request("GET", f"/api/projects/{saved['id']}/exports/{submitted['id']}.json")
        self.assertEqual(200, status)
        self.assertEqual(snapshot, manifest["snapshot"])
        self.assertEqual(result, manifest["result"])
        self.assertEqual("NONE", manifest["issuance_effect"])

        reopened = self.store.get(saved["id"])
        self.assertEqual(changed["settings"]["scene"], reopened["settings"]["scene"])
        self.assertEqual(30, reopened["fps"])
        self.assertEqual([asset], reopened["assets"])

    def test_scene_cancel_before_publication_leaves_no_admitted_outputs(self):
        ready, release = threading.Event(), threading.Event()
        scratch_paths = []

        def scene_adapter(recipe, output_dir, **kwargs):
            output_dir = Path(output_dir)
            scratch_paths.append(output_dir)
            movie, source = output_dir / "TEST_FIXTURE.mp4", output_dir / "TEST_FIXTURE.blend"
            shutil.copyfile(self.movie, movie)
            source.write_bytes(b"BLENDER-v300\nCANCEL TEST FIXTURE; NOT A WORKING SCENE\n")
            ready.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test did not release the scene adapter")
            # Return finished scratch files even if cancelled: the Store worker
            # must reject them at its final check before publishing anything.
            return {"path": movie, "scene_path": source}

        with patch("server.find_blender", return_value="/test-fixture/blender"), \
                patch("server.render_scene", side_effect=scene_adapter), \
                patch.object(self.store, "admit", wraps=self.store.admit) as admit:
            try:
                status, _, submitted = self.request("POST", f"/api/projects/{self.p['id']}/scene",
                                                     {"scene": self.scene_recipe()})
                self.assertEqual(202, status, submitted)
                self.assertTrue(ready.wait(timeout=3))
                status, _, requested = self.request("POST", f"/api/jobs/{submitted['id']}/cancel", {})
                self.assertEqual(200, status, requested)
                release.set()
                cancelled = self.finished_job(submitted["id"])
            finally:
                release.set()
            admit.assert_not_called()

        self.assertEqual("cancelled", cancelled["state"], cancelled)
        self.assertIsNone(cancelled["result"])
        directory = self.store.project_dir(self.p["id"])
        self.assertEqual([], self.store.get(self.p["id"])["assets"])
        self.assertEqual([], list((directory / "media").iterdir()))
        self.assertEqual([], list((directory / "exports").iterdir()))
        self.assertTrue(scratch_paths)
        self.assertTrue(all(not path.exists() for path in scratch_paths))

    def test_scene_late_cancel_preserves_committed_result_and_outputs(self):
        admitted, release = threading.Event(), threading.Event()
        original_admit = self.store.admit
        blend_bytes = b"BLENDER-v300\nLATE CANCEL HTTP FIXTURE; NOT A WORKING SCENE\n"
        provenance = {"backend": "test-fixture-scene-adapter", "fixture": True}

        def scene_adapter(recipe, output_dir, **kwargs):
            output_dir = Path(output_dir)
            movie, source = output_dir / "TEST_FIXTURE.mp4", output_dir / "TEST_FIXTURE.blend"
            shutil.copyfile(self.movie, movie)
            source.write_bytes(blend_bytes)
            return {"path": movie, "scene_path": source, "provenance": provenance}

        def admit_during_publication(*args, **kwargs):
            # Execute the actual ffprobe, file move, and registry writes. Pause
            # before returning so cancellation deterministically hits the
            # publication interval, not a completed job or a fake asset.
            asset = original_admit(*args, **kwargs)
            admitted.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test did not release media publication")
            return asset

        with patch("server.find_blender", return_value="/test-fixture/blender"), \
                patch("server.render_scene", side_effect=scene_adapter), \
                patch.object(self.store, "admit", side_effect=admit_during_publication) as admit:
            try:
                status, _, submitted = self.request("POST", f"/api/projects/{self.p['id']}/scene",
                                                     {"scene": self.scene_recipe()})
                self.assertEqual(202, status, submitted)
                self.assertTrue(admitted.wait(timeout=3))
                directory = self.store.project_dir(self.p["id"])
                published = self.store.get(self.p["id"])["assets"]
                self.assertEqual(1, len(published))
                self.assertEqual(self.movie.read_bytes(), (directory / published[0]["path"]).read_bytes())
                self.assertEqual(blend_bytes, (directory / "exports" / (submitted["id"] + ".blend")).read_bytes())
                status, _, requested = self.request("POST", f"/api/jobs/{submitted['id']}/cancel", {})
                self.assertEqual(200, status, requested)
                self.assertEqual("running", requested["state"])
                release.set()
                completed = self.finished_job(submitted["id"])
            finally:
                release.set()
            admit.assert_called_once()

        self.assertEqual("completed", completed["state"], completed)
        self.assertIsNone(completed["error"])
        self.assertEqual(1, completed["progress"])
        result = completed["result"]
        self.assertEqual(published[0], result["asset"])
        self.assertEqual(provenance, result["asset"]["provenance"])
        self.assertEqual(hashlib.sha256(blend_bytes).hexdigest(), result["scene_sha256"])
        status, _, movie = self.request("GET", result["url"])
        self.assertEqual(200, status)
        self.assertEqual(self.movie.read_bytes(), movie)
        status, headers, source = self.request("GET", result["scene_url"])
        self.assertEqual(200, status)
        self.assertEqual(blend_bytes, source)
        self.assertIn("attachment;", headers["Content-Disposition"])
        manifest = json.loads((directory / "exports" / (submitted["id"] + ".json")).read_text())
        self.assertEqual(result, manifest["result"])
        persisted = json.loads((self.store.root / "jobs" / (submitted["id"] + ".json")).read_text())
        self.assertEqual("completed", persisted["state"])
        self.assertEqual(result, persisted["result"])

    def test_bad_scene_recipes_and_frame_ranges_do_not_enter_queue(self):
        recipe = self.scene_recipe()
        invalid = [
            {"scene": None},
            {"scene": {**recipe, "script": "unsupported"}},
            {"scene": {**recipe, "objects": [{"id": "bad", "type": "code"}]}},
            {"scene": {**recipe, "frame_end": 7201}},
            {"scene": recipe, "frame_start": 0},
            {"scene": recipe, "frame_start": 25},
            {"scene": recipe, "frame_start": 1.5},
            {"scene": recipe, "frame_end": 0},
            {"scene": recipe, "frame_end": 25},
            {"scene": recipe, "frame_end": True},
            {"scene": recipe, "frame_end": "24"},
            {"scene": recipe, "frame_start": 8, "frame_end": 7},
        ]
        with patch("server.find_blender", return_value="/test-fixture/blender"), \
                patch("server.render_scene") as renderer, \
                patch.object(self.store, "submit", wraps=self.store.submit) as submit:
            for payload in invalid:
                with self.subTest(payload=payload):
                    status, _, response = self.request("POST", f"/api/projects/{self.p['id']}/scene", payload)
                    self.assertEqual(400, status, response)
            renderer.assert_not_called()
            submit.assert_not_called()
        self.assertEqual({}, self.store.jobs)
        self.assertEqual([], self.store.get(self.p["id"])["assets"])

    def test_scene_render_reports_missing_blender_before_queueing(self):
        with patch("server.find_blender", return_value=None), \
                patch.object(self.store, "submit", wraps=self.store.submit) as submit:
            status, _, response = self.request("POST", f"/api/projects/{self.p['id']}/scene",
                                               {"scene": self.scene_recipe()})
        self.assertEqual(400, status, response)
        self.assertIn("Blender", response["error"])
        submit.assert_not_called()

    def test_generation_readiness_without_workflow_is_read_only(self):
        with patch("generation_readiness.check_comfyui", return_value={"available": True}) as connection, \
                patch("generation_readiness._json_request") as schema_request:
            status, _, report = self.request("GET", f"/api/projects/{self.p['id']}/generation-readiness")
        self.assertEqual(200, status, report)
        self.assertTrue(report["available"])
        self.assertFalse(report["ready"])
        self.assertEqual(0, report["checked_nodes"])
        self.assertIn("Import a ComfyUI API workflow", report["reason"])
        connection.assert_called_once_with(self.store.comfy_url)
        schema_request.assert_not_called()
        self.assertFalse((self.store.project_dir(self.p["id"]) / "workflow.json").exists())
        self.assertEqual({}, self.store.jobs)

    def test_missing_model_preflight_blocks_generate_before_submission(self):
        # Fixture schemas model the /object_info contract, with one unavailable
        # model. No request is sent to ComfyUI and no generation is simulated.
        workflow = {
            "1": {"class_type": "FixturePrompt", "inputs": {"text": POSITIVE_MARKER}},
            "2": {"class_type": "FixtureModel", "inputs": {"model_name": "missing-test-model.safetensors"}},
            "3": {"class_type": "FixtureGenerate", "inputs": {"prompt": ["1", 0], "model": ["2", 0]}},
            "4": {"class_type": "SaveVideo", "inputs": {"video": ["3", 0], "format": "mp4"}},
        }
        schemas = {
            "FixturePrompt": {"input": {"required": {"text": ["STRING"]}}, "output": ["TEXT"]},
            "FixtureModel": {"input": {"required": {"model_name": [["installed-test-model.safetensors"]]}}, "output": ["MODEL"]},
            "FixtureGenerate": {"input": {"required": {"prompt": ["TEXT"], "model": ["MODEL"]}}, "output": ["VIDEO"]},
            "SaveVideo": {"input": {"required": {"video": ["VIDEO"], "format": [["mp4", "webm"]]}}, "output_node": True, "output": []},
        }
        status, _, response = self.request("POST", f"/api/projects/{self.p['id']}/workflow", workflow)
        self.assertEqual(201, status, response)
        workflow_path = self.store.project_dir(self.p["id"]) / "workflow.json"
        workflow_before = workflow_path.read_bytes()
        with patch("generation_readiness.check_comfyui", return_value={"available": True}), \
                patch("generation_readiness._json_request", return_value=schemas) as schema_request, \
                patch("server.generate_comfyui") as generate, \
                patch.object(self.store, "submit", wraps=self.store.submit) as submit:
            status, _, report = self.request("GET", f"/api/projects/{self.p['id']}/generation-readiness")
            self.assertEqual(200, status, report)
            self.assertTrue(report["available"])
            self.assertFalse(report["ready"])
            self.assertEqual(4, report["checked_nodes"])
            self.assertEqual(1, len(report["errors"]))
            self.assertIn("Model unavailable", report["reason"])
            status, _, response = self.request("POST", f"/api/projects/{self.p['id']}/generate",
                                               {"prompt": "HTTP PREFLIGHT TEST ONLY", "seed": 7})
            self.assertEqual(400, status, response)
            self.assertIn(report["reason"], response["error"])
            self.assertEqual([call(self.store.comfy_url, "/object_info", timeout=5)] * 2,
                             schema_request.call_args_list)
            generate.assert_not_called()
            submit.assert_not_called()
        self.assertEqual(workflow_before, workflow_path.read_bytes())
        self.assertEqual({}, self.store.jobs)
        self.assertEqual([], self.store.get(self.p["id"])["assets"])

    def test_new_editor_static_assets_are_served_with_correct_types(self):
        for name, content_type in (("compositor-ui.js", "text/javascript"),
                                   ("scene-editor.js", "text/javascript"),
                                   ("scene-editor.css", "text/css")):
            with self.subTest(name=name):
                status, headers, body = self.request("GET", "/" + name)
                self.assertEqual(200, status)
                self.assertEqual(content_type, headers["Content-Type"])
                self.assertEqual((WEB / name).read_bytes(), body)
                self.assertGreater(len(body), 100)
        status, _, _ = self.request("GET", "/scene.py")
        self.assertEqual(404, status)


if __name__ == "__main__":
    unittest.main()

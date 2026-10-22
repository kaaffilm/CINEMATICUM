"""Actual checkpoint inference through owned HTTP jobs and saved editing plans."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile

from learned_tracking import find_learned_python
from server import Server, Store
from test_learned_tracking import synthetic_motion, sam_recipe, tap_recipe


class LearnedToolHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-LEARNED-HTTP-TEST-")
        self.root = Path(self.temporary.name)
        self.store = Store(self.root / "workspace")
        self._serve()
        self.project = self.store.new_project({"name": "ENGINE TEST learned editing", "width": 256, "height": 160, "fps": 12})
        self.project_id = self.project["id"]
        self.base = "/api/projects/" + self.project_id

    def _serve(self):
        self.server = Server(0, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()

    def _close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.shutdown()

    def tearDown(self):
        self._close()
        self.temporary.cleanup()

    def request(self, method, path, body=None, token=True):
        headers = {"X-Cinematicum-Token": self.store.token} if token else {}
        if body is not None:
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=45)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status, content_type, data = response.status, response.getheader("Content-Type", ""), response.read()
        finally:
            connection.close()
        return status, json.loads(data) if content_type.startswith("application/json") else data

    def wait(self, job, state="completed", seconds=180):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and job["state"] in {"queued", "running"}:
            time.sleep(.05)
            status, job = self.request("GET", "/api/jobs/" + job["id"])
            self.assertEqual(200, status)
        self.assertEqual(state, job["state"], job)
        return job

    def start(self, route, payload, state="completed"):
        status, job = self.request("POST", self.base + "/" + route, payload)
        self.assertEqual(202, status, job)
        return self.wait(job, state)

    def save(self, project):
        status, saved = self.request("PUT", self.base, project)
        self.assertEqual(200, status, saved)
        return saved

    def source(self, still=False):
        fixture, frames, masks, centers = synthetic_motion(self.root / "fixture")
        original = self.root / "fixture" / fixture["assets"][0]["path"]
        if still:
            original = self.root / "ENGINE_TEST_still.png"
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "256x160", "-i", "pipe:0", "-frames:v", "1", "-threads", "1", str(original)],
                           input=frames[0].tobytes(), capture_output=True, check=True, timeout=20)
        asset = self.store.admit(self.project_id, original, original.name)
        project = self.store.get(self.project_id)
        project["clips"] = [{"id": "picture", "asset_id": asset["id"], "track": 0, "start": 0, "in": 0,
                             "duration": 4 if still else 10}]
        project["settings"].update(image_precision="high16", transparent_background=True)
        return self.save(project), masks, centers

    def test_invalid_or_unauthenticated_learned_requests_never_start_inference(self):
        for route in ("learned-track", "learned-apply-plan", "learned-frame"):
            self.assertEqual(403, self.request("POST", self.base + "/" + route, {}, token=False)[0])
        self.assertEqual(400, self.request("POST", self.base + "/learned-track",
                                         {"clip_id": "absent", "recipe": sam_recipe()})[0])
        self.assertEqual(400, self.request("POST", self.base + "/learned-track",
                                         {"clip_id": "absent", "recipe": sam_recipe(), "python": "/external/code"})[0])
        self.assertFalse(self.store.jobs)

    @unittest.skipUnless(find_learned_python(), "The actual pinned SAM2/TAPIR inference runtime is required")
    def test_real_sam_image_prompt_apply_undo_reopen_render_and_archive(self):
        import numpy as np
        project, masks, _ = self.source(still=True)
        seed = self.start("learned-frame", {"project": project, "clip_id": "picture", "settings": {"frame_start": 0, "frame_count": 1}})
        self.assertEqual("image", seed["result"]["source_stream"]["kind"])
        status, preview = self.request("GET", seed["result"]["url"])
        self.assertEqual(200, status)
        self.assertEqual(b"\x89PNG\r\n\x1a\n", preview[:8])
        recipe = sam_recipe()
        recipe["frame_count"] = 1
        job = self.start("learned-track", {"project": project, "clip_id": "picture", "recipe": recipe})
        result = job["result"]
        self.assertEqual("image", result["measurement"]["source_stream"]["kind"])
        self.assertEqual("cinematicum-learned-mask", result["asset"]["provenance"]["type"])
        status, receipt = self.request("GET", result["receipt_url"])
        self.assertEqual(200, status)
        for record in receipt["artifacts"]:
            status, data = self.request("GET", result["artifact_urls"][record["filename"]])
            self.assertEqual(200, status)
            path = self.store.project_dir(self.project_id) / "learned" / "outputs" / job["id"] / record["filename"]
            self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            if isinstance(data, bytes):
                self.assertEqual(path.read_bytes(), data)
        project = self.store.get(self.project_id)
        before = copy.deepcopy(project)
        payload = {"project": project, "clip_id": "picture", "job_id": job["id"], "action": "mask", "hold_still": True}
        status, plan = self.request("POST", self.base + "/learned-apply-plan", payload)
        self.assertEqual(200, status, plan)
        self.assertEqual(before, self.store.get(self.project_id), "Planning must not mutate the editable project")
        project["clips"][0].update(compositor=plan["compositor"], learned_recipe=plan["recipe"], learned_bindings=[plan["binding"]])
        saved = self.save(project)
        before["revision"] = saved["revision"]
        undone = self.save(before)
        self.assertNotIn("learned_bindings", undone["clips"][0])
        saved["revision"] = undone["revision"]
        saved = self.save(saved)
        root = self.store.root
        self._close()
        self.store = Store(root)
        self._serve()
        self.assertEqual(saved, self.store.get(self.project_id))
        exported = self.start("render", {"profile": "master16", "project": saved})
        status, media = self.request("GET", exported["result"]["url"])
        self.assertEqual(200, status)
        self.assertEqual(exported["result"]["sha256"], hashlib.sha256(media).hexdigest())
        target = self.root / "ENGINE_TEST_downloaded_cutout.mkv"
        target.write_bytes(media)
        alpha_bytes = subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-vf", "alphaextract",
                                      "-threads", "1", "-pix_fmt", "gray16le", "-f", "rawvideo", "pipe:1"],
                                     capture_output=True, check=True, timeout=20).stdout
        alpha = np.frombuffer(alpha_bytes, dtype="<u2").reshape(4, 160, 256)
        self.assertEqual({0, 65535}, set(np.unique(alpha).tolist()))
        self.assertTrue(all(np.array_equal(frame, alpha[0]) for frame in alpha))
        measured, oracle = alpha[0] > 0, masks[0]
        self.assertGreater(float((measured & oracle).sum() / (measured | oracle).sum()), .95)
        changed = copy.deepcopy(saved)
        changed["clips"][0]["duration"] = 3
        changed = self.save(changed)
        self.assertTrue(changed["clips"][0]["learned_bindings"][0]["invalidated"])
        failure = self.start("render", {"profile": "master16", "project": changed}, state="failed")
        self.assertIn("stale", failure["error"].lower())
        saved["revision"] = changed["revision"]
        saved = self.save(saved)
        self.assertNotIn("invalidated", saved["clips"][0]["learned_bindings"][0])
        from project_archive import export_archive, import_archive
        archive = self.root / "ENGINE_TEST_learned.cinematicum.zip"
        export_archive(saved, self.store.project_dir(self.project_id), archive)
        with zipfile.ZipFile(archive) as package:
            self.assertTrue({"learned/outputs/" + job["id"] + "/" + name for name in result["artifact_urls"]} <= set(package.namelist()))
        restored = import_archive(archive, self.store.root / "projects")
        restored_url = result["artifact_urls"]["mask.mkv"].replace(self.project_id, restored["id"])
        self.assertEqual(self.request("GET", result["artifact_urls"]["mask.mkv"]), self.request("GET", restored_url))
        history = self.request("GET", "/api/projects/" + restored["id"] + "/studio-results")[1]["results"]
        self.assertIn(job["id"], [row["output_id"] for row in history])

    @unittest.skipUnless(find_learned_python(), "The actual pinned SAM2/TAPIR inference runtime is required")
    def test_real_tapir_visibility_corrections_plan_save_and_timing_invalidation(self):
        project, _, centers = self.source()
        job = self.start("learned-track", {"project": project, "clip_id": "picture", "recipe": tap_recipe()})
        result = job["result"]
        samples = result["measurement"]["measurement"]["tracks"][0]["track"]["samples"]
        self.assertEqual([True] * 4 + [False] * 3 + [True] * 3, [sample["visible"] for sample in samples])
        payload = {"project": project, "clip_id": "picture", "job_id": job["id"], "action": "point", "point_id": "disk_center"}
        status, error = self.request("POST", self.base + "/learned-apply-plan", payload)
        self.assertEqual(400, status, error)
        self.assertIn("loses", error["error"])
        self.assertEqual(project, self.store.get(self.project_id))
        payload["corrections"] = [{"frame": frame, "x": centers[frame][0] / 256, "y": centers[frame][1] / 160} for frame in (4, 5, 6)]
        status, plan = self.request("POST", self.base + "/learned-apply-plan", payload)
        self.assertEqual(200, status, plan)
        self.assertEqual(payload["corrections"], plan["tracking"]["source"]["learned_corrections"])
        project["clips"][0].update(tracking=plan["tracking"], learned_recipe=plan["recipe"], learned_bindings=[plan["binding"]])
        saved = self.save(project)
        exported = self.start("render", {"profile": "master16", "project": saved})
        self.assertEqual(200, self.request("GET", exported["result"]["url"])[0])
        changed = copy.deepcopy(saved)
        changed["clips"][0]["reverse"] = True
        changed = self.save(changed)
        self.assertIn("invalidated", changed["clips"][0]["learned_bindings"][0])
        saved["revision"] = changed["revision"]
        self.assertNotIn("invalidated", self.save(saved)["clips"][0]["learned_bindings"][0])
        other = self.store.new_project({"name": "Different owned project"})
        unrelated_url = result["artifact_urls"]["result.json"].replace(self.project_id, other["id"])
        self.assertEqual(404, self.request("GET", unrelated_url)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)

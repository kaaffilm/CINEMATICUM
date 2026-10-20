"""HTTP and persistence tests. Any generated media here are test fixtures only."""
from __future__ import annotations
import copy
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from server import Store, Server, ConflictError, WorkspaceInUseError


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="cinematicum-http-test-fixtures-")
        cls.movie = Path(cls.fixtures.name) / "TEST_FIXTURE.mp4"
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=1", "-threads", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.movie)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cinematicum-server-tests-")
        self.store = Store(self.tmp.name)
        self.p = self.store.new_project({"name": "TEST PROJECT", "width": 160, "height": 90, "fps": 24})
        self.server = Server(0, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.shutdown()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, token=True):
        headers = dict(headers or {})
        if token:
            headers["X-Cinematicum-Token"] = self.store.token
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=20)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        status, rh, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        if rh.get("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return status, rh, data

    def upload(self):
        status, _, asset = self.request("POST", f"/api/projects/{self.p['id']}/import?name=TEST_FIXTURE.mp4", self.movie.read_bytes(), {"Content-Type": "application/octet-stream"})
        self.assertEqual(201, status, asset)
        return asset

    def add_clip(self, asset):
        p = self.store.get(self.p["id"])
        p["clips"] = [{"id": "clip1", "asset_id": asset["id"], "start": 0, "in": 0, "duration": 24, "track": 0}]
        return p

    def test_origin_host_token_and_json_are_required(self):
        path = "/api/projects"
        for headers, token in [({}, False), ({"Origin": "https://hostile.example"}, True), ({"Host": "hostile.example"}, True), ({"Sec-Fetch-Site": "cross-site"}, True)]:
            status, _, _ = self.request("POST", path, {"name": "bad"}, headers, token)
            self.assertEqual(403, status)
        status, _, _ = self.request("POST", path, b'{"name":"bad"}', {"Content-Type": "text/plain"})
        self.assertEqual(400, status)
        status, _, data = self.request("POST", path, {"name": "good"})
        self.assertEqual(201, status)
        self.assertEqual("good", data["name"])

    def test_import_ranges_metadata_and_no_path_read(self):
        asset = self.upload()
        self.assertEqual("video", asset["kind"])
        self.assertEqual(64, len(asset["sha256"]))
        media = f"/api/projects/{self.p['id']}/media/{asset['id']}"
        status, h, data = self.request("GET", media, headers={"Range": "bytes=0-31"})
        self.assertEqual(206, status)
        self.assertEqual(self.movie.read_bytes()[:32], data)
        self.assertEqual("bytes", h["Accept-Ranges"])
        status, _, data = self.request("GET", media, headers={"Range": "bytes=-16"})
        self.assertEqual(self.movie.read_bytes()[-16:], data)
        status, _, _ = self.request("GET", media, headers={"Range": "bytes=999999999-"})
        self.assertEqual(416, status)
        status, _, _ = self.request("GET", "/api/projects/../media/etc/passwd")
        self.assertIn(status, (400, 404))
        status, _, _ = self.request("GET", "/../../etc/passwd")
        self.assertEqual(404, status)

    def test_save_reopen_and_conflict_preserve_changes(self):
        asset = self.upload()
        p = self.add_clip(asset)
        status, _, saved = self.request("PUT", f"/api/projects/{p['id']}", p)
        self.assertEqual(200, status, saved)
        self.assertGreater(saved["revision"], p["revision"])
        p["name"] = "Stale edit"
        status, _, _ = self.request("PUT", f"/api/projects/{p['id']}", p)
        self.assertEqual(409, status)
        self.store.shutdown()
        self.store = Store(self.tmp.name)
        self.server.store = self.store
        reopened = self.store.get(p["id"])
        self.assertEqual(24, reopened["clips"][0]["duration"])
        self.assertEqual("TEST PROJECT", reopened["name"])

    def test_registry_cannot_be_overwritten_by_project_payload(self):
        asset = self.upload()
        p = self.add_clip(asset)
        p["assets"] = [{**asset, "path": "/etc/passwd"}]
        saved = self.store.save(p["id"], p)
        self.assertEqual(asset["path"], saved["assets"][0]["path"])
        outside = Path(self.tmp.name) / "outside.mp4"
        shutil.copy2(self.movie, outside)
        actual = self.store.project_dir(p["id"]) / asset["path"]
        actual.unlink()
        actual.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.save(p["id"], saved)

    def test_invalid_import_leaves_no_admitted_file(self):
        status, _, _ = self.request("POST", f"/api/projects/{self.p['id']}/import?name=invalid.mp4", b"not media", {"Content-Type": "application/octet-stream"})
        self.assertEqual(400, status)
        self.assertEqual([], self.store.get(self.p["id"])["assets"])
        self.assertEqual([], list(self.store.project_dir(self.p["id"]).glob("upload-*")))

    def test_async_export_is_real_playable_media(self):
        asset = self.upload()
        p = self.add_clip(asset)
        status, _, job = self.request("POST", f"/api/projects/{p['id']}/render", {"project": p, "profile": "h264"})
        self.assertEqual(202, status, job)
        p["clips"][0]["duration"] = 1  # Render owns its snapshot.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            _, _, completed = self.request("GET", f"/api/jobs/{job['id']}")
            if completed["state"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        self.assertEqual("completed", completed["state"], completed)
        self.assertAlmostEqual(1, completed["result"]["duration"], places=2)
        status, _, data = self.request("GET", completed["result"]["url"])
        self.assertEqual(200, status)
        self.assertGreater(len(data), 1000)
        report_path = self.store.project_dir(p["id"]) / "exports" / (job["id"] + ".json")
        self.assertEqual("NONE", json.loads(report_path.read_text())["issuance_effect"])

    def test_atomic_automation_and_invalid_recipe(self):
        asset = self.upload()
        p = self.add_clip(asset)
        p = self.store.save(p["id"], p)
        status, _, changed = self.request("POST", f"/api/projects/{p['id']}/automate", {"project": p, "operations": [{"action": "grade", "values": {"saturation": 0}}, {"action": "volume", "value": 0}]})
        self.assertEqual(200, status, changed)
        self.assertEqual(0, changed["clips"][0]["grade"]["saturation"])
        status, _, _ = self.request("POST", f"/api/projects/{p['id']}/automate", {"project": changed, "operations": [{"action": "grade", "values": {"saturation": 2}}, {"action": "shell", "command": "ignored"}]})
        self.assertEqual(400, status)
        self.assertEqual(0, self.store.get(p["id"])["clips"][0]["grade"]["saturation"])

    def test_ui_workflow_is_rejected_and_bootstrap_has_capabilities(self):
        status, _, body = self.request("POST", f"/api/projects/{self.p['id']}/workflow", {"nodes": [], "links": []})
        self.assertEqual(400, status)
        with patch("server.check_comfyui", return_value={"available": False, "reason": "test server absent"}):
            status, _, body = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status)
        self.assertEqual(self.store.token, body["token"])
        self.assertEqual(False, body["capabilities"]["comfyui"]["available"])


class WorkspaceLockTests(unittest.TestCase):
    """Exercise real OS process contention rather than mocking flock."""

    def other_process(self, workspace):
        program = """
import json, sys
from server import Store, WorkspaceInUseError
try:
    store = Store(sys.argv[1])
except WorkspaceInUseError as exc:
    print(json.dumps({"locked": True, "error": str(exc)}))
    raise SystemExit(73)
else:
    store.shutdown()
    print(json.dumps({"locked": False}))
"""
        result = subprocess.run([sys.executable, "-c", program, str(workspace)],
                                cwd=str(Path(__file__).resolve().parent), capture_output=True,
                                text=True, timeout=5)
        return result.returncode, json.loads(result.stdout)

    def test_second_process_cannot_recover_live_jobs_and_owner_releases(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-lock-tests-") as workspace:
            owner = Store(workspace)
            try:
                job_path = Path(workspace) / "jobs" / "owned-test-job.json"
                job_path.write_text(json.dumps({"id": "owned-test-job", "state": "running"}), encoding="utf-8")
                before = job_path.read_bytes()
                status, result = self.other_process(workspace)
                self.assertEqual(status, 73)
                self.assertTrue(result["locked"])
                self.assertIn("already in use", result["error"])
                self.assertEqual(job_path.read_bytes(), before, "Rejected process must not relabel a live job as interrupted")
            finally:
                owner.shutdown()
            owner.shutdown()  # Idempotent and must not affect the next owner.
            self.assertTrue((Path(workspace) / ".cinematicum-workspace.lock").is_file())
            status, result = self.other_process(workspace)
            self.assertEqual(status, 0)
            self.assertFalse(result["locked"])
            self.assertEqual(json.loads(job_path.read_text())["state"], "interrupted")

    def test_lock_remains_held_until_worker_finishes_shutdown(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-lock-worker-tests-") as workspace:
            owner = Store(workspace)
            started, cancellation_seen, allow_finish = threading.Event(), threading.Event(), threading.Event()

            def worker(job_id, progress, cancel):
                started.set()
                cancel.wait(timeout=5)
                cancellation_seen.set()
                allow_finish.wait(timeout=5)
                return {"fixture": "worker shutdown ordering test"}

            closer = None
            try:
                owner.submit("lock-test-project", "test", worker)
                self.assertTrue(started.wait(timeout=2))
                closer = threading.Thread(target=owner.shutdown)
                closer.start()
                self.assertTrue(cancellation_seen.wait(timeout=2))
                self.assertTrue(closer.is_alive())
                status, result = self.other_process(workspace)
                self.assertEqual(status, 73)
                self.assertTrue(result["locked"])
                allow_finish.set()
                closer.join(timeout=3)
                self.assertFalse(closer.is_alive())
                status, result = self.other_process(workspace)
                self.assertEqual(status, 0)
                self.assertFalse(result["locked"])
            finally:
                allow_finish.set()
                owner.shutdown()
                if closer is not None:
                    closer.join(timeout=1)

    def test_failed_initialization_releases_workspace_lock(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-lock-init-tests-") as workspace:
            obstruction = Path(workspace) / "projects"
            obstruction.write_text("Initialization failure test fixture", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                Store(workspace)
            obstruction.unlink()
            status, result = self.other_process(workspace)
            self.assertEqual(status, 0)
            self.assertFalse(result["locked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

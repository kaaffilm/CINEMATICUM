"""Real HTTP, project, TLS worker, recovery and portable scene acceptance."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import zipfile

from project_archive import export_archive, import_archive
from server import Server, Store
from test_scene_processing import fixture, read_frames, red_center


class SceneDispatchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-SCENE-HTTP-TEST-")
        self.root = Path(self.temp.name)
        self.instances = []
        self.open_store()

    def open_store(self, root=None, project_id=None):
        root = root or self.root / ("workspace-" + str(len(self.instances)))
        store = Store(root)
        project = store.get(project_id) if project_id else store.new_project({"name": "ENGINE TEST scene dispatch", "width": 64, "height": 48})
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        thread.start()
        self.instances.append({"store": store, "project": project, "server": server, "thread": thread})
        return len(self.instances) - 1

    def close_store(self, index):
        item = self.instances[index]
        if item.get("closed"):
            return
        item["server"].shutdown()
        item["server"].server_close()
        item["thread"].join()
        item["store"].shutdown()
        item["closed"] = True

    def tearDown(self):
        for index in reversed(range(len(self.instances))):
            self.close_store(index)
        self.temp.cleanup()

    def base(self, index=0):
        return "/api/projects/" + self.instances[index]["project"]["id"]

    def request(self, method, path, body=None, *, index=0, token=True):
        item = self.instances[index]
        headers = {"X-Cinematicum-Token": item["store"].token} if token else {}
        if body is not None:
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", item["server"].server_port, timeout=60)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status, response_headers, data = response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()
        if response_headers.get("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return status, response_headers, data

    def post(self, path, body, expected=200, index=0):
        status, _, result = self.request("POST", path, body, index=index)
        self.assertEqual(expected, status, result)
        return result

    def wait_job(self, job, index=0):
        deadline = time.monotonic() + 60
        while job["state"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.04)
            code, _, job = self.request("GET", "/api/jobs/" + job["id"], index=index)
            self.assertEqual(200, code, job)
        self.assertEqual("completed", job["state"], job)
        return job

    def start(self, name="local", index=0):
        result = self.post("/api/scene-workers/start", {"name": name}, index=index)
        return next(worker for worker in result["workers"] if worker["name"] == name)

    def submit(self, index=0, operation="ENGINE_TEST_batch", workers=None, frames=None):
        return self.post(self.base(index) + "/scene-dispatch",
                         {"graph": fixture(animated=True), "contexts": [{}], "frames": frames or [1, 3],
                          "workers": workers or ["local"], "operation_id": operation}, 202, index)

    def test_mutations_require_auth_and_reject_unowned_paths_before_work(self):
        before = self.instances[0]["store"].get(self.instances[0]["project"]["id"])
        for action in ("start", "pair", "invite", "revoke", "stop"):
            self.assertEqual(403, self.request("POST", "/api/scene-workers/" + action, {}, token=False)[0])
        self.assertEqual(403, self.request("POST", self.base() + "/scene-dispatch", {}, token=False)[0])
        for payload in ({"name": "../other"}, {"name": "local", "command": "render"}, {"name": "local", "directory": "/tmp/other"}):
            self.assertEqual(400, self.request("POST", "/api/scene-workers/start", payload)[0])
        self.assertEqual([], self.request("GET", "/api/scene-workers")[2]["workers"])
        self.assertFalse(self.instances[0]["store"].jobs)
        self.assertEqual(before, self.instances[0]["store"].get(before["id"]))

    def test_actual_local_graph_apply_undo_reopen_render_and_portable_semantic_paths(self):
        from scene_processing import compile_scene_graph
        store = self.instances[0]["store"]
        project_id = self.instances[0]["project"]["id"]
        graph = fixture(animated=True)
        graph["context"]["asset_path"] = {"type": "string", "default": "/character/hero"}
        for key in graph["assets"][0]["scene"]["objects"][0]["keyframes"]:
            key["rotation"] = [0, 0, 30]
        graph["nodes"].append({"id": "shear", "op": "transform", "input": "source", "space": "parent",
                               "filter": {"paths": ["/world/objects/box"]}, "transform": {"scale": [1.2, .8, 1]}})
        # An explicit camera node contains an absolute scene path, which must
        # remain a portable identity rather than become an external file path.
        graph["nodes"].append({"id": "camera", "op": "camera", "input": "shear", "path": "/world/camera"})
        graph["output"] = "camera"
        before = store.get(project_id)
        saved = self.post(self.base() + "/authoring-apply", {"tool": "scene-processing", "document": graph, "project": before})
        self.assertEqual(before["revision"] + 1, saved["revision"])
        normalized = saved["scene_processing"]
        undo = copy.deepcopy(before)
        undo["revision"] = saved["revision"]
        self.assertEqual(200, self.request("PUT", self.base(), undo)[0])
        self.assertNotIn("scene_processing", store.get(project_id))
        current = store.get(project_id)
        sampled = compile_scene_graph(normalized, {"frame": 3})["scene"]
        saved = self.post(self.base() + "/authoring-apply", {"tool": "scene-processing", "document": normalized,
                                                            "scene": sampled, "project": current})
        self.assertEqual(sampled, saved["settings"]["scene"])
        reopened = self.request("GET", self.base())[2]
        job = self.post(self.base() + "/scene-processing", {"recipe": {"operation": "render", "graph": reopened["scene_processing"], "context": {"frame": 3}}}, 202)
        job = self.wait_job(job)
        result = job["result"]
        self.assertEqual("video", result["asset"]["kind"])
        self.assertTrue(result["asset"]["name"].endswith(".mp4"))
        self.assertEqual("cinematicum-scene-processing", result["asset"]["provenance"]["type"])
        self.assertIn("authored.blend", result["artifact_urls"])
        self.assertEqual("/character/hero", result["receipt"]["context"]["asset_path"])
        self.assertEqual("/world/objects/box", result["receipt"]["baked_transforms"][0]["path"])
        self.assertEqual(200, self.request("GET", result["display_url"])[0])
        archive = self.root / "ENGINE_TEST_scene.cinematicum.zip"
        export_archive(store.get(project_id), store.project_dir(project_id), archive)
        restored = import_archive(archive, store.root / "projects")
        self.assertEqual(normalized, restored["scene_processing"])
        for name, url in result["artifact_urls"].items():
            status, _, data = self.request("GET", url.replace(project_id, restored["id"]))
            self.assertEqual(200, status, name)
            if name == "preview.mp4":
                preview = self.root / "restored.mp4"
                preview.write_bytes(data)
                self.assertEqual(1, len(read_frames(preview)))
        with self.assertRaisesRegex(ValueError, "external path"):
            corrupted = store.get(project_id)
            corrupted["unowned_file"] = "/outside/project.mov"
            export_archive(corrupted, store.project_dir(project_id), self.root / "invalid.zip")

    def test_two_http_studios_pair_two_actual_workers_and_publish_ordered_portable_results(self):
        self.start()
        invitation = self.post("/api/scene-workers/invite", {"name": "local"})
        peer = self.open_store()
        paired = self.post("/api/scene-workers/pair", {"name": "peer", "invitation": invitation,
                                                     "participant_name": "ENGINE TEST peer"}, index=peer)
        self.assertFalse(paired["workers"][0]["local"])
        self.start(index=peer)
        submitted = self.submit(index=peer, workers=["local", "peer"])
        job = self.wait_job(submitted["job"], peer)
        result = job["result"]
        self.assertEqual(submitted["batch"]["id"], result["output_id"])
        self.assertEqual(2, result["receipt"]["worker_count"])
        self.assertEqual(2, result["receipt"]["task_count"])
        code, _, data = self.request("GET", result["display_url"], index=peer)
        self.assertEqual(200, code)
        video = self.root / "ENGINE_TEST_actual_dispatch.mp4"
        video.write_bytes(data)
        frames = read_frames(video)
        self.assertEqual(2, len(frames))
        self.assertGreater(red_center(frames[1]), red_center(frames[0]) + 8)
        store, project_id = self.instances[peer]["store"], self.instances[peer]["project"]["id"]
        duplicate = self.submit(index=peer, workers=["local", "peer"])
        self.assertEqual(job["id"], duplicate["job"]["id"])
        self.assertEqual(1, len(store.jobs))
        status = self.request("GET", self.base(peer) + "/scene-dispatch/" + result["output_id"], index=peer)[2]
        self.assertEqual("completed", status["status"])
        self.assertNotIn("output", status)
        self.assertNotIn("token", json.dumps(status))
        archive = self.root / "ENGINE_TEST_dispatch.cinematicum.zip"
        export_archive(store.get(project_id), store.project_dir(project_id), archive)
        with zipfile.ZipFile(archive) as package:
            self.assertFalse(any("scene-services" in name or "binding" in name for name in package.namelist()))
        restored = import_archive(archive, store.root / "projects")
        for record in result["receipt"]["artifacts"]:
            url = result["artifact_urls"][record["filename"]].replace(project_id, restored["id"])
            code, _, body = self.request("GET", url, index=peer)
            self.assertEqual(200, code, record["filename"])
            if isinstance(body, dict):
                path = store.project_dir(restored["id"]) / "scene-processing" / "outputs" / result["output_id"] / record["filename"]
                body = path.read_bytes()
            self.assertEqual(record["sha256"], hashlib.sha256(body).hexdigest())
        history = self.request("GET", "/api/projects/" + restored["id"] + "/studio-results", index=peer)[2]["results"]
        self.assertEqual([result["output_id"]], [entry["output_id"] for entry in history])

    def test_reopen_keeps_listener_stopped_and_recovers_lost_admission_mapping_once(self):
        original_worker = self.start()
        submitted = self.submit(frames=[1])
        job = self.wait_job(submitted["job"])
        store = self.instances[0]["store"]
        project_id = self.instances[0]["project"]["id"]
        record_path = store.scene_workers.records / (submitted["batch"]["id"] + ".json")
        record = json.loads(record_path.read_text())
        record["job_id"] = None
        record_path.write_text(json.dumps(record))
        root = store.root
        self.close_store(0)
        reopened = self.open_store(root, project_id)
        rows = self.request("GET", "/api/scene-workers", index=reopened)[2]["workers"]
        self.assertFalse(rows[0]["running"])
        self.assertFalse(self.instances[reopened]["store"].scene_workers.services)
        status = self.request("GET", self.base(reopened) + "/scene-dispatch/" + submitted["batch"]["id"], index=reopened)[2]
        self.assertEqual(job["id"], status["job_id"])
        resumed_worker = self.start(index=reopened)
        for field in ("endpoint", "certificate_sha256", "worker_id", "client_id"):
            self.assertEqual(original_worker[field], resumed_worker[field])
        recovered = self.post(self.base(reopened) + "/scene-dispatch/" + submitted["batch"]["id"] + "/resume", {}, 202, reopened)
        self.assertEqual(job["id"], recovered["job"]["id"])
        self.assertEqual(1, len(self.instances[reopened]["store"].jobs))
        other = self.instances[reopened]["store"].new_project({"name": "ENGINE TEST unrelated", "width": 64, "height": 48})
        path = "/api/projects/" + other["id"] + "/scene-dispatch/" + submitted["batch"]["id"]
        self.assertEqual(404, self.request("GET", path, index=reopened)[0])
        self.assertEqual(404, self.request("POST", path + "/cancel", {}, index=reopened)[0])

    def test_queued_cancellation_settles_without_starting_work_then_retry_renders(self):
        self.start()
        store = self.instances[0]["store"]
        gate, entered = threading.Event(), threading.Event()
        def occupied():
            entered.set()
            gate.wait(30)
        blocker = store.pool.submit(occupied)
        self.assertTrue(entered.wait(2))
        try:
            submitted = self.submit(frames=[1])
            self.assertEqual("queued", submitted["job"]["state"])
            cancelled = self.post(self.base() + "/scene-dispatch/" + submitted["batch"]["id"] + "/cancel", {}, 202)
            self.assertEqual("cancelled", cancelled["job"]["state"])
            self.assertEqual("cancelled", cancelled["batch"]["status"])
            self.assertTrue(all(task["remote_id"] is None for task in cancelled["batch"]["tasks"]))
        finally:
            gate.set()
            blocker.result(5)
        retry = self.post(self.base() + "/scene-dispatch/" + submitted["batch"]["id"] + "/retry", {}, 202)
        self.assertNotEqual(submitted["job"]["id"], retry["job"]["id"])
        completed = self.wait_job(retry["job"])
        self.assertEqual(submitted["batch"]["id"], completed["result"]["output_id"])
        self.assertEqual(1, completed["result"]["receipt"]["task_count"])


if __name__ == "__main__":
    unittest.main()

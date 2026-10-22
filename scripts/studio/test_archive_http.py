"""Real archive HTTP transport and durable job lifecycle acceptance.

Synthetic pictures and tones are ENGINE TEST media only. Positive roundtrips
use actual ZIP/media bytes, HTTP uploads/downloads and decoded render output;
only a deliberately blocked queue is used to make cancellation deterministic.
"""
from __future__ import annotations

import copy
import hashlib
import http.client
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile

from project_archive import MAX_BYTES, MANIFEST
from server import Server, Store


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Real FFmpeg media is required")
class ArchiveHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="cinematicum-ARCHIVE-HTTP-SIGNALS-")
        cls.movie = Path(cls.fixtures.name) / "ENGINE_TEST_archive_source.mkv"
        cls.ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=32x24:r=12:d=0.5",
                    "-f", "lavfi", "-i", "sine=f=440:r=48000:d=0.5",
                    "-c:v", "ffv1", "-c:a", "pcm_s16le", str(cls.movie)])

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    @staticmethod
    def ffmpeg(arguments):
        return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y",
                               "-filter_complex_threads", "1", "-threads", "1"] + arguments,
                              check=True, capture_output=True, timeout=10).stdout

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-ARCHIVE-HTTP-TEST-")
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "workspace")
        self.project = self.store.new_project({"name": "ENGINE TEST archive HTTP", "fps": 12, "width": 32, "height": 24})
        self.directory = self.store.project_dir(self.project["id"])
        self.base = "/api/projects/" + self.project["id"]
        try:
            self.server = Server(0, self.store)
        except BaseException:
            self.store.shutdown()
            self.temp.cleanup()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()
        self.queue_releases = []

    def tearDown(self):
        for release in self.queue_releases:
            release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.store.shutdown()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None, *, token=True):
        headers = dict(headers or {})
        if token:
            headers["X-Cinematicum-Token"] = self.store.token
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status, received, data = response.status, dict(response.getheaders()), response.read()
            if received.get("Content-Type", "").startswith("application/json"):
                data = json.loads(data)
            return status, received, data
        finally:
            connection.close()

    def terminal(self, job, maximum=5):
        deadline = time.monotonic() + maximum
        while time.monotonic() < deadline:
            status, _, current = self.request("GET", "/api/jobs/" + job["id"])
            self.assertEqual(status, 200, current)
            if current["state"] not in {"queued", "running"}:
                return current
            time.sleep(.01)
        self.fail("Archive HTTP job did not reach a terminal state: " + str(job))

    def wait_no_uploads(self, maximum=1):
        deadline = time.monotonic() + maximum
        while time.monotonic() < deadline and list(self.directory.glob("archive-upload-*.zip")):
            time.sleep(.01)
        self.assertEqual(list(self.directory.glob("archive-upload-*.zip")), [], "Uploaded ZIP ownership was not released")

    def archive(self, project=None):
        status, _, job = self.request("POST", self.base + "/archive-export", {"project": project or self.store.get(self.project["id"])})
        self.assertEqual(status, 202, job)
        job = self.terminal(job)
        self.assertEqual(job["state"], "completed", job)
        self.assertEqual(job["kind"], "archive-export")
        status, headers, payload = self.request("GET", job["result"]["url"])
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertEqual(hashlib.sha256(payload).hexdigest(), job["result"]["sha256"])
        self.assertEqual(len(payload), job["result"]["size"])
        return payload, job

    def upload_archive(self, payload, **kwargs):
        return self.request("POST", self.base + "/archive-restore", payload,
                            {"Content-Type": "application/octet-stream"}, **kwargs)

    def block_queue(self):
        entered, release = threading.Event(), threading.Event()
        self.queue_releases.append(release)

        def work(_ident, _progress, cancelled):
            entered.set()
            while not release.wait(.01):
                if cancelled.is_set():
                    raise RuntimeError("ENGINE TEST queue owner cancelled")
            return {"engine_test_only": True}

        job = self.store.submit(self.project["id"], "engine-test-queue-owner", work)
        self.assertTrue(entered.wait(1), "Test queue owner did not start")
        return job, release

    def render_bytes(self, project):
        status, _, job = self.request("POST", "/api/projects/" + project["id"] + "/render", {"profile": "prores", "project": project})
        self.assertEqual(status, 202, job)
        job = self.terminal(job)
        self.assertEqual(job["state"], "completed", job)
        status, _, movie = self.request("GET", job["result"]["url"])
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(movie).hexdigest(), job["result"]["sha256"])
        path = self.root / (project["id"] + "-ENGINE_TEST.mov")
        path.write_bytes(movie)
        pixels = self.ffmpeg(["-i", str(path), "-map", "0:v:0", "-an", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"])
        pcm = self.ffmpeg(["-i", str(path), "-map", "0:a:0", "-vn", "-f", "s16le", "pipe:1"])
        return pixels, pcm

    def test_real_saved_media_export_attachment_restore_and_render_identity(self):
        media_bytes = self.movie.read_bytes()
        status, _, asset = self.request("POST", self.base + "/import?name=ENGINE_TEST_archive_source.mkv",
                                        media_bytes, {"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 201, asset)
        project = self.store.get(self.project["id"])
        project["clips"] = [{"id": "ENGINE_TEST_picture", "asset_id": asset["id"], "track": 0,
                             "start": 0, "in": 1, "duration": 4, "grade": {"exposure": .25}}]
        project["settings"]["preserve_this_edit"] = {"label": "ENGINE TEST authoring state"}
        status, _, project = self.request("PUT", self.base, project)
        self.assertEqual(status, 200, project)
        before = {name: (self.directory / name).read_bytes() for name in ("project.json", "assets.json", asset["path"])}
        forged = copy.deepcopy(project)
        forged["assets"] = [{"id": "external", "path": "/not-owned/source.mkv"}]
        payload, exported = self.archive(forged)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read(MANIFEST))
            archived_project = json.loads(archive.read("project.json"))
            self.assertEqual(archived_project["assets"], project["assets"], "Client inventory must never replace owned media")
            self.assertEqual(archive.read(asset["path"]), media_bytes)
            self.assertEqual(manifest["issuance_effect"], "NONE")
        status, _, restore = self.upload_archive(payload)
        self.assertEqual(status, 202, restore)
        restored_job = self.terminal(restore)
        self.assertEqual(restored_job["state"], "completed", restored_job)
        restored_id = restored_job["result"]["project_id"]
        self.assertNotEqual(restored_id, project["id"])
        status, _, restored = self.request("GET", "/api/projects/" + restored_id)
        self.assertEqual(status, 200, restored)
        self.assertEqual(restored["clips"], project["clips"])
        self.assertEqual(restored["settings"], project["settings"])
        self.assertEqual(restored["assets"], project["assets"])
        self.assertEqual(restored["revision"], 1)
        self.assertEqual(restored["archive_restore"]["archive_sha256"], exported["result"]["sha256"])
        self.assertEqual(restored["archive_restore"]["issuance_effect"], "NONE")
        self.assertEqual(len(self.store.projects()), 2)
        self.wait_no_uploads()
        for name, original in before.items():
            self.assertEqual((self.directory / name).read_bytes(), original)
        original_pixels, original_pcm = self.render_bytes(project)
        restored_pixels, restored_pcm = self.render_bytes(restored)
        self.assertEqual(len(original_pixels), 4 * 32 * 24 * 3)
        self.assertEqual(len(original_pcm), 16000 * 2 * 2)
        self.assertEqual(restored_pixels, original_pixels)
        self.assertEqual(restored_pcm, original_pcm)

    def test_auth_origin_mime_and_declared_upload_bound_block_before_write(self):
        for endpoint, body, mime in (("archive-export", b"{}", "application/json"),
                                     ("archive-restore", b"not a zip", "application/octet-stream")):
            for extra, token in (({}, False), ({"Origin": "https://invalid.example"}, True),
                                 ({"Sec-Fetch-Site": "cross-site"}, True), ({"Host": "invalid.example"}, True)):
                status, _, error = self.request("POST", self.base + "/" + endpoint, body,
                                                {"Content-Type": mime, **extra}, token=token)
                self.assertEqual(status, 403, error)
        for headers in ({"Content-Type": "application/zip"},
                        {"Content-Type": "application/octet-stream", "Content-Length": str(MAX_BYTES + 1)},
                        {"Content-Type": "application/octet-stream", "Transfer-Encoding": "chunked"}):
            status, _, error = self.request("POST", self.base + "/archive-restore", b"short", headers)
            self.assertEqual(status, 400, error)
        self.assertEqual(self.store.jobs, {})
        self.wait_no_uploads()
        self.assertEqual(len(self.store.projects()), 1)

    def test_bad_archive_is_a_failed_job_and_upload_is_removed(self):
        before = (self.directory / "project.json").read_bytes()
        status, _, job = self.upload_archive(b"ENGINE TEST invalid ZIP bytes")
        self.assertEqual(status, 202, job)
        result = self.terminal(job)
        self.assertEqual(result["state"], "failed", result)
        self.assertTrue(result["error"])
        self.wait_no_uploads()
        self.assertEqual((self.directory / "project.json").read_bytes(), before)
        self.assertEqual(len(self.store.projects()), 1)
        self.assertEqual(list((self.root / "workspace").glob(".cinematicum-import-*")), [])

    def test_interrupted_upload_is_removed_without_submitting_restore(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.putrequest("POST", self.base + "/archive-restore")
            connection.putheader("Content-Type", "application/octet-stream")
            connection.putheader("X-Cinematicum-Token", self.store.token)
            connection.putheader("Content-Length", "8192")
            connection.endheaders()
            connection.send(b"ENGINE TEST partial upload")
            connection.sock.shutdown(socket.SHUT_WR)
            response = connection.getresponse()
            self.assertEqual(response.status, 400, response.read())
        finally:
            connection.close()
        self.wait_no_uploads()
        self.assertEqual(self.store.jobs, {})
        self.assertEqual(len(self.store.projects()), 1)

    def test_cancel_queued_restore_releases_upload_before_queue_owner_finishes(self):
        payload, _ = self.archive()
        owner, release = self.block_queue()
        status, _, queued = self.upload_archive(payload)
        self.assertEqual(status, 202, queued)
        self.assertEqual(queued["state"], "queued")
        self.assertEqual(len(list(self.directory.glob("archive-upload-*.zip"))), 1)
        status, _, cancelled = self.request("POST", "/api/jobs/" + queued["id"] + "/cancel", {})
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled["state"], "cancelled")
        self.wait_no_uploads()
        self.assertEqual(self.store.job(owner["id"])["state"], "running", "The queued cancellation must not wait for another export")
        self.assertEqual(len(self.store.projects()), 1)
        release.set()

    def test_shutdown_cleans_never_started_restore_input_and_restart_keeps_original(self):
        payload, _ = self.archive()
        self.block_queue()
        status, _, queued = self.upload_archive(payload)
        self.assertEqual(status, 202, queued)
        self.assertEqual(queued["state"], "queued")
        self.assertEqual(len(list(self.directory.glob("archive-upload-*.zip"))), 1)
        original = (self.directory / "project.json").read_bytes()
        self.store.shutdown()
        self.wait_no_uploads()
        self.assertEqual((self.directory / "project.json").read_bytes(), original)
        with_store = Store(self.root / "workspace")
        try:
            self.assertEqual(len(with_store.projects()), 1)
            self.assertNotIn(with_store.job(queued["id"])["state"], {"queued", "running", "completed"})
        finally:
            with_store.shutdown()

    def test_full_queue_rejects_restore_and_releases_uploaded_bytes(self):
        payload, _ = self.archive()
        owner, release = self.block_queue()
        for _ in range(7):
            self.store.submit(self.project["id"], "engine-test-queued", lambda *_: {"engine_test_only": True})
        status, _, error = self.upload_archive(payload)
        self.assertEqual(status, 400, error)
        self.assertIn("queue is full", error["error"])
        self.wait_no_uploads()
        self.assertFalse(any(job["kind"] == "archive-restore" for job in self.store.jobs.values()))
        self.assertEqual(len(self.store.projects()), 1)
        release.set()

    def test_startup_only_removes_exact_owned_regular_orphan_uploads(self):
        original = (self.directory / "project.json").read_bytes()
        self.store.shutdown()
        orphan = self.directory / ("archive-upload-" + "a" * 32 + ".zip")
        orphan.write_bytes(b"ENGINE TEST upload interrupted before durable submission")
        ordinary = self.directory / "ENGINE_TEST_keep.zip"
        ordinary.write_bytes(b"ENGINE TEST unrelated user artifact")
        target = self.root / "ENGINE_TEST_external.zip"
        target.write_bytes(b"ENGINE TEST external file must survive")
        symlink = self.directory / ("archive-upload-" + "b" * 32 + ".zip")
        symlink.symlink_to(target)
        named_directory = self.directory / ("archive-upload-" + "c" * 32 + ".zip")
        named_directory.mkdir()
        unrelated_project = self.root / "workspace/projects/ENGINE_TEST_not_a_project"
        unrelated_project.mkdir()
        unrelated = unrelated_project / ("archive-upload-" + "d" * 32 + ".zip")
        unrelated.write_bytes(b"ENGINE TEST file outside the managed UUID namespace")
        reopened = Store(self.root / "workspace")
        try:
            self.assertFalse(orphan.exists())
            self.assertEqual((self.directory / "project.json").read_bytes(), original)
            self.assertEqual(ordinary.read_bytes(), b"ENGINE TEST unrelated user artifact")
            self.assertTrue(symlink.is_symlink())
            self.assertEqual(target.read_bytes(), b"ENGINE TEST external file must survive")
            self.assertTrue(named_directory.is_dir())
            self.assertTrue(unrelated.is_file())
            self.assertEqual(len(reopened.projects()), 1)
        finally:
            reopened.shutdown()


if __name__ == "__main__":
    unittest.main()

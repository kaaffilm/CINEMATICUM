"""Owned-runtime boundaries and transfer tests, without downloading model weights.

Loopback HTTP and small child-process fixtures test real cancellation/lifecycle.
They are explicitly not evidence that Wan inference ran; that requires the
installed Mac runtime and a decoded generated video.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from adapters import _bind_workflow, validate_workflow
import managed_generation as managed


def content_entry(data, url="https://files.pythonhosted.org/test/runtime.whl"):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "url": url}


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data); self.status = status
        self.headers = {"Content-Length": str(len(data)), **(headers or {})}


class Opener:
    def __init__(self, factory): self.factory = factory; self.requests = []
    def open(self, request, timeout=None):
        self.requests.append(request); return self.factory(request)


class ManagedGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-generation-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self): self.temporary.cleanup()

    def manager(self): return managed.ManagedGeneration(self.root / "Generation")

    def archive(self, extra=None, include_license=True):
        destination = self.root / (str(time.monotonic_ns()) + ".zip")
        commit = "a" * 40; prefix = "ComfyUI-" + commit + "/"
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr(prefix + "main.py", "print('source fixture')\n")
            if include_license: archive.writestr(prefix + "LICENSE", "Fixture license\n")
            if extra:
                for name, value in extra: archive.writestr(name.replace("$PREFIX/", prefix), value)
        return destination, commit

    def test_shipped_lock_has_exact_source_models_and_compatible_wheels(self):
        lock = managed.load_lock()
        self.assertEqual("63be2f9b82ad0dac88a7ceaa28a9cf3154125a18", lock["source"]["commit"])
        self.assertEqual(71, len(lock["packages"]))
        self.assertEqual(9_828_025_775, sum(p["size"] for p in lock["models"]))
        self.assertEqual(10_634_173_896, sum(p["size"] for p in [lock["source"], *lock["models"], *lock["packages"]]))
        for package in lock["packages"]:
            self.assertTrue(package["filename"].endswith(("any.whl", "arm64.whl", "universal2.whl")), package["filename"])
        altered = self.root / "lock.json"; altered.write_bytes(managed.LOCK_FILE.read_bytes() + b" ")
        with patch.object(managed, "LOCK_FILE", altered), self.assertRaisesRegex(ValueError, "does not match"):
            managed.load_lock()

    def test_status_and_constructor_do_not_create_directories_or_install(self):
        manager = self.manager()
        with patch.object(managed, "_run", side_effect=AssertionError("status must not spawn")), \
             patch.object(managed, "_download", side_effect=AssertionError("status must not download")):
            result = manager.status()
        self.assertFalse(manager.root.exists())
        self.assertFalse(result["installed"]); self.assertFalse(result["ready"])
        self.assertFalse(result["model_execution_verified"])

    def test_foreign_directory_and_symlinks_are_not_adopted(self):
        manager = self.manager(); manager.root.mkdir(); foreign = manager.root / "foreign.txt"; foreign.write_text("Keep me")
        with self.assertRaisesRegex(ValueError, "no CINEMATICUM owner"): manager._ensure_root()
        self.assertEqual("Keep me", foreign.read_text()); foreign.unlink(); manager._ensure_root()
        outside = self.root / "outside"; outside.mkdir(); (manager.root / "models").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"): manager._owned("models/file")
        with self.assertRaisesRegex(ValueError, "Invalid"): manager._owned("../outside/file")

    def test_pre_cancelled_install_does_not_create_or_download(self):
        manager = self.manager(); event = threading.Event(); event.set()
        with patch.object(managed, "host_support", return_value={"supported": True}), \
             patch.object(managed, "choose_python") as choose, self.assertRaisesRegex(RuntimeError, "cancelled"):
            manager.install(event=event)
        choose.assert_not_called(); self.assertFalse(manager.root.exists())
        self.assertIsNone(manager.status()["operation"])

    def test_default_workflow_binds_real_video_and_tiled_decode(self):
        graph = self.manager().default_workflow()
        validate_workflow(graph)
        bound, bindings = _bind_workflow(graph, "rain over an empty road", "text", 77)
        self.assertEqual(77, bound["3"]["inputs"]["seed"])
        self.assertEqual("rain over an empty road", bound["6"]["inputs"]["text"])
        self.assertTrue(bindings["seed"]); self.assertTrue(bindings["negative"])
        self.assertEqual("VAEDecodeTiled", graph["8"]["class_type"])
        self.assertEqual("cpu", graph["38"]["inputs"]["device"])
        self.assertEqual("mp4", graph["50"]["inputs"]["format"])
        self.assertEqual("h264", graph["50"]["inputs"]["format.codec"])
        self.assertEqual("re-encode", graph["50"]["inputs"]["format.codec.encoding"])
        self.assertEqual("CINEMATICUM_SEED", graph["3"]["inputs"]["seed"])
        self.assertEqual("euler", graph["3"]["inputs"]["sampler_name"])
        self.assertEqual("simple", graph["3"]["inputs"]["scheduler"])

    def test_shot_bounds_reject_unsupported_or_nonfinite_values(self):
        bad = [{"width": 481}, {"width": True}, {"height": 512}, {"length": 18}, {"length": 85},
               {"steps": 3}, {"steps": 4.5}, {"cfg": float("nan")}, {"fps": float("inf")},
               {"fps": False}, {"unknown": 1}]
        for options in bad:
            with self.subTest(options=options), self.assertRaises(ValueError): managed.default_workflow(options)
        graph = managed.default_workflow({"width": 272, "height": 480, "length": 9, "steps": 4, "fps": 8})
        self.assertEqual(480, graph["40"]["inputs"]["height"])

    def test_resume_checks_range_and_hash_before_publication(self):
        payload = b"actual verified content" * 1000; entry = content_entry(payload); destination = self.root / "weights.bin"
        partial = destination.with_name(destination.name + "." + entry["sha256"][:12] + ".part"); partial.write_bytes(payload[:73])
        opener = Opener(lambda request: Response(payload[73:], 206, {"Content-Range": "bytes 73-%d/%d" % (len(payload)-1, len(payload))}))
        self.assertEqual(len(payload)-73, managed._remaining_download(entry, destination))
        progress = []
        with patch.object(managed.urllib.request, "build_opener", return_value=opener):
            managed._download(entry, destination, progress=progress.append)
        self.assertEqual("bytes=73-", opener.requests[0].get_header("Range"))
        self.assertEqual(payload, destination.read_bytes()); self.assertFalse(partial.exists()); self.assertEqual(len(payload), progress[-1])
        self.assertEqual(0, managed._remaining_download(entry, destination))

    def test_server_ignoring_range_restarts_the_owned_partial(self):
        payload = b"exact bytes" * 300; entry = content_entry(payload); destination = self.root / "weights.bin"
        destination.with_name(destination.name + "." + entry["sha256"][:12] + ".part").write_bytes(payload[:81])
        with patch.object(managed.urllib.request, "build_opener", return_value=Opener(lambda _: Response(payload))):
            managed._download(entry, destination)
        self.assertEqual(payload, destination.read_bytes())

    def test_wrong_hash_length_range_and_redirect_fail_closed(self):
        payload = b"known bytes"; entry = content_entry(payload)
        responses = [Response(b"other bytes"), Response(payload, headers={"Content-Length": "999"}),
                     Response(payload, 206, {"Content-Range": "bytes 1-11/12"})]
        for index, response in enumerate(responses):
            destination = self.root / (str(index) + ".bin")
            with self.subTest(index=index), patch.object(managed.urllib.request, "build_opener", return_value=Opener(lambda _: response)), \
                 self.assertRaises(ValueError): managed._download(entry, destination)
            self.assertFalse(destination.exists())
        for url in ("http://huggingface.co/model", "https://huggingface.co.evil.invalid/weight", "https://user:secret@huggingface.co/a", "https://huggingface.co:8188/a", "file:///tmp/model"):
            with self.subTest(url=url), self.assertRaises(ValueError): managed._safe_url(url)
        for url in ("https://cdn-lfs.huggingface.co/a", "https://cas-bridge.xethub.hf.co/a", "https://files.pythonhosted.org/a"):
            self.assertEqual(url, managed._safe_url(url))

    def test_trickling_http_can_cancel_before_one_megabyte_arrives(self):
        payload = b"x" * (1024 * 1024); event = threading.Event(); destination = self.root / "trickle.bin"
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers()
                try:
                    for offset in range(0, len(payload), 128):
                        self.wfile.write(payload[offset:offset+128]); self.wfile.flush(); time.sleep(.01)
                except (OSError, ValueError): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        timer = threading.Timer(.15, event.set); timer.start(); began = time.monotonic()
        try:
            entry = content_entry(payload, "http://127.0.0.1:%d/model" % server.server_port)
            with patch.object(managed, "_safe_url", side_effect=lambda url: url), self.assertRaisesRegex(RuntimeError, "cancelled"):
                managed._download(entry, destination, event)
            elapsed = time.monotonic() - began
            self.assertLess(elapsed, 1.0)
            partial = destination.with_name(destination.name + "." + entry["sha256"][:12] + ".part")
            self.assertGreater(partial.stat().st_size, 0); self.assertLess(partial.stat().st_size, len(payload)); self.assertFalse(destination.exists())
        finally:
            event.set(); timer.cancel(); server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_download_deadline_retains_a_resumable_partial(self):
        payload = b"bounded download"; entry = content_entry(payload); destination = self.root / "bounded.bin"
        with patch.object(managed.urllib.request, "build_opener", return_value=Opener(lambda _: Response(payload))), \
             patch.object(managed, "DOWNLOAD_MAX_SECONDS", -1), self.assertRaisesRegex(RuntimeError, "six-hour limit"):
            managed._download(entry, destination)
        self.assertFalse(destination.exists())
        self.assertTrue(destination.with_name(destination.name + "." + entry["sha256"][:12] + ".part").exists())

    def test_extraction_keeps_license_and_records_actual_source_hashes(self):
        archive, commit = self.archive(); destination = self.root / "source"
        manifest = managed.extract_source(archive, destination, commit)
        self.assertEqual(commit, manifest["commit"])
        self.assertEqual({"main.py", "LICENSE"}, {f["path"] for f in manifest["files"]})
        for item in manifest["files"]:
            data = (destination / item["path"]).read_bytes()
            self.assertEqual(len(data), item["size"]); self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])

    def test_source_archive_rejects_traversal_links_and_missing_license(self):
        for entry in ("$PREFIX/../../escape", "/absolute", "$PREFIX/evil\\path"):
            archive, commit = self.archive([(entry, "bad")])
            with self.subTest(entry=entry), self.assertRaises(ValueError): managed.extract_source(archive, self.root / "out", commit)
            self.assertFalse((self.root / "out").exists())
        archive, commit = self.archive(); link = zipfile.ZipInfo("ComfyUI-" + commit + "/link"); link.create_system=3; link.external_attr=(stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "a") as stream: stream.writestr(link, "../../other")
        with self.assertRaisesRegex(ValueError, "unsupported path or link"): managed.extract_source(archive, self.root / "linked", commit)
        archive, commit = self.archive(include_license=False)
        with self.assertRaisesRegex(ValueError, "engine or license"): managed.extract_source(archive, self.root / "unlicensed", commit)

    def test_source_verification_detects_modified_extra_and_linked_code(self):
        manager = self.manager(); manager._ensure_root(); version = manager._owned("versions/wan21-v1-" + "b"*32, mkdir=True)
        archive, commit = self.archive(); source = version / "ComfyUI"; manifest = managed.extract_source(archive, source, commit)
        receipt = {"source_manifest_sha256": managed._atomic_json(version / "source-files.json", manifest)}
        (source / "main.py").write_text("modified\n")
        with self.assertRaisesRegex(ValueError, "source identity changed"): manager._verify(version, receipt, None)
        (source / "main.py").write_text("print('source fixture')\n"); (source / "unreviewed.py").write_text("bad")
        with self.assertRaisesRegex(ValueError, "files changed"): manager._verify(version, receipt, None)
        (source / "unreviewed.py").unlink(); (source / "main.py").unlink(); (source / "main.py").symlink_to(self.root / "outside")
        with self.assertRaises((OSError, ValueError)): manager._verify(version, receipt, None)

    def test_child_command_cancellation_terminates_only_its_process_group(self):
        event = threading.Event(); marker = self.root / "pid.txt"
        foreign = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
        timer = threading.Timer(.2, event.set); timer.start()
        try:
            program = "import os,pathlib,time;pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(30)" % str(marker)
            with self.assertRaisesRegex(RuntimeError, "cancelled"): managed._run([sys.executable, "-c", program], event)
            self.assertTrue(marker.exists()); pid = int(marker.read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
            self.assertIsNone(foreign.poll())
        finally:
            timer.cancel(); managed._stop(foreign)

    @contextmanager
    def startup_fixture(self, manager, *, foreign_endpoint=False, ready=True):
        """Actual OS child and flock; schema/network are explicit fixtures."""
        manager._ensure_root(); version = manager._owned("versions/wan21-v1-" + "c"*32, mkdir=True)
        (version / "ComfyUI").mkdir(exist_ok=True); captured = {}; real_popen = subprocess.Popen
        def launch(command, **kwargs):
            captured["arguments"] = json.loads(command[-1])
            child = real_popen([sys.executable, "-c", "import time;time.sleep(30)"], **kwargs)
            captured["process"] = child; return child
        def stats(url, path, **kwargs):
            self.assertEqual("/system_stats", path)
            return {"system": {"argv": ["foreign"] if foreign_endpoint else captured["arguments"]}}
        with patch.object(manager, "_installation", return_value=(version, {})), patch.object(manager, "_verify"), \
             patch.object(managed.subprocess, "Popen", side_effect=launch), patch("adapters._json_request", side_effect=stats), \
             patch("generation_readiness.workflow_readiness", return_value={"ready": ready, "errors": [] if ready else ["Missing model"]}):
            try: yield captured
            finally: manager.stop()

    def test_restart_after_owned_process_exit_releases_previous_lock_and_log(self):
        manager = self.manager(); manager._ensure_root()
        dead = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True); dead.wait(timeout=5)
        old_log = (manager.root / "old.log").open("wb"); old_lock = manager._file_lock("runtime.lock"); old_lock.__enter__()
        manager._process=dead; manager._log=old_log; manager._runtime_lock=old_lock; manager._ready=True
        self.assertFalse(manager.status()["running"])
        with self.startup_fixture(manager) as state:
            result = manager.start()
            self.assertTrue(result["ready"]); self.assertTrue(old_log.closed); self.assertIsNone(result["operation"])
            self.assertTrue(result["base_url"].startswith("http://127.0.0.1:")); self.assertFalse(result["model_execution_verified"])
            self.assertIn("--disable-all-custom-nodes", state["arguments"])
            self.assertIn("--offline", state["arguments"])
            self.assertNotIn("8188", state["arguments"])
            self.assertIsNone(state["process"].poll())
        self.assertIsNotNone(state["process"].poll())

    def test_foreign_endpoint_or_failed_preflight_cannot_claim_ready(self):
        for foreign, ready in ((True, True), (False, False)):
            manager = self.manager()
            with self.subTest(foreign=foreign, ready=ready), self.startup_fixture(manager, foreign_endpoint=foreign, ready=ready) as state:
                with self.assertRaisesRegex(RuntimeError, "does not belong|not ready"): manager.start()
                self.assertFalse(manager.status()["ready"]); self.assertIsNotNone(state["process"].poll())
                self.assertIsNone(manager._runtime_lock)


if __name__ == "__main__": unittest.main()

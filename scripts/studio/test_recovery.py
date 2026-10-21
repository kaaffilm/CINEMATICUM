"""Loss, concurrency and restart tests for real on-disk editor checkpoints."""
import copy
import http.client
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

from server import Store, Server, ConflictError
import recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-RECOVERY-TEST-")
        self.store = Store(self.temp.name)
        self.project = self.store.new_project({"name": "ENGINE TEST recovery", "width": 160, "height": 90})
        self.editor = "1" * 32
        self.other = "2" * 32

    def tearDown(self):
        self.store.shutdown()
        self.temp.cleanup()

    def checkpoint(self, project=None, serial=1, editor=None):
        p = copy.deepcopy(project or self.project)
        p["name"] = "ENGINE TEST unsaved %d" % serial
        return self.store.checkpoint(p["id"], {"project": p, "editor_id": editor or self.editor, "sequence": serial})

    def test_restart_recovers_unsaved_titles_and_scene_without_committing(self):
        p = copy.deepcopy(self.project)
        p["titles"] = [{"id": "unsaved-title", "text": "ENGINE TEST unsaved title", "start": 0, "duration": 24}]
        p["settings"]["last_prompt"] = "ENGINE TEST scene intent"
        before = (self.store.project_dir(p["id"]) / "project.json").read_bytes()
        self.checkpoint(p)
        self.store.shutdown()
        self.store = Store(self.temp.name)
        listed = self.store.recovery(p["id"])
        self.assertEqual(len(listed["drafts"]), 1)
        recovered = self.store.recovery(p["id"], {"action": "restore", "kind": "draft", "key": self.editor, "sequence": 1})
        self.assertFalse(recovered["committed"])
        self.assertEqual(recovered["project"]["titles"][0]["text"], p["titles"][0]["text"])
        self.assertEqual(before, (self.store.project_dir(p["id"]) / "project.json").read_bytes())
        self.assertEqual(self.store.get(p["id"])["name"], self.project["name"])

    def test_late_and_duplicate_requests_cannot_replace_newer_draft(self):
        self.checkpoint(serial=2)
        self.assertFalse(self.checkpoint(serial=1)["checkpointed"])
        self.assertFalse(self.checkpoint(serial=2)["checkpointed"])
        p = copy.deepcopy(self.project); p["settings"]["extra"] = "different bytes"
        with self.assertRaisesRegex(ValueError, "different edits"):
            self.checkpoint(p, serial=2)
        with self.assertRaisesRegex(ValueError, "draft changed"):
            self.store.recovery(p["id"], {"action": "discard", "key": self.editor, "sequence": 1})
        self.assertEqual(self.store.recovery(p["id"])["drafts"][0]["sequence"], 2)

    def test_save_acknowledges_only_matching_editor_and_older_sequence(self):
        self.checkpoint(serial=1)
        self.checkpoint(serial=1, editor=self.other)
        saved = copy.deepcopy(self.project)
        saved["_recovery"] = {"editor_id": self.editor, "sequence": 1}
        self.store.save(saved["id"], saved)
        drafts = self.store.recovery(saved["id"])["drafts"]
        self.assertEqual([x["key"] for x in drafts], [self.other])
        self.assertTrue(drafts[0]["stale"])
        with self.assertRaises(ConflictError):
            self.checkpoint(serial=2)
        self.assertNotIn("_recovery", self.store.get(saved["id"]))

    def test_snapshot_saved_before_newer_draft_does_not_delete_the_draft(self):
        self.checkpoint(serial=3)
        saved = copy.deepcopy(self.project)
        saved["_recovery"] = {"editor_id": self.editor, "sequence": 2}
        self.store.save(saved["id"], saved)
        self.assertEqual(self.store.recovery(saved["id"])["drafts"][0]["sequence"], 3)

    def test_failed_checkpoint_and_failed_project_replace_preserve_prior_bytes(self):
        self.checkpoint(serial=1)
        directory = self.store.project_dir(self.project["id"])
        path = directory / "recovery" / (self.editor + ".json")
        before = path.read_bytes()
        with patch("server.os.replace", side_effect=OSError("ENGINE TEST simulated interrupted replace")):
            with self.assertRaises(OSError):
                self.checkpoint(serial=2)
        self.assertEqual(path.read_bytes(), before)
        saved_before = (directory / "project.json").read_bytes()
        with patch("server.os.replace", side_effect=OSError("ENGINE TEST simulated interruption")):
            with self.assertRaises(OSError):
                self.store.save(self.project["id"], self.project)
        self.assertEqual((directory / "project.json").read_bytes(), saved_before)
        self.assertEqual(path.read_bytes(), before)

    def test_saved_history_is_bounded_and_recovery_is_validated(self):
        p = self.project
        for index in range(23):
            p["name"] = "ENGINE TEST save %d" % index
            p = self.store.save(p["id"], p)
        versions = self.store.recovery(p["id"])["versions"]
        self.assertEqual(len(versions), 20)
        result = self.store.recovery(p["id"], {"action": "restore", "kind": "version", "key": versions[-1]["key"]})
        self.assertEqual(result["project"]["revision"], p["revision"])
        self.assertNotEqual(result["project"]["name"], p["name"])
        self.assertEqual(self.store.get(p["id"])["name"], p["name"])

    def test_interrupted_save_then_new_media_admission_does_not_block_future_save(self):
        directory = self.store.project_dir(self.project["id"])
        replace = os.replace
        def interrupt_project(source, destination):
            if Path(destination) == directory / "project.json":
                raise OSError("ENGINE TEST interrupted committed-project replace")
            return replace(source, destination)
        with patch("server.os.replace", side_effect=interrupt_project):
            with self.assertRaises(OSError):
                self.store.save(self.project["id"], self.project)
        archive = directory / "versions" / "000000000001.json"
        archived = archive.read_bytes()
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        picture = Path(self.temp.name) / "ENGINE_TEST_admitted_after_interruption.png"
        picture.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0)) +
                            chunk(b"IDAT", zlib.compress((b"\x00" + bytes([40, 80, 120]) * 16) * 16)) + chunk(b"IEND", b""))
        asset = self.store.admit(self.project["id"], picture, picture.name)
        project = self.store.get(self.project["id"])
        project["name"] = "ENGINE TEST successful save after interruption"
        saved = self.store.save(project["id"], project)
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(archive.read_bytes(), archived)
        restored = self.store.recovery(project["id"], {"action": "restore", "kind": "version", "key": "000000000001"})
        self.assertEqual(restored["project"]["assets"][0]["id"], asset["id"])
        self.assertEqual(restored["project"]["name"], self.project["name"])

    def test_corruption_symlinks_and_invalid_identifiers_never_restore(self):
        self.checkpoint()
        directory = self.store.project_dir(self.project["id"])
        path = directory / "recovery" / (self.editor + ".json")
        data = json.loads(path.read_text()); data["project"]["name"] = "altered"
        path.write_text(json.dumps(data))
        self.assertEqual(self.store.recovery(self.project["id"])["unreadable"], 1)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.store.recovery(self.project["id"], {"action": "restore", "kind": "draft", "key": self.editor, "sequence": 1})
        for invalid in ("../project", "1" * 31, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.checkpoint(editor=invalid)
        outside = Path(self.temp.name) / "ENGINE_TEST_preserve.json"
        outside.write_text("preserved")
        path.unlink();path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.checkpoint()
        self.assertEqual(outside.read_text(), "preserved")

    def test_http_checkpoint_requires_token_and_recovery_candidate_stays_unsaved(self):
        httpd = Server(0, self.store)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True); worker.start()
        def request(method, suffix, body=None, authorized=True):
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            headers = {"Content-Type": "application/json"}
            if authorized: headers["X-Cinematicum-Token"] = self.store.token
            conn.request(method, "/api/projects/" + self.project["id"] + suffix,
                         None if body is None else json.dumps(body), headers)
            response = conn.getresponse(); result = response.status, json.loads(response.read());conn.close();return result
        try:
            body = {"editor_id": self.editor, "sequence": 1, "project": self.project}
            self.assertEqual(request("POST", "/checkpoint", body, False)[0], 403)
            self.assertEqual(request("POST", "/checkpoint", body)[0], 200)
            self.assertEqual(len(request("GET", "/recovery")[1]["drafts"]), 1)
            status, result = request("POST", "/recovery", {"action": "restore", "kind": "draft", "key": self.editor, "sequence": 1})
            self.assertEqual(status, 200)
            self.assertFalse(result["committed"])
            self.assertEqual(self.store.get(self.project["id"])["revision"], self.project["revision"])
        finally:
            httpd.shutdown();httpd.server_close();worker.join()


if __name__ == "__main__":
    unittest.main()

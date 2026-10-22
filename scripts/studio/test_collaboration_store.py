"""Real paired Studio workspaces: media, merged edits, undo and crash recovery."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import uuid
import zipfile

from collaboration import Client, ConflictError
from collaboration_store import _write, _read, _journal_digest, _copy_verified, _hash
from server import Store, digest_file


class CollaborativeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-COLLABORATION-STORE-TEST-")
        self.root = Path(self.temporary.name)
        self.first = Store(self.root / "first")
        self.second = Store(self.root / "second")
        self.stores = [self.first, self.second]
        project = self.first.new_project({"name": "ENGINE TEST paired media", "width": 32, "height": 24})
        self.first_id = project["id"]
        original = self.root / "ENGINE_TEST_color.png"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=red:s=32x24",
                        "-frames:v", "1", "-threads", "1", str(original)], check=True, timeout=15,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.original_hash = digest_file(original)
        asset = self.first.admit(project["id"], original, "Red source.png")
        project = self.first.get(self.first_id)
        project["clips"] = [{"id": "picture", "asset_id": asset["id"], "start": 0, "duration": 4, "track": 0}]
        self.first.save(self.first_id, project)
        self.anchor = self.second.new_project({"name": "Unchanged second workspace", "width": 32, "height": 24})
        self.first.collaboration.create(self.first_id, {"name": "First", "host": "127.0.0.1", "port": 0})
        invitation = self.first.collaboration.invite(self.first_id, {})["invitation"]
        joined = self.second.collaboration.join(self.anchor["id"], {"invitation": invitation, "name": "Second"})
        self.second_id = joined["project"]["id"]

    def tearDown(self):
        for store in reversed(self.stores):
            store.shutdown()
        self.temporary.cleanup()

    def sync(self, store, project_id):
        return store.collaboration.sync(project_id, {"revision": store.get(project_id)["revision"]})["project"]

    def test_two_real_stores_merge_clip_edits_and_transfer_owned_media(self):
        first = self.first.get(self.first_id)
        second = self.second.get(self.second_id)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["assets"], second["assets"])
        self.assertEqual(self.anchor, self.second.get(self.anchor["id"]))
        owned = self.second.project_dir(self.second_id) / second["assets"][0]["path"]
        self.assertEqual(self.original_hash, digest_file(owned))
        first["clips"][0]["x"] = .125
        second["clips"][0]["opacity"] = .5
        self.first.save(self.first_id, first)
        self.second.save(self.second_id, second)
        merged = self.sync(self.first, self.first_id)
        self.assertEqual(.125, merged["clips"][0]["x"])
        self.assertEqual(.5, merged["clips"][0]["opacity"])
        peer = self.second.get(self.second_id)
        self.assertEqual(merged["clips"], peer["clips"])
        from engine import render_project, probe_media
        output = self.root / "ENGINE_TEST_collaboration.mp4"
        render_project(peer, self.second.project_dir(self.second_id), output, profile="h264")
        report = probe_media(output)
        self.assertEqual((32, 24), (report["width"], report["height"]))
        self.assertGreater(report["duration"], .1)

    def test_same_property_conflict_preserves_draft_base_and_clears_rejected_operation(self):
        first, second = self.first.get(self.first_id), self.second.get(self.second_id)
        first["name"], second["name"] = "First accepted edit", "Second conflicting edit"
        before_second = self.second.get(self.second_id)
        self.first.save(self.first_id, first)
        with self.assertRaises(ConflictError) as conflict:
            self.second.save(self.second_id, second)
        self.assertEqual("edit_conflict", conflict.exception.code)
        self.assertEqual(before_second, self.second.get(self.second_id))
        self.assertFalse(self.second.collaboration.status(self.second_id)["pending_operation"])
        self.assertEqual("First accepted edit", self.sync(self.second, self.second_id)["name"])

    def test_selective_undo_retains_the_other_participants_edit(self):
        first, second = self.first.get(self.first_id), self.second.get(self.second_id)
        first["clips"][0]["x"], second["clips"][0]["opacity"] = .125, .6
        self.first.save(self.first_id, first)
        event = self.first.collaboration.status(self.first_id)["own_events"][-1]
        self.second.save(self.second_id, second)
        current = self.sync(self.first, self.first_id)
        result = self.first.collaboration.undo(self.first_id, {"event_id": event, "revision": current["revision"]})
        self.assertEqual(0, result["project"]["clips"][0]["x"])
        self.assertEqual(.6, result["project"]["clips"][0]["opacity"])
        self.assertEqual(result["project"]["clips"], self.sync(self.second, self.second_id)["clips"])

    def test_actual_coordinator_restart_is_explicit_and_keeps_pairing_and_database(self):
        original = self.first.collaboration.status(self.first_id)
        root = self.first.root
        self.first.shutdown()
        reopened = Store(root)
        self.stores.append(reopened)
        self.first = reopened
        status = reopened.collaboration.status(self.first_id)
        self.assertTrue(status["active"])
        self.assertFalse(status["host_running"])
        result = reopened.collaboration.resume(self.first_id, {})
        self.assertTrue(result["status"]["host_running"])
        self.assertEqual(original["url"], result["status"]["url"])
        project = self.second.get(self.second_id)
        project["name"] = "Accepted after TLS restart"
        self.second.save(self.second_id, project)
        self.assertEqual(project["name"], self.sync(reopened, self.first_id)["name"])

    def test_pairing_secrets_never_enter_portable_project_or_shared_status(self):
        from project_archive import export_archive
        binding = self.first.collaboration._binding(self.first_id)
        token = binding["connection"]["token"].encode()
        status = json.dumps(self.first.collaboration.status(self.first_id)).encode()
        self.assertNotIn(token, status)
        private = self.first.collaboration._path(self.first_id)
        self.assertEqual(0o600, private.stat().st_mode & 0o777)
        output = self.root / "ENGINE_TEST_paired.cinematicum.zip"
        export_archive(self.first.get(self.first_id), self.first.project_dir(self.first_id), output)
        with zipfile.ZipFile(output) as package:
            self.assertFalse(any("collaboration" in name or "binding" in name for name in package.namelist()))
            for name in package.namelist():
                self.assertNotIn(token, package.read(name))

    def test_committed_remote_operation_replays_once_after_local_restart(self):
        # Simulate a process exit between a real coordinator commit and its
        # local materialization. The exact pending request is journaled first.
        manager = self.second.collaboration
        record = manager._binding(self.second_id)
        client = Client(record["connection"])
        snapshot = client.snapshot()
        proposal = copy.deepcopy(snapshot["project"])
        proposal["name"] = "Recovered once"
        operation_id = uuid.uuid4().hex
        record["pending"] = {"kind": "save", "project": proposal, "dependencies": snapshot["dependencies"],
                             "base_revision": snapshot["revision"], "operation_id": operation_id}
        _write(manager._path(self.second_id), record)
        committed = client.submit(proposal, snapshot["dependencies"], snapshot["revision"], operation_id)
        root = self.second.root
        self.second.shutdown()
        reopened = Store(root)
        self.stores.append(reopened)
        self.second = reopened
        recovered = self.sync(reopened, self.second_id)
        self.assertEqual("Recovered once", recovered["name"])
        self.assertEqual(committed["revision"], client.snapshot()["revision"])
        self.assertFalse(reopened.collaboration.status(self.second_id)["pending_operation"])
        self.assertEqual([committed["event_id"]], reopened.collaboration.status(self.second_id)["own_events"])

    def test_leaving_keeps_local_project_and_does_not_publish_future_edits(self):
        before = self.second.get(self.second_id)
        result = self.second.collaboration.leave(self.second_id, {})
        self.assertEqual(before, result["project"])
        self.assertFalse(result["status"]["active"])
        after = self.second.get(self.second_id)
        after["name"] = "Local independent edit"
        self.second.save(self.second_id, after)
        self.assertNotEqual(after["name"], self.sync(self.first, self.first_id)["name"])

    def _stage_committed_remote_edit(self):
        project = self.first.get(self.first_id)
        project["name"] = "Remote edit awaiting local commit"
        self.first.save(self.first_id, project)
        manager = self.second.collaboration
        record = manager._binding(self.second_id)
        snapshot = Client(record["connection"]).snapshot()
        current = self.second.get(self.second_id)
        stage, materialized = manager._materialize(record, snapshot, current)
        with mock.patch.object(manager, "_finish_transaction", side_effect=OSError("Injected process exit before local replay")):
            with self.assertRaisesRegex(OSError, "Injected process exit"):
                manager._commit(record, snapshot, stage, materialized, current)
        path = manager.transactions / (self.second_id + ".json")
        return manager, path, _read(path)

    def test_real_committed_project_and_new_media_recover_after_interrupted_local_publish(self):
        # The actual TLS commit, download, media copy and asset registry write
        # complete before a simulated process exit at the project replacement.
        source = self.root / "ENGINE_TEST_blue.png"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=blue:s=32x24",
                        "-frames:v", "1", "-threads", "1", str(source)], check=True, timeout=15,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        asset = self.first.admit(self.first_id, source, "New remote picture.png")
        project = self.first.get(self.first_id)
        project["clips"][0]["asset_id"] = asset["id"]
        project["name"] = "Recovered complete media revision"
        self.first.save(self.first_id, project)
        previous = self.second.get(self.second_id)
        target = self.second.project_dir(self.second_id) / "project.json"
        import server
        original_write = server.atomic_json
        def interrupted_write(path, value):
            if Path(path) == target:
                raise OSError("Injected exit after asset publication")
            return original_write(path, value)
        with mock.patch.object(server, "atomic_json", side_effect=interrupted_write):
            with self.assertRaisesRegex(OSError, "Injected exit"):
                self.sync(self.second, self.second_id)
        self.assertEqual(previous["revision"], json.loads(target.read_text())["revision"])
        root = self.second.root
        self.second.shutdown()
        reopened = Store(root)
        self.stores.append(reopened)
        self.second = reopened
        recovered = reopened.get(self.second_id)
        self.assertEqual(project["name"], recovered["name"])
        self.assertEqual(previous["revision"] + 1, recovered["revision"])
        self.assertEqual(asset["id"], recovered["clips"][0]["asset_id"])
        copied = reopened.project_dir(self.second_id) / asset["path"]
        self.assertEqual(asset["sha256"], digest_file(copied))
        self.assertEqual([], list(reopened.collaboration.transactions.glob("*.json")))
        self.assertFalse(reopened.collaboration.status(self.second_id)["host_running"])
        # A second independent restart must not apply the same revision again.
        reopened.shutdown()
        second_reopen = Store(root)
        self.stores.append(second_reopen)
        self.second = second_reopen
        self.assertEqual(recovered, second_reopen.get(self.second_id))

    def test_corrupted_durable_transaction_does_not_replace_existing_project_or_binding(self):
        manager, path, journal = self._stage_committed_remote_edit()
        directory = self.second.project_dir(self.second_id)
        protected = [directory / "project.json", directory / "assets.json", manager._path(self.second_id)]
        before = {item: item.read_bytes() for item in protected}
        journal["project"]["name"] = "Valid JSON with a damaged checkpoint"
        _write(path, journal)
        with self.assertRaisesRegex(ValueError, "content identity"):
            manager._finish_transaction(path)
        for item in protected:
            self.assertEqual(before[item], item.read_bytes())
        self.assertTrue(path.exists())
        self.assertTrue((manager.staging / journal["stage"]).is_dir())

    def test_replay_revalidates_project_and_pairing_before_modifying_files(self):
        manager, path, original = self._stage_committed_remote_edit()
        directory = self.second.project_dir(self.second_id)
        protected = [directory / "project.json", directory / "assets.json", manager._path(self.second_id)]
        before = {item: item.read_bytes() for item in protected}
        invalid_project = copy.deepcopy(original)
        invalid_project["project"]["clips"][0]["asset_id"] = "missing-source"
        invalid_pairing = copy.deepcopy(original)
        invalid_pairing["binding"]["connection"]["client_id"] = uuid.uuid4().hex
        for journal in (invalid_project, invalid_pairing):
            with self.subTest(project=journal is invalid_project):
                journal["sha256"] = _journal_digest(journal)
                _write(path, journal)
                with self.assertRaises(ValueError):
                    manager._finish_transaction(path)
                for item in protected:
                    self.assertEqual(before[item], item.read_bytes())
        _write(path, original)
        manager._finish_transaction(path)
        self.assertEqual("Remote edit awaiting local commit", self.second.get(self.second_id)["name"])

    def test_copy_checks_actual_bytes_after_preflight_and_cleans_failed_temporary(self):
        source = self.root / "ENGINE_TEST_staged-media.bin"
        destination = self.root / "ENGINE_TEST_existing-media.bin"
        source.write_bytes(b"authenticated staged source")
        expected = _hash(source)
        destination.write_bytes(b"preserved existing media")
        # Model an external write after a successful preflight hash. The copy
        # must independently compare the bytes it actually read with the manifest.
        source.write_bytes(b"altered staged media bytes")
        with self.assertRaisesRegex(ValueError, "changed while it was copied"):
            _copy_verified(source, destination, expected)
        self.assertEqual(b"preserved existing media", destination.read_bytes())
        self.assertEqual([], list(self.root.glob(".collaboration-commit-*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)

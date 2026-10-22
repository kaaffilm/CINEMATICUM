"""Actual paired TLS clients, SQLite recovery and decoded peer media acceptance.

All pictures/sound are synthetic ENGINE TEST SIGNALS. No mocked transport,
SQLite engine, project validator, media decoder or renderer is used.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import collaboration as collab
from engine import probe_media, render_project, validate_project


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ffmpeg(arguments):
    return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1"] + arguments,
                          capture_output=True, check=True, timeout=40).stdout


class ActualCollaborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe") or not shutil.which("openssl"):
            raise RuntimeError("Actual collaboration acceptance requires FFmpeg, ffprobe and OpenSSL; skipping is not acceptance.")
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix="cinematicum-COLLAB-ENGINE-TEST-")
        cls.fixture = Path(cls.fixture_temp.name).resolve()
        seed = collab.Coordinator(cls.fixture / "certificate-seed")
        collab._certificate(seed)
        seed.close()
        cls.source = cls.fixture / "source"
        (cls.source / "media").mkdir(parents=True)
        cls.media = cls.source / "media/ENGINE_TEST_collaboration.mkv"
        ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=64x48:r=12:d=0.5", "-f", "lavfi", "-i", "sine=f=660:r=48000:d=0.5", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(cls.media)])
        cls.asset = {"id": "source_video", "path": "media/ENGINE_TEST_collaboration.mkv", "sha256": sha(cls.media), **probe_media(cls.media)}
        cls.deps = {cls.asset["path"]: {"sha256": cls.asset["sha256"], "size": cls.asset["size"]}}
        cls.base = validate_project({"version": 1, "id": "shared_project", "name": "ENGINE TEST collaboration", "fps": 12, "width": 64, "height": 48,
            "assets": [], "clips": [], "titles": [{"id": ident, "text": ident, "start": index * 2, "duration": 2, "size": 8} for index, ident in enumerate(("first", "second", "third"))],
            "tracks": [{"id": 0}, {"id": -1}], "settings": {}}, cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-COLLAB-TEST-")
        self.root = Path(self.temporary.name).resolve()
        self.coordinator = collab.Coordinator(self.root / "authority")
        for name in ("key.pem", "certificate.pem"):
            shutil.copyfile(self.fixture / "certificate-seed/tls" / name, self.coordinator.tls / name)
        self.service = collab.start_tls_server(self.coordinator)
        self.binding = self.coordinator.create_session(self.base, {}, "Alice")
        self.alice = collab.Client(self.binding)
        self.bob_binding = collab.Client.join(self.alice.invite(), "Bob")
        self.bob = collab.Client(self.bob_binding)

    def tearDown(self):
        self.service.close()
        self.coordinator.close()
        self.temporary.cleanup()

    def edit(self, client, change, operation="edit", snapshot=None):
        snapshot = snapshot or client.snapshot()
        project = copy.deepcopy(snapshot["project"])
        dependencies = copy.deepcopy(snapshot["dependencies"])
        change(project, dependencies)
        return client.submit(project, dependencies, snapshot["revision"], operation)

    def concurrent(self, functions):
        barrier = threading.Barrier(len(functions))
        def run(function):
            barrier.wait(timeout=10)
            return function()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            futures = [pool.submit(run, function) for function in functions]
            return [future.result(timeout=30) for future in futures]

    def media_session(self, clips=True):
        project = copy.deepcopy(self.base)
        project["titles"] = []
        project["assets"] = [copy.deepcopy(self.asset)]
        project["clips"] = [{"id": "picture", "asset_id": self.asset["id"], "start": 0, "in": 0, "duration": 6}] if clips else []
        project = validate_project(project, self.source)
        binding = self.coordinator.create_session(project, self.deps, "Media owner")
        owner = collab.Client(binding)
        return owner, project

    def test_actual_tls_pairing_members_and_private_credential_storage(self):
        self.assertTrue(self.service.url.startswith("https://127.0.0.1:"))
        connection = self.alice._connect()
        try:
            self.assertIn(connection.sock.version(), ("TLSv1.2", "TLSv1.3"))
            self.assertEqual(hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest(), self.binding["certificate_sha256"])
        finally:
            connection.close()
        self.assertEqual([item["name"] for item in self.bob.members()["members"]], ["Alice", "Bob"])
        with self.coordinator._db() as db:
            rows = list(db.execute("SELECT token_hash FROM clients"))
        self.assertNotIn(self.binding["token"], json.dumps([dict(row) for row in rows]))
        self.assertEqual(self.alice.snapshot()["project"], self.bob.snapshot()["project"])

    def test_pinned_certificate_and_invalid_credentials_are_rejected(self):
        changed = copy.deepcopy(self.binding)
        changed["certificate_sha256"] = "0" * 64
        with self.assertRaises(collab.CollaborationError) as error:
            collab.Client(changed)
        self.assertEqual(error.exception.code, "certificate_mismatch")
        changed = copy.deepcopy(self.binding)
        changed["token"] = "wrong-credential-" * 3
        with self.assertRaises(collab.CollaborationError) as error:
            collab.Client(changed).snapshot()
        self.assertEqual(error.exception.status, 401)
        other = collab.Coordinator(self.root / "different-identity")
        try:
            _, _, pem, fingerprint = collab._certificate(other)
            changed.update(certificate_pem=pem, certificate_sha256=fingerprint)
            with self.assertRaises(ssl.SSLCertVerificationError):
                collab.Client(changed).snapshot()
        finally:
            other.close()

    def test_two_simultaneous_clients_merge_distinct_entities(self):
        base = self.alice.snapshot()
        results = self.concurrent([
            lambda: self.edit(self.alice, lambda p, d: p["titles"][0].update(text="Alice's first"), "alice-first", base),
            lambda: self.edit(self.bob, lambda p, d: p["titles"][1].update(text="Bob's second"), "bob-second", base),
        ])
        self.assertEqual(sorted(item["revision"] for item in results), [1, 2])
        current = self.bob.snapshot()
        self.assertEqual([item["text"] for item in current["project"]["titles"]][:2], ["Alice's first", "Bob's second"])

    def test_same_entity_disjoint_properties_and_integer_tracks_merge(self):
        base = self.alice.snapshot()
        self.edit(self.alice, lambda p, d: (p["titles"][0].update(text="New words"), p["tracks"][0].update(mute=True)), "alice-fields", base)
        result = self.edit(self.bob, lambda p, d: (p["titles"][0].update(x=.25), p["tracks"][0].update(gain=.75)), "bob-fields", base)
        self.assertEqual(result["project"]["titles"][0]["text"], "New words")
        self.assertEqual(result["project"]["titles"][0]["x"], .25)
        self.assertTrue(result["project"]["tracks"][0]["mute"])
        self.assertEqual(result["project"]["tracks"][0]["gain"], .75)

    def test_same_field_conflict_rejects_entire_edit_without_partial_write(self):
        base = self.alice.snapshot()
        first = self.edit(self.alice, lambda p, d: p["titles"][0].update(text="Alice"), "alice", base)
        with self.assertRaises(collab.ConflictError) as error:
            self.edit(self.bob, lambda p, d: (p["titles"][0].update(text="Bob"), p.update(name="Must not partially save")), "bob", base)
        self.assertEqual(error.exception.code, "edit_conflict")
        self.assertEqual(error.exception.details["conflicts"][0]["path"], "/project/titles/@first/text")
        self.assertEqual(error.exception.details["revision"], 1)
        self.assertEqual(self.alice.snapshot()["project"], first["project"])

    def test_delete_versus_edit_keeps_authored_work_until_resolution(self):
        base = self.alice.snapshot()
        self.edit(self.alice, lambda p, d: p["titles"][0].update(text="Still needed"), "keep", base)
        with self.assertRaises(collab.ConflictError) as error:
            self.edit(self.bob, lambda p, d: p["titles"].pop(0), "delete", base)
        self.assertEqual(error.exception.details["conflicts"][0]["reason"], "delete_versus_edit")
        self.assertEqual(self.bob.snapshot()["project"]["titles"][0]["text"], "Still needed")

    def test_concurrent_insertions_preserve_both_entities_and_deterministic_order(self):
        base = self.alice.snapshot()
        a = {**base["project"]["titles"][0], "id": "insert_a", "text": "A"}
        b = {**a, "id": "insert_b", "text": "B"}
        self.edit(self.alice, lambda p, d: p["titles"].insert(1, a), "insert-a", base)
        result = self.edit(self.bob, lambda p, d: p["titles"].insert(1, b), "insert-b", base)
        self.assertEqual([item["id"] for item in result["project"]["titles"]], ["first", "insert_a", "insert_b", "second", "third"])

    def test_competing_reorders_are_explicit_conflicts(self):
        base = self.alice.snapshot()
        self.edit(self.alice, lambda p, d: p["titles"].reverse(), "reverse", base)
        with self.assertRaises(collab.ConflictError) as error:
            self.edit(self.bob, lambda p, d: p["titles"].insert(0, p["titles"].pop(1)), "reorder", base)
        self.assertEqual(error.exception.details["conflicts"][0]["reason"], "concurrent_reorder")

    def test_concurrent_retry_commits_exactly_once_and_preserves_receipt(self):
        base = self.alice.snapshot()
        project = copy.deepcopy(base["project"])
        project["name"] = "Exactly once"
        results = self.concurrent([lambda: self.alice.submit(project, {}, 0, "same-operation"), lambda: self.alice.submit(project, {}, 0, "same-operation")])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["revision"], 1)
        self.assertEqual(len(self.bob.events(0, 0)["events"]), 1)
        with self.coordinator._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 1)

    def test_operation_id_cannot_be_reused_for_a_different_edit(self):
        self.edit(self.alice, lambda p, d: p.update(name="First"), "same")
        with self.assertRaises(collab.ConflictError) as error:
            self.edit(self.alice, lambda p, d: p.update(name="Different"), "same")
        self.assertEqual(error.exception.code, "operation_reused")
        self.assertEqual(self.bob.snapshot()["project"]["name"], "First")

    def test_selective_undo_preserves_other_participants_later_disjoint_changes(self):
        original = self.alice.snapshot()
        own = self.edit(self.alice, lambda p, d: p["titles"][0].update(text="Alice edit"), "own")
        self.edit(self.bob, lambda p, d: (p["titles"][0].update(x=.4), p["titles"][1].update(text="Bob edit")), "other")
        result = self.alice.undo(own["event_id"], "undo-own")
        self.assertEqual(result["project"]["titles"][0]["text"], original["project"]["titles"][0]["text"])
        self.assertEqual(result["project"]["titles"][0]["x"], .4)
        self.assertEqual(result["project"]["titles"][1]["text"], "Bob edit")
        self.assertEqual(self.alice.undo(own["event_id"], "undo-own"), result)
        with self.assertRaises(collab.CollaborationError) as error:
            self.bob.undo(own["event_id"], "not-mine")
        self.assertEqual(error.exception.status, 403)

    def test_selective_undo_refuses_to_overwrite_later_same_field_edits(self):
        own = self.edit(self.alice, lambda p, d: p.update(name="Alice name"), "own")
        self.edit(self.bob, lambda p, d: p.update(name="Later Bob name"), "later")
        with self.assertRaises(collab.ConflictError):
            self.alice.undo(own["event_id"], "undo-own")
        self.assertEqual(self.alice.snapshot()["project"]["name"], "Later Bob name")

    def test_sqlite_restart_recovers_edits_credentials_invites_and_retry_receipts(self):
        base = self.alice.snapshot()
        project = copy.deepcopy(base["project"]); project["name"] = "Durable name"
        first = self.alice.submit(project, {}, 0, "durable-op")
        invitation = self.alice.invite()
        certificate = self.service.certificate_sha256
        self.service.close(); self.coordinator.close()
        self.coordinator = collab.Coordinator(self.root / "authority")
        self.service = collab.start_tls_server(self.coordinator)
        self.assertEqual(self.service.certificate_sha256, certificate)
        self.binding["url"] = self.service.url
        self.alice = collab.Client(self.binding)
        invitation["url"] = self.service.url
        peer = collab.Client(collab.Client.join(invitation, "After restart"))
        self.assertEqual(peer.snapshot()["project"]["name"], "Durable name")
        self.assertEqual(self.alice.submit(project, {}, 0, "durable-op"), first)
        self.assertEqual(len(peer.events(0, 0)["events"]), 1)

    def test_long_poll_delivers_a_real_concurrent_event(self):
        entered = threading.Event()
        def wait():
            entered.set()
            return self.bob.events(0, 2)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(wait)
            self.assertTrue(entered.wait(3))
            time.sleep(.1)
            own = self.edit(self.alice, lambda p, d: p.update(name="Live update"), "live")
            received = future.result(timeout=5)
        self.assertEqual(received["events"][0]["id"], own["event_id"])
        self.assertEqual(received["revision"], 1)

    def test_single_use_invites_roles_and_revocation(self):
        invitation = self.alice.invite()
        peer = collab.Client(collab.Client.join(invitation, "Charlie"))
        with self.assertRaises(collab.CollaborationError) as error:
            collab.Client.join(invitation, "Uninvited reuse")
        self.assertEqual(error.exception.code, "invitation_expired")
        with self.assertRaises(collab.CollaborationError) as error:
            self.bob.invite()
        self.assertEqual(error.exception.status, 403)
        self.alice.revoke(peer.binding["client_id"])
        with self.assertRaises(collab.CollaborationError) as error:
            peer.snapshot()
        self.assertEqual(error.exception.status, 401)
        with self.assertRaises(collab.CollaborationError):
            peer.events(0, 0)

    def test_expired_invitation_is_rejected_by_durable_authority(self):
        invitation = self.alice.invite()
        with self.coordinator._db() as db:
            db.execute("UPDATE invites SET expires=? WHERE token_hash=?", (time.time() - 1, hashlib.sha256(invitation["invite_token"].encode()).hexdigest()))
        with self.assertRaises(collab.CollaborationError) as error:
            collab.Client.join(invitation, "Too late")
        self.assertEqual(error.exception.code, "invitation_expired")

    def test_initial_media_is_missing_until_actual_upload_and_blocks_pairing(self):
        owner, project = self.media_session()
        missing = owner.snapshot()["missing_blobs"]
        self.assertEqual([item["sha256"] for item in missing], [self.asset["sha256"]])
        with self.assertRaises(collab.ConflictError) as error:
            owner.invite()
        self.assertEqual(error.exception.code, "missing_media")
        with self.assertRaises(collab.ConflictError) as error:
            owner.submit(project, self.deps, 0, "before-upload")
        self.assertEqual(error.exception.code, "missing_media")
        self.assertEqual(owner.upload_blob(self.media, self.asset["sha256"]), next(iter(self.deps.values())))
        self.assertEqual(owner.snapshot()["missing_blobs"], [])
        peer = collab.Client(collab.Client.join(owner.invite(), "Media peer"))
        self.assertEqual(peer.snapshot()["dependencies"], self.deps)

    def test_actual_peer_media_download_and_merged_edit_render_all_frames_and_sound(self):
        owner, project = self.media_session()
        owner.upload_blob(self.media, self.asset["sha256"])
        peer = collab.Client(collab.Client.join(owner.invite(), "Rendering peer"))
        base = owner.snapshot()
        self.edit(owner, lambda p, d: p["clips"][0].update(volume=.5), "owner-mix", base)
        merged = self.edit(peer, lambda p, d: p["clips"][0].update(duration=4), "peer-trim", base)
        destination = self.root / "peer-project"
        (destination / "media").mkdir(parents=True)
        received = peer.download_blob(self.asset["sha256"], destination / self.asset["path"], expected_size=self.asset["size"])
        self.assertEqual(received["sha256"], sha(destination / self.asset["path"]))
        decoded = probe_media(destination / self.asset["path"])
        self.assertTrue(decoded["has_audio"])
        self.assertEqual((decoded["width"], decoded["height"]), (64, 48))
        outputs = [self.root / "owner.mp4", self.root / "peer.mp4"]
        for root, output in zip((self.source, destination), outputs):
            render_project(merged["project"], root, output, profile="h264")
        pictures = [ffmpeg(["-i", str(path), "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]) for path in outputs]
        sounds = [ffmpeg(["-i", str(path), "-map", "0:a:0", "-f", "s16le", "-ac", "2", "-ar", "48000", "pipe:1"]) for path in outputs]
        self.assertEqual(len(pictures[0]), 4 * 64 * 48 * 3)
        self.assertEqual(pictures[0], pictures[1])
        self.assertGreater(len(set(pictures[0])), 200)
        self.assertEqual(sounds[0], sounds[1])
        self.assertGreater(len(sounds[0]), 40000)
        self.assertGreater(len(set(sounds[0])), 100)

    def test_blob_membership_does_not_leak_known_hashes_across_projects(self):
        owner, _ = self.media_session()
        owner.upload_blob(self.media, self.asset["sha256"])
        with self.assertRaises(collab.CollaborationError) as error:
            self.bob.download_blob(self.asset["sha256"], self.root / "stolen.mkv")
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(error.exception.code, "missing_media")
        self.assertFalse((self.root / "stolen.mkv").exists())

    def test_wrong_hash_and_interrupted_stream_leave_no_published_blob_or_temporary(self):
        with self.assertRaises(collab.CollaborationError) as error:
            self.alice.upload_blob(self.media, "0" * 64)
        self.assertEqual(error.exception.code, "hash_mismatch")
        with self.assertRaises(collab.CollaborationError):
            self.coordinator.upload_blob(self.binding["session_id"], self.binding["token"], self.asset["sha256"], io.BytesIO(b"short"), 100)
        self.assertEqual(list(self.coordinator.uploads.iterdir()), [])
        self.assertEqual(list(self.coordinator.blobs.iterdir()), [])

    def test_corrupt_download_is_rejected_without_replacing_destination(self):
        owner, _ = self.media_session()
        owner.upload_blob(self.media, self.asset["sha256"])
        blob = self.coordinator.blobs / self.asset["sha256"]
        payload = bytearray(blob.read_bytes()); payload[-20] ^= 255; blob.write_bytes(payload)
        target = self.root / "received.mkv"
        with self.assertRaises(collab.CollaborationError) as error:
            owner.download_blob(self.asset["sha256"], target)
        self.assertEqual(error.exception.code, "hash_mismatch")
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".collaboration-download-*")))
        with self.assertRaises(collab.CollaborationError) as error:
            owner.invite()
        self.assertEqual(error.exception.code, "hash_mismatch")

    def test_semantic_merge_rejects_a_clip_whose_asset_was_concurrently_removed(self):
        owner, project = self.media_session(clips=False)
        owner.upload_blob(self.media, self.asset["sha256"])
        peer = collab.Client(collab.Client.join(owner.invite(), "Editor"))
        base = owner.snapshot()
        self.edit(owner, lambda p, d: (p["assets"].clear(), d.clear()), "remove-media", base)
        with self.assertRaises(collab.ConflictError) as error:
            self.edit(peer, lambda p, d: p["clips"].append({"id": "new_clip", "asset_id": self.asset["id"], "start": 0, "duration": 3}), "use-media", base)
        self.assertEqual(error.exception.code, "invalid_merged_project")
        snapshot = owner.snapshot()
        self.assertEqual(snapshot["revision"], 1)
        self.assertEqual(snapshot["project"]["clips"], [])
        self.assertEqual(snapshot["project"]["assets"], [])

    def test_unsafe_dependency_paths_duplicate_ids_and_identity_changes_are_rejected(self):
        for path in ("../outside.mkv", "/tmp/outside.mkv", "media/../outside.mkv", "media/code.py", "project.json", "assets.json", "media/back\\slash.mkv"):
            with self.subTest(path=path), self.assertRaises(collab.CollaborationError):
                collab.validate_dependencies({path: {"sha256": "a" * 64, "size": 1}})
        with self.assertRaises(collab.CollaborationError):
            self.edit(self.alice, lambda p, d: p["titles"].append(copy.deepcopy(p["titles"][0])), "duplicate")
        with self.assertRaises(collab.CollaborationError):
            self.edit(self.alice, lambda p, d: p.update(id="different-project"), "identity-change")
        self.assertEqual(self.alice.snapshot()["revision"], 0)

    def test_upload_and_download_refuse_symlinks_and_existing_destinations(self):
        link = self.root / "link.mkv"; link.symlink_to(self.media)
        with self.assertRaises(OSError):
            self.alice.upload_blob(link, self.asset["sha256"])
        self.alice.upload_blob(self.media, self.asset["sha256"])
        target = self.root / "existing.mkv"; target.write_bytes(b"keep this owned file")
        with self.assertRaises(collab.CollaborationError):
            self.alice.download_blob(self.asset["sha256"], target)
        self.assertEqual(target.read_bytes(), b"keep this owned file")
        directory = self.root / "real"; directory.mkdir()
        alias = self.root / "alias"; alias.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(collab.CollaborationError):
            self.alice.download_blob(self.asset["sha256"], alias / "escape.mkv")

    def test_http_parser_rejects_duplicate_and_nonfinite_metadata(self):
        for raw in (b'{"project":{},"project":{}}', b'{"base_revision":NaN}', b'{"base_revision":1e999}'):
            with self.subTest(raw=raw):
                connection = self.alice._connect()
                try:
                    connection.request("POST", "/v1/sessions/" + self.binding["session_id"] + "/edits", body=raw,
                                       headers={**self.alice._headers(), "Content-Type": "application/json"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    self.assertIn("error", json.loads(response.read()))
                finally:
                    connection.close()
        self.assertEqual(self.alice.snapshot()["revision"], 0)

    def test_ordinary_project_revision_fields_do_not_create_false_shared_conflicts(self):
        base = self.alice.snapshot()
        a = copy.deepcopy(base["project"]); a.update(revision=100, updated_at="local-A", _recovery={"editor_id": "A"})
        a["titles"][0]["text"] = "Shared content A"
        first = self.alice.submit(a, {}, 0, "a-local-revision")
        b = copy.deepcopy(base["project"]); b.update(revision=8, updated_at="local-B")
        b["titles"][1]["text"] = "Shared content B"
        second = self.bob.submit(b, {}, 0, "b-local-revision")
        self.assertEqual((first["revision"], second["revision"]), (1, 2))
        for key in ("revision", "updated_at", "_recovery"):
            self.assertNotIn(key, second["project"])

    def test_shared_scene_dimensions_cannot_be_silently_normalized_during_merge(self):
        from scene import default_scene
        with self.assertRaises(collab.ConflictError) as error:
            self.edit(self.alice, lambda p, d: p["settings"].update(scene=default_scene(128, 96)), "wrong-scene")
        self.assertEqual(error.exception.code, "invalid_merged_project")
        self.assertIn("resolution", error.exception.details["validation_error"])
        self.assertEqual(self.alice.snapshot()["revision"], 0)

    def test_selective_undo_cannot_remove_media_needed_by_another_participants_edit(self):
        owner, _ = self.media_session(clips=False)
        owner.upload_blob(self.media, self.asset["sha256"])
        peer = collab.Client(collab.Client.join(owner.invite(), "Editor"))
        # Create a second admitted identity using the same real immutable bytes.
        added = {**self.asset, "id": "other_asset", "path": "media/ENGINE_TEST_other.mkv"}
        own = self.edit(owner, lambda p, d: (p["assets"].append(added), d.update({added["path"]: {"sha256": added["sha256"], "size": added["size"]}})), "add-asset")
        self.edit(peer, lambda p, d: p["clips"].append({"id": "later_clip", "asset_id": added["id"], "start": 0, "duration": 3}), "use-added")
        with self.assertRaises(collab.ConflictError) as error:
            owner.undo(own["event_id"], "remove-added")
        self.assertEqual(error.exception.code, "invalid_merged_project")
        self.assertEqual(len(peer.snapshot()["project"]["clips"]), 1)
        self.assertEqual(len(peer.snapshot()["project"]["assets"]), 2)

    def test_coordinator_refuses_unrelated_directory_without_mutating_it(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir(mode=0o755)
        existing = unrelated / "owner.txt"; existing.write_bytes(b"preserve")
        before = unrelated.stat().st_mode
        with self.assertRaises(collab.CollaborationError):
            collab.Coordinator(unrelated)
        self.assertEqual(unrelated.stat().st_mode, before)
        self.assertEqual(existing.read_bytes(), b"preserve")
        self.assertEqual([path.name for path in unrelated.iterdir()], ["owner.txt"])

    def test_unknown_revision_is_not_a_last_write_wins_fallback(self):
        snapshot = self.alice.snapshot()
        snapshot["project"]["name"] = "Unknown base"
        with self.assertRaises(collab.ConflictError) as error:
            self.alice.submit(snapshot["project"], {}, 999, "unknown-base")
        self.assertEqual(error.exception.code, "unknown_revision")
        with self.assertRaises(collab.ConflictError) as error:
            self.bob.events(999, 0)
        self.assertEqual(error.exception.code, "unknown_revision")
        self.assertEqual(self.alice.snapshot()["revision"], 0)


if __name__ == "__main__":
    unittest.main()

"""Private local bindings and recoverable materialization of paired projects.

The TLS coordinator owns shared revisions. Studio keeps its independent local
revision, immutable media and recovery history. Credentials and transaction
journals are deliberately outside portable project directories.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
import uuid

from collaboration import Client, Coordinator, CollaborationError, ConflictError, start_tls_server, validate_dependencies
from engine import validate_project
from project_archive import _collect, _open_owned, _relative, _allowed
from scene import validate_scene

_ID = re.compile(r"[a-f0-9]{32}\Z")
_LOCAL = {"revision", "updated_at", "_recovery", "archive_restore"}


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()


def _journal_digest(value):
    return hashlib.sha256(_json({key: item for key, item in value.items() if key != "sha256"})).hexdigest()


def _write(path, value):
    from server import atomic_json
    atomic_json(path, value)
    os.chmod(path, 0o600)


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read(path):
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32 * 1024 * 1024:
            raise ValueError("The private collaboration record is not a bounded regular file.")
        return json.load(stream)


def _directory(path):
    path = Path(path)
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise ValueError("A collaboration directory contains an unrelated file or symbolic link.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _hash(path):
    result = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Shared dependencies must be regular owned files.")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
        after = os.fstat(stream.fileno())
        if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("A shared dependency changed while its identity was checked.")
    return {"sha256": result.hexdigest(), "size": info.st_size}


def _owned(root, relative, *, parent=False):
    _relative(relative)
    if not _allowed(relative):
        raise ValueError("A shared dependency is outside the portable project format.")
    current = Path(root)
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("A shared project dependency contains a symbolic link.")
    if parent:
        current.parent.mkdir(parents=True, exist_ok=True)
    return current


def _normalize(project, directory):
    project = validate_project(copy.deepcopy(project), directory)
    if project.get("settings", {}).get("scene") is not None:
        scene = validate_scene(project["settings"]["scene"])
        if (scene["width"], scene["height"]) != (project["width"], project["height"]):
            raise ValueError("A shared scene must have the explicit project resolution.")
        project["settings"]["scene"] = scene
    return project


def _validate_binding(record, project_id):
    if (not isinstance(record, dict) or record.get("version") != 1 or record.get("local_project_id") != project_id
            or not isinstance(record.get("shared_project_id"), str) or not _ID.fullmatch(record["shared_project_id"])
            or type(record.get("remote_revision")) is not int or record["remote_revision"] < 0):
        raise ValueError("The private collaboration binding is inconsistent.")
    client = Client(record.get("connection"))
    client._headers()  # Validate the private credential locally without making a request.
    if not isinstance(record["connection"].get("client_id"), str) or not _ID.fullmatch(record["connection"]["client_id"]):
        raise ValueError("The private collaboration participant identity is inconsistent.")
    events = record.get("own_events", [])
    if (not isinstance(events, list) or len(events) > 100
            or any(not isinstance(event, str) or not _ID.fullmatch(event) for event in events)
            or len(set(events)) != len(events)):
        raise ValueError("The private collaboration edit history is inconsistent.")
    return record


def _copy_verified(source, destination, identity):
    """Publish only the bytes actually hashed during this copy, including on replay."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".collaboration-commit-", delete=False) as output:
            temporary = Path(output.name)
            digest, size = hashlib.sha256(), 0
            with os.fdopen(os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as incoming:
                before = os.fstat(incoming.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("A staged shared dependency is no longer a regular file.")
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    size += len(block)
                    if size > identity["size"]:
                        raise ValueError("A staged shared dependency changed while it was copied.")
                    digest.update(block)
                    output.write(block)
                after = os.fstat(incoming.fileno())
                if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                        or {"sha256": digest.hexdigest(), "size": size} != identity):
                    raise ValueError("A staged shared dependency changed while it was copied.")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        _sync_directory(destination.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class CollaborationStore:
    def __init__(self, store):
        self.store = store
        self.root = _directory(store.root / "collaboration")
        self.bindings = _directory(self.root / "bindings")
        self.staging = _directory(self.root / "staging")
        self.transactions = _directory(self.root / "transactions")
        self.coordinators = _directory(self.root / "coordinators")
        self.services = {}
        # These journals contain already validated, already committed remote
        # edits. Replay is local only and never opens a listener or a connection.
        for path in sorted(self.transactions.glob("*.json")):
            if _ID.fullmatch(path.stem):
                self._finish_transaction(path)

    def _path(self, project_id):
        if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
            raise ValueError("Invalid local collaboration project identity.")
        return self.bindings / (project_id + ".json")

    def bound(self, project_id):
        path = self._path(project_id)
        return path.exists() or path.is_symlink()

    def _binding(self, project_id):
        return _validate_binding(_read(self._path(project_id)), project_id)

    def status(self, project_id):
        self.store.project_dir(project_id)
        if not self.bound(project_id):
            return {"active": False}
        record = self._binding(project_id)
        return {"active": True, "owner": bool(record.get("host")), "host_running": project_id in self.services,
                "url": record["connection"]["url"], "shared_project_id": record["shared_project_id"],
                "certificate_sha256": record["connection"]["certificate_sha256"],
                "shared_revision": record["remote_revision"], "participant_id": record["connection"]["client_id"],
                "own_events": record.get("own_events", []), "pending_operation": bool(record.get("pending"))}

    def _dependencies(self, project, directory, temporary):
        normalized, files, _ = _collect(project, directory)
        dependencies, sources = {}, {}
        for relative, entry in files.items():
            if relative in {"project.json", "assets.json"}:
                continue
            if entry.get("data") is not None:
                source = _owned(temporary, relative, parent=True)
                source.write_bytes(entry["data"])
                os.chmod(source, 0o600)
            else:
                # The archive walker has checked each directory component.
                source = _owned(directory, relative)
            identity = _hash(source)
            if identity["size"] != entry["size"] or entry.get("expected") not in {None, identity["sha256"]}:
                raise ValueError("A shared dependency no longer matches its admitted identity: " + relative)
            dependencies[relative], sources[relative] = identity, source
        return normalized, validate_dependencies(dependencies), sources

    def _upload(self, record, dependencies, sources):
        client = Client(record["connection"])
        uploaded = record.setdefault("uploaded", {})
        for relative, identity in dependencies.items():
            if uploaded.get(identity["sha256"]) != identity["size"]:
                result = client.upload_blob(sources[relative], identity["sha256"])
                if {key: result.get(key) for key in ("sha256", "size")} != identity:
                    raise ValueError("The shared server acknowledged a different media identity.")
                uploaded[identity["sha256"]] = identity["size"]
                _write(self._path(record["local_project_id"]), record)

    def create(self, project_id, payload):
        if not isinstance(payload, dict) or set(payload) - {"name", "host", "port", "advertise_host"}:
            raise ValueError("Sharing requires a participant name and explicit listener address.")
        with self.store.lock:
            if self.bound(project_id):
                raise ConflictError("This project already has a collaboration binding. Resume it or leave before sharing again.")
            project, directory = self.store.get(project_id), self.store.project_dir(project_id)
            with tempfile.TemporaryDirectory(prefix="share-", dir=self.staging) as temporary:
                project, dependencies, sources = self._dependencies(project, directory, Path(temporary))
                coordinator = Coordinator(_directory(self.coordinators / project_id))
                try:
                    service = start_tls_server(coordinator, host=payload.get("host", "127.0.0.1"),
                                               port=payload.get("port", 0), advertise_host=payload.get("advertise_host"))
                except BaseException:
                    coordinator.close()
                    raise
                try:
                    connection = coordinator.create_session(project, dependencies, owner_name=payload.get("name", "Owner"))
                except BaseException:
                    service.close(); coordinator.close()
                    raise
                self.services[project_id] = service
                record = {"version": 1, "local_project_id": project_id, "shared_project_id": project_id,
                          "remote_revision": 0, "connection": connection, "uploaded": {}, "own_events": [],
                          "host": {"host": payload.get("host", "127.0.0.1"), "port": service.server.server_port,
                                   "advertise_host": payload.get("advertise_host")}}
                _write(self._path(project_id), record)
                self._upload(record, dependencies, sources)
                snapshot = Client(connection).snapshot()
                if snapshot["missing_blobs"]:
                    raise ConflictError("Initial media transfer is incomplete. Resume the shared project.", code="missing_media")
            return {"project": self.store.get(project_id), "status": self.status(project_id)}

    def resume(self, project_id, payload):
        if payload != {}:
            raise ValueError("Resuming uses the exact saved collaboration address.")
        with self.store.lock:
            record = self._binding(project_id)
            if record.get("host") and project_id not in self.services:
                coordinator = Coordinator(_directory(self.coordinators / project_id))
                try:
                    service = start_tls_server(coordinator, **record["host"])
                    if service.url != record["connection"]["url"] or service.certificate_sha256 != record["connection"]["certificate_sha256"]:
                        service.close()
                        raise ValueError("The resumed coordinator does not match its paired TLS address and identity.")
                    self.services[project_id] = service
                except BaseException:
                    coordinator.close()
                    raise
            client = Client(record["connection"])
            missing = client.snapshot()["missing_blobs"]
            if missing:
                with tempfile.TemporaryDirectory(prefix="resume-", dir=self.staging) as temporary:
                    _, dependencies, sources = self._dependencies(self.store.get(project_id), self.store.project_dir(project_id), Path(temporary))
                    for entry in missing:
                        record["uploaded"].pop(entry["sha256"], None)
                    self._upload(record, dependencies, sources)
            return self.sync(project_id, {"revision": self.store.get(project_id)["revision"]})

    def join(self, anchor_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"invitation", "name"}:
            raise ValueError("Joining requires an invitation and a participant name.")
        with self.store.lock:
            self.store.project_dir(anchor_id)
            connection = Client.join(payload["invitation"], payload["name"])
            snapshot = Client(connection).snapshot()
            local_id = uuid.uuid4().hex
            record = {"version": 1, "local_project_id": local_id, "shared_project_id": snapshot["project"]["id"],
                      "remote_revision": snapshot["revision"], "connection": connection,
                      "uploaded": {}, "own_events": []}
            # Download/validate first. A failed pairing never replaces the open
            # project and never creates a half-populated project in its menu.
            stage, project = self._materialize(record, snapshot, None)
            directory = self.store.root / "projects" / local_id
            try:
                directory.mkdir(mode=0o700)
                (directory / "media").mkdir()
                (directory / "exports").mkdir()
                return self._commit(record, snapshot, stage, project, current=None)
            except BaseException:
                if not (directory / "project.json").exists() and not any(self.transactions.glob(local_id + ".json")):
                    shutil.rmtree(directory, ignore_errors=True)
                    shutil.rmtree(stage, ignore_errors=True)
                raise

    def _materialize(self, record, snapshot, current):
        if snapshot.get("missing_blobs"):
            raise ConflictError("The shared project has missing media. Its owner must finish uploading it.", code="missing_media")
        if snapshot.get("project", {}).get("id") != record["shared_project_id"]:
            raise ValueError("A received snapshot changed the paired project identity.")
        dependencies = validate_dependencies(snapshot.get("dependencies"))
        stage = Path(tempfile.mkdtemp(prefix="project-", dir=self.staging))
        client = Client(record["connection"])
        existing_root = self.store.project_dir(record["local_project_id"]) if current is not None else None
        try:
            for relative, identity in dependencies.items():
                target = _owned(stage, relative, parent=True)
                source = _owned(existing_root, relative) if existing_root is not None else None
                if source is not None and source.exists() and _hash(source) == identity:
                    os.link(source, target, follow_symlinks=False)
                else:
                    if source is not None and source.exists() and relative != "workflow.json":
                        raise ValueError("A remote edit would replace an immutable local dependency: " + relative)
                    client.download_blob(identity["sha256"], target, expected_size=identity["size"])
            project = copy.deepcopy(snapshot["project"])
            project["id"] = record["local_project_id"]
            project["revision"] = 0 if current is None else current["revision"]
            project = _normalize(project, stage)
            _, closure, _ = _collect(project, stage)
            if set(closure) - {"project.json", "assets.json"} != set(dependencies):
                raise ValueError("The shared dependency manifest does not match the complete project state.")
            return stage, project
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def _commit(self, record, snapshot, stage, project, current, own_event=None):
        local_id = record["local_project_id"]
        updated = copy.deepcopy(record)
        updated["remote_revision"] = snapshot["revision"]
        updated.pop("pending", None)
        if own_event and own_event not in updated.setdefault("own_events", []):
            updated["own_events"].append(own_event)
            updated["own_events"] = updated["own_events"][-100:]
        project["revision"] = 1 if current is None else current["revision"] + 1
        project["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        directory = self.store.root / "projects" / local_id
        previous_files = {}
        for relative in snapshot["dependencies"]:
            path = _owned(directory, relative)
            if path.exists():
                previous_files[relative] = _hash(path)
        journal = {"version": 1, "project_id": local_id, "stage": stage.name,
                   "previous_revision": None if current is None else current["revision"], "previous_files": previous_files,
                   "project": project, "dependencies": snapshot["dependencies"], "binding": updated}
        if record.get("pending", {}).get("recovery_ack") is not None:
            journal["recovery_ack"] = record["pending"]["recovery_ack"]
        journal["sha256"] = _journal_digest(journal)
        path = self.transactions / (local_id + ".json")
        if path.exists() or path.is_symlink():
            raise ConflictError("A prior local collaboration transaction must finish before another edit.")
        _write(path, journal)
        self._finish_transaction(path)
        return {"project": self.store.get(local_id), "status": self.status(local_id)}

    def _finish_transaction(self, path):
        from server import atomic_json, read_json
        import recovery
        journal = _read(path)
        if not isinstance(journal, dict) or journal.get("sha256") != _journal_digest(journal):
            raise ValueError("A local collaboration transaction failed its saved content identity check.")
        project_id = journal.get("project_id")
        if (journal.get("version") != 1 or not isinstance(project_id, str) or not _ID.fullmatch(project_id)
                or path.name != project_id + ".json" or not re.fullmatch(r"project-[A-Za-z0-9_-]+", journal.get("stage", ""))):
            raise ValueError("A local collaboration transaction has an invalid identity.")
        stage = self.staging / journal["stage"]
        if stage.is_symlink() or not stage.is_dir():
            raise ValueError("The collaboration transaction lost its verified staging directory.")
        directory = self.store.project_dir(project_id)
        project = journal["project"]
        previous_revision = journal.get("previous_revision")
        if (previous_revision is not None and (type(previous_revision) is not int or previous_revision < 1)
                or not isinstance(project, dict) or project.get("id") != project_id
                or type(project.get("revision")) is not int
                or project["revision"] != (1 if previous_revision is None else previous_revision + 1)):
            raise ValueError("A local collaboration transaction has inconsistent project revisions.")
        binding = _validate_binding(journal.get("binding"), project_id)
        if "pending" in binding:
            raise ValueError("A committed collaboration transaction cannot contain an unfinished remote edit.")
        if self.bound(project_id):
            previous_binding = self._binding(project_id)
            if (previous_binding["connection"] != binding["connection"]
                    or previous_binding["shared_project_id"] != binding["shared_project_id"]
                    or binding["remote_revision"] < previous_binding["remote_revision"]):
                raise ValueError("A local collaboration transaction changed its paired coordinator or participant.")
        dependencies = validate_dependencies(journal["dependencies"])
        validate_dependencies(journal["previous_files"])
        normalized = _normalize(project, stage)
        if normalized != project:
            raise ValueError("A local collaboration transaction is no longer a validated project checkpoint.")
        _, closure, _ = _collect(normalized, stage)
        if set(closure) - {"project.json", "assets.json"} != set(dependencies):
            raise ValueError("A local collaboration transaction lost its complete dependency manifest.")
        for relative, identity in dependencies.items():
            if _hash(_owned(stage, relative)) != identity:
                raise ValueError("A staged shared file no longer matches its validated identity.")
            entry = closure[relative]
            if entry["size"] != identity["size"] or entry.get("expected") not in {None, identity["sha256"]}:
                raise ValueError("A local collaboration dependency disagrees with its saved project identity.")
            if entry.get("data") is not None and hashlib.sha256(entry["data"]).hexdigest() != identity["sha256"]:
                raise ValueError("A local collaboration descriptor disagrees with its saved dependency identity.")
        current = read_json(directory / "project.json", {})
        if current.get("revision") not in {journal["previous_revision"], project["revision"]}:
            raise ConflictError("The local project changed outside its recoverable collaboration transaction.")
        if current and (current.get("id") != project_id or current.get("revision") == project["revision"] and current != project):
            raise ConflictError("The local project content changed outside its recoverable collaboration transaction.")
        for relative, identity in dependencies.items():
            source, destination = _owned(stage, relative), _owned(directory, relative, parent=True)
            if _hash(source) != identity:
                raise ValueError("A staged shared file no longer matches its validated identity.")
            if destination.exists():
                actual = _hash(destination)
                if actual == identity:
                    continue
                if relative != "workflow.json" or actual != journal["previous_files"].get(relative):
                    raise ValueError("An existing project dependency changed during collaboration recovery.")
            _copy_verified(source, destination, identity)
        if current and current.get("revision") == journal["previous_revision"]:
            recovery.preserve_saved(directory, current, atomic_json)
        atomic_json(directory / "assets.json", project["assets"])
        atomic_json(directory / "project.json", project)
        _write(self._path(project_id), binding)
        try:
            recovery.acknowledge(directory, journal.get("recovery_ack"), journal["previous_revision"] or 0)
        except (OSError, ValueError, KeyError):
            pass
        path.unlink()
        _sync_directory(path.parent)
        shutil.rmtree(stage, ignore_errors=True)

    def _recover_pending(self, record):
        pending = record.get("pending")
        if not pending:
            return None
        client = Client(record["connection"])
        try:
            if pending["kind"] == "save":
                snapshot = client.submit(pending["project"], pending["dependencies"], pending["base_revision"], pending["operation_id"])
            else:
                snapshot = client.undo(pending["event_id"], pending["operation_id"])
        except ConflictError as error:
            if error.code in {"edit_conflict", "missing_media", "invalid_merged_project", "unknown_revision"}:
                record.pop("pending", None)
                _write(self._path(record["local_project_id"]), record)
            raise
        current = self.store.get(record["local_project_id"])
        stage, project = self._materialize(record, snapshot, current)
        return self._commit(record, snapshot, stage, project, current,
                            own_event=snapshot.get("event_id") if snapshot.get("changed") else None)

    def save(self, project_id, project):
        with self.store.lock:
            record = self._binding(project_id)
            if record.get("pending"):
                self._recover_pending(record)
                raise ConflictError("The previous shared save was recovered. Reload its committed revision before applying this draft.")
            current = self.store.get(project_id)
            if project.get("revision") != current["revision"]:
                raise ConflictError("The local shared project changed. Sync before saving this draft.")
            proposal = copy.deepcopy(project)
            proposal.pop("_recovery", None)
            proposal["id"], proposal["version"], proposal["assets"] = project_id, 1, current["assets"]
            proposal = _normalize(proposal, self.store.project_dir(project_id))
            with tempfile.TemporaryDirectory(prefix="save-", dir=self.staging) as temporary:
                proposal, dependencies, sources = self._dependencies(proposal, self.store.project_dir(project_id), Path(temporary))
                self._upload(record, dependencies, sources)
            proposal["id"] = record["shared_project_id"]
            for key in _LOCAL:
                proposal.pop(key, None)
            record["pending"] = {"kind": "save", "project": proposal, "dependencies": dependencies,
                                 "base_revision": record["remote_revision"], "operation_id": uuid.uuid4().hex}
            if project.get("_recovery") is not None:
                receipt = project["_recovery"]
                import recovery
                if not isinstance(receipt, dict):
                    raise ValueError("Invalid recovery acknowledgement.")
                recovery.identity(receipt.get("editor_id")); recovery.sequence(receipt.get("sequence"))
                record["pending"]["recovery_ack"] = copy.deepcopy(receipt)
            _write(self._path(project_id), record)
            # Unknown transport/materialization failures retain the exact
            # operation identity; retry cannot duplicate an accepted edit.
            return self._recover_pending(record)["project"]

    def sync(self, project_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"revision"}:
            raise ValueError("Sync requires the currently displayed local revision.")
        with self.store.lock:
            current, record = self.store.get(project_id), self._binding(project_id)
            if payload["revision"] != current["revision"]:
                raise ConflictError("The local project changed before synchronization.")
            if record.get("pending"):
                return self._recover_pending(record)
            client = Client(record["connection"])
            snapshot = client.snapshot()
            if snapshot["revision"] == record["remote_revision"]:
                return {"project": current, "status": self.status(project_id)}
            if snapshot["revision"] < record["remote_revision"]:
                raise ConflictError("The shared coordinator is older than this saved binding.")
            stage, project = self._materialize(record, snapshot, current)
            return self._commit(record, snapshot, stage, project, current)

    def undo(self, project_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"event_id", "revision"}:
            raise ValueError("Selective shared undo requires an owned event and current local revision.")
        with self.store.lock:
            current, record = self.store.get(project_id), self._binding(project_id)
            if current["revision"] != payload["revision"] or record.get("pending"):
                raise ConflictError("Sync the latest local shared edit before undoing it.")
            if payload["event_id"] not in record.get("own_events", []):
                raise ValueError("Undo selects this participant's committed edit.")
            record["pending"] = {"kind": "undo", "event_id": payload["event_id"], "operation_id": uuid.uuid4().hex}
            _write(self._path(project_id), record)
            return self._recover_pending(record)

    def invite(self, project_id, payload):
        if payload != {}:
            raise ValueError("Pairing creates one expiring invitation.")
        with self.store.lock:
            record = self._binding(project_id)
            if record.get("pending"):
                raise ConflictError("Finish the pending shared save before pairing a participant.")
            return {"invitation": Client(record["connection"]).invite(), "status": self.status(project_id)}

    def revoke(self, project_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"client_id"}:
            raise ValueError("Revocation requires one selected participant.")
        with self.store.lock:
            record = self._binding(project_id)
            return Client(record["connection"]).revoke(payload["client_id"])

    def leave(self, project_id, payload):
        if payload != {}:
            raise ValueError("Leaving retains the local project and its media.")
        with self.store.lock:
            record = self._binding(project_id)
            if record.get("pending"):
                raise ConflictError("Recover the pending shared operation before leaving.")
            service = self.services.pop(project_id, None)
            if service:
                service.close(); service.coordinator.close()
            archived = _directory(self.root / "disconnected") / (project_id + "-" + uuid.uuid4().hex + ".json")
            os.rename(self._path(project_id), archived)
            return {"project": self.store.get(project_id), "status": {"active": False}}

    def close(self):
        for service in list(self.services.values()):
            service.close(); service.coordinator.close()
        self.services.clear()

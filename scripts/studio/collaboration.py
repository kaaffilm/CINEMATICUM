"""Opt-in, paired TLS collaboration with durable, three-way project edits.

This service never serves the Studio filesystem. Its only binary transport is
an authenticated, per-session SHA-256 blob store. Local Store revisions remain
independent. Pairing credentials belong in private local bindings, not projects.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import hmac
import http.client
import http.server
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

VERSION = 1
MAX_JSON = 8 * 1024 * 1024
MAX_BLOB = 64 * 1024 ** 3
MAX_FILES = 10000
CHUNK = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
_MISSING = object()
_LOCAL_KEYS = {"revision", "updated_at", "_recovery", "archive_restore"}


class CollaborationError(ValueError):
    def __init__(self, message, code="invalid_request", status=400, **details):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details

    def as_dict(self):
        return {"error": str(self), "code": self.code, **self.details}


class ConflictError(CollaborationError):
    def __init__(self, message, code="edit_conflict", **details):
        super().__init__(message, code=code, status=409, **details)


def _json(value):
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise CollaborationError("Collaboration data must be finite JSON.") from exc
    if len(data) > MAX_JSON:
        raise CollaborationError("Collaboration metadata exceeds 8 MiB.")
    return data


def _load(data):
    if len(data) > MAX_JSON:
        raise CollaborationError("Collaboration metadata exceeds 8 MiB.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CollaborationError("Duplicate JSON keys are not allowed.")
            result[key] = value
        return result
    def constant(_):
        raise CollaborationError("Non-finite JSON numbers are not allowed.")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CollaborationError("Invalid collaboration JSON.") from exc


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _identifier(value, label="Identity"):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CollaborationError(label + " is invalid.")
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100 or any(ord(c) < 32 for c in value):
        raise CollaborationError("A participant name must contain 1–100 printable characters.")
    return value.strip()


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise CollaborationError("A blob needs a lowercase SHA-256 identity.")
    return value


def _tree(value, depth=0, budget=None):
    budget = [0] if budget is None else budget
    budget[0] += 1
    if depth > 64 or budget[0] > 250000:
        raise CollaborationError("Project metadata is too deeply nested or large.")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 512:
                raise CollaborationError("Project object keys must be short strings.")
            _tree(child, depth + 1, budget)
    elif isinstance(value, list):
        if value and all(isinstance(item, dict) and "id" in item for item in value):
            identities = [_entity_identity(item["id"]) for item in value]
            if len(identities) != len(set(identities)):
                raise CollaborationError("Entity lists cannot contain duplicate identities.")
        for child in value:
            _tree(child, depth + 1, budget)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise CollaborationError("Project metadata must be JSON values.")
    elif isinstance(value, float) and not math.isfinite(value):
        raise CollaborationError("Project numbers must be finite.")


def validate_dependencies(value):
    """The portable archive allowlist is also the collaboration path boundary."""
    if not isinstance(value, dict) or len(value) > MAX_FILES:
        raise CollaborationError("Dependencies must be a manifest of at most 10,000 files.")
    if __package__:
        from .project_archive import _allowed, _relative
    else:
        from project_archive import _allowed, _relative
    result, folded, total = {}, set(), 0
    for path, entry in value.items():
        try:
            relative = _relative(path)
        except ValueError as exc:
            raise CollaborationError("A dependency path is unsafe.") from exc
        if relative in ("project.json", "assets.json") or not _allowed(relative):
            raise CollaborationError("A dependency is outside the transferable project format: " + relative)
        if relative.casefold() in folded:
            raise CollaborationError("Dependency paths collide on case-insensitive filesystems.")
        folded.add(relative.casefold())
        if not isinstance(entry, dict) or set(entry) != {"sha256", "size"}:
            raise CollaborationError("Each dependency needs exactly its SHA-256 and byte size.")
        if type(entry["size"]) is not int or not 0 < entry["size"] <= MAX_BLOB:
            raise CollaborationError("Dependency byte sizes must be positive and no larger than 64 GiB.")
        total += entry["size"]
        result[relative] = {"sha256": _sha(entry["sha256"]), "size": entry["size"]}
    if total > MAX_BLOB:
        raise CollaborationError("Shared dependencies exceed 64 GiB.")
    return result


def validate_document(project, dependencies, validator=None):
    if not isinstance(project, dict) or project.get("version") != 1:
        raise CollaborationError("A version 1 CINEMATICUM project is required.")
    project = copy.deepcopy(project)
    for key in _LOCAL_KEYS:
        project.pop(key, None)
    _identifier(project.get("id"), "Shared project identity")
    for key in ("assets", "clips", "titles"):
        if not isinstance(project.get(key), list):
            raise CollaborationError("Shared projects need an " + key + " list.")
        for entity in project[key]:
            if not isinstance(entity, dict):
                raise CollaborationError("Shared entities must be objects.")
            _identifier(entity.get("id"), "Entity identity")
    _tree(project)
    dependencies = validate_dependencies(dependencies)
    assets = {item["id"]: item for item in project["assets"]}
    for asset in assets.values():
        path = asset.get("path")
        if not isinstance(path, str) or not path.startswith("media/"):
            raise CollaborationError("Shared media must use an admitted relative media path.")
        dependency = dependencies.get(path)
        if dependency is None or dependency["sha256"] != asset.get("sha256") or dependency["size"] != asset.get("size"):
            raise ConflictError("Shared media has a missing or inconsistent dependency.", code="missing_media", paths=[path])
    if __package__:
        from .project_archive import _portable_json
    else:
        from project_archive import _portable_json
    try:
        _portable_json(project)
    except ValueError as exc:
        raise CollaborationError(str(exc)) from exc
    if validator is not None:
        normalized = validator(copy.deepcopy(project))
        if isinstance(normalized, dict):
            if normalized.get("id") != project["id"] or normalized.get("version") != 1:
                raise CollaborationError("The validator changed the shared document identity.")
            return validate_document(normalized, dependencies)
    result = {"project": project, "dependencies": dependencies}
    if len(_json(result)) > MAX_JSON - 8192:
        raise CollaborationError("Project metadata must leave space for the collaboration revision envelope.")
    return result


def _equal(a, b):
    if a is _MISSING or b is _MISSING:
        return a is b
    # JSON booleans and numbers are different authored values.
    return type(a) is type(b) and (a == b if not isinstance(a, (dict, list)) else _json(a) == _json(b))


def _copy(value):
    return _MISSING if value is _MISSING else copy.deepcopy(value)


def _path(path):
    return "/" + "/".join(("@" + str(part["id"]) if isinstance(part, dict) else str(part)).replace("~", "~0").replace("/", "~1") for part in path)


def _conflict(conflicts, path, base, current, proposed, reason="same_property"):
    if len(conflicts) >= 100:
        return
    item = {"path": _path(path), "segments": path, "reason": reason}
    for key, value in (("base", base), ("current", current), ("proposed", proposed)):
        item[key + "_exists"] = value is not _MISSING
        if value is not _MISSING:
            raw = _json(value)
            item[key] = value if len(raw) <= 2048 else {"excerpt": raw[:1024].decode("utf-8", errors="replace"), "truncated": True}
    conflicts.append(item)


def _entity_identity(value):
    if type(value) is int and -10000000 <= value <= 10000000:
        return value  # Timeline tracks have stable integer IDs.
    return _identifier(value, "Entity identity")


def _sort_ids(values):
    return sorted(values, key=lambda value: (type(value).__name__, str(value)))


def _entity_lists(*values):
    return all(isinstance(value, list) and all(isinstance(item, dict) and type(item.get("id")) in (str, int) for item in value) for value in values)


def _ordered_entities(base, current, proposed, merged, path, conflicts):
    allowed = set(merged)
    b, c, p = ([item["id"] for item in branch if item["id"] in allowed] for branch in (base, current, proposed))
    existing = set(b)
    c_old, p_old = ([ident for ident in order if ident in existing] for order in (c, p))
    if c_old != b and p_old != b and c_old != p_old:
        _conflict(conflicts, path + ["@order"], b, c, p, "concurrent_reorder")
        return [merged[ident] for ident in _sort_ids(allowed)]
    backbone = c_old if c_old != b else p_old if p_old != b else b
    edges = {ident: set() for ident in allowed}
    for left, right in zip(backbone, backbone[1:]):
        edges[left].add(right)
    for order in (c, p):
        for left, right in zip(order, order[1:]):
            if left not in existing or right not in existing:
                edges[left].add(right)
    incoming = {ident: 0 for ident in allowed}
    for children in edges.values():
        for child in children:
            incoming[child] += 1
    result = []
    while len(result) < len(allowed):
        ready = _sort_ids(ident for ident in allowed if incoming[ident] == 0 and ident not in result)
        if not ready:
            _conflict(conflicts, path + ["@order"], b, c, p, "incompatible_insertion_order")
            return [merged[ident] for ident in _sort_ids(allowed)]
        ident = ready[0]
        result.append(ident)
        for child in edges[ident]:
            incoming[child] -= 1
    return [merged[ident] for ident in result]


def _merge(base, current, proposed, path, conflicts):
    if _equal(proposed, base) or _equal(proposed, current):
        return _copy(current)
    if _equal(current, base):
        return _copy(proposed)
    if all(isinstance(value, dict) for value in (base, current, proposed)):
        result = {}
        for key in sorted(set(base) | set(current) | set(proposed)):
            value = _merge(base.get(key, _MISSING), current.get(key, _MISSING), proposed.get(key, _MISSING), path + [key], conflicts)
            if value is not _MISSING:
                result[key] = value
        return result
    if _entity_lists(base, current, proposed):
        b, c, p = ({item["id"]: item for item in branch} for branch in (base, current, proposed))
        merged = {}
        for ident in _sort_ids(set(b) | set(c) | set(p)):
            value = _merge(b.get(ident, _MISSING), c.get(ident, _MISSING), p.get(ident, _MISSING), path + [{"id": ident}], conflicts)
            if value is not _MISSING:
                merged[ident] = value
        return _ordered_entities(base, current, proposed, merged, path, conflicts)
    reason = "delete_versus_edit" if current is _MISSING or proposed is _MISSING else "same_property"
    _conflict(conflicts, path, base, current, proposed, reason)
    return _copy(current)


def three_way_merge(base, current, proposed):
    """Return a merged JSON document or explicit conflicts; never partially commit."""
    conflicts = []
    result = _merge(base, current, proposed, [], conflicts)
    if conflicts:
        raise ConflictError("Concurrent edits need an explicit choice.", conflicts=conflicts)
    return result


def _private_directory(path):
    path = Path(path).absolute()
    if path.is_symlink():
        raise CollaborationError("The collaboration directory cannot be a symlink.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise CollaborationError("The collaboration directory is invalid.")
    os.chmod(path, 0o700)
    return path


def _regular(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise CollaborationError("Collaboration storage must contain regular owned files.")
    return info


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Coordinator:
    def __init__(self, directory, validator=None):
        candidate = Path(directory).absolute()
        if candidate.is_dir() and not candidate.is_symlink() and any(candidate.iterdir()):
            existing_marker = candidate / "coordinator.json"
            if not existing_marker.is_file() or existing_marker.is_symlink():
                raise CollaborationError("Choose a new empty directory for collaboration state.")
            if _load(existing_marker.read_bytes()) != {"format": "CINEMATICUM_COLLABORATION", "version": VERSION}:
                raise CollaborationError("This directory is not a supported collaboration coordinator.")
        self.root = _private_directory(directory)
        self.validator = validator
        self.condition = threading.Condition()
        self.endpoint = None
        self.closed = False
        marker = self.root / "coordinator.json"
        if marker.exists() or marker.is_symlink():
            _regular(marker)
            if _load(marker.read_bytes()) != {"format": "CINEMATICUM_COLLABORATION", "version": VERSION}:
                raise CollaborationError("This directory is not a supported collaboration coordinator.")
        else:
            if any(self.root.iterdir()):
                raise CollaborationError("Choose a new empty directory for collaboration state.")
            with marker.open("xb") as stream:
                stream.write(_json({"format": "CINEMATICUM_COLLABORATION", "version": VERSION}))
                stream.flush(); os.fsync(stream.fileno())
            os.chmod(marker, 0o600)
        self.blobs = _private_directory(self.root / "blobs")
        self.uploads = _private_directory(self.root / "uploads")
        self.tls = _private_directory(self.root / "tls")
        self.database = self.root / "state.sqlite3"
        if self.database.exists() or self.database.is_symlink():
            _regular(self.database)
        else:
            fd = os.open(self.database, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, document_id TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, role TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS clients_session ON clients(session_id);
                CREATE TABLE IF NOT EXISTS snapshots(session_id TEXT NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL, event_id TEXT, PRIMARY KEY(session_id,revision));
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, revision INTEGER NOT NULL, client_id TEXT NOT NULL, operation_id TEXT NOT NULL, before_document TEXT NOT NULL, after_document TEXT NOT NULL, undo_of TEXT, created REAL NOT NULL, UNIQUE(session_id,revision));
                CREATE TABLE IF NOT EXISTS operations(session_id TEXT NOT NULL, client_id TEXT NOT NULL, operation_id TEXT NOT NULL, payload_hash TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(session_id,client_id,operation_id));
                CREATE TABLE IF NOT EXISTS invites(token_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL, expires REAL NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS blobs(sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS session_blobs(session_id TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(session_id,sha256));
            """)
        _sync_directory(self.root)

    @contextmanager
    def _db(self):
        if self.closed:
            raise CollaborationError("The coordinator is closed.", status=503)
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        self.closed = True
        with self.condition:
            self.condition.notify_all()

    def _binding(self, session_id, client_id, token):
        if self.endpoint is None:
            raise CollaborationError("Start the TLS service before pairing a participant.")
        return {"version": VERSION, **self.endpoint, "session_id": session_id, "client_id": client_id, "token": token}

    def create_session(self, project, dependencies=None, owner_name="Owner"):
        if self.endpoint is None:
            raise CollaborationError("Start the TLS service before creating a shared session.")
        document = validate_document(project, dependencies or {}, self.validator)
        session_id, client_id, token = uuid.uuid4().hex, uuid.uuid4().hex, secrets.token_urlsafe(32)
        owner_name = _name(owner_name)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO sessions VALUES(?,?,0,?)", (session_id, document["project"]["id"], time.time()))
            db.execute("INSERT INTO clients(id,session_id,name,token_hash,role,created) VALUES(?,?,?,?,?,?)", (client_id, session_id, owner_name, _digest(token.encode()), "owner", time.time()))
            db.execute("INSERT INTO snapshots VALUES(?,0,?,NULL)", (session_id, _json(document).decode()))
        return self._binding(session_id, client_id, token)

    def _authenticate(self, db, session_id, token, owner=False):
        _identifier(session_id, "Session identity")
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise CollaborationError("Participant authentication is required.", code="unauthorized", status=401)
        digest = _digest(token.encode())
        client = db.execute("SELECT * FROM clients WHERE session_id=? AND token_hash=? AND revoked=0", (session_id, digest)).fetchone()
        if client is None or not hmac.compare_digest(client["token_hash"], digest):
            raise CollaborationError("Participant authentication is invalid or revoked.", code="unauthorized", status=401)
        if owner and client["role"] != "owner":
            raise CollaborationError("Only the session owner can pair or revoke participants.", code="forbidden", status=403)
        return client

    def _missing(self, db, session_id, dependencies):
        missing = []
        for path, item in dependencies.items():
            row = db.execute("SELECT b.size FROM blobs b JOIN session_blobs s ON s.sha256=b.sha256 WHERE s.session_id=? AND b.sha256=?", (session_id, item["sha256"])).fetchone()
            try:
                info = _regular(self.blobs / item["sha256"])
                stored = info.st_size == item["size"]
            except (OSError, CollaborationError):
                stored = False
            if row is None or row["size"] != item["size"] or not stored:
                missing.append({"path": path, **item})
        return missing

    def _snapshot(self, db, session_id):
        row = db.execute("SELECT p.revision,s.document,s.event_id FROM sessions p JOIN snapshots s ON s.session_id=p.id AND s.revision=p.revision WHERE p.id=?", (session_id,)).fetchone()
        if row is None:
            raise CollaborationError("Shared project does not exist.", code="not_found", status=404)
        document = _load(row["document"])
        return {**document, "revision": row["revision"], "event_id": row["event_id"], "missing_blobs": self._missing(db, session_id, document["dependencies"])}

    def _validate_materialized(self, document):
        """Validate the actual portable dependency closure without copying media.

        The engine/archive validators only read this private view; no renderer or
        inference worker runs here. Every linked byte identity is independently
        checked before semantic validation. Temporary views never become projects.
        """
        if __package__:
            from .project_archive import _collect
            from .scene import validate_scene
        else:
            from project_archive import _collect
            from scene import validate_scene
        authored_scene = document["project"].get("settings", {}).get("scene")
        if authored_scene is not None:
            scene = validate_scene(authored_scene)
            if (scene["width"], scene["height"]) != (document["project"]["width"], document["project"]["height"]):
                raise CollaborationError("A shared 3D scene must explicitly match the project resolution.")
        with tempfile.TemporaryDirectory(prefix="validate-", dir=self.uploads) as temporary:
            root = Path(temporary)
            (root / "media").mkdir()
            checked = set()
            for relative, item in document["dependencies"].items():
                digest = item["sha256"]
                source = self.blobs / digest
                info = _regular(source)
                if info.st_size != item["size"]:
                    raise CollaborationError("A shared dependency changed its byte size.", code="hash_mismatch")
                if digest not in checked:
                    actual = hashlib.sha256()
                    with source.open("rb") as stream:
                        for block in iter(lambda: stream.read(CHUNK), b""):
                            actual.update(block)
                    if actual.hexdigest() != digest:
                        raise CollaborationError("A shared dependency failed its content hash.", code="hash_mismatch")
                    checked.add(digest)
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.link(source, destination, follow_symlinks=False)
            project, closure, _ = _collect(document["project"], root)
            expected_paths = set(closure) - {"project.json", "assets.json"}
            if expected_paths != set(document["dependencies"]):
                raise CollaborationError("Shared dependencies must equal the complete portable project closure.")
            for path in expected_paths:
                expected = closure[path]
                item = document["dependencies"][path]
                if expected["size"] != item["size"] or (expected.get("expected") is not None and expected["expected"] != item["sha256"]):
                    raise CollaborationError("A dependency no longer matches its project provenance: " + path)
                if expected.get("data") is not None and _digest(expected["data"]) != item["sha256"]:
                    raise CollaborationError("A dependency descriptor no longer matches its portable bytes: " + path)
            return validate_document(project, document["dependencies"], self.validator)

    def snapshot(self, session_id, token):
        with self._db() as db:
            db.execute("BEGIN")
            self._authenticate(db, session_id, token)
            return self._snapshot(db, session_id)

    def invite(self, session_id, token, expires_seconds=600):
        if type(expires_seconds) is not int or not 30 <= expires_seconds <= 3600:
            raise CollaborationError("Pairing invitations expire in 30–3600 seconds.")
        value, expires = secrets.token_urlsafe(32), time.time() + expires_seconds
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._authenticate(db, session_id, token, owner=True)
            missing = self._snapshot(db, session_id)["missing_blobs"]
            if missing:
                raise ConflictError("Upload the initial project media before pairing a participant.", code="missing_media", missing_blobs=missing)
            snapshot = self._snapshot(db, session_id)
            self._validate_materialized({key: snapshot[key] for key in ("project", "dependencies")})
            db.execute("INSERT INTO invites VALUES(?,?,?,0)", (_digest(value.encode()), session_id, expires))
        return {"version": VERSION, **self.endpoint, "session_id": session_id, "invite_token": value, "expires_at": expires}

    def join(self, invitation, name):
        if not isinstance(invitation, dict):
            raise CollaborationError("A pairing invitation is required.")
        session_id = _identifier(invitation.get("session_id"), "Session identity")
        token = invitation.get("invite_token")
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise CollaborationError("Pairing invitation is invalid.", code="unauthorized", status=401)
        name, client_id, credential = _name(name), uuid.uuid4().hex, secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM invites WHERE token_hash=? AND session_id=?", (_digest(token.encode()), session_id)).fetchone()
            if row is None or row["consumed"] or row["expires"] <= time.time():
                raise CollaborationError("Pairing invitation expired or was already consumed.", code="invitation_expired", status=401)
            db.execute("UPDATE invites SET consumed=1 WHERE token_hash=?", (row["token_hash"],))
            db.execute("INSERT INTO clients(id,session_id,name,token_hash,role,created) VALUES(?,?,?,?,?,?)", (client_id, session_id, name, _digest(credential.encode()), "editor", time.time()))
        return self._binding(session_id, client_id, credential)

    def members(self, session_id, token):
        with self._db() as db:
            db.execute("BEGIN")
            self._authenticate(db, session_id, token)
            return {"members": [dict(row) for row in db.execute("SELECT id,name,role,revoked,created FROM clients WHERE session_id=? ORDER BY created,id", (session_id,))]}

    def revoke(self, session_id, token, client_id):
        _identifier(client_id, "Participant identity")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._authenticate(db, session_id, token, owner=True)
            target = db.execute("SELECT role FROM clients WHERE session_id=? AND id=?", (session_id, client_id)).fetchone()
            if target is None or target["role"] == "owner":
                raise CollaborationError("Choose an editor in this shared project.")
            db.execute("UPDATE clients SET revoked=1 WHERE session_id=? AND id=?", (session_id, client_id))
        with self.condition:
            self.condition.notify_all()
        return {"revoked": client_id}

    def _replay(self, db, session_id, client_id, operation_id, payload_hash):
        _identifier(operation_id, "Operation identity")
        row = db.execute("SELECT * FROM operations WHERE session_id=? AND client_id=? AND operation_id=?", (session_id, client_id, operation_id)).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            raise ConflictError("An operation identity was reused with different content.", code="operation_reused")
        return _load(row["response"])

    def _commit(self, db, session_id, client, operation_id, payload_hash, before, merged, undo_of=None):
        merged = validate_document(merged["project"], merged["dependencies"])
        if merged["project"]["id"] != before["project"]["id"]:
            raise CollaborationError("The shared document identity is immutable.")
        missing = self._missing(db, session_id, merged["dependencies"])
        if missing:
            raise ConflictError("Upload the referenced media before publishing this edit.", code="missing_media", missing_blobs=missing)
        try:
            merged = self._validate_materialized(merged)
        except (ValueError, OSError) as exc:
            message = str(exc).replace(str(self.root), "[shared storage]")[:500]
            raise ConflictError("The merged edit has an invalid project or dependency closure.", code="invalid_merged_project", revision=before["revision"], validation_error=message) from exc
        revision = before["revision"]
        changed = not _equal({key: before[key] for key in ("project", "dependencies")}, merged)
        event_id = before["event_id"]
        if changed:
            revision += 1
            event_id = uuid.uuid4().hex
            old = {key: before[key] for key in ("project", "dependencies")}
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", (event_id, session_id, revision, client["id"], operation_id, _json(old).decode(), _json(merged).decode(), undo_of, time.time()))
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (session_id, revision, _json(merged).decode(), event_id))
            db.execute("UPDATE sessions SET revision=? WHERE id=?", (revision, session_id))
        response = {**merged, "revision": revision, "event_id": event_id, "missing_blobs": [], "changed": changed, "client_id": client["id"]}
        db.execute("INSERT INTO operations VALUES(?,?,?,?,?)", (session_id, client["id"], operation_id, payload_hash, _json(response).decode()))
        return response

    def submit(self, session_id, token, project, dependencies, base_revision, operation_id):
        if type(base_revision) is not int or base_revision < 0:
            raise CollaborationError("An edit needs its authoritative base revision.")
        proposed = validate_document(project, dependencies)
        payload_hash = _digest(_json({"operation": "edit", "base_revision": base_revision, **proposed}))
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            client = self._authenticate(db, session_id, token)
            replay = self._replay(db, session_id, client["id"], operation_id, payload_hash)
            if replay is not None:
                return replay
            before = self._snapshot(db, session_id)
            base = db.execute("SELECT document FROM snapshots WHERE session_id=? AND revision=?", (session_id, base_revision)).fetchone()
            if base is None:
                raise ConflictError("The edit base revision is unavailable.", code="unknown_revision", revision=before["revision"])
            if proposed["project"]["id"] != before["project"]["id"]:
                raise CollaborationError("The shared document identity is immutable.")
            try:
                merged = three_way_merge(_load(base["document"]), {key: before[key] for key in ("project", "dependencies")}, proposed)
            except ConflictError as exc:
                exc.details["revision"] = before["revision"]
                raise
            response = self._commit(db, session_id, client, operation_id, payload_hash, before, merged)
        with self.condition:
            self.condition.notify_all()
        return response

    def undo(self, session_id, token, event_id, operation_id):
        _identifier(event_id, "Event identity")
        payload_hash = _digest(_json({"operation": "undo", "event_id": event_id}))
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            client = self._authenticate(db, session_id, token)
            replay = self._replay(db, session_id, client["id"], operation_id, payload_hash)
            if replay is not None:
                return replay
            event = db.execute("SELECT * FROM events WHERE session_id=? AND id=?", (session_id, event_id)).fetchone()
            if event is None:
                raise CollaborationError("The edit event is unavailable.", code="not_found", status=404)
            if event["client_id"] != client["id"]:
                raise CollaborationError("Selective undo can only reverse this participant's own edit.", code="forbidden", status=403)
            before = self._snapshot(db, session_id)
            try:
                merged = three_way_merge(_load(event["after_document"]), {key: before[key] for key in ("project", "dependencies")}, _load(event["before_document"]))
            except ConflictError as exc:
                exc.details["revision"] = before["revision"]
                raise
            response = self._commit(db, session_id, client, operation_id, payload_hash, before, merged, undo_of=event_id)
        with self.condition:
            self.condition.notify_all()
        return response

    def events(self, session_id, token, after_revision=0, wait_seconds=15):
        if type(after_revision) is not int or after_revision < 0 or not isinstance(wait_seconds, (int, float)) or isinstance(wait_seconds, bool) or not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 20:
            raise CollaborationError("Event polling needs a nonnegative revision and a 0–20 second wait.")
        deadline = time.monotonic() + wait_seconds
        while True:
            with self._db() as db:
                db.execute("BEGIN")
                self._authenticate(db, session_id, token)
                revision = db.execute("SELECT revision FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
                if after_revision > revision:
                    raise ConflictError("The event cursor is newer than this coordinator.", code="unknown_revision", revision=revision)
                rows = db.execute("SELECT e.id,e.revision,e.client_id,c.name,e.operation_id,e.undo_of,e.created FROM events e JOIN clients c ON c.id=e.client_id WHERE e.session_id=? AND e.revision>? ORDER BY e.revision LIMIT 100", (session_id, after_revision)).fetchall()
            if rows or time.monotonic() >= deadline or self.closed:
                return {"events": [dict(row) for row in rows], "revision": revision, "more": bool(rows and rows[-1]["revision"] < revision)}
            with self.condition:
                self.condition.wait(timeout=min(0.25, max(0, deadline - time.monotonic())))

    def upload_blob(self, session_id, token, digest, stream, size):
        digest = _sha(digest)
        if type(size) is not int or not 0 < size <= MAX_BLOB:
            raise CollaborationError("Blob length must be positive and no larger than 64 GiB.")
        with self._db() as db:
            self._authenticate(db, session_id, token)
        fd, temporary = tempfile.mkstemp(prefix="upload-", dir=self.uploads)
        try:
            actual, remaining = hashlib.sha256(), size
            with os.fdopen(fd, "wb") as output:
                while remaining:
                    block = stream.read(min(CHUNK, remaining))
                    if not block:
                        raise CollaborationError("The blob stream ended before its declared size.")
                    actual.update(block); output.write(block); remaining -= len(block)
                output.flush(); os.fsync(output.fileno())
            if not hmac.compare_digest(actual.hexdigest(), digest):
                raise CollaborationError("Blob bytes do not match their SHA-256 identity.", code="hash_mismatch")
            destination = self.blobs / digest
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._authenticate(db, session_id, token)
                total = db.execute("SELECT COALESCE(SUM(b.size),0),COUNT(*) FROM blobs b JOIN session_blobs s ON s.sha256=b.sha256 WHERE s.session_id=?", (session_id,)).fetchone()
                present = db.execute("SELECT 1 FROM session_blobs WHERE session_id=? AND sha256=?", (session_id, digest)).fetchone()
                if present is None and (total[0] + size > MAX_BLOB or total[1] >= MAX_FILES):
                    raise CollaborationError("The shared blob inventory exceeds 10,000 files or 64 GiB.")
                try:
                    os.link(temporary, destination, follow_symlinks=False)
                    _sync_directory(self.blobs)
                except FileExistsError:
                    info = _regular(destination)
                    if info.st_size != size:
                        raise CollaborationError("An existing immutable blob has inconsistent storage.")
                    # Re-verify existing bytes before adopting a globally present object.
                    check = hashlib.sha256()
                    with destination.open("rb") as existing:
                        for block in iter(lambda: existing.read(CHUNK), b""):
                            check.update(block)
                    if check.hexdigest() != digest:
                        raise CollaborationError("An existing immutable blob failed its content hash.", code="hash_mismatch")
                db.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (digest, size))
                db.execute("INSERT OR IGNORE INTO session_blobs VALUES(?,?)", (session_id, digest))
            return {"sha256": digest, "size": size}
        finally:
            Path(temporary).unlink(missing_ok=True)

    def open_blob(self, session_id, token, digest):
        digest = _sha(digest)
        with self._db() as db:
            self._authenticate(db, session_id, token)
            row = db.execute("SELECT b.size FROM blobs b JOIN session_blobs s ON s.sha256=b.sha256 WHERE s.session_id=? AND b.sha256=?", (session_id, digest)).fetchone()
            if row is None:
                raise CollaborationError("The blob is not owned by this shared project.", code="missing_media", status=404)
        try:
            fd = os.open(self.blobs / digest, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != row["size"]:
                os.close(fd)
                raise CollaborationError("The owned blob is missing or damaged.", code="missing_media", status=409)
        except FileNotFoundError as exc:
            raise CollaborationError("The owned blob is missing.", code="missing_media", status=409) from exc
        return os.fdopen(fd, "rb"), row["size"]


def _certificate(coordinator):
    key, cert = coordinator.tls / "key.pem", coordinator.tls / "certificate.pem"
    if key.exists() or cert.exists() or key.is_symlink() or cert.is_symlink():
        _regular(key); _regular(cert)
    else:
        with tempfile.TemporaryDirectory(prefix="create-", dir=coordinator.tls) as temporary:
            generated_key, generated_cert = Path(temporary) / "key.pem", Path(temporary) / "certificate.pem"
            config = Path(temporary) / "openssl.cnf"
            config.write_text("[req]\nprompt = no\ndistinguished_name = identity\nx509_extensions = identity_extensions\n[identity]\nCN = CINEMATICUM paired coordinator\n[identity_extensions]\nbasicConstraints = critical,CA:TRUE\nkeyUsage = critical,digitalSignature,keyEncipherment,keyCertSign\nextendedKeyUsage = serverAuth\n", encoding="ascii")
            command = ["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-nodes", "-days", "3650", "-config", str(config), "-keyout", str(generated_key), "-out", str(generated_cert)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CollaborationError("OpenSSL is required to create the local TLS identity.") from exc
            if result.returncode:
                raise CollaborationError("OpenSSL could not create the local TLS identity.")
            os.chmod(generated_key, 0o600); os.chmod(generated_cert, 0o600)
            os.rename(generated_key, key); os.rename(generated_cert, cert)
            _sync_directory(coordinator.tls)
    pem = cert.read_text("ascii")
    fingerprint = _digest(ssl.PEM_cert_to_DER_cert(pem))
    return key, cert, pem, fingerprint


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True
    request_queue_size = 16

    def __init__(self, *args, **kwargs):
        self.worker_slots = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.worker_slots.release()

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ssl.SSLError, socket.timeout, ConnectionError)):
            return
        super().handle_error(request, client_address)

    def get_request(self):
        connection, address = self.socket.accept()
        connection.settimeout(30)
        try:
            # A peer that stalls its handshake must not block the accept loop.
            return self.tls_context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False), address
        except Exception:
            connection.close()
            raise


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "CINEMATICUM-Paired/1"
    sys_version = ""

    def log_message(self, *_):
        pass

    def _reply(self, status, payload):
        data = _json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _length(self, maximum):
        headers = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(headers) != 1 or not re.fullmatch(r"[0-9]{1,12}", headers[0]):
            raise CollaborationError("Exactly one explicit Content-Length is required.")
        value = int(headers[0])
        if value <= 0 or value > maximum:
            raise CollaborationError("The request body has an invalid length.")
        return value

    def _body(self):
        length = self._length(MAX_JSON)
        if self.headers.get_content_type() != "application/json":
            raise CollaborationError("A JSON request body is required.")
        data = self.rfile.read(length)
        if len(data) != length:
            raise CollaborationError("The JSON request body was interrupted.")
        value = _load(data)
        if not isinstance(value, dict):
            raise CollaborationError("A JSON object request body is required.")
        return value

    def _dispatch(self):
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.fragment or "%" in parsed.path:
            raise CollaborationError("Invalid collaboration route.")
        coordinator = self.server.coordinator
        if self.command == "POST" and parsed.path == "/v1/join":
            body = self._body()
            return self._reply(200, coordinator.join(body, body.get("name")))
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[:2] != ["v1", "sessions"]:
            raise CollaborationError("Unknown collaboration route.", code="not_found", status=404)
        session, action = parts[2], parts[3]
        auth = self.headers.get_all("Authorization", [])
        token = auth[0][7:] if len(auth) == 1 and auth[0].startswith("Bearer ") else ""
        # Authenticate before reading bodies, including large blob uploads.
        with coordinator._db() as db:
            coordinator._authenticate(db, session, token)
        if action == "blobs" and len(parts) == 5:
            digest = _sha(parts[4])
            if self.command == "PUT":
                return self._reply(200, coordinator.upload_blob(session, token, digest, self.rfile, self._length(MAX_BLOB)))
            if self.command == "GET":
                stream, size = coordinator.open_blob(session, token, digest)
                with stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(size))
                    self.send_header("X-Content-SHA256", digest)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for block in iter(lambda: stream.read(CHUNK), b""):
                        self.wfile.write(block)
                self.close_connection = True
                return
        if len(parts) != 4:
            raise CollaborationError("Unknown collaboration route.", code="not_found", status=404)
        if self.command == "GET":
            if action == "snapshot":
                return self._reply(200, coordinator.snapshot(session, token))
            if action == "members":
                return self._reply(200, coordinator.members(session, token))
            if action == "events":
                query = parse_qs(parsed.query, strict_parsing=True)
                if set(query) - {"after", "wait"} or any(len(values) != 1 for values in query.values()):
                    raise CollaborationError("Invalid event query.")
                return self._reply(200, coordinator.events(session, token, int(query.get("after", ["0"])[0]), float(query.get("wait", ["15"])[0])))
        if self.command == "POST":
            body = self._body()
            if action == "edits":
                return self._reply(200, coordinator.submit(session, token, body.get("project"), body.get("dependencies"), body.get("base_revision"), body.get("operation_id")))
            if action == "undo":
                return self._reply(200, coordinator.undo(session, token, body.get("event_id"), body.get("operation_id")))
            if action == "invites":
                return self._reply(200, coordinator.invite(session, token, body.get("expires_seconds", 600)))
            if action == "revoke":
                return self._reply(200, coordinator.revoke(session, token, body.get("client_id")))
        raise CollaborationError("Unknown collaboration operation.", code="not_found", status=404)

    def _handle(self):
        try:
            self._dispatch()
        except CollaborationError as exc:
            self._reply(exc.status, exc.as_dict())
        except (ValueError, KeyError, TypeError) as exc:
            self._reply(400, {"error": "Invalid collaboration request.", "code": "invalid_request"})
        except (BrokenPipeError, ConnectionError, socket.timeout):
            self.close_connection = True
        except Exception:
            self._reply(500, {"error": "The coordinator could not complete this operation.", "code": "coordinator_error"})

    do_GET = do_POST = do_PUT = _handle


class RunningService:
    def __init__(self, coordinator, server, endpoint):
        self.coordinator, self.server = coordinator, server
        self.url = endpoint["url"]
        self.certificate_pem = endpoint["certificate_pem"]
        self.certificate_sha256 = endpoint["certificate_sha256"]
        self.thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True, name="cinematicum-collaboration")
        self.thread.start()

    def close(self):
        self.server.shutdown(); self.server.server_close()
        self.thread.join(timeout=5)


def start_tls_server(coordinator, host="127.0.0.1", port=0, advertise_host=None):
    if not isinstance(coordinator, Coordinator):
        raise CollaborationError("A collaboration coordinator is required.")
    if type(port) is not int or not 0 <= port <= 65535:
        raise CollaborationError("The TLS port is invalid.")
    # An explicit peer-facing address is an application/user choice, not discovery.
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise CollaborationError("Bind the collaboration service to an explicit IP address.") from exc
    if address.version != 4:
        raise CollaborationError("This coordinator currently binds IPv4 interfaces.")
    if address.is_unspecified and not advertise_host:
        raise CollaborationError("A peer-facing listener needs its explicit advertised hostname or address.")
    public_host = advertise_host or host
    if not isinstance(public_host, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", public_host):
        raise CollaborationError("The advertised coordinator hostname is invalid.")
    key, cert, pem, fingerprint = _certificate(coordinator)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server = _HTTPServer((host, port), _Handler)
    server.coordinator, server.tls_context = coordinator, context
    endpoint = {"url": f"https://{public_host}:{server.server_port}", "certificate_pem": pem, "certificate_sha256": fingerprint}
    coordinator.endpoint = endpoint
    return RunningService(coordinator, server, endpoint)


class Client:
    """One paired participant; every request validates TLS before sending its token."""
    def __init__(self, binding, timeout=45):
        if not isinstance(binding, dict) or binding.get("version") != VERSION:
            raise CollaborationError("A supported private collaboration binding is required.")
        self.binding = copy.deepcopy(binding)
        self.timeout = timeout
        parsed = urlsplit(binding.get("url", ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or parsed.port is None:
            raise CollaborationError("Pair only an explicit HTTPS coordinator address and port.")
        self.host, self.port = parsed.hostname, parsed.port
        pem = binding.get("certificate_pem")
        try:
            if not isinstance(pem, str) or len(pem) > 16384:
                raise ValueError("Invalid certificate")
            fingerprint = _digest(ssl.PEM_cert_to_DER_cert(pem))
        except (ValueError, ssl.SSLError) as exc:
            raise CollaborationError("The invitation has no valid TLS certificate.") from exc
        if not hmac.compare_digest(fingerprint, _sha(binding.get("certificate_sha256"))):
            raise CollaborationError("The invitation certificate does not match its pinned identity.", code="certificate_mismatch")
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.check_hostname = False  # Identity is the explicitly paired DER certificate.
        self.context.verify_mode = ssl.CERT_REQUIRED
        self.context.load_verify_locations(cadata=pem)
        self.session_id = _identifier(binding.get("session_id"), "Session identity")

    def _connect(self):
        connection = http.client.HTTPSConnection(self.host, self.port, context=self.context, timeout=self.timeout)
        connection.connect()
        if not hmac.compare_digest(_digest(connection.sock.getpeercert(binary_form=True)), self.binding["certificate_sha256"]):
            connection.close()
            raise CollaborationError("The coordinator TLS identity changed.", code="certificate_mismatch")
        return connection

    def _headers(self):
        token = self.binding.get("token", "")
        if not isinstance(token, str) or not 32 <= len(token) <= 128 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise CollaborationError("A private participant credential is required.")
        return {"Authorization": "Bearer " + token}

    @staticmethod
    def _response(response):
        data = response.read(MAX_JSON + 1)
        value = _load(data)
        if not isinstance(value, dict):
            raise CollaborationError("The coordinator returned invalid metadata.")
        if response.status >= 400:
            message, code = value.pop("error", "Collaboration request failed."), value.pop("code", "coordinator_error")
            if response.status == 409:
                raise ConflictError(message, code=code, **value)
            raise CollaborationError(message, code=code, status=response.status, **value)
        return value

    def _request(self, method, action, body=None, anonymous=False):
        connection = self._connect()
        try:
            path = "/v1/join" if anonymous else "/v1/sessions/" + self.session_id + "/" + action
            headers = {} if anonymous else self._headers()
            data = None if body is None else _json(body)
            if data is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, path, body=data, headers=headers)
            return self._response(connection.getresponse())
        finally:
            connection.close()

    @classmethod
    def join(cls, invitation, name):
        client = cls(invitation)
        binding = client._request("POST", "", {"session_id": client.session_id, "invite_token": invitation.get("invite_token"), "name": name}, anonymous=True)
        # Never replace the explicitly trusted endpoint with response-supplied routing.
        for key in ("url", "certificate_pem", "certificate_sha256"):
            binding[key] = invitation[key]
        if binding.get("session_id") != client.session_id:
            raise CollaborationError("Pairing returned a different shared project.")
        return binding

    def snapshot(self):
        return self._request("GET", "snapshot")

    def submit(self, project, dependencies, base_revision, operation_id):
        return self._request("POST", "edits", {"project": project, "dependencies": dependencies, "base_revision": base_revision, "operation_id": operation_id})

    def events(self, after_revision=0, wait_seconds=15):
        if type(after_revision) is not int or not isinstance(wait_seconds, (int, float)) or isinstance(wait_seconds, bool) or not math.isfinite(wait_seconds):
            raise CollaborationError("Event polling needs a revision and finite wait duration.")
        return self._request("GET", f"events?after={after_revision}&wait={wait_seconds}")

    def undo(self, event_id, operation_id):
        return self._request("POST", "undo", {"event_id": event_id, "operation_id": operation_id})

    def invite(self, expires_seconds=600):
        return self._request("POST", "invites", {"expires_seconds": expires_seconds})

    def members(self):
        return self._request("GET", "members")

    def revoke(self, client_id):
        return self._request("POST", "revoke", {"client_id": client_id})

    def upload_blob(self, path, expected_sha256):
        digest = _sha(expected_sha256)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BLOB:
                raise CollaborationError("Upload one regular owned media file of at most 64 GiB.")
            connection = self._connect()
            try:
                connection.putrequest("PUT", "/v1/sessions/" + self.session_id + "/blobs/" + digest)
                for key, value in {**self._headers(), "Content-Type": "application/octet-stream", "Content-Length": str(info.st_size)}.items():
                    connection.putheader(key, value)
                connection.endheaders()
                remaining = info.st_size
                while remaining:
                    block = source.read(min(CHUNK, remaining))
                    if not block:
                        raise CollaborationError("The source changed while being uploaded.")
                    connection.send(block); remaining -= len(block)
                after = os.fstat(source.fileno())
                if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise CollaborationError("The source changed while being uploaded.")
                return self._response(connection.getresponse())
            finally:
                connection.close()

    def download_blob(self, digest, owned_destination, expected_size=None):
        digest = _sha(digest)
        destination = Path(owned_destination).absolute()
        # Root's project bridge chooses this path. No network-supplied path is used.
        if not destination.parent.is_dir() or destination.parent.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
            raise CollaborationError("Download into an existing owned directory without symlinks.")
        if destination.exists() or destination.is_symlink():
            raise CollaborationError("A blob download cannot replace an existing file.")
        connection = self._connect()
        temporary = None
        try:
            connection.request("GET", "/v1/sessions/" + self.session_id + "/blobs/" + digest, headers=self._headers())
            response = connection.getresponse()
            if response.status != 200:
                return self._response(response)
            raw_size = response.getheader("Content-Length", "")
            if not re.fullmatch(r"[0-9]{1,12}", raw_size):
                raise CollaborationError("The coordinator returned an invalid blob size.")
            size = int(raw_size)
            if not 0 < size <= MAX_BLOB or (expected_size is not None and size != expected_size) or response.getheader("X-Content-SHA256") != digest:
                raise CollaborationError("The received blob identity or size is inconsistent.")
            fd, temporary = tempfile.mkstemp(prefix=".collaboration-download-", dir=destination.parent)
            actual, remaining = hashlib.sha256(), size
            with os.fdopen(fd, "wb") as output:
                while remaining:
                    block = response.read(min(CHUNK, remaining))
                    if not block:
                        raise CollaborationError("The blob download was interrupted.")
                    actual.update(block); output.write(block); remaining -= len(block)
                output.flush(); os.fsync(output.fileno())
            if not hmac.compare_digest(actual.hexdigest(), digest):
                raise CollaborationError("Downloaded bytes failed their SHA-256 identity.", code="hash_mismatch")
            os.link(temporary, destination, follow_symlinks=False)
            _sync_directory(destination.parent)
            return {"sha256": digest, "size": size, "path": str(destination)}
        finally:
            connection.close()
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

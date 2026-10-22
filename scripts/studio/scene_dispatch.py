"""Authenticated fixed-operation scene workers and durable distributed batches.

TLS identities and bearer credentials are explicitly paired and kept outside
projects. SQLite records jobs before work starts. Only validated scene data is
accepted: no paths, commands, Python, arbitrary URLs or caller-named outputs.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid
import zipfile

from adapters import _cancelled, _run_owned
from collaboration import (Client as PinnedClient, CollaborationError, RunningService,
                           _HTTPServer, _Handler, _certificate, _private_directory,
                           _regular, _sync_directory)
from scene import validate_scene
from scene_processing import (MAX_ARTIFACT_BYTES, MAX_TASKS, _artifact_inventory, _hash_file,
    _identifier, _mapping, _number, _publish_directory, _write_json, canonical_bytes,
    compile_scene_graph, digest, validate_context, validate_scene_graph)

VERSION = 1
WORKER_ARTIFACTS = frozenset({"preview.mp4", "authored.blend", "linear-masters.zip", "scene.json", "receipt.json"})
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_JOB = re.compile(r"[a-f0-9]{32}\Z")
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
CHUNK = 1024 * 1024


class DispatchError(CollaborationError):
    pass


def _json_load(data):
    from collaboration import _load
    return _load(data)


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value): raise DispatchError("A SHA-256 identity is required.")
    return value


def _job_id(value):
    if not isinstance(value, str) or not _JOB.fullmatch(value): raise DispatchError("A valid owned job identity is required.")
    return value


def _operation(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise DispatchError("An explicit idempotent operation identity is required.")
    return value


def _label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 80 or any(ord(c) < 32 for c in value):
        raise DispatchError("A printable client/worker name is required.")
    return value.strip()


def _open_private_database(root, filename):
    path = root / filename
    if path.exists() or path.is_symlink(): _regular(path)
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600); os.close(descriptor)
    return path


def _marker(directory, format_name):
    candidate = Path(directory).absolute()
    if any(path.is_symlink() for path in (candidate, *candidate.parents)):
        raise DispatchError("Scene dispatch storage paths cannot contain symbolic links.")
    expected = {"format": format_name, "version": VERSION}
    if candidate.is_dir() and any(candidate.iterdir()):
        marker = candidate / "identity.json"
        if marker.is_symlink() or not marker.is_file(): raise DispatchError("Choose a new empty owned directory for scene dispatch.")
        value = _json_load(marker.read_bytes())
        if (not isinstance(value, dict) or value.get("format") != format_name or value.get("version") != VERSION
                or not isinstance(value.get("id"), str) or not _JOB.fullmatch(value["id"])):
            raise DispatchError("This directory belongs to a different or unsupported service.")
    else:
        candidate = _private_directory(candidate)
        value = {**expected, "id": uuid.uuid4().hex}
        _write_json(candidate / "identity.json", value); os.chmod(candidate / "identity.json", 0o600)
    return _private_directory(candidate), value["id"]


def validate_render_request(value):
    _mapping(value, {"version", "operation", "scene", "scene_sha256", "graph_sha256", "context_sha256", "context"}, "Worker render request")
    if type(value.get("version")) is not int or value["version"] != VERSION or value.get("operation") != "scene_render":
        raise DispatchError("The paired worker accepts only scene_render version 1.")
    scene = validate_scene(value.get("scene"))
    if scene["frame_end"] != 1 or any(x.get("keyframes") or x.get("parent_id") or x.get("modeling") for x in scene["objects"]):
        raise DispatchError("Distributed tasks require an evaluated single-frame scene.")
    if scene["camera"].get("keyframes") or any(x.get("keyframes") for x in scene["lights"]):
        raise DispatchError("Distributed camera/light animation must be sampled before submission.")
    if not scene["objects"]: raise DispatchError("A render task needs visible scene geometry.")
    actual = digest(scene)
    if _sha(value.get("scene_sha256")) != actual: raise DispatchError("Compiled scene hash does not match its data.")
    context = value.get("context")
    if not isinstance(context, dict) or len(context) > 35 or len(canonical_bytes(context)) > 16384:
        raise DispatchError("Worker context is invalid or exceeds its bounds.")
    for key, item in context.items():
        _identifier(key, "Context name")
        if type(item) is bool or isinstance(item, str) and len(item) <= 256: continue
        if isinstance(item, list) and len(item) == 3:
            for part in item: _number(part, "Context coordinate")
        elif isinstance(item, (int, float)) and not isinstance(item, bool): _number(item, "Context value", -1e6, 1e6)
        else: raise DispatchError("Worker context contains an unsupported value.")
    frame, fps = _number(context.get("frame"), "Source frame", -7200, 7200), _number(context.get("fps"), "Render fps", 1, 60)
    if context.get("time") != frame / fps: raise DispatchError("Context time must equal frame/fps.")
    if _sha(value.get("context_sha256")) != digest(context): raise DispatchError("Context hash does not match its data.")
    return {"version": VERSION, "operation": "scene_render", "scene": scene, "scene_sha256": actual,
            "graph_sha256": _sha(value.get("graph_sha256")), "context_sha256": digest(context), "context": copy.deepcopy(context)}


def render_request(compiled):
    return validate_render_request({"version": VERSION, "operation": "scene_render", "scene": compiled["scene"],
        "scene_sha256": compiled["scene_sha256"], "graph_sha256": compiled["graph_sha256"],
        "context_sha256": compiled["context_sha256"], "context": compiled["evaluation"]["context"]})


class RenderWorker:
    def __init__(self, directory, slots=1):
        self.root, self.worker_id = _marker(directory, "CINEMATICUM_SCENE_WORKER")
        self.slots = _number(slots, "Worker slots", 1, 2, True)
        self.lease = os.open(self.root / "authority.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try: fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lease); raise DispatchError("This scene worker is already running.")
        self.tls = _private_directory(self.root / "tls")
        self.jobs_dir = _private_directory(self.root / "jobs")
        self.database = _open_private_database(self.root, "worker.sqlite3")
        self.closed = False; self.endpoint = None
        self.stopping = threading.Event(); self.condition = threading.Condition()
        self.active = {}; self.active_lock = threading.Lock(); self.scheduler = None
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY,name TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,role TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS invites(token_hash TEXT PRIMARY KEY,expires REAL NOT NULL,consumed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,client_id TEXT NOT NULL,operation_id TEXT NOT NULL,payload_hash TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,progress REAL NOT NULL DEFAULT 0,attempt INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL,error TEXT,result TEXT,UNIQUE(client_id,operation_id));
            """)
            db.execute("UPDATE jobs SET status='interrupted',error='The prior worker stopped before a terminal receipt was committed.',updated=? WHERE status IN ('running','cancelling')", (time.time(),))
        _sync_directory(self.root)

    @contextmanager
    def _db(self):
        if self.closed: raise DispatchError("The scene worker is closed.", status=503)
        db = sqlite3.connect(self.database, timeout=30); db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL"); db.execute("PRAGMA busy_timeout=30000")
        try:
            with db: yield db
        finally: db.close()

    def _binding(self, client_id, token):
        if not self.endpoint: raise DispatchError("Start the worker TLS service before pairing.")
        return {"version": VERSION, **self.endpoint, "session_id": self.worker_id, "client_id": client_id, "token": token}

    def pair_owner(self, name="Owner"):
        if not self.endpoint: raise DispatchError("Start the worker TLS service before pairing.")
        client_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("INSERT INTO clients(id,name,token_hash,role,created) VALUES(?,?,?,?,?)", (client_id, _label(name), hashlib.sha256(token.encode()).hexdigest(), "owner", time.time()))
        return self._binding(client_id, token)

    def _authenticate(self, db, session_id, token, owner=False):
        if session_id != self.worker_id or not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise DispatchError("Worker authentication is required.", code="unauthorized", status=401)
        hashed = hashlib.sha256(token.encode()).hexdigest()
        row = db.execute("SELECT * FROM clients WHERE token_hash=? AND revoked=0", (hashed,)).fetchone()
        if row is None or not hmac.compare_digest(row["token_hash"], hashed):
            raise DispatchError("Worker authentication is invalid or revoked.", code="unauthorized", status=401)
        if owner and row["role"] != "owner": raise DispatchError("Only the owner may pair or revoke clients.", code="forbidden", status=403)
        return row

    def invite(self, session_id, token, expires_seconds=600):
        expires_seconds = _number(expires_seconds, "Invitation lifetime", 30, 3600, True)
        secret = secrets.token_urlsafe(32); expires = time.time() + expires_seconds
        with self._db() as db:
            self._authenticate(db, session_id, token, owner=True)
            db.execute("INSERT INTO invites(token_hash,expires) VALUES(?,?)", (hashlib.sha256(secret.encode()).hexdigest(), expires))
        return {"version": VERSION, **self.endpoint, "session_id": self.worker_id, "invite_token": secret, "expires": expires}

    def join(self, value):
        if not isinstance(value, dict) or value.get("session_id") != self.worker_id:
            raise DispatchError("Worker invitation identity is invalid.", code="unauthorized", status=401)
        secret = value.get("invite_token", "")
        if not isinstance(secret, str) or not 32 <= len(secret) <= 128: raise DispatchError("A one-use worker invitation is required.", code="unauthorized", status=401)
        hashed = hashlib.sha256(secret.encode()).hexdigest()
        client_id, token, name = uuid.uuid4().hex, secrets.token_urlsafe(32), _label(value.get("name"))
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM invites WHERE token_hash=?", (hashed,)).fetchone()
            if row is None or row["consumed"] or row["expires"] < time.time(): raise DispatchError("Worker invitation is expired or already consumed.", code="unauthorized", status=401)
            db.execute("UPDATE invites SET consumed=1 WHERE token_hash=?", (hashed,))
            db.execute("INSERT INTO clients(id,name,token_hash,role,created) VALUES(?,?,?,?,?)", (client_id, name, hashlib.sha256(token.encode()).hexdigest(), "client", time.time()))
        return self._binding(client_id, token)

    def revoke(self, session_id, token, client_id):
        _job_id(client_id)
        with self._db() as db:
            owner = self._authenticate(db, session_id, token, owner=True)
            if owner["id"] == client_id: raise DispatchError("An owner cannot revoke the credential used for this request.")
            if db.execute("UPDATE clients SET revoked=1 WHERE id=?", (client_id,)).rowcount != 1: raise DispatchError("Worker client does not exist.", status=404)
        return {"revoked": client_id}

    def _owned_job(self, db, client, job_id):
        row = db.execute("SELECT * FROM jobs WHERE id=? AND client_id=?", (_job_id(job_id), client["id"])).fetchone()
        if row is None: raise DispatchError("This render job is not owned by the authenticated client.", code="not_found", status=404)
        return row

    def _report(self, row):
        return {"id": row["id"], "worker_id": self.worker_id, "client_id": row["client_id"], "operation_id": row["operation_id"],
                "request_sha256": row["payload_hash"], "status": row["status"], "progress": row["progress"], "attempt": row["attempt"],
                "created": row["created"], "updated": row["updated"], "error": row["error"],
                "result": _json_load(row["result"]) if row["result"] else None}

    def submit_job(self, session_id, token, request, operation_id):
        request = validate_render_request(request); operation_id = _operation(operation_id)
        payload = canonical_bytes(request).decode(); payload_hash = digest(request)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE"); client = self._authenticate(db, session_id, token)
            previous = db.execute("SELECT * FROM jobs WHERE client_id=? AND operation_id=?", (client["id"], operation_id)).fetchone()
            if previous:
                if previous["payload_hash"] != payload_hash: raise DispatchError("This operation identity was already used for different scene data.", code="operation_reused", status=409)
                return self._report(previous)
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status NOT IN ('completed','failed','cancelled','interrupted')").fetchone()[0] >= 64:
                raise DispatchError("This worker already has 64 unsettled jobs.", code="queue_full", status=409)
            job_id, now = uuid.uuid4().hex, time.time()
            db.execute("INSERT INTO jobs(id,client_id,operation_id,payload_hash,payload,status,created,updated) VALUES(?,?,?,?,?,'queued',?,?)", (job_id, client["id"], operation_id, payload_hash, payload, now, now))
            report = self._report(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
        with self.condition: self.condition.notify_all()
        return report

    def job(self, session_id, token, job_id):
        with self._db() as db:
            client = self._authenticate(db, session_id, token)
            return self._report(self._owned_job(db, client, job_id))

    def operation(self, session_id, token, operation_id):
        """Read-only recovery of an accepted submission whose reply was lost."""
        with self._db() as db:
            client = self._authenticate(db, session_id, token)
            row = db.execute("SELECT * FROM jobs WHERE client_id=? AND operation_id=?", (client["id"], _operation(operation_id))).fetchone()
            return {"job": self._report(row) if row is not None else None}

    def cancel_job(self, session_id, token, job_id):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE"); client = self._authenticate(db, session_id, token); row = self._owned_job(db, client, job_id)
            if row["status"] not in TERMINAL:
                status = "cancelled" if row["status"] == "queued" else "cancelling"
                db.execute("UPDATE jobs SET status=?,updated=? WHERE id=?", (status, time.time(), job_id))
        with self.active_lock:
            if job_id in self.active: self.active[job_id]["cancel"].set()
        return self.job(session_id, token, job_id)

    def retry_job(self, session_id, token, job_id):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE"); client = self._authenticate(db, session_id, token); row = self._owned_job(db, client, job_id)
            if row["status"] in {"failed", "interrupted", "cancelled"}:
                lease_path = self.jobs_dir / job_id / "render.lock"
                if lease_path.parent.exists():
                    lease = os.open(lease_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    try:
                        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError: raise DispatchError("A previous attempt is still settling; retry after its owned lease is released.", code="attempt_settling", status=409)
                    finally: os.close(lease)
                db.execute("UPDATE jobs SET status='queued',progress=0,error=NULL,result=NULL,updated=? WHERE id=?", (time.time(), job_id))
        with self.condition: self.condition.notify_all()
        return self.job(session_id, token, job_id)

    def open_artifact(self, session_id, token, job_id, filename):
        if filename not in WORKER_ARTIFACTS: raise DispatchError("Unknown worker artifact.", status=404)
        with self._db() as db:
            client = self._authenticate(db, session_id, token); row = self._owned_job(db, client, job_id)
            if row["status"] != "completed" or not row["result"]: raise DispatchError("Only completed render artifacts may be downloaded.", status=409)
            result = _json_load(row["result"])
            record = next((x for x in result["artifacts"] if x["filename"] == filename), None)
            if record is None: raise DispatchError("Artifact is absent from this completed task.", status=404)
            path = self.jobs_dir / job_id / ("attempt-%04d" % row["attempt"]) / "render" / "published" / filename
            for ancestor in (path, *list(path.parents)[:4]):
                if ancestor.is_symlink(): raise DispatchError("Worker artifact storage is invalid.")
            info = _regular(path)
            if info.st_size != record["size"] or _hash_file(path) != record["sha256"]: raise DispatchError("Worker artifact bytes no longer match their completed receipt.", code="artifact_corrupt", status=409)
            stream = path.open("rb")
            return stream, record

    def activate(self):
        if self.scheduler: return
        self.scheduler = threading.Thread(target=self._schedule, daemon=True, name="scene-worker-scheduler")
        self.scheduler.start()

    def _schedule(self):
        while not self.stopping.is_set():
            with self.active_lock: room = self.slots - len(self.active)
            if room:
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    rows = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created,id LIMIT ?", (room,)).fetchall()
                    for row in rows: db.execute("UPDATE jobs SET status='running',attempt=attempt+1,updated=?,error=NULL WHERE id=?", (time.time(), row["id"]))
                for row in rows:
                    event = threading.Event()
                    thread = threading.Thread(target=self._execute, args=(row["id"], row["attempt"] + 1, _json_load(row["payload"]), event), daemon=True, name="scene-render-" + row["id"][:8])
                    with self.active_lock: self.active[row["id"]] = {"cancel": event, "thread": thread}
                    thread.start()
            with self.condition: self.condition.wait(timeout=.1)

    def _execute(self, job_id, attempt, request, event):
        process = None; stdout_thread = stderr_thread = None; lines = queue.Queue(); errors = bytearray()
        job_dir = _private_directory(self.jobs_dir / job_id)
        attempt_dir = _private_directory(job_dir / ("attempt-%04d" % attempt))
        result = None; failure = None; send_cancel = False; started = time.monotonic()
        def read_stdout():
            try:
                for line in iter(process.stdout.readline, b""):
                    if len(line) > 8 * 1024 * 1024: raise ValueError("Render worker emitted oversized metadata.")
                    lines.put(line)
            finally: lines.put(None)
        def read_stderr():
            for block in iter(lambda: process.stderr.read(4096), b""):
                if len(errors) < 65536: errors.extend(block[:65536 - len(errors)])
        try:
            with self._db() as db:
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            if status == "cancelling" or self.stopping.is_set(): event.set()
            if event.is_set(): raise RuntimeError("Render cancelled before engine launch.")
            process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).with_name("scene_processing_worker.py")), "--owned-render"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            packet = {"version": VERSION, "request": request, "directory": str(attempt_dir / "render"), "lease": str(job_dir / "render.lock")}
            process.stdin.write(canonical_bytes(packet) + b"\n"); process.stdin.flush()
            stdout_thread = threading.Thread(target=read_stdout, daemon=True); stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start(); stderr_thread.start()
            eof = False; cancel_started = None
            while process.poll() is None or not eof:
                if self.stopping.is_set(): event.set()
                if time.monotonic() - started > 3600:
                    failure = "The owned render exceeded its 3600-second task bound."; event.set()
                if event.is_set() and not send_cancel:
                    try: process.stdin.write(b"cancel\n"); process.stdin.flush()
                    except (BrokenPipeError, OSError): pass
                    send_cancel = True; cancel_started = time.monotonic()
                if cancel_started and time.monotonic() - cancel_started > 20 and process.poll() is None:
                    # This handle belongs to the process created above. No saved
                    # PID is ever signalled after a restart.
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
                try: line = lines.get(timeout=.1)
                except queue.Empty:
                    if process.poll() is not None and stdout_thread and not stdout_thread.is_alive(): eof = True
                    continue
                if line is None: eof = True; continue
                message = _json_load(line)
                if not isinstance(message, dict): raise RuntimeError("Invalid worker response.")
                if "progress" in message:
                    progress = _number(message["progress"], "Render progress", 0, 1)
                    with self._db() as db: db.execute("UPDATE jobs SET progress=?,updated=? WHERE id=? AND status='running'", (min(.99, progress), time.time(), job_id))
                if "error" in message: failure = str(message["error"])[:4000]
                if "result" in message:
                    if result is not None: raise RuntimeError("The worker emitted more than one final result.")
                    result = message["result"]
            code = process.wait(timeout=5)
            if code or not result: raise RuntimeError(failure or errors.decode("utf-8", "replace")[-2000:] or "The renderer returned no completed receipt.")
            published = attempt_dir / "render" / "published"
            records = result.get("artifacts")
            if not isinstance(records, list) or len(records) not in {4, 5} or {x.get("filename") for x in records} not in (WORKER_ARTIFACTS, WORKER_ARTIFACTS - {"linear-masters.zip"}):
                raise RuntimeError("Worker result artifact inventory is incomplete.")
            if len({x["filename"] for x in records}) != len(records): raise RuntimeError("Worker artifact identities are duplicated.")
            for record in records:
                path = published / record["filename"]
                info = _regular(path)
                if info.st_size != record["size"] or info.st_size > MAX_ARTIFACT_BYTES or _hash_file(path) != record["sha256"]:
                    raise RuntimeError("Actual worker artifact failed its byte identity.")
            if result["receipt"].get("scene_sha256") != request["scene_sha256"] or result["receipt"].get("context_sha256") != request["context_sha256"]:
                raise RuntimeError("Worker completed a different scene/context.")
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                status = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
                if status == "cancelling" or event.is_set(): raise RuntimeError("Render cancelled before result publication.")
                db.execute("UPDATE jobs SET status='completed',progress=1,result=?,updated=? WHERE id=?", (canonical_bytes(result).decode(), time.time(), job_id))
        except Exception as exc:
            with self._db() as db:
                state = "interrupted" if self.stopping.is_set() else "cancelled" if event.is_set() else "failed"
                db.execute("UPDATE jobs SET status=?,error=?,result=NULL,updated=? WHERE id=?", (state, str(exc)[:4000], time.time(), job_id))
        finally:
            if process:
                if process.poll() is None:
                    try: process.stdin.close()
                    except OSError: pass
                    try: process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
                for thread in (stdout_thread, stderr_thread):
                    if thread: thread.join(timeout=2)
                for stream in (process.stdin, process.stdout, process.stderr):
                    try: stream.close()
                    except OSError: pass
            if errors:
                path = attempt_dir / "stderr.txt"
                with path.open("xb") as stream: stream.write(errors)
                os.chmod(path, 0o600)
            with self.active_lock: self.active.pop(job_id, None)
            with self.condition: self.condition.notify_all()

    def close(self):
        if self.closed: return
        self.stopping.set()
        with self.condition: self.condition.notify_all()
        if self.scheduler: self.scheduler.join(timeout=5)
        with self.active_lock: active = list(self.active.values())
        for item in active: item["cancel"].set()
        for item in active: item["thread"].join(timeout=35)
        if any(item["thread"].is_alive() for item in active): raise DispatchError("Owned render children have not settled; worker identity remains locked.")
        self.closed = True; fcntl.flock(self.lease, fcntl.LOCK_UN); os.close(self.lease)


class _RenderHandler(_Handler):
    def _dispatch(self):
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "%" in parsed.path:
            raise DispatchError("Invalid worker route.")
        worker = self.server.coordinator
        if self.command == "POST" and parsed.path == "/v1/join": return self._reply(200, worker.join(self._body()))
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[:2] != ["v1", "sessions"]: raise DispatchError("Unknown worker route.", status=404)
        session, action = parts[2], parts[3]
        auth = self.headers.get_all("Authorization", [])
        token = auth[0][7:] if len(auth) == 1 and auth[0].startswith("Bearer ") else ""
        with worker._db() as db: worker._authenticate(db, session, token)
        if self.command == "GET" and action == "jobs" and len(parts) == 5:
            return self._reply(200, worker.job(session, token, parts[4]))
        if self.command == "GET" and action == "operations" and len(parts) == 5:
            return self._reply(200, worker.operation(session, token, parts[4]))
        if self.command == "GET" and action == "artifacts" and len(parts) == 6:
            stream, record = worker.open_artifact(session, token, parts[4], parts[5])
            with stream:
                self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(record["size"])); self.send_header("X-Content-SHA256", record["sha256"])
                self.send_header("Cache-Control", "no-store"); self.send_header("Connection", "close"); self.end_headers()
                for block in iter(lambda: stream.read(CHUNK), b""): self.wfile.write(block)
            self.close_connection = True; return
        if self.command == "POST":
            body = self._body()
            if action == "jobs" and len(parts) == 4:
                _mapping(body, {"request", "operation_id"}, "Render job")
                return self._reply(200, worker.submit_job(session, token, body.get("request"), body.get("operation_id")))
            if action in {"cancel", "retry"} and len(parts) == 5 and body == {}:
                return self._reply(200, (worker.cancel_job if action == "cancel" else worker.retry_job)(session, token, parts[4]))
            if action == "invites" and len(parts) == 4:
                _mapping(body, {"expires_seconds"}, "Worker invitation")
                return self._reply(200, worker.invite(session, token, body.get("expires_seconds", 600)))
            if action == "revoke" and len(parts) == 4:
                _mapping(body, {"client_id"}, "Worker revocation")
                return self._reply(200, worker.revoke(session, token, body.get("client_id")))
        raise DispatchError("Unknown fixed worker operation.", status=404)


def start_render_worker(worker, host="127.0.0.1", port=0, advertise_host=None):
    if not isinstance(worker, RenderWorker): raise DispatchError("A scene render worker is required.")
    port = _number(port, "Worker TLS port", 0, 65535, True)
    try: address = ipaddress.ip_address(host)
    except ValueError as exc: raise DispatchError("Bind the worker to an explicit IP address.") from exc
    if address.version != 4: raise DispatchError("Worker listeners currently bind IPv4 interfaces.")
    if address.is_unspecified and not advertise_host: raise DispatchError("A peer-facing worker requires its explicit advertised hostname/address.")
    public_host = advertise_host or host
    if not isinstance(public_host, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", public_host): raise DispatchError("Worker advertised hostname is invalid.")
    key, cert, pem, fingerprint = _certificate(worker)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server = _HTTPServer((host, port), _RenderHandler); server.coordinator = worker; server.tls_context = context
    endpoint = {"url": f"https://{public_host}:{server.server_port}", "certificate_pem": pem, "certificate_sha256": fingerprint}
    worker.endpoint = endpoint
    service = RunningService(worker, server, endpoint); worker.activate()
    return service


class RenderClient(PinnedClient):
    def submit_job(self, request, operation_id):
        return self._request("POST", "jobs", {"request": validate_render_request(request), "operation_id": _operation(operation_id)})
    def job(self, job_id): return self._request("GET", "jobs/" + _job_id(job_id))
    def operation(self, operation_id): return self._request("GET", "operations/" + _operation(operation_id))["job"]
    def cancel_job(self, job_id): return self._request("POST", "cancel/" + _job_id(job_id), {})
    def retry_job(self, job_id): return self._request("POST", "retry/" + _job_id(job_id), {})
    def download_artifact(self, job_id, record, destination):
        if not isinstance(record, dict) or set(record) != {"filename", "size", "sha256"} or record["filename"] not in WORKER_ARTIFACTS:
            raise DispatchError("Invalid completed worker artifact record.")
        expected = _sha(record["sha256"]); size = _number(record["size"], "Artifact size", 1, MAX_ARTIFACT_BYTES, True)
        destination = Path(destination).absolute()
        if destination.is_symlink() or destination.exists(): raise DispatchError("Downloaded artifacts must use new owned paths.")
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (destination.parent, *destination.parent.parents)): raise DispatchError("Artifact parents cannot be symlinks.")
        connection = self._connect(); temporary = None
        try:
            connection.request("GET", "/v1/sessions/" + self.session_id + "/artifacts/" + _job_id(job_id) + "/" + record["filename"], headers=self._headers())
            response = connection.getresponse()
            if response.status != 200: return self._response(response)
            if response.getheader("X-Content-SHA256") != expected or response.getheader("Content-Length") != str(size):
                raise DispatchError("Worker artifact response identity differs from its receipt.")
            fd, filename = tempfile.mkstemp(prefix=".download-", dir=destination.parent); temporary = Path(filename)
            actual, count = hashlib.sha256(), 0
            with os.fdopen(fd, "wb") as stream:
                while True:
                    block = response.read(CHUNK)
                    if not block: break
                    count += len(block)
                    if count > size: raise DispatchError("Worker artifact exceeded its declared size.")
                    actual.update(block); stream.write(block)
                stream.flush(); os.fsync(stream.fileno())
            if count != size or actual.hexdigest() != expected: raise DispatchError("Worker artifact failed independent streamed SHA-256 verification.")
            os.link(temporary, destination); _sync_directory(destination.parent)
            return {**record, "path": str(destination)}
        finally:
            connection.close()
            if temporary: temporary.unlink(missing_ok=True)


class Dispatcher:
    def __init__(self, directory, named_bindings):
        self.root, self.dispatcher_id = _marker(directory, "CINEMATICUM_SCENE_DISPATCHER")
        if not isinstance(named_bindings, dict) or not 1 <= len(named_bindings) <= 8:
            raise DispatchError("Pair 1–8 explicitly named render workers.")
        self.clients = {_identifier(name, "Worker name"): RenderClient(binding) for name, binding in named_bindings.items()}
        identities = [(c.session_id, c.binding["client_id"]) for c in self.clients.values()]
        if len(set(identities)) != len(identities): raise DispatchError("A paired worker credential cannot be repeated under multiple names.")
        self.database = _open_private_database(self.root, "dispatch.sqlite3")
        self.batches_dir = _private_directory(self.root / "batches")
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,operation_id TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,error TEXT,output TEXT);
                CREATE TABLE IF NOT EXISTS tasks(batch_id TEXT NOT NULL,task_index INTEGER NOT NULL,task_id TEXT NOT NULL,context TEXT NOT NULL,worker_name TEXT NOT NULL,worker_identity TEXT NOT NULL,remote_id TEXT,status TEXT NOT NULL,report TEXT,PRIMARY KEY(batch_id,task_index));
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database, timeout=30); db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL"); db.execute("PRAGMA busy_timeout=30000")
        try:
            with db: yield db
        finally: db.close()

    def _identity(self, client):
        return {"worker_id": client.session_id, "client_id": client.binding["client_id"], "certificate_sha256": client.binding["certificate_sha256"]}

    def _client(self, task):
        client = self.clients.get(task["worker_name"])
        if client is None or canonical_bytes(self._identity(client)).decode() != task["worker_identity"]:
            raise DispatchError("A batch's paired worker identity changed; restore its exact private binding before resuming.", code="worker_identity_changed", status=409)
        return client

    def submit(self, graph, contexts=None, frames=None, operation_id=None):
        graph = validate_scene_graph(graph); operation_id = _operation(operation_id)
        contexts = [{}] if contexts is None else contexts
        if not isinstance(contexts, list) or not 1 <= len(contexts) <= 16: raise DispatchError("A batch requires 1–16 context variations.")
        frames = [graph["context"]["frame"]["default"]] if frames is None else frames
        if not isinstance(frames, list) or not frames or len(frames) * len(contexts) > MAX_TASKS: raise DispatchError("A batch supports 1–64 context/frame tasks.")
        normalized = []
        for context in contexts:
            if not isinstance(context, dict): raise DispatchError("A context variation must be an object.")
            if "frame" in context: raise DispatchError("Batch frame values belong in frames, not context variations.")
            for frame in frames:
                ctx = validate_context({**context, "frame": frame}, graph["context"])
                normalized.append({key: value for key, value in ctx.items() if key != "time"})
        if len({digest(ctx) for ctx in normalized}) != len(normalized): raise DispatchError("Batch context/frame tasks must be distinct.")
        tasks, shape = [], None
        worker_names = sorted(self.clients)
        for index, ctx in enumerate(normalized):
            compiled = compile_scene_graph(graph, ctx)
            request = render_request(compiled)
            task_shape = (request["scene"]["width"], request["scene"]["height"], request["context"]["fps"])
            if shape is not None and task_shape != shape: raise DispatchError("One batch preview requires a common resolution and fps across all tasks.")
            shape = task_shape; name = worker_names[index % len(worker_names)]
            tasks.append({"context": ctx, "task_id": digest({"graph": digest(graph), "context": ctx}), "worker_name": name, "worker_identity": self._identity(self.clients[name])})
        payload = {"version": VERSION, "graph": graph, "tasks": tasks}; payload_hash = digest(payload)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM batches WHERE operation_id=?", (operation_id,)).fetchone()
            if old:
                if old["payload_hash"] != payload_hash: raise DispatchError("Batch operation identity was reused for different graph/context/worker data.", code="operation_reused", status=409)
                return self.status(old["id"])
            batch_id, now = uuid.uuid4().hex, time.time()
            db.execute("INSERT INTO batches(id,operation_id,payload_hash,payload,status,created,updated) VALUES(?,?,?,?,'queued',?,?)", (batch_id, operation_id, payload_hash, canonical_bytes(payload).decode(), now, now))
            for index, task in enumerate(tasks):
                db.execute("INSERT INTO tasks(batch_id,task_index,task_id,context,worker_name,worker_identity,status) VALUES(?,?,?,?,?,?,'pending')", (batch_id, index, task["task_id"], canonical_bytes(task["context"]).decode(), task["worker_name"], canonical_bytes(task["worker_identity"]).decode()))
        return self.status(batch_id)

    def status(self, batch_id):
        with self._db() as db:
            db.execute("BEGIN")
            batch = db.execute("SELECT * FROM batches WHERE id=?", (_job_id(batch_id),)).fetchone()
            if batch is None: raise DispatchError("Owned dispatch batch does not exist.", status=404)
            tasks = db.execute("SELECT * FROM tasks WHERE batch_id=? ORDER BY task_index", (batch_id,)).fetchall()
        return {"id": batch_id, "operation_id": batch["operation_id"], "request_sha256": batch["payload_hash"], "status": batch["status"],
                "error": batch["error"], "created": batch["created"], "updated": batch["updated"], "output": batch["output"],
                "tasks": [{"index": row["task_index"], "id": row["task_id"], "context": _json_load(row["context"]),
                           "worker": row["worker_name"], "worker_identity": _json_load(row["worker_identity"]),
                           "remote_id": row["remote_id"], "status": row["status"], "report": _json_load(row["report"]) if row["report"] else None} for row in tasks]}

    def _store_task(self, batch_id, index, report):
        if not isinstance(report, dict) or report.get("status") not in {"queued", "running", "cancelling", *TERMINAL}:
            raise DispatchError("A worker returned an invalid owned job status.")
        with self._db() as db:
            db.execute("UPDATE tasks SET remote_id=?,status=?,report=? WHERE batch_id=? AND task_index=?", (_job_id(report["id"]), report["status"], canonical_bytes(report).decode(), batch_id, index))

    def _remote_submit(self, batch_id, task, graph):
        client = self._client(task)
        request = render_request(compile_scene_graph(graph, _json_load(task["context"])))
        report = client.submit_job(request, batch_id + "_" + str(task["task_index"]))
        if report.get("request_sha256") != digest(request) or report.get("worker_id") != client.session_id or report.get("client_id") != client.binding["client_id"]:
            raise DispatchError("Worker job is bound to a different request or participant.")
        self._store_task(batch_id, task["task_index"], report)
        return report

    def cancel(self, batch_id):
        with self._db() as db:
            row = db.execute("SELECT status FROM batches WHERE id=?", (_job_id(batch_id),)).fetchone()
            if row is None: raise DispatchError("Unknown owned batch.", status=404)
            if row["status"] == "completed": return self.status(batch_id)
            db.execute("UPDATE batches SET status='cancelling',updated=? WHERE id=?", (time.time(), batch_id))
            tasks = db.execute("SELECT * FROM tasks WHERE batch_id=?", (batch_id,)).fetchall()
        unsettled = []
        for task in tasks:
            try:
                client = self._client(task)
                report = client.job(task["remote_id"]) if task["remote_id"] else client.operation(batch_id + "_" + str(task["task_index"]))
                if report is not None:
                    if report["status"] not in TERMINAL: report = client.cancel_job(report["id"])
                    self._store_task(batch_id, task["task_index"], report)
            except Exception: unsettled.append(task["task_index"])
        if unsettled: raise DispatchError("Cancellation was requested but these paired workers could not yet confirm it.", code="cancellation_unsettled", status=409, tasks=unsettled)
        return self.status(batch_id)

    def retry(self, batch_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM batches WHERE id=?", (_job_id(batch_id),)).fetchone()
            if row is None: raise DispatchError("Unknown owned batch.", status=404)
            if row["status"] in {"running", "cancelling"}: raise DispatchError("Settle the current batch attempt before retrying.", status=409)
            tasks = db.execute("SELECT * FROM tasks WHERE batch_id=? ORDER BY task_index", (batch_id,)).fetchall()
        for task in tasks:
            if task["remote_id"] and task["status"] in {"failed", "cancelled", "interrupted"}:
                self._store_task(batch_id, task["task_index"], self._client(task).retry_job(task["remote_id"]))
        with self._db() as db: db.execute("UPDATE batches SET status='queued',error=NULL,updated=? WHERE id=? AND status!='completed'", (time.time(), batch_id))
        return self.status(batch_id)

    def run(self, batch_id, output_dir, progress=None, cancel_event=None):
        """Resume durable task identities; retain actual downloads after a crash."""
        batch_id = _job_id(batch_id); progress = progress or (lambda value: None)
        root = _private_directory(self.batches_dir / batch_id)
        lock = os.open(root / "dispatch.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lock); raise DispatchError("This owned batch is already being collected.", status=409)
        output = Path(output_dir).absolute()
        try:
            with self._db() as db:
                row = db.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
                if row is None: raise DispatchError("Unknown owned batch.", status=404)
                payload = _json_load(row["payload"])
                if digest(payload) != row["payload_hash"]: raise DispatchError("Stored batch identity is corrupt.")
                if row["status"] == "completed":
                    if str(output) != row["output"]: raise DispatchError("Completed batch already has a different immutable output location.")
                    return self._verified_result(output)
                if row["status"] in {"failed", "cancelled", "interrupted"}: raise DispatchError("Explicitly retry this settled batch before rendering again.", status=409)
                tasks = db.execute("SELECT * FROM tasks WHERE batch_id=? ORDER BY task_index", (batch_id,)).fetchall()
            if output.exists() or output.is_symlink():
                # Publication can precede the SQLite completion commit during a
                # crash. Reconcile only a byte-verified receipt for this batch.
                result = self._verified_result(output)
                if result["receipt"].get("batch_id") != batch_id or result["receipt"].get("request_sha256") != row["payload_hash"]:
                    raise DispatchError("Existing output belongs to different work.")
                with self._db() as db: db.execute("UPDATE batches SET status='completed',output=?,updated=? WHERE id=?", (str(output), time.time(), batch_id))
                return result
            for task in tasks: self._client(task)
            with self._db() as db: db.execute("UPDATE batches SET status='running',updated=? WHERE id=? AND status!='cancelling'", (time.time(), batch_id))
            cancelling = row["status"] == "cancelling" or bool(cancel_event and cancel_event.is_set())
            if not cancelling:
                with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
                    futures = [pool.submit(self._remote_submit, batch_id, task, payload["graph"]) for task in tasks]
                    for future in futures: future.result()
            else:
                # Recover lost replies by read-only operation lookup. A cancel
                # must neither manufacture new jobs nor leave accepted but
                # locally unrecorded jobs running under a false settled state.
                for task in tasks:
                    if not task["remote_id"]:
                        recovered = self._client(task).operation(batch_id + "_" + str(task["task_index"]))
                        if recovered is not None: self._store_task(batch_id, task["task_index"], recovered)
            started_cancel = None
            while True:
                with self._db() as db:
                    state = db.execute("SELECT status FROM batches WHERE id=?", (batch_id,)).fetchone()[0]
                    tasks = db.execute("SELECT * FROM tasks WHERE batch_id=? ORDER BY task_index", (batch_id,)).fetchall()
                cancelling = cancelling or state == "cancelling" or bool(cancel_event and cancel_event.is_set())
                if cancelling and started_cancel is None:
                    started_cancel = time.monotonic(); self.cancel(batch_id)
                reports = []
                for task in tasks:
                    if task["remote_id"]:
                        report = self._client(task).job(task["remote_id"])
                        self._store_task(batch_id, task["task_index"], report); reports.append(report)
                    elif not cancelling: raise DispatchError("A submitted task has no durable remote identity.")
                amount = sum(1 if r["status"] == "completed" else min(.99, r.get("progress", 0)) for r in reports) / len(tasks)
                progress(.05 + .8 * amount)
                if cancelling:
                    if all(r["status"] in TERMINAL for r in reports):
                        with self._db() as db: db.execute("UPDATE batches SET status='cancelled',error='Cancelled before final publication.',updated=? WHERE id=?", (time.time(), batch_id))
                        raise DispatchError("Distributed render cancelled; owned remote jobs settled.", code="cancelled")
                    if time.monotonic() - started_cancel > 40: raise DispatchError("Owned cancellation is still settling on paired workers.", code="cancellation_unsettled", status=409)
                elif any(r["status"] in {"failed", "interrupted", "cancelled"} for r in reports):
                    raise DispatchError("One or more real worker tasks failed or were interrupted; inspect task receipts and retry explicitly.", code="worker_task_failed", status=409)
                elif all(r["status"] == "completed" for r in reports): break
                time.sleep(.1)
            with self._db() as db: tasks = db.execute("SELECT * FROM tasks WHERE batch_id=? ORDER BY task_index", (batch_id,)).fetchall()
            result = self._collect(batch_id, row["payload_hash"], payload["graph"], tasks, root, output, progress, cancel_event)
            with self._db() as db: db.execute("UPDATE batches SET status='completed',output=?,updated=?,error=NULL WHERE id=?", (str(output), time.time(), batch_id))
            return result
        except Exception as exc:
            with self._db() as db:
                state = db.execute("SELECT status FROM batches WHERE id=?", (batch_id,)).fetchone()
                if state and state[0] not in {"completed", "cancelled", "cancelling"}:
                    db.execute("UPDATE batches SET status='interrupted',error=?,updated=? WHERE id=?", (str(exc)[:4000], time.time(), batch_id))
            raise
        finally: fcntl.flock(lock, fcntl.LOCK_UN); os.close(lock)

    def _verified_result(self, output):
        if output.is_symlink() or not output.is_dir(): raise DispatchError("Published dispatch output is invalid.")
        path = output / "receipt.json"; _regular(path)
        receipt = _json_load(path.read_bytes())
        for record in receipt.get("artifacts", []):
            from scene_processing import ARTIFACT_NAMES
            if not isinstance(record, dict) or record.get("filename") not in ARTIFACT_NAMES - {"receipt.json"}: raise DispatchError("Invalid dispatch output inventory.")
            candidate = output / record["filename"]; info = _regular(candidate)
            if info.st_size != record["size"] or _hash_file(candidate) != record["sha256"]: raise DispatchError("Published dispatch artifact is corrupt.")
        if {x["filename"] for x in receipt.get("artifacts", [])} != {"graph.json", "dispatch.json", "tasks.zip", "preview.mp4"}:
            raise DispatchError("Published dispatch inventory is incomplete.")
        return {"operation": "dispatch", "receipt": receipt, "path": str(output / "preview.mp4"), "issuance_effect": "NONE"}

    def _collect(self, batch_id, request_hash, graph, tasks, root, output, progress, cancel_event):
        downloaded = []
        for index, task in enumerate(tasks):
            _cancelled(cancel_event)
            report = _json_load(task["report"]); client = self._client(task)
            result = report.get("result")
            if not result or result["receipt"].get("graph_sha256") != digest(graph): raise DispatchError("Worker result is not bound to this graph.")
            context = validate_context(_json_load(task["context"]), graph["context"])
            if result["receipt"].get("context_sha256") != digest(context): raise DispatchError("Worker result context differs from its task.")
            target = _private_directory(root / ("task-%04d" % index))
            for record in result["artifacts"]:
                filename = record.get("filename")
                if filename not in WORKER_ARTIFACTS: raise DispatchError("Unknown worker artifact in result.")
                path = target / filename
                if path.exists() or path.is_symlink():
                    info = _regular(path)
                    if info.st_size != record["size"] or _hash_file(path) != record["sha256"]: raise DispatchError("Previously collected worker bytes are corrupt; they were not overwritten.")
                else: client.download_artifact(report["id"], record, path)
            actual_receipt = _json_load((target / "receipt.json").read_bytes())
            if canonical_bytes(actual_receipt) != canonical_bytes(result["receipt"]): raise DispatchError("Downloaded receipt differs from the authenticated job response.")
            downloaded.append({"index": index, "task_id": task["task_id"], "context": context, "worker": task["worker_name"],
                               "worker_identity": _json_load(task["worker_identity"]), "remote_job": report["id"],
                               "remote_attempt": report["attempt"], "artifacts": result["artifacts"]})
            progress(.85 + .08 * (index + 1) / len(tasks))
        output.parent.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (output.parent, *output.parent.parents)): raise DispatchError("Dispatch output parents cannot be symlinks.")
        with tempfile.TemporaryDirectory(prefix=".dispatch-publish-", dir=output.parent) as temporary:
            staged = Path(temporary) / "published"; staged.mkdir()
            _write_json(staged / "graph.json", graph)
            manifest = {"format": "CINEMATICUM_DISTRIBUTED_SCENE_BATCH", "version": VERSION, "batch_id": batch_id,
                        "request_sha256": request_hash, "graph_sha256": digest(graph), "tasks": downloaded,
                        "presentation": "Context-major, then requested frame order; one decoded frame per task.", "issuance_effect": "NONE"}
            _write_json(staged / "dispatch.json", manifest)
            with zipfile.ZipFile(staged / "tasks.zip", "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for task in downloaded:
                    for record in task["artifacts"]:
                        _cancelled(cancel_event)
                        path = root / ("task-%04d" % task["index"]) / record["filename"]
                        archive.write(path, "task-%04d/" % task["index"] + record["filename"])
                archive.writestr("manifest.json", canonical_bytes(manifest))
            fps = downloaded[0]["context"]["fps"]
            # Paths are generated private names. Reset decoded timestamps to an
            # exact frame grid, avoiding one-frame MP4 duration quantization.
            listing = Path(temporary) / "frames.txt"
            listing.write_text("".join("file '" + str(root / ("task-%04d" % item["index"]) / "preview.mp4").replace("'", "'\\''") + "'\n" for item in downloaded), encoding="utf-8")
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg: raise DispatchError("FFmpeg is required to assemble actual worker frames.")
            command = [ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                       "-vf", f"setpts=N/({fps}*TB)", "-r", str(fps), "-frames:v", str(len(tasks)), "-an", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(staged / "preview.mp4")]
            _run_owned(command, Path(temporary) / "assembly.log", cancel_event, 120)
            _cancelled(cancel_event)
            receipt = {"format": "CINEMATICUM_SCENE_PROCESSING", "version": VERSION, "operation": "dispatch", "batch_id": batch_id,
                       "request_sha256": request_hash, "graph_sha256": digest(graph), "task_count": len(tasks),
                       "worker_count": len({item["worker_identity"]["worker_id"] for item in downloaded}),
                       "artifacts": _artifact_inventory(staged), "issuance_effect": "NONE"}
            _write_json(staged / "receipt.json", receipt); _cancelled(cancel_event)
            _publish_directory(staged, output)
        progress(1)
        return self._verified_result(output)

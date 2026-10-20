#!/usr/bin/env python3
"""Loopback-only CINEMATICUM editor, asset store, and asynchronous render jobs.

Only imported media are exposed. There is no HTTP shell or arbitrary path reader.
All mutating requests require a per-process token and an accepted browser origin.
"""
from __future__ import annotations

import argparse
import copy
import errno
import fcntl
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
import uuid
import webbrowser

from engine import probe_media, validate_project, render_project, MEDIA_EXTENSIONS
from adapters import AdapterError, check_comfyui, find_blender, generate_comfyui, render_blender, validate_workflow
from generation_readiness import workflow_readiness
from scene import validate_scene, render_scene

VERSION = "0.2.0"
MAX_UPLOAD = 8 * 1024 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
MEDIA_SUFFIXES = MEDIA_EXTENSIONS | {".blend"}
WEB = Path(__file__).resolve().parent / "web"
REPOSITORY = Path(__file__).resolve().parents[2]


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent), delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(str(tmp), str(path))
    finally:
        tmp.unlink(missing_ok=True)


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name):
    value = Path(str(name).replace("\\", "/")).name
    value = "".join(c for c in value if ord(c) >= 32 and c != "\x7f")[:180]
    return value or "untitled"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return copy.deepcopy(default)
        raise


def default_workspace():
    if sys.platform == "darwin":
        return Path.home() / "Movies" / "CINEMATICUM"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "cinematicum"


class WorkspaceInUseError(RuntimeError):
    """Another process owns this workspace and its durable job state."""


class Store:
    def __init__(self, root, comfy_url="http://127.0.0.1:8188"):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._shutdown_lock = threading.Lock()
        self._closing = False
        self._closed = False
        self._workspace_lock_fd = None
        self.pool = None
        self._acquire_workspace_lock()
        try:
            # Recovery may rewrite queued/running jobs, so it must follow the
            # process-wide lock, never merely the in-process threading.RLock.
            (self.root / "projects").mkdir(exist_ok=True)
            (self.root / "jobs").mkdir(exist_ok=True)
            self.token = secrets.token_urlsafe(32)
            self.comfy_url = comfy_url.rstrip("/")
            self.jobs = {}
            self.events = {}
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cinematicum-render")
            self._cap_cache = None
            self._cap_time = 0
            for path in (self.root / "jobs").glob("*.json"):
                try:
                    job = read_json(path)
                    if job.get("state") in {"queued", "running"}:
                        job.update(state="interrupted", error="The application stopped before this job completed. Start a new render.")
                        atomic_json(path, job)
                    self.jobs[job["id"]] = job
                except (ValueError, KeyError, OSError):
                    continue
        except BaseException:
            if self.pool is not None:
                self.pool.shutdown(wait=True, cancel_futures=True)
            self._release_workspace_lock()
            raise

    def _acquire_workspace_lock(self):
        # Keep this inode permanently. Unlinking a lock file can let a new
        # process lock a different inode while the previous owner still runs.
        path = self.root / ".cinematicum-workspace.lock"
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags, 0o600)
        try:
            os.set_inheritable(fd, False)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise WorkspaceInUseError(
                        f"Workspace is already in use by another CINEMATICUM process: {self.root}. "
                        "Quit that instance before opening this workspace, or choose a different --workspace folder."
                    ) from None
                raise
            os.ftruncate(fd, 0)
            os.write(fd, (json.dumps({"pid": os.getpid(), "started_at": time.time()}) + "\n").encode("utf-8"))
            self._workspace_lock_fd = fd
        except BaseException:
            os.close(fd)
            raise

    def _release_workspace_lock(self):
        fd = self._workspace_lock_fd
        if fd is not None:
            self._workspace_lock_fd = None
            os.close(fd)  # Closing releases flock; a process crash does too.

    def _require_open(self):
        if self._closing or self._closed:
            raise RuntimeError("CINEMATICUM workspace is shutting down or closed.")

    def project_dir(self, project_id):
        self._require_open()
        if not isinstance(project_id, str) or not IDENTIFIER.fullmatch(project_id):
            raise ValueError("Invalid project ID")
        directory = self.root / "projects" / project_id
        if directory.is_symlink() or not directory.is_dir():
            raise FileNotFoundError("Project does not exist")
        return directory

    def projects(self):
        result = []
        for path in (self.root / "projects").glob("*/project.json"):
            if path.parent.is_symlink():
                continue
            try:
                p = read_json(path)
                result.append({k: p.get(k) for k in ("id", "name", "fps", "width", "height", "updated_at")})
            except (ValueError, OSError):
                continue
        return sorted(result, key=lambda p: p.get("updated_at") or "", reverse=True)

    def new_project(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Project properties must be an object")
        with self.lock:
            self._require_open()
            project_id = uuid.uuid4().hex
            directory = self.root / "projects" / project_id
            directory.mkdir()
            (directory / "media").mkdir()
            (directory / "exports").mkdir()
            project = {"version": 1, "id": project_id, "name": str(payload.get("name", "Untitled film"))[:160].strip() or "Untitled film", "fps": payload.get("fps", 24), "width": payload.get("width", 1280), "height": payload.get("height", 720), "assets": [], "clips": [], "titles": [], "settings": {}, "revision": 0}
            try:
                validate_project(project, directory)
                atomic_json(directory / "assets.json", [])
                return self.save(project_id, project, creating=True)
            except Exception:
                shutil.rmtree(directory)
                raise

    def get(self, project_id):
        with self.lock:
            directory = self.project_dir(project_id)
            project = read_json(directory / "project.json")
            project["assets"] = read_json(directory / "assets.json", [])
            return project

    def save(self, project_id, project, creating=False):
        if not isinstance(project, dict):
            raise ValueError("Project must be an object")
        with self.lock:
            directory = self.project_dir(project_id)
            p = copy.deepcopy(project)
            p["id"] = project_id
            p["version"] = 1
            p["name"] = str(p.get("name", "Untitled film"))[:160]
            p["assets"] = read_json(directory / "assets.json", [])
            current = read_json(directory / "project.json", {})
            # Imports do not alter timeline revisions. Two editors cannot silently overwrite edits.
            if not creating and p.get("revision") != current.get("revision"):
                raise ConflictError("Project was changed in another window. Reopen it before saving.")
            normalized = validate_project(p, directory)
            if isinstance(normalized, dict):
                p = normalized
            if not isinstance(p.get("settings", {}), dict):
                raise ValueError("Project settings must be an object")
            p.setdefault("settings", {})
            if p["settings"].get("scene") is not None:
                p["settings"]["scene"] = validate_scene(p["settings"]["scene"], width=p["width"], height=p["height"])
            p["revision"] = current.get("revision", 0) + 1
            p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            atomic_json(directory / "project.json", p)
            return p

    def asset(self, project_id, asset_id):
        p = self.get(project_id)
        asset = next((a for a in p["assets"] if a["id"] == asset_id), None)
        if not asset:
            raise FileNotFoundError("Asset does not exist")
        root = self.project_dir(project_id)
        path = (root / asset["path"]).resolve()
        if not path.is_file() or not path.is_relative_to((root / "media").resolve()):
            raise ValueError("Asset path is outside imported media")
        return asset, path

    def admit(self, project_id, file_path, name, provenance=None):
        directory = self.project_dir(project_id)
        incoming = Path(file_path)
        suffix = Path(name).suffix.lower()
        if suffix not in MEDIA_SUFFIXES:
            raise ValueError("Unsupported file. Import video, audio, an image, or a Blender scene.")
        if not incoming.is_file() or incoming.stat().st_size == 0:
            raise ValueError("Imported file is empty")
        if suffix == ".blend":
            with incoming.open("rb") as f:
                magic = f.read(7)
            if magic not in {b"BLENDER", b"\x1f\x8b\x08\x00\x00\x00\x00"} and not magic.startswith((b"\x1f\x8b", b"\x28\xb5\x2f\xfd")):
                raise ValueError("File is not a Blender scene")
            meta = {"kind": "scene", "duration": 0, "width": 0, "height": 0, "has_audio": False}
        else:
            meta = probe_media(incoming)
        asset_id = uuid.uuid4().hex
        target = directory / "media" / (asset_id + suffix)
        asset = {"id": asset_id, "name": safe_name(name), "path": "media/" + target.name, "sha256": digest_file(incoming), "size": incoming.stat().st_size, **meta}
        if provenance:
            asset["provenance"] = provenance
        with self.lock:
            self._require_open()
            assets = read_json(directory / "assets.json", [])
            # Duplicate imports, including unchanged title plates, reuse immutable media.
            duplicate = next((a for a in assets if a.get("sha256") == asset["sha256"] and a.get("kind") == asset["kind"]), None)
            if duplicate is not None:
                incoming.unlink(missing_ok=True)
                return duplicate
            if len(assets) >= 512:
                raise ValueError("This project already contains the maximum of 512 imported assets. Create another project.")
            shutil.move(str(incoming), str(target))
            assets.append(asset)
            atomic_json(directory / "assets.json", assets)
            project = read_json(directory / "project.json")
            project["assets"] = assets
            atomic_json(directory / "project.json", project)
        return asset

    def capabilities(self, fresh=False):
        if self._cap_cache is not None and not fresh and time.monotonic() - self._cap_time < 15:
            return copy.deepcopy(self._cap_cache)
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        filters = ""
        encoders = ""
        if ffmpeg:
            try:
                filters = subprocess.check_output([ffmpeg, "-hide_banner", "-filters"], stderr=subprocess.DEVNULL, timeout=5, text=True)
                encoders = subprocess.check_output([ffmpeg, "-hide_banner", "-encoders"], stderr=subprocess.DEVNULL, timeout=5, text=True)
            except (OSError, subprocess.SubprocessError):
                pass
        result = {"version": VERSION, "ffmpeg": bool(ffmpeg and ffprobe), "blender": bool(find_blender()), "comfyui": check_comfyui(self.comfy_url), "titles": "overlay" in filters, "raster_titles": "overlay" in filters, "drawtext": "drawtext" in filters, "h264": "libx264" in encoders, "prores": "prores_ks" in encoders, "workspace": str(self.root), "color_space": "SDR Rec.709", "commercial_providers": "No paid provider is configured in this build."}
        result["scene_authoring"] = result["blender"] and result["ffmpeg"]
        result["node_compositor"] = all(name in filters for name in ("geq", "overlay", "split", "gblur"))
        self._cap_cache, self._cap_time = copy.deepcopy(result), time.monotonic()
        return result

    def _write_job(self, job):
        atomic_json(self.root / "jobs" / (job["id"] + ".json"), job)

    def submit(self, project_id, kind, fn, snapshot=None):
        with self.lock:
            self._require_open()
            active = sum(j["state"] in {"queued", "running"} for j in self.jobs.values())
            if active >= 8:
                raise ValueError("Render queue is full. Wait for or cancel a queued job.")
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "project_id": project_id, "kind": kind, "state": "queued", "progress": 0, "created_at": time.time(), "error": None, "result": None}
            event = threading.Event()
            self.jobs[job_id] = job
            self.events[job_id] = event
            self._write_job(job)
            if snapshot is not None:
                atomic_json(self.root / "jobs" / (job_id + ".snapshot"), snapshot)

        def execute():
            if event.is_set():
                with self.lock:
                    job.update(state="cancelled", error="Job cancelled before starting", finished_at=time.time())
                    self.events.pop(job_id, None)
                    self._write_job(job)
                return
            with self.lock:
                job["state"] = "running"
                self._write_job(job)
            last_write = [0.0]

            def progress(value):
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    return
                with self.lock:
                    job["progress"] = min(0.999, max(0.0, float(value)))
                    if time.monotonic() - last_write[0] > 1:
                        self._write_job(job)
                        last_write[0] = time.monotonic()
            try:
                result = fn(job_id, progress, event)
                with self.lock:
                    # A successful worker return commits its published result.
                    # Workers must raise on cooperative cancellation before that
                    # commit. A late request must not hide already published
                    # media/source files or discard their successful result.
                    job.update(state="completed", progress=1, result=result, error=None)
            except Exception as exc:
                with self.lock:
                    job.update(state="cancelled" if event.is_set() else "failed", error=str(exc)[-6000:])
            finally:
                with self.lock:
                    job["finished_at"] = time.time()
                    self._write_job(job)
                    self.events.pop(job_id, None)
        self.pool.submit(execute)
        return copy.deepcopy(job)

    def job(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise FileNotFoundError("Job does not exist")
            return copy.deepcopy(self.jobs[job_id])

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise FileNotFoundError("Job does not exist")
            if job_id in self.events:
                self.events[job_id].set()
                if job["state"] == "queued":
                    job.update(state="cancelled", error="Job cancelled before starting", finished_at=time.time())
                    self.events.pop(job_id, None)
                    self._write_job(job)
            return copy.deepcopy(job)

    def render(self, project_id, payload):
        profile = payload.get("profile", "h264")
        if profile not in {"preview", "h264", "prores"}:
            raise ValueError("Unknown export profile")
        project = payload.get("project", self.get(project_id))
        p = copy.deepcopy(project)
        p["id"] = project_id
        p["assets"] = self.get(project_id)["assets"]
        directory = self.project_dir(project_id)
        normalized = validate_project(p, directory)
        if isinstance(normalized, dict):
            p = normalized
        if not p.get("clips") and not p.get("titles"):
            raise ValueError("Add media to the timeline before rendering")
        snapshot = copy.deepcopy(p)

        def work(job_id, progress, event):
            suffix = ".mov" if profile == "prores" else ".mp4"
            output = directory / "exports" / (job_id + suffix)
            report = render_project(snapshot, directory, output, profile=profile, progress=progress, cancel_event=event)
            if event.is_set():
                output.unlink(missing_ok=True)
                raise RuntimeError("Job cancelled")
            result = dict(report or {})
            result.update(url=f"/api/projects/{project_id}/exports/{output.name}", filename=output.name, project_revision=snapshot.get("revision"), profile=profile, sha256=digest_file(output))
            atomic_json(directory / "exports" / (job_id + ".json"), {"result": result, "snapshot": snapshot, "issuance_effect": "NONE"})
            return result
        return self.submit(project_id, "render", work, snapshot)

    def generation(self, project_id, payload):
        directory = self.project_dir(project_id)
        raw = str(payload.get("workflow_path", "workflow.json"))
        if raw != "workflow.json":
            raise ValueError("Import a ComfyUI API workflow into this project first")
        workflow = validate_workflow(read_json(directory / "workflow.json"))
        prompt = str(payload.get("prompt", "")).strip()
        negative = str(payload.get("negative", ""))
        seed = payload.get("seed", 0)
        if not prompt or len(prompt) > 32000 or len(negative) > 32000:
            raise ValueError("A prompt of 1–32000 characters is required")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**53:
            raise ValueError("Seed must be an integer from 0 to 9007199254740991")
        readiness = workflow_readiness(self.comfy_url, workflow)
        if not readiness["ready"]:
            raise ValueError("Generation preflight failed: " + " ".join(readiness["errors"][:5]))

        def work(job_id, progress, event):
            with tempfile.TemporaryDirectory(prefix="generation-", dir=str(directory)) as scratch:
                result = generate_comfyui(self.comfy_url, workflow, prompt, negative, seed, Path(scratch), progress=progress, cancel_event=event)
                if event.is_set():
                    raise RuntimeError("Generation cancelled locally")
                asset = self.admit(project_id, result["path"], "Generated take" + Path(result["path"]).suffix, result.get("provenance"))
                return {"asset": asset, "url": f"/api/projects/{project_id}/media/{asset['id']}"}
        return self.submit(project_id, "generate", work, {"prompt": prompt, "negative": negative, "seed": seed, "workflow": workflow})

    def generation_readiness(self, project_id):
        directory = self.project_dir(project_id)
        path = directory / "workflow.json"
        return workflow_readiness(self.comfy_url, read_json(path) if path.is_file() else None)

    def scene_render(self, project_id, payload):
        """Render a bounded editable scene recipe and preserve its Blender source."""
        project = self.get(project_id)
        recipe = validate_scene(payload.get("scene", project.get("settings", {}).get("scene")),
                                width=project["width"], height=project["height"])
        if not recipe["objects"]:
            raise ValueError("Add at least one object before rendering the 3D scene")
        start = payload.get("frame_start", 1)
        end = payload.get("frame_end", recipe["frame_end"])
        if (any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end))
                or not 1 <= start <= end <= recipe["frame_end"]):
            raise ValueError("Scene render frames must be within the scene's frame range (1–7200)")
        if not find_blender():
            raise ValueError("Blender is required to render a scene")
        directory = self.project_dir(project_id)
        snapshot = {"scene": recipe, "frame_start": start, "frame_end": end,
                    "fps": project["fps"], "project_revision": project["revision"]}

        def work(job_id, progress, event):
            source = directory / "exports" / (job_id + ".blend")
            manifest = directory / "exports" / (job_id + ".json")
            source_published = False
            try:
                with tempfile.TemporaryDirectory(prefix="scene-", dir=str(directory)) as scratch:
                    result = render_scene(recipe, Path(scratch), fps=project["fps"],
                                          frame_start=start, frame_end=end, progress=progress, cancel_event=event)
                    if event.is_set():
                        raise RuntimeError("Scene render cancelled")
                    generated_source = Path(result["scene_path"])
                    if not generated_source.is_file() or generated_source.stat().st_size == 0:
                        raise RuntimeError("Scene renderer did not preserve its Blender source")
                    os.replace(str(generated_source), str(source))
                    asset = self.admit(project_id, result["path"], recipe.get("name", "Scene") + " render.mp4", result.get("provenance"))
                    source_published = True
                    report = {"asset": asset, "url": f"/api/projects/{project_id}/media/{asset['id']}",
                              "scene_url": f"/api/projects/{project_id}/exports/{source.name}",
                              "scene_filename": source.name, "scene_sha256": digest_file(source),
                              "project_revision": project["revision"]}
                    atomic_json(manifest, {"result": report, "snapshot": snapshot, "issuance_effect": "NONE"})
                    return report
            finally:
                if not source_published:
                    source.unlink(missing_ok=True)
                    manifest.unlink(missing_ok=True)
        return self.submit(project_id, "scene", work, snapshot)

    def blender(self, project_id, payload):
        p = self.get(project_id)
        scene = next((a for a in p["assets"] if a["kind"] == "scene" and (a["path"] == payload.get("scene_path") or a["id"] == payload.get("scene_path"))), None)
        if not scene:
            raise ValueError("Import and select a Blender .blend scene first")
        _, path = self.asset(project_id, scene["id"])
        start, end = payload.get("frame_start", 1), payload.get("frame_end", 48)
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)) or not 1 <= start <= end <= 100000 or end - start > 10000:
            raise ValueError("Blender frame range must contain 1–10001 frames, starting at frame 1 or later")
        if not find_blender():
            raise ValueError("Blender is not installed")
        directory = self.project_dir(project_id)

        def work(job_id, progress, event):
            with tempfile.TemporaryDirectory(prefix="blender-", dir=str(directory)) as scratch:
                result = render_blender(path, Path(scratch), start, end, fps=p["fps"], progress=progress, cancel_event=event)
                if event.is_set():
                    raise RuntimeError("Blender render cancelled")
                asset = self.admit(project_id, result["path"], Path(scene["name"]).stem + " render.mp4", result.get("provenance"))
                return {"asset": asset, "url": f"/api/projects/{project_id}/media/{asset['id']}"}
        return self.submit(project_id, "blender", work, {"scene": scene, "frame_start": start, "frame_end": end, "fps": p["fps"]})

    def automate(self, project_id, payload):
        """Atomic typed editing recipes. No eval, shell, network, or implied LLM."""
        project = copy.deepcopy(payload.get("project") or self.get(project_id))
        operations = payload.get("operations")
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise ValueError("Supply between 1 and 100 editing operations")
        for op in operations:
            if not isinstance(op, dict):
                raise ValueError("Each operation must be an object")
            ids = op.get("clip_ids")
            clips = project["clips"] if ids is None else [c for c in project["clips"] if c["id"] in ids]
            action = op.get("action")
            if action == "grade":
                values = op.get("values", {})
                if not isinstance(values, dict) or not set(values) <= {"exposure", "contrast", "saturation", "temperature"}:
                    raise ValueError("Unknown grade setting")
                for clip in clips:
                    clip.setdefault("grade", {}).update(values)
            elif action == "volume":
                for clip in clips:
                    clip["volume"] = op.get("value")
            elif action == "sequence":
                position = op.get("start", 0)
                for clip in sorted(clips, key=lambda c: c["start"]):
                    clip["start"], clip["track"] = position, op.get("track", 0)
                    position += clip["duration"]
            elif action == "trim":
                for clip in clips:
                    for key in ("in", "duration"):
                        if key in op:
                            clip[key] = op[key]
            else:
                raise ValueError("Supported automation actions: grade, volume, sequence, trim")
        return self.save(project_id, project)

    def shutdown(self):
        # Concurrent/repeated shutdown calls cannot release another caller's
        # lock early while a render subprocess is still finishing.
        with self._shutdown_lock:
            if self._closed:
                return
            with self.lock:
                self._closing = True
                for event in self.events.values():
                    event.set()
            self.pool.shutdown(wait=True, cancel_futures=True)
            with self.lock:
                self._closed = True
                self._release_workspace_lock()


class ConflictError(ValueError):
    pass


class Handler(BaseHTTPRequestHandler):
    server_version = "CINEMATICUM/" + VERSION
    protocol_version = "HTTP/1.0"

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # Closing the native window may abandon a media request.
            return

    @property
    def store(self):
        return self.server.store

    def log_message(self, fmt, *args):
        # Never log upload names, prompts, request bodies, or authentication values.
        if str(args[1] if len(args) > 1 else "").startswith("5"):
            sys.stderr.write("CINEMATICUM request failed\n")

    def guard(self, mutate=False):
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in hosts:
            raise PermissionError("Invalid Host header")
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + h for h in hosts}:
            raise PermissionError("Cross-origin requests are not allowed")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise PermissionError("Cross-site requests are not allowed")
        if mutate and not secrets.compare_digest(self.headers.get("X-Cinematicum-Token", ""), self.store.token):
            raise PermissionError("Application token is missing or expired. Reload the editor.")

    def headers_common(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def json(self, status, body):
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.headers_common()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def length(self, limit):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked request bodies are unsupported; supply Content-Length")
        raw = self.headers.get("Content-Length", "0")
        if not raw.isdigit() or not 0 < int(raw) <= limit:
            raise ValueError("Request is empty or exceeds the size limit")
        return int(raw)

    def body(self):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Expected application/json")
        length = self.length(MAX_JSON)
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("Incomplete request body")
        return json.loads(data, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))

    def file(self, path, download=False):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError("File is missing")
        size = path.stat().st_size
        start, end = 0, size - 1
        partial = False
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            try:
                if not match or not any(match.groups()):
                    raise ValueError()
                a, b = match.groups()
                if not a:
                    start, end = max(0, size - int(b)), size - 1
                else:
                    start, end = int(a), min(size - 1, int(b) if b else size - 1)
                if not 0 <= start <= end < size:
                    raise ValueError()
                partial = True
            except (ValueError, TypeError):
                self.send_response(416)
                self.headers_common()
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = max(0, end - start + 1)
        self.send_response(206 if partial else 200)
        self.headers_common()
        types = {".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".mov": "video/quicktime"}
        self.send_header("Content-Type", types.get(path.suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream"))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as f:
            f.seek(start)
            while length:
                data = f.read(min(1024 * 1024, length))
                if not data:
                    break
                self.wfile.write(data)
                length -= len(data)

    def thumbnail(self, project_id, asset_id):
        asset, path = self.store.asset(project_id, asset_id)
        if asset["kind"] not in {"video", "image"}:
            raise FileNotFoundError("This asset has no picture thumbnail")
        directory = self.store.project_dir(project_id) / "thumbnails"
        directory.mkdir(exist_ok=True)
        dest = directory / (asset_id + ".jpg")
        if not dest.exists():
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise ValueError("FFmpeg is required for thumbnails")
            with tempfile.NamedTemporaryFile(suffix=".jpg", dir=str(directory), delete=False) as f:
                tmp = Path(f.name)
            try:
                subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-y", "-threads", "1", "-i", str(path), "-frames:v", "1", "-vf", "scale=320:180:force_original_aspect_ratio=decrease", "-threads", "1", str(tmp)], check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                os.replace(str(tmp), str(dest))
            finally:
                tmp.unlink(missing_ok=True)
        self.file(dest)

    def dispatch_get(self):
        parsed = urlparse(self.path)
        parts = unquote(parsed.path).strip("/").split("/")
        if parsed.path in {"/", "/index.html", "/app.js", "/style.css", "/compositor-ui.js", "/scene-editor.js", "/scene-editor.css"}:
            return self.file(WEB / ("index.html" if parsed.path == "/" else parsed.path[1:]))
        if parts == ["api", "bootstrap"]:
            projects = self.store.projects()
            p = self.store.get(projects[0]["id"]) if projects else self.store.new_project({"name": "Untitled film"})
            return self.json(200, {"token": self.store.token, "project": p, "projects": self.store.projects(), "capabilities": self.store.capabilities(), "jobs": sorted(self.store.jobs.values(), key=lambda j: j["created_at"], reverse=True)[:30]})
        if parts == ["api", "capabilities"]:
            return self.json(200, self.store.capabilities(fresh=True))
        if parts == ["api", "projects"]:
            return self.json(200, self.store.projects())
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            return self.json(200, self.store.job(parts[2]))
        if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
            project_id = parts[2]
            if len(parts) == 3:
                return self.json(200, self.store.get(project_id))
            if len(parts) == 4 and parts[3] == "generation-readiness":
                return self.json(200, self.store.generation_readiness(project_id))
            if len(parts) == 5 and parts[3] == "media":
                asset, path = self.store.asset(project_id, parts[4])
                return self.file(path, download=asset["kind"] == "scene")
            if len(parts) == 5 and parts[3] == "thumbnail":
                return self.thumbnail(project_id, parts[4])
            if len(parts) == 5 and parts[3] == "exports":
                if not re.fullmatch(r"[a-f0-9]{32}\.(mp4|mov|json|blend)", parts[4]):
                    raise ValueError("Invalid export filename")
                return self.file(self.store.project_dir(project_id) / "exports" / parts[4], download=parts[4].endswith(".blend") or "download" in parse_qs(parsed.query))
        raise FileNotFoundError("Route does not exist")

    def dispatch_write(self):
        parsed = urlparse(self.path)
        parts = unquote(parsed.path).strip("/").split("/")
        query = parse_qs(parsed.query)
        if self.command == "POST" and parts == ["api", "projects"]:
            return self.json(201, self.store.new_project(self.body()))
        if self.command == "POST" and len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
            return self.json(200, self.store.cancel(parts[2]))
        if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
            project_id = parts[2]
            directory = self.store.project_dir(project_id)
            if self.command == "PUT" and len(parts) == 3:
                return self.json(200, self.store.save(project_id, self.body()))
            if self.command != "POST" or len(parts) != 4:
                raise FileNotFoundError("Route does not exist")
            action = parts[3]
            if action == "import":
                length = self.length(MAX_UPLOAD)
                name = safe_name(query.get("name", ["media.mp4"])[0])
                suffix = Path(name).suffix.lower()
                if suffix not in MEDIA_SUFFIXES:
                    raise ValueError("Unsupported media format")
                tmp = directory / ("upload-" + uuid.uuid4().hex + suffix)
                try:
                    with tmp.open("xb") as f:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Upload was interrupted")
                            f.write(chunk)
                            remaining -= len(chunk)
                    return self.json(201, self.store.admit(project_id, tmp, name))
                finally:
                    tmp.unlink(missing_ok=True)
            if action == "workflow":
                graph = self.body()
                workflow = validate_workflow(graph)
                with self.store.lock:
                    self.store._require_open()
                    atomic_json(directory / "workflow.json", workflow)
                return self.json(201, {"workflow_path": "workflow.json"})
            payload = self.body()
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            if action == "render":
                return self.json(202, self.store.render(project_id, payload))
            if action == "generate":
                return self.json(202, self.store.generation(project_id, payload))
            if action == "blender":
                return self.json(202, self.store.blender(project_id, payload))
            if action == "scene":
                return self.json(202, self.store.scene_render(project_id, payload))
            if action == "automate":
                return self.json(200, self.store.automate(project_id, payload))
        raise FileNotFoundError("Route does not exist")

    def do_request(self, mutate=False):
        try:
            self.connection.settimeout(120)
            self.guard(mutate)
            return self.dispatch_write() if mutate else self.dispatch_get()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except ConflictError as exc:
            self.json(409, {"error": str(exc)})
        except PermissionError as exc:
            self.json(403, {"error": str(exc)})
        except FileNotFoundError as exc:
            self.json(404, {"error": str(exc)})
        except (ValueError, KeyError, TypeError, AdapterError) as exc:
            self.json(400, {"error": str(exc)})
        except Exception as exc:
            self.json(500, {"error": str(exc)[-2000:]})

    def do_GET(self):
        return self.do_request()

    def do_HEAD(self):
        return self.do_request()

    def do_POST(self):
        return self.do_request(True)

    def do_PUT(self):
        return self.do_request(True)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port, store):
        self.store = store
        super().__init__(("127.0.0.1", port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="CINEMATICUM local audiovisual editor")
    parser.add_argument("--workspace", type=Path, default=default_workspace(), help="Folder for projects, imported media, and exports")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the editor in the default browser")
    parser.add_argument("--comfy-url", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))
    parser.add_argument("--doctor", action="store_true", help="Report installed engines without starting the editor")
    parser.add_argument("--render", metavar="PROJECT_ID", help="Render a saved project without opening the editor")
    parser.add_argument("--profile", choices=["preview", "h264", "prores"], default="h264")
    args = parser.parse_args(argv)
    try:
        store = Store(args.workspace, args.comfy_url)
    except WorkspaceInUseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.doctor:
        print(json.dumps(store.capabilities(True), indent=2))
        store.shutdown()
        return 0
    if args.render:
        job = store.render(args.render, {"profile": args.profile})
        while store.job(job["id"])["state"] in {"queued", "running"}:
            time.sleep(0.1)
        result = store.job(job["id"])
        print(json.dumps(result, indent=2))
        store.shutdown()
        return 0 if result["state"] == "completed" else 1
    try:
        httpd = Server(args.port, store)
    except OSError as exc:
        print(f"Cannot start CINEMATICUM on port {args.port}: {exc}. Use --port with a free port.", file=sys.stderr)
        store.shutdown()
        return 1
    url = f"http://127.0.0.1:{httpd.server_port}"
    print(f"CINEMATICUM editor: {url}\nProjects: {store.root}", flush=True)
    if args.open:
        webbrowser.open(url)
    def stop(signum, frame):
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        store.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from frame_preview import render_frame, preview_identity
from waveform import extract_waveform
from timebase import project_rate
from tracking import tracking_frame, track_clip, stabilization_motion, validate_track_for_clip
from spatial_import import import_obj
from camera_io import import_camera
from color_pipeline import import_cube, list_luts
import recovery
from collaboration import CollaborationError

VERSION = "0.13.0"
MAX_UPLOAD = 8 * 1024 * 1024 * 1024
MAX_JSON = 8 * 1024 * 1024
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
MEDIA_SUFFIXES = MEDIA_EXTENSIONS | {".blend"}
EPHEMERAL_JOBS = {"frame-preview", "tracking-frame", "audio-source"}
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
        directory_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
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
        self.shutdown_reason = "owner-shutdown"
        self._workspace_lock_fd = None
        self.pool = None
        self.preview_pool = None
        self.audio_pool = None
        self.collaboration = None
        self.scene_workers = None
        self.audio_pending = {}
        self.waveform_slots = threading.BoundedSemaphore(2)
        self.stop_decoding = threading.Event()
        self._acquire_workspace_lock()
        try:
            # Recovery may rewrite queued/running jobs, so it must follow the
            # process-wide lock, never merely the in-process threading.RLock.
            (self.root / "projects").mkdir(exist_ok=True)
            (self.root / "jobs").mkdir(exist_ok=True)
            # These names are reserved for streamed restore inputs, never
            # admitted media. Once the exclusive workspace lock is held no
            # previous process can still be uploading or restoring them.
            for project_dir in (self.root / "projects").iterdir():
                if not IDENTIFIER.fullmatch(project_dir.name) or project_dir.is_symlink() or not project_dir.is_dir():
                    continue
                for abandoned in project_dir.glob("archive-upload-*.zip"):
                    if re.fullmatch(r"archive-upload-[a-f0-9]{32}\.zip", abandoned.name) and not abandoned.is_symlink() and abandoned.is_file():
                        abandoned.unlink()
                for abandoned in project_dir.glob("relink-upload-*"):
                    if (re.fullmatch(r"relink-upload-[a-f0-9]{32}\.[a-zA-Z0-9]+", abandoned.name)
                            and abandoned.suffix.lower() in MEDIA_SUFFIXES
                            and not abandoned.is_symlink() and abandoned.is_file()):
                        abandoned.unlink()
            self.token = secrets.token_urlsafe(32)
            self.comfy_url = comfy_url.rstrip("/")
            self.external_comfy_url = self.comfy_url
            self.managed_generation = None
            self.managed_generation_url = None
            self.jobs = {}
            self.events = {}
            self.futures = {}
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cinematicum-render")
            self.preview_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cinematicum-frame")
            self.audio_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cinematicum-source-audio")
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
            from collaboration_store import CollaborationStore
            self.collaboration = CollaborationStore(self)
            from scene_dispatch_store import SceneDispatchStore
            self.scene_workers = SceneDispatchStore(self)
        except BaseException:
            if self.pool is not None:
                self.pool.shutdown(wait=True, cancel_futures=True)
            if self.preview_pool is not None:
                self.preview_pool.shutdown(wait=True, cancel_futures=True)
            if self.audio_pool is not None:
                self.audio_pool.shutdown(wait=True, cancel_futures=True)
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
                result.append({k: p.get(k) for k in ("id", "name", "fps", "frame_rate", "width", "height", "updated_at")})
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
            if "frame_rate" in payload:
                project["frame_rate"] = copy.deepcopy(payload["frame_rate"])
                if "fps" not in payload:
                    project.pop("fps")
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
            if not creating and self.collaboration is not None and self.collaboration.bound(project_id):
                return self.collaboration.save(project_id, project)
            directory = self.project_dir(project_id)
            p = copy.deepcopy(project)
            receipt = p.pop("_recovery", None)
            if receipt is not None:
                if not isinstance(receipt, dict):
                    raise ValueError("Invalid recovery acknowledgement.")
                recovery.identity(receipt.get("editor_id"))
                recovery.sequence(receipt.get("sequence"))
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
            recovery.preserve_saved(directory, current, atomic_json)
            # Validation reprobes server-owned media. Persist upgraded stream
            # identities so reopening a pre-0.9 asset retains exact audio binding.
            if p["assets"] != read_json(directory / "assets.json", []):
                atomic_json(directory / "assets.json", p["assets"])
            atomic_json(directory / "project.json", p)
            try:
                recovery.acknowledge(directory, receipt, current.get("revision", 0))
            except (OSError, ValueError, KeyError):
                # The committed edit is durable. Retain an unreadable draft for
                # review instead of claiming that a successful save failed.
                pass
            return p

    def checkpoint(self, project_id, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("project"), dict):
            raise ValueError("A recovery checkpoint requires a project snapshot.")
        with self.lock:
            current = self.get(project_id)
            p = copy.deepcopy(payload["project"])
            if p.get("id") != project_id or p.get("revision") != current["revision"]:
                raise ConflictError("The saved project changed. Reopen it before checkpointing this draft.")
            p.pop("_recovery", None)
            p["assets"] = current["assets"]
            directory = self.project_dir(project_id)
            p = validate_project(p, directory)
            if not isinstance(p.get("settings", {}), dict):
                raise ValueError("Project settings must be an object")
            if p.get("settings", {}).get("scene") is not None:
                p["settings"]["scene"] = validate_scene(p["settings"]["scene"], width=p["width"], height=p["height"])
            return recovery.put(directory, payload.get("editor_id"), payload.get("sequence"), p, atomic_json)

    def recovery(self, project_id, payload=None):
        with self.lock:
            current, directory = self.get(project_id), self.project_dir(project_id)
            if payload is None:
                return recovery.listing(directory, current)
            if not isinstance(payload, dict):
                raise ValueError("Recovery selection must be an object.")
            if payload.get("action") == "discard":
                recovery.discard(directory, payload.get("key"), payload.get("sequence"))
                return {"discarded": True}
            if payload.get("action") != "restore":
                raise ValueError("Unknown recovery action.")
            p, record = recovery.candidate(directory, current, payload.get("kind"), payload.get("key"), payload.get("sequence"))
            p = validate_project(p, directory)
            if p.get("settings", {}).get("scene") is not None:
                p["settings"]["scene"] = validate_scene(p["settings"]["scene"], width=p["width"], height=p["height"])
            return {"project": p, "base_revision": record["base_revision"], "saved_revision": current["revision"], "committed": False}

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
            if suffix == ".exr":
                from imaging import probe_exr_source
                header = probe_exr_source(directory, incoming)
                if (header["width"], header["height"]) != (meta["width"], meta["height"]):
                    raise ValueError("EXR image dimensions disagree between header readers.")
                meta["imaging_source"] = header
        asset_id = uuid.uuid4().hex
        target = directory / "media" / (asset_id + suffix)
        asset = {"id": asset_id, "name": safe_name(name), "path": "media/" + target.name, "sha256": digest_file(incoming), "size": incoming.stat().st_size, **meta}
        if provenance:
            asset["provenance"] = provenance
        with self.lock:
            self._require_open()
            assets = read_json(directory / "assets.json", [])
            # A developed display image belongs to its exact linear master and
            # receipt, even when another image happens to contain equal pixels.
            # Ordinary duplicate imports and unchanged title plates still reuse
            # their immutable media.
            development = isinstance(provenance, dict) and provenance.get("type") in {
                "cinematicum-imaging", "cinematicum-deep-compositing", "cinematicum-physical-rendering", "cinematicum-learned-mask", "cinematicum-scene-processing"}
            duplicate = next((a for a in assets if a.get("sha256") == asset["sha256"]
                              and a.get("kind") == asset["kind"]
                              and (not development or a.get("provenance") == provenance)), None)
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
        try:
            generation_status = check_comfyui(self.generation_endpoint())
        except ValueError as error:
            generation_status = {"available": False, "reason": str(error)}
        result = {"version": VERSION, "ffmpeg": bool(ffmpeg and ffprobe), "blender": bool(find_blender()), "comfyui": generation_status, "titles": "overlay" in filters, "raster_titles": "overlay" in filters, "drawtext": "drawtext" in filters, "h264": "libx264" in encoders, "prores": "prores_ks" in encoders, "workspace": str(self.root), "color_space": "SDR Rec.709", "commercial_providers": "No paid provider is configured in this build."}
        result["scene_authoring"] = result["blender"] and result["ffmpeg"]
        result["node_compositor"] = all(name in filters for name in ("geq", "overlay", "split", "gblur"))
        result["point_tracking"] = "find_rect" in filters
        from planar_tracking import planar_capabilities
        result["planar_tracking"] = planar_capabilities()
        result["color_pipeline"] = all(name in filters for name in ("geq", "lut1d", "lut3d"))
        from engine import get_capabilities
        movie_capabilities = get_capabilities()
        for name in ("high_depth_movie", "master16", "image_precisions"):
            result[name] = movie_capabilities[name]
        result["camera_import"] = True
        from imaging import imaging_capabilities
        result["imaging"] = imaging_capabilities()
        result["mesh_modeling"] = result["blender"]
        self._cap_cache, self._cap_time = copy.deepcopy(result), time.monotonic()
        return result

    def _write_job(self, job):
        # Authoring stills are a reproducible cache. Scrubbing must not create
        # thousands of durable render receipts or hide actual export history.
        if job.get("kind") in EPHEMERAL_JOBS:
            return
        atomic_json(self.root / "jobs" / (job["id"] + ".json"), job)

    def submit(self, project_id, kind, fn, snapshot=None, cleanup=None):
        def execute():
            with self.lock:
                if event.is_set():
                    job.update(state="cancelled", error="Job cancelled before starting", finished_at=time.time())
                    self.events.pop(job_id, None)
                    self._write_job(job)
                    return
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
                    if isinstance(exc, AdapterError) and getattr(exc, "prompt_id", None):
                        job["prompt_id"] = exc.prompt_id
                    if isinstance(getattr(exc, "cancellation", None), dict):
                        job["remote_cancellation"] = copy.deepcopy(exc.cancellation)
            finally:
                with self.lock:
                    job["finished_at"] = time.time()
                    self._write_job(job)
                    self.events.pop(job_id, None)
        def completed(_future):
            try:
                # Executor shutdown cancels queued Futures without calling
                # execute(). Settle their durable state before releasing owned
                # uploads; they must not reopen as unexplained interruptions.
                if _future.cancelled():
                    with self.lock:
                        if job["state"] == "queued":
                            job.update(state="cancelled", error="Job cancelled before starting", finished_at=time.time())
                            self._write_job(job)
                        self.events.pop(job_id, None)
                if cleanup is not None:
                    cleanup()
            finally:
                with self.lock:
                    self.futures.pop(job_id, None)

        with self.lock:
            # Job admission and executor ownership are one transaction. Quit
            # cannot close an executor between the durable queued record and
            # its Future, or release the workspace before cleanup is owned.
            self._require_open()
            active = sum(j["state"] in {"queued", "running"}
                         and (j.get("kind") == "audio-source") == (kind == "audio-source")
                         for j in self.jobs.values())
            if active >= (32 if kind == "audio-source" else 8):
                raise ValueError("Source audio preparation queue is full. Retry when preparation completes."
                                 if kind == "audio-source" else "Render queue is full. Wait for or cancel a queued job.")
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "project_id": project_id, "kind": kind, "state": "queued", "progress": 0, "created_at": time.time(), "error": None, "result": None}
            event = threading.Event()
            self.jobs[job_id] = job
            self.events[job_id] = event
            self._write_job(job)
            if snapshot is not None:
                atomic_json(self.root / "jobs" / (job_id + ".snapshot"), snapshot)
            pool = self.audio_pool if kind == "audio-source" else self.preview_pool if kind in EPHEMERAL_JOBS else self.pool
            future = pool.submit(execute)
            self.futures[job_id] = future
            # A cancelled queued Future never invokes execute(). It still owns
            # an uploaded input, so cancellation and shutdown release it here.
            future.add_done_callback(completed)
            if event.is_set():
                future.cancel()
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
                    future = self.futures.get(job_id)
                    if future is not None:
                        future.cancel()
            return copy.deepcopy(job)

    def render(self, project_id, payload):
        profile = payload.get("profile", "h264")
        if profile not in {"preview", "h264", "prores", "master16", "master32"}:
            raise ValueError("Unknown export profile")
        project = payload.get("project", self.get(project_id))
        p = copy.deepcopy(project)
        p["id"] = project_id
        p["assets"] = self.get(project_id)["assets"]
        directory = self.project_dir(project_id)
        normalized = validate_project(p, directory)
        if isinstance(normalized, dict):
            p = normalized
        if profile == "master16" and p.get("settings", {}).get("image_precision", "standard8") != "high16":
            raise ValueError("Select 16-bit SDR movie processing before exporting a 16-bit master.")
        if profile == "master32" and p.get("settings", {}).get("image_precision") != "float32":
            raise ValueError("Select Scene-linear Float32 processing before exporting the EXR movie master.")
        if not p.get("clips") and not p.get("titles") and not p.get("sequence_duration"):
            raise ValueError("Add media to the timeline before rendering")
        snapshot = copy.deepcopy(p)

        def work(job_id, progress, event):
            suffix = ".zip" if profile == "master32" else ".mov" if profile == "prores" else ".mkv" if profile == "master16" else ".mp4"
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

    def frame_preview(self, project_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("Expected a frame preview request")
        project = copy.deepcopy(payload.get("project", self.get(project_id)))
        project["id"] = project_id
        project["assets"] = self.get(project_id)["assets"]
        directory = self.project_dir(project_id)
        project = validate_project(project, directory)
        frame = payload.get("frame")
        total = max([c["start"] + c["duration"] for c in project["clips"]] +
                    [t["start"] + t["duration"] for t in project["titles"]] +
                    [c["start"] + c["duration"] for c in project.get("captions", [])] + [project.get("sequence_duration", 0)])
        if type(frame) is not int or not 0 <= frame < total:
            raise ValueError("Preview frame must be inside this timeline")
        identity = preview_identity(project, frame)
        output = directory / "previews" / (identity + ".png")
        with self.lock:
            for previous in list(self.jobs.values()):
                if previous.get("project_id") == project_id and previous.get("kind") == "frame-preview" and previous.get("state") in {"queued", "running"}:
                    self.cancel(previous["id"])
            old_jobs = sorted((job for job in self.jobs.values() if job.get("kind") == "frame-preview"
                               and job.get("state") not in {"queued", "running"}),
                              key=lambda job: job["created_at"], reverse=True)
            for old in old_jobs[64:]:
                self.jobs.pop(old["id"], None)

        def work(job_id, progress, event):
            if event.is_set():
                raise RuntimeError("Frame preview superseded")
            if output.is_file() and not output.is_symlink():
                result = {"frame": frame, "width": project["width"], "height": project["height"],
                          "sha256": digest_file(output), "pipeline": "timeline-export-graph", "cached": True}
            else:
                result = render_frame(project, directory, frame, output, cancel_event=event)
            result["url"] = f"/api/projects/{project_id}/previews/{output.name}"
            # Only reproducible, app-named still cache files are evicted.
            cached = sorted(output.parent.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True)
            for old in cached[64:]:
                if re.fullmatch(r"[a-f0-9]{64}\.png", old.name) and old != output and not old.is_symlink():
                    old.unlink(missing_ok=True)
            return result
        return self.submit(project_id, "frame-preview", work)

    def analysis_snapshot(self, project_id, payload):
        """Validate the unsaved edit against this project's imported inventory."""
        if not isinstance(payload, dict):
            raise ValueError("Expected an analysis request object")
        current = self.get(project_id)
        project = copy.deepcopy(payload.get("project", current))
        if not isinstance(project, dict):
            raise ValueError("Project must be an object")
        project["id"] = project_id
        project["assets"] = current["assets"]
        return validate_project(project, self.project_dir(project_id))

    def archive_export(self, project_id, payload):
        from project_archive import export_archive
        snapshot = self.analysis_snapshot(project_id, payload)
        directory = self.project_dir(project_id)

        def work(job_id, progress, event):
            output = directory / "exports" / (job_id + ".cinematicum.zip")
            report = export_archive(snapshot, directory, output, cancel_event=event, progress=progress)
            result = {key: report[key] for key in ("filename", "sha256", "size", "files", "total_bytes", "warnings", "issuance_effect")}
            result.update(url=f"/api/projects/{project_id}/exports/{output.name}", project_revision=snapshot.get("revision"))
            atomic_json(directory / "exports" / (job_id + ".json"), {"result": result, "issuance_effect": "NONE"})
            return result
        return self.submit(project_id, "archive-export", work, snapshot)

    def archive_restore(self, project_id, incoming):
        from project_archive import import_archive
        self.get(project_id)
        incoming = Path(incoming)
        directory = self.project_dir(project_id)
        if incoming.parent != directory or incoming.is_symlink() or not re.fullmatch(r"archive-upload-[a-f0-9]{32}\.zip", incoming.name):
            raise ValueError("Archive restore requires a project-owned upload.")

        def work(job_id, progress, event):
            restored = import_archive(incoming, self.root / "projects", cancel_event=event, progress=progress)
            return {"project_id": restored["id"], "name": restored["name"], **restored["archive_restore"]}

        # Both worker completion and cancellation before execution release the
        # upload. The request handler removes it if submission itself fails.
        return self.submit(project_id, "archive-restore", work, cleanup=lambda: incoming.unlink(missing_ok=True))

    def model_mesh(self, project_id, payload):
        """Evaluate a candidate; only the editor's undoable apply changes a scene."""
        from scene_modeling import model_mesh
        self.get(project_id)
        if not isinstance(payload, dict) or set(payload) != {"object", "operation"}:
            raise ValueError("Mesh editing needs one object and one operation.")
        request = copy.deepcopy(payload)

        def work(job_id, progress, event):
            progress(.05)
            result = model_mesh(request, cancel_event=event)
            if event.is_set():
                raise RuntimeError("Mesh edit cancelled")
            progress(1)
            return result
        return self.submit(project_id, "scene-modeling", work)

    def imaging_render(self, project_id, payload):
        """Process owned source pixels, retaining linear and display artifacts."""
        from imaging import run_imaging
        if not isinstance(payload, dict) or set(payload) != {"recipe"}:
            raise ValueError("Image processing requires one recipe.")
        project, recipe = self.get(project_id), copy.deepcopy(payload["recipe"])
        directory = self.project_dir(project_id)

        def work(job_id, progress, event):
            output = directory / "imaging" / "outputs" / job_id
            result = run_imaging(project, directory, recipe, output,
                                 progress=progress, cancel_event=event)
            if event.is_set():
                raise RuntimeError("Image processing cancelled")
            # The artifact set remains immutable. Asset admission owns a copy
            # and never moves display.png out of its EXR/receipt collection.
            with tempfile.TemporaryDirectory(prefix="imaging-admit-", dir=str(directory)) as temp:
                display = Path(temp) / "display.png"
                shutil.copyfile(result["path"], display)
                asset = self.admit(project_id, display,
                                   "Image " + str(recipe.get("operation", "processed")) + " " + job_id[:8] + ".png",
                                   result.get("provenance"))
            base = f"/api/projects/{project_id}/imaging/outputs/{job_id}"
            result.update(asset=asset, url=f"/api/projects/{project_id}/media/{asset['id']}",
                          exr_url=base + "/linear.exr", receipt_url=base + "/receipt.json",
                          display_url=base + "/display.png")
            if "motion" in result["artifacts"]:
                result["motion_url"] = base + "/motion.png"
            return result
        return self.submit(project_id, "imaging", work, {"recipe": recipe})

    def tracking(self, project_id, payload, seed_only=False, learned_seed=False):
        project = self.analysis_snapshot(project_id, payload)
        directory = self.project_dir(project_id)
        clip_id = payload.get("clip_id")
        request = copy.deepcopy(payload.get("settings", {}))
        if not isinstance(request, dict):
            raise ValueError("Tracking settings must be an object")
        if seed_only:
            with self.lock:
                old_jobs = sorted((job for job in self.jobs.values() if job.get("kind") == "tracking-frame"
                                   and job.get("state") not in {"queued", "running"}),
                                  key=lambda job: job["created_at"], reverse=True)
                for old in old_jobs[32:]:
                    self.jobs.pop(old["id"], None)

        def work(job_id, progress, event):
            output = directory / "analysis" / (job_id + (".png" if seed_only else ".json"))
            if seed_only:
                if learned_seed:
                    from learned_tracking import learned_frame
                    result = learned_frame(project, directory, clip_id, request, output, cancel_event=event)
                else:
                    result = tracking_frame(project, directory, clip_id, request, output, cancel_event=event)
                cached = sorted(output.parent.glob("*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
                for old in cached[32:]:
                    if re.fullmatch(r"[a-f0-9]{32}\.png", old.name) and not old.is_symlink():
                        old.unlink(missing_ok=True)
            else:
                measured = track_clip(project, directory, clip_id, request, progress=progress, cancel_event=event)
                if event.is_set():
                    raise RuntimeError("Tracking cancelled")
                atomic_json(output, measured)
                result = {"track": measured, "sha256": digest_file(output)}
            result.update(url=f"/api/projects/{project_id}/analysis/{output.name}", filename=output.name)
            return result
        return self.submit(project_id, "tracking-frame" if seed_only else "tracking", work,
                           None if seed_only else {"project": project, "clip_id": clip_id, "settings": request})

    def tracking_plan(self, project_id, payload, motion=False):
        project = self.analysis_snapshot(project_id, payload)
        directory = self.project_dir(project_id)
        clip_id, measured = payload.get("clip_id"), payload.get("track")
        if motion:
            return {"motion": stabilization_motion(project, directory, clip_id, measured,
                                                    mode=payload.get("mode", "stabilize"))}
        return {"track": validate_track_for_clip(project, directory, clip_id, measured)}

    def tracking_setup(self, project_id, payload):
        if payload != {}:
            raise ValueError("Tracking setup accepts an empty options object.")
        self.get(project_id)

        def work(job_id, progress, event):
            from install_tracking import install
            progress(.05)
            result = install(cancel_event=event)
            with self.lock:
                self._cap_cache = None
            from planar_tracking import planar_capabilities
            return {"installation": result, "status": planar_capabilities()}
        return self.submit(project_id, "tracking-setup", work)

    def interchange(self, project_id, payload, importing=False, inspecting=False):
        from interchange import export_otio, import_otio
        from fcpxml import export_fcpxml, import_fcpxml, inspect_fcpxml
        format_name = payload.get("format", "otio")
        if not isinstance(format_name, str) or format_name not in {"otio", "fcpxml"}:
            raise ValueError("Timeline interchange format must be otio or fcpxml.")
        project = self.analysis_snapshot(project_id, payload)
        directory = self.project_dir(project_id)
        if inspecting:
            if format_name != "fcpxml":
                raise ValueError("XML reference inspection requires the fcpxml format.")
            return inspect_fcpxml(payload.get("document"))
        if importing:
            importer = import_fcpxml if format_name == "fcpxml" else import_otio
            return importer(payload.get("document"), project, directory, payload.get("asset_map"))
        result = (export_fcpxml if format_name == "fcpxml" else export_otio)(project, directory)
        output = directory / "exports" / (uuid.uuid4().hex + "." + format_name)
        if format_name == "fcpxml":
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(output.parent), delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(result["document"])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, output)
                directory_fd = os.open(str(output.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        else:
            atomic_json(output, result["document"])
        return {"url": f"/api/projects/{project_id}/exports/{output.name}", "filename": output.name,
                "format": format_name, "warnings": result.get("warnings", []), "sha256": digest_file(output)}

    def waveform(self, project_id, asset_id, bins, stream_index=None, channels=None):
        asset, path = self.asset(project_id, asset_id)
        if not asset.get("has_audio"):
            raise ValueError("This source has no audio stream")
        if not self.waveform_slots.acquire(timeout=1):
            raise ValueError("Waveform decoding is busy. Retry shortly.")
        try:
            return extract_waveform(path, self.project_dir(project_id) / "waveforms", bins=bins,
                                    cancel_event=self.stop_decoding, stream_index=stream_index, channels=channels)
        finally:
            self.waveform_slots.release()

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
        base_url = self.generation_endpoint()
        readiness = workflow_readiness(base_url, workflow, prompt=prompt, negative=negative, seed=seed)
        if not readiness["ready"]:
            raise ValueError("Generation preflight failed: " + " ".join(readiness["errors"][:5]))

        def work(job_id, progress, event):
            if self.generation_endpoint() != base_url:
                raise ValueError("The generation runtime changed before this shot started. Submit it again to the current engine.")
            with tempfile.TemporaryDirectory(prefix="generation-", dir=str(directory)) as scratch:
                result = generate_comfyui(base_url, workflow, prompt, negative, seed, Path(scratch), progress=progress, cancel_event=event)
                if event.is_set():
                    raise RuntimeError("Generation cancelled locally")
                asset = self.admit(project_id, result["path"], "Generated take" + Path(result["path"]).suffix, result.get("provenance"))
                return {"asset": asset, "url": f"/api/projects/{project_id}/media/{asset['id']}"}
        return self.submit(project_id, "generate", work, {"prompt": prompt, "negative": negative, "seed": seed, "workflow": workflow})

    def generation_readiness(self, project_id):
        directory = self.project_dir(project_id)
        path = directory / "workflow.json"
        return workflow_readiness(self.generation_endpoint(), read_json(path) if path.is_file() else None)

    def generation_endpoint(self):
        """Never reuse a dead managed child's ephemeral port as a new engine."""
        with self.lock:
            self._require_open()
            if self.managed_generation_url is not None:
                status = self.managed_generation.status() if self.managed_generation is not None else {}
                if (not status.get("running") or not status.get("ready")
                        or status.get("base_url") != self.managed_generation_url
                        or self.comfy_url != self.managed_generation_url):
                    raise ValueError("The local generation engine stopped. Open Local generation setup and start it again.")
            return self.comfy_url

    def generation_manager(self):
        with self.lock:
            self._require_open()
            if self.managed_generation is None:
                from managed_generation import ManagedGeneration
                self.managed_generation = ManagedGeneration()
            return self.managed_generation

    def generation_runtime_status(self):
        return self.generation_manager().status()

    def generation_runtime_job(self, project_id, action, payload):
        self.project_dir(project_id)
        if action not in {"setup", "start"} or not isinstance(payload, dict) or payload:
            raise ValueError("Generation setup and start accept an empty options object")
        manager = self.generation_manager()
        with self.lock:
            if any(job["kind"] in {"generate", "generation-setup", "generation-start"}
                   and job["state"] in {"queued", "running"} for job in self.jobs.values()):
                raise ValueError("A generation runtime operation is already active")

        def work(job_id, progress, event):
            result = manager.install(progress, event) if action == "setup" else manager.start(progress, event)
            with self.lock:
                if action == "start":
                    base_url = result.get("base_url")
                    endpoint = urlparse(base_url) if isinstance(base_url, str) else None
                    if (endpoint is None or endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
                            or not endpoint.port or endpoint.username or endpoint.password or endpoint.path
                            or endpoint.query or endpoint.fragment):
                        raise ValueError("Managed generation did not return its owned loopback endpoint")
                    self.comfy_url = base_url
                    self.managed_generation_url = base_url
                self._cap_cache = None
            return result
        with self.lock:
            if any(job["kind"] in {"generate", "generation-setup", "generation-start"}
                   and job["state"] in {"queued", "running"} for job in self.jobs.values()):
                raise ValueError("A generation runtime operation is already active")
            return self.submit(project_id, "generation-" + action, work)

    def generation_runtime_stop(self):
        with self.lock:
            if any(job["kind"] in {"generate", "generation-setup", "generation-start"}
                   and job["state"] in {"queued", "running"} for job in self.jobs.values()):
                raise ValueError("Finish or cancel the active generation job before stopping its runtime")
            result = self.generation_manager().stop()
            self.comfy_url = self.external_comfy_url
            self.managed_generation_url = None
            self._cap_cache = None
            return result

    def generation_default_workflow(self, project_id, options):
        directory = self.project_dir(project_id)
        workflow = validate_workflow(self.generation_manager().default_workflow(options))
        with self.lock:
            self._require_open()
            destination = directory / "workflow.json"
            if destination.is_symlink():
                raise ValueError("Workflow destination must not be a symlink")
            if destination.is_file():
                previous = read_json(destination)
                if previous != workflow:
                    history = directory / "workflow-history"
                    if history.is_symlink():
                        raise ValueError("Workflow history must not be a symlink")
                    history.mkdir(exist_ok=True)
                    prior_bytes = destination.read_bytes()
                    prior_sha = hashlib.sha256(prior_bytes).hexdigest()
                    archived = history / (prior_sha + ".json")
                    if archived.is_symlink():
                        raise ValueError("Workflow history entry must not be a symlink")
                    if archived.exists():
                        if not archived.is_file() or digest_file(archived) != prior_sha:
                            raise ValueError("The previous workflow archive is incomplete; the current workflow was preserved")
                    else:
                        temporary = history / (".workflow-" + uuid.uuid4().hex + ".part")
                        try:
                            with temporary.open("xb") as output:
                                output.write(prior_bytes)
                                output.flush()
                                os.fsync(output.fileno())
                            # A hard link publishes complete bytes atomically and
                            # never overwrites a concurrently created archive.
                            try:
                                os.link(temporary, archived)
                            except FileExistsError:
                                if archived.is_symlink() or not archived.is_file() or digest_file(archived) != prior_sha:
                                    raise ValueError("Workflow history changed; the current workflow was preserved")
                        finally:
                            temporary.unlink(missing_ok=True)
            atomic_json(destination, workflow)
        return {"workflow_path": "workflow.json", "workflow": workflow,
                "previous_workflow_retained": True}

    def media_inventory(self, project_id):
        from media_management import inventory
        return inventory(self.get(project_id), self.project_dir(project_id))

    def media_proxy(self, project_id, payload):
        from media_management import create_proxy, asset_record, proxy_recipe
        if not isinstance(payload, dict) or set(payload) - {"asset_id", "long_edge"}:
            raise ValueError("Proxy creation accepts one asset and a preview size.")
        project, directory = self.get(project_id), self.project_dir(project_id)
        asset_record(project, payload.get("asset_id"))
        edge = payload.get("long_edge", 960)
        proxy_recipe(edge)

        def work(job_id, progress, event):
            result = create_proxy(project, directory, payload["asset_id"], edge,
                                  progress=progress, cancel_event=event)
            result["url"] = f"/api/projects/{project_id}/media-proxy/{payload['asset_id']}?long_edge={edge}"
            return result
        return self.submit(project_id, "media-proxy", work,
                           {"asset_id": payload["asset_id"], "long_edge": edge})

    def audio_source(self, project_id, payload):
        from audio_source import cached_source, create_source, source_identity, source_recipe
        from media_management import asset_record
        if not isinstance(payload, dict) or set(payload) - {"asset_id", "stream_index", "channels", "playback_rate"}:
            raise ValueError("Source audio preparation accepts one asset, its stream ID and source channel mapping.")
        project, directory = self.get(project_id), self.project_dir(project_id)
        asset = asset_record(project, payload.get("asset_id"))
        stream_index, channels = payload.get("stream_index"), payload.get("channels")
        playback_rate = payload.get("playback_rate", 1)
        recipe = source_recipe(asset, stream_index, channels, playback_rate)
        key = source_identity(asset, recipe)
        url = f"/api/projects/{project_id}/audio-source/{key}"
        cached = cached_source(project, directory, asset["id"], stream_index, channels, playback_rate)
        if cached:
            return {**cached, "url": url}
        identity = (project_id, key)
        with self.lock:
            self._require_open()
            pending_id = self.audio_pending.get(identity)
            pending = self.jobs.get(pending_id)
            if pending and pending["state"] in {"queued", "running"}:
                return {"job": copy.deepcopy(pending)}
            old_jobs = sorted((job for job in self.jobs.values() if job.get("kind") == "audio-source"
                               and job["state"] not in {"queued", "running"}),
                              key=lambda job: job["created_at"], reverse=True)
            for old in old_jobs[128:]:
                self.jobs.pop(old["id"], None)

            def work(job_id, progress, event):
                result = create_source(project, directory, asset["id"], stream_index, channels,
                                       progress=progress, cancel_event=event, playback_rate=playback_rate)
                return {**result, "url": url}

            def cleanup():
                with self.lock:
                    self.audio_pending.pop(identity, None)

            job = self.submit(project_id, "audio-source", work, cleanup=cleanup)
            self.audio_pending[identity] = job["id"]
            return {"job": job}

    def media_relink(self, project_id, asset_id, incoming):
        from media_management import relink_original
        with self.lock:
            return relink_original(self.get(project_id), self.project_dir(project_id), asset_id, incoming)

    def editorial(self, project_id, payload):
        from editorial import apply_action
        project = self.analysis_snapshot(project_id, payload)
        result = apply_action(project, payload.get("action"), payload.get("values", {}), self.project_dir(project_id))
        if payload.get("action") == "captions_export":
            extension = result["format"]
            if extension not in {"srt", "vtt"}:
                raise ValueError("Unsupported caption sidecar format.")
            output = self.project_dir(project_id) / "exports" / (uuid.uuid4().hex + "." + extension)
            output.write_text(result["text"], encoding="utf-8")
            result["url"] = f"/api/projects/{project_id}/exports/{output.name}"
            result["sha256"] = digest_file(output)
        return result

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
                    "fps": project["fps"], "frame_rate": project_rate(project).as_dict(), "project_revision": project["revision"]}

        def work(job_id, progress, event):
            source = directory / "exports" / (job_id + ".blend")
            masters = directory / "exports" / (job_id + ".zip")
            manifest = directory / "exports" / (job_id + ".json")
            source_published = False
            try:
                with tempfile.TemporaryDirectory(prefix="scene-", dir=str(directory)) as scratch:
                    result = render_scene(recipe, Path(scratch), fps=project_rate(project),
                                          frame_start=start, frame_end=end, progress=progress, cancel_event=event)
                    if event.is_set():
                        raise RuntimeError("Scene render cancelled")
                    generated_source = Path(result["scene_path"])
                    if not generated_source.is_file() or generated_source.stat().st_size == 0:
                        raise RuntimeError("Scene renderer did not preserve its Blender source")
                    masters_report = {}
                    if result.get("masters_path"):
                        generated_masters = Path(result["masters_path"])
                        if (generated_masters.is_symlink() or not generated_masters.is_file()
                                or not generated_masters.resolve().is_relative_to(Path(scratch).resolve())
                                or digest_file(generated_masters) != result.get("masters_sha256")):
                            raise RuntimeError("Scene-linear masters failed output identity validation")
                        os.replace(str(generated_masters), str(masters))
                        masters_report = {"masters_url": f"/api/projects/{project_id}/exports/{masters.name}",
                                          "masters_filename": masters.name, "masters_sha256": result["masters_sha256"],
                                          "masters_manifest": result["masters_manifest"]}
                    if event.is_set():
                        raise RuntimeError("Scene render cancelled")
                    os.replace(str(generated_source), str(source))
                    asset = self.admit(project_id, result["path"], recipe.get("name", "Scene") + " render.mp4", result.get("provenance"))
                    source_published = True
                    report = {"asset": asset, "url": f"/api/projects/{project_id}/media/{asset['id']}",
                              "scene_url": f"/api/projects/{project_id}/exports/{source.name}",
                              "scene_filename": source.name, "scene_sha256": digest_file(source),
                              "project_revision": project["revision"], **masters_report}
                    atomic_json(manifest, {"result": report, "snapshot": snapshot, "issuance_effect": "NONE"})
                    return report
            finally:
                if not source_published:
                    source.unlink(missing_ok=True)
                    masters.unlink(missing_ok=True)
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
                result = render_blender(path, Path(scratch), start, end, fps=project_rate(p), progress=progress, cancel_event=event)
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
            locked = {track["id"] for track in project.get("tracks", []) if track.get("locked")}
            if any(clip.get("track", 0) in locked for clip in clips):
                raise ValueError("Unlock the selected tracks before applying editing automation")
            if action == "sequence" and op.get("track", 0) in locked:
                raise ValueError("Unlock the destination track before arranging clips")
            if action == "grade":
                values = op.get("values", {})
                if not isinstance(values, dict) or not set(values) <= {"exposure", "contrast", "saturation", "temperature"}:
                    raise ValueError("Unknown grade setting")
                for clip in clips:
                    clip.setdefault("grade", {}).update(values)
            elif action == "volume":
                for clip in clips:
                    clip["volume"] = op.get("value")
                    for key in clip.get("keyframes", []):
                        if "volume" in key:
                            key["volume"] = op.get("value")
            elif action == "sequence":
                position = op.get("start", 0)
                for clip in sorted(clips, key=lambda c: c["start"]):
                    clip["start"], clip["track"] = position, op.get("track", 0)
                    position += clip["duration"]
            elif action == "trim":
                for clip in clips:
                    changes_source = ("in" in op and op["in"] != clip.get("in", 0)) or (
                        clip.get("reverse", False) and "duration" in op and op["duration"] != clip["duration"])
                    derived_mask = any(node.get("tracking_source") for node in clip.get("compositor", {}).get("nodes", []))
                    if changes_source and (clip.get("tracking") or derived_mask):
                        raise ValueError("Remove measured stabilization and tracked mask motion before changing the source range with automation")
                    clip.setdefault("animation_start", 0)
                    clip.setdefault("animation_duration", clip["duration"])
                    clip.setdefault("animation_offset", 0)
                    audio = clip.setdefault("audio", {})
                    audio.setdefault("fade_duration", clip["duration"])
                    audio.setdefault("fade_offset", 0)
                    for key in ("in", "duration"):
                        if key in op:
                            clip[key] = op[key]
            else:
                raise ValueError("Supported automation actions: grade, volume, sequence, trim")
        return self.save(project_id, project)

    def prepare_quit(self, payload):
        """Reserve shutdown atomically, or leave active work completely alone."""
        if not isinstance(payload, dict) or set(payload) != {"cancel_active"} or type(payload["cancel_active"]) is not bool:
            raise ValueError("Quit preparation requires an explicit cancel_active boolean.")
        with self.lock:
            self._require_open()
            jobs = [{"id": job["id"], "kind": job["kind"], "state": job["state"]}
                    for job in self.jobs.values() if job["state"] in {"queued", "running"}
                    and job["kind"] not in EPHEMERAL_JOBS and job["kind"] != "audio-source"]
            if jobs and not payload["cancel_active"]:
                return {"ready": False, "active_jobs": jobs}
            self.shutdown_reason = "native-user-confirmed-job-cancellation" if jobs else "native-quit-no-active-jobs"
            # Close admission under the same lock as the active-work check.
            # A job submitted concurrently cannot slip through the quit prompt.
            self._closing = True
            for event in self.events.values():
                event.set()
            return {"ready": True, "active_jobs": jobs}

    def shutdown(self):
        # Concurrent/repeated shutdown calls cannot release another caller's
        # lock early while a render subprocess is still finishing.
        with self._shutdown_lock:
            if self._closed:
                return
            with self.lock:
                self._closing = True
                self.stop_decoding.set()
                active_at_shutdown = [{"id": job["id"], "kind": job["kind"], "state": job["state"]}
                                      for job in self.jobs.values() if job["state"] in {"queued", "running"}]
                for event in self.events.values():
                    event.set()
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.preview_pool.shutdown(wait=True, cancel_futures=True)
            self.audio_pool.shutdown(wait=True, cancel_futures=True)
            if self.managed_generation is not None:
                self.managed_generation.shutdown()
            if self.collaboration is not None:
                self.collaboration.close()
            if self.scene_workers is not None:
                self.scene_workers.close()
            with self.lock:
                # Preserve the reason and exact affected jobs, without prompt or
                # media content, so an ordinary quit is distinguishable from a crash.
                try:
                    atomic_json(self.root / "last-session-exit.json", {
                        "version": 1, "reason": self.shutdown_reason, "completed_at": time.time(),
                        "active_at_shutdown": active_at_shutdown,
                        "terminal_jobs": [{"id": job["id"], "state": job["state"], "error": job.get("error")}
                                          for job in self.jobs.values() if job["id"] in {entry["id"] for entry in active_at_shutdown}],
                    })
                except OSError as error:
                    print("CINEMATICUM shutdown receipt could not be saved: " + str(error), file=sys.stderr)
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

    def body(self, limit=MAX_JSON):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Expected application/json")
        length = self.length(limit)
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("Incomplete request body")
        return json.loads(data, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))

    def file(self, path, download=False, etag=None):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError("File is missing")
        if etag is not None:
            if not isinstance(etag, str) or not re.fullmatch(r"[a-f0-9]{64}", etag):
                raise ValueError("Invalid media content identity")
            etag = '"' + etag + '"'
            if self.headers.get("If-Match") not in {None, etag}:
                return self.json(412, {"error": "The prepared audio changed. Prepare the source again before playback."})
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
        if etag is not None:
            self.send_header("ETag", etag)
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
        if parsed.path in {"/learned-tracking-ui.js", "/collaboration-ui.js", "/runtime-management-ui.js", "/reconstruction-ui.js", "/scene-processing-ui.js", "/multicam-sync-ui.js", "/multicam-monitor.js", "/float-movie-ui.js", "/retime-model.js", "/retime-ui.js"}:
            return self.file(WEB / parsed.path[1:])
        if parts == ["api", "runtime-management"]:
            from runtime_management import inventory
            return self.json(200, inventory())
        if parts == ["api", "scene-workers"]:
            return self.json(200, self.store.scene_workers.inventory())
        if parsed.path in {"/", "/index.html", "/app.js", "/style.css", "/editing.js", "/viewer-tools.js", "/compositor-ui.js", "/scene-editor.js", "/scene-editor.css", "/tracking-ui.js", "/interchange-ui.js", "/camera-io-ui.js", "/color-pipeline-ui.js", "/imaging-ui.js", "/deep-compositing-ui.js", "/ray-optics-ui.js", "/physical-rendering-ui.js", "/recovery-ui.js", "/production-ui.js", "/archive-ui.js", "/media-management-ui.js", "/editorial-ui.js", "/sequence-playback.js", "/decoded-frame-cache.js", "/managed-generation-ui.js", "/audio-routing.js", "/pcm-playback.js"}:
            return self.file(WEB / ("index.html" if parsed.path == "/" else parsed.path[1:]))
        if parts == ["api", "bootstrap"]:
            projects = self.store.projects()
            p = self.store.get(projects[0]["id"]) if projects else self.store.new_project({"name": "Untitled film"})
            durable_jobs = [job for job in self.store.jobs.values() if job.get("kind") not in EPHEMERAL_JOBS]
            return self.json(200, {"token": self.store.token, "project": p, "projects": self.store.projects(), "capabilities": self.store.capabilities(), "jobs": sorted(durable_jobs, key=lambda j: j["created_at"], reverse=True)[:30]})
        if parts == ["api", "capabilities"]:
            return self.json(200, self.store.capabilities(fresh=True))
        if parts == ["api", "imaging-capabilities"]:
            from imaging import imaging_capabilities
            return self.json(200, imaging_capabilities())
        if parts == ["api", "float-movie-capabilities"]:
            from float_movie import capabilities
            return self.json(200, capabilities())
        if parts == ["api", "retime-capabilities"]:
            from retime import capabilities
            return self.json(200, capabilities())
        if parts == ["api", "tapnext-capabilities"]:
            from learned_tracking import tapnext_capabilities
            return self.json(200, tapnext_capabilities())
        if parts == ["api", "learned-capabilities"]:
            from learned_tracking import learned_capabilities
            return self.json(200, learned_capabilities())
        if parts == ["api", "multicam-sync-capabilities"]:
            from multicam_sync import sync_capabilities
            return self.json(200, sync_capabilities())
        if len(parts) == 2 and parts[0] == "api" and parts[1] in {"deep-capabilities", "ray-optics-capabilities", "physical-rendering-capabilities", "scene-processing-capabilities", "reconstruction-capabilities"}:
            from studio_tools import capabilities
            tool = {"deep-capabilities": "deep-compositing", "ray-optics-capabilities": "ray-optics",
                    "physical-rendering-capabilities": "physical-rendering", "scene-processing-capabilities": "scene-processing",
                    "reconstruction-capabilities": "reconstruction"}[parts[1]]
            return self.json(200, capabilities(tool))
        if parts == ["api", "ray-optics-catalog"]:
            from ray_optics import ray_optics_catalog
            query = parse_qs(parsed.query)
            return self.json(200, ray_optics_catalog(query.get("q", [""])[0], int(query.get("limit", ["100"])[0])))
        if parts == ["api", "generation-runtime"]:
            return self.json(200, self.store.generation_runtime_status())
        if parts == ["api", "projects"]:
            return self.json(200, self.store.projects())
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            return self.json(200, self.store.job(parts[2]))
        if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
            project_id = parts[2]
            if len(parts) == 3:
                return self.json(200, self.store.get(project_id))
            if len(parts) == 4 and parts[3] == "recovery":
                return self.json(200, self.store.recovery(project_id))
            if len(parts) == 4 and parts[3] == "generation-readiness":
                return self.json(200, self.store.generation_readiness(project_id))
            if len(parts) == 4 and parts[3] == "media-inventory":
                return self.json(200, self.store.media_inventory(project_id))
            if len(parts) == 4 and parts[3] == "color-luts":
                return self.json(200, {"luts": list_luts(self.store.project_dir(project_id))})
            if len(parts) == 4 and parts[3] == "imaging-catalog":
                from imaging import imaging_catalog
                self.store.get(project_id)
                return self.json(200, imaging_catalog(parse_qs(parsed.query).get("config", [None])[0]))
            if len(parts) == 4 and parts[3] == "imaging-sources":
                from imaging import list_raw_sources
                return self.json(200, {"sources": list_raw_sources(self.store.project_dir(project_id))})
            if len(parts) == 4 and parts[3] == "deep-sources":
                from deep_compositing import list_deep_sources
                return self.json(200, {"sources": list_deep_sources(self.store.project_dir(project_id))})
            if len(parts) == 4 and parts[3] == "studio-results":
                from studio_tools import list_results
                return self.json(200, {"results": list_results(self.store, project_id)})
            if len(parts) in {4, 5} and parts[3] == "scene-dispatch":
                return self.json(200, self.store.scene_workers.status(project_id, parts[4] if len(parts) == 5 else None))
            if len(parts) == 4 and parts[3] == "collaboration":
                return self.json(200, self.store.collaboration.status(project_id))
            if len(parts) == 4 and parts[3] == "collaboration-members":
                from collaboration import Client
                binding = self.store.collaboration._binding(project_id)
                return self.json(200, Client(binding["connection"]).members())
            if len(parts) == 7 and parts[3] in {"deep", "optics", "physical", "learned", "scene-processing", "reconstruction"} and parts[4] == "outputs":
                from studio_tools import artifact
                path = artifact(self.store, project_id, parts[3], parts[5], parts[6])
                return self.file(path, download=path.suffix not in {".png", ".svg", ".mp4"} or "download" in parse_qs(parsed.query))
            if len(parts) == 7 and parts[3:5] == ["multicam-sync", "outputs"]:
                from multicam_sync import artifact
                path, identity = artifact(self.store.project_dir(project_id), parts[5], parts[6])
                return self.file(path, download=True, etag=identity["sha256"])
            if len(parts) == 7 and parts[3:5] == ["imaging", "outputs"]:
                if not IDENTIFIER.fullmatch(parts[5]) or parts[6] not in {"linear.exr", "display.png", "receipt.json", "motion.png"}:
                    raise ValueError("Invalid image processing artifact")
                root = self.store.project_dir(project_id) / "imaging" / "outputs"
                path = root / parts[5] / parts[6]
                if root.resolve() != self.store.project_dir(project_id).resolve() / "imaging" / "outputs" or path.resolve().parent != (root.resolve() / parts[5]) or path.parent.is_symlink():
                    raise ValueError("Image artifact is outside its owned output")
                return self.file(path, download=parts[6] != "display.png" or "download" in parse_qs(parsed.query))
            if len(parts) == 5 and parts[3] == "media":
                asset, path = self.store.asset(project_id, parts[4])
                return self.file(path, download=asset["kind"] == "scene")
            if len(parts) == 5 and parts[3] == "media-proxy":
                from media_management import proxy_file
                edge = int(parse_qs(parsed.query).get("long_edge", ["960"])[0])
                path, receipt = proxy_file(self.store.get(project_id), self.store.project_dir(project_id), parts[4], edge)
                return self.file(path)
            if len(parts) == 5 and parts[3] == "audio-source":
                from audio_source import source_file
                path, receipt = source_file(self.store.get(project_id), self.store.project_dir(project_id), parts[4])
                return self.file(path, etag=receipt["sha256"])
            if len(parts) == 5 and parts[3] == "thumbnail":
                return self.thumbnail(project_id, parts[4])
            if len(parts) == 5 and parts[3] == "waveform":
                values = parse_qs(parsed.query)
                bins = int(values.get("bins", ["512"])[0])
                stream_index = int(values["stream_index"][0]) if "stream_index" in values else None
                if ("left" in values) != ("right" in values):
                    raise ValueError("Choose both source audio channels for the waveform")
                channels = [int(values["left"][0]), int(values["right"][0])] if "left" in values else None
                return self.json(200, self.store.waveform(project_id, parts[4], bins, stream_index, channels))
            if len(parts) == 5 and parts[3] == "previews":
                if not re.fullmatch(r"[a-f0-9]{64}\.png", parts[4]):
                    raise ValueError("Invalid frame preview filename")
                return self.file(self.store.project_dir(project_id) / "previews" / parts[4])
            if len(parts) == 5 and parts[3] == "exports":
                if not re.fullmatch(r"[a-f0-9]{32}(\.(mp4|mov|mkv|json|blend|otio|fcpxml|zip|srt|vtt|cinematicum\.zip)|-shot-plan\.json)", parts[4]):
                    raise ValueError("Invalid export filename")
                return self.file(self.store.project_dir(project_id) / "exports" / parts[4], download=parts[4].endswith((".blend", ".otio", ".fcpxml", ".mkv", ".zip", ".srt", ".vtt", "-shot-plan.json")) or "download" in parse_qs(parsed.query))
            if len(parts) == 5 and parts[3] == "analysis":
                if not re.fullmatch(r"[a-f0-9]{32}\.(png|json)", parts[4]):
                    raise ValueError("Invalid analysis filename")
                return self.file(self.store.project_dir(project_id) / "analysis" / parts[4], download="download" in parse_qs(parsed.query))
        raise FileNotFoundError("Route does not exist")

    def dispatch_write(self):
        parsed = urlparse(self.path)
        parts = unquote(parsed.path).strip("/").split("/")
        if self.command == "POST" and parts == ["api", "prepare-quit"]:
            return self.json(200, self.store.prepare_quit(self.body()))
        if self.command == "POST" and len(parts) == 3 and parts[:2] == ["api", "scene-workers"]:
            if parts[2] not in {"start", "pair", "invite", "revoke", "stop"}:
                raise FileNotFoundError("Unknown scene-worker operation")
            return self.json(200, getattr(self.store.scene_workers, parts[2])(self.body()))
        query = parse_qs(parsed.query)
        if self.command == "POST" and parts == ["api", "projects"]:
            return self.json(201, self.store.new_project(self.body()))
        if self.command == "POST" and len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
            return self.json(200, self.store.cancel(parts[2]))
        if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
            project_id = parts[2]
            directory = self.store.project_dir(project_id)
            if self.command == "POST" and len(parts) == 6 and parts[3] == "scene-dispatch":
                return self.json(202, self.store.scene_workers.control(project_id, parts[4], parts[5], self.body()))
            if self.command == "POST" and len(parts) == 5 and parts[3] == "runtime-management":
                from runtime_management import validate_request, run
                runtime_id = parts[4]
                request = validate_request(runtime_id, self.body())
                def setup(job_id, progress, event):
                    result = run(runtime_id, request, progress=progress, cancel_event=event)
                    with self.store.lock:
                        self.store._cap_cache = None
                    return result
                job = self.store.submit(project_id, "runtime-setup", setup,
                                        {"runtime_id": runtime_id, **request})
                return self.json(202, job)
            if self.command == "PUT" and len(parts) == 3:
                return self.json(200, self.store.save(project_id, self.body()))
            if self.command == "POST" and len(parts) == 5 and parts[3:] == ["scene", "import-obj"]:
                return self.json(200, import_obj(self.body()))
            if self.command == "POST" and len(parts) == 5 and parts[3:] == ["scene", "import-camera"]:
                project = self.store.get(project_id)
                return self.json(200, import_camera(self.body(), width=project["width"], height=project["height"]))
            if self.command == "POST" and len(parts) == 5 and parts[3:] == ["scene", "model-mesh"]:
                return self.json(202, self.store.model_mesh(project_id, self.body()))
            if self.command != "POST" or len(parts) != 4:
                raise FileNotFoundError("Route does not exist")
            action = parts[3]
            if action == "lensfun-import":
                from lens_geometry import parse_lensfun_xml
                payload = self.body(768 * 1024)
                if not isinstance(payload, dict) or set(payload) != {"text"}:
                    raise ValueError("Lensfun import accepts the selected XML text only.")
                return self.json(200, parse_lensfun_xml(payload["text"]))
            if action == "checkpoint":
                return self.json(200, self.store.checkpoint(project_id, self.body()))
            if action == "recovery":
                return self.json(200, self.store.recovery(project_id, self.body()))
            if action in {"production-review", "production-plan", "production-conform", "production-export"}:
                from production import review_plan, prepare_plan, conform_plan, export_plan
                payload = self.body()
                project = self.store.analysis_snapshot(project_id, payload)
                if action == "production-export":
                    result = export_plan(project)
                    output = directory / "exports" / (uuid.uuid4().hex + "-shot-plan.json")
                    atomic_json(output, result["document"])
                    result.update(url=f"/api/projects/{project_id}/exports/{output.name}?download=1",
                                  filename=output.name, sha256=digest_file(output))
                    return self.json(200, result)
                operation = {"production-review": review_plan, "production-plan": prepare_plan,
                             "production-conform": conform_plan}[action]
                options = {"replace_format": payload.get("replace_format", False)} if action == "production-conform" else {}
                return self.json(200, operation(payload.get("document"), project, directory,
                                               payload.get("bindings"), **options))
            if action == "archive-export":
                return self.json(202, self.store.archive_export(project_id, self.body()))
            if action == "archive-restore":
                from project_archive import MAX_BYTES
                if self.headers.get_content_type() != "application/octet-stream":
                    raise ValueError("Expected a selected archive file as application/octet-stream")
                length = self.length(MAX_BYTES)
                incoming = directory / ("archive-upload-" + uuid.uuid4().hex + ".zip")
                submitted = False
                try:
                    with incoming.open("xb") as target:
                        remaining = length
                        while remaining:
                            block = self.rfile.read(min(1024 * 1024, remaining))
                            if not block:
                                raise ValueError("Project archive upload was interrupted")
                            target.write(block)
                            remaining -= len(block)
                        target.flush()
                        os.fsync(target.fileno())
                    job = self.store.archive_restore(project_id, incoming)
                    submitted = True
                    return self.json(202, job)
                finally:
                    if not submitted:
                        incoming.unlink(missing_ok=True)
            if action == "imaging-raw-import":
                from imaging import import_raw_source
                length = self.length(min(MAX_UPLOAD, 512 * 1024 * 1024))
                name = safe_name(query.get("name", ["camera.dng"])[0])
                with tempfile.TemporaryDirectory(prefix="raw-upload-", dir=str(directory)) as temp:
                    incoming = Path(temp) / name
                    with incoming.open("xb") as f:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("RAW upload was interrupted")
                            f.write(chunk)
                            remaining -= len(chunk)
                    with self.store.lock:
                        self.store._require_open()
                        result = import_raw_source(directory, incoming, name)
                return self.json(201, result)
            if action == "deep-import":
                from studio_tools import import_deep
                if self.headers.get_content_type() != "application/octet-stream":
                    raise ValueError("Expected a selected OpenEXR file as application/octet-stream")
                length = self.length(min(MAX_UPLOAD, 1024 * 1024 * 1024))
                name = safe_name(query.get("name", ["source.exr"])[0])
                if Path(name).suffix.lower() != ".exr":
                    raise ValueError("Deep source import requires an OpenEXR file")
                with tempfile.TemporaryDirectory(prefix="deep-upload-", dir=str(directory)) as temp:
                    incoming = Path(temp) / name
                    with incoming.open("xb") as target:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("OpenEXR upload was interrupted")
                            target.write(chunk)
                            remaining -= len(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    result = import_deep(self.store, project_id, incoming, name)
                return self.json(201, result)
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
            if action == "media-relink":
                if self.headers.get_content_type() != "application/octet-stream":
                    raise ValueError("Expected the selected original as application/octet-stream")
                length = self.length(MAX_UPLOAD)
                asset_id = query.get("asset_id", [""])[0]
                from media_management import asset_record
                asset = asset_record(self.store.get(project_id), asset_id)
                tmp = directory / ("relink-upload-" + uuid.uuid4().hex + Path(asset["path"]).suffix)
                try:
                    with tmp.open("xb") as stream:
                        remaining = length
                        while remaining:
                            block = self.rfile.read(min(1024 * 1024, remaining))
                            if not block:
                                raise ValueError("Original-media upload was interrupted.")
                            stream.write(block)
                            remaining -= len(block)
                        stream.flush()
                        os.fsync(stream.fileno())
                    return self.json(200, self.store.media_relink(project_id, asset_id, tmp))
                finally:
                    tmp.unlink(missing_ok=True)
            if action == "workflow":
                graph = self.body()
                workflow = validate_workflow(graph)
                with self.store.lock:
                    self.store._require_open()
                    atomic_json(directory / "workflow.json", workflow)
                return self.json(201, {"workflow_path": "workflow.json"})
            payload = self.body(32 * 1024 * 1024 if action == "color-lut-import" else MAX_JSON)
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            if action in {"collaboration-create", "collaboration-join", "collaboration-sync", "collaboration-invite",
                          "collaboration-undo", "collaboration-leave", "collaboration-resume", "collaboration-revoke"}:
                operation = getattr(self.store.collaboration, action.removeprefix("collaboration-"))
                return self.json(200, operation(project_id, payload))
            if action == "color-lut-import":
                if set(payload) != {"text"}:
                    raise ValueError("LUT import accepts selected .cube text only.")
                with self.store.lock:
                    self.store._require_open()
                    lut = import_cube(payload["text"], directory)
                return self.json(201, {"lut": lut})
            if action == "render":
                return self.json(202, self.store.render(project_id, payload))
            if action == "generate":
                return self.json(202, self.store.generation(project_id, payload))
            if action in {"generation-setup", "generation-start"}:
                return self.json(202, self.store.generation_runtime_job(project_id, action.split("-", 1)[1], payload))
            if action == "generation-stop":
                if payload:
                    raise ValueError("Generation stop accepts an empty options object")
                return self.json(200, self.store.generation_runtime_stop())
            if action == "generation-workflow":
                return self.json(201, self.store.generation_default_workflow(project_id, payload))
            if action == "media-proxy":
                return self.json(202, self.store.media_proxy(project_id, payload))
            if action == "audio-source":
                result = self.store.audio_source(project_id, payload)
                return self.json(202 if "job" in result else 200, result)
            if action == "editorial":
                return self.json(200, self.store.editorial(project_id, payload))
            if action in {"multicam-sync", "multicam-sync-apply"}:
                from multicam_sync import submit_analysis, apply_plan
                return self.json(202 if action == "multicam-sync" else 200,
                                 (submit_analysis if action == "multicam-sync" else apply_plan)(self.store, project_id, payload))
            if action == "blender":
                return self.json(202, self.store.blender(project_id, payload))
            if action == "scene":
                return self.json(202, self.store.scene_render(project_id, payload))
            if action == "imaging-render":
                return self.json(202, self.store.imaging_render(project_id, payload))
            if action in {"deep-render", "ray-optics", "physical-rendering", "scene-processing", "reconstruction"}:
                from studio_tools import run_tool
                tool = "deep-compositing" if action == "deep-render" else action
                return self.json(202, run_tool(self.store, project_id, tool, payload))
            if action == "scene-dispatch":
                return self.json(202, self.store.scene_workers.submit(project_id, payload))
            if action == "authoring-apply":
                from studio_tools import apply_document
                return self.json(200, apply_document(self.store, project_id, payload))
            if action in {"learned-track", "learned-apply-plan"}:
                from learned_tools import track, apply_plan
                result = (track if action == "learned-track" else apply_plan)(self.store, project_id, payload)
                return self.json(202 if action == "learned-track" else 200, result)
            if action == "learned-frame":
                return self.json(202, self.store.tracking(project_id, payload, seed_only=True, learned_seed=True))
            if action == "frame-preview":
                return self.json(202, self.store.frame_preview(project_id, payload))
            if action in {"tracking-frame", "tracking"}:
                return self.json(202, self.store.tracking(project_id, payload, seed_only=action == "tracking-frame"))
            if action == "tracking-setup":
                return self.json(202, self.store.tracking_setup(project_id, payload))
            if action in {"tracking-motion", "tracking-validate"}:
                return self.json(200, self.store.tracking_plan(project_id, payload, motion=action == "tracking-motion"))
            if action in {"interchange-export", "interchange-import", "interchange-inspect"}:
                return self.json(200, self.store.interchange(project_id, payload, importing=action == "interchange-import", inspecting=action == "interchange-inspect"))
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
        except CollaborationError as exc:
            self.json(exc.status, exc.as_dict())
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
    parser.add_argument("--profile", choices=["preview", "h264", "prores", "master16", "master32"], default="h264")
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
        if not store._closing:
            store.shutdown_reason = "signal:" + signal.Signals(signum).name
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        store.shutdown_reason = "signal:SIGINT"
    finally:
        httpd.server_close()
        store.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

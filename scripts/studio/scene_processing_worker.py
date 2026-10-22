#!/usr/bin/env python3
"""One owned scene render. Parent EOF cancels its actual renderer process.

Invoked only by scene_dispatch with private owned paths. This is not an HTTP or
arbitrary command endpoint. A per-job lease prevents a restarted authority from
overlapping a still-settling previous attempt.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import _cancelled, find_blender
from scene import render_scene
from scene_processing import _hash_file, _write_json, canonical_bytes


def main():
    if sys.argv[1:] != ["--owned-render"]:
        raise ValueError("Use the owned render supervisor.")
    packet = json.loads(sys.stdin.buffer.readline(9 * 1024 * 1024))
    if not isinstance(packet, dict) or set(packet) != {"version", "request", "directory", "lease"} or packet["version"] != 1:
        raise ValueError("Invalid owned render packet.")
    directory, lease = Path(packet["directory"]), Path(packet["lease"])
    if not directory.is_absolute() or not lease.is_absolute() or directory.parent.parent != lease.parent:
        raise ValueError("Owned render paths are inconsistent.")
    if any(part.is_symlink() for part in (directory, directory.parent, directory.parent.parent, lease)):
        raise ValueError("Owned render paths cannot be symlinks.")
    directory.mkdir(mode=0o700)
    lock = os.open(lease, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cancelled = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: cancelled.set())

    def parent_watch():
        # The one request line has already been consumed. An explicit cancel or
        # EOF (including a crashed supervisor) always interrupts the owned job.
        # Raw descriptor IO holds no Python buffered-stream lock during
        # interpreter shutdown. A blocked daemon BufferedReader would abort a
        # successful child while its parent intentionally retains the pipe.
        os.read(sys.stdin.fileno(), 256)
        cancelled.set()
    threading.Thread(target=parent_watch, daemon=True, name="scene-parent-liveness").start()
    def emit(value):
        sys.stdout.buffer.write(canonical_bytes(value) + b"\n"); sys.stdout.buffer.flush()
    try:
        from scene_dispatch import validate_render_request
        request = validate_render_request(packet["request"])
        _cancelled(cancelled)
        engine = find_blender()
        if not engine: raise ValueError("Actual Blender is required for scene worker rendering.")
        version = subprocess.run([str(engine), "--version"], capture_output=True, text=True, timeout=20, check=True).stdout
        started_epoch, started_clock = time.time(), time.monotonic()
        rendered = render_scene(request["scene"], directory / "scratch", fps=request["context"]["fps"], frame_start=1, frame_end=1,
                                progress=lambda value: emit({"progress": value}), cancel_event=cancelled)
        _cancelled(cancelled)
        published = directory / "published"; published.mkdir(mode=0o700)
        for key, filename in (("path", "preview.mp4"), ("scene_path", "authored.blend"), ("masters_path", "linear-masters.zip")):
            if key in rendered:
                shutil.move(rendered[key], published / filename); os.chmod(published / filename, 0o600)
        _write_json(published / "scene.json", request["scene"])
        artifacts = [{"filename": path.name, "size": path.stat().st_size, "sha256": _hash_file(path)} for path in sorted(published.iterdir())]
        receipt = {"format": "CINEMATICUM_SCENE_WORKER_RESULT", "version": 1, "operation": "scene_render",
                   "graph_sha256": request["graph_sha256"], "context_sha256": request["context_sha256"],
                   "scene_sha256": request["scene_sha256"], "context": request["context"],
                   "renderer": rendered["provenance"], "engine_version": version.splitlines()[0],
                   "engine_build": next((line.strip() for line in version.splitlines() if "build hash:" in line), None),
                   "execution": {"started": started_epoch, "finished": time.time(), "elapsed": time.monotonic() - started_clock},
                   "artifacts": artifacts, "issuance_effect": "NONE"}
        _write_json(published / "receipt.json", receipt)
        artifacts = [*artifacts, {"filename": "receipt.json", "size": (published / "receipt.json").stat().st_size,
                                 "sha256": _hash_file(published / "receipt.json")}]
        _cancelled(cancelled)
        emit({"result": {"receipt": receipt, "artifacts": artifacts}})
    except Exception as exc:
        emit({"error": str(exc)[:4000], "cancelled": cancelled.is_set()})
        return 2 if cancelled.is_set() else 1
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN); os.close(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

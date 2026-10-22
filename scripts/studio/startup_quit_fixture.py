#!/usr/bin/env python3
"""Isolated ENGINE TEST server with explicit startup barriers and real workers.

Only the test transport waits at a response boundary. Production Handler,
Store, authentication, project saving, render workers and graceful shutdown
remain unchanged. RELEASE on owned stdin opens the barrier; EOF closes only
this fixture. Nothing in this file is installed in the application runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

from server import Handler, Server, Store


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--phase", choices=("app-script", "bootstrap", "protection", "normal"), required=True)
    parser.add_argument("--port", default=0, type=int)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    if args.workspace.exists():
        raise ValueError("A fresh isolated fixture workspace is required")
    store = Store(args.workspace)
    httpd = None
    release = threading.Event()
    event_lock = threading.Lock()
    gate_path = {"app-script": "/app.js", "bootstrap": "/api/bootstrap"}.get(args.phase)
    events = []

    def record(kind, **values):
        with event_lock:
            events.append({"event": kind, "at": time.time(), **values})
            write(args.evidence / "transport-events.json", events)

    class FixtureHandler(Handler):
        def dispatch_get(self):
            if urlparse(self.path).path == gate_path:
                record("barrier-entered", path=gate_path)
                print("ENGINE_TEST_GATE: " + args.phase, flush=True)
                if not release.wait(12):
                    raise ValueError("The explicit ENGINE TEST response barrier was not released")
                record("barrier-released", path=gate_path)
            return super().dispatch_get()

        def body(self, *args, **kwargs):
            value = super().body(*args, **kwargs)
            if urlparse(self.path).path == "/api/prepare-quit":
                self.quit_payload = value
            return value

        def json(self, status, body):
            route = urlparse(self.path).path
            if route == "/api/prepare-quit":
                record("quit-response", status=status,
                       authenticated=self.headers.get("X-Cinematicum-Token") == store.token,
                       decision=getattr(self, "quit_payload", None), response=body)
            elif self.command == "PUT" and route.startswith("/api/projects/"):
                record("save-response", status=status,
                       revision=body.get("revision") if isinstance(body, dict) else None)
            return super().json(status, body)

    try:
        project = store.new_project({"name": "ENGINE TEST — startup quit", "fps": 12,
                                     "width": 640, "height": 360})
        fixture = {"project_id": project["id"], "phase": args.phase, "engine_test_only": True}
        if args.phase == "protection":
            from test_high_precision import numeric_ramp, rgba16_bytes, WIDTH, HEIGHT
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise ValueError("Actual FFmpeg is required")
            source = args.evidence / "ENGINE_TEST_quit_source.png"
            subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-f", "rawvideo",
                            "-pixel_format", "rgba64le", "-video_size", f"{WIDTH}x{HEIGHT}", "-i", "pipe:0",
                            "-frames:v", "1", "-c:v", "png", "-pix_fmt", "rgba64be", "-threads", "1",
                            "-update", "1", str(source)], input=rgba16_bytes(numeric_ramp()),
                           capture_output=True, check=True, timeout=10)
            upload = args.evidence / "ENGINE_TEST_upload.png"
            shutil.copyfile(source, upload)
            asset = store.admit(project["id"], upload, source.name)
            project = store.get(project["id"])
            project["settings"].update(image_precision="high16", transparent_background=False)
            project["clips"] = [{"id": "quit_test_picture", "asset_id": asset["id"], "track": 0,
                                 "start": 0, "in": 0, "duration": 48, "scale": .73,
                                 "rotation": 27, "x": .07, "y": -.09}]
            project = store.save(project["id"], project)
            fixture["source"] = {"asset_id": asset["id"], "path": asset["path"],
                                 "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        # Inspect the real installed engines before opening the measured page;
        # this is the production capability calculation, not a substituted one.
        store.capabilities()
        httpd = Server(args.port, store)
        httpd.RequestHandlerClass = FixtureHandler
        fixture["url"] = f"http://127.0.0.1:{httpd.server_port}"
        write(args.evidence / "fixture.json", fixture)
        write(args.evidence / "initial-project.json", project)

        def stop(signum=None, frame=None):
            release.set()
            if not store._closing:
                store.shutdown_reason = "ENGINE_TEST-cleanup" if signum is None else "signal:" + signal.Signals(signum).name
            threading.Thread(target=httpd.shutdown, daemon=True).start()

        def commands():
            for line in sys.stdin:
                if line.strip() == "RELEASE":
                    record("release-command")
                    release.set()
                elif line.strip() == "EXIT":
                    stop()
                    return
                else:
                    record("invalid-test-command")
                    stop()
                    return
            stop()

        signal.signal(signal.SIGTERM, stop)
        threading.Thread(target=commands, daemon=True).start()
        print("CINEMATICUM editor: " + fixture["url"], flush=True)
        print("ENGINE_TEST_FIXTURE: " + json.dumps(fixture), flush=True)
        httpd.serve_forever(poll_interval=.02)
    finally:
        release.set()
        if httpd:
            httpd.server_close()
        store.shutdown()


if __name__ == "__main__":
    main()

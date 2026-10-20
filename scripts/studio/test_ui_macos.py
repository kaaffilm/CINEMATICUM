#!/usr/bin/env python3
"""Real WKWebView integration test on macOS, with synthetic TEST media only.

Compile the helper separately, then run this harness:
  xcrun swiftc scripts/studio/macos/SmokeTest.swift -o /tmp/cinematicum-webkit-smoke
  python3 scripts/studio/test_ui_macos.py --binary /tmp/cinematicum-webkit-smoke

The helper drives the shipped UI. This harness independently checks its saved
project and decodes the real exported file. It does not contact paid providers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from engine import probe_media
from server import Server, Store


def run(binary, evidence):
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST SIGNALS — NOT A FILM", "checks": {}}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cinematicum-webkit-TEST-workspace-") as scratch:
        scratch = Path(scratch)
        store = Store(scratch / "workspace")
        server = None
        thread = None
        try:
            project = store.new_project({"name": "ENGINE TEST — Synthetic browser fixture", "fps": 12, "width": 160, "height": 90})
            fixture = scratch / "ENGINE_TEST_ONLY_source.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=12:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-threads", "1",
                "-c:a", "aac", "-t", "1", str(fixture),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
            store.admit(project["id"], fixture, "ENGINE_TEST_ONLY_source.mp4")
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            thread.start()
            screenshot = evidence / "ENGINE_TEST_webkit.png"
            command = [str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}", "--output", str(screenshot), "--timeout", "14"]
            process = subprocess.run(command, capture_output=True, text=True, timeout=18)
            ui = None
            for line in reversed(process.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict) and "passed" in candidate:
                        ui = candidate
                        break
                except ValueError:
                    continue
            if ui is None:
                raise RuntimeError("WebKit helper returned no JSON result: " + (process.stderr or process.stdout)[-3000:])
            result["ui"] = ui
            result["helper_exit_code"] = process.returncode
            if process.stderr.strip():
                result["helper_stderr_tail"] = process.stderr[-1800:]
            result["checks"]["native_ui_passed"] = ui.get("passed") is True and process.returncode == 0
            saved = store.get(project["id"])
            result["checks"]["one_clip_saved"] = len(saved["clips"]) == 1 and saved["clips"][0]["duration"] == 12
            result["checks"]["exposure_saved"] = bool(saved["clips"]) and saved["clips"][0].get("grade", {}).get("exposure") == .75
            result["checks"]["raster_title_saved"] = len(saved["titles"]) == 1 and bool(saved["titles"][0].get("asset_id")) and saved["titles"][0]["text"] == "ENGINE TEST"
            jobs = [j for j in store.jobs.values() if j["project_id"] == project["id"] and j["kind"] == "render"]
            completed = [j for j in jobs if j["state"] == "completed"]
            result["checks"]["real_render_completed"] = len(completed) == 1
            if completed:
                job = completed[0]
                media = store.project_dir(project["id"]) / "exports" / job["result"]["filename"]
                metadata = probe_media(media)
                result["media"] = metadata
                result["checks"]["export_frame_count"] = metadata["frames"] == 12
                result["checks"]["export_picture_and_audio"] = metadata["width"] == 160 and metadata["height"] == 90 and metadata["has_audio"] and abs(metadata["duration"] - 1) < .1
                result["checks"]["browser_played_actual_export"] = ui.get("video_src") == job["result"]["url"] and ui.get("video_current_time", 0) > .05
                subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(media), "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5)
                result["checks"]["export_decodes"] = True
                export_copy = evidence / "ENGINE_TEST_export.mp4"
                shutil.copy2(media, export_copy)
                result["export"] = str(export_copy)
            valid_snapshot = False
            if screenshot.is_file() and screenshot.stat().st_size > 1000:
                with screenshot.open("rb") as image:
                    valid_snapshot = image.read(8) == b"\x89PNG\r\n\x1a\n"
            result["checks"]["webkit_snapshot"] = valid_snapshot
            result["screenshot"] = str(screenshot) if screenshot.is_file() else None
            result["passed"] = bool(result["checks"]) and all(result["checks"].values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(k for k, value in result["checks"].items() if not value)
            (evidence / "ENGINE_TEST_saved_project.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
        except Exception as exc:
            result["error"] = str(exc)
            if isinstance(exc, subprocess.CalledProcessError):
                error = exc.stderr or b""
                result["process_error"] = (error.decode(errors="replace") if isinstance(error, bytes) else error)[-3000:]
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=1)
            store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["evidence_directory"] = str(evidence)
    (evidence / "ENGINE_TEST_report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run real native WebKit editing and export verification on macOS")
    parser.add_argument("--binary", type=Path, help="Previously compiled SmokeTest.swift executable")
    parser.add_argument("--output", type=Path, help="Folder for screenshot, test export, and JSON evidence")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Native WKWebView test requires macOS; use engine/server tests on this platform."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift separately and pass its executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-webkit-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Native WKWebView acceptance for CINEMATICUM's own animated node controls.

Uses one disposable synthetic source and workspace. The DOM script authors
independent curves and a polygon gesture, seeks, undoes/redoes, splits/trims,
renders and plays. Python inspects saved data and independently decodes the
actual before/after PNGs and exported movie. No user project is opened.

  python3 test_compositor_animation_ui_macos.py --binary /tmp/cinematicum-smoke
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from server import Server, Store
from test_editing_ui_macos import close, read_helper_result


HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS, FRAMES, PAUSED_FRAME = 160, 90, 12, 24, 12
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def saved_checks(project, ui):
    checks = {}
    clips = sorted(project.get("clips", []), key=lambda clip: clip["start"])
    checks["two_clips_from_native_split"] = len(clips) == 2
    if len(clips) != 2:
        return checks
    left, right = clips
    checks["left_clip_source_range"] = left["id"] == ui.get("original_clip_id") and left["start"] == 0 and left["duration"] == 8 and left["in"] == 0
    checks["right_clip_leading_trim"] = right["id"] == ui.get("right_clip_id") and right["start"] == 11 and right["duration"] == 13 and right["in"] == 11
    checks["original_animation_domain_preserved"] = all(clip.get("animation_duration") == 24 and clip.get("animation_start", 0) == 0 for clip in clips) and left.get("animation_offset", 0) == 0 and right.get("animation_offset") == 11
    checks["split_copies_identical_node_curves"] = left.get("compositor") == right.get("compositor")
    recipe = right.get("compositor", {})
    nodes = {node["id"]: node for node in recipe.get("nodes", [])}
    grade, mask = nodes.get(ui.get("grade_id"), {}), nodes.get(ui.get("mask_id"), {})
    source = next((node for node in nodes.values() if node["type"] == "source"), {})
    checks["source_grade_mask_graph_connected"] = len(nodes) == 3 and grade.get("inputs") == [source.get("id")] and mask.get("inputs") == [grade.get("id")] and recipe.get("output") == mask.get("id")
    exposure = grade.get("animation", {}).get("exposure", [])
    xpos = mask.get("animation", {}).get("x", [])
    points = mask.get("animation", {}).get("points", [])
    checks["independent_channels_retain_original_key_times"] = all([key["frame"] for key in keys] == [0, 16] for keys in (exposure, xpos, points))
    if len(exposure) == len(xpos) == len(points) == 2:
        checks["exposure_easing_saved"] = exposure[0]["interpolation"] == "ease_out" and close(exposure[0]["value"], 0) and close(exposure[1]["value"], 1)
        checks["mask_easing_saved"] = xpos[0]["interpolation"] == "ease_in_out" and close(xpos[0]["value"], .25) and close(xpos[1]["value"], .75)
        checks["polygon_gesture_saved_with_stable_topology"] = all(len(key["value"]) == 3 for key in points) and close(points[0]["value"][1][0], .5) and close(points[0]["value"][1][1], .1) and close(points[1]["value"][1][0], .7, .00001) and close(points[1]["value"][1][1], .2, .00001)
    checks["no_unrequested_media_or_titles"] = len(project["assets"]) == 1 and not project.get("titles")
    return checks


def run(binary, evidence):
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    began, result = time.monotonic(), {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST — NOT FILM FOOTAGE", "checks": {}}
    deadline, checks = began + 18.5, result["checks"]

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining < .1:
            raise TimeoutError("The isolated compositor animation acceptance exceeded its time budget.")
        return min(maximum, remaining)

    def command(arguments, maximum=4):
        return subprocess.run(arguments, check=True, capture_output=True, timeout=budget(maximum))

    with tempfile.TemporaryDirectory(prefix="cinematicum-animation-ENGINE-TEST-") as temporary:
        scratch = Path(temporary)
        store = server = thread = None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("FFmpeg and ffprobe are required for actual media acceptance.")
            fixture = scratch / "ENGINE_TEST_ONLY_animation_source.mp4"
            command([ffmpeg, "-v", "error", "-nostdin", "-y", "-threads", "1", "-f", "lavfi", "-i",
                     "testsrc2=size=160x90:rate=12:duration=2", "-c:v", "libx264", "-preset", "ultrafast",
                     "-pix_fmt", "yuv420p", "-threads", "1", "-an", str(fixture)])
            original_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
            store = Store(scratch / "workspace")
            project = store.new_project({"name": "ENGINE TEST — animated compositor", "fps": FPS, "width": WIDTH, "height": HEIGHT})
            admitted = store.admit(project["id"], fixture, fixture.name)
            admitted_media = store.project_dir(project["id"]) / admitted["path"]
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            screenshot = evidence / "ENGINE_TEST_animation_webkit.png"
            native_timeout = budget(13.6, reserve=2.3)
            native = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}/",
                                     "--output", str(screenshot), "--timeout", str(round(native_timeout, 2)),
                                     "--script", str(HERE / "macos" / "CompositorAnimationSmoke.js")],
                                    capture_output=True, text=True, timeout=budget(native_timeout + .7))
            ui = read_helper_result(native)
            result["ui"], result["helper_exit_code"] = ui, native.returncode
            (evidence / "ENGINE_TEST_ui.json").write_text(json.dumps(ui, indent=2), encoding="utf-8")
            checks["native_dom_acceptance_passed"] = ui.get("passed") is True and native.returncode == 0
            checks["no_browser_errors"] = not ui.get("page_errors", [])
            checks["bounded_native_runtime"] = ui.get("elapsed_ms", 99999) < 14000
            if native.stderr:
                result["helper_stderr_tail"] = native.stderr[-1600:]
            saved, directory = store.get(project["id"]), store.project_dir(project["id"])
            (evidence / "ENGINE_TEST_saved_project.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
            checks.update(saved_checks(saved, ui))
            with store.lock:
                jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
            pictures = {}
            for name in ("before", "after"):
                requested = ui.get(name + "_frame", {})
                found = [job for job in jobs if job["kind"] == "frame-preview" and job["state"] == "completed" and job.get("result", {}).get("url") == requested.get("url")]
                checks[name + "_png_from_completed_graph_job"] = bool(found) and requested.get("frame") == PAUSED_FRAME
                if not found:
                    continue
                receipt = found[-1]["result"]
                picture = directory / "previews" / Path(urlsplit(receipt["url"]).path).name
                payload = picture.read_bytes()
                checks[name + "_png_verified_receipt"] = payload.startswith(PNG_SIGNATURE) and hashlib.sha256(payload).hexdigest() == receipt.get("sha256") and receipt.get("pipeline") == "timeline-export-graph"
                pictures[name] = command([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(picture),
                                          "-frames:v", "1", "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
                shutil.copy2(picture, evidence / ("ENGINE_TEST_" + name + "_frame_12.png"))
            frame_bytes = WIDTH * HEIGHT * 3
            checks["trim_and_split_preserve_decoded_picture_exactly"] = set(pictures) == {"before", "after"} and len(pictures["before"]) == frame_bytes and pictures["before"] == pictures["after"]
            completed = [job for job in jobs if job["kind"] == "render" and job["state"] == "completed"]
            checks["one_completed_movie_export"] = len(completed) == 1
            if completed:
                receipt = completed[-1]["result"]
                movie = directory / "exports" / receipt["filename"]
                metadata = probe_media(movie)
                result["media"] = metadata
                checks["actual_export_format"] = metadata["width"] == WIDTH and metadata["height"] == HEIGHT and metadata["frames"] == FRAMES and metadata["has_audio"]
                checks["webkit_plays_that_movie"] = ui.get("video_src") == receipt["url"] and ui.get("video_time", 0) > .06
                pixels = command([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(movie), "-map", "0:v:0", "-an",
                                  "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
                frames = [pixels[at:at + frame_bytes] for at in range(0, len(pixels), frame_bytes)]
                checks["all_frames_decode"] = len(frames) == FRAMES and len(pixels) == FRAMES * frame_bytes
                checks["trimmed_gap_is_black"] = len(frames) == FRAMES and all(max(frames[i]) <= 3 for i in (8, 9, 10))
                checks["animated_export_changes"] = len({hashlib.sha256(frame).digest() for frame in frames}) >= 16
                if "after" in pictures and len(frames) == FRAMES:
                    error = sum(abs(a - b) for a, b in zip(pictures["after"], frames[PAUSED_FRAME])) / frame_bytes
                    checks["displayed_png_matches_decoded_movie_frame"] = error < 10
                    result["paused_vs_export_mean_rgb_error"] = round(error, 5)
                shutil.copy2(movie, evidence / "ENGINE_TEST_animated_export.mp4")
            checks["source_unchanged"] = (admitted["sha256"] == original_hash
                and any(asset["id"] == admitted["id"] and asset["path"] == admitted["path"]
                        and asset["sha256"] == original_hash for asset in saved["assets"])
                and hashlib.sha256(admitted_media.read_bytes()).hexdigest() == original_hash)
            checks["actual_native_screenshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == PNG_SIGNATURE
            result["jobs"] = [{"kind": job["kind"], "state": job["state"], **({"error": job["error"]} if job.get("error") else {})} for job in jobs]
            if not all(checks.values()):
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(key for key, passed in checks.items() if not passed)
        except Exception as exc:
            result["error"] = str(exc)
            checks["completed_without_fixture_error"] = False
            if isinstance(exc, subprocess.CalledProcessError):
                result["process_error"] = (exc.stderr or b"").decode(errors="replace")[-2000:]
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=.2)
            if store is not None:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["bounded_whole_run"] = result["elapsed_seconds"] < 19
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    result["evidence_directory"] = str(evidence)
    (evidence / "ENGINE_TEST_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Real native WK node animation, mask, undo/redo, trim and movie acceptance")
    parser.add_argument("--binary", type=Path, help="Previously compiled macos/SmokeTest.swift executable")
    parser.add_argument("--output", type=Path, help="Destination for actual PNG/movie/project evidence")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual WKWebView acceptance requires macOS; no UI or media results are simulated."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and pass the executable using --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-animation-ENGINE-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

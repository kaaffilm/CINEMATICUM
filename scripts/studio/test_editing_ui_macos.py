#!/usr/bin/env python3
"""Real WK editing/compositor acceptance with a disposable synthetic project.

Compile macos/SmokeTest.swift separately. Each invocation uses shipped controls,
one actual render, and independent saved-recipe/pixel/PCM checks. It neither
opens a user's workspace nor invokes providers or an external editor UI.

  python3 test_editing_ui_macos.py --binary /tmp/cinematicum-smoke --profile h264
  python3 test_editing_ui_macos.py --binary /tmp/cinematicum-smoke --profile preview

The separate profiles keep each native helper below 14 seconds and the normal
whole invocation below 18 seconds. Slow machines fail with bounded diagnostics;
they never substitute mocked browser or render results.
"""
from __future__ import annotations

import argparse
from array import array
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from server import Server, Store


WIDTH, HEIGHT, FPS, FRAMES, PAUSED_FRAME = 160, 90, 12, 8, 3
HERE = Path(__file__).resolve().parent
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def close(a, b, tolerance=1e-8):
    return isinstance(a, (float, int)) and not isinstance(a, bool) and abs(a - b) <= tolerance


def waveform_points(wave, clip):
    """Independent geometry from the server's actual decoded PCM statistics."""
    upper, lower = [], []
    peak = wave["peaks"][0]
    source_frames = wave["duration"] * FPS
    for i in range(128):
        local = i / 127 * (clip["duration"] - 1)
        source_frame = clip["in"] + ((clip["duration"] - 1 - local) if clip["reverse"] else local) * clip["speed"]
        index = max(0, min(wave["bins"] - 1, math.floor(source_frame / source_frames * wave["bins"])))
        upper.extend([i / 127 * 100, 50 - peak["max"][index] * 44])
        lower.append([i / 127 * 100, 50 - peak["min"][index] * 44])
    return upper + [value for pair in reversed(lower) for value in pair]


def read_helper_result(process):
    for line in reversed(process.stdout.splitlines()):
        try:
            result = json.loads(line)
            if isinstance(result, dict) and "passed" in result:
                return result
        except ValueError:
            continue
    raise RuntimeError("Native WebKit helper returned no JSON result: " + (process.stderr or process.stdout)[-2200:])


def saved_checks(project, ui):
    checks = {}
    clips = project.get("clips", [])
    checks["one_clip_added_through_ui"] = len(clips) == 1 and clips[0]["id"] == ui.get("clip_id")
    if not clips:
        return checks
    clip = clips[0]
    checks["fractional_in_and_retime_saved"] = close(clip.get("in"), .5) and close(clip.get("speed"), 1.5) and clip["duration"] == FRAMES and clip.get("reverse") is True
    checks["source_range_and_timeline_origin"] = clip["start"] == 0 and clip["track"] == 0 and clip["asset_id"] == ui.get("asset_id")
    audio = clip.get("audio", {})
    checks["clip_gain_balance_fades_saved"] = close(clip.get("volume"), .8) and close(audio.get("pan"), .25) and audio.get("fade_in") == audio.get("fade_out") == 1
    track = next((item for item in project.get("tracks", []) if item["id"] == 0), {})
    checks["mixer_and_track_state_saved"] = track.get("name") == "ENGINE TEST picture" and close(track.get("gain"), .65) and track.get("solo") is True and track.get("mute") is False and track.get("locked") is False
    keys = sorted(clip.get("keyframes", []), key=lambda item: item["frame"])
    checks["eased_pose_keys_saved"] = len(keys) == 2 and [item["frame"] for item in keys] == [0, 7] and keys[0].get("interpolation") == "ease_in_out" and close(keys[0].get("x"), 0) and close(keys[1].get("x"), .12)
    checks["grade_saved"] = close(clip.get("grade", {}).get("exposure"), .25)
    graph = clip.get("compositor", {})
    nodes = {item["id"]: item for item in graph.get("nodes", [])}
    source = next((item for item in nodes.values() if item["type"] == "source"), {})
    curve, mask = nodes.get(ui.get("curves_id"), {}), nodes.get(ui.get("mask_id"), {})
    checks["source_curves_polygon_connected_to_output"] = len(nodes) == 3 and curve.get("type") == "curves" and mask.get("type") == "mask" and curve.get("inputs") == [source.get("id")] and mask.get("inputs") == [curve.get("id")] and graph.get("output") == mask.get("id")
    master = curve.get("params", {}).get("master", [])
    checks["authored_curve_midpoint_saved"] = len(master) == 3 and close(master[1][0], .4) and close(master[1][1], .8) and master[0] == [0, 0] and master[-1] == [1, 1]
    params = mask.get("params", {})
    points = params.get("points", [])
    checks["authored_polygon_and_rotation_saved"] = params.get("shape") == "polygon" and len(points) == 3 and close(points[0][0], .2) and close(points[0][1], .75) and close(params.get("rotation"), 30) and close(params.get("width"), .9) and close(params.get("height"), .9)
    checks["no_unexpected_title_or_media_mutation"] = not project.get("titles") and len(project["assets"]) == 1
    return checks


def run(binary, evidence, profile="h264"):
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    deadline = began + 17.5
    result = {"passed": False, "browser": "WKWebView", "profile": profile,
              "fixture": "SYNTHETIC ENGINE TEST SIGNALS — NOT A FILM", "checks": {}}
    checks = result["checks"]

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The isolated editing smoke exceeded its 18-second execution budget.")
        return min(maximum, remaining)

    def command(arguments, maximum=4):
        return subprocess.run(arguments, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=budget(maximum))

    with tempfile.TemporaryDirectory(prefix="cinematicum-editing-ENGINE-TEST-") as temporary:
        scratch = Path(temporary)
        store, server, thread = None, None, None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("This real media test needs FFmpeg and ffprobe.")
            fixture = scratch / "ENGINE_TEST_ONLY_source.mp4"
            command([ffmpeg, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1",
                     "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=12:duration=2",
                     "-f", "lavfi", "-i", "aevalsrc=0.12*sin(2*PI*440*t)*(0.2+0.8*t/2)|0.10*sin(2*PI*660*t)*(1-0.8*t/2):s=48000:d=2",
                     "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-threads", "1",
                     "-c:a", "aac", "-b:a", "192k", "-t", "2", str(fixture)])
            store = Store(scratch / "workspace")
            project = store.new_project({"name": "ENGINE TEST — own editing and compositing UI", "fps": FPS, "width": WIDTH, "height": HEIGHT})
            store.admit(project["id"], fixture, fixture.name)
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            screenshot = evidence / "ENGINE_TEST_editing_webkit.png"
            # Leave time for independent decode and graceful server cancellation.
            native_timeout = budget(13.3, reserve=2.4)
            native = subprocess.run([
                str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}/?smoke_profile={profile}",
                "--output", str(screenshot), "--timeout", str(round(native_timeout, 2)),
                "--script", str(HERE / "macos" / "EditingSmoke.js"),
            ], capture_output=True, text=True, timeout=min(native_timeout + .6, budget(14)))
            ui = read_helper_result(native)
            (evidence / "ENGINE_TEST_ui.json").write_text(json.dumps(ui, indent=2, ensure_ascii=False), encoding="utf-8")
            waveform_path = ui.pop("waveform_path", "")
            result["ui"] = ui
            result["helper_exit_code"] = native.returncode
            if native.stderr.strip():
                result["helper_stderr_tail"] = native.stderr[-1400:]
            checks["native_ui_passed"] = ui.get("passed") is True and native.returncode == 0
            checks["no_uncaught_browser_error"] = not ui.get("page_errors", [])
            checks["native_under_14_seconds"] = ui.get("elapsed_ms", 999999) < 14000
            saved = store.get(project["id"])
            (evidence / "ENGINE_TEST_saved_project.json").write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
            checks.update(saved_checks(saved, ui))
            directory = store.project_dir(project["id"])

            wave_files = list((directory / "waveforms").glob("*.json"))
            checks["real_decoded_waveform_cached"] = len(wave_files) == 1
            if wave_files and saved["clips"]:
                wave = json.loads(wave_files[0].read_text())
                actual = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", waveform_path)]
                expected = waveform_points(wave, saved["clips"][0])
                checks["svg_matches_decoded_reversed_source_range"] = len(actual) == len(expected) == 512 and max(abs(a - b) for a, b in zip(actual, expected)) < .011
                peak = wave["peaks"][0]["max"]
                checks["waveform_measures_nonconstant_stereo_audio"] = wave["channels"] == 2 and wave["sample_rate"] == 48000 and sum(wave["sample_counts"]) >= 96000 and max(peak) - min(peak) > .03
                result["waveform"] = {"bins": wave["bins"], "decoded_samples": sum(wave["sample_counts"]), "svg_points": len(actual) // 2}
                shutil.copy2(wave_files[0], evidence / "ENGINE_TEST_decoded_waveform.json")

            with store.lock:
                jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
            completed = [job for job in jobs if job["kind"] == "render" and job["state"] == "completed"]
            checks["one_real_render_completed"] = len(completed) == 1
            frame = ui.get("paused_frame", {})
            frame_jobs = [job for job in jobs if job["kind"] == "frame-preview" and job["state"] == "completed" and job.get("result", {}).get("url") == frame.get("url")]
            checks["displayed_png_is_completed_export_graph_frame"] = bool(frame_jobs) and frame.get("frame") == PAUSED_FRAME and frame.get("width") == WIDTH and frame.get("height") == HEIGHT
            preview = None
            if frame_jobs:
                receipt = frame_jobs[-1]["result"]
                preview = directory / "previews" / Path(urlsplit(receipt["url"]).path).name
                payload = preview.read_bytes()
                checks["paused_png_receipt_matches_real_file"] = payload.startswith(PNG_SIGNATURE) and hashlib.sha256(payload).hexdigest() == receipt.get("sha256") and receipt.get("pipeline") == "timeline-export-graph" and receipt.get("frame") == PAUSED_FRAME
                shutil.copy2(preview, evidence / "ENGINE_TEST_paused_frame_3.png")
            scopes = ui.get("scopes", {})
            checks["three_distinct_measured_scope_rasters"] = set(scopes) == {"histogram", "waveform", "vectorscope"} and len({scope.get("hash") for scope in scopes.values()}) == 3 and all(scope.get("ink_pixels", 0) > 50 for scope in scopes.values())

            if completed:
                job = completed[0]
                movie = directory / "exports" / job["result"]["filename"]
                metadata = probe_media(movie)
                result["media"] = metadata
                checks["requested_render_profile"] = job["result"].get("profile") == profile
                checks["eight_frame_av_export"] = metadata["frames"] == FRAMES and metadata["width"] == WIDTH and metadata["height"] == HEIGHT and metadata["has_audio"] and abs(metadata["duration"] - FRAMES / FPS) < .06
                checks["webkit_played_this_export"] = ui.get("video_src") == job["result"]["url"] and ui.get("video_current_time", 0) > .08 and urlsplit(ui.get("download_href", "")).path == job["result"]["url"]
                raw_video, raw_audio = scratch / "decoded.rgb", scratch / "decoded.f32"
                command([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(movie),
                         "-map", "0:v:0", "-an", "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", str(raw_video),
                         "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "48000", "-f", "f32le", str(raw_audio)])
                pixels = raw_video.read_bytes()
                bytes_per_frame = WIDTH * HEIGHT * 3
                checks["all_export_frames_decode"] = len(pixels) == bytes_per_frame * FRAMES
                frame_hashes = {hashlib.sha256(pixels[i:i + bytes_per_frame]).hexdigest() for i in range(0, len(pixels), bytes_per_frame)}
                checks["export_has_changing_picture"] = len(frame_hashes) > 3
                samples = array("f")
                samples.frombytes(raw_audio.read_bytes())
                if sys.byteorder != "little":
                    samples.byteswap()
                count = min(len(samples) // 2, round(FRAMES / FPS * 48000))
                channels = [samples[channel:count * 2:2] for channel in range(2)]
                rms = [math.sqrt(sum(value * value for value in channel) / max(1, len(channel))) for channel in channels]
                checks["export_decodes_nonzero_stereo_pcm"] = count >= 30000 and all(.0001 < value < 1 for value in rms) and abs(rms[0] - rms[1]) > .0001
                result["decoded"] = {"video_frames": len(pixels) // bytes_per_frame, "distinct_frames": len(frame_hashes), "stereo_samples": count, "channel_rms": rms}
                if preview is not None:
                    png = command([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(preview),
                                   "-frames:v", "1", "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
                    delivered = pixels[PAUSED_FRAME * bytes_per_frame:(PAUSED_FRAME + 1) * bytes_per_frame]
                    error = sum(abs(a - b) for a, b in zip(png, delivered)) / max(1, len(png))
                    # H.264 is lossy; compare actual decoded RGB, not file bytes.
                    checks["paused_png_matches_delivered_frame"] = len(png) == len(delivered) == bytes_per_frame and error < 12
                    result["decoded"]["paused_vs_delivered_mean_rgb_error"] = round(error, 5)
                export_copy = evidence / "ENGINE_TEST_edited_export.mp4"
                shutil.copy2(movie, export_copy)
                result["export"] = str(export_copy)

            checks["native_window_screenshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == PNG_SIGNATURE
            result["screenshot"] = str(screenshot) if screenshot.is_file() else None
            result["jobs"] = [{"kind": job["kind"], "state": job["state"], **({"error": job["error"]} if job.get("error") else {})} for job in jobs]
            if not all(checks.values()):
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
        except Exception as exc:
            result["error"] = str(exc)
            checks["completed_without_fixture_or_decode_error"] = False
            if isinstance(exc, subprocess.CalledProcessError):
                detail = exc.stderr or b""
                result["process_error"] = (detail.decode(errors="replace") if isinstance(detail, bytes) else detail)[-2200:]
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=.2)
            if store is not None:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["whole_run_under_18_seconds"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
    result["evidence_directory"] = str(evidence)
    (evidence / "ENGINE_TEST_report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded actual WKWebView editing, waveform, compositor, scope and media acceptance")
    parser.add_argument("--binary", type=Path, help="Previously compiled macos/SmokeTest.swift executable")
    parser.add_argument("--output", type=Path, help="Folder for actual screenshot, PNG, movie and JSON evidence")
    parser.add_argument("--profile", choices=("h264", "preview"), default="h264", help="Run Export/H.264 or the Render preview control in this invocation")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Real WKWebView acceptance requires macOS; no browser or media result is simulated."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and pass its executable using --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-editing-ENGINE-TEST-evidence-"))
    result = run(args.binary, output, args.profile)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Own WK controls, cubic path history, effect ports and actual rendered media.

Only a disposable constant-gray numeric signal is admitted. The saved graph,
before/after subdivision PNG receipts and decoded export are verified outside
the UI. There is no direct application-state or HTTP mutation by the JS test.
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

from compositor import node_params_at
from engine import probe_media
from roto import sample_coverage
from server import Server, Store
from test_editing_ui_macos import close, read_helper_result

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS, FRAMES, PAUSED_FRAME = 160, 90, 12, 12, 6
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def saved_checks(project, ui):
    checks = {}
    clips = project.get("clips", [])
    checks["one_own_clip"] = len(clips) == 1
    recipe = clips[0].get("compositor", {}) if len(clips) == 1 else {}
    nodes = {node["id"]: node for node in recipe.get("nodes", [])}
    mask, grade, source = (nodes.get(ui.get(kind + "_id"), {}) for kind in ("mask", "grade", "source"))
    checks["effect_port_uses_distinct_source_and_alpha_branches"] = (len(nodes) == 3
        and source.get("type") == "source" and mask.get("inputs") == [source.get("id")]
        and grade.get("inputs") == [source.get("id")] and grade.get("mask_input") == mask.get("id")
        and grade.get("mask_invert") is False and recipe.get("output") == grade.get("id")
        and grade.get("params", {}).get("exposure") == 1)
    keys = mask.get("animation", {}).get("bezier", [])
    checks["cubic_geometry_and_key_domain_persist"] = (mask.get("params", {}).get("shape") == "bezier"
        and len(mask.get("params", {}).get("bezier", [])) == 5 and len(keys) == 2
        and [key.get("frame") for key in keys] == [0, 8]
        and all(len(key.get("value", [])) == 5 for key in keys))
    if len(keys) == 2 and all(len(key.get("value", [])) == 5 for key in keys):
        first, last = keys
        checks["custom_cubic_tangents_persist"] = (first.get("interpolation") == "cubic"
            and first.get("out_tangent") == 2.5 and last.get("in_tangent") == .2)
        checks["subdivision_keeps_true_cubic_controls"] = (close(last["value"][0][4], .65, 1e-5)
            and close(last["value"][0][5], .16, 1e-5)
            and close(last["value"][0][2], .2790861, 1e-8))
        checks["per_anchor_feather_survives_animation_subdivision"] = (first["value"][0][6] == 1
            and last["value"][0][6] == 2.5 and last["value"][1][6] == 1.75
            and all(key["value"][2][6] == 1 for key in keys))
    checks["no_unrequested_assets_or_titles"] = len(project["assets"]) == 1 and not project.get("titles")
    return checks, mask


def run(binary, evidence):
    evidence = Path(evidence).resolve(); evidence.mkdir(parents=True, exist_ok=True)
    began = time.monotonic(); deadline = began + 18.3
    result = {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST — NOT FILM FOOTAGE", "checks": {}}
    checks = result["checks"]

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining < .1:
            raise TimeoutError("Bezier native acceptance exceeded its time budget.")
        return min(maximum, remaining)

    def command(arguments, maximum=4, **kwargs):
        return subprocess.run(arguments, check=True, capture_output=True, timeout=budget(maximum), **kwargs)

    with tempfile.TemporaryDirectory(prefix="cinematicum-roto-webkit-ENGINE-TEST-") as temporary:
        scratch = Path(temporary); store = server = thread = None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("FFmpeg and ffprobe are required for real media acceptance.")
            fixture = scratch / "ENGINE_TEST_ONLY_gray.mkv"
            command([ffmpeg, "-v", "error", "-nostdin", "-y", "-threads", "1", "-f", "rawvideo",
                     "-pixel_format", "rgba", "-video_size", "160x90", "-framerate", "12", "-i", "pipe:0",
                     "-an", "-c:v", "ffv1", "-pix_fmt", "bgra", "-threads", "1", str(fixture)],
                    input=bytes((64, 64, 64, 255)) * WIDTH * HEIGHT * FRAMES)
            source_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
            store = Store(scratch / "workspace")
            project = store.new_project({"name": "ENGINE TEST — cubic roto and effect ports", "fps": FPS, "width": WIDTH, "height": HEIGHT})
            asset = store.admit(project["id"], fixture, fixture.name)
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True); thread.start()
            screenshot = evidence / "ENGINE_TEST_roto_webkit.png"
            native_timeout = budget(13.6, reserve=2.1)
            native = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}/",
                                     "--output", str(screenshot), "--timeout", str(round(native_timeout, 2)),
                                     "--script", str(HERE / "macos" / "RotoSmoke.js")],
                                    capture_output=True, text=True, timeout=budget(native_timeout + .6))
            ui = read_helper_result(native); result["ui"] = ui; result["helper_exit_code"] = native.returncode
            checks["native_controls_and_history_passed"] = native.returncode == 0 and ui.get("passed") is True
            checks["no_browser_errors"] = not ui.get("page_errors", [])
            checks["bounded_native_runtime"] = ui.get("elapsed_ms", 99999) < 14000
            if native.stderr: result["helper_stderr_tail"] = native.stderr[-1400:]
            saved, directory = store.get(project["id"]), store.project_dir(project["id"])
            (evidence / "ENGINE_TEST_saved_project.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
            (evidence / "ENGINE_TEST_ui.json").write_text(json.dumps(ui, indent=2), encoding="utf-8")
            data_checks, mask = saved_checks(saved, ui); checks.update(data_checks)
            with store.lock:
                jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
            pictures = {}; size = WIDTH * HEIGHT * 3
            for name in ("before", "after"):
                requested = ui.get(name + "_frame", {})
                found = [job for job in jobs if job["kind"] == "frame-preview" and job["state"] == "completed"
                         and job.get("result", {}).get("url") == requested.get("url")]
                checks[name + "_is_actual_graph_frame6"] = bool(found) and requested.get("frame") == PAUSED_FRAME
                if found:
                    receipt = found[-1]["result"]
                    path = directory / "previews" / Path(urlsplit(receipt["url"]).path).name; payload = path.read_bytes()
                    checks[name + "_receipt_verified"] = (payload.startswith(PNG_SIGNATURE)
                        and hashlib.sha256(payload).hexdigest() == receipt.get("sha256")
                        and receipt.get("pipeline") == "timeline-export-graph")
                    pictures[name] = command([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(path),
                                             "-frames:v", "1", "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
                    shutil.copy2(path, evidence / ("ENGINE_TEST_" + name + "_frame6.png"))
            checks["exact_subdivision_preserves_decoded_picture"] = (set(pictures) == {"before", "after"}
                and len(pictures["before"]) == size and pictures["before"] == pictures["after"])
            if "after" in pictures and mask:
                pixels = pictures["after"]; low, high = pixels[0], pixels[3 * (45 * WIDTH + 80)]
                checks["effect_changes_only_authored_region"] = abs(low - 64) <= 1 and high > low + 16
                params = node_params_at(mask, PAUSED_FRAME); errors = []
                for y in range(3, HEIGHT, 7):
                    for x in range(3, WIDTH, 9):
                        coverage = sum(sample_coverage(params, WIDTH, HEIGHT, x + dx, y + dy)
                                       for dx in (.25, .75) for dy in (.25, .75)) / 4
                        expected = low + (high - low) * coverage
                        errors.append(abs(pixels[3 * (y * WIDTH + x)] - expected))
                result["independent_coverage_mean_error"] = sum(errors) / len(errors)
                result["independent_coverage_max_error"] = max(errors)
                checks["cubic_feather_matches_independent_point_oracle"] = sum(errors) / len(errors) < .8 and max(errors) < 2.1
            completed = [job for job in jobs if job["kind"] == "render" and job["state"] == "completed"]
            checks["one_real_movie_export"] = len(completed) == 1
            if completed:
                receipt = completed[-1]["result"]; movie = directory / "exports" / receipt["filename"]
                metadata = probe_media(movie); result["media"] = metadata
                checks["movie_has_expected_dimensions_and_frame_count"] = (metadata["width"] == WIDTH
                    and metadata["height"] == HEIGHT and metadata["frames"] == FRAMES)
                checks["webkit_plays_that_movie"] = ui.get("video_src") == receipt["url"] and ui.get("video_time", 0) > .06
                pixels = command([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(movie),
                                  "-map", "0:v:0", "-an", "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
                checks["every_movie_frame_decodes"] = len(pixels) == FRAMES * size
                checks["path_animation_changes_actual_movie_pixels"] = (len(pixels) == FRAMES * size
                    and pixels[:size] != pixels[8 * size:9 * size])
                if "after" in pictures and len(pixels) == FRAMES * size:
                    error = sum(abs(a - b) for a, b in zip(pictures["after"], pixels[6 * size:7 * size])) / size
                    result["paused_export_mean_rgb_error"] = error
                    checks["paused_graph_matches_delivered_movie"] = error < 2
                shutil.copy2(movie, evidence / "ENGINE_TEST_cubic_export.mp4")
            checks["source_unchanged"] = (asset["sha256"] == source_hash
                and hashlib.sha256((directory / asset["path"]).read_bytes()).hexdigest() == source_hash)
            checks["actual_native_screenshot"] = (screenshot.is_file() and screenshot.stat().st_size > 1000
                and screenshot.read_bytes().startswith(PNG_SIGNATURE))
            result["jobs"] = [{"kind": job["kind"], "state": job["state"],
                               **({"error": job["error"]} if job.get("error") else {})} for job in jobs]
            if not all(checks.values()):
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(name for name, ok in checks.items() if not ok)
        except Exception as error:
            result["error"] = str(error); checks["completed_without_fixture_error"] = False
            if isinstance(error, subprocess.CalledProcessError):
                result["process_error"] = (error.stderr or b"").decode(errors="replace")[-1600:]
        finally:
            if server is not None: server.shutdown(); server.server_close()
            if thread is not None: thread.join(timeout=.2)
            if store is not None: store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["bounded_whole_run"] = result["elapsed_seconds"] < 19
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    (evidence / "ENGINE_TEST_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="Real native Bezier handles, point feather, mask ports, undo and media acceptance")
    parser.add_argument("--binary", type=Path); parser.add_argument("--output", type=Path); args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual WKWebView acceptance requires macOS; no UI or media result is simulated."})); return 0
    if not args.binary or not args.binary.is_file(): parser.error("Pass the compiled macos/SmokeTest.swift executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-roto-ENGINE-TEST-evidence-"))
    result = run(args.binary, output); print(json.dumps(result, sort_keys=True)); return 0 if result["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())

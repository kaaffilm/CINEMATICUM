#!/usr/bin/env python3
"""Native plan/import/bind/preview/assemble/undo/save/export acceptance.

All media and projects are isolated synthetic ENGINE TEST fixtures, not films.
The shipped UI performs mutations; Python independently reads the saved recipe,
source hashes and every decoded output picture/PCM sample. Slow native runs fail
within a bounded deadline instead of substituting simulated browser results.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from production import normalize_plan
from server import Server, Store
from test_editing_ui_macos import read_helper_result


HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS, FRAMES = 160, 90, 24, 8
FIRST_SHOT_ID, SECOND_SHOT_ID = "__proto__", "constructor"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started, deadline = time.monotonic(), time.monotonic() + 15.5
    result = {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST — NOT A FILM", "checks": {}}
    checks, screenshot = result["checks"], output / "ENGINE_TEST_production_webkit.png"

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("Production acceptance exceeded its 15.5-second execution budget.")
        return min(maximum, remaining)

    def command(arguments, maximum=3):
        return subprocess.run(arguments, check=True, capture_output=True, timeout=budget(maximum)).stdout

    with tempfile.TemporaryDirectory(prefix="cinematicum-production-webkit-ENGINE-TEST-") as temporary:
        work, store, server, thread, project = Path(temporary), None, None, None, None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("Actual FFmpeg/ffprobe are required for source and output media.")
            store = Store(work / "workspace")
            project = store.new_project({"name": "ENGINE TEST — Production conformance", "fps": FPS, "width": WIDTH, "height": HEIGHT})
            assets, hashes = {}, {}
            for name, frequency in (("red", 440), ("blue", 880)):
                path = work / ("ENGINE_TEST_production_" + name + ".mp4")
                command([ffmpeg, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1",
                         "-f", "lavfi", "-i", f"color=c={name}:s={WIDTH}x{HEIGHT}:r={FPS}:d=0.5",
                         "-f", "lavfi", "-i", f"sine=f={frequency}:r=48000:d=0.5",
                         "-frames:v", "12", "-t", "0.5", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                         "-threads", "1", "-c:a", "aac", str(path)])
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                assets[name] = store.admit(project["id"], path, path.name)
            project = store.get(project["id"])
            project["clips"] = [{"id": "ENGINE_TEST_prior_cut", "asset_id": assets["red"]["id"], "track": 0, "start": 0, "in": 0, "duration": 3}]
            project["settings"]["preserved_engine_test"] = {"value": "must survive production assembly"}
            project = store.save(project["id"], project)
            plan = {"film": "ENGINE TEST — Planned cut", "fps": FPS, "width": WIDTH, "height": HEIGHT,
                    "runtime_frames": FRAMES, "shots": [
                        {"id": FIRST_SHOT_ID, "filename": assets["red"]["name"], "duration_frames": 4, "description": "Synthetic red source with 440 Hz tone."},
                        {"id": SECOND_SHOT_ID, "filename": assets["blue"]["name"], "duration_frames": 4, "description": "Synthetic blue source with 880 Hz tone."}]}
            fixture = {"plan": plan, "red_id": assets["red"]["id"], "blue_id": assets["blue"]["id"]}
            script = work / "ProductionSmoke.js"
            script.write_text("const PRODUCTION_TEST=" + json.dumps(fixture) + ";\n" + (HERE / "macos/ProductionSmoke.js").read_text(), encoding="utf-8")
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            native_timeout = budget(11.8, 2)
            process = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}/",
                                      "--output", str(screenshot), "--script", str(script), "--timeout", str(round(native_timeout, 2))],
                                     capture_output=True, text=True, timeout=budget(native_timeout + .5, .7))
            ui = read_helper_result(process)
            result["ui"], result["helper_exit_code"] = ui, process.returncode
            if process.stderr:
                result["helper_stderr_tail"] = process.stderr[-1200:]
            checks["native_production_controls"] = process.returncode == 0 and ui.get("passed") is True
            checks["no_browser_errors"] = not ui.get("page_errors", [])
            for step in ("read_plan_and_block_missing_sources", "persist_unresolved_plan_without_replacing_edit",
                         "reject_blank_and_fractional_source_ranges",
                         "bind_actual_imported_takes_and_validate_handles", "preview_source_trim_and_release_decoder",
                         "download_exact_portable_plan", "assemble_once_and_undo_redo", "save_and_render_actual_prores_cut"):
                checks[step] = step in ui.get("steps", [])
            saved = store.get(project["id"])
            directory = store.project_dir(project["id"])
            clips = sorted(saved["clips"], key=lambda clip: clip["start"])
            expected = [(assets["red"]["id"], 0, 2, 4), (assets["blue"]["id"], 4, 3, 4)]
            checks["exact_shot_order_and_source_handles_saved"] = [(c["asset_id"], c["start"], c["in"], c["duration"]) for c in clips] == expected
            checks["inventory_and_unrelated_settings_preserved"] = len(saved["assets"]) == 2 and saved["settings"].get("preserved_engine_test") == project["settings"]["preserved_engine_test"]
            record = saved["settings"].get("production", {})
            canonical = normalize_plan(plan)
            checks["canonical_plan_and_bindings_saved"] = record.get("plan") == canonical and record.get("bindings", {}).get(FIRST_SHOT_ID, {}).get("in_frame") == 2 and record.get("bindings", {}).get(SECOND_SHOT_ID, {}).get("in_frame") == 3
            checks["reserved_string_ids_survive_binding_and_save"] = set(record.get("bindings", {})) == {FIRST_SHOT_ID, SECOND_SHOT_ID} and record.get("bindings", {}).get(FIRST_SHOT_ID, {}).get("asset_id") == assets["red"]["id"] and record.get("bindings", {}).get(SECOND_SHOT_ID, {}).get("asset_id") == assets["blue"]["id"]
            checks["portable_export_exact"] = ui.get("exported_plan") == canonical
            plan_name = Path(urlsplit(ui.get("plan_export_href", "")).path).name
            plan_download = directory / "exports" / plan_name
            plan_bytes = plan_download.read_bytes() if plan_download.is_file() and plan_name.endswith("-shot-plan.json") else b""
            checks["portable_download_is_real_persisted_attachment"] = bool(plan_bytes) and len(plan_bytes) == ui.get("plan_download_bytes") and json.loads(plan_bytes) == canonical
            if plan_bytes:
                result["portable_plan_download_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
            checks["no_issuance_claim"] = record.get("issuance_effect") == "NONE"
            identities = record.get("media_identities", {})
            checks["source_identity_and_bytes_preserved"] = all(
                hashlib.sha256((directory / assets[name]["path"]).read_bytes()).hexdigest() == hashes[name]
                and identities.get(shot, {}).get("sha256") == hashes[name]
                for name, shot in (("red", FIRST_SHOT_ID), ("blue", SECOND_SHOT_ID)))
            with store.lock:
                jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
            rendered = [job for job in jobs if job["kind"] == "render" and job["state"] == "completed"]
            checks["one_completed_real_export"] = len(rendered) == 1
            checks["no_generation_or_filler_jobs"] = all(job["kind"] in {"render", "frame-preview"} for job in jobs)
            if rendered:
                receipt = rendered[0]["result"]
                movie = directory / "exports" / receipt["filename"]
                result["media"] = metadata = probe_media(movie)
                checks["delivery_identity_verified"] = hashlib.sha256(movie.read_bytes()).hexdigest() == receipt.get("sha256")
                checks["ui_download_is_actual_delivery"] = Path(urlsplit(ui.get("export_href", "")).path).name == movie.name
                checks["delivery_format_and_duration"] = metadata["width"] == WIDTH and metadata["height"] == HEIGHT and metadata["frames"] == FRAMES and abs(metadata["duration"] - FRAMES / FPS) < 1e-6
                pixels = command([ffmpeg, "-v", "error", "-nostdin", "-i", str(movie), "-map", "0:v:0", "-an", "-pix_fmt", "rgb24", "-threads", "1", "-f", "rawvideo", "pipe:1"])
                pcm = command([ffmpeg, "-v", "error", "-nostdin", "-i", str(movie), "-map", "0:a:0", "-vn", "-f", "s16le", "pipe:1"])
                frame_size = WIDTH * HEIGHT * 3
                checks["all_eight_real_frames_decode"] = len(pixels) == FRAMES * frame_size
                samples = [list(pixels[frame * frame_size + (45 * WIDTH + 80) * 3:frame * frame_size + (45 * WIDTH + 80) * 3 + 3]) for frame in range(FRAMES)]
                result["decoded_center_rgb"] = samples
                checks["red_then_blue_without_missing_shot_fill"] = len(pixels) == FRAMES * frame_size and all(
                    color[0 if index < 4 else 2] > 200 and color[2 if index < 4 else 0] < 25
                    for index, color in enumerate(samples))
                checks["exact_stereo_pcm_duration"] = len(pcm) == 16000 * 2 * 2
                checks["actual_source_sound_survives"] = bool(pcm) and max(abs(sample[0]) for sample in struct.iter_unpack("<h", pcm)) > 100
                shutil.copy2(movie, output / "ENGINE_TEST_production_cut.mov")
            checks["native_production_screenshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(PNG_SIGNATURE)
            (output / "ENGINE_TEST_production_saved_project.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
            (output / "ENGINE_TEST_production_plan.json").write_text(json.dumps(canonical, indent=2), encoding="utf-8")
            if not all(checks.values()):
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
        except Exception as error:
            result["error"] = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                result["process_error"] = (error.stderr or b"").decode(errors="replace")[-1600:]
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=.2)
            if store:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    checks["bounded_whole_run"] = result["elapsed_seconds"] < 16
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    (output / "ENGINE_TEST_production_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual WKWebView acceptance requires macOS; no native result is simulated."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Supply the compiled macos/SmokeTest.swift executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-production-ENGINE-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

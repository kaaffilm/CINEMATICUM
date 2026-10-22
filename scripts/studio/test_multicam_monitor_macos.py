#!/usr/bin/env python3
"""Actual multicamera monitor/fixed-sound acceptance in <=18-second phases.

Uses the compiled SmokeTest.swift helper on macOS, or the explicit Chromium
adapter for browser acceptance. Every invocation owns and closes its server,
browser process group and media jobs. A browser result never certifies native.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import uuid

from editorial import apply_action
from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result
from test_multicam_sync_macos import identity, safe_directory, write_json, read_json, source_inventory as sync_inventory

HERE = Path(__file__).resolve().parent
KIND = "cinematicum-owned-multicam-monitor-v1"
PHASES = ("prepare", "author", "play", "render")


def source_inventory():
    result = sync_inventory()
    for name in ("test_multicam_monitor.py", "test_multicam_monitor_macos.py", "test_multicam_monitor_browser.cjs", "macos/MulticamMonitorSmoke.js", "macos/AudioProbeWorklet.js"):
        result[name] = identity(HERE / name)
    return dict(sorted(result.items()))


def foreground(argv, timeout):
    process = subprocess.Popen(list(map(str, argv)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=.3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); stdout, stderr = process.communicate(timeout=.2)
        raise TimeoutError("The owned acceptance process exceeded its foreground budget")
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def run(binary, output, operation, fixture_workspace, expected_sources, *, transport="WKWebView"):
    began = time.monotonic(); deadline = began + 18
    output = safe_directory(output, new=True)
    result = {"kind": KIND, "operation": operation, "browser": transport, "native_certified": operation != "prepare" and transport == "WKWebView" and sys.platform == "darwin",
              "passed": False, "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT", "checks": {}}
    checks = result["checks"]; store = server = thread = root = fixture = project = None

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The multicamera monitor phase exhausted its 18-second budget")
        return min(maximum, remaining)

    try:
        if operation not in PHASES:
            raise ValueError("Unknown monitor acceptance phase")
        before = source_inventory(); result["source_before"] = before
        if before != expected_sources:
            raise ValueError("The runtime or acceptance source differs from the explicit frozen inventory")
        checks["exact_frozen_runtime_web_and_acceptance_source"] = True
        if operation == "prepare":
            root = Path(fixture_workspace).absolute()
            if root.exists() or any(p.is_symlink() for p in (root, *root.parents)):
                raise ValueError("Prepare requires a new explicit fixture directory")
            root.parent.mkdir(parents=True, exist_ok=True)
            code = "import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_multicam_monitor import make_fixture\nprint(json.dumps(make_fixture(Path(sys.argv[2]))))\n"
            made = foreground([sys.executable, "-I", "-B", "-c", code, HERE, root], budget(9, 3))
            if made.returncode:
                raise RuntimeError("Actual H.264/PCM fixture preparation failed: " + made.stderr[-1600:])
            originals = json.loads(made.stdout)
            store = Store(root / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST camera monitor sentinel", "width": 96, "height": 64, "fps": 24})
            project = store.new_project({"name": "ENGINE TEST fixed sound camera monitor", "width": 96, "height": 64, "fps": 24})
            cameras = []
            for original in originals:
                incoming = root / ("owned-upload-" + Path(original["path"]).name)
                shutil.copyfile(root / original["path"], incoming)
                asset = store.admit(project["id"], incoming, original["name"] + ".mov", {"fixture": "ENGINE TEST"})
                cameras.append({"asset_id": asset["id"], "filename": Path(original["path"]).name, "identity": identity(root / original["path"])})
            project = store.get(project["id"])
            project = apply_action(project, "multicam_create", {"name": "ENGINE TEST camera monitor", "start": 0, "track": 0,
                "angles": [{"asset_id": cameras[0]["asset_id"], "in": 12}, {"asset_id": cameras[1]["asset_id"], "in": 24}]}, store.project_dir(project["id"]))["project"]
            store.save(project["id"], project); project = store.get(project["id"])
            fixture = {"kind": KIND, "acceptance_id": uuid.uuid4().hex, "project_id": project["id"], "project_name": project["name"],
                       "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"], "cameras": cameras,
                       "truth": {p.name: identity(p) for p in (root / "truth").iterdir()}}
            write_json(root / "monitor-fixture.json", fixture)
            checks["two_actual_original_h264_cameras_with_frame_counters_and_independent_pcm"] = len(cameras) == 2 and len(project["assets"][1]["audio_streams"]) == 2
            checks["actual_typed_manual_group_without_lock_or_picture_cuts"] = len(project["clips"]) == 1 and project["clips"][0]["duration"] == 120 and not project["multicam_groups"][0].get("audio_lock")
        else:
            root = safe_directory(fixture_workspace); fixture = read_json(root / "monitor-fixture.json")
            if fixture.get("kind") != KIND or not re.fullmatch("[a-f0-9]{32}", fixture.get("acceptance_id", "")):
                raise ValueError("The explicit fixture has a different acceptance identity")
            if (root / (operation + "-passed.json")).exists():
                raise ValueError("Preserve the completed phase; prepare a new fixture for repetition")
            prior_path = root / (PHASES[PHASES.index(operation) - 1] + "-passed.json"); prior = read_json(prior_path)
            if prior.get("passed") is not True or prior.get("acceptance_id") != fixture["acceptance_id"] or prior.get("source_inventory") != before:
                raise ValueError("The prior phase does not certify this exact fixture/source")
            persisted = root / "workspace/projects" / fixture["project_id"] / "project.json"
            if identity(persisted) != prior["saved_project_identity"]:
                raise ValueError("The saved camera edit changed after the preceding phase")
            if any(identity(root / "media" / c["filename"]) != c["identity"] for c in fixture["cameras"]) or {p.name: identity(p) for p in (root / "truth").iterdir()} != fixture["truth"]:
                raise ValueError("Original camera bytes or independent sample truth changed")
            for path in (root / "workspace/jobs").glob("*.json"):
                job = read_json(path)
                if job.get("project_id") not in (fixture["project_id"], fixture["sentinel_id"]) or job.get("state") not in ("completed", "failed", "cancelled"):
                    raise ValueError("A prior attempt has unexpected or pending work; preserve it and use a new fixture")
            result["helper_identity"] = identity(binary); result["prior_phase_identity"] = identity(prior_path)
            store = Store(root / "workspace"); project = store.get(fixture["project_id"]); initial = copy.deepcopy(project)
            with store.lock:
                jobs_before = set(store.jobs)
            script = output / "ENGINE_TEST_multicam_monitor.js"
            script.write_text((HERE / "macos/MulticamMonitorSmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps({**fixture, "operation": operation})))
            result["executed_javascript_identity"] = identity(script)
            downloads = output / "native_downloads"; downloads.mkdir()

            class ProbeHandler(Handler):
                def dispatch_get(self):
                    if self.path == "/ENGINE_TEST_audio_probe_worklet.js":
                        return self.file(HERE / "macos/AudioProbeWorklet.js")
                    return super().dispatch_get()

            server = Server(0, store); server.RequestHandlerClass = ProbeHandler
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True); thread.start()
            origin = "http://127.0.0.1:" + str(server.server_port); screenshot = output / "ENGINE_TEST_multicam_monitor.png"
            maximum = budget(14.5, 2.5)
            process = foreground([Path(binary).resolve(), "--url", origin + "/", "--output", screenshot, "--script", script, "--download-dir", downloads, "--timeout", round(maximum, 2)], budget(maximum + .2, 2.1))
            ui = read_helper_result(process); result["ui"] = ui; result["helper_exit_code"] = process.returncode
            write_json(output / "ENGINE_TEST_browser_result.json", ui)
            checks["actual_shipped_controls_succeeded"] = process.returncode == 0 and ui.get("passed") is True
            checks["no_uncaught_browser_or_download_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
            if not checks["actual_shipped_controls_succeeded"]:
                raise ValueError(ui.get("error") or "Actual monitor controls failed")
            required = {
                "author": ["two_original_camera_decoders_show_exact_shared_clock_source_frames", "one_undo_redo_of_fixed_camera_sound_without_silent_save", "nondefault_locked_stream_swapped_channels_and_authored_gain_pan", "source_mapping_saved_and_reopened"],
                "play": ["two_actual_camera_pictures_advance_on_shared_live_audio_clock", "one_live_picture_cut_preserves_uninterrupted_original_pcm_voice", "measured_nondefault_stream_swap_gain_pan_and_zero_underruns", "actual_pcm_pause_restart", "one_undo_redo_save_of_camera_cut_with_audio_lock_preserved"],
                "render": ["saved_camera_cut_audio_lock_and_simultaneous_clocks_reopen", "actual_prores_pcm_render_and_download"],
            }[operation]
            checks.update({name: name in ui.get("steps", []) for name in required})
            project = store.get(fixture["project_id"]); group = project["multicam_groups"][0]; lock = group.get("audio_lock", {})
            checks["saved_fixed_source_mapping_and_clock_binding"] = lock.get("angle_id") == group["angles"][1]["id"] and lock.get("stream_index") == 2 and lock.get("channels") == [1, 0] and len(lock.get("clock", {}).get("angles", [])) == 2
            checks["saved_timeline_gain_pan_and_original_picture_routes_preserved"] = all(c["volume"] == .5 and c["audio"]["pan"] == .25 and "stream_index" not in c["audio"] and "channels" not in c["audio"] for c in project["clips"])
            checks["actual_camera_inventory_preserved"] = len(project["assets"]) == 2 and all(identity(store.project_dir(project["id"]) / a["path"]) == next(c["identity"] for c in fixture["cameras"] if c["asset_id"] == a["id"]) for a in project["assets"])
            with store.lock:
                jobs = [copy.deepcopy(j) for key, j in store.jobs.items() if key not in jobs_before]
            if operation == "play":
                manifest = ui["metrics"]["cross_cut"]["route"]["manifest"]
                url = manifest.get("url", "")
                if not re.fullmatch(r"/api/projects/" + project["id"] + r"/audio-source/[a-f0-9]{64}", url):
                    raise ValueError("The actual PCM manifest escaped its owned original source")
                with urlopen(origin + url, timeout=budget(2, 1)) as response:
                    data = response.read(4 * 1024 * 1024)
                source = output / "ENGINE_TEST_actual_live_source.wav"; source.write_bytes(data)
                checks["actual_http_pcm_bytes_match_live_receipt"] = identity(source)["sha256"] == manifest["sha256"] and len(data) == manifest["byte_size"] and manifest["source_sha256"] == fixture["cameras"][1]["identity"]["sha256"]
                code = "import json,sys,numpy as np\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_multicam_monitor import ffmpeg\na=np.frombuffer(ffmpeg(['-i',sys.argv[2],'-map','0:a:0','-f','f32le','pipe:1']),'<f4').reshape(-1,2)\nb=np.fromfile(Path(sys.argv[3])/'truth/camera_b_1_decoded.f32le','<f4').reshape(-1,2)[:,::-1]\nprint(json.dumps({'sample_frames':len(a),'max_error':float(np.max(np.abs(a-b))) if a.shape==b.shape else None}))\n"
                inspected = foreground([sys.executable, "-I", "-B", "-c", code, HERE, source, root], budget(2.5, .6))
                if inspected.returncode:
                    raise ValueError("Independent live-source inspection failed: " + inspected.stderr[-1200:])
                measurement = json.loads(inspected.stdout); result["independent_source_pcm"] = measurement
                checks["all_live_source_samples_are_exact_original_nondefault_channel_pair"] = measurement["sample_frames"] == 288000 and measurement["max_error"] == 0
                checks["one_continuous_owned_pcm_voice_and_no_render_substitute"] = ui["metrics"]["voice_count"] == 1 and not ui["metrics"]["source_seek_events"] and any(j["kind"] == "audio-source" for j in jobs) and not any(j["kind"] == "render" for j in jobs)
            elif operation == "render":
                renders = [j for j in jobs if j["kind"] == "render"]
                if len(renders) != 1 or renders[0]["state"] != "completed" or renders[0]["result"]["profile"] != "prores":
                    raise ValueError("The actual export is not one completed owned ProRes job")
                rows = ui.get("downloads", [])
                if len(rows) != 1:
                    raise ValueError("Exactly one actual movie download must complete")
                row = rows[0]; movie = Path(row.get("path", "")).absolute(); filename = row.get("suggested_filename", "")
                valid_name = movie.name == filename if transport == "Chromium" else bool(re.fullmatch(r"ENGINE_TEST_[A-Fa-f0-9-]{36}_" + re.escape(filename), movie.name))
                if movie.parent != downloads or not valid_name or row.get("state") != "completed":
                    raise ValueError("The rendered movie escaped its owned download destination")
                rendered = store.project_dir(project["id"]) / "exports" / renders[0]["result"]["filename"]
                checks["actual_download_matches_completed_job_bytes"] = identity(movie) == identity(rendered) and identity(movie)["sha256"] == renders[0]["result"]["sha256"] and row["url"] == origin + ui["metrics"]["download_href"]
                cut = next(c["start"] for c in project["clips"] if c["start"] > 0)
                code = "import json,sys,numpy as np\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_multicam_monitor import decoded_movie\na,rgb,frames=decoded_movie(Path(sys.argv[2]));cut=int(sys.argv[4])\nb=np.fromfile(Path(sys.argv[3])/'truth/camera_b_1_decoded.f32le','<f4').reshape(-1,2)[48000:288000,::-1]*[.375,.5]\nexpected=list(range(12,12+cut))+list(range(24+cut,144))\nprint(json.dumps({'sample_frames':len(a),'max_pcm_error':float(np.max(np.abs(a-b))) if a.shape==b.shape else None,'frames':len(frames),'every_source_counter_correct':frames.tolist()==expected,'every_picture_camera_correct':bool((rgb[:cut,32,48,0]>220).all() and (rgb[cut:,32,48,2]>220).all()),'cut_frame':cut}))\n"
                inspected = foreground([sys.executable, "-I", "-B", "-c", code, HERE, movie, root, cut], budget(2.5, .5))
                if inspected.returncode:
                    raise ValueError("Independent movie decode failed: " + inspected.stderr[-1200:])
                measurement = json.loads(inspected.stdout); result["independent_movie"] = measurement
                checks["all_120_source_counter_frames_and_camera_boundary_are_exact"] = measurement["frames"] == 120 and measurement["every_source_counter_correct"] and measurement["every_picture_camera_correct"]
                checks["all_240000_stereo_sample_frames_preserve_fixed_original_source_gain_pan"] = measurement["sample_frames"] == 240000 and measurement["max_pcm_error"] <= 1 / 32768 + 1e-7
                checks["render_preserves_saved_camera_edit"] = project["clips"] == initial["clips"] and project["multicam_groups"] == initial["multicam_groups"]
            checks["actual_browser_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000
    except Exception as error:
        result["error"] = str(error)
    finally:
        if server:
            server.shutdown(); server.server_close()
        if thread:
            thread.join(timeout=.3)
        if store:
            store.shutdown()
            with store.lock:
                owned_jobs = copy.deepcopy(list(store.jobs.values()))
            checks["all_owned_jobs_terminal"] = all(j["state"] not in ("queued", "running") for j in owned_jobs)
            write_json(output / "ENGINE_TEST_owned_jobs.json", owned_jobs)
        if root and fixture and project:
            persisted = root / "workspace/projects" / fixture["project_id"] / "project.json"
            result["saved_project_identity"] = identity(persisted); (output / "ENGINE_TEST_saved_project.json").write_bytes(persisted.read_bytes())
            checks["original_media_and_independent_truth_unchanged"] = all(identity(root / "media" / c["filename"]) == c["identity"] for c in fixture["cameras"]) and {p.name: identity(p) for p in (root / "truth").iterdir()} == fixture["truth"]
        result["source_after"] = source_inventory(); checks["source_unchanged_during_actual_phase"] = result.get("source_before") == result["source_after"]
    result["elapsed_seconds"] = round(time.monotonic() - began, 3); checks["phase_within_18_second_foreground_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(k for k, v in checks.items() if not v)
    report = output / "ENGINE_TEST_multicam_monitor_report.json"; write_json(report, result)
    if result["passed"]:
        write_json(root / (operation + "-passed.json"), {"passed": True, "acceptance_id": fixture["acceptance_id"], "operation": operation,
            "saved_project_identity": result["saved_project_identity"], "source_inventory": before, "report_identity": identity(report)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operation", choices=PHASES, required=True); parser.add_argument("--fixture-workspace", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True); args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"passed": False, "reason": "Actual macOS WKWebView is required; browser acceptance cannot certify native."})); return 1
    result = run(args.binary, args.output, args.operation, args.fixture_workspace, read_json(args.source_manifest))
    print(json.dumps({"passed": result["passed"], "operation": args.operation, "checks": result["checks"], "elapsed_seconds": result["elapsed_seconds"], "error": result.get("error")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

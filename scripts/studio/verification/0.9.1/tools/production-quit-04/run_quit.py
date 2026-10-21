#!/usr/bin/env python3
"""Actual production quit alert acceptance with two genuine isolated FFmpeg jobs.

The first real render survives Keep Working and completes. A second real render
is admitted through shipped Export controls, then Cancel Jobs and Quit settles
its durable cancellation. No job delay, fake state, callback replacement, user
project, or installed-app startup is part of this independent evidence tool.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

# The initial 96-frame workload reached 86.9% at the unchanged 60-second
# first-completion deadline. Keep the real 640x360 transform/export work and
# active-job requirements; use 48 frames for this quit-behavior gate.
WIDTH, HEIGHT, FPS, FRAMES = 640, 360, 12, 48
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Expected a bounded, regular acceptance record: " + str(path))
    return json.loads(path.read_text())


def runtime_hashes(source):
    """Inspect the frozen installer declaration; do not execute it."""
    installer = source / "scripts/studio/install_macos.py"
    declarations = []
    for statement in ast.parse(installer.read_text()).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "RUNTIME_FILES" for target in statement.targets):
            declarations.append(ast.literal_eval(statement.value))
    if len(declarations) != 1:
        raise ValueError("The exact source has no unambiguous runtime file declaration")
    paths = list(declarations[0])
    if not paths or not all(isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts for path in paths):
        raise ValueError("The actual runtime declaration is unsafe")
    studio = source / "scripts/studio"
    web = studio / "web"
    for path in web.rglob("*"):
        if path.is_symlink():
            raise ValueError("A runtime web path is a symlink: " + str(path))
        if path.is_file():
            paths.append(path.relative_to(studio).as_posix())
    paths.append("macos/StudioApp.swift")
    for relative in paths:
        path = studio / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("Expected a regular frozen runtime source: " + str(path))
    return {path: sha(studio / path) for path in sorted(paths)}


def native_process(command, output):
    """Only this owned process group is cleaned up on an acceptance timeout."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=95)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
        (output / "native.stdout").write_text(stdout)
        (output / "native.stderr").write_text(stderr)
        raise RuntimeError("Actual ordinary-quit acceptance exceeded its 95-second owned-process bound") from None
    (output / "native.stdout").write_text(stdout)
    (output / "native.stderr").write_text(stderr)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def run(source, binary, python, output):
    source, binary, python, output = (path.absolute() for path in (source, binary, python, output))
    if sys.platform != "darwin":
        raise ValueError("Actual AppKit ordinary-quit acceptance requires macOS; no native result is simulated")
    if output == source or source in output.parents:
        raise ValueError("Keep independent acceptance evidence outside the frozen repository")
    build = read_json(binary.parent / "build.json")
    production = source / "scripts/studio/macos/StudioApp.swift"
    if build.get("compiled") is not True or sha(binary) != build.get("binary_sha256") or sha(production) != build.get("production_source_sha256"):
        raise ValueError("Actual helper/build receipt/production source identities differ")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("Real FFmpeg and ffprobe are required")
    output.mkdir(parents=True, exist_ok=False)
    workspace, pictures = output / "workspace", output / "native-alerts"
    pictures.mkdir()
    report = {"schema": "cinematicum-production-native-quit-v1", "passed": False,
              "acceptance_runner_sha256": sha(Path(__file__).absolute()),
              "scope": "Unchanged production ordinary-quit/alert/cancel methods and real AppKit alert buttons; isolated actual server launch and child-exit forwarding; not production launcher or installed-bundle UI acceptance",
              "fixture": "SYNTHETIC ENGINE TEST ONLY — NOT FILM FOOTAGE",
              "workload": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": FRAMES,
                           "profile": "master16", "first": "complete after Keep Working", "second": "cancel through actual ordinary-quit alert"},
              "build": build, "checks": {}, "installed_app_ui_certified": False,
              "accessibility_or_screen_recording_permission_requested": False,
              "runtime_source_sha256_before": runtime_hashes(source),
              "source_integrity_file_sha256": sha(source / "scripts/studio/source-integrity.json")}
    checks = report["checks"]
    began = time.monotonic()
    sys.path.insert(0, str(source / "scripts/studio"))
    from server import Store
    from test_high_precision import numeric_ramp, rgba16_bytes, WIDTH as SOURCE_WIDTH, HEIGHT as SOURCE_HEIGHT
    from test_editing_ui_macos import read_helper_result
    store = None
    try:
        fixture = output / "ENGINE_TEST_QUIT_16bit_source.png"
        subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-f", "rawvideo", "-pixel_format", "rgba64le",
                        "-video_size", f"{SOURCE_WIDTH}x{SOURCE_HEIGHT}", "-i", "pipe:0", "-frames:v", "1", "-c:v", "png",
                        "-pix_fmt", "rgba64be", "-threads", "1", "-update", "1", str(fixture)],
                       input=rgba16_bytes(numeric_ramp()), capture_output=True, check=True, timeout=15)
        source_sha = sha(fixture)
        # Production admission consumes its upload path. Keep the original
        # evidence fixture intact and give Store a separate copied staging file.
        upload = output / "ENGINE_TEST_QUIT_upload.png"
        shutil.copyfile(fixture, upload)
        store = Store(workspace)
        project = store.new_project({"name": "ENGINE TEST — real ordinary quit", "fps": FPS, "width": WIDTH, "height": HEIGHT})
        asset = store.admit(project["id"], upload, fixture.name)
        project = store.get(project["id"])
        project["settings"].update(image_precision="high16", transparent_background=False)
        project["clips"] = [{"id": "ordinary_quit_fixture", "asset_id": asset["id"], "track": 0,
                             "start": 0, "in": 0, "duration": FRAMES, "scale": .73, "rotation": 27, "x": .07, "y": -.09}]
        project = store.save(project["id"], project)
        directory = store.project_dir(project["id"])
        identities = {"project_id": project["id"], "asset_id": asset["id"]}
        report.update(fixture_identity=identities, source_fixture_sha256=source_sha, initial_project=project)
        # Release the real workspace lock before the native helper launches its
        # own real server process. Do not reopen Store after the tested quit:
        # doing so would replace the final shutdown receipt during cleanup.
        store.shutdown(); store = None
        initial_exit = read_json(workspace / "last-session-exit.json")
        report["fixture_preparation_exit"] = initial_exit
        bindings = "const QUIT_TEST=" + json.dumps(identities) + ";\n"
        scripts = {}
        for original, name in (("QuitWorkflow.js", "bound-first-job.js"), ("QuitRestart.js", "bound-second-job.js")):
            path = Path(__file__).with_name(original)
            target = output / name
            target.write_text(bindings + path.read_text())
            scripts[original] = {"source_sha256": sha(path), "bound_sha256": sha(target), "path": str(target)}
        report["ui_scripts"] = scripts
        command = [str(binary), "--python", str(python), "--server", str(source / "scripts/studio/server.py"),
                   "--workspace", str(workspace), "--evidence", str(pictures),
                   "--script", scripts["QuitWorkflow.js"]["path"], "--restart-script", scripts["QuitRestart.js"]["path"]]
        (output / "native-command.json").write_text(json.dumps(command, indent=2) + "\n")
        process = native_process(command, output)
        native = read_helper_result(process)
        report.update(native=native, native_returncode=process.returncode)
        checks["actual_native_ordinary_quit_gate"] = process.returncode == 0 and native.get("passed") is True
        first_id = native.get("workflow", {}).get("job_id", "")
        second_id = native.get("second_render", {}).get("job_id", "")
        if not all(IDENTIFIER.fullmatch(value) for value in (first_id, second_id)) or first_id == second_id:
            raise ValueError("Native result does not identify two distinct actual owned jobs")
        jobs = [read_json(path) for path in sorted((workspace / "jobs").glob("*.json"))]
        renders = [job for job in jobs if job.get("kind") == "render"]
        report["durable_render_jobs"] = renders
        first = next((job for job in renders if job.get("id") == first_id), {})
        second = next((job for job in renders if job.get("id") == second_id), {})
        checks["two_distinct_actual_render_jobs"] = len(renders) == 2 and {job["id"] for job in renders} == {first_id, second_id}
        checks["first_render_durably_completed"] = first.get("state") == "completed" and first.get("finished_at") is not None and isinstance(first.get("result"), dict)
        checks["first_actual_work_finished_after_keep_working_click"] = isinstance(native.get("keep_working_click_at"), (int, float)) and first.get("finished_at", 0) >= native["keep_working_click_at"]
        checks["second_render_durably_cancelled"] = second.get("state") == "cancelled" and second.get("finished_at") is not None and second.get("result") is None
        checks["second_admitted_after_first_completed"] = second.get("created_at", 0) >= first.get("finished_at", float("inf"))
        saved = read_json(directory / "project.json")
        report["saved_project"] = saved
        checks["ordinary_dirty_edit_saved_and_retained"] = saved.get("settings", {}).get("transparent_background") is True and saved["settings"].get("image_precision") == "high16"
        first_snapshot = read_json(workspace / "jobs" / (first_id + ".snapshot"))
        second_snapshot = read_json(workspace / "jobs" / (second_id + ".snapshot"))
        report["render_snapshot_sha256"] = {first_id: sha(workspace / "jobs" / (first_id + ".snapshot")), second_id: sha(workspace / "jobs" / (second_id + ".snapshot"))}
        checks["actual_job_snapshots_separate_before_and_after_saved_edit"] = first_snapshot.get("settings", {}).get("transparent_background") is False and second_snapshot.get("settings", {}).get("transparent_background") is True
        completed = directory / "exports" / (first_id + ".mkv")
        if completed.is_symlink() or not completed.is_file():
            raise ValueError("First actual completed master is missing after the second job was cancelled")
        complete_sha, complete_size = sha(completed), completed.stat().st_size
        observation = native.get("completed_master_before_cancellation")
        checks["completed_master_bytes_preserved_across_later_cancellation"] = observation == {"path": str(completed), "bytes": complete_size, "sha256": complete_sha}
        receipt = first.get("result") or {}
        checks["independent_completed_master_hash_matches_receipt"] = receipt.get("sha256") == complete_sha and receipt.get("filename") == first_id + ".mkv" and receipt.get("profile") == "master16"
        export_receipt = read_json(directory / "exports" / (first_id + ".json"))
        checks["completed_export_manifest_survives_cancellation"] = export_receipt.get("result") == receipt and export_receipt.get("snapshot") == first_snapshot
        export_paths = sorted(path.name for path in (directory / "exports").iterdir())
        report["export_directory_after_quit"] = export_paths
        checks["cancelled_job_publishes_no_media_or_partial_export"] = export_paths == sorted([first_id + ".json", first_id + ".mkv"])
        probe = json.loads(subprocess.run([ffprobe, "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(completed)],
                                          capture_output=True, text=True, check=True, timeout=20).stdout)
        streams = probe["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        audio = next(stream for stream in streams if stream["codec_type"] == "audio")
        report["retained_master_streams"] = streams
        checks["retained_master_independently_decodes_exact_format_and_frame_count"] = video["codec_name"] == "ffv1" and video["pix_fmt"] == "gbrap16le" and video["width"] == WIDTH and video["height"] == HEIGHT and int(video["nb_read_frames"]) == FRAMES and video["r_frame_rate"] == f"{FPS}/1" and audio["codec_name"] == "pcm_s16le" and audio["channels"] == 2 and int(audio["sample_rate"]) == 48000
        decoded = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(completed), "-map", "0:v:0",
                                  "-map", "0:a:0", "-threads", "1", "-f", "null", "-"], capture_output=True, text=True, check=True, timeout=25)
        checks["retained_picture_and_audio_fully_decode_without_error"] = decoded.returncode == 0 and not decoded.stderr.strip()
        exit_receipt = read_json(workspace / "last-session-exit.json")
        report["final_session_exit"] = exit_receipt
        checks["durable_exit_reason_is_native_confirmed_job_cancellation"] = exit_receipt.get("reason") == "native-user-confirmed-job-cancellation" and exit_receipt.get("completed_at", 0) > initial_exit["completed_at"]
        # The second job can finish cancellation between prepare-quit and the
        # SIGTERM handler's active-at-shutdown snapshot. Both legal orderings
        # must agree with the actual durable terminal job state.
        at_shutdown = {job["id"] for job in exit_receipt.get("active_at_shutdown", [])}
        terminal = {job["id"]: job["state"] for job in exit_receipt.get("terminal_jobs", [])}
        durable = {job["id"]: job["state"] for job in jobs}
        checks["shutdown_receipt_matches_all_affected_terminal_jobs"] = set(terminal) == at_shutdown and first_id not in at_shutdown and all(state in {"completed", "cancelled", "failed"} and durable.get(job_id) == state for job_id, state in terminal.items())
        checks["actual_owned_server_exited_normally"] = native.get("owned_server_exit_status") == 0
        checks["source_fixture_identity_preserved"] = sha(fixture) == source_sha and sha(directory / asset["path"]) == source_sha
        alerts = native.get("alerts", [])
        checks["both_actual_native_alert_choices_observed"] = len(alerts) == 2 and [item.get("action") for item in alerts] == ["Keep Working", "Cancel Jobs and Quit"]
        captures = []
        for alert in alerts:
            path = Path(alert.get("picture", ""))
            valid = path.parent == pictures and not path.is_symlink() and path.is_file() and path.stat().st_size > 1000 and path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            captures.append({"path": str(path), "valid": valid, "sha256": sha(path) if valid else None})
        report["actual_alert_captures"] = captures
        checks["actual_alert_captures_retained"] = len(captures) == 2 and all(item["valid"] for item in captures)
        checks["frozen_production_class_and_runtime_unchanged"] = sha(production) == build["production_source_sha256"] and runtime_hashes(source) == report["runtime_source_sha256_before"]
        if not all(checks.values()):
            report["error"] = "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
    except Exception as error:
        report["error"] = str(error)
        checks["completed_without_fixture_or_native_error"] = False
        if isinstance(error, subprocess.CalledProcessError):
            report["subprocess_stderr"] = str(error.stderr)[-5000:]
    finally:
        if store is not None:
            store.shutdown()
    report["elapsed_seconds"] = round(time.monotonic() - began, 3)
    report["passed"] = bool(checks) and all(checks.values()) and "error" not in report
    (output / "production-quit-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", required=True, type=Path, help="New isolated evidence directory outside the repository")
    args = parser.parse_args()
    try:
        report = run(args.source, args.binary, args.python, args.output)
        print(json.dumps({"passed": report["passed"], "checks": report["checks"], "error": report.get("error"),
                          "report": str(args.output.absolute() / "production-quit-report.json"),
                          "elapsed_seconds": report["elapsed_seconds"]}, indent=2))
        return 0 if report["passed"] else 1
    except Exception as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

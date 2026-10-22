#!/usr/bin/env python3
"""One bounded actual AppKit phase; never starts the installed application.

Use --phase app-script, bootstrap, or protection with separate evidence folders.
The helper replaces only production startup with a fresh owned ENGINE TEST
server. No user workspace, force quit, fake job or active-work bypass is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE / "verification/0.9.1/tools/production-quit-05/QuitWorkflow.js"
FILES = ("macos/StudioApp.swift", "web/app.js", "server.py", "engine.py", "startup_quit_fixture.py",
         "macos/StartupQuitAcceptance.swift", "build_startup_quit.py", "test_startup_quit_macos.py",
         "verification/0.9.1/tools/production-quit-05/QuitWorkflow.js")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Expected a bounded regular acceptance record")
    return json.loads(path.read_text())


def run(binary, python, output, phase):
    if sys.platform != "darwin":
        raise ValueError("Actual AppKit acceptance requires macOS; no result is simulated")
    binary, python, output = (Path(path).resolve() for path in (binary, python, output))
    source_before = {name: sha(HERE / name) for name in FILES}
    build = read(binary.parent / "build.json")
    if (build.get("compiled") is not True or sha(binary) != build.get("binary_sha256")
            or source_before["macos/StudioApp.swift"] != build.get("production_source_sha256")
            or source_before["macos/StartupQuitAcceptance.swift"] != build.get("harness_sha256")):
        raise ValueError("Native helper, build receipt or exact production source differs")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"schema": "cinematicum-startup-quit-acceptance-v1", "passed": False, "phase": phase,
              "native_certified": False, "engine_test_only": True, "installed_app_certified": False,
              "force_kill_used": False, "checks": {}, "source_sha256": source_before, "build": build}
    checks = report["checks"]
    command = [str(binary), "--python", str(python), "--server", str(HERE / "startup_quit_fixture.py"),
               "--workspace", str(output / "workspace"), "--evidence", str(output), "--phase", phase,
               "--workflow", str(WORKFLOW)]
    report["command"] = command
    try:
        # Native self-deadline is 13 seconds plus at most two seconds of owned
        # graceful failure cleanup. Outer timeout records failure without kill.
        with (output / "native.stdout").open("wb") as stdout, (output / "native.stderr").open("wb") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            try:
                code = process.wait(timeout=17)
            except subprocess.TimeoutExpired:
                report["owned_helper_pid"] = process.pid
                raise RuntimeError("Native helper exceeded its bound; no force termination was used") from None
        native = read(output / "native-report.json")
        report["native"] = native
        checks["actual_production_native_quit_phase"] = code == 0 and native.get("passed") is True
        fixture = read(output / "fixture.json")
        project_dir = output / "workspace/projects" / fixture["project_id"]
        saved, initial = read(project_dir / "project.json"), read(output / "initial-project.json")
        receipt = read(output / "workspace/last-session-exit.json")
        report["shutdown_receipt"] = receipt
        report["saved_project_sha256"] = sha(project_dir / "project.json")
        if phase == "protection":
            job_id = native.get("workflow", {}).get("job_id")
            if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
                raise ValueError("Actual native render identity is invalid")
            job = read(output / "workspace/jobs" / (job_id + ".json"))
            report["actual_job"] = job
            checks["actual_worker_durably_cancelled_after_choice"] = job.get("state") == "cancelled" and job.get("result") is None
            checks["explicit_active_job_cancellation_reason"] = receipt.get("reason") == "native-user-confirmed-job-cancellation"
            checks["actual_dirty_edit_persisted"] = saved["settings"].get("transparent_background") is True and initial["settings"].get("transparent_background") is False
            source = fixture["source"]
            checks["source_media_preserved"] = sha(project_dir / source["path"]) == source["sha256"]
            checks["no_cancelled_partial_export"] = not (project_dir / "exports" / (job_id + ".mkv")).exists()
            checks["two_actual_native_alert_pictures"] = all((output / name).is_file() and (output / name).stat().st_size > 1000 for name in ("keep-working.png", "cancel-jobs.png"))
        else:
            checks["initial_project_preserved_exactly"] = saved == initial
            checks["no_work_bypassed_on_startup_quit"] = receipt.get("reason") == "native-quit-no-active-jobs" and receipt.get("active_at_shutdown") == [] and receipt.get("terminal_jobs") == []
        checks["source_remained_frozen"] = source_before == {name: sha(HERE / name) for name in FILES}
        if not all(checks.values()):
            report["error"] = "Failed: " + ", ".join(name for name, value in checks.items() if not value)
    except Exception as error:
        report["error"] = str(error)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["passed"] = bool(checks) and all(checks.values()) and "error" not in report
    report["native_certified"] = report["passed"]
    (output / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("app-script", "bootstrap", "protection"))
    args = parser.parse_args()
    report = run(args.binary, args.python, args.output, args.phase)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

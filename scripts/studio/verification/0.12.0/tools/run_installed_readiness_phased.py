#!/usr/bin/env python3
"""Bounded installed-readiness observations with one private preservation baseline.

Uses the accepted unchanged launch helper/controller. No product code is
injected, no HTTP mutation or force termination is performed. Full workspace
hashing happens only in prepare/verify; each tool phase persists its observed
result before that separate preservation gate. All eight 0.12 selected runtimes
include deep and the actual dense-flow retime readiness probe.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

CORE = "c9869e86b9421b7fdc083d249b1616114320f0d5"
CORE_TREE = "941da9dbc805788a89c610ee688cc17de08fccc4"
CORE_MANIFEST = "31125bf9cef0a920bc0a5e45b2f132fdfbf4d3a5640d55cb01af372266d736d3"
RUNNER_SHA = "f772386b7c36db369d150c48e42dd16b550f5c80c91f77c8000129135ef73bfe"
CONTROLLER_SOURCE_SHA = "e7d5dd055bd4afd8d2e5fce05d02cd2402970bccf535756889284e4f709a47a7"
CONTROLLER_BINARY_SHA = "cdd2bfe16006d71e685f9ddc6bb844bdf8d970b9681217702c9aaeb70833b6f8"
NATIVE_SHA = "ca2a5bf65d934b87b0dfafc55392b648bda650c1c7ce76491cc5b21e20a84b39"
TOOLS = ("deep", "ray-optics", "physical-rendering", "learned", "reconstruction", "scene-processing", "multicam-sync", "retime")
HEX = re.compile(r"[a-f0-9]{64}")
SCHEMA = "cinematicum-installed-readiness-phased-v2"
TOOL_CHECKS = {
    "existing_production_app_not_adopted",
    "live_lock_job_project_and_preview_guards_passed",
    "exact_new_canonical_app_launched_by_launchservices",
    "actual_owned_bundled_server_default_workspace_and_loopback_listener",
    "actual_bootstrap_and_required_runtime_flags",
    "live_editor_matches_accepted_installed_bytes",
    "one_selected_actual_installed_default_runtime_available",
    "owned_app_alive_after_actual_readiness",
    "native_window_present_when_observable",
    "actual_first_ordinary_native_quit_completed",
    "owned_bundled_server_exited",
    "workspace_ownership_released",
    "fresh_actual_job_free_shutdown_receipt",
    "source_controller_and_native_pins_unchanged",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def source_bytes(path):
    """Bounded NOFOLLOW read before importing the hash-pinned accepted helper."""
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "Use explicit absolute paths without parent traversal")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= 16 * 1024**2, "Expected bounded regular metadata/source")
            data = bytearray()
            while True:
                block = os.read(leaf, 1024 * 1024)
                if not block:
                    break
                data.extend(block)
                require(len(data) <= 16 * 1024**2, "Source metadata grew beyond its limit")
            after = os.fstat(leaf)
            current = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(key(before) == key(after) == key(current) and len(data) == before.st_size, "Source changed during inspection")
            return bytes(data)
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def sha(path):
    return hashlib.sha256(source_bytes(path)).hexdigest()


def load_helper(args):
    validate_core_commit(args.expected_core_commit)
    require(HEX.fullmatch(args.expected_helper_sha256 or ""), "Expected coordinator SHA256 is required")
    require(sha(Path(__file__).absolute()) == args.expected_helper_sha256, "Coordinator differs from its explicit source pin")
    require(sha(args.runner) == RUNNER_SHA, "Accepted launch-helper source differs")
    require(sha(args.runner.parent / "InstalledAppControl.swift") == CONTROLLER_SOURCE_SHA, "Accepted controller source differs")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("cinematicum_accepted_installed_launch", args.runner)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    # This is the accepted helper's explicit CLI configuration, also assigned
    # by its main(). No helper function, class, path, or control API is replaced.
    helper.NATIVE_SHA = NATIVE_SHA
    return helper


def outside_protected(h, value):
    p = Path(value)
    require(p.is_absolute() and ".." not in p.parts, "Evidence paths must be explicit and absolute")
    require(not p.is_relative_to(h.APP) and not p.is_relative_to(h.WORKSPACE), "Evidence must stay outside the app and protected workspace")
    return p


def project_guards(h, names, expected_projects=None):
    projects = sorted(name for name in names if re.fullmatch(r"projects/[a-f0-9]{32}/project\.json", name))
    require(projects, "Read-only launch refuses an empty project workspace")
    if expected_projects is not None:
        require(projects == expected_projects, "Existing project membership changed between phases")
    for name in projects:
        _, project = h.read_json(h.WORKSPACE / name)
        require(isinstance(project, dict) and project.get("id") == name.split("/")[1], "Existing project identity is unreadable")
    cleanup = [name for name in names if re.fullmatch(r"projects/[a-f0-9]{32}/(?:archive-upload-[a-f0-9]{32}\.zip|relink-upload-[a-f0-9]{32}\.[a-zA-Z0-9]+)", name)]
    require(not cleanup, "Startup-owned temporary inputs are present; read-only launch refused")
    return projects, h.no_preview_eviction(projects)


def names_only(h, path):
    """Inspect entry types/names, never reread the multi-GB protected contents."""
    found, entries, size = [], 0, 0
    def visit(fd, prefix="", depth=0):
        nonlocal entries, size
        require(depth <= 64, "Workspace nesting exceeds its bound")
        with os.scandir(fd) as scan:
            names = sorted(entry.name for entry in scan)
        entries += len(names)
        require(entries <= 20_000, "Workspace entry count exceeds its bound")
        for name in names:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode), "Workspace symlink traversal refused")
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, h.DIRECTORY_FLAGS, dir_fd=fd)
                try:
                    visit(child, prefix + name + "/", depth + 1)
                finally:
                    os.close(child)
            else:
                require(stat.S_ISREG(info.st_mode) and len(found) < h.MAX_FILES, "Nonregular/excessive workspace entries")
                require(name != ".env" and not name.startswith(".env."), "Credential-like file is outside this gate")
                size += info.st_size
                require(size <= h.MAX_BYTES, "Workspace size exceeds its bound")
                found.append(prefix + name)
    fd = h.open_directory(path)
    try:
        visit(fd)
    finally:
        os.close(fd)
    return found


def validate_core_commit(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{40}", value),
            "Supply the exact accepted core commit; placeholders or inferred pins are not allowed")
    require(value == CORE, "Explicit core commit differs from the accepted 0.12 freeze")
    return value


def assert_core_tree(h, source_root, core_commit):
    validate_core_commit(core_commit)
    fd = h.open_directory(Path(source_root)); os.close(fd)
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(["git", "-C", str(source_root), "-c", "core.fsmonitor=false",
                             "rev-parse", "--verify", core_commit + "^{tree}"],
                            capture_output=True, text=True, timeout=10, env=environment)
    require(result.returncode == 0 and result.stdout.strip() == CORE_TREE,
            "Explicit core commit does not resolve to the accepted 0.12 tree")


def validate_retime_readiness(value):
    require(isinstance(value, dict) and value.get("available") is True,
            "Actual installed retime runtime is unavailable")
    require(value.get("versions") == {"numpy": "2.3.5", "opencv-python-headless": "4.11.0.86"},
            "Actual retime runtime differs from the pinned Tracking packages")
    require(value.get("method") == "OpenCV DIS medium bidirectional dense optical flow",
            "Retime response does not identify the accepted measured-flow method")
    probe = value.get("operation_probe")
    error = probe.get("median_displacement_error_pixels") if isinstance(probe, dict) else None
    require(type(error) in (int, float) and math.isfinite(error) and 0 <= error <= .2,
            "Actual retime dense-flow displacement probe is missing or outside tolerance")
    expected = {"analysis_edge": 640, "max_frames": 240, "max_edge": 1280, "max_pixels": 1280 * 720}
    require(all(type(value.get(k)) is int and value[k] == v for k, v in expected.items())
            and value.get("rendered_playback") is True,
            "Retime response does not expose the accepted bounded rendered-playback contract")
    return {"available": True, "versions": value["versions"], "method": value["method"],
            "operation_probe": {"median_displacement_error_pixels": error},
            **expected, "rendered_playback": True}


def source_pin(h, source_root, source, core_commit):
    validate_core_commit(core_commit)
    require(source.get("git_head") == core_commit and source.get("source_integrity", {}).get("sha256") == CORE_MANIFEST,
            "Installation source evidence is not the explicitly accepted 0.12 core")
    assert_core_tree(h, source_root, core_commit)
    studio = Path(source_root) / "scripts/studio"
    code = {name: source[name] for name in ("runtime_files", "native_sources", "installer")}
    require(h.digest(h.canonical(code)) == source["code_identity_sha256"], "Installation source code identity is inconsistent")
    for name, record in source["runtime_files"].items():
        require(h.file_record(studio / name)[0] == record, "Accepted runtime source changed: " + name)
    for name, record in source["native_sources"].items():
        require(h.file_record(studio / "macos" / name)[0] == record, "Accepted native source changed: " + name)
    require(h.file_record(studio / "install_macos.py")[0] == source["installer"], "Accepted installer source changed")
    require(h.file_record(studio / "source-integrity.json")[0] == source["source_integrity"], "Accepted source-integrity manifest changed")
    return {"core_commit": core_commit, "core_tree": CORE_TREE, "source_manifest_sha256": CORE_MANIFEST,
            "code_identity_sha256": source["code_identity_sha256"], "runtime_file_count": source["runtime_file_count"]}


def runtime_pins(h, state):
    require(state["core_tree"] == CORE_TREE and state["controller_binary_sha256"] == CONTROLLER_BINARY_SHA,
            "Prepared core tree or accepted controller binary pin differs")
    binary = Path(state["paths"]["binary"])
    build_record, build = h.read_json(binary.parent / "build.json")
    require(build_record == state["controller_build_record"] and build.get("compiled") is True
            and build.get("schema") == "cinematicum-installed-app-controller-build-v1"
            and build.get("source_sha256") == CONTROLLER_SOURCE_SHA
            and build.get("binary_sha256") == state["controller_binary_sha256"]
            and h.file_record(binary)[0]["sha256"] == state["controller_binary_sha256"], "Accepted controller identity changed")
    install_record, installation = h.read_json(Path(state["paths"]["installation"]))
    require(install_record == state["installation_record"], "Installation evidence changed")
    require(h.installation_identity(installation) == state["expected_installed_identity"], "Accepted installed identity changed")
    require(h.file_record(h.APP / "Contents/MacOS/CINEMATICUMStudio")[0]["sha256"] == NATIVE_SHA, "Installed native binary changed")
    require(h.file_record(h.APP / "Contents/Resources/source-manifest.json")[0] == state["expected_installed_identity"]["embedded_source_manifest"], "Installed source manifest changed")
    return source_pin(h, state["paths"]["source"], state["source"], state["core_commit"])


def phase_binding(h, state, baseline_sha):
    return {"private_baseline_sha256": baseline_sha, "coordinator_sha256": state["coordinator_sha256"],
            "accepted_runner_sha256": RUNNER_SHA, "controller_source_sha256": CONTROLLER_SOURCE_SHA,
            "controller_binary_sha256": state["controller_binary_sha256"], "installed_native_sha256": NATIVE_SHA,
            "installation_evidence_sha256": state["installation_record"]["sha256"],
            "core_commit": state["core_commit"], "core_tree": CORE_TREE, "core_source_manifest_sha256": CORE_MANIFEST,
            "source_code_identity_sha256": state["source"]["code_identity_sha256"]}


def load_state(h, args):
    require(HEX.fullmatch(args.baseline_sha256 or ""), "The exact private baseline SHA256 is required")
    record, state = h.read_json(args.private_baseline)
    require(record["sha256"] == args.baseline_sha256 and state.get("schema") == SCHEMA + ":private-baseline", "Private baseline identity differs")
    require(state["coordinator_sha256"] == args.expected_helper_sha256 and state["paths"]["runner"] == str(args.runner)
            and state["paths"]["output"] == str(args.output) and state["paths"]["private_baseline"] == str(args.private_baseline),
            "Phase paths/source differ from the exact prepared baseline")
    require(tuple(state["tools"]) == TOOLS, "Prepared tool set differs")
    require(state["core_commit"] == args.expected_core_commit and state["core_tree"] == CORE_TREE,
            "Phase commit differs from the explicitly prepared source pin")
    _, prepared = h.read_json(args.output / "prepare-report.json")
    require(prepared.get("passed") is True and prepared.get("private_baseline_sha256") == args.baseline_sha256,
            "Preparation did not pass or refers to another private baseline")
    runtime_pins(h, state)
    return state


def prepare(h, args):
    started = time.monotonic()
    output = outside_protected(h, args.output)
    private = outside_protected(h, args.private_baseline)
    require(not private.is_relative_to(output) and not output.is_relative_to(private.parent), "Private snapshots and public evidence must use separate sibling trees")
    for p in (output.parent, private.parent.parent):
        fd = h.open_directory(p); os.close(fd)
    require(not output.exists() and not private.parent.exists(), "Use fresh evidence and private-baseline directories")
    require(HEX.fullmatch(args.expected_controller_sha256 or "") and HEX.fullmatch(args.expected_installation_sha256 or ""), "Explicit controller and installation evidence pins are required")
    require(args.expected_controller_sha256 == CONTROLLER_BINARY_SHA, "Use the exact accepted 0.12 controller binary pin")
    install_record, installation = h.read_json(args.installation_evidence)
    require(install_record["sha256"] == args.expected_installation_sha256 and installation.get("schema") == "cinematicum-installation-after-v1", "Use the exact independently collected private after-receipt")
    expected = h.installation_identity(installation)
    source_root = Path(installation["paths"]["source"])
    for p in (output, private):
        require(not p.is_relative_to(source_root) and not p.is_relative_to(Path(installation["paths"]["original_checkout"])), "Private/public evidence must remain outside source checkouts")
    output.mkdir(mode=0o700)
    private.parent.mkdir(mode=0o700)
    report = {"schema": SCHEMA + ":prepare", "passed": False, "checks": {}, "tools": list(TOOLS),
              "full_snapshot_private": True, "full_workspace_hashes_deferred_during_tool_phases": True}
    try:
        build_record, build = h.read_json(args.binary.parent / "build.json")
        state = {"schema": SCHEMA + ":private-baseline", "created_unix": time.time(), "tools": list(TOOLS),
                 "core_commit": args.expected_core_commit, "core_tree": CORE_TREE,
                 "coordinator_sha256": args.expected_helper_sha256,
                 "paths": {"runner": str(args.runner), "binary": str(args.binary), "installation": str(args.installation_evidence),
                           "source": str(source_root), "output": str(output), "private_baseline": str(private)},
                 "controller_build_record": build_record, "controller_binary_sha256": args.expected_controller_sha256,
                 "installation_record": install_record, "expected_installed_identity": expected, "source": installation["source"]}
        report["source_binding"] = runtime_pins(h, state)
        report["preflight"] = h.native_control(args.binary, None, "preflight", output, "native-preflight")
        require(report["preflight"].get("existing_production_app_count") == 0, "An existing production app cannot be adopted")
        h.workspace_unlocked(); report["jobs"] = h.no_active_jobs()
        workspace = h.tree(h.WORKSPACE)
        projects, preview = project_guards(h, workspace["files"])
        app = h.tree(h.APP)
        require(app["inventory_sha256"] == expected["bundle_inventory_sha256"] and app["file_count"] == expected["bundle_file_count"], "Whole bundle differs from accepted installation")
        h.workspace_unlocked(); h.no_active_jobs()
        state.update(bundle_before=app, workspace_before=workspace, projects=projects)
        h.write_new(private, state)
        baseline_sha = h.file_record(private)[0]["sha256"]
        report.update(private_baseline_sha256=baseline_sha, binding=phase_binding(h, state, baseline_sha),
                      workspace_before=h.private_inventory(workspace, h.OPERATIONAL), preview_guard=preview,
                      bundle_file_count=app["file_count"], bundle_inventory_sha256=app["inventory_sha256"], existing_project_count=len(projects))
        report["checks"] = {"accepted_source_controller_native_and_installation_pinned": True,
                            "no_existing_app_or_active_jobs_or_workspace_owner": True,
                            "existing_projects_valid_without_startup_cleanup_or_preview_eviction": True,
                            "whole_bundle_matches_verified_installation": True,
                            "full_protected_workspace_baseline_captured_privately": True}
        report["passed"] = True
    except Exception as error:
        report["error"] = h.safe_error(error)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    h.write_new(output / "prepare-report.json", report)
    return report


def tool_phase(h, args):
    state = load_state(h, args)
    require(args.tool in TOOLS, "Only the eight selected 0.12 readiness tools are allowed")
    output = args.output / args.tool
    output.mkdir(mode=0o700, exist_ok=False)
    binary = Path(state["paths"]["binary"])
    report = {"schema": SCHEMA + ":tool", "passed": False, "tool": args.tool, "checks": {},
              "binding": phase_binding(h, state, args.baseline_sha256), "preservation_status": "pending_separate_verify_phase",
              "force_termination_used": False, "permissions_requested": False, "production_code_injected": False,
              "project_content_recorded": False, "scope": "Actual installed default-runtime GET readiness, source-bound native launch and ordinary quit; final preservation is separate."}
    h.write_new(output / "phase-started.json", {"schema": SCHEMA + ":started", "tool": args.tool,
                "binding": report["binding"], "started_unix": time.time()})
    started = time.monotonic(); checks = report["checks"]
    owned_path = owned = child = port = None
    try:
        preflight = h.native_control(binary, None, "preflight", output, "native-preflight")
        require(preflight.get("existing_production_app_count") == 0, "Existing production app cannot be adopted")
        checks["existing_production_app_not_adopted"] = True
        h.workspace_unlocked(); report["jobs_before_launch"] = h.no_active_jobs()
        _, report["preview_guard"] = project_guards(h, names_only(h, h.WORKSPACE), state["projects"])
        checks["live_lock_job_project_and_preview_guards_passed"] = True
        launch = h.native_control(binary, None, "launch", output, "native-launch")
        owned = launch["owned"]; owned_path = output / "owned-launch.json"; h.write_new(owned_path, owned)
        report["launch"] = launch
        require(launch.get("creates_new_instance") is True and owned.get("native_sha256") == NATIVE_SHA, "LaunchServices did not return the exact new owned native instance")
        checks["exact_new_canonical_app_launched_by_launchservices"] = True
        child = h.find_bundled_child(owned["pid"]); port = h.child_port(child)
        report["owned_server"] = {**child, "loopback_port": port,
                                  "bundled_script_sha256": h.file_record(h.APP / "Contents/Resources/studio/server.py")[0]["sha256"]}
        checks["actual_owned_bundled_server_default_workspace_and_loopback_listener"] = True
        bootstrap, headers = h.get(port, "/api/bootstrap")
        report["bootstrap_runtime"] = h.sanitize_bootstrap(bootstrap, len(state["projects"])); del bootstrap
        require(str(headers["server"]).startswith("CINEMATICUM/" + h.VERSION), "Installed HTTP engine identity differs")
        checks["actual_bootstrap_and_required_runtime_flags"] = True
        for route, filename in (("/", "index.html"), ("/app.js", "app.js")):
            body, _ = h.get(port, route, as_json=False)
            expected = state["bundle_before"]["files"]["Contents/Resources/studio/web/" + filename]
            require(h.digest(body) == expected["sha256"] == h.file_record(h.APP / "Contents/Resources/studio/web" / filename)[0]["sha256"], "Live editor differs from the accepted installed bytes")
        checks["live_editor_matches_accepted_installed_bytes"] = True
        readiness, _ = h.get(port, "/api/" + args.tool + "-capabilities")
        require(isinstance(readiness, dict) and readiness.get("available") is True, "Installed default runtime is unavailable: " + args.tool)
        if args.tool == "physical-rendering":
            require(readiness.get("pbrt_available") is True, "Actual installed PBRT runtime is unavailable")
        if args.tool == "learned":
            require(set(readiness.get("models", {})) == {"sam2", "tapir"}, "Actual installed learned runtime must expose both checkpoints")
        report["installed_tool_readiness"] = {"available": True, "response_sha256": h.digest(h.canonical(readiness)),
                                              "pbrt_available": readiness.get("pbrt_available") if args.tool == "physical-rendering" else None}
        if args.tool == "retime":
            report["installed_tool_readiness"]["retime_probe"] = validate_retime_readiness(readiness)
        checks["one_selected_actual_installed_default_runtime_available"] = True
        deadline = time.monotonic() + 8; observed = None; attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            observation = h.native_control(binary, owned_path, "observe", output, "native-observe-" + str(attempt))
            observed = observation.get("owned", {})
            require(observed.get("running") is True, "Owned installed app exited during observation")
            if observed.get("finished_launching") is True and (observed.get("window_metadata_available") is False or observed.get("normal_window_count", 0) > 0):
                break
            time.sleep(.2)
        require(observed and observed.get("finished_launching") is True, "Owned installed app never completed launch")
        checks["owned_app_alive_after_actual_readiness"] = observed.get("running") is True
        checks["native_window_present_when_observable"] = observed.get("window_metadata_available") is False or observed.get("normal_window_count", 0) > 0
        report["window_observation"] = {k: observed[k] for k in ("window_metadata_available", "normal_window_count", "onscreen_window_count", "window_observation_limit") if k in observed}
        h.assert_child(child); require(h.child_port(child, timeout=1) == port, "Owned server listener changed")
        report["jobs_before_quit"] = h.no_active_jobs()
        bootstrap, _ = h.get(port, "/api/bootstrap")
        report["bootstrap_before_quit"] = h.sanitize_bootstrap(bootstrap, len(state["projects"])); del bootstrap
        report["ordinary_quit"] = h.native_control(binary, owned_path, "terminate", output, "native-ordinary-quit")
        require(report["ordinary_quit"].get("owned_app_terminated") is True, "Owned ordinary termination did not complete")
        checks["actual_first_ordinary_native_quit_completed"] = True
        require(child["pid"] not in h.process_table(), "Owned bundled server remains alive")
        checks["owned_bundled_server_exited"] = True
        h.workspace_unlocked(); checks["workspace_ownership_released"] = True
        _, exit_receipt = h.read_json(h.WORKSPACE / "last-session-exit.json")
        require(exit_receipt.get("reason") == "native-quit-no-active-jobs" and exit_receipt.get("completed_at", 0) >= owned["launch_unix"], "Fresh ordinary shutdown receipt absent")
        active = exit_receipt.get("active_at_shutdown", [])
        require(all(job.get("kind") in h.EPHEMERAL for job in active), "Durable jobs were active at shutdown")
        report["canonical_quit_receipt"] = {"reason": exit_receipt["reason"], "completed_at": exit_receipt["completed_at"],
                                            "ephemeral_jobs_at_shutdown_count": len(active), "durable_jobs_at_shutdown_count": 0,
                                            "terminal_state_counts": dict(Counter(job.get("state") for job in exit_receipt.get("terminal_jobs", [])))}
        checks["fresh_actual_job_free_shutdown_receipt"] = True
        runtime_pins(h, state); checks["source_controller_and_native_pins_unchanged"] = True
    except Exception as error:
        report["error"] = h.safe_error(error); checks["completed_without_observation_error"] = False
    finally:
        if owned_path is not None and not report.get("ordinary_quit", {}).get("owned_app_terminated"):
            try:
                h.no_active_jobs()
                status = h.native_control(binary, owned_path, "observe", output, "native-cleanup-observe")
                if status.get("owned", {}).get("running"):
                    if child is not None and port is not None:
                        h.assert_child(child)
                        value, _ = h.get(port, "/api/bootstrap")
                        h.sanitize_bootstrap(value, len(state["projects"])); del value
                    h.no_active_jobs()
                    report["failure_cleanup"] = h.native_control(binary, owned_path, "terminate", output, "native-cleanup-ordinary-quit")
            except Exception as error:
                report["failure_cleanup_error"] = h.safe_error(error)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["passed"] = bool(checks) and all(checks.values()) and "error" not in report
    report["event_records"] = {p.name: h.file_record(p)[0] for p in sorted(output.iterdir()) if p.is_file()}
    # No whole-workspace/bundle rehash occurs here or in a finally block.
    h.write_new(output / "tool-report.json", report)
    return report


def compare_workspace(h, before, after):
    old = {n: r for n, r in before["files"].items() if n not in h.OPERATIONAL}
    new = {n: r for n, r in after["files"].items() if n not in h.OPERATIONAL}
    missing = set(old) - set(new)
    changed = {n for n in set(old) & set(new) if old[n] != new[n]}
    added = set(new) - set(old)
    unexpected = {n for n in added if not h.derivative(n)}
    return {"passed": not missing and not changed and not unexpected,
            "missing_count": len(missing), "changed_count": len(changed), "unexpected_added_count": len(unexpected),
            "added_derivative_count": len(added - unexpected), "missing_path_sha256": sorted(map(h.path_digest, missing)),
            "changed_path_sha256": sorted(map(h.path_digest, changed)), "unexpected_added_path_sha256": sorted(map(h.path_digest, unexpected))}


def validate_phase(h, report, tool, binding):
    require(report.get("schema") == SCHEMA + ":tool" and report.get("tool") == tool and tool in TOOLS,
            "Unexpected readiness phase or unsupported tool")
    require(report.get("binding") == binding, "Tool phase belongs to different source/controller/native/baseline identities")
    checks = report.get("checks")
    require(report.get("passed") is True and "error" not in report and isinstance(checks, dict)
            and set(checks) == TOOL_CHECKS and all(v is True for v in checks.values()),
            "A selected tool phase did not pass every required actual observation")
    require(report.get("force_termination_used") is False and report.get("permissions_requested") is False and report.get("production_code_injected") is False,
            "Tool phase crossed the no-force/no-permission/no-injection boundary")
    quit_result = report.get("ordinary_quit", {})
    require(quit_result.get("owned_app_terminated") is True and quit_result.get("passed") is True
            and quit_result.get("controller_exit_code") == 0 and quit_result.get("operation") == "terminate"
            and quit_result.get("termination_mechanism") == "NSRunningApplication.terminate"
            and quit_result.get("force_termination_used") is False
            and report.get("canonical_quit_receipt", {}).get("durable_jobs_at_shutdown_count") == 0,
            "Tool phase lacks actual ordinary termination and no-active-jobs evidence")
    require(report.get("installed_tool_readiness", {}).get("available") is True, "Tool phase lacks actual runtime readiness")
    if tool == "retime":
        validate_retime_readiness(report.get("installed_tool_readiness", {}).get("retime_probe"))
    require(report.get("preservation_status") == "pending_separate_verify_phase", "Unexpected tool preservation scope")


def verify(h, args):
    state = load_state(h, args); started = time.monotonic()
    output = args.output / "verify"; output.mkdir(mode=0o700, exist_ok=False)
    report = {"schema": SCHEMA + ":verify", "passed": False, "checks": {}, "tools": list(TOOLS),
              "binding": phase_binding(h, state, args.baseline_sha256), "force_termination_used": False,
              "project_content_recorded": False, "scope": "Eight source-bound installed default-runtime readiness phases plus one complete preservation comparison; canonical launch is a separate gate."}
    try:
        phases = {}; binaries = Path(state["paths"]["binary"])
        for tool in TOOLS:
            directory = args.output / tool
            record, phase = h.read_json(directory / "tool-report.json")
            validate_phase(h, phase, tool, report["binding"])
            for name, expected in phase.get("event_records", {}).items():
                require(Path(name).name == name and name not in {".", ".."} and name.endswith(".json"), "Unsafe phase event path")
                require(h.file_record(directory / name)[0] == expected, "Native phase event or ownership receipt changed")
            require({"native-launch.json", "owned-launch.json", "native-ordinary-quit.json", "phase-started.json"}.issubset(phase.get("event_records", {})), "Required native/ownership events are missing")
            _, ownership = h.read_json(directory / "owned-launch.json")
            _, began = h.read_json(directory / "phase-started.json")
            require(began.get("tool") == tool and began.get("binding") == report["binding"]
                    and began.get("started_unix", 0) >= state["created_unix"], "Tool execution predates or differs from its baseline")
            require(phase.get("launch", {}).get("owned") == ownership and ownership.get("native_sha256") == NATIVE_SHA
                    and ownership.get("launch_unix", 0) >= began["started_unix"] - 2,
                    "Tool ownership receipt differs from its actual launch")
            server = phase.get("owned_server", {})
            require(server.get("parent_pid") == ownership.get("pid")
                    and server.get("arguments_match_bundled_server_and_default_workspace") is True,
                    "Server ownership does not belong to this native launch")
            if server.get("pid") in h.process_table():
                current_command = h.process_field(server["pid"], "command")
                current_started = h.process_field(server["pid"], "lstart")
                require(current_command is None or h.digest(current_command.encode()) != server.get("command_sha256")
                        or current_started != server.get("started"), "An owned bundled server still runs")
            observed = h.native_control(binaries, directory / "owned-launch.json", "observe", output, "ownership-" + tool)
            require(observed.get("owned_pid_absent") is True, "A phase-owned native instance remains or has ambiguous ownership")
            phases[tool] = {"report_sha256": record["sha256"], "checks": len(phase["checks"]), "elapsed_seconds": phase["elapsed_seconds"],
                            "readiness_response_sha256": phase["installed_tool_readiness"]["response_sha256"]}
        report["phases"] = phases
        report["checks"]["all_eight_actual_tool_receipts_and_ownership_events_bound"] = True
        preflight = h.native_control(binaries, None, "preflight", output, "native-preflight")
        require(preflight.get("existing_production_app_count") == 0, "A current canonical app prevents final preservation acceptance")
        h.workspace_unlocked(); report["jobs_after"] = h.no_active_jobs()
        report["checks"]["no_current_app_active_jobs_or_workspace_owner"] = True
        after_app = h.tree(h.APP)
        require(after_app == state["bundle_before"], "Whole installed bundle changed across readiness phases")
        report["bundle_after"] = {"file_count": after_app["file_count"], "inventory_sha256": after_app["inventory_sha256"]}
        report["checks"]["whole_installed_bundle_preserved"] = True
        after_workspace = h.tree(h.WORKSPACE)
        comparison = compare_workspace(h, state["workspace_before"], after_workspace)
        report["workspace_comparison"] = comparison
        report["workspace_before"] = h.private_inventory(state["workspace_before"], h.OPERATIONAL)
        report["workspace_after"] = h.private_inventory(after_workspace, h.OPERATIONAL)
        require(comparison["passed"], "Protected workspace bytes changed or unexpected files appeared")
        report["checks"]["all_preexisting_project_and_cache_files_preserved"] = True
        report["checks"]["only_permitted_new_cache_derivatives"] = True
        runtime_pins(h, state)
        report["checks"]["accepted_source_controller_and_installed_native_still_bound"] = True
        h.workspace_unlocked(); h.no_active_jobs()
        report["passed"] = True
    except Exception as error:
        report["error"] = h.safe_error(error)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    h.write_new(output / "readiness-verification-report.json", report)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("prepare", "run-tool", "verify"))
    for name in ("runner", "private-baseline", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--expected-helper-sha256", required=True)
    p.add_argument("--expected-core-commit", required=True, help="Exact accepted 0.12 commit; its Git tree and source manifest are independently pinned")
    p.add_argument("--baseline-sha256")
    p.add_argument("--binary", type=Path)
    p.add_argument("--installation-evidence", type=Path)
    p.add_argument("--expected-controller-sha256")
    p.add_argument("--expected-installation-sha256")
    p.add_argument("--tool", choices=TOOLS)
    args = p.parse_args(argv)
    try:
        require(sys.platform == "darwin", "Actual macOS is required; no native readiness result is simulated")
        for name in ("runner", "private_baseline", "output", "binary", "installation_evidence"):
            value = getattr(args, name)
            if value is not None:
                require(value.is_absolute() and ".." not in value.parts, "Use explicit absolute paths")
        h = load_helper(args)
        outside_protected(h, args.output); outside_protected(h, args.private_baseline)
        if args.phase == "prepare":
            require(args.binary is not None and args.installation_evidence is not None and args.tool is None, "Prepare needs explicit controller/installation evidence and no tool")
            result = prepare(h, args)
        else:
            require((args.phase == "run-tool") == (args.tool is not None), "Select exactly one tool only for run-tool")
            result = tool_phase(h, args) if args.phase == "run-tool" else verify(h, args)
        print(json.dumps({"phase": args.phase, "tool": args.tool, "passed": result["passed"], "checks": result.get("checks"),
                          "private_baseline_sha256": result.get("private_baseline_sha256"), "elapsed_seconds": result.get("elapsed_seconds"),
                          "error": result.get("error")}, sort_keys=True, indent=2))
        return 0 if result["passed"] else 1
    except Exception as error:
        message = "Filesystem/process operation failed" if isinstance(error, OSError) else str(error)
        print(json.dumps({"phase": args.phase, "passed": False, "error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only observation of the canonical installed app's real launcher and engine.

Launch is exclusively NSWorkspace/LaunchServices. Termination is exclusively
NSRunningApplication.terminate after no active durable media jobs are observed.
No product code is injected, no HTTP mutation is sent, and no permission or
force-quit mechanism is used. Existing project bytes are hashed before/after.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import time

APP = Path("/Users/midiakiasat/Applications/CINEMATICUM Studio.app")
WORKSPACE = Path("/Users/midiakiasat/Movies/CINEMATICUM")
NATIVE_SHA = None  # Required explicitly from the independent installation receipt.
BUNDLE_ID, VERSION, BUILD = "com.cinematicum.studio", "0.13.0", "14"
MAX_BYTES, MAX_FILES, MAX_METADATA = 4 * 1024**3, 10_000, 16 * 1024**2
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
OPERATIONAL = {".cinematicum-workspace.lock", "last-session-exit.json"}
EPHEMERAL = {"frame-preview", "tracking-frame", "audio-source"}
TOOL_NAMES = ("deep", "ray-optics", "physical-rendering", "learned", "reconstruction", "scene-processing", "multicam-sync")
JOB_STATES = {"queued", "running", "completed", "cancelled", "failed", "interrupted"}
ID = re.compile(r"^[a-f0-9]{32}$")


def require(value, message):
    if not value:
        raise ValueError(message)


def safe_error(error):
    if isinstance(error, OSError):
        return type(error).__name__ + ": filesystem/network operation failed; errno=" + str(error.errno) + "; private path details omitted"
    return str(error)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def path_digest(value):
    return digest(str(value).encode())


def open_directory(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "An explicit absolute path without parent traversal is required")
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def file_at(parent, name, *, collect=False, limit=MAX_BYTES):
    require(name not in {"", ".", ".."} and "/" not in name and "\x00" not in name, "Invalid file component")
    require(name != ".env" and not name.startswith(".env."), "Credential-like environment files are outside this read-only gate")
    fd = os.open(name, FILE_FLAGS, dir_fd=parent)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, "Expected a bounded regular file")
        h, content, size = hashlib.sha256(), bytearray() if collect else None, 0
        while True:
            block = os.read(fd, min(1024 * 1024, limit - size + 1))
            if not block: break
            size += len(block)
            require(size <= limit, "A file grew beyond the evidence size bound")
            h.update(block)
            if collect: content.extend(block)
        after, current = os.fstat(fd), os.stat(name, dir_fd=parent, follow_symlinks=False)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        require(identity(before) == identity(after) == identity(current) and size == before.st_size,
                "A file changed during its independent hash inspection")
        return {"sha256": h.hexdigest(), "size": size, "mode": stat.S_IMODE(before.st_mode)}, bytes(content) if collect else None
    finally:
        os.close(fd)


def file_record(path, *, collect=False, limit=MAX_BYTES):
    path = Path(path)
    fd = open_directory(path.parent)
    try: return file_at(fd, path.name, collect=collect, limit=limit)
    finally: os.close(fd)


def read_json(path):
    record, content = file_record(path, collect=True, limit=MAX_METADATA)
    return record, json.loads(content)


def tree(path):
    files, size, entries = {}, 0, 0
    def visit(fd, prefix="", depth=0):
        nonlocal size, entries
        require(depth <= 64, "Evidence tree nesting exceeds its bound")
        with os.scandir(fd) as scan: names = sorted(item.name for item in scan)
        entries += len(names)
        require(entries <= 20_000, "Evidence tree entry count exceeds its bound")
        for name in names:
            relative = prefix + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode), "Symlink traversal is outside the launch gate; path SHA-256 " + path_digest(relative))
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
                try: visit(child, relative + "/", depth + 1)
                finally: os.close(child)
            else:
                require(stat.S_ISREG(info.st_mode) and len(files) < MAX_FILES, "Nonregular file or excessive file count")
                record, _ = file_at(fd, name, limit=MAX_BYTES - size)
                size += record["size"]; files[relative] = record
    fd = open_directory(path)
    try: visit(fd)
    finally: os.close(fd)
    return {"files": files, "file_count": len(files), "total_bytes": size, "inventory_sha256": digest(canonical(files))}


def private_inventory(inventory, excluded=()):
    files = {path_digest(name): record for name, record in inventory["files"].items() if name not in excluded}
    return {"file_count": len(files), "total_bytes": sum(item["size"] for item in files.values()),
            "inventory_sha256": digest(canonical(files)), "path_sha256_to_identity": files,
            "privacy": "Project paths and contents are not recorded; keys hash relative paths, values contain only byte hashes, lengths and modes"}


def workspace_unlocked():
    root = open_directory(WORKSPACE)
    try:
        try: fd = os.open(".cinematicum-workspace.lock", FILE_FLAGS, dir_fd=root)
        except FileNotFoundError: return
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), "Workspace ownership lock is not regular")
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError("Another real process owns the canonical workspace; launch is refused") from None
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally: os.close(fd)
    finally: os.close(root)


def durable_jobs():
    try: root = open_directory(WORKSPACE / "jobs")
    except FileNotFoundError: return []
    try:
        # Store startup considers every immediate *.json, irrespective of the
        # filename or job kind. Refuse ambiguous names before the app can rewrite
        # a stale queued/running receipt, including a persisted ephemeral job.
        with os.scandir(root) as scan: names = sorted(item.name for item in scan if item.name.endswith(".json"))
        require(len(names) <= MAX_FILES, "Durable job record count exceeds its bound")
        require(all(re.fullmatch(r"[a-f0-9]{32}\.json", name) for name in names),
                "Noncanonical startup job metadata is present; read-only launch is refused")
        records = []
        for name in names:
            _, data = file_at(root, name, collect=True, limit=MAX_METADATA)
            value = json.loads(data)
            require(isinstance(value, dict) and value.get("id") == name[:-5]
                    and isinstance(value.get("state"), str) and value["state"] in JOB_STATES,
                    "A startup job identity or state is unreadable or ambiguous")
            records.append({"state": value["state"]})
        return records
    finally: os.close(root)


def no_active_jobs():
    jobs = durable_jobs()
    require(not any(job["state"] in {"queued", "running"} for job in jobs), "Active or stale durable work is present; launch/quit is refused")
    return {"record_count": len(jobs), "active_count": 0, "terminal_state_counts": dict(Counter(job["state"] for job in jobs))}


def no_preview_eviction(projects):
    counts = []
    for project_file in projects:
        try: root = open_directory(WORKSPACE / Path(project_file).parent / "previews")
        except FileNotFoundError:
            counts.append(0)
            continue
        try:
            # Production sorts every immediate *.png before deciding whether
            # an older canonical filename may be removed. Noncanonical names
            # and directories therefore also consume that 64-entry budget.
            with os.scandir(root) as scan: count = sum(item.name.endswith(".png") for item in scan)
            require(count < 64, "Opening a project might evict a pre-existing preview cache; launch is refused")
            counts.append(count)
        finally: os.close(root)
    return {"projects_inspected": len(counts), "maximum_immediate_png_entries": max(counts, default=0),
            "all_immediate_png_names_and_entry_types_counted": True}


def native_control(binary, ownership, operation, output, label):
    command = [str(binary), "--operation", operation, "--expected-native-sha256", NATIVE_SHA]
    if ownership is not None: command += ["--ownership", str(ownership)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=25)
    try: report = json.loads(process.stdout)
    except ValueError: raise RuntimeError("Independent native controller returned no metadata JSON") from None
    report["controller_exit_code"] = process.returncode
    report["controller_stderr_bytes"] = len(process.stderr.encode())
    report["controller_stderr_sha256"] = digest(process.stderr.encode())
    write_new(output / (label + ".json"), report)
    require(process.returncode == 0 and report.get("passed") is True, "Native controller failed during " + operation + ": " + str(report.get("error", "gate not satisfied")))
    return report


def process_table():
    process = subprocess.run(["/bin/ps", "-axo", "pid=,ppid="], capture_output=True, text=True, check=True, timeout=5)
    require(len(process.stdout) < 1024 * 1024, "Process parent inventory exceeds its bound")
    result = {}
    for row in process.stdout.splitlines():
        columns = row.split()
        if len(columns) == 2 and all(part.isdigit() for part in columns): result[int(columns[0])] = int(columns[1])
    return result


def process_field(pid, field):
    process = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", field + "="], capture_output=True, text=True, timeout=5)
    require(len(process.stdout) < 65536, "Owned-process metadata exceeds its bound")
    return process.stdout.strip() if process.returncode == 0 else None


def find_bundled_child(parent, timeout=25):
    suffix = " -B -u " + str(APP / "Contents/Resources/studio/server.py") + " --workspace " + str(WORKSPACE) + " --port 0"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = []
        table = process_table()
        require(parent in table, "Owned canonical application exited before its bundled server was identified")
        for pid, ppid in table.items():
            if ppid != parent: continue
            command = process_field(pid, "command")
            if command and command.endswith(suffix):
                started = process_field(pid, "lstart")
                require(started, "Bundled server has no observable process start identity")
                matches.append({"pid": pid, "parent_pid": parent, "started": started,
                                "command_sha256": digest(command.encode()), "arguments_match_bundled_server_and_default_workspace": True})
        require(len(matches) <= 1, "More than one matching bundled server child exists")
        if matches: return matches[0]
        time.sleep(.1)
    raise RuntimeError("Owned canonical app did not launch its actual bundled server within 25 seconds")


def assert_child(child):
    require(process_table().get(child["pid"]) == child["parent_pid"], "Owned bundled server changed parent or exited")
    command, started = process_field(child["pid"], "command"), process_field(child["pid"], "lstart")
    require(command is not None and digest(command.encode()) == child["command_sha256"] and started == child["started"],
            "Owned bundled server process identity changed")


def child_port(child, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert_child(child)
        result = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(child["pid"]), "-iTCP", "-sTCP:LISTEN", "-Fpn"],
                                capture_output=True, text=True, timeout=5)
        require(len(result.stdout) < 65536, "Owned listener metadata exceeds its bound")
        if result.returncode not in {0, 1}: raise RuntimeError("Cannot inspect the owned server's listener")
        pids = {int(row[1:]) for row in result.stdout.splitlines() if re.fullmatch(r"p[0-9]+", row)}
        names = [row[1:] for row in result.stdout.splitlines() if row.startswith("n")]
        if names:
            require(pids == {child["pid"]}, "Listener data belongs to another process")
            require(len(names) == 1 and re.fullmatch(r"127\.0\.0\.1:[0-9]+", names[0]), "Bundled server is not listening exclusively on one IPv4 loopback port")
            port = int(names[0].rsplit(":", 1)[1])
            require(1 <= port <= 65535, "Invalid owned loopback port")
            return port
        time.sleep(.1)
    raise RuntimeError("Actual bundled child did not expose its own loopback listener")


def get(port, path, *, as_json=True):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=25)
    try:
        connection.request("GET", path, headers={"Host": "127.0.0.1:" + str(port)})
        response = connection.getresponse()
        body = response.read(MAX_METADATA + 1)
        require(response.status == 200 and len(body) <= MAX_METADATA, "Owned server GET failed or exceeded the bounded response size")
        headers = {"server": response.getheader("Server"), "content_type": response.getheader("Content-Type")}
        return json.loads(body) if as_json else body, headers
    finally: connection.close()


def sanitize_bootstrap(value, workspace_count):
    require(isinstance(value, dict) and isinstance(value.get("capabilities"), dict), "Actual bootstrap has no runtime capability state")
    caps = value["capabilities"]
    require(caps.get("version") == VERSION and caps.get("workspace") == str(WORKSPACE), "Actual engine version/default workspace differs")
    require(isinstance(value.get("project"), dict) and isinstance(value.get("projects"), list)
            and len(value["projects"]) == workspace_count, "Actual bootstrap does not expose the existing project count")
    jobs = value.get("jobs")
    require(isinstance(jobs, list) and not any(job.get("state") in {"queued", "running"} for job in jobs), "Actual bootstrap reports active durable work")
    flags = {key: caps.get(key) is True for key in ("ffmpeg", "h264", "prores", "high_depth_movie", "master16", "blender", "node_compositor", "color_pipeline")}
    require(all(flags[key] for key in ("ffmpeg", "h264", "high_depth_movie", "master16")), "Installed engine does not expose required actual FFmpeg/high16 readiness")
    for key in ("comfyui", "planar_tracking", "imaging"):
        flags[key + "_available"] = isinstance(caps.get(key), dict) and caps[key].get("available") is True
    return {"engine_version": caps["version"], "default_workspace_matches": True,
            "existing_project_count": len(value["projects"]), "listed_durable_job_count": len(jobs),
            "active_durable_job_count": 0, "runtime_availability_flags": flags,
            "token_project_names_prompts_assets_and_job_payloads_discarded": True}


def derivative(relative):
    return bool(re.fullmatch(r"projects/[a-f0-9]{32}/(?:thumbnails/[a-f0-9]{32}\.jpg|previews/[a-f0-9]{64}\.png|waveforms/[a-f0-9]{64}\.json|audio-sources/[a-f0-9]{64}\.(?:wav|json))", relative))


def installation_identity(value):
    require(value.get("passed") is True and {item.get("name") for item in value.get("gates", []) if item.get("passed") is True}
            == {"source", "installed", "receipt_and_backup", "projects", "original_checkout"}, "Installation evidence did not pass all independent gates")
    installed = value["installed"]
    if value.get("schema") == "cinematicum-installation-after-v1":
        bundle = installed["bundle"]
        result = {"bundle_id": bundle["bundle_id"], "version": bundle["version"], "build": bundle["build"],
                  "bundle_file_count": bundle["file_count"], "bundle_inventory_sha256": bundle["inventory_sha256"],
                  "executable": installed["executable"], "embedded_source_manifest": installed["embedded_source_manifest"]}
        require(value.get("paths", {}).get("app") == str(APP), "Installation evidence identifies another app")
    else:
        require(value.get("schema") == "cinematicum-installation-public-summary-v1" and value.get("installer", {}).get("app") == str(APP), "Unsupported installation evidence or different app")
        result = {key: installed[key] for key in ("bundle_id", "version", "build", "bundle_file_count", "bundle_inventory_sha256", "executable", "embedded_source_manifest")}
    require(result["bundle_id"] == BUNDLE_ID and result["version"] == VERSION and result["build"] == BUILD
            and result["executable"]["sha256"] == NATIVE_SHA, "Installation evidence differs from the exact accepted native build")
    return result


def write_new(path, value):
    data = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as target:
        target.write(data); target.flush(); os.fsync(target.fileno())


def run(binary, installation, output, selected_tools=()):
    require(all(name in TOOL_NAMES for name in selected_tools) and len(set(selected_tools)) == len(selected_tools),
            "Choose each supported installed tool at most once")
    require(sys.platform == "darwin", "Canonical LaunchServices acceptance requires macOS; no result is simulated")
    binary, installation, output = (path.absolute() for path in (binary, installation, output))
    require(not output.is_relative_to(APP) and not output.is_relative_to(WORKSPACE), "Evidence must stay outside the installed app and protected workspace")
    fd = open_directory(output.parent); os.close(fd)
    output.mkdir(mode=0o700, exist_ok=False)
    report = {"schema": "cinematicum-canonical-installed-launch-v1", "passed": False, "checks": {},
              "scope": "Exact canonical installed app through real LaunchServices; production launcher, bundled engine and explicitly selected tool readiness; no UI editing/playback/export or production-quality acceptance",
              "selected_tools": list(selected_tools), "all_tools_requested": set(selected_tools) == set(TOOL_NAMES),
              "app": str(APP), "workspace_path_sha256": path_digest(WORKSPACE),
              "force_termination_used": False, "permissions_requested": False,
              "project_content_recorded": False, "signing_or_notarization_certified": False,
              "comparison_exclusions": {"workspace_operational_metadata": sorted(OPERATIONAL),
                                        "new_files": "Only app-named thumbnail, preview, waveform and source-audio cache derivatives; all pre-existing cache files remain protected"}}
    checks = report["checks"]
    owned_path, owned, child, before_app, before_workspace = None, None, None, None, None
    started = time.monotonic()
    try:
        report["acceptance_runner_sha256"] = file_record(Path(__file__).absolute())[0]["sha256"]
        build_record, build = read_json(binary.parent / "build.json")
        require(build.get("schema") == "cinematicum-installed-app-controller-build-v1" and build.get("compiled") is True
                and file_record(binary)[0]["sha256"] == build.get("binary_sha256"), "Native controller differs from its independent build receipt")
        report["controller_build_sha256"] = build_record["sha256"]
        report["controller_binary_sha256"] = build["binary_sha256"]
        install_record, installation_value = read_json(installation)
        expected = installation_identity(installation_value)
        report["installation_evidence_sha256"] = install_record["sha256"]
        report["expected_installed_identity"] = expected
        preflight = native_control(binary, None, "preflight", output, "native-preflight")
        checks["existing_production_app_not_adopted"] = preflight.get("existing_production_app_count") == 0
        workspace_unlocked()
        report["jobs_before_launch"] = no_active_jobs()
        before_workspace = tree(WORKSPACE)
        projects = [name for name in before_workspace["files"] if re.fullmatch(r"projects/[a-f0-9]{32}/project\.json", name)]
        require(projects, "Canonical bootstrap would create a project in an empty workspace; read-only gate refuses launch")
        for name in projects:
            _, project = read_json(WORKSPACE / name)
            require(isinstance(project, dict) and project.get("id") == name.split("/")[1],
                    "Existing project identity is unreadable; read-only bootstrap cannot be guaranteed")
        del project
        cleanup_names = [name for name in before_workspace["files"] if re.fullmatch(r"projects/[a-f0-9]{32}/(?:archive-upload-[a-f0-9]{32}\.zip|relink-upload-[a-f0-9]{32}\.[a-zA-Z0-9]+)", name)]
        require(not cleanup_names, "Startup-owned temporary inputs are present; their removal is outside this read-only gate")
        report["preview_cache_before_launch"] = no_preview_eviction(projects)
        report["workspace_before"] = private_inventory(before_workspace, OPERATIONAL)
        report["existing_project_count"] = len(projects)
        write_new(output / "workspace-before-hashes.json", report["workspace_before"])
        before_app = tree(APP)
        require(before_app["inventory_sha256"] == expected["bundle_inventory_sha256"] and before_app["file_count"] == expected["bundle_file_count"], "Current whole installed bundle differs from independent installation evidence")
        manifest = file_record(APP / "Contents/Resources/source-manifest.json")[0]
        require(manifest == expected["embedded_source_manifest"], "Installed source manifest changed")
        _, raw_plist = file_record(APP / "Contents/Info.plist", collect=True, limit=MAX_METADATA)
        plist = plistlib.loads(raw_plist)
        require((plist.get("CFBundleIdentifier"), plist.get("CFBundleShortVersionString"), plist.get("CFBundleVersion"), plist.get("CFBundleExecutable"))
                == (BUNDLE_ID, VERSION, BUILD, "CINEMATICUMStudio"), "Canonical bundle metadata differs")
        report["bundle_before"] = before_app
        checks["whole_installed_bundle_matches_verified_installation"] = True
        launch = native_control(binary, None, "launch", output, "native-launch")
        owned = launch["owned"]
        owned_path = output / "owned-launch.json"
        write_new(owned_path, owned)
        report["launch"] = launch
        checks["exact_canonical_bundle_launched_by_launchservices"] = launch.get("creates_new_instance") is True and owned.get("native_sha256") == NATIVE_SHA
        child = find_bundled_child(owned["pid"])
        port = child_port(child)
        report["owned_server"] = {**child, "loopback_port": port,
                                  "bundled_script_sha256": file_record(APP / "Contents/Resources/studio/server.py")[0]["sha256"],
                                  "port_discovery": "lsof restricted to the exact owned bundled-server PID; no port scanning"}
        checks["real_owned_child_uses_exact_bundled_server_and_default_workspace"] = True
        checks["only_owned_server_loopback_listener_used"] = True
        bootstrap, headers = get(port, "/api/bootstrap")
        report["bootstrap_runtime"] = sanitize_bootstrap(bootstrap, len(projects))
        del bootstrap
        require(str(headers["server"]).startswith("CINEMATICUM/" + VERSION), "HTTP server header differs from the actual expected engine")
        checks["actual_bootstrap_version_workspace_and_runtime_ready"] = True
        for route, filename in (("/", "index.html"), ("/app.js", "app.js")):
            body, _ = get(port, route, as_json=False)
            require(digest(body) == file_record(APP / "Contents/Resources/studio/web" / filename)[0]["sha256"], "Live HTTP editor bytes differ from the bundled runtime")
        checks["live_editor_files_match_installed_bytes"] = True
        report["installed_tool_readiness"] = {}
        for name in selected_tools:
            readiness, _ = get(port, "/api/" + name + "-capabilities")
            require(isinstance(readiness, dict) and readiness.get("available") is True,
                    "Installed tool runtime is unavailable: " + name)
            if name == "physical-rendering":
                require(readiness.get("pbrt_available") is True, "Installed physical renderer cannot find the accepted PBRT runtime")
            if name == "learned":
                require(set(readiness.get("models", {})) == {"sam2", "tapir"}, "Installed learned runtime must expose both actual checkpoints")
            report["installed_tool_readiness"][name] = {"available": True,
                "response_sha256": digest(canonical(readiness)),
                "pbrt_available": readiness.get("pbrt_available") if name == "physical-rendering" else None}
        if selected_tools:
            checks["selected_installed_tools_resolve_their_actual_default_runtimes"] = True
        observe_deadline, observed = time.monotonic() + 8, None
        attempts = 0
        while time.monotonic() < observe_deadline:
            attempts += 1
            observation = native_control(binary, owned_path, "observe", output, "native-observe-" + str(attempts))
            observed = observation.get("owned", {})
            require(observed.get("running") is True, "Owned installed app exited during readiness observation")
            if observed.get("finished_launching") is True and (observed.get("window_metadata_available") is False or observed.get("normal_window_count", 0) > 0): break
            time.sleep(.2)
        require(observed and observed.get("finished_launching") is True, "Installed app did not remain launched")
        checks["canonical_app_remains_alive_after_real_engine_bootstrap"] = observed.get("running") is True
        report["window_observation"] = {key: observed[key] for key in ("window_metadata_available", "normal_window_count", "onscreen_window_count", "window_observation_limit") if key in observed}
        checks["native_window_present_when_metadata_is_observable"] = observed.get("window_metadata_available") is False or observed.get("normal_window_count", 0) > 0
        assert_child(child)
        require(child_port(child, timeout=1) == port, "Owned listener changed before ordinary quit")
        report["jobs_before_quit"] = no_active_jobs()
        # Re-read the actual engine state immediately before native termination.
        last_bootstrap, _ = get(port, "/api/bootstrap")
        report["bootstrap_before_quit"] = sanitize_bootstrap(last_bootstrap, len(projects)); del last_bootstrap
        report["ordinary_quit"] = native_control(binary, owned_path, "terminate", output, "native-ordinary-quit")
        checks["canonical_app_accepted_ordinary_native_termination"] = report["ordinary_quit"].get("owned_app_terminated") is True
        after_table = process_table()
        checks["actual_owned_server_exited_with_canonical_app"] = child["pid"] not in after_table
        require(checks["actual_owned_server_exited_with_canonical_app"], "Owned bundled server remains alive after its canonical app quit")
        workspace_unlocked()
        checks["canonical_workspace_ownership_released"] = True
        _, exit_receipt = read_json(WORKSPACE / "last-session-exit.json")
        require(exit_receipt.get("reason") == "native-quit-no-active-jobs" and exit_receipt.get("completed_at", 0) >= owned["launch_unix"], "No fresh job-free native quit receipt was persisted")
        active = exit_receipt.get("active_at_shutdown", [])
        require(all(job.get("kind") in EPHEMERAL for job in active), "Durable media work became active during ordinary quit")
        report["canonical_quit_receipt"] = {"reason": exit_receipt["reason"], "completed_at": exit_receipt["completed_at"],
                                             "ephemeral_jobs_at_shutdown_count": len(active),
                                             "durable_jobs_at_shutdown_count": 0,
                                             "terminal_state_counts": dict(Counter(job.get("state") for job in exit_receipt.get("terminal_jobs", [])))}
        checks["production_job_free_quit_path_persisted_its_real_receipt"] = True
    except Exception as error:
        report["error"] = safe_error(error)
        checks["completed_without_launch_or_observation_error"] = False
    finally:
        # No force kill or cancellation. A failed observation may still own an
        # app; request ordinary termination only if durable work is absent.
        if owned_path is not None and not report.get("ordinary_quit", {}).get("owned_app_terminated"):
            try:
                no_active_jobs()
                status = native_control(binary, owned_path, "observe", output, "native-cleanup-observe")
                if status.get("owned", {}).get("running"):
                    report["failure_cleanup"] = native_control(binary, owned_path, "terminate", output, "native-cleanup-ordinary-quit")
            except Exception as error:
                report["failure_cleanup_error"] = safe_error(error)
        try:
            if before_app is not None:
                after_app = tree(APP)
                report["bundle_after"] = after_app
                checks["whole_installed_bundle_unchanged_after_launch_and_quit"] = before_app == after_app
            if before_workspace is not None:
                after_workspace = tree(WORKSPACE)
                before_files = {name: value for name, value in before_workspace["files"].items() if name not in OPERATIONAL}
                after_files = {name: value for name, value in after_workspace["files"].items() if name not in OPERATIONAL}
                missing = set(before_files) - set(after_files)
                changed = {name for name in set(before_files) & set(after_files) if before_files[name] != after_files[name]}
                added = set(after_files) - set(before_files)
                unexpected = {name for name in added if not derivative(name)}
                report["workspace_after"] = private_inventory(after_workspace, OPERATIONAL)
                report["workspace_comparison"] = {"missing_count": len(missing), "changed_count": len(changed),
                    "added_derivative_count": len(added - unexpected), "unexpected_added_count": len(unexpected),
                    "missing_path_sha256": sorted(map(path_digest, missing)), "changed_path_sha256": sorted(map(path_digest, changed)),
                    "unexpected_added_path_sha256": sorted(map(path_digest, unexpected))}
                checks["all_existing_protected_project_and_runtime_cache_files_preserved"] = not missing and not changed
                checks["only_known_cache_derivatives_added"] = not unexpected
                write_new(output / "workspace-after-hashes.json", report["workspace_after"])
        except Exception as error:
            checks["final_preservation_hashes_completed"] = False
            report["preservation_error"] = safe_error(error)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["passed"] = bool(checks) and all(checks.values()) and "error" not in report
    write_new(output / "installed-launch-report.json", report)
    return report


def main():
    global NATIVE_SHA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--installation-evidence", required=True, type=Path,
                        help="Actual installation-after.json or its hash-bound installation-02-summary.json")
    parser.add_argument("--output", required=True, type=Path, help="New evidence directory outside the canonical app/workspace")
    parser.add_argument("--expected-native-sha256", required=True, help="Exact SHA-256 from the independently verified installation")
    parser.add_argument("--tool", action="append", default=[], choices=TOOL_NAMES,
                        help="Readiness phase for one named tool; repeat only when the foreground budget allows. Omit for canonical launch/quit alone.")
    args = parser.parse_args()
    try:
        require(re.fullmatch(r"[a-f0-9]{64}", args.expected_native_sha256), "An exact native executable SHA-256 is required")
        NATIVE_SHA = args.expected_native_sha256
        report = run(args.binary, args.installation_evidence, args.output, tuple(args.tool))
        print(json.dumps({"passed": report["passed"], "checks": report["checks"], "error": report.get("error"),
                          "elapsed_seconds": report["elapsed_seconds"],
                          "report": str(args.output.absolute() / "installed-launch-report.json")}, indent=2))
        return 0 if report["passed"] else 1
    except Exception as error:
        print(json.dumps({"passed": False, "error": safe_error(error)}), file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Container-local editor control. Invoked only by docker exec, never HTTP.

The command surface is deliberately finite: launch/focus, status, request-close,
and a graphics diagnostic. Native projects remain owned by the native editors.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

STATE = Path("/tmp/cinematicum-state")
PROJECTS = Path("/projects")
REGISTRY = Path("/opt/cinematicum/installed.json")
IDS = {"shotcut", "kdenlive", "cinelerra", "natron", "friction", "glaxnimate", "blender"}
DESKTOPS = {key: index for index, key in enumerate(
    ("kdenlive", "shotcut", "cinelerra", "natron", "friction", "glaxnimate", "blender"))}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    os.replace(str(temporary), str(path))


def registry():
    data = json.loads(REGISTRY.read_text())
    engines = {}
    for entry in data.get("engines", []):
        key = entry.get("id")
        if key not in IDS or key in engines:
            raise ValueError("Installed editor registry is invalid")
        path = Path(entry["executable"]).resolve()
        path.relative_to(Path("/opt/editors") / key)
        if not path.is_file():
            raise ValueError("Installed editor executable is absent: " + key)
        engines[key] = entry
    return data, engines


def project_path(value):
    relative = Path(value or ".")
    if relative.is_absolute() or ".." in relative.parts or "\x00" in str(relative):
        raise ValueError("Project path must be relative to /projects")
    path = (PROJECTS / relative).resolve(strict=True)
    path.relative_to(PROJECTS.resolve())
    if not path.is_file() and not path.is_dir():
        raise ValueError("Project must be a regular file or directory")
    return path


def run(argv, timeout=3):
    completed = subprocess.run(argv, capture_output=True, text=True,
                               errors="replace", timeout=timeout, check=False)
    return {"exit_code": completed.returncode,
            "stdout": completed.stdout[-16000:], "stderr": completed.stderr[-8000:]}


def proc_info(pid):
    try:
        root = Path("/proc") / str(int(pid))
        if root.stat().st_uid != os.getuid():
            return None
        text = (root / "stat").read_text()
        rest = text[text.rfind(")") + 2:].split()
        if rest[0] == "Z":
            return None
        cmdline = (root / "cmdline").read_bytes().split(b"\x00")
        return {"pid": int(pid), "ppid": int(rest[1]), "pgrp": int(rest[2]),
                "start_ticks": int(rest[19]),
                "argv": [x.decode("utf-8", errors="replace") for x in cmdline if x]}
    except (OSError, ValueError, IndexError):
        return None


def processes():
    result = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            info = proc_info(entry.name)
            if info:
                result.append(info)
    return result


def editor_processes(record, entry, table=None):
    if not record:
        return []
    table = processes() if table is None else table
    leader = next((x for x in table if x["pid"] == record["pid"]), None)
    if leader and leader["start_ticks"] != record.get("start_ticks"):
        return []
    group = [x for x in table if x["pgrp"] == record["pid"]
             and x["start_ticks"] >= record.get("start_ticks", 0)]
    prefix = "/opt/editors/" + entry["id"] + "/"
    if not any(any(arg.startswith(prefix) for arg in x["argv"]) for x in group):
        return []
    return group


def windows():
    response = run(["wmctrl", "-lp"])
    if response["exit_code"]:
        return []
    result = []
    for line in response["stdout"].splitlines():
        values = line.split(None, 4)
        if len(values) >= 4 and re.fullmatch(r"0x[0-9a-fA-F]+", values[0]):
            try:
                result.append({"id": values[0], "pid": int(values[2]), "desktop": int(values[1]),
                               "title": values[4][:500] if len(values) > 4 else ""})
            except ValueError:
                pass
    return result


def load_record(key):
    path = STATE / (key + ".json")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def editor_state(key, entry, table=None, visible=None):
    record = load_record(key)
    owned = editor_processes(record, entry, table)
    pids = {x["pid"] for x in owned}
    visible = windows() if visible is None else visible
    matched = [x for x in visible if x["pid"] in pids]
    return {"id": key, "label": entry["label"], "version": entry.get("version"),
            "installed": True, "running": bool(owned), "windows": matched,
            "window_ready": bool(matched),
            "project": record.get("project") if record else None,
            "pids": sorted(pids)}


def reconcile_windows():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / "windows.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _reconcile_windows()


def _reconcile_windows():
    """Keep each complete editor and its dialogs on its own persistent desktop."""
    _, entries = registry()
    table, visible = processes(), windows()
    seen_file = STATE / "mapped-windows.json"
    try:
        seen = json.loads(seen_file.read_text())
    except (OSError, ValueError):
        seen = {}
    active = set()
    for key, entry in entries.items():
        state = editor_state(key, entry, table, visible)
        for window in state["windows"]:
            identity = key + ":" + str(window["pid"]) + ":" + window["id"]
            active.add(identity)
            if window["desktop"] != DESKTOPS[key]:
                run(["wmctrl", "-ir", window["id"], "-t", str(DESKTOPS[key])])
            if identity not in seen:
                # Preserve Cinelerra's multi-window compositor layout and all
                # transient dialogs. Only new ordinary main windows maximize.
                if key != "cinelerra":
                    props = run(["xprop", "-id", window["id"],
                                 "_NET_WM_WINDOW_TYPE", "WM_TRANSIENT_FOR"])["stdout"]
                    is_dialog = "_NET_WM_WINDOW_TYPE_DIALOG" in props
                    is_transient = re.search(r"WM_TRANSIENT_FOR.*0x[1-9a-fA-F]", props)
                    if not is_dialog and not is_transient:
                        run(["wmctrl", "-ir", window["id"], "-b", "add,maximized_vert,maximized_horz"])
                seen[identity] = True
    write_json(seen_file, {key: True for key in seen if key in active})


def status():
    data, entries = registry()
    table, visible = processes(), windows()
    ready = (STATE / "ready.json").is_file()
    return {"ok": True, "ready": ready, "display": ":100",
            "mode": "native-editor-sessions", "graphics": "software-mesa",
            "complete_set": data.get("complete_set", False),
            "editors": [editor_state(key, entries[key], table, visible)
                        for key in sorted(entries)]}


def launch(key, relative_project):
    _, entries = registry()
    if key not in entries:
        raise ValueError("Editor is not installed: " + key)
    if not (STATE / "ready.json").exists():
        raise ValueError("Native display is not ready")
    project = project_path(relative_project)
    entry = entries[key]
    current = editor_state(key, entry)
    run(["wmctrl", "-s", str(DESKTOPS[key])])
    if current["running"]:
        # Never replace an editor's unsaved document when changing a selection.
        if current["project"] != str(project):
            raise ValueError("This editor already has another native document open; close it in the editor first")
        if current["windows"]:
            run(["wmctrl", "-ia", current["windows"][-1]["id"]])
        return dict(current, ok=True, action="focused")
    env = os.environ.copy()
    env.update({"DISPLAY": ":100", "APPDIR": entry["appdir"],
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/cinematicum-runtime/bus",
                "QT_X11_NO_MITSHM": "1", "LIBGL_ALWAYS_SOFTWARE": "1",
                "GALLIUM_DRIVER": "llvmpipe", "QT_XCB_GL_INTEGRATION": "xcb_glx"})
    # Each upstream bundle supplies its own Qt/plugin paths through AppRun.
    for name in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "LD_LIBRARY_PATH"):
        env.pop(name, None)
    argv = [entry["executable"]]
    if key == "blender":
        argv.extend(["--disable-autoexec", "--gpu-backend", "opengl"])
    if project.is_file():
        argv.append(str(project))
    cwd = project if project.is_dir() else project.parent
    log_path = STATE / (key + ".log")
    with log_path.open("ab", buffering=0) as log:
        child = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, start_new_session=True,
                                 close_fds=True)
    info = proc_info(child.pid)
    if info is None:
        raise ValueError("Editor exited before its process identity could be recorded")
    record = {"pid": child.pid, "start_ticks": info["start_ticks"],
              "project": str(project), "started": time.time()}
    write_json(STATE / (key + ".json"), record)
    # Startup is asynchronous; return an honest starting state when the window
    # has not mapped yet. The host polls status rather than inferring success.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = editor_state(key, entry)
        if current["windows"] or not current["running"]:
            break
        time.sleep(0.1)
    if not current["running"]:
        tail = log_path.read_bytes()[-4000:].decode("utf-8", errors="replace")
        raise ValueError("Editor process exited during startup: " + tail)
    if current["windows"]:
        reconcile_windows()
        run(["wmctrl", "-ia", current["windows"][-1]["id"]])
    return dict(current, ok=True, action="started")


def close_editor(key):
    _, entries = registry()
    if key not in entries:
        raise ValueError("Editor is not installed")
    current = editor_state(key, entries[key])
    # WM_DELETE_WINDOW lets each editor show its own unsaved-work dialog.
    # No signal is sent and no process is killed by this command.
    for window in current["windows"]:
        run(["wmctrl", "-ic", window["id"]])
    return {"ok": True, "action": "close_requested", "id": key,
            "windows": len(current["windows"]), "requires_editor_confirmation": current["running"]}


def probe(key):
    cpu = Path("/proc/cpuinfo").read_text(errors="replace")
    flags = next((line.split(":", 1)[1].split() for line in cpu.splitlines()
                  if line.startswith("flags") and ":" in line), [])
    gl = run(["glxinfo", "-B"], timeout=12)
    return {"ok": True, "avx": "avx" in flags, "avx2": "avx2" in flags,
            "graphics": gl, "editor": launch(key, "."),
            "warning": "Window readiness is not a feature-parity or rendering verification"}


def key_command(action):
    shortcuts = {"save": "ctrl+s", "undo": "ctrl+z", "redo": "ctrl+shift+z"}
    if action not in shortcuts:
        raise ValueError("Unsupported editor command")
    active = run(["xdotool", "getactivewindow"])
    if active["exit_code"] or not active["stdout"].strip().isdigit():
        raise ValueError("No active editor window")
    xid = int(active["stdout"].strip())
    _, entries = registry()
    table, visible = processes(), windows()
    match = None
    for key, entry in entries.items():
        state = editor_state(key, entry, table, visible)
        if any(int(window["id"], 16) == xid for window in state["windows"]):
            match = key
            break
    if match is None:
        raise ValueError("The active window does not belong to a CINEMATICUM editor")
    result = run(["xdotool", "key", "--clearmodifiers", shortcuts[action]])
    if result["exit_code"]:
        raise ValueError("Editor key command failed")
    return {"ok": True, "action": action, "editor": match,
            "delivered": True, "saved": False,
            "note": "Native editor handles the command and any confirmation dialog"}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    start = sub.add_parser("launch")
    start.add_argument("editor", choices=sorted(IDS))
    start.add_argument("project", nargs="?", default=".")
    close = sub.add_parser("request-close")
    close.add_argument("editor", choices=sorted(IDS))
    diagnostic = sub.add_parser("probe")
    diagnostic.add_argument("editor", choices=sorted(IDS))
    key = sub.add_parser("key")
    key.add_argument("command", choices=("save", "undo", "redo"))
    args = parser.parse_args()
    if os.getuid() == 0:
        raise ValueError("Native editors must run as the unprivileged application user")
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / "control.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if args.action == "status":
            result = status()
        elif args.action == "launch":
            result = launch(args.editor, args.project)
        elif args.action == "request-close":
            result = close_editor(args.editor)
        elif args.action == "probe":
            result = probe(args.editor)
        else:
            result = key_command(args.command)
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        raise SystemExit(1)

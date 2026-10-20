#!/usr/bin/env python3
"""Own one Xpra desktop, window manager, PulseAudio session and editor children."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from control import reconcile_windows

STATE = Path("/tmp/cinematicum-state")
RUNTIME = Path("/tmp/cinematicum-runtime")
SECRET = Path("/run/cinematicum/password")
stopping = False


def signal_stop(_signum, _frame):
    global stopping
    stopping = True


def emit(**data):
    print(json.dumps(data, sort_keys=True), flush=True)


def main():
    if os.getuid() == 0:
        raise RuntimeError("CINEMATICUM native runtime requires a non-root user")
    password = SECRET.read_bytes()
    if len(password) < 32 or b"\n" in password or b"\r" in password:
        raise RuntimeError("Xpra secret must contain at least 32 bytes with no newline")
    del password
    for path in (STATE, RUNTIME, Path.home() / ".config", Path.home() / ".cache"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUNTIME.chmod(0o700)
    ready = STATE / "ready.json"
    ready.unlink(missing_ok=True)
    os.environ.update({"DISPLAY": ":100", "XDG_RUNTIME_DIR": str(RUNTIME),
                       "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(RUNTIME / "bus")})
    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    bus = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--nopidfile",
                            "--address=unix:path=" + str(RUNTIME / "bus")],
                           start_new_session=True)
    argv = ["xpra", "start-desktop", ":100",
            "--daemon=no", "--bind-tcp=0.0.0.0:14500",
            "--tcp-auth=file:filename=" + str(SECRET),
            "--html=on", "--mdns=no", "--notifications=no", "--printing=no",
            "--file-transfer=no", "--open-files=no", "--open-url=no",
            "--start-new-commands=no", "--exit-with-client=no",
            "--pulseaudio=yes", "--speaker=on", "--microphone=disabled",
            "--webcam=no", "--clipboard=yes", "--opengl=no",
            "--resize-display=yes", "--desktop-scaling=1",
            "--socket-dir=" + str(RUNTIME), "--socket-permissions=600",
            "--xvfb=Xvfb +extension GLX +extension RANDR +extension RENDER -screen 0 1600x1000x24 -nolisten tcp -noreset",
            "--start-child=openbox --sm-disable"]
    # Remote command execution and file transfer are disabled; only the parent's
    # docker-exec allowlist can create editor processes. The public listener has
    # file authentication; the host maps it to a random loopback-only port.
    child = subprocess.Popen(argv, start_new_session=True)
    start = time.monotonic()
    display_ready = False
    while not stopping and child.poll() is None and bus.poll() is None:
        if not display_ready:
            check = subprocess.run(["wmctrl", "-m"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=3)
            if check.returncode == 0:
                subprocess.run(["wmctrl", "-n", "7"], check=True)
                ready.write_text(json.dumps({"pid": os.getpid(), "display": ":100",
                                             "ready_at": time.time()}) + "\n")
                display_ready = True
                emit(status="ready", display=":100", port=14500, graphics="software-mesa")
            elif time.monotonic() - start > 90:
                emit(status="error", error="Native desktop startup timed out")
                break
        else:
            try:
                reconcile_windows()
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                # A window can disappear between enumeration and activation.
                # A transient window-manager race must not close other editors.
                emit(status="window_update_deferred", error=str(exc))
        # The host starts the container with --init, which reaps editors that
        # outlive their short-lived docker-exec launch command.
        time.sleep(0.25)
    ready.unlink(missing_ok=True)
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
    if bus.poll() is None:
        bus.terminate()
        try:
            bus.wait(timeout=3)
        except subprocess.TimeoutExpired:
            bus.kill()
            bus.wait(timeout=3)
    return child.returncode or 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        emit(status="error", error=str(exc))
        raise SystemExit(1)

"""Owned, cancellable preparation of calibrated lens sampling maps.

Only the shipped numeric worker runs. Its six 16-bit PNGs are admitted after
checking the normalized request, fixed filenames, headers, sizes and hashes.
This module has no NumPy dependency; the isolated imaging runtime accelerates
the same algorithm when installed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time


def _stop(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def prepare_lens_maps(params, width, height, scratch, cancel_event=None, timeout=90):
    if __package__:
        from .compositor import LENS_MAP_NAMES, lens_map_request
        from .imaging import find_imaging_python
    else:
        from compositor import LENS_MAP_NAMES, lens_map_request
        from imaging import find_imaging_python
    request = lens_map_request(params, width, height)
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Lens preparation cancelled")
    directory = Path(tempfile.mkdtemp(prefix="lens-" + digest[:12] + "-", dir=str(scratch)))
    executable = find_imaging_python() or sys.executable
    command = [executable, "-I", str(Path(__file__).with_name("compositor.py")), "--lens-maps", str(directory)]
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith(("PYTHON", "OCIO")):
            environment.pop(key, None)
    environment.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    with tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as outgoing, tempfile.TemporaryFile() as errors:
        incoming.write(encoded); incoming.seek(0)
        process = subprocess.Popen(command, stdin=incoming, stdout=outgoing, stderr=errors,
                                   start_new_session=True, env=environment)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Lens preparation cancelled")
                if time.monotonic() - started > timeout:
                    raise RuntimeError("Calibrated lens preparation exceeded its time limit")
                if cancel_event is not None:
                    cancel_event.wait(.05)
                else:
                    time.sleep(.05)
            errors.seek(0); detail = errors.read(8000).decode("utf-8", errors="replace")
            if process.returncode:
                raise ValueError("Calibrated lens preparation failed: " + detail[-2000:])
            outgoing.seek(0); response = outgoing.read(65537)
            if len(response) > 65536:
                raise ValueError("Calibrated lens receipt exceeds its size limit")
        finally:
            _stop(process)
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Lens preparation cancelled")
    receipt = json.loads(response)
    if (not isinstance(receipt, dict) or receipt.get("version") != 1
            or receipt.get("request_sha256") != digest
            or receipt.get("width") != width or receipt.get("height") != height
            or receipt.get("backend") not in {"python", "numpy"}
            or not isinstance(receipt.get("maps"), dict) or set(receipt["maps"]) != set(LENS_MAP_NAMES)):
        raise ValueError("Calibrated lens receipt does not match the requested image and calibration")
    paths = {}
    if {p.name for p in directory.iterdir()} != {name + ".png" for name in LENS_MAP_NAMES}:
        raise ValueError("Calibrated lens worker produced unexpected files")
    for name in LENS_MAP_NAMES:
        item = receipt["maps"][name]
        channels = 4 if name in {"wx", "wy"} else 1
        path = directory / (name + ".png")
        limit = width * height * channels * 2 + height * 2 + 65536
        if (not isinstance(item, dict) or item.get("file") != path.name
                or item.get("channels") != channels or item.get("bit_depth") != 16
                or path.is_symlink() or not path.is_file() or not 33 <= path.stat().st_size <= limit):
            raise ValueError("Calibrated lens map metadata is invalid")
        data = path.read_bytes()
        if len(data) != item.get("bytes") or hashlib.sha256(data).hexdigest() != item.get("sha256"):
            raise ValueError("Calibrated lens map does not match its receipt")
        if (data[:8] != b"\x89PNG\r\n\x1a\n" or data[8:16] != b"\x00\x00\x00\rIHDR"
                or struct.unpack(">IIBBBBB", data[16:29]) != (width, height, 16, 6 if channels == 4 else 0, 0, 0, 0)):
            raise ValueError("Calibrated lens map header does not match its expected precision and dimensions")
        paths[name] = path
    return {"paths": paths, "receipt": receipt}

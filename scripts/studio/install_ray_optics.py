#!/usr/bin/env python3
"""Install/check the SHA-256-pinned isolated Optiland CPU runtime.

macOS arm64 uses CPython 3.13 (macOS 14+); Linux x86_64 verification uses
CPython 3.12. Every direct/transitive wheel has an exact URL and SHA-256.
No package resolution, source build, system install or existing-path replacement
is performed. --step performs one bounded, resumable foreground phase without
starting detached work; --info describes the pinned setup without modifying it.
A permanent venv is published through a stable relative link only after exact
wheel, isolation, full inventory, ray-tracing and diffraction verification.
The native CLI keeps its 14-second phase deadline. A foreground CI caller may
explicitly request a bounded larger phase budget through the Python API; this
does not remove cancellation, numerical probes, or either inventory check.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import urllib.request
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ray_optics

PINNED_PACKAGES = {
    "certifi": "2026.10.19", "charset-normalizer": "3.5.2", "contourpy": "1.4.0", "cycler": "0.12.1",
    "fonttools": "4.67.0", "idna": "3.20", "kiwisolver": "1.5.1", "llvmlite": "0.50.0",
    "matplotlib": "3.11.2", "numba": "0.68.0", "numpy": "2.3.5", "optiland": "0.6.3", "packaging": "26.3",
    "pandas": "3.0.6", "pillow": "13.0.0", "pyparsing": "3.3.3", "python-dateutil": "2.9.0.post0",
    "pyyaml": "6.0.3", "requests": "2.34.2", "scipy": "1.18.1", "seaborn": "0.13.2", "six": "1.17.0",
    "tabulate": "0.10.0", "typing-extensions": "4.16.0", "urllib3": "2.8.0", "vtk": "9.7.1"}
VERSIONS_DIRECTORY = ".cinematicum-optics-runtimes"
RECEIPT = "cinematicum-optics-install.json"
PENDING = ".cinematicum-optics-pending.json"
CHUNK_BYTES = 4 * 1024 * 1024
# Leave up to five seconds for termination of a currently owned child while
# keeping a foreground invocation below the native command's 20-second budget.
STEP_SECONDS = 14
PHASES = {"venv", "ensurepip", "download", "install", "dependencies", "verify", "inventory", "publish"}
BASE_PROBE = "import json,platform,sys;print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine()}))"


def _target():
    if sys.platform == "darwin" and platform.machine() == "arm64":
        if int(platform.mac_ver()[0].split(".")[0]) < 14:
            raise ValueError("The pinned Optiland wheels require macOS 14 or later.")
        return "macos-arm64", "3.13", "py313-v1", "macos-arm64-py313"
    if sys.platform == "linux" and platform.machine() == "x86_64":
        return "linux-x86_64", "3.12", "py312-v1", "linux-x86_64-py312"
    raise ValueError("Managed optics wheels are pinned for macOS arm64 Python 3.13 and Linux x86_64 Python 3.12.")


def default_destination():
    target, _, version, _ = _target()
    base = Path.home() / ("Library/Application Support" if target == "macos-arm64" else ".local/share")
    return base / "CINEMATICUM/Optics" / version


def _read(path, limit=2 * 1024 * 1024):
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise ValueError("Optics installer record must be a regular file.")
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Optics installer record exceeds its size limit.")
    return json.loads(data), data


def load_lock(target=None):
    if target is None:
        target = _target()[3]
    if target not in ("macos-arm64-py313", "linux-x86_64-py312"):
        raise ValueError("Unknown optics wheel platform.")
    lock, data = _read(Path(__file__).with_name(f"ray-optics-{target}.lock.json"))
    platform_name = "macos-arm64" if target.startswith("macos") else "linux-x86_64"
    python = "3.13" if target.startswith("macos") else "3.12"
    if lock.get("schema") != "cinematicum-ray-optics-wheel-lock" or lock.get("version") != 1 or lock.get("platform") != platform_name or lock.get("python") != python:
        raise ValueError("The optics wheel lock has an unsupported identity or platform.")
    packages = lock.get("packages", [])
    if len(packages) != len(PINNED_PACKAGES) or {p.get("name"): p.get("version") for p in packages} != PINNED_PACKAGES:
        raise ValueError("The optics wheel lock must contain every exact direct and transitive package.")
    for package in packages:
        url = urlsplit(package.get("url", "")); filename = package.get("filename", "")
        if (not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", filename) or url.scheme != "https" or url.netloc != "files.pythonhosted.org"
                or url.query or url.fragment or not re.fullmatch(r"/packages/[a-f0-9/]+/" + re.escape(filename), url.path)
                or not re.fullmatch(r"[a-f0-9]{64}", package.get("sha256", ""))
                or not isinstance(package.get("size"), int) or isinstance(package["size"], bool) or not 0 < package["size"] < 250 * 1024 * 1024):
            raise ValueError("An optics wheel has an invalid immutable identity, URL or size.")
    return lock, hashlib.sha256(data).hexdigest()


class _BudgetEvent:
    """Cancellation interface with a wall-clock deadline, without a helper thread."""
    def __init__(self, parent=None, seconds=STEP_SECONDS):
        self.parent = parent
        self.deadline = time.monotonic() + seconds

    def timed_out(self):
        return time.monotonic() >= self.deadline

    def is_set(self):
        return self.timed_out() or self.parent is not None and self.parent.is_set()

    def wait(self, seconds):
        remaining = min(seconds, max(0, self.deadline - time.monotonic()))
        if self.parent is not None:
            self.parent.wait(remaining)
        elif remaining:
            time.sleep(remaining)
        return self.is_set()


def _cancel(event):
    if event is not None and event.is_set():
        if isinstance(event, _BudgetEvent) and event.timed_out():
            raise TimeoutError("The bounded optics phase timed out; owned verified progress remains resumable.")
        raise InterruptedError("Optics runtime installation cancelled; owned progress remains resumable.")


def _run(command, timeout=STEP_SECONDS, cancel_event=None):
    event = cancel_event or threading.Event()
    _cancel(event)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PIP_", "MPL", "NUMBA"))}
    env.update(PIP_CONFIG_FILE=os.devnull, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MPLBACKEND="Agg",
               PYTHONDONTWRITEBYTECODE="1")
    process = None
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen([str(x) for x in command], stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.STDOUT, env=env, start_new_session=True)
            started = time.monotonic()
            while process.poll() is None:
                event.wait(.04)
                _cancel(event)
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Optics installation command exceeded {timeout} seconds.")
            size = output.seek(0, os.SEEK_END); output.seek(max(0, size - 2 * 1024 * 1024))
            text = output.read().decode("utf-8", errors="replace")
            if process.returncode:
                raise RuntimeError("Optics installation command failed: " + text[-2400:])
            return text
        finally:
            if process:
                ray_optics._stop(process)


def _require_python(report):
    target, version, _, _ = _target()
    expected_platform, machine = ("darwin", "arm64") if target == "macos-arm64" else ("linux", "x86_64")
    if report.get("python", [])[:2] != [int(v) for v in version.split(".")] or report.get("platform") != expected_platform or report.get("machine") != machine:
        raise ValueError(f"Choose a native {machine} CPython {version} interpreter for these exact wheels.")


def choose_python(value=None):
    version = _target()[1]
    candidates = [Path(value).expanduser()] if value else [Path(sys.executable), Path(f"/opt/homebrew/bin/python{version}")]
    executable = shutil.which(f"python{version}")
    if not value and executable:
        candidates.append(Path(executable))
    for path in candidates:
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            continue
        try:
            _require_python(json.loads(_run([path, "-I", "-B", "-c", BASE_PROBE], 3)))
            return path
        except (OSError, ValueError, RuntimeError, TimeoutError):
            if value:
                raise
    raise ValueError(f"Pass the absolute path of a native CPython {version} interpreter with --python.")


def verify_pip_report(path, lock):
    report, _ = _read(path)
    entries = report.get("install", [])
    expected = {p["name"]: p for p in lock["packages"]}
    if len(entries) != len(expected):
        raise ValueError("pip did not install exactly the locked optics wheel inventory.")
    seen = set()
    for entry in entries:
        metadata, download = entry.get("metadata", {}), entry.get("download_info", {})
        name = re.sub(r"[-_.]+", "-", metadata.get("name", "")).lower(); required = expected.get(name)
        if (name in seen or required is None or metadata.get("version") != required["version"] or
                download.get("url") != required["url"] or download.get("archive_info", {}).get("hashes", {}).get("sha256") != required["sha256"]):
            raise ValueError("pip installed an optics wheel with a different version, URL or hash.")
        seen.add(name)


def verify_local_pip_report(path, package, wheel):
    report, _ = _read(path)
    entries = report.get("install", [])
    if len(entries) != 1:
        raise ValueError("pip did not install exactly one locked optics wheel.")
    metadata, download = entries[0].get("metadata", {}), entries[0].get("download_info", {})
    name = re.sub(r"[-_.]+", "-", metadata.get("name", "")).lower()
    if (name != package["name"] or metadata.get("version") != package["version"]
            or download.get("url") != wheel.as_uri()
            or download.get("archive_info", {}).get("hashes", {}).get("sha256") != package["sha256"]):
        raise ValueError("pip installed an optics wheel with different local bytes or metadata.")


def probe_runtime(directory, cancel_event=None):
    directory = Path(directory)
    sources = _source_identity()
    config_path = directory / "pyvenv.cfg"
    if config_path.is_symlink() or not config_path.is_file() or not re.search(r"(?mi)^include-system-site-packages\s*=\s*false\s*$", config_path.read_text()):
        raise ValueError("Optics runtime must be a real isolated venv without system packages.")
    probe = "import importlib.metadata as m,json,platform,sys;names=" + repr(list(PINNED_PACKAGES)) + ";print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine(),'prefix':sys.prefix,'base_prefix':sys.base_prefix,'versions':{n:m.version(n) for n in names},'locations':{n:str(m.distribution(n).locate_file('')) for n in names}}))"
    python = directory / "bin/python"
    report = json.loads(_run([python, "-I", "-B", "-c", probe], 5, cancel_event))
    _require_python(report)
    if report["versions"] != PINNED_PACKAGES or Path(report["prefix"]).resolve() != directory.resolve() or report["prefix"] == report["base_prefix"]:
        raise ValueError("The optical interpreter, isolation or pinned package versions do not match.")
    for location in report["locations"].values():
        try:
            Path(location).resolve().relative_to(directory.resolve())
        except ValueError as exc:
            raise ValueError("An optics package was loaded outside its isolated runtime.") from exc
    with tempfile.TemporaryDirectory(prefix="cinematicum-optics-install-TEST-") as temporary:
        root = Path(temporary); model = ray_optics.default_prescription()
        model["fields"] = [model["fields"][0]]; model["wavelengths"] = [model["wavelengths"][1]]; model["aperture"]["value"] = 1
        result = ray_optics.run_ray_optics({"id": "optics-installer-verification"}, root,
                    {"version": 1, "operation": "analyze", "prescription": model}, root / "optics/outputs/probe",
                    python=str(python), cancel_event=cancel_event)
        actual = result["analysis"]
        checks = {"catalog_dispersion": abs(actual["materials"][0]["refractive_indices"][0]["n"] - 1.51680003) < 1e-7,
                  "thick_lens_focal_length": abs(actual["paraxial"]["effective_focal_length_mm"] - 49.2129957616) < 1e-7,
                  "real_ray_spot": 0 < actual["spots"][0]["rms_radius_mm"] < .0001,
                  "diffraction_strehl": .98 < actual["diffraction"][0]["strehl_ratio"] <= 1.000001,
                  "mtf_normalization": abs(actual["diffraction"][0]["tangential_mtf"][0] - 1) < 1e-12,
                  "complete_artifacts": set(result["artifacts"]) == ray_optics.ARTIFACT_NAMES}
        if not all(checks.values()):
            raise ValueError("The installed Optiland engine failed real optical numerical acceptance: " + json.dumps(checks))
        report["checks"] = checks; report["engine"] = result["receipt"]["runtime"]
    if _source_identity() != sources:
        raise ValueError("Optics verification code changed during actual numerical acceptance.")
    report["verification_sources"] = sources
    return report


def _destination(value):
    path = Path(value).expanduser() if value is not None else default_destination()
    if not path.is_absolute() or ".." in path.parts or path.name in ("", ".", ".."):
        raise ValueError("Optics destination must be an absolute named directory without parent traversal.")
    return path.parent.resolve() / path.name


def _hash_regular(path, limit=2 * 1024 * 1024 * 1024, cancel_event=None):
    digest = hashlib.sha256(); size = 0
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("Optics runtime files must be bounded regular files.")
        while True:
            _cancel(cancel_event)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("An optics runtime file grew beyond its byte limit.")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or size != before.st_size:
        raise ValueError("An optics runtime file changed while its bytes were verified.")
    return {"sha256": digest.hexdigest(), "bytes": size, "mode": stat.S_IMODE(before.st_mode)}


def _source_identity():
    root = Path(__file__).resolve().parent
    return {name: _hash_regular(root / name, 8 * 1024 * 1024)["sha256"]
            for name in ("install_ray_optics.py", "ray_optics.py", "ray_optics_worker.py", "imaging.py")}


def _base_identity(path):
    resolved = Path(path).resolve(strict=True)
    return {"resolved_path": str(resolved), **_hash_regular(resolved, 256 * 1024 * 1024)}


def _inventory(runtime, cancel_event=None):
    """Bind every directory, link and regular file except the self-containing receipt."""
    result = {}; total = 0
    for current, directories, files in os.walk(runtime, followlinks=False):
        directories.sort(); files.sort()
        for name in directories + files:
            _cancel(cancel_event)
            path = Path(current) / name; relative = path.relative_to(runtime).as_posix()
            if relative == RECEIPT:
                continue
            details = path.lstat()
            if stat.S_ISLNK(details.st_mode):
                result[relative] = {"link": os.readlink(path)}
            elif stat.S_ISREG(details.st_mode):
                result[relative] = _hash_regular(path, cancel_event=cancel_event)
                total += result[relative]["bytes"]
            elif stat.S_ISDIR(details.st_mode):
                result[relative] = {"directory": True, "mode": stat.S_IMODE(details.st_mode)}
            else:
                raise ValueError("Optics runtime contains a nonregular filesystem object.")
            if len(result) > 100000 or total > 10 * 1024 * 1024 * 1024:
                raise ValueError("Optics runtime inventory exceeds its explicit file or byte bound.")
    return result


def _existing(destination, digest, cancel_event=None):
    if not os.path.lexists(destination):
        return None
    if not destination.is_symlink():
        raise ValueError("An existing unmanaged optics destination will not be replaced or modified.")
    link = Path(os.readlink(destination))
    if link.is_absolute() or len(link.parts) != 2 or link.parts[0] != VERSIONS_DIRECTORY or not re.fullmatch(_target()[2] + r"-[a-f0-9]{32}", link.name):
        raise ValueError("An unrelated optics symlink will not be changed.")
    runtime = destination.parent / link
    if runtime.is_symlink() or runtime.parent.is_symlink() or not runtime.is_dir():
        raise ValueError("The managed optical runtime link is invalid.")
    receipt, _ = _read(runtime / RECEIPT, 32 * 1024 * 1024)
    if (receipt.get("schema") != "cinematicum-optics-install" or receipt.get("wheel_lock_sha256") != digest
            or receipt.get("runtime_directory") != str(runtime) or receipt.get("stable_destination") != str(destination)):
        raise ValueError("The managed optical runtime lacks a matching wheel installation receipt.")
    if receipt.get("version") != 2 or not isinstance(receipt.get("inventory"), dict):
        raise ValueError("The existing optics receipt predates full inventory verification; it is preserved. Choose a new destination for the current managed installer.")
    if _base_identity(receipt["base_python"]) != receipt.get("base_python_identity"):
        raise ValueError("The external native Python interpreter changed after optics runtime publication.")
    before = _inventory(runtime, cancel_event)
    if before != receipt["inventory"]:
        raise ValueError("The installed optics runtime inventory changed after publication.")
    verification = probe_runtime(runtime, cancel_event)
    if _inventory(runtime, cancel_event) != before:
        raise ValueError("The installed optics runtime changed during actual numerical verification.")
    return {"status": "unchanged", "runtime": str(destination), "python": str(destination / "bin/python"),
            "wheel_lock_sha256": digest, "receipt": str(runtime / RECEIPT), "verification": verification,
            "inventory_entries": len(before)}


@contextmanager
def _install_lock(parent):
    fd = os.open(parent / ".cinematicum-optics-install.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Optics install lock is not a regular file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another managed optics installation is running.") from exc
        yield
    finally:
        os.close(fd)


def _save_state(path, value, create=False):
    data = ray_optics._json_bytes(value) + b"\n"
    if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
        raise ValueError("An optics installation record cannot replace a link or nonregular path.")
    temporary = path if create else path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if not create:
            os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if not create and temporary.exists():
            temporary.unlink()


def _runtime_from_state(destination, state, digest):
    name = state.get("runtime_name", ""); index = state.get("package_index")
    if (state.get("schema") != "cinematicum-optics-pending" or state.get("version") != 2
            or state.get("destination") != str(destination) or state.get("wheel_lock_sha256") != digest
            or not re.fullmatch(_target()[2] + r"-[a-f0-9]{32}", name) or state.get("phase") not in PHASES
            or type(index) is not int or not 0 <= index <= len(PINNED_PACKAGES)
            or state["phase"] in {"download", "install"} and index == len(PINNED_PACKAGES)):
        raise ValueError("Unrelated or malformed pending optics installation will not be adopted.")
    runtime = destination.parent / VERSIONS_DIRECTORY / name
    if runtime.is_symlink() or runtime.parent.is_symlink() or not runtime.is_dir():
        raise ValueError("The pending optics runtime is not an owned real directory.")
    marker, _ = _read(runtime / "owner.json")
    keys = ("schema", "version", "destination", "wheel_lock_sha256", "runtime_name", "base_python", "base_python_identity")
    if marker != {key: state.get(key) for key in keys}:
        raise ValueError("The pending optics runtime ownership marker differs from its journal.")
    if not isinstance(state.get("base_python"), str) or not Path(state["base_python"]).is_absolute():
        raise ValueError("The pending native Python identity is invalid.")
    if _base_identity(state["base_python"]) != state.get("base_python_identity"):
        raise ValueError("The pending optics setup cannot switch or mutate its native interpreter.")
    return runtime


def _verify_wheel(path, package, event=None):
    actual = _hash_regular(path, 250 * 1024 * 1024, event)
    if (actual["sha256"], actual["bytes"]) != (package["sha256"], package["size"]):
        raise ValueError("The optics wheel differs from its exact pinned SHA-256 or byte count.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Optics wheel downloads cannot redirect away from their exact pinned HTTPS URL.")


def _download_chunk(directory, package, event=None, wheel_cache=None):
    path = directory / package["filename"]; partial = path.with_name(path.name + ".part")
    if os.path.lexists(path):
        _verify_wheel(path, package, event); return True
    offset = 0
    if os.path.lexists(partial):
        details = partial.lstat()
        if not stat.S_ISREG(details.st_mode) or not 0 <= details.st_size <= package["size"]:
            raise ValueError("Invalid partial optics wheel ownership or size.")
        offset = details.st_size
    if offset == package["size"]:
        _verify_wheel(partial, package, event); os.replace(partial, path); return True
    end = min(package["size"], offset + CHUNK_BYTES) - 1
    source = Path(wheel_cache) / package["filename"] if wheel_cache is not None else None
    if source is not None and os.path.lexists(source):
        _verify_wheel(source, package, event)
        response = source.open("rb"); response.seek(offset)
    else:
        request = urllib.request.Request(package["url"], headers={"Range": f"bytes={offset}-{end}", "Accept-Encoding": "identity"})
        _cancel(event)
        response = urllib.request.build_opener(_NoRedirect()).open(request, timeout=4)
        if (response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{package['size']}"
                or response.headers.get("Content-Length") != str(end - offset + 1)
                or response.headers.get("Content-Encoding", "identity") != "identity"):
            response.close()
            raise ValueError("The pinned optics wheel server did not honor the exact unencoded resumable byte range.")
    started = time.monotonic()
    with response:
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_size != offset:
                raise ValueError("Partial optics wheel changed during its bounded download.")
            stream.seek(offset); count = 0
            while count < end - offset + 1:
                _cancel(event)
                if time.monotonic() - started > 7:
                    break
                chunk = response.read(min(256 * 1024, end - offset + 1 - count))
                if not chunk:
                    raise ValueError("The optics wheel response ended before its requested byte range.")
                stream.write(chunk); count += len(chunk)
            stream.flush(); os.fsync(stream.fileno())
    if partial.stat().st_size == package["size"]:
        _verify_wheel(partial, package, event); os.replace(partial, path); return True
    return False


def info(destination=None):
    lock, digest = load_lock(); destination = _destination(destination)
    result = {"runtime": "ray-optics", "platform": lock["platform"], "python": lock["python"],
              "destination": str(destination), "wheel_lock_sha256": digest,
              "download_bytes": sum(p["size"] for p in lock["packages"]), "packages": lock["packages"],
              "destination_exists": os.path.lexists(destination), "pending": os.path.lexists(destination.parent / PENDING),
              "bounded_step": True, "phase_budget_seconds": STEP_SECONDS, "download_chunk_bytes": CHUNK_BYTES,
              "scope": "Pinned CPU Optiland; actual sequential rays, catalogue dispersion, PSF and MTF. Native Python is external."}
    if result["pending"]:
        state, _ = _read(destination.parent / PENDING, 32 * 1024 * 1024)
        _runtime_from_state(destination, state, digest)
        result.update(phase=state["phase"], package_index=state["package_index"])
    return result


def _step(destination, python, event, wheel_cache):
    _cancel(event); lock, digest = load_lock(); destination = _destination(destination)
    if os.path.lexists(destination):
        return _existing(destination, digest, event)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _install_lock(destination.parent):
        if os.path.lexists(destination):
            return _existing(destination, digest, event)
        journal = destination.parent / PENDING
        if not os.path.lexists(journal):
            base = choose_python(python); versions = destination.parent / VERSIONS_DIRECTORY
            if versions.is_symlink() or os.path.lexists(versions) and not versions.is_dir():
                raise ValueError("An unrelated file or link occupies the managed optics versions directory.")
            versions.mkdir(mode=0o700, exist_ok=True)
            name = _target()[2] + "-" + uuid.uuid4().hex; runtime = versions / name; runtime.mkdir(mode=0o700)
            state = {"schema": "cinematicum-optics-pending", "version": 2, "destination": str(destination),
                     "wheel_lock_sha256": digest, "runtime_name": name, "base_python": str(base),
                     "base_python_identity": _base_identity(base), "phase": "venv", "package_index": 0}
            _save_state(runtime / "owner.json", {key: state[key] for key in
                        ("schema", "version", "destination", "wheel_lock_sha256", "runtime_name", "base_python", "base_python_identity")}, True)
            _save_state(journal, state, True)
            return {"status": "in_progress", "phase": "venv", "package_index": 0, "wheel_lock_sha256": digest,
                    "download_bytes": sum(p["size"] for p in lock["packages"])}
        state, _ = _read(journal, 32 * 1024 * 1024)
        runtime = _runtime_from_state(destination, state, digest); phase = state["phase"]; base = Path(state["base_python"])
        if python is not None and Path(python).expanduser() != base:
            raise ValueError("A resumable optics install cannot switch its base interpreter.")
        interpreter = runtime / "bin/python"; cache = runtime / "wheel-cache"
        if phase == "venv":
            command = [base, "-I", "-B", "-m", "venv", "--without-pip"]
            if _target()[1] == "3.13":
                command.append("--without-scm-ignore-files")
            _run([*command, runtime], 10, event); state["phase"] = "ensurepip"
        elif phase == "ensurepip":
            _run([interpreter, "-I", "-B", "-m", "ensurepip", "--default-pip"], 10, event)
            if cache.is_symlink() or os.path.lexists(cache) and not cache.is_dir():
                raise ValueError("The owned optics wheel cache is invalid.")
            cache.mkdir(mode=0o700, exist_ok=True); state["phase"] = "download"
        elif phase == "download":
            if cache.is_symlink() or not cache.is_dir():
                raise ValueError("The owned optics wheel cache is invalid.")
            package = lock["packages"][state["package_index"]]
            if _download_chunk(cache, package, event, wheel_cache):
                state["package_index"] += 1
                if state["package_index"] == len(lock["packages"]):
                    state.update(phase="install", package_index=0)
        elif phase == "install":
            package = lock["packages"][state["package_index"]]; wheel = cache / package["filename"]
            _verify_wheel(wheel, package, event)
            requirements = runtime / "wheel-requirement.txt"
            text = f"{package['name']} @ {wheel.as_uri()} --hash=sha256:{package['sha256']}\n"
            if os.path.lexists(requirements) and (requirements.is_symlink() or not requirements.is_file()):
                raise ValueError("The owned optics requirement path is invalid.")
            requirements.write_text(text)
            report = runtime / ("pip-" + package["name"] + ".json")
            if report.is_symlink() or os.path.lexists(report) and not report.is_file():
                raise ValueError("The owned optics pip receipt path is invalid.")
            _run([interpreter, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
                  "install", "--no-index", "--no-deps", "--only-binary=:all:", "--require-hashes", "--force-reinstall",
                  "--no-compile", "--report", report, "-r", requirements], 10, event)
            verify_local_pip_report(report, package, wheel); state["package_index"] += 1
            if state["package_index"] == len(lock["packages"]):
                state["phase"] = "dependencies"
        elif phase == "dependencies":
            for package in lock["packages"]:
                verify_local_pip_report(runtime / ("pip-" + package["name"] + ".json"), package, cache / package["filename"])
            _run([interpreter, "-I", "-B", "-m", "pip", "--isolated", "check"], 5, event)
            state["phase"] = "verify"
        elif phase == "verify":
            verification = probe_runtime(runtime, event)
            _save_state(runtime / "optics-acceptance.json", verification)
            state.pop("inventory", None); state["phase"] = "inventory"
        elif phase == "inventory":
            verification, _ = _read(runtime / "optics-acceptance.json")
            if verification.get("verification_sources") != _source_identity():
                state["phase"] = "verify"; _save_state(journal, state)
                raise ValueError("Optics verification source changed; the next explicit step reruns real numerical acceptance.")
            state["inventory"] = _inventory(runtime, event); state["phase"] = "publish"
        elif phase == "publish":
            verification, _ = _read(runtime / "optics-acceptance.json")
            if verification.get("verification_sources") != _source_identity() or _inventory(runtime, event) != state.get("inventory"):
                state.pop("inventory", None); state["phase"] = "verify"; _save_state(journal, state)
                raise ValueError("The optical runtime or verification source changed before publication; resume to rerun acceptance.")
            current = probe_runtime(runtime, event)
            if (current["versions"] != verification["versions"] or current["verification_sources"] != verification["verification_sources"]
                    or _inventory(runtime, event) != state["inventory"]):
                state.pop("inventory", None); state["phase"] = "verify"; _save_state(journal, state)
                raise ValueError("The optical runtime changed during publication verification; resume to rerun acceptance.")
            receipt = {"schema": "cinematicum-optics-install", "version": 2, "runtime_directory": str(runtime),
                       "stable_destination": str(destination), "base_python": str(base),
                       "base_python_identity": state["base_python_identity"], "wheel_lock_sha256": digest,
                       "wheels": lock["packages"], "verification": current, "inventory": state["inventory"]}
            _cancel(event); _save_state(runtime / RECEIPT, receipt)
            os.symlink(str(Path(VERSIONS_DIRECTORY) / runtime.name), destination, target_is_directory=True)
            journal.unlink()
            return {"status": "installed", "runtime": str(destination), "python": str(destination / "bin/python"),
                    "wheel_lock_sha256": digest, "receipt": str(runtime / RECEIPT), "verification": current,
                    "inventory_entries": len(state["inventory"])}
        _cancel(event); _save_state(journal, state)
        result = {"status": "in_progress", "phase": state["phase"], "package_index": state["package_index"], "wheel_lock_sha256": digest}
        if state["phase"] == "download":
            package = lock["packages"][state["package_index"]]
            partial = cache / (package["filename"] + ".part")
            result.update(package=package["name"], package_bytes=package["size"],
                          package_downloaded_bytes=partial.stat().st_size if partial.exists() else 0)
        return result


def _phase_budget(value):
    if type(value) is not int or not 1 <= value <= 60:
        raise ValueError("An explicit foreground optics phase budget must be an integer from 1 to 60 seconds.")
    return value


def step(destination=None, python=None, cancel_event=None, wheel_cache=None, *, phase_budget_seconds=STEP_SECONDS):
    """One foreground phase; deadline cancellation terminates only owned children."""
    event = _BudgetEvent(cancel_event, _phase_budget(phase_budget_seconds))
    try:
        return _step(destination, python, event, wheel_cache)
    except InterruptedError:
        _cancel(event)
        raise


def install(destination=None, python=None, check_only=False, cancel_event=None, progress=None, wheel_cache=None,
            *, phase_budget_seconds=STEP_SECONDS):
    phase_budget_seconds = _phase_budget(phase_budget_seconds)
    lock, digest = load_lock(); destination = _destination(destination)
    if check_only:
        _cancel(cancel_event)
        result = _existing(destination, digest, _BudgetEvent(cancel_event, phase_budget_seconds))
        if result is None:
            raise ValueError("The managed optics runtime is not installed at " + str(destination))
        return result
    started = time.monotonic()
    while True:
        _cancel(cancel_event)
        if time.monotonic() - started > 3600:
            raise TimeoutError("Optics installation exceeded its one-hour foreground budget; owned progress remains resumable.")
        result = step(destination, python, cancel_event, wheel_cache, phase_budget_seconds=phase_budget_seconds)
        if progress is not None:
            progress(result)
        if result["status"] != "in_progress":
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--wheel-cache", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--step", action="store_true")
    mode.add_argument("--info", action="store_true")
    args = parser.parse_args()
    try:
        if args.info:
            result = info(args.destination)
        elif args.step:
            result = step(args.destination, args.python, wheel_cache=args.wheel_cache)
        else:
            result = install(args.destination, args.python, args.check, wheel_cache=args.wheel_cache)
        print(json.dumps(result, sort_keys=True, allow_nan=False)); return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())

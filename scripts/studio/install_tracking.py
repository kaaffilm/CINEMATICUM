#!/usr/bin/env python3
"""Install or verify CINEMATICUM's optional Apple Silicon tracking runtime.

python3 scripts/studio/install_tracking.py --python /opt/homebrew/bin/python3.13
python3 scripts/studio/install_tracking.py --check

Only the two SHA-256-locked macOS arm64 wheels for Python 3.13 are installed.
An existing healthy runtime is left unchanged. A new venv is created at its
permanent, versioned path, verified there, then published by creating the stable
runtime symlink atomically. The venv is never moved (its scripts use absolute
interpreter paths), and no existing destination is replaced.
"""
import argparse
from contextlib import contextmanager
from contextvars import ContextVar
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
import time
import uuid
from urllib.parse import urlsplit

RUNTIME_REQUIREMENTS = {"numpy": "2.3.5", "opencv-python-headless": "4.11.0.86"}
_CANCEL_EVENT = ContextVar("cinematicum_tracking_install_cancel", default=None)


LOCK = Path(__file__).with_name("tracking-macos-arm64-py313.lock.json")
VERSIONS_DIRECTORY = ".cinematicum-tracking-runtimes"
RECEIPT = "cinematicum-tracking-install.json"
PROBE_CHECKS = {"projective_reprojection", "affine_reprojection", "optical_flow_translation"}

BASE_PROBE = "import json,platform,sys; print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine()}))"
RUNTIME_PROBE = r'''
import importlib.metadata, json, pathlib, platform, sys
import numpy as np
import cv2
cv2.setNumThreads(1)
points = np.array([[10,10],[40,10],[75,15],[15,40],[40,40],[75,45],[20,75],[60,75]], dtype=np.float64)
known = np.array([[1.08,.12,4],[-.07,.94,6],[.0007,-.0004,1]], dtype=np.float64)
target = cv2.perspectiveTransform(points.reshape(-1,1,2), known).reshape(-1,2)
measured, inliers = cv2.findHomography(points, target, cv2.RANSAC, .1)
assert measured is not None and inliers.sum() == len(points)
assert np.max(np.abs(cv2.perspectiveTransform(points.reshape(-1,1,2), measured).reshape(-1,2)-target)) < .0001
affine = np.array([[.97,-.12,5],[.09,1.03,-3]], dtype=np.float64)
affine_target = points @ affine[:,:2].T + affine[:,2]
measured_affine, mask = cv2.estimateAffine2D(points, affine_target, method=cv2.RANSAC, ransacReprojThreshold=.1)
assert mask.sum() == len(points) and np.max(np.abs(measured_affine-affine)) < .0001
rng = np.random.default_rng(6241)
image = cv2.GaussianBlur(rng.integers(0,256,(128,160),dtype=np.uint8),(3,3),.7)
shifted = cv2.warpAffine(image,np.float32([[1,0,3],[0,1,-2]]),(160,128))
features = cv2.goodFeaturesToTrack(image,80,.02,8)
features = features[(features[:,0,0]>15)&(features[:,0,0]<145)&(features[:,0,1]>15)&(features[:,0,1]<113)]
tracked, status, error = cv2.calcOpticalFlowPyrLK(image,shifted,features,None,winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,40,.001))
valid=status.ravel().astype(bool)
assert valid.sum() >= 12 and np.median(np.linalg.norm(tracked[valid]-features[valid]-np.float32([[[3,-2]]]),axis=2)) < .05
modules={"numpy":np,"opencv-python-headless":cv2}
print(json.dumps({"python":list(sys.version_info[:3]),"platform":sys.platform,"machine":platform.machine(),
 "prefix":sys.prefix,"base_prefix":sys.base_prefix,
 "versions":{name:importlib.metadata.version(name) for name in modules},
 "modules":{name:str(pathlib.Path(module.__file__).resolve()) for name,module in modules.items()},
 "checks":{"projective_reprojection":True,"affine_reprojection":True,"optical_flow_translation":True}}))
'''


def default_destination():
    return Path.home() / "Library/Application Support/CINEMATICUM/Tracking/py313-v1"


def _clean_env():
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "OCIO", "PIP_"))}
    env.update(PIP_CONFIG_FILE=os.devnull, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    return env


def _run(command, timeout):
    from adapters import _cancelled, _terminate_owned
    event = _CANCEL_EVENT.get()
    _cancelled(event)
    process = None
    try:
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen([str(part) for part in command], stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, env=_clean_env(),
                                       start_new_session=True)
            started = time.monotonic()
            while process.poll() is None:
                _cancelled(event)
                if time.monotonic() - started > timeout:
                    raise RuntimeError("The tracking installation command exceeded its %d-second limit." % timeout)
                if event is not None:
                    event.wait(.1)
                else:
                    time.sleep(.1)
            _cancelled(event)
            length = log.seek(0, os.SEEK_END)
            log.seek(max(0, length - 2 * 1024 * 1024))
            output = log.read().decode("utf-8", errors="replace")
            if process.returncode:
                raise RuntimeError("Tracking installation command failed: " + output[-2400:])
            return output
    finally:
        if process is not None:
            _terminate_owned(process)


def _read_json(path, maximum=128 * 1024):
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("An tracking installer record is not a regular file.")
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("An tracking installer record exceeds its size limit.")
    return json.loads(data), data


def load_lock():
    lock, data = _read_json(LOCK)
    if (lock.get("schema") != "cinematicum-tracking-wheel-lock" or lock.get("version") != 1
            or lock.get("platform") != "macos-arm64" or lock.get("python") != "3.13"):
        raise ValueError("The tracking wheel lock has an unsupported platform or schema.")
    packages = lock.get("packages")
    if not isinstance(packages, list) or len(packages) != len(RUNTIME_REQUIREMENTS):
        raise ValueError("The tracking wheel lock must contain the two required packages.")
    if {item.get("name"): item.get("version") for item in packages} != RUNTIME_REQUIREMENTS:
        raise ValueError("The tracking wheel lock and worker runtime versions disagree.")
    for item in packages:
        filename = ("opencv_python_headless-4.11.0.86-cp37-abi3-macosx_13_0_arm64.whl"
                    if item["name"] == "opencv-python-headless" else "numpy-2.3.5-cp313-cp313-macosx_11_0_arm64.whl")
        url = urlsplit(item.get("url", ""))
        if (item.get("filename") != filename or url.scheme != "https" or url.netloc != "files.pythonhosted.org"
                or not re.fullmatch(r"/packages/[a-z0-9/]+/" + re.escape(filename), url.path)
                or url.query or url.fragment or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))
                or not isinstance(item.get("size"), int) or not 0 < item["size"] < 40 * 1024 * 1024):
            raise ValueError("The tracking lock contains an unsupported wheel identity or location.")
    return lock, hashlib.sha256(data).hexdigest()


def _require_host():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise ValueError("This wheel installer supports Apple Silicon macOS only. The editor itself does not require this optional runtime.")


def _require_python(report):
    if report.get("python", [])[:2] != [3, 13] or report.get("platform") != "darwin" or report.get("machine") != "arm64":
        raise ValueError("Choose an Apple Silicon CPython 3.13 interpreter, for example /opt/homebrew/bin/python3.13.")


def choose_python(value=None):
    candidates = [Path(value).expanduser()] if value else [Path(sys.executable),
        Path.home() / "Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python",
        Path("/opt/homebrew/bin/python3.13")]
    for candidate in candidates:
        if not candidate.is_absolute() or not candidate.is_file() or not os.access(str(candidate), os.X_OK):
            continue
        try:
            _require_python(json.loads(_run([candidate, "-I", "-c", BASE_PROBE], 10)))
            return candidate
        except (ValueError, RuntimeError):
            if value:
                raise
    raise ValueError("Apple Silicon Python 3.13 is required. Pass its absolute path with --python.")


def probe_runtime(directory):
    directory = Path(directory)
    if not (directory / "pyvenv.cfg").is_file() or (directory / "pyvenv.cfg").is_symlink():
        raise ValueError("The destination is not an isolated Python virtual environment; it will not be replaced.")
    config = (directory / "pyvenv.cfg").read_text(encoding="utf-8")
    if not re.search(r"(?mi)^include-system-site-packages\s*=\s*false\s*$", config):
        raise ValueError("The existing runtime exposes system packages; it will not be changed.")
    report = json.loads(_run([directory / "bin/python", "-I", "-c", RUNTIME_PROBE], 18))
    _require_python(report)
    root = directory.resolve()
    if Path(report.get("prefix", "")).resolve() != root or report.get("prefix") == report.get("base_prefix"):
        raise ValueError("The tracking interpreter did not activate the requested isolated environment.")
    if report.get("versions") != RUNTIME_REQUIREMENTS:
        raise ValueError("The existing runtime does not match the pinned tracking versions; it will not be changed.")
    if report.get("checks") != dict.fromkeys(PROBE_CHECKS, True):
        raise ValueError("The runtime failed its actual optical-flow, affine or projective geometry checks.")
    for name in RUNTIME_REQUIREMENTS:
        try:
            Path(report["modules"][name]).resolve().relative_to(root)
        except (KeyError, ValueError) as exc:
            raise ValueError("An tracking module was imported from outside its isolated environment.") from exc
    return report


def _destination(value):
    path = Path(value).expanduser() if value is not None else default_destination()
    if not path.is_absolute() or path.name in {"", ".", ".."} or ".." in path.parts:
        raise ValueError("The tracking destination must be a named absolute path without parent traversal.")
    # The explicitly selected containing directory may have OS-managed aliases
    # (macOS /var -> /private/var). Preserve the final leaf for no-overwrite checks.
    return path.parent.resolve() / path.name


def _existing(destination, lock_sha):
    if not os.path.lexists(destination):
        return None
    if destination.is_symlink():
        link = Path(os.readlink(destination))
        if (link.is_absolute() or len(link.parts) != 2 or link.parts[0] != VERSIONS_DIRECTORY
                or not re.fullmatch(r"py313-v1-[0-9a-f]{32}", link.name)):
            raise ValueError("The destination is an unrelated symlink; it will not be replaced.")
        runtime = destination.parent / link
        if runtime.parent.is_symlink() or runtime.is_symlink() or not runtime.is_dir():
            raise ValueError("The managed runtime link is invalid; it will not be replaced.")
        receipt, _ = _read_json(runtime / RECEIPT)
        if (receipt.get("schema") != "cinematicum-tracking-install" or receipt.get("version") != 1
                or receipt.get("runtime_directory") != str(runtime) or receipt.get("wheel_lock_sha256") != lock_sha):
            raise ValueError("The existing runtime link has no matching CINEMATICUM installation receipt.")
    elif not destination.is_dir():
        raise ValueError("An unrelated file occupies the tracking destination; it will not be replaced.")
    return {"status": "unchanged", "runtime": str(destination), "python": str(destination / "bin/python"),
            "verification": probe_runtime(destination), "wheel_lock_sha256": lock_sha,
            "existing_wheel_provenance": "installer receipt" if destination.is_symlink() else "existing environment; package versions and behavior verified, original wheel hashes not asserted"}


@contextmanager
def _install_lock(parent):
    fd = os.open(str(parent / ".cinematicum-tracking-install.lock"), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("The tracking installation lock is not a regular file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another tracking installation is running.") from exc
        yield
    finally:
        os.close(fd)


def verify_pip_report(path, lock):
    report, _ = _read_json(path, maximum=2 * 1024 * 1024)
    installed = report.get("install", [])
    if len(installed) != len(lock["packages"]):
        raise ValueError("pip did not report exactly the two locked tracking wheels.")
    expected = {item["name"].lower(): item for item in lock["packages"]}
    seen = set()
    for item in installed:
        metadata, download = item.get("metadata", {}), item.get("download_info", {})
        name = metadata.get("name", "").lower()
        entry = expected.get(name)
        if (entry is None or name in seen or metadata.get("version") != entry["version"]
                or download.get("url") != entry["url"]
                or download.get("archive_info", {}).get("hashes", {}).get("sha256") != entry["sha256"]):
            raise ValueError("The installed wheel report differs from the pinned identities.")
        seen.add(name)


def _build_runtime(directory, python, lock):
    _run([python, "-I", "-m", "venv", "--without-scm-ignore-files", directory], 90)
    requirements = directory / "tracking-wheel-requirements.txt"
    requirements.write_text("".join("%s @ %s --hash=sha256:%s\n" % (p["name"], p["url"], p["sha256"]) for p in lock["packages"]), encoding="utf-8")
    report = directory / "pip-install-report.json"
    _run([directory / "bin/python", "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
          "install", "--no-index", "--no-deps", "--only-binary=:all:", "--require-hashes", "--timeout", "30", "--retries", "2",
          "--report", report, "-r", requirements], 600)
    verify_pip_report(report, lock)
    return probe_runtime(directory)


def _install(destination=None, python=None, check_only=False):
    _require_host()
    lock, lock_sha = load_lock()
    destination = _destination(destination)
    existing = _existing(destination, lock_sha)
    if existing:
        return existing
    if check_only:
        raise ValueError("The optional tracking runtime is not installed at " + str(destination))
    python = choose_python(python)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _install_lock(destination.parent):
        existing = _existing(destination, lock_sha)
        if existing:
            return existing
        versions = destination.parent / VERSIONS_DIRECTORY
        if versions.is_symlink() or os.path.lexists(versions) and not versions.is_dir():
            raise ValueError("The managed tracking versions path is occupied by an unrelated file or link.")
        versions.mkdir(mode=0o700, exist_ok=True)
        runtime = versions / ("py313-v1-" + uuid.uuid4().hex)
        runtime.mkdir(mode=0o700)
        published = False
        try:
            verification = _build_runtime(runtime, python, lock)
            receipt = {"schema": "cinematicum-tracking-install", "version": 1,
                       "runtime_directory": str(runtime), "stable_destination": str(destination),
                       "base_python": str(python), "wheel_lock_sha256": lock_sha,
                       "wheels": lock["packages"], "verification": verification}
            with (runtime / RECEIPT).open("x", encoding="utf-8") as record:
                json.dump(receipt, record, indent=2, sort_keys=True, allow_nan=False)
                record.write("\n")
                record.flush()
                os.fsync(record.fileno())
            # symlink() atomically creates a previously absent path. Unlike
            # replace()/rename(), it cannot overwrite a concurrent destination.
            os.symlink(str(Path(VERSIONS_DIRECTORY) / runtime.name), str(destination), target_is_directory=True)
            published = True
            return {"status": "installed", "runtime": str(destination), "python": str(destination / "bin/python"),
                    "receipt": str(runtime / RECEIPT), "verification": verification, "wheel_lock_sha256": lock_sha}
        finally:
            if not published:
                shutil.rmtree(runtime)


def install(destination=None, python=None, check_only=False, cancel_event=None):
    token = _CANCEL_EVENT.set(cancel_event)
    try:
        return _install(destination, python, check_only)
    finally:
        _CANCEL_EVENT.reset(token)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", type=Path, help="Absolute Apple Silicon CPython 3.13 path; no system Python is modified.")
    parser.add_argument("--destination", type=Path, help="Optional separate absolute runtime destination; existing paths are never replaced.")
    parser.add_argument("--check", action="store_true", help="Verify the existing runtime without installing or changing it.")
    args = parser.parse_args()
    try:
        result = install(args.destination, args.python, args.check)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Owned offline DiffusionLight worker; readiness is distinct from inference.

Runtime settings are installation configuration, never project-supplied code or
model locations. This module neither installs dependencies nor downloads models.
"""
from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time
import uuid

SOURCE_LOCK_SHA256 = "22f47f70dc890bd8884791ef3924e8b7d700dd82039ce1c47e73ca3e5701d33e"
RUNTIME_KEYS = {"python", "upstream_root", "model_manifest", "model_manifest_sha256", "device"}


def digest(path):
    value = hashlib.sha256()
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("DiffusionLight inputs must be regular files.")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("A DiffusionLight input changed during verification.")
    return value.hexdigest()


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _path(value, directory=False):
    if not isinstance(value, (str, Path)) or not Path(value).is_absolute():
        raise ValueError("DiffusionLight runtime paths must be absolute.")
    path = Path(value)
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError("DiffusionLight runtime paths cannot contain symbolic links.")
    if directory and not path.is_dir() or not directory and not path.is_file():
        raise ValueError("A required DiffusionLight runtime input is missing.")
    return path


def validate_runtime(runtime):
    if not isinstance(runtime, dict) or set(runtime) != RUNTIME_KEYS:
        raise ValueError("DiffusionLight requires explicit app-owned Python, source, model manifest, manifest hash and device.")
    if runtime["device"] not in {"cpu", "cuda"}:
        raise ValueError("This upstream DiffusionLight worker supports explicit CPU or CUDA; MPS has not been validated.")
    if not _sha(runtime["model_manifest_sha256"]):
        raise ValueError("The app-owned DiffusionLight model manifest requires its trusted SHA256.")
    # Standard virtual environments intentionally use a Python executable
    # symlink. Keep its invocation path so Python recognizes pyvenv.cfg, while
    # source, weight and manifest paths below remain strictly regular/canonical.
    executable = Path(runtime["python"]) if isinstance(runtime["python"], (str, Path)) else Path()
    if not executable.is_absolute() or not executable.is_file() or executable.parent.resolve() != executable.parent:
        raise ValueError("DiffusionLight requires an absolute app-owned Python executable.")
    result = {name: str(_path(runtime[name], name == "upstream_root")) for name in ("upstream_root", "model_manifest")}
    result["python"] = str(executable)
    result.update(device=runtime["device"], model_manifest_sha256=runtime["model_manifest_sha256"])
    if not os.access(result["python"], os.X_OK):
        raise ValueError("DiffusionLight Python is not executable.")
    if digest(result["model_manifest"]) != result["model_manifest_sha256"]:
        raise ValueError("The DiffusionLight model manifest differs from the app-owned trusted identity.")
    return result


def options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {"algorithm", "seed", "steps"}:
        raise ValueError("DiffusionLight options are algorithm, seed and steps.")
    result = {"algorithm": "iterative", "seed": 0, "steps": 30, **value}
    if result["algorithm"] not in {"iterative", "normal"}:
        raise ValueError("DiffusionLight algorithm must be iterative or normal.")
    for name, low, high in (("seed", 0, 2**32 - 1), ("steps", 10, 100)):
        if type(result[name]) is not int or not low <= result[name] <= high:
            raise ValueError("DiffusionLight %s is outside its integer range." % name)
    return result


def _environment():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PYTHON", "HF_", "HUGGINGFACE", "TRANSFORMERS", "DIFFUSERS", "PIP_", "OCIO"))}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", DIFFUSERS_OFFLINE="1",
               HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", PYTHONDONTWRITEBYTECODE="1",
               OMP_NUM_THREADS="4", TOKENIZERS_PARALLELISM="false")
    return env


def _stop(process):
    if process is None:
        return
    # start_new_session makes this exact child's PID the owned process group.
    # Its leader may already have exited while an inherited child remains.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=2)
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        process.poll()  # Reap our own leader even when its children are exiting.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(.02)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=2)


def _record_state(output_dir, **updates):
    """Keep the latest known execution state, including across cancellation."""
    path = Path(output_dir) / "progress.json"
    if path.exists():
        _path(path)
        if path.stat().st_size > 65536:
            raise ValueError("DiffusionLight inference state exceeds its bound.")
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict) or value.get("schema") != "cinematicum-diffusionlight-execution":
            raise ValueError("DiffusionLight inference state is not owned execution evidence.")
    else:
        value = {"schema": "cinematicum-diffusionlight-execution", "version": 1,
                 "inference_started": False, "inference_executed": False, "inference_completed": False}
    if value.get("inference_started") is True and updates.get("inference_started") is False:
        raise ValueError("DiffusionLight inference-start evidence cannot be reset.")
    if value.get("inference_executed") is True and "inference_executed" in updates and updates["inference_executed"] is not True:
        raise ValueError("Completed DiffusionLight inference evidence cannot be reset.")
    if value.get("inference_started") is True and updates.get("inference_executed") is False:
        raise ValueError("Started DiffusionLight inference cannot be relabeled as unexecuted.")
    if value.get("inference_completed") is True and "inference_completed" in updates and updates["inference_completed"] is not True:
        raise ValueError("Completed DiffusionLight inference evidence cannot be reset.")
    value.update(updates, updated_at=time.time())
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with temporary.open("xb") as stream:
            stream.write((json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return value


def _run(runtime, request, cancel_event=None, timeout=1800, _stderr=None):
    runtime = validate_runtime(runtime)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 21600:
        raise ValueError("DiffusionLight timeout must be between one second and six hours.")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("DiffusionLight operation cancelled before launch.")
    lock = Path(__file__).with_name("diffusionlight-source-lock.json")
    if digest(lock) != SOURCE_LOCK_SHA256:
        raise ValueError("The shipped DiffusionLight source lock changed.")
    request = {**request, "runtime": runtime}
    worker = Path(__file__).with_name("diffusionlight_worker.py")
    process = None
    with tempfile.TemporaryFile() as output, (nullcontext(_stderr) if _stderr is not None else tempfile.TemporaryFile()) as logs:
        process = subprocess.Popen([runtime["python"], "-I", str(worker)], stdin=subprocess.PIPE,
                                   stdout=output, stderr=logs, env=_environment(), start_new_session=True,
                                   cwd=str(worker.parent))
        started = time.monotonic()
        try:
            process.stdin.write(json.dumps(request, allow_nan=False).encode())
            process.stdin.close()
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("DiffusionLight operation cancelled.")
                if time.monotonic() - started > timeout:
                    raise RuntimeError("DiffusionLight worker exceeded its owned operation timeout.")
                if cancel_event is not None:
                    cancel_event.wait(.05)
                else:
                    time.sleep(.05)
            output.seek(0)
            raw = output.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise RuntimeError("DiffusionLight worker response exceeded its bound.")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError("DiffusionLight worker did not return a valid result.") from exc
            if not isinstance(result, dict):
                raise RuntimeError("DiffusionLight worker response must be an object.")
            if process.returncode or result.get("available") is not True:
                raise RuntimeError(result.get("error", "DiffusionLight worker failed."))
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("DiffusionLight operation cancelled after worker completion.")
            return result
        except (OSError, ValueError, RuntimeError) as exc:
            if request.get("command") == "doctor":
                logs.seek(0, os.SEEK_END)
                length = logs.tell()
                logs.seek(max(0, length - 16384))
                tail = logs.read().decode(errors="replace")
                if tail:
                    raise RuntimeError(str(exc) + "\nWorker stderr tail:\n" + tail) from exc
            raise
        finally:
            _stop(process)


def doctor(runtime, cancel_event=None, timeout=1800):
    """Verify local assets and import the pinned runtime; does not execute models."""
    try:
        return _run(runtime, {"command": "doctor"}, cancel_event, timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        return {"available": False, "inference_verified": False, "error": str(exc)}


def infer(runtime, source_image, source_sha256, output_dir, settings=None, cancel_event=None, timeout=21600):
    """Run actual exposure-conditioned inference, spherical projection and HDR merge.

    The caller supplies a new empty owned output directory and retains partial
    outputs on failure. Nothing is added to a project or admitted automatically.
    """
    source_image = _path(source_image)
    if not _sha(source_sha256) or digest(source_image) != source_sha256:
        raise ValueError("DiffusionLight source photograph differs from its admitted SHA256.")
    output_dir = _path(output_dir, True)
    if any(output_dir.iterdir()):
        raise ValueError("DiffusionLight output directory must be newly owned and empty.")
    settings = options(settings)
    _record_state(output_dir, stage="worker_initialization", status="pending")
    with (output_dir / "worker.log").open("xb") as logs:
        try:
            return _run(runtime, {"command": "infer", "source_image": str(source_image),
                                 "source_sha256": source_sha256, "output_dir": str(output_dir),
                                 "settings": settings}, cancel_event, timeout, _stderr=logs)
        except BaseException as exc:
            # The worker may have been terminated during model inference. Keep
            # its last executed false/unknown/true evidence unchanged.
            logs.write(("\nController failure: " + str(exc) + "\n").encode(errors="replace"))
            logs.flush()
            os.fsync(logs.fileno())
            _record_state(output_dir, status="failed", error=str(exc))
            raise

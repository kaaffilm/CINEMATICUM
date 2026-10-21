"""Project-owned still-image processing through an optional isolated runtime.

The editor/server remains standard-library-only. NumPy, OpenColorIO and LibRaw
are imported only by image_worker.py under the explicitly installed interpreter.
Recipes contain identifiers and finite numeric settings, never executable code,
arbitrary config files, network addresses or user-selected output paths.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time


RUNTIME_REQUIREMENTS = {"numpy": "2.3.5", "opencolorio": "2.6.0", "rawpy": "0.27.1", "OpenEXR": "3.4.15"}
DEFAULT_CONFIG = "studio-config-v5.0.0_aces-v2.1_ocio-v2.6"
DEFAULT_DISPLAY = "sRGB - Display"
MAX_RAW_BYTES = 512 * 1024 * 1024
MAX_RAW_SOURCES = 128
MAX_PIXELS = 33_554_432
MAX_SENSOR_PIXELS = 67_108_864
MAX_BRACKETS = 16
RAW_SUFFIXES = frozenset({".3fr", ".arw", ".cr2", ".cr3", ".crw", ".dng", ".erf", ".fff",
                          ".iiq", ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf",
                          ".pef", ".raf", ".raw", ".rw2", ".rwl", ".srw", ".x3f"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".exr"})
ARTIFACT_NAMES = frozenset({"linear.exr", "display.png", "receipt.json"})
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a finite number.")
    try:
        good = math.isfinite(value) and low <= value <= high
    except OverflowError:
        good = False
    if not good:
        raise ValueError("%s must be between %g and %g." % (label, low, high))
    return float(value)


def _text(value, label, length=240):
    if (not isinstance(value, str) or not value or len(value) > length
            or any(ord(c) < 32 for c in value)):
        raise ValueError(label + " must be bounded printable text.")
    return value


def _identity(value, label="Identity", digest=False):
    if not isinstance(value, str) or not (_SHA if digest else _ID).fullmatch(value):
        raise ValueError(label + " is invalid.")
    return value


def _owned(root, relative, is_dir=False, create=False):
    """Reject every symlink component; never normalize a traversal into acceptance."""
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("The imaging project root must be an existing real directory.")
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or any(p in {".", ".."} for p in relative.parts):
        raise ValueError("Imaging paths must be owned by this project.")
    cursor = root
    for index, part in enumerate(relative.parts):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("Imaging paths must not contain symbolic links.")
        directory_component = index < len(relative.parts) - 1 or is_dir
        if directory_component:
            if create:
                cursor.mkdir(exist_ok=True)
            if not cursor.is_dir():
                raise ValueError("An imaging directory is missing or invalid.")
    return cursor


def _hash_file(path, max_size=None):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise ValueError("Imaging media is missing or cannot be opened safely.") from exc
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size < 1 or max_size and before.st_size > max_size:
            raise ValueError("Imaging media must be a nonempty regular file within the size limit.")
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Imaging media changed during verification.")
    return digest.hexdigest(), before.st_size


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _read_json(path, limit=1024 * 1024):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(str(path), flags), "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Imaging metadata is not a regular file.")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Imaging metadata exceeds its size limit.")
    return json.loads(data.decode("utf-8"))


def find_imaging_python(python=None):
    configured = python if python is not None else os.environ.get("CINEMATICUM_IMAGING_PYTHON")
    path = Path(configured).expanduser() if configured else Path.home() / "Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python"
    if not path.is_absolute() or not path.is_file() or not os.access(str(path), os.X_OK):
        return None
    # A venv interpreter is normally a symlink to its base Python executable.
    return str(path)


def _command(python=None):
    executable = find_imaging_python(python)
    if not executable:
        raise ValueError("The isolated imaging runtime is not installed. Install the CINEMATICUM Imaging runtime to use OCIO, RAW development and HDR merging.")
    return [executable, "-I", "-B", str(Path(__file__).with_name("image_worker.py"))]


def _worker_env():
    env = os.environ.copy()
    # Explicit builtin configs are independent of ambient OCIO/Python settings.
    for key in list(env):
        if key.startswith(("OCIO", "PYTHON")):
            env.pop(key, None)
    env["OMP_NUM_THREADS"] = "2"
    env["OPENBLAS_NUM_THREADS"] = "2"
    return env


def _short_request(request, python=None, timeout=18):
    try:
        result = subprocess.run(_command(python), input=_json_bytes(request), capture_output=True,
                                timeout=timeout, env=_worker_env(), check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("The imaging runtime did not answer within its time limit.") from exc
    if len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError("The imaging runtime returned an oversized response.")
    try:
        message = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("The imaging runtime could not start: " + result.stderr.decode("utf-8", errors="replace")[-1400:]) from exc
    if result.returncode or message.get("error"):
        raise ValueError(message.get("error", "The imaging runtime failed."))
    return message


def imaging_capabilities(python=None):
    base = {"available": False, "operations": [], "requirements": RUNTIME_REQUIREMENTS.copy(),
            "source_limit_bytes": MAX_RAW_BYTES, "max_pixels": MAX_PIXELS, "max_brackets": MAX_BRACKETS,
            "raw_extensions": sorted(RAW_SUFFIXES), "delivery": "SDR sRGB PNG; scene-linear float EXR preserved separately"}
    if not find_imaging_python(python):
        return {**base, "reason": "The isolated CINEMATICUM Imaging runtime is not installed."}
    try:
        result = _short_request({"command": "doctor"}, python)
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        result["ffmpeg"] = bool(ffmpeg and ffprobe)
        if not result["ffmpeg"]:
            result.update(available=False, operations=[], reason="FFmpeg and ffprobe are required for imaging output.")
        return {**base, **result}
    except (ValueError, OSError) as exc:
        return {**base, "reason": str(exc)}


def imaging_catalog(config=None, python=None):
    if config is not None:
        _text(config, "OCIO builtin config")
    return _short_request({"command": "catalog", "config": config or DEFAULT_CONFIG}, python)


def probe_exr_source(project_dir, incoming_path, python=None):
    """Read a staged EXR's actual header before ordinary asset admission."""
    root = Path(project_dir).absolute()
    incoming = Path(incoming_path).absolute()
    try:
        relative = incoming.relative_to(root)
    except ValueError as exc:
        raise ValueError("An EXR upload must be staged inside its project.") from exc
    path = _owned(root, relative)
    if path.suffix.lower() != ".exr":
        raise ValueError("Choose an OpenEXR source file.")
    digest, size = _hash_file(path, 1024 * 1024 * 1024)
    return _short_request({"command": "probe_exr", "project_dir": str(root),
                           "input": {"path": str(relative), "sha256": digest, "size": size}}, python)


def validate_imaging_recipe(value):
    if not isinstance(value, dict):
        raise ValueError("An imaging recipe must be an object.")
    recipe = copy.deepcopy(value)
    common = {"version", "operation", "config", "display", "view", "exposure"}
    operation = recipe.get("operation")
    extra = {"ocio": {"asset_id", "input_space"},
             "raw": {"source_id", "demosaic", "half_size", "white_balance", "user_wb", "highlight"},
             "hdr_merge": {"brackets", "input_transfer"}}
    if not isinstance(operation, str) or operation not in extra or set(recipe) - common - extra[operation]:
        raise ValueError("The imaging recipe contains an unsupported operation or property.")
    if recipe.get("version") != 1 or isinstance(recipe.get("version"), bool):
        raise ValueError("Unsupported imaging recipe version.")
    recipe["config"] = _text(recipe.get("config", DEFAULT_CONFIG), "OCIO builtin config")
    # This initial display deliverable is intentionally bounded to monitor sRGB.
    # HDR/P3 displays need a managed viewer/delivery path, not mislabeled PNGs.
    recipe["display"] = recipe.get("display", DEFAULT_DISPLAY)
    if recipe["display"] != DEFAULT_DISPLAY:
        raise ValueError("The current display PNG path requires the sRGB - Display output. Float scene data remains in the EXR.")
    recipe["view"] = _text(recipe.get("view", "ACES 2.0 - SDR 100 nits (Rec.709)"), "OCIO view")
    recipe["exposure"] = _number(recipe.get("exposure", 0), "Exposure stops", -20, 20)
    if operation == "ocio":
        recipe["asset_id"] = _identity(recipe.get("asset_id"), "Source asset")
        recipe["input_space"] = _text(recipe.get("input_space"), "Source color space")
    elif operation == "raw":
        recipe["source_id"] = _identity(recipe.get("source_id"), "RAW source", True)
        choices = {"demosaic": ("AHD", {"AHD", "LINEAR", "VNG", "PPG", "DCB"}),
                   "white_balance": ("camera", {"camera", "auto", "daylight", "custom"}),
                   "highlight": ("clip", {"clip", "blend", "reconstruct"})}
        for key, (default, allowed) in choices.items():
            recipe[key] = recipe.get(key, default)
            if not isinstance(recipe[key], str) or recipe[key] not in allowed:
                raise ValueError("Unsupported RAW " + key.replace("_", " ") + ".")
        recipe["half_size"] = recipe.get("half_size", False)
        if not isinstance(recipe["half_size"], bool):
            raise ValueError("RAW half_size must be true or false.")
        wb = recipe.get("user_wb", [1, 1, 1, 1])
        if not isinstance(wb, list) or len(wb) != 4:
            raise ValueError("Custom RAW white balance requires four R/G/B/G multipliers.")
        recipe["user_wb"] = [_number(v, "RAW white balance multiplier", .01, 32) for v in wb]
    else:
        brackets = recipe.get("brackets")
        if not isinstance(brackets, list) or not 2 <= len(brackets) <= MAX_BRACKETS:
            raise ValueError("HDR merging requires 2–16 aligned still images.")
        ids, times = set(), set()
        for entry in brackets:
            if not isinstance(entry, dict) or set(entry) != {"asset_id", "exposure_time"}:
                raise ValueError("Each HDR bracket needs an asset_id and exposure_time in seconds.")
            ident = _identity(entry["asset_id"], "Bracket asset")
            if ident in ids:
                raise ValueError("HDR bracket assets must be distinct.")
            ids.add(ident)
            entry["exposure_time"] = _number(entry["exposure_time"], "Exposure time in seconds", .000001, 3600)
            times.add(entry["exposure_time"])
        if len(times) < 2:
            raise ValueError("HDR merging requires at least two different exposure times.")
        recipe["input_transfer"] = recipe.get("input_transfer", "srgb")
        if not isinstance(recipe["input_transfer"], str) or recipe["input_transfer"] not in {"srgb", "rec709", "linear"}:
            raise ValueError("HDR input transfer must be srgb, rec709, or linear.")
    return recipe


def _raw_descriptor(project_dir, source_id, verify=True):
    source_id = _identity(source_id, "RAW source", True)
    path = _owned(project_dir, "imaging/sources/" + source_id + ".json")
    try:
        descriptor = _read_json(path)
    except (OSError, ValueError) as exc:
        raise ValueError("The original RAW source descriptor is missing or invalid.") from exc
    expected = "imaging/sources/" + source_id + ".raw"
    if (not isinstance(descriptor, dict) or descriptor.get("id") != source_id or
            descriptor.get("sha256") != source_id or descriptor.get("path") != expected or
            not isinstance(descriptor.get("metadata"), dict)):
        raise ValueError("The RAW source descriptor has been altered.")
    source = _owned(project_dir, expected)
    if verify:
        digest, size = _hash_file(source, MAX_RAW_BYTES)
        if digest != source_id or size != descriptor.get("size"):
            raise ValueError("The preserved RAW source no longer matches its content identity.")
    return descriptor


def list_raw_sources(project_dir):
    root = Path(project_dir)
    if not (root / "imaging").exists():
        return []
    _owned(root, "imaging", is_dir=True)
    if not (root / "imaging/sources").exists():
        return []
    directory = _owned(root, "imaging/sources", is_dir=True)
    paths = sorted(directory.glob("*.json"))
    if len(paths) > MAX_RAW_SOURCES:
        raise ValueError("The project exceeds the 128 RAW source limit.")
    return [_raw_descriptor(root, path.stem) for path in paths]


def import_raw_source(project_dir, incoming_path, original_name, python=None):
    root = Path(project_dir).absolute()
    incoming = Path(incoming_path).absolute()
    try:
        relative = incoming.relative_to(root)
    except ValueError as exc:
        raise ValueError("A RAW upload must be staged inside its project.") from exc
    incoming = _owned(root, relative)
    name = _text(original_name, "RAW filename", 200)
    if Path(name).name != name or "\\" in name or Path(name).suffix.lower() not in RAW_SUFFIXES:
        raise ValueError("Choose a supported camera RAW filename.")
    digest, size = _hash_file(incoming, MAX_RAW_BYTES)
    directory = _owned(root, "imaging/sources", is_dir=True, create=True)
    destination = directory / (digest + ".raw")
    descriptor_path = directory / (digest + ".json")
    if descriptor_path.exists() or descriptor_path.is_symlink():
        return _raw_descriptor(root, digest)
    if len(list(directory.glob("*.json"))) >= MAX_RAW_SOURCES:
        raise ValueError("This project already has 128 preserved RAW sources.")
    metadata = _short_request({"command": "probe_raw", "project_dir": str(root),
                               "input": {"path": str(relative), "sha256": digest, "size": size}}, python)
    descriptor = {"version": 1, "id": digest, "sha256": digest, "size": size, "name": name,
                  "path": "imaging/sources/" + destination.name, "metadata": metadata,
                  "created_at": time.time()}
    temporary = []
    try:
        fd, staging = tempfile.mkstemp(prefix="raw-", dir=str(directory))
        temporary.append(Path(staging))
        with os.fdopen(fd, "wb") as target:
            source_fd = os.open(str(incoming), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(source_fd, "rb") as source:
                shutil.copyfileobj(source, target, 1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        if _hash_file(staging, MAX_RAW_BYTES) != (digest, size):
            raise ValueError("The RAW upload changed while being preserved.")
        try:
            os.link(staging, str(destination))
        except FileExistsError:
            if _hash_file(destination, MAX_RAW_BYTES) != (digest, size):
                raise ValueError("A preserved RAW source has conflicting bytes.")
        fd, staging_json = tempfile.mkstemp(prefix="raw-meta-", dir=str(directory))
        temporary.append(Path(staging_json))
        with os.fdopen(fd, "wb") as target:
            target.write(_json_bytes(descriptor))
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(staging_json, str(descriptor_path))
        except FileExistsError:
            return _raw_descriptor(root, digest)
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return _raw_descriptor(root, digest)


def _asset_input(project, root, ident):
    assets = project.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("The project media inventory is invalid.")
    found = [a for a in assets if isinstance(a, dict) and a.get("id") == ident]
    if len(found) != 1 or found[0].get("kind") != "image":
        raise ValueError("Imaging requires an imported still-image asset.")
    asset = found[0]
    relative = asset.get("path")
    if (not isinstance(relative, str) or not relative.startswith("media/") or
            Path(relative).suffix.lower() not in IMAGE_SUFFIXES):
        raise ValueError("The image is outside the project's admitted media inventory.")
    path = _owned(root, relative)
    expected = _identity(asset.get("sha256"), "Image content identity", True)
    digest, size = _hash_file(path, 1024 * 1024 * 1024)
    if digest != expected or size != asset.get("size"):
        raise ValueError("An input image no longer matches the admitted media identity.")
    return {"asset_id": ident, "path": relative, "sha256": digest, "size": size,
            "name": _text(asset.get("name", ident), "Image name", 240)}


def _stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=3)
    except ProcessLookupError:
        pass


def run_imaging(project, project_dir, recipe, output_dir, progress=None, cancel_event=None, python=None):
    recipe = validate_imaging_recipe(recipe)
    root = Path(project_dir).absolute()
    output = Path(output_dir).absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Imaging outputs must stay inside their project.") from exc
    if len(relative.parts) != 3 or relative.parts[:2] != ("imaging", "outputs"):
        raise ValueError("Use imaging/outputs/<job_id> for imaging output.")
    output_id = _identity(relative.name, "Imaging output identity")
    parent = _owned(root, "imaging/outputs", is_dir=True, create=True)
    if output.exists() or output.is_symlink():
        raise ValueError("An imaging output identity cannot be overwritten.")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Imaging job cancelled.")
    if recipe["operation"] == "raw":
        source = _raw_descriptor(root, recipe["source_id"])
        inputs = [{key: source[key] for key in ("path", "sha256", "size", "name")}]
        inputs[0]["source_id"] = source["id"]
    elif recipe["operation"] == "ocio":
        inputs = [_asset_input(project, root, recipe["asset_id"])]
    else:
        inputs = [_asset_input(project, root, entry["asset_id"]) for entry in recipe["brackets"]]
        if len({entry["sha256"] for entry in inputs}) != len(inputs):
            raise ValueError("HDR brackets cannot repeat identical image content.")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("FFmpeg and ffprobe are required for imaging processing.")
    command = _command(python)
    with tempfile.TemporaryDirectory(prefix=".building-", dir=str(parent)) as scratch_name:
        scratch = Path(scratch_name)
        request = {"command": "render", "project_dir": str(root), "output_dir": str(scratch),
                   "recipe": recipe, "inputs": inputs, "ffmpeg": ffmpeg, "ffprobe": ffprobe}
        log_path = scratch / "worker-result.json"
        error_path = scratch / "worker-stderr.log"
        process = None
        with log_path.open("wb") as log, error_path.open("wb") as error_log:
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=error_log,
                                           env=_worker_env(), start_new_session=True)
                process.stdin.write(_json_bytes(request))
                process.stdin.close()
                started, last_progress = time.monotonic(), -1
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RuntimeError("Imaging job cancelled.")
                    if time.monotonic() - started > 300:
                        raise RuntimeError("The imaging job exceeded its five-minute limit.")
                    if progress:
                        try:
                            value = _read_json(scratch / "progress.json", 256).get("progress", 0)
                            if isinstance(value, (int, float)) and math.isfinite(value) and value > last_progress:
                                progress(min(.98, max(0, value)))
                                last_progress = value
                        except (OSError, ValueError):
                            pass
                    if cancel_event is not None:
                        cancel_event.wait(.1)
                    else:
                        time.sleep(.1)
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Imaging job cancelled.")
            finally:
                if process is not None:
                    _stop_process(process)
        try:
            result = _read_json(log_path, 2 * 1024 * 1024)
        except (OSError, ValueError) as exc:
            detail = error_path.read_text(errors="replace")[-1400:]
            raise RuntimeError("The imaging worker did not return a valid result. " + detail) from exc
        if process.returncode or result.get("error"):
            raise RuntimeError(result.get("error", "The imaging worker failed."))
        generated = scratch / "result"
        if generated.is_symlink() or not generated.is_dir() or {p.name for p in generated.iterdir()} != ARTIFACT_NAMES:
            raise RuntimeError("The imaging worker did not produce the required bounded artifacts.")
        artifacts = {}
        for key, filename in (("display", "display.png"), ("linear", "linear.exr"), ("receipt", "receipt.json")):
            digest, size = _hash_file(generated / filename, 1024 * 1024 * 1024)
            artifacts[key] = {"filename": filename, "sha256": digest, "size": size}
        receipt = _read_json(generated / "receipt.json")
        for key in ("display", "linear"):
            if receipt.get("artifacts", {}).get(key) != artifacts[key]:
                raise RuntimeError("An imaging output does not match its receipt.")
        if receipt.get("recipe") != recipe or receipt.get("inputs") != inputs:
            raise RuntimeError("The imaging receipt does not match the requested source identities and recipe.")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Imaging job cancelled.")
        os.rename(str(generated), str(output))
    if progress:
        progress(1)
    provenance = {"type": "cinematicum-imaging", "version": 1, "operation": recipe["operation"],
                  "output_id": output_id, "receipt_sha256": artifacts["receipt"]["sha256"],
                  "linear_sha256": artifacts["linear"]["sha256"], "display_encoding": "sRGB",
                  "linear_space": receipt["linear_space"], "recipe": recipe}
    return {"path": str(output / "display.png"), "exr_path": str(output / "linear.exr"),
            "receipt_path": str(output / "receipt.json"), "output_id": output_id,
            "artifacts": artifacts, "provenance": provenance, "receipt": receipt}

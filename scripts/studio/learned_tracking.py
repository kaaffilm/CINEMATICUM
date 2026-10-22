"""Owned learned masks/points, exact clip clocks and undoable application plans.

This module is standard-library only. It never substitutes a geometric tracker
for missing SAM2, TAPIR or TAPNext weights. The subprocess receives conformed source
frames and publishes a verified immutable result only after successful work.
"""
from __future__ import annotations

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
import sys
import tempfile
import time
import uuid

MAX_FRAMES = 32
MAX_POINTS = 16
ANALYSIS_EDGE = 512
MAX_SECONDS = 600
ARTIFACT_NAMES = frozenset({"result.json", "receipt.json", "preview.png", "mask.mkv"})
WORKER = Path(__file__).with_name("learned_tracking_worker.py")
LOCK = Path(__file__).with_name("learned-runtime-lock.json")
COORDINATES = "normalized-source-xy-top-left"
HEX = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _number(value, label, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be a finite number between {minimum} and {maximum}")
    if integer and int(value) != value:
        raise ValueError(label + " must be an integer")
    return int(value) if integer else float(value)


def _id(value, label="Identity"):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(label + " must be a bounded alphanumeric identity")
    return value


def _sha(value, label="Digest"):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError(label + " must be a lowercase SHA-256 digest")
    return value


def _bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _motion_digest(value):
    """Hash numerical motion semantics across actual JSON browser transport.

    JSON has one number type: JavaScript writes Python's1.0 and0.0 as1 and0.
    Normalize only exactly integral floats, without rounding or tolerances.
    Booleans remain distinct. Artifact/recipe byte hashes deliberately keep
    using _digest; this normalization applies only to editable motion identity.
    """
    def normalize(item):
        if type(item) is float and item.is_integer():
            return int(item)
        if isinstance(item, list):
            return [normalize(member) for member in item]
        if isinstance(item, dict):
            return {key: normalize(member) for key, member in item.items()}
        return item
    return _digest(normalize(value))


def _legacy_motion_digest(value, restore_correction_floats=True):
    """Recover only the numeric types authored by the original motion schema.

    This lets an existing measured binding migrate after a browser roundtrip.
    Every value and metadata field remains covered by its old exact hash; no
    changed geometry, correction, source timing or boolean is accepted.
    """
    legacy = copy.deepcopy(value)
    def floating(item):
        if type(item) is not int:
            return item
        try:
            converted = float(item)
        except OverflowError:
            return item
        # An arbitrary large integer must never be narrowed to a neighboring
        # IEEE754 value while checking a prior exact fingerprint.
        return converted if math.isfinite(converted) and int(converted) == item else item
    for key in legacy.get("keys", []):
        for name in ("x", "y"):
            if name in key: key[name] = floating(key[name])
    metadata = legacy.get("source", {})
    reference = metadata.get("reference_point")
    if isinstance(reference, list):
        metadata["reference_point"] = [floating(item) for item in reference]
    identity = metadata.get("source")
    if isinstance(identity, dict):
        for name in ("in", "speed"):
            if name in identity: identity[name] = floating(identity[name])
    # The original application preserved user-authored correction number
    # types. Check either unchanged correction types or restored floats;
    # neither candidate can migrate without its exact prior fingerprint.
    corrections = metadata.get("learned_corrections", [])
    if restore_correction_floats:
        for correction in corrections if isinstance(corrections, list) else []:
            if isinstance(correction, dict):
                for name in ("x", "y"):
                    if name in correction: correction[name] = floating(correction[name])
    return _digest(legacy)


def _inference_files(backend):
    if backend == "tapnext":
        return Path(__file__).with_name("tapnext_worker.py"), Path(__file__).with_name("tapnext-runtime-lock.json")
    return WORKER, LOCK


def tapnext_capabilities(python=None):
    from tapnext_runtime import default_destination
    base = {"available": False, "backend": "tapnext", "device": "cpu", "max_frames": MAX_FRAMES,
            "max_queries": MAX_POINTS, "analysis_edge": ANALYSIS_EDGE, "mps_verified": False}
    executable = find_learned_python(python)
    selected = Path(os.environ.get("CINEMATICUM_TAPNEXT_HOME") or default_destination()).expanduser()
    if executable is None or not selected.is_dir():
        return {**base, "reason": "Install the pinned TAPNext overlay through Runtime setup"}
    try:
        worker, _ = _inference_files("tapnext")
        process = subprocess.run([executable, "-I", "-B", str(worker), "--capabilities"],
                                 env=_env(), capture_output=True, text=True, timeout=25)
        if process.returncode or len(process.stdout) > 65536:
            raise ValueError(process.stderr.strip()[-1000:] or "TAPNext did not pass its integrity probe")
        result = json.loads(process.stdout)
        if not result.get("available") or set(result.get("models", {})) != {"tapnext"}:
            raise ValueError("The actual TAPNext checkpoint is unavailable")
        return {**base, **result}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {**base, "reason": str(error)}


def validate_recipe(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Learned tracking requires a version1 recipe")
    backend = value.get("backend")
    if backend not in {"sam2", "tapir", "tapnext"}:
        raise ValueError("Choose actual SAM2 segmentation, TAPIR or TAPNext point inference")
    allowed = {"version", "backend", "frame_start", "frame_count", "prompts" if backend == "sam2" else "points"}
    if set(value) != allowed:
        raise ValueError("Learned tracking contains missing or unsupported recipe fields")
    first = _number(value["frame_start"], "First analysis frame", 0, 1_296_000, True)
    count = _number(value["frame_count"], "Analysis frame count", 1, MAX_FRAMES, True)
    result = {"version": 1, "backend": backend, "frame_start": first, "frame_count": count}
    last = first + count - 1
    if backend in {"tapir", "tapnext"}:
        if not isinstance(value["points"], list) or not 1 <= len(value["points"]) <= MAX_POINTS:
            raise ValueError("Point models accept1–16 explicit point queries")
        points, seen = [], set()
        for point in value["points"]:
            if not isinstance(point, dict) or set(point) != {"id", "frame", "x", "y"}:
                raise ValueError("Point queries require id, frame, x and y")
            ident = _id(point["id"], "Query identity")
            if ident in seen:
                raise ValueError("Point query identities must be unique")
            seen.add(ident)
            points.append({"id": ident, "frame": _number(point["frame"], "Query frame", first, last, True),
                           "x": _number(point["x"], "Query X", 0, 1), "y": _number(point["y"], "Query Y", 0, 1)})
        result["points"] = points
    else:
        if not isinstance(value["prompts"], list) or not 1 <= len(value["prompts"]) <= 16:
            raise ValueError("SAM2 accepts1–16 corrective prompt frames for one object")
        prompts, seen = [], set()
        for prompt in value["prompts"]:
            if not isinstance(prompt, dict) or set(prompt) - {"frame", "points", "box"} or not {"frame", "points"} <= set(prompt):
                raise ValueError("SAM2 prompts require a frame, positive/negative points, and an optional box")
            frame = _number(prompt["frame"], "Prompt frame", first, last, True)
            if frame in seen:
                raise ValueError("Combine all SAM2 corrections on a frame into one prompt")
            seen.add(frame)
            if not isinstance(prompt["points"], list) or len(prompt["points"]) > 32:
                raise ValueError("Each SAM2 prompt supports at most32 points")
            points = []
            for point in prompt["points"]:
                if not isinstance(point, dict) or set(point) != {"x", "y", "label"} or type(point["label"]) is not int or point["label"] not in {0, 1}:
                    raise ValueError("SAM2 points require normalized XY and integer label1 foreground or0 background")
                points.append({"x": _number(point["x"], "Prompt X", 0, 1), "y": _number(point["y"], "Prompt Y", 0, 1), "label": point["label"]})
            clean = {"frame": frame, "points": points}
            if "box" in prompt:
                box = prompt["box"]
                if not isinstance(box, list) or len(box) != 4:
                    raise ValueError("SAM2 box requires normalized left,top,right,bottom")
                box = [_number(v, "Box coordinate", 0, 1) for v in box]
                if not box[0] < box[2] or not box[1] < box[3]:
                    raise ValueError("SAM2 box must have positive width and height")
                clean["box"] = box
            if not points and "box" not in clean:
                raise ValueError("SAM2 prompt needs a real point or box")
            prompts.append(clean)
        prompts.sort(key=lambda item: item["frame"])
        if "box" not in prompts[0] and not any(point["label"] == 1 for point in prompts[0]["points"]):
            raise ValueError("The first SAM2 prompt needs foreground evidence")
        result["prompts"] = prompts
    return result


def _prepare(project, project_dir, clip_id, recipe):
    from engine import validate_project, _media_path
    from tracking import _prepare as prepare
    project = validate_project(project, project_dir)
    clip = next((item for item in project["clips"] if item["id"] == clip_id), None)
    if clip is None or clip["track"] < 0:
        raise ValueError("Select an owned picture clip for learned analysis")
    asset = next(item for item in project["assets"] if item["id"] == clip["asset_id"])
    if asset["kind"] == "image":
        if recipe.get("backend", "sam2") != "sam2":
            raise ValueError("Learned point trajectories require a real video source; use SAM2 for still images")
        first = _number(recipe.get("frame_start", 0), "Still analysis frame", 0, clip["duration"] - 1, True)
        if recipe.get("frame_count", 1) != 1:
            raise ValueError("A still-image SAM2 analysis uses exactly one actual image frame")
        window = copy.deepcopy(clip); window["reverse"] = False
        prepared = [project, clip, asset, _media_path(project_dir, asset["path"]), window, first, 1, asset["width"], asset["height"]]
    else:
        prepared = list(prepare(project, project_dir, clip_id, recipe))
    asset = prepared[2]
    factor = min(1, ANALYSIS_EDGE / max(asset["width"], asset["height"]))
    prepared[7:9] = [max(16, int(asset["width"] * factor / 2) * 2), max(16, int(asset["height"] * factor / 2) * 2)]
    if prepared[5] + prepared[6] > prepared[1]["duration"]:
        raise ValueError("Learned analysis must stay inside the selected conformed clip")
    return prepared


def validate_request(project, project_dir, clip_id, recipe):
    recipe = validate_recipe(recipe)
    prepared = _prepare(project, project_dir, clip_id, recipe)
    if recipe["frame_start"] + recipe["frame_count"] > prepared[1]["duration"]:
        raise ValueError("Learned analysis extends past the conformed clip")
    return recipe


def _stream(asset):
    return {"kind": asset["kind"], "video_stream_index": asset["video_stream_index"], "width": asset["width"], "height": asset["height"],
            "rotation": asset.get("rotation", 0), "exif_orientation": asset.get("exif_orientation", 1)}


def _source(project, clip, asset):
    from tracking import _identity
    result = _identity(project, clip, asset)
    _sha(result.get("sha256"), "Admitted original source hash")
    return result


def _env():
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "OCIO", "PIP_"))}
    environment.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2", TOKENIZERS_PARALLELISM="false")
    return environment


def find_learned_python(python=None):
    value = python or os.environ.get("CINEMATICUM_LEARNED_PYTHON")
    base = Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/share")
    path = Path(value).expanduser() if value else base / "CINEMATICUM/LearnedTracking/torch28-v1/bin/python"
    return str(path) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else None


def learned_capabilities(python=None):
    base = {"available": False, "max_frames": MAX_FRAMES, "max_queries": MAX_POINTS, "analysis_edge": ANALYSIS_EDGE,
            "job_seconds": MAX_SECONDS, "device": "cpu", "mps_verified": False,
            "sam2_scope": "One prompted object, image/video propagation, editable correction prompts; binary alpha, no automatic instance discovery",
            "tapir_scope": "Up to16 actual point trajectories with learned occlusion/uncertainty and explicit manual corrections"}
    executable = find_learned_python(python)
    if executable is None:
        return {**base, "reason": "Install the optional pinned SAM2/TAPIR runtime and model checkpoints"}
    try:
        probe = subprocess.run([executable, "-I", "-B", str(WORKER), "--capabilities"], env=_env(),
                               capture_output=True, text=True, timeout=25)
        if probe.returncode or len(probe.stdout) > 65536:
            raise ValueError(probe.stderr.strip()[-1000:] or "The learned runtime did not pass its integrity probe")
        runtime = json.loads(probe.stdout)
        if not runtime.get("available") or set(runtime.get("models", {})) != {"sam2", "tapir"}:
            raise ValueError("Both real learned checkpoints must be available")
        return {**base, **runtime, "python": executable}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {**base, "reason": str(error)}


def _cancel(event, deadline=None):
    if event is not None and event.is_set():
        raise RuntimeError("Learned tracking cancelled")
    if deadline is not None and time.monotonic() > deadline:
        raise RuntimeError("Learned tracking exceeded its600-second job limit; use a shorter range")


def _run(command, directory, label, event, deadline, output=None, progress=None):
    from imaging import _read_json
    errors = Path(directory) / (label + ".stderr")
    process = None
    with errors.open("wb") as stderr, (Path(output).open("wb") if output else open(os.devnull, "wb")) as stdout:
        try:
            _cancel(event, deadline)
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       env=_env(), start_new_session=True)
            previous = -1
            while process.poll() is None:
                _cancel(event, deadline)
                if errors.stat().st_size > 2 * 1024 * 1024:
                    raise RuntimeError("Learned inference produced excessive diagnostics")
                progress_path = Path(directory) / "progress.json"
                if progress and progress_path.exists():
                    status = _read_json(progress_path, 4096)
                    value = _number(status.get("progress"), "Worker progress", 0, 1)
                    if value > previous:
                        progress(.15 + .7 * value)
                        previous = value
                if event is not None: event.wait(.05)
                else: time.sleep(.05)
            if process.returncode:
                raise RuntimeError("Learned inference failed: " + errors.read_text(errors="replace")[-2000:])
            _cancel(event, deadline)
        finally:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=2)


def _owned(project_dir, relative, directory=False, create=False):
    root = Path(project_dir).absolute()
    relative = Path(relative)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Learned artifacts must remain inside their project")
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if current.is_symlink(): raise ValueError("Learned artifacts cannot traverse symbolic links")
        if create and (index < len(relative.parts) - 1 or directory): current.mkdir(exist_ok=True)
    if current.exists():
        mode = current.stat().st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
            raise ValueError("Learned artifact has an invalid filesystem type")
    elif not create:
        raise FileNotFoundError("The learned artifact does not exist")
    return current


def learned_frame(project, project_dir, clip_id, request, output, cancel_event=None):
    """Decode the exact authored source frame for real prompt placement."""
    from engine import _executable, _video_timing
    from timebase import project_rate
    from imaging import _hash_file
    if not isinstance(request, dict) or set(request) - {"frame_start", "frame_count"} or request.get("frame_count", 1) != 1:
        raise ValueError("Learned seed preview accepts one selected conformed frame")
    prepared = _prepare(project, project_dir, clip_id, {**request, "frame_count": 1})
    project, clip, asset, source, window, first, _, width, height = prepared
    identity = _source(project, clip, asset)
    if _hash_file(source)[0] != identity["sha256"]: raise ValueError("The admitted source changed before prompt placement")
    rate = project_rate(project); begin = clip["duration"] - first - 1 if clip["reverse"] else first
    chain = _video_timing(window, rate) + [f"trim=start_frame={begin}:end_frame={begin+1}", f"scale={width}:{height}:flags=area", "format=rgb24"]
    output = Path(output)
    try: relative = output.absolute().relative_to(Path(project_dir).absolute())
    except ValueError as error: raise ValueError("Learned seed preview must be project-owned") from error
    if relative.parts[0] != "analysis" or len(relative.parts) != 2 or not re.fullmatch(r"[a-f0-9]{32}\.png", relative.name):
        raise ValueError("Learned seed preview needs its owned analysis job identity")
    _owned(project_dir, relative.parent, directory=True, create=True)
    if output.exists() or output.is_symlink(): raise ValueError("Learned previews cannot overwrite another job")
    with tempfile.TemporaryDirectory(prefix=f".learned-seed-{output.stem}-", dir=str(output.parent)) as temporary:
        work = Path(temporary); target = work / "frame.png"
        inputs = ["-loop", "1", "-framerate", rate.ffmpeg] if asset["kind"] == "image" else []
        _run([_executable("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", "1", "-protocol_whitelist", "file,pipe", *inputs,
              "-i", str(source), "-map", f"0:{asset['video_stream_index']}", "-vf", ",".join(chain), "-frames:v", "1", "-an", "-threads", "1", str(target)],
              work, "seed", cancel_event, time.monotonic()+30)
        if _hash_file(source)[0] != identity["sha256"]: raise ValueError("The source changed during prompt placement")
        digest, size = _hash_file(target, 16*1024*1024)
        _cancel(cancel_event); os.rename(target, output)
    return {"width": width, "height": height, "frame_start": first, "frame_count": 1,
            "source": identity, "source_stream": _stream(asset), "sha256": digest, "size": size}


def run_learned_tracking(project, project_dir, clip_id, recipe, output_dir, progress=None, cancel_event=None, python=None):
    from engine import _executable
    from engine import _video_timing
    from imaging import _hash_file, _read_json
    from timebase import project_rate
    from tracking import validate_track
    recipe = validate_request(project, project_dir, clip_id, recipe)
    prepared = _prepare(project, project_dir, clip_id, recipe)
    project, clip, asset, source, window, first, count, width, height = prepared
    identity, stream = _source(project, clip, asset), _stream(asset)
    root, output = Path(project_dir).absolute(), Path(output_dir).absolute()
    try: relative = output.relative_to(root)
    except ValueError as error: raise ValueError("Learned output must be project-owned") from error
    if len(relative.parts) != 3 or relative.parts[:2] != ("learned", "outputs") or not re.fullmatch(r"[a-f0-9]{32}", relative.name):
        raise ValueError("Learned output needs its exact owned job identity")
    _owned(root, relative.parent, directory=True, create=True)
    if output.exists() or output.is_symlink(): raise ValueError("Learned results cannot overwrite an existing output")
    deadline = time.monotonic() + MAX_SECONDS
    _cancel(cancel_event, deadline)
    if _hash_file(source)[0] != identity["sha256"]:
        raise ValueError("The original source changed after admission; import it again")
    executable = find_learned_python(python)
    if executable is None: raise ValueError("Install the pinned SAM2/TAPIR runtime before inference")
    if progress: progress(.02)
    with tempfile.TemporaryDirectory(prefix=f".learned-work-{relative.name}-", dir=str(output.parent)) as temporary:
        work = Path(temporary)
        begin = clip["duration"] - first - count if clip["reverse"] else first
        chain = _video_timing(window, project_rate(project)) + [f"trim=start_frame={begin}:end_frame={begin+count}",
                 f"scale={width}:{height}:flags=area", "format=rgb24"]
        if clip["reverse"]: chain.append("reverse")
        chain.append("setpts=PTS-STARTPTS")
        raw = work / "frames.rgb"
        image_input = ["-loop", "1", "-framerate", project_rate(project).ffmpeg] if asset["kind"] == "image" else []
        _run([_executable("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-threads", "1",
              "-protocol_whitelist", "file,pipe", *image_input, "-i", str(source), "-map", f"0:{asset['video_stream_index']}",
              "-vf", ",".join(chain), "-frames:v", str(count), "-an", "-threads", "1", "-pix_fmt", "rgb24",
              "-f", "rawvideo", "pipe:1"], work, "decode", cancel_event, deadline, raw)
        if raw.stat().st_size != width * height * count * 3:
            raise ValueError("Not every requested learned-analysis frame exists")
        if progress: progress(.12)
        request = {"recipe": recipe, "frames": str(raw), "width": width, "height": height, "directory": str(work)}
        manifest = work / "request.json"; manifest.write_bytes(_bytes(request))
        _run([executable, "-I", "-B", str(_inference_files(recipe["backend"])[0]), "--request", str(manifest)], work, "inference", cancel_event, deadline, progress=progress)
        measured = _read_json(work / "worker-result.json", 2 * 1024 * 1024)
        if measured.get("backend") != recipe["backend"] or measured.get("frame_count") != count or measured.get("width") != width or measured.get("height") != height:
            raise ValueError("Learned inference result does not match its frozen request")
        lock = _read_json(_inference_files(recipe["backend"])[1], 256 * 1024)
        if measured.get("checkpoint_sha256") != lock["models"][recipe["backend"]]["sha256"]:
            raise ValueError("Learned inference did not use the selected official checkpoint")
        tracks = []
        if recipe["backend"] in {"tapir", "tapnext"}:
            if not isinstance(measured.get("tracks"), list) or len(measured["tracks"]) != len(recipe["points"]):
                raise ValueError("TAPIR omitted one of its explicit queries")
            for item, query in zip(measured["tracks"], recipe["points"]):
                track = validate_track({"version": 1, "kind": "point-track", "backend": "tapnext-pytorch-bootstrapped" if recipe["backend"] == "tapnext" else "tapir-pytorch-panning",
                    "coordinates": COORDINATES, "source": identity, "reference_frame": item["reference_frame"],
                    "samples": item["samples"]}, identity)
                if item["id"] != query["id"] or len(track["samples"]) != count or track["samples"][0]["frame"] != first or track["reference_frame"] != query["frame"]:
                    raise ValueError("TAPIR returned a different point or frame range")
                tracks.append({"id": item["id"], "track": track})
            measured["tracks"] = tracks
        else:
            frames = measured.get("mask_frames")
            if not isinstance(frames, list) or len(frames) != count or [item.get("frame") for item in frames] != list(range(first, first + count)):
                raise ValueError("SAM2 did not produce every requested mask")
            matte = work / "mask.rgba64le"
            if matte.stat().st_size != width * height * count * 8:
                raise ValueError("SAM2 mask bytes do not match the conformed frame range")
        published = work / "published"; published.mkdir()
        shutil.copyfile(work / "preview.png", published / "preview.png")
        if recipe["backend"] == "sam2":
            _run([_executable("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", "1",
                  "-f", "rawvideo", "-pix_fmt", "rgba64le", "-s", f"{width}x{height}", "-r", project_rate(project).ffmpeg,
                  "-i", str(work / "mask.rgba64le"), "-an", "-frames:v", str(count), "-c:v", "ffv1", "-level", "3",
                  "-pix_fmt", "gbrap16le", "-threads", "1", "-color_primaries", "bt709", "-color_trc", "iec61966-2-1",
                  "-colorspace", "rgb", "-color_range", "pc", str(published / "mask.mkv")], work, "encode-mask", cancel_event, deadline)
        if _hash_file(source)[0] != identity["sha256"]:
            raise ValueError("The original source changed during learned inference")
        result = {"version": 1, "kind": "learned-tracking", "output_id": relative.name, "recipe": recipe,
                  "source": identity, "source_stream": stream, "coordinates": COORDINATES, "measurement": measured}
        if recipe["backend"] == "sam2": result["mask_sha256"] = _hash_file(published / "mask.mkv")[0]
        (published / "result.json").write_bytes(_bytes(result))
        artifacts = []
        for path in sorted(published.iterdir()):
            digest, size = _hash_file(path, 256 * 1024 * 1024)
            artifacts.append({"filename": path.name, "sha256": digest, "size": size})
        receipt = {"version": 1, "type": "cinematicum-learned-tracking", "output_id": relative.name,
                   "backend": recipe["backend"], "source": identity, "source_stream": stream,
                   "recipe": recipe, "recipe_sha256": _digest(recipe), "result_sha256": _digest(result),
                   "checkpoint_sha256": measured["checkpoint_sha256"], "runtime": measured["runtime"],
                   "artifacts": artifacts, "semantics": "Original source is unchanged; binary SAM alpha or checkpoint-backed learned points with explicit visibility"}
        (published / "receipt.json").write_bytes(_bytes(receipt))
        _cancel(cancel_event, deadline)
        os.rename(published, output)
    if progress: progress(1)
    provenance = {"type": "cinematicum-learned-mask" if recipe["backend"] == "sam2" else "cinematicum-learned-points",
                  "version": 1, "output_id": relative.name, "recipe_sha256": _digest(recipe), "result_sha256": _digest(result),
                  "checkpoint_sha256": measured["checkpoint_sha256"], "source_sha256": identity["sha256"], "display_encoding": "sRGB"}
    response = {"output_id": relative.name, "backend": recipe["backend"], "measurement": result,
                "path": str(relative / "preview.png"), "receipt_path": str(relative / "receipt.json"),
                "result_path": str(relative / "result.json"), "artifacts": artifacts, "provenance": provenance}
    if recipe["backend"] == "sam2": response["mask_path"] = str(relative / "mask.mkv")
    return response


def _validate_result(result, project, clip, asset):
    if not isinstance(result, dict) or result.get("version") != 1 or result.get("kind") != "learned-tracking" or result.get("coordinates") != COORDINATES:
        raise ValueError("Expected an owned learned-tracking result")
    if result.get("source") != _source(project, clip, asset) or result.get("source_stream") != _stream(asset):
        raise ValueError("The learned result belongs to different source bytes, stream or clip timing")
    recipe = validate_recipe(result.get("recipe"))
    if result.get("measurement", {}).get("backend") != recipe["backend"]:
        raise ValueError("The learned result backend does not match its frozen recipe")
    from imaging import _read_json
    lock = _read_json(_inference_files(recipe["backend"])[1], 256 * 1024)
    if result["measurement"].get("checkpoint_sha256") != lock["models"][recipe["backend"]]["sha256"]:
        raise ValueError("The learned result lacks its exact official checkpoint identity")
    return recipe


def _binding(result, target):
    return {"version": 1, "backend": result["recipe"]["backend"], "source": copy.deepcopy(result["source"]),
            "source_stream": copy.deepcopy(result["source_stream"]), "recipe_sha256": _digest(result["recipe"]),
            "result_sha256": _digest(result), "checkpoint_sha256": result["measurement"]["checkpoint_sha256"],
            "frame_start": result["recipe"]["frame_start"], "frame_count": result["recipe"]["frame_count"],
            "target": target}


def mask_application(project, project_dir, clip_id, result, mask_asset, invert=False, hold_still=False):
    from compositor import validate_graph
    prepared = _prepare(project, project_dir, clip_id, {"frame_start": 0, "frame_count": 1})
    project, clip, asset = prepared[:3]
    recipe = _validate_result(result, project, clip, asset)
    if recipe["backend"] != "sam2" or type(invert) is not bool or type(hold_still) is not bool:
        raise ValueError("A SAM2 foreground cutout requires its actual mask asset and boolean inversion")
    if hold_still and (asset["kind"] != "image" or recipe["frame_count"] != 1):
        raise ValueError("Only a measured single still image can explicitly hold its mask across the still clip")
    if (not isinstance(mask_asset, dict) or mask_asset.get("kind") != "video"
            or mask_asset.get("pixel_format") not in {"bgra", "rgba", "gbrap", "gbrap16le"}
            or mask_asset.get("sha256") != result.get("mask_sha256")):
        raise ValueError("The admitted SAM2 mask must retain its video alpha channel")
    provenance = mask_asset.get("provenance", {})
    if provenance.get("type") != "cinematicum-learned-mask" or provenance.get("result_sha256") != _digest(result):
        raise ValueError("The selected mask asset does not belong to this learned result")
    graph = copy.deepcopy(clip.get("compositor") or {"version": 1, "nodes": [{"id": "source", "type": "source", "inputs": [], "params": {}}], "output": "source"})
    suffix = uuid.uuid4().hex[:12]
    matte_id, cutout_id = "sam_matte_" + suffix, "sam_cutout_" + suffix
    graph["nodes"].extend([
        {"id": matte_id, "type": "media_source", "inputs": [], "params": {"asset_id": mask_asset["id"], "source_in": 0,
         "duration": recipe["frame_count"], "offset": recipe["frame_start"] + clip.get("animation_offset", 0), "outside": "hold" if hold_still else "transparent"}},
        {"id": cutout_id, "type": "alpha_mask", "inputs": [graph["output"], matte_id], "params": {"invert": invert}},
    ])
    graph["output"] = cutout_id
    graph = validate_graph(graph, animation_start=clip.get("animation_start", 0), animation_duration=clip.get("animation_duration", clip["duration"]))
    binding = _binding(result, {"kind": "alpha-mask", "node_id": cutout_id, "mask_node_id": matte_id,
                               "asset_id": mask_asset["id"], "asset_sha256": _sha(mask_asset.get("sha256")), "hold_still": hold_still})
    return {"compositor": graph, "binding": binding}


def point_application(project, project_dir, clip_id, result, point_id, corrections=None, frame_start=None, frame_count=None):
    from tracking import stabilization_motion, validate_track
    prepared = _prepare(project, project_dir, clip_id, {"frame_start": 0, "frame_count": 1})
    project, clip, asset = prepared[:3]
    recipe = _validate_result(result, project, clip, asset)
    if recipe["backend"] not in {"tapir", "tapnext"}: raise ValueError("Point stabilization requires an actual learned point result")
    item = next((item for item in result["measurement"]["tracks"] if item["id"] == point_id), None)
    if item is None: raise ValueError("Choose one of the measured point identities")
    track = copy.deepcopy(item["track"])
    corrections = [] if corrections is None else corrections
    if not isinstance(corrections, list) or len(corrections) > recipe["frame_count"]:
        raise ValueError("Point corrections must be a bounded explicit sample list")
    seen = set()
    for correction in corrections:
        if not isinstance(correction, dict) or set(correction) != {"frame", "x", "y"}:
            raise ValueError("A manual point correction needs frame, x and y")
        frame = _number(correction["frame"], "Corrected frame", recipe["frame_start"], recipe["frame_start"] + recipe["frame_count"] - 1, True)
        if frame in seen: raise ValueError("Correct each trajectory frame at most once")
        seen.add(frame)
        sample = track["samples"][frame - recipe["frame_start"]]
        sample.update(x=_number(correction["x"], "Corrected X", 0, 1), y=_number(correction["y"], "Corrected Y", 0, 1), visible=True)
        # Preserve learned confidence; manual correction is recorded separately.
    first = recipe["frame_start"] if frame_start is None else _number(frame_start, "Applied first frame", recipe["frame_start"], recipe["frame_start"] + recipe["frame_count"] - 1, True)
    count = recipe["frame_count"] - (first - recipe["frame_start"]) if frame_count is None else _number(frame_count, "Applied frame count", 1, recipe["frame_count"], True)
    if first + count > recipe["frame_start"] + recipe["frame_count"]: raise ValueError("Applied tracking range exceeds the measured samples")
    track["samples"] = [sample for sample in track["samples"] if first <= sample["frame"] < first + count]
    if not first <= track["reference_frame"] < first + count: track["reference_frame"] = first
    track = validate_track(track, result["source"])
    motion = stabilization_motion(project, project_dir, clip_id, track)
    motion["source"]["learned_corrections"] = copy.deepcopy(corrections)
    motion["source"]["learned_result_sha256"] = _digest(result)
    binding = _binding(result, {"kind": "tracking-motion", "motion_sha256": _motion_digest(motion), "point_id": _id(point_id)})
    return {"tracking": motion, "binding": binding, "track": track}


def validate_learned_bindings(value, project, clip, assets):
    """Preserve stale editable bindings while deterministically marking them.

    Call after the clip/graph/assets are normalized. Undo restores acceptance
    by restoring matching source/timing/target bytes, not by trusting a flag.
    """
    if value is None: return []
    if not isinstance(value, list) or len(value) > 16:
        raise ValueError("A clip supports at most16 learned result bindings")
    records, targets = [], set()
    assets = assets if isinstance(assets, dict) else {item["id"]: item for item in assets}
    for raw in value:
        fields = {"version", "backend", "source", "source_stream", "recipe_sha256", "result_sha256", "checkpoint_sha256", "frame_start", "frame_count", "target"}
        if not isinstance(raw, dict) or not fields <= set(raw) or set(raw) - fields - {"invalidated"} or type(raw["version"]) is not int or raw["version"] != 1 or raw["backend"] not in {"sam2", "tapir", "tapnext"}:
            raise ValueError("Invalid learned result binding")
        clean = {key: copy.deepcopy(raw[key]) for key in fields}
        for key in ("recipe_sha256", "result_sha256", "checkpoint_sha256"): _sha(clean[key], key)
        _number(clean["frame_start"], "Measured first frame", 0, 1_296_000, True)
        _number(clean["frame_count"], "Measured frame count", 1, MAX_FRAMES, True)
        if not isinstance(clean["source"], dict) or not isinstance(clean["source_stream"], dict) or not isinstance(clean["target"], dict) or len(_bytes(clean)) > 16384:
            raise ValueError("Learned binding source/target metadata is invalid")
        _sha(clean["source"].get("sha256"), "Measured original hash")
        target = clean["target"]
        reason = None
        asset = assets.get(clip.get("asset_id"))
        if asset is None or asset.get("kind") not in {"video", "image"} or clean["source"] != _source(project, clip, asset) or clean["source_stream"] != _stream(asset):
            reason = "Measured source, selected stream or clip timing changed; remeasure or remove the learned application"
        if target.get("kind") == "alpha-mask" and clean["backend"] == "sam2":
            if set(target) != {"kind", "node_id", "mask_node_id", "asset_id", "asset_sha256", "hold_still"} or type(target["hold_still"]) is not bool:
                raise ValueError("Learned mask binding has unsupported target fields")
            for key in ("node_id", "mask_node_id", "asset_id"): _id(target[key])
            _sha(target["asset_sha256"])
            graph = clip.get("compositor", {})
            nodes = {node["id"]: node for node in graph.get("nodes", [])}
            cutout, matte = nodes.get(target["node_id"]), nodes.get(target["mask_node_id"])
            key = target["node_id"]
            if cutout is None and matte is None:
                continue  # deleting the applied graph removes its obsolete binding
            mask = assets.get(target["asset_id"], {})
            expected = {"asset_id": target["asset_id"], "source_in": 0, "duration": clean["frame_count"],
                        "offset": clean["frame_start"] + clean["source"].get("animation_offset", 0), "outside": "hold" if target["hold_still"] else "transparent"}
            if target["hold_still"] and (clean["source_stream"].get("kind") != "image" or clean["frame_count"] != 1):
                raise ValueError("Only an actual single-image measurement can use still-mask hold")
            if (not cutout or cutout.get("type") != "alpha_mask" or cutout.get("inputs", [None, None])[1] != target["mask_node_id"]
                    or not matte or matte.get("type") != "media_source" or matte.get("params") != expected
                    or mask.get("sha256") != target["asset_sha256"]):
                reason = "The applied learned matte, its frame placement or its immutable media changed"
        elif target.get("kind") == "tracking-motion" and clean["backend"] in {"tapir", "tapnext"}:
            if set(target) != {"kind", "motion_sha256", "point_id"}:
                raise ValueError("Learned point binding has unsupported target fields")
            _sha(target["motion_sha256"]); _id(target["point_id"])
            key = "tracking-motion"
            if "tracking" not in clip: continue
            canonical = _motion_digest(clip["tracking"])
            if canonical != target["motion_sha256"]:
                if target["motion_sha256"] in {_digest(clip["tracking"]), _legacy_motion_digest(clip["tracking"]),
                                                _legacy_motion_digest(clip["tracking"], False)}:
                    # Upgrade an unchanged prior binding once. The exact old
                    # fingerprint must match before numerical normalization.
                    target["motion_sha256"] = canonical
                else:
                    reason = "The applied learned motion changed outside its explicit correction workflow"
        else:
            raise ValueError("Learned binding backend and target do not match")
        if key in targets: raise ValueError("Each applied target has one learned source binding")
        targets.add(key)
        if reason: clean["invalidated"] = reason
        records.append(clean)
    return records


def assert_learned_export_ready(project):
    stale = []
    for sequence in [project] + project.get("sequences", []):
        for clip in sequence.get("clips", []):
            for binding in clip.get("learned_bindings", []):
                if binding.get("invalidated"):
                    stale.append(clip["id"])
    if stale:
        raise ValueError("Learned masks or tracks are stale on " + ", ".join(dict.fromkeys(stale)) + ". Remeasure or remove them before rendering.")


def verify_learned_source_files(project, project_dir, cancel_event=None):
    from engine import _media_path
    from imaging import _hash_file
    assets = {item["id"]: item for item in project.get("assets", [])}
    checked = set()
    for sequence in [project] + project.get("sequences", []):
        for clip in sequence.get("clips", []):
            for binding in clip.get("learned_bindings", []):
                if binding.get("invalidated"): continue
                identities = [(binding["source"]["asset_id"], binding["source"]["sha256"])]
                if binding["target"]["kind"] == "alpha-mask": identities.append((binding["target"]["asset_id"], binding["target"]["asset_sha256"]))
                for ident, digest in identities:
                    _cancel(cancel_event)
                    if (ident, digest) in checked: continue
                    asset = assets.get(ident)
                    if not asset or _hash_file(_media_path(project_dir, asset["path"]))[0] != digest:
                        raise ValueError("An original or applied learned matte changed after measurement; reimport and remeasure")
                    checked.add((ident, digest))


capabilities = learned_capabilities
run = run_learned_tracking

"""Pinned official CameraCtrl/AnimateDiffV3 inference for calibrated 16-frame shots.

The actual model runs only in an operator-provisioned isolated CUDA environment.
Input poses, checkpoint hashes and outputs are preserved as immutable evidence.
This wrapper does not assert that rendered pixels meet pose-following tolerances.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from adapters import _terminate_owned
from reconstruction import _cancel, _hash_file, _number, _owned

ARTIFACT_NAMES = frozenset({"trajectory.txt", "conditioning.json", "video.mp4", "provenance.json"})
MAX_ARTIFACT_BYTES = 3 * 1024 ** 3
MAX_SECONDS = 7200
FRAMES, WIDTH, HEIGHT, FPS = 16, 384, 256, 8
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[a-f0-9]{32}\Z")


def _encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _vector(value, n):
    if not isinstance(value, list) or len(value) != n:
        raise ValueError("CameraCtrl camera values must have fixed finite dimensions.")
    return [_number(v, "Camera coordinate", -10000, 10000) for v in value]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _pose(value):
    if not isinstance(value, dict) or set(value) != {"intrinsics", "w2c"}:
        raise ValueError("CameraCtrl requires normalized camera intrinsics and 3x4 world-to-camera pose.")
    intrinsics = _vector(value["intrinsics"], 4)
    if any(not .001 < v <= 5 for v in intrinsics[:2]) or any(not -1 <= v <= 2 for v in intrinsics[2:]):
        raise ValueError("CameraCtrl intrinsics must be normalized and have positive focal lengths.")
    if not isinstance(value["w2c"], list) or len(value["w2c"]) != 3:
        raise ValueError("CameraCtrl requires a 3x4 pose.")
    matrix = [_vector(row, 4) for row in value["w2c"]]
    axes = [row[:3] for row in matrix]
    if (any(abs(_dot(axis, axis)-1)>1e-3 for axis in axes)
        or any(abs(_dot(axes[i], axes[j]))>1e-3 for i in range(3) for j in range(i))):
        raise ValueError("CameraCtrl pose rotation must have orthonormal axes.")
    if _dot(axes[0], _cross(axes[1], axes[2])) < .999:
        raise ValueError("CameraCtrl pose rotation must be right-handed.")
    return {"intrinsics": intrinsics, "w2c": matrix}


def default_settings():
    return {"version": 1, "prompt": "", "seed": 42, "poses": [],
            "fps": FPS, "width": WIDTH, "height": HEIGHT}


def validate_settings(value):
    defaults = default_settings()
    if (not isinstance(value, dict) or set(value)-set(defaults)
        or type(value.get("version")) is not int or value["version"] != 1):
        raise ValueError("Unsupported CameraCtrl recipe schema.")
    settings = {**defaults, **value}
    prompt = settings["prompt"]
    if (not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 300
            or any(ord(c) < 32 for c in prompt)):
        raise ValueError("CameraCtrl requires a bounded nonempty text prompt.")
    settings["seed"] = _number(settings["seed"], "Seed", 0, 2147483647, True)
    if (settings["fps"], settings["width"], settings["height"]) != (FPS, WIDTH, HEIGHT):
        raise ValueError("CameraCtrl is pinned to the official 384x256/8fps profile.")
    if not isinstance(settings["poses"], list) or len(settings["poses"]) != FRAMES:
        raise ValueError("CameraCtrl requires exactly 16 per-frame camera poses.")
    settings["poses"] = [_pose(v) for v in settings["poses"]]
    if any(x["intrinsics"] != settings["poses"][0]["intrinsics"] for x in settings["poses"]):
        raise ValueError("This camera model requires constant intrinsics.")
    return settings


def validate_recipe(recipe, project):
    if (not isinstance(recipe, dict) or set(recipe) != {"operation", "settings"}
            or recipe["operation"] != "camera-conditioned-inference"):
        raise ValueError("Only actual CameraCtrl inference recipes are accepted.")
    return {"operation": "camera-conditioned-inference", "settings": validate_settings(recipe["settings"])}


def _source_member(root, member, digest, maximum):
    if (not isinstance(member, str) or not member or Path(member).is_absolute()
            or ".." in Path(member).parts or not isinstance(digest, str) or not _SHA.fullmatch(digest)):
        raise RuntimeError("CameraCtrl source manifest includes an unsafe path or hash.")
    path = root/member
    if path.is_symlink() or not path.is_file() or _hash_file(path, maximum)[0] != digest:
        raise RuntimeError("CameraCtrl source member differs from its approved digest.")
    return path


def _weight(value, maximum=12 * 1024 ** 3):
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise RuntimeError("CameraCtrl weight descriptor is invalid.")
    path = Path(value["path"])
    if (not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents))
            or not _SHA.fullmatch(value["sha256"])):
        raise RuntimeError("CameraCtrl checkpoint must be an absolute hash-pinned file.")
    if _hash_file(path, maximum)[0] != value["sha256"]:
        raise RuntimeError("CameraCtrl weight differs from its approved SHA-256.")
    return str(path)


def _runtime():
    pointer = os.environ.get("CINEMATICUM_CAMERACTRL_LOCK")
    expected = os.environ.get("CINEMATICUM_CAMERACTRL_LOCK_SHA256")
    if not pointer or not expected or not _SHA.fullmatch(expected):
        raise RuntimeError("CameraCtrl needs an operator-approved runtime manifest and SHA-256.")
    target = Path(pointer)
    if not target.is_absolute() or any(part.is_symlink() for part in (target, *target.parents)):
        raise RuntimeError("CameraCtrl runtime manifest must be a trusted absolute file.")
    if _hash_file(target, 2 * 1024 ** 2)[0] != expected:
        raise RuntimeError("CameraCtrl manifest differs from its approved digest.")
    data = json.loads(target.read_text())
    names = {"schema", "python", "root", "source_files", "sd_model_root",
             "sd_files", "unet_subfolder", "motion", "pose", "config"}
    if not isinstance(data, dict) or set(data) != names or data["schema"] != "cinematicum-cameractrl-runtime-v1":
        raise RuntimeError("CameraCtrl runtime manifest is malformed.")
    source = Path(data["root"])
    sdroot = Path(data["sd_model_root"])
    interpreter = Path(data["python"])
    if (not source.is_absolute() or not source.is_dir() or source.is_symlink()
        or not sdroot.is_absolute() or not sdroot.is_dir()
        or not interpreter.is_absolute() or not interpreter.is_file()
        or not os.access(interpreter, os.X_OK)):
        raise RuntimeError("CameraCtrl requires an installed source, model and Python runtime.")
    for root, mapping in ((source, data["source_files"]), (sdroot, data["sd_files"])):
        if not isinstance(mapping, dict) or not mapping:
            raise RuntimeError("CameraCtrl runtime manifest lacks source or SD model identities.")
        for member, digest in mapping.items():
            _source_member(root, member, digest, 12 * 1024 ** 3)
    if "inference.py" not in data["source_files"]:
        raise RuntimeError("CameraCtrl official inference source must be hash-bound.")
    if not isinstance(data["unet_subfolder"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", data["unet_subfolder"]):
        raise RuntimeError("CameraCtrl UNet choice is invalid.")
    bindings = {key: _weight(data[key]) for key in ("motion", "pose", "config")}
    return data, expected, bindings


def capabilities():
    result = {"available": False, "operations": [], "inference_accepted": False,
              "reason": "The optional CameraCtrl CUDA/weight runtime is unavailable.",
              "conditioning": "Calibrated 3x4 W2C frames with original Pluecker ray sampling",
              "limits": {"frames": FRAMES, "width": WIDTH, "height": HEIGHT, "fps": FPS}}
    try:
        _, digest, _ = _runtime()
        result.update(available=True, operations=["camera-conditioned-inference"],
                      runtime_lock_sha256=digest,
                      reason="Pinned runtime available; actual video and camera-motion acceptance remain unproven.")
    except (RuntimeError, ValueError, OSError) as exc:
        result["reason"] = str(exc)
    return result


def _center_rays(poses):
    """Independent center-pixel sanity oracle for the official relative Pluecker encoding."""
    origin = poses[0]["w2c"]
    result = []
    for pose in poses:
        mat = pose["w2c"]
        Rt = [[mat[j][i] for j in range(3)] for i in range(3)]
        t = [mat[j][3] for j in range(3)]
        center = [-_dot(v, t) for v in Rt]
        axis = [_dot(v, [0, 0, 1]) for v in Rt]
        relative_center = [_dot(origin[i][:3], center)+origin[i][3] for i in range(3)]
        relative_direction = [_dot(origin[i][:3], axis) for i in range(3)]
        result.append([*_cross(relative_center, relative_direction), *relative_direction])
    return result


def _execute(runtime, bindings, trajectory, prompts, destination, event):
    directory = Path(runtime["root"])
    command = [
        runtime["python"], "inference.py", "--ori_model_path", runtime["sd_model_root"],
        "--unet_subfolder", runtime["unet_subfolder"], "--motion_module_ckpt", bindings["motion"],
        "--pose_adaptor_ckpt", bindings["pose"], "--model_config", bindings["config"],
        "--visualization_captions", str(prompts), "--use_specific_seeds",
        "--trajectory_file", str(trajectory), "--n_procs", "1", "--local_rank", "0",
        "--out_root", str(destination), "--video_length", str(FRAMES),
        "--image_width", str(WIDTH), "--image_height", str(HEIGHT)
    ]
    env = {k:v for k,v in os.environ.items()
           if not k.startswith(("PYTHON", "HF_", "TRANSFORMERS_", "TORCH_"))}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
    with (destination.parent/"inference.log").open("wb") as logfile:
        proc = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                                stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        try:
            while proc.poll() is None:
                _cancel(event)
                if time.monotonic()-started > MAX_SECONDS:
                    raise TimeoutError("CameraCtrl inference exceeded its owned execution budget.")
                if (destination.parent/"inference.log").stat().st_size > 8*1024**2:
                    raise RuntimeError("CameraCtrl diagnostics exceeded their byte limit.")
                event.wait(.1) if event is not None else time.sleep(.1)
            _cancel(event)
            if proc.returncode:
                raise RuntimeError("Actual CameraCtrl CUDA inference did not complete.")
        finally:
            _terminate_owned(proc)
    videos = list(destination.glob("*.mp4"))
    if len(videos) != 1 or not videos[0].is_file():
        raise RuntimeError("CameraCtrl inference did not produce exactly one media output.")
    return videos[0]


def _probe(movie):
    report = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-count_frames", "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate",
         "-of", "json", str(movie)], timeout=120, check=True, capture_output=True)
    if len(report.stdout) > 65536:
        raise ValueError("CameraCtrl media probe exceeded the accepted response size.")
    streams = json.loads(report.stdout)["streams"]
    if len(streams) != 1 or (streams[0].get("width"), streams[0].get("height")) != (WIDTH, HEIGHT):
        raise ValueError("CameraCtrl inference returned an unexpected image geometry.")
    if int(streams[0].get("nb_read_frames") or -1) != FRAMES:
        raise ValueError("CameraCtrl inference returned incorrect decoded frame count.")
    return {"decoded_frames": FRAMES, "width": WIDTH, "height": HEIGHT,
            "frame_rate": streams[0].get("r_frame_rate")}


def run(project, project_dir, recipe, output_dir, progress=None, cancel_event=None):
    request = validate_recipe(recipe, project)
    _cancel(cancel_event)
    runtime, locked_sha, bindings = _runtime()
    root = Path(project_dir).absolute()
    output = Path(output_dir).absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("CameraCtrl output must stay inside the owning project.") from exc
    if (len(relative.parts) != 3 or relative.parts[:2] != ("camera-control", "outputs")
            or not _ID.fullmatch(relative.name)):
        raise ValueError("CameraCtrl requires an owned immutable output ID.")
    parent = _owned(root, "camera-control/outputs", directory=True, create=True)
    if os.path.lexists(output):
        raise ValueError("CameraCtrl cannot overwrite accepted outputs.")
    settings = request["settings"]
    with tempfile.TemporaryDirectory(dir=parent, prefix=".camera-building-") as tmp:
        scratch = Path(tmp)
        publishing = scratch/"publishing"
        publishing.mkdir()
        rows = []
        for index, pose in enumerate(settings["poses"]):
            fields = [index/FPS, *pose["intrinsics"], 0., 0.,
                      *(number for row in pose["w2c"] for number in row)]
            rows.append(" ".join(format(float(v), ".12g") for v in fields))
        (publishing/"trajectory.txt").write_text(str(FRAMES)+"\n"+"\n".join(rows)+"\n")
        (publishing/"conditioning.json").write_bytes(_encoded({
            "schema": "cinematicum-camera-pose-conditioning-v1",
            "frame_count": FRAMES, "image_width": WIDTH, "image_height": HEIGHT,
            "intrinsics": settings["poses"][0]["intrinsics"],
            "center_pluecker_samples": _center_rays(settings["poses"])
        }))
        captions = scratch/"captions.json"
        captions.write_bytes(_encoded({"captions": [settings["prompt"]], "seeds": [settings["seed"]]}))
        video_dir = scratch/"render"
        video_dir.mkdir()
        if progress: progress(.08)
        video = _execute(runtime, bindings, publishing/"trajectory.txt", captions, video_dir, cancel_event)
        measured = _probe(video)
        if progress: progress(.9)
        shutil.copyfile(video, publishing/"video.mp4")
        artifacts=[]
        for filename in ("trajectory.txt", "conditioning.json", "video.mp4"):
            digest,size=_hash_file(publishing/filename,MAX_ARTIFACT_BYTES)
            artifacts.append({"filename":filename,"sha256":digest,"size":size,"bytes":size})
        if _runtime()[1] != locked_sha:
            raise RuntimeError("CameraCtrl runtime changed during execution.")
        receipt={"type":"cinematicum-cameractrl","version":1,
                 "operation":"camera-conditioned-inference","runtime_lock_sha256":locked_sha,
                 "seed":settings["seed"],
                 "trajectory_sha256":artifacts[0]["sha256"],
                 "conditioning_sha256":artifacts[1]["sha256"],
                 "decoded_video":measured,"artifacts":artifacts,
                 "model_inference":"required_actual_cuda_execution",
                 "camera_motion_quality":"requires_independent_real-shot_measurement"}
        (publishing/"provenance.json").write_bytes(_encoded(receipt))
        ph,ps=_hash_file(publishing/"provenance.json")
        _cancel(cancel_event)
        os.rename(publishing,output)
    if progress:progress(1.)
    return {"output_id":relative.name,"measurement":measured,"receipt":receipt,
            "artifacts":[*artifacts,{"filename":"provenance.json",
                                   "sha256":ph,"size":ps,"bytes":ps}]}

"""Offline CameraCtrl inference controller; runtime configuration is app-owned.

This is a separate SD1.5/AnimateDiff/CameraCtrl CUDA backend. It never maps Wan
parameters to camera conditioning and never installs or downloads a runtime.
Use a supervised job for infer(); it can take minutes and accepts cancellation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time


UPSTREAM_COMMIT = "af45a7a0dbeedb7f6ed66aac4a9e5411a279f0d2"
CAMERA_CHECKPOINT_SHA256 = "31ec2d70923d5e12910a857ba63a8ff2511629bbce7e2f25b85befd205ef1bbf"
CAMERA_CHECKPOINT_BYTES = 2619352551
WIDTH, HEIGHT, FRAMES = 384, 256, 16


def _number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be a finite number")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(name + " is outside its supported range")
    return float(value)


def _integer(value, name, minimum, maximum):
    number = _number(value, name, minimum, maximum)
    if number != int(number):
        raise ValueError(name + " must be an integer")
    return int(number)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _rigid(value):
    if not isinstance(value, list) or len(value) != 4 or any(not isinstance(r, list) or len(r) != 4 for r in value):
        raise ValueError("w2c must be an explicit 4 by 4 OpenCV world-to-camera matrix")
    matrix = [[_number(x, "w2c element", -1e6, 1e6) for x in row] for row in value]
    if any(abs(x-y) > 1e-7 for x,y in zip(matrix[3], [0,0,0,1])):
        raise ValueError("w2c homogeneous row must be [0,0,0,1]")
    rotation = [r[:3] for r in matrix[:3]]
    if any(abs(_dot(rotation[i],rotation[j])-(1 if i == j else 0)) > 1e-5 for i in range(3) for j in range(3)):
        raise ValueError("w2c rotation must be orthonormal")
    if abs(_dot(rotation[0], _cross(rotation[1],rotation[2]))-1) > 1e-5:
        raise ValueError("w2c rotation must be right-handed")
    return matrix


def _inverse_rigid(matrix):
    rotation = [[matrix[j][i] for j in range(3)] for i in range(3)]
    translation = [matrix[i][3] for i in range(3)]
    return [rotation[i]+[-_dot(rotation[i],translation)] for i in range(3)]+[[0.,0.,0.,1.]]


def _multiply(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def validate_request(value):
    """Validate explicit measured/calibrated poses without inventing roll or intrinsics.

    OpenCV axes: x right, y down, z forward. Matrices map world coordinates into
    camera coordinates. All translations use the same declared scene unit.
    Intrinsics are already in the output raster: no implicit crop or resize.
    """
    if not isinstance(value, dict):
        raise ValueError("CameraCtrl request must be an object")
    allowed = {"prompt","negative_prompt","seed","steps","guidance_scale","fps","width","height","frames","coordinate_system","world_unit","intrinsic_units"}
    if set(value)-allowed:
        raise ValueError("Unsupported CameraCtrl request fields: " + ", ".join(sorted(set(value)-allowed)))
    if value.get("coordinate_system") != "opencv_w2c" or value.get("intrinsic_units") != "pixels":
        raise ValueError("Explicit opencv_w2c matrices and pixel intrinsics are required")
    if value.get("world_unit") not in ("metre", "scene_unit"):
        raise ValueError("world_unit must explicitly be metre or scene_unit")
    if value.get("width",WIDTH) != WIDTH or value.get("height",HEIGHT) != HEIGHT:
        raise ValueError("This locked CameraCtrl model supports only 384 by 256 output")
    prompt = value.get("prompt")
    negative = value.get("negative_prompt", "")
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>4096 or not isinstance(negative,str) or len(negative)>4096:
        raise ValueError("A nonempty prompt and bounded negative prompt are required")
    frames = value.get("frames")
    if not isinstance(frames,list) or len(frames) != FRAMES:
        raise ValueError("This locked CameraCtrl model requires exactly 16 camera records")
    parsed = []
    for frame in frames:
        if not isinstance(frame,dict) or set(frame) != {"w2c","intrinsics"}:
            raise ValueError("Each frame requires only w2c and intrinsics; rectify lens distortion first")
        intrinsics = frame["intrinsics"]
        if not isinstance(intrinsics,dict) or set(intrinsics) != {"fx","fy","cx","cy"}:
            raise ValueError("Each frame requires explicit fx, fy, cx, cy pixel intrinsics")
        k = {name:_number(intrinsics[name],name,1e-3,1e6) for name in ("fx","fy")}
        k.update({"cx":_number(intrinsics["cx"],"cx",0,WIDTH),"cy":_number(intrinsics["cy"],"cy",0,HEIGHT)})
        parsed.append({"w2c":_rigid(frame["w2c"]),"intrinsics":k})
    return {"prompt":prompt.strip(),"negative_prompt":negative,"seed":_integer(value.get("seed",42),"seed",0,2**32-1),
            "steps":_integer(value.get("steps",25),"steps",1,100),"guidance_scale":_number(value.get("guidance_scale",14),"guidance_scale",1,30),
            "fps":_integer(value.get("fps",8),"fps",1,60),"width":WIDTH,"height":HEIGHT,"frames":parsed,
            "coordinate_system":"opencv_w2c","world_unit":value["world_unit"],"intrinsic_units":"pixels"}


def conditioning(value):
    """Independent reference construction matching upstream first-camera gauge."""
    request = validate_request(value)
    first_w2c = request["frames"][0]["w2c"]
    c2w = [_multiply(first_w2c,_inverse_rigid(frame["w2c"])) for frame in request["frames"]]
    intrinsic = [[frame["intrinsics"][k] for k in ("fx","fy","cx","cy")] for frame in request["frames"]]
    probes = []
    for frame_index in (0,1,FRAMES-1):
        matrix = c2w[frame_index]
        origin = [matrix[i][3] for i in range(3)]
        fx,fy,cx,cy = intrinsic[frame_index]
        for x,y in ((0,0),(WIDTH//2,HEIGHT//2),(WIDTH-1,HEIGHT-1)):
            direction = [(x+.5-cx)/fx,(y+.5-cy)/fy,1.]
            norm = math.sqrt(_dot(direction,direction))
            direction = [v/norm for v in direction]
            direction = [_dot(matrix[i][:3],direction) for i in range(3)]
            probes.append({"frame":frame_index,"x":x,"y":y,"plucker":_cross(origin,direction)+direction})
    return {"intrinsics":intrinsic,"relative_c2w":c2w,"probes":probes,
            "layout":"batch, moment_xyz+direction_xyz, frame, height, width",
            "shape":[1,6,FRAMES,HEIGHT,WIDTH],"pixel_centres":"x+0.5,y+0.5",
            "relative_pose":"first_w2c @ inverse(each_w2c)","world_unit":request["world_unit"]}


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stop(process):
    # The group is owned by this invocation, including FFmpeg/merge children.
    # Reap the worker and stop any surviving children even if it already exited.
    try:
        os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=3)
    try:
        os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run(runtime, mode, output_dir, request=None, cancel_event=None, timeout=7200):
    if not isinstance(runtime,dict):
        raise ValueError("An app-owned runtime object is required")
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 1<=timeout<=21600:
        raise ValueError("CameraCtrl timeout must be finite and between one second and six hours")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True,exist_ok=False)
    runtime_path = output/"runtime-input.json"
    runtime_path.write_text(json.dumps(runtime,allow_nan=False),encoding="utf-8")
    # Preserve the venv executable path: resolving its symlink bypasses pyvenv.cfg.
    command = [str(Path(runtime.get("python", ""))),"-I",str(Path(__file__).with_name("camera_ctrl_worker.py")),
               "--runtime",str(runtime_path),"--output",str(output),"--mode",mode]
    if request is not None:
        request_path = output/"request.json"
        request_path.write_text(json.dumps(validate_request(request),sort_keys=True,allow_nan=False),encoding="utf-8")
        command += ["--request",str(request_path)]
    if not Path(runtime.get("python", "")).is_absolute() or not Path(command[0]).is_file() or not os.access(command[0],os.X_OK):
        raise ValueError("An existing absolute app-owned Python runtime is required")
    env = {k:v for k,v in os.environ.items() if k in ("PATH","HOME","TMPDIR","SYSTEMROOT","WINDIR","LD_LIBRARY_PATH","DYLD_LIBRARY_PATH")}
    env.update({"HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1","HF_DATASETS_OFFLINE":"1","PYTHONDONTWRITEBYTECODE":"1","TOKENIZERS_PARALLELISM":"false"})
    started = time.monotonic()
    process = None
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("CameraCtrl inference cancelled before launch")
        with (output/"worker.log").open("wb") as log:
            process = subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("CameraCtrl inference cancelled")
                if time.monotonic()-started > timeout:
                    raise TimeoutError("CameraCtrl worker exceeded the supervised job deadline")
                time.sleep(.1)
        report_path = output/"result.json"
        if not report_path.is_file() or report_path.stat().st_size > 1024*1024:
            raise RuntimeError("CameraCtrl worker did not return a bounded result; inspect worker.log")
        result = json.loads(report_path.read_text(encoding="utf-8"))
        if process.returncode != 0 or result.get("passed") is not True:
            raise RuntimeError(result.get("error","CameraCtrl worker failed; inspect worker.log"))
        if mode == "infer":
            video = output/"output.mp4"
            if result.get("video_sha256") != _digest(video) or result.get("frame_count") != FRAMES:
                raise RuntimeError("CameraCtrl emitted output failed independent file binding")
        return result
    finally:
        if process is not None:
            _stop(process)


def doctor(runtime, output_dir, cancel_event=None, timeout=120):
    """Inspect the configured local CUDA runtime and physically verify all assets."""
    try:
        return _run(runtime,"doctor",output_dir,cancel_event=cancel_event,timeout=timeout)
    except (OSError,ValueError,RuntimeError,TimeoutError,InterruptedError) as error:
        return {"passed":False,"available":False,"backend":"CameraCtrl","error":str(error),"inference_executed":False}


def infer(runtime, request, output_dir, cancel_event=None, timeout=7200):
    return _run(runtime,"infer",output_dir,request,cancel_event,timeout)

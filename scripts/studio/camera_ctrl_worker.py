"""Supervised offline worker for the real, pinned CameraCtrl model."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

# -I intentionally removes the script directory from sys.path. Only the shipped
# sibling controller is added; upstream code is copied from verified Git blobs.
sys.path.insert(0,str(Path(__file__).resolve().parent))
from camera_ctrl_standalone import (UPSTREAM_COMMIT,CAMERA_CHECKPOINT_SHA256,CAMERA_CHECKPOINT_BYTES,
                         WIDTH,HEIGHT,FRAMES,validate_request,conditioning,_digest)

MOTION_SHA256 = "2412711886f61091846f53204aabc38aa6e09356d62a9808abe4daa802168343"
ADAPTER_SHA256 = "fd2d8e26480f6ab013c1e6af86fdf1dedbb1ed5baf850ccd5f365f39d6c3472c"
CONFIG = "configs/train_cameractrl/adv3_256_384_cameractrl_relora.yaml"


def _json(path,limit=2*1024*1024):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing or oversized JSON input: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"),parse_constant=lambda value:(_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("A physical regular asset file is required: " + str(path))
    return path


def _entry(entry,root=None,expected_sha=None,expected_bytes=None):
    if not isinstance(entry,dict) or set(entry) != {"path","sha256","bytes"}:
        raise ValueError("Every weight file requires path, sha256 and bytes")
    value = entry["path"]
    if not isinstance(value,str) or not value or "\\" in value:
        raise ValueError("Invalid weight file path")
    if root is not None:
        relative = PurePosixPath(value)
        if relative.is_absolute() or any(part in ("..",".") for part in relative.parts):
            raise ValueError("Weight manifest paths must be relative to the base model")
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Weight file escapes its base model root")
    else:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("Checkpoint path must be absolute")
    path = _regular(path)
    digest = entry["sha256"]
    size = entry["bytes"]
    if not isinstance(digest,str) or not re.fullmatch("[0-9a-f]{64}",digest) or isinstance(size,bool) or not isinstance(size,int) or size<=0:
        raise ValueError("Invalid weight hash or size")
    if expected_sha is not None and digest != expected_sha or expected_bytes is not None and size != expected_bytes:
        raise ValueError("Weight identity is not the pinned official checkpoint")
    if path.stat().st_size != size or _digest(path) != digest:
        raise ValueError("Weight file failed physical hash verification: " + str(path))
    return path


def _source_snapshot(source,output):
    source = Path(source)
    if not source.is_absolute() or not source.is_dir():
        raise ValueError("An absolute local CameraCtrl Git checkout is required")
    def git(*args):
        return subprocess.check_output(["git","--no-replace-objects","-C",str(source),*args],stderr=subprocess.STDOUT,timeout=15)
    commit = git("cat-file","commit",UPSTREAM_COMMIT)
    if hashlib.sha1(b"commit "+str(len(commit)).encode()+b"\0"+commit).hexdigest() != UPSTREAM_COMMIT:
        raise ValueError("CameraCtrl commit object failed verification")
    if git("rev-parse","HEAD").decode().strip() != UPSTREAM_COMMIT:
        raise ValueError("CameraCtrl checkout must be at the exact locked commit")
    destination = output/"upstream-source"
    destination.mkdir()
    identities = {}
    def tree_files(identity,prefix=""):
        # Verify commit -> every tree -> blob closure ourselves. Merely reading
        # ls-tree trusts local object contents and Git replacement references.
        raw = git("cat-file","tree",identity)
        if hashlib.sha1(b"tree "+str(len(raw)).encode()+b"\0"+raw).hexdigest() != identity:
            raise ValueError("CameraCtrl tree object failed verification")
        position = 0
        while position < len(raw):
            space = raw.index(b" ",position)
            zero = raw.index(b"\0",space+1)
            mode = raw[position:space].decode("ascii")
            name = raw[space+1:zero].decode("utf-8")
            if not name or name in (".","..") or "/" in name or "\\" in name or zero+21>len(raw):
                raise ValueError("Invalid CameraCtrl source tree entry")
            blob = raw[zero+1:zero+21].hex()
            position = zero+21
            relative = prefix+name
            if mode == "40000":
                yield from tree_files(blob,relative+"/")
            else:
                yield mode,relative,blob
    tree_line = commit.split(b"\n",1)[0]
    if not re.fullmatch(b"tree [0-9a-f]{40}",tree_line):
        raise ValueError("Invalid CameraCtrl commit tree")
    # Import only verified source files copied into this owned directory. An
    # untracked module or stale bytecode in the original checkout cannot shadow it.
    for mode,relative,blob in tree_files(tree_line[5:].decode("ascii")):
        if not relative.endswith((".py",".yaml")):
            continue
        if mode not in ("100644","100755"):
            raise ValueError("Unexpected source file type")
        path = _regular(source/relative)
        data = path.read_bytes()
        if hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest() != blob:
            raise ValueError("CameraCtrl tracked source changed: " + relative)
        target = destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        identities[relative] = {"git_blob":blob,"sha256":hashlib.sha256(data).hexdigest()}
    if not {"inference.py","tools/merge_lora2unet.py",CONFIG}.issubset(identities):
        raise ValueError("CameraCtrl source snapshot is incomplete")
    return destination,identities


def verify_models(runtime):
    manifest_path = Path(runtime.get("model_manifest",""))
    if not manifest_path.is_absolute() or not re.fullmatch("[0-9a-f]{64}",str(runtime.get("model_manifest_sha256",""))):
        raise ValueError("An app-owned absolute model manifest and its SHA256 are required")
    _regular(manifest_path)
    if _digest(manifest_path) != runtime["model_manifest_sha256"]:
        raise ValueError("Model manifest hash mismatch")
    manifest = _json(manifest_path)
    if manifest.get("schema") != "cinematicum.cameractrl-models.v1":
        raise ValueError("Unsupported CameraCtrl model manifest")
    base = Path(manifest.get("base_model_root",""))
    if not base.is_absolute() or not base.is_dir() or base.is_symlink():
        raise ValueError("A physical local SD1.5 base model directory is required")
    origin = manifest.get("base_source",{})
    if not isinstance(origin.get("repository"),str) or not origin["repository"] or not re.fullmatch("[0-9a-f]{40}",str(origin.get("revision",""))):
        raise ValueError("The base model requires its actual repository and immutable revision")
    entries = manifest.get("base_files")
    if not isinstance(entries,list) or not entries or len(entries)>10000:
        raise ValueError("A complete bounded base model file inventory is required")
    names = [entry.get("path") for entry in entries if isinstance(entry,dict)]
    if len(names)!=len(entries) or len(set(names))!=len(names):
        raise ValueError("Duplicate or invalid base model manifest entries")
    for entry in entries:
        _entry(entry,base)
    actual = {str(path.relative_to(base).as_posix()) for path in base.rglob("*") if path.is_file()}
    if actual != set(names) or any(path.is_symlink() for path in base.rglob("*")):
        raise ValueError("The complete base model directory must match its file manifest")
    for subdir in ("vae","tokenizer","text_encoder","unet"):
        if not any(name.startswith(subdir+"/") for name in names):
            raise ValueError("Missing SD1.5 component: " + subdir)
    for path in ("vae/config.json","text_encoder/config.json","unet/config.json","tokenizer/vocab.json","tokenizer/merges.txt"):
        if path not in names:
            raise ValueError("Missing required base model file: " + path)
    checkpoints = {
        "camera_checkpoint":_entry(manifest.get("camera_checkpoint"),expected_sha=CAMERA_CHECKPOINT_SHA256,expected_bytes=CAMERA_CHECKPOINT_BYTES),
        "motion_module":_entry(manifest.get("motion_module"),expected_sha=MOTION_SHA256,expected_bytes=1673262583),
        "adapter_checkpoint":_entry(manifest.get("adapter_checkpoint"),expected_sha=ADAPTER_SHA256,expected_bytes=102134097),
    }
    return manifest,base,checkpoints


def _runtime(runtime):
    if runtime.get("device") != "cuda:0":
        raise ValueError("The locked official CameraCtrl backend requires cuda:0; MPS/Wan is a different model")
    if sys.version_info[:2] != (3,10):
        raise ValueError("The locked CameraCtrl runtime requires Python 3.10")
    expected = {"torch":"1.13.1","torchvision":"0.14.1","diffusers":"0.24.0","xformers":"0.0.16","imageio":"2.27.0"}
    versions = {name:importlib.metadata.version(name) for name in expected}
    if any(versions[name].split("+")[0] != value for name,value in expected.items()):
        raise ValueError("CameraCtrl dependency versions differ from the upstream locked environment: " + json.dumps(versions))
    import torch
    if not torch.cuda.is_available() or torch.cuda.device_count()<1:
        raise ValueError("No compatible CUDA device is available for CameraCtrl")
    if torch.version.cuda != "11.7":
        raise ValueError("The locked CameraCtrl runtime requires the CUDA 11.7 PyTorch build")
    return {"python":sys.version.split()[0],"packages":versions,"cuda":torch.version.cuda,"device":torch.cuda.get_device_name(0)}


def _media_runtime(runtime):
    ffmpeg = Path(runtime.get("ffmpeg",""))
    ffprobe = Path(runtime.get("ffprobe",""))
    if not ffmpeg.is_absolute() or not ffmpeg.is_file() or not ffprobe.is_absolute() or not ffprobe.is_file():
        raise ValueError("Absolute app-owned FFmpeg and FFprobe executables are required")
    encoders = subprocess.check_output([str(ffmpeg),"-v","error","-encoders"],stderr=subprocess.STDOUT,timeout=10).decode("utf-8","replace")
    if not any("libx264" in line.split() for line in encoders.splitlines()):
        raise ValueError("The configured FFmpeg must provide the libx264 encoder")
    probe_version = subprocess.check_output([str(ffprobe),"-version"],stderr=subprocess.STDOUT,timeout=10).decode("utf-8","replace").splitlines()[0]
    return ffmpeg,ffprobe,probe_version


def _encode(runtime,frames,output,request):
    ffmpeg,ffprobe,_ = _media_runtime(runtime)
    video = output/"output.mp4"
    subprocess.run([str(ffmpeg),"-v","error","-nostdin","-y","-framerate",str(request["fps"]),"-i",str(frames/"%04d.png"),
                    "-frames:v",str(FRAMES),"-an","-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",str(video)],check=True,timeout=120)
    probe = json.loads(subprocess.check_output([str(ffprobe),"-v","error","-select_streams","v:0","-count_frames","-show_entries",
        "stream=width,height,nb_read_frames,r_frame_rate,codec_name","-of","json",str(video)],timeout=30))
    stream = probe["streams"][0]
    if (stream.get("width"),stream.get("height"),int(stream.get("nb_read_frames",0))) != (WIDTH,HEIGHT,FRAMES):
        raise RuntimeError("Actual emitted CameraCtrl movie failed raster/frame-count verification")
    return {"video":"output.mp4","video_sha256":_digest(video),"video_bytes":video.stat().st_size,"frame_count":FRAMES,"ffprobe":probe}


def _progress(output,report,stage):
    report["stage"] = stage
    evidence = {key:report.get(key) for key in ("stage","inference_started","inference_executed","inference_completed","model_load_verified","conditioning")}
    temporary = output/"progress.json.tmp"
    temporary.write_text(json.dumps(evidence,sort_keys=True,allow_nan=False),encoding="utf-8")
    temporary.replace(output/"progress.json")


def execute(runtime,output,mode,request=None,state=None):
    report = state if state is not None else {}
    report.update({"inference_started":False,"inference_executed":False,"inference_completed":False,"model_load_verified":False})
    _progress(output,report,"verifying_runtime")
    versions = _runtime(runtime)
    source,source_files = _source_snapshot(runtime.get("upstream_root",""),output)
    manifest,base,checkpoints = verify_models(runtime)
    _,_,probe_version = _media_runtime(runtime)
    sys.path.insert(0,str(source))
    # Import the actual upstream entry point before reporting readiness. This
    # catches missing legacy transitive packages, native extensions and APIs.
    import inference as official
    report.update({"passed":True,"available":True,"backend":"CameraCtrl","upstream_commit":UPSTREAM_COMMIT,"source_files":source_files,
              "runtime":versions,"model_manifest_sha256":runtime["model_manifest_sha256"],"base_source":manifest["base_source"],
              "ffprobe_version":probe_version,"upstream_import_verified":True,"model_load_verified":False,
              "inference_executed":False,"generated_camera_accuracy_accepted":False,"production_accepted":False})
    if mode == "doctor":
        _progress(output,report,"runtime_prerequisites_verified")
        return report
    request = validate_request(request)
    reference = conditioning(request)
    (output/"conditioning.json").write_text(json.dumps(reference,sort_keys=True,allow_nan=False),encoding="utf-8")
    # Generate the adapted UNet using the exact upstream merge operation rather
    # than trusting an externally labelled 'merged' model with unknown contents.
    model = output/"adapted-model"
    model.mkdir()
    for component in ("vae","tokenizer","text_encoder","unet"):
        (model/component).symlink_to(base/component,target_is_directory=True)
    merged = model/"unet_webvidlora_v3"
    subprocess.run([sys.executable,"-B",str(source/"tools/merge_lora2unet.py"),"--lora_ckpt_path",str(checkpoints["adapter_checkpoint"]),
                    "--unet_ckpt_path",str(model),"--save_path",str(merged),"--unet_config_path",str(base/"unet/config.json")],
                   cwd=str(source),check=True)
    report["merged_unet"] = {path.name:_digest(path) for path in merged.iterdir() if path.is_file()}
    import torch
    import numpy as np
    from PIL import Image
    from omegaconf import OmegaConf
    config = OmegaConf.load(source/CONFIG)
    torch.manual_seed(request["seed"])
    K = torch.tensor(reference["intrinsics"],dtype=torch.float32)[None]
    c2w = torch.tensor(reference["relative_c2w"],dtype=torch.float32)[None]
    rays = official.ray_condition(K,c2w,HEIGHT,WIDTH,device="cpu")
    if list(rays.shape) != [1,FRAMES,HEIGHT,WIDTH,6] or not torch.isfinite(rays).all():
        raise RuntimeError("Actual upstream Plucker rays have invalid shape or values")
    maximum_error = 0.
    for probe in reference["probes"]:
        observed = rays[0,probe["frame"],probe["y"],probe["x"]]
        maximum_error = max(maximum_error,float((observed-torch.tensor(probe["plucker"])).abs().max()))
    if maximum_error>2e-5 or float((rays[...,3:].norm(dim=-1)-1).abs().max())>2e-5 or float((rays[...,:3]*rays[...,3:]).sum(-1).abs().max())>2e-4:
        raise RuntimeError("Actual upstream ray conditioning disagrees with the independent geometric reference")
    pose_embedding = rays.permute(0,4,1,2,3).contiguous().to("cuda:0")
    report["conditioning"] = {"verified":True,"shape":list(pose_embedding.shape),"maximum_reference_error":maximum_error,
        "conditioning_sha256":_digest(output/"conditioning.json"),"tensor_sha256":hashlib.sha256(pose_embedding.cpu().numpy().tobytes()).hexdigest(),
        "world_unit":request["world_unit"],"mapping":"first_w2c @ inverse(each_w2c), pixel centres +0.5, moment then direction"}
    _progress(output,report,"loading_model")
    pipeline = official.get_pipeline(str(model),"unet_webvidlora_v3",2,None,config.unet_additional_kwargs,str(checkpoints["motion_module"]),
        config.pose_encoder_kwargs,config.attention_processor_kwargs,config.noise_scheduler_kwargs,str(checkpoints["camera_checkpoint"]),None,"cuda:0")
    report["model_load_verified"] = True
    generator = torch.Generator(device="cuda:0").manual_seed(request["seed"])
    report.update({"inference_started":True,"inference_executed":None})
    _progress(output,report,"inference_running")
    with torch.inference_mode():
        videos = pipeline(prompt=request["prompt"],negative_prompt=request["negative_prompt"],pose_embedding=pose_embedding,video_length=FRAMES,
            height=HEIGHT,width=WIDTH,num_inference_steps=request["steps"],guidance_scale=request["guidance_scale"],generator=generator).videos
    report.update({"inference_executed":True,"inference_completed":True})
    _progress(output,report,"validating_model_output")
    if tuple(videos.shape)!=(1,3,FRAMES,HEIGHT,WIDTH) or not torch.isfinite(videos).all() or float(videos.min())<0 or float(videos.max())>1:
        raise RuntimeError("Actual CameraCtrl model returned invalid RGB frames")
    frames = output/"frames"
    frames.mkdir()
    rgb = videos[0].detach().cpu().permute(1,2,3,0).numpy()
    frame_hashes = []
    for index,frame in enumerate(rgb):
        path = frames/("%04d.png" % index)
        Image.fromarray(np.rint(frame*255).astype(np.uint8),"RGB").save(path)
        frame_hashes.append(_digest(path))
    report.update(_encode(runtime,frames,output,request))
    report.update({"inference_executed":True,"source_frame_sha256":frame_hashes,"seed":request["seed"],"steps":request["steps"],"fps":request["fps"],
                   "request_sha256":_digest(output/"request.json")})
    _progress(output,report,"output_verified")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--request")
    parser.add_argument("--mode",choices=("doctor","infer"),required=True)
    args = parser.parse_args()
    output = Path(args.output)
    result = {"inference_started":False,"inference_executed":False,"inference_completed":False,"production_accepted":False}
    try:
        result = execute(_json(args.runtime),output,args.mode,_json(args.request) if args.request else None,state=result)
        status = 0
    except Exception as error:
        result.update({"passed":False,"available":False,"backend":"CameraCtrl","error":type(error).__name__+": "+str(error),"production_accepted":False})
        status = 1
    (output/"result.json").write_text(json.dumps(result,sort_keys=True,allow_nan=False),encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())

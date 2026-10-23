"""Official DiffusionLight: checkpoint-backed image-to-HDR generation.

This is a strictly opt-in external CUDA runtime, not a simulated HDR transform.
An operator-pinned source/weight manifest is required; output must decode as a
real finite float EXR before it can be admitted to an owned project.
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
from reconstruction import _cancel, _hash_file, _owned
from imaging import _number

ARTIFACT_NAMES=frozenset({"lighting.exr","input.png","provenance.json"})
MAX_ARTIFACT_BYTES=2*1024**3
HEX=re.compile(r"[a-f0-9]{64}\Z")
ID=re.compile(r"[a-f0-9]{32}\Z")

def encoded(x):
    return (json.dumps(x,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()

def default_settings():
    return {"version":1,"asset_id":"","seed":42,"exposures":[0,-2.5,-5]}

def validate_settings(value):
    defaults=default_settings()
    if not isinstance(value,dict) or set(value)-set(defaults) or type(value.get("version")) is not int or value["version"]!=1:
        raise ValueError("DiffusionLight needs fixed version-1 image settings.")
    x={**defaults,**value}
    if not isinstance(x["asset_id"],str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",x["asset_id"]):
        raise ValueError("DiffusionLight requires one admitted photograph.")
    if x["exposures"]!=[0,-2.5,-5]:
        raise ValueError("This upstream DiffusionLight path uses measured 0/-2.5/-5 EV bracketing.")
    if type(x["seed"]) is not int or not 0<=x["seed"]<=2147483647:
        raise ValueError("DiffusionLight seed must be a bounded integer.")
    return x

def validate_recipe(recipe,project):
    if not isinstance(recipe,dict) or set(recipe)!={"operation","settings"} or recipe["operation"]!="diffusionlight-hdr":
        raise ValueError("Only official DiffusionLight HDR inference is accepted.")
    s=validate_settings(recipe["settings"])
    assets=[a for a in project.get("assets",[]) if isinstance(a,dict) and a.get("id")==s["asset_id"]]
    if len(assets)!=1 or assets[0].get("kind")!="image" or Path(assets[0].get("path","")).suffix.lower() not in {".png",".jpg",".jpeg"}:
        raise ValueError("HDR generation requires exactly one admitted JPEG or PNG.")
    a=assets[0]
    if not isinstance(a.get("sha256"),str) or not HEX.fullmatch(a["sha256"]) or type(a.get("size")) is not int or not 0<a["size"]<=64*1024**2:
        raise ValueError("DiffusionLight source image identity is incomplete.")
    if type(a.get("width")) is not int or type(a.get("height")) is not int or not 64<=a["width"]<=8192 or not 64<=a["height"]<=8192:
        raise ValueError("DiffusionLight source dimensions are invalid.")
    return {"operation":"diffusionlight-hdr","settings":s}

def _runtime():
    f=os.environ.get("CINEMATICUM_DIFFUSIONLIGHT_LOCK")
    sha=os.environ.get("CINEMATICUM_DIFFUSIONLIGHT_LOCK_SHA256")
    if not f or not sha or not HEX.fullmatch(sha):
        raise RuntimeError("DiffusionLight requires an approved external source/checkpoint lock.")
    p=Path(f)
    if not p.is_absolute() or any(v.is_symlink() for v in (p,*p.parents)) or _hash_file(p,1024**2)[0]!=sha:
        raise RuntimeError("DiffusionLight runtime manifest is unsafe or changed.")
    v=json.loads(p.read_text())
    if not isinstance(v,dict) or set(v)!={"schema","root","python","files"} or v["schema"]!="cinematicum-diffusionlight-runtime-v1":
        raise RuntimeError("DiffusionLight manifest is invalid.")
    root=Path(v["root"]);python=Path(v["python"])
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or not python.is_absolute() or not python.is_file() or not os.access(python,os.X_OK):
        raise RuntimeError("DiffusionLight pinned source and CUDA Python interpreter are unavailable.")
    files=v["files"]
    if not isinstance(files,dict) or not all(x in files for x in ("inpaint.py","ball2envmap.py","exposure2hdr.py")) or len(files)<4:
        raise RuntimeError("DiffusionLight source and model files must all be independently pinned.")
    for filename,expected in files.items():
        relative=Path(filename)
        if relative.is_absolute() or ".." in relative.parts or not isinstance(expected,str) or not HEX.fullmatch(expected):
            raise RuntimeError("DiffusionLight runtime contains unsafe source paths.")
        target=root/relative
        if target.is_symlink() or not target.is_file() or _hash_file(target,4*1024**3)[0]!=expected:
            raise RuntimeError("DiffusionLight source/checkpoint bytes differ from lock.")
    return v,sha

def capabilities():
    r={"available":False,"operations":[],"actual_inference_accepted":False,
       "scope":"Official inpaint → chrome-ball projection → multi-exposure float EXR",
       "reason":"DiffusionLight pinned CUDA runtime is missing."}
    try:
        _,sha=_runtime()
        r.update(available=True,operations=["diffusionlight-hdr"],lock_sha256=sha,
                 reason="External inference and production HDR quality remain subject to actual execution.")
    except (OSError,ValueError,RuntimeError) as e:r["reason"]=str(e)
    return r

def _invoke(python,root,args,scratch,event,timeout=3600):
    environment={k:v for k,v in os.environ.items() if not k.startswith(("PYTHON","TORCH_","HF_","TRANSFORMERS_"))}
    environment.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_DATASETS_OFFLINE="1")
    with (scratch/"inference.log").open("ab") as log:
        process=subprocess.Popen([python,*args],cwd=root,env=environment,stdin=subprocess.DEVNULL,
                                 stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        start=time.monotonic()
        try:
            while process.poll() is None:
                _cancel(event)
                if time.monotonic()-start>timeout:raise TimeoutError("DiffusionLight inference exceeded its deadline.")
                if (scratch/"inference.log").stat().st_size>8*1024**2:raise RuntimeError("DiffusionLight exceeded its diagnostics budget.")
                event.wait(.1) if event is not None else time.sleep(.1)
            _cancel(event)
            if process.returncode:raise RuntimeError("Actual DiffusionLight inference failed.")
        finally:_terminate_owned(process)

def _probe_exr(path):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=MAX_ARTIFACT_BYTES:
        raise ValueError("DiffusionLight did not produce a bounded EXR environment.")
    with path.open("rb") as src:
        if src.read(4)!=b"\x76\x2f\x31\x01":raise ValueError("DiffusionLight HDR is not OpenEXR.")
    p=subprocess.run(["ffprobe","-v","error","-show_entries","stream=width,height,pix_fmt",
                      "-of","json",str(path)],capture_output=True,check=True,timeout=30)
    if len(p.stdout)>65536:raise ValueError("EXR probe response is oversized.")
    streams=json.loads(p.stdout).get("streams",[])
    if len(streams)<1 or not 16<=int(streams[0].get("width",0))<=8192 or not 16<=int(streams[0].get("height",0))<=8192:
        raise ValueError("DiffusionLight HDR dimensions are invalid.")
    return {"width":int(streams[0]["width"]),"height":int(streams[0]["height"]),
            "pixel_format":streams[0].get("pix_fmt"),"format":"OpenEXR"}

def run(project,project_dir,recipe,output_dir,progress=None,cancel_event=None):
    request=validate_recipe(recipe,project);_cancel(cancel_event);runtime,locked=_runtime()
    root=Path(project_dir).absolute();output=Path(output_dir).absolute()
    try:relative=output.relative_to(root)
    except ValueError as e:raise ValueError("DiffusionLight output must belong to its project.") from e
    if len(relative.parts)!=3 or relative.parts[:2]!=("diffusionlight","outputs") or not ID.fullmatch(relative.name):
        raise ValueError("DiffusionLight output requires an immutable owned identity.")
    parent=_owned(root,"diffusionlight/outputs",directory=True,create=True)
    if os.path.lexists(output):raise ValueError("DiffusionLight output already exists.")
    asset=next(a for a in project["assets"] if a["id"]==request["settings"]["asset_id"])
    source=_owned(root,asset["path"])
    identity=_hash_file(source,64*1024**2)
    if identity!=(asset["sha256"],asset["size"]):raise ValueError("HDR source differs from admitted bytes.")
    with tempfile.TemporaryDirectory(prefix=".diffusionlight-",dir=parent) as temp:
        scratch=Path(temp);inp=scratch/"source";inp.mkdir()
        image=inp/("source"+source.suffix.lower());shutil.copyfile(source,image)
        if _hash_file(image,64*1024**2)!=identity:raise ValueError("DiffusionLight source copy changed.")
        work=scratch/"generated"
        work.mkdir()
        py=runtime["python"];upstream=Path(runtime["root"])
        _invoke(py,upstream,["inpaint.py","--dataset",str(inp),"--output_dir",str(work),
                            "--limit_input","1","--seed",str(request["settings"]["seed"])],scratch,cancel_event)
        if progress:progress(.4)
        env=work/"envmap";_invoke(py,upstream,["ball2envmap.py","--ball_dir",str(work/"square"),
                                  "--envmap_dir",str(env)],scratch,cancel_event,300)
        if progress:progress(.7)
        hdr=work/"hdr";_invoke(py,upstream,["exposure2hdr.py","--input_dir",str(env),
                               "--output_dir",str(hdr)],scratch,cancel_event,300)
        files=list(hdr.glob("*.exr"))
        if len(files)!=1:raise ValueError("DiffusionLight did not produce exactly one HDR map.")
        measured=_probe_exr(files[0])
        if _hash_file(source,64*1024**2)!=identity or _runtime()[1]!=locked:
            raise ValueError("DiffusionLight source or runtime changed during inference.")
        publication=scratch/"published";publication.mkdir()
        shutil.copyfile(files[0],publication/"lighting.exr")
        # Original photo remains a separate immutable provenance input, not a converted HDR claim.
        shutil.copyfile(image,publication/"input.png")
        artifacts=[]
        for file in ("lighting.exr","input.png"):
            digest,size=_hash_file(publication/file,MAX_ARTIFACT_BYTES)
            artifacts.append({"filename":file,"sha256":digest,"size":size,"bytes":size})
        receipt={"type":"cinematicum-diffusionlight","version":1,"runtime_lock_sha256":locked,
                 "source_asset_id":asset["id"],"source_sha256":identity[0],
                 "inference_pipeline":["inpaint","ball2envmap","exposure2hdr"],
                 "measurement":measured,"artifacts":artifacts,
                 "color_calibration_verified":False,"production_quality_accepted":False}
        (publication/"provenance.json").write_bytes(encoded(receipt))
        sha,size=_hash_file(publication/"provenance.json")
        _cancel(cancel_event);os.rename(publication,output)
    if progress:progress(1.)
    return {"output_id":relative.name,"measurement":measured,"receipt":receipt,
            "artifacts":[*artifacts,{"filename":"provenance.json","sha256":sha,"size":size,"bytes":size}]}

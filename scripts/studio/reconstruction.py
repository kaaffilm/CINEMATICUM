"""Project-owned COLMAP image reconstruction; optional engines stay isolated.

Input photographs are immutable admitted image assets. The worker performs
actual CPU SIFT extraction/matching, incremental SfM and Ceres adjustment.
Results are proposals and portable artifacts, never silent project edits.
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
import stat
import subprocess
import sys
import tempfile
import time

from adapters import _terminate_owned
from camera_io import _axis, _camera
from scene import default_scene, validate_scene

SPARSE_ARTIFACT_NAMES = frozenset({"cameras.txt", "images.txt", "points3D.txt", "rigs.txt", "frames.txt",
    "sparse.ply", "database.db", "reconstruction.json", "scene.json", "undistorted-images.zip",
    "preview.png", "provenance.json"})
ARTIFACT_NAMES = SPARSE_ARTIFACT_NAMES | frozenset({"textured-mesh.zip", "pipeline.mg", "cameras.sfm", "alicevision.json"})
MAX_IMAGES = 48
MAX_IMAGE_BYTES = 64*1024*1024
MAX_INPUT_BYTES = 512*1024*1024
MAX_INPUT_PIXELS = 128*1024*1024
MAX_OUTPUT_BYTES = 512*1024*1024
MAX_SECONDS = 900
PINNED_PACKAGES = {"pycolmap":"4.2.1", "numpy":"2.5.4", "pillow":"13.0.0"}
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_OUTPUT = re.compile(r"[a-f0-9]{32}\Z")


def _json(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,indent=2)+"\n").encode()


def _number(value,label,low,high,integer=False):
    try:valid=not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high and (not integer or int(value)==value)
    except OverflowError:valid=False
    if not valid:
        raise ValueError(f"{label} must be {'an integer ' if integer else ''}between {low} and {high}.")
    return int(value) if integer else float(value)


def default_settings():
    return {"version":1,"asset_ids":[],"camera_model":"SIMPLE_RADIAL","camera_params":None,
        "refine_intrinsics":True,"matching":"exhaustive","max_image_size":1600,"max_features":4096,
        "threads":2,"seed":0,"scale":1.,"up_axis":"Z","marker_limit":2000,"require_all_images":True}


def validate_settings(value):
    defaults=default_settings()
    if not isinstance(value,dict) or set(value)-set(defaults):raise ValueError("Reconstruction settings contain unsupported properties.")
    if type(value.get("version")) is not int or value["version"]!=1:raise ValueError("Unsupported reconstruction settings version.")
    result=copy.deepcopy(defaults);result.update(copy.deepcopy(value))
    ids=result["asset_ids"]
    if (not isinstance(ids,list) or len(ids)>MAX_IMAGES or any(not isinstance(v,str) or not _ID.fullmatch(v) for v in ids)
            or len(ids)!=len(set(ids))):raise ValueError("Select at most 48 unique admitted photo identities.")
    model=result["camera_model"]
    if not isinstance(model,str) or model not in {"PINHOLE","SIMPLE_RADIAL","OPENCV"}:raise ValueError("Choose PINHOLE, SIMPLE_RADIAL or OPENCV camera calibration.")
    if result["matching"] not in ("exhaustive","sequential"):raise ValueError("Choose exhaustive or sequential image matching.")
    if result["up_axis"] not in ("Z","Y"):raise ValueError("Choose the reconstruction's Z or Y world up axis explicitly.")
    for key in ("refine_intrinsics","require_all_images"):
        if type(result[key]) is not bool:raise ValueError(key+" must be true or false.")
    for key,low,high in (("max_image_size",256,3200),("max_features",256,8192),("threads",1,4),
                         ("seed",0,2147483647),("marker_limit",0,5000)):
        result[key]=_number(result[key],key,low,high,True)
    result["scale"]=_number(result["scale"],"Scene scale",.000001,1000)
    params=result["camera_params"]
    if params is not None:
        count=8 if model=="OPENCV" else 4
        if not isinstance(params,list) or len(params)!=count:raise ValueError(f"{model} calibration requires {count} numeric parameters.")
        result["camera_params"]=[_number(v,"Camera parameter",-2,100000) for v in params]
        focal=1 if model=="SIMPLE_RADIAL" else 2
        if any(v<=0 for v in params[:focal]):raise ValueError("Camera focal lengths must be positive.")
        if any(not 0<=v<=8192 for v in params[focal:focal+2]):raise ValueError("The normalized-photo principal point must be between 0 and 8192 pixels.")
        if any(abs(v)>2 for v in params[focal+2:]):raise ValueError("Supported initial distortion coefficients must be between -2 and 2.")
    return result


def validate_recipe(recipe,project):
    if not isinstance(recipe,dict) or set(recipe)!={"operation","settings"}:raise ValueError("Reconstruction needs operation and typed settings only.")
    if recipe["operation"]=="meshroom_dense":
        from alicevision import validate_recipe as validate_dense
        return validate_dense(recipe,project)
    if recipe["operation"]!="reconstruct":
        raise ValueError("Choose the sparse COLMAP or typed Meshroom dense operation; CPU COLMAP does not implement CUDA PatchMatch.")
    settings=validate_settings(recipe["settings"])
    if not 3<=len(settings["asset_ids"])<=MAX_IMAGES:raise ValueError("Select 3–48 overlapping photographs.")
    if settings["camera_params"] is None and not settings["refine_intrinsics"]:raise ValueError("Fixed intrinsics require explicit calibrated parameters.")
    assets=project.get("assets",[])
    total_pixels=0
    for ident in settings["asset_ids"]:
        matches=[a for a in assets if isinstance(a,dict) and a.get("id")==ident]
        if len(matches)!=1 or matches[0].get("kind")!="image":raise ValueError("Every reconstruction input must be one admitted still photograph.")
        asset=matches[0]
        if Path(asset.get("path","")).suffix.lower() not in {".png",".jpg",".jpeg"}:raise ValueError("Reconstruction currently accepts opaque PNG or JPEG photographs.")
        w=_number(asset.get("width"),"Photo width",32,8192,True);h=_number(asset.get("height"),"Photo height",32,8192,True)
        if w*h>16*1024*1024:raise ValueError("Each reconstruction photograph is bounded to 16 megapixels.")
        total_pixels+=w*h
    if total_pixels>MAX_INPUT_PIXELS:raise ValueError("The selected photographs exceed the 128-megapixel aggregate decode budget.")
    return {"operation":"reconstruct","settings":settings}


def find_python(python=None):
    value=python if python is not None else os.environ.get("CINEMATICUM_RECONSTRUCTION_PYTHON")
    relative="Library/Application Support/CINEMATICUM/Reconstruction/py313-v1/bin/python" if sys.platform=="darwin" else ".local/share/CINEMATICUM/Reconstruction/py312-v1/bin/python"
    path=Path(value).expanduser() if value else Path.home()/relative
    return str(path) if path.is_absolute() and path.is_file() and os.access(path,os.X_OK) else None


def _command(python=None):
    executable=find_python(python)
    if not executable:raise RuntimeError("The optional COLMAP runtime is not installed. Use Runtime setup or CINEMATICUM_RECONSTRUCTION_PYTHON.")
    return [executable,"-I","-B",str(Path(__file__).with_name("reconstruction_worker.py"))]


def _env():
    env={k:v for k,v in os.environ.items() if not k.startswith(("PYTHON","COLMAP_"))}
    env.update(OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",MKL_NUM_THREADS="2",VECLIB_MAXIMUM_THREADS="2")
    return env


def capabilities(python=None):
    result={"available":False,"operations":[],"dense_available":False,"reason":"The optional COLMAP runtime is not installed.",
            "scope":"CPU SIFT extraction/matching, incremental SfM, Ceres bundle adjustment, official image undistortion and editable camera/point proposals.",
            "limits":{"photos":MAX_IMAGES,"seconds":MAX_SECONDS,"aggregate_megapixels":128,"threads":4}}
    try:
        response=subprocess.run(_command(python),input=_json({"command":"doctor"}),capture_output=True,timeout=10,env=_env())
        if len(response.stdout)>65536:raise ValueError("The reconstruction runtime probe returned excessive data.")
        doctor=json.loads(response.stdout)
        if response.returncode or not doctor.get("available"):raise RuntimeError(doctor.get("error","COLMAP runtime verification failed."))
        result.update(available=True,operations=["reconstruct"],versions=doctor["versions"],reason=None,
                      cuda_compiled=doctor["cuda_compiled"],dense_reason="The managed CPU workflow does not implement CUDA PatchMatch or dense meshing.")
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:result["reason"]=str(exc)
    from alicevision import capabilities as dense_capabilities
    result["meshroom"]=dense_capabilities()
    if result["meshroom"]["available"]:result["operations"].append("meshroom_dense")
    return result


def _hash_file(path,limit=MAX_OUTPUT_BYTES):
    with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)),"rb") as stream:
        first=os.fstat(stream.fileno())
        if not stat.S_ISREG(first.st_mode) or not 0<first.st_size<=limit:raise ValueError("Reconstruction files must be bounded nonempty regular files.")
        digest=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
        last=os.fstat(stream.fileno())
        if (first.st_ino,first.st_size,first.st_mtime_ns)!=(last.st_ino,last.st_size,last.st_mtime_ns):raise ValueError("Reconstruction input changed during verification.")
    return digest.hexdigest(),first.st_size


def _owned(root,relative,directory=False,create=False):
    root=Path(root).absolute();relative=Path(relative)
    if root.is_symlink() or not root.is_dir():raise ValueError("Reconstruction requires a real project directory.")
    if relative.is_absolute() or not relative.parts or any(p in {".",".."} for p in relative.parts):raise ValueError("Reconstruction paths must remain in their project.")
    current=root
    for i,part in enumerate(relative.parts):
        current/=part
        if current.is_symlink():raise ValueError("Reconstruction paths cannot contain symbolic links.")
        if i<len(relative.parts)-1 or directory:
            if create:current.mkdir(exist_ok=True)
            if not current.is_dir():raise ValueError("An owned reconstruction directory is missing.")
    return current


def _cancel(event):
    if event is not None and event.is_set():raise InterruptedError("Reconstruction cancelled.")


def _worker(request,scratch,python,progress,event):
    output=scratch/"worker.json";errors=scratch/"worker.stderr"
    with output.open("wb") as out,errors.open("wb") as err:
        process=subprocess.Popen(_command(python),stdin=subprocess.PIPE,stdout=out,stderr=err,env=_env(),start_new_session=True)
        try:
            process.stdin.write(_json(request));process.stdin.close();start=time.monotonic();last=-1.
            while process.poll() is None:
                _cancel(event)
                if time.monotonic()-start>MAX_SECONDS:raise TimeoutError("Reconstruction exceeded its owned 15-minute execution budget.")
                if output.stat().st_size>2*1024*1024 or errors.stat().st_size>8*1024*1024:raise RuntimeError("Reconstruction exceeded its diagnostic output budget.")
                if progress:
                    try:
                        value=json.loads((scratch/"progress.json").read_text())["progress"]
                        if type(value) in (float,int) and math.isfinite(value) and last<value<1:progress(value);last=value
                    except (OSError,ValueError,KeyError):pass
                event.wait(.1) if event is not None else time.sleep(.1)
            _cancel(event)
        finally:_terminate_owned(process)
    try:result=json.loads(output.read_text())
    except (OSError,ValueError) as exc:raise RuntimeError("COLMAP did not return a valid result: "+errors.read_text(errors="replace")[-1500:]) from exc
    if process.returncode or result.get("error"):raise RuntimeError(result.get("error","COLMAP reconstruction failed."))
    return result


def scene_proposal(project,metadata,settings,output_id):
    """Reviewable scene proposal: measured poses and explicitly bounded markers.

    Sparse points retain full RGB/track data in COLMAP/PLY artifacts. The single
    authored mesh uses small monochrome tetrahedra only to make points editable
    and visible; those markers are not a reconstructed watertight surface.
    """
    cameras=[]
    for item in metadata["cameras"]:
        r=item["rotation"];fx,fy,cx,cy=item["undistorted"]["params"]
        width,height=item["undistorted"]["width"],item["undistorted"]["height"]
        # COLMAP may produce an odd corrected image dimension. The scene
        # renderer requires even dimensions. An explicit uniform factor of
        # two preserves aspect, normalized intrinsics and the field of view;
        # no reference pixels are cropped, stretched, or replaced.
        canvas_scale=2 if width%2 or height%2 else 1
        camera=_camera(item["center"],r[0],[-v for v in r[1]],[-v for v in r[2]],
                       width,height,fx,fy,cx,cy,settings["scale"],settings["up_axis"])
        cameras.append({"id":str(item["image_id"]),"asset_id":item["asset_id"],"name":item["name"],"camera":camera,
                        "width":width,"height":height,"scene_width":width*canvas_scale,"scene_height":height*canvas_scale,
                        "scene_canvas_scale":canvas_scale,
                        "undistorted_member":item["undistorted"]["member"],"source_camera_model":item["source_model"]})
    if not cameras:raise ValueError("Reconstruction produced no usable calibrated cameras.")
    scene=copy.deepcopy(project.get("settings",{}).get("scene")) or default_scene(cameras[0]["scene_width"],cameras[0]["scene_height"])
    scene.update(width=cameras[0]["scene_width"],height=cameras[0]["scene_height"])
    scene["camera"]={**scene.get("camera",{}),**cameras[0]["camera"]}
    points=[[_number(v*settings["scale"],"Scaled sparse point",-1e6,1e6) for v in _axis(p["xyz"],settings["up_axis"])] for p in metadata["marker_points"]]
    if points:
        extent=max(max(p[i] for p in points)-min(p[i] for p in points) for i in range(3))
        radius=max(.00001,min(10.,extent*.0015));vertices=[];faces=[]
        offsets=((1,1,1),(-1,-1,1),(-1,1,-1),(1,-1,-1))
        for point in points:
            base=len(vertices);vertices.extend([[v+radius*d for v,d in zip(point,offset)] for offset in offsets])
            faces.extend([[base+a,base+b,base+c] for a,b,c in ((0,2,1),(0,1,3),(0,3,2),(1,2,3))])
        scene.setdefault("objects",[]).append({"id":"reconstruction_points_"+output_id[:16],"name":"COLMAP sparse point markers",
            "type":"mesh","position":[0,0,0],"rotation":[0,0,0],"scale":[1,1,1],
            "material":{"color":"#b4d9e8","roughness":.7,"metallic":0},
            "mesh":{"version":1,"vertices":vertices,"triangles":faces}})
    return validate_scene(scene),cameras


def run(project,project_dir,recipe,output_dir,progress=None,cancel_event=None,python=None):
    if isinstance(recipe,dict) and recipe.get("operation")=="meshroom_dense":
        from alicevision import run as run_dense
        return run_dense(project,project_dir,recipe,output_dir,progress,cancel_event)
    recipe=validate_recipe(recipe,project);_cancel(cancel_event);_command(python)
    root=Path(project_dir).absolute();output=Path(output_dir).absolute()
    try:relative=output.relative_to(root)
    except ValueError as exc:raise ValueError("Reconstruction output must remain inside its project.") from exc
    if len(relative.parts)!=3 or relative.parts[:2]!=("reconstruction","outputs") or not _OUTPUT.fullmatch(relative.name):raise ValueError("Use reconstruction/outputs/<owned-job-id> for immutable reconstruction output.")
    parent=_owned(root,"reconstruction/outputs",directory=True,create=True)
    if os.path.lexists(output):raise ValueError("An existing reconstruction output cannot be overwritten.")
    settings=recipe["settings"];inputs=[];originals=[];total=0
    with tempfile.TemporaryDirectory(prefix=".building-",dir=parent) as temporary:
        scratch=Path(temporary);generated=scratch/"result";generated.mkdir();copies=scratch/"source";copies.mkdir()
        for index,ident in enumerate(settings["asset_ids"]):
            _cancel(cancel_event);asset=next(a for a in project["assets"] if a["id"]==ident);source=_owned(root,asset["path"])
            digest,size=_hash_file(source,MAX_IMAGE_BYTES);total+=size
            if total>MAX_INPUT_BYTES:raise ValueError("Reconstruction source bytes exceed the 512-MiB job budget.")
            if (digest,size)!=(asset.get("sha256"),asset.get("size")):raise ValueError("A source photograph no longer matches its admitted identity.")
            copied=copies/(f"{index:03d}_"+ident+source.suffix.lower());shutil.copyfile(source,copied)
            if _hash_file(copied,MAX_IMAGE_BYTES)!=(digest,size):raise ValueError("A source photograph changed while preparing reconstruction.")
            identity={"asset_id":ident,"sha256":digest,"bytes":size,"name":str(asset.get("name",ident))[:512],"member_stem":f"{index:03d}_"+ident,
                      "width":asset["width"],"height":asset["height"]}
            inputs.append(identity);originals.append((source,digest,size))
        request={"command":"reconstruct","settings":settings,"inputs":[{**record,"path":str(path)} for record,path in zip(inputs,sorted(copies.iterdir()))],
                 "output_dir":str(generated),"work_dir":str(scratch/"work"),"progress_path":str(scratch/"progress.json")}
        result=_worker(request,scratch,python,progress,cancel_event)
        metadata=json.loads((generated/"reconstruction.json").read_text())
        try:
            scene,cameras=scene_proposal(project,metadata,settings,relative.name)
            proposal_error=None;(generated/"scene.json").write_bytes(_json({"scene":scene,"reconstruction":settings,"cameras":cameras}))
        except ValueError as exc:
            # Camera/geometry bounds never invalidate or silently alter the
            # actual solved reconstruction. Its immutable scientific outputs
            # remain usable, with the proposal limitation stated explicitly.
            scene=None;cameras=[];proposal_error=str(exc)
        for path,digest,size in originals:
            if _hash_file(path,MAX_IMAGE_BYTES)!=(digest,size):raise ValueError("A source photograph changed during reconstruction.")
        actual={p.name for p in generated.iterdir()}
        required={"cameras.txt","images.txt","points3D.txt","sparse.ply","database.db","reconstruction.json","undistorted-images.zip","preview.png"}
        if actual-SPARSE_ARTIFACT_NAMES or "provenance.json" in actual or not required<=actual:raise RuntimeError("The COLMAP worker returned an invalid artifact inventory.")
        artifacts=[];total=0
        for name in sorted(actual):
            digest,size=_hash_file(generated/name);total+=size;artifacts.append({"filename":name,"sha256":digest,"bytes":size,"size":size})
        if total>MAX_OUTPUT_BYTES:raise ValueError("Reconstruction outputs exceed the 512-MiB publication budget.")
        receipt={"type":"cinematicum-reconstruction","version":1,"operation":"reconstruct","settings":settings,"inputs":inputs,
                 "engine":result["engine"],"statistics":metadata["statistics"],"bundle_adjustment":metadata["bundle_adjustment"],
                 "normalization":metadata["normalization"],"unregistered_asset_ids":metadata["unregistered_asset_ids"],
                 "scope":result["scope"],"proposal_error":proposal_error,"artifacts":artifacts,
                 "source_sha256":{p.name:_hash_file(p)[0] for p in (Path(__file__),Path(__file__).with_name("reconstruction_worker.py"),Path(__file__).with_name("camera_io.py"))}}
        (generated/"provenance.json").write_bytes(_json(receipt));receipt_sha,receipt_size=_hash_file(generated/"provenance.json")
        _cancel(cancel_event);os.rename(generated,output)
    if progress:progress(1)
    return {"output_id":relative.name,"settings":settings,"scene":scene,"cameras":cameras,"proposal_error":proposal_error,
            "statistics":metadata["statistics"],"receipt":receipt,"provenance":{**receipt,"output_id":relative.name,"receipt_sha256":receipt_sha},
            "artifacts":[*artifacts,{"filename":"provenance.json","sha256":receipt_sha,"bytes":receipt_size,"size":receipt_size}]}

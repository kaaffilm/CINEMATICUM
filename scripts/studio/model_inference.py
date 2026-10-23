"""Project-owned CameraCtrl/DiffusionLight jobs and immutable output admission.

Runtime profiles are operator configuration at fixed Application Support paths.
HTTP payloads contain model names, typed options and admitted source identities;
they cannot choose an interpreter, repository, checkpoint or output directory.
Status reads small profile JSON only. Doctors and inference use Store.submit.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
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

MODELS = {"camera_ctrl":"CameraCtrl", "diffusionlight":"DiffusionLight"}
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_PHOTO_BYTES = 256*1024*1024
MAX_ARTIFACT_BYTES = 1024**3
ARTIFACT_NAMES = frozenset({"output.mp4","conditioning.json","worker-result.json","environment.exr","preview.png",
                            "worker-provenance.json","worker.log","doctor.json","provenance.json"})


def _profile_root():
    return Path.home()/"Library/Application Support/CINEMATICUM/GenerationModels"


def _model(value):
    if not isinstance(value,str) or value not in MODELS:
        raise ValueError("Select CameraCtrl or DiffusionLight")
    return value


def _pairs(values):
    result = {}
    for key,value in values:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _json(path,limit=1024*1024):
    path = _regular(path)
    if path.stat().st_size>limit:
        raise ValueError("Model inference metadata exceeds its size bound")
    with path.open("rb") as stream:
        data = stream.read(limit+1)
    if len(data)>limit:
        raise ValueError("Model inference metadata exceeds its size bound")
    return json.loads(data,object_pairs_hook=_pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("A regular owned file is required")
    return path


def _owned(root,relative):
    root = Path(root)
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or any(part in (".","..") for part in relative.parts):
        raise ValueError("Invalid model output path")
    candidate = root
    for component in relative.parts:
        candidate = candidate/component
        if candidate.is_symlink():
            raise ValueError("Owned model inputs and outputs cannot contain symbolic links")
    if candidate.resolve().parent != root.resolve()/relative.parent:
        raise ValueError("Model file escaped its owned directory")
    return _regular(candidate)


def _digest(path,limit=MAX_ARTIFACT_BYTES,cancel_event=None):
    path = _regular(path)
    value = hashlib.sha256()
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        if before.st_size>limit:
            raise ValueError("Model input or output exceeds its byte bound")
        for block in iter(lambda:source.read(4*1024*1024),b""):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Model operation cancelled while verifying its owned files")
            value.update(block)
        after = os.fstat(source.fileno())
    if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
        raise ValueError("A model input or output changed during verification")
    return value.hexdigest(),after.st_size


def _write(path,value):
    path = Path(path)
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def _profile(model):
    model = _model(model)
    root = _profile_root()
    path = root/model/"runtime.json"
    # The profile itself, including all components under the user's home, must
    # be a physical operator-owned path rather than a project-controlled alias.
    home = Path.home()
    candidate = home
    for part in path.relative_to(home).parts:
        candidate = candidate/part
        if candidate.is_symlink():
            raise ValueError("The operator model runtime profile cannot contain symbolic links")
    path = _regular(path)
    if path.stat().st_size>64*1024:
        raise ValueError("The operator model profile exceeds 64 KiB")
    with path.open("rb") as stream:
        data = stream.read(64*1024+1)
    if len(data)>64*1024:
        raise ValueError("The operator model profile exceeds 64 KiB")
    runtime = json.loads(data,object_pairs_hook=_pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError("Nonfinite profile JSON")))
    keys = {"python","upstream_root","model_manifest","model_manifest_sha256","device"}
    if model == "camera_ctrl":
        keys |= {"ffmpeg","ffprobe"}
    if not isinstance(runtime,dict) or set(runtime)!=keys:
        raise ValueError("The operator model runtime profile has unsupported fields")
    for key in keys-{"device","model_manifest_sha256"}:
        value = runtime[key]
        if not isinstance(value,str) or len(value)>4096 or not Path(value).is_absolute():
            raise ValueError("Operator runtime paths must be explicit absolute paths")
    if not isinstance(runtime["model_manifest_sha256"],str) or not SHA256.fullmatch(runtime["model_manifest_sha256"]):
        raise ValueError("The operator profile requires its trusted model manifest SHA256")
    if runtime["device"] not in ({"cuda:0"} if model=="camera_ctrl" else {"cpu","cuda"}):
        raise ValueError("CameraCtrl requires CUDA; DiffusionLight supports its explicit CPU or CUDA backend")
    return runtime,hashlib.sha256(data).hexdigest()


def status():
    """Cheap read-only configuration status; never imports or hashes models."""
    models = []
    for model,label in MODELS.items():
        try:
            _,identity = _profile(model)
            entry = {"model":model,"label":label,"configured":True,"profile_sha256":identity,
                     "reason":"Operator profile present; run Verify runtime to check actual dependencies and weight bytes."}
        except (OSError,ValueError,TypeError) as error:
            entry = {"model":model,"label":label,"configured":False,"reason":"Operator runtime profile unavailable: "+str(error)}
        entry.update(runtime_verified=False,inference_accepted=False,production_accepted=False)
        models.append(entry)
    return {"models":models,"automatic_installation":False,"scope":"Profile configuration only; no model import, weight hashing or inference."}


def _implementation(model):
    name = "camera_ctrl" if model=="camera_ctrl" else "diffusionlight"
    return importlib.import_module(("." if __package__ else "")+name,__package__ or None)


def _photo(project,source_id):
    if not isinstance(source_id,str) or not IDENTIFIER.fullmatch(source_id):
        raise ValueError("Select one admitted project photograph")
    matches = [value for value in project.get("assets",[]) if isinstance(value,dict) and value.get("id")==source_id]
    if len(matches)!=1:
        raise ValueError("The source photograph is not uniquely owned by this project")
    asset = matches[0]
    relative = Path(asset.get("path",""))
    if asset.get("kind")!="image" or relative.suffix.lower() not in {".png",".jpg",".jpeg"} or relative.parts!=("media",source_id+relative.suffix):
        raise ValueError("DiffusionLight requires one admitted PNG or JPEG still photograph")
    if not isinstance(asset.get("sha256"),str) or not SHA256.fullmatch(asset["sha256"]) or type(asset.get("size")) is not int or not 0<asset["size"]<=MAX_PHOTO_BYTES:
        raise ValueError("The admitted photograph lacks a bounded physical file identity")
    width,height = asset.get("width"),asset.get("height")
    if type(width) is not int or type(height) is not int or min(width,height)<1 or width*height>16*1024*1024:
        raise ValueError("DiffusionLight photographs are bounded to 16 megapixels")
    return copy.deepcopy(asset)


def _photo_copy(directory,asset,run,event):
    source = _owned(directory,asset["path"])
    if _digest(source,MAX_PHOTO_BYTES,event)!=(asset["sha256"],asset["size"]):
        raise ValueError("The source photograph no longer matches its admitted identity")
    target = run/("source"+source.suffix.lower())
    shutil.copyfile(source,target)
    if _digest(target,MAX_PHOTO_BYTES,event)!=(asset["sha256"],asset["size"]):
        raise ValueError("The source photograph changed while creating its job snapshot")
    return target


def _movie(runtime,path,expected,event):
    if event.is_set():
        raise RuntimeError("CameraCtrl cancelled before output validation")
    process = subprocess.Popen([runtime["ffprobe"],"-v","error","-select_streams","v:0","-count_frames","-show_entries",
        "stream=width,height,nb_read_frames,codec_name,r_frame_rate","-of","json",str(path)],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    import time
    started = time.monotonic()
    try:
        while True:
            if event.is_set():
                raise RuntimeError("CameraCtrl cancelled while validating actual output frames")
            if time.monotonic()-started>30:
                raise RuntimeError("CameraCtrl output decoder exceeded its validation deadline")
            try:
                raw,error = process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if process.returncode or len(raw)>128*1024:
            raise ValueError("Actual generated movie could not be independently decoded")
        probe = json.loads(raw)
        stream = probe["streams"][0]
        rate = str(stream.get("r_frame_rate","")).split("/")
        fps = float(rate[0])/float(rate[1]) if len(rate)==2 else float(rate[0])
        if (stream.get("width"),stream.get("height"),int(stream.get("nb_read_frames",0)),stream.get("codec_name"))!=(384,256,16,"h264") or abs(fps-expected["fps"])>1e-6:
            raise ValueError("Actual CameraCtrl movie raster, frame count, codec or rate differs from the submitted shot")
        return probe
    finally:
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait(timeout=2)
        try:
            os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass


def _mkdir(root,relative):
    candidate = Path(root)
    for component in Path(relative).parts:
        if component in (".",".."):
            raise ValueError("Invalid owned model directory")
        candidate = candidate/component
        if candidate.is_symlink():
            raise ValueError("Owned model directories cannot be symbolic links")
        candidate.mkdir(exist_ok=True)
        if not candidate.is_dir():
            raise ValueError("Owned model directory is not a directory")
    return candidate


def _publish(store,project_id,model,action,job_id,run,selected,report,profile_sha,inputs,event):
    directory = store.root/"projects"/project_id
    parent = _mkdir(directory,Path("model-inference")/"outputs")
    target = parent/job_id
    if target.exists() or target.is_symlink():
        raise ValueError("This immutable model output already exists")
    stage = Path(tempfile.mkdtemp(prefix="publish-"+job_id+"-",dir=str(parent)))
    try:
        identities = []
        for name,source in selected.items():
            if name not in ARTIFACT_NAMES-{"provenance.json"}:
                raise ValueError("Unexpected model inference artifact")
            source = _owned(run,Path(source).relative_to(run))
            digest,size = _digest(source,cancel_event=event)
            shutil.copyfile(source,stage/name)
            if _digest(stage/name,cancel_event=event)!=(digest,size):
                raise ValueError("A worker output changed during publication")
            identities.append({"filename":name,"sha256":digest,"bytes":size})
        if not identities:
            raise ValueError("Model inference did not publish any real artifacts")
        receipt = {"schema":"cinematicum-model-inference","version":1,"model":model,"operation":action,
            "project_id":project_id,"output_id":job_id,"profile_sha256":profile_sha,"inputs":inputs,
            "inference_executed":action=="infer" and report.get("inference_executed") is True,
            "generated_camera_accuracy_accepted":False,"production_accepted":False,"worker_report":report,"artifacts":identities,
            "scope":"Actual model output requires independent picture/lighting acceptance. HDR environments retain their EXR; PNG is a display derivative."}
        _write(stage/"provenance.json",receipt)
        if event.is_set():
            raise RuntimeError("Model job cancelled before immutable output publication")
        os.replace(str(stage),str(target))
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    result = _result(receipt)
    result["receipt_sha256"] = _digest(target/"provenance.json",8*1024*1024)[0]
    # A late cancellation/quit can defer Media admission but cannot hide an
    # already committed output. The immutable artifacts remain downloadable.
    display = "output.mp4" if model=="camera_ctrl" else "preview.png"
    if action=="infer" and display in result["artifact_urls"]:
        result["display_url"] = result["artifact_urls"][display]
        if model=="diffusionlight":
            result["exr_url"] = result["artifact_urls"]["environment.exr"]
        with store.lock:
            if store._closing or event.is_set():
                result["media_admission"] = "deferred_after_publication"
                return result
            provenance = {"type":"cinematicum-camera-ctrl" if model=="camera_ctrl" else "cinematicum-diffusionlight-display",
                "version":1,"output_id":job_id,"receipt_sha256":result["receipt_sha256"],"profile_sha256":profile_sha,
                "inference_executed":True,"production_accepted":False}
            if model=="diffusionlight":
                provenance.update(linear_environment_sha256=next(item["sha256"] for item in identities if item["filename"]=="environment.exr"),
                    display_transform="Relative EXR / its 99th percentile, clipped 0..1, gamma 1/2.4; SDR display derivative only")
            try:
                with tempfile.TemporaryDirectory(prefix="model-admit-",dir=str(directory)) as temporary:
                    incoming = Path(temporary)/display
                    shutil.copyfile(target/display,incoming)
                    label = "CameraCtrl generated take.mp4" if model=="camera_ctrl" else "DiffusionLight display derivative.png"
                    asset = store.admit(project_id,incoming,label,provenance)
                result.update(asset=asset,url=f"/api/projects/{project_id}/media/{asset['id']}",media_admission="admitted")
            except Exception as error:
                result.update(media_admission="failed_after_publication",media_admission_error=str(error)[-6000:])
    return result


def _receipt(directory,job_id):
    if not isinstance(job_id,str) or not IDENTIFIER.fullmatch(job_id):
        raise ValueError("Invalid model output identity")
    relative = Path("model-inference")/"outputs"/job_id
    receipt_path = _owned(directory,relative/"provenance.json")
    receipt = _json(receipt_path,8*1024*1024)
    if (not isinstance(receipt,dict) or receipt.get("schema")!="cinematicum-model-inference" or receipt.get("version")!=1
            or receipt.get("output_id")!=job_id or not isinstance(receipt.get("project_id"),str) or not IDENTIFIER.fullmatch(receipt["project_id"])
            or receipt.get("model") not in MODELS or receipt.get("operation") not in {"doctor","infer"}):
        raise ValueError("Invalid project-owned model inference receipt")
    entries = receipt.get("artifacts")
    if not isinstance(entries,list) or not entries or len(entries)>len(ARTIFACT_NAMES)-1:
        raise ValueError("Model inference receipt lacks its bounded artifact inventory")
    names = set()
    for entry in entries:
        if (not isinstance(entry,dict) or entry.get("filename") not in ARTIFACT_NAMES-{"provenance.json"}
                or entry["filename"] in names or not isinstance(entry.get("sha256"),str) or not SHA256.fullmatch(entry["sha256"])
                or type(entry.get("bytes")) is not int or not 0<entry["bytes"]<=MAX_ARTIFACT_BYTES):
            raise ValueError("Model inference receipt has invalid artifact identities")
        names.add(entry["filename"])
    return receipt,receipt_path


def _result(receipt,project_id=None):
    # The originating project ID stays immutable in provenance after a verified
    # portable restore. HTTP URLs belong to the current owned project directory.
    project_id = receipt["project_id"] if project_id is None else project_id
    base = f"/api/projects/{project_id}/model-inference/outputs/{receipt['output_id']}"
    urls = {entry["filename"]:base+"/"+entry["filename"] for entry in receipt["artifacts"]}
    urls["provenance.json"] = base+"/provenance.json"
    result = {"model":receipt["model"],"operation":receipt["operation"],"output_id":receipt["output_id"],"artifact_urls":urls,
        "receipt_url":urls["provenance.json"],"inference_executed":receipt["inference_executed"],"production_accepted":False,
        "report":receipt["worker_report"]}
    if receipt["operation"]=="infer":
        display = "output.mp4" if receipt["model"]=="camera_ctrl" else "preview.png"
        if display in urls:
            result["display_url"] = urls[display]
        if "environment.exr" in urls:
            result["exr_url"] = urls["environment.exr"]
    return result


def artifact(store,project_id,job_id,filename):
    if filename not in ARTIFACT_NAMES:
        raise ValueError("Invalid model artifact filename")
    directory = store.project_dir(project_id)
    receipt,receipt_path = _receipt(directory,job_id)
    if filename=="provenance.json":
        return receipt_path
    entries = [entry for entry in receipt["artifacts"] if entry["filename"]==filename]
    if len(entries)!=1:
        raise FileNotFoundError("This model result does not contain that artifact")
    path = _owned(directory,Path("model-inference")/"outputs"/job_id/filename)
    if _digest(path)!=(entries[0]["sha256"],entries[0]["bytes"]):
        raise ValueError("The model artifact differs from its immutable published identity")
    return path


def list_results(store,project_id,limit=30):
    directory = store.project_dir(project_id)
    if (directory/"model-inference").is_symlink():
        raise ValueError("Invalid model inference output directory")
    root = directory/"model-inference"/"outputs"
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("Invalid model inference output directory")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("Invalid model result history limit")
    results = []
    if root.is_dir():
        for path in root.iterdir():
            if path.is_symlink() or not path.is_dir() or not IDENTIFIER.fullmatch(path.name):
                continue
            try:
                receipt,receipt_path = _receipt(directory,path.name)
                result = _result(receipt,project_id)
                result["modified_at"] = receipt_path.stat().st_mtime
                results.append(result)
            except (OSError,ValueError,KeyError,TypeError):
                continue
    return sorted(results,key=lambda value:value["modified_at"],reverse=True)[:limit]


def archive_dependencies(project,project_dir,cancel_event=None):
    """Return verified inert artifacts for the existing portable archive engine.

    Neither runtime profiles nor raw runs/checkpoints enter portable projects.
    Receipts retain their originating project ID; current-directory ownership
    and immutable file hashes supply the same portable authority as studio tools.
    """
    directory = Path(project_dir)
    parent = directory/"model-inference"
    root = parent/"outputs"
    if parent.is_symlink() or root.is_symlink():
        raise ValueError("Model inference archive directories cannot be symbolic links")
    records = []
    outputs = {}
    if root.exists():
        if not root.is_dir():
            raise ValueError("Model inference outputs must be a directory")
        for count,path in enumerate(root.iterdir(),1):
            if count>10000:
                raise ValueError("Model inference archive inventory exceeds 10,000 entries")
            if not IDENTIFIER.fullmatch(path.name):
                continue
            if path.is_symlink() or not path.is_dir():
                raise ValueError("Model inference archive output is not an owned directory")
            receipt,receipt_path = _receipt(directory,path.name)
            expected = {entry["filename"]:entry for entry in receipt["artifacts"]}
            if {member.name for member in path.iterdir()}!=set(expected)|{"provenance.json"}:
                raise ValueError("Model inference archive output differs from its complete receipt inventory")
            receipt_hash,receipt_bytes = _digest(receipt_path,8*1024*1024,cancel_event)
            prefix = "model-inference/outputs/"+path.name+"/"
            records.append({"path":prefix+"provenance.json","role":"model-inference-receipt","sha256":receipt_hash,"bytes":receipt_bytes})
            for name,entry in expected.items():
                member = _owned(directory,Path(prefix)/name)
                if _digest(member,cancel_event=cancel_event)!=(entry["sha256"],entry["bytes"]):
                    raise ValueError("A model inference archive artifact differs from its published identity")
                records.append({"path":prefix+name,"role":"model-inference-artifact","sha256":entry["sha256"],"bytes":entry["bytes"]})
            outputs[path.name] = (receipt,receipt_hash,expected)
    for asset in project.get("assets",[]):
        provenance = asset.get("provenance",{}) if isinstance(asset,dict) else {}
        kind = provenance.get("type") if isinstance(provenance,dict) else None
        if kind not in {"cinematicum-camera-ctrl","cinematicum-diffusionlight-display"}:
            continue
        output = outputs.get(provenance.get("output_id"))
        if output is None:
            raise ValueError("Generated model media is missing its retained inference artifacts")
        receipt,receipt_hash,entries = output
        model = "camera_ctrl" if kind=="cinematicum-camera-ctrl" else "diffusionlight"
        name = "output.mp4" if model=="camera_ctrl" else "preview.png"
        if (provenance.get("version")!=1 or provenance.get("receipt_sha256")!=receipt_hash or provenance.get("profile_sha256")!=receipt.get("profile_sha256")
                or receipt.get("model")!=model or receipt.get("operation")!="infer" or receipt.get("inference_executed") is not True
                or name not in entries or (entries[name]["sha256"],entries[name]["bytes"])!=(asset.get("sha256"),asset.get("size"))):
            raise ValueError("Generated model media differs from its retained source provenance")
        if model=="diffusionlight" and ("environment.exr" not in entries or provenance.get("linear_environment_sha256")!=entries["environment.exr"]["sha256"]):
            raise ValueError("A DiffusionLight display derivative is missing its exact HDR environment")
    return records


def submit(store,project_id,action,payload):
    if action not in {"doctor","infer"} or not isinstance(payload,dict):
        raise ValueError("Unknown model operation")
    model = _model(payload.get("model"))
    allowed = {"model"} if action=="doctor" else {"model","options"}|({"source_id"} if model=="diffusionlight" else set())
    if set(payload)!=allowed:
        raise ValueError("Model jobs accept only their typed options and admitted source identity")
    directory = store.project_dir(project_id)
    project = store.get(project_id)
    runtime,profile_sha = _profile(model)
    module = _implementation(model)
    options = None
    source_asset = None
    if action=="infer":
        options = module.validate_request(payload["options"]) if model=="camera_ctrl" else module.options(payload["options"])
        if model=="diffusionlight":
            source_asset = _photo(project,payload["source_id"])
    snapshot = {"model":model,"operation":action,"profile_sha256":profile_sha,"options":options,
                "source":{key:source_asset[key] for key in ("id","sha256","size")} if source_asset else None}

    def work(job_id,progress,event):
        current,current_sha = _profile(model)
        if current_sha!=profile_sha or current!=runtime:
            raise ValueError("The operator runtime profile changed while this job was queued; submit it again")
        run = _mkdir(directory,Path("model-inference")/"runs"/job_id)
        worker = run/"worker"
        progress(.02)
        if action=="doctor":
            if model=="camera_ctrl":
                report = module.doctor(runtime,worker,cancel_event=event)
            else:
                report = module.doctor(runtime,cancel_event=event)
            if event.is_set():
                raise RuntimeError("Model runtime verification cancelled")
            _write(run/"doctor.json",report)
            selected = {"doctor.json":run/"doctor.json"}
            if (worker/"worker.log").is_file() and (worker/"worker.log").stat().st_size>0:
                selected["worker.log"] = worker/"worker.log"
        elif model=="camera_ctrl":
            report = module.infer(runtime,options,worker,cancel_event=event)
            if (report.get("passed") is not True or report.get("inference_executed") is not True or report.get("inference_completed") is not True
                    or report.get("model_load_verified") is not True or report.get("conditioning",{}).get("verified") is not True or report.get("frame_count")!=16):
                raise RuntimeError("CameraCtrl did not return actual completed, conditioned model inference")
            video = _owned(run,Path("worker")/"output.mp4")
            if _digest(video,cancel_event=event)[0]!=report.get("video_sha256"):
                raise ValueError("The actual generated movie differs from its worker identity")
            report["independent_ffprobe"] = _movie(runtime,video,options,event)
            _write(run/"worker-result.json",report)
            selected = {"output.mp4":video,"conditioning.json":worker/"conditioning.json","worker-result.json":run/"worker-result.json"}
        else:
            source = _photo_copy(directory,source_asset,run,event)
            worker.mkdir()
            report = module.infer(runtime,source,source_asset["sha256"],worker,settings=options,cancel_event=event)
            if report.get("available") is not True or report.get("inference_executed") is not True:
                raise RuntimeError("DiffusionLight did not return actual completed HDR inference")
            for key,name in (("environment","environment.exr"),("preview","preview.png"),("provenance","provenance.json")):
                identity = report.get(key,{})
                path = _owned(run,Path("worker")/name)
                if identity.get("path")!=name or _digest(path,cancel_event=event)!=(identity.get("sha256"),identity.get("bytes")):
                    raise ValueError("The actual DiffusionLight output differs from its worker identity")
            hdr = report.get("hdr",{})
            if (hdr.get("width"),hdr.get("height"),hdr.get("channels"),hdr.get("dtype"))!=(512,256,3,"float32"):
                raise ValueError("DiffusionLight did not return its actual float32 HDR environment")
            for key in ("minimum","maximum","mean","standard_deviation","fraction_above_one"):
                value = hdr.get(key)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError("DiffusionLight returned invalid decoded HDR statistics")
            with _owned(run,Path("worker")/"environment.exr").open("rb") as stream:
                magic = stream.read(4)
            if magic!=b"\x76\x2f\x31\x01":
                raise ValueError("DiffusionLight output is not an actual OpenEXR")
            selected = {"environment.exr":worker/"environment.exr","preview.png":worker/"preview.png","worker-provenance.json":worker/"provenance.json"}
        if (worker/"worker.log").is_file() and (worker/"worker.log").stat().st_size>0:
            selected["worker.log"] = worker/"worker.log"
        progress(.98)
        return _publish(store,project_id,model,action,job_id,run,selected,report,profile_sha,snapshot,event)

    return store.submit(project_id,"model-"+model+"-"+action,work,snapshot)

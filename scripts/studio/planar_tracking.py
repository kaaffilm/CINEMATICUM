"""Owned planar analysis orchestration, source binding and measured motion.

The application process imports no NumPy/OpenCV. Its optional isolated worker
must demonstrate real feature/flow/homography operations before being offered.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

if __package__:
    from .projective_warp import (COORDINATES, IDENTITY, MAX_PLANAR_FRAMES, MAX_PLANAR_ANALYSIS_EDGE,
                                 MAX_PLANAR_DECODE_BYTES, MAX_PLANAR_TRACK_BYTES, invert, multiply,
                                 number, quad_matrix, transform, validate_matrix, validate_planar_motion, validate_quad)
else:
    from projective_warp import (COORDINATES, IDENTITY, MAX_PLANAR_FRAMES, MAX_PLANAR_ANALYSIS_EDGE,
                                 MAX_PLANAR_DECODE_BYTES, MAX_PLANAR_TRACK_BYTES, invert, multiply,
                                number, quad_matrix, transform, validate_matrix, validate_planar_motion, validate_quad)

ANALYSIS_EDGE = MAX_PLANAR_ANALYSIS_EDGE
WORKER = Path(__file__).with_name("planar_worker.py")


def _environment():
    env=os.environ.copy()
    for key in list(env):
        if key.startswith(("PYTHON","OCIO")):env.pop(key,None)
    env.update(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",VECLIB_MAXIMUM_THREADS="1")
    return env


def planar_capabilities(python=None):
    if __package__:
        from .imaging import find_imaging_python
    else:
        from imaging import find_imaging_python
    explicit=python or os.environ.get("CINEMATICUM_TRACKING_PYTHON")
    candidates=[explicit, str(Path.home()/"Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python"),
                find_imaging_python()]
    reasons=[];seen=set()
    for name in candidates:
        if not name or name in seen:continue
        seen.add(name);path=Path(name).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path,os.X_OK):continue
        try:
            result=subprocess.run([str(path),"-I","-B",str(WORKER),"--capabilities"],env=_environment(),
                                  capture_output=True,text=True,timeout=12)
            if result.returncode:raise ValueError(result.stderr.strip()[-500:])
            value=json.loads(result.stdout)
            if not value.get("runtime_operations_verified") or not value.get("available"):raise ValueError("Planar runtime did not pass its operation probe")
            return {**value,"python":str(path),"max_frames":MAX_PLANAR_FRAMES,"analysis_edge":ANALYSIS_EDGE,"max_decoded_bytes":MAX_PLANAR_DECODE_BYTES}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:reasons.append(str(exc))
    return {"available":False,"models":[],"reason":"Install the optional CINEMATICUM Tracking runtime to measure affine/projective motion. "
            +(reasons[-1] if reasons else "No isolated OpenCV runtime was found.")}


def _digest(path,cancel_event=None,deadline=None):
    value=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            if cancel_event is not None and cancel_event.is_set():raise RuntimeError("Planar tracking cancelled")
            if deadline is not None and time.monotonic()>deadline:raise RuntimeError("Planar tracking exceeded its two-minute processing limit")
            value.update(block)
    return value.hexdigest()


def _source(prepared,cancel_event=None,deadline=None):
    if __package__:
        from .tracking import _identity
    else:
        from tracking import _identity
    project,clip,asset,path=prepared[:4]
    if not isinstance(asset.get("sha256"),str) or len(asset["sha256"])!=64:
        raise ValueError("Import this original through CINEMATICUM before tracking; its admitted source hash is missing")
    digest=_digest(path,cancel_event,deadline)
    if digest!=asset["sha256"]:
        raise ValueError("The original source changed since admission; import the intended original again")
    return {**_identity(project,clip,asset),"sha256":digest}


def track_planar(project,project_dir,clip_id,request,progress=None,cancel_event=None):
    if __package__:
        from .tracking import _prepare, _decode_first, _run
    else:
        from tracking import _prepare, _decode_first, _run
    if __package__:
        from .engine import _executable
    else:
        from engine import _executable
    if not isinstance(request,dict) or set(request)-{"mode","quad","frame_start","frame_count"}:
        raise ValueError("Planar measurement accepts a model, four corners and an exact frame range")
    model=request.get("mode")
    if model not in {"affine","projective"}:raise ValueError("Choose affine or projective plane tracking")
    quad=validate_quad(request.get("quad"))
    prepared=_prepare(project,project_dir,clip_id,request)
    project,clip,asset,path,window,first,count,width,height=prepared
    if count>MAX_PLANAR_FRAMES:raise ValueError("Planar measurement supports at most 960 source-conformed frames")
    deadline=time.monotonic()+120
    identity=_source(prepared,cancel_event,deadline)
    runtime=planar_capabilities()
    if not runtime["available"]:raise ValueError(runtime["reason"])
    if progress:progress(.05)
    with tempfile.TemporaryDirectory(prefix="cinematicum-planar-track-") as temporary:
        directory=Path(temporary)
        chain,_,_=_decode_first(prepared,directory,cancel_event,deadline)
        raw=directory/"frames.gray"
        _run([_executable("ffmpeg"),"-hide_banner","-nostdin","-v","error","-threads","1",
              "-protocol_whitelist","file,pipe","-i",str(path),"-map",f"0:{asset['video_stream_index']}",
              "-vf",','.join(chain+["format=gray"]),"-frames:v",str(count),"-an","-threads","1",
              "-pix_fmt","gray","-f","rawvideo","pipe:1"],directory,"planar-decode",cancel_event,deadline,raw)
        if raw.stat().st_size!=width*height*count:raise ValueError("Not every requested planar frame could be decoded")
        if progress:progress(.35)
        manifest=directory/"request.json"
        manifest.write_text(json.dumps({"frames":str(raw),"width":width,"height":height,"count":count,
                                       "model":model,"quad":quad},allow_nan=False))
        output=directory/"result.json"
        _run([runtime["python"],"-I","-B",str(WORKER),"--request",str(manifest)],directory,"planar-measure",
             cancel_event,deadline,output,env=_environment())
        if output.stat().st_size>MAX_PLANAR_TRACK_BYTES:raise ValueError("Planar measurement exceeded its result bound")
        measured=json.loads(output.read_text())
        if _source(prepared,cancel_event,deadline)!=identity:raise ValueError("The original source changed during planar measurement")
    for sample in measured["samples"]:sample["frame"]+=first
    result={"version":1,"kind":"planar-track","coordinates":COORDINATES,"source":identity,
            "reference_frame":first,"reference_quad":quad,"analysis_width":width,"analysis_height":height,**measured}
    result=validate_planar_track(result,identity)
    if progress:progress(1)
    return result


def validate_planar_track(track,expected_source):
    if not isinstance(track,dict) or track.get("version")!=1 or track.get("kind")!="planar-track":
        raise ValueError("Expected a CINEMATICUM planar-track document")
    if len(json.dumps(track,allow_nan=False).encode())>MAX_PLANAR_TRACK_BYTES:raise ValueError("Planar track exceeds 2 MiB")
    if track.get("coordinates")!=COORDINATES or track.get("source")!=expected_source:
        raise ValueError("The planar track belongs to different source bytes, timing or coordinate conventions")
    model=track.get("model")
    if model not in {"affine","projective"}:raise ValueError("Planar measurement has an unsupported model")
    quad=validate_quad(track.get("reference_quad"))
    samples=track.get("samples")
    if not isinstance(samples,list) or not 1<=len(samples)<=MAX_PLANAR_FRAMES:raise ValueError("Planar tracks need 1–960 explicit measured frames")
    analysis_width=number(track.get("analysis_width"),"Analysis width",16,MAX_PLANAR_ANALYSIS_EDGE,True)
    analysis_height=number(track.get("analysis_height"),"Analysis height",16,MAX_PLANAR_ANALYSIS_EDGE,True)
    if analysis_width*analysis_height*len(samples)>MAX_PLANAR_DECODE_BYTES:
        raise ValueError("Planar track exceeds its decoded-window byte bound")
    result=[];previous=None
    for sample in samples:
        if not isinstance(sample,dict) or type(sample.get("visible")) is not bool:raise ValueError("Every planar sample needs explicit visibility")
        frame=number(sample.get("frame"),"Planar sample",0,expected_source["duration"]-1,True)
        if previous is not None and frame!=previous+1:raise ValueError("Planar samples cannot hide gaps")
        previous=frame
        visible=sample["visible"]
        features=number(sample.get("features"),"Measured feature count",0,1500,True)
        inliers=number(sample.get("inliers"),"Measured inlier count",0,features,True)
        ratio=number(sample.get("inlier_ratio"),"Inlier ratio",0,1)
        coverage=number(sample.get("coverage"),"Spatial coverage",0,1)
        confidence=number(sample.get("confidence"),"Geometric confidence",0,1)
        matrix=corners=error=None
        if visible:
            if inliers<16 or ratio<.6 or coverage<.12 or not math.isclose(ratio,inliers/features,abs_tol=1e-6):
                raise ValueError("A visible plane lacks declared geometric support")
            matrix=validate_matrix(sample.get("matrix"))
            if model=="affine" and any(abs(matrix[i]-IDENTITY[i])>1e-6 for i in (6,7,8)):
                raise ValueError("An affine track contains projective coefficients")
            corners=[transform(matrix,p) for p in quad]
            supplied=sample.get("corners")
            if not isinstance(supplied,list) or len(supplied)!=4:raise ValueError("Measured corners are missing")
            for actual,expected in zip(supplied,corners):
                if not isinstance(actual,list) or len(actual)!=2 or any(abs(number(a,"Measured corner",-8,8)-b)>1e-6 for a,b in zip(actual,expected)):
                    raise ValueError("Measured corners disagree with the full homography")
            error=number(sample.get("error_pixels"),"Median reprojection error",0,1.25)
        elif sample.get("matrix") is not None or sample.get("corners") is not None or confidence!=0:
            raise ValueError("A lost plane must not retain a fabricated transform or confidence")
        result.append({"frame":frame,"visible":visible,"matrix":matrix,"corners":corners,"confidence":confidence,
                       "features":features,"inliers":inliers,"inlier_ratio":ratio,"coverage":coverage,"error_pixels":error,
                       "reason":str(sample.get("reason",""))[:240]})
    if track.get("reference_frame")!=result[0]["frame"] or not result[0]["visible"] or any(abs(a-b)>1e-6 for a,b in zip(result[0]["matrix"],IDENTITY)):
        raise ValueError("The first measured planar frame must be the visible identity reference")
    return {"version":1,"kind":"planar-track","model":model,"coordinates":COORDINATES,"source":copy.deepcopy(expected_source),
            "reference_frame":result[0]["frame"],"reference_quad":quad,"samples":result,
            "analysis_width":analysis_width,
            "analysis_height":analysis_height,
            "backend":str(track.get("backend","imported"))[:160],"opencv":str(track.get("opencv",""))[:40],
            "numpy":str(track.get("numpy",""))[:40],"measurement_note":str(track.get("measurement_note",""))[:1024]}


def validate_planar_for_clip(project,project_dir,clip_id,track):
    if __package__:
        from .tracking import _prepare
    else:
        from tracking import _prepare
    prepared=_prepare(project,project_dir,clip_id,{"frame_count":1})
    return validate_planar_track(track,_source(prepared))


def planar_motion(project,project_dir,clip_id,track,mode="stabilize"):
    if __package__:
        from .tracking import _prepare
    else:
        from tracking import _prepare
    prepared=_prepare(project,project_dir,clip_id,{"frame_count":1})
    project,clip,asset=prepared[:3]
    track=validate_planar_track(track,_source(prepared))
    if mode not in {"stabilize","corner_pin"}:raise ValueError("Choose planar stabilization or corner pin")
    if any(not sample["visible"] for sample in track["samples"]):
        raise ValueError("The plane was lost. Shorten or remeasure a fully visible range before applying motion")
    pin=quad_matrix(track["reference_quad"])
    keys=[]
    for sample in track["samples"]:
        frame=sample["frame"]+clip.get("animation_offset",0)
        matrix=invert(sample["matrix"]) if mode=="stabilize" else multiply(_background_motion(clip,frame),multiply(sample["matrix"],pin))
        keys.append({"frame":frame,"matrix":matrix})
    value={"version":1,"mode":mode,"coordinates":COORDINATES,"canvas":{"width":asset["width"],"height":asset["height"]},
           "keys":keys,"outside":"identity" if mode=="stabilize" else "transparent",
           "source":{"track_backend":track["backend"],"model":track["model"],"source":track["source"],
                     "reference_frame":track["reference_frame"],"reference_quad":track["reference_quad"],
                     "tracked_clip_start":clip["start"],"track_sha256":hashlib.sha256(json.dumps(track,sort_keys=True,allow_nan=False).encode()).hexdigest()}}
    if mode=="corner_pin":value["source"]["tracked_transform"]=_authored_transform(clip)
    return validate_planar_motion(value,clip.get("animation_start",0),clip.get("animation_duration",clip["duration"]))


def _authored_transform(clip):
    """The parent transform copied by the authored corner-pin overlay."""
    fields=("x","y","scale","rotation")
    result={key:clip.get(key,1 if key=="scale" else 0) for key in fields}
    result["keyframes"]=[{key:value for key,value in frame.items() if key in (*fields,"frame","interpolation")}
                         for frame in clip.get("keyframes",[]) if any(key in frame for key in fields)]
    result["stabilization"]=_stabilization_identity(clip)
    return result


def _stabilization_identity(clip):
    # Measurement keys are not editable in the UI. Bind their immutable
    # measurement identity without copying a second measured-matrix document into
    # every overlay. Source timing has its own exact binding.
    return {name:{"track_sha256":motion.get("source",{}).get("track_sha256"),
                  "invalidated":motion.get("invalidated")}
            for name in ("tracking","planar_motion") if (motion:=clip.get(name)) is not None}


def _background_motion(clip,frame):
    """Place a pin on the plane as displayed after background stabilization."""
    matrix=IDENTITY
    planar=clip.get("planar_motion")
    if planar:
        if planar.get("invalidated"):
            raise ValueError("Remeasure or remove stale background stabilization before creating a corner pin")
        if planar["mode"]!="stabilize":raise ValueError("The measured video has an unsupported planar transform")
        matrix=next((key["matrix"] for key in planar["keys"] if key["frame"]==frame),IDENTITY)
    point=clip.get("tracking")
    if point:
        keys=point["keys"]
        left=max((key for key in keys if key["frame"]<=frame),key=lambda key:key["frame"],default=keys[0])
        right=min((key for key in keys if key["frame"]>=frame),key=lambda key:key["frame"],default=keys[-1])
        amount=(frame-left["frame"])/(right["frame"]-left["frame"]) if right["frame"]!=left["frame"] else 0
        x=left["x"]+(right["x"]-left["x"])*amount;y=left["y"]+(right["y"]-left["y"])*amount
        matrix=multiply([1.,0.,x,0.,1.,y,0.,0.,1.],matrix)
    return matrix


def validate_planar_binding(motion,project,clip,assets):
    """Call after all clips/assets are normalized; source edits must clear motion."""
    if __package__:
        from .tracking import _identity
    else:
        from tracking import _identity
    if motion.get("invalidated"):
        return
    source=motion["source"].get("source")
    if not isinstance(source,dict):raise ValueError("Planar motion lacks its exact measured source binding")
    tracked=clip if motion["mode"]=="stabilize" else next((c for c in project["clips"] if c["id"]==source.get("clip_id")),None)
    if tracked is None or tracked.get("asset_id") not in assets:raise ValueError("The measured background clip is missing; remove or remeasure its corner pin")
    if tracked.get("retime"):raise ValueError("Remove dependent measured planar motion before applying a variable-speed source clock")
    asset=assets[tracked["asset_id"]]
    if asset.get("kind")!="video":raise ValueError("A measured planar background must be an owned video source")
    identity=_identity(project,tracked,asset)
    if source!=identity:raise ValueError("Measured planar source/timing changed; remove the planar motion and measure this range again")
    if motion["canvas"]!={"width":asset["width"],"height":asset["height"]}:raise ValueError("Planar canvas differs from its measured source")
    if motion["mode"]=="corner_pin":
        if tracked["start"]!=motion["source"].get("tracked_clip_start"):raise ValueError("The measured background moved on the timeline; recreate the corner pin")
        if assets.get(clip.get("asset_id"),{}).get("kind")!="image":raise ValueError("Measured corner pins currently require an owned image overlay")
        if clip["start"]-tracked["start"]+tracked.get("animation_offset",0)!=clip.get("animation_offset",0):
            raise ValueError("The corner-pin image moved out of sync with its measured background; clear or recreate its planar motion")
        if clip.get("speed",1)!=1 or clip.get("reverse",False):
            raise ValueError("Measured corner-pin images use the original project clock; clear planar motion before retiming")
        if clip.get("track",0)<=tracked.get("track",0):
            raise ValueError("A corner-pin image must remain on a picture track above its measured background")
        if "tracked_transform" in motion["source"] and motion["source"]["tracked_transform"]!=_authored_transform(tracked):
            raise ValueError("The measured background transform changed; recreate its corner pin")


def assert_planar_export_ready(project):
    """An editable stale measurement is never an accepted delivery state."""
    stale=[clip["id"] for sequence in [project]+project.get("sequences",[])
           for clip in sequence.get("clips",[]) if clip.get("planar_motion",{}).get("invalidated")]
    if stale:
        raise ValueError("Planar motion is stale on "+", ".join(stale[:8])+". Remeasure or explicitly remove it before exporting.")


def verify_planar_source_files(project,project_dir,cancel_event=None):
    """Rehash measured originals once before any paused-frame/movie graph.

    Metadata binding validation alone cannot detect later byte replacement at
    an admitted path. Active and stored sequence motions share one deduplicated
    check. Overlay images remain ordinary editable inputs; only measured
    backgrounds are bound to their exact original bytes.
    """
    if __package__:
        from .engine import _media_path
    else:
        from engine import _media_path
    assets={asset["id"]:asset for asset in project.get("assets",[])}
    expected={}
    for sequence in [project]+project.get("sequences",[]):
        for clip in sequence.get("clips",[]):
            motion=clip.get("planar_motion")
            if motion is None or motion.get("invalidated"):continue
            source=motion.get("source",{}).get("source",{})
            ident=source.get("asset_id");digest=source.get("sha256")
            if ident not in assets or not isinstance(digest,str) or len(digest)!=64:
                raise ValueError("Measured planar source identity is missing; remove or remeasure its motion")
            if ident in expected and expected[ident]!=digest:
                raise ValueError("Planar motions disagree about their measured original source bytes")
            expected[ident]=digest
    deadline=time.monotonic()+120
    for ident,digest in expected.items():
        path=_media_path(project_dir,assets[ident]["path"])
        if _digest(path,cancel_event,deadline)!=digest:
            raise ValueError("A measured planar original changed on disk; remove its motion and import the intended original again")
    return {"sources_verified":len(expected)}

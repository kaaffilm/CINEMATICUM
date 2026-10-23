"""Source-bound checkerboard calibration through an isolated OpenCV worker.

The main application imports no NumPy/OpenCV. Calibration remains a measured
proposal; it never changes footage, chooses a camera profile or estimates
rolling-shutter timing from static target views.
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
import tempfile
import time
import zipfile

ARTIFACT_NAMES=frozenset({"calibration.json","observations.json","opencv.yml","corners.zip","preview.png","provenance.json"})
MAX_ARTIFACT_BYTES=128*1024*1024
MAX_SECONDS=900
MAX_IMAGES=40
_ID=re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def _json(value):return (json.dumps(value,sort_keys=True,allow_nan=False,indent=2)+"\n").encode()


def _number(value,name,low,high,integer=False):
    try:valid=(not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high and (not integer or int(value)==value))
    except OverflowError:valid=False
    if not valid:
        raise ValueError(name+" is outside its finite supported range.")
    return int(value) if integer else float(value)


def default_settings():
    return {"version":1,"asset_ids":[],"columns":8,"rows":6,"square_size_mm":25.,
            "radial_terms":2,"same_optics_confirmed":False,"require_all_images":True}


def validate_settings(value):
    defaults=default_settings()
    if not isinstance(value,dict) or set(value)-set(defaults) or type(value.get("version")) is not int or value["version"]!=1:
        raise ValueError("Unsupported checkerboard calibration settings.")
    result={**defaults,**copy.deepcopy(value)};ids=result["asset_ids"]
    if not isinstance(ids,list) or len(ids)>MAX_IMAGES or any(not isinstance(v,str) or not _ID.fullmatch(v) for v in ids) or len(set(ids))!=len(ids):
        raise ValueError("Choose at most 40 unique admitted photograph identities.")
    for key,low,high in (("columns",4,15),("rows",4,12)):
        result[key]=_number(result[key],key,low,high,True)
    if result["columns"]*result["rows"]>180:raise ValueError("The checkerboard exceeds its corner-count bound.")
    result["square_size_mm"]=_number(result["square_size_mm"],"Physical square pitch",1,1000)
    if type(result["radial_terms"]) is not int or result["radial_terms"] not in {2,3}:raise ValueError("Choose two or three radial terms.")
    for key in ("same_optics_confirmed","require_all_images"):
        if type(result[key]) is not bool:raise ValueError(key+" must be explicit true or false.")
    return result


def validate_recipe(value,project):
    if not isinstance(value,dict) or set(value)!={"operation","settings"} or value.get("operation")!="calibrate_checkerboard":
        raise ValueError("Choose the measured checkerboard lens-calibration operation.")
    settings=validate_settings(value["settings"])
    if not settings["same_optics_confirmed"]:raise ValueError("Confirm that all photographs use the same fixed focus, zoom and image geometry.")
    if not 12<=len(settings["asset_ids"])<=MAX_IMAGES:raise ValueError("Select 12–40 overlapping checkerboard views with varied target poses.")
    dimensions=set();pixels=0
    for ident in settings["asset_ids"]:
        matches=[a for a in project.get("assets",[]) if isinstance(a,dict) and a.get("id")==ident]
        if len(matches)!=1 or matches[0].get("kind")!="image":raise ValueError("Calibration inputs must be admitted still photographs.")
        asset=matches[0]
        if Path(asset.get("path","")).suffix.lower() not in {".png",".jpg",".jpeg"}:raise ValueError("Calibration accepts opaque eight-bit PNG or JPEG photographs.")
        width=_number(asset.get("width"),"Calibration width",64,2048,True)
        height=_number(asset.get("height"),"Calibration height",64,2048,True)
        if width*height>4*1024*1024:raise ValueError("Calibration photographs are bounded to four megapixels.")
        pixels+=width*height;dimensions.add((width,height))
    if len(dimensions)!=1:raise ValueError("All calibration photographs must have the same stored pixel dimensions.")
    if pixels>128*1024*1024:raise ValueError("Calibration exceeds its 128-megapixel aggregate input budget.")
    return {"operation":"calibrate_checkerboard","settings":settings}


def _command(python=None):
    from imaging import find_imaging_python
    explicit=python or os.environ.get("CINEMATICUM_TRACKING_PYTHON")
    candidates=[explicit] if explicit else [
        str(Path.home()/"Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python"),
        str(Path.home()/".local/share/CINEMATICUM/Tracking/py312-v1/bin/python"),find_imaging_python()]
    for name in candidates:
        if not name:continue
        path=Path(name).expanduser()
        if path.is_absolute() and path.is_file() and os.access(path,os.X_OK):
            return [str(path),"-I","-B",str(Path(__file__).with_name("lens_calibration_worker.py"))]
    raise RuntimeError("The isolated OpenCV Tracking runtime is unavailable. Runtime setup must provide its Python executable.")


def _environment():
    env={key:value for key,value in os.environ.items() if not key.startswith(("PYTHON","OCIO"))}
    env.update(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",VECLIB_MAXIMUM_THREADS="1")
    return env


def capabilities(python=None):
    result={"available":False,"operations":[],"runtime_operations_verified":False,"reason":None,
        "limits":{"photos":MAX_IMAGES,"seconds":MAX_SECONDS,"image_edge":2048,"aggregate_megapixels":128},
        "scope":"Actual checkerboard detection and Brown calibration with held-out views, observability gates and conditional covariance; no rolling-shutter timing or automatic lens identity match."}
    try:
        response=subprocess.run(_command(python)+["--doctor"],capture_output=True,env=_environment(),timeout=15)
        if len(response.stdout)>65536 or response.returncode:raise RuntimeError("The calibration runtime did not pass its bounded operation probe.")
        doctor=json.loads(response.stdout)
        if not doctor.get("available") or not doctor.get("runtime_operations_verified"):raise RuntimeError("The calibration worker did not verify its actual detector/projection APIs.")
        result.update(available=True,operations=["calibrate_checkerboard"],runtime_operations_verified=True,
                      opencv=doctor.get("opencv"),numpy=doctor.get("numpy"))
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:result["reason"]=str(exc)
    return result


def _check(event,deadline):
    if event is not None and event.is_set():raise InterruptedError("Lens calibration cancelled.")
    if time.monotonic()>deadline:raise TimeoutError("Lens calibration exceeded its owned 15-minute execution budget.")


def _stop(process):
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    if process.poll() is None:
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    if process.poll() is None:process.wait(timeout=2)


def _worker(command,request,scratch,event,deadline):
    _check(event,deadline);manifest=Path(scratch)/"request.json";manifest.write_bytes(_json(request))
    output=Path(scratch)/"worker.json";errors=Path(scratch)/"worker.stderr"
    with output.open("wb") as out,errors.open("wb") as err:
        process=subprocess.Popen(command+["--request",str(manifest)],cwd=scratch,stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,env=_environment(),start_new_session=True)
        try:
            while process.poll() is None:
                _check(event,deadline)
                if output.stat().st_size>65536 or errors.stat().st_size>8*1024*1024:raise RuntimeError("Calibration exceeded its diagnostic output budget.")
                event.wait(.1) if event is not None else time.sleep(.1)
            _check(event,deadline)
        finally:_stop(process)
    if output.stat().st_size>65536 or errors.stat().st_size>8*1024*1024:raise RuntimeError("Calibration exceeded its diagnostic output budget.")
    if process.returncode:raise RuntimeError("Measured calibration failed: "+errors.read_text(errors="replace")[-2400:])
    result=json.loads(output.read_text())
    if not isinstance(result,dict) or result.get("error"):raise RuntimeError("The calibration worker did not return a successful result.")
    return result


def _rotation(value):
    if not isinstance(value,list) or len(value)!=9:raise ValueError("A measured board pose lacks its rotation.")
    r=[_number(v,"Board rotation",-1.001,1.001) for v in value]
    for a in range(3):
        for b in range(3):
            if abs(sum(r[a*3+k]*r[b*3+k] for k in range(3))-(1 if a==b else 0))>2e-3:raise ValueError("A board rotation is not orthonormal.")
    a,b,c,d,e,f,g,h,i=r
    if abs(a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)-1)>2e-3:raise ValueError("A board pose has a reflected coordinate frame.")
    return r


def validate_measurement(calibration,observations,settings,width,height):
    """Independently verify physical projection and the published uncertainty shape."""
    if (not isinstance(calibration,dict) or type(calibration.get("version")) is not int or calibration.get("version")!=1 or calibration.get("kind")!="checkerboard-lens-calibration" or
            calibration.get("image_size")!={"width":width,"height":height}):raise ValueError("Calibration belongs to a different image canvas.")
    if not isinstance(observations,dict) or type(observations.get("version")) is not int or observations.get("version")!=1 or observations.get("kind")!="checkerboard-observations":
        raise ValueError("Calibration lacks its actual measured target observations.")
    if (calibration.get("settings")!=settings or calibration.get("pixel_convention")!="zero-based-integer-pixel-centers" or
            observations.get("pixel_convention")!="zero-based-integer-pixel-centers" or
            observations.get("board")!={"columns":settings["columns"],"rows":settings["rows"],"square_size_mm":settings["square_size_mm"]}):
        raise ValueError("Calibration target settings or pixel conventions differ from their admitted request.")
    matrix=calibration.get("camera_matrix");dist=calibration.get("distortion")
    if not isinstance(matrix,list) or len(matrix)!=3 or any(not isinstance(row,list) or len(row)!=3 for row in matrix):raise ValueError("Invalid measured camera matrix.")
    k=[[_number(v,"Camera matrix",-100000,100000) for v in row] for row in matrix]
    if k[0][0]<=0 or k[1][1]<=0 or any(abs(k[r][c]-(1 if (r,c)==(2,2) else 0))>1e-8 for r,c in ((0,1),(1,0),(2,0),(2,1),(2,2))):raise ValueError("Calibration needs the declared zero-skew pinhole matrix.")
    if not isinstance(dist,list) or len(dist)!=5:raise ValueError("Calibration requires exactly five Brown distortion coefficients.")
    dist=[_number(v,"Measured Brown coefficient",-10,10) for v in dist]
    if settings["radial_terms"]==2 and abs(dist[4])>1e-12:raise ValueError("The fixed third radial coefficient changed.")
    order=["fx","fy","cx","cy","k1","k2","p1","p2"]+(["k3"] if settings["radial_terms"]==3 else [])
    if calibration.get("parameter_order")!=order:raise ValueError("Covariance parameter order differs from its fitted model.")
    covariance=calibration.get("covariance");n=len(order)
    if not isinstance(covariance,list) or len(covariance)!=n or any(not isinstance(row,list) or len(row)!=n for row in covariance):raise ValueError("Calibration lacks its full estimated-parameter covariance matrix.")
    covariance=[[_number(v,"Conditional covariance",-1e12,1e12) for v in row] for row in covariance]
    chol=[[0.]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1):
            if abs(covariance[i][j]-covariance[j][i])>1e-7*max(1,abs(covariance[i][j])):raise ValueError("Calibration covariance is not symmetric.")
            residual=covariance[i][j]-sum(chol[i][m]*chol[j][m] for m in range(j))
            if i==j:
                if residual<=0:raise ValueError("Calibration covariance is singular or not positive definite.")
                chol[i][j]=math.sqrt(residual)
            else:chol[i][j]=residual/chol[j][j]
    views=calibration.get("views");measured=observations.get("views")
    if not isinstance(views,list) or not isinstance(measured,list) or not 12<=len(views)<=MAX_IMAGES or len(views)!=len(measured):raise ValueError("Calibration lacks its complete accepted view inventory.")
    by_id={v.get("asset_id"):v for v in measured if isinstance(v,dict)}
    ids=[v.get("asset_id") for v in views if isinstance(v,dict)]
    if len(ids)!=len(views) or len(set(ids))!=len(ids) or set(ids)!=set(by_id) or not set(ids)<=set(settings["asset_ids"]):raise ValueError("Calibration views do not match the selected photographs.")
    if settings["require_all_images"] and set(ids)!=set(settings["asset_ids"]):raise ValueError("Calibration omitted a required source photograph.")
    rejected=observations.get("rejected",[])
    if not isinstance(rejected,list) or len(rejected)>MAX_IMAGES:raise ValueError("Calibration rejected-view inventory is invalid.")
    rejected_ids=[]
    for record in rejected:
        if not isinstance(record,dict) or not isinstance(record.get("reason"),str) or not 1<=len(record["reason"])<=512:
            raise ValueError("Every omitted calibration photograph needs its explicit bounded reason.")
        rejected_ids.append(record.get("asset_id"))
    if (len(set(rejected_ids))!=len(rejected_ids) or set(rejected_ids)&set(ids) or
            set(rejected_ids)|set(ids)!=set(settings["asset_ids"])):
        raise ValueError("Accepted and rejected calibration views do not account for every admitted input.")
    square=settings["square_size_mm"]/1000;count=settings["columns"]*settings["rows"];train=holdout=0
    for view in views:
        r=_rotation(view.get("rotation"));t=view.get("translation")
        if not isinstance(t,list) or len(t)!=3:raise ValueError("A board pose lacks its measured translation.")
        t=[_number(v,"Board translation",-10000,10000) for v in t]
        corners=by_id[view["asset_id"]].get("corners")
        if not isinstance(corners,list) or len(corners)!=count:raise ValueError("A target observation omitted expected corners.")
        sse=0.
        for index,corner in enumerate(corners):
            if not isinstance(corner,list) or len(corner)!=2:raise ValueError("An observed checkerboard corner is invalid.")
            u=_number(corner[0],"Observed X",0,width-1);v=_number(corner[1],"Observed Y",0,height-1)
            x=(index%settings["columns"])*square;y=(index//settings["columns"])*square
            q=[r[row*3]*x+r[row*3+1]*y+t[row] for row in range(3)]
            if q[2]<=1e-9:raise ValueError("The measured target lies behind its calibrated camera.")
            x,y=q[0]/q[2],q[1]/q[2];r2=x*x+y*y;k1,k2,p1,p2,k3=dist
            radial=1+k1*r2+k2*r2*r2+k3*r2*r2*r2
            xd=x*radial+2*p1*x*y+p2*(r2+2*x*x);yd=y*radial+p1*(r2+2*y*y)+2*p2*x*y
            sse+=(k[0][0]*xd+k[0][2]-u)**2+(k[1][1]*yd+k[1][2]-v)**2
        rms=math.sqrt(sse/count);declared=_number(view.get("rms_pixels"),"Measured view RMS",0,2)
        if abs(rms-declared)>2e-4:raise ValueError("Calibration reprojection RMS disagrees with its observed corners and physical model.")
        if type(view.get("training")) is not bool:raise ValueError("Every measured view needs explicit training/holdout provenance.")
        if view["training"]:train+=1
        else:holdout+=1
    if train<8 or holdout<2:raise ValueError("Calibration requires independent held-out target poses.")
    diagnostic=calibration.get("quality",{}).get("observability",{})
    if diagnostic.get("rank")!=n or not 1<=_number(diagnostic.get("condition"),"Intrinsic information condition",1,1e10)<=1e10:
        raise ValueError("The measured calibration is not locally identifiable within its declared conditioning bound.")
    if calibration.get("rolling_shutter",{}).get("estimated") is not False:raise ValueError("Static target calibration cannot claim a measured rolling-shutter readout.")
    return calibration


def profile_proposal(calibration):
    width=calibration["image_size"]["width"];height=calibration["image_size"]["height"];k=calibration["camera_matrix"];d=calibration["distortion"]
    params={"model":"brown","direction":"undistort","fx":k[0][0]/width,"fy":k[1][1]/height,
        "cx":k[0][2]/width,"cy":k[1][2]/height,"k1":d[0],"k2":d[1],"p1":d[2],"p2":d[3],"k3":d[4]}
    from compositor import validate_graph
    graph={"version":1,"nodes":[{"id":"source","type":"source","inputs":[],"params":{}},
        {"id":"calibrated_lens","type":"lens_distortion","inputs":["source"],"params":params}],"output":"calibrated_lens"}
    params=validate_graph(graph)["nodes"][1]["params"]
    return {"version":1,"reference_image_size":calibration["image_size"],"pixel_convention":"zero-based integer pixel centers",
        "normalization":"fx and cx divided by width; fy and cy divided by height; uniform resizing with identical aspect/orientation only",
        "params":params}


def run(project,project_dir,recipe,output_dir,progress=None,cancel_event=None,python=None):
    import imaging as core
    recipe=validate_recipe(recipe,project);settings=recipe["settings"];deadline=time.monotonic()+MAX_SECONDS
    _check(cancel_event,deadline);command=_command(python);root=Path(project_dir).absolute();output=Path(output_dir).absolute()
    try:relative=output.relative_to(root)
    except ValueError as exc:raise ValueError("Calibration output must remain inside its project.") from exc
    if len(relative.parts)!=3 or relative.parts[:2]!=("lens-calibration","outputs") or not re.fullmatch(r"[a-f0-9]{32}",relative.name):raise ValueError("Calibration requires its exact owned job output identity.")
    parent=core._owned(root,"lens-calibration/outputs",is_dir=True,create=True)
    if os.path.lexists(output):raise ValueError("An existing calibration output cannot be overwritten.")
    inputs=[];originals=[];total=0
    with tempfile.TemporaryDirectory(prefix=".calibration-",dir=parent) as temporary:
        scratch=Path(temporary);copies=scratch/"sources";copies.mkdir();generated=scratch/"result";generated.mkdir()
        for index,ident in enumerate(settings["asset_ids"]):
            _check(cancel_event,deadline);asset=next(a for a in project["assets"] if a["id"]==ident);source=core._owned(root,asset["path"])
            digest,size=core._hash_file(source,32*1024*1024);total+=size
            if total>512*1024*1024:raise ValueError("Calibration exceeds its 512-MiB source byte budget.")
            if (digest,size)!=(asset.get("sha256"),asset.get("size")):raise ValueError("A calibration photograph changed since admission.")
            copy_path=copies/(f"{index:03d}_"+ident+source.suffix.lower());shutil.copyfile(source,copy_path)
            if core._hash_file(copy_path,32*1024*1024)!=(digest,size):raise ValueError("A calibration photograph changed while being staged.")
            inputs.append({"asset_id":ident,"sha256":digest,"bytes":size,"filename":copy_path.name,"width":asset["width"],"height":asset["height"]})
            originals.append((source,digest,size))
        if progress:progress(.1)
        request={"command":"calibrate","settings":settings,"inputs":[{"asset_id":record["asset_id"],"path":str(copies/record["filename"]),
            "width":record["width"],"height":record["height"]} for record in inputs],"output_dir":str(generated)}
        worker=_worker(command,request,scratch,cancel_event,deadline)
        if progress:progress(.8)
        for name in ("calibration.json","observations.json","opencv.yml"):core._hash_file(generated/name,4*1024*1024)
        calibration=json.loads((generated/"calibration.json").read_text());observations=json.loads((generated/"observations.json").read_text())
        validate_measurement(calibration,observations,settings,inputs[0]["width"],inputs[0]["height"])
        source_by_id={record["asset_id"]:record for record in inputs}
        for view in observations["views"]:
            if view.get("sha256")!=source_by_id[view["asset_id"]]["sha256"]:raise ValueError("Measured corners do not bind to the admitted source photograph bytes.")
        for record in inputs:
            if core._hash_file(copies/record["filename"],32*1024*1024)!=(record["sha256"],record["bytes"]):
                raise ValueError("A staged photograph changed during measured calibration.")
        try:profile=profile_proposal(calibration);proposal_error=None
        except ValueError as exc:profile=None;proposal_error=str(exc)
        corners=generated/"corners"
        if corners.exists():
            if corners.is_symlink() or not corners.is_dir():raise ValueError("Calibration previews escaped their owned output directory.")
            names=list(corners.iterdir())
            if len(names)>MAX_IMAGES:raise ValueError("Calibration returned too many diagnostic previews.")
            with zipfile.ZipFile(generated/"corners.zip","w",compression=zipfile.ZIP_STORED) as archive:
                for image in sorted(names):
                    _check(cancel_event,deadline)
                    if not _ID.fullmatch(image.stem) or image.suffix!=".png":raise ValueError("Invalid calibration preview identity.")
                    core._hash_file(image,4*1024*1024);archive.write(image,image.name)
            if names:shutil.copyfile(sorted(names)[0],generated/"preview.png")
            shutil.rmtree(corners)
        if not {p.name for p in generated.iterdir()}<=ARTIFACT_NAMES-{"provenance.json"}:raise ValueError("Calibration returned an unexpected artifact inventory.")
        for source,digest,size in originals:
            if core._hash_file(source,32*1024*1024)!=(digest,size):raise ValueError("A source photograph changed during calibration.")
        artifacts=[];total=0
        for path in sorted(generated.iterdir()):
            digest,size=core._hash_file(path,MAX_ARTIFACT_BYTES);total+=size;artifacts.append({"filename":path.name,"sha256":digest,"bytes":size,"size":size})
        if total>MAX_ARTIFACT_BYTES:raise ValueError("Calibration outputs exceed their 128-MiB publication budget.")
        receipt={"type":"cinematicum-lens-calibration","version":1,"operation":"calibrate_checkerboard","settings":settings,"inputs":inputs,
            "engine":worker.get("engine"),"quality":calibration["quality"],"lens_profile":profile,"proposal_error":proposal_error,
            "scope":"Measured fixed-optics Brown calibration from actual checkerboard detections. Covariance is conditional on the stated target/noise model. No automatic lens identity match, metric target certification or rolling-shutter readout estimate.",
            "artifacts":artifacts,"source_sha256":{p.name:core._hash_file(p,1024*1024)[0] for p in (Path(__file__),Path(__file__).with_name("lens_calibration_worker.py"))}}
        (generated/"provenance.json").write_bytes(_json(receipt));digest,size=core._hash_file(generated/"provenance.json",4*1024*1024)
        if total+size>MAX_ARTIFACT_BYTES:raise ValueError("Calibration provenance exceeds its publication budget.")
        _check(cancel_event,deadline);os.rename(generated,output)
    if progress:progress(1)
    return {"output_id":relative.name,"settings":settings,"lens_profile":profile,"proposal_error":proposal_error,
        "quality":calibration["quality"],"calibration":calibration,"receipt":receipt,
        "artifacts":[*artifacts,{"filename":"provenance.json","sha256":digest,"bytes":size,"size":size}]}

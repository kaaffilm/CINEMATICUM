"""Isolated measured checkerboard lens calibration; imports OpenCV only here.

All coordinates passed to OpenCV are zero-based pixel-center coordinates.
Training and held-out observations stay separate. Reported covariance is a
local least-squares estimate conditional on a rigid metric board, the selected
Brown model, and independent equal-variance pixel-coordinate errors.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MAX_VIEWS=40
MIN_VIEWS=12
MAX_PIXELS=2048*2048
MAX_IMAGE_BYTES=32*1024*1024
MAX_CONDITION=1e7
PARAMETERS=("fx","fy","cx","cy","k1","k2","p1","p2","k3")
OPENCV_PARAMETERS=(*PARAMETERS,"k4","k5","k6","s1","s2","s3","s4","tau_x","tau_y")
PIXEL_CONVENTION="zero-based-integer-pixel-centers"
_ID=re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def runtime():
    # OpenCV reads this before decoding. Header limits complement the checks
    # on the actual stored pixel dimensions after IMREAD_UNCHANGED.
    os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"]=str(MAX_PIXELS)
    import cv2 as cv
    import numpy as np
    cv.setNumThreads(1)
    cv.setRNGSeed(0)
    return cv,np


def _finite(value,name,low,high,integer=False):
    try:admitted=not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high and (not integer or int(value)==value)
    except (OverflowError,ValueError):admitted=False
    if not admitted:
        raise ValueError(name+" is outside its supported range")
    return int(value) if integer else float(value)


def settings(value):
    required={"version","asset_ids","columns","rows","square_size_mm","radial_terms","same_optics_confirmed","require_all_images"}
    if not isinstance(value,dict) or set(value)!=required or type(value.get("version")) is not int or value["version"]!=1:
        raise ValueError("Expected the complete version-1 checkerboard calibration settings")
    ids=value["asset_ids"]
    if not isinstance(ids,list) or not MIN_VIEWS<=len(ids)<=MAX_VIEWS or any(not isinstance(v,str) or not _ID.fullmatch(v) for v in ids) or len(set(ids))!=len(ids):
        raise ValueError("Calibration needs 12–40 distinct admitted still photographs")
    result=dict(value)
    result["columns"]=_finite(value["columns"],"Inner-corner columns",4,15,True)
    result["rows"]=_finite(value["rows"],"Inner-corner rows",4,12,True)
    result["square_size_mm"]=_finite(value["square_size_mm"],"Measured square size in millimeters",1.,1000.)
    if type(value["radial_terms"]) is not int or value["radial_terms"] not in (2,3):raise ValueError("Choose two or three Brown radial coefficients")
    if value["same_optics_confirmed"] is not True:raise ValueError("Confirm the same lens, focus, zoom and stored-image geometry for every calibration view")
    if type(value["require_all_images"]) is not bool:raise ValueError("The all-images detection policy must be explicit")
    return result


def request(value):
    if not isinstance(value,dict) or set(value)!={"command","settings","inputs","output_dir"} or value["command"]!="calibrate":
        raise ValueError("Expected an owned checkerboard calibration request")
    config=settings(value["settings"]);inputs=value["inputs"]
    if not isinstance(inputs,list) or len(inputs)!=len(config["asset_ids"]):raise ValueError("Calibration input count does not match its selected photographs")
    dimensions=set();paths=set()
    for item,ident in zip(inputs,config["asset_ids"]):
        if not isinstance(item,dict) or set(item)!={"asset_id","path","width","height"} or item["asset_id"]!=ident:
            raise ValueError("Calibration input identities or order differ from the selected photographs")
        w=_finite(item["width"],"Stored image width",64,2048,True);h=_finite(item["height"],"Stored image height",64,2048,True)
        if w*h>MAX_PIXELS:raise ValueError("A calibration photograph exceeds four megapixels")
        if not isinstance(item["path"],str):raise ValueError("Calibration input paths must be absolute staged image files")
        path=Path(item["path"])
        if not path.is_absolute() or path.suffix.lower() not in (".png",".jpg",".jpeg") or str(path) in paths:
            raise ValueError("Calibration inputs must be distinct absolute PNG/JPEG files")
        dimensions.add((w,h));paths.add(str(path))
    if len(dimensions)!=1:raise ValueError("All calibration views must retain identical stored pixel dimensions")
    if not isinstance(value["output_dir"],str) or not Path(value["output_dir"]).is_absolute():raise ValueError("Calibration output needs its absolute owned directory")
    return config,inputs,next(iter(dimensions)),Path(value["output_dir"])


def object_points(config,np):
    # OpenCV's point collection API requires Point3f, not float64 arrays.
    result=np.zeros((config["rows"]*config["columns"],3),dtype=np.float32)
    result[:,:2]=np.array([(x,y) for y in range(config["rows"]) for x in range(config["columns"])],np.float32)*config["square_size_mm"]
    return result


def _points(value,count,width,height,np):
    result=np.asarray(value,dtype=np.float64)
    if result.shape!=(count,2) or not np.isfinite(result).all() or np.any(result[:,0]<0) or np.any(result[:,0]>width-1) or np.any(result[:,1]<0) or np.any(result[:,1]>height-1):
        raise ValueError("Detected checkerboard corners do not form a complete finite in-image pixel array")
    return np.ascontiguousarray(result.reshape(-1,1,2),dtype=np.float32)


def _rms(cv,np,obj,points,rvec,tvec,K,D):
    projected,jac=cv.projectPoints(obj,rvec,tvec,K,D)
    residual=projected.reshape(-1,2).astype(np.float64)-points.reshape(-1,2)
    rotation=cv.Rodrigues(rvec)[0]
    depths=(rotation@obj.astype(np.float64).T+np.asarray(tvec).reshape(3,1))[2]
    if not np.isfinite(projected).all() or np.any(depths<=0):raise ValueError("A solved target pose projects behind the camera or has invalid pixels")
    return math.sqrt(float(np.sum(residual*residual))/len(obj)),residual,jac,rotation


def _coverage(points,width,height,cv,np):
    hull=cv.convexHull(np.concatenate([v.reshape(-1,2) for v in points]).astype(np.float32))
    centers=np.array([v.reshape(-1,2).mean(axis=0) for v in points],np.float32)
    center_hull=cv.convexHull(centers)
    return {"aggregate_coverage":float(cv.contourArea(hull)/(width*height)),
            "centroid_coverage":float(cv.contourArea(center_hull)/(width*height)),
            "centroid_span_x":float(np.ptp(centers[:,0])/width),
            "centroid_span_y":float(np.ptp(centers[:,1])/height)}


def _uncertainty(jacobians,residuals,width,height,free,np):
    scales=np.array([width,height,width,height,*([1.]*(len(free)-4))],np.float64)
    reduced=[];extrinsic_ranks=[]
    for jac in jacobians:
        E=np.asarray(jac[:,:6],np.float64);I=np.asarray(jac[:,6:][:,free],np.float64)
        U,s,Vh=np.linalg.svd(E,full_matrices=False)
        rank=int(np.sum(s>np.finfo(float).eps*max(E.shape)*s[0]))
        if rank!=6:raise ValueError("A target pose is locally underconstrained")
        # Orthogonal projection is the Schur elimination of each view's six
        # nuisance pose parameters. Its scale does not affect this subspace.
        reduced.append((I-U[:,:rank]@(U[:,:rank].T@I))*scales)
        extrinsic_ranks.append(rank)
    J=np.vstack(reduced);_,s,Vh=np.linalg.svd(J,full_matrices=False)
    tolerance=np.finfo(float).eps*max(J.shape)*s[0]
    rank=int(np.sum(s>tolerance));condition=float(s[0]/s[-1]) if s[-1]>0 else float("inf")
    if rank!=len(free) or not math.isfinite(condition) or condition>MAX_CONDITION:
        raise ValueError("The intrinsics are rank-deficient or ill-conditioned after eliminating target poses")
    npoints=sum(v.size//2 for v in residuals);dof=2*npoints-6*len(jacobians)-len(free)
    if dof<=0:raise ValueError("Calibration has no residual degrees of freedom")
    sse=sum(float(np.sum(v*v)) for v in residuals);variance=sse/dof
    if not math.isfinite(variance) or variance<=0:raise ValueError("A positive measured pixel-noise variance is needed to report covariance")
    cov_normalized=(Vh.T*(variance/(s*s)))@Vh
    covariance=cov_normalized*scales[:,None]*scales[None,:]
    covariance=(covariance+covariance.T)*.5
    try:np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError as exc:raise ValueError("The intrinsic covariance is not positive definite") from exc
    return covariance,{"rank":rank,"columns":len(free),"condition":condition,"max_condition":MAX_CONDITION,
        "parameter_scales":scales.tolist(),"singular_values":s.tolist(),"rank_tolerance":float(tolerance),
        "extrinsic_ranks":extrinsic_ranks,"dof":dof,"pixel_noise_variance":variance,
        "assumption":"Local least squares with independent equal-variance pixel-coordinate errors, a rigid measured board, fixed optics and the selected Brown model. This is conditional model uncertainty, not a confidence guarantee for unseen footage.",
        "method":"SVD of parameter-scaled projectPoints Jacobians after Schur/orthogonal elimination of six nuisance pose parameters per training view; physical parameter units restored."}


def solve(observations,width,height,config):
    """Fit actual detected observations; the test entry point accepts measured pixels."""
    config=settings(config);cv,np=runtime()
    if not isinstance(observations,list) or not MIN_VIEWS<=len(observations)<=MAX_VIEWS:raise ValueError("At least twelve detected target views are required")
    ids=[v.get("asset_id") if isinstance(v,dict) else None for v in observations]
    if any(not isinstance(ident,str) or ident not in config["asset_ids"] for ident in ids) or len(set(ids))!=len(ids):raise ValueError("Calibration observation identities are invalid")
    if config["require_all_images"] and set(ids)!=set(config["asset_ids"]):raise ValueError("Every selected image must supply a complete detected target")
    _finite(width,"Calibration width",64,2048,True);_finite(height,"Calibration height",64,2048,True)
    obj=object_points(config,np)
    points=[_points(v.get("corners"),len(obj),width,height,np) for v in observations]
    heldout_count=max(2,round(len(points)*.2))
    heldout={int(round((i+.5)*len(points)/heldout_count-.5)) for i in range(heldout_count)}
    training=[i for i in range(len(points)) if i not in heldout]
    flags=cv.CALIB_FIX_K3 if config["radial_terms"]==2 else 0
    output=cv.calibrateCameraExtended([obj.copy() for _ in training],[points[i] for i in training],
        (width,height),None,None,flags=flags,
        criteria=(cv.TERM_CRITERIA_COUNT|cv.TERM_CRITERIA_EPS,200,1e-10))
    rms,K,D,rvecs,tvecs,std_intr,std_extr,cv_view_errors=output
    K=np.asarray(K,np.float64);D=np.asarray(D,np.float64).reshape(-1)
    if K.shape!=(3,3) or D.shape!=(5,) or not np.isfinite(K).all() or not np.isfinite(D).all() or K[0,0]<=0 or K[1,1]<=0:
        raise ValueError("OpenCV returned invalid pinhole/Brown parameters")
    if config["radial_terms"]==2 and abs(float(D[4]))>1e-15:raise ValueError("The fixed third radial coefficient changed")
    std_intr=np.asarray(std_intr,np.float64).reshape(-1);std_extr=np.asarray(std_extr,np.float64).reshape(-1,6)
    if len(std_intr)!=18 or len(std_extr)!=len(training) or not np.isfinite(std_intr).all() or not np.isfinite(std_extr).all():
        raise ValueError("OpenCV returned incomplete or nonfinite parameter deviations")
    poses={i:(rvecs[j],tvecs[j],j) for j,i in enumerate(training)}
    for i in sorted(heldout):
        ok,rvec,tvec=cv.solvePnP(obj,points[i],K,D,flags=cv.SOLVEPNP_ITERATIVE)
        if not ok:raise ValueError("A held-out view has no independently solved target pose")
        poses[i]=(rvec,tvec,None)
    views=[];jacobians=[];residuals=[];normals=[];view_errors=[];train_sse=hold_sse=0.;train_n=hold_n=0
    for i,observed in enumerate(observations):
        rvec,tvec,j=poses[i];view_rms,residual,jac,rotation=_rms(cv,np,obj,points[i],rvec,tvec,K,D)
        is_training=i in training;view_errors.append(view_rms)
        deviation=None
        if is_training:
            jacobians.append(jac);residuals.append(residual);normals.append(rotation[:,2]);train_sse+=float(np.sum(residual*residual));train_n+=len(obj)
            deviation={"rotation_radians":std_extr[j,:3].tolist(),"translation_meters":(std_extr[j,3:]/1000.).tolist(),
                       "scope":"OpenCV marginal deviations conditional on the training calibration model"}
        else:hold_sse+=float(np.sum(residual*residual));hold_n+=len(obj)
        views.append({"asset_id":observed["asset_id"],"rotation":rotation.reshape(-1).tolist(),
                      "translation":(np.asarray(tvec,np.float64).reshape(3)/1000.).tolist(),
                      "rms_pixels":view_rms,"training":is_training,"stddev":deviation})
    normal_spread=max(math.degrees(math.acos(min(1.,max(0.,abs(float(np.dot(a,b))))))) for a in normals for b in normals)
    if normal_spread<10.:raise ValueError("The target planes are parallel or lack sufficient orientation diversity")
    coverage=_coverage([points[i] for i in training],width,height,cv,np)
    # These explicit capture-quality thresholds supplement the numerical rank
    # test. Coverage/diversity alone is not an observability certificate.
    if coverage["aggregate_coverage"]<.4 or coverage["centroid_coverage"]<.02 or coverage["centroid_span_x"]<.15 or coverage["centroid_span_y"]<.15:
        raise ValueError("The calibration target does not cover enough of the image and viewpoint centers")
    train_rms=math.sqrt(train_sse/train_n);holdout_rms=math.sqrt(hold_sse/hold_n)
    max_training=max(view_errors[i] for i in training);max_holdout=max(view_errors[i] for i in heldout)
    if train_rms>.75 or max_training>1.25 or holdout_rms>1.0 or max_holdout>1.5:
        raise ValueError("Training or held-out reprojection error exceeds the declared pixel-quality bounds")
    if abs(train_rms-float(rms))>2e-4 or np.max(np.abs(np.asarray(cv_view_errors).reshape(-1)-[view_errors[i] for i in training]))>2e-4:
        raise ValueError("The independent reprojection calculation disagrees with OpenCV RMS")
    free=list(range(8 if config["radial_terms"]==2 else 9))
    covariance,observability=_uncertainty(jacobians,residuals,width,height,free,np)
    estimated=set(PARAMETERS[i] for i in free)
    return {"version":1,"kind":"checkerboard-lens-calibration","image_size":{"width":width,"height":height},
        "camera_matrix":K.tolist(),"distortion":D.tolist(),"parameter_order":[PARAMETERS[i] for i in free],
        "covariance":covariance.tolist(),"opencv_stddev":{"parameter_order":list(OPENCV_PARAMETERS),"values":std_intr.tolist(),
            "labels":["estimated" if name in estimated else "fixed-or-unestimated" for name in OPENCV_PARAMETERS],
            "note":"Zero for a fixed or unestimated parameter is an API sentinel, not measured perfect certainty."},
        "quality":{**coverage,"normal_spread_degrees":normal_spread,"train_rms_pixels":train_rms,
            "holdout_rms_pixels":holdout_rms,"max_per_view_rms_pixels":max(view_errors),
            "max_training_view_rms_pixels":max_training,"max_holdout_view_rms_pixels":max_holdout,
            "training_views":len(training),"heldout_views":len(heldout),"observability":observability,
            "thresholds":{"aggregate_coverage":.4,"centroid_coverage":.02,"centroid_span_x":.15,"centroid_span_y":.15,
                "normal_spread_degrees":10.,"train_rms_pixels":.75,"training_view_rms_pixels":1.25,"holdout_rms_pixels":1.,"holdout_view_rms_pixels":1.5}},
        "views":views,"settings":config,"opencv":cv.__version__,"numpy":np.__version__,
        "engine":{"name":"OpenCV","opencv":cv.__version__,"numpy":np.__version__},
        "pixel_convention":PIXEL_CONVENTION,"board_units":"millimeters","pose_translation_units":"meters",
        "pose_convention":"Pattern-to-camera; row-major proper rotation and translation. Object grid order is row-major (column*square_size_mm,row*square_size_mm,0).",
        "fit_scope":"Only training views estimate intrinsics and covariance. Held-out views solve six target-pose parameters with those intrinsics fixed; no all-view refit is performed.",
        "rolling_shutter":{"estimated":False,"reason":"Static checkerboard calibration estimates a global-shutter pinhole/Brown projection. It does not estimate sensor row timing or compensate unknown within-frame motion."}}


def _read_image(item,cv,np):
    path=Path(item["path"])
    if path.is_symlink():raise ValueError("A calibration input is a symbolic link")
    with path.open("rb") as stream:
        record=os.fstat(stream.fileno())
        if not stat.S_ISREG(record.st_mode) or not 0<record.st_size<=MAX_IMAGE_BYTES:raise ValueError("A calibration input is empty, nonregular or oversized")
        data=stream.read(MAX_IMAGE_BYTES+1)
    if len(data)!=record.st_size:raise ValueError("A calibration input changed while being read")
    suffix=path.suffix.lower()
    if suffix==".png" and not data.startswith(b"\x89PNG\r\n\x1a\n") or suffix in (".jpg",".jpeg") and not data.startswith(b"\xff\xd8"):
        raise ValueError("A calibration input does not match its PNG/JPEG container")
    # IMREAD_UNCHANGED preserves native bit depth and ignores EXIF orientation.
    image=cv.imdecode(np.frombuffer(data,np.uint8),cv.IMREAD_UNCHANGED)
    if image is None or image.dtype!=np.uint8 or image.ndim not in (2,3):raise ValueError("Calibration photographs must decode as 8-bit grayscale or color pixels")
    if image.shape[:2]!=(item["height"],item["width"]):raise ValueError("Stored calibration pixels differ from their admitted dimensions (EXIF orientation is ignored)")
    if image.ndim==3:
        if image.shape[2]==4:
            if not np.all(image[:,:,3]==255):raise ValueError("Calibration target images must be opaque")
            image=image[:,:,:3]
        if image.shape[2]!=3:raise ValueError("Unsupported calibration image channel layout")
        gray=cv.cvtColor(image,cv.COLOR_BGR2GRAY)
    else:gray=image
    return image,gray,hashlib.sha256(data).hexdigest()


def doctor():
    cv,np=runtime()
    for name in ("findChessboardCornersSB","calibrateCameraExtended","calibrateCameraROExtended","solvePnP","projectPoints"):
        if not callable(getattr(cv,name,None)):raise RuntimeError("OpenCV is missing the required calibration API: "+name)
    cols,rows,side=8,6,32
    image=np.full(((rows+3)*side,(cols+3)*side),255,np.uint8)
    for y in range(rows+1):
        for x in range(cols+1):
            if (x+y)%2==0:image[(y+1)*side:(y+2)*side,(x+1)*side:(x+2)*side]=0
    found,corners=cv.findChessboardCornersSB(image,(cols,rows),flags=cv.CALIB_CB_NORMALIZE_IMAGE|cv.CALIB_CB_ACCURACY)
    if not found or corners.shape!=(cols*rows,1,2) or not np.isfinite(corners).all():raise RuntimeError("The actual sector-based checkerboard operation failed its generated ENGINE TEST pattern")
    points=np.array([[0,0,0],[1,0,0],[0,1,0]],np.float32)
    projected,jac=cv.projectPoints(points,np.zeros(3),np.array([0.,0.,4.]),np.array([[400.,0.,200.],[0.,400.,150.],[0.,0.,1.]]),np.zeros(5))
    if not np.allclose(projected.reshape(-1,2),[[200.,150.],[300.,150.],[200.,250.]],atol=1e-5) or jac.shape!=(6,15):raise RuntimeError("The actual projection/Jacobian operation failed its ENGINE TEST values")
    return {"available":True,"backend":"opencv-checkerboard-calibration","opencv":cv.__version__,"numpy":np.__version__,
            "runtime_operations_verified":True,"actual_calibration_acceptance":False,"scope":"Actual SB detection and projection on generated ENGINE TEST data; this probe does not calibrate or accept a production lens."}


def calibrate(value):
    config,inputs,(width,height),output=request(value);cv,np=runtime()
    if output.is_symlink() or output.exists() and (not output.is_dir() or any(output.iterdir())):raise ValueError("Calibration output must be a new or empty owned directory")
    observations=[];rejected=[];images=[]
    for item in inputs:
        image,gray,digest=_read_image(item,cv,np)
        found,corners=cv.findChessboardCornersSB(gray,(config["columns"],config["rows"]),
            flags=cv.CALIB_CB_NORMALIZE_IMAGE|cv.CALIB_CB_EXHAUSTIVE|cv.CALIB_CB_ACCURACY)
        if not found:
            rejected.append({"asset_id":item["asset_id"],"reason":"The full declared checkerboard was not detected"})
            continue
        actual=_points(corners.reshape(-1,2),config["columns"]*config["rows"],width,height,np)
        observations.append({"asset_id":item["asset_id"],"corners":actual.reshape(-1,2).tolist(),"sha256":digest})
        painted=cv.cvtColor(image,cv.COLOR_GRAY2BGR) if image.ndim==2 else image.copy()
        cv.drawChessboardCorners(painted,(config["columns"],config["rows"]),actual,True)
        factor=min(1.,512/max(width,height))
        if factor<1:painted=cv.resize(painted,(round(width*factor),round(height*factor)),interpolation=cv.INTER_AREA)
        images.append((item["asset_id"],painted))
    if rejected and config["require_all_images"]:raise ValueError("Every selected image must contain the full declared checkerboard: "+", ".join(v["asset_id"] for v in rejected))
    result=solve(observations,width,height,config)
    measured={"version":1,"kind":"checkerboard-observations","image_size":{"width":width,"height":height},
              "pixel_convention":PIXEL_CONVENTION,"board":{"columns":config["columns"],"rows":config["rows"],"square_size_mm":config["square_size_mm"]},
              "views":observations,"rejected":rejected,"detection":"OpenCV sector-based full-board subpixel detection on original stored pixels; no image resizing or extra cornerSubPix refinement."}
    with tempfile.TemporaryDirectory(prefix=".lens-calibration-",dir=output.parent) as temporary:
        stage=Path(temporary)/"result";stage.mkdir();(stage/"corners").mkdir()
        for name,record in (("calibration.json",result),("observations.json",measured)):
            (stage/name).write_text(json.dumps(record,allow_nan=False,indent=2)+"\n",encoding="utf-8")
        storage=cv.FileStorage(str(stage/"opencv.yml"),cv.FILE_STORAGE_WRITE)
        if not storage.isOpened():raise RuntimeError("OpenCV could not create its calibration file")
        try:
            storage.write("image_width",width);storage.write("image_height",height)
            storage.write("camera_matrix",np.asarray(result["camera_matrix"],np.float64));storage.write("distortion_coefficients",np.asarray(result["distortion"],np.float64).reshape(1,5))
            storage.write("intrinsic_covariance",np.asarray(result["covariance"],np.float64));storage.write("training_rms_pixels",result["quality"]["train_rms_pixels"])
            storage.write("heldout_rms_pixels",result["quality"]["holdout_rms_pixels"]);storage.write("pixel_convention",PIXEL_CONVENTION)
        finally:storage.release()
        for ident,painted in images:
            if not cv.imwrite(str(stage/"corners"/(ident+".png")),painted):raise RuntimeError("Could not write the measured-corner debug image")
        if output.exists():output.rmdir()  # Refuses a directory populated since the initial check.
        os.rename(stage,output)
    return {"ok":True,"kind":result["kind"],"engine":result["engine"],"views":len(observations),"rejected":len(rejected),
            "training_rms_pixels":result["quality"]["train_rms_pixels"],"heldout_rms_pixels":result["quality"]["holdout_rms_pixels"],
            "artifacts":["calibration.json","observations.json","opencv.yml","corners/"]}


def main():
    if sys.argv[1:]==["--doctor"]:result=doctor()
    elif len(sys.argv)==3 and sys.argv[1]=="--request":
        data=Path(sys.argv[2]).read_bytes()
        if len(data)>65536:raise ValueError("Calibration request exceeds 64 KiB")
        def invalid_constant(value):
            raise ValueError("Nonfinite JSON constants are not admitted: "+value)
        result=calibrate(json.loads(data,parse_constant=invalid_constant))
    else:raise ValueError("Expected --doctor or --request with an owned calibration manifest")
    print(json.dumps(result,allow_nan=False,separators=(",",":")))


if __name__=="__main__":
    try:main()
    except Exception as exc:
        sys.stderr.write(type(exc).__name__+": "+str(exc)[:1800]+"\n");sys.exit(1)

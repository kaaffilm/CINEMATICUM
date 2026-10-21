"""Isolated OpenCV planar measurement worker; no model or neural labels.

Features follow pyramidal Lucas–Kanade flow, forward/backward consistency and
photometric gates. RANSAC fits reference-to-current affine/homography motion.
Losing sufficient support produces explicit gaps; it never guesses a new plane.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from projective_warp import COORDINATES, IDENTITY, MAX_PLANAR_FRAMES, validate_matrix, validate_quad, transform


def runtime():
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    return cv2,np


def capabilities():
    cv,np=runtime()
    points=np.array([[0,0],[20,0],[20,20],[0,20],[10,10],[5,15]],np.float32)
    matrix,mask=cv.findHomography(points,points+np.array([2,3],np.float32),cv.RANSAC,1)
    affine,_=cv.estimateAffine2D(points,points+np.array([2,3],np.float32),method=cv.RANSAC)
    image=np.random.default_rng(7).integers(0,256,(64,64),dtype=np.uint8)
    features=cv.goodFeaturesToTrack(image,maxCorners=32,qualityLevel=.02,minDistance=5)
    moved,status,_=cv.calcOpticalFlowPyrLK(image,image,features,None)
    if matrix is None or affine is None or features is None or moved is None or not status.all():
        raise ValueError("The isolated OpenCV runtime failed actual feature/flow/model operations")
    if not np.allclose(matrix,[[1,0,2],[0,1,3],[0,0,1]],atol=1e-6):
        raise ValueError("OpenCV homography execution produced unexpected coordinates")
    return {"available":True,"backend":"opencv-lk-ransac","opencv":cv.__version__,"numpy":np.__version__,
            "models":["affine","projective"],"coordinates":COORDINATES,"runtime_operations_verified":True}


def measure(request):
    cv,np=runtime()
    if not isinstance(request,dict) or set(request)!={"frames","width","height","count","model","quad"}:
        raise ValueError("Invalid planar worker request")
    w,h,count=request["width"],request["height"],request["count"]
    if any(type(v) is not int for v in (w,h,count)) or not 16<=w<=640 or not 16<=h<=640 or not 1<=count<=MAX_PLANAR_FRAMES:
        raise ValueError("Planar analysis exceeds its frame/canvas bounds")
    model=request["model"]
    if model not in {"affine","projective"}:raise ValueError("Unknown planar model")
    quad=validate_quad(request["quad"])
    path=Path(request["frames"])
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size!=w*h*count:
        raise ValueError("The bounded decoded frame sequence is missing or incomplete")
    frames=np.memmap(path,dtype=np.uint8,mode="r",shape=(count,h,w))
    roi=np.asarray(quad,np.float32)*[w,h]-.5
    mask=np.zeros((h,w),np.uint8)
    cv.fillConvexPoly(mask,np.rint(roi).astype(np.int32),255)
    # Erode the boundary so LK patches do not chiefly measure the background.
    mask=cv.erode(mask,np.ones((9,9),np.uint8))
    features=cv.goodFeaturesToTrack(frames[0],mask=mask,maxCorners=1500,qualityLevel=.012,minDistance=4,blockSize=5)
    if features is None or len(features)<24:
        raise ValueError("Choose a larger textured plane; fewer than 24 usable source features were found")
    reference=features.reshape(-1,2).copy();current=reference.copy()
    original_count=len(reference)
    canvas_to_pixels=np.array([[w,0,-.5],[0,h,-.5],[0,0,1]],np.float64)
    pixels_to_canvas=np.linalg.inv(canvas_to_pixels)
    roi_area=abs(float(cv.contourArea(roi.astype(np.float32))))
    samples=[{"frame":0,"visible":True,"matrix":IDENTITY,"corners":quad,"confidence":1.,
              "features":original_count,"inliers":original_count,"inlier_ratio":1.,"coverage":1.,"error_pixels":0.,"reason":""}]
    lost=False
    for frame in range(1,count):
        failed={"frame":frame,"visible":False,"matrix":None,"corners":None,"confidence":0.,
                "features":0,"inliers":0,"inlier_ratio":0.,"coverage":0.,"error_pixels":None,
                "reason":"Support was lost earlier; automatic reacquisition is disabled"}
        if lost:
            samples.append(failed);continue
        points=current.reshape(-1,1,2).astype(np.float32)
        following,status,error=cv.calcOpticalFlowPyrLK(frames[frame-1],frames[frame],points,None,
            winSize=(21,21),maxLevel=3,criteria=(cv.TERM_CRITERIA_COUNT|cv.TERM_CRITERIA_EPS,40,.01))
        reason="Insufficient forward/backward optical-flow support"
        accepted=None
        if following is not None and status is not None:
            back,reverse_status,_=cv.calcOpticalFlowPyrLK(frames[frame],frames[frame-1],following,None,
                winSize=(21,21),maxLevel=3,criteria=(cv.TERM_CRITERIA_COUNT|cv.TERM_CRITERIA_EPS,40,.01))
            if back is not None and reverse_status is not None:
                next_points=following.reshape(-1,2)
                good=(status.ravel()!=0)&(reverse_status.ravel()!=0)&np.isfinite(next_points).all(axis=1)
                good&=np.linalg.norm(back.reshape(-1,2)-current,axis=1)<=1.25
                good&=error.ravel()<=25
                good&=(next_points[:,0]>=2)&(next_points[:,0]<w-2)&(next_points[:,1]>=2)&(next_points[:,1]<h-2)
                previous_reference,observed=reference[good],next_points[good]
                failed["features"]=int(len(observed))
                if len(observed)>=16:
                    if model=="projective":
                        matrix,inlier_mask=cv.findHomography(previous_reference,observed,cv.RANSAC,2.,maxIters=2500,confidence=.995)
                    else:
                        affine,inlier_mask=cv.estimateAffine2D(previous_reference,observed,method=cv.RANSAC,
                            ransacReprojThreshold=2.,maxIters=2500,confidence=.995,refineIters=10)
                        matrix=None if affine is None else np.vstack([affine,[0,0,1]])
                    reason="The fitted plane lacks reliable spatial inlier support"
                    if matrix is not None and inlier_mask is not None and np.isfinite(matrix).all():
                        inside=inlier_mask.ravel()!=0
                        ref,obs=previous_reference[inside],observed[inside]
                        inliers=len(ref);ratio=inliers/len(observed)
                        coverage=abs(float(cv.contourArea(cv.convexHull(ref))))/max(roi_area,1) if inliers>=3 else 0
                        failed.update(inliers=int(inliers),inlier_ratio=float(ratio),coverage=float(min(1,coverage)))
                        projected=cv.perspectiveTransform(ref.reshape(-1,1,2),matrix).reshape(-1,2)
                        residual=float(np.median(np.linalg.norm(projected-obs,axis=1))) if inliers else float("inf")
                        if inliers>=16 and ratio>=.6 and coverage>=.12 and residual<=1.25 and inliers>=original_count*.15:
                            try:
                                normalized=validate_matrix((pixels_to_canvas@matrix@canvas_to_pixels).reshape(-1).tolist())
                                corners=[transform(normalized,p) for p in quad]
                                area=abs(sum(corners[n][0]*corners[(n+1)%4][1]-corners[(n+1)%4][0]*corners[n][1] for n in range(4)))/2
                                if not .2<=area/(roi_area/(w*h))<=5:
                                    raise ValueError("The tracked plane changed area beyond the measurement bound")
                                accepted={"frame":frame,"visible":True,"matrix":normalized,"corners":corners,
                                    "confidence":float(ratio*min(1,coverage/.5)*max(0,1-residual/2)),
                                    "features":int(len(observed)),"inliers":int(inliers),"inlier_ratio":float(ratio),
                                    "coverage":float(min(1,coverage)),"error_pixels":residual,"reason":""}
                                reference,current=ref.copy(),obs.copy()
                            except ValueError as exc:reason=str(exc)
        if accepted is None:
            lost=True;failed["reason"]=reason;samples.append(failed)
        else:samples.append(accepted)
    return {"backend":"opencv-lk-ransac","opencv":cv.__version__,"numpy":np.__version__,
            "model":model,"samples":samples,"initial_features":original_count,
            "measurement_note":"Classical LK flow with forward/backward and photometric checks, then RANSAC. Confidence summarizes geometric support, not semantic visibility or an occlusion probability. Lost support is not automatically reacquired."}


def main():
    if sys.argv[1:]==["--capabilities"]:result=capabilities()
    elif len(sys.argv)==3 and sys.argv[1]=="--request":
        data=Path(sys.argv[2]).read_bytes()
        if len(data)>65536:raise ValueError("Planar worker request is oversized")
        result=measure(json.loads(data))
    else:raise ValueError("Expected a bounded planar request")
    sys.stdout.write(json.dumps(result,allow_nan=False,separators=(",",":")))


if __name__=="__main__":
    try:main()
    except Exception as exc:
        sys.stderr.write(type(exc).__name__+": "+str(exc)+"\n")
        sys.exit(1)

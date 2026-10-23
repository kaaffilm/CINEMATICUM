"""Short actual-OpenCV ENGINE TESTS; no production lens acceptance claim.

Each case is separately runnable with the isolated tracking Python:
  python test_lens_calibration_smoke.py --engine-case detector
  python test_lens_calibration_smoke.py --engine-case covariance

Normal unittest discovery keeps OpenCV/NumPy in child interpreters and skips
explicitly if the selected interpreter cannot perform the actual worker probe.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

HERE=Path(__file__).resolve().parent


def _rotation(np,rx,ry,rz):
    cx,sx=math.cos(rx),math.sin(rx);cy,sy=math.cos(ry),math.sin(ry);cz,sz=math.cos(rz),math.sin(rz)
    return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1.]])@np.array([[cy,0,sy],[0,1.,0],[-sy,0,cy]])@np.array([[1.,0,0],[0,cx,-sx],[0,sx,cx]])


def _project(np,obj,R,t,K,D):
    """Independent Brown oracle, without OpenCV projection/Jacobian calls."""
    camera=obj@R.T+t;x=camera[:,0]/camera[:,2];y=camera[:,1]/camera[:,2]
    r2=x*x+y*y;k1,k2,p1,p2,k3=D;radial=1+k1*r2+k2*r2*r2+k3*r2*r2*r2
    return np.column_stack((K[0,0]*(x*radial+2*p1*x*y+p2*(r2+2*x*x))+K[0,2],
                            K[1,1]*(y*radial+p1*(r2+2*y*y)+2*p2*x*y)+K[1,2]))


def _detector(worker,cv,np):
    cols,rows,side=8,6,24
    source=np.full(((rows+3)*side,(cols+3)*side),255,np.uint8)
    for y in range(rows+1):
        for x in range(cols+1):
            if (x+y)%2==0:source[(y+1)*side:(y+2)*side,(x+1)*side:(x+2)*side]=0
    source_quad=np.array([[0,0],[source.shape[1]-1,0],[source.shape[1]-1,source.shape[0]-1],[0,source.shape[0]-1]],np.float32)
    destination=np.array([[100,70],[520,90],[545,425],[75,405]],np.float32)
    H=cv.getPerspectiveTransform(source_quad,destination)
    image=cv.warpPerspective(source,H,(640,480),flags=cv.INTER_LINEAR,borderValue=180)
    found,corners=cv.findChessboardCornersSB(image,(cols,rows),flags=cv.CALIB_CB_NORMALIZE_IMAGE|cv.CALIB_CB_EXHAUSTIVE|cv.CALIB_CB_ACCURACY)
    assert found,"Actual SB operation did not detect the generated perspective target"
    actual=worker._points(corners.reshape(-1,2),cols*rows,640,480,np).reshape(-1,2)
    native=np.array([(2*side-.5+x*side,2*side-.5+y*side,1.) for y in range(rows) for x in range(cols)])
    homogeneous=native@H.T;expected=homogeneous[:,:2]/homogeneous[:,2:]
    # This unmarked target has a legitimate 180-degree ordering ambiguity.
    rms=min(math.sqrt(float(np.mean(np.sum((order-expected)**2,axis=1)))) for order in (actual,actual[::-1]))
    assert rms<.6,("Actual subpixel corner error",rms)
    assert actual.shape==(48,2) and image.shape==(480,640)
    return {"actual_SB_corners":48,"native_image_size":[640,480],"corner_oracle_rms_pixels":rms}


def _covariance(worker,cv,np):
    width,height=1280,960
    config={"version":1,"asset_ids":["smoke_%02d"%i for i in range(20)],"columns":8,"rows":6,
            "square_size_mm":25.,"radial_terms":2,"same_optics_confirmed":True,"require_all_images":True}
    K=np.array([[900.,0,637.2],[0,910.,482.4],[0,0,1.]])
    D=np.array([-.12,.035,.0008,-.0006,0.]);obj=np.array([(25.*x,25.*y,0.) for y in range(6) for x in range(8)])
    center=np.array([87.5,62.5,0.]);rng=np.random.default_rng(48197);observations=[]
    for i,ident in enumerate(config["asset_ids"]):
        x=(.28,.43,.58,.73)[i%4];y=(.24,.37,.50,.63,.76)[i//4];z=360.+19*(i%3)
        R=_rotation(np,-.30+.15*(i%5),-.34+.17*((i*3)%5),.035*(i%3-1))
        t=np.array([(x*width-K[0,2])*z/K[0,0],(y*height-K[1,2])*z/K[1,1],z])-R@center
        # Explicit 0.08-pixel iid generated measurement noise: covariance must
        # represent a nonzero conditional estimate, never perfect certainty.
        measured=_project(np,obj,R,t,K,D)+rng.normal(0,.08,(48,2))
        observations.append({"asset_id":ident,"corners":measured.tolist()})
    result=worker.solve(observations,width,height,config)
    fitted=np.array(result["camera_matrix"]);distortion=np.array(result["distortion"]);cov=np.array(result["covariance"])
    assert np.max(np.abs((np.diag(fitted)[:2]-np.diag(K)[:2])/np.diag(K)[:2]))<.01
    assert np.max(np.abs(fitted[:2,2]-K[:2,2]))<3
    assert cov.shape==(8,8) and np.allclose(cov,cov.T) and np.all(np.linalg.eigvalsh(cov)>0)
    assert np.max(np.abs(cov-np.diag(np.diag(cov))))>0
    assert np.allclose(np.sqrt(np.diag(cov)),result["opencv_stddev"]["values"][:8],rtol=5e-4,atol=1e-8)
    assert result["quality"]["observability"]["rank"]==8
    assert result["quality"]["observability"]["pixel_noise_variance"]>0
    assert result["quality"]["holdout_rms_pixels"]<.3
    assert result["opencv_stddev"]["labels"][8]=="fixed-or-unestimated" and distortion[4]==0
    assert result["rolling_shutter"]["estimated"] is False
    for view,observation in zip(result["views"],observations):
        R=np.array(view["rotation"]).reshape(3,3);t=np.array(view["translation"])*1000
        assert np.allclose(R.T@R,np.eye(3),atol=1e-9) and abs(np.linalg.det(R)-1)<1e-9
        residual=_project(np,obj,R,t,fitted,distortion)-np.array(observation["corners"])
        rms=math.sqrt(float(np.sum(residual*residual))/48)
        assert abs(rms-view["rms_pixels"])<2e-4
    return {"training_views":result["quality"]["training_views"],"heldout_views":result["quality"]["heldout_views"],
            "holdout_rms_pixels":result["quality"]["holdout_rms_pixels"],"intrinsic_rank":8,
            "intrinsic_condition":result["quality"]["observability"]["condition"]}


def _case(name):
    start=time.monotonic()
    sys.path.insert(0,str(HERE))
    import lens_calibration_worker as worker
    cv,np=worker.runtime()
    result={"detector":_detector,"covariance":_covariance}[name](worker,cv,np)
    print(json.dumps({"case":name,"engine":{"name":"OpenCV","opencv":cv.__version__,"numpy":np.__version__},
        "actual_calibration_acceptance":False,"scope":"Generated ENGINE TEST only; no production physical lens acceptance or rolling-shutter estimate",
        "elapsed_seconds":time.monotonic()-start,**result},allow_nan=False,separators=(",",":")))


class LensCalibrationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python=os.environ.get("CINEMATICUM_TRACKING_PYTHON",sys.executable)
        try:
            probe=subprocess.run([cls.python,"-I","-B",str(HERE/"lens_calibration_worker.py"),"--doctor"],capture_output=True,text=True,timeout=4)
            state=json.loads(probe.stdout) if probe.returncode==0 else {}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:raise unittest.SkipTest("Actual OpenCV smoke runtime unavailable: "+str(exc))
        if state.get("runtime_operations_verified") is not True:raise unittest.SkipTest("Actual OpenCV smoke probe failed: "+probe.stderr[:300])

    def case(self,name):
        result=subprocess.run([self.python,"-I","-B",str(Path(__file__).resolve()),"--engine-case",name],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        record=json.loads(result.stdout)
        self.assertIs(record["actual_calibration_acceptance"],False)
        print(result.stdout.strip())

    def test_actual_sector_based_detector(self):self.case("detector")
    def test_independent_projection_and_covariance(self):self.case("covariance")


if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--engine-case":_case(sys.argv[2])
    else:unittest.main()

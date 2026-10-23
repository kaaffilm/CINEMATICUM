"""Actual OpenCV operations on generated ENGINE TEST targets, not lens acceptance.

The application/test discovery process never imports numpy or OpenCV. Engine
cases run in the selected isolated tracking interpreter (or this interpreter
when explicitly installed), and skip clearly when its actual doctor fails.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
WORKER=HERE/"lens_calibration_worker.py"


def _worker():
    spec=importlib.util.spec_from_file_location("lens_worker",WORKER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _settings(count=20,radial_terms=2):
    return {"version":1,"asset_ids":["engine_%02d"%i for i in range(count)],
            "columns":8,"rows":6,"square_size_mm":25.,"radial_terms":radial_terms,
            "same_optics_confirmed":True,"require_all_images":True}


def _project(np,obj,rotation,translation,K,D):
    """Independent Brown projection oracle: deliberately no cv.projectPoints."""
    camera=obj@rotation.T+translation
    x=camera[:,0]/camera[:,2];y=camera[:,1]/camera[:,2]
    r2=x*x+y*y;k1,k2,p1,p2,k3=D
    radial=1.+k1*r2+k2*r2*r2+k3*r2*r2*r2
    xd=x*radial+2*p1*x*y+p2*(r2+2*x*x)
    yd=y*radial+p1*(r2+2*y*y)+2*p2*x*y
    return np.column_stack((K[0,0]*xd+K[0,2],K[1,1]*yd+K[1,2]))


def _rotation(np,rx,ry,rz):
    cx,sx=math.cos(rx),math.sin(rx);cy,sy=math.cos(ry),math.sin(ry);cz,sz=math.cos(rz),math.sin(rz)
    return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1.]])@np.array([[cy,0,sy],[0,1.,0],[-sy,0,cy]])@np.array([[1.,0,0],[0,cx,-sx],[0,sx,cx]])


def _dataset(np,count=20,radial_terms=2,parallel=False):
    config=_settings(count,radial_terms);width,height=1280,960
    K=np.array([[900.,0,637.2],[0,910.,482.4],[0,0,1.]])
    D=np.array([-.12,.035,.0008,-.0006,.005 if radial_terms==3 else 0.])
    obj=np.array([(25.*x,25.*y,0.) for y in range(6) for x in range(8)])
    center=np.array([87.5,62.5,0.]);rng=np.random.default_rng(48197)
    observations=[]
    for i in range(count):
        # Wide image coverage, genuinely different plane normals and measured
        # iid coordinate noise make this a nonzero-uncertainty ENGINE TEST.
        x=(.28,.43,.58,.73)[i%4];y=(.24,.37,.50,.63,.76)[i//4]
        z=360.+19.*(i%3)
        R=_rotation(np,0 if parallel else (-.30+.15*(i%5)),0 if parallel else (-.34+.17*((i*3)%5)),.035*(i%3-1))
        target=np.array([(x*width-K[0,2])*z/K[0,0],(y*height-K[1,2])*z/K[1,1],z])
        t=target-R@center
        pixels=_project(np,obj,R,t,K,D)+rng.normal(0,.08,(len(obj),2))
        if np.any(pixels<0) or np.any(pixels[:,0]>=width) or np.any(pixels[:,1]>=height):raise AssertionError("ENGINE TEST target unexpectedly leaves image")
        observations.append({"asset_id":config["asset_ids"][i],"corners":pixels.tolist()})
    return config,width,height,K,D,observations


def _engine_case(name):
    worker=_worker();cv,np=worker.runtime()
    if name in ("brown2","brown3"):
        radial=2 if name=="brown2" else 3
        config,width,height,K,D,observations=_dataset(np,radial_terms=radial)
        solved=worker.solve(observations,width,height,config)
        fitted=np.array(solved["camera_matrix"]);distortion=np.array(solved["distortion"])
        assert np.max(np.abs((np.diag(fitted)[:2]-np.diag(K)[:2])/np.diag(K)[:2]))<.01
        assert np.max(np.abs(fitted[:2,2]-K[:2,2]))<3.
        assert abs(distortion[0]-D[0])<.02 and abs(distortion[1]-D[1])<.05
        assert solved["quality"]["holdout_rms_pixels"]<.3
        assert solved["quality"]["observability"]["rank"]==radial+6
        covariance=np.array(solved["covariance"])
        assert covariance.shape==(radial+6,radial+6) and np.allclose(covariance,covariance.T)
        assert np.all(np.linalg.eigvalsh(covariance)>0)
        assert np.max(np.abs(covariance-np.diag(np.diag(covariance))))>0
        # OpenCV independently marginalizes the full normal matrix; agreement
        # checks our physical-unit Schur covariance without assuming diagonality.
        assert np.allclose(np.sqrt(np.diag(covariance)),solved["opencv_stddev"]["values"][:radial+6],rtol=5e-4,atol=1e-8)
        assert solved["quality"]["observability"]["pixel_noise_variance"]>0
        assert solved["rolling_shutter"]["estimated"] is False
        if radial==2:
            assert distortion[4]==0 and solved["opencv_stddev"]["values"][8]==0
            assert solved["opencv_stddev"]["labels"][8]=="fixed-or-unestimated"
        # Independent oracle also checks exported meter poses and each RMS.
        obj=np.array([(25.*x,25.*y,0.) for y in range(6) for x in range(8)])
        for view,observed in zip(solved["views"],observations):
            R=np.array(view["rotation"]).reshape(3,3);t=np.array(view["translation"])*1000
            assert np.max(np.abs(R.T@R-np.eye(3)))<1e-9 and abs(np.linalg.det(R)-1)<1e-9
            residual=_project(np,obj,R,t,fitted,distortion)-np.array(observed["corners"])
            rms=math.sqrt(float(np.sum(residual*residual))/len(obj))
            assert abs(rms-view["rms_pixels"])<2e-4
        print(json.dumps({"case":name,"train_rms":solved["quality"]["train_rms_pixels"],"holdout_rms":solved["quality"]["holdout_rms_pixels"],"condition":solved["quality"]["observability"]["condition"]}))
    elif name=="parallel":
        config,w,h,K,D,observations=_dataset(np,parallel=True)
        try:worker.solve(observations,w,h,config)
        except (ValueError,cv.error) as exc:
            assert any(term in str(exc).lower() for term in ("parallel","orientation","rank-deficient","ill-conditioned")),str(exc)
        else:raise AssertionError("Parallel target poses were accepted")
    elif name=="holdout":
        config,w,h,K,D,observations=_dataset(np)
        # The deterministic held-out indices are 2,7,12,17. Nonrigid corner
        # displacement cannot be absorbed by the six held-out pose parameters.
        for i in (2,7,12,17):
            for j,p in enumerate(observations[i]["corners"]):p[0]+=4 if j%2 else -4
        try:worker.solve(observations,w,h,config)
        except ValueError as exc:assert "reprojection error" in str(exc),str(exc)
        else:raise AssertionError("Poor held-out observations were accepted")
    elif name=="raster":
        _raster_case(worker,cv,np)
    elif name=="admission":
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/"image.png"
            item={"asset_id":"engine_00","path":str(path),"width":960,"height":720}
            opaque=np.full((720,960,4),255,np.uint8);assert cv.imwrite(str(path),opaque)
            image,gray,digest=worker._read_image(item,cv,np)
            assert image.shape==(720,960,3) and gray.shape==(720,960) and len(digest)==64
            def refuses(array,reason):
                assert cv.imwrite(str(path),array)
                try:worker._read_image(item,cv,np)
                except ValueError as exc:assert reason in str(exc),str(exc)
                else:raise AssertionError("Invalid native pixels admitted")
            opaque[0,0,3]=254;refuses(opaque,"opaque")
            refuses(np.zeros((720,960),np.uint16),"8-bit")
            refuses(np.zeros((719,960),np.uint8),"dimensions")
            config,w,h,K,D,observations=_dataset(np)
            try:worker.solve(observations[:-1],w,h,config)
            except ValueError as exc:assert "Every selected image" in str(exc),str(exc)
            else:raise AssertionError("The all-images policy admitted missing observations")
    else:raise ValueError(name)


def _raster_case(worker,cv,np):
    config=_settings(13);config["require_all_images"]=False
    w,h=960,720;side=40
    K=np.array([[680.,0,480.],[0,690.,360.],[0,0,1.]])
    target=np.full((9*side,11*side),255,np.uint8)
    for y in range(7):
        for x in range(9):
            if (x+y)%2==0:target[(y+1)*side:(y+2)*side,(x+1)*side:(x+2)*side]=0
    source=np.array([[0,0],[target.shape[1]-1,0],[target.shape[1]-1,target.shape[0]-1],[0,target.shape[0]-1]],np.float32)
    # The first inner corner lies at 2*side-.5 because pixel centers have
    # integer coordinates and the black/white cell boundary is halfway.
    plane=np.column_stack(((source-(2*side-.5))*25./side,np.zeros(4)))
    center=np.array([87.5,62.5,0.])
    with tempfile.TemporaryDirectory(prefix="cinematicum-lens-engine-") as folder:
        root=Path(folder);inputs=[]
        for i,ident in enumerate(config["asset_ids"]):
            if i==12:
                path=root/(ident+".png");assert cv.imwrite(str(path),np.full((h,w),180,np.uint8))
                inputs.append({"asset_id":ident,"path":str(path),"width":w,"height":h})
                continue
            x=(.30,.50,.70)[i%3];y=(.29,.43,.57,.71)[i//3];z=395.+18*(i%2)
            R=_rotation(np,(-.27,.22,.31,-.18)[i%4],(-.29,.27,.12)[i%3],.045*(i%3-1))
            t=np.array([(x*w-480.)*z/680.,(y*h-360.)*z/690.,z])-R@center
            destination=_project(np,plane,R,t,K,np.zeros(5)).astype(np.float32)
            H=cv.getPerspectiveTransform(source,destination)
            # Aliasing/subpixel raster sampling supplies actual finite detector
            # uncertainty. No oracle corners are sent to the worker here.
            image=cv.warpPerspective(target,H,(w,h),flags=cv.INTER_LINEAR,borderMode=cv.BORDER_CONSTANT,borderValue=180)
            path=root/(ident+".png");assert cv.imwrite(str(path),image)
            inputs.append({"asset_id":ident,"path":str(path),"width":w,"height":h})
        output=root/"result";manifest=root/"request.json"
        manifest.write_text(json.dumps({"command":"calibrate","settings":config,"inputs":inputs,"output_dir":str(output)}))
        run=subprocess.run([sys.executable,str(WORKER),"--request",str(manifest)],capture_output=True,text=True,timeout=60)
        assert run.returncode==0,run.stderr
        summary=json.loads(run.stdout);calibration=json.loads((output/"calibration.json").read_text());observations=json.loads((output/"observations.json").read_text())
        assert summary["views"]==12 and len(calibration["views"])==12 and summary["rejected"]==1
        assert observations["rejected"]==[{"asset_id":config["asset_ids"][-1],"reason":"The full declared checkerboard was not detected"}]
        assert [v["asset_id"] for v in observations["views"]]==config["asset_ids"][:12]
        assert all(len(v["corners"])==48 and len(v["sha256"])==64 for v in observations["views"])
        assert calibration["rolling_shutter"]["estimated"] is False
        assert calibration["quality"]["holdout_rms_pixels"]<1.
        # The server validates measured pixels with its independent pure-Python
        # Brown oracle before certifying the compositor's normalized profile.
        import lens_calibration as backend
        backend.validate_measurement(calibration,observations,config,w,h)
        profile=backend.profile_proposal(calibration)
        assert profile["params"]["fx"]==calibration["camera_matrix"][0][0]/w
        assert profile["params"]["fy"]==calibration["camera_matrix"][1][1]/h
        assert profile["params"]["cx"]==calibration["camera_matrix"][0][2]/w
        assert profile["params"]["cy"]==calibration["camera_matrix"][1][2]/h
        storage=cv.FileStorage(str(output/"opencv.yml"),cv.FILE_STORAGE_READ)
        try:assert np.allclose(storage.getNode("camera_matrix").mat(),calibration["camera_matrix"])
        finally:storage.release()
        for ident in config["asset_ids"][:12]:
            preview=cv.imread(str(output/"corners"/(ident+".png")))
            assert preview is not None and max(preview.shape[:2])<=512
        print(json.dumps({"case":"raster","actual_SB_views":12,"train_rms":calibration["quality"]["train_rms_pixels"],"holdout_rms":calibration["quality"]["holdout_rms_pixels"],"scope":"generated ENGINE TEST, not production lens acceptance"}))


class ValidationContracts(unittest.TestCase):
    def test_module_does_not_import_heavy_runtime(self):
        script="import sys;sys.path.insert(0,sys.argv[1]);import lens_calibration_worker;assert 'cv2' not in sys.modules and 'numpy' not in sys.modules"
        subprocess.run([sys.executable,"-I","-c",script,str(HERE)],check=True,capture_output=True,timeout=5)

    def test_strict_settings(self):
        worker=_worker()
        for changes in ({"same_optics_confirmed":False},{"columns":3},{"rows":13},{"radial_terms":True},{"square_size_mm":float("nan")},{"require_all_images":0}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):worker.settings({**_settings(),**changes})
        self.assertEqual(worker.settings(_settings())["columns"],8)

    def test_strict_manifest_and_native_dimensions(self):
        worker=_worker();config=_settings(12)
        inputs=[{"asset_id":ident,"path":"/owned/"+ident+".png","width":960,"height":720} for ident in config["asset_ids"]]
        value={"command":"calibrate","settings":config,"inputs":inputs,"output_dir":"/owned/result"}
        self.assertEqual(worker.request(value)[2],(960,720))
        for changed in ({**inputs[0],"width":2049},{**inputs[0],"height":719},{**inputs[0],"path":"relative.png"},{**inputs[0],"path":inputs[1]["path"]}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):worker.request({**value,"inputs":[changed,*inputs[1:]]})

    def test_nonfinite_json_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/"request.json";manifest.write_text('{"settings":NaN}')
            result=subprocess.run([sys.executable,str(WORKER),"--request",str(manifest)],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,1);self.assertIn("Nonfinite JSON",result.stderr)


class ActualOpenCVEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python=os.environ.get("CINEMATICUM_TRACKING_PYTHON",sys.executable)
        try:
            probe=subprocess.run([cls.python,str(WORKER),"--doctor"],capture_output=True,text=True,timeout=15)
            state=json.loads(probe.stdout) if probe.returncode==0 else {}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
            raise unittest.SkipTest("Actual OpenCV ENGINE TEST runtime unavailable: "+str(exc))
        if state.get("runtime_operations_verified") is not True:raise unittest.SkipTest("Actual OpenCV ENGINE TEST doctor failed: "+probe.stderr[:300])

    def case(self,name):
        result=subprocess.run([self.python,str(Path(__file__).resolve()),"--engine-case",name],capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        if result.stdout:print(result.stdout.strip())

    def test_independent_brown_two_radial_with_covariance(self):self.case("brown2")
    def test_independent_brown_three_radial_with_covariance(self):self.case("brown3")
    def test_parallel_target_poses_are_refused(self):self.case("parallel")
    def test_nonrigid_heldout_error_is_refused(self):self.case("holdout")
    def test_actual_raster_detection_and_cli_artifacts(self):self.case("raster")
    def test_actual_native_image_and_all_views_admission(self):self.case("admission")


if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--engine-case":_engine_case(sys.argv[2])
    else:unittest.main()

"""Real CPU COLMAP acceptance against independently rendered photographs.

The image fixture uses NumPy ray/plane intersections and Pillow textures. It
does not supply COLMAP features, matches, poses or points. Optional runtime
tests require CINEMATICUM_RECONSTRUCTION_PYTHON and never download packages.
"""
import copy
from contextlib import closing
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

import reconstruction as reconstruction
import install_reconstruction as installer
from scene import default_scene


def photographs(root, radial=0.):
    """Independent calibrated RGB photographs of four textured depth planes."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    width,height=640,480
    planes=[(0.,0.,5.5,9.,7.),(-1.,-.35,3.1,1.5,1.8),(1.05,.15,3.8,1.65,2.),(0.,1.65,4.3,2.4,1.1)]
    textures=[]
    for index in range(len(planes)):
        rng=np.random.default_rng(8317+index)
        image=Image.fromarray(rng.integers(65,192,(768,768,3),dtype=np.uint8));draw=ImageDraw.Draw(image)
        for _ in range(850):
            x,y=rng.integers(0,768,2);r=int(rng.integers(3,21));color=tuple(int(v) for v in rng.integers(0,256,3))
            box=(int(x)-r,int(y)-r,int(x)+r,int(y)+r)
            if rng.random()<.5:draw.ellipse(box,fill=color,outline=(15,15,15),width=2)
            else:draw.rectangle(box,fill=color,outline=(240,240,240),width=2)
        textures.append(np.asarray(image.filter(ImageFilter.GaussianBlur(.45)),dtype=np.float64))
    f=650.;cx=width/2;cy=height/2;yy,xx=np.mgrid[:height,:width]
    xd=(xx+.5-cx)/f;yd=(yy+.5-cy)/f;xu=xd.copy();yu=yd.copy()
    # Invert the independently specified SIMPLE_RADIAL forward projection.
    for _ in range(12):
        factor=1+radial*(xu*xu+yu*yu);xu=xd/factor;yu=yd/factor
    rays=np.stack((xu,yu,np.ones_like(xx)),axis=-1);records=[]
    for i,x in enumerate(np.linspace(-.85,.85,8)):
        center=np.array([x,.16*np.sin(i*1.7),.10*np.cos(i*1.1)])
        forward=np.array([0.,0.,4.2])-center;forward/=np.linalg.norm(forward)
        right=np.cross(forward,[0.,-1.,0.]);right/=np.linalg.norm(right)
        down=np.cross(forward,right);rotation=np.stack([right,down,forward])
        world=rays@rotation;distance=np.full((height,width),np.inf);rgb=np.zeros((height,width,3))
        for plane,texture in zip(planes,textures):
            px,py,z,w,h=plane;t=(z-center[2])/world[:,:,2];point=center+world*t[:,:,None]
            u=(point[:,:,0]-px)/w+.5;v=(point[:,:,1]-py)/h+.5
            valid=(t>0)&(t<distance)&(u>=0)&(u<=1)&(v>=0)&(v<=1)
            tx=np.clip(u*767,0,767);ty=np.clip(v*767,0,767);x0=tx.astype(int);y0=ty.astype(int)
            x1=np.minimum(x0+1,767);y1=np.minimum(y0+1,767);a=(tx-x0)[:,:,None];b=(ty-y0)[:,:,None]
            sample=(1-b)*((1-a)*texture[y0,x0]+a*texture[y0,x1])+b*((1-a)*texture[y1,x0]+a*texture[y1,x1])
            rgb[valid]=sample[valid];distance[valid]=t[valid]
        name=f"photo-{i:02}.png";Image.fromarray(np.rint(rgb).clip(0,255).astype(np.uint8)).save(root/name)
        records.append({"name":name,"center":center.tolist(),"rotation":rotation.tolist()})
    return {"schema":"independent-textured-plane-photographs","width":width,"height":height,
            "camera_model":"SIMPLE_RADIAL" if radial else "PINHOLE",
            "camera_params":[f,cx,cy,radial] if radial else [f,f,cx,cy],"planes":planes,"images":records}


def geometry_metrics(output,truth):
    """Read the actual serialized model; derive errors independently of its QC."""
    import numpy as np
    import pycolmap
    model=pycolmap.Reconstruction(Path(output));ordered=[];expected=[];rotations=[]
    for index,item in enumerate(truth["images"]):
        image=next(v for v in model.images.values() if v.name==f"{index:03d}_photo_{index:02d}.png")
        ordered.append(image.projection_center());expected.append(item["center"]);rotations.append(image.cam_from_world().rotation.matrix())
    a=np.array(ordered);b=np.array(expected);ac=a-a.mean(0);bc=b-b.mean(0)
    u,s,vt=np.linalg.svd(bc.T@ac/len(a));d=np.eye(3);d[-1,-1]=np.sign(np.linalg.det(u@vt));rotation=u@d@vt
    scale=np.sum(s*np.diag(d))/np.mean(np.sum(ac*ac,axis=1));translation=b.mean(0)-scale*rotation@a.mean(0)
    aligned=scale*(a@rotation.T)+translation;camera_error=np.sqrt(np.mean(np.sum((aligned-b)**2,axis=1)))
    angles=[]
    for solved,expected in zip(rotations,truth["images"]):
        relative=(solved@rotation.T)@np.array(expected["rotation"]).T
        angles.append(float(np.degrees(np.arccos(np.clip((np.trace(relative)-1)/2,-1,1)))))
    points=np.array([p.xyz for p in model.points3D.values()]);p=scale*(points@rotation.T)+translation;distances=[]
    for x,y,z,w,h in truth["planes"]:
        dx=np.maximum(np.abs(p[:,0]-x)-w/2,0);dy=np.maximum(np.abs(p[:,1]-y)-h/2,0)
        distances.append(np.sqrt(dx*dx+dy*dy+(p[:,2]-z)**2))
    surface=np.min(np.array(distances),axis=0);errors=[]
    for image in model.images.values():
        pose=image.cam_from_world();r=pose.rotation.matrix();t=pose.translation;params=image.camera.params
        for point in image.points2D:
            if not point.has_point3D():continue
            q=r@model.points3D[point.point3D_id].xyz+t;x,y=q[:2]/q[2]
            if image.camera.model_name=="PINHOLE":fx,fy,cx,cy=params;projected=[fx*x+cx,fy*y+cy]
            elif image.camera.model_name=="SIMPLE_RADIAL":
                f,cx,cy,k=params;factor=1+k*(x*x+y*y);projected=[f*x*factor+cx,f*y*factor+cy]
            else:raise AssertionError("Fixture geometry checker supports explicit PINHOLE/SIMPLE_RADIAL only")
            errors.append(float(np.linalg.norm(np.array(projected)-point.xy)))
    return {"registered":model.num_reg_images(),"points":model.num_points3D(),"observations":len(errors),
            "camera_rmse":float(camera_error),"camera_angle_max_degrees":max(angles),
            "surface_median_error":float(np.median(surface)),"surface_95_error":float(np.percentile(surface,95)),
            "reprojection_rms":float(np.sqrt(np.mean(np.square(errors)))),"alignment_scale":float(scale)}


def _project(root,truth):
    assets=[]
    for index,record in enumerate(truth["images"]):
        path=root/"media"/record["name"];data=path.read_bytes()
        assets.append({"id":f"photo_{index:02d}","name":record["name"],"kind":"image","path":"media/"+record["name"],
                       "width":truth["width"],"height":truth["height"],"size":len(data),"sha256":hashlib.sha256(data).hexdigest()})
    settings=reconstruction.default_settings();settings.update(asset_ids=[a["id"] for a in assets],camera_model=truth["camera_model"],
        camera_params=truth["camera_params"],refine_intrinsics=False,max_image_size=640,marker_limit=150)
    return {"id":"reconstruction_test","width":640,"height":480,"settings":{"scene":default_scene(640,480)},"assets":assets},settings


def _virtual_project():
    assets=[{"id":f"photo_{i}","kind":"image","path":f"media/{i}.png","width":640,"height":480,"size":4,"sha256":"0"*64} for i in range(3)]
    settings=reconstruction.default_settings();settings["asset_ids"]=[a["id"] for a in assets]
    return {"assets":assets},settings


class ReconstructionValidationTests(unittest.TestCase):
    def test_server_import_has_no_optional_engine_dependencies(self):
        code="import sys;sys.path.insert(0,sys.argv[1]);import reconstruction,install_reconstruction;print([n for n in ('pycolmap','numpy','PIL') if n in sys.modules])"
        result=subprocess.run([sys.executable,"-I","-B","-c",code,str(Path(__file__).parent)],capture_output=True,text=True,check=True,timeout=10)
        self.assertEqual("[]",result.stdout.strip())

    def test_missing_engine_does_not_claim_reconstruction_or_dense_support(self):
        caps=reconstruction.capabilities("/missing/COLMAP/python")
        self.assertFalse(caps["available"]);self.assertFalse(caps["dense_available"]);self.assertEqual([],caps["operations"])
        self.assertIn("not installed",caps["reason"])

    def test_settings_are_strict_bounded_data(self):
        value=reconstruction.default_settings();before=copy.deepcopy(value)
        for change in ({"version":True},{"asset_ids":["a","a"]},{"asset_ids":["../outside"]},{"camera_model":[]},
                       {"camera_model":"FISHEYE"},{"matching":[]},{"up_axis":[]},{"max_features":8193},
                       {"threads":True},{"seed":float("nan")},{"scale":10**1000},{"marker_limit":5001},
                       {"camera_params":[650,320,240,float("inf")]},{"refine_intrinsics":1},
                       {"require_all_images":None},{"command":"arbitrary"}):
            with self.subTest(change=change),self.assertRaises(ValueError):reconstruction.validate_settings({**value,**change})
        self.assertEqual(before,value)

    def test_calibrations_are_model_specific_and_preserved(self):
        for model,params in (("PINHOLE",[650,620,320,240]),("SIMPLE_RADIAL",[650,320,240,.08]),
                             ("OPENCV",[650,620,320,240,.1,-.02,.001,-.002])):
            value={**reconstruction.default_settings(),"camera_model":model,"camera_params":params}
            self.assertEqual(params,reconstruction.validate_settings(value)["camera_params"])
            for broken in ([0,*params[1:]],params[:-1],[True,*params[1:]]):
                with self.subTest(model=model,broken=broken),self.assertRaises(ValueError):reconstruction.validate_settings({**value,"camera_params":broken})

    def test_recipe_rejects_dense_raw_missing_and_ambiguous_inputs(self):
        project,settings=_virtual_project();recipe={"operation":"reconstruct","settings":settings}
        self.assertEqual(recipe,reconstruction.validate_recipe(recipe,project))
        with self.assertRaisesRegex(ValueError,"CUDA"):reconstruction.validate_recipe({**recipe,"operation":"dense"},project)
        with self.assertRaisesRegex(ValueError,"calibrated"):reconstruction.validate_recipe({**recipe,"settings":{**settings,"refine_intrinsics":False}},project)
        for mutate in (lambda p:p["assets"].append(copy.deepcopy(p["assets"][0])),
                       lambda p:p["assets"][0].update(kind="video"),lambda p:p["assets"][0].update(path="media/a.dng"),
                       lambda p:p["assets"][0].update(width=8192,height=8192)):
            broken=copy.deepcopy(project);mutate(broken)
            with self.assertRaises(ValueError):reconstruction.validate_recipe(recipe,broken)
        with self.assertRaisesRegex(ValueError,"3–48"):reconstruction.validate_recipe({**recipe,"settings":{**settings,"asset_ids":["photo_0"]}},project)

    def test_pre_cancel_changes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-cancel-") as temporary:
            root=Path(temporary);project,settings=_virtual_project();event=threading.Event();event.set()
            with self.assertRaises(InterruptedError):
                reconstruction.run(project,root,{"operation":"reconstruct","settings":settings},root/"reconstruction/outputs"/("a"*32),cancel_event=event,python=sys.executable)
            self.assertEqual([],list(root.iterdir()))

    def test_existing_outputs_and_symlink_directories_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-ownership-") as temporary:
            root=Path(temporary);project,settings=_virtual_project();recipe={"operation":"reconstruct","settings":settings}
            output=root/"reconstruction/outputs"/("a"*32);output.mkdir(parents=True);(output/"keep").write_bytes(b"preserved")
            with self.assertRaisesRegex(ValueError,"overwritten"):reconstruction.run(project,root,recipe,output,python=sys.executable)
            self.assertEqual(b"preserved",(output/"keep").read_bytes())
            other=root/"other";other.mkdir();(other/"reconstruction").symlink_to(root/"reconstruction",target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"symbolic"):reconstruction.run(project,other,recipe,other/"reconstruction/outputs"/("b"*32),python=sys.executable)
            self.assertEqual(["a"*32],[p.name for p in output.parent.iterdir()])

    def test_source_identity_mismatch_and_input_symlink_fail_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-source-") as temporary:
            root=Path(temporary);(root/"media").mkdir();(root/"media/0.png").write_bytes(b"test")
            project,settings=_virtual_project();recipe={"operation":"reconstruct","settings":settings};output=root/"reconstruction/outputs"/("a"*32)
            with self.assertRaisesRegex(ValueError,"admitted identity"):reconstruction.run(project,root,recipe,output,python=sys.executable)
            (root/"media/0.png").rename(root/"keep.png");(root/"media/0.png").symlink_to(root/"keep.png")
            with self.assertRaisesRegex(ValueError,"symbolic"):reconstruction.run(project,root,recipe,output,python=sys.executable)
            self.assertEqual(b"test",(root/"keep.png").read_bytes());self.assertEqual([],list(output.parent.iterdir()))

    def test_worker_explicitly_disables_bytecode_under_isolation(self):
        self.assertEqual([sys.executable,"-I","-B"],reconstruction._command(sys.executable)[:3])


class ReconstructionInstallerTests(unittest.TestCase):
    def test_both_platform_locks_bind_every_wheel_and_size(self):
        for target,total in (("linux-x86_64-py312",62063012),("macos-arm64-py313",31083204)):
            lock,digest=installer.load_lock(target)
            self.assertEqual(total,sum(p["size"] for p in lock["packages"]));self.assertEqual(64,len(digest))
            self.assertEqual(installer.PINNED_PACKAGES,{p["name"]:p["version"] for p in lock["packages"]})
            self.assertEqual(len(lock["packages"]),len({p["filename"] for p in lock["packages"]}))

    def test_information_has_no_filesystem_side_effect(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-info-") as temporary:
            root=Path(temporary);result=installer.info(root/"new/runtime")
            self.assertFalse(result["destination_exists"]);self.assertTrue(result["bounded_step"])
            self.assertEqual([],list(root.iterdir()))

    def test_installer_cli_runs_under_interpreter_isolation(self):
        result=subprocess.run([sys.executable,"-I","-B",str(Path(installer.__file__)),"--info"],capture_output=True,text=True,timeout=10)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual("reconstruction",json.loads(result.stdout)["runtime"])

    def test_unmanaged_destination_and_unrelated_symlink_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-installer-") as temporary:
            root=Path(temporary);destination=root/"existing";destination.mkdir();(destination/"keep").write_bytes(b"unchanged")
            with self.assertRaisesRegex(ValueError,"unmanaged"):installer.step(destination)
            link=root/"link";link.symlink_to(destination,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"unrelated"):installer.step(link)
            self.assertEqual(b"unchanged",(destination/"keep").read_bytes());self.assertEqual(str(destination),os.readlink(link))
            self.assertEqual({"existing","link"},{p.name for p in root.iterdir()})

    def test_cancelled_install_creates_no_directory_or_journal(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-install-cancel-") as temporary:
            root=Path(temporary);event=threading.Event();event.set()
            with self.assertRaises(InterruptedError):installer.step(root/"new/runtime",cancel_event=event)
            self.assertEqual([],list(root.iterdir()))


class ReconstructionRuntimeTests(unittest.TestCase):
    @classmethod
    def runtime(cls,program,*args,timeout=90):
        result=subprocess.run([cls.python,"-I","-B","-c",program,str(Path(__file__).parent),*map(str,args)],
            capture_output=True,text=True,timeout=timeout,env=reconstruction._env())
        if result.returncode:raise AssertionError(result.stderr+result.stdout)
        return json.loads(result.stdout)

    @classmethod
    def setUpClass(cls):
        cls.python=reconstruction.find_python()
        if not cls.python:raise unittest.SkipTest("The optional managed COLMAP runtime is not installed")
        caps=reconstruction.capabilities(cls.python)
        if not caps["available"]:raise unittest.SkipTest(caps["reason"])
        cls.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-TEST-");cls.addClassCleanup(cls.temporary.cleanup)
        cls.root=Path(cls.temporary.name);cls.progress=[]
        program="import sys,json;sys.path.insert(0,sys.argv[1]);from test_reconstruction import photographs;print(json.dumps(photographs(sys.argv[2],float(sys.argv[3]))))"
        cls.truth=cls.runtime(program,cls.root/"media",0)
        cls.project,cls.settings=_project(cls.root,cls.truth);cls.original=copy.deepcopy(cls.project)
        cls.recipe={"operation":"reconstruct","settings":cls.settings};cls.output=cls.root/"reconstruction/outputs"/("1"*32)
        cls.result=reconstruction.run(cls.project,cls.root,cls.recipe,cls.output,progress=cls.progress.append,python=cls.python)
        cls.metrics=cls.runtime("import sys,json;sys.path.insert(0,sys.argv[1]);from test_reconstruction import geometry_metrics;print(json.dumps(geometry_metrics(sys.argv[2],json.loads(sys.argv[3]))))",cls.output,json.dumps(cls.truth))
        cls.metadata=json.loads((cls.output/"reconstruction.json").read_text())

    def test_real_sfm_recovers_independent_camera_and_surface_geometry(self):
        m=self.metrics
        self.assertEqual(8,m["registered"]);self.assertGreater(m["points"],1000);self.assertGreater(m["observations"],5000)
        self.assertLess(m["camera_rmse"],.005);self.assertLess(m["camera_angle_max_degrees"],.3)
        self.assertLess(m["surface_median_error"],.02);self.assertLess(m["surface_95_error"],.06);self.assertLess(m["reprojection_rms"],.5)
        self.assertAlmostEqual(m["reprojection_rms"],self.result["statistics"]["reprojection"]["rms_pixels"],places=10)

    def test_actual_sift_matching_and_geometric_verification_are_persisted(self):
        with closing(sqlite3.connect((self.output/"database.db").as_uri()+"?mode=ro&immutable=1",uri=True)) as database:
            features=database.execute("SELECT SUM(rows) FROM keypoints").fetchone()[0]
            descriptors=database.execute("SELECT SUM(rows) FROM descriptors").fetchone()[0]
            verified=database.execute("SELECT COUNT(*) FROM two_view_geometries WHERE rows>0").fetchone()[0]
        self.assertGreater(features,10000);self.assertEqual(features,descriptors);self.assertGreater(verified,10)
        self.assertEqual(features,self.result["statistics"]["features"])
        self.assertEqual(verified,self.result["statistics"]["verified_pairs"])
        with closing(sqlite3.connect((self.output/"database.db").as_uri()+"?mode=ro",uri=True)) as database:
            self.assertEqual("delete",database.execute("PRAGMA journal_mode").fetchone()[0])
        self.assertFalse((self.output/"database.db-wal").exists());self.assertFalse((self.output/"database.db-shm").exists())
        self.assertEqual(1,self.progress[-1]);self.assertEqual(sorted(set(self.progress)),self.progress)

    def test_artifacts_and_original_photographs_are_exactly_bound(self):
        receipt=json.loads((self.output/"provenance.json").read_text());artifacts=self.result["artifacts"]
        self.assertEqual({p.name for p in self.output.iterdir()},{a["filename"] for a in artifacts})
        self.assertNotIn("provenance.json",{a["filename"] for a in receipt["artifacts"]})
        for artifact in artifacts:
            data=(self.output/artifact["filename"]).read_bytes()
            self.assertEqual((len(data),hashlib.sha256(data).hexdigest()),(artifact["bytes"],artifact["sha256"]))
        for asset in self.project["assets"]:
            data=(self.root/asset["path"]).read_bytes();self.assertEqual(asset["sha256"],hashlib.sha256(data).hexdigest())
        self.assertEqual(self.original,self.project);self.assertNotIn(str(self.root),json.dumps(receipt))
        self.assertEqual("CPU",receipt["engine"]["device"]);self.assertIn("Not implemented",receipt["scope"]["dense"])

    def test_official_undistorted_pixels_and_intrinsics_are_exported_together(self):
        with zipfile.ZipFile(self.output/"undistorted-images.zip") as archive:
            manifest=json.loads(archive.read("manifest.json"));self.assertEqual(8,len(manifest["cameras"]))
            self.assertEqual({"manifest.json",*[c["undistorted"]["member"] for c in manifest["cameras"]]},set(archive.namelist()))
            for camera in manifest["cameras"]:
                calibrated=camera["undistorted"];data=archive.read(calibrated["member"])
                self.assertEqual("PINHOLE",calibrated["model"]);self.assertEqual(4,len(calibrated["params"]))
                self.assertEqual((len(data),hashlib.sha256(data).hexdigest()),(calibrated["bytes"],calibrated["sha256"]))
                self.assertEqual(b"\x89PNG\r\n\x1a\n",data[:8])
        self.assertEqual(8,len(self.result["cameras"]))

    def test_camera_scene_proposal_preserves_objects_and_explicit_axes_scale(self):
        settings={**self.settings,"up_axis":"Y","scale":.3}
        scene,cameras=reconstruction.scene_proposal(self.project,self.metadata,settings,"2"*32)
        self.assertEqual(self.project["settings"]["scene"]["objects"],scene["objects"][:-1]);self.assertEqual([],scene["camera"]["keyframes"])
        position=self.metadata["cameras"][0]["center"]
        self.assertEqual([.3*position[0],-.3*position[2],.3*position[1]],cameras[0]["camera"]["position"])
        marker=scene["objects"][-1];self.assertEqual(600,len(marker["mesh"]["vertices"]));self.assertEqual(600,len(marker["mesh"]["triangles"]))
        first=self.metadata["marker_points"][0]["xyz"];center=[sum(v[i] for v in marker["mesh"]["vertices"][:4])/4 for i in range(3)]
        for a,b in zip(center,[.3*first[0],-.3*first[2],.3*first[1]]):self.assertAlmostEqual(a,b,places=12)

    def test_actual_ceres_probe_reduces_nonzero_objective(self):
        response=subprocess.run(reconstruction._command(self.python),input=json.dumps({"command":"install_probe"}),capture_output=True,text=True,timeout=15,env=reconstruction._env())
        self.assertEqual(0,response.returncode,response.stderr);report=json.loads(response.stdout)
        self.assertTrue(all(report["checks"].values()));self.assertGreater(report["features"],20)
        before=report["bundle_adjustment"]["initial_cost"];after=report["bundle_adjustment"]["final_cost"]
        self.assertGreater(before,1);self.assertLess(after,before*.0001)

    def test_immutable_published_job_cannot_be_overwritten(self):
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir()}
        with self.assertRaisesRegex(ValueError,"overwritten"):reconstruction.run(self.project,self.root,self.recipe,self.output,python=self.python)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir()})

    def test_real_worker_cancellation_removes_only_its_private_scratch(self):
        event=threading.Event();seen=[];output=self.root/"reconstruction/outputs"/("3"*32);started=time.monotonic()
        def progress(value):
            seen.append(value)
            if value>=.12:event.set()
        with self.assertRaises(InterruptedError):reconstruction.run(self.project,self.root,self.recipe,output,progress,event,self.python)
        self.assertTrue(any(v>=.12 for v in seen));self.assertLess(time.monotonic()-started,15);self.assertFalse(output.exists())
        self.assertEqual([self.output.name],sorted(p.name for p in output.parent.iterdir()))
        for asset in self.project["assets"]:self.assertEqual(asset["sha256"],hashlib.sha256((self.root/asset["path"]).read_bytes()).hexdigest())

    def test_source_change_during_actual_job_prevents_publication(self):
        source=self.root/self.project["assets"][0]["path"];before=source.read_bytes();output=self.root/"reconstruction/outputs"/("4"*32);changed=[]
        def progress(value):
            if value>=.12 and not changed:source.write_bytes(before+b"external edit");changed.append(True)
        try:
            with self.assertRaisesRegex(ValueError,"changed during reconstruction"):
                reconstruction.run(self.project,self.root,self.recipe,output,progress=progress,python=self.python)
            self.assertTrue(changed);self.assertFalse(output.exists());self.assertEqual(before+b"external edit",source.read_bytes())
        finally:source.write_bytes(before)

    def test_actual_radial_sfm_retains_original_model_and_corrected_reference(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-reconstruction-radial-") as temporary:
            root=Path(temporary);truth=self.runtime("import sys,json;sys.path.insert(0,sys.argv[1]);from test_reconstruction import photographs;print(json.dumps(photographs(sys.argv[2],.08)))",root/"media")
            project,settings=_project(root,truth);output=root/"reconstruction/outputs"/("5"*32)
            result=reconstruction.run(project,root,{"operation":"reconstruct","settings":settings},output,python=self.python)
            measured=self.runtime("import sys,json;sys.path.insert(0,sys.argv[1]);from test_reconstruction import geometry_metrics;print(json.dumps(geometry_metrics(sys.argv[2],json.loads(sys.argv[3]))))",output,json.dumps(truth))
            self.__class__.radial_metrics=measured;self.assertEqual(8,measured["registered"]);self.assertLess(measured["camera_rmse"],.005);self.assertLess(measured["reprojection_rms"],.5)
            self.assertIsNone(result["proposal_error"]);self.assertIn("SIMPLE_RADIAL",(output/"cameras.txt").read_text())
            for camera in result["cameras"]:
                self.assertEqual(0,camera["scene_width"]%2);self.assertEqual(0,camera["scene_height"]%2)
                self.assertEqual(camera["width"]*camera["scene_canvas_scale"],camera["scene_width"])
                self.assertEqual(camera["height"]*camera["scene_canvas_scale"],camera["scene_height"])
            metadata=json.loads((output/"reconstruction.json").read_text());normalized={x["asset_id"]:x for x in metadata["normalization"]["photos"]}
            for camera in metadata["cameras"]:
                self.assertEqual("SIMPLE_RADIAL",camera["source_model"]);self.assertEqual([650.,320.,240.,.08],camera["source_params"])
                self.assertEqual("PINHOLE",camera["undistorted"]["model"])
                self.assertNotEqual(normalized[camera["asset_id"]]["normalized_sha256"],camera["undistorted"]["sha256"])


if __name__=="__main__":unittest.main()

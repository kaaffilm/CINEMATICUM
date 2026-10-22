"""Typed transport and real CPU radiance/AD acceptance.

Set CINEMATICUM_PHYSICAL_PYTHON to the independently installed pinned runtime.
Set CINEMATICUM_PBRT to an actual PBRT-v4 executable for its separate acceptance.
No test downloads packages, manufactures an engine response or substitutes a
rendering callback. The tests inspect float pixels and actual parameter gradients.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import physical_rendering as physical
from scene import default_scene, object_matrix_at, validate_scene
from spatial_import import validate_mesh


def fixture(width=32,height=32):
    scene=default_scene(width,height)
    scene["camera"].update(position=[0,0,4],target=[0,0,0],fov=35)
    scene["lights"]=[]
    scene["objects"]=[{"id":"surface","name":"Surface","type":"plane","position":[0,0,0],"rotation":[0,0,0],"scale":[5,5,1]}]
    settings=physical.default_settings()
    settings.update(mode="rgb",spp=64,world_spectrum={"type":"uniform","value":1.},
                    material_overrides={"surface":{"type":"diffuse","reflectance":{"type":"rgb","value":[.2,.4,.6]}}})
    return validate_scene(scene),physical.validate_settings(settings,scene)


class PhysicalValidationTests(unittest.TestCase):
    def test_server_import_is_standard_library_only(self):
        code="import sys;sys.path.insert(0,sys.argv[1]);import physical_rendering;print([n for n in ('mitsuba','drjit','numpy') if n in sys.modules])"
        result=subprocess.run([sys.executable,"-I","-B","-c",code,str(Path(__file__).parent)],capture_output=True,text=True,check=True,timeout=15)
        self.assertEqual("[]",result.stdout.strip())

    def test_missing_runtime_is_an_explicit_failure(self):
        result=physical.capabilities("/does-not-exist/python")
        self.assertFalse(result["available"])
        self.assertEqual(["pbrt_export","pbrt_import"],result["operations"])
        self.assertIn("not installed",result["reason"])

    def test_strict_settings_bounds_and_references(self):
        scene,settings=fixture();before=copy.deepcopy(settings)
        for change in ({"version":True},{"mode":[]},{"spp":True},{"spp":0},{"seed":float("nan")},
                       {"max_depth":65},{"frame":7201},{"filename":"/tmp/result.exr"},
                       {"material_overrides":{"missing":{"type":"diffuse"}}},
                       {"light_spectra":{"missing":{"type":"uniform","value":1}}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                physical.validate_settings({**settings,**change},scene)
        self.assertEqual(before,settings)

    def test_spectral_curves_and_band_semantics_are_strict(self):
        for curve in ({"type":"sampled","wavelengths":[500,400],"values":[1,1]},
                      {"type":"sampled","wavelengths":[400,400],"values":[1,1]},
                      {"type":"sampled","wavelengths":[200,500],"values":[1,1]},
                      {"type":"rgb","value":[1,2]}, {"type":"uniform","value":float("inf")},
                      {"type":"spectrum","filename":"secret.spd"}):
            with self.subTest(curve=curve),self.assertRaises(ValueError):physical.validate_spectrum(curve)
        with self.assertRaises(ValueError):physical.validate_spectrum({"type":"uniform","value":1.001},reflectance=True)
        settings=physical.default_settings()
        for bands in ([{"name":"R","min_nm":400,"max_nm":500}], [{"name":"blue","min_nm":500,"max_nm":400}],
                      [{"name":"same","min_nm":400,"max_nm":500}]*2):
            with self.subTest(bands=bands),self.assertRaises(ValueError):physical.validate_settings({**settings,"spectral_bands":bands})

    def test_inverse_and_camera_limits_fail_before_work(self):
        scene,settings=fixture();project={"settings":{"scene":scene}}
        with self.assertRaisesRegex(ValueError,"selected object"):
            physical.validate_recipe({"operation":"inverse","settings":settings,"target_asset_id":"image"},project)
        for change in ({"focal_ratio":1.2},{"dof_enabled":True,"aperture_blades":5}):
            broken=copy.deepcopy(scene);broken["camera"].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):physical.validate_recipe({"operation":"render","settings":settings},{"settings":{"scene":broken}})
        big=default_scene(2048,2048)
        with self.assertRaisesRegex(ValueError,"pixel samples"):
            physical.validate_recipe({"operation":"render","settings":physical.default_settings()},{"settings":{"scene":big}})

    def test_material_inputs_are_data_and_polarization_is_explicit(self):
        for value in ({"type":[]},{"type":"principled","filename":"material.xml"},{"type":"diffuse","script":"code"},
                      {"type":"dielectric","ior":0},{"type":"polarizer","angle":float("nan")},
                      {"type":"conductor","eta":{"type":"uniform","value":1},"k":{"type":"uniform","value":-1}}):
            with self.subTest(value=value),self.assertRaises(ValueError):physical.validate_material(value)
        scene,settings=fixture();settings["material_overrides"]["surface"]={"type":"polarizer"}
        with self.assertRaisesRegex(ValueError,"polarized"):physical.validate_settings(settings,scene)

    def test_worker_argv_disables_bytecode_under_isolation(self):
        with patch.object(physical,"find_python",return_value=sys.executable):
            self.assertEqual([sys.executable,"-I","-B"],physical._command()[:3])

    def test_versioned_macos_llvm_discovery_and_invalid_override_refusal(self):
        versioned="/opt/homebrew/opt/llvm@20/lib/libLLVM.dylib"
        unversioned="/opt/homebrew/opt/llvm/lib/libLLVM.dylib"
        # This tests path selection only. Actual dylib loading, CPU pixels and
        # derivatives are separate required installer/native acceptance gates.
        with patch.dict(os.environ,{"DRJIT_LIBLLVM_PATH":"/untrusted/inherited"},clear=True), \
             patch.object(physical,"sys_platform_is_macos",return_value=True):
            with patch.object(Path,"is_file",lambda path:str(path)==versioned):
                self.assertEqual(versioned,physical._env()["DRJIT_LIBLLVM_PATH"])
            with patch.object(Path,"is_file",lambda path:str(path) in {unversioned,versioned}):
                self.assertEqual(unversioned,physical._env()["DRJIT_LIBLLVM_PATH"])
            with patch.object(Path,"is_file",return_value=False):
                self.assertNotIn("DRJIT_LIBLLVM_PATH",physical._env())
            for missing in ("relative/libLLVM.dylib","/does-not-exist/libLLVM.dylib"):
                with patch.dict(os.environ,{"CINEMATICUM_PHYSICAL_LLVM":missing}),self.assertRaisesRegex(RuntimeError,"existing absolute"):
                    physical._env()
        with tempfile.TemporaryDirectory() as temporary:
            explicit=Path(temporary)/"chosen-library";explicit.write_bytes(b"path-selection-only")
            with patch.dict(os.environ,{"CINEMATICUM_PHYSICAL_LLVM":str(explicit)},clear=True):
                self.assertEqual(str(explicit),physical._env()["DRJIT_LIBLLVM_PATH"])

    def test_fixed_managed_pbrt_discovery_preserves_explicit_precedence(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{},clear=True), \
             patch.object(physical.shutil,"which",return_value=None),patch.object(Path,"home",return_value=Path(temporary)):
            for macos,base in ((True,"Library/Application Support"),(False,".local/share")):
                with self.subTest(macos=macos),patch.object(physical,"sys_platform_is_macos",return_value=macos):
                    binary=Path(temporary)/base/"CINEMATICUM/Physical/pbrt-v4-b4ce9687-v1/bin/pbrt"
                    self.assertIsNone(physical.find_pbrt())
                    binary.parent.mkdir(parents=True);binary.write_bytes(b"path-selection-only")
                    binary.chmod(0o600);self.assertIsNone(physical.find_pbrt())
                    binary.chmod(0o700);self.assertEqual(str(binary),physical.find_pbrt())
                    with patch.dict(os.environ,{"CINEMATICUM_PBRT":"/explicit/missing"}):
                        self.assertIsNone(physical.find_pbrt())
                    with patch.object(physical.shutil,"which",return_value=sys.executable):
                        self.assertEqual(sys.executable,physical.find_pbrt())

    def test_primitive_meshes_are_closed_or_intentional_planes_and_sphere_faces_point_outward(self):
        for kind,count in (("cube",12),("plane",2),("sphere",960),("cylinder",128)):
            mesh=physical.geometry_mesh({"type":kind})
            self.assertEqual(count,len(mesh["triangles"]))
            if kind=="sphere":
                for triangle in mesh["triangles"]:
                    a,b,c=[mesh["vertices"][i] for i in triangle]
                    u=[y-x for x,y in zip(a,b)];v=[y-x for x,y in zip(a,c)]
                    n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                    self.assertGreater(sum(x*y for x,y in zip(n,a)),0)


class PBRTTransportTests(unittest.TestCase):
    def test_real_v4_grammar_static_roundtrip_preserves_float_geometry_and_spectra(self):
        scene,settings=fixture(32,24)
        mesh=validate_mesh({"version":1,"vertices":[[-1,-1,0],[1,-1,0],[0,1,0]],"triangles":[[0,1,2]],
                            "normals":[[0,0,1]],"normal_indices":[[0,0,0]],"uvs":[[0,0],[1,0],[.5,1]],"uv_indices":[[0,1,2]]})
        scene["objects"][0].update(type="mesh",mesh=mesh,position=[.25,.5,0],scale=[2,1,1],rotation=[15,0,30])
        settings.update(mode="spectral",world_spectrum={"type":"sampled","wavelengths":[360.,500.,830.],"values":[.2,1.7,.1]})
        text=physical.export_pbrt(scene,settings)
        self.assertIn('"point3 P"',text);self.assertIn('Film "rgb"',text);self.assertNotIn("WorldEnd",text)
        imported,returned=physical.import_pbrt(text)
        self.assertEqual(settings["world_spectrum"],returned["world_spectrum"])
        self.assertEqual((32,24),(imported["width"],imported["height"]))
        expected=physical._world_mesh(mesh,object_matrix_at(scene,"surface",1))
        actual=imported["objects"][0]["mesh"]
        for key in ("vertices","normals","uvs"):
            flat=physical._flatten_mesh(expected)[key]
            self.assertEqual(len(flat),len(actual[key]))
            for p,q in zip(flat,actual[key]):
                for a,b in zip(p,q):self.assertAlmostEqual(a,b,places=10)

    def test_unknown_features_and_parameters_are_never_silently_dropped(self):
        scene,settings=fixture();base=physical.export_pbrt(scene,settings)
        for suffix in ('Include "outside.pbrt"','Texture "x" "spectrum" "imagemap" "string filename" "private.png"',
                       'WorldEnd','Material "plastic"','Shape "sphere" "float radius" 1',
                       'LightSource "spot"','AttributeEnd','MakeNamedMedium "fog" "string type" "homogeneous"'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):physical.import_pbrt(base+suffix)
        with self.assertRaisesRegex(ValueError,"unsupported parameters"):
            physical.import_pbrt(base.replace('"rgb reflectance" [0.2 0.4 0.6]','"rgb reflectance" [0.2 0.4 0.6] "float mystery" [1]'))
        with self.assertRaisesRegex(ValueError,"output filename"):
            physical.import_pbrt(base.replace('"render.exr"','"../outside.exr"'))

    def test_pbrt_transform_column_major_and_negative_orientation(self):
        scene,settings=fixture();base=physical.export_pbrt(scene,settings)
        transform='Transform [1 0 0 0 0 1 0 0 0 0 1 0 2 3 4 1]\nReverseOrientation\n'
        imported,_=physical.import_pbrt(base.replace('Shape "trianglemesh"',transform+'Shape "trianglemesh"'))
        mesh=imported["objects"][0]["mesh"]
        self.assertEqual([-3.,-2.,4.],mesh["vertices"][0])
        self.assertEqual([2,1,0],mesh["triangles"][0])

    def test_pbrt_metal_and_shift_boundaries_are_explicit(self):
        scene,settings=fixture();settings["material_overrides"]={}
        scene["objects"][0]["material"]["metallic"]=.5
        with self.assertRaisesRegex(ValueError,"explicit physical material"):physical.export_pbrt(scene,settings)
        scene["objects"][0]["material"]["metallic"]=0;scene["camera"]["shift_x"]=.1
        with self.assertRaisesRegex(ValueError,"shifted"):physical.export_pbrt(scene,settings)

    def test_pbrt_camera_handedness_and_implicit_film_defaults_are_never_changed(self):
        scene,settings=fixture();base=physical.export_pbrt(scene,settings)
        for before,after,reason in (('Scale -1 1 1\n','','handedness'),
                                    ('Scale -1 1 1','Scale 1 1 1','camera transforms'),
                                    ('PixelFilter "box"\n','','implicit renderer defaults'),
                                    ('"bool savefp16" [false]','"bool savefp16" [true]','savefp16'),
                                    (' "bool savefp16" [false]','','savefp16'),
                                    (' "string filename" ["render.exr"]','','output filename')):
            with self.subTest(before=before,after=after),self.assertRaisesRegex(ValueError,reason):
                physical.import_pbrt(base.replace(before,after))

    def test_export_import_needs_no_optional_engine_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-physical-transport-") as temporary:
            root=Path(temporary);scene,settings=fixture();project={"settings":{"scene":scene}}
            result=physical.run(project,root,{"operation":"pbrt_export","settings":settings},root/"physical/outputs/export",python="/missing")
            before={p.name:p.read_bytes() for p in (root/"physical/outputs/export").iterdir()}
            with self.assertRaisesRegex(ValueError,"overwritten"):
                physical.run(project,root,{"operation":"pbrt_export","settings":settings},root/"physical/outputs/export",python="/missing")
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/"physical/outputs/export").iterdir()})
            receipt=json.loads(before["provenance.json"])
            self.assertNotIn("provenance.json",[a["filename"] for a in receipt["artifacts"]])
            self.assertEqual(set(before),{a["filename"] for a in result["artifacts"]})
            imported=physical.run({},root,{"operation":"pbrt_import","settings":physical.default_settings(),"pbrt_text":before["scene.pbrt"].decode()},root/"physical/outputs/import",python="/missing")
            self.assertEqual(1,len(imported["scene"]["objects"]))

    def test_output_and_input_symlinks_are_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-physical-ownership-") as temporary:
            root=Path(temporary);outside=root/"preserved";outside.mkdir();(outside/"keep").write_bytes(b"existing")
            (root/"physical").symlink_to(outside,target_is_directory=True)
            scene,settings=fixture()
            with self.assertRaisesRegex(ValueError,"symbolic"):
                physical.run({"settings":{"scene":scene}},root,{"operation":"pbrt_export","settings":settings},root/"physical/outputs/x")
            self.assertEqual(["keep"],[p.name for p in outside.iterdir()])


class _PhysicalRuntimeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python=physical.find_python()
        if not cls.python:raise unittest.SkipTest("The optional physical rendering runtime is not installed")
        caps=physical.capabilities(cls.python)
        if not caps["available"]:raise unittest.SkipTest(caps["reason"])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="cinematicum-physical-TEST-");self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.scene,self.settings=fixture()
        self.project={"settings":{"scene":self.scene},"width":32,"height":32,"assets":[]};self.counter=0

    def run_job(self,settings=None,operation="render",**extra):
        self.counter+=1
        return physical.run(self.project,self.root,{"operation":operation,"settings":settings or self.settings,**extra},
                            self.root/"physical/outputs"/str(self.counter),python=self.python)

    def output(self,result,name):return self.root/"physical/outputs"/result["output_id"]/name

    def runtime(self,program,*args):
        result=subprocess.run([self.python,"-I","-B","-c",program,str(Path(__file__).parent),*map(str,args)],
                              capture_output=True,text=True,timeout=60,env=physical._env())
        self.assertEqual(0,result.returncode,result.stderr+result.stdout)
        return json.loads(result.stdout)


class PhysicalRuntimeTests(_PhysicalRuntimeCase):
    def test_real_diffuse_radiance_float_output_and_receipt_identity(self):
        result=self.run_job();metrics=result["provenance"]["metrics"]
        self.assertEqual("float32",metrics["dtype"]);self.assertEqual(["R","G","B"],metrics["channels"])
        for expected,actual in zip((.2,.4,.6),metrics["mean"]):self.assertAlmostEqual(expected,actual,delta=.008)
        self.assertEqual("sRGB",result["provenance"]["display_encoding"])
        for artifact in result["artifacts"]:
            data=self.output(result,artifact["filename"]).read_bytes()
            self.assertEqual(artifact["sha256"],hashlib.sha256(data).hexdigest());self.assertEqual(len(data),artifact["bytes"])
        self.assertNotIn(str(self.root),self.output(result,"provenance.json").read_text())

    def test_real_spectral_bands_integrate_energy_and_retain_negative_rgb(self):
        self.scene["objects"]=[];settings=physical.default_settings();settings.update(spp=256,
            world_spectrum={"type":"sampled","wavelengths":[360,590,600,640,650,830],"values":[0,0,1,1,0,0]},
            spectral_bands=[{"name":"blue","min_nm":400,"max_nm":500},{"name":"red","min_nm":600,"max_nm":640}])
        result=self.run_job(settings);metrics=result["provenance"]["metrics"];bands=metrics["spectral"]
        self.assertEqual(["blue","red"],bands["channels"]);self.assertEqual(0.,bands["mean"][0])
        self.assertAlmostEqual(40.,bands["mean"][1],delta=.15);self.assertLess(metrics["min"],0)
        self.assertTrue(self.output(result,"spectral.exr").is_file())

    def test_actual_stokes_and_crossed_polarizers(self):
        self.scene["objects"]=[{"id":"p1","name":"First","type":"plane","position":[0,0,0],"rotation":[0,0,0],"scale":[5,5,1]},
                               {"id":"p2","name":"Second","type":"plane","position":[0,0,1],"rotation":[0,0,0],"scale":[5,5,1]}]
        settings=physical.default_settings();settings.update(mode="polarized",spp=128,world_spectrum={"type":"uniform","value":1},
            material_overrides={"p1":{"type":"polarizer","angle":0},"p2":{"type":"polarizer","angle":0}})
        aligned=self.run_job(settings)["provenance"]["metrics"]
        self.assertEqual(15,len(aligned["channels"]));self.assertIn("S3.B",aligned["channels"])
        for i in range(3):self.assertAlmostEqual(aligned["mean"][3+i],aligned["mean"][6+i],delta=1e-5)
        settings["material_overrides"]["p2"]["angle"]=90
        crossed=self.run_job(settings)["provenance"]["metrics"]
        self.assertLess(sum(crossed["mean"][:3]),sum(aligned["mean"][:3])*.004)
        self.assertGreater(sum(aligned["mean"][:3]),1.)

    def test_quarter_wave_retarder_creates_measured_circular_polarization(self):
        # Quarter-wave circular polarization is a normal-incidence property.
        # A narrow field avoids averaging the oblique-incidence retarder response.
        self.scene["camera"]["fov"]=10
        self.scene["objects"]=[{"id":"p1","name":"Polarizer","type":"plane","position":[0,0,0],"rotation":[0,0,0],"scale":[5,5,1]},
                               {"id":"p2","name":"Retarder","type":"plane","position":[0,0,1],"rotation":[0,0,0],"scale":[5,5,1]}]
        settings=physical.default_settings();settings.update(mode="polarized",spp=128,world_spectrum={"type":"uniform","value":1},
            material_overrides={"p1":{"type":"polarizer","angle":45},"p2":{"type":"retarder","angle":0,"retardance":90}})
        metrics=self.run_job(settings)["provenance"]["metrics"]
        s0=sum(metrics["mean"][3:6]);s3=abs(sum(metrics["mean"][12:15]))
        self.assertGreater(s3/s0,.99)

    def test_actual_camera_rays_preserve_normalized_principal_point_and_roll(self):
        result=self.runtime(r'''
import sys,json,numpy as np,mitsuba as mi
sys.path.insert(0,sys.argv[1]);from test_physical_rendering import fixture
from physical_rendering_worker import build_scene
mi.set_variant('llvm_ad_rgb');s,r=fixture();s['camera'].update(shift_x=.15,shift_y=-.1,roll=27)
scene=build_scene(s,r,mi,np);sensor=scene.sensors()[0]
ray,_=sensor.sample_ray(0,.5,[.65,.6],[.5,.5])
print(json.dumps({'direction':np.array(ray.d).reshape(-1).tolist()}))
''')
        for a,b in zip(result["direction"],[0,0,-1]):self.assertAlmostEqual(a,b,delta=2e-6)

    def test_real_image_gradient_matches_independent_finite_difference(self):
        result=self.runtime(r'''
import sys,json,numpy as np,mitsuba as mi,drjit as dr
sys.path.insert(0,sys.argv[1]);from test_physical_rendering import fixture
from physical_rendering_worker import build_scene
mi.set_variant('llvm_ad_rgb');dr.set_thread_count(2);s,r=fixture();scene=build_scene(s,r,mi,np,inverse=True);p=mi.traverse(scene)
key=next(k for k in p.keys() if k.endswith('reflectance.value'));original=np.array(p[key]).reshape(-1)
dr.enable_grad(p[key]);p.update();image=mi.render(scene,p,spp=512,seed=19);dr.backward(dr.mean(image));gradient=np.array(dr.grad(p[key])).reshape(-1)
finite=[]
for c in range(3):
 values=[]
 for sign in (-1,1):
  color=original.copy();color[c]+=sign*.001;p[key]=mi.Color3f(color);p.update();values.append(float(dr.mean(mi.render(scene,spp=512,seed=19)).array[0]))
 finite.append((values[1]-values[0])/.002)
print(json.dumps({'gradient':gradient.tolist(),'finite':finite}))
''')
        for gradient,finite in zip(result["gradient"],result["finite"]):
            self.assertGreater(abs(gradient),.25);self.assertAlmostEqual(gradient,finite,delta=.006)

    def test_inverse_runs_actual_ad_and_reduces_loss_with_explicit_editable_proposal(self):
        target=self.run_job();target_path=self.output(target,"render.exr")
        media=self.root/"media";media.mkdir();copied=media/"target.exr";shutil.copyfile(target_path,copied)
        digest=hashlib.sha256(copied.read_bytes()).hexdigest()
        self.project["assets"].append({"id":"target","kind":"image","path":"media/target.exr","sha256":digest,"size":copied.stat().st_size})
        settings=physical.validate_settings(self.settings,self.scene);settings["material_overrides"]["surface"]["reflectance"]["value"]=[.7,.2,.1]
        settings["optimization"]={"object_id":"surface","iterations":28,"learning_rate":.05};before=copy.deepcopy(settings)
        result=self.run_job(settings,operation="inverse",target_asset_id="target");report=json.loads(self.output(result,"optimization.json").read_text())
        self.assertLess(report["final_loss"],report["initial_loss"]*.05)
        self.assertEqual(28,len(report["gradients"]));self.assertGreater(sum(abs(v) for row in report["gradients"] for v in row),.1)
        self.assertEqual(before,settings);self.assertEqual(digest,hashlib.sha256(copied.read_bytes()).hexdigest())
        self.assertEqual(result["optimized_settings"],json.loads(self.output(result,"optimized-settings.json").read_text()))
        self.assertEqual(digest,result["receipt"]["inputs"][0]["sha256"])

    def test_real_worker_cancellation_leaves_no_published_or_partial_output(self):
        settings=physical.validate_settings(self.settings,self.scene);settings["spp"]=4096
        event=threading.Event();timer=threading.Timer(.15,event.set);timer.start();self.addCleanup(timer.cancel)
        start=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,"cancelled"):
            physical.run(self.project,self.root,{"operation":"render","settings":settings},self.root/"physical/outputs/cancelled",python=self.python,cancel_event=event)
        self.assertLess(time.monotonic()-start,8)
        self.assertFalse((self.root/"physical/outputs/cancelled").exists())
        self.assertEqual([],list((self.root/"physical/outputs").iterdir()))

    def test_target_identity_mismatch_fails_without_a_rendered_result(self):
        (self.root/"media").mkdir();path=self.root/"media/target.png";path.write_bytes(b"not the admitted original")
        self.project["assets"].append({"id":"target","kind":"image","path":"media/target.png","sha256":"0"*64,"size":path.stat().st_size})
        self.settings["optimization"]["object_id"]="surface"
        with self.assertRaisesRegex(ValueError,"admitted identity"):self.run_job(operation="inverse",target_asset_id="target")
        self.assertEqual([],list((self.root/"physical/outputs").iterdir()))


class PBRTExecutableTests(_PhysicalRuntimeCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pbrt=physical.find_pbrt()
        if not cls.pbrt:raise unittest.SkipTest("Actual PBRT-v4 executable is not installed")

    def test_actual_pbrt_parser_and_spectral_render_of_exported_scene(self):
        self.scene["objects"]=[{"id":"sphere","name":"Sphere","type":"sphere","position":[0,0,0],"rotation":[0,0,0],"scale":[1,1,1]},
                               {"id":"box","name":"Cube","type":"cube","position":[1.5,0,0],"rotation":[0,0,25],"scale":[.3,.4,.5]},
                               {"id":"cylinder","name":"Cylinder","type":"cylinder","position":[-1.5,0,0],"rotation":[0,30,0],"scale":[.4,.4,.6]}]
        self.settings["material_overrides"]={};self.settings["spp"]=16
        result=self.run_job(operation="pbrt_render")
        formatted=subprocess.run([self.pbrt,"--format",str(self.output(result,"scene.pbrt"))],capture_output=True,text=True,timeout=20)
        self.assertEqual(0,formatted.returncode,formatted.stderr);self.assertIn('Shape "trianglemesh"',formatted.stdout)
        metrics=result["provenance"]["metrics"]
        self.assertTrue(metrics["finite"]);self.assertGreater(metrics["max"]-metrics["min"],.1)
        self.assertEqual("pbrt-v4",result["provenance"]["engine"]["name"])
        imported,settings=physical.import_pbrt(formatted.stdout)
        self.assertEqual(3,len(imported["objects"]));self.assertEqual(16,settings["spp"])

    def test_actual_pbrt_camera_preserves_asymmetric_authored_view_and_roll(self):
        self.scene,self.settings=fixture(64,48);self.project["settings"]["scene"]=self.scene
        self.project.update(width=64,height=48)
        self.scene["camera"]["roll"]=23
        self.scene["objects"][0].update(position=[.65,.3,0],scale=[.15,.2,1])
        self.settings.update(spp=32,world_spectrum={"type":"uniform","value":0},material_overrides={
            "surface":{"type":"diffuse","reflectance":{"type":"rgb","value":[0,0,0]},"emission":{"type":"uniform","value":1}}})
        authored=self.run_job();transported=self.run_job(operation="pbrt_render")
        data=self.runtime(r'''
import sys,json,numpy as np,mitsuba as mi
results=[]
for path in sys.argv[2:]:
 a=np.array(mi.Bitmap(path)).sum(2);yy,xx=np.mgrid[:a.shape[0],:a.shape[1]]
 results.append([float((a*xx).sum()/a.sum()),float((a*yy).sum()/a.sum())])
print(json.dumps(results))
''',self.output(authored,"render.exr"),self.output(transported,"render.exr"))
        self.assertGreater(data[0][0],39.)
        for expected,actual in zip(*data):self.assertAlmostEqual(expected,actual,delta=.15)
        imported,_=physical.import_pbrt(self.output(transported,"scene.pbrt").read_text())
        self.assertAlmostEqual(23.,imported["camera"]["roll"],places=8)


if __name__=="__main__":unittest.main()

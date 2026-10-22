"""Planar geometry, source binding, edit invalidation, and real rendered pixels.

Fixtures are synthetic ENGINE TEST media. Inference cases run only with a real
operation-verified OpenCV runtime; prescribed matrices test the independent
compositor and are never reported as measured model/worker acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from engine import probe_media, render_project, validate_project
from planar_tracking import (assert_planar_export_ready, planar_capabilities, planar_motion,
                             track_planar, validate_planar_binding, validate_planar_track,
                             verify_planar_source_files)
from projective_warp import (COORDINATES, IDENTITY, compile_planar_warp, quad_matrix,
                             transform, validate_matrix, validate_planar_motion)
from tracking import _identity

WIDTH, HEIGHT, FRAMES, FPS = 192, 144, 12, 12
QUAD = [[.16, .14], [.68, .14], [.68, .76], [.16, .76]]


def ffmpeg(arguments, data=None):
    return subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y",
                           "-threads", "1", "-filter_complex_threads", "1"]+arguments,
                          input=data, capture_output=True, check=True, timeout=30).stdout


def png(path, width=32, height=32, rgba=(255, 0, 255, 255)):
    def chunk(kind, data):
        return struct.pack(">I", len(data))+kind+data+struct.pack(">I", zlib.crc32(kind+data)&0xffffffff)
    pixels=b"".join(b"\0"+bytes(rgba)*width for _ in range(height))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,6,0,0,0))+
                          chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b""))


def build_fixture(root, lost=False):
    """Moving textured plane with analytically known translation, not a film."""
    root=Path(root);(root/"media").mkdir(exist_ok=True)
    rng=random.Random(294);texture=[rng.choice((32,225)) for _ in range(48*40)]
    raw=bytearray()
    for frame in range(FRAMES):
        picture=bytearray([65,65,65]*(WIDTH*HEIGHT))
        if not(lost and frame==6):
            for y in range(80):
                for x in range(96):
                    value=texture[(y//2)*48+x//2]
                    index=((24+frame+y)*WIDTH+32+2*frame+x)*3
                    picture[index:index+3]=bytes((value,value,value))
        raw.extend(picture)
    video=root/"media"/("ENGINE_TEST_lost.mkv" if lost else "ENGINE_TEST_planar.mkv")
    ffmpeg(["-f","rawvideo","-pixel_format","rgb24","-video_size",f"{WIDTH}x{HEIGHT}",
            "-framerate",str(FPS),"-i","pipe:0","-c:v","ffv1",str(video)],bytes(raw))
    plate=root/"media/ENGINE_TEST_pin.png";png(plate)
    assets=[]
    for ident,path in (("plane",video),("image",plate)):
        asset=probe_media(path);asset.update(id=ident,name=path.name,path="media/"+path.name,
                                           sha256=hashlib.sha256(path.read_bytes()).hexdigest());assets.append(asset)
    project={"version":1,"id":"planar-test","name":"ENGINE TEST planar motion","width":WIDTH,"height":HEIGHT,
             "fps":FPS,"assets":assets,"titles":[],"clips":[{"id":"background","asset_id":"plane","track":0,
             "start":0,"in":0,"duration":FRAMES,"volume":0}],"settings":{}}
    return validate_project(project,root)


def prescribed_track(project):
    """An explicitly prescribed geometry fixture, distinct from inference."""
    clip=project["clips"][0];asset=next(a for a in project["assets"] if a["id"]==clip["asset_id"])
    source=_identity(project,clip,asset);samples=[]
    for frame in range(FRAMES):
        matrix=[1.,0.,2*frame/WIDTH,0.,1.,frame/HEIGHT,0.,0.,1.]
        samples.append({"frame":frame,"visible":True,"matrix":matrix,"corners":[[x+2*frame/WIDTH,y+frame/HEIGHT] for x,y in QUAD],
                        "confidence":1.,"features":100,"inliers":100,"inlier_ratio":1.,"coverage":.7,"error_pixels":0.,"reason":""})
    return {"version":1,"kind":"planar-track","model":"projective","coordinates":COORDINATES,"source":source,
            "reference_frame":0,"reference_quad":copy.deepcopy(QUAD),"analysis_width":WIDTH,"analysis_height":HEIGHT,
            "backend":"PRESCRIBED ENGINE TEST GEOMETRY — NOT MEASURED INFERENCE","samples":samples}


def pin_clip(project, motion):
    background=project["clips"][0]
    return {"id":"pin","asset_id":"image","track":1,"start":background["start"],"in":0,"duration":FRAMES,
            "volume":0,"animation_start":0,"animation_offset":0,"animation_duration":FRAMES,"planar_motion":motion}


class PlanarGeometryTests(unittest.TestCase):
    def test_projective_corners_and_inverse_horizon_are_checked(self):
        quad=[[.1,.2],[.8,.12],[.9,.75],[.2,.9]];matrix=quad_matrix(quad)
        for source,target in zip(((0,0),(1,0),(1,1),(0,1)),quad):
            for actual,expected in zip(transform(matrix,source),target):self.assertAlmostEqual(actual,expected,places=10)
        for bad in ([0.]*9,[1.,0,0,0,1,0,-2,0,1],[1,0,float("nan"),0,1,0,0,0,1]):
            with self.subTest(matrix=bad),self.assertRaises(ValueError):validate_matrix(bad)

    def test_stale_motion_keeps_keys_but_cannot_execute_or_export(self):
        motion={"version":1,"mode":"corner_pin","coordinates":COORDINATES,"canvas":{"width":WIDTH,"height":HEIGHT},
                "keys":[{"frame":9,"matrix":IDENTITY}],"outside":"transparent","source":{},"invalidated":"Source timing changed"}
        saved=validate_planar_motion(motion,0,3)
        self.assertEqual(saved["keys"][0]["frame"],9)
        self.assertIn("a='0'",','.join(compile_planar_warp(saved,0,WIDTH,HEIGHT)))
        project={"clips":[],"sequences":[{"clips":[{"id":"stored-pin","planar_motion":saved}]}]}
        with self.assertRaisesRegex(ValueError,"stale.*stored-pin"):assert_planar_export_ready(project)
        saved.update(mode="stabilize",outside="identity")
        self.assertEqual(compile_planar_warp(saved,0,WIDTH,HEIGHT),[])
        del saved["invalidated"]
        with self.assertRaisesRegex(ValueError,"outside"):validate_planar_motion(saved,0,3)


@unittest.skipUnless(shutil.which("node"),"Node required for shipped edit-invalidation logic")
class PlanarUIBindingTests(unittest.TestCase):
    def test_dialog_survives_dom_attribute_serialization_and_loads_png_seed(self):
        # DOM getters serialize a bare data attribute as data-name="". Returning
        # invented nodes for missing selectors hid a real WK startup exception.
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
  constructor(){this.children=new Map();this.listeners={};this.value='';this.hidden=false;this.disabled=false;this.open=false;this.textContent='';this.classList={toggle(){}};}
  set innerHTML(value){this.markup=value;this.children=new Map([...value.matchAll(/\b(data-track-[a-z-]+)(?=[\s=>])/g)].map(match=>[match[1],new Element()]));}
  get innerHTML(){return this.markup.replace(/\s(data-track-[a-z-]+)(?=[\s>])/g,' $1=""');}
  querySelector(selector){const match=selector.match(/^\[(data-track-[a-z-]+)\]$/);return match?this.children.get(match[1])||null:null;}
  getContext(){return new Proxy({},{get:()=>()=>{}});}
  addEventListener(name,callback){this.listeners[name]=callback;}
  showModal(){this.open=true;}
  remove(){}
}
const document={body:{append(){}},createElement(){return document.dialog=new Element();}};
class Image {set src(url){this.url=url;Promise.resolve().then(()=>this.onload());}}
const requests=[],context={project:{id:'p',clips:[],assets:[]},clip:{id:'c',start:0,duration:12},asset:{name:'ENGINE_TEST_planar.mkv'},frame:0};
const bridge={capabilities:()=>({planar_tracking:{available:true}}),request:async(path,options)=>{
  requests.push({path,options});return {id:'seed',state:'completed',result:{url:'/analysis/seed.png',width:192,height:144,frame_start:0,frame_count:12}};
}};
const sandbox={window:{},document,Image,setTimeout};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
(async()=>{
  const api=sandbox.window.CinematicumTracking.mount(bridge),dialog=document.dialog;
  assert(dialog.querySelector('[data-track-stale]'),'Stale status must be an actual DOM element');
  api.open(context);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1);assert.equal(requests[0].path,'/api/projects/p/tracking-frame');
  assert(dialog.querySelector('[data-track-status]').textContent.includes('Click a textured feature'));
  const model=dialog.querySelector('[data-track-model]');model.value='projective';model.onchange();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,2);assert.equal(requests[1].options.body.settings.mode,'projective');
  assert(dialog.querySelector('[data-track-status]').textContent.includes('Choose the top-left'));
  assert.equal(dialog.querySelector('[data-track-canvas]').width,192);
  assert.equal(dialog.querySelector('[data-track-stale]').hidden,true);
  api.destroy();
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""
        completed=subprocess.run([shutil.which("node"),"-e",script,str(Path(__file__).parent/"web/tracking-ui.js")],
                                 text=True,capture_output=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def check(self, action):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const sandbox={window:{}};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const reconcile=sandbox.window.CinematicumTracking.reconcilePlanarBindings;
const copy=value=>JSON.parse(JSON.stringify(value));
const source={asset_id:'a',sha256:'a'.repeat(64),width:192,height:144,clip_id:'c',in:0,duration:12,speed:1,reverse:false,animation_offset:0,frame_rate:{numerator:12,denominator:1}};
const matrix=[1,0,0,0,1,0,0,0,1];
const motion={version:1,mode:'stabilize',canvas:{width:192,height:144},keys:[{frame:0,matrix}],source:{source:copy(source),tracked_clip_start:0,track_sha256:'b'.repeat(64)}};
const project={fps:12,assets:[{id:'a',sha256:source.sha256,width:192,height:144,kind:'video'},{id:'image',kind:'image'}],clips:[{id:'c',asset_id:'a',track:0,start:0,in:0,duration:12,planar_motion:copy(motion)},{id:'pin',asset_id:'image',track:1,start:0,in:0,duration:12,x:.1,rotation:12,keyframes:[{frame:2,x:.2}],planar_motion:{...copy(motion),mode:'corner_pin'}}]};
"""+action
        completed=subprocess.run([shutil.which("node"),"-e",script,str(Path(__file__).parent/"web/tracking-ui.js")],
                                 text=True,capture_output=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_timing_edits_preserve_measurements_and_authored_overlay(self):
        self.check(r"""
const before=copy(project),keys=JSON.stringify(project.clips[1].planar_motion.keys),authored=JSON.stringify(project.clips[1].keyframes);
project.clips[0].speed=2;project.clips[0].duration=6;
const report=reconcile(project);assert.equal(report.invalidated,2);assert.equal(project.clips.length,2);
assert.equal(JSON.stringify(project.clips[1].planar_motion.keys),keys);assert.equal(JSON.stringify(project.clips[1].keyframes),authored);
assert.equal(project.clips[1].x,.1);assert.equal(project.clips[1].rotation,12);
const reopened=copy(project);assert.equal(reconcile(reopened).stale.length,2);
assert.equal(reconcile(before).stale.length,0);assert(!before.clips[1].planar_motion.invalidated);
""")

    def test_translation_follows_background_once_but_independent_pin_move_invalidates(self):
        self.check(r"""
project.clips[0].start=7;const report=reconcile(project);assert.equal(report.remapped,1);assert.equal(report.invalidated,0);
assert.equal(project.clips[1].start,7);assert.equal(project.clips[1].planar_motion.source.tracked_clip_start,7);
assert.equal(reconcile(project).remapped,0);project.clips[1].start=8;
assert.equal(reconcile(project).invalidated,1);assert(project.clips[1].planar_motion.invalidated.includes('out of sync'));
""")

    def test_missing_driver_and_source_byte_change_are_not_silent(self):
        self.check(r"""
const altered=copy(project);altered.assets[0].sha256='f'.repeat(64);assert.equal(reconcile(altered).invalidated,2);
project.clips.shift();const result=reconcile(project);assert.equal(result.invalidated,1);assert.equal(project.clips.length,1);assert.equal(project.clips[0].x,.1);
assert(project.clips[0].planar_motion.invalidated.includes('missing'));
""")

    def test_stored_sequences_have_their_own_clip_namespace(self):
        self.check(r"""
const stored=copy(project.clips);project.clips=[];project.sequences=[{id:'stored',clips:stored}];stored[0].start=6;
assert.equal(reconcile(project).remapped,1);assert.equal(stored[1].start,6);
project.frame_rate={numerator:24000,denominator:1001};assert.equal(reconcile(project).invalidated,2);
""")

    def test_restoring_background_timing_restores_pin_regardless_of_clip_order(self):
        self.check(r"""
const background=project.clips[0],pin=project.clips[1];
pin.planar_motion.source.tracked_transform={x:0,y:0,scale:1,rotation:0,keyframes:[],stabilization:{planar_motion:{track_sha256:background.planar_motion.source.track_sha256,invalidated:null}}};
project.clips.reverse();background.speed=2;background.duration=6;
assert.equal(reconcile(project).invalidated,2);
background.speed=1;background.duration=12;const restored=reconcile(project);
assert.equal(restored.restored,2);assert.equal(restored.stale.length,0);
assert(!background.planar_motion.invalidated);assert(!pin.planar_motion.invalidated);
""")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg required for planar render regression")
class PlanarRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-PLANAR-ENGINE-TEST-")
        cls.root=Path(cls.temporary.name);cls.project=build_fixture(cls.root);cls.track=prescribed_track(cls.project)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_measurement_import_rejects_timing_drift_and_false_visibility(self):
        source=self.track["source"]
        validate_planar_track(self.track,source)
        for field,value in (("in",1),("speed",2),("duration",10),("reverse",True),("animation_offset",1)):
            expected=copy.deepcopy(source);expected[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"timing"):validate_planar_track(self.track,expected)
        bad=copy.deepcopy(self.track);bad["samples"][3].update(visible=False,confidence=0)
        with self.assertRaisesRegex(ValueError,"lost plane"):validate_planar_track(bad,source)

    def test_actual_stabilized_pixels_and_corner_pin_share_stabilized_plane(self):
        project=copy.deepcopy(self.project)
        project["clips"][0]["planar_motion"]=planar_motion(project,self.root,"background",self.track)
        pin=planar_motion(project,self.root,"background",self.track,"corner_pin")
        # H^-1 applied to the background also belongs in the pin transform.
        for key in pin["keys"]:
            for actual,expected in zip(key["matrix"],quad_matrix(QUAD)):self.assertAlmostEqual(actual,expected,places=10)
        project["clips"].append(pin_clip(project,pin))
        output=self.root/"ENGINE_TEST_stabilized_pin.mov";render_project(project,self.root,output,"prores")
        raw=ffmpeg(["-i",str(output),"-f","rawvideo","-pix_fmt","rgb24","-threads","1","pipe:1"])
        self.assertEqual(len(raw),WIDTH*HEIGHT*3*FRAMES)
        centers=[]
        for frame in (0,FRAMES-1):
            picture=raw[frame*WIDTH*HEIGHT*3:(frame+1)*WIDTH*HEIGHT*3]
            pixels=[(index//3%WIDTH,index//3//WIDTH) for index in range(0,len(picture),3)
                    if picture[index]>180 and picture[index+1]<65 and picture[index+2]>180]
            self.assertGreater(len(pixels),4000)
            centers.append((sum(x for x,_ in pixels)/len(pixels),sum(y for _,y in pixels)/len(pixels)))
        self.assertAlmostEqual(centers[0][0],centers[1][0],delta=.15)
        self.assertAlmostEqual(centers[0][1],centers[1][1],delta=.15)

    def test_point_stabilization_is_composed_and_background_motion_drift_rejected(self):
        project=copy.deepcopy(self.project)
        project["clips"][0]["tracking"]={"version":1,"mode":"stabilize","keys":[{"frame":0,"x":0,"y":0},{"frame":11,"x":-22/WIDTH,"y":-11/HEIGHT}],"source":{"track_sha256":"a"*64}}
        motion=planar_motion(project,self.root,"background",self.track,"corner_pin")
        for key in motion["keys"]:
            for actual,expected in zip(key["matrix"],quad_matrix(QUAD)):self.assertAlmostEqual(actual,expected,places=10)
        project["clips"].append(pin_clip(project,motion));project=validate_project(project,self.root)
        project["clips"][0].pop("tracking")
        with self.assertRaisesRegex(ValueError,"transform changed"):validate_project(project,self.root)

    def test_stale_motion_saves_reopens_but_movie_export_is_blocked(self):
        project=copy.deepcopy(self.project);motion=planar_motion(project,self.root,"background",self.track)
        motion["invalidated"]="The source range changed. Remeasure it.";project["clips"][0]["planar_motion"]=motion
        project["clips"][0]["duration"]=3;project["clips"][0]["animation_duration"]=3
        saved=validate_project(json.loads(json.dumps(project)),self.root)
        self.assertEqual(len(saved["clips"][0]["planar_motion"]["keys"]),12)
        with self.assertRaisesRegex(ValueError,"stale"):render_project(saved,self.root,self.root/"forbidden.mp4")
        self.assertFalse((self.root/"forbidden.mp4").exists())

    def test_render_rehashes_admitted_original_even_after_measurement_import(self):
        project=copy.deepcopy(self.project);project["clips"][0]["planar_motion"]=planar_motion(project,self.root,"background",self.track)
        self.assertEqual(verify_planar_source_files(project,self.root)["sources_verified"],1)
        bad=copy.deepcopy(project);bad["clips"][0]["planar_motion"]["source"]["source"]["sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"changed on disk"):verify_planar_source_files(bad,self.root)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg required")
class PlanarInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime=planar_capabilities()
        if not cls.runtime.get("available"):raise unittest.SkipTest("Actual OpenCV planar runtime unavailable: "+cls.runtime.get("reason",""))
        cls.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-PLANAR-MEASURE-TEST-")
        cls.root=Path(cls.temporary.name);cls.project=build_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_real_affine_and_projective_measurement_tracks_known_translation(self):
        for model in ("affine","projective"):
            with self.subTest(model=model):
                measured=track_planar(self.project,self.root,"background",{"mode":model,"quad":QUAD,"frame_start":0,"frame_count":FRAMES})
                self.assertEqual(len(measured["samples"]),FRAMES)
                self.assertTrue(all(sample["visible"] for sample in measured["samples"]))
                for sample in measured["samples"]:
                    for actual,corner in zip(sample["corners"],QUAD):
                        self.assertAlmostEqual(actual[0]*WIDTH,corner[0]*WIDTH+2*sample["frame"],delta=.8)
                        self.assertAlmostEqual(actual[1]*HEIGHT,corner[1]*HEIGHT+sample["frame"],delta=.8)

    def test_real_extended_range_and_wider_canvas_measure_known_motion(self):
        # Labelled synthetic ENGINE TEST media. This exercises both former
        # limits in a real decode/worker/import/apply journey, not a film claim.
        width,height,count=768,96,300
        rng=random.Random(8271);texture=rng.randbytes(width*height);raw=bytearray()
        shifts=[]
        for frame in range(count):
            dx=round(4*math.sin(frame/29));dy=round(2*math.sin(frame/37));shifts.append((dx,dy))
            for y in range(height):
                row=texture[((y-dy)%height)*width:((y-dy)%height+1)*width]
                raw.extend(row[-dx:]+row[:-dx] if dx else row)
        video=self.root/"media/ENGINE_TEST_extended_planar.mkv"
        ffmpeg(["-f","rawvideo","-pixel_format","gray","-video_size",f"{width}x{height}",
                "-framerate","30","-i","pipe:0","-c:v","ffv1",str(video)],bytes(raw))
        asset=probe_media(video);asset.update(id="plane",name=video.name,path="media/"+video.name,
                                             sha256=hashlib.sha256(video.read_bytes()).hexdigest())
        project={"version":1,"id":"extended-planar-test","name":"ENGINE TEST extended planar motion",
                 "width":width,"height":height,"fps":30,"assets":[asset],"titles":[],"settings":{},
                 "clips":[{"id":"background","asset_id":"plane","track":0,"start":0,"in":0,"duration":count,"volume":0}]}
        project=validate_project(project,self.root)
        quad=[[.1,.15],[.9,.15],[.9,.85],[.1,.85]]
        measured=track_planar(project,self.root,"background",{"mode":"projective","quad":quad,"frame_count":count})
        self.assertEqual((measured["analysis_width"],measured["analysis_height"]),(width,height))
        self.assertEqual(len(measured["samples"]),count)
        self.assertTrue(all(sample["visible"] for sample in measured["samples"]))
        for sample in measured["samples"][::29]+measured["samples"][-1:]:
            dx,dy=shifts[sample["frame"]]
            for actual,corner in zip(sample["corners"],quad):
                self.assertAlmostEqual(actual[0]*width,corner[0]*width+dx,delta=.8)
                self.assertAlmostEqual(actual[1]*height,corner[1]*height+dy,delta=.8)
        motion=planar_motion(project,self.root,"background",measured)
        self.assertEqual(len(motion["keys"]),count)
        self.assertEqual(motion["keys"][-1]["frame"],count-1)

    def test_real_occlusion_produces_gaps_without_fake_reacquisition(self):
        project=build_fixture(self.root,lost=True)
        measured=track_planar(project,self.root,"background",{"mode":"projective","quad":QUAD,"frame_start":0,"frame_count":FRAMES})
        self.assertTrue(all(sample["visible"] for sample in measured["samples"][:6]))
        self.assertTrue(all(not sample["visible"] and sample["matrix"] is None for sample in measured["samples"][6:]))
        with self.assertRaisesRegex(ValueError,"lost"):planar_motion(project,self.root,"background",measured)


if __name__=="__main__":unittest.main()

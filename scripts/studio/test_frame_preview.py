"""Actual rendered pixels for the authoring viewer; test signals are not films."""
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
import zlib

from engine import RenderCancelled, probe_media, render_project
from frame_preview import preview_identity, render_frame
from color_pipeline import import_cube


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class FramePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-FRAME-TEST-")
        self.root = Path(self.temporary.name)
        (self.root / "media").mkdir()
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        pixels = b"".join(b"\x00" + bytes([60, 100, 160, 255]) * 160 for _ in range(90))
        data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 90, 8, 6, 0, 0, 0))
        data += chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
        source = self.root / "media" / "ENGINE_TEST_frame.png"
        source.write_bytes(data)
        self.project = {"version": 1, "id": "frame_test", "name": "ENGINE TEST ONLY", "fps": 12, "width": 160, "height": 90,
                        "assets": [{"id": "source", "path": "media/ENGINE_TEST_frame.png", **probe_media(source)}],
                        "clips": [{"id": "picture", "asset_id": "source", "track": 0, "start": 0, "in": 0,
                                   "duration": 12, "keyframes": [{"frame": 0, "opacity": .1}, {"frame": 11, "opacity": 1}],
                                   "compositor": {"version": 1, "nodes": [
                                       {"id": "source", "type": "source", "inputs": [], "params": {}},
                                       {"id": "grade", "type": "grade", "inputs": ["source"], "params": {"saturation": 0}}],
                                       "output": "grade"}}], "titles": [], "settings": {}}

    def tearDown(self):
        self.temporary.cleanup()

    def pixel(self, path, frame=0):
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-i", str(path),
                                 "-vf", "select=eq(n\\,%d)" % frame, "-frames:v", "1", "-threads", "1",
                                 "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True, timeout=20)
        return tuple(result.stdout[(45*160+80)*3:(45*160+80)*3+3])

    def test_current_frame_uses_the_actual_export_graph(self):
        first, last = self.root / "first.png", self.root / "last.png"
        render_frame(self.project, self.root, 0, first)
        report = render_frame(self.project, self.root, 11, last)
        self.assertEqual(report["pipeline"], "timeline-export-graph")
        a, b = self.pixel(first), self.pixel(last)
        self.assertLess(max(b) - min(b), 8, "Node saturation must affect authoring preview pixels")
        self.assertGreater(sum(b), sum(a) * 3, "The requested frame must evaluate actual animation")
        movie = self.root / "delivered.mov"
        render_project(self.project, self.root, movie, "prores")
        delivered = self.pixel(movie, 11)
        self.assertLess(max(abs(x-y) for x,y in zip(b, delivered)), 9,
                        "PNG frame and movie delivery must share effect evaluation")

    def test_invalid_and_cancelled_frames_never_replace_existing_output(self):
        output = self.root / "preserved.png"
        output.write_bytes(b"existing saved result")
        for frame in (-1, 12, True, .5):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                render_frame(self.project, self.root, frame, output)
        event = threading.Event(); event.set()
        with self.assertRaises(RenderCancelled):
            render_frame(self.project, self.root, 0, output, cancel_event=event)
        self.assertEqual(output.read_bytes(), b"existing saved result")

    def test_preview_identity_changes_with_unsaved_effects_and_frame(self):
        p = copy.deepcopy(self.project)
        first = preview_identity(p, 0)
        p["clips"][0]["compositor"]["nodes"][1]["params"]["saturation"] = .5
        self.assertNotEqual(first, preview_identity(p, 0))
        self.assertNotEqual(preview_identity(p, 0), preview_identity(p, 1))

    def test_project_lut_changes_decoded_preview_and_movie_through_one_graph(self):
        project = copy.deepcopy(self.project)
        clip = project['clips'][0]
        clip.pop('compositor')
        clip['keyframes'] = []
        clip['duration'] = 2
        descriptor = import_cube('LUT_1D_SIZE 2\n1 1 1\n0 0 0\n', self.root)
        clip['color_pipeline'] = {'version': 1, 'enabled': True,
            'lut': {'sha256': descriptor['sha256'], 'interpolation': 'linear'}}
        picture, movie = self.root / 'lut.png', self.root / 'lut.mov'
        render_frame(project, self.root, 0, picture)
        expected = (195, 155, 95)
        actual = self.pixel(picture)
        self.assertLess(max(abs(a-b) for a,b in zip(actual, expected)), 4)
        render_project(project, self.root, movie, 'prores')
        self.assertLess(max(abs(a-b) for a,b in zip(actual, self.pixel(movie))), 9)
        clip['color_pipeline']['enabled'] = False
        render_frame(project, self.root, 0, picture)
        self.assertLess(max(abs(a-b) for a,b in zip(self.pixel(picture), (60,100,160))), 4)

    def test_input_transform_feeds_compositor_and_never_runs_after_it(self):
        project = copy.deepcopy(self.project)
        clip = project['clips'][0]
        clip['keyframes'] = []
        clip['duration'] = 2
        descriptor = import_cube('LUT_1D_SIZE 2\n0.1 0.6 0.9\n0.1 0.6 0.9\n', self.root)
        clip['color_pipeline'] = {'version': 1, 'enabled': True,
            'lut': {'sha256': descriptor['sha256'], 'interpolation': 'linear'}}
        picture = self.root / 'lut-before-composite.png'
        render_frame(project, self.root, 0, picture)
        gray = self.pixel(picture)
        self.assertLess(max(gray)-min(gray), 8, 'Compositor monochrome must process the LUT output')
        self.assertGreater(min(gray), 70)


@unittest.skipUnless(shutil.which("node"), "Node is required")
class FrameViewerSchedulingTests(unittest.TestCase):
    def test_planar_and_high16_edit_mode_request_processed_frames_with_transport_guards(self):
        script = r'''
        const fs=require('fs'),vm=require('vm'),assert=require('assert');
        const timers=new Map();let nextTimer=0;
        class Image {decode(){return Promise.resolve();}}
        const sandbox={window:{},Image,setTimeout:callback=>{timers.set(++nextTimer,callback);return nextTimer;},clearTimeout:id=>timers.delete(id)};
        vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
        const Viewer=sandbox.window.CinematicumFrameViewer,copy=value=>JSON.parse(JSON.stringify(value));
        (async()=>{
          for(const trigger of ['planar','high16']) {
            const project={id:'p',clips:[{id:'clip'}],titles:[],settings:{}};
            if(trigger==='planar')project.clips[0].planar_motion={mode:'corner_pin'};
            else project.settings.image_precision='high16';
            const state={project,mode:'edit',playing:false,rendered:false,frame:7,revision:3};
            const requests=[],image={hidden:true},status={hidden:true,classList:{remove(){},add(){}}};
            const viewer=new Viewer({getState:()=>state,prepareSnapshot:async()=>copy(project),image,status,
              request:async(path,options)=>{requests.push({path,options});return options?{id:'job'}:{state:'completed',result:{url:'/processed.png'}};}});
            viewer.invalidate();assert.equal(timers.size,1,trigger+' must schedule the exact frame from ordinary edit mode');
            const [id,callback]=timers.entries().next().value;timers.delete(id);await callback();
            assert.equal(requests[0].path,'/api/projects/p/frame-preview');
            assert.equal(requests[0].options.body.frame,7);
            assert.deepEqual(requests[0].options.body.project,project);
            assert.equal(requests[1].path,'/api/jobs/job');
            assert.equal(image.hidden,false);assert.equal(image.src,'/processed.png');
            assert.equal(status.textContent,'Rendered frame 7 · export graph');
            for(const blocked of [{mode:'3d'},{mode:'generate'},{playing:true},{rendered:true}]) {
              Object.assign(state,{mode:'edit',playing:false,rendered:false},blocked);
              const count=requests.length;viewer.invalidate();
              assert.equal(timers.size,0,trigger+' must preserve the mode/transport guard');
              assert.equal(requests.length,count);assert.equal(image.hidden,true);assert.equal(status.hidden,true);
            }
          }
        })().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
        '''
        completed = subprocess.run([shutil.which("node"), "-e", script,
                                    str(Path(__file__).parent / "web" / "viewer-tools.js")],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)


@unittest.skipUnless(shutil.which("node"), "Node is required")
class TimelineEvaluationTests(unittest.TestCase):
    def test_independent_property_keys_and_fractional_source_time(self):
        script = r'''
        const fs=require('fs'),vm=require('vm'),assert=require('assert');
        const c={window:{}};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
        const e=c.window.CinematicumEditing;
        const clip={x:0,opacity:1,in:2.5,start:10,duration:24,speed:.25,keyframes:[{frame:12,x:1},{frame:18,opacity:.2}]};
        assert.equal(e.pose(clip,0).x,0);assert.equal(e.pose(clip,6).x,.5);
        assert.equal(e.pose(clip,15).x,1);assert.equal(e.sourceFrame(clip,15),3.75);
        const project={tracks:[{id:0,solo:true,gain:.5},{id:1},{id:-1}],clips:[]};
        assert.equal(e.active(project,1),false);assert.equal(e.active(project,-1),true);
        const k={...clip,volume:1,track:0,audio:{fade_in:12},keyframes:[]};
        assert.equal(e.audioGain(project,k,6),.25);
        const forward={start:20,in:10,duration:40,speed:.5};
        const reverse={...forward,reverse:true};
        assert.equal(e.trim(forward,'left',30,120).in,15);
        assert.equal(e.trim(reverse,'left',30,120).in,10);
        assert.equal(e.trim(forward,'right',50,120).in,10);
        assert.equal(e.trim(reverse,'right',50,120).in,15);
        assert.equal(e.trim(reverse,'right',100,120).duration,60);
        for(const original of [forward,reverse]) {
          const trimmed=e.trim(original,'left',30,120);
          const changed={...original,...trimmed};
          for(let frame=changed.start;frame<changed.start+changed.duration;frame++)
            assert.equal(e.sourceFrame(original,frame),e.sourceFrame(changed,frame));
        }
        for(const interpolation of Object.keys(e.easings)) {
          const original={x:0,volume:1,duration:24,keyframes:[{frame:0,x:0,interpolation},{frame:23,x:1}]};
          const trimmed={...original,duration:12,animation_start:0,animation_duration:24,animation_offset:5};
          for(let frame=0;frame<12;frame++)assert.equal(e.curve(original,'x',frame+5),e.curve(trimmed,'x',frame));
        }
        // Exercise the shipped slider handler without a browser: authoring X
        // must not insert or reshape an unrelated eased audio-gain curve.
        const project2={fps:24,tracks:[]};
        const selected={asset_id:'fixture',start:0,in:0,track:0,duration:24,x:0,volume:1,audio:{},
          keyframes:[{frame:0,volume:1,interpolation:'ease_in'},{frame:23,volume:.1}]};
        Object.assign(c,{editing:e,state:{frame:10,selected:{type:'clip'},project:project2},
          selectedItem:()=>selected,selectionLocked:()=>false,checkpoint:()=>{},changed:()=>{},
          toast:()=>{},clone:v=>JSON.parse(JSON.stringify(v)),clamp:e.clamp,sourceFor:()=>({kind:'image'})});
        const app=fs.readFileSync(require('path').join(require('path').dirname(process.argv[1]),'app.js'),'utf8');
        for(const [begin,end] of [['function keyPosition(','\nfunction splitSelected('],['function normalizeFades(','\nfunction renderTimeline(']]) {
          vm.runInContext(app.slice(app.indexOf(begin),app.indexOf(end,app.indexOf(begin))),c);
        }
        const before=Array.from({length:24},(_,frame)=>e.curve(selected,'volume',frame));
        vm.runInContext("writeField('x',0.25)",c);
        assert.equal(selected.keyframes.find(k=>k.frame===10).volume,undefined);
        assert.deepEqual(Array.from({length:24},(_,frame)=>e.curve(selected,'volume',frame)),before);
        '''
        subprocess.run([shutil.which("node"), "-e", script, str(Path(__file__).parent / "web" / "editing.js")],
                       capture_output=True, check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()

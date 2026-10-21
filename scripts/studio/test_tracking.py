"""Actual measured motion and rendered stabilization; no AI model is simulated."""
import copy
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

from engine import probe_media, validate_project, render_project
from tracking import track_clip, tracking_frame, stabilization_motion, validate_motion, validate_track_for_clip


@unittest.skipUnless(shutil.which("node"), "Node required for deferred-request UI checks")
class TrackingUIJobTests(unittest.TestCase):
    """Exercise the shipped dialog against deliberately reordered requests."""

    def run_dialog(self, scenario):
        harness = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const payload=JSON.parse(fs.readFileSync(0,'utf8')),requests=[],timers=[];
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
class Element {
  constructor(){this.listeners={};this.children=new Map();this.value=0;this.hidden=false;this.disabled=false;this.open=false;this.classList={toggle(){}};}
  querySelector(selector){if(!this.children.has(selector))this.children.set(selector,new Element());return this.children.get(selector);}
  addEventListener(name,callback){(this.listeners[name]??=[]).push(callback);}
  showModal(){this.open=true;}
  close(){this.open=false;for(const callback of this.listeners.close||[])callback();}
  remove(){}
  getContext(){return new Proxy({}, {get:()=>()=>{}});}
}
const document={body:{append(){}},createElement(){const element=new Element();document.dialog=element;return element;}};
class Image {set src(value){this.url=value;Promise.resolve().then(()=>this.onload());}}
const sandbox={window:{},document,Image,setTimeout:callback=>timers.push(callback)};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(payload.source,'utf8'),sandbox);
const bridge={request(url,options){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});requests.push({url,options,resolve,reject});return promise;}};
const api=sandbox.window.CinematicumTracking.mount(bridge),dialog=document.dialog;
const el=name=>dialog.querySelector(`[data-track-${name}]`);
el('radius').value=12;el('threshold').value=.15;
const context={project:{id:'test-project'},clip:{id:'clip',start:0,duration:24},asset:{name:'ENGINE TEST'},frame:0};
const request=(suffix,method='GET')=>requests.filter(item=>item.url.endsWith(suffix)&&(item.options?.method||'GET')===method).at(-1);
const postSeed=()=>request('/tracking-frame','POST');
const cancel=id=>request(`/api/jobs/${id}/cancel`,'POST');
const tick=async()=>{assert(timers.length,'A job poll should be scheduled');timers.shift()();await flush();};
(async()=>{
"""
        script = harness + scenario + "\n})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});"
        result = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps({
            "source": str(Path(__file__).parent / "web" / "tracking-ui.js")}),
            text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_obsolete_poll_cannot_disown_or_report_progress_for_new_job(self):
        self.run_dialog(r"""
api.open(context);postSeed().resolve({id:'old',state:'running'});await flush();await tick();
const oldPoll=request('/api/jobs/old');assert(oldPoll);
dialog.close();api.open(context);postSeed().resolve({id:'new',state:'running'});await flush();
oldPoll.resolve({id:'old',state:'completed',progress:.91,result:{url:'/obsolete.png'}});await flush();
assert.notStrictEqual(el('progress').value,.91,'An obsolete response must not report progress in a new session');
const pending=el('cancel').onclick();await flush();
assert(cancel('new'),'The new session must retain ownership of its cancellable job');
cancel('new').resolve({state:'cancelled'});await pending;
if(cancel('old'))cancel('old').resolve({state:'cancelled'});await flush();
""")

    def test_late_cancel_completion_cannot_unlock_reopened_dialog(self):
        self.run_dialog(r"""
api.open(context);postSeed().resolve({id:'old',state:'running'});await flush();
const pending=el('cancel').onclick();await flush();assert(cancel('old'));
dialog.close();api.open(context);postSeed().resolve({id:'new',state:'running'});await flush();
const activeStatus=el('status').textContent;
cancel('old').resolve({state:'cancelled'});await pending;await flush();
assert.strictEqual(el('start').disabled,true,'An old cancel continuation must not unlock a running new session');
assert.strictEqual(el('status').textContent,activeStatus,'An old cancel completion must not overwrite the current status');
const finish=el('cancel').onclick();await flush();assert(cancel('new'));
cancel('new').resolve({state:'cancelled'});await finish;
""")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class TrackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-TRACK-TEST-")
        cls.root = Path(cls.temp.name)
        (cls.root / "media").mkdir()
        cls.width, cls.height, cls.frames = 128, 96, 12
        rng = random.Random(1927)
        texture = [rng.choice([30, 225]) for _ in range(24 * 24)]
        for occlude in (False, True):
            raw = bytearray()
            for frame in range(cls.frames):
                image = bytearray([65, 65, 65] * (cls.width * cls.height))
                if not (occlude and frame == 6):
                    for y in range(24):
                        for x in range(24):
                            index = ((26 + frame + y) * cls.width + 24 + 2 * frame + x) * 3
                            image[index:index+3] = bytes([texture[y * 24 + x]] * 3)
                raw.extend(image)
            path = cls.root / "media" / ("lost.mkv" if occlude else "moving.mkv")
            subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
                            "-video_size", "128x96", "-framerate", "12", "-i", "pipe:0", "-c:v", "ffv1", str(path)],
                           input=raw, check=True, timeout=10)
        asset = probe_media(cls.root / "media/moving.mkv")
        asset.update(id="a", name="ENGINE_TEST_measured_motion", path="media/moving.mkv",
                     sha256=hashlib.sha256((cls.root / "media/moving.mkv").read_bytes()).hexdigest())
        cls.project = validate_project({"version": 1, "id": "test-tracking", "name": "ENGINE TEST", "fps": 12, "width": 128, "height": 96, "assets": [asset], "titles": [],
                     "clips": [{"id": "c", "asset_id": "a", "start": 0, "in": 0, "duration": 12, "track": 0}]}, cls.root)
        cls.settings = {"frame_start": 0, "frame_count": 12, "x": 36/128, "y": 38/96, "radius": 8, "threshold": .1}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_measured_track_and_actual_stabilized_picture(self):
        track = track_clip(self.project, self.root, "c", self.settings)
        self.assertTrue(all(p["visible"] for p in track["samples"]))
        for index, p in enumerate(track["samples"]):
            self.assertAlmostEqual(p["x"] * 128, 36 + index * 2, delta=.01)
            self.assertAlmostEqual(p["y"] * 96, 38 + index, delta=.01)
        motion = stabilization_motion(self.project, self.root, "c", track)
        self.assertEqual(len(motion["keys"]), 2)
        updated = copy.deepcopy(self.project)
        updated["clips"][0]["tracking"] = motion
        updated["clips"][0]["keyframes"] = [{"frame": 0, "volume": .3}, {"frame": 11, "volume": .8}]
        output = self.root / "media/ENGINE_TEST_stabilized.mp4"
        render_project(updated, self.root, output)
        asset = probe_media(output)
        asset.update(id="a", path="media/"+output.name, name="ENGINE_TEST_stabilized", sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        review = copy.deepcopy(self.project); review["assets"] = [asset]
        measured = track_clip(review, self.root, "c", self.settings)
        self.assertTrue(all(p["visible"] for p in measured["samples"]))
        for p in measured["samples"]:
            self.assertAlmostEqual(p["x"] * 128, 36, delta=1)
            self.assertAlmostEqual(p["y"] * 96, 38, delta=1)

    def test_missing_visibility_cannot_silently_drive_motion(self):
        project = copy.deepcopy(self.project)
        project["assets"][0]["path"] = "media/lost.mkv"
        project["assets"][0]["sha256"] = hashlib.sha256((self.root / "media/lost.mkv").read_bytes()).hexdigest()
        track = track_clip(project, self.root, "c", self.settings)
        self.assertFalse(track["samples"][6]["visible"])
        with self.assertRaisesRegex(ValueError, "loses"):
            stabilization_motion(project, self.root, "c", track)

    def test_seed_frame_import_identity_and_cancellation(self):
        png = self.root / "seed.png"
        report = tracking_frame(self.project, self.root, "c", self.settings, png)
        self.assertTrue(png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual((report["width"], report["height"]), (128, 96))
        track = track_clip(self.project, self.root, "c", self.settings)
        self.assertEqual(validate_track_for_clip(self.project, self.root, "c", track)["samples"], track["samples"])
        wrong = copy.deepcopy(track); wrong["source"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "different media"):
            stabilization_motion(self.project, self.root, "c", wrong)
        missing = copy.deepcopy(track); del missing["samples"][4]
        with self.assertRaisesRegex(ValueError, "contiguous"):
            stabilization_motion(self.project, self.root, "c", missing)
        event = threading.Event(); event.set()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            track_clip(self.project, self.root, "c", self.settings, cancel_event=event)

    def test_fractional_source_range_matches_exact_full_clip_frames(self):
        """A tracking window must not independently reround source timestamps."""
        from engine import _video_timing
        from timebase import project_rate
        from tracking import _decode_first, _prepare

        def decode(source, chain, count):
            return subprocess.run(["ffmpeg", "-v", "error", "-threads", "1", "-i", str(source),
                                   "-vf", ",".join(chain), "-frames:v", str(count), "-an", "-threads", "1",
                                   "-f", "rawvideo", "-pix_fmt", "yuv420p", "pipe:1"],
                                  check=True, capture_output=True, timeout=10).stdout

        size = self.width * self.height * 3 // 2
        for speed in (.5, 1, 1.5):
            for reverse in (False, True):
                with self.subTest(speed=speed, reverse=reverse):
                    project = copy.deepcopy(self.project)
                    clip = project["clips"][0]
                    clip.update(speed=speed, reverse=reverse, duration=int(11.5 / speed))
                    clip["in"] = .5
                    prepared = _prepare(project, self.root, "c", {"frame_start": 1, "frame_count": 4})
                    source = prepared[3]
                    complete_chain = _video_timing(clip, project_rate(project)) + [
                        "scale=128:96:flags=area", "format=yuv420p"]
                    full = decode(source, complete_chain, clip["duration"])
                    expected = full[size:5 * size]
                    with tempfile.TemporaryDirectory(prefix="cinematicum-WINDOW-TEST-") as temporary:
                        chain, _, raw = _decode_first(prepared, temporary, None, time.monotonic() + 10)
                        self.assertEqual(raw.read_bytes(), expected[:size], "The visible seed must be the exact selected clip frame")
                        self.assertEqual(decode(source, chain, 4), expected, "The measured range must retain the original conform phase")

    def test_motion_validation_and_manual_channels_stay_independent(self):
        track = track_clip(self.project, self.root, "c", self.settings)
        project = copy.deepcopy(self.project)
        project["clips"][0].update(x=.2, rotation=20, scale=.8, keyframes=[{"frame": 9, "y": .3, "interpolation": "ease_in"}])
        original = copy.deepcopy(project["clips"][0])
        motion = stabilization_motion(project, self.root, "c", track)
        self.assertEqual(project["clips"][0], original)
        self.assertAlmostEqual(motion["keys"][-1]["x"], -22/128)
        broken = copy.deepcopy(motion); broken["keys"][0]["x"] = float("nan")
        with self.assertRaises(ValueError):
            validate_motion(broken, 0, 12)
        broken = copy.deepcopy(motion); broken["keys"].reverse()
        with self.assertRaises(ValueError):
            validate_motion(broken, 0, 12)


if __name__ == "__main__":
    unittest.main()

"""Real MP4 regression for generated-take sample timing and edit quantization."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from macos.verify_generated_take import verify_timing


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class GeneratedTakeTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-ENGINE-TEST-timing-")
        cls.directory=Path(cls.temporary.name)
        cls.source=cls.encode("complete",17)
        cls.original=cls.source.read_bytes()
        cls.probe=cls.inspect(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def encode(cls,name,length):
        source=cls.directory/(name+".mp4")
        subprocess.run(["ffmpeg","-v","error","-nostdin","-f","lavfi","-i","testsrc2=size=128x80:rate=16",
                        "-frames:v",str(length),"-an","-c:v","libx264","-threads","1","-bf","2",
                        "-video_track_timescale","16384","-y",str(source)],check=True,capture_output=True,timeout=10)
        return source

    @staticmethod
    def inspect(source):
        return json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_frames","-show_packets",
            "-show_entries","stream=avg_frame_rate,time_base,start_pts,duration,duration_ts,nb_read_frames:frame=media_type,best_effort_timestamp:packet=stream_index,pts,dts,duration",
            "-of","json",str(source)],timeout=10))

    def variant(self,name,atom,offset,value):
        data=bytearray(self.original)
        # The fixture is an actual H.264 encode; only the named MP4 integer is
        # changed. Requiring one occurrence prevents editing compressed media.
        self.assertEqual(data.count(atom),1)
        struct.pack_into(">I",data,data.index(atom)+offset,value)
        path=self.directory/(name+".mp4"); path.write_bytes(data)
        return path,self.inspect(path)

    def test_complete_exact_samples_with_ceil_edit_pass(self):
        before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        timing=verify_timing(self.source,self.probe,17,16)
        self.assertTrue(timing["passed"],timing)
        self.assertEqual((timing["media_timescale"],timing["media_duration"]),(16384,17408))
        self.assertEqual((timing["movie_timescale"],timing["movie_duration"]),(1000,1063))
        self.assertEqual(timing["edit_media_time"],2048)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),before)

    def test_floor_edit_explains_eight_tick_probe_difference_without_losing_samples(self):
        source,probe=self.variant("floor-edit",b"elst",12,1062)
        self.assertEqual(probe["streams"][0]["duration_ts"],17400)
        self.assertEqual(probe["streams"][0]["duration"],"1.062012")
        timing=verify_timing(source,probe,17,16)
        self.assertTrue(timing["passed"],timing)
        self.assertEqual(timing["expected_media_ticks"],"17408")
        self.assertEqual(timing["edit_quantization_seconds"],"-1/2000")
        # Independent decoding proves the header-only variant contains the
        # exact same 17 unique pictures as the real original encoded fixture.
        decoded=[]
        for path in (self.source,source):
            decoded.append(subprocess.check_output(["ffmpeg","-v","error","-nostdin","-threads","1","-i",str(path),
                "-map","0:v:0","-an","-threads","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],timeout=10))
        self.assertEqual(decoded[0],decoded[1])
        stride=128*80*3
        self.assertEqual(len(decoded[1]),17*stride)
        self.assertEqual(len({hashlib.sha256(decoded[1][index*stride:(index+1)*stride]).hexdigest() for index in range(17)}),17)

    def test_edit_duration_beyond_the_measured_clock_quantization_is_rejected(self):
        for duration in (1061,1064):
            with self.subTest(duration=duration):
                source,probe=self.variant("wrong-edit-"+str(duration),b"elst",12,duration)
                timing=verify_timing(source,probe,17,16)
                self.assertFalse(timing["passed"])
                self.assertFalse(timing["checks"]["edit_duration_is_one_tick_quantization"])

    def test_actual_missing_frame_cannot_pass_on_container_duration(self):
        source=self.encode("missing-last-frame",16)
        timing=verify_timing(source,self.inspect(source),17,16)
        self.assertFalse(timing["passed"])
        self.assertFalse(timing["checks"]["complete_packet_presentation_grid"])
        self.assertFalse(timing["checks"]["complete_media_duration"])

    def test_short_packet_durations_are_rejected_even_with_unchanged_media_header(self):
        source,probe=self.variant("short-samples",b"stts",16,1023)
        timing=verify_timing(source,probe,17,16)
        self.assertFalse(timing["passed"])
        self.assertTrue(timing["checks"]["complete_media_duration"])
        self.assertFalse(timing["checks"]["every_stored_sample_has_full_frame_duration"])

    def test_shifted_edit_start_cannot_pass_as_the_requested_frame_grid(self):
        source,probe=self.variant("shifted-edit",b"elst",16,2049)
        timing=verify_timing(source,probe,17,16)
        self.assertFalse(timing["passed"])
        self.assertFalse(timing["checks"]["complete_packet_presentation_grid"])

    def test_short_media_header_cannot_be_explained_as_movie_clock_rounding(self):
        source,probe=self.variant("short-media-duration",b"mdhd",20,17400)
        timing=verify_timing(source,probe,17,16)
        self.assertFalse(timing["passed"])
        self.assertFalse(timing["checks"]["complete_media_duration"])

    @unittest.skipUnless(shutil.which("node"),"Node is required for the shipped editor")
    def test_quantized_take_keeps_last_frame_through_actual_import_and_edit_functions(self):
        from engine import probe_media,validate_project
        source,_=self.variant("editor-floor-edit",b"elst",12,1062)
        directory=self.directory/"editor-project"; (directory/"media").mkdir(parents=True,exist_ok=True)
        media=directory/"media"/"ENGINE_TEST_generated.mp4"; shutil.copyfile(source,media)
        before=hashlib.sha256(media.read_bytes()).hexdigest()
        asset={"id":"source","name":"ENGINE TEST generated","path":"media/ENGINE_TEST_generated.mp4",**probe_media(media)}
        self.assertEqual(asset["duration"],17400/16384)
        project={"version":1,"id":"timing-proof","name":"ENGINE TEST edit timing","width":128,"height":80,"fps":16,
                 "assets":[asset],"clips":[],"titles":[],"tracks":[],"settings":{}}
        program=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8')),source=fs.readFileSync(input.root+'/app.js','utf8');
const clone=value=>JSON.parse(JSON.stringify(value)),noop=()=>{},state={project:input.project,selected:null,frame:0,zoom:16};
let serial=0;
function section(first,next){const start=source.indexOf('function '+first+'('),end=source.indexOf('function '+next+'(');assert(start>=0&&end>start);return source.slice(start,end);}
const sandbox={window:{},state,uid:()=>`clip-${++serial}`,durationFrames:()=>0,clone,
  selectedItem:()=>state.project.clips.find(c=>c.id===state.selected?.id),selectionLocked:()=>false,
  sourceFor:c=>state.project.assets.find(a=>a.id===c.asset_id),checkpoint:noop,changed:noop,
  renderTimeline:noop,drawPreview:noop,toast:message=>{throw Error(message);}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(input.root+'/editing.js','utf8'),sandbox);
const editing=sandbox.window.CinematicumEditing;sandbox.editing=editing;sandbox.clamp=editing.clamp;sandbox.preserveAnimation=editing.preserveAnimation;
vm.runInContext(section('defaultClip','addAsset')+section('writeField','renderTimeline')+
  section('normalizeFades','trackingContext')+section('timelineMove','timelineUp'),sandbox);
const asset=state.project.assets[0],clip=sandbox.defaultClip(asset,0,0),snapshots=[];
state.project.clips=[clip];state.selected={type:'clip',id:clip.id};
function retain(){snapshots.push(clone(state.project));}
assert.strictEqual(clip.duration,17,'Import dropped the final valid picture');retain();
sandbox.writeField('volume',.5);assert.strictEqual(clip.duration,17,'Gain edit shortened the source');retain();
sandbox.writeField('duration',18);assert.strictEqual(clip.duration,17,'Inspector extended beyond the last frame');retain();
sandbox.writeField('duration',16);assert.strictEqual(clip.duration,16);
state.drag={type:'clip',edge:'right',original:clone(clip),startX:0,moved:false};
sandbox.timelineMove({clientX:32,altKey:true});
assert.strictEqual(clip.duration,17,'Right-edge trim cannot expose the final picture');retain();
for(const requested of [0,1,-1]){
 const result=editing.trimEdit(state.project,clip.id,'slip',requested);
 assert(result.delta===0,'A full-length clip has no slip handles');
 assert.strictEqual(result.clips[0].in,0,'Zero-offset slip created a negative source in');
 assert.strictEqual(result.clips[0].duration,17);
}
sandbox.writeField('duration',16);
const slipped=editing.trimEdit(state.project,clip.id,'slip',1);
assert.strictEqual(slipped.delta,1);assert.strictEqual(slipped.clips[0].in,1);
snapshots.push({...clone(state.project),clips:clone(slipped.clips)});
// Retiming retains the same nearest-frame source boundary without adding a
// whole extra source frame, and ordinary edits cannot shorten it afterward.
sandbox.writeField('duration',17);sandbox.writeField('speed',.5);
assert.strictEqual(clip.duration,34);sandbox.writeField('duration',35);
assert.strictEqual(clip.duration,34);sandbox.writeField('volume',.7);
assert.strictEqual(clip.duration,34);retain();
for(const [available,expected] of [[16.49,16],[16.5,17],[16.51,17],[17.49,17]]){
 assert.strictEqual(sandbox.defaultClip({...asset,duration:available/16},0,0).duration,expected,'Use nearest frame, not ceiling or an epsilon');
}
assert.strictEqual(sandbox.defaultClip({...asset,kind:'image'},0,0).duration,80);
process.stdout.write(JSON.stringify(snapshots));
"""
        result=subprocess.run([shutil.which("node"),"-e",program],input=json.dumps({"root":str(Path(__file__).parent/"web"),"project":project}),
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        snapshots=json.loads(result.stdout)
        for snapshot in snapshots:
            accepted=validate_project(snapshot,directory)
            self.assertEqual(accepted["clips"][0]["duration"],snapshot["clips"][0]["duration"])
        self.assertEqual(hashlib.sha256(media.read_bytes()).hexdigest(),before)


if __name__=="__main__":
    unittest.main()

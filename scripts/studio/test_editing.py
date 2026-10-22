"""Shipped editing equations retain authored trajectories across source trims."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node required for the shipped editing evaluator")
class EditingDomainTests(unittest.TestCase):
    def run_script(self, assertions):
        setup = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root=JSON.parse(fs.readFileSync(0,'utf8')).root,sandbox={window:{}};
vm.createContext(sandbox);
for(const name of ['editing.js','compositor-ui.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const editing=sandbox.window.CinematicumEditing,compositor=sandbox.window.CinematicumCompositor;
const clone=value=>JSON.parse(JSON.stringify(value));
const original={id:'clip',start:10,in:6,duration:8,speed:1,reverse:false,track:0,
  x:.1,y:-.1,scale:1,rotation:10,opacity:1,volume:.5,
  animation_start:0,animation_duration:8,animation_offset:0,
  keyframes:[{frame:0,x:.2,volume:.3,interpolation:'ease_out'},{frame:7,x:.8,volume:1.2}],
  tracking:{version:1,mode:'stabilize',keys:[{frame:0,x:0,y:0},{frame:7,x:-.2,y:.1}]},
  compositor:{version:1,nodes:[{id:'source',type:'source',inputs:[],params:{}},
    {id:'mask',type:'mask',inputs:['source'],params:{x:.2},animation:{x:[{frame:0,value:.2,interpolation:'ease_in_out'},{frame:7,value:.8}]}}],output:'mask'},
  audio:{fade_in:2,fade_out:2,fade_duration:8,fade_offset:0}};
const snapshot=JSON.stringify(original),project={width:128,height:96,clips:[original]},asset={width:64,height:64};
const samples=(clip,frame)=>({pose:editing.pose(clip,frame),tracking:editing.trackingOffset(clip,frame,project,asset),
  node:compositor.paramsAt(clip.compositor.nodes[1],frame+(clip.animation_offset??0)),
  gain:editing.audioGain(project,clip,frame)});
function unchangedChannels(clip){for(const key of ['keyframes','compositor','tracking'])assert.strictEqual(JSON.stringify(clip[key]),JSON.stringify(original[key]),key+' changed');}
function sameSamples(next,first,count){for(let i=0;i<count;i++)assert.deepStrictEqual(clone(samples(next,i)),clone(samples(original,first+i)));}
function trim(edge,requested){const next=clone(original),result=editing.trim(next,edge,requested,64);Object.assign(next,{start:result.start,in:result.in,duration:result.duration});return editing.preserveAnimation(next,original,result.offset);}
"""
        result = subprocess.run([shutil.which("node"), "-e", setup + assertions],
                                input=json.dumps({"root": str(Path(__file__).parent / "web")}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extending_head_and_tail_enlarges_only_editable_domain(self):
        self.run_script(r"""
const head=trim('left',8),tail=trim('right',22);
assert.deepStrictEqual([head.animation_start,head.animation_duration,head.animation_offset],[-2,8,-2]);
assert.deepStrictEqual([tail.animation_start,tail.animation_duration,tail.animation_offset],[0,12,0]);
unchangedChannels(head);unchangedChannels(tail);
for(let i=0;i<8;i++)assert.deepStrictEqual(clone(samples(head,i+2)),clone(samples(original,i)));
sameSamples(tail,0,8);
assert.strictEqual(head.audio.fade_duration,8);assert.strictEqual(head.audio.fade_offset,-2);
assert.strictEqual(tail.audio.fade_duration,8);assert.strictEqual(tail.audio.fade_offset,0);
// Both newly visible regions now accept authored node keys without deleting old ones.
head.compositor.nodes[1].animation.x.push({frame:-2,value:.1});
tail.compositor.nodes[1].animation.x.push({frame:11,value:.9});
for(const clip of [head,tail])assert.strictEqual(compositor.validate(clip.compositor,{animationStart:clip.animation_start,animationDuration:clip.animation_duration}),'');
assert.strictEqual(JSON.stringify(original),snapshot,'Original edit was mutated');
""")

    def test_split_and_shorter_trims_retain_all_compositor_and_tracking_samples(self):
        self.run_script(r"""
const left=clone(original),right=clone(original);left.duration=3;right.start+=3;right.in+=3;right.duration-=3;
editing.preserveAnimation(left,original);editing.preserveAnimation(right,original,3);
for(const clip of [left,right]){unchangedChannels(clip);assert.deepStrictEqual([clip.animation_start,clip.animation_duration],[0,8]);}
sameSamples(left,0,3);sameSamples(right,3,5);
const head=trim('left',12),tail=trim('right',14);
unchangedChannels(head);unchangedChannels(tail);sameSamples(head,2,6);sameSamples(tail,0,4);
right.keyframes[0].x=1;assert.strictEqual(original.keyframes[0].x,.2,'Preserved authored keys must be detached');
assert.strictEqual(JSON.stringify(original),snapshot);
""")

    def test_legacy_visible_interval_union_preserves_existing_extended_domain(self):
        self.run_script(r"""
const legacy=clone(original);legacy.animation_offset=-3;legacy.duration=20;
editing.ensureAnimationDomain(legacy);
assert.deepStrictEqual([legacy.animation_start,legacy.animation_duration],[-3,17]);unchangedChannels(legacy);
const retained=clone(original);retained.animation_start=-20;retained.animation_duration=40;retained.animation_offset=3;
editing.ensureAnimationDomain(retained);assert.deepStrictEqual([retained.animation_start,retained.animation_duration],[-20,40]);unchangedChannels(retained);
const reverse=clone(original);reverse.reverse=true;
for(const [edge,requested] of [['left',8],['right',22]]){
  const next=clone(reverse),result=editing.trim(next,edge,requested,64);Object.assign(next,{start:result.start,in:result.in,duration:result.duration});editing.preserveAnimation(next,reverse,result.offset);
  assert(next.animation_start<=next.animation_offset);assert(next.animation_duration>=next.animation_offset+next.duration);unchangedChannels(next);
}
""")


if __name__ == "__main__":
    unittest.main()

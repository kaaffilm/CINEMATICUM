"""Execute shipped cache ownership code with instrumented decoder resources."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node is required")
class MediaLifecycleTests(unittest.TestCase):
    def test_deleted_rebound_inactive_and_active_decoders_have_bounded_ownership(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(JSON.parse(fs.readFileSync(0,'utf8')).path,'utf8');
function section(first,next){return source.slice(source.indexOf('function '+first+'('),source.indexOf('function '+next+'('));}
const nodes=[],state={project:{clips:[],assets:[],titles:[]},media:new Map(),playing:false,rendered:false,frame:0,history:[],future:[]};
class Element{constructor(){this.events=new Map();this.src='';this.paused=true;this.loads=0;nodes.push(this)}addEventListener(k,v){this.events.set(k,v)}removeEventListener(k,v){assert.equal(this.events.get(k),v);this.events.delete(k)}removeAttribute(k){if(k==='src')this.src=''}pause(){this.paused=true}load(){this.loads++}}
const noop=()=>{},widget={classList:{add:noop},textContent:''};let checkpoints=0;
const sandbox={state,document:{createElement:()=>new Element()},Image:Element,mediaUrl:a=>'/owned/'+a.id,
  assetById:id=>state.project.assets.find(a=>a.id===id),drawPreview:noop,toast:noop,
  window:{CinematicumSequencePlayback:{clear:noop}},mediaEditor:null,
  frameViewer:null,recoveryEditor:{schedule:()=>checkpoints++},$:()=>widget,renderTimeline:noop,renderInspector:noop,renderMedia:noop,updateTransport:noop,
  durationFrames:()=>24,clamp:(v,a,b)=>Math.max(a,Math.min(b,v)),switchPreview:noop};
vm.createContext(sandbox);vm.runInContext(section('releaseMedia','adoptProject')+section('mediaFor','ensureAudio')+section('changed','mutate'),sandbox);
const asset={id:'a',kind:'video',path:'media/a.mp4',name:'ENGINE TEST'};state.project.assets=[asset];
let disconnected=0;
for(let i=0;i<40;i++){
 const clip={id:'delete-'+i,asset_id:'a'};state.project.clips.push(clip);const m=sandbox.mediaFor(clip,asset);
 m.source={disconnect:()=>disconnected++};state.project.clips=[];sandbox.changed();
 assert.equal(state.media.size,0);assert.equal(m.el.src,'');assert.equal(m.el.events.size,0);
}
assert.equal(disconnected,40);assert.equal(nodes.reduce((n,e)=>n+e.loads,0),40);assert.equal(checkpoints,40);
// An ordinary cut sequence never retains a decoder for every visited clip.
for(let i=0;i<40;i++)state.project.clips.push({id:'warm-'+i,asset_id:'a'});
for(const c of state.project.clips){sandbox.mediaFor(c,asset);sandbox.pruneMedia(new Set([c.id]));assert(state.media.size<=13)}
assert.equal(state.media.size,13);
// Simultaneous active layers survive cache pruning even when above the warm bound.
sandbox.clearMedia();const active=new Set();for(const c of state.project.clips.slice(0,24)){sandbox.mediaFor(c,asset);active.add(c.id)}
sandbox.pruneMedia(active);assert.equal(state.media.size,24);
// Reusing a clip identity for a different asset must release the old source.
const c=state.project.clips[0],old=state.media.get(c.id),b={...asset,id:'b',path:'media/b.mp4'};
state.project.assets.push(b);c.asset_id='b';const replacement=sandbox.mediaFor(c,b);
assert.notEqual(replacement,old);assert.equal(old.el.src,'');assert.equal(old.el.events.size,0);
assert(replacement.el.src.endsWith('/b'));
// A preview proxy changes decoder ownership without changing the original binding.
sandbox.mediaEditor={playbackUrl:()=>'/owned-proxy/b'};
const proxy=sandbox.mediaFor(c,b);assert.notEqual(proxy,replacement);assert.equal(replacement.el.src,'');assert.equal(proxy.el.src,'/owned-proxy/b');
assert.equal(c.asset_id,'b');assert.equal(b.path,'media/b.mp4');
// Root audio belongs to the same clip, but uses an original-source decoder.
// A live gain edit must not evict it as if it were a nested sequence instance.
c.start=0;c.duration=24;const sound=sandbox.mediaFor({...c,id:c.id+'/sound'},{...b,kind:'audio'});
sound.ownerClipId=c.id;sound.nested=false;state.revision=3;c.volume=.5;sandbox.pruneMedia();
assert.strictEqual(state.media.get(c.id+'/sound'),sound);assert.equal(sound.el.src,'','Sound waits for its verified PCM source');assert.strictEqual(sound.el.loads,0);
sound.url='/api/projects/p/audio-source/verified';sound.el.src=sound.url;
assert.strictEqual(sandbox.mediaFor({...c,id:c.id+'/sound'},{...b,kind:'audio'}),sound,'PCM decoder URL is distinct from its immutable original request URL');
assert.strictEqual(sound.el.src,sound.url);
// Nested instances own separate active resources and are evicted after edits.
state.revision=7;const nested=sandbox.mediaFor({...c,id:'parent/'+c.id},b);nested.nested=true;nested.revision=7;
sandbox.pruneMedia(new Set(['parent/'+c.id]));assert.equal(state.media.get('parent/'+c.id),nested);
state.revision=8;sandbox.pruneMedia(new Set(['parent/'+c.id]));assert.equal(nested.el.src,'');assert(!state.media.has('parent/'+c.id));
sandbox.clearMedia();assert.equal(state.media.size,0);assert(nodes.every(n=>n.src===''&&n.events.size===0&&n.loads===1));
console.log(JSON.stringify({cycles:40,retained_deleted:0,inactive_limit:12,active_layers_preserved:24,all_resources_released:true}));
"""
        result = subprocess.run([shutil.which("node"), "-e", script],
                                input=json.dumps({"path": str(Path(__file__).parent / "web/app.js")}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["all_resources_released"])


if __name__ == "__main__":
    unittest.main()

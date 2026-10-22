"""Independent sample-oracle acceptance for bounded live reverse source audio."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


class PCMReverseTests(unittest.TestCase):
    def test_reverse_chunks_seek_pause_and_forward_voice_keep_exact_stereo_samples(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Actual shipped PCM scheduling requires Node")
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const scheduled=[],requests=[],timers=new Map();let serial=0;
const frames=216013,rate=48000,value=(frame,ch)=>Math.fround(((frame*(ch?7:3))%7999)/7999-.5);
const manifest={url:'/api/projects/p/audio-source/key',sha256:'a'.repeat(64),data_offset:58,byte_size:58+frames*8,frames,duration:frames/rate,source_time_scale:1};
const context={currentTime:0,sampleRate:44100,createBuffer(ch,count,rate){return {count,rate,data:Array.from({length:ch},()=>new Float32Array(count)),getChannelData(i){return this.data[i];}};},createBufferSource(){return {connect(out){this.out=out;},disconnect(){},stop(){this.stopped=true;},start(when,offset,duration){scheduled.push({node:this,when,offset,duration});}};}};
const sandbox={window:{},setTimeout(fn){timers.set(++serial,fn);return serial;},clearTimeout(id){timers.delete(id);},fetch:async(url,options)=>{
 assert.equal(url,manifest.url);assert.equal(options.headers['If-Match'],'"'+manifest.sha256+'"');
 const [first,last]=options.headers.Range.match(/\d+/g).map(Number);requests.push([first,last]);
 assert.equal((first-58)%8,0);assert(last<manifest.byte_size);assert(last-first+1<=48000*8);
 const raw=new ArrayBuffer(last-first+1),view=new DataView(raw),start=(first-58)/8;
 for(let i=0;i<raw.byteLength/8;i++)for(let ch=0;ch<2;ch++)view.setFloat32(i*8+ch*4,value(start+i,ch),true);
 return {status:206,headers:{get(name){return name==='Content-Range'?`bytes ${first}-${last}/${manifest.byte_size}`:'"'+manifest.sha256+'"';}},arrayBuffer:async()=>raw};
}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const api=sandbox.window.CinematicumPCMPlayback,reverse=api.createDecoder(),forward=api.createDecoder();
const flush=async()=>{for(let i=0;i<24;i++)await Promise.resolve();};
const tick=async(time)=>{context.currentTime=time;const pending=[...timers.values()];timers.clear();for(const fn of pending)fn();await flush();};
(async()=>{
 reverse.loadSource(context,{id:'reverse'},manifest,manifest.duration,{reverse:true});await flush();
 assert.equal(reverse.readyState,4);assert.equal(requests.length,3,'Only three source seconds are prefetched');
 assert.equal(reverse.currentTime,manifest.duration);
 await reverse.play();
 const anchor=scheduled[0].when;
 for(let i=1;i<=92;i++)await tick(i*.05);
 assert(reverse.ended);assert(reverse.paused);assert(Math.abs(reverse.currentTime)<1e-10);assert.equal(reverse.pcmState.underruns,0);
 let cursor=0;
 for(const event of scheduled){
  assert(Math.abs(event.when-(anchor+cursor/rate))<1e-10);
  const first=Math.round(event.offset*rate),count=Math.round(event.duration*rate);
  for(let i=0;i<count;i++)for(let ch=0;ch<2;ch++)assert.equal(event.node.buffer.data[ch][first+i],value(frames-1-cursor-i,ch),'Reverse preserves frame order and channel pairing');
  cursor+=count;
 }
 assert.equal(cursor,frames,'A partial final chunk must neither drop nor duplicate samples');
 assert.equal(reverse.played.length,1);assert(Math.abs(reverse.played.start(0))<1e-10);assert(Math.abs(reverse.played.end(0)-manifest.duration)<1e-10);
 reverse.currentTime=2.2;await flush();const before=scheduled.length;await reverse.play();
 const seek=scheduled[before],virtual=frames-Math.round(2.2*rate),offset=Math.round(seek.offset*rate);
 assert.equal(seek.node.buffer.data[0][offset],value(Math.round(2.2*rate)-1,0));
 await tick(context.currentTime+.125);reverse.pause();const paused=reverse.currentTime;
 assert(paused<2.2);assert(scheduled.slice(before).every(e=>e.node.stopped));
 await tick(context.currentTime+.5);assert.equal(reverse.currentTime,paused);
 forward.loadSource(context,{id:'forward'},manifest,0);await flush();await forward.play();
 const f=scheduled.find(e=>e.node.out?.id==='forward');assert.equal(f.node.buffer.data[0][0],value(0,0));
 assert.notEqual(f.node.buffer,scheduled[0].node.buffer,'Forward and reverse voices never alias opposite sample order');
 reverse.clear();forward.clear();assert.equal(timers.size,0);assert.equal(reverse.currentTime,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result = subprocess.run([node, "-e", script, str(Path(__file__).parent / "web/pcm-playback.js")],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

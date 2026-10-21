"""Execute the shipped bounded PCM scheduler against independent sample oracles."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node required')
class PCMPlaybackTests(unittest.TestCase):
    def run_js(self, code):
        result = subprocess.run([shutil.which('node'), '-e', code],
                                input=json.dumps({'path': str(Path(__file__).parent/'web/pcm-playback.js')}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_contiguous_sample_scheduling_seek_pause_and_tempo_source_clock(self):
        self.run_js(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=JSON.parse(fs.readFileSync(0,'utf8')).path;
let timerId=0;const timers=new Map(),requests=[],scheduled=[];
const value=(frame,ch)=>Math.fround(((frame*(ch?7:3))%7999)/7999-.5),frames=216000;
const manifest={url:'/api/projects/p/audio-source/key',sha256:'a'.repeat(64),data_offset:58,byte_size:58+frames*8,frames,duration:frames/48000,source_time_scale:1};
const context={currentTime:0,sampleRate:48000,createBuffer(channels,count,rate){return {count,rate,data:Array.from({length:channels},()=>new Float32Array(count)),getChannelData(index){return this.data[index];}};},createBufferSource(){return {buffer:null,connect(){},disconnect(){},stop(){this.stopAt=context.currentTime;},start(when,offset,duration){scheduled.push({node:this,when,offset,duration});}};}};
const sandbox={window:{},setTimeout(fn){const id=++timerId;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);},fetch:async(url,options)=>{
 assert.strictEqual(url,manifest.url);assert.strictEqual(options.headers['If-Match'],'"'+manifest.sha256+'"');
 const [first,last]=options.headers.Range.match(/\d+/g).map(Number);requests.push([first,last]);assert.strictEqual((first-58)%8,0);assert(last<manifest.byte_size);
 const buffer=new ArrayBuffer(last-first+1),view=new DataView(buffer),start=(first-58)/8;
 for(let i=0;i<buffer.byteLength/8;i++){view.setFloat32(i*8,value(start+i,0),true);view.setFloat32(i*8+4,value(start+i,1),true);}
 return {status:206,headers:{get(name){return name==='Content-Range'?`bytes ${first}-${last}/${manifest.byte_size}`:name==='ETag'?'"'+manifest.sha256+'"':null;}},arrayBuffer:async()=>buffer};
}};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path,'utf8'),sandbox);
const api=sandbox.window.CinematicumPCMPlayback,decoder=api.createDecoder(),flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const tick=async(time)=>{context.currentTime=time;const current=[...timers];timers.clear();for(const [,fn]of current)fn();await flush();};
(async()=>{
 decoder.loadSource(context,{},manifest,0);await flush();assert.strictEqual(decoder.readyState,4);assert.strictEqual(requests.length,3,'Only three seconds are fetched before playback');
 await decoder.play();assert.strictEqual(scheduled.length,3);
 for(let step=1;step<=88;step++)await tick(step*.05);
 assert.strictEqual(requests.length,5);assert.strictEqual(scheduled.length,5);assert.strictEqual(decoder.pcmState.underruns,0);
 let cursor=0;
 for(const event of scheduled){
  assert(Math.abs(event.when-(.02+cursor/48000))<1e-10);assert.strictEqual(event.offset,0);
  const count=Math.round(event.duration*48000);assert.strictEqual(count,event.node.buffer.count);
  for(let i=0;i<count;i++)for(let channel=0;channel<2;channel++)assert.strictEqual(event.node.buffer.data[channel][i],value(cursor+i,channel));
  cursor+=count;
 }
 assert.strictEqual(cursor,frames);await tick(4.6);assert(decoder.ended);assert.strictEqual(decoder.currentTime,4.5);assert(decoder.paused);
 decoder.currentTime=2.2;await flush();const before=scheduled.length;await decoder.play();
 const seekNode=scheduled[before];assert(Math.abs(seekNode.offset-.2)<1e-10);assert(Math.abs(decoder.currentTime-2.2)<1e-10);
 await tick(4.77);decoder.pause();const paused=decoder.currentTime;await tick(5);assert.strictEqual(decoder.currentTime,paused);assert(scheduled.slice(before).every(item=>item.node.stopAt!==undefined));
 decoder.clear();assert.strictEqual(timers.size,0);
 const fast={...manifest,source_time_scale:1.5};decoder.loadSource(context,{},fast,3);await flush();assert.strictEqual(decoder.currentTime,3);assert.strictEqual(decoder.duration,6.75);
 await decoder.play();await tick(5.52);assert(Math.abs(decoder.currentTime-3.75)<1e-9);decoder.clear();
})().catch(error=>{console.error(error);process.exitCode=1;});
""")

    def test_range_identity_failure_is_explicit_and_long_sources_stay_bounded(self):
        self.run_js(r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=JSON.parse(fs.readFileSync(0,'utf8')).path;
let requests=0,wrong=true;const timers=new Map();let next=0;
const context={currentTime:0,sampleRate:48000,createBuffer(channels,count){return {getChannelData:()=>new Float32Array(count)};},createBufferSource(){throw Error('Unverified source bytes must not be scheduled.');}};
const frames=48000*3600,manifest={url:'/api/projects/p/audio-source/key',sha256:'a'.repeat(64),data_offset:58,byte_size:58+frames*8,frames,duration:3600,source_time_scale:1};
const sandbox={window:{},setTimeout(fn){timers.set(++next,fn);return next;},clearTimeout(id){timers.delete(id);},fetch:async(url,options)=>{
 requests++;const [first,last]=options.headers.Range.match(/\d+/g).map(Number);assert(last-first+1<=48000*8);
 return {status:206,body:{cancel:async()=>{}},headers:{get(name){return name==='Content-Range'?`bytes ${first}-${last}/${manifest.byte_size}`:'"'+(wrong?'b':'a').repeat(64)+'"';}},arrayBuffer:async()=>new ArrayBuffer(last-first+1)};
}};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path,'utf8'),sandbox);const api=sandbox.window.CinematicumPCMPlayback,decoder=api.createDecoder();
const flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
(async()=>{
 decoder.loadSource(context,{},manifest,1800);await flush();assert(decoder.error?.message.includes('verified sample byte range'));assert(decoder.paused);assert.strictEqual(decoder.readyState,0);assert.strictEqual(requests,3);
 decoder.clear();wrong=false;decoder.loadSource(context,{},manifest,1800);await flush();assert.strictEqual(decoder.error,null);assert.strictEqual(decoder.readyState,4);assert.strictEqual(decoder.currentTime,1800);assert.strictEqual(requests,6,'A failed range can be retried; a one-hour source is never downloaded whole');
 decoder.clear();assert.strictEqual(timers.size,0);
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


if __name__ == '__main__':
    unittest.main()

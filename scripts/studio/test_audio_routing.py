"""Live audio identity, graph rewiring, and explicit unsupported-state checks."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from engine import probe_media


@unittest.skipUnless(shutil.which('node'), 'Node required')
class AudioRoutingTests(unittest.TestCase):
    def test_nested_audio_clock_converts_combined_rates_and_retains_reverse_preview_mute(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),root=JSON.parse(fs.readFileSync(0,'utf8')).root;
const context=()=>({setTransform(){},clearRect(){},save(){},restore(){},translate(){},rotate(){},drawImage(){}});
const sandbox={window:{},document:{createElement(){return {width:0,height:0,getContext:context};}}};vm.createContext(sandbox);for(const name of ['editing.js','sequence-playback.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const api=sandbox.window.CinematicumSequencePlayback,media={kind:'audio',el:{duration:10,currentTime:0,volume:1,readyState:4,paused:true,playbackRate:1,preservesPitch:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;}}};for(const key of ['gain','left','right'])media[key]={gain:{value:1}};
const childClip={id:'sound',asset_id:'a',start:0,in:4,duration:40,speed:2,track:-1,volume:1};
const parent={id:'nest',sequence_id:'child',start:10,in:2,duration:20,speed:1.5,track:0,volume:1};
const project={width:96,height:64,fps:24,sequence_id:'main',assets:[{id:'a',kind:'audio',has_audio:true,audio_channels:2}],clips:[parent],titles:[],tracks:[],sequences:[{id:'child',clips:[childClip],titles:[],tracks:[]}]};
const args={project,frame:14,audioFrame:14.25,transportEpoch:0,context:context(),width:96,height:64,mediaFor:()=>media,playing:true,activeIds:new Set(),revision:0,ensureAudio:()=>({ready:true})};
api.draw(args);assert(Math.abs(media.el.currentTime-20.75/24)<1e-12);assert.strictEqual(media.el.playbackRate,3);assert(Math.abs(api.clock().frame-14.25)<1e-12);
media.el.currentTime+=1/24;assert(Math.abs(api.clock().frame-(14.25+1/3))<1e-12);
parent.reverse=true;childClip.reverse=true;args.transportEpoch++;api.draw(args);assert(Math.abs(media.el.currentTime-32.75/24)<1e-12);assert.strictEqual(media.gain.gain.value,0,'Reversed ancestors retain the disclosed live-preview mute');assert(Math.abs(api.clock().frame-14.25)<1e-12);
childClip.reverse=false;args.transportEpoch++;api.draw(args);assert.strictEqual(media.gain.gain.value,0);assert.strictEqual(api.clock(),null,'A net reverse clip remains silent in live preview');
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'root':str(Path(__file__).parent/'web')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_shipped_transport_uses_audio_clock_gaps_and_cancels_pending_preparation(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=JSON.parse(fs.readFileSync(0,'utf8')).path;
const source=fs.readFileSync(path,'utf8');let now=0,callback=null,clock={waiting:true,frame:0},resumeResolve;
const widget={textContent:'',label:'',setAttribute(key,value){this.label=value;}},state={project:{id:'project',fps:24,settings:{},clips:[],tracks:[],sequences:[]},frame:0,rendered:false,playing:false,media:new Map()};
const context={state:'running',resume:()=>Promise.resolve()};
const sandbox={state,$:()=>widget,audioContext:context,playbackAudioFrame:0,playbackEpoch:0,playbackRequest:0,playbackPreparing:false,playbackAudioUnavailable:false,
 playbackFrame:0,playbackOrigin:0,animation:null,frameViewer:{hide(){},invalidate(){}},performance:{now:()=>now},durationFrames:()=>96,
 drawPreview(){},updateTransport(){},toast(){},setTimeout,requestAnimationFrame(fn){callback=fn;return 1;},cancelAnimationFrame(){callback=null;},
 window:{CinematicumSequencePlayback:{ready:()=>true,clock:()=>clock}}};
vm.createContext(sandbox);vm.runInContext(source.slice(source.indexOf('function hasSpeedRamps('),source.indexOf('function updatePreviewNote()')),sandbox);vm.runInContext(source.slice(source.indexOf('function stop()'),source.indexOf('function switchPreview(')),sandbox);
(async()=>{
 await sandbox.play();assert(state.playing);assert.strictEqual(widget.label,'Pause timeline');
 now=200;callback(now);assert.strictEqual(state.frame,0,'Startup must wait on source clock');
 clock={waiting:false,frame:5.75};now=300;callback(now);assert.strictEqual(state.frame,5);assert.strictEqual(sandbox.playbackAudioFrame,5.75);
 clock=null;now=350;callback(now);assert(Math.abs(sandbox.playbackAudioFrame-6.95)<1e-10,'Silent gap must continue from the prior audio position');
 clock={waiting:false,frame:3};now=400;callback(now);assert(Math.abs(sandbox.playbackAudioFrame-6.95)<1e-10,'A new delayed master cannot rewind transport');
 clock={waiting:false,frame:96};now=450;callback(now);assert(!state.playing);assert.strictEqual(state.frame,95);
 context.resume=()=>new Promise(resolve=>{resumeResolve=resolve;});const pending=sandbox.play();assert(sandbox.playbackPreparing);
 sandbox.stop();resumeResolve();await pending;assert(!state.playing);assert(!sandbox.playbackPreparing);assert.strictEqual(widget.label,'Play timeline');
 context.resume=()=>Promise.reject(Error('Unavailable'));clock=null;await sandbox.play();assert(state.playing);assert(sandbox.playbackAudioUnavailable,'Audio failure must leave picture transport usable and explicitly silent');sandbox.stop();
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'path':str(Path(__file__).parent/'web/app.js')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_audio_clock_survives_startup_lag_without_seeking_and_handles_transport_changes(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),root=JSON.parse(fs.readFileSync(0,'utf8')).root;
const sandbox={window:{}};vm.createContext(sandbox);for(const name of ['editing.js','sequence-playback.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const api=sandbox.window.CinematicumSequencePlayback,created=new Map();let routeReady=true;
const project={width:96,height:64,fps:24,clips:[{id:'a',asset_id:'sound',start:0,in:0,duration:48,track:-1,volume:1,audio:{fade_in:24}},{id:'b',asset_id:'sound',start:72,in:24,duration:48,track:-1,volume:1}],assets:[{id:'sound',kind:'audio',has_audio:true,audio_channels:2}],tracks:[],titles:[]};
const mediaFor=clip=>{if(created.has(clip.id))return created.get(clip.id);let currentTime=0;const seeks=[];const media={kind:'audio',seeks,el:{duration:10,readyState:4,volume:1,paused:true,ended:false,seeking:false,playbackRate:1,preservesPitch:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;},get currentTime(){return currentTime;},set currentTime(value){seeks.push(value);currentTime=value;}},advance(value){currentTime=value;}};for(const key of ['gain','left','right'])media[key]={gain:{value:1}};created.set(clip.id,media);return media;};
const args={project,frame:0,audioFrame:0,transportEpoch:1,context:{},width:96,height:64,mediaFor,playing:false,activeIds:new Set(),revision:0,ensureAudio:()=>({ready:routeReady,state:routeReady?'ready':'pending'})};
api.draw(args);assert(api.ready());args.playing=true;api.draw(args);const a=created.get('a');assert.strictEqual(a.gain.gain.value,0);assert.strictEqual(api.clock().frame,0,'A zero-gain fade-in must use its source clock immediately');
// A source taking 200ms to produce audio must hold its own clock, not be
// repeatedly sought toward the faster animation-frame clock.
for(let i=0;i<12;i++){args.frame=Math.floor(i*.5);args.audioFrame=i*.5;api.draw(args);assert.strictEqual(api.clock().frame,0);}
assert.strictEqual(a.seeks.length,0);a.advance(.5);assert(Math.abs(api.clock().frame-12)<1e-10);
// The transport then renders a continuous audio time alongside integer frames.
args.audioFrame=12.25;args.frame=12;a.advance(12.25/24);api.draw(args);assert.strictEqual(a.seeks.length,0);assert(Math.abs(api.clock().frame-12.25)<1e-10);
// Explicit user seek gets one source seek and a fresh clock anchor.
args.transportEpoch++;args.audioFrame=30;args.frame=30;api.draw(args);assert.deepStrictEqual(a.seeks,[1.25]);assert.strictEqual(api.clock().frame,30);
// A genuine source-speed edit likewise realigns once; steady redraws do not.
project.clips[0].speed=1.5;api.draw(args);assert.strictEqual(a.seeks.length,2);assert.strictEqual(a.el.playbackRate,1.5);
for(let i=0;i<8;i++)api.draw(args);assert.strictEqual(a.seeks.length,2);
// Silent gaps have no media master, so the transport can use its wall clock.
args.frame=60;args.audioFrame=60;api.draw(args);assert.strictEqual(api.clock(),null);
args.frame=72;args.audioFrame=72;routeReady=false;api.draw(args);assert(api.clock().waiting);assert(!api.ready());
routeReady=true;api.draw(args);const b=created.get('b');assert.strictEqual(b.el.currentTime,1);assert.strictEqual(api.clock().frame,72);
b.advance(2.999999999);b.el.ended=true;b.el.paused=true;assert.strictEqual(api.clock().frame,120,'An ended decoder must release transport into the next cut/gap');
project.tracks=[{id:-1,mute:true}];api.draw(args);assert.strictEqual(api.clock(),null);
api.clear();assert.strictEqual(api.clock(),null);assert(api.ready());
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'root':str(Path(__file__).parent/'web')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_live_draw_does_not_reconfigure_native_decoder_when_audio_values_are_unchanged(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),root=JSON.parse(fs.readFileSync(0,'utf8')).root;
const sandbox={window:{}};vm.createContext(sandbox);for(const name of ['editing.js','sequence-playback.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const values={playbackRate:.5,preservesPitch:false,muted:true,volume:0},writes={playbackRate:0,preservesPitch:0,muted:0,volume:0};
const element={duration:10,currentTime:.25,readyState:4,paused:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;}};
for(const key of Object.keys(values))Object.defineProperty(element,key,{get(){return values[key];},set(value){writes[key]++;values[key]=value;}});
const media={kind:'audio',el:element};for(const key of ['gain','left','right'])media[key]={gain:{value:1}};
const project={width:96,height:64,fps:24,clips:[{id:'a',asset_id:'sound',start:0,duration:24,track:-1,volume:.7}],assets:[{id:'sound',kind:'audio',has_audio:true,audio_channels:2}],tracks:[],titles:[]};
const args={project,frame:6,context:{},width:96,height:64,mediaFor:()=>media,playing:true,activeIds:new Set(),revision:0,ensureAudio:()=>({ready:true})};
for(let i=0;i<60;i++)sandbox.window.CinematicumSequencePlayback.draw(args);
assert.deepStrictEqual(writes,{playbackRate:1,preservesPitch:1,muted:1,volume:1},'Steady playback must not repeatedly call AVFoundation media setters');
assert.strictEqual(media.gain.gain.value,.7);assert.strictEqual(element.paused,false);
project.clips[0].speed=1.5;sandbox.window.CinematicumSequencePlayback.draw(args);assert.strictEqual(writes.playbackRate,2);assert.strictEqual(element.playbackRate,1.5);
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'root':str(Path(__file__).parent/'web')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_native_worklet_observer_captures_contiguous_frames_including_startup_zeros(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),module=JSON.parse(fs.readFileSync(0,'utf8')).module;
let Processor,result;class AudioWorkletProcessor{constructor(){this.port={postMessage:value=>{result=value;}};}}
const sandbox={AudioWorkletProcessor,currentFrame:256,sampleRate:48000,registerProcessor(name,value){Processor=value;}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(module,'utf8'),sandbox);const processor=new Processor();
processor.port.onmessage({data:{action:'capture',start_frame:150}});
for(let block=0;block<70&&!result;block++){
 sandbox.currentFrame=256+block*128;
 const inputs=Array.from({length:3},(_,input)=>Array.from({length:2},(_,channel)=>Float32Array.from({length:128},(_,i)=>block<4?0:(sandbox.currentFrame+i+input*10000+channel*1000)/100000)));
 processor.process(inputs,[[new Float32Array(128),new Float32Array(128)]]);
}
assert(result);assert.strictEqual(result.start_frame,256);assert.strictEqual(result.requested_start_frame,150);assert.strictEqual(result.end_frame,8448);
for(let input=0;input<3;input++)for(let channel=0;channel<2;channel++){
 const values=result.samples[input][channel];assert.strictEqual(values.length,8192);
 for(let i=0;i<512;i++)assert.strictEqual(values[i],0,'Startup silence must remain in the observation');
 for(let i=512;i<8192;i++)assert.strictEqual(values[i],Math.fround((256+i+input*10000+channel*1000)/100000),'No skipped or duplicated render quanta');
}
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'module':str(Path(__file__).parent/'macos/AudioProbeWorklet.js')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_pending_audio_recovers_to_graph_gain_without_staying_element_muted(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),root=JSON.parse(fs.readFileSync(0,'utf8')).root;
const sandbox={window:{}};vm.createContext(sandbox);for(const name of ['editing.js','sequence-playback.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const media={kind:'audio',el:{duration:10,currentTime:0,volume:1,readyState:4,paused:true,play(){return Promise.resolve();},pause(){}}};
const project={width:96,height:64,fps:24,clips:[{id:'a',asset_id:'sound',start:0,duration:24,track:-1,volume:.7}],assets:[{id:'sound',kind:'audio',has_audio:true,audio_channels:2}],tracks:[],titles:[]};
const args={project,frame:0,context:{},width:96,height:64,mediaFor:()=>media,playing:false,activeIds:new Set(),revision:0,ensureAudio:()=>({ready:false,state:'pending'})};
sandbox.window.CinematicumSequencePlayback.draw(args);assert.strictEqual(media.el.muted,true);assert.strictEqual(media.el.volume,0);
args.ensureAudio=()=>{for(const key of ['gain','left','right'])media[key]={gain:{value:1}};return {ready:true,state:'ready'};};
sandbox.window.CinematicumSequencePlayback.draw(args);assert.strictEqual(media.el.muted,false);assert.strictEqual(media.el.volume,1);assert.strictEqual(media.gain.gain.value,.7);
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'root':str(Path(__file__).parent/'web')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_owned_source_manifest_routing_shared_jobs_and_selection_races(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=JSON.parse(fs.readFileSync(0,'utf8')).module;
let sources=0;const timers=new Map();let timerId=0;
class Element{
 constructor(){this.listeners=new Map();this.readyState=0;this.muted=false;this.volume=1;this.paused=true;this._src='';this.loads=[];}
 addEventListener(name,fn){if(!this.listeners.has(name))this.listeners.set(name,new Set());this.listeners.get(name).add(fn);}
 removeEventListener(name,fn){this.listeners.get(name)?.delete(fn);}
 emit(name){for(const fn of this.listeners.get(name)||[])fn();}
 set src(value){this._src=value;this.readyState=0;this.error=null;this.loads.push(value);}
 get src(){return this._src;}
 get audioTracks(){throw Error('Native track selection must never be accessed.');}
 loadSource(context,output,manifest,sourceTime){this.src=manifest.url;this.context=context;this.output=output;this.sourceTime=sourceTime;this.emit('loadedmetadata');}
 clear(){this.pause();this._src='';this.readyState=0;}
 pause(){this.paused=true;}load(){}ready(){this.readyState=4;this.emit('loadeddata');}
}
const node=kind=>({kind,gain:{value:1},connections:[],connect(...args){this.connections.push(args);},disconnect(){this.connections=[];}});
const context={destination:node('destination'),createMediaElementSource(){throw Error('Owned PCM must not create a native media-element source.');},createGain(){sources++;return node('gain');},createChannelSplitter(count){return {...node('split'),count};},createChannelMerger(count){return {...node('merge'),count};}};
const sandbox={window:{},setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);}};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path,'utf8'),sandbox);
const api=sandbox.window.CinematicumAudioRouting,media=()=>({kind:'audio',el:new Element()}),asset={id:'asset',sha256:'a'.repeat(64),duration:2,has_audio:true,audio_stream_index:1,audio_channels:2,audio_streams:[{index:1,channels:2},{index:2,channels:6}]};
let project={id:'project'},posts=[],gets=[],requests=[],polls=0;
const manifest=(body,changes={})=>{const key=String(body.channels?.[0]??0).repeat(64);return {state:'ready',version:2,playback_rate:body.playback_rate,source_time_scale:body.playback_rate,data_offset:58,frame_bytes:8,asset_id:body.asset_id,source_sha256:asset.sha256,stream_index:body.stream_index,channels:body.channels,cache_key:key,sha256:'b'.repeat(64),url:'/api/projects/project/audio-source/'+key,codec:'pcm_f32le',rate:48000,output_channels:2,frames:96000,source_frames:72000,padded_frames:24000,duration:2,byte_size:768058,...changes};};
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const advance=async()=>{for(const [id,timer]of [...timers])if(timer.delay===150){timers.delete(id);timer.fn();}await flush();};
api.configure({getProject:()=>project,request:async(path,options)=>{
 if(options?.method==='POST'){posts.push(options.body);return await new Promise(resolve=>requests.push({resolve,body:options.body}));}
 gets.push(path);polls++;return polls===1?{id:'job',state:'running'}:{id:'job',state:'completed',result:manifest(posts[0])};
}});
const a=media(),b=media(),warnings=[],clip={audio:{stream_index:2,channels:[5,2]}};
const ensure=(m,c=clip,options)=>api.ensure(m,context,c,asset,message=>warnings.push(message),options);
(async()=>{
 assert.strictEqual(ensure(a).state,'pending');assert.strictEqual(ensure(b).state,'pending');assert.strictEqual(posts.length,1,'One asset selection has one shared preparation job');
 assert.strictEqual(a.el.src,'');assert.strictEqual(a.el.muted,true);assert.strictEqual(sources,0);
 requests.shift().resolve({job:{id:'job',state:'queued'}});await flush();assert.strictEqual(gets.length,0);
 await advance();assert.strictEqual(gets.length,1);assert.strictEqual(a.el.src,'');await advance();
 assert.strictEqual(a.el.src,manifest(posts[0]).url);assert.strictEqual(b.el.src,a.el.src);assert.strictEqual(sources,10);assert.strictEqual(a.audioGate.gain.value,0);assert.strictEqual(a.el.muted,false);
 a.el.ready();b.el.ready();let result=ensure(a);assert.strictEqual(result.state,'ready');assert.strictEqual(result.binding,'decoded-source-pcm');assert.strictEqual(result.source_sha256,asset.sha256);
 assert.strictEqual(a.split.count,2,'The engine has already mapped the source pair into stereo');assert.strictEqual(a.split.connections[0][1],0);assert.strictEqual(a.split.connections[1][1],1);assert.strictEqual(a.stereo,null);assert.strictEqual(a.audioGate.gain.value,1);
 const originalSource=a.source,oldURL=a.el.src;
 const second={audio:{stream_index:2,channels:[1,1]}};result=ensure(a,second);assert.strictEqual(result.state,'pending');assert.strictEqual(a.audioGate.gain.value,0);assert.strictEqual(posts.length,2);
 // Change choice again while the earlier request is in flight. Its eventual
 // receipt may populate the shared cache but cannot change this decoder.
 const third={audio:{stream_index:2,channels:[2,1]}};ensure(a,third);assert.strictEqual(posts.length,3);
 const stale=requests.shift(),current=requests.shift();stale.resolve(manifest(stale.body));await flush();assert.strictEqual(a.el.src,oldURL);
 current.resolve(manifest(current.body));await flush();assert.strictEqual(a.el.src,manifest(current.body).url);a.el.ready();
 assert.strictEqual(ensure(a,third).state,'ready');assert.strictEqual(a.source,originalSource);assert.strictEqual(sources,10,'The existing five-node gain graph survives a different source pair');
 // Cancel only the client's wait. The shared server job must not be cancelled.
 const fourth={audio:{stream_index:2,channels:[3,1]}};ensure(a,fourth);const pending=requests.shift();pending.resolve({job:{id:'cancel-wait',state:'queued'}});await flush();api.suspend();await flush();
 assert(![...timers.values()].some(t=>t.delay===150));assert.strictEqual(posts.length,4);assert(!gets.some(path=>path.includes('cancel')));
 ensure(a,fourth,{prepare:false});assert.strictEqual(posts.length,4);
 // Release all observers and owned graph connections.
 api.release(a);api.release(b);assert.strictEqual(a.source.connections.length,0);assert.strictEqual(a.audioGate.gain.value,0);assert.strictEqual(timers.size,0);
 assert([...a.el.listeners.values()].every(list=>list.size===0));
 // A stale result after switching projects cannot rebind a disposed source.
 const c=media();ensure(c,{audio:{stream_index:2,channels:[4,1]}});const released=requests.shift();api.release(c);released.resolve(manifest(released.body));await flush();assert.strictEqual(c.el.src,'');
 assert.strictEqual(warnings.length,0);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'module':str(Path(__file__).parent/'web/audio-routing.js')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_owned_pcm_refuses_wrong_receipts_and_resolves_shared_asset_alias(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=JSON.parse(fs.readFileSync(0,'utf8')).module;
const node=()=>({gain:{value:1},connect(){},disconnect(){}}),context={destination:node(),createMediaElementSource:node,createGain:node,createChannelSplitter:node,createChannelMerger:node};
const sandbox={window:{},setTimeout,clearTimeout};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path,'utf8'),sandbox);
const api=sandbox.window.CinematicumAudioRouting,asset={id:'asset',sha256:'a'.repeat(64),duration:1,has_audio:true,audio_stream_index:1,audio_channels:2,audio_streams:[{index:1,channels:2}]};
const ready={state:'ready',version:2,playback_rate:1,source_time_scale:1,data_offset:58,frame_bytes:8,asset_id:'asset',source_sha256:asset.sha256,stream_index:1,channels:[1,0],cache_key:'c'.repeat(64),sha256:'b'.repeat(64),url:'/api/projects/p/audio-source/'+'c'.repeat(64),codec:'pcm_f32le',rate:48000,output_channels:2,frames:48000,source_frames:48000,padded_frames:0,duration:1,byte_size:384058};
const make=()=>({kind:'audio',el:{readyState:0,muted:false,volume:1,pause(){},loadSource(context,output,manifest){this.src=manifest.url;},clear(){this.src='';},addEventListener(){},removeEventListener(){}}});
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
(async()=>{
 for(const changes of [{source_sha256:'d'.repeat(64)},{stream_index:0},{channels:[0,1]},{rate:44100},{output_channels:1},{codec:'aac'},{url:'https://foreign.example/pcm.wav'},{frames:1},{asset_id:'other'},{version:1},{data_offset:44},{frame_bytes:4},{playback_rate:1.5},{source_time_scale:1.5},{byte_size:384044}]){
  let warnings=0;const m=make(),ownAsset={...asset,id:'asset'+JSON.stringify(changes)};
  api.configure({getProject:()=>({id:'p'}),request:async()=>({...ready,asset_id:ownAsset.id,...changes})});
  api.ensure(m,context,{audio:{channels:[1,0]}},ownAsset,()=>warnings++);await flush();
  assert.strictEqual(m.audioRoute.state,'unsupported');assert.strictEqual(m.el.src,undefined);assert.strictEqual(m.el.muted,true);assert.strictEqual(warnings,1);
  api.ensure(m,context,{audio:{channels:[1,0]}},ownAsset,()=>warnings++);assert.strictEqual(warnings,1);api.release(m);
 }
 let posts=0;const m=make();api.configure({getProject:()=>({id:'p'}),request:async(path,options)=>{
  if(options?.method==='POST'){posts++;return posts===1?{job:{id:'shared',state:'completed',result:{...ready,asset_id:'other'}}}:ready;}
  throw Error('No poll is required for an already completed shared job');
 }});
 api.ensure(m,context,{audio:{channels:[1,0]}},asset);await flush();assert.strictEqual(posts,2);assert.strictEqual(m.el.src,ready.url);assert.strictEqual(m.audioRoute.state,'pending');
 m.el.readyState=4;assert.strictEqual(api.ensure(m,context,{audio:{channels:[1,0]}},asset).state,'ready');api.release(m);
 const invalid=make();assert.strictEqual(api.ensure(invalid,context,{audio:{channels:[9,0]}},asset).state,'unsupported');assert.strictEqual(invalid.el.src,undefined);api.release(invalid);
 assert.strictEqual(api.ensure(make(),context,{}, {has_audio:false}).state,'silent');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'module':str(Path(__file__).parent/'web/audio-routing.js')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_probe_exposes_container_track_ids_separate_from_stream_indexes(self):
        with tempfile.TemporaryDirectory(prefix='cinematicum-audio-identity-ENGINE-TEST-') as root:
            path=Path(root)/'ENGINE_TEST.mov'
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1',
                            '-f','lavfi','-i','color=s=32x32:r=24:d=0.25','-f','lavfi','-i','aevalsrc=.1|.2:s=48000:d=0.25',
                            '-f','lavfi','-i','aevalsrc=.3|.4:s=48000:d=0.25','-map','0:v','-map','1:a','-map','2:a',
                            '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','pcm_s16le',str(path)],
                           capture_output=True,check=True,timeout=10)
            streams=probe_media(path)['audio_streams']
            self.assertEqual([stream['index'] for stream in streams],[1,2])
            self.assertEqual([int(stream['container_id'],16) for stream in streams],[2,3])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_saving_legacy_asset_metadata_retains_reprobed_container_ids_on_reopen(self):
        from server import Store
        with tempfile.TemporaryDirectory(prefix='cinematicum-legacy-audio-ENGINE-TEST-') as root:
            root=Path(root);source=root/'ENGINE_TEST.mov';workspace=root/'workspace';store=None
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1',
                            '-f','lavfi','-i','color=s=32x32:r=24:d=0.25','-f','lavfi','-i','aevalsrc=.1|.2:s=48000:d=0.25',
                            '-f','lavfi','-i','aevalsrc=.3|.4:s=48000:d=0.25','-map','0:v','-map','1:a','-map','2:a',
                            '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','pcm_s16le',str(source)],
                           capture_output=True,check=True,timeout=10)
            identity=hashlib.sha256(source.read_bytes()).hexdigest();expected=probe_media(source)['audio_streams']
            try:
                store=Store(workspace);project=store.new_project({'name':'ENGINE TEST legacy source metadata','width':32,'height':32,'fps':24})
                asset=store.admit(project['id'],source,'ENGINE TEST.mov');directory=store.project_dir(project['id'])
                assets_file=directory/'assets.json';legacy=json.loads(assets_file.read_text())
                for stream in legacy[0]['audio_streams']:stream.pop('container_id',None)
                assets_file.write_text(json.dumps(legacy))
                project=store.get(project['id']);self.assertTrue(all('container_id' not in stream for stream in project['assets'][0]['audio_streams']))
                project['clips']=[{'id':'source','asset_id':asset['id'],'start':0,'duration':6,'in':0,'track':0}]
                saved=store.save(project['id'],project);self.assertEqual(saved['assets'][0]['audio_streams'],expected)
                store.shutdown();store=Store(workspace);reopened=store.get(project['id']);retained=reopened['assets'][0]
                self.assertEqual(retained['audio_streams'],expected)
                self.assertEqual({key:retained[key] for key in ('id','path','sha256')},{key:asset[key] for key in ('id','path','sha256')})
                self.assertEqual(hashlib.sha256((directory/retained['path']).read_bytes()).hexdigest(),identity)
                self.assertEqual(reopened['clips'][0]['asset_id'],asset['id'])
            finally:
                if store:store.shutdown()


if __name__=='__main__':unittest.main()

#!/usr/bin/env node
/* Actual decoded-frame reuse through shipped traversal and pinned Chrome/CDP.
 * Usage: node test_decoded_frame_cache_browser.cjs --browser ABS [--evidence NEW_ABS]
 * POSIX, Node 22 built-ins and FFmpeg only; no browser/package downloads.
 * Synthetic ENGINE TEST media and the owned browser profile are removed on exit.
 * This does not certify sustained production-media or native Mac performance.
 */
'use strict';
const fs=require('node:fs'),http=require('node:http'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const values=process.argv.slice(2),options={};
if(values.length%2)throw Error('Use paired --option value arguments');
for(let i=0;i<values.length;i+=2){if(!['--browser','--evidence'].includes(values[i])||options[values[i]])throw Error('Unknown or duplicate option');options[values[i]]=values[i+1];}
if(typeof WebSocket!=='function')throw Error('Node 22 built-in WebSocket is required');
if(process.platform==='win32')throw Error('This acceptance harness requires an owned POSIX browser process group');
if(!options['--browser']||!path.isAbsolute(options['--browser'])||!fs.statSync(options['--browser']).isFile())throw Error('--browser requires an existing absolute browser executable');
if(options['--evidence']&&!path.isAbsolute(options['--evidence']))throw Error('--evidence requires a new absolute directory');
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
function signalOwnedGroup(group,signal){
 // The only supplied ID is the PID returned by our detached:true spawn below.
 // POSIX creates a new session/group with that ID; it cannot be our outer group.
 // No request-provided group IDs, zero (current group), or negative IDs enter.
 if(group===null)return false;
 if(!Number.isSafeInteger(group)||group<=1||group===process.pid)throw Error('Invalid owned browser process group');
 try{process.kill(-group,signal);return true;}catch(error){if(error.code==='ESRCH')return false;throw error;}
}
async function stopOwnedGroup(group){
 // A browser main process may exit before its renderer/GPU children. Signal
 // the owned group even after that exit; main-PID liveness is not sufficient.
 if(!signalOwnedGroup(group,'SIGTERM'))return;
 await new Promise(resolve=>setTimeout(resolve,250));
 signalOwnedGroup(group,'SIGKILL');
 await new Promise(resolve=>setTimeout(resolve,100));
}
class CDP {
 constructor(socket,deadline){
  this.socket=socket;this.deadline=deadline;this.nextId=0;this.pending=new Map();this.events=new Set();this.errors=[];
  socket.addEventListener('message',event=>{
   let value;try{value=JSON.parse(event.data);}catch(error){this.fail(error);return;}
   if(value.id){const item=this.pending.get(value.id);if(!item)return;this.pending.delete(value.id);clearTimeout(item.timer);if(value.error)item.reject(Error(value.error.message));else item.resolve(value.result);}
   else{
    if(value.method==='Runtime.exceptionThrown')this.errors.push(value.params.exceptionDetails.exception?.description||value.params.exceptionDetails.text);
    for(const item of this.events)if(value.method===item.method&&value.sessionId===item.sessionId){this.events.delete(item);clearTimeout(item.timer);item.resolve(value.params);}
   }
  });
  socket.addEventListener('close',()=>this.fail(Error('Owned CDP connection closed')));
  socket.addEventListener('error',()=>this.fail(Error('Owned CDP connection failed')));
 }
 static async connect(url,deadline){
  const socket=new WebSocket(url),cdp=new CDP(socket,deadline);
  await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{socket.close();reject(Error('CDP connection deadline exceeded'));},Math.max(1,deadline-Date.now()));
   socket.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
   socket.addEventListener('error',()=>{clearTimeout(timer);reject(Error('CDP connection failed'));},{once:true});
  });return cdp;
 }
 fail(error){for(const item of this.pending.values()){clearTimeout(item.timer);item.reject(error);}this.pending.clear();for(const item of this.events){clearTimeout(item.timer);item.reject(error);}this.events.clear();}
 send(method,params={},sessionId){
  const id=++this.nextId;return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{this.pending.delete(id);reject(Error('CDP deadline exceeded: '+method));},Math.max(1,this.deadline-Date.now()));
   this.pending.set(id,{resolve,reject,timer});
   try{this.socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));}catch(error){clearTimeout(timer);this.pending.delete(id);reject(error);}
  });
 }
 event(method,sessionId){
  return new Promise((resolve,reject)=>{const item={method,sessionId,resolve,reject};item.timer=setTimeout(()=>{this.events.delete(item);reject(Error('CDP event deadline exceeded: '+method));},Math.max(1,this.deadline-Date.now()));this.events.add(item);});
 }
 close(){this.fail(Error('CDP test finished'));try{this.socket.close();}catch(error){}}
}
async function main(){
 const started=Date.now(),deadline=started+15000,web=path.join(__dirname,'web');
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'cinematicum-decoded-frame-ENGINE-TEST-'));
 let server,browser,cdp,evidence=null,stderr='',spawnError=null,exited=false,ownedBrowserGroup=null;
 const signal=()=>{signalOwnedGroup(ownedBrowserGroup,'SIGKILL');if(server){server.closeAllConnections();server.close();}fs.rmSync(temporary,{recursive:true,force:true});process.exit(143);};process.once('SIGTERM',signal);process.once('SIGINT',signal);
 try{
  if(options['--evidence']){evidence=options['--evidence'];fs.mkdirSync(evidence);}
  const fixture=path.join(temporary,'ENGINE-TEST-decoded-frames.mp4');
  const generated=spawnSync('ffmpeg',['-v','error','-nostdin','-y','-f','lavfi','-i','testsrc2=size=64x48:rate=24:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-g','1',fixture],{encoding:'utf8',timeout:Math.min(6000,Math.max(1,deadline-Date.now())),maxBuffer:1024*1024});
  if(generated.status!==0)throw Error('ENGINE TEST fixture generation failed: '+(generated.error||generated.stderr));
  const index=fs.readFileSync(path.join(web,'index.html'),'utf8');
  assert(index.indexOf('src="/decoded-frame-cache.js"')>index.indexOf('src="/editing.js"'));
  assert(index.indexOf('src="/sequence-playback.js"')>index.indexOf('src="/decoded-frame-cache.js"'),'Production script order must initialize the cache before traversal');
  const sources={};for(const name of ['editing.js','decoded-frame-cache.js','sequence-playback.js'])sources['/'+name]=fs.readFileSync(path.join(web,name));
  const media=fs.readFileSync(fixture),html=Buffer.from('<!doctype html><script src="/editing.js"></script><script src="/decoded-frame-cache.js"></script><script src="/sequence-playback.js"></script><body></body>');
  server=http.createServer((req,res)=>{
   const value=req.url==='/'?html:req.url==='/fixture.mp4'?media:sources[req.url];if(!value){res.writeHead(404);res.end();return;}
   res.setHeader('Content-Type',req.url==='/fixture.mp4'?'video/mp4':req.url==='/'?'text/html':'text/javascript');
   if(req.url==='/fixture.mp4'){
    res.setHeader('Accept-Ranges','bytes');const match=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');
    if(match){const first=Number(match[1]),last=Math.min(value.length-1,match[2]?Number(match[2]):value.length-1);if(first>last||first>=value.length){res.writeHead(416,{'Content-Range':'bytes */'+value.length});res.end();return;}res.writeHead(206,{'Content-Range':`bytes ${first}-${last}/${value.length}`,'Content-Length':last-first+1});res.end(value.subarray(first,last+1));return;}
   }
   res.setHeader('Content-Length',value.length);res.end(value);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port,profile=path.join(temporary,'browser-profile');
  const browserHash=hash(fs.readFileSync(options['--browser']));
  // detached:true creates a separately owned POSIX group for complete cleanup.
  // The harness remains its foreground supervisor: no unref or background job.
  browser=spawn(options['--browser'],['--headless=new','--no-sandbox','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions','--disable-component-update','--disable-default-apps','--safebrowsing-disable-auto-update','--autoplay-policy=no-user-gesture-required','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe'],detached:true});
  ownedBrowserGroup=Number.isSafeInteger(browser.pid)?browser.pid:null;
  browser.on('error',error=>{spawnError=error;});browser.on('exit',()=>{exited=true;});browser.stderr.on('data',data=>{if(stderr.length<48000)stderr+=data.toString().slice(0,48000-stderr.length);});
  const activePort=path.join(profile,'DevToolsActivePort');let discovery;
  while(Date.now()<deadline){
   if(spawnError)throw spawnError;if(exited)throw Error('Owned browser exited before CDP became ready: '+stderr);
   if(fs.existsSync(activePort)){const lines=fs.readFileSync(activePort,'utf8').trim().split('\n');if(/^\d+$/.test(lines[0])&&lines[1]?.startsWith('/devtools/browser/')){discovery='ws://127.0.0.1:'+lines[0]+lines[1];break;}}
   await new Promise(resolve=>setTimeout(resolve,25));
  }
  if(!discovery)throw Error('Owned Chrome did not expose CDP before the foreground deadline');
  cdp=await CDP.connect(discovery,deadline);const version=await cdp.send('Browser.getVersion');
  const {targetId}=await cdp.send('Target.createTarget',{url:'about:blank'}),{sessionId}=await cdp.send('Target.attachToTarget',{targetId,flatten:true});
  await cdp.send('Page.enable',{},sessionId);await cdp.send('Runtime.enable',{},sessionId);
  const loaded=cdp.event('Page.loadEventFired',sessionId);loaded.catch(()=>{});await cdp.send('Page.navigate',{url:origin},sessionId);await loaded;
  const scenario=async()=>{
   const video=document.createElement('video');video.muted=true;video.preload='auto';document.body.append(video);
   const loaded=new Promise((resolve,reject)=>{video.addEventListener('loadeddata',resolve,{once:true});video.addEventListener('error',reject,{once:true});});video.src='/fixture.mp4';await loaded;
   let registrations=0;const request=video.requestVideoFrameCallback;
   if(request)video.requestVideoFrameCallback=function(callback){registrations++;return request.call(this,callback);};
   const canvas=document.createElement('canvas');canvas.width=64;canvas.height=48;document.body.append(canvas);const target=canvas.getContext('2d',{willReadFrequently:true});
   const media={kind:'video',el:video,requestUrl:'/fixture.mp4',disposed:false};let seeks=0;video.addEventListener('seeking',()=>seeks++);
   const project={id:'ENGINE-TEST-cache',fps:24,width:64,height:48,titles:[],tracks:[],assets:[{id:'asset',kind:'video',sha256:'a'.repeat(64),width:64,height:48}],clips:[{id:'clip',asset_id:'asset',start:0,in:0,duration:48,track:0}]};
   const playback=window.CinematicumSequencePlayback,draw=(frame,playing=false)=>{target.clearRect(0,0,64,48);playback.draw({project,frame,context:target,width:64,height:48,mediaFor:()=>media,ensureAudio:()=>null,playing,activeIds:new Set(),revision:0});};
   const pixels=()=>Array.from(target.getImageData(0,0,64,48).data),fingerprint=()=>pixels().reduce((hash,value)=>Math.imul(hash^value,16777619)>>>0,2166136261);
   const seekDraw=async frame=>{draw(frame);if(video.seeking)await new Promise(resolve=>video.addEventListener('seeked',resolve,{once:true}));draw(frame);return fingerprint();};
   const first=await seekDraw(6),firstPixels=pixels(),second=await seekDraw(12),before=seeks;draw(6);await new Promise(resolve=>setTimeout(resolve,30));
   const reused=fingerprint(),reusedPixels=pixels(),identicalPixels=firstPixels.every((value,i)=>value===reusedPixels[i]),after=seeks,stats=playback.cacheStats();
   playback.clear();const cleared=playback.cacheStats(),forwardRegistrations=registrations;
   draw(12,true);await new Promise(resolve=>setTimeout(resolve,60));const forward=playback.cacheStats(),forwardCopies=forward.bytes,forwardCallbacks=registrations-forwardRegistrations;video.pause();playback.clear();
   return {first,second,reused,identicalPixels,before,after,stats,cleared,forwardCopies,forwardCallbacks};
  };
const evaluated=await cdp.send('Runtime.evaluate',{expression:'('+scenario.toString()+')()',awaitPromise:true,returnByValue:true},sessionId);
  if(evaluated.exceptionDetails)throw Error(evaluated.exceptionDetails.exception?.description||evaluated.exceptionDetails.text);
  const result=evaluated.result.value;
  assert.notEqual(result.first,result.second,'Native decoded fixture frames must differ');assert.equal(result.reused,result.first);assert.equal(result.identicalPixels,true,'Frozen decoded pixel bytes must match their original picture');assert.equal(result.after,result.before,'Cache hit must avoid a new native decoder seek');assert(result.stats.hits>=1);assert.equal(result.cleared.bytes,0);assert.equal(result.cleared.observers,0);assert.equal(result.forwardCopies,0,'Normal forward playback must allocate no decoded snapshots');assert.equal(result.forwardCallbacks,0,'Normal forward playback must register no snapshot callbacks');assert.deepEqual(cdp.errors,[]);
  const afterHash=hash(fs.readFileSync(options['--browser']));assert.equal(afterHash,browserHash,'The pinned browser executable changed during acceptance');
  const report={schema:'cinematicum-decoded-frame-browser-v1',passed:true,synthetic_engine_test:true,native_certified:false,production_media_accepted:false,transport:'Chrome DevTools Protocol / Node22 WebSocket',browser_version:version.product,browser_sha256:browserHash,browser_sha256_after:afterHash,fixture_sha256:hash(media),source_sha256:Object.fromEntries(Object.entries(sources).map(([name,data])=>['web'+name,hash(data)])),index_sha256:hash(Buffer.from(index)),elapsed_ms:Date.now()-started,...result};
  if(evidence){const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',fromSurface:true},sessionId);fs.writeFileSync(path.join(evidence,'decoded-frame-cache.png'),Buffer.from(screenshot.data,'base64'));fs.writeFileSync(path.join(evidence,'report.json'),JSON.stringify(report,null,2)+'\n');}
  console.log(JSON.stringify(report));
 }catch(error){if(evidence){fs.writeFileSync(path.join(evidence,'failure.json'),JSON.stringify({passed:false,error:String(error.stack||error)},null,2)+'\n');fs.writeFileSync(path.join(evidence,'browser.stderr'),stderr);}throw error;}
 finally{
  if(cdp){cdp.deadline=Date.now()+500;await cdp.send('Browser.close').catch(()=>{});cdp.close();}
  await stopOwnedGroup(ownedBrowserGroup);
  if(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
  fs.rmSync(temporary,{recursive:true,force:true,maxRetries:2,retryDelay:50});process.removeListener('SIGTERM',signal);process.removeListener('SIGINT',signal);
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});

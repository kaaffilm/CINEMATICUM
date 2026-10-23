/* Original-source decoded pictures and explicit, bounded WebGL texture storage.
 * Disabled until the application enables/prepares it. No native video copying
 * or API calls happen while ordinary playback traverses cache misses.
 */
(()=>{
 'use strict';
 const HASH=/^[a-f0-9]{64}$/,INTEGER=/^-?[0-9]{1,16}$/,POSITIVE=/^[1-9][0-9]{0,9}$/;
 const MAX_BYTES=96*1024*1024,MAX_ENTRIES=120,POLICY='opaque-rgba8-srgb-bt709-display-sar-autorotation-v1';
 const decimal=value=>{if(typeof value!=='number'||!Number.isFinite(value))throw Error('Source time must be finite.');const match=String(value).match(/^(-?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i),fraction=match[3]||'',power=Number(match[4]||0)-fraction.length;let n=BigInt(match[2]+fraction)*(match[1]?-1n:1n),d=1n;if(power>=0)n*=10n**BigInt(power);else d=10n**BigInt(-power);return {n,d};};
 const abortError=()=>Object.assign(Error('Source-picture preparation was cancelled or superseded.'),{name:'AbortError'});
 const limit=(value,name)=>{if(!Number.isSafeInteger(value)||value<0||value>MAX_BYTES)throw Error(name+' must be an integer byte budget from0 through96MiB.');return value;};
 class SourceFrameCache{
  constructor({maxCpuBytes=MAX_BYTES,maxGpuBytes=MAX_BYTES,maxEntries=MAX_ENTRIES,onChange=()=>{},createCanvas=()=>document.createElement('canvas'),makeImageData=(bytes,width,height)=>new ImageData(bytes,width,height),fetchBytes=(url,options)=>fetch(url,options),digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),value=>value.toString(16).padStart(2,'0')).join('')}={}){
   this.maxCpuBytes=limit(maxCpuBytes,'CPU cache');this.maxGpuBytes=limit(maxGpuBytes,'Texture cache');if(!Number.isSafeInteger(maxEntries)||maxEntries<1||maxEntries>MAX_ENTRIES)throw Error('The decoded cache retains1–120 pictures.');
   this.maxEntries=maxEntries;this.onChange=onChange;this.createCanvas=createCanvas;this.makeImageData=makeImageData;this.fetchBytes=fetchBytes;this.digest=digest;
   this.enabled=false;this.entries=new Map();this.textures=new Map();this.cpuBytes=0;this.gpuBytes=0;this.gpuSurfaceBytes=0;this.pending=null;this.epoch=0;this.hits=0;this.misses=0;this.uploads=0;this.deletions=0;this.contextLosses=0;this.gpuUnavailable=false;this.disposed=false;this.gl=null;this.gpuCanvas=null;this.program=null;this.buffer=null;
  }
  static eligible(project,asset){return Boolean(project&&asset&&asset.kind==='video'&&HASH.test(asset.sha256||'')&&(project.settings?.image_precision||'standard8')==='standard8'&&asset.color_transfer==='iec61966-2-1'&&! /^(yuva|gbrap|rgba|bgra|argb|abgr|ya)/.test(asset.pixel_format||''));}
  setEnabled(value){if(typeof value!=='boolean')throw Error('Choose an explicit cache enabled state.');if(this.disposed)throw Error('The source-picture cache was disposed.');this.enabled=value;if(!value)this.clear();this._notify();}
  _notify(){try{this.onChange(this.stats());}catch(error){}}
  _identity(project,asset){return JSON.stringify([project.id,asset.id,asset.sha256,asset.video_stream_index,asset.width,asset.height]);}
  _frameKey(identity,receipt,frame){return identity+'|'+receipt.time_base.numerator+'/'+receipt.time_base.denominator+'|'+frame.pts;}
  _dropTexture(entry){if(!entry.texture)return;try{this.gl?.deleteTexture(entry.texture);}catch(error){}this.deletions++;this.gpuBytes-=entry.byteSize;this.textures.delete(entry.key);entry.texture=null;}
  _drop(entry){this._dropTexture(entry);this.entries.delete(entry.key);this.cpuBytes-=entry.byteSize;entry.canvas.width=1;entry.canvas.height=1;}
  _room(bytes,entries=0){while(this.entries.size&&(this.cpuBytes+bytes>this.maxCpuBytes||this.entries.size+entries>this.maxEntries))this._drop(this.entries.values().next().value);if(this.cpuBytes+bytes>this.maxCpuBytes||entries>this.maxEntries)throw Error('The decoded source window exceeds the retained CPU cache budget.');}
  _validate(project,asset,receipt){
   if(!SourceFrameCache.eligible(project,asset))throw Error('Source-picture caching requires opaque Standard8 video with explicitly tagged sRGB transfer.');
   if(!receipt||receipt.version!==1||receipt.source_sha256!==asset.sha256||receipt.stream_index!==asset.video_stream_index||receipt.width!==asset.width||receipt.height!==asset.height||receipt.pixel_format!=='rgba8'||receipt.opaque!==true||receipt.source_only!==true||receipt.decoder_pts_verified!==true||receipt.policy!==POLICY||!HASH.test(receipt.cache_key||'')||!HASH.test(receipt.sha256||''))throw Error('The decoded source receipt does not match this original source.');
   const size=receipt.width*receipt.height*4,count=receipt.frame_count;
   if(!Number.isSafeInteger(size)||size<4||Math.max(receipt.width,receipt.height)>4096||receipt.width*receipt.height>4096*2160||!Number.isInteger(count)||count<1||count>MAX_ENTRIES||count>this.maxEntries||receipt.byte_size!==size*count||receipt.byte_size>this.maxCpuBytes||receipt.byte_size>MAX_BYTES)throw Error('The decoded source receipt exceeds its exact CPU byte/count budget.');
   if(!receipt.time_base||!POSITIVE.test(receipt.time_base.numerator)||!POSITIVE.test(receipt.time_base.denominator)||!INTEGER.test(receipt.origin_pts||'')||!Array.isArray(receipt.frames)||receipt.frames.length!==count)throw Error('The decoded source receipt has no bounded native clock.');
   const origin=BigInt(receipt.origin_pts),baseN=BigInt(receipt.time_base.numerator),baseD=BigInt(receipt.time_base.denominator);let previous=null;
   for(let i=0;i<count;i++){const frame=receipt.frames[i];if(!frame||!INTEGER.test(frame.pts||'')||!INTEGER.test(frame.end_pts||'')||!HASH.test(frame.sha256||'')||frame.byte_offset!==i*size||frame.byte_size!==size)throw Error('The decoded source frame inventory is invalid.');const first=BigInt(frame.pts),last=BigInt(frame.end_pts);if(first>=last||previous!==null&&first!==previous)throw Error('The decoded source PTS intervals are not consecutive.');previous=last;}
   return {size,count,origin,baseN,baseD,identity:this._identity(project,asset)};
  }
  async accept(project,asset,receipt,bytes,isCurrent=()=>true){
   if(!this.enabled||this.disposed)throw abortError();const epoch=this.epoch,valid=this._validate(project,asset,receipt),payload=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes);
   if(payload.byteLength!==receipt.byte_size)throw Error('The source decoder byte inventory is incomplete.');
   const current=()=>this.enabled&&!this.disposed&&this.epoch===epoch&&isCurrent();
   if(!current())throw abortError();this._room(payload.byteLength,valid.count);
   if(await this.digest(payload)!==receipt.sha256)throw Error('The decoded source payload SHA-256 differs from its receipt.');
   for(const frame of receipt.frames){if(!current())throw abortError();const part=payload.subarray(frame.byte_offset,frame.byte_offset+frame.byte_size);if(await this.digest(part)!==frame.sha256)throw Error('A decoded source picture SHA-256 differs from its receipt.');for(let i=3;i<part.length;i+=4)if(part[i]!==255)throw Error('The source decoder returned alpha in an opaque cache window.');}
   const staged=[];
   try{
    for(const frame of receipt.frames){
     if(!current())throw abortError();const key=this._frameKey(valid.identity,receipt,frame),old=this.entries.get(key);if(old&&old.sha256===frame.sha256)continue;
     const canvas=this.createCanvas();canvas.width=receipt.width;canvas.height=receipt.height;staged.push({key,canvas,identity:valid.identity,sourceSha:asset.sha256,stream:asset.video_stream_index,pts:BigInt(frame.pts),endPts:BigInt(frame.end_pts),origin:valid.origin,baseN:valid.baseN,baseD:valid.baseD,width:receipt.width,height:receipt.height,byteSize:valid.size,sha256:frame.sha256,texture:null,gpuUnsupported:false});
     const context=canvas.getContext('2d');if(!context)throw Error('Decoded source Canvas2D storage is unavailable.');const part=new Uint8ClampedArray(payload.buffer,payload.byteOffset+frame.byte_offset,frame.byte_size);context.putImageData(this.makeImageData(part,receipt.width,receipt.height),0,0);
    }
    if(!current())throw abortError();
    for(const entry of staged){const old=this.entries.get(entry.key);if(old)this._drop(old);this._room(entry.byteSize,1);this.entries.set(entry.key,entry);this.cpuBytes+=entry.byteSize;}
   }catch(error){for(const entry of staged)if(this.entries.get(entry.key)!==entry){entry.canvas.width=1;entry.canvas.height=1;}throw error;}
   this._notify();return this.stats();
  }
  async _download(response,expected,check){
   if(!response.body?.getReader)throw Error('Bounded streaming source downloads are unavailable.');const reader=response.body.getReader(),bytes=new Uint8Array(expected);let offset=0;try{for(;;){check();const part=await reader.read();check();if(part.done)break;if(!(part.value instanceof Uint8Array)||offset+part.value.byteLength>expected)throw Error('The source-picture response exceeded its exact byte inventory.');bytes.set(part.value,offset);offset+=part.value.byteLength;}if(offset!==expected)throw Error('The source-picture response was truncated.');return bytes;}catch(error){await reader.cancel().catch(()=>{});throw error;}finally{reader.releaseLock();}
  }
  async prepare({project,asset,start=0,frames=60,request,isCurrent=()=>true,onProgress=()=>{}}){
   if(!this.enabled||this.disposed)throw abortError();if(this.pending)throw Error('Finish or cancel the previous source-picture preparation.');if(typeof request!=='function')throw Error('The authenticated application request bridge is required.');
   if(!SourceFrameCache.eligible(project,asset))throw Error('Source-picture caching requires opaque Standard8 video with explicitly tagged sRGB transfer.');
   const frameBytes=asset.width*asset.height*4;frames=Math.min(frames,this.maxEntries,Math.floor(this.maxCpuBytes/frameBytes));if(!Number.isInteger(frames)||frames<1||!Number.isFinite(start)||start<0||start>21600)throw Error('The source window is outside its time/byte bounds.');
   const owned={epoch:this.epoch,controller:new AbortController(),request,job:null,cancelled:false,deadline:Date.now()+120000};this.pending=owned;
   const check=()=>{if(owned.cancelled||this.epoch!==owned.epoch||!this.enabled||!isCurrent()||Date.now()>owned.deadline)throw abortError();};
   const cancelJob=()=>{if(owned.job&&!owned.cancelSent){owned.cancelSent=true;request('/api/jobs/'+encodeURIComponent(owned.job)+'/cancel',{method:'POST',body:{}}).catch(()=>{});}};owned.cancel=()=>{owned.cancelled=true;owned.controller.abort();cancelJob();};
   const bridge=(path,options)=>new Promise((resolve,reject)=>{const stop=()=>reject(abortError());owned.controller.signal.addEventListener('abort',stop,{once:true});Promise.resolve().then(()=>request(path,options)).then(value=>{const job=value?.job||value;if(options?.method==='POST'&&typeof job?.id==='string'){owned.job=job.id;if(owned.cancelled)cancelJob();}if(!owned.cancelled)resolve(value);},reject).finally(()=>owned.controller.signal.removeEventListener('abort',stop));});
   const deadlineTimer=setTimeout(()=>owned.cancel(),120000);
   try{
    this._room(frameBytes*frames,frames);const response=await bridge('/api/projects/'+encodeURIComponent(project.id)+'/source-frames',{method:'POST',body:{asset_id:asset.id,start,frames}});
    let job=response.job||response;owned.job=typeof job.id==='string'?job.id:null;if(owned.cancelled){cancelJob();throw abortError();}check();
    while(job.state==='queued'||job.state==='running'){
     onProgress(Number(job.progress)||0);await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{owned.controller.signal.removeEventListener('abort',stop);resolve();},150);const stop=()=>{clearTimeout(timer);reject(abortError());};owned.controller.signal.addEventListener('abort',stop,{once:true});});check();const polled=await bridge('/api/jobs/'+encodeURIComponent(owned.job));job=polled.job||polled;check();
    }
    if(job.state!=='completed')throw Error(job.error||'No decoded source pictures were admitted.');const receipt=job.result;this._validate(project,asset,receipt);check();
    const expected='/api/projects/'+encodeURIComponent(project.id)+'/source-frames/'+receipt.cache_key;if(receipt.url!==expected)throw Error('The source-picture result points outside its owned byte route.');
    const fetched=await this.fetchBytes(expected,{cache:'no-store',signal:owned.controller.signal});if(!fetched.ok)throw Error('The decoded source bytes are unavailable.');const length=fetched.headers?.get?.('Content-Length');if(length!==null&&length!==undefined&&Number(length)!==receipt.byte_size)throw Error('The source-picture response length differs from its receipt.');
    const bytes=await this._download(fetched,receipt.byte_size,check);check();await this.accept(project,asset,receipt,bytes,()=>!owned.cancelled&&isCurrent());check();onProgress(1);return this.stats();
   }catch(error){owned.cancel();throw error;}finally{clearTimeout(deadlineTimer);if(this.pending===owned)this.pending=null;this._notify();}
  }
  _shader(gl,type,source){const shader=gl.createShader(type);if(!shader)throw Error('No WebGL shader resource.');gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)){gl.deleteShader(shader);throw Error('The source texture shader could not compile.');}return shader;}
  _ensureGL(){
   if(this.gpuUnavailable||this.maxGpuBytes===0)return false;if(this.gl&&!this.gl.isContextLost?.())return true;
   const canvas=this.gpuCanvas||this.createCanvas();canvas.width=1;canvas.height=1;this.gpuCanvas=canvas;
   if(!this.lost){this.lost=event=>{event.preventDefault?.();this.contextLosses++;for(const entry of this.textures.values())entry.texture=null;this.textures.clear();this.gpuBytes=0;this.gpuSurfaceBytes=0;this.gl=null;this.program=null;this.buffer=null;this.gpuUnavailable=true;this._notify();};this.restored=()=>{this.gpuUnavailable=false;this._notify();};canvas.addEventListener?.('webglcontextlost',this.lost);canvas.addEventListener?.('webglcontextrestored',this.restored);}
   let gl,vertex,fragment,program,buffer;
   try{
    gl=canvas.getContext('webgl',{alpha:false,premultipliedAlpha:false,preserveDrawingBuffer:true,antialias:false,depth:false,stencil:false});if(!gl||gl.isContextLost?.())throw Error('WebGL texture storage is unavailable.');
    vertex=this._shader(gl,gl.VERTEX_SHADER,'attribute vec2 position;attribute vec2 coordinates;varying vec2 uv;void main(){uv=coordinates;gl_Position=vec4(position,0.0,1.0);}');fragment=this._shader(gl,gl.FRAGMENT_SHADER,'precision highp float;varying vec2 uv;uniform sampler2D picture;void main(){gl_FragColor=texture2D(picture,uv);}');program=gl.createProgram();if(!program)throw Error('No WebGL program resource.');gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('The source texture program could not link.');gl.deleteShader(vertex);vertex=null;gl.deleteShader(fragment);fragment=null;
    buffer=gl.createBuffer();if(!buffer)throw Error('No WebGL vertex buffer resource.');gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,0,1,1,-1,1,1,-1,1,0,0,1,1,1,0]),gl.STATIC_DRAW);gl.useProgram(program);const position=gl.getAttribLocation(program,'position'),coordinates=gl.getAttribLocation(program,'coordinates');if(position<0||coordinates<0)throw Error('The source texture geometry attributes are unavailable.');gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,16,0);gl.enableVertexAttribArray(coordinates);gl.vertexAttribPointer(coordinates,2,gl.FLOAT,false,16,8);gl.uniform1i(gl.getUniformLocation(program,'picture'),0);gl.disable(gl.BLEND);gl.disable(gl.DEPTH_TEST);gl.disable(gl.DITHER);this.gl=gl;this.program=program;this.buffer=buffer;this.gpuError=null;return true;
   }catch(error){try{if(vertex)gl.deleteShader(vertex);if(fragment)gl.deleteShader(fragment);if(buffer)gl.deleteBuffer(buffer);if(program)gl.deleteProgram(program);}catch(ignored){}this.gpuUnavailable=true;this.gpuError=String(error.message||error);return false;}
  }
  _gpu(entry){
   if(entry.gpuUnsupported||entry.byteSize*2>this.maxGpuBytes||!this._ensureGL())return null;const gl=this.gl;
   if(entry.width>gl.getParameter(gl.MAX_TEXTURE_SIZE)||entry.height>gl.getParameter(gl.MAX_TEXTURE_SIZE)){entry.gpuUnsupported=true;return null;}
   const surfaceBytes=entry.byteSize,needed=entry.texture?0:entry.byteSize;
   while(this.textures.size&&this.gpuBytes+needed+surfaceBytes>this.maxGpuBytes){const candidate=this.textures.values().next().value;if(candidate===entry){this.textures.delete(entry.key);this.textures.set(entry.key,entry);continue;}this._dropTexture(candidate);}
   if(this.gpuBytes+needed+surfaceBytes>this.maxGpuBytes)return null;
   try{
    if(!entry.texture){
     const texture=gl.createTexture();if(!texture)throw Error('No WebGL source texture resource.');gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,false);gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL,gl.NONE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
     try{gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,entry.canvas);if(gl.getError()!==gl.NO_ERROR)throw Error('The source texture upload failed.');}catch(error){gl.deleteTexture(texture);throw error;}
     entry.texture=texture;this.textures.set(entry.key,entry);this.gpuBytes+=entry.byteSize;this.uploads++;
    }else{this.textures.delete(entry.key);this.textures.set(entry.key,entry);}
    const canvas=this.gpuCanvas;if(canvas.width!==entry.width)canvas.width=entry.width;if(canvas.height!==entry.height)canvas.height=entry.height;this.gpuSurfaceBytes=surfaceBytes;gl.viewport(0,0,entry.width,entry.height);gl.useProgram(this.program);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,entry.texture);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);if(gl.getError()!==gl.NO_ERROR||gl.isContextLost?.())throw Error('The source texture presentation failed.');return canvas;
   }catch(error){for(const retained of [...this.textures.values()])this._dropTexture(retained);if(this.gpuCanvas){this.gpuCanvas.width=1;this.gpuCanvas.height=1;}this.gpuSurfaceBytes=0;this.gpuUnavailable=true;this.gpuError=String(error.message||error);return null;}
  }
  _get(project,asset,time){
   if(!this.enabled||this.disposed||!SourceFrameCache.eligible(project,asset))return null;const identity=this._identity(project,asset);let found=null;
   for(const entry of this.entries.values())if(entry.identity===identity){const targetNumerator=entry.origin*time.d*entry.baseN+time.n*entry.baseD,denominator=time.d*entry.baseN;if(targetNumerator>=entry.pts*denominator&&targetNumerator<entry.endPts*denominator){found=entry;break;}}
   if(!found){this.misses++;return null;}this.hits++;this.entries.delete(found.key);this.entries.set(found.key,found);return this._gpu(found)||found.canvas;
  }
  get(project,asset,seconds){try{return this._get(project,asset,decimal(seconds));}catch(error){return null;}}
  getFrame(project,asset,sourceFrame){
   try{const frame=decimal(sourceFrame),labels=[[23.976,24000],[29.97,30000],[59.94,60000]],label=labels.find(([fps])=>Math.abs(project.fps-fps)<1e-6),rate=project.frame_rate||(label?{numerator:label[1],denominator:1001}:{numerator:project.fps,denominator:1});if(!Number.isInteger(rate.numerator)||!Number.isInteger(rate.denominator)||rate.numerator<1||rate.denominator<1)return null;return this._get(project,asset,{n:frame.n*BigInt(rate.denominator),d:frame.d*BigInt(rate.numerator)});}catch(error){return null;}
  }
  stats(){return {enabled:this.enabled,entries:this.entries.size,cpuBytes:this.cpuBytes,maxCpuBytes:this.maxCpuBytes,textures:this.textures.size,textureBytes:this.gpuBytes,surfaceBytes:this.gpuSurfaceBytes,maxGpuBytes:this.maxGpuBytes,pending:Boolean(this.pending),maxPendingBytes:this.maxCpuBytes,hits:this.hits,misses:this.misses,uploads:this.uploads,textureDeletions:this.deletions,contextLosses:this.contextLosses,gpuUnavailable:this.gpuUnavailable,gpuError:this.gpuError||null,gpuResidency:'unobservable',productionMediaAccepted:false};}
  clear(){this.epoch++;this.pending?.cancel?.();for(const entry of [...this.entries.values()])this._drop(entry);if(this.gpuCanvas){this.gpuCanvas.width=1;this.gpuCanvas.height=1;}this.gpuSurfaceBytes=0;this._notify();}
  dispose(){this.clear();this.enabled=false;this.disposed=true;const gl=this.gl;try{if(this.buffer)gl.deleteBuffer(this.buffer);if(this.program)gl.deleteProgram(this.program);gl?.getExtension('WEBGL_lose_context')?.loseContext();}catch(error){}this.gpuCanvas?.removeEventListener?.('webglcontextlost',this.lost);this.gpuCanvas?.removeEventListener?.('webglcontextrestored',this.restored);this.gl=null;this.buffer=null;this.program=null;this.gpuCanvas=null;}
 }
 window.CinematicumSourceFrameCache=SourceFrameCache;
})();

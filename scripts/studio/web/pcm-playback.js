/* Lossless, bounded source PCM transport. The engine owns stream selection and
 * pitch-preserving tempo; WebAudio schedules exact stereo sample ranges here. */
(()=>{
  'use strict';
  const RATE=48000,CHUNK=48000,HORIZON=3,MAX_BYTES=128*1024*1024;
  const pools=new WeakMap(),entries=new Set(),waiters=[];
  let retainedBytes=0,activeRequests=0;
  function forget(entry){
    if(entry.disposed)return;entry.disposed=true;entry.pool.delete(entry.key);entries.delete(entry);retainedBytes-=entry.bytes;entry.buffer=null;
  }
  function reserve(bytes){
    for(const entry of entries)if(retainedBytes+bytes>MAX_BYTES&&!entry.refs.size)forget(entry);
    if(retainedBytes+bytes>MAX_BYTES)throw Error('Live audio reached its 128 MiB PCM buffer limit. Reduce simultaneous source voices or use Render preview.');
    retainedBytes+=bytes;
  }
  async function fetchRange(url,first,last,size,sha256){
    if(activeRequests>=4)await new Promise(resolve=>waiters.push(resolve));else activeRequests++;
    try{
      const etag='"'+sha256+'"',response=await fetch(url,{headers:{Range:`bytes=${first}-${last}`,'If-Match':etag},cache:'no-store',credentials:'same-origin'});
      if(response.status!==206||response.headers.get('Content-Range')!==`bytes ${first}-${last}/${size}`||response.headers.get('ETag')!==etag){await response.body?.cancel();throw Error('The source audio server did not return the verified sample byte range.');}
      const bytes=await response.arrayBuffer();if(bytes.byteLength!==last-first+1)throw Error('The source audio byte range was truncated.');return bytes;
    }finally{const next=waiters.shift();if(next)next();else activeRequests--;}
  }
  function acquire(decoder,index){
    const {context,manifest,reverse}=decoder;let pool=pools.get(context);if(!pool){pool=new Map();pools.set(context,pool);}
    const key=manifest.url+'|'+manifest.sha256+'|'+Boolean(reverse)+'|'+index;let entry=pool.get(key);
    if(entry?.error){forget(entry);entry=null;}
    if(!entry){
      const start=index*CHUNK,count=Math.min(CHUNK,manifest.frames-start),bytes=count*8;reserve(bytes);
      entry={key,pool,bytes,index,start,count,refs:new Set(),buffer:null,error:null,disposed:false};pool.set(key,entry);entries.add(entry);
      // Virtual chunks always advance; reverse voices read bounded original
      // ranges from the end and reverse stereo frames without swapping channels.
      const originalStart=reverse?manifest.frames-start-count:start;
      const first=manifest.data_offset+originalStart*8;
      entry.promise=fetchRange(manifest.url,first,first+bytes-1,manifest.byte_size,manifest.sha256).then(raw=>{
        if(entry.disposed)return;
        const view=new DataView(raw),buffer=context.createBuffer(2,count,RATE),left=buffer.getChannelData(0),right=buffer.getChannelData(1);
        for(let i=0;i<count;i++){
          const sample=reverse?count-1-i:i;
          const l=view.getFloat32(sample*8,true),r=view.getFloat32(sample*8+4,true);
          if(!Number.isFinite(l)||!Number.isFinite(r))throw Error('The original source contains non-finite audio samples.');
          left[i]=l;right[i]=r;
        }
        entry.buffer=buffer;
      }).catch(error=>{entry.error=String(error.message||error);});
    }else{entries.delete(entry);entries.add(entry);}
    entry.refs.add(decoder);return entry;
  }
  class Decoder{
    constructor(){
      this.listeners=new Map();this.chunks=new Map();this.nodes=new Set();this.context=null;this.output=null;this.manifest=null;this.reverse=false;
      this.paused=true;this.seeking=false;this.ended=false;this.readyState=0;this.networkState=0;this.error=null;
      this.volume=1;this.muted=false;this.playbackRate=1;this.preservesPitch=true;this.crossOrigin='anonymous';this.isConnected=false;
      this._position=0;this._anchor=0;this._when=0;this._scheduled=0;this._timer=null;this._generation=0;this._ranges=[];this._rangeStart=0;
      this.pcmState={kind:'scheduled-source-pcm',range_requests:0,scheduled_chunks:0,underruns:0};
    }
    addEventListener(type,fn){if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(fn);}
    removeEventListener(type,fn){this.listeners.get(type)?.delete(fn);}
    emit(type){for(const fn of [...(this.listeners.get(type)||[])])fn({type,target:this});}
    get src(){return this.manifest?.url||'';}
    get currentSrc(){return this.manifest?(typeof location!=='undefined'?new URL(this.manifest.url,location.href).href:this.manifest.url):'';}
    get duration(){return this.manifest?this.manifest.duration*this.manifest.source_time_scale:NaN;}
    frame(){
      if(this.paused||!this.context)return this._position;
      return Math.max(this._anchor,Math.min(this.manifest.frames,this._scheduled,this._anchor+(this.context.currentTime-this._when)*RATE));
    }
    get currentTime(){
      const elapsed=this.frame()/RATE*(this.manifest?.source_time_scale||1);
      return this.reverse?this.duration-elapsed:elapsed;
    }
    positionFor(value){
      const frame=Math.round(Math.max(0,Math.min(this.duration,value))/this.manifest.source_time_scale*RATE);
      return this.reverse?this.manifest.frames-frame:frame;
    }
    set currentTime(value){
      if(!this.manifest||!Number.isFinite(value))return;
      const target=this.positionFor(value);
      if(target===Math.round(this.frame()))return;
      this.pause();this._position=target;this.ended=target>=this.manifest.frames;this.seeking=true;this.readyState=1;this.emit('seeking');this.update();
    }
    get played(){
      const ranges=this._ranges.map(range=>range.slice()),end=this.currentTime;
      if(!this.paused&&end!==this._rangeStart)ranges.push([Math.min(this._rangeStart,end),Math.max(this._rangeStart,end)]);
      const merged=[];for(const range of ranges.sort((a,b)=>a[0]-b[0])){const last=merged.at(-1);if(last&&range[0]<=last[1]+1/RATE)last[1]=Math.max(last[1],range[1]);else merged.push(range);}
      return {length:merged.length,start:index=>merged[index][0],end:index=>merged[index][1]};
    }
    loadSource(context,output,manifest,sourceTime=0,{reverse=false}={}){
      this.clear();this.context=context;this.output=output;this.manifest=manifest;this.reverse=Boolean(reverse);this.networkState=2;this.readyState=1;
      this._position=this.positionFor(sourceTime);this.ended=this._position>=manifest.frames;
      this.emit('loadedmetadata');this.update();
    }
    fail(message){
      if(this.error)return;this.pause();this.error={message};this.readyState=0;this.networkState=3;this.emit('error');
    }
    update(){
      if(!this.manifest||this.error)return;
      const frame=this.frame(),first=Math.floor(frame/CHUNK),last=Math.min(Math.ceil(this.manifest.frames/CHUNK)-1,Math.ceil((frame+HORIZON*RATE)/CHUNK)-1),needed=new Set();
      try{
        for(let index=first;index<=last;index++){
          needed.add(index);if(this.chunks.has(index))continue;
          const entry=acquire(this,index);this.chunks.set(index,entry);this.pcmState.range_requests++;
          const generation=this._generation;
          entry.promise.then(()=>{if(generation===this._generation&&this.manifest){this.readiness();if(!this.paused)this.schedule();}});
        }
        for(const [index,entry]of this.chunks)if(!needed.has(index)){entry.refs.delete(this);this.chunks.delete(index);}
        this.readiness();
      }catch(error){this.fail(String(error.message||error));}
    }
    readiness(){
      if(!this.manifest||this.error)return;
      for(const entry of this.chunks.values())if(entry.error){this.fail(entry.error);return;}
      const frame=this.frame();let end=frame;
      while(end<this.manifest.frames){const entry=this.chunks.get(Math.floor(end/CHUNK));if(!entry?.buffer)break;end=Math.min(this.manifest.frames,entry.start+entry.count);}
      const enough=end-frame>=Math.min(this.manifest.frames-frame,(this.paused?HORIZON:.1)*RATE)-1;
      if(enough){
        const changed=this.readyState<2;this.readyState=4;this.networkState=1;
        if(this.seeking){this.seeking=false;this.emit('seeked');}
        if(changed){this.emit('loadeddata');this.emit('canplay');}
      }else if(this.paused||end-frame<.1*RATE){
        const changed=this.readyState>=2;this.readyState=1;this.networkState=2;if(changed)this.emit('waiting');
      }
    }
    schedule(){
      if(this.paused||!this.manifest||this.error)return;
      const frame=this.frame();
      for(const node of [...this.nodes])if(node._end<=frame){try{node.disconnect();}catch(error){}this.nodes.delete(node);}
      while(this._scheduled<this.manifest.frames){
        const index=Math.floor(this._scheduled/CHUNK),entry=this.chunks.get(index);if(!entry?.buffer)break;
        const start=this._scheduled,end=entry.start+entry.count,when=this._when+(start-this._anchor)/RATE,offset=(start-entry.start)/RATE;
        // A range can arrive after its playback boundary but before tick()'s
        // next timer. WebAudio starts a past timestamp immediately; allowing
        // that would shift the decoded samples while our source clock keeps
        // advancing. Freeze at the last scheduled sample and explicitly
        // rebuffer, exactly as for a timer-detected underrun.
        if(when<this.context.currentTime-1/RATE){
          this.pcmState.underruns++;this.pause();this.readyState=1;this.emit('waiting');this.update();return;
        }
        const source=this.context.createBufferSource();source.buffer=entry.buffer;source.connect(this.output);
        source._end=end;this.nodes.add(source);source.onended=()=>{source.disconnect();this.nodes.delete(source);};
        source.start(when,offset,(end-start)/RATE);this._scheduled=end;this.pcmState.scheduled_chunks++;
      }
    }
    async play(){
      if(!this.paused||!this.manifest||this.ended)return;
      if(this.error||this.readyState<2)throw Error(this.error?.message||'Source audio is not ready.');
      this.paused=false;this._anchor=this._position;this._scheduled=this._position;
      this._when=Math.ceil((this.context.currentTime+.02)*this.context.sampleRate)/this.context.sampleRate;
      this._rangeStart=this.currentTime;this.schedule();this.emit('play');this.tick();
    }
    tick(){
      if(this.paused)return;
      const actual=this._anchor+Math.max(0,this.context.currentTime-this._when)*RATE;
      if(actual>=this.manifest.frames){this.pause();this._position=this.manifest.frames;this.ended=true;this.emit('ended');return;}
      if(actual>this._scheduled+1){
        this.pcmState.underruns++;this.pause();this.readyState=1;this.emit('waiting');this.update();return;
      }
      this.update();if(!this.paused){this.schedule();this._timer=setTimeout(()=>{this._timer=null;this.tick();},50);}
    }
    pause(){
      if(this.paused)return;
      const end=this.currentTime;this._position=Math.round(this.frame());this.paused=true;
      if(end!==this._rangeStart)this._ranges.push([Math.min(this._rangeStart,end),Math.max(this._rangeStart,end)]);
      if(this._timer!==null)clearTimeout(this._timer);this._timer=null;
      for(const node of this.nodes){node.onended=null;try{node.stop();node.disconnect();}catch(error){}}this.nodes.clear();this.emit('pause');
    }
    clear(){
      this.pause();this._generation++;
      for(const entry of this.chunks.values())entry.refs.delete(this);this.chunks.clear();
      this.manifest=null;this.reverse=false;this._position=0;this._ranges=[];this.ended=false;this.seeking=false;this.error=null;this.readyState=0;this.networkState=0;
    }
    removeAttribute(name){if(name==='src')this.clear();}
    load(){}
  }
  window.CinematicumPCMPlayback={createDecoder:()=>new Decoder()};
})();

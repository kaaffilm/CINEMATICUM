/* Owned source-audio playback. Original bytes select the stream/channel pair on
 * the engine; one lossless stereo source feeds live authored gain and pan here.
 * Browser AudioTrack ordering and selection are deliberately not involved.
 */
(()=>{
  'use strict';
  const routes=new WeakMap(),liveRoutes=new Set(),cache=new Map(),cacheLimit=128;
  const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  let service=null;
  function configure(value){
    if(!value||typeof value.request!=='function'||typeof value.getProject!=='function')throw Error('Source audio needs the local project service.');
    service=value;
  }
  function sourceChoice(clip,asset,playbackRate){
    const project=service?.getProject(),streams=Array.isArray(asset.audio_streams)&&asset.audio_streams.length?asset.audio_streams:
      asset.has_audio?[{index:asset.audio_stream_index,channels:asset.audio_channels}]:[];
    const index=clip.audio?.stream_index??asset.audio_stream_index,stream=streams.find(item=>item.index===index);
    if(!project?.id||!asset.id||!hash(asset.sha256))return {error:'This source lacks a verified media identity. Reopen the project before playing its audio.'};
    if(!stream)return {error:'The selected source audio stream is missing from the inspected media.'};
    const channels=stream.channels,map=clip.audio?.channels??null;
    if(!Number.isInteger(index)||index<0||!Number.isInteger(channels)||channels<1||channels>32)return {error:'Live audio supports inspected source streams with 1–32 channels. Use a rendered preview for this source.'};
    if(map!==null&&(!Array.isArray(map)||map.length!==2||map.some(value=>!Number.isInteger(value)||value<0||value>=channels)))return {error:'The selected source channel mapping is outside this audio stream.'};
    if(!Number.isFinite(playbackRate)||playbackRate<.01||playbackRate>64)return {error:'Live source audio supports combined speeds from 0.01 to 64. Use Render preview for this nested retime.'};
    const result={projectId:project.id,assetId:asset.id,sha256:asset.sha256,index,channels,map:map?.slice()??null,duration:asset.duration,playbackRate};
    result.key=JSON.stringify([result.projectId,result.assetId,result.sha256,index,result.map,playbackRate]);
    return result;
  }
  function validateManifest(value,choice){
    const prefix='/api/projects/'+encodeURIComponent(choice.projectId)+'/audio-source/';
    if(!value||value.state!=='ready'||value.asset_id!==choice.assetId||value.source_sha256!==choice.sha256||
       value.stream_index!==choice.index||JSON.stringify(value.channels)!==JSON.stringify(choice.map)||
       value.rate!==48000||value.output_channels!==2||value.codec!=='pcm_f32le'||
       value.version!==2||value.playback_rate!==choice.playbackRate||value.source_time_scale!==choice.playbackRate||value.data_offset!==58||value.frame_bytes!==8||
       !hash(value.cache_key)||!hash(value.sha256)||value.url!==prefix+value.cache_key||
       !Number.isSafeInteger(value.frames)||value.frames<1||!Number.isSafeInteger(value.byte_size)||value.byte_size!==value.frames*8+value.data_offset||
       !Number.isSafeInteger(value.source_frames)||value.source_frames<1||!Number.isSafeInteger(value.padded_frames)||value.padded_frames<0||
       value.source_frames+value.padded_frames!==value.frames||!Number.isFinite(value.duration)||Math.abs(value.duration-value.frames/48000)>1/48000||
       (Number.isFinite(choice.duration)&&(value.duration+1/48000)*choice.playbackRate<choice.duration)){
      throw Error('The decoded audio did not match the source identity, selected channels, or lossless playback format.');
    }
    return Object.freeze({...value,channels:value.channels?.slice()??null});
  }
  function disconnect(node){try{node?.disconnect();}catch(error){}}
  function status(route,state,message='',details={}){
    const {media}=route,value={state,ready:state==='ready',message,...details};media.audioRoute=value;
    if(media.audioGate&&media.audioGate.gain.value!==(value.ready?1:0))media.audioGate.gain.value=value.ready?1:0;
    // Once connected, graph gain gates silence. Muting the native decoder can
    // reconfigure its source provider, so its own gain remains at unity.
    const muted=media.source?false:!value.ready;
    if(media.el.muted!==muted)media.el.muted=muted;
    if(state==='unsupported'){
      const key=(route.choice?.key||'')+'|'+message;
      if(route.warning!==key){route.warning=key;route.notify?.(message,true,9000);}
    }
    return value;
  }
  function trimCache(){
    for(const [key,entry]of cache){if(cache.size<=cacheLimit)break;if(!entry.consumers.size&&!entry.busy)cache.delete(key);}
  }
  function detach(route){
    const entry=route.entry;if(!entry)return;entry.consumers.delete(route);route.entry=null;
    if(!entry.consumers.size&&entry.wake){clearTimeout(entry.timer);entry.wake();}
    trimCache();
  }
  function notifyEntry(entry){for(const route of [...entry.consumers])if(!route.disposed&&route.entry===entry)refresh(route);}
  async function run(entry){
    if(entry.busy||entry.state==='ready'||entry.state==='failed')return;
    entry.busy=true;
    try{
      while(entry.consumers.size&&entry.state==='pending'){
        let value=entry.jobId?await entry.request('/api/jobs/'+encodeURIComponent(entry.jobId)):
          await entry.request('/api/projects/'+encodeURIComponent(entry.choice.projectId)+'/audio-source',{
            method:'POST',body:{asset_id:entry.choice.assetId,stream_index:entry.choice.index,channels:entry.choice.map,playback_rate:entry.choice.playbackRate}});
        const job=value?.job||value;
        if(value?.state==='ready'||job?.state==='completed'){
          // Equal imported bytes can share an engine job. Ask the ready cache
          // once for this asset's receipt, without starting another decode.
          if(job?.state==='completed'&&job.result?.source_sha256===entry.choice.sha256&&job.result?.asset_id!==entry.choice.assetId){
            value=await entry.request('/api/projects/'+encodeURIComponent(entry.choice.projectId)+'/audio-source',{
              method:'POST',body:{asset_id:entry.choice.assetId,stream_index:entry.choice.index,channels:entry.choice.map,playback_rate:entry.choice.playbackRate}});
            if(value?.state!=='ready')throw Error('The shared decoded audio did not publish this source receipt.');
          }
          entry.manifest=validateManifest(value?.state==='ready'?value:job.result,entry.choice);entry.state='ready';notifyEntry(entry);break;
        }
        if(job?.state==='failed'||job?.state==='cancelled')throw Error(job.error||job.message||'Source audio preparation did not complete.');
        if(!job||!['queued','running'].includes(job.state)||typeof job.id!=='string'||!job.id||job.id.length>128)throw Error('The local audio service returned an invalid preparation job.');
        if(entry.jobId&&entry.jobId!==job.id)throw Error('The source audio preparation job changed identity.');
        entry.jobId=job.id;entry.message=typeof job.message==='string'?job.message:'Decoding selected source audio.';notifyEntry(entry);
        if(entry.consumers.size)await new Promise(resolve=>{
          entry.wake=()=>{entry.wake=null;entry.timer=null;resolve();};entry.timer=setTimeout(entry.wake,150);
        });
      }
    }catch(error){entry.state='failed';entry.error=String(error.message||error);notifyEntry(entry);}
    finally{entry.busy=false;trimCache();}
  }
  function attach(route){
    const choice=route.choice;
    if(route.entry?.choice.key===choice.key)return;
    detach(route);let entry=cache.get(choice.key);
    if(!entry){entry={choice,request:service.request,state:'pending',consumers:new Set(),busy:false,jobId:null,manifest:null};cache.set(choice.key,entry);}
    else{cache.delete(choice.key);cache.set(choice.key,entry);}
    entry.consumers.add(route);route.entry=entry;void run(entry);trimCache();
  }
  function connectGraph(route){
    const {media,context}=route;if(media.source)return;
    media.el.pause?.();if(media.el.volume!==1)media.el.volume=1;if(media.el.muted)media.el.muted=false;
    media.source=context.createGain();media.source.channelCount=2;media.source.channelCountMode='explicit';media.source.channelInterpretation='discrete';
    media.left=context.createGain();media.right=context.createGain();media.merge=context.createChannelMerger(2);
    media.gain=context.createGain();media.audioGate=context.createGain();media.audioGate.gain.value=0;media.stereo=null;
    media.split=context.createChannelSplitter(2);media.split.channelCount=2;media.split.channelCountMode='explicit';media.split.channelInterpretation='discrete';
    // The source decoder has already selected and ordered the requested pair.
    // A second pan or downmix here would change the authored source samples.
    media.source.connect(media.split);media.split.connect(media.left,0);media.split.connect(media.right,1);
    media.left.connect(media.merge,0,0);media.right.connect(media.merge,0,1);
    media.merge.connect(media.gain);media.gain.connect(media.audioGate);media.audioGate.connect(context.destination);
  }
  function clearDecoderTimer(route){if(route.decoderTimer!=null)clearTimeout(route.decoderTimer);route.decoderTimer=null;}
  function details(route){
    const manifest=route.manifest;
    return {binding:'decoded-source-pcm',stream_index:route.choice.index,channels:route.choice.channels,channel_map:route.choice.map,playback_rate:route.choice.playbackRate,
      source_sha256:manifest.source_sha256,sha256:manifest.sha256,cache_key:manifest.cache_key,url:manifest.url,manifest};
  }
  function refresh(route){
    const {media,choice}=route;if(route.disposed)return media.audioRoute;
    if(choice.error)return status(route,'unsupported',choice.error);
    if(route.error)return status(route,'unsupported',route.error);
    const entry=route.entry;
    if(entry?.state==='failed')return status(route,'unsupported','Source audio preparation failed: '+entry.error+' Audio is muted; use Render preview.');
    if(!route.manifest&&entry?.state==='ready')route.manifest=entry.manifest;
    if(!route.manifest)return status(route,'pending',entry?.message||'Preparing verified source audio.');
    try{
      const manifest=route.manifest;
      if(route.loadedKey!==manifest.cache_key){
        connectGraph(route);status(route,'pending','Loading decoded source audio.');
        media.el.pause?.();media.audioSyncKey=null;route.loadedKey=manifest.cache_key;media.url=manifest.url;
        clearDecoderTimer(route);route.decoderTimer=setTimeout(()=>{
          route.decoderTimer=null;if(!route.disposed&&media.el.readyState<2){route.error='The decoded source audio did not load. Audio is muted; use Render preview.';refresh(route);}
        },10000);
        if(typeof media.el.loadSource!=='function')throw Error('The owned PCM transport is unavailable.');
        media.el.loadSource(route.context,media.source,manifest,route.sourceTime);
      }
      if(media.el.error)throw Error(media.el.error.message||'The lossless audio decoder failed.');
      if(media.el.readyState<2||media.el.seeking)return status(route,'pending','Loading decoded source audio.',details(route));
      clearDecoderTimer(route);return status(route,'ready','',details(route));
    }catch(error){route.error='Live source audio failed: '+String(error.message||error)+' Audio is muted; use Render preview.';return status(route,'unsupported',route.error);}
  }
  function ensure(media,context,clip,asset,notify,{prepare=true,playbackRate=clip.speed??1,sourceTime=0}={}){
    if(!media||media.kind==='image'||!asset.has_audio)return {state:'silent',ready:false,message:''};
    if(!context)return {state:'pending',ready:false,message:'Start playback to enable source audio.'};
    let route=routes.get(media.el);
    if(route&&route.context!==context)return status(route,'unsupported','The source belongs to another audio context. Reopen the project before playing audio.');
    const choice=sourceChoice(clip,asset,playbackRate);
    if(!route){
      route={media,context,choice,notify,prepare:false,listeners:[],disposed:false,entry:null,manifest:null,loadedKey:null,decoderTimer:null};
      routes.set(media.el,route);liveRoutes.add(route);
      for(const event of ['loadedmetadata','loadeddata','canplay','seeked','error']){
        const handler=()=>{if(!route.disposed)refresh(route);};media.el.addEventListener?.(event,handler);route.listeners.push([event,handler]);
      }
    }
    if(route.disposed)return {state:'unsupported',ready:false,message:'The source audio decoder has been released.'};
    route.notify=notify;route.sourceTime=sourceTime;
    if(route.choice.key!==choice.key||route.choice.error!==choice.error){
      detach(route);clearDecoderTimer(route);route.manifest=null;route.loadedKey=null;route.error=null;media.audioSyncKey=null;
      media.el.pause?.();if(media.audioGate)media.audioGate.gain.value=0;
    }
    if(prepare&&!route.prepare){
      const previous=cache.get(choice.key);
      if(previous?.state==='failed'&&!previous.consumers.size)cache.delete(choice.key);
      if(route.error){route.error=null;route.loadedKey=null;}
    }
    route.choice=choice;route.prepare=prepare;
    if(prepare&&!choice.error&&!route.manifest)attach(route);
    else if(!prepare&&route.entry?.state!=='ready')detach(route);
    return refresh(route);
  }
  function suspend(){
    for(const route of liveRoutes){route.prepare=false;if(route.entry?.state!=='ready')detach(route);}
  }
  function release(media){
    const route=media?.el&&routes.get(media.el);if(!route)return;
    route.disposed=true;detach(route);clearDecoderTimer(route);liveRoutes.delete(route);
    for(const [event,listener]of route.listeners)media.el.removeEventListener?.(event,listener);
    route.listeners=[];for(const key of ['source','gain','left','right','split','merge','stereo','audioGate'])disconnect(media[key]);
    if(media.audioGate)media.audioGate.gain.value=0;media.el.muted=true;media.el.clear?.();
  }
  window.CinematicumAudioRouting={configure,ensure,suspend,release,requiresOriginal:clip=>clip?.audio?.stream_index!=null||clip?.audio?.channels!=null};
})();

// Native UI operations plus observation of the real application's WebAudio output.
// AUDIO_ROUTING_TEST contains only synthetic fixture IDs supplied by this harness.
return await(async()=>{
 const $=selector=>document.querySelector(selector),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),steps=[],metrics={};
 const captures=[],sources=new WeakMap(),eventSources=new WeakSet(),eventListeners=[];let originalEnsure=null,routing=null,currentRoute=null,workletLoading=null,workletReady=false,phase='baseline';
 async function until(fn,message,timeout=3000){const end=performance.now()+timeout;while(performance.now()<end){if(fn())return;await sleep(25);}throw Error(message+'; '+($('#toast')?.textContent||'')+'; '+(currentRoute?.message||''));}
 function reach(selector){const el=$(selector);if(!el)throw Error('Missing '+selector);for(let parent=el.parentElement;parent;parent=parent.parentElement){if(!parent.matches('.timeline-scroll,.timeline-tools,.inspector,dialog'))continue;const r=el.getBoundingClientRect(),b=parent.getBoundingClientRect();if(r.top<b.top+3)parent.scrollTop+=r.top-b.top-3;else if(r.bottom>b.top+parent.clientHeight-3)parent.scrollTop+=r.bottom-b.top-parent.clientHeight+3;if(r.left<b.left+3)parent.scrollLeft+=r.left-b.left-3;else if(r.right>b.left+parent.clientWidth-3)parent.scrollLeft+=r.right-b.left-parent.clientWidth+3;}const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(r.width<2||r.height<2||r.top<0||r.bottom>innerHeight+.5||(hit!==el&&!el.contains(hit)))throw Error('Unreachable '+selector);return el;}
 function click(selector){const el=reach(selector);if(el.disabled)throw Error('Disabled '+selector);el.click();}
 function set(selector,value,event='input'){const el=reach(selector);el.value=String(value);el.dispatchEvent(new Event(event,{bubbles:true}));}
 const frequencies=[220,330,440,660,990,997];
 function measured(values,rate){
  const count=values[0].length,stats={sum:[0,0],squares:[0,0],min:[1,1],max:[-1,-1],tones:frequencies.map(()=>({cos:[0,0],sin:[0,0]}))};
  for(let i=0;i<count;i++){
   for(let channel=0;channel<2;channel++){const value=values[channel][i];stats.sum[channel]+=value;stats.squares[channel]+=value*value;stats.min[channel]=Math.min(stats.min[channel],value);stats.max[channel]=Math.max(stats.max[channel],value);}
   for(let frequency=0;frequency<frequencies.length;frequency++){const phase=2*Math.PI*frequencies[frequency]*i/rate,cos=Math.cos(phase),sin=Math.sin(phase);for(let channel=0;channel<2;channel++){stats.tones[frequency].cos[channel]+=values[channel][i]*cos;stats.tones[frequency].sin[channel]+=values[channel][i]*sin;}}
  }
  return {samples:count,left:stats.sum[0]/count,right:stats.sum[1]/count,rms:stats.squares.map(value=>Math.sqrt(value/count)),min:stats.min,max:stats.max,sample_rate:rate,amplitudes:Object.fromEntries(frequencies.map((frequency,i)=>[frequency,stats.tones[i].cos.map((value,channel)=>2*Math.hypot(value,stats.tones[i].sin[channel])/count)]))};
 }
 function observe(media,context,result){
  currentRoute=result;metrics.last_route=result;
  if(!eventSources.has(media.el)){
   eventSources.add(media.el);metrics.media_events??=[];
   for(const type of ['seeking','seeked','ratechange','volumechange','play','pause','waiting','stalled']){
    const listener=()=>{if(metrics.media_events.length<100)metrics.media_events.push({type,phase,media_time:media.el.currentTime,context_time:context.currentTime,paused:media.el.paused,seeking:media.el.seeking,rate:media.el.playbackRate});};
    media.el.addEventListener(type,listener);eventListeners.push([media.el,type,listener]);
   }
  }
  if(!workletReady){
   if(!context.audioWorklet){metrics.worklet_error='AudioWorklet is unavailable in this native runtime';return;}
   if(!workletLoading)workletLoading=context.audioWorklet.addModule('/ENGINE_TEST_audio_probe_worklet.js').then(()=>{workletReady=true;}).catch(error=>{metrics.worklet_error=String(error);});
   return;
  }
  if(!media.audioGate)return;
  let capture=captures.find(item=>item.media===media);
  if(!capture){
   if(sources.has(media.el)&&sources.get(media.el)!==media.source)throw Error('A media element acquired a second MediaElementSource');sources.set(media.el,media.source);
   const processor=new AudioWorkletNode(context,'cinematicum-audio-probe',{numberOfInputs:3,numberOfOutputs:1,outputChannelCount:[2],channelCount:2,channelCountMode:'explicit',channelInterpretation:'speakers'}),oscillator=context.createOscillator(),gain=context.createGain();
   oscillator.frequency.value=997;gain.gain.value=.25;oscillator.connect(gain);gain.connect(processor,0,2);
   media.source.connect(processor,0,0);media.audioGate.connect(processor,0,1);processor.connect(context.destination);oscillator.start();
   capture={processor,oscillator,gain,media,context,armed:false,result:null,phase,playStartedAt:null};captures.push(capture);
   processor.port.onmessage=event=>{capture.result=event.data;};
  }
  if(capture.phase!==phase){capture.phase=phase;capture.armed=false;capture.result=null;capture.playStartedAt=null;}
  if(!media.el.paused&&capture.playStartedAt===null)capture.playStartedAt=context.currentTime;
  if(!capture.armed&&!media.el.paused&&media.el.readyState>=2&&media.el.currentTime>=1.2&&media.audioRoute?.ready&&context.state==='running'&&context.currentTime>=1.5){
   capture.armed=true;capture.processor.port.postMessage({action:'capture',start_frame:Math.ceil(context.currentTime*context.sampleRate)+2048,sample_count:32768});
  }
 }
 function selectClip(){
  const clip=reach('.timeline-clip[data-type="clip"]'),bounds=clip.getBoundingClientRect(),pointer={bubbles:true,button:0,pointerId:91,isPrimary:true,clientX:bounds.left+18,clientY:bounds.top+bounds.height/2};
  clip.dispatchEvent(new PointerEvent('pointerdown',pointer));window.dispatchEvent(new PointerEvent('pointerup',pointer));
 }
 async function capturePhase(){
  await until(()=>captures.some(capture=>capture.phase===phase&&capture.result),'Actual routed stereo PCM was not captured',5000);
  const capture=captures.find(item=>item.phase===phase&&item.result),media=capture.media,result={};
  result.pcm=measured(capture.result.samples[1],capture.result.sample_rate);
  result.raw_source_pcm=measured(capture.result.samples[0],capture.result.sample_rate);
  result.measurement_calibration=measured(capture.result.samples[2],capture.result.sample_rate);
  result.capture_window={start_frame:capture.result.start_frame,end_frame:capture.result.end_frame,requested_start_frame:capture.result.requested_start_frame,sample_rate:capture.result.sample_rate,render_thread:true};
  result.element={volume:media.el.volume,muted:media.el.muted,paused:media.el.paused,seeking:media.el.seeking,current_time:media.el.currentTime,duration:media.el.duration,ready_state:media.el.readyState,network_state:media.el.networkState,playback_rate:media.el.playbackRate,connected:media.el.isConnected,cross_origin:media.el.crossOrigin,played:Array.from({length:media.el.played.length},(_,i)=>[media.el.played.start(i),media.el.played.end(i)]),error:media.el.error?.message||null};
  result.graph={gain:media.gain.gain.value,left:media.left.gain.value,right:media.right.gain.value,gate:media.audioGate.gain.value,split_outputs:media.split.numberOfOutputs,stereo:media.stereo?.gain.value??null,source_channel_count:media.source.channelCount,source_interpretation:media.source.channelInterpretation};
  result.audio_context={state:capture.context.state,time:capture.context.currentTime,sample_rate:capture.context.sampleRate};
  result.decoder={...media.el.pcmState};
  result.source_url=media.url;result.original_request_url=media.requestUrl;result.current_src=media.el.currentSrc;result.route=media.audioRoute;
  result.steady_seeks=(metrics.media_events||[]).filter(event=>event.phase===phase&&event.type==='seeking'&&event.context_time>capture.playStartedAt+.25).length;
  if($('#play-button').getAttribute('aria-label')==='Pause timeline')click('#play-button');
  return result;
 }
 function assertPCM(result,scales){
  const manifest=result.route?.manifest;
  if(!manifest||result.source_url!==manifest.url||new URL(result.current_src,location.href).pathname!==manifest.url||
     !result.original_request_url.endsWith('/media/'+AUDIO_ROUTING_TEST.asset_id)||
     manifest.asset_id!==AUDIO_ROUTING_TEST.asset_id||manifest.source_sha256!==AUDIO_ROUTING_TEST.source_sha256||
     manifest.rate!==48000||manifest.output_channels!==2||manifest.codec!=='pcm_f32le')throw Error('Live audio did not use its verified lossless original-source derivative');
  if(result.route?.binding!==AUDIO_ROUTING_TEST.binding||result.route.stream_index!==AUDIO_ROUTING_TEST.stream_index||result.route.channel_map?.join(',')!=='1,0')throw Error('The selected source identity or channel route was not applied');
  if(result.decoder.kind!=='scheduled-source-pcm'||!result.decoder.scheduled_chunks||result.decoder.underruns)throw Error('Live source PCM did not use uninterrupted owned sample scheduling');
  if(result.steady_seeks)throw Error('Steady playback repeatedly sought the audio decoder');
  if(Math.abs(result.measurement_calibration.amplitudes[997][0]-.25)>.005)throw Error('The independent WebAudio observation calibration failed');
  const oracle=AUDIO_ROUTING_TEST.oracle,[leftFrequency,rightFrequency]=AUDIO_ROUTING_TEST.frequencies;
  if([0,1].some(channel=>Math.abs(result.pcm.rms[channel]-oracle.rms[channel]*scales[channel])>.005)||[220,330,440,660].some(frequency=>[0,1].some(channel=>Math.abs(result.pcm.amplitudes[frequency][channel]-oracle.amplitudes[frequency][channel]*scales[channel])>.005)))throw Error('Live WebAudio amplitudes/RMS do not match independently decoded source PCM and authored gain/pan');
  if(frequencies.filter(frequency=>frequency!==leftFrequency&&frequency!==rightFrequency).some(frequency=>result.pcm.amplitudes[frequency].some(value=>value>.015))||result.pcm.amplitudes[rightFrequency][0]>.015||result.pcm.amplitudes[leftFrequency][1]>.015)throw Error('The live route includes the wrong stream or unswapped channels');
  if([0,1].some(channel=>Math.abs(result.raw_source_pcm.rms[channel]-oracle.rms[channel])>.005)||[220,330,440,660].some(frequency=>[0,1].some(channel=>Math.abs(result.raw_source_pcm.amplitudes[frequency][channel]-oracle.amplitudes[frequency][channel])>.005)))throw Error('Raw source PCM does not contain the independently selected original channel pair');
 }
 async function sequenceScenario(){
  const report={passed:false,scenario:AUDIO_ROUTING_TEST.scenario,steps:[],metrics:{runs:[]}},voices=new Map();
  let original=null,processor=null,oscillator=null,calibrationGain=null,context=null,loading=null,ready=false,captured=null,armed=false,runStart=0;
  const expected=new Map(AUDIO_ROUTING_TEST.routes.map(route=>[route.clip_id,route]));
  function attach(){
   if(!ready)return;
   if(!processor){
    processor=new AudioWorkletNode(context,'cinematicum-audio-probe',{numberOfInputs:3,numberOfOutputs:1,outputChannelCount:[2],channelCount:2,channelCountMode:'explicit',channelInterpretation:'speakers'});
    processor.port.onmessage=event=>{captured=event.data;};processor.connect(context.destination);
    oscillator=context.createOscillator();calibrationGain=context.createGain();oscillator.frequency.value=997;calibrationGain.gain.value=.25;
    oscillator.connect(calibrationGain);calibrationGain.connect(processor,0,2);oscillator.start();
   }
   for(const voice of voices.values())if(!voice.connected&&voice.media.source&&voice.media.audioGate){
    voice.media.source.connect(processor,0,0);voice.media.audioGate.connect(processor,0,1);voice.connected=true;
   }
  }
  function matches(actual,oracle){
   return actual.samples>=32768&&[0,1].every(channel=>Math.abs(actual.rms[channel]-oracle.rms[channel])<.005)&&
    [220,330,440,660,990].every(frequency=>[0,1].every(channel=>Math.abs(actual.amplitudes[frequency][channel]-(oracle.amplitudes[frequency]?.[channel]||0))<.005));
  }
  try{
   await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&window.CinematicumAudioRouting,'Sequence audio fixture did not bootstrap',4000);
   const api=window.CinematicumAudioRouting;original=api.ensure;
   api.ensure=function(media,audioContext,clip,asset,notify,options){
    const result=original.call(this,media,audioContext,clip,asset,notify,options),spec=expected.get(clip.id);
    if(!spec||!audioContext)return result;
    context=audioContext;let voice=voices.get(clip.id);
    if(voice&&voice.media!==media){
     if(!voice.media.el.paused||voice.media.el.pcmState?.scheduled_chunks!==0)throw Error('The same authored voice changed decoder during playback');
     if(voice.connected){voice.media.source.disconnect(processor);voice.media.audioGate.disconnect(processor);}
     voice=null;
    }
    if(!voice){voice={media,spec,route:result,connected:false,drift:0,observations:0};voices.set(clip.id,voice);}
    voice.route=result;voice.lastOptions={...options};voice.lastIdentity={disposed:media.disposed,request_url:media.requestUrl,owner:media.ownerClipId,nested:media.nested};
    if(!loading)loading=context.audioWorklet.addModule('/ENGINE_TEST_audio_probe_worklet.js').then(()=>{ready=true;attach();});
    attach();
    if(result.ready&&!media.el.paused&&context.currentTime>runStart+.5){
     voice.drift=Math.max(voice.drift,Math.abs(media.el.currentTime-options.sourceTime));voice.observations++;
     if(voice.firstSourceTime==null)voice.firstSourceTime=media.el.currentTime;voice.lastSourceTime=media.el.currentTime;
    }
    return result;
   };
   for(let iteration=0;iteration<AUDIO_ROUTING_TEST.repetitions;iteration++){
    captured=null;armed=false;for(const voice of voices.values()){voice.drift=0;voice.observations=0;voice.firstSourceTime=null;voice.lastSourceTime=null;}
    click('#jump-start');runStart=context?.currentTime||0;click('#play-button');
    await until(()=>{
     if(!processor||voices.size!==expected.size||[...voices.values()].some(voice=>!voice.connected||!voice.route?.ready||voice.media.el.paused))return false;
     const clock=window.CinematicumSequencePlayback.clock();
     if(clock?.waiting||!Number.isFinite(clock?.frame)||clock.frame<AUDIO_ROUTING_TEST.capture_frame)return false;
     if(!armed){armed=true;processor.port.postMessage({action:'capture',start_frame:Math.ceil(context.currentTime*context.sampleRate)+2048,sample_count:32768});}
     return Boolean(captured);
    },'Repeated '+AUDIO_ROUTING_TEST.scenario+' live mix was not captured',4000);
    const current={iteration:iteration+1,pcm:measured(captured.samples[1],captured.sample_rate),raw_pcm:measured(captured.samples[0],captured.sample_rate),calibration:measured(captured.samples[2],captured.sample_rate),
     window:{start_frame:captured.start_frame,end_frame:captured.end_frame,sample_rate:captured.sample_rate,render_thread:true},voices:[]};
    for(const [clipId,voice]of voices){
     const {media,spec,route}=voice,manifest=route.manifest;
     current.voices.push({clip_id:clipId,route,decoder:{...media.el.pcmState},clock_drift_seconds:voice.drift,observations:voice.observations,first_source_time:voice.firstSourceTime,last_source_time:voice.lastSourceTime,reverse:media.el.reverse,current_time:media.el.currentTime,request_url:media.requestUrl});
     if(!manifest||route.binding!=='decoded-source-pcm'||manifest.source_sha256!==AUDIO_ROUTING_TEST.source_sha256||manifest.asset_id!==AUDIO_ROUTING_TEST.asset_id||
        route.stream_index!==spec.stream_index||JSON.stringify(route.channel_map)!==JSON.stringify(spec.channels)||manifest.source_time_scale!==spec.playback_rate||manifest.playback_rate!==spec.playback_rate)throw Error('A sequence voice lost its selected-source or combined-speed identity');
     if(media.el.pcmState?.kind!=='scheduled-source-pcm'||!media.el.pcmState.scheduled_chunks||media.el.pcmState.underruns)throw Error('Repeated sequence playback underrun');
     if(Boolean(spec.reverse)!==Boolean(media.el.reverse))throw Error('A source voice lost its composed reverse direction');
     if(spec.reverse&&!(voice.lastSourceTime<voice.firstSourceTime-.02))throw Error('Reverse source time did not decrease while transport advanced');
     if(voice.observations<3||voice.drift>.08)throw Error('A sequence voice drifted from the shared timeline clock');
    }
    report.metrics.runs.push(current);
    if(Math.abs(current.calibration.amplitudes[997][0]-.25)>.005)throw Error('Live mix observation calibration failed');
    if(!matches(current.pcm,AUDIO_ROUTING_TEST.oracle))throw Error('Actual simultaneous live mix differs from independently decoded source amplitudes and authored gains');
    if(!matches(current.raw_pcm,AUDIO_ROUTING_TEST.raw_oracle))throw Error('Actual source voices differ from the independently selected pitch-preserving PCM');
    click('#play-button');await until(()=>[...voices.values()].every(voice=>voice.media.el.paused),'Pause did not stop all owned source voices');
    report.steps.push('native_'+AUDIO_ROUTING_TEST.scenario+'_pcm_restart_'+(iteration+1));
   }
   click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Sequence playback project did not save');
   report.steps.push('native_save_after_repeated_playback');report.passed=true;
  }catch(error){report.error=error.message;report.toast=$('#toast')?.textContent;report.metrics.routes=[...voices].map(([clip_id,voice])=>({clip_id,route:voice.route,decoder:{...voice.media.el.pcmState},clock_drift_seconds:voice.drift,options:voice.lastOptions,identity:voice.lastIdentity,paused:voice.media.el.paused,current_time:voice.media.el.currentTime}));report.metrics.transport={label:$('#play-button')?.getAttribute('aria-label'),clock:window.CinematicumSequencePlayback.clock()};}
  finally{
   if(original)window.CinematicumAudioRouting.ensure=original;
   if($('#play-button')?.getAttribute('aria-label')==='Pause timeline')$('#play-button').click();
   for(const voice of voices.values())if(voice.connected){try{voice.media.source.disconnect(processor);voice.media.audioGate.disconnect(processor);}catch(error){}}
   if(oscillator){oscillator.stop();oscillator.disconnect();calibrationGain.disconnect();}if(processor){processor.port.onmessage=null;processor.disconnect();}
  }
  return report;
 }
 try{
  if(AUDIO_ROUTING_TEST.scenario&&AUDIO_ROUTING_TEST.scenario!=='routing')return await sequenceScenario();
  await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&window.CinematicumAudioRouting,'Native audio fixture did not bootstrap',4000);
  routing=window.CinematicumAudioRouting;originalEnsure=routing.ensure;
  routing.ensure=function(media,context,...args){const result=originalEnsure.call(this,media,context,...args);if(context)observe(media,context,result);return result;};
  selectClip();
  click('#source-audio-button');set('[data-audio-stream]',AUDIO_ROUTING_TEST.stream_index,'change');set('[data-audio-left]',1);set('[data-audio-right]',0);click('[data-apply-audio]');
  await until(()=>$('.editorial-dialog [data-status]')?.textContent.startsWith('Applied.'),'Source audio controls did not apply');click('.editorial-heading button');steps.push('native_source_stream_and_channel_controls');
  click('#jump-start');click('#play-button');
  Object.assign(metrics,await capturePhase());assertPCM(metrics,[1,1]);
  steps.push('measured_actual_live_stream_'+AUDIO_ROUTING_TEST.stream_index+'_swapped_stereo_pcm');
  phase='gain_pan';selectClip();set('[data-field="volume"]',.5);set('[data-field="audio.pan"]',.25);click('#jump-start');click('#play-button');
  metrics.gain_pan=await capturePhase();assertPCM(metrics.gain_pan,[.375,.5]);
  if(metrics.gain_pan.route.cache_key!==metrics.route.cache_key)throw Error('Live gain and pan unexpectedly changed the source decode recipe');
  steps.push('native_gain_pan_and_explicit_restart_pcm');
  click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Mapped project did not save');steps.push('saved_mapping');
  return {passed:true,steps,metrics};
 }catch(error){return {passed:false,error:error.message,steps,metrics,toast:$('#toast')?.textContent};}
 finally{
  if(routing&&originalEnsure)routing.ensure=originalEnsure;
  for(const [element,type,listener]of eventListeners)element.removeEventListener(type,listener);
  for(const capture of captures){capture.processor.port.onmessage=null;capture.oscillator.stop();capture.oscillator.disconnect();capture.gain.disconnect();try{capture.media.audioGate.disconnect(capture.processor);capture.media.source.disconnect(capture.processor);}catch(error){}capture.processor.disconnect();}
 }
})();

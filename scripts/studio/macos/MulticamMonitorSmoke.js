// Only shipped controls author the edit. This observer taps the real output;
// its silent worklet never supplies sound to the application's transport.
const MONITOR_FIXTURE = /* ENGINE_TEST_CONFIG */ {};
return await (async () => {
  const began = performance.now(), deadline = began + 14000, steps = [], metrics = {};
  const $ = selector => document.querySelector(selector), sleep = ms => new Promise(r => setTimeout(r, ms));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b), fixture = MONITOR_FIXTURE;
  const detail = () => `; monitor=${$('[data-monitor-status]')?.textContent}; toast=${$('#toast')?.textContent}`;
  function check(value, message) {if (!value) throw Error(message + detail());}
  function control(selector) {const node = $(selector); check(node && !node.disabled, 'Unavailable ' + selector); node.scrollIntoView({block:'nearest'}); return node;}
  const click = selector => control(selector).click();
  function set(selector, value) {const node = control(selector); node.value = String(value); node.dispatchEvent(new Event('input', {bubbles:true})); node.dispatchEvent(new Event('change', {bubbles:true}));}
  async function until(fn, message, ms=2500) {const end = Math.min(deadline, performance.now()+ms); while (performance.now()<end) {if(fn())return;await sleep(20);} throw Error(message+detail());}
  async function get(url) {const r=await fetch(url);check(r.ok,'GET failed '+url);return r.json();}
  const readProject=()=>get('/api/projects/'+fixture.project_id);
  async function save(monitor=false) {click(monitor?'[data-monitor-save]':'#save-project');await until(()=>$('#save-state')?.textContent==='SAVED LOCALLY','The camera edit did not save');}
  async function selectProject(id,name) {if($('#project-select').value!==id)set('#project-select',id);await until(()=>$('#project-select').value===id&&!$('#project-select').disabled&&$('#viewer-project').textContent===name,'The exact fixture project did not open');}
  function selectClip(id) {
    const node=control(`.timeline-clip[data-clip="${id}"]`),r=node.getBoundingClientRect();
    node.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,pointerId:41,isPrimary:true,clientX:r.left+15,clientY:r.top+12}));
    window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,buttons:0,pointerId:41,isPrimary:true}));
  }
  async function openMonitor(clip) {
    selectClip(clip.id);click('#multicam-button');await until(()=>$('.editorial-dialog')?.open&&$('[data-monitor-open]'),'Camera group controls did not open');
    click('[data-monitor-open]');await until(()=>$('#multicam-monitor-dialog')?.open&&document.querySelectorAll('[data-monitor-angle] video').length===2&&!$('[data-monitor-play]').disabled,'Both original cameras did not enter the monitor');
  }
  function pixels() {
    return [...document.querySelectorAll('[data-monitor-angle]')].map(figure=>{
      const video=figure.querySelector('video');if(video.readyState<2||video.seeking||video.error)return {ready:false,error:video.error?.message};
      const canvas=document.createElement('canvas');canvas.width=96;canvas.height=64;const ctx=canvas.getContext('2d');ctx.drawImage(video,0,0,96,64);
      const rgba=ctx.getImageData(0,0,96,64).data;let index=0;
      for(let bit=0;bit<8;bit++){const at=(4*96+bit*8+4)*4;if((rgba[at]+rgba[at+1]+rgba[at+2])/3>127)index|=1<<bit;}
      return {ready:true,angle_id:figure.dataset.monitorAngle,decoded_source_frame:index,expected_source_frame:Number(figure.dataset.sourceFrame),time:video.currentTime,paused:video.paused,muted:video.muted,src:new URL(video.currentSrc).pathname,pixel:[...rgba.slice((32*96+48)*4,(32*96+48)*4+3)]};
    });
  }
  async function author() {
    const initial=await readProject(),clip=initial.clips[0],group=initial.multicam_groups[0];
    check(initial.clips.length===1&&!group.audio_lock,'The authored fixture already has an audio lock');
    await openMonitor(clip);set('[data-monitor-seek]',24);
    await until(()=>pixels().every(v=>v.ready&&v.decoded_source_frame===v.expected_source_frame),'Both actual paused source pictures did not follow their synchronized clock',3500);
    metrics.paused_angles=pixels();check(same(metrics.paused_angles.map(v=>v.decoded_source_frame),[36,48]),'Actual decoded source frames differ from the independent source counters');
    check(metrics.paused_angles.every(v=>v.muted&&v.paused),'Monitor pictures can feed duplicate source sound');
    steps.push('two_original_camera_decoders_show_exact_shared_clock_source_frames');
    set('[data-monitor-audio]',group.angles[1].id);click('[data-monitor-lock]');
    await until(()=>$('[data-monitor-status]').textContent.startsWith('Sound stays')&&!$('[data-monitor-lock]').disabled,'The fixed sound camera did not apply');
    check(!(await readProject()).multicam_groups[0].audio_lock,'The monitor silently saved before Save');
    click('[data-monitor-close]');await save();const locked=await readProject();
    check(locked.multicam_groups[0].audio_lock?.angle_id===group.angles[1].id,'The fixed sound camera did not save');
    click('#undo-button');await save();check(!(await readProject()).multicam_groups[0].audio_lock,'One undo did not release the complete sound choice');
    click('#redo-button');await save();check(same((await readProject()).multicam_groups,locked.multicam_groups),'Redo changed the camera/source clock binding');
    steps.push('one_undo_redo_of_fixed_camera_sound_without_silent_save');
    selectClip(clip.id);click('#source-audio-button');await until(()=>$('.editorial-dialog')?.open&&$('[data-audio-stream]'),'Locked source audio controls did not open');
    check($('[data-audio-stream]').options.length===2&&$('.editorial-dialog [data-panel] h3')?.textContent.includes('camera_b'),'Source audio controls did not expose the locked camera');
    set('[data-audio-stream]',2);set('[data-audio-left]',1);set('[data-audio-right]',0);click('[data-apply-audio]');
    await until(()=>$('.editorial-dialog [data-status]')?.textContent.startsWith('Applied.'),'The fixed source stream/channel mapping did not apply');
    click('.editorial-dialog [aria-label="Close editorial controls"]');selectClip(clip.id);set('[data-field="volume"]',.5);set('[data-field="audio.pan"]',.25);await save();
    const mapped=await readProject(),lock=mapped.multicam_groups[0].audio_lock;
    check(lock.stream_index===2&&same(lock.channels,[1,0]),'The saved sound source mapping differs');
    check(mapped.clips[0].volume===.5&&mapped.clips[0].audio.pan===.25&&mapped.clips[0].audio.stream_index==null,'Gain/pan or the original picture source route was overwritten');
    await selectProject(fixture.sentinel_id,fixture.sentinel_name);await selectProject(fixture.project_id,fixture.project_name);
    const reopened=await readProject();check(same(reopened.clips,mapped.clips)&&same(reopened.multicam_groups,mapped.multicam_groups),'Source mapping did not survive save/reopen');
    steps.push('nondefault_locked_stream_swapped_channels_and_authored_gain_pan','source_mapping_saved_and_reopened');
  }
  function measured(values,rate) {
    const frequencies=[220,330,440,660,880,990,997],count=values[0].length,rms=[0,0],amplitudes={};let minimumWindowRMS=[1,1];
    for(let ch=0;ch<2;ch++){
      rms[ch]=Math.sqrt(values[ch].reduce((sum,x)=>sum+x*x,0)/count);
      for(let start=0;start+256<=count;start+=256)minimumWindowRMS[ch]=Math.min(minimumWindowRMS[ch],Math.sqrt(values[ch].slice(start,start+256).reduce((sum,x)=>sum+x*x,0)/256));
    }
    for(const frequency of frequencies)amplitudes[frequency]=[0,1].map(ch=>{let re=0,im=0;for(let i=0;i<count;i++){const phase=2*Math.PI*frequency*i/rate;re+=values[ch][i]*Math.cos(phase);im+=values[ch][i]*Math.sin(phase);}return 2*Math.hypot(re,im)/count;});
    return {samples:count,rms,amplitudes,minimum_window_rms:minimumWindowRMS};
  }
  async function playAndCut() {
    const initial=await readProject(),group=initial.multicam_groups[0],clip=initial.clips[0],sound=initial.assets.find(a=>a.id===group.angles[1].asset_id);
    check(initial.clips.length===1&&group.audio_lock?.stream_index===2&&same(group.audio_lock.channels,[1,0]),'The locked source did not survive backend restart');
    const routing=window.CinematicumAudioRouting,original=routing.ensure,voices=new Set(),events=[];
    let media=null,context=null,processor=null,oscillator=null,gain=null,loading=null,ready=false,captured=null,route=null,connected=false,cutFrame=null;
    function attach() {
      if(!ready||!media?.audioGate||!media.source||connected)return;
      processor=new AudioWorkletNode(context,'cinematicum-audio-probe',{numberOfInputs:3,numberOfOutputs:1,outputChannelCount:[2],channelCount:2,channelCountMode:'explicit',channelInterpretation:'speakers'});
      processor.port.onmessage=event=>{captured=event.data;};processor.connect(context.destination);
      media.source.connect(processor,0,0);media.audioGate.connect(processor,0,1);
      oscillator=context.createOscillator();gain=context.createGain();oscillator.frequency.value=997;gain.gain.value=.25;oscillator.connect(gain);gain.connect(processor,0,2);oscillator.start();connected=true;
    }
    routing.ensure=function(voice,ctx,candidate,asset,notify,options) {
      const result=original.call(this,voice,ctx,candidate,asset,notify,options);
      if(ctx&&asset.kind==='audio'){
        voices.add(voice);media??=voice;context=ctx;route=result;
        if(!loading)loading=context.audioWorklet.addModule('/ENGINE_TEST_audio_probe_worklet.js').then(()=>{ready=true;attach();});
        attach();if(result.ready)check(asset.id===sound.id&&candidate.audio.stream_index===2&&same(candidate.audio.channels,[1,0]),'Live playback selected picture audio instead of the fixed source');
      }
      return result;
    };
    function analyzeCapture() {
      check(captured,'No actual render-thread observation was collected');
      const report={mixed:measured(captured.samples[1],captured.sample_rate),raw:measured(captured.samples[0],captured.sample_rate),calibration:measured(captured.samples[2],captured.sample_rate),window:{start_frame:captured.start_frame,end_frame:captured.end_frame,sample_rate:captured.sample_rate},decoder:{...media.el.pcmState},route};
      check(Math.abs(report.calibration.amplitudes[997][0]-.25)<.005,'The independent output observer calibration failed');
      for(let ch=0;ch<2;ch++){
        const expected=ch===0?.15:.15,frequency=ch===0?660:440;
        check(Math.abs(report.mixed.amplitudes[frequency][ch]-expected)<.005,'Actual output gain/pan/selected channel differs');
        check(Math.abs(report.mixed.rms[ch]-expected/Math.sqrt(2))<.005,'Actual output RMS differs');
        check(report.mixed.minimum_window_rms[ch]>.07,'The actual output contains a gap across the camera cut');
        check(Math.abs(report.raw.amplitudes[frequency][ch]-(ch===0?.4:.3))<.005,'The original selected source samples differ');
        for(const wrong of [220,330,880,990])check(report.mixed.amplitudes[wrong][ch]<.005,'A different camera or default source stream entered the mix');
      }
      check(report.decoder.kind==='scheduled-source-pcm'&&report.decoder.scheduled_chunks>0&&report.decoder.underruns===0,'The actual PCM decoder underrun during the camera edit');
      check(route.manifest?.asset_id===sound.id&&route.manifest.source_sha256===sound.sha256&&route.stream_index===2&&same(route.channel_map,[1,0]),'The live source receipt lost original camera identity');
      return report;
    }
    try {
      await openMonitor(clip);set('[data-monitor-seek]',24);click('[data-monitor-play]');
      await until(()=>connected&&route?.ready&&!media.el.paused&&pixels().every(v=>v.ready&&!v.paused),'Actual picture and fixed-source PCM did not start together',4000);
      const first=pixels();await sleep(230);const second=pixels();
      check(first.every((v,i)=>v.decoded_source_frame<second[i].decoded_source_frame),'Both camera pictures did not advance simultaneously');
      check(second.every(v=>Math.abs(v.decoded_source_frame-v.expected_source_frame)<=2),'A decoded camera picture drifted from the shared clock');
      metrics.playing_angles={before:first,after:second};
      steps.push('two_actual_camera_pictures_advance_on_shared_live_audio_clock');
      const listener=event=>events.push({type:event.type,time:context.currentTime});media.el.addEventListener('seeking',listener);
      captured=null;processor.port.postMessage({action:'capture',start_frame:Math.ceil(context.currentTime*context.sampleRate)+1024,sample_count:32768});
      await sleep(160);cutFrame=Math.floor(window.CinematicumSequencePlayback.clock().frame);
      click(`[data-monitor-cut="${group.angles[1].id}"]`);
      await until(()=>document.querySelectorAll('.timeline-clip[data-clip]').length===2&&!$('[data-monitor-lock]').disabled,'The live camera cut did not apply as one edit');
      await until(()=>Boolean(captured),'The real audio output across the live cut was not captured');
      metrics.cross_cut=analyzeCapture();metrics.voice_count=voices.size;metrics.source_seek_events=events;
      check(voices.size===1&&!events.length,'The locked source voice was replaced or sought during a picture-only cut');
      check($('#play-button').getAttribute('aria-label')==='Pause timeline','The live camera cut unexpectedly stopped the shared transport');
      click('[data-monitor-play]');media.el.removeEventListener('seeking',listener);
      steps.push('one_live_picture_cut_preserves_uninterrupted_original_pcm_voice','measured_nondefault_stream_swap_gain_pan_and_zero_underruns');
      set('[data-monitor-seek]',24);captured=null;click('[data-monitor-play]');
      await until(()=>route?.ready&&!media.el.paused,'Explicit source playback restart failed');
      processor.port.postMessage({action:'capture',start_frame:Math.ceil(context.currentTime*context.sampleRate)+2048,sample_count:8192});
      await until(()=>Boolean(captured),'Actual restarted sound was not observed');metrics.restart=analyzeCapture();click('[data-monitor-play]');
      await save(true);click('[data-monitor-close]');const cut=await readProject(),right=cut.clips.find(c=>c.asset_id===sound.id);
      check(cut.clips.length===2&&right&&right.start>24&&right.start<100,'The actual camera cut has an invalid source clock');
      metrics.cut_frame=right.start;check(Math.abs(right.start-cutFrame)<=1,'The control did not cut at its click-time playhead');
      check(same(cut.multicam_groups,initial.multicam_groups),'Picture switching changed the locked camera or source mapping');
      click('#undo-button');await save();const undone=await readProject();check(undone.clips.length===1&&same(undone.multicam_groups,initial.multicam_groups),'One undo did not restore the picture while preserving the sound choice');
      click('#redo-button');await save();check(same((await readProject()).clips,cut.clips),'Redo lost the actual source-clock cut');
      steps.push('actual_pcm_pause_restart','one_undo_redo_save_of_camera_cut_with_audio_lock_preserved');
    } finally {
      routing.ensure=original;
      if($('#multicam-monitor-dialog')?.open)$('[data-monitor-close]').click();
      if(processor){try{media.source.disconnect(processor);media.audioGate.disconnect(processor);}catch(_error){}processor.disconnect();processor.port.onmessage=null;}
      if(oscillator){oscillator.stop();oscillator.disconnect();gain.disconnect();}
    }
  }
  async function render() {
    const p=await readProject(),group=p.multicam_groups[0];
    check(p.clips.length===2&&group.audio_lock.stream_index===2&&same(group.audio_lock.channels,[1,0]),'The saved picture cut and sound lock did not reopen');
    const right=p.clips.find(c=>c.start>0);metrics.cut_frame=right.start;
    await openMonitor(right);set('[data-monitor-seek]',right.start);
    await until(()=>pixels().every(v=>v.ready&&Math.abs(v.decoded_source_frame-v.expected_source_frame)<.01),'Reopened original camera clocks do not match the saved edit',3500);
    metrics.reopened_angles=pixels();check($('[data-monitor-audio]').value===group.audio_lock.angle_id,'The persisted fixed sound angle is not selected');click('[data-monitor-close]');
    steps.push('saved_camera_cut_audio_lock_and_simultaneous_clocks_reopen');
    click('#export-button');click('[data-export="prores"]');await until(()=>!$('#download-job')?.hidden&&$('#job-label')?.textContent==='ProRes export complete','The actual camera movie export did not finish',7000);
    const link=control('#download-job'),url=new URL(link.href);check(url.origin===location.origin&&url.pathname.startsWith('/api/projects/'+p.id+'/exports/')&&url.pathname.endsWith('.mov'),'The movie download escaped its project');
    metrics.download_href=url.pathname+url.search;metrics.download_name=link.download;link.click();steps.push('actual_prores_pcm_render_and_download');
    return {expect_download:true};
  }
  try {
    await until(()=>$('#project-select')&&!$('#project-select').disabled&&[...$('#project-select').options].some(o=>o.value===fixture.project_id),'The exact fixture did not bootstrap',3000);
    await selectProject(fixture.project_id,fixture.project_name);
    const operation={author,play:playAndCut,render}[fixture.operation];check(operation,'Unknown phase');const extra=await operation();
    return {passed:true,operation:fixture.operation,steps,metrics,...extra,elapsed_ms:Math.round(performance.now()-began)};
  } catch(error) {metrics.failure_videos=[...document.querySelectorAll('[data-monitor-angle] video')].map(v=>({src:v.currentSrc,ready:v.readyState,seeking:v.seeking,network:v.networkState,time:v.currentTime,error:v.error?.message}));metrics.failure_pixels=pixels();return {passed:false,operation:fixture.operation,steps,metrics,error:String(error),elapsed_ms:Math.round(performance.now()-began)};}
})();

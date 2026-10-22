// Shared ordinary-control acceptance for native WKWebView and explicit Chromium.
return await (async()=>{
  const cfg=/* ENGINE_TEST_CONFIG */ {},began=performance.now(),deadline=began+13000,steps=[],metrics={};
  const $=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)],sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const diagnostic=()=>'; ramp='+($('[data-retime-status]')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,maximum=2300){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(20);}throw Error(label+diagnostic());}
  function click(s){const e=$(s);if(!e||e.disabled||e.hidden)throw Error('Unavailable '+s+diagnostic());e.click();}
  function choose(s,v){const e=$(s);if(!e||e.disabled)throw Error('Unavailable '+s);e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  function selectClip(element){if(!element)throw Error('Actual timeline clip is missing');const box=element.getBoundingClientRect();element.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,clientX:box.x+box.width/2,clientY:box.y+20}));document.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));}
  async function saved(id){const response=await fetch('/api/projects/'+id,{cache:'no-store'});if(!response.ok)throw Error('Saved project not readable');return response.json();}
  function canonical(value){return JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);}
  async function select(id){if($('#project-select').value!==id){choose('#project-select',id);await until(()=>$('#project-select').value===id&&/^(LOCAL PROJECT|SAVED LOCALLY)$/.test($('#save-state').textContent)&&!$('#viewer-project').textContent.includes('sentinel'),'Saved project did not open');}}
  async function render(id){const previous=$('#download-job')?.getAttribute('href');click('#export-button');click('[data-export="prores"]');await until(()=>$('#job-label').textContent==='ProRes export complete'&&!$('#download-job').hidden&&$('#download-job').getAttribute('href')!==previous&&$('#download-job').getAttribute('href').includes('/'+id+'/exports/'),'Actual ProRes ramp export failed',5000);const href=$('#download-job').getAttribute('href');click('#download-job');return href;}
  let context=null,processor=null,source=null;
  try{
    await until(()=>$('#project-select')?.options.length>=2&&$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('#archive-button'),'Actual ramp project did not bootstrap',4000);
    await select(cfg.project_id);
    if(cfg.operation==='author'){
      selectClip($('.timeline-clip[data-clip="'+cfg.clip_id+'"]'));click('[data-action="retime"]');
      choose('[data-retime-duration]',12);choose('[data-retime-method]','optical_flow');choose('[data-retime-audio]','varispeed');
      const rows=all('[data-retime-key]');choose('[data-retime-key]:first-child [data-retime-speed]',.5);choose('[data-retime-key]:last-child [data-retime-speed]',1.5);
      click('[data-retime-add]');if(all('[data-retime-key]').length!==3||Number(all('[data-retime-frame]')[1].value)!==6||Number(all('[data-retime-speed]')[1].value)!==1)throw Error('Real intermediate key authoring failed');
      click('[data-retime-key]:nth-child(2) [data-retime-delete]');if(all('[data-retime-key]').length!==2||!$('[data-retime-summary]').textContent.includes('12.000 source frames'))throw Error('Curve source-span summary is wrong');
      steps.push('real_speed_key_controls');click('[data-retime-apply]');await until(()=>!$('.cinematicum-retime').open&&$('#save-state').textContent==='UNSAVED'&&$('[data-field="speed"]').disabled,'Real ramp apply failed',3200);
      click('#undo-button');selectClip($('.timeline-clip[data-clip="'+cfg.clip_id+'"]'));if($('[data-field="speed"]').disabled)throw Error('One undo retained the ramp');
      click('#redo-button');selectClip($('.timeline-clip[data-clip="'+cfg.clip_id+'"]'));if(!$('[data-field="speed"]').disabled)throw Error('One redo lost the ramp');steps.push('one_undo_redo_applies_recipe');
      click('#jump-start');for(let i=0;i<7;i++)click('#step-forward');click('#split-button');
      if(all('.timeline-clip[data-type="clip"]').length!==2||Math.abs(Number($('[data-field="in"]').value)-(4+2+16/24))>1e-9)throw Error('Split used a linear source in-point');
      choose('[data-field="duration"]',7);if(Number($('[data-field="duration"]').value)!==7)throw Error('Ramp tail trim did not apply');click('#undo-button');
      const bars=all('.timeline-clip[data-type="clip"]');selectClip(bars[1]);if(Number($('[data-field="duration"]').value)!==8)throw Error('One undo did not restore the retained curve tail');
      steps.push('split_and_tail_trim_preserve_source_curve');click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Retime save failed',2400);
      choose('#project-select',cfg.sentinel_id);await until(()=>$('#viewer-project').textContent.includes('sentinel'),'Sentinel did not open');await select(cfg.project_id);
      const project=await saved(cfg.project_id),clips=[...project.clips].sort((a,b)=>a.start-b.start);
      if(clips.length!==2||clips[0].retime.offset!==0||clips[1].retime.offset!==4||clips.some(c=>c.retime.method!=='optical_flow'||c.retime.audio!=='varispeed'||c.audio.stream_index!==2||c.audio.channels.join(',')!=='1,0'||c.volume!==.6||c.audio.pan!==.25))throw Error('Save/reopen lost editable ramp or original audio routing');
      selectClip(all('.timeline-clip[data-type="clip"]')[1]);click('[data-action="retime"]');
      if(Number(all('[data-retime-speed]')[0].value)!==.5+4/12||Number(all('[data-retime-frame]').at(-1).value)!==8)throw Error('Split interval did not reopen as equivalent local curve keys');
      click('[data-retime-apply]');await until(()=>!$('.cinematicum-retime').open,'Unchanged split curve did not reapply',2400);
      click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Reapplied split curve did not save');
      const retained=(await saved(cfg.project_id)).clips.find(c=>c.start===7);
      if(retained.retime.offset!==4||canonical(retained.retime)!==canonical(clips[1].retime))throw Error('Reapplying unchanged local keys rounded or discarded the original curve handles');
      steps.push('save_switch_reopen_keeps_recipe_routing_and_gain');
    }else if(cfg.operation==='playback'){
      click('#jump-start');for(let i=0;i<cfg.truth.probe_absolute_frame;i++)click('#step-forward');
      await until(()=>$('#frame-status').textContent==='Rendered frame '+cfg.truth.probe_absolute_frame+' · export graph'&&!$('#processed-frame').hidden&&$('#processed-frame').complete,'Interpolated paused frame did not arrive',4500);
      const image=$('#processed-frame'),canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const rgba=[...ctx.getImageData(48,32,1,1).data];metrics.processed_pixel=rgba;
      if(cfg.truth.probe_pixel.some((v,i)=>Math.abs(v-rgba[i])>12))throw Error('Paused optical-flow picture misses independent translated texture: '+rgba);steps.push('actual_interpolated_paused_picture');
      click('#play-button');await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2&&$('#job-label').textContent==='Render complete','Play did not complete a real retimed preview',4500);
      const video=$('#render-video');if(!video.currentSrc.includes('/exports/')||Math.abs(video.duration-15/24)>.08)throw Error('Play did not use the actual completed ramp movie');steps.push('play_uses_actual_rendered_preview');
      context=new (window.AudioContext||window.webkitAudioContext)();await context.resume();source=context.createMediaElementSource(video);processor=context.createScriptProcessor(1024,2,2);
      let samples=0,left=0,right=0,peak=0;processor.onaudioprocess=event=>{const a=event.inputBuffer.getChannelData(0),b=event.inputBuffer.getChannelData(1);for(let c=0;c<2;c++)event.outputBuffer.getChannelData(c).set(event.inputBuffer.getChannelData(c));for(let i=0;i<a.length;i++){samples++;left+=a[i]*a[i];right+=b[i]*b[i];peak=Math.max(peak,Math.abs(a[i]),Math.abs(b[i]));}};
      source.connect(processor);processor.connect(context.destination);video.currentTime=0;click('#play-button');
      await until(()=>video.currentTime>.35&&samples>8000&&peak>.025,'Rendered video clock or actual stereo audio did not advance',1700);
      const ratio=Math.sqrt(left/Math.max(right,1e-20));metrics.playback={media_time:video.currentTime,samples,peak,left_right_rms_ratio:ratio,decoded_video_frames:video.getVideoPlaybackQuality?.().totalVideoFrames??video.webkitDecodedFrameCount??null};
      if(ratio<.55||ratio>.95||metrics.playback.decoded_video_frames!==null&&metrics.playback.decoded_video_frames<4)throw Error('Rendered stereo routing/picture decoder failed: '+JSON.stringify(metrics.playback));video.pause();steps.push('rendered_picture_clock_and_nonzero_stereo_audio');
      processor.disconnect();source.disconnect();await context.close();context=null;
      metrics.movie_href=await render(cfg.project_id);steps.push('actual_prores_export_and_download');
    }else if(cfg.operation==='archive'){
      const original=await saved(cfg.project_id),originalText=JSON.stringify(original);
      click('#archive-button');click('[data-archive-export]');await until(()=>!$('.cinematicum-archive').open&&$('#job-label').textContent==='Project archive ready'&&!$('#download-job').hidden,'Actual ramp archive failed',3200);
      const href=$('#download-job').getAttribute('href'),name=$('#download-job').download,response=await fetch(href,{cache:'no-store'});if(!response.ok)throw Error('Archive read failed');const blob=await response.blob();if(blob.size<1000)throw Error('Real project archive absent');click('#download-job');
      click('#archive-button');const transfer=new DataTransfer();transfer.items.add(new File([blob],name||'ENGINE_TEST.cinematicum.zip',{type:'application/zip'}));const input=$('[data-archive-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));click('[data-archive-restore]');
      await until(()=>$('#job-label').textContent==='Project restored'&&!$('#open-restored-project').hidden,'Actual project ZIP file restore failed',3500);steps.push('actual_archive_download_and_file_upload');
      const restoredID=$('#open-restored-project').dataset.projectId;if(!/^[a-f0-9]{32}$/.test(restoredID)||restoredID===cfg.project_id||JSON.stringify(await saved(cfg.project_id))!==originalText)throw Error('Restore changed the original project');
      click('#open-restored-project');await until(()=>$('#project-select').value===restoredID&&all('.timeline-clip[data-type="clip"]').length===2,'Restored speed ramps did not open');
      const restored=await saved(restoredID);if(canonical(restored.clips)!==canonical(original.clips))throw Error('Archive lost editable time mapping');metrics.restored_project_id=restoredID;steps.push('restored_new_identity_keeps_editable_ramps');
      metrics.movie_href=await render(restoredID);steps.push('restored_picture_audio_render_and_download');
    }else throw Error('Unsupported phase');
    return {passed:true,steps,metrics,expect_download:cfg.operation!=='author',expected_download_count:cfg.operation==='archive'?2:cfg.operation==='playback'?1:0,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,metrics,error:String(error),elapsed_ms:Math.round(performance.now()-began)};}
  finally{try{processor?.disconnect();source?.disconnect();if(context)await context.close();}catch{}}
})();

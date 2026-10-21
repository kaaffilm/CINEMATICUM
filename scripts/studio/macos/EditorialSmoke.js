// Native controls only. EDITORIAL_TEST is injected by the isolated harness.
return await(async()=>{
 const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms)),steps=[],metrics={};
 async function until(fn,label,timeout=3000){const end=performance.now()+timeout;while(performance.now()<end){if(fn())return;await sleep(30);}throw Error(label+'; '+$('.editorial-dialog [data-status]')?.textContent+'; '+($('#toast')?.textContent||''));}
 function reach(selector){const e=$(selector);if(!e)throw Error('Missing '+selector);for(let p=e.parentElement;p;p=p.parentElement){if(!p.matches('.timeline-scroll,.timeline-tools,.inspector,dialog,.editorial-cues'))continue;const r=e.getBoundingClientRect(),b=p.getBoundingClientRect();if(r.top<b.top+3)p.scrollTop+=r.top-b.top-3;else if(r.bottom>b.top+p.clientHeight-3)p.scrollTop+=r.bottom-b.top-p.clientHeight+3;if(r.left<b.left+3)p.scrollLeft+=r.left-b.left-3;else if(r.right>b.left+p.clientWidth-3)p.scrollLeft+=r.right-b.left-p.clientWidth+3;}const r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(r.width<2||r.height<2||r.top<0||r.bottom>innerHeight+.5||(hit!==e&&!e.contains(hit)))throw Error('Unreachable '+selector);return e;}
 function click(s){const e=reach(s);if(e.disabled)throw Error('Disabled '+s);e.click();}
 function set(s,v,event='input'){const e=reach(s);e.value=String(v);e.dispatchEvent(new Event(event,{bubbles:true}));}
 function close(){click('.editorial-heading button');}
 async function applied(){await until(()=>$('.editorial-dialog [data-status]')?.textContent.startsWith('Applied.'),'Editorial edit did not apply');}
 function selectFirst(selector='.timeline-clip'){const e=reach(selector),r=e.getBoundingClientRect(),value={bubbles:true,button:0,pointerId:76,isPrimary:true,clientX:r.left+Math.min(r.width/2,18),clientY:r.top+r.height/2};e.dispatchEvent(new PointerEvent('pointerdown',value));window.dispatchEvent(new PointerEvent('pointerup',value));if(!$('.timeline-clip.selected'))throw Error('Clip selection failed');}
 function drag(selector,delta){const e=reach(selector),r=e.getBoundingClientRect(),value={bubbles:true,button:0,pointerId:77,isPrimary:true,clientX:r.left+r.width/2,clientY:r.top+r.height/2};e.dispatchEvent(new PointerEvent('pointerdown',value));window.dispatchEvent(new PointerEvent('pointermove',{...value,clientX:value.clientX+delta,altKey:true}));window.dispatchEvent(new PointerEvent('pointerup',{...value,clientX:value.clientX+delta}));}
 try{
  await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('#save-project'),'Native editor did not bootstrap',4000);
  const stage=EDITORIAL_TEST.stage;
  if(stage==='sequences'){
   click('#editorial-button');set('[data-sequence-name]','Nested assembly');click('[data-action="sequence_create"]');await applied();
   if(!$('.editorial-sequence')?.textContent.includes('Nested assembly'))throw Error('New sequence did not become active');steps.push('native_sequence_creation');
   click('[data-nest="main"]');await applied();close();if(document.querySelectorAll('.timeline-clip').length!==1)throw Error('Nested clip missing');
   click('#undo-button');if(document.querySelectorAll('.timeline-clip').length!==0)throw Error('Nest undo failed');click('#redo-button');if(document.querySelectorAll('.timeline-clip').length!==1)throw Error('Nest redo failed');steps.push('nested_clip_one_undo_redo');
   selectFirst();if($('#inspector .inspector-name')?.textContent!=='Main sequence'||$('#selection-kind')?.textContent!=='SEQUENCE')throw Error('Nested source is not identified in its inspector');
   set('#inspector [data-field="duration"]',999,'change');if(Number($('#inspector [data-field="duration"]').value)!==16)throw Error('Nested duration escaped its child source');
   set('#inspector [data-field="in"]',999,'change');if(Number($('#inspector [data-field="in"]').value)!==15||Number($('#inspector [data-field="duration"]').value)!==1)throw Error('Nested source in escaped its child source');
   click('#undo-button');selectFirst();if(Number($('#inspector [data-field="in"]').value)!==0||Number($('#inspector [data-field="duration"]').value)!==16)throw Error('Nested source trim undo lost the live range');
   drag('.timeline-clip [data-edge="right"]',150);if(Number($('#inspector [data-field="duration"]').value)!==16)throw Error('Nested pointer trim escaped child duration');steps.push('nested_inspector_and_source_trim_bounds');
  }else if(stage==='captions'){
   click('#captions-button');click('[data-add-cue]');set('[data-cue-start]',0);set('[data-cue-end]',16);set('[data-cue-text]','ENGINE TEST\nسلام');click('[data-caption-burn]');click('[data-apply-captions]');await applied();steps.push('caption_cue_and_burnin_applied');
   click('[data-export-caption="srt"]');await until(()=>!$('[data-caption-download]')?.hidden,'Caption sidecar missing');metrics.sidecar=$('[data-caption-download]').getAttribute('href');if(!metrics.sidecar.includes('/exports/'))throw Error('Sidecar is not a real owned download');steps.push('actual_srt_download');close();
   selectFirst('.timeline-clip[data-type="title"]');if($('#inspector [data-field]')||!$('#inspector [data-action="captions"]'))throw Error('Caption plate can diverge through the ordinary title inspector');
   const captionBefore=$('.timeline-clip[data-type="title"]').getAttribute('aria-label');drag('.timeline-clip[data-type="title"]',120);if($('.timeline-clip[data-type="title"]').getAttribute('aria-label')!==captionBefore)throw Error('Caption plate moved independently from its cue');
   click('#inspector [data-action="captions"]');if(Number($('[data-cue-start]').value)!==0||Number($('[data-cue-end]').value)!==16||$('[data-cue-text]').value!=='ENGINE TEST\nسلام')throw Error('Protected caption cue changed');close();steps.push('caption_plate_readonly_drag_and_edit_route');
  }else if(stage==='audio'){
   selectFirst();click('#source-audio-button');set('[data-audio-stream]',2,'change');set('[data-audio-left]',1);set('[data-audio-right]',0);click('[data-apply-audio]');await applied();close();steps.push('actual_source_stream_channel_controls');
   click('#undo-button');click('#redo-button');steps.push('audio_mapping_undo_redo');
  }else if(stage==='multicam'){
   click('#multicam-button');for(const row of document.querySelectorAll('[data-camera]')){row.querySelector('[data-camera-use]').click();row.querySelector('[data-camera-in]').value='0';}set('[data-multicam-name]','Two native cameras');click('[data-create-multicam]');await applied();close();selectFirst();
   for(let i=0;i<6;i++)document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
   click('#multicam-button');click('[data-angle]:not([disabled])');await applied();close();steps.push('native_multicam_creation_and_angle_cut');
  }else throw Error('Unknown stage');
  click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Save failed');steps.push('saved_real_project');
  click('#export-button');click('[data-export="prores"]');await until(()=>$('#job-label').textContent==='ProRes export complete'&&!$('#download-job').hidden,'Render failed',6500);
  metrics.movie=$('#download-job').getAttribute('href');steps.push('actual_prores_export');
  return {passed:true,stage,steps,metrics};
 }catch(error){return {passed:false,stage:EDITORIAL_TEST.stage,error:error.message,steps,metrics,status:$('.editorial-dialog [data-status]')?.textContent,toast:$('#toast')?.textContent,job:$('#job-detail')?.textContent};}
})();

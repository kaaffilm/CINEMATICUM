// Operate shipped controls in real WKWebView on disposable ENGINE TEST media.
return await (async()=>{
  const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const steps=[],deadline=performance.now()+12500;
  function require(ok,message){if(!ok)throw Error(message+'; tracking='+($('[data-track-status]')?.textContent||'')+'; toast='+($('#toast')?.textContent||''));}
  async function until(fn,message,ms=2200){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(fn())return;await sleep(30);}require(false,message);}
  function click(s){const e=$(s);require(e&&!e.disabled,'Unavailable control '+s);e.click();}
  function set(s,v){const e=$(s);require(e&&!e.disabled,'Unavailable field '+s);e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('.media-item [data-add]'),'Fixture did not bootstrap',3500);
    click('.media-item [data-add]');const clipId=$('.timeline-clip').dataset.clip;
    click('[data-action="track"]');await until(()=>$('[data-track-status]')?.textContent.includes('Click a textured feature'),'Seed frame did not decode');
    const canvas=$('[data-track-canvas]');require(canvas.width===128&&canvas.height===96,'Seed dimensions are wrong');
    const rect=canvas.getBoundingClientRect();canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:rect.left+rect.width*36/128,clientY:rect.top+rect.height*38/96,pointerId:9,button:0}));
    set('[data-track-radius]',8);set('[data-track-threshold]',.1);click('[data-track-run]');
    await until(()=>$('[data-track-status]').textContent.includes('12 of 12 frames matched'),'Actual measurement failed',3500);steps.push('exact_seed_point_pick_and_measured_12_frame_track');
    const measurements=$('[data-track-download]').getAttribute('href');require(/\/analysis\/[a-f0-9]{32}\.json\?download=1$/.test(measurements),'No measurement receipt');
    click('[data-track-stabilize]');await until(()=>$('[data-track-status]').textContent.includes('Stabilization applied'),'Stabilization did not apply');
    click('[data-track-mask]');await until(()=>$('[data-track-status]').textContent.includes('Animated mask added'),'Tracked mask did not apply');steps.push('independent_motion_and_animated_mask');
    click('[data-track-close]');await sleep(30);click('[data-mode="composite"]');
    require($('[data-graph-status]').textContent==='2 nodes · 2 in output','Tracked mask is not connected');
    click('#undo-button');require($('[data-graph-status]').textContent==='1 nodes · 1 in output','Mask did not undo as one operation');
    click('#redo-button');require($('[data-graph-status]').textContent==='2 nodes · 2 in output','Mask redo failed');steps.push('one_checkpoint_mask_undo_redo');
    click('[data-mode="edit"]');set('[data-field="speed"]',2);require(Number($('[data-field="duration"]').value)===6,'Retime did not preserve source duration');click('#undo-button');require(Number($('[data-field="duration"]').value)===12,'Retime undo failed');steps.push('retime_and_undo_preserve_motion');
    click('#jump-start');for(let i=0;i<6;i++)click('#step-forward');click('#split-button');require(document.querySelectorAll('.timeline-clip').length===2,'Clip did not split');steps.push('split_preserves_animation_domain');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Save failed',2200);
    return {passed:true,steps,clip_id:clipId,measurements,project_id:$('#project-select').value};
  }catch(error){return {passed:false,error:String(error),steps};}
})();

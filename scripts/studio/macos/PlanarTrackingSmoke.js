// Shipped controls, real measurement worker, persisted project, real movie.
return await (async()=>{
  const $=selector=>document.querySelector(selector),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const steps=[],began=performance.now(),deadline=began+120000;
  const detail=()=>'; project='+($('#viewer-project')?.textContent||'')+'; selected='+($('#project-select')?.value||'')+'; status='+($('[data-track-status]')?.textContent||'')+'; toast='+($('#toast')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; job='+($('#job-label')?.textContent||'');
  function require(ok,message){if(!ok)throw Error(message+detail());}
  async function until(fn,message,ms=5000){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(message+detail());}
  function click(selector){const node=$(selector);require(node&&!node.disabled,'Unavailable control '+selector);node.click();}
  function set(selector,value){const node=$(selector);require(node&&!node.disabled,'Unavailable field '+selector);node.value=String(value);node.dispatchEvent(new Event('change',{bubbles:true}));}
  function selectClip(id){const node=$(`.timeline-clip[data-clip="${id}"]`);require(node,'Missing clip '+id);const rect=node.getBoundingClientRect();node.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,pointerId:71,isPrimary:true,clientX:rect.left+15,clientY:rect.top+12}));window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,buttons:0,pointerId:71,isPrimary:true}));}
  const evidence={project_id:PLANAR_TEST.project_id};
  try {
    const projectId=PLANAR_TEST.project_id,sentinel=PLANAR_TEST.sentinel_id;
    await until(()=>$('#project-select')&&!$('#project-select').disabled&&[...$('#project-select').options].some(option=>option.value===projectId),'Planar project list did not bootstrap',10000);
    // Project timestamps have one-second precision. A fresh store may open the
    // sentinel first; fixture admission must never depend on filesystem order.
    if($('#project-select').value!==projectId)set('#project-select',projectId);
    await until(()=>$('#project-select').value===projectId&&!$('#project-select').disabled&&$('#viewer-project')?.textContent==='ENGINE TEST — native planar motion'&&$('.media-item [data-add]'),'Planar fixture did not open',5000);
    require(sentinel!==projectId&&[...$('#project-select').options].some(option=>option.value===sentinel),'Reopen sentinel is missing');
    steps.push('select_exact_fixture_project');
    const media=[...document.querySelectorAll('.media-item')].find(node=>node.textContent.includes('ENGINE_TEST_planar.mkv'));
    require(media,'Real moving-plane fixture is missing');media.querySelector('[data-add]').click();
    const clipId=$('.timeline-clip[data-type="clip"]').dataset.clip;evidence.clip_id=clipId;
    click('[data-action="track"]');await until(()=>$('[data-track-status]')?.textContent.includes('Click a textured feature'),'Initial seed did not decode');
    set('[data-track-model]','projective');await until(()=>$('[data-track-status]')?.textContent.includes('Choose the top-left'),'Planar seed did not decode');
    require($('[data-track-setup]').hidden,'Installed planar runtime did not pass its operation probe');
    const canvas=$('[data-track-canvas]');require(canvas.width===192&&canvas.height===144,'Planar seed dimensions differ');
    const rect=canvas.getBoundingClientRect();
    for(const [x,y] of [[.16,.14],[.68,.14],[.68,.76],[.16,.76]])canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:72,clientX:rect.left+x*rect.width,clientY:rect.top+y*rect.height}));
    click('[data-track-run]');await until(()=>$('[data-track-status]').textContent.includes('12 of 12 frames matched'),'Actual projective measurement failed',20000);
    const measurements=$('[data-track-download]').getAttribute('href');evidence.measurements=measurements;require(/\/analysis\/[a-f0-9]{32}\.json\?download=1$/.test(measurements),'No retained measurement artifact');
    steps.push('native_four_corner_pick_and_actual_projective_measurement');
    click('[data-track-stabilize]');await until(()=>$('[data-track-status]').textContent.includes('Stabilization applied'),'Measured stabilization failed');
    const image=[...$('[data-track-image]').options].find(option=>option.value);
    require(image,'Corner-pin image is missing');set('[data-track-image]',image.value);
    click('[data-track-pin]');await until(()=>$('[data-track-status]').textContent.includes('Corner-pin image added'),'Image pin failed');
    click('[data-track-close]');require(document.querySelectorAll('.timeline-clip[data-type="clip"]').length===2,'Corner pin did not create an editable image clip');
    const pinId=[...document.querySelectorAll('.timeline-clip[data-type="clip"]')].find(node=>node.dataset.clip!==clipId).dataset.clip;evidence.pin_id=pinId;
    steps.push('planar_stabilization_and_image_pin_on_stabilized_background');
    click('#undo-button');require(document.querySelectorAll('.timeline-clip[data-type="clip"]').length===1,'Pin undo failed');
    click('#undo-button');require(!$('[data-action="clear-planar"]'),'Stabilization undo failed');
    click('#redo-button');click('#redo-button');require(document.querySelectorAll('.timeline-clip[data-type="clip"]').length===2,'Planar redo failed');
    steps.push('separate_stabilization_and_pin_undo_redo');
    selectClip(clipId);set('[data-field="duration"]',10);
    require(Boolean($('#inspector [data-planar-stale]')?.getClientRects().length),'Source trim did not visibly invalidate measured motion');
    require(document.querySelectorAll('.timeline-clip[data-type="clip"]').length===2,'Source trim deleted the authored overlay');
    selectClip(pinId);require(Boolean($('#inspector [data-planar-stale]')?.getClientRects().length),'Dependent overlay was not marked stale');
    click('#undo-button');selectClip(clipId);
    require(!$('#inspector [data-planar-stale]'),'Undo did not restore valid measured motion');
    set('[data-field="start"]',3);selectClip(pinId);require(Number($('[data-field="start"]').value)===3,'Timeline translation did not move the dependent pin');
    require(!$('#inspector [data-planar-stale]'),'Pure timeline translation invalidated valid source motion');
    click('#undo-button');selectClip(pinId);set('[data-field="start"]',1);
    require(Boolean($('#inspector [data-planar-stale]')?.getClientRects().length),'Independent overlay move was not marked stale');
    click('#undo-button');steps.push('timing_dependency_invalidation_translation_remap_and_undo');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Planar project did not save');
    set('#project-select',sentinel);await until(()=>$('#viewer-project').textContent.includes('sentinel')&&!$('#project-select').disabled,'Sentinel did not load');
    set('#project-select',projectId);await until(()=>$('#viewer-project').textContent==='ENGINE TEST — native planar motion'&&!$('#project-select').disabled,'Saved planar project did not reopen');
    require(document.querySelectorAll('.timeline-clip[data-type="clip"]').length===2,'Saved overlay was lost');
    selectClip(clipId);require($('[data-action="clear-planar"]'),'Saved stabilization was lost');selectClip(pinId);require($('[data-action="clear-planar"]'),'Saved pin was lost');
    click('#jump-start');await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#frame-status')?.textContent==='Rendered frame 0 · export graph','Actual planar paused frame did not render',15000);
    steps.push('save_reopen_and_actual_processed_frame');
    click('#export-button');click('[data-export="prores"]');
    await until(()=>['ProRes export complete','Job failed','Job cancelled'].includes($('#job-label')?.textContent),'Planar movie did not finish',60000);
    require($('#job-label').textContent==='ProRes export complete','Planar movie failed');
    require(!$('#download-job').hidden,'Movie download is unavailable');steps.push('native_export_of_reopened_measured_composite');
    return {...evidence,passed:true,steps,
      download_href:$('#download-job').getAttribute('href'),elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...evidence,passed:false,steps,error:String(error),diagnostics:{active_project:$('#project-select')?.value,frame_status:$('#frame-status')?.textContent,job_label:$('#job-label')?.textContent,clip_ids:[...document.querySelectorAll('.timeline-clip[data-type="clip"]')].map(node=>node.dataset.clip)},elapsed_ms:Math.round(performance.now()-began)};}
})();

// Native DOM acceptance for linear masters, pass selection, range and undo.
// Only synthetic geometry is created; no app-state writes or HTTP shortcuts.
return await (async()=>{
  const steps=[],$=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms)),deadline=performance.now()+14500;
  async function until(fn,label,ms=2500){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(label+'; '+($('#toast')?.textContent||'')+'; '+($('#job-detail')?.textContent||''));}
  function reach(s){const e=$(s);if(!e||e.disabled)throw Error('Unavailable '+s);for(let p=e.parentElement;p;p=p.parentElement){if(!p.matches('.scene-inspector,.scene-object-list,.scene-tools,.scene-footer'))continue;const b=p.getBoundingClientRect(),r=e.getBoundingClientRect();if(r.top<b.top+2)p.scrollTop+=r.top-b.top-2;else if(r.bottom>b.top+p.clientHeight-2)p.scrollTop+=r.bottom-b.top-p.clientHeight+2;}return e;}
  function click(s){reach(s).click();}
  function set(s,v){const e=reach(s);if(e.type==='checkbox')e.checked=v;else e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  const checked=s=>$(s)?.checked===true;
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Test project did not bootstrap',4000);
    click('[data-mode="3d"]');await until(()=>$('.scene-editor'),'3D editor did not mount');
    click('[data-scene-add="plane"]');set('.scene-end-frame',3);set('.scene-samples select',4);
    click('.scene-object-list [data-scene-select="camera"]');
    if($('[data-scene-property="orientation_mode"]').value!=='transport')throw Error('New scene does not default to continuous camera transport');
    set('[data-scene-property="orientation_mode"]','world_up');click('#undo-button');
    if($('[data-scene-property="orientation_mode"]').value!=='transport')throw Error('Camera orientation mode does not undo');
    steps.push('camera_policy_is_authored_and_undoable');
    click('.scene-object-list [data-scene-select="world"]');set('[data-scene-property="transparent"]',true);
    click('#undo-button');if(checked('[data-scene-property="transparent"]'))throw Error('Transparent world did not undo');
    click('#redo-button');if(!checked('[data-scene-property="transparent"]'))throw Error('Transparent world did not redo');
    steps.push('transparent_world_undo_redo');
    click('.scene-object-list [data-scene-select="output"]');
    if(!$('[data-scene-render-pass="normal"]').disabled)throw Error('Passes enabled while EXR output is off');
    set('[data-scene-property="linear_exr"]',true);set('[data-scene-render-pass="depth"]',true);set('[data-scene-render-pass="normal"]',true);
    click('#undo-button');if(checked('[data-scene-render-pass="normal"]'))throw Error('Pass selection did not undo');
    click('#redo-button');if(!checked('[data-scene-render-pass="normal"]'))throw Error('Pass selection did not redo');
    set('[data-scene-render-range="end"]',2);set('[data-scene-render-range="start"]',2);
    if(Number($('.scene-end-frame').value)!==3)throw Error('Render range changed the authored scene duration');
    steps.push('float_masters_passes_and_independent_render_range');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Scene output did not save');
    click('[data-scene-action="render"]');
    await until(()=>['Media ready','Job failed','Job cancelled'].includes($('#job-label')?.textContent),'Native master render did not finish',10000);
    if($('#job-label').textContent!=='Media ready')throw Error('Native master render failed: '+$('#job-detail').textContent);
    await until(()=>$('#download-masters')&&!$('#download-masters').hidden&&!$('#download-scene').hidden&&$('.media-item[data-asset]'),'Master/source downloads or movie missing');
    steps.push('native_master_archive_source_and_movie_available');
    return {passed:true,steps,masters_href:$('#download-masters').getAttribute('href'),scene_href:$('#download-scene').getAttribute('href'),project_id:$('#project-select').value};
  }catch(error){return {passed:false,steps,error:error.message,scene_message:$('.scene-message')?.textContent,job_detail:$('#job-detail')?.textContent};}
})();

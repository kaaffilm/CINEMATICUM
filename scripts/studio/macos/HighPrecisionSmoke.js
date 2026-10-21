// Operate shipped controls, then click the real native WKDownload link.
// Source pixels, saved state and the downloaded movie are checked independently.
return await (async () => {
  const began=performance.now(),deadline=began+22000,steps=[];
  const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const detail=()=>'; toast='+($('#toast')?.textContent||'')+'; job='+($('#job-detail')?.textContent||'');
  function require(ok,message){if(!ok)throw Error(message+detail());}
  function control(s){const e=$(s);require(e&&!e.disabled&&!e.closest('[inert]'),'Unavailable '+s);e.scrollIntoView({block:'nearest'});return e;}
  function click(s){control(s).click();}
  function set(s,v){const e=control(s);if(e.type==='checkbox')e.checked=Boolean(v);else e.value=String(v);if(e.type==='range')e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}
  async function until(fn,label,ms=2500){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(label+detail());}
  try {
    await until(()=>$('#viewer-project')?.textContent==='ENGINE TEST — native 16-bit SDR'&&$('.media-item [data-add]'),'Source project did not bootstrap',5000);
    const projectId=$('#project-select').value;
    const sentinel=[...$('#project-select').options].find(o=>o.textContent.includes('sentinel'))?.value;
    require(sentinel&&sentinel!==projectId,'Missing independent reopen project');
    click('.media-item [data-add]');
    await until(()=>document.querySelectorAll('.timeline-clip[data-type="clip"]').length===1,'Source did not enter timeline');
    click('#export-button');
    require($('#movie-precision').value==='standard8'&&$('[data-export="master16"]').disabled,'Eight-bit project must not offer an enabled 16-bit master');
    set('#movie-precision','high16');set('#movie-transparent',true);click('#close-export');
    click('#undo-button');click('#export-button');
    require($('#movie-precision').value==='high16'&&!$('#movie-transparent').checked,'Transparency did not undo independently');
    click('#close-export');click('#redo-button');click('#export-button');
    require($('#movie-transparent').checked&&!$('[data-export="master16"]').disabled,'Transparency redo/master profile failed');
    click('#close-export');steps.push('precision_profile_and_transparency_undo_redo');
    click('[data-mode="composite"]');
    const details=$('.clip-transform-details');if(details&&!details.open)details.querySelector('summary').click();
    set('[data-field="scale"]',.73);set('[data-field="rotation"]',27);set('[data-field="x"]',.07);set('[data-field="y"]',-.09);
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Transform did not save');
    set('#project-select',sentinel);await until(()=>$('#viewer-project').textContent.includes('sentinel')&&!$('#project-select').disabled,'Sentinel project did not load');
    set('#project-select',projectId);await until(()=>$('#viewer-project').textContent==='ENGINE TEST — native 16-bit SDR'&&!$('#project-select').disabled,'Saved project did not reopen');
    click('#export-button');
    require($('#movie-precision').value==='high16'&&$('#movie-transparent').checked,'Saved precision/alpha settings were lost on reopen');
    click('#close-export');click('#jump-start');
    const clip=$('.timeline-clip[data-type="clip"]');require(clip,'Saved clip missing');
    const rect=clip.getBoundingClientRect();clip.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,pointerId:41,isPrimary:true,clientX:rect.left+15,clientY:rect.top+12}));
    window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,buttons:0,pointerId:41,isPrimary:true}));
    click('[data-mode="composite"]');
    for(const [field,value] of [['scale',.73],['rotation',27],['x',.07],['y',-.09]])require(Math.abs(Number($('[data-field="'+field+'"]').value)-value)<.00001,'Transform lost after reopen: '+field);
    await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#processed-frame')?.naturalWidth===64&&$('#frame-status')?.textContent==='Rendered frame 0 · export graph','16-bit processed frame did not arrive',6500);
    const frameUrl=new URL($('#processed-frame').currentSrc||$('#processed-frame').src,location.href).pathname;
    steps.push('transformed_project_saved_reopened_and_processed_frame_visible');
    click('#export-button');click('[data-export="master16"]');
    await until(()=>['16-bit master complete','Job failed','Job cancelled'].includes($('#job-label')?.textContent),'16-bit native export did not finish',10000);
    require($('#job-label').textContent==='16-bit master complete','16-bit master failed');
    await until(()=>!$('#download-job').hidden&&$('#download-job').getAttribute('href')?.includes('.mkv?download=1'),'Native master download unavailable');
    require($('#view-job').hidden&&$('#rendered-preview').disabled,'An FFV1 master must not be sent to the browser movie decoder');
    const href=$('#download-job').getAttribute('href'),filename=$('#download-job').download;
    steps.push('native_export_dialog_completed_actual_ffv1_master');
    click('#download-job');steps.push('clicked_real_native_master_download');
    return {passed:true,expect_download:true,steps,project_id:projectId,download_href:href,download_filename:filename,
      processed_frame_url:frameUrl,job_label:$('#job-label').textContent,elapsed_ms:Math.round(performance.now()-began)};
  } catch(error) {
    return {passed:false,steps,error:String(error),elapsed_ms:Math.round(performance.now()-began)};
  }
})();

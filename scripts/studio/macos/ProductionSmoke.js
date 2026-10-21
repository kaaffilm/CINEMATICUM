// Actual WKWebView controls; Python supplies PRODUCTION_TEST and checks decoded
// output independently. These colored video/audio sources are ENGINE TESTS.
return await (async()=>{
  const began=performance.now(),deadline=began+11000,steps=[];
  const $=selector=>document.querySelector(selector),all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostics=()=>'; production='+($('[data-production-status]')?.textContent||'')+'; toast='+($('#toast')?.textContent||'')+'; job='+($('#job-label')?.textContent||'');
  async function until(predicate,label,maximum=1800){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(25);}throw Error(label+diagnostics());}
  function click(selector){const element=$(selector);if(!element||element.disabled)throw Error('Unavailable control '+selector+diagnostics());element.click();}
  function set(selector,value){const element=$(selector);if(!element||element.disabled)throw Error('Unavailable field '+selector);element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  const clips=()=>all('.timeline-clip[data-type="clip"]');
  function inputPlan(){const transfer=new DataTransfer();transfer.items.add(new File([JSON.stringify(PRODUCTION_TEST.plan)],'ENGINE_TEST_shotlist.json',{type:'application/json'}));const input=$('[data-production-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  const dialogOpen=()=>Boolean($('.cinematicum-production')?.open);
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&clips().length===1&&$('#production-button'),'Production fixture did not bootstrap',3300);
    const originalID=clips()[0].dataset.clip,projectID=$('#project-select').value;
    click('#production-button');inputPlan();
    await until(()=>all('[data-production-row]').length===2&&!$('[data-production-save]').disabled,'Selected shot plan did not load');
    if(!$('[data-production-conform]').disabled||all('.shot-status.error').length!==2)throw Error('Missing bindings must block cut assembly.');
    if(clips().length!==1||clips()[0].dataset.clip!==originalID)throw Error('Plan review changed the current edit.');
    steps.push('read_plan_and_block_missing_sources');
    click('[data-production-save]');await until(()=>!dialogOpen(),'Unresolved plan was not applied as a settings edit');
    if(clips().length!==1||clips()[0].dataset.clip!==originalID||$('#save-state').textContent!=='UNSAVED')throw Error('Saving plan replaced footage or committed without Save.');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Unresolved plan did not save');
    const response=await fetch(`/api/projects/${encodeURIComponent(projectID)}`),savedPlan=await response.json();
    if(!response.ok||savedPlan.settings?.production?.plan?.shots?.length!==2||savedPlan.clips?.[0]?.id!==originalID)throw Error('Unresolved plan was not persisted with the existing cut.');
    click('#production-button');await until(()=>all('[data-production-row]').length===2&&!$('[data-production-match]').disabled,'Persisted unresolved plan did not reopen');
    if(!$('[data-production-conform]').disabled)throw Error('Reopening an unresolved plan made it renderable.');
    steps.push('persist_unresolved_plan_without_replacing_edit');
    click('[data-production-match]');
    if($('[data-production-source="0"]').value!==PRODUCTION_TEST.red_id||$('[data-production-source="1"]').value!==PRODUCTION_TEST.blue_id)throw Error('Explicit filename matching selected different assets.');
    for(const invalid of ['', '1.5']){
      set('[data-production-in="0"]',invalid);
      if(!$('[data-production-review]').disabled||!$('[data-production-save]').disabled||!$('[data-production-preview-shot="0"]').disabled||!$('[data-production-conform]').disabled)throw Error('Blank/fractional source ranges must stay invalid, without coercing them to frame zero.');
    }
    steps.push('reject_blank_and_fractional_source_ranges');
    set('[data-production-out="0"]',6);set('[data-production-in="1"]',3);
    if(Number($('[data-production-in="0"]').value)!==2||Number($('[data-production-out="1"]').value)!==7)throw Error('Source in/out editing changed the planned length.');
    click('[data-production-review]');await until(()=>!$('[data-production-conform]').disabled&&all('.shot-status.ready').length===2,'Real selected source handles did not validate');
    if(!$('[data-production-row-status="0"]').textContent.includes('2 head / 6 tail'))throw Error('Actual first-take handles were not displayed.');
    steps.push('bind_actual_imported_takes_and_validate_handles');
    click('[data-production-preview-shot="0"]');
    await until(()=>!$('[data-production-preview]').hidden&&$('[data-production-video]').readyState>=2&&!$('[data-production-video]').seeking&&Math.abs($('[data-production-video]').currentTime-2/24)<.03,'Selected take preview did not decode and seek',2100);
    const previewSource=$('[data-production-video]').getAttribute('src');
    if(!previewSource.endsWith('/media/'+PRODUCTION_TEST.red_id))throw Error('Preview selected the wrong take.');
    click('[data-production-stop-preview]');
    if($('[data-production-video]').hasAttribute('src'))throw Error('Closing source preview retained decoder ownership.');
    steps.push('preview_source_trim_and_release_decoder');
    click('[data-production-export]');await until(()=>!$('[data-production-download]').hidden,'Shot requirements export did not finish');
    const planDownload=$('[data-production-download]').getAttribute('href');
    if(!planDownload.startsWith(`/api/projects/${encodeURIComponent(projectID)}/exports/`)||!/\/[a-f0-9]{32}-shot-plan\.json\?download=1$/.test(planDownload))throw Error('Portable plan is not an actual project-owned attachment.');
    const exportedResponse=await fetch(planDownload);
    if(!exportedResponse.ok||!exportedResponse.headers.get('content-disposition')?.includes('attachment'))throw Error('Portable shot requirements did not download as an attachment.');
    const exportedText=await exportedResponse.text(),exportedPlan=JSON.parse(exportedText);
    if(exportedPlan.runtime_frames!==8||exportedPlan.shots?.length!==2||exportedPlan.shots[1].start_frame!==4)throw Error('Portable shot requirements lost exact ordering/timing.');
    steps.push('download_exact_portable_plan');
    click('[data-production-conform]');await until(()=>!dialogOpen()&&clips().length===2,'Planned cut was not assembled');
    const appliedIDs=clips().map(clip=>clip.dataset.clip);
    if(appliedIDs.includes(originalID)||$('#save-state').textContent!=='UNSAVED')throw Error('Assembly did not create an unsaved cut.');
    click('#undo-button');if(clips().length!==1||clips()[0].dataset.clip!==originalID)throw Error('One Undo did not restore the prior edit.');
    click('#redo-button');if(clips().length!==2||clips().some(clip=>!appliedIDs.includes(clip.dataset.clip)))throw Error('Redo did not restore the exact planned cut.');
    steps.push('assemble_once_and_undo_redo');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Planned cut did not save');
    click('#export-button');click('[data-export="prores"]');
    await until(()=>$('#job-label')?.textContent==='ProRes export complete','Actual planned-cut export failed',3100);
    const download=$('#download-job').getAttribute('href');
    if(!download?.includes('/exports/')||!download.includes('.mov'))throw Error('Export did not return an actual MOV artifact.');
    steps.push('save_and_render_actual_prores_cut');
    click('#production-button');await until(()=>all('.shot-status.ready').length===2&&!$('[data-production-conform]').disabled,'Saved plan/take bindings did not reopen');
    if(Number($('[data-production-in="0"]').value)!==2||Number($('[data-production-in="1"]').value)!==3)throw Error('Saved source trims changed.');
    const bounds=$('.cinematicum-production').getBoundingClientRect();
    if(bounds.width<700||bounds.height<300)throw Error('Production controls were not visibly laid out.');
    return {passed:true,steps,project_id:projectID,original_clip_id:originalID,applied_clip_ids:appliedIDs,
      preview_source:previewSource,exported_plan:exportedPlan,plan_export_href:planDownload,plan_download_bytes:new TextEncoder().encode(exportedText).length,export_href:download,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,error:String(error),production_status:$('[data-production-status]')?.textContent||'',toast:$('#toast')?.textContent||'',job_detail:$('#job-detail')?.textContent||'',elapsed_ms:Math.round(performance.now()-began)};}
})();

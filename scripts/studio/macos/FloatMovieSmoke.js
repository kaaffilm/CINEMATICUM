// Shipped controls only. The coordinator independently verifies retained media.
return await (async()=>{
  const deadline=performance.now()+12000,checks=[], $=s=>document.querySelector(s);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail=()=>'; toast='+($('#toast')?.textContent||'')+'; job='+($('#job-detail')?.textContent||'');
  function require(value,label){checks.push({name:label,passed:Boolean(value)});if(!value)throw Error(label+detail());}
  function control(selector){const e=$(selector);if(!e||e.disabled||e.closest('[inert]'))throw Error('Unavailable '+selector+detail());e.scrollIntoView({block:'nearest'});return e;}
  function click(selector){control(selector).click();}
  function set(selector,value){const e=control(selector);if(e.type==='checkbox')e.checked=Boolean(value);else e.value=String(value);e.dispatchEvent(new Event('change',{bubbles:true}));}
  async function until(test,label,maximum=4000){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(test())return;await sleep(30);}throw Error(label+detail());}
  async function open(){click('#export-button');await until(()=>$('[data-float-setting="output_space"]'),'Real OCIO catalog unavailable');}
  try{
    const id=FLOAT_TEST.project_id;
    await until(()=>$('#project-select')&&!$('#project-select').disabled&&[...$('#project-select').options].some(o=>o.value===id),'Fixture bootstrap missing',5000);
    if($('#project-select').value!==id)set('#project-select',id);
    await until(()=>$('#project-select').value===id&&!$('#project-select').disabled&&$('#viewer-project').textContent==='ENGINE TEST float native','Exact fixture did not open');
    require(document.querySelectorAll('.timeline-clip[data-type="clip"]').length===2,'actual_two_layer_timeline');
    await open();require($('#movie-precision').value==='float32'&&!$('[data-export="master32"]').disabled&&$('[data-export="master16"]').disabled,'float_export_profile_gate');
    if(FLOAT_TEST.phase==='author'){
      set('[data-float-setting="output_space"]','ACES2065-1');click('#close-export');click('#undo-button');await open();
      require($('[data-float-setting="output_space"]').value==='ACEScg','color_setting_undo');
      click('#close-export');click('#redo-button');await open();
      require($('[data-float-setting="output_space"]').value==='ACES2065-1','color_setting_redo');
      set('#movie-transparent',false);click('#close-export');click('#undo-button');await open();
      require($('#movie-transparent').checked,'alpha_setting_independent_undo');
      require(document.querySelectorAll('[data-float-clip]').length===2,'both_source_spaces_editable');
      click('#close-export');click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Float project save failed');
      set('#project-select',FLOAT_TEST.sentinel_id);await until(()=>$('#viewer-project').textContent.includes('sentinel')&&!$('#project-select').disabled,'Sentinel did not open');
      set('#project-select',id);await until(()=>$('#viewer-project').textContent==='ENGINE TEST float native'&&!$('#project-select').disabled,'Saved float project did not reopen');
      await open();require($('#movie-precision').value==='float32'&&$('#movie-transparent').checked&&$('[data-float-setting="output_space"]').value==='ACES2065-1','saved_settings_reopen');
      click('#close-export');await until(()=>!$('#processed-frame').hidden&&$('#processed-frame').complete&&$('#processed-frame').naturalWidth===32,'Actual float display derivative missing',5000);
      require($('#frame-status').textContent==='Rendered frame 0 · export graph','processed_ocio_preview_visible');
      return {passed:true,checks,project_id:id,processed_frame_url:new URL($('#processed-frame').src,location.href).pathname};
    }
    require($('[data-float-setting="output_space"]').value==='ACES2065-1','export_uses_saved_ocio_output');
    click('[data-export="master32"]');await until(()=>['Float EXR master complete','Job failed','Job cancelled'].includes($('#job-label')?.textContent),'Float owned export did not terminate',10000);
    require($('#job-label').textContent==='Float EXR master complete','actual_owned_float_master_complete');
    await until(()=>!$('#download-job').hidden&&$('#download-job').getAttribute('href')?.includes('.zip?download=1'),'Master download missing');
    require($('#view-job').hidden&&$('#rendered-preview').disabled,'float_zip_not_sent_to_movie_decoder');
    const href=$('#download-job').getAttribute('href'),filename=$('#download-job').download;click('#download-job');
    return {passed:true,expect_download:true,checks,project_id:id,download_href:href,download_filename:filename};
  }catch(error){return{passed:false,checks,error:String(error)};}
})();

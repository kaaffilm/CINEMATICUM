// Actual shipped controls and Store jobs. The owner fixture deliberately blocks
// setup until Cancel; this is an interface/ownership test, never model evidence.
return await (async()=>{
  const began=performance.now(),deadline=began+11000,steps=[],result={fixture:'ENGINE TEST — no model execution'};
  const $=selector=>document.querySelector(selector),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail=()=>'; toast='+($('#toast')?.textContent||'')+'; phase='+($('[data-generation-phase]')?.textContent||'')+'; error='+($('[data-generation-error]')?.textContent||'');
  function require(value,label){if(!value)throw Error(label+detail());}
  function control(selector){const value=$(selector);require(value&&!value.disabled&&!value.hidden,'Unavailable control '+selector);value.scrollIntoView({block:'nearest',inline:'nearest'});return value;}
  function click(selector){control(selector).click();}
  function set(selector,value,event='input'){const element=control(selector);element.value=String(value);element.dispatchEvent(new Event(event,{bubbles:true}));}
  async function until(predicate,label,maximum=2000){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(40);}throw Error(label+detail());}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Project did not bootstrap',3500);
    result.project_id=$('#project-select').value;click('[data-mode="generate"]');click('#manage-generation');
    await until(()=>$('#managed-generation-dialog')?.open&&!$('[data-generation-setup]')?.disabled,'Owned generation controls did not load');
    require(!$('#generate-button')||$('#generate-button').disabled,'Offline fixture claimed generation availability');
    require($('[data-generation-state]').textContent==='Not installed','Fixture unexpectedly claimed an installed engine');
    set('[data-generation-canvas]','272x480','change');set('[data-generation-length]',9);set('[data-generation-steps]',4);set('[data-generation-fps]',8);set('[data-generation-cfg]',5);
    require($('[data-generation-duration]').textContent.includes('272 × 480 · 9 frames · 1.13 seconds'),'Shot settings did not update');
    set('[data-generation-length]',10);require($('[data-generation-workflow]').disabled,'Unsupported 4n+1 length was accepted');set('[data-generation-length]',9);
    click('[data-generation-workflow]');await until(()=>$('[data-generation-workflow-status]')?.textContent==='These settings are saved in this project.','Real project workflow did not save');
    require($('#workflow-label')?.textContent==='Workflow selected.','The saved workflow did not reach Generate');steps.push('actual_shot_settings_validation_and_project_workflow_save');
    click('[data-generation-setup]');await until(()=>$('[data-generation-cancel]')&&!$('[data-generation-cancel]').hidden&&!$('[data-generation-cancel]').disabled,'Modal did not expose the owned job cancellation');
    require($('[data-generation-setup]').disabled&&$('[data-generation-start]').disabled,'Duplicate setup/start was not disabled');
    require(!$('[data-generation-close]').disabled,'Close was blocked during setup');click('[data-generation-close]');require(!$('#managed-generation-dialog').open,'Setup modal would not close');
    await until(()=>$('#job-label')?.textContent==='Installing local generation','Closing the modal lost the running job');
    click('#manage-generation');await until(()=>$('#managed-generation-dialog').open&&!$('[data-generation-cancel]').disabled,'Reopening did not retain the owned job');
    click('[data-generation-cancel]');await until(()=>$('#job-label')?.textContent==='Job cancelled'&&!$('[data-generation-setup]').disabled,'Cancellation did not terminate the owned setup job',3000);
    require($('[data-generation-cancel]').hidden,'Terminal cancellation left a live cancel control');
    require(!$('#generate-button')||$('#generate-button').disabled,'Cancelled setup claimed a ready generator');steps.push('modal_close_reopen_and_cancellation_preserve_own_job');
    result.workflow_summary=$('[data-generation-duration]').textContent;result.phase=$('[data-generation-phase]').textContent;result.job_label=$('#job-label').textContent;
    return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),elapsed_ms:Math.round(performance.now()-began)};}
})();

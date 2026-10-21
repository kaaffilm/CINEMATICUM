// Synthetic native acceptance: mutate through DOM, then restart in a new stage.
return await(async()=>{
  const $=s=>document.querySelector(s),steps=[],sleep=ms=>new Promise(r=>setTimeout(r,ms));
  async function until(fn,label,ms=3000){const end=performance.now()+ms;while(performance.now()<end){if(fn())return;await sleep(40)}throw Error(label+'; '+($('#toast')?.textContent||''));}
  function click(selector){const e=$(selector);if(!e||e.disabled)throw Error('Unavailable '+selector);e.click();}
  function field(name,value){const e=$('[data-field="'+name+'"]');if(!e)throw Error('Missing field '+name);e.value=String(value);e.dispatchEvent(new Event(e.type==='range'?'input':'change',{bubbles:true}));if(e.type==='range')e.dispatchEvent(new Event('change',{bubbles:true}));}
  const count=type=>document.querySelectorAll('.timeline-clip[data-type="'+type+'"]').length;
  try {
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST recovery')&&$('.media-item[data-asset]'),'Boot failed',4500);
    if(RECOVERY_TEST.stage==='checkpoint'){
      const asset=$('.media-item[data-asset]');
      for(let index=0;index<40;index++){asset.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,button:0}));if(count('clip')!==1)throw Error('Clip admission failed');click('#delete-button');if(count('clip')!==0)throw Error('Clip deletion failed');}
      steps.push('forty_native_add_delete_cycles');
      asset.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,button:0}));
      click('#add-title');field('text','ENGINE TEST recovery title');field('size',12);field('duration',12);field('fade',2);
      await until(()=>$('#recovery-state').textContent==='Recovery checkpointed','Unsaved edit never checkpointed',4500);
      if($('#save-state').textContent!=='UNSAVED')throw Error('Checkpoint unexpectedly committed the edit');
      steps.push('unsaved_title_and_clip_durably_checkpointed');
    }else{
      if(count('clip')||count('title'))throw Error('Recovery silently replaced the saved project');
      await until(()=>$('#recovery-button').textContent.includes('Recover'),'Saved checkpoint not offered');
      click('#recovery-button');await until(()=>$('#recovery-dialog').open&&$('[data-restore="draft"]'),'Recovery choices absent');
      click('[data-restore="draft"]');await until(()=>!$('#recovery-dialog').open&&count('clip')===1&&count('title')===1,'Recovery did not restore authored objects');
      if($('#save-state').textContent!=='UNSAVED')throw Error('Recovery must remain unsaved');
      click('#undo-button');if(count('clip')||count('title'))throw Error('Recovery undo failed');
      click('#redo-button');if(count('clip')!==1||count('title')!==1)throw Error('Recovery redo failed');
      steps.push('fresh_browser_recovery_one_undo_and_redo');
      click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Recovered project did not save',4500);
      click('#preview-render');await until(()=>$('#job-label').textContent==='Render complete','Recovered edit did not render',6000);
      await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2,'Recovered rendered movie did not decode');
      steps.push('recovered_title_rasterized_saved_and_exported');
    }
    return {passed:true,stage:RECOVERY_TEST.stage,steps,clips:count('clip'),titles:count('title'),save_state:$('#save-state').textContent,recovery_state:$('#recovery-state').textContent};
  }catch(error){return {passed:false,stage:RECOVERY_TEST.stage,steps,error:error.message};}
})();

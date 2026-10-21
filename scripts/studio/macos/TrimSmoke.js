// Isolated native acceptance. The Python harness injects TRIM_TEST.stage.
// All edits, undo, saving and export use actual CINEMATICUM DOM controls.
return await(async()=>{
  const steps=[],metrics={},$=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
  async function until(fn,label,timeout=2500){const end=performance.now()+timeout;while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(label+'; '+($('#toast')?.textContent||''));}
  function reach(selector){
    const e=$(selector);if(!e)throw Error('Missing '+selector);
    for(let p=e.parentElement;p;p=p.parentElement){
      if(!p.matches('.timeline-scroll,.timeline-tools,.inspector,dialog'))continue;
      const r=e.getBoundingClientRect(),b=p.getBoundingClientRect();
      if(r.top<b.top+2)p.scrollTop+=r.top-b.top-2;else if(r.bottom>b.top+p.clientHeight-2)p.scrollTop+=r.bottom-b.top-p.clientHeight+2;
      if(r.left<b.left+2)p.scrollLeft+=r.left-b.left-2;else if(r.right>b.left+p.clientWidth-2)p.scrollLeft+=r.right-b.left-p.clientWidth+2;
    }
    const r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
    if(r.width<2||r.height<2||r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5||(hit!==e&&!e.contains(hit)))throw Error('Unreachable '+selector);
    return e;
  }
  function click(selector){const e=reach(selector);if(e.disabled)throw Error('Disabled '+selector);e.click();}
  function set(selector,value,event='input'){const e=reach(selector);if(e.disabled)throw Error('Disabled '+selector);e.value=String(value);e.dispatchEvent(new Event(event,{bubbles:true}));}
  function select(id){
    const e=reach('.timeline-clip[data-clip="'+id+'"]'),r=e.getBoundingClientRect(),event={bubbles:true,button:0,pointerId:92,isPrimary:true,clientX:r.left+r.width/2,clientY:r.top+r.height/2};
    e.dispatchEvent(new PointerEvent('pointerdown',event));window.dispatchEvent(new PointerEvent('pointerup',event));
    if(!$('.timeline-clip[data-clip="'+id+'"]')?.classList.contains('selected'))throw Error('Timeline did not select '+id);
  }
  function timings(){
    const result=[];for(const id of ['before','middle','after']){select(id);result.push(['start','duration','in'].map(key=>Number($('[data-field="'+key+'"]').value)));}select('middle');return result;
  }
  function same(actual,expected,label){if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(label+': '+JSON.stringify(actual));}
  function plan(kind,delta){click('#trim-edit-button');if(!$('#trim-edit-dialog').open)throw Error('Trim controls did not open');set('#trim-edit-kind',kind,'change');set('#trim-edit-delta',delta);return $('#trim-edit-summary').textContent;}
  function apply(){click('#apply-trim-edit');if($('#trim-edit-dialog').open)throw Error('Trim edit did not commit');}
  const baseline=[[0,8,8],[8,8,24],[16,8,40]];
  const expected={slip:[[0,8,8],[8,8,27],[16,8,40]],slide:[[0,10,8],[10,8,24],[18,6,42]],roll:[[0,8,8],[8,6,24],[14,10,38]]};
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&document.querySelectorAll('.timeline-clip').length===3,'Fixture did not bootstrap',4000);
    set('#timeline-zoom',160);same(timings(),baseline,'Fixture timing');
    if(!$('#undo-button').disabled)throw Error('Selection or zoom unexpectedly created history');
    const stage=TRIM_TEST.stage;
    if(stage==='guards'){
      let summary=plan('slip',999);if(!summary.includes('Applied offset: +48')||!summary.includes('Limited by'))throw Error('Positive source handle was not reported accurately');
      apply();same(timings(),[[0,8,8],[8,8,72],[16,8,40]],'Positive source clamp');click('#undo-button');same(timings(),baseline,'Clamp undo');if(!$('#undo-button').disabled)throw Error('Clamp created multiple undo entries');
      summary=plan('slip',-999);if(!summary.includes('Applied offset: -24')||!summary.includes('Limited by'))throw Error('Negative source handle was not reported accurately');
      apply();same(timings(),[[0,8,8],[8,8,0],[16,8,40]],'Negative source clamp');click('#undo-button');same(timings(),baseline,'Negative clamp undo');if(!$('#undo-button').disabled)throw Error('Negative clamp created multiple undo entries');
      plan('slip',0);if(!$('#apply-trim-edit').disabled)throw Error('Zero trim should not create a history entry');click('#close-trim-edit');
      steps.push('both_source_handle_limits_and_zero_noop');
      click('[data-track-control="locked"][data-track-id="0"]');if($('[data-track-control="locked"][data-track-id="0"]').getAttribute('aria-pressed')!=='true')throw Error('Track did not lock');
      click('#trim-edit-button');if($('#trim-edit-dialog').open||! /unlock|locked/i.test($('#toast')?.textContent||''))throw Error('Locked track allowed a trim');
      click('#undo-button');same(timings(),baseline,'Locked trim changed timing');if(!$('#undo-button').disabled)throw Error('Rejected locked trim created an undo entry');
      if($('[data-track-control="locked"][data-track-id="0"]').getAttribute('aria-pressed')!=='false')throw Error('Lock undo did not restore track');
      steps.push('locked_track_rejected_without_edit_history');
    }else{
      if(!expected[stage])throw Error('Unknown trim acceptance stage');
      const delta={slip:3,slide:2,roll:-2}[stage],summary=plan(stage,delta);metrics.plan=summary;
      if(!summary.includes('Applied offset: '+(delta>0?'+':'')+delta+' frames.'))throw Error('Trim preview reports the wrong offset');
      apply();same(timings(),expected[stage],'Applied '+stage);if($('#undo-button').disabled)throw Error('Trim has no undo');
      click('#undo-button');same(timings(),baseline,'Undo '+stage);if(!$('#undo-button').disabled)throw Error('One trim created more than one undo entry');
      click('#redo-button');same(timings(),expected[stage],'Redo '+stage);if(!$('#redo-button').disabled)throw Error('Redo did not consume the one edit');
      steps.push(stage+'_three_clip_timing_one_undo_and_redo');
    }
    metrics.saved_timing=timings();click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Trimmed timeline did not save');
    steps.push('actual_project_saved');
    if(stage!=='guards'){
      click('#export-button');click('[data-export="h264"]');
      await until(()=>$('#job-label').textContent==='Render complete'&&!$('#download-job').hidden,'Actual timeline export did not complete',6500);
      if($('#job-indicator').classList.contains('error'))throw Error('Actual timeline render failed');
      metrics.download=$('#download-job').getAttribute('href');if(!metrics.download?.includes('/exports/'))throw Error('No real exported movie download');
      reach('#download-job');steps.push('actual_h264_export_through_ui');
    }
    return {passed:true,stage,steps,metrics};
  }catch(error){return {passed:false,stage:TRIM_TEST.stage,steps,metrics,error:error.message,toast:$('#toast')?.textContent,job:$('#job-label')?.textContent,job_detail:$('#job-detail')?.textContent};}
})();

// Real shipped controls submit a bounded actual FFmpeg master job. No fake job
// state, patched API or worker sleep is introduced by this acceptance fixture.
return await (async()=>{
  const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const until=async(fn,message,ms)=>{const end=performance.now()+ms;while(performance.now()<end){if(fn())return;await sleep(40);}throw Error(message);};
  await until(()=>$('#project-select')&&!$('#project-select').disabled&&[...$('#project-select').options].some(o=>o.value===QUIT_TEST.project_id),'Actual quit fixture did not bootstrap',6000);
  if($('#project-select').value!==QUIT_TEST.project_id){$('#project-select').value=QUIT_TEST.project_id;$('#project-select').dispatchEvent(new Event('change',{bubbles:true}));}
  await until(()=>$('#project-select').value===QUIT_TEST.project_id&&!$('#project-select').disabled&&document.querySelector('.timeline-clip'),'Actual quit fixture did not open',3000);
  $('#export-button').click();
  const master=$('[data-export="master16"]');
  if(!master||master.disabled)throw Error('Actual FFV1 master control is unavailable');
  master.click();
  await until(()=>typeof state!=='undefined'&&state.job?.kind==='render'&&state.job?.state==='running'&&Number(state.job.progress)>0,'Actual FFmpeg render did not make progress',15000);
  const jobId=state.job.id;
  // Create one ordinary unsaved edit after render submission; production quit
  // must save it before presenting its actual active-job alert.
  $('#export-button').click();
  const transparent=$('#movie-transparent');
  if(!transparent||transparent.disabled||transparent.checked)throw Error('Unexpected initial transparency state');
  transparent.checked=true;transparent.dispatchEvent(new Event('change',{bubbles:true}));
  $('#close-export').click();
  if(!state.dirty)throw Error('Shipped transparency control did not create an unsaved edit');
  const actual=await api('/api/jobs/'+encodeURIComponent(jobId));
  if(actual.state!=='running'||!(actual.progress>0))throw Error('Actual render finished before ordinary-quit acceptance');
  return {passed:true,project_id:QUIT_TEST.project_id,job_id:jobId,job_state:actual.state,job_progress:actual.progress,dirty_before_quit:state.dirty};
})();

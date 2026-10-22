// A second real job submitted through shipped controls verifies admission stayed
// open after Keep Working. The first completed master remains on disk unchanged.
return await (async()=>{
  const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
  if(state.project?.id!==QUIT_TEST.project_id||state.job?.id!==QUIT_FIRST_JOB_ID||state.job?.state!=='completed')
    throw Error('First actual render has not completed in its original project');
  $('#export-button').click();
  const master=$('[data-export="master16"]');
  if(!master||master.disabled||!$('#movie-transparent').checked)throw Error('Saved second-export controls are unavailable');
  master.click();
  const end=performance.now()+15000;
  while(performance.now()<end){
    const job=state.job;
    if(job?.id!==QUIT_FIRST_JOB_ID&&job?.kind==='render'){
      if(['failed','cancelled','interrupted','completed'].includes(job.state))throw Error('Second render ended before actual native quit: '+job.state);
      if(job.state==='running'&&Number(job.progress)>0){
        const actual=await api('/api/jobs/'+encodeURIComponent(job.id));
        if(actual.state!=='running'||!(actual.progress>0))throw Error('Second actual render ended before ordinary quit');
        return {passed:true,project_id:QUIT_TEST.project_id,job_id:actual.id,job_state:actual.state,job_progress:actual.progress,first_job_id:QUIT_FIRST_JOB_ID};
      }
    }
    await sleep(40);
  }
  throw Error('Second actual FFmpeg render was not admitted and making progress');
})();

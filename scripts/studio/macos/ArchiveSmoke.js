// Actual WKWebView archive/download/File-upload/restore controls. Python creates
// isolated ENGINE TEST media, observes the real restore call and checks pixels.
return await(async()=>{
  const began=performance.now(),deadline=began+11800,steps=[];
  const $=selector=>document.querySelector(selector),all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostic=()=>'; archive='+($('[data-archive-status]')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,maximum=1800){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(25);}throw Error(label+diagnostic());}
  function click(selector){const element=$(selector);if(!element||element.disabled||element.hidden)throw Error('Unavailable '+selector+diagnostic());element.click();}
  function field(name,value){const element=$('[data-field="'+name+'"]');if(!element||element.disabled)throw Error('Unavailable inspector '+name);element.value=String(value);element.dispatchEvent(new Event(element.type==='range'?'input':'change',{bubbles:true}));if(element.type==='range')element.dispatchEvent(new Event('change',{bubbles:true}));}
  const count=type=>all('.timeline-clip[data-type="'+type+'"]').length;
  async function readProject(id){const response=await fetch('/api/projects/'+encodeURIComponent(id),{cache:'no-store'});if(!response.ok)throw Error('Could not read actual saved project');return response.text();}
  async function render(label,projectID){
    const previous=$('#download-job')?.getAttribute('href');
    click('#export-button');click('[data-export="prores"]');
    await until(()=>$('#job-label')?.textContent==='ProRes export complete'&&!$('#download-job').hidden&&$('#download-job').getAttribute('href')!==previous&&$('#download-job').getAttribute('href').includes('/'+projectID+'/exports/'),label+' did not export actual ProRes',2700);
    return $('#download-job').getAttribute('href');
  }
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST archive')&&$('.media-item[data-asset]')&&$('#archive-button'),'Archive fixture did not bootstrap',3300);
    const sourceID=$('#project-select').value,asset=$('.media-item[data-asset]'),assetID=asset.dataset.asset;
    asset.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,button:0}));
    await until(()=>count('clip')===1,'Actual source was not added to the timeline');
    field('duration',8);
    click('#add-title');field('text','ENGINE TEST archive');field('size',12);field('duration',8);field('fade',1);
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Media/title edit did not save',2500);
    const authored=JSON.parse(await readProject(sourceID));
    if(authored.clips?.length!==1||authored.clips[0].duration!==8||authored.titles?.length!==1||!authored.titles[0].asset_id||authored.titles[0].text!=='ENGINE TEST archive')throw Error('Actual saved edit lacks its rasterized title or exact source trim');
    steps.push('author_and_save_actual_media_and_raster_title');
    const originalRender=await render('Original edit',sourceID);
    steps.push('render_original_prores_cut');
    click('#archive-button');await until(()=>$('.cinematicum-archive')?.open,'Archive dialog did not open');
    const bounds=$('.cinematicum-archive').getBoundingClientRect();
    if(bounds.width<450||bounds.height<250)throw Error('Archive controls are not visibly laid out');
    if(!$('[data-archive-restore]').disabled)throw Error('Restore must require a selected actual file');
    click('[data-archive-export]');
    await until(()=>!$('.cinematicum-archive').open&&$('#job-label').textContent==='Project archive ready'&&!$('#download-job').hidden&&/\.zip(?:\?|$)/.test($('#download-job').getAttribute('href')),'Archive job did not produce its actual ZIP download',2200);
    const archiveHref=$('#download-job').getAttribute('href'),archiveName=$('#download-job').download;
    const response=await fetch(archiveHref,{cache:'no-store'});
    if(!response.ok)throw Error('The completed archive download could not be read');
    const blob=await response.blob(),signature=new Uint8Array(await blob.slice(0,4).arrayBuffer());
    if(blob.size<1000||signature.join(',')!=='80,75,3,4')throw Error('Download is not the actual nonempty ZIP archive');
    const originalBeforeRestore=await readProject(sourceID);
    steps.push('download_real_verified_project_archive');
    click('#archive-button');await until(()=>$('.cinematicum-archive')?.open,'Archive restore controls did not open');
    const transfer=new DataTransfer();transfer.items.add(new File([blob],archiveName||'ENGINE_TEST.cinematicum.zip',{type:'application/zip'}));
    const file=$('[data-archive-file]');file.files=transfer.files;file.dispatchEvent(new Event('change',{bubbles:true}));
    if($('[data-archive-restore]').disabled)throw Error('Actual downloaded archive did not enable restore');
    click('[data-archive-restore]');
    await until(()=>!$('.cinematicum-archive').open&&$('#job-label').textContent==='Project restored'&&!$('#open-restored-project').hidden,'Actual File upload/restore job failed',2400);
    const restoredID=$('#open-restored-project').dataset.projectId;
    if(!/^[a-f0-9]{32}$/.test(restoredID)||restoredID===sourceID||$('#project-select').value!==sourceID)throw Error('Restore must create a new identity and preserve the currently open original');
    if(await readProject(sourceID)!==originalBeforeRestore)throw Error('Restoring modified the saved original project');
    steps.push('upload_real_file_restore_new_identity_keep_original');
    click('#open-restored-project');
    await until(()=>$('#project-select').value===restoredID&&count('clip')===1&&count('title')===1,'Explicit Open restored project did not load the restored edit');
    const restored=JSON.parse(await readProject(restoredID));
    if(restored.clips[0].asset_id!==assetID||restored.titles[0].asset_id!==authored.titles[0].asset_id||restored.archive_restore?.source_project_id!==sourceID)throw Error('Restored media/title references or source provenance changed');
    steps.push('explicitly_open_restored_edit_with_all_media_relationships');
    const restoredRender=await render('Restored edit',restoredID);
    if(await readProject(sourceID)!==originalBeforeRestore)throw Error('Opening/rendering the restored project modified the original');
    steps.push('render_restored_prores_cut');
    click('#archive-button');await until(()=>$('.cinematicum-archive')?.open,'Restored archive controls did not reopen');
    return {passed:true,steps,source_project_id:sourceID,restored_project_id:restoredID,asset_id:assetID,title_asset_id:authored.titles[0].asset_id,
      source_render_href:originalRender,restored_render_href:restoredRender,archive_href:archiveHref,archive_filename:archiveName,archive_bytes:blob.size,
      elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,error:String(error),job_label:$('#job-label')?.textContent||'',job_detail:$('#job-detail')?.textContent||'',
    archive_status:$('[data-archive-status]')?.textContent||'',toast:$('#toast')?.textContent||'',elapsed_ms:Math.round(performance.now()-began)};}
})();

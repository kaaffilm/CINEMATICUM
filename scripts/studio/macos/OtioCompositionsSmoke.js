// Real FileList import, ordinary controls, completed downloads and exact-frame
// pixels. Shared by native WKWebView and the explicit Chromium adapter.
return await (async()=>{
  const cfg=/* ENGINE_TEST_CONFIG */ {},began=performance.now(),deadline=began+13000,steps=[],metrics={};
  const $=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)],sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const diagnostic=()=>'; interchange='+($('[data-interchange-status]')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,maximum=2200){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(25);}throw Error(label+diagnostic());}
  function click(s){const e=$(s);if(!e||e.disabled||e.hidden)throw Error('Unavailable '+s+diagnostic());e.click();}
  function choose(s,v){const e=$(s);if(!e||e.disabled)throw Error('Unavailable '+s);e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  function file(selector,name,value,type='application/json'){const transfer=new DataTransfer();transfer.items.add(new File([value],name,{type}));const input=$(selector);input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  async function saved(id){const response=await fetch('/api/projects/'+id,{cache:'no-store'});if(!response.ok)throw Error('Saved project not readable');return response.json();}
  // Archive JSON is canonically key-sorted; object insertion order is not
  // authoring state. Array order, values and every operator field still match.
  function canonical(value){return JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);}
  async function select(id){if($('#project-select').value!==id){choose('#project-select',id);await until(()=>$('#project-select').value===id&&/^(LOCAL PROJECT|SAVED LOCALLY)$/.test($('#save-state').textContent)&&!$('#viewer-project').textContent.includes('sentinel'),'Saved project did not open');}}
  async function render(id){const previous=$('#download-job')?.getAttribute('href');click('#export-button');click('[data-export="prores"]');await until(()=>$('#job-label').textContent==='ProRes export complete'&&!$('#download-job').hidden&&$('#download-job').getAttribute('href')!==previous&&$('#download-job').getAttribute('href').includes('/'+id+'/exports/'),'Actual ProRes export failed',5000);const href=$('#download-job').getAttribute('href');click('#download-job');return href;}
  function operatorCounts(document){const counts={dissolves:0,timewarps:0};function visit(v){if(!v||typeof v!=='object')return;if(v.OTIO_SCHEMA==='Transition.1')counts.dissolves++;if(v.OTIO_SCHEMA==='LinearTimeWarp.1')counts.timewarps++;for(const [key,value] of Object.entries(v))if(key!=='metadata'){if(Array.isArray(value))value.forEach(visit);else visit(value);}}visit(document);return counts;}
  try{
    await until(()=>$('#project-select')?.options.length>=2&&$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('#archive-button'),'Actual test project did not bootstrap',4500);
    await select(cfg.project_id);
    if(cfg.operation==='author'){
      if(!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]'))throw Error('Original cut missing before import');
      const raw=await (await fetch('/ENGINE_TEST_timeline.otio',{cache:'no-store'})).text();
      click('#interchange-button');click('[data-interchange-tab="import"]');file('[data-interchange-file]','ENGINE_TEST_public_composition.otio',raw);
      await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===2,'Actual OTIO references not available');
      for(const select of all('[data-interchange-reference]')){const name=select.closest('label').querySelector('small').textContent;const row=cfg.truth.media.find(row=>name.includes('ENGINE_TEST_'+row.name+'.mov'));if(!row)throw Error('Unexpected source reference');select.value=row.asset_id;select.dispatchEvent(new Event('change',{bubbles:true}));}
      click('[data-interchange-review]');await until(()=>!$('[data-interchange-preview]').hidden,'Real composition review failed',3200);
      if(!$('[data-interchange-candidate-summary]').textContent.includes('28 frames')||!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]')||! /^(LOCAL PROJECT|SAVED LOCALLY)$/.test($('#save-state').textContent))throw Error('Review changed the project or lost the master trim');
      steps.push('actual_public_file_relink_review_without_mutation');
      click('[data-interchange-apply]');await until(()=>!$('.cinematicum-interchange').open&&all('.timeline-clip[data-type="clip"]').length===1&&!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]'),'Composition did not apply');
      const imported=$('.timeline-clip[data-type="clip"]').dataset.clip;
      if($('#save-state').textContent!=='UNSAVED')throw Error('Import silently saved');
      click('#undo-button');if(!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]'))throw Error('One undo did not restore the original cut');
      click('#redo-button');if(!$('.timeline-clip[data-clip="'+imported+'"]'))throw Error('One redo did not restore the composition');
      steps.push('one_undo_redo_for_composition_import');
      click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Composition save failed',2500);
      choose('#project-select',cfg.sentinel_id);await until(()=>$('#viewer-project').textContent.includes('sentinel'),'Sentinel did not open');await select(cfg.project_id);
      if(!$('.timeline-clip[data-clip="'+imported+'"]'))throw Error('Reopen lost imported identity');
      const project=await saved(cfg.project_id);
      if(project.sequence_duration!==28||project.sequences.filter(s=>s.otio_dissolve).length!==2||project.sequences.flatMap(s=>s.clips).filter(c=>c.reverse).length!==2)throw Error('Saved graph lost dissolve or reverse semantics');
      steps.push('save_switch_reopen_keeps_editable_dissolve_and_reverse');
      click('#interchange-button');click('[data-interchange-export]');await until(()=>!$('[data-interchange-download]').hidden,'Actual OTIO export failed',2600);
      const link=$('[data-interchange-download]'),response=await fetch(link.href);if(!response.ok||!response.headers.get('content-disposition')?.includes('attachment'))throw Error('OTIO attachment absent');
      const text=await response.text(),exported=JSON.parse(text),operators=operatorCounts(exported);if(operators.dissolves!==2||operators.timewarps!==2)throw Error('Public re-export lost real operators: '+JSON.stringify(operators));
      metrics.otio_download_href=link.getAttribute('href');metrics.exported_operators=operators;click('[data-interchange-download]');
      click('[data-interchange-tab="import"]');file('[data-interchange-file]','ENGINE_TEST_exact_roundtrip.otio',text);await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===2,'Actual downloaded OTIO did not reopen');
      click('[data-interchange-review]');await until(()=>!$('[data-interchange-preview]').hidden,'Exact downloaded composition could not be reviewed',2900);
      if(!$('[data-interchange-import-warnings]').textContent.includes('authoring metadata restored')||! /^(LOCAL PROJECT|SAVED LOCALLY)$/.test($('#save-state').textContent))throw Error('Private identity verification or unsaved-review fence failed');
      steps.push('actual_otio_download_private_roundtrip_review');
    }else if(cfg.operation==='render'){
      if($('#duration').textContent!=='00:00:01:04'||all('.timeline-clip[data-type="clip"]').length!==1)throw Error('Saved 28-frame composition did not reopen');
      steps.push('reopened_real_nested_timeline');
      click('#jump-start');for(let i=0;i<10;i++)click('#step-forward');
      await until(()=>$('#frame-status').textContent==='Rendered frame 10 · export graph'&&!$('#processed-frame').hidden&&$('#processed-frame').complete,'Actual processed transition frame did not arrive',4300);
      const image=$('#processed-frame'),canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const context=canvas.getContext('2d');context.drawImage(image,0,0);const rgba=[...context.getImageData(32,20,1,1).data];metrics.processed_transition_pixel=rgba;
      if(Math.abs(rgba[0]-90)>6||rgba[1]>6||Math.abs(rgba[2]-90)>6)throw Error('Actual 50% dissolve frame is not a linear blend: '+rgba);
      steps.push('actual_processed_transition_frame');metrics.movie_href=await render(cfg.project_id);steps.push('actual_prores_export_and_download');
    }else if(cfg.operation==='archive'){
      const original=await saved(cfg.project_id),originalText=JSON.stringify(original);
      click('#archive-button');click('[data-archive-export]');await until(()=>!$('.cinematicum-archive').open&&$('#job-label').textContent==='Project archive ready'&&!$('#download-job').hidden,'Actual archive did not complete',3200);
      const href=$('#download-job').getAttribute('href'),name=$('#download-job').download,response=await fetch(href,{cache:'no-store'});if(!response.ok)throw Error('Archive read failed');const blob=await response.blob();if(blob.size<1000||[...new Uint8Array(await blob.slice(0,4).arrayBuffer())].join(',')!=='80,75,3,4')throw Error('Actual archive ZIP is absent');
      click('#download-job');metrics.archive_href=href;
      click('#archive-button');file('[data-archive-file]',name||'ENGINE_TEST.cinematicum.zip',blob,'application/zip');click('[data-archive-restore]');
      await until(()=>$('#job-label').textContent==='Project restored'&&!$('#open-restored-project').hidden,'Actual archive File upload/restore failed',3500);
      steps.push('actual_archive_download_and_file_upload');
      const restoredID=$('#open-restored-project').dataset.projectId;if(!/^[a-f0-9]{32}$/.test(restoredID)||restoredID===cfg.project_id||JSON.stringify(await saved(cfg.project_id))!==originalText)throw Error('Restore overwrote the original edit');
      click('#open-restored-project');await until(()=>$('#project-select').value===restoredID&&all('.timeline-clip[data-type="clip"]').length===1,'Restored composition did not open');
      const restored=await saved(restoredID);if(canonical(restored.clips)!==canonical(original.clips)||canonical(restored.sequences)!==canonical(original.sequences))throw Error('Archive lost editable sequence operators');
      metrics.restored_project_id=restoredID;steps.push('new_restored_identity_preserves_original');
      metrics.movie_href=await render(restoredID);steps.push('restored_nested_picture_audio_render_and_download');
      if(JSON.stringify(await saved(cfg.project_id))!==originalText)throw Error('Restored render changed the saved original');
    }else throw Error('Unsupported phase');
    return {passed:true,steps,metrics,expect_download:true,expected_download_count:cfg.operation==='archive'?2:1,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,metrics,error:String(error),elapsed_ms:Math.round(performance.now()-began)};}
})();

// Async-function body for the native WK helper. Mutations use shipped controls.
// GET of the actual export is read-only; its bytes become an ordinary FileList.
return await (async () => {
  const began=performance.now(),deadline=began+11500,steps=[],$=selector=>document.querySelector(selector),all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostics=()=>'; interchange='+($('[data-interchange-status]')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,milliseconds=1900) {const end=Math.min(deadline,performance.now()+milliseconds);while(performance.now()<end){if(predicate())return;await sleep(30);}throw Error(label+diagnostics());}
  function click(selector) {const e=$(selector);if(!e||e.disabled)throw Error('Unavailable control: '+selector+diagnostics());e.click();}
  function set(selector,value) {const e=$(selector);if(!e||e.disabled)throw Error('Unavailable field: '+selector);e.value=String(value);if(e.type==='range')e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}
  function file(name,text) {const transfer=new DataTransfer();transfer.items.add(new File([text],name,{type:'application/json'}));const input=$('[data-interchange-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  const clipSelector=id=>'.timeline-clip[data-clip="'+id+'"]';
  function selectClip(id) {const element=$(clipSelector(id));if(!element)throw Error('Missing timeline clip '+id);element.focus();element.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));}
  const clipNodes=()=>all('.timeline-clip[data-type="clip"]');
  const firstClip=document=>document.tracks.children.flatMap(track=>track.children).find(item=>/^Clip\./.test(item.OTIO_SCHEMA));
  function stripMetadata(value) {if(Array.isArray(value))return value.map(stripMetadata);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,key==='metadata'?{}:stripMetadata(item)]));return value;}
  try {
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&clipNodes().length===2&&$('.media-item[data-asset]'),'Test cut timeline did not bootstrap',4500);
    const oldID=clipNodes()[0].dataset.clip,assetID=$('.media-item[data-asset]').dataset.asset;
    selectClip(oldID);click('[data-mode="color"]');set('[data-field="grade.exposure"]',.5);click('[data-mode="edit"]');
    if($('#save-state').textContent!=='UNSAVED')throw Error('Fixture edit was not left unsaved.');
    click('#interchange-button');click('[data-interchange-export]');
    await until(()=>!$('[data-interchange-download]').hidden,'Actual OTIO export did not complete',2500);
    const href=$('[data-interchange-download]').getAttribute('href'),download=await fetch(href);
    if(!download.ok||!download.headers.get('content-disposition')?.includes('attachment'))throw Error('The ordinary OTIO download did not return an attachment.');
    const exportedText=await download.text(),exported=JSON.parse(exportedText),exportedClip=exported.metadata?.cinematicum?.project?.clips?.find(clip=>clip.id===oldID);
    if(exportedClip?.grade?.exposure!==.5)throw Error('Export omitted the current unsaved grade edit.');
    if(!exported.tracks.children.some(track=>track.children.some(item=>item.OTIO_SCHEMA==='Gap.1')))throw Error('The exported file did not contain the real three-frame gap.');
    if(!$('[data-interchange-export-warnings]').textContent.includes('unprocessed cuts'))throw Error('Effect interchange limits were not disclosed.');
    steps.push('export_unsaved_edit_and_read_actual_download');
    click('[data-interchange-tab="import"]');file('ENGINE_TEST_roundtrip.otio',exportedText);
    await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===1,'Exported media references were not listed');
    if($('[data-interchange-reference]').value!=='')throw Error('Automatic content matching should be the default.');
    click('[data-interchange-review]');await until(()=>!$('[data-interchange-preview]').hidden,'Hash-based roundtrip review failed',2300);
    if(!$('[data-interchange-import-warnings]').textContent.includes('authoring metadata restored'))throw Error('The exact CINEMATICUM roundtrip did not restore its private authoring metadata.');
    if(!$('[data-interchange-candidate-summary]').textContent.includes('24000/1001'))throw Error('The reviewed rate lost its rational clock.');
    if(!$(clipSelector(oldID))||$('#save-state').textContent!=='UNSAVED')throw Error('Review must not apply or save a candidate.');
    steps.push('review_exact_roundtrip_with_real_content_hash');
    file('ENGINE_TEST_duplicate.otio','{"OTIO_SCHEMA":"Timeline.1","OTIO_SCHEMA":"Timeline.1"}');
    await until(()=>!$('[data-interchange-review]').disabled&&$('[data-interchange-file-name]').textContent.includes('duplicate'),'Duplicate-member fixture did not load');
    click('[data-interchange-review]');await until(()=>!$('[data-interchange-review]').disabled&&$('[data-interchange-status]').textContent.includes('Duplicate JSON member'),'Original JSON duplicate members were not rejected by the backend');
    if(!$('[data-interchange-preview]').hidden||!$(clipSelector(oldID)))throw Error('Rejected OTIO changed the timeline or exposed an apply action.');
    steps.push('reject_original_json_duplicate_members_without_applying');
    const external=stripMetadata(exported);firstClip(external).source_range.start_time.value+=1.25;
    firstClip(external).effects=[{OTIO_SCHEMA:'Effect.1',name:'ENGINE TEST unsupported blur',effect_name:'Blur'}];
    file('ENGINE_TEST_external.otio',JSON.stringify(external));
    await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===1&&$('[data-interchange-file-name]').textContent.includes('external'),'External OTIO did not load');
    click('[data-interchange-review]');await until(()=>!$('[data-interchange-review]').disabled&&$('[data-interchange-status]').textContent.includes('Unresolved OTIO media'),'A path without a content hash was incorrectly opened or auto-linked');
    set('[data-interchange-reference]',assetID);click('[data-interchange-review]');
    await until(()=>!$('[data-interchange-preview]').hidden,'Explicit existing-asset relink failed',2300);
    if(!$('[data-interchange-import-warnings]').textContent.includes('unsupported blur is not applied'))throw Error('Unsupported external effect was not reported.');
    if(!$(clipSelector(oldID)))throw Error('The review replaced the timeline before approval.');
    steps.push('explicit_existing_asset_relink_and_warning_review');
    click('[data-interchange-apply]');await until(()=>!$('.cinematicum-interchange').open&&clipNodes().length===2,'Explicit timeline replacement did not apply');
    const appliedID=clipNodes()[0].dataset.clip;selectClip(appliedID);
    if(Number($('[data-field="in"]').value)!==1.75)throw Error('Imported fractional source in was not preserved.');
    if($('#save-state').textContent!=='UNSAVED')throw Error('Imported edit must remain unsaved until the user saves.');
    click('#undo-button');if(!$(clipSelector(oldID)))throw Error('Replacement did not undo to the original clip identities in one change.');selectClip(oldID);
    if(Number($('[data-field="in"]').value)!==.5)throw Error('Undo did not restore the original source trim.');
    click('#redo-button');if(!$(clipSelector(appliedID)))throw Error('Redo did not restore the reviewed import.');selectClip(appliedID);
    if(Number($('[data-field="in"]').value)!==1.75)throw Error('Redo lost the imported source trim.');
    steps.push('replace_timeline_once_and_undo_redo');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Imported timeline save failed',2200);
    // Leave the real reviewed interchange controls visible in the native
    // screenshot. This second review does not apply or save another edit.
    click('#interchange-button');click('[data-interchange-tab="import"]');file('ENGINE_TEST_external.otio',JSON.stringify(external));
    await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===1,'Saved timeline review did not load');
    set('[data-interchange-reference]',assetID);click('[data-interchange-review]');await until(()=>!$('[data-interchange-preview]').hidden,'Saved timeline review did not complete');
    if($('#save-state').textContent!=='SAVED LOCALLY')throw Error('Review changed the saved project.');
    return {passed:true,steps,project_id:$('#project-select').value,asset_id:assetID,original_clip_id:oldID,imported_clip_id:appliedID,export_href:href,download_bytes:new TextEncoder().encode(exportedText).length,exported_unsaved_exposure:exportedClip.grade.exposure,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,error:String(error),interchange_status:$('[data-interchange-status]')?.textContent||'',elapsed_ms:Math.round(performance.now()-began)};}
})();

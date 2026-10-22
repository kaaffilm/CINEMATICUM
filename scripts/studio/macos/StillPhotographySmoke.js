// The same shipped controls run in WKWebView and Chromium acceptance. No
// application state or engine output is synthesized by the harness.
const PHOTO_FIXTURE = /* ENGINE_TEST_CONFIG */ {};
return await (async () => {
  const begun=performance.now(),deadline=begun+14000,steps=[],result={operation:PHOTO_FIXTURE.operation};
  const $=selector=>document.querySelector(selector),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostic=()=>`; imaging=${$('[data-imaging-status]')?.textContent}; job=${$('#job-label')?.textContent}/${$('#job-detail')?.textContent}; toast=${$('#toast')?.textContent}`;
  function require(value,message){if(!value)throw Error(message+diagnostic());}
  const canonical=value=>JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
  function control(selector){const node=$(selector);require(node&&!node.disabled&&!node.closest('[inert]'),'Unavailable control '+selector);node.scrollIntoView({block:'nearest'});return node;}
  const click=selector=>control(selector).click();
  function set(selector,value){const node=control(selector);if(node.type==='checkbox')node.checked=Boolean(value);else node.value=String(value);node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));}
  async function until(fn,label,ms=1800){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(fn())return;await pause(20);}throw Error(label+diagnostic());}
  async function get(url){const response=await fetch(url,{cache:'no-store'});require(response.ok,'GET failed '+url);return response.json();}
  const project=()=>get(`/api/projects/${PHOTO_FIXTURE.project_id}`);
  async function select(id,name){if($('#project-select').value!==id)set('#project-select',id);await until(()=>$('#project-select').value===id&&!$('#project-select').disabled&&$('#viewer-project').textContent===name,'The exact fixture project did not open',2500);}
  async function save(){click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','The photograph edit did not save');}
  async function reopen(){await select(PHOTO_FIXTURE.sentinel_id,PHOTO_FIXTURE.sentinel_name);await select(PHOTO_FIXTURE.project_id,PHOTO_FIXTURE.project_name);}
  function selectLastClip(){const node=[...document.querySelectorAll('.timeline-clip[data-type=clip]')].at(-1);require(node,'No photograph clip can be selected');node.scrollIntoView({block:'nearest'});const rect=node.getBoundingClientRect();node.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,pointerId:41,isPrimary:true,clientX:rect.left+15,clientY:rect.top+12}));window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,buttons:0,pointerId:41,isPrimary:true}));}
  async function importPhotos(){
    const initial=await project();require(!initial.assets.length&&!initial.clips.length,'The import fixture is not empty');
    const transfer=new DataTransfer();for(let i=0;i<PHOTO_FIXTURE.photographs.length;i++){const response=await fetch(`/__engine_test__/photo/${i}`);require(response.ok,'An independent original photograph is missing');transfer.items.add(new File([await response.blob()],PHOTO_FIXTURE.photographs[i].name,{type:'image/png'}));}
    const input=control('#media-input');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));
    await until(()=>$('#asset-count').textContent.trim()==='6'&&$('#media-footer-label').textContent==='Media is copied into your project','The six actual source photographs were not imported',9000);
    const admitted=await project();require(admitted.assets.length===6&&admitted.assets.every(a=>PHOTO_FIXTURE.photographs.some(p=>p.name===a.name&&p.identity.sha256===a.sha256)),'Admitted photograph identities differ');
    require(!admitted.clips.length,'Import unexpectedly authored a timeline edit');
    click('#export-button');await until(()=>$('#export-dialog').open,'The movie processing controls did not open');set('#movie-precision','high16');click('#close-export');await save();
    await reopen();const reopened=await project();require(reopened.assets.length===6&&reopened.settings.image_precision==='high16','The immutable originals or selected 16-bit SDR processing did not reopen');
    steps.push('six_actual_png_files_imported_through_shipped_input','selected_existing_16bit_sdr_processing','originals_unchanged_and_reopened');
  }
  async function develop(kind){
    const initial=await project(),isHDR=kind==='hdr',operation=isHDR?'hdr_merge':'panorama';
    const beforeCount=isHDR?0:1;require(initial.clips.length===beforeCount,'The preceding saved edit was not preserved');
    const selected=PHOTO_FIXTURE.photographs.filter(p=>p.role===kind).map(row=>({...row,asset:initial.assets.find(a=>a.name===row.name)}));require(selected.length===3&&selected.every(p=>p.asset),'The original selected sources are missing');
    click('#develop-image');await until(()=>$('#imaging-dialog')?.open&&!$('[data-imaging-run]').disabled,'The actual imaging and geometry runtimes did not become ready',3500);
    set('[data-imaging-operation]',operation);click('[data-imaging-run]');require($('[data-imaging-status]').classList.contains('error'),'Empty photograph selection was not rejected');
    if(isHDR){
      for(const row of selected){const parent=[...$('[data-imaging-brackets]').children].find(node=>node.querySelector('input[type=checkbox]')?.dataset.assetId===row.asset.id);require(parent,'Missing bracket row');const check=parent.querySelector('input[type=checkbox]');check.checked=true;check.dispatchEvent(new Event('change',{bubbles:true}));const shutter=parent.querySelector('input[type=number]');require(!shutter.disabled,'A selected bracket has no active shutter control');shutter.value=String(row.exposure_time);shutter.dispatchEvent(new Event('change',{bubbles:true}));}
      set('[data-imaging-transfer]','measured');set('[data-imaging-alignment]','homography');set('[data-imaging-deghost]','reference');set('[data-imaging-reference]',selected[1].asset.id);set('[data-imaging-ghost-threshold]',.5);
    }else{
      for(const row of selected)set(`[data-imaging-panorama-images] input[data-asset-id="${row.asset.id}"]`,true);
      set('[data-imaging-panorama-transfer]','linear');set('[data-imaging-panorama-reference]',selected[0].asset.id);set('[data-imaging-panorama-exposure]',true);
    }
    const run=control('[data-imaging-run]'),rect=run.getBoundingClientRect(),hit=document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2);require((hit===run||run.contains(hit))&&rect.bottom<=innerHeight,'The Develop action is not visible and hit-testable');
    click('[data-imaging-run]');await until(()=>!$('[data-imaging-run]').disabled&&!$('[data-imaging-downloads]').hidden&&$('[data-imaging-picture]').complete&&$('[data-imaging-picture]').naturalWidth>0,'The actual photograph processing job did not return its image',7600);
    const receiptURL=new URL($('[data-imaging-receipt-download]').href).pathname,receipt=await get(receiptURL),jobID=receiptURL.split('/').slice(-2)[0];
    require(receipt.operation===operation&&receipt.source_details.runtime.opencv,'A completed actual OpenCV receipt is missing');
    result.job_id=jobID;result.receipt_url=receiptURL;result.clicked_downloads=[];
    if(isHDR){
      require(receipt.recipe.alignment==='homography'&&receipt.recipe.deghost==='reference'&&receipt.recipe.input_transfer==='measured','The selected HDR controls were not executed');
      require(receipt.source_details.response.inverse_response_rgb.length===256&&receipt.source_details.deghost.motion_pixels>1000,'The response or motion was not actually measured');
      click('[data-imaging-motion-toggle]');await until(()=>$('[data-imaging-picture]').complete&&new URL($('[data-imaging-picture]').src).pathname.endsWith('/motion.png'),'The measured motion mask did not display');
      const img=$('[data-imaging-picture]'),canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;const context=canvas.getContext('2d');context.drawImage(img,0,0);const data=context.getImageData(0,0,canvas.width,canvas.height).data;let whites=0;for(let i=0;i<data.length;i+=4)if(data[i]>250&&data[i+3]>250)whites++;require(whites===receipt.source_details.deghost.motion_pixels,'Visible mask differs from measured motion');result.visible_motion_pixels=whites;click('[data-imaging-motion-toggle]');
    }else require(receipt.source_details.measurements.length===3&&receipt.width>600,'All three photographs were not stitched geometrically');
    for(const key of isHDR?['display','exr','receipt','motion']:['display','exr','receipt']){const link=control(`[data-imaging-${key}-download]`);const url=new URL(link.href);require(url.origin===location.origin&&url.pathname.includes(`/imaging/outputs/${jobID}/`),'An artifact escaped its owned output');result.clicked_downloads.push({key,url:url.pathname,name:url.pathname.split('/').pop()});link.click();await pause(25);}
    const admitted=await project(),asset=admitted.assets.find(a=>a.provenance?.output_id===jobID);require(asset?.kind==='image'&&admitted.clips.length===beforeCount,'Processing changed the timeline or failed to admit reusable media');
    result.asset_id=asset.id;click('[data-imaging-close]');click(`[data-add="${asset.id}"]`);await until(()=>document.querySelectorAll('.timeline-clip[data-type=clip]').length===beforeCount+1,'Developed media was not added through the normal timeline control');
    click('#undo-button');require(document.querySelectorAll('.timeline-clip[data-type=clip]').length===beforeCount,'Undo did not remove the new photograph edit');click('#redo-button');require(document.querySelectorAll('.timeline-clip[data-type=clip]').length===beforeCount+1,'Redo did not restore the photograph edit');
    selectLastClip();set('[data-field=duration]',12);await save();const saved=await project();require(saved.clips.length===beforeCount+1&&saved.clips.at(-1).asset_id===asset.id&&saved.clips.at(-1).duration===12,'The saved cut does not use the developed image');
    await reopen();const reopened=await project();require(canonical(reopened.clips)===canonical(saved.clips)&&canonical(reopened.assets)===canonical(saved.assets),'Save/reopen changed source identities or the authored cut');
    click('[data-mode=color]');click(isHDR?'#jump-start':'#jump-end');await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame').complete&&$('#processed-frame').naturalWidth===160&&$('#frame-status').textContent.includes('export graph'),'The saved photograph did not render through the actual movie graph',5500);
    result.frame_url=new URL($('#processed-frame').src).pathname;steps.push('authored_controls_executed_actual_owned_job','actual_master_display_receipt_and_mask_downloads','admitted_image_did_not_silently_edit_timeline','normal_add_undo_redo_save_reopen','actual_paused_movie_frame_rendered');
  }
  async function deliver(){
    const saved=await project();require(saved.clips.length===2&&saved.assets.length===8,'The two developed photographs did not survive restart');
    click('#export-button');await until(()=>$('#export-dialog').open,'The movie export dialog did not open');click('[data-export=master16]');
    await until(()=>!$('#export-dialog').open&&$('#job-label').textContent==='16-bit master complete'&&!$('#download-job').hidden,'The actual photograph timeline export did not complete',6500);
    const movieURL=new URL($('#download-job').href);result.movie_url=movieURL.pathname+movieURL.search;result.movie_name=$('#download-job').download;click('#download-job');
    click('#archive-button');await until(()=>$('.cinematicum-archive')?.open,'The archive dialog did not open');click('[data-archive-export]');
    await until(()=>!$('.cinematicum-archive').open&&$('#job-label').textContent==='Project archive ready'&&!$('#download-job').hidden,'The photograph archive did not complete',2800);
    const archiveURL=new URL($('#download-job').href);result.archive_url=archiveURL.pathname+archiveURL.search;result.archive_name=$('#download-job').download;const response=await fetch(result.archive_url),blob=await response.blob();require(response.ok&&blob.size>1000,'The actual archive download is missing');click('#download-job');
    click('#archive-button');await until(()=>$('.cinematicum-archive').open,'The restore controls did not open');const transfer=new DataTransfer();transfer.items.add(new File([blob],result.archive_name,{type:'application/zip'}));const file=control('[data-archive-file]');file.files=transfer.files;file.dispatchEvent(new Event('change',{bubbles:true}));click('[data-archive-restore]');
    await until(()=>!$('.cinematicum-archive').open&&$('#job-label').textContent==='Project restored'&&!$('#open-restored-project').hidden,'The exact downloaded photograph archive did not restore',2800);
    click('#open-restored-project');await until(()=>$('#project-select').value!==PHOTO_FIXTURE.project_id&&$('#viewer-project').textContent.includes('ENGINE TEST'),'The restored photograph project did not open');result.restored_id=$('#project-select').value;
    const restored=await get(`/api/projects/${result.restored_id}`);require(canonical(restored.clips)===canonical(saved.clips)&&restored.assets.length===saved.assets.length,'The archive changed the restored cut or inventory');
    result.expect_download=true;steps.push('actual_lossless_16bit_sdr_movie_export_and_download','actual_project_archive_download_and_file_restore','restored_edit_and_media_preserved');
  }
  try{
    await until(()=>$('#project-select')?.options.length>=2&&$('#viewer-project').textContent,'The application did not bootstrap',3500);await select(PHOTO_FIXTURE.project_id,PHOTO_FIXTURE.project_name);
    if(PHOTO_FIXTURE.operation==='import')await importPhotos();else if(['hdr','panorama'].includes(PHOTO_FIXTURE.operation))await develop(PHOTO_FIXTURE.operation);else await deliver();
    return {...result,passed:true,steps,expected_download_count:{import:0,hdr:4,panorama:3,deliver:2}[PHOTO_FIXTURE.operation],elapsed_ms:Math.round(performance.now()-begun)};
  }catch(error){return {...result,passed:false,steps,error:String(error),elapsed_ms:Math.round(performance.now()-begun)};}
})();

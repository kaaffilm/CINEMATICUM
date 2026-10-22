// Shipped interchange/editor controls and actual completed downloads. The
// fixture File exercises the ordinary onchange; no physical chooser is claimed.
return await (async()=>{
  const cfg=/* ENGINE_TEST_CONFIG */ {},began=performance.now(),deadline=began+13000;
  const checks={},frames={},metrics={},$=selector=>document.querySelector(selector),all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));let probe=null;
  const diagnostic=()=>'; interchange='+($('[data-interchange-status]')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  function require(ok,name){checks[name]=!!ok;if(!ok)throw Error(name+diagnostic());}
  async function until(predicate,label,maximum=2200){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(20);}throw Error(label+diagnostic());}
  function control(selector){const element=$(selector);if(!element||element.disabled||element.hidden||element.closest('[inert]'))throw Error('Unavailable '+selector+diagnostic());element.scrollIntoView({block:'nearest',inline:'nearest'});return element;}
  const click=selector=>control(selector).click();
  function choose(selector,value){const element=control(selector);element.value=String(value);require(element.value===String(value),'explicit_control_value_exists');element.dispatchEvent(new Event('change',{bubbles:true}));}
  function file(text,name){const transfer=new DataTransfer();transfer.items.add(new File([text],name,{type:'application/xml'}));const input=control('[data-interchange-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  async function savedProject(){const response=await fetch('/api/projects/'+cfg.project_id,{cache:'no-store'});if(!response.ok)throw Error('Owned saved project not readable');return response.json();}
  async function openProject(id,name){if($('#project-select').value!==id){choose('#project-select',id);await until(()=>$('#project-select').value===id&&$('#viewer-project').textContent===name,'Owned project did not open');}}
  async function exactFrame(frame){
    click('#jump-start');for(let n=0;n<frame;n++)click('#step-forward');
    await until(()=>{const image=$('#processed-frame');return image&&!image.hidden&&image.complete&&image.naturalWidth===cfg.expected.width&&$('#frame-status').textContent==='Rendered frame '+frame+' · export graph';},'Exact imported frame did not render',4000);
    const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);
    require(url.origin===location.origin&&url.pathname.startsWith('/api/projects/'+cfg.project_id+'/previews/')&&/\/[a-f0-9]{64}\.png$/.test(url.pathname),'actual_owned_paused_frame');
    const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const context=canvas.getContext('2d');context.drawImage(image,0,0);
    const pixels=[...context.getImageData(cfg.expected.preview_x,cfg.expected.preview_y,1,1).data];
    return {url:url.pathname,frame,pixel:pixels,width:canvas.width,height:canvas.height};
  }
  try{
    await until(()=>$('#project-select')?.options.length>=2&&$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Owned FCPXML fixture did not bootstrap',3500);
    await openProject(cfg.project_id,cfg.operation==='author'?cfg.initial_name:cfg.imported_name);
    if(cfg.operation==='author'){
      const original=JSON.stringify(await savedProject());
      require(!!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]'),'original_cut_visible_before_import');
      click('#interchange-button');choose('#interchange-format','fcpxml');click('[data-interchange-tab="import"]');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(atob(cfg.document_base64),c=>c.charCodeAt(0)));
      file(text,'ENGINE_TEST_independent_timing.fcpxml');
      await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===cfg.media.length,'Real FCPXML file inspection did not complete',2600);
      for(const select of all('[data-interchange-reference]')){
        const label=select.closest('label').querySelector('strong').textContent,row=cfg.media.find(row=>label===row.reference_label);
        if(!row)throw Error('Unexpected imported source reference');select.value=row.asset_id;select.dispatchEvent(new Event('change',{bubbles:true}));
      }
      click('[data-interchange-review]');await until(()=>!$('[data-interchange-preview]').hidden,'Actual FCPXML relink review failed',3200);
      require($('[data-interchange-candidate-summary]').textContent.includes(cfg.expected.frames+' frames'),'review_retains_exact_rational_extent');
      require(!!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]')&&/^(LOCAL PROJECT|SAVED LOCALLY)$/.test($('#save-state').textContent)&&JSON.stringify(await savedProject())===original,'review_does_not_mutate_live_or_saved_edit');
      require($('[data-interchange-import-warnings]').textContent.includes('independent native lanes'),'magnetic_connection_limit_shown');
      click('[data-interchange-apply]');await until(()=>!$('.cinematicum-interchange').open&&!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]')&&all('.timeline-clip[data-type="clip"]').length===cfg.expected.top_level_clips,'Reviewed timeline did not apply');
      const ids=all('.timeline-clip[data-type="clip"]').map(element=>element.dataset.clip).sort();
      require($('#save-state').textContent==='UNSAVED','apply_is_unsaved_edit');
      click('#undo-button');require(!!$('.timeline-clip[data-clip="'+cfg.original_clip_id+'"]'),'one_undo_restores_original_cut');
      click('#redo-button');require(JSON.stringify(all('.timeline-clip[data-type="clip"]').map(element=>element.dataset.clip).sort())===JSON.stringify(ids),'one_redo_restores_imported_identity');
      click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Imported timeline did not save');
      const authored=JSON.stringify(await savedProject());await openProject(cfg.sentinel_id,cfg.sentinel_name);await openProject(cfg.project_id,cfg.imported_name);
      require(JSON.stringify(await savedProject())===authored&&JSON.stringify(all('.timeline-clip[data-type="clip"]').map(element=>element.dataset.clip).sort())===JSON.stringify(ids),'save_switch_reopen_preserves_complete_saved_edit');
      const project=await savedProject();require(project.sequence_duration===cfg.expected.frames,'saved_exact_timeline_extent');
      require(project.clips.some(clip=>clip.sequence_id)&&project.clips.some(clip=>clip.speed===cfg.expected.forward_speed),'nested_reference_and_forward_time_map_remain_editable');
      click('#interchange-button');choose('#interchange-format','fcpxml');click('[data-interchange-export]');
      await until(()=>!$('[data-interchange-download]').hidden,'Actual FCPXML export failed',2600);
      const link=$('[data-interchange-download]'),url=new URL(link.href,location.href),response=await fetch(url,{cache:'no-store'});
      require(url.origin===location.origin&&url.pathname.startsWith('/api/projects/'+cfg.project_id+'/exports/')&&url.pathname.endsWith('.fcpxml')&&response.ok&&response.headers.get('content-disposition')?.includes('attachment'),'owned_fcpxml_attachment');
      const exportedText=await response.text(),xml=new DOMParser().parseFromString(exportedText,'application/xml');
      require(!xml.querySelector('parsererror')&&xml.documentElement.tagName==='fcpxml','actual_download_is_fcpxml');
      require(xml.querySelectorAll('timeMap').length>=1&&xml.querySelectorAll('ref-clip').length>=1&&xml.querySelectorAll('media > sequence').length>=1,'public_time_map_and_compound_resources_exported');
      metrics.fcpxml_href=link.getAttribute('href');click('[data-interchange-download]');
      click('[data-interchange-tab="import"]');file(exportedText,'ENGINE_TEST_downloaded.fcpxml');
      await until(()=>!$('[data-interchange-review]').disabled&&all('[data-interchange-reference]').length===cfg.media.length,'Downloaded public XML did not reopen');
      require(all('[data-interchange-reference]').every(select=>select.value===''),'downloaded_source_hashes_use_automatic_relink');
      click('[data-interchange-review]');await until(()=>!$('[data-interchange-preview]').hidden,'Downloaded FCPXML did not review with owned content hashes',2900);
      metrics.review_save_state=$('#save-state').textContent;
      require(/^(LOCAL PROJECT|SAVED LOCALLY)$/.test(metrics.review_save_state)&&JSON.stringify(await savedProject())===authored,'download_review_preserves_saved_edit');
      click('[data-interchange-close]');
    }else if(cfg.operation==='render'){
      require(all('.timeline-clip[data-type="clip"]').length===cfg.expected.top_level_clips,'saved_imported_lanes_reopen');
      frames.imported=await exactFrame(cfg.expected.preview_frame);
      require(frames.imported.pixel.slice(0,3).every((value,index)=>Math.abs(value-cfg.expected.preview_rgb[index])<=cfg.expected.preview_tolerance),'paused_frame_matches_independent_source_pixel');
      click('#export-button');click('[data-export="prores"]');
      await until(()=>$('#job-label').textContent==='ProRes export complete'&&!$('#download-job').hidden,'Actual imported movie export failed',4800);
      const href=$('#download-job').getAttribute('href'),url=new URL(href,location.href);
      require(url.origin===location.origin&&url.pathname.startsWith('/api/projects/'+cfg.project_id+'/exports/')&&url.pathname.endsWith('.mov'),'actual_owned_prores_export');
      metrics.movie_href=href;click('#download-job');
      if(cfg.native_playback_required){
        probe=document.createElement('video');probe.controls=true;probe.muted=true;probe.playsInline=true;
        probe.style.cssText='position:fixed;left:24px;bottom:28px;width:240px;z-index:10000;background:black';
        probe.setAttribute('aria-label','ENGINE TEST native ProRes export decoder');probe.src=url.pathname;document.body.append(probe);
        await until(()=>probe.readyState>=2,'Native ProRes decoder did not open the actual export',2500);await probe.play();
        await until(()=>probe.currentTime>.06,'Native export movie clock did not advance',1000);
        metrics.playback={url:url.pathname,time:probe.currentTime,mechanism:'test-owned native video element; product ProRes transport is not asserted'};probe.pause();
        require(metrics.playback.time>.06,'native_decoder_plays_actual_downloaded_movie');
      }else metrics.playback={attempted:false,reason:'Explicit Chromium portability run does not certify the native ProRes decoder.'};
    }else throw Error('Unsupported native FCPXML phase');
    return {passed:true,checks,frames,metrics,expected_download_count:1,expect_download:true,physical_open_panel_asserted:false,physical_save_panel_asserted:false,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,checks,frames,metrics,error:String(error),physical_open_panel_asserted:false,physical_save_panel_asserted:false,elapsed_ms:Math.round(performance.now()-began)};}
  finally{if(probe){probe.pause();probe.removeAttribute('src');probe.load();probe.remove();}}
})();

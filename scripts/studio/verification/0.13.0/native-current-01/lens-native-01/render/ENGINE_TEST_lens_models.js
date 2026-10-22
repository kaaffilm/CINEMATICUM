// Actual editor controls. A fixture File exercises the shipped onchange;
// neither the physical open panel nor the physical save panel is asserted.
return await (async()=>{
  const cfg={"acceptance_id": "64f5fcf5751342c6acc4661da7afe708", "asset_id": "bac04bf6b15a4016a2fd2ba1d0958a90", "calibration_count": 106, "delivery": "prores", "expected_profile": {"calibration_aspect": 1.3333333333333333, "calibration_crop": 2.0, "center_x": 0.0, "center_y": 0.0, "coefficients": [-0.013136, 0.015797, 0.0], "distortion": "ptlens", "focal_mm": 7.0, "image_crop": 2.0, "lens": "Olympus Zuiko Digital ED 7-14mm f/4.0", "maker": "Olympus", "source_sha256": "f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615", "version": 1}, "helper_identity": {"sha256": "c6b70d236c056a6ed3eaa08ef44aaa1672ecce904f8004095b69ac2a60f3bee7", "size": 206920}, "kind": "cinematicum-owned-lens-models-v1", "profile_id": "ea257b1f0767fc45329a2d98", "project_id": "62d2a0bd06544062bf1ca5ede41154cd", "project_name": "ENGINE TEST native Lensfun and fisheye", "sentinel_id": "4b50dc3e0bca4a6ba953ed53f72074da", "sentinel_identity": {"sha256": "665b924f195e7e30c6fcaa7660bcf75c5279614f335f3f2378779fe8be4804a8", "size": 350}, "sentinel_name": "ENGINE TEST lens sentinel", "source_identity": {"sha256": "5ef0dc256b99666cb55d44da6ed5ebae7fec1aaf04cbe78b1f87e49717e09d4b", "size": 129979}, "truth": {"lensfun.xml": {"sha256": "f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615", "size": 116602}, "source.rgba": {"sha256": "274448bda14cd5bafe4ba07235077ccb7c818e2e65cc820170b5e5e6ec65d2ba", "size": 460800}}, "operation": "render", "lens_id": "e28b3a9d-070f-436d-8bf2-d9d97a17b72e"},began=performance.now(),deadline=began+13000;
  const checks={},frames={},metrics={},$=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));let probe=null;
  const diagnostic=()=>'; frame='+($('#frame-status')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  function require(ok,name){checks[name]=!!ok;if(!ok)throw Error(name+diagnostic());}
  async function until(predicate,label,maximum=2000){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(20);}throw Error(label+diagnostic());}
  function control(selector){const e=$(selector);if(!e||e.disabled||e.hidden||e.closest('[inert]'))throw Error('Unavailable '+selector+diagnostic());e.scrollIntoView({block:'nearest',inline:'nearest'});return e;}
  const click=selector=>control(selector).click();
  function choose(selector,value){const e=control(selector);e.value=String(value);e.dispatchEvent(new Event('change',{bubbles:true}));}
  function selectClip(){const e=control('.timeline-clip[data-clip]');e.focus();e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));}
  function selectLens(id){const e=control('[data-node="'+id+'"]'),box=e.getBoundingClientRect(),data={bubbles:true,cancelable:true,pointerId:89,pointerType:'mouse',isPrimary:true,button:0,clientX:box.left+40,clientY:box.top+15};e.dispatchEvent(new PointerEvent('pointerdown',{...data,buttons:1}));window.dispatchEvent(new PointerEvent('pointerup',{...data,buttons:0}));}
  async function openProject(id,name){if($('#project-select').value!==id){choose('#project-select',id);await until(()=>$('#project-select').value===id&&$('#viewer-project').textContent===name,'Owned project did not open');}}
  async function saved(){click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Actual graph save failed');}
  async function exactFrame(previous){
    await until(()=>{const img=$('#processed-frame');return img&&!img.hidden&&img.complete&&img.naturalWidth===160&&$('#frame-status').textContent==='Rendered frame 0 · export graph'&&(!previous||new URL(img.currentSrc||img.src,location.href).pathname!==previous);},'Actual lens PNG did not arrive',3200);
    const img=$('#processed-frame'),url=new URL(img.currentSrc||img.src,location.href);require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'owned_real_frame_path');
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);const pixels=ctx.getImageData(0,0,160,90).data;let hash=2166136261;
    for(const value of pixels)hash=Math.imul(hash^value,16777619);
    return {url:url.pathname,pixel_hash:(hash>>>0).toString(16),frame:0};
  }
  try{
    await until(()=>$('#project-select')?.options.length>=2&&$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Owned lens fixture did not bootstrap',3500);
    await openProject(cfg.project_id,cfg.project_name);click('[data-mode="composite"]');click('#jump-start');
    if(cfg.operation==='author'){
      click('[data-add="'+cfg.asset_id+'"]');choose('[data-graph-add-type]','lens_distortion');click('[data-graph-action="add"]');
      metrics.lens_id=$('.compositor-node.selected').dataset.node;require($('[data-graph-output]').value===metrics.lens_id,'connected_lens_node');
      choose('[data-node-param="fx"]',.55);choose('[data-node-param="fy"]',.72);let previous=null;
      for(const projection of ['equidistant','equisolid','stereographic','orthographic']){choose('[data-lens-model]',projection);frames[projection]=await exactFrame(previous);previous=frames[projection].url;}
      require(new Set(Object.values(frames).map(row=>row.pixel_hash)).size===4,'four_distinct_actual_fisheye_pictures');
      const bytes=Uint8Array.from(atob(cfg.profile_base64),c=>c.charCodeAt(0)),transfer=new DataTransfer();
      transfer.items.add(new File([bytes],'ENGINE_TEST_pinned_lensfun.xml',{type:'application/xml'}));
      const input=control('[data-lensfun-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));
      await until(()=>all('[data-lensfun-choice] option').length===106,'Real Lensfun file did not produce106 exact samples',2500);
      choose('[data-lensfun-choice]',cfg.profile_id);require($('[data-lensfun-choice] option:checked').textContent.includes('7 mm · crop 2 · ptlens'),'exact_measured_upstream_sample');
      require(Number($('[data-lensfun-crop]').value)===2,'calibration_capture_crop_explicit');click('[data-node-action="lensfun-apply"]');
      require($('[data-lens-model]').value==='lensfun','actual_profile_apply');frames.lensfun=await exactFrame(previous);
      click('#undo-button');selectLens(metrics.lens_id);require($('[data-lens-model]').value==='orthographic','one_undo_restores_fisheye');
      click('#redo-button');selectLens(metrics.lens_id);require($('[data-lens-model]').value==='lensfun'&&Number($('[data-lens-crop]').value)===2,'one_redo_restores_profile');
      await saved();await openProject(cfg.sentinel_id,cfg.sentinel_name);await openProject(cfg.project_id,cfg.project_name);selectClip();selectLens(metrics.lens_id);
      require($('[data-lens-model]').value==='lensfun'&&Number($('[data-lens-crop]').value)===2,'saved_profile_reopens_in_editor');
      frames.reopened=await exactFrame();require(frames.reopened.pixel_hash===frames.lensfun.pixel_hash,'reopened_picture_identical');
      require(!all('[data-node-key]').length,'static_calibration_has_no_unsupported_animation');
    }else if(cfg.operation==='render'){
      selectClip();selectLens(cfg.lens_id);metrics.lens_id=cfg.lens_id;
      require($('[data-lens-model]').value==='lensfun','reopened_measured_profile');frames.lensfun=await exactFrame();
      click('#export-button');click('[data-export="'+cfg.delivery+'"]');
      const label=cfg.delivery==='prores'?'ProRes export complete':'Render complete';
      await until(()=>$('#job-label').textContent===label&&!$('#download-job').hidden,'Actual lens movie export failed',4800);
      const href=$('#download-job').getAttribute('href'),url=new URL(href,location.href);
      require(url.origin===location.origin&&url.pathname.includes('/'+cfg.project_id+'/exports/'),'export_belongs_to_owned_project');
      metrics.movie_href=href;metrics.delivery=cfg.delivery;click('#download-job');
      if(cfg.delivery==='h264'){
        await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2,'H.264 export did not decode');click('#play-button');
        await until(()=>$('#render-video').currentTime>.06,'Actual editor export playback did not advance');
        metrics.playback={url:$('#render-video').getAttribute('src'),time:$('#render-video').currentTime,mechanism:'shipped editor transport'};
        if(!$('#render-video').paused)click('#play-button');
      }else{
        // The editor offers ProRes as a download, not a browser preview. Probe
        // that exact export with a separate test-owned native media element.
        // This certifies native decoding, not an added product transport flow.
        probe=document.createElement('video');probe.controls=true;probe.muted=true;probe.playsInline=true;
        probe.style.cssText='position:fixed;left:24px;bottom:28px;width:240px;z-index:10000;background:black';
        probe.setAttribute('aria-label','ENGINE TEST native ProRes export decoder');probe.src=url.pathname;document.body.append(probe);
        await until(()=>probe.readyState>=2,'Native ProRes export decoder is unavailable',2500);await probe.play();
        await until(()=>probe.currentTime>.06,'Native ProRes export clock did not advance',1000);
        metrics.playback={url:url.pathname,time:probe.currentTime,mechanism:'test-owned native video element; product ProRes transport is not asserted'};probe.pause();
      }
      require(metrics.playback.time>.06,'actual_export_decoder_and_clock_advance');
    }else throw Error('Unsupported native lens phase');
    return {passed:true,checks,frames,metrics,expected_download_count:cfg.operation==='render'?1:0,expect_download:cfg.operation==='render',physical_open_panel_asserted:false,physical_save_panel_asserted:false,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,checks,frames,metrics,error:String(error),physical_open_panel_asserted:false,physical_save_panel_asserted:false,elapsed_ms:Math.round(performance.now()-began)};}
  finally{if(probe){probe.pause();probe.removeAttribute('src');probe.load();probe.remove();}}
})();

// Shipped editor controls, real frame PNGs, shared undo and exported movie.
// Python supplies LENS_TEST and independently decodes all evidence.
return await (async()=>{
  const began=performance.now(),deadline=began+12500,steps=[],result={};
  const $=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail=()=>'; frame='+($('#frame-status')?.textContent||'')+'; toast='+($('#toast')?.textContent||'')+'; job='+($('#job-detail')?.textContent||'');
  function require(ok,message){if(!ok)throw Error(message+detail());}
  function control(selector){const element=$(selector);require(element&&!element.disabled&&!element.closest('[inert]'),'Unavailable control '+selector);element.scrollIntoView({block:'nearest',inline:'nearest'});return element;}
  const click=selector=>control(selector).click();
  function set(selector,value){const element=control(selector);element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  async function until(predicate,label,ms=1800){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(predicate())return;await sleep(30);}throw Error(label+detail());}
  function selectNode(id){const element=control('[data-node="'+id+'"]'),r=element.getBoundingClientRect(),data={bubbles:true,cancelable:true,pointerId:97,pointerType:'mouse',isPrimary:true,button:0,clientX:r.left+40,clientY:r.top+15};element.dispatchEvent(new PointerEvent('pointerdown',{...data,buttons:1}));window.dispatchEvent(new PointerEvent('pointerup',{...data,buttons:0}));}
  const value=name=>Number($('[data-node-param="'+name+'"]').value);
  function checkIntrinsics(){for(const name of ['fx','fy','cx','cy'])require(Math.abs(value(name)-LENS_TEST.params[name])<1e-12,'Copied scene intrinsic differs: '+name);}
  function checkCoefficients(reset=false){for(const name of ['k1','k2','k3','p1','p2'])require(Math.abs(value(name)-(reset?0:LENS_TEST.params[name]))<1e-12,'Coefficient differs: '+name);}
  function frameEvidence(){
    const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);
    require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'Lens frame did not use the export graph');
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
    const pixels=ctx.getImageData(0,0,160,90).data;let hash=2166136261;
    for(let i=0;i<pixels.length;i+=4)for(let c=0;c<3;c++)hash=Math.imul(hash^pixels[i+c],16777619);
    return {url:url.pathname,frame:6,hash:(hash>>>0).toString(16)};
  }
  async function exactFrame(previous){await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#processed-frame')?.naturalWidth===160&&$('#frame-status')?.textContent==='Rendered frame 6 · export graph'&&(!previous||new URL($('#processed-frame').currentSrc||$('#processed-frame').src,location.href).pathname!==previous),'Calibrated frame-6 PNG did not arrive',3500);return frameEvidence();}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&all('.media-item [data-add]').length===1,'Lens fixture did not bootstrap',3500);
    click('[data-add="'+LENS_TEST.asset_id+'"]');click('[data-mode="composite"]');click('#jump-start');
    set('[data-graph-add-type]','lens_distortion');click('[data-graph-action="add"]');
    result.lens_id=$('.compositor-node.selected').dataset.node;
    require($('[data-graph-output]').value===result.lens_id,'Lens was not connected to the selected picture');
    click('#undo-button');require(!all('[data-node-type="lens_distortion"]').length,'Add-lens undo failed');
    click('#redo-button');selectNode(result.lens_id);require(all('[data-node-type="lens_distortion"]').length===1,'Add-lens redo failed');
    click('[data-node-action="lens-camera"]');checkIntrinsics();
    click('#undo-button');require(value('fx')===1&&value('fy')===1,'Copy-camera single undo failed');
    click('#redo-button');checkIntrinsics();
    for(const name of ['k1','k2','k3','p1','p2'])set('[data-node-param="'+name+'"]',LENS_TEST.params[name]);
    const reset=control('[data-node-action="lens-reset"]'),rect=reset.getBoundingClientRect();
    require(rect.top>=0&&rect.bottom<=innerHeight&&rect.left>=0&&rect.right<=innerWidth,'Lens controls are clipped outside the visible window');
    click('[data-node-action="lens-reset"]');checkCoefficients(true);click('#undo-button');checkCoefficients();
    click('#redo-button');checkCoefficients(true);click('#undo-button');checkCoefficients();
    set('[data-node-param="k1"]',1);checkCoefficients();
    require(!$('#redo-button').disabled,'Rejected calibration edit discarded the existing redo entry');
    click('#redo-button');checkCoefficients(true);click('#undo-button');checkCoefficients();
    require(!all('[data-node-key]').length,'Static calibration exposes unsupported animation controls');
    steps.push('visible_lens_controls_camera_intrinsics_validation_and_single_undo_redo');
    for(let i=0;i<6;i++)click('#step-forward');
    require($('#timecode').textContent==='00:00:00:06','Frame-six seek failed');
    result.undistort_frame=await exactFrame();
    set('[data-node-param="direction"]','distort');click('#undo-button');require($('[data-node-param="direction"]').value==='undistort','Operation undo failed');
    click('#redo-button');require($('[data-node-param="direction"]').value==='distort','Operation redo failed');
    result.distort_frame=await exactFrame(result.undistort_frame.url);
    require(result.undistort_frame.hash!==result.distort_frame.hash,'Correction and reproduction returned the same pixels');
    steps.push('both_lens_operations_produce_real_distinct_paused_frames');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Calibrated lens graph did not save');
    click('#export-button');click('[data-export="h264"]');
    await until(()=>['Render complete','Job failed'].includes($('#job-label')?.textContent),'Calibrated movie did not finish',4500);
    require($('#job-label').textContent==='Render complete','Calibrated movie export failed');
    await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2,'Calibrated movie did not decode');
    click('#play-button');await until(()=>$('#render-video').currentTime>.06,'Calibrated movie did not play');
    result.video_src=$('#render-video').getAttribute('src');result.video_time=$('#render-video').currentTime;
    if(!$('#render-video').paused)click('#play-button');
    steps.push('save_export_and_play_calibrated_movie');
    return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),timecode:$('#timecode')?.textContent,frame_status:$('#frame-status')?.textContent,elapsed_ms:Math.round(performance.now()-began)};}
})();

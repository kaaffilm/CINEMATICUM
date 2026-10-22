// Native WKWebView: author independent media sources through shipped controls.
// Python supplies MULTI_SOURCE_TEST and independently checks real decoded media.
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
  function pointer(target,type,x,y){target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:94,pointerType:'mouse',isPrimary:true,button:0,buttons:type==='pointerup'?0:1,clientX:x,clientY:y,altKey:true}));}
  function selectNode(id){const element=control('[data-node="'+id+'"]'),r=element.getBoundingClientRect();pointer(element,'pointerdown',r.left+50,r.top+15);pointer(window,'pointerup',r.left+50,r.top+15);}
  function add(type){set('[data-graph-add-type]',type);click('[data-graph-action="add"]');return $('.compositor-node.selected')?.dataset.node;}
  function field(name){return $('[data-node-media-field="'+name+'"]')?.value;}
  function seek(frame){set('[data-node-animation-frame]',frame);require($('#timecode').textContent==='00:00:'+String(Math.floor(frame/12)).padStart(2,'0')+':'+String(frame%12).padStart(2,'0'),'Playhead seek failed');}
  function frameEvidence(){
    const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);
    require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'Frame did not use the export graph');
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
    const pixels=ctx.getImageData(0,0,160,90).data;let hash=2166136261;
    for(let i=0;i<pixels.length;i+=4)for(let c=0;c<3;c++)hash=Math.imul(hash^pixels[i+c],16777619);
    return {url:url.pathname,frame:12,hash:(hash>>>0).toString(16)};
  }
  async function exactFrame(previous){await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#processed-frame')?.naturalWidth===160&&$('#frame-status')?.textContent==='Rendered frame 12 · export graph'&&(!previous||new URL($('#processed-frame').currentSrc||$('#processed-frame').src,location.href).pathname!==previous),'The composed frame-12 PNG did not arrive',3500);return frameEvidence();}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&all('.media-item [data-add]').length===2,'Two-source fixture did not bootstrap',3500);
    require(!all('.timeline-clip[data-type="clip"]').length,'Fixture must start with an empty timeline');
    result.project_id=$('#project-select').value;
    click('[data-add="'+MULTI_SOURCE_TEST.red_id+'"]');result.original_clip_id=$('.timeline-clip[data-type="clip"]').dataset.clip;
    click('[data-mode="composite"]');click('#jump-start');
    const originalOutput=$('[data-graph-output]').value;
    result.source_id=add('media_source');
    require(result.source_id&&field('asset_id')===MULTI_SOURCE_TEST.blue_id,'Additional source did not choose the other project movie');
    require($('[data-graph-output]').value===originalOutput,'Adding a disconnected source changed the graph output');
    click('#undo-button');require(!all('[data-node-type="media_source"]').length,'One-step add-source undo failed');
    click('#redo-button');require(all('[data-node-type="media_source"]').length===1,'Add-source redo failed');selectNode(result.source_id);
    set('[data-node-media-field="duration"]',8);set('[data-node-media-field="source_in"]',4);set('[data-node-media-field="offset"]',6);
    set('[data-node-media-field="outside"]','hold');click('#undo-button');require(field('outside')==='transparent','One-step outside-policy undo failed');
    click('#redo-button');require(field('outside')==='hold','Outside-policy redo failed');
    set('[data-node-media-field="outside"]','transparent');
    require($('[data-node-media-sample]').textContent.includes('transparent'),'Leading source gap was not shown');
    // A rejected edit must keep both graph values and the shared undo stack.
    set('[data-node-media-field="duration"]',999);
    require(field('duration')==='8','Out-of-range media duration was saved');
    steps.push('additional_owned_media_source_timing_validation_and_undo_redo');

    result.mask_id=add('mask');set('[data-node-param="shape"]','rectangle');
    for(const [name,value]of [['x',.75],['y',.5],['width',.5],['height',1],['feather',0]])set('[data-node-param="'+name+'"][type="number"]',value);
    result.merge_id=add('merge');
    require($('[data-node-connection="0"]').value===originalOutput&&$('[data-node-connection="1"]').value===result.mask_id,'Two independent media branches were not merged');
    seek(12);result.before_frame=await exactFrame();
    selectNode(result.source_id);require($('[data-node-media-sample]').textContent.includes('source frame 10'),'Source sampling differs from independent animation time');
    selectNode(result.merge_id);steps.push('two_source_mask_merge_and_real_paused_frame');

    seek(8);click('#split-button');require(all('.timeline-clip[data-type="clip"]').length===2,'Split did not preserve both clip windows');
    result.right_clip_id=$('.timeline-clip.selected').dataset.clip;
    const bar=control('.timeline-clip.selected'),edge=control('.timeline-clip.selected [data-edge="left"]'),r=bar.getBoundingClientRect(),e=edge.getBoundingClientRect();
    const x=e.left+e.width/2,y=e.top+e.height/2,delta=r.width/16*3;
    pointer(edge,'pointerdown',x,y);pointer(window,'pointermove',x+delta,y);pointer(window,'pointerup',x+delta,y);
    seek(12);result.after_frame=await exactFrame(result.before_frame.url);
    require(result.before_frame.hash===result.after_frame.hash,'Split and trim changed the retained multisource frame');
    selectNode(result.source_id);require(field('source_in')==='4'&&field('offset')==='6'&&field('duration')==='8','Editing the clip rewrote independent source timing');
    selectNode(result.merge_id);steps.push('split_and_leading_trim_preserve_source_domain_and_pixels');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Multi-source graph did not save');
    click('#export-button');click('[data-export="h264"]');
    await until(()=>['Render complete','Job failed'].includes($('#job-label')?.textContent),'Multi-source movie did not finish',4200);
    require($('#job-label').textContent==='Render complete','Multi-source export failed');
    await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2,'Export movie did not decode');
    click('#play-button');await until(()=>$('#render-video').currentTime>.06,'Export movie did not play');
    result.video_src=$('#render-video').getAttribute('src');result.video_time=$('#render-video').currentTime;
    if(!$('#render-video').paused)click('#play-button');
    steps.push('save_export_and_play_real_composite');
    return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),timecode:$('#timecode')?.textContent,frame_status:$('#frame-status')?.textContent,elapsed_ms:Math.round(performance.now()-began)};}
})();

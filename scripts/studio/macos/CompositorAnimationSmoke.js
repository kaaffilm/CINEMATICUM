// Actual shipped controls in WKWebView. No application-state or HTTP mutation.
// The Python fixture independently checks saved animation, PNGs and movie pixels.
return await (async()=>{
  const began=performance.now(),deadline=began+13000,steps=[],result={};
  const $=selector=>document.querySelector(selector),all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail=()=>'; frame='+($('#frame-status')?.textContent||'')+'; toast='+($('#toast')?.textContent||'')+'; job='+($('#job-detail')?.textContent||'');
  function require(condition,message){if(!condition)throw Error(message+detail());}
  function control(selector){const element=$(selector);require(element&&!element.disabled&&!element.closest('[inert]'),'Unavailable control '+selector);element.scrollIntoView({block:'nearest',inline:'nearest'});return element;}
  function click(selector){control(selector).click();}
  function set(selector,value){const element=control(selector);element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  function value(name){return Number(control('[data-node-param="'+name+'"][type="number"]').value);}
  function close(actual,expected,label){require(Math.abs(actual-expected)<.00001,label+': '+actual+' != '+expected);}
  async function until(predicate,label,ms=1800){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(predicate())return;await sleep(35);}throw Error(label+detail());}
  function pointer(target,type,x,y){target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:84,pointerType:'mouse',isPrimary:true,button:0,buttons:type==='pointerup'?0:1,clientX:x,clientY:y,altKey:true}));}
  function selectNode(id){const element=control('[data-node="'+id+'"]'),r=element.getBoundingClientRect();pointer(element,'pointerdown',r.left+50,r.top+15);pointer(window,'pointerup',r.left+50,r.top+15);}
  function seek(frame){set('[data-node-animation-frame]',frame);require($('#timecode').textContent==='00:00:'+String(Math.floor(frame/12)).padStart(2,'0')+':'+String(frame%12).padStart(2,'0'),'Playhead seek failed');}
  function add(kind){set('[data-graph-add-type]',kind);click('[data-graph-action="add"]');return $('[data-graph-output]').value;}
  function moveVertex(index,to){
    const svg=control('[data-polygon-editor]'),handle=control('[data-polygon-point="'+index+'"]'),r=svg.getBoundingClientRect(),h=handle.getBoundingClientRect();
    const x=r.left+(18+220*to[0])/256*r.width,y=r.top+(18+220*to[1])/256*r.height;
    pointer(handle,'pointerdown',h.left+h.width/2,h.top+h.height/2);
    pointer(window,'pointermove',(h.left+h.width/2+x)/2,(h.top+h.height/2+y)/2);
    pointer(window,'pointermove',x,y);pointer(window,'pointerup',x,y);
  }
  function chooseVertex(index){const handle=control('[data-polygon-point="'+index+'"]'),r=handle.getBoundingClientRect();pointer(handle,'pointerdown',r.left+r.width/2,r.top+r.height/2);pointer(window,'pointerup',r.left+r.width/2,r.top+r.height/2);}
  function frameEvidence(){
    const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);
    require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'Frame did not use the project renderer');
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const context=canvas.getContext('2d');context.drawImage(image,0,0);
    const pixels=context.getImageData(0,0,160,90).data;let hash=2166136261,bright=0;
    for(let i=0;i<pixels.length;i+=4){for(let c=0;c<3;c++)hash=Math.imul(hash^pixels[i+c],16777619);if(pixels[i]+pixels[i+1]+pixels[i+2]>50)bright++;}
    require(bright>400,'The authored picture is empty');return {url:url.pathname,frame:12,hash:(hash>>>0).toString(16),bright_pixels:bright,width:160,height:90};
  }
  async function exactFrame(previous){await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#processed-frame')?.naturalWidth===160&&$('#frame-status')?.textContent==='Rendered frame 12 · export graph'&&(!previous||new URL($('#processed-frame').currentSrc||$('#processed-frame').src,location.href).pathname!==previous),'The exact frame-12 PNG did not arrive',3500);return frameEvidence();}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('.media-item [data-add]'),'Source project did not bootstrap',3500);
    require(all('.timeline-clip[data-type="clip"]').length===0,'Fixture must start with an empty timeline');
    result.project_id=$('#project-select').value;click('.media-item [data-add]');
    result.original_clip_id=$('.timeline-clip[data-type="clip"]').dataset.clip;
    click('[data-mode="composite"]');click('#jump-start');
    result.grade_id=add('grade');click('[data-node-key="exposure"]');
    set('[data-node-animation-easing]','ease_out');seek(16);
    set('[data-node-param="exposure"][type="number"]',1);
    result.mask_id=add('mask');set('[data-node-param="shape"]','polygon');
    set('[data-node-param="x"][type="number"]',.25);set('[data-node-param="width"][type="number"]',.9);set('[data-node-param="height"][type="number"]',.9);set('[data-node-param="feather"][type="number"]',.12);
    seek(0);click('[data-node-key="x"]');set('[data-node-animation-easing]','ease_in_out');click('[data-node-key="points"]');
    seek(16);set('[data-node-param="x"][type="number"]',.75);
    moveVertex(1,[.7,.2]);
    close(Number($('[data-polygon-coordinate="0"]').value),.7,'Animated polygon drag X');
    require(all('[data-node-animation-seek]').length===2,'Path did not gain its second key');
    click('#undo-button');close(Number($('[data-polygon-coordinate="0"]').value),.5,'One-step path undo');require(all('[data-node-animation-seek]').length===1,'Undo retained a spurious path key');
    click('#redo-button');close(Number($('[data-polygon-coordinate="0"]').value),.7,'One-step path redo');
    require($('[data-node-action="polygon-add"]').disabled&&$('[data-node-action="polygon-remove"]').disabled,'Animated path topology was not protected');
    steps.push('independent_grade_mask_and_path_keys_one_gesture_undo_redo');

    seek(8);close(value('x'),.5,'Smooth mask midpoint');
    close(Number($('[data-polygon-coordinate="0"]').value),.6,'Linear vertex midpoint');
    selectNode(result.grade_id);close(value('exposure'),.75,'Independent eased exposure midpoint');
    selectNode(result.mask_id);seek(12);close(value('x'),.671875,'Mask at frame12');
    close(Number($('[data-polygon-coordinate="0"]').value),.65,'Vertex at frame12');
    result.before_frame=await exactFrame();steps.push('evaluated_inspector_and_real_paused_frame');

    seek(8);click('#split-button');require(all('.timeline-clip[data-type="clip"]').length===2,'Split did not produce two clips');
    result.right_clip_id=$('.timeline-clip.selected').dataset.clip;close(value('x'),.5,'Split reset animation timing');chooseVertex(1);
    const bar=control('.timeline-clip.selected'),edge=control('.timeline-clip.selected [data-edge="left"]'),r=bar.getBoundingClientRect(),e=edge.getBoundingClientRect();
    const start=e.left+e.width/2,delta=r.width/16*3,y=e.top+e.height/2;
    pointer(edge,'pointerdown',start,y);pointer(window,'pointermove',start+delta,y);pointer(window,'pointerup',start+delta,y);
    seek(12);close(value('x'),.671875,'Left trim changed the motion trajectory');
    close(Number($('[data-polygon-coordinate="0"]').value),.65,'Left trim changed the path trajectory');
    click('#undo-button');close(value('x'),.671875,'Trim undo lost the sampled pose');click('#redo-button');close(value('x'),.671875,'Trim redo lost the sampled pose');
    result.after_frame=await exactFrame(result.before_frame.url);
    require(result.before_frame.hash===result.after_frame.hash,'Split and trim changed the retained exact frame');
    steps.push('split_left_trim_and_undo_redo_preserve_decoded_frame');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Shared project did not save');
    click('#export-button');click('[data-export="h264"]');
    await until(()=>['Render complete','Job failed'].includes($('#job-label')?.textContent),'Animated movie did not finish',4500);
    require($('#job-label').textContent==='Render complete','Animated movie render failed');
    await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2,'Actual movie did not decode');
    click('#play-button');await until(()=>$('#render-video').currentTime>.06,'Actual movie did not play');
    result.video_src=$('#render-video').getAttribute('src');result.video_time=$('#render-video').currentTime;if(!$('#render-video').paused)click('#play-button');
    steps.push('save_render_and_play_actual_animated_movie');
    return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),timecode:$('#timecode')?.textContent,toast:$('#toast')?.textContent,frame_status:$('#frame-status')?.textContent,elapsed_ms:Math.round(performance.now()-began)};}
})();

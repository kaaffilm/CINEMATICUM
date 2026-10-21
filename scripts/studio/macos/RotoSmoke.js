// Real shipped DOM controls. The owner fixture independently checks saved
// cubic geometry, the renderer's PNG receipt and the decoded export.
return await (async()=>{
  const began=performance.now(),deadline=began+13000,steps=[],result={};
  const $=selector=>document.querySelector(selector),all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail=()=>'; frame='+($('#frame-status')?.textContent||'')+'; toast='+($('#toast')?.textContent||'')+'; job='+($('#job-detail')?.textContent||'');
  function require(condition,message){if(!condition)throw Error(message+detail());}
  function control(selector){const element=$(selector);require(element&&!element.disabled&&!element.closest('[inert]'),'Unavailable control '+selector);element.scrollIntoView({block:'nearest',inline:'nearest'});return element;}
  function click(selector){control(selector).click();}
  function set(selector,value){const element=control(selector);element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  function close(actual,expected,label){require(Math.abs(actual-expected)<.00001,label+': '+actual+' != '+expected);}
  async function until(predicate,label,ms=1800){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(predicate())return;await sleep(35);}throw Error(label+detail());}
  function pointer(target,type,x,y){target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:86,pointerType:'mouse',isPrimary:true,button:0,buttons:type==='pointerup'?0:1,clientX:x,clientY:y}));}
  function selectNode(id){const element=control('[data-node="'+id+'"]'),r=element.getBoundingClientRect();pointer(element,'pointerdown',r.left+50,r.top+15);pointer(window,'pointerup',r.left+50,r.top+15);}
  function seek(frame){set('[data-node-animation-frame]',frame);require($('#timecode').textContent==='00:00:00:'+String(frame).padStart(2,'0'),'Playhead seek failed');}
  function add(kind){set('[data-graph-add-type]',kind);click('[data-graph-action="add"]');return $('[data-graph-output]').value;}
  function moveHandle(anchor,handle,to){
    set('[data-bezier-selection]',anchor);
    const svg=control('[data-bezier-editor]'),target=control('[data-bezier-point="'+anchor+'"][data-bezier-handle="'+handle+'"]');
    const screen=(x,y)=>{const p=svg.createSVGPoint();p.x=x;p.y=y;return p.matrixTransform(svg.getScreenCTM());};
    const start=screen(Number(target.getAttribute('cx')),Number(target.getAttribute('cy'))),end=screen(18+220*to[0],18+220*to[1]);
    pointer(target,'pointerdown',start.x,start.y);pointer(window,'pointermove',end.x,end.y);pointer(window,'pointerup',end.x,end.y);
  }
  function frameEvidence(){
    const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);
    require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'Frame did not use the project renderer');
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const context=canvas.getContext('2d');context.drawImage(image,0,0);
    const pixels=context.getImageData(0,0,160,90).data;let hash=2166136261;
    for(let i=0;i<pixels.length;i+=4)for(let c=0;c<3;c++)hash=Math.imul(hash^pixels[i+c],16777619);
    return {url:url.pathname,frame:6,hash:(hash>>>0).toString(16),width:160,height:90};
  }
  async function exactFrame(previous){await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#processed-frame')?.naturalWidth===160&&$('#frame-status')?.textContent==='Rendered frame 6 · export graph'&&(!previous||new URL($('#processed-frame').currentSrc||$('#processed-frame').src,location.href).pathname!==previous),'The exact frame-6 PNG did not arrive',3500);return frameEvidence();}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('.media-item [data-add]'),'Source project did not bootstrap',3500);
    require(all('.timeline-clip[data-type="clip"]').length===0,'Fixture must start with an empty timeline');
    result.project_id=$('#project-select').value;click('.media-item [data-add]');click('[data-mode="composite"]');click('#jump-start');
    result.mask_id=add('mask');result.source_id=$('[data-node-connection="0"]').value;
    set('[data-node-param="shape"]','bezier');set('[data-node-param="width"][type="number"]',1);set('[data-node-param="height"][type="number"]',1);set('[data-node-param="feather"][type="number"]',.2);
    click('[data-node-key="bezier"]');set('[data-node-tangent="out_tangent"]',2.5);seek(8);
    moveHandle(0,4,[.8,.22]);close(Number($('[data-bezier-coordinate="4"]').value),.8,'Outgoing handle gesture X');close(Number($('[data-bezier-coordinate="5"]').value),.22,'Outgoing handle gesture Y');
    require(all('[data-node-animation-seek]').length===2,'The path gesture did not create its second key');
    click('#undo-button');close(Number($('[data-bezier-coordinate="4"]').value),.7209139,'One gesture undo');require(all('[data-node-animation-seek]').length===1,'Undo retained a spurious path key');
    click('#redo-button');close(Number($('[data-bezier-coordinate="4"]').value),.8,'One gesture redo');
    set('[data-bezier-coordinate="6"]',2.5);set('[data-node-tangent="in_tangent"]',.2);seek(6);
    const t=.75,amount=.7*t*t*t-2.2*t*t+2.5*t;
    close(Number($('[data-bezier-coordinate="4"]').value),.7209139+(.8-.7209139)*amount,'Custom cubic handle evaluation');
    close(Number($('[data-bezier-coordinate="6"]').value),1+1.5*amount,'Animated point feather evaluation');
    steps.push('real_cubic_handles_point_feather_tangents_and_one_gesture_history');
    result.grade_id=add('grade');set('[data-node-connection="0"]',result.source_id);set('[data-node-effect-mask]',result.mask_id);set('[data-node-param="exposure"][type="number"]',1);
    require(all('[data-node-input]').length>=3,'Effect input ports were not drawn');
    result.before_frame=await exactFrame();selectNode(result.mask_id);set('[data-bezier-selection]',0);
    click('[data-node-action="bezier-split"]');require($('[data-bezier-selection]').options.length===5,'Cubic subdivision did not insert an anchor');
    click('#undo-button');require($('[data-bezier-selection]').options.length===4,'Subdivision undo');click('#redo-button');require($('[data-bezier-selection]').options.length===5,'Subdivision redo');
    result.after_frame=await exactFrame(result.before_frame.url);
    require(result.before_frame.hash===result.after_frame.hash,'Exact cubic subdivision changed the rendered picture');
    steps.push('effect_mask_port_and_animated_shape_subdivision_preserve_real_pixels');
    const api=window.CinematicumCompositor,p=JSON.parse(JSON.stringify(api.nodeTypes.mask.defaults));p.shape='bezier';p.bezier[1][6]=2.75;
    const svg=api.svgDocument(p,160,90),roundtrip=api.parseSvgDocument(svg);
    require(JSON.stringify(p)===JSON.stringify(roundtrip),'Cubic SVG authoring metadata lost geometry or feather');
    let rejected=0;for(const unsafe of ['<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><path d="M0 0 L1 0 L0 1Z"/></svg>','<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.invalid/a.png"/></svg>'])try{api.parseSvgDocument(unsafe);}catch(error){rejected++;}
    require(rejected===2,'Unsupported SVG active or external content was accepted');result.svg_checks={metadata_roundtrip:true,unsupported_content_rejected:rejected};
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Shared project did not save');
    click('#export-button');click('[data-export="h264"]');await until(()=>['Render complete','Job failed'].includes($('#job-label')?.textContent),'Bezier movie did not finish',4500);require($('#job-label').textContent==='Render complete','Bezier movie render failed');
    await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2,'Actual movie did not decode');click('#play-button');await until(()=>$('#render-video').currentTime>.06,'Actual movie did not play');
    result.video_src=$('#render-video').getAttribute('src');result.video_time=$('#render-video').currentTime;if(!$('#render-video').paused)click('#play-button');
    steps.push('strict_svg_roundtrip_and_actual_saved_animated_movie_playback');return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),timecode:$('#timecode')?.textContent,toast:$('#toast')?.textContent,frame_status:$('#frame-status')?.textContent,elapsed_ms:Math.round(performance.now()-began)};}
})();

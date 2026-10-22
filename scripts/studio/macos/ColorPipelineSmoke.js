// Native WK acceptance through the shipped colour controls. Fixtures are test
// signals only. API GETs read evidence; no hidden application state is mutated.
return await (async()=>{
  const began=performance.now(),deadline=began+12000,steps=[],result={};
  const $=selector=>document.querySelector(selector),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostics=()=>'; color='+($('[data-color-status]')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  function require(value,message){if(!value)throw Error(message+diagnostics());}
  function control(selector){const e=$(selector);require(e&&!e.disabled,'Unavailable control '+selector);return e;}
  const click=selector=>control(selector).click();
  function set(selector,value){const e=control(selector);e.value=String(value);e.dispatchEvent(new Event('change',{bubbles:true}));}
  async function until(predicate,label,ms=1600){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(predicate())return;await sleep(25);}throw Error(label+diagnostics());}
  function file(name,text){const transfer=new DataTransfer();transfer.items.add(new File([text],name,{type:'text/plain'}));const input=control('[data-color-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  function applyVisibility(phase){
    const dialog=$('.cinematicum-color-pipeline'),button=control('[data-color-apply]'),footer=dialog.querySelector('footer'),body=dialog.querySelector('.color-body');
    const d=dialog.getBoundingClientRect(),b=button.getBoundingClientRect(),f=footer.getBoundingClientRect(),content=body.getBoundingClientRect();
    require(dialog.open&&d.width>0&&d.height>0&&d.left>=0&&d.top>=0&&d.right<=innerWidth+.5&&d.bottom<=innerHeight+.5,'Color dialog exceeds the actual viewport');
    require(b.width>20&&b.height>20&&b.left>=d.left&&b.top>=f.top&&b.right<=d.right&&b.bottom<=f.bottom&&b.bottom<=d.bottom,'Apply is clipped outside its visible footer');
    require(content.bottom<=f.top+.5&&content.height>0,'Scrollable color controls overlap the Apply footer');
    const points=[[.5,.5],[.15,.25],[.85,.25],[.15,.75],[.85,.75]];
    for(const [x,y] of points){const hit=document.elementFromPoint(b.left+b.width*x,b.top+b.height*y);require(hit===button||button.contains(hit),'Apply is obscured or cannot receive a pointer');}
    const bounds=rect=>({x:Math.round(rect.x),y:Math.round(rect.y),width:Math.round(rect.width),height:Math.round(rect.height)});
    const evidence={phase,viewport:{width:innerWidth,height:innerHeight},dialog:bounds(d),apply:bounds(b),body_client_height:body.clientHeight,body_scroll_height:body.scrollHeight,hit_points:points.length};
    (result.apply_visibility??=[]).push(evidence);return evidence;
  }
  function frameEvidence(){const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'Paused image did not come from the export graph');const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);return {url:url.pathname,pixel:[...ctx.getImageData(80,45,1,1).data]};}
  async function exactFrame(previous){await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame')?.complete&&$('#processed-frame')?.naturalWidth===160&&$('#frame-status')?.textContent==='Rendered frame 0 · export graph'&&(!previous||new URL($('#processed-frame').currentSrc||$('#processed-frame').src,location.href).pathname!==previous),'Actual paused frame did not finish',2400);return frameEvidence();}
  async function open(){click('[data-action="color-pipeline"]');await until(()=>$('.cinematicum-color-pipeline')?.open&&!$('[data-color-apply]')?.disabled,'Color editor did not load');applyVisibility('open');}
  const text='TITLE "ENGINE TEST domain channel map"\nLUT_3D_SIZE 2\nDOMAIN_MIN 0.25 -0.5 0.1\nDOMAIN_MAX 0.75 1.5 0.6\n'+[0,1].flatMap(b=>[0,1].flatMap(g=>[0,1].map(r=>`${1-r} ${g} ${b}`))).join('\n')+'\n';
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('.timeline-clip[data-type="clip"]'),'Color fixture did not bootstrap',3500);
    const clip=$('.timeline-clip[data-type="clip"]');result.clip_id=clip.dataset.clip;result.project_id=$('#project-select').value;const initialSaveState=$('#save-state').textContent;clip.focus();clip.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));click('[data-mode="color"]');click('#jump-start');
    result.before_frame=await exactFrame();await open();
    file('ENGINE_TEST_invalid.cube','LUT_3D_SIZE 2\n0 0 0\n');
    await until(()=>!$('[data-color-import]').disabled&&$('[data-color-status]').classList.contains('error'),'Invalid cube was not rejected');
    require($('[data-color-lut]').value==='','Invalid import selected a LUT');steps.push('reject_incomplete_cube_without_changing_clip');
    file('ENGINE_TEST_domain.cube',text);await until(()=>!$('[data-color-import]').disabled&&$('[data-color-lut]').value.length===64,'Valid cube did not import');
    result.sha256=$('[data-color-lut]').value;require($('[data-color-lut-detail]').textContent.includes('0.25, -0.5, 0.1'),'Custom domain was not displayed');
    require($('#save-state').textContent===initialSaveState,'Import changed the saved clip before Apply');
    const beforeScroll=applyVisibility('imported'),scrollBody=$('.cinematicum-color-pipeline .color-body');scrollBody.scrollTop=scrollBody.scrollHeight;
    const afterScroll=applyVisibility('body-scrolled');require(beforeScroll.apply.y===afterScroll.apply.y,'Scrolling the color controls moved Apply off its fixed footer');
    if(scrollBody.scrollHeight>scrollBody.clientHeight+1)require(scrollBody.scrollTop>0,'Overflowing color controls cannot be scrolled');
    scrollBody.scrollTop=0;steps.push('apply_visible_and_hit_testable_in_actual_viewport');
    set('[data-color-interpolation]','trilinear');click('[data-color-apply]');await until(()=>!$('.cinematicum-color-pipeline').open,'Color Apply did not close');
    require($('.cinematicum-color-pipeline').getClientRects().length===0,'Closed color dialog still occupies visible layout');
    require($('#save-state').textContent==='UNSAVED','Color Apply was not an undoable edit');result.after_frame=await exactFrame(result.before_frame.url);
    require(result.after_frame.pixel.some((v,i)=>i<3&&Math.abs(v-result.before_frame.pixel[i])>15),'Imported LUT did not change actual decoded pixels');
    steps.push('import_domain_lut_and_apply_actual_rendered_pixels');
    click('#undo-button');await open();require($('[data-color-lut]').value==='','One undo did not remove the applied pipeline');click('[data-color-close]');
    click('#redo-button');await open();require($('[data-color-lut]').value===result.sha256&&$('[data-color-interpolation]').value==='trilinear','Redo did not restore LUT and interpolation');
    set('[data-color-preset]','logc3');require($('[data-color-transfer]').value==='logc3_ei800'&&$('[data-color-primaries]').value==='arri_wide_gamut3','Camera preset did not bind transfer and primaries');
    set('[data-color-preset]','rec709');click('[data-color-close]');steps.push('one_change_undo_redo_and_explicit_camera_preset');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Color edit did not save');
    const response=await fetch(`/api/projects/${encodeURIComponent(result.project_id)}/color-luts`);require(response.ok,'Project LUT listing failed');const listing=await response.json();require(listing.luts?.some(lut=>lut.sha256===result.sha256&&lut.dimension===3&&lut.size===2),'Project did not own imported LUT identity');
    steps.push('save_project_and_read_content_addressed_lut_descriptor');
    // Keep the actual tools visible for the native screenshot; opening a
    // dialog performs no authoring mutation and preserves the saved state.
    await open();require($('#save-state').textContent==='SAVED LOCALLY','Reopening color tools changed the project');
    return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),elapsed_ms:Math.round(performance.now()-began)};}
})();

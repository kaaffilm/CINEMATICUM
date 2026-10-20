// Async-function body for SmokeTest.swift --script. TEST geometry, never a film.
// Operates DOM controls only; no app-state mutations or HTTP shortcuts.
return await (async () => {
  const began=performance.now(),deadline=began+14500,steps=[];
  const $=selector=>document.querySelector(selector);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostics=()=>'; toast='+($('#toast')?.textContent||'')+'; scene='+($('.scene-message')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'');
  async function until(predicate,label,milliseconds=2000) {
    const end=Math.min(deadline,performance.now()+milliseconds);
    while(performance.now()<end){if(predicate())return;await sleep(40);}
    throw Error(label+diagnostics());
  }
  function click(selector) {
    const element=$(selector);
    if(!element||element.disabled)throw Error('Unavailable control: '+selector+diagnostics());
    element.click();
  }
  function set(selector,value) {
    const element=$(selector);
    if(!element||element.disabled)throw Error('Unavailable field: '+selector+diagnostics());
    element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function sampleViewport() {
    const canvas=$('.scene-viewport canvas');
    if(!canvas||canvas.width<32||canvas.height<32)throw Error('3D canvas has no visible drawing buffer.');
    const gl=canvas.getContext('webgl');
    if(!gl||gl.isContextLost())throw Error('The real WebGL context is unavailable.');
    const bytes=new Uint8Array(canvas.width*canvas.height*4);
    gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
    if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL readPixels failed.');
    const samples=[],colors=new Set();let different=0;
    for(let y=0;y<40;y++)for(let x=0;x<64;x++){
      const px=Math.min(canvas.width-1,Math.floor((x+.5)*canvas.width/64)),py=Math.min(canvas.height-1,Math.floor((y+.5)*canvas.height/40)),index=(py*canvas.width+px)*4;
      const rgb=[bytes[index],bytes[index+1],bytes[index+2]];samples.push(...rgb);
      colors.add(rgb.map(value=>value>>3).join(','));
      if(Math.abs(rgb[0]-bytes[0])+Math.abs(rgb[1]-bytes[1])+Math.abs(rgb[2]-bytes[2])>18)different++;
    }
    return {width:canvas.width,height:canvas.height,samples,unique_colors:colors.size,nonuniform_pixels:different};
  }
  try {
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('#project-select')?.value,'Empty test project did not bootstrap',5000);
    if(document.querySelectorAll('.media-item[data-asset]').length||document.querySelectorAll('.timeline-clip').length)throw Error('The scene test must start without media or timeline clips.');
    steps.push('bootstrap_empty_project');
    click('[data-mode="3d"]');
    await until(()=>$('.scene-viewport canvas')?.getBoundingClientRect().width>100,'3D workspace did not mount');
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const empty=sampleViewport();
    click('[data-scene-add="cube"]');
    set('[data-scene-property="name"]','ENGINE TEST — authored cube');
    set('.scene-end-frame',2);
    set('.scene-samples select',4);
    set('[data-scene-property="material.color"]','#4d9bd8');
    set('.scene-current-frame',1);
    click('[data-scene-action="keyframe"]');
    await until(()=>$('[data-scene-key="1"]'),'First pose key was not created');
    set('.scene-current-frame',2);
    set('[data-scene-property="position.0"]',.6);
    set('[data-scene-property="rotation.2"]',25);
    await until(()=>document.querySelectorAll('[data-scene-key]').length===2&&Number($('[data-scene-property="position.0"]')?.value)===.6&&Number($('[data-scene-property="rotation.2"]')?.value)===25,'Second pose did not persist in scene controls');
    steps.push('author_cube_material_and_two_pose_keys');
    const picture=sampleViewport();let changed=0;
    for(let i=0;i<picture.samples.length;i+=3)if(Math.abs(picture.samples[i]-empty.samples[i])+Math.abs(picture.samples[i+1]-empty.samples[i+1])+Math.abs(picture.samples[i+2]-empty.samples[i+2])>25)changed++;
    if(picture.unique_colors<4||picture.nonuniform_pixels<20||changed<8)throw Error('The viewport did not draw the authored geometry: '+JSON.stringify({colors:picture.unique_colors,nonuniform:picture.nonuniform_pixels,changed}));
    steps.push('read_actual_webgl_pixels');
    click('#save-project');
    await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Scene save did not finish',2500);
    steps.push('save_editable_scene');
    click('[data-scene-action="render"]');
    await until(()=>['Media ready','Job failed','Job cancelled'].includes($('#job-label')?.textContent),'Actual Blender render did not complete in the bounded test',11000);
    if($('#job-label').textContent!=='Media ready')throw Error('Scene render failed'+diagnostics());
    await until(()=>$('.media-item[data-asset]')&&!$('#download-scene').hidden&&$('#download-scene').getAttribute('href')?.includes('.blend'),'Rendered movie or downloadable Blender source was not admitted',1500);
    steps.push('render_actual_blender_movie_and_source');
    const assetID=$('.media-item[data-asset]').dataset.asset,sceneHref=$('#download-scene').getAttribute('href'),movieHref=$('#download-job').getAttribute('href');
    const assetSelector='.media-item[data-asset="'+assetID+'"]';
    let undoCount=0;
    // Rendering may checkpoint an equivalent normalized recipe. Cross that
    // snapshot, if present, to undo the last authored rotation key itself.
    do {
      click('#undo-button');undoCount++;
      if(!$(assetSelector))throw Error('Undo removed completed scene media from the bin.');
    } while(Number($('[data-scene-property="rotation.2"]')?.value)===25&&undoCount<3);
    const undoneRotation=Number($('[data-scene-property="rotation.2"]')?.value);
    if(undoneRotation!==0||Number($('[data-scene-property="position.0"]')?.value)!==.6)throw Error('Undo did not restore the previous authored pose.');
    for(let i=0;i<undoCount;i++){
      click('#redo-button');
      if(!$(assetSelector))throw Error('Redo removed completed scene media from the bin.');
    }
    if(Number($('[data-scene-property="rotation.2"]')?.value)!==25||Number($('[data-scene-property="position.0"]')?.value)!==.6||document.querySelectorAll('[data-scene-key]').length!==2)throw Error('Redo did not restore both authored scene keys.');
    steps.push('undo_redo_preserves_rendered_media');
    $(assetSelector).dispatchEvent(new MouseEvent('dblclick',{bubbles:true,view:window,button:0}));
    await until(()=>document.querySelectorAll('.timeline-clip[data-type="clip"]').length===1,'Rendered shot did not enter the timeline');
    click('#save-project');
    await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Timeline save did not finish',1500);
    steps.push('add_authored_shot_to_timeline_and_save');
    return {passed:true,steps,project_id:$('#project-select').value,asset_id:assetID,scene_href:sceneHref,movie_href:movieHref,scene_frame:Number($('.scene-current-frame').value),scene_key_count:document.querySelectorAll('[data-scene-key]').length,undo_count:undoCount,undone_rotation:undoneRotation,webgl:{width:picture.width,height:picture.height,unique_colors:picture.unique_colors,nonuniform_pixels:picture.nonuniform_pixels,changed_pixels_from_empty:changed},job_label:$('#job-label').textContent,elapsed_ms:Math.round(performance.now()-began)};
  } catch(error) {
    return {passed:false,steps,error:String(error),toast:$('#toast')?.textContent||'',scene_message:$('.scene-message')?.textContent||'',job_label:$('#job-label')?.textContent||'',job_detail:$('#job-detail')?.textContent||'',elapsed_ms:Math.round(performance.now()-began)};
  }
})();

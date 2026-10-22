// Async-function body for SmokeTest.swift --script. The Python harness supplies
// MESH_IMPORT_TEST with explicit test OBJ/MTL bytes. Only ordinary DOM controls
// and a real FileList are operated; no application state or HTTP is mutated.
return await (async () => {
  const began=performance.now(),deadline=began+11500,steps=[],$=selector=>document.querySelector(selector);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),count=()=>document.querySelectorAll('.scene-object-list [data-scene-select="object"]').length;
  const diagnostics=()=>'; import='+($('.scene-import-status')?.textContent||'')+'; scene='+($('.scene-message')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,milliseconds=1800) {const end=Math.min(deadline,performance.now()+milliseconds);while(performance.now()<end){if(predicate())return;await sleep(30);}throw Error(label+diagnostics());}
  function click(selector) {const element=$(selector);if(!element||element.disabled)throw Error('Unavailable control '+selector+diagnostics());element.click();}
  function set(selector,value) {const element=$(selector);if(!element||element.disabled)throw Error('Unavailable field '+selector+diagnostics());element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  function chooseFiles(files) {
    const input=$('[data-scene-import-file]');if(!input||input.disabled)throw Error('Mesh file input is unavailable.');
    const transfer=new DataTransfer();for(const file of files)transfer.items.add(new File([file.text],file.name,{type:'text/plain'}));
    input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function picture() {
    const canvas=$('.scene-viewport canvas'),gl=canvas?.getContext('webgl');if(!gl||gl.isContextLost()||canvas.width<100||canvas.height<100)throw Error('An actual WebGL viewport is required.');
    const pixels=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL pixels could not be read.');
    const colors=new Set();let colorful=0;
    for(let y=0;y<48;y++)for(let x=0;x<64;x++){const px=Math.floor((x+.5)*canvas.width/64),py=Math.floor((y+.5)*canvas.height/48),i=(py*canvas.width+px)*4,r=pixels[i],g=pixels[i+1],b=pixels[i+2];colors.add([r>>3,g>>3,b>>3].join(','));if(Math.max(r,g,b)-Math.min(r,g,b)>35&&Math.max(r,g,b)>60)colorful++;}
    return {width:canvas.width,height:canvas.height,colors:colors.size,colorful_pixels:colorful};
  }
  try {
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('#project-select')?.value,'Test project did not bootstrap',4500);
    click('[data-mode="3d"]');await until(()=>$('.scene-viewport canvas')?.getBoundingClientRect().width>100,'3D workspace did not mount');
    if(count()!==0)throw Error('Mesh test must start with an empty scene.');
    click('[data-scene-action="import-obj"]');
    chooseFiles([{name:'ENGINE_TEST_invalid.obj',text:'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 999\n'}]);
    click('[data-scene-import-submit]');
    await until(()=>!$('[data-scene-import-submit]').disabled&&$('.scene-import-status').textContent.includes('missing value'),'Invalid topology did not produce an honest import error');
    if(count()!==0||!$('#undo-button').disabled)throw Error('A failed import mutated project geometry or history.');
    steps.push('reject_invalid_topology_without_project_mutation');
    chooseFiles([{name:MESH_IMPORT_TEST.name,text:MESH_IMPORT_TEST.obj},...Object.entries(MESH_IMPORT_TEST.materials).map(([name,text])=>({name,text}))]);
    set('[data-scene-import-axis]','Z');set('[data-scene-import-scale]',1);
    click('[data-scene-import-submit]');
    await until(()=>!$('.scene-import-dialog').open&&count()===2,'Validated mesh parts were not admitted',3000);
    if(!$('.scene-message').textContent.includes('texture images are not imported'))throw Error('Unsupported material texture was not reported.');
    const firstID=$('.scene-object-list [data-scene-select="object"]').dataset.id;
    if(!$('.scene-mesh-info')?.textContent.includes('triangles'))throw Error('Imported topology is absent from the own object inspector.');
    steps.push('import_obj_and_mtl_through_real_file_input');
    const importedPicture=picture();if(importedPicture.colors<12||importedPicture.colorful_pixels<20)throw Error('Imported geometry did not produce a shaded WebGL picture: '+JSON.stringify(importedPicture));
    click('#undo-button');if(count()!==0||!$('#undo-button').disabled)throw Error('The entire import did not undo as one checkpoint.');
    click('#redo-button');if(count()!==2||!$(`.scene-object-list [data-id="${firstID}"]`))throw Error('Redo did not restore the imported geometry and IDs.');
    click(`.scene-object-list [data-scene-select="object"][data-id="${firstID}"]`);click('[data-scene-action="fit"]');
    const restoredPicture=picture();if(restoredPicture.colors<12||restoredPicture.colorful_pixels<20)throw Error('Restored geometry was not redrawn after GPU cache disposal.');
    steps.push('import_is_one_undoable_checkpoint_and_redraws_after_redo');
    click('[data-scene-action="duplicate"]');if(count()!==3)throw Error('Imported mesh duplication did not create an editable object.');
    click('#undo-button');if(count()!==2)throw Error('Mesh duplication did not undo independently.');
    click(`.scene-object-list [data-scene-select="object"][data-id="${firstID}"]`);
    set('[data-scene-property="name"]','ENGINE TEST edited imported mesh');set('[data-scene-property="position.0"]',.4);set('[data-scene-property="rotation.2"]',10);set('[data-scene-property="scale.0"]',1.2);set('[data-scene-property="material.color"]','#3f87d5');
    set('.scene-end-frame',3);set('.scene-current-frame',1);click('[data-scene-action="keyframe"]');
    set('.scene-current-frame',3);set('[data-scene-property="position.0"]',1.4);set('[data-scene-property="rotation.2"]',40);
    click(`.scene-key-lane[data-track-id="${firstID}"] [data-scene-key="1"]`);set('.scene-key-interpolation','ease_in');set('.scene-current-frame',2);
    if(Math.abs(Number($('[data-scene-property="position.0"]').value)-.65)>.001)throw Error('Imported mesh did not use the shared eased animation evaluator.');
    steps.push('author_mesh_transform_material_and_eased_motion');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Imported scene could not be saved',2200);
    steps.push('save_canonical_mesh_in_shared_project');
    return {passed:true,steps,project_id:$('#project-select').value,edited_object_id:firstID,objects:count(),webgl:restoredPicture,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,error:String(error),objects:count(),import_status:$('.scene-import-status')?.textContent||'',scene_message:$('.scene-message')?.textContent||'',elapsed_ms:Math.round(performance.now()-began)};}
})();

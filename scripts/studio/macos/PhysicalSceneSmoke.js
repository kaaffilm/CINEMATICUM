// Native WKWebView DOM acceptance for physical authorship. Synthetic TEST scene.
return await (async()=>{
  const steps=[],sleep=ms=>new Promise(r=>setTimeout(r,ms)),$=s=>document.querySelector(s);
  async function until(fn,label){const end=performance.now()+3000;while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(label);}
  function click(s){const e=$(s);if(!e||e.disabled)throw Error('Unavailable control '+s);e.click();}
  function set(s,v){const e=$(s);if(!e||e.disabled)throw Error('Unavailable field '+s);if(e.type==='checkbox')e.checked=v;else e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  const value=p=>Number($(`[data-scene-property="${p}"]`).value);
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Test project did not bootstrap');
    click('[data-mode="3d"]');await until(()=>$('.scene-editor'),'Scene editor did not mount');
    click('[data-scene-add="sphere"]');set('[data-scene-property="name"]','ENGINE TEST physical sphere');
    click('[data-scene-material="glass"]');if(value('material.transmission')!==1||value('material.ior')!==1.5)throw Error('Glass preset did not update material');
    click('#undo-button');if(value('material.transmission')!==0)throw Error('Material preset did not undo as one operation');
    click('#redo-button');if(value('material.transmission')!==1)throw Error('Material preset redo failed');
    set('[data-scene-property="material.ior"]',1.47);set('[data-scene-property="material.emission_color"]','#ff9d45');set('[data-scene-property="material.emission_strength"]',.25);
    steps.push('principled_glass_and_emission_controls_one_undo');
    click('.scene-object-list [data-scene-select="camera"]');set('[data-scene-property="sensor_height_mm"]',36);
    set('[data-scene-property="__focal_length_mm"]',50);if(Math.abs(value('fov')-39.5978)>.02)throw Error('Physical focal length did not derive vertical FOV');
    click('#undo-button');if(Math.abs(value('fov')-45)>.01)throw Error('Physical lens change did not undo');
    click('#redo-button');if(Math.abs(value('__focal_length_mm')-50)>.02)throw Error('Physical lens change did not redo');
    set('[data-scene-property="dof_enabled"]',true);if(!$('[data-scene-property="dof_enabled"]').checked)throw Error('DOF checkbox did not commit');
    click('#undo-button');if($('[data-scene-property="dof_enabled"]').checked)throw Error('DOF checkbox undo failed');
    click('#redo-button');if(!$('[data-scene-property="dof_enabled"]').checked)throw Error('DOF checkbox redo failed');
    set('[data-scene-property="focus_distance"]',3);set('[data-scene-property="f_stop"]',2.8);
    set('[data-scene-property="aperture_blades"]',7);set('[data-scene-property="aperture_rotation"]',15);set('[data-scene-property="aperture_ratio"]',1.3);
    set('[data-scene-property="roll"]',17);set('[data-scene-property="shift_x"]',.07);set('[data-scene-property="shift_y"]',-.04);set('[data-scene-property="focal_ratio"]',1.2);
    set('.scene-end-frame',2);click('[data-scene-action="keyframe"]');set('.scene-current-frame',2);
    set('[data-scene-property="focus_distance"]',6);set('[data-scene-property="f_stop"]',5.6);set('[data-scene-property="roll"]',25);
    set('.scene-current-frame',1);if(value('focus_distance')!==3||value('roll')!==17)throw Error('First physical camera key was not retained');
    set('.scene-current-frame',2);if(value('focus_distance')!==6||value('f_stop')!==5.6||value('roll')!==25)throw Error('Second physical camera key was not retained');
    steps.push('physical_lens_dof_calibrated_camera_animation_undo');
    click('.scene-object-list [data-scene-select="render"]');set('[data-scene-property="max_bounces"]',7);set('[data-scene-property="diffuse_bounces"]',3);set('[data-scene-property="glossy_bounces"]',5);set('[data-scene-property="transmission_bounces"]',6);set('[data-scene-property="transparent_max_bounces"]',4);set('[data-scene-property="seed"]',37);set('[data-scene-property="use_denoising"]',false);
    if($('[data-scene-property="use_denoising"]').checked||value('max_bounces')!==7)throw Error('Light-path controls did not commit');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Physical scene did not save');
    steps.push('cycles_light_paths_saved');
    click('.scene-object-list [data-scene-select="camera"]');click('[data-scene-action="camera"]');
    const canvas=$('.scene-viewport canvas'),gl=canvas.getContext('webgl');if(!gl||gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual WebGL physical view failed');
    return {passed:true,steps};
  }catch(error){return {passed:false,steps,error:error.message,scene_message:$('.scene-message')?.textContent,toast:$('#toast')?.textContent};}
})();

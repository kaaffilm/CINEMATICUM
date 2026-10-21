// Native WKWebView DOM acceptance for physical authorship. Synthetic TEST scene.
return await (async()=>{
  const steps=[],layout={},sleep=ms=>new Promise(r=>setTimeout(r,ms)),$=s=>document.querySelector(s);
  async function until(fn,label){const end=performance.now()+3000;while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(label);}
  function visible(e,label){
    if(!e)throw Error('Missing '+label);
    const r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
    if(r.width<2||r.height<2||r.left<-.5||r.top<-.5||r.right>innerWidth+.5||r.bottom>innerHeight+.5)throw Error('Control is outside the window: '+label+' '+JSON.stringify({x:r.x,y:r.y,width:r.width,height:r.height}));
    for(let p=e.parentElement;p;p=p.parentElement){const s=getComputedStyle(p);if(/auto|scroll|hidden|clip/.test(s.overflowY)){const b=p.getBoundingClientRect();if(r.top<b.top+p.clientTop-.5||r.bottom>b.top+p.clientTop+p.clientHeight+.5)throw Error('Control is vertically clipped: '+label);}if(/auto|scroll|hidden|clip/.test(s.overflowX)){const b=p.getBoundingClientRect();if(r.left<b.left+p.clientLeft-.5||r.right>b.left+p.clientLeft+p.clientWidth+.5)throw Error('Control is horizontally clipped: '+label);}}
    const hit=document.elementFromPoint(x,y);if(hit!==e&&!e.contains(hit))throw Error('Control cannot be hit: '+label+' (covered by '+(hit?.className||hit?.tagName||'nothing')+')');
    return e;
  }
  function reach(s){
    const e=$(s);if(!e)throw Error('Missing control '+s);
    // Scroll only the actual bounded scene tool/list/inspector surfaces. Never
    // move the page to make a clipped footer or an overflowing editor pass.
    for(let p=e.parentElement;p;p=p.parentElement){
      if(!p.matches('.scene-inspector,.scene-object-list,.scene-tools,.scene-motion-toolbar,.scene-footer'))continue;
      const b=p.getBoundingClientRect(),r=e.getBoundingClientRect(),top=b.top+p.clientTop,left=b.left+p.clientLeft;
      if(r.top<top+2)p.scrollTop+=r.top-top-2;else if(r.bottom>top+p.clientHeight-2)p.scrollTop+=r.bottom-top-p.clientHeight+2;
      if(r.left<left+2)p.scrollLeft+=r.left-left-2;else if(r.right>left+p.clientWidth-2)p.scrollLeft+=r.right-left-p.clientWidth+2;
    }
    return visible(e,s);
  }
  function click(s){const e=reach(s);if(e.disabled)throw Error('Unavailable control '+s);e.click();}
  function set(s,v){const e=reach(s);if(e.disabled)throw Error('Unavailable field '+s);if(e.type==='checkbox')e.checked=v;else e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  function checkLayout(){
    const viewport=$('.scene-viewport').getBoundingClientRect(),footer=$('.scene-footer').getBoundingClientRect(),module=$('#scene-module').getBoundingClientRect(),timeline=$('.timeline-panel').getBoundingClientRect();
    Object.assign(layout,{window:{width:innerWidth,height:innerHeight},viewport:{width:viewport.width,height:viewport.height},inspector_height:$('.scene-inspector').clientHeight,footer_bottom:footer.bottom,timeline_top:timeline.top,module_bottom:module.bottom});
    if(viewport.width<250||viewport.height<180)throw Error('3D viewport has been squeezed below a useful size: '+JSON.stringify(layout.viewport));
    if($('.scene-inspector').clientHeight<100)throw Error('Inspector is not independently usable');
    if(footer.bottom>timeline.top+.5||footer.bottom>module.bottom+.5)throw Error('Scene render footer is clipped by the film timeline');
    visible($('.scene-render'),'persistent Render scene button');
    visible($('.scene-footnote'),'scene footer note');
  }
  function checkCameraHeading(){
    const inspector=$('.scene-inspector'),heading=inspector.querySelector('h3');
    if(inspector.scrollTop!==0||heading?.textContent!=='Render camera')throw Error('Selecting camera did not reveal its inspector heading');
    visible(heading,'selected camera inspector heading');
  }
  const value=p=>Number($(`[data-scene-property="${p}"]`).value);
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Test project did not bootstrap');
    click('[data-mode="3d"]');await until(()=>$('.scene-editor'),'Scene editor did not mount');
    checkLayout();steps.push('viewport_and_render_footer_inside_window');
    click('[data-scene-add="sphere"]');set('[data-scene-property="name"]','ENGINE TEST physical sphere');
    for(const control of document.querySelectorAll('.scene-tools button:not(:disabled),.scene-tools input')){
      const attribute=['data-scene-add','data-scene-tool','data-scene-action'].find(a=>control.hasAttribute(a));
      reach(attribute?'['+attribute+'="'+control.getAttribute(attribute)+'"]':'.scene-snap');
    }
    layout.toolbar_scrollable=$('.scene-tools').scrollWidth>$('.scene-tools').clientWidth;$('.scene-tools').scrollLeft=0;
    reach('.scene-samples select');checkLayout();steps.push('all_scene_tools_and_samples_reachable');
    click('[data-scene-material="glass"]');if(value('material.transmission')!==1||value('material.ior')!==1.5)throw Error('Glass preset did not update material');
    click('#undo-button');if(value('material.transmission')!==0)throw Error('Material preset did not undo as one operation');
    click('#redo-button');if(value('material.transmission')!==1)throw Error('Material preset redo failed');
    set('[data-scene-property="material.ior"]',1.47);set('[data-scene-property="material.emission_color"]','#ff9d45');set('[data-scene-property="material.emission_strength"]',.25);
    steps.push('principled_glass_and_emission_controls_one_undo');
    click('.scene-object-list [data-scene-select="camera"]');checkCameraHeading();
    reach('[data-scene-property="focal_ratio"]');layout.camera_inspector_scroll=$('.scene-inspector').scrollTop;
    if(layout.camera_inspector_scroll<=0||$('.scene-properties').scrollTop!==0)throw Error('Full camera controls are not reachable in their own inspector');
    checkLayout();click('.scene-object-list [data-scene-select="camera"]');checkCameraHeading();
    steps.push('camera_selection_reveals_heading_and_full_inspector_scrolls');set('[data-scene-property="sensor_height_mm"]',36);
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
    click('.scene-object-list [data-scene-select="camera"]');checkCameraHeading();click('[data-scene-action="camera"]');checkLayout();
    const canvas=$('.scene-viewport canvas'),gl=canvas.getContext('webgl');if(!gl||gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual WebGL physical view failed');
    return {passed:true,steps,layout};
  }catch(error){return {passed:false,steps,layout,error:error.message,scene_message:$('.scene-message')?.textContent,toast:$('#toast')?.textContent};}
})();

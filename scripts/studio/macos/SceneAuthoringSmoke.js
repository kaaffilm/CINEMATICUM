// Owned WKWebView acceptance. The Python harness supplies only fixture data;
// all scene changes below pass through visible CINEMATICUM controls.
return await(async()=>{
  const steps=[],metrics={},$=selector=>document.querySelector(selector),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  async function until(predicate,label,timeout=3000){const end=performance.now()+timeout;while(performance.now()<end){if(predicate())return;await sleep(30);}throw Error(label);}
  function reach(selector){
    const element=$(selector);if(!element)throw Error('Missing '+selector);
    for(let parent=element.parentElement;parent;parent=parent.parentElement){if(!parent.matches('.scene-inspector,.scene-object-list,.scene-tools,.scene-motion-toolbar,.scene-footer'))continue;const r=element.getBoundingClientRect(),b=parent.getBoundingClientRect();if(r.top<b.top+2)parent.scrollTop+=r.top-b.top-2;else if(r.bottom>b.top+parent.clientHeight-2)parent.scrollTop+=r.bottom-b.top-parent.clientHeight+2;if(r.left<b.left+2)parent.scrollLeft+=r.left-b.left-2;else if(r.right>b.left+parent.clientWidth-2)parent.scrollLeft+=r.right-b.left-parent.clientWidth+2;}
    const r=element.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
    if(r.width<2||r.height<2||r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5||(hit!==element&&!element.contains(hit)))throw Error('Unreachable '+selector);
    return element;
  }
  function click(selector){const element=reach(selector);if(element.disabled)throw Error('Disabled '+selector);element.click();}
  function set(selector,value){const element=reach(selector);if(element.disabled)throw Error('Disabled '+selector);element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  const busy=()=>$('.scene-editor').classList.contains('scene-model-busy');
  const editing=()=>$('.scene-editor').classList.contains('scene-edit-mode');
  const statistics=()=>$('.scene-model-statistics')?.textContent||'';
  const near=(actual,expected,tolerance=.00001)=>Math.abs(actual-expected)<tolerance;
  async function operation(run){run();if(!busy())throw Error('The control did not start its real modeling job');await until(()=>!busy(),'Actual modeling job did not finish in this stage',10000);if($('.scene-message.error:not([hidden])'))throw Error($('.scene-message').textContent);}
  function uvValue(axis){return Number($('[data-scene-uv-coordinate="'+axis+'"]').value);}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Owned scene project did not bootstrap');
    click('[data-mode="3d"]');await until(()=>$('.scene-editor'),'Scene editor did not mount');
    click('.scene-object-list [data-scene-select="object"][data-id="modeled"]');
    const stage=AUTHORING_TEST.stage;
    if(stage==='hierarchy'){
      set('[data-scene-property="parent_id"]','parent');
      if($('[data-scene-property="parent_id"]').value!=='parent')throw Error('Parent control did not retain its value');
      click('#undo-button');if($('[data-scene-property="parent_id"]').value!=='')throw Error('Parent assignment did not undo');
      click('#redo-button');if($('[data-scene-property="parent_id"]').value!=='parent')throw Error('Parent assignment did not redo');
      const parent=$('.scene-object-list [data-id="parent"]'),child=$('.scene-object-list [data-id="modeled"]');
      if([...parent.parentElement.children].indexOf(parent)>[...parent.parentElement.children].indexOf(child)||parseFloat(child.style.paddingLeft)<=parseFloat(parent.style.paddingLeft))throw Error('Outliner did not display the hierarchy');
      click('.scene-object-list [data-scene-select="object"][data-id="parent"]');
      if([...$('[data-scene-property="parent_id"]').options].some(option=>option.value==='modeled'))throw Error('Parent selector permits a cycle');
      click('.scene-inspector [data-scene-action="delete"]');
      if(!$('.scene-object-list [data-id="parent"]')||!$('.scene-message.error:not([hidden])'))throw Error('Deleting a parent orphaned its child');
      click('.scene-object-list [data-scene-select="object"][data-id="modeled"]');
      const handle=reach('[data-scene-axis="x"]');handle.focus();handle.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));
      // Position controls display two decimal places. The Python harness also
      // verifies the full saved local value (-.125), independently of display.
      if(!near(Number($('[data-scene-property="position.0"]').value),1)||!near(Number($('[data-scene-property="position.1"]').value),-.13))throw Error('World X movement did not convert through the rotated/scaled parent');
      steps.push('parent_selector_shared_undo_and_redo','ordered_indented_hierarchy','cycle_and_orphan_refusal','world_axis_keyboard_to_parent_local');
    }else if(stage==='convert'){
      await operation(()=>click('.scene-tools [data-scene-action="edit-mesh"]'));
      if(!statistics().includes('8 vertices')||!statistics().includes('6 faces'))throw Error('Real editable cage was not created');
      steps.push('parented_object_real_mesh_conversion');
    }else if(stage==='project'){
      set('[data-scene-uv-method]','box');await operation(()=>click('[data-scene-uv-action="project"]'));
      if(!$('.scene-uv-panel .scene-model-statistics').textContent.includes('24 UV points'))throw Error('Box atlas was not evaluated');
      click('#undo-button');if(!$('.scene-uv-panel .scene-model-statistics').textContent.includes('0 UV points'))throw Error('UV projection did not undo');
      click('#redo-button');if(!$('.scene-uv-panel .scene-model-statistics').textContent.includes('24 UV points'))throw Error('UV projection did not redo');
      reach('[data-scene-uv-canvas]');steps.push('box_projection_real_job_shared_undo_and_redo','reachable_uv_canvas');
    }else if(stage==='uvmove'){
      set('[data-scene-uv-index]',0);
      const original=AUTHORING_TEST.uvs[0],surface=reach('[data-scene-uv-canvas]'),r=surface.getBoundingClientRect(),scale=252;
      const x=r.left+(160+(original[0]-.5)*scale)*r.width/320,y=r.top+(150-(original[1]-.5)*scale)*r.height/300;
      const dx=.1*scale*r.width/320,dy=.05*scale*r.height/300;
      const pointer=(type,px,py)=>surface.dispatchEvent(new PointerEvent(type,{bubbles:true,button:0,pointerId:91,isPrimary:true,clientX:px,clientY:py}));
      pointer('pointerdown',x,y);pointer('pointermove',x+dx,y+dy);
      surface.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
      if(busy()||!near(uvValue(0),original[0])||!near(uvValue(1),original[1]))throw Error('Canceling UV drag changed the mapping');
      // Cancellation rebuilt the inspector, so use the current canvas and its
      // current position for the committed pointer gesture.
      const current=reach('[data-scene-uv-canvas]'),bounds=current.getBoundingClientRect(),px=bounds.left+(160+(original[0]-.5)*scale)*bounds.width/320,py=bounds.top+(150-(original[1]-.5)*scale)*bounds.height/300;
      const send=(type,xx,yy)=>current.dispatchEvent(new PointerEvent(type,{bubbles:true,button:0,pointerId:92,isPrimary:true,clientX:xx,clientY:yy}));
      await operation(()=>{send('pointerdown',px,py);send('pointermove',px+.1*scale*bounds.width/320,py+.05*scale*bounds.height/300);send('pointerup',px+.1*scale*bounds.width/320,py+.05*scale*bounds.height/300);});
      if(!near(uvValue(0),original[0]+.1)||!near(uvValue(1),original[1]-.05))throw Error('UV drag did not commit the selected coordinates');
      click('#undo-button');if(!near(uvValue(0),original[0])||!near(uvValue(1),original[1]))throw Error('UV drag did not undo as one edit');
      click('#redo-button');if(!near(uvValue(0),original[0]+.1)||!near(uvValue(1),original[1]-.05))throw Error('UV drag redo did not restore coordinates');
      steps.push('uv_pointer_drag_cancel','uv_pointer_drag_real_job_one_undo_and_redo');
    }else if(stage==='unwrap'){
      await operation(()=>click('[data-scene-uv-action="unwrap"]'));
      if(Number($('[data-scene-uv-index]').max)<1)throw Error('Actual unwrap produced no editable UVs');
      steps.push('actual_smart_unwrap_control_and_job');
    }else if(stage==='array'){
      await operation(()=>click('[data-scene-model-action="add-array"]'));
      if(!$('.scene-modifier-heading').textContent.includes('Array')||!statistics().includes('24 evaluated triangles'))throw Error('Array control did not create real repeated geometry');
      click('#undo-button');if($('.scene-modifier'))throw Error('Array did not undo');click('#redo-button');if(!$('.scene-modifier-heading').textContent.includes('Array'))throw Error('Array did not redo');
      steps.push('live_array_real_evaluation_and_shared_undo');
    }else if(stage==='arrayoffset'){
      await operation(()=>set('[data-modifier-property="offset.0"]',3));
      if(Number($('[data-modifier-property="offset.0"]').value)!==3)throw Error('Vector modifier property did not retain its value');
      steps.push('array_vector_parameter_re_evaluates_geometry');
    }else if(stage==='gpu'){
      click('.scene-object-list [data-scene-select="render"]');set('[data-scene-property="device"]','METAL');
      click('#undo-button');if($('[data-scene-property="device"]').value!=='CPU')throw Error('GPU choice did not undo');
      click('#redo-button');if($('[data-scene-property="device"]').value!=='METAL')throw Error('GPU choice did not redo');
      steps.push('explicit_gpu_selection_and_shared_undo');
    }else throw Error('Unknown scene-authoring stage');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Scene did not save');
    const canvas=$('.scene-viewport canvas'),gl=canvas.getContext('webgl');if(!gl||gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual viewport WebGL failed');
    metrics.viewport_height=canvas.getBoundingClientRect().height;
    if(editing())click('.scene-tools [data-scene-action="edit-mesh"]');
    return {passed:true,stage,steps,metrics};
  }catch(error){return {passed:false,stage:AUTHORING_TEST.stage,steps,metrics,error:error.message,scene_message:$('.scene-message')?.textContent,toast:$('#toast')?.textContent};}
})();

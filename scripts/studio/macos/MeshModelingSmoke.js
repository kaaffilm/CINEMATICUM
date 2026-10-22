// The Python harness injects MODELING_TEST.stage and persists each owned test
// project between bounded native runs. No fake geometry engine is substituted.
return await(async()=>{
  const steps=[],metrics={},$=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
  async function until(fn,label,timeout=3500){const end=performance.now()+timeout;while(performance.now()<end){if(fn())return;await sleep(35);}throw Error(label);}
  function reach(s){
    const e=$(s);if(!e)throw Error('Missing '+s);
    for(let p=e.parentElement;p;p=p.parentElement){if(!p.matches('.scene-inspector,.scene-object-list,.scene-tools,.scene-motion-toolbar,.scene-footer'))continue;const r=e.getBoundingClientRect(),b=p.getBoundingClientRect();if(r.top<b.top+2)p.scrollTop+=r.top-b.top-2;else if(r.bottom>b.top+p.clientHeight-2)p.scrollTop+=r.bottom-b.top-p.clientHeight+2;if(r.left<b.left+2)p.scrollLeft+=r.left-b.left-2;else if(r.right>b.left+p.clientWidth-2)p.scrollLeft+=r.right-b.left-p.clientWidth+2;}
    const r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
    if(r.width<2||r.height<2||r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5||(hit!==e&&!e.contains(hit)))throw Error('Unreachable control '+s);
    return e;
  }
  function click(s){const e=reach(s);if(e.disabled)throw Error('Disabled '+s);e.click();}
  function set(s,v){const e=reach(s);if(e.disabled)throw Error('Disabled '+s);if(e.type==='checkbox')e.checked=v;else e.value=String(v);e.dispatchEvent(new Event('change',{bubbles:true}));}
  const busy=()=>$('.scene-editor').classList.contains('scene-model-busy');
  const editing=()=>$('.scene-editor').classList.contains('scene-edit-mode');
  const stats=()=>$('.scene-model-statistics')?.textContent||'';
  async function operation(run){run();if(!busy())throw Error('Modeling operation did not start its owned job');await until(()=>!busy(),'Real mesh evaluation did not complete within this native test stage',10500);if($('.scene-message.error:not([hidden])'))throw Error($('.scene-message').textContent);}
  function ensureEdit(){if(!editing())click('.scene-tools [data-scene-action="edit-mesh"]');}
  function chooseFace(index){ensureEdit();click('[data-scene-element-mode="face"]');set('[data-scene-element-index]',index);}
  const countMods=()=>document.querySelectorAll('.scene-modifier').length;
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST'),'Test project did not bootstrap');
    click('[data-mode="3d"]');await until(()=>$('.scene-editor'),'Scene editor did not mount');
    click('.scene-object-list [data-scene-select="object"][data-id="modeled"]');
    const stage=MODELING_TEST.stage;
    if(stage==='convert'){
      await operation(()=>click('.scene-tools [data-scene-action="edit-mesh"]'));
      if(!stats().includes('8 vertices')||!stats().includes('6 faces'))throw Error('Cube was not converted to a real editable cage');
      // Independently project a known cage vertex into the real camera view,
      // then select it through the actual canvas pointer handlers.
      click('[data-scene-action="camera"]');
      const canvas=$('.scene-viewport canvas'),r=canvas.getBoundingClientRect(),eye=[7,-9,6],target=[0,0,1],point=[1,1,2];
      const sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),unit=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);},cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
      const back=unit(sub(eye,target)),right=unit(cross([0,0,1],back)),up=cross(back,right),q=sub(point,eye),depth=-dot(q,back),aspect=4/3;
      let width=r.width,height=r.height;if(width/height>aspect)width=height*aspect;else height=width/aspect;
      const focal=1/Math.tan(Math.PI/8),x=r.left+(r.width-width)/2+(1+dot(q,right)/depth*focal/aspect)*width/2,y=r.top+(r.height-height)/2+(1-dot(q,up)/depth*focal)*height/2;
      if(document.elementFromPoint(x,y)!==canvas)throw Error('Projected test vertex is not reachable on the canvas');
      for(const type of ['pointerdown','pointerup'])canvas.dispatchEvent(new PointerEvent(type,{bubbles:true,button:0,pointerId:73,isPrimary:true,clientX:x,clientY:y}));
      if(Number($('[data-scene-element-index]').value)!==6)throw Error('Canvas picking selected the wrong actual control vertex');
      metrics.picked_vertex=6;steps.push('actual_canvas_vertex_pick');
      click('#undo-button');if($('.scene-model-statistics'))throw Error('Mesh conversion did not undo to the primitive');
      click('#redo-button');if(!stats().includes('8 vertices'))throw Error('Mesh conversion redo did not restore the evaluated cage');
      steps.push('convert_actual_engine_one_undo');
    }else if(stage==='vertex'){
      ensureEdit();set('[data-scene-element-index]',0);
      await operation(()=>set('[data-scene-model-coordinate="0"]',-1.3));
      if(Math.abs(Number($('[data-scene-model-coordinate="0"]').value)+1.3)>.00001)throw Error('Vertex coordinate was not edited');
      click('#undo-button');if(Number($('[data-scene-model-coordinate="0"]').value)!==-1)throw Error('Vertex edit did not undo');
      click('#redo-button');if(Math.abs(Number($('[data-scene-model-coordinate="0"]').value)+1.3)>.00001)throw Error('Vertex edit redo failed');
      steps.push('vertex_coordinate_move_one_undo');
    }else if(stage==='extrude'){
      chooseFace(1);set('.scene-extrusion-distance',.7);await operation(()=>click('[data-scene-model-action="extrude"]'));
      if(!stats().includes('12 vertices')||!stats().includes('10 faces'))throw Error('Face extrusion did not create side walls and a new cap');
      click('#undo-button');if(!stats().includes('6 faces'))throw Error('Extrusion did not undo');click('#redo-button');if(!stats().includes('10 faces'))throw Error('Extrusion redo failed');
      steps.push('extrude_faces_real_topology_one_undo');
    }else if(stage==='subdivide'){
      chooseFace(1);await operation(()=>click('[data-scene-model-action="subdivide"]'));
      if(!stats().includes('17 vertices')||!stats().includes('13 faces'))throw Error('Subdivision did not split the selected face and adjacent edges');
      steps.push('subdivide_faces_real_connected_topology');
    }else if(stage==='delete'){
      ensureEdit();click('[data-scene-element-mode="vertex"]');
      const before=stats(),canvas=reach('.scene-viewport canvas');canvas.focus();
      canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Delete',bubbles:true,cancelable:true}));
      if(busy()||stats()!==before||!$('.scene-object-list [data-scene-select="object"][data-id="modeled"]'))throw Error('Vertex Delete shortcut removed the object instead of requiring face selection');
      chooseFace(0);await operation(()=>{const canvas=reach('.scene-viewport canvas');canvas.focus();canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Delete',bubbles:true,cancelable:true}));});
      if(!stats().includes('12 faces'))throw Error('Selected face was not deleted');click('#undo-button');if(!stats().includes('13 faces'))throw Error('Face deletion undo did not restore topology');
      steps.push('delete_shortcut_respects_edit_mode_and_restore_one_undo');
    }else if(['mirror','bevel','subdivision'].includes(stage)){
      const before=countMods();await operation(()=>click('[data-scene-model-action="add-'+stage+'"]'));
      if(countMods()!==before+1)throw Error('Live modifier was not added');
      const final=stats();click('#undo-button');if(countMods()!==before)throw Error('Modifier add did not undo');click('#redo-button');if(countMods()!==before+1||stats()!==final)throw Error('Modifier redo did not restore evaluated geometry');
      steps.push('actual_'+stage+'_modifier_one_undo');
    }else if(stage==='reorder'){
      const second=document.querySelectorAll('.scene-modifier')[1],id=second.dataset.modifierId;
      await operation(()=>click('[data-scene-model-action="up"][data-modifier-id="'+id+'"]'));
      if($('.scene-modifier').dataset.modifierId!==id)throw Error('Modifier evaluation order did not change');
      steps.push('modifier_reorder_recalculates_geometry');
    }else if(stage==='disable'||stage==='enable'){
      const modifier=[...document.querySelectorAll('.scene-modifier')].find(e=>e.querySelector('.scene-modifier-heading label')?.textContent.includes('Subdivision'));
      const selector='[data-scene-modifier="'+modifier.dataset.modifierId+'"][data-modifier-property="enabled"]';
      const before=stats();await operation(()=>set(selector,stage==='enable'));
      if($(selector).checked!==(stage==='enable')||stats()===before)throw Error('Modifier enable state did not change evaluated geometry');
      steps.push('modifier_'+stage+'_changes_evaluated_mesh');
    }else if(stage==='apply'){
      const before=countMods();await operation(()=>click('[data-scene-model-action="apply"]'));
      if(countMods()!==0)throw Error('Apply stack did not bake and clear the live stack');
      metrics.applied_statistics=stats();click('#undo-button');if(countMods()!==before)throw Error('Applying stack did not undo back to original cage and live stack');
      steps.push('apply_stack_re_evaluates_bakes_and_undo_restores');
    }else throw Error('Unknown native modeling stage');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Modeled geometry did not save');
    if(editing())click('.scene-tools [data-scene-action="edit-mesh"]');
    const canvas=$('.scene-viewport canvas'),gl=canvas.getContext('webgl');if(!gl||gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual modeled viewport WebGL failed');
    reach('.scene-render');metrics.statistics=stats();metrics.viewport_height=canvas.getBoundingClientRect().height;
    return {passed:true,stage,steps,metrics};
  }catch(error){return {passed:false,stage:MODELING_TEST.stage,steps,metrics,error:error.message,scene_message:$('.scene-message')?.textContent,toast:$('#toast')?.textContent};}
})();

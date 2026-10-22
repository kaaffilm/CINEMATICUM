/* Actual SAM2/TAPIR/TAPNext editor. The bridge owns undo, save and frozen job admission. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const unit = value => finite(value) && value >= 0 && value <= 1;
  function validateRecipe(recipe) {
    if (!recipe || recipe.version !== 1 || !['sam2','tapir','tapnext'].includes(recipe.backend) ||
        !Number.isInteger(recipe.frame_start) || recipe.frame_start < 0 || !Number.isInteger(recipe.frame_count) ||
        recipe.frame_count < 1 || recipe.frame_count > 32) throw Error('Choose an exact range of 1–32 conformed clip frames.');
    const inside = frame => Number.isInteger(frame) && frame >= recipe.frame_start && frame < recipe.frame_start + recipe.frame_count;
    if (recipe.backend === 'sam2') {
      if (!Array.isArray(recipe.prompts) || !recipe.prompts.length || recipe.prompts.length > 16) throw Error('Add a foreground point or box for the object.');
      const seen = new Set();
      for (const prompt of recipe.prompts) {
        if (!inside(prompt.frame) || seen.has(prompt.frame) || !Array.isArray(prompt.points) || prompt.points.length > 32 ||
            prompt.points.some(p => !unit(p.x) || !unit(p.y) || ![0,1].includes(p.label))) throw Error('Prompt frames must be unique and point coordinates normalized.');
        seen.add(prompt.frame);
        if (prompt.box && (!Array.isArray(prompt.box) || prompt.box.length !== 4 || !prompt.box.every(unit) ||
            prompt.box[0] >= prompt.box[2] || prompt.box[1] >= prompt.box[3])) throw Error('Draw a positive-width object box.');
        if (!prompt.points.length && !prompt.box) throw Error('Every prompt frame needs a point or box.');
      }
      const first = [...recipe.prompts].sort((a,b)=>a.frame-b.frame)[0];
      if (!first.box && !first.points.some(p=>p.label===1)) throw Error('The first prompt needs a foreground point or box.');
    } else {
      if (!Array.isArray(recipe.points) || !recipe.points.length || recipe.points.length > 16) throw Error('Choose 1–16 actual point queries.');
      const ids = new Set();
      for (const point of recipe.points) {
        if (!identifier(point.id) || ids.has(point.id) || !inside(point.frame) || !unit(point.x) || !unit(point.y)) throw Error('Every query needs a unique ID, valid frame and normalized coordinates.');
        ids.add(point.id);
      }
    }
    return recipe;
  }

  function mount(host, bridge) {
    if (!host || !bridge?.request || !bridge.getProject || !bridge.getContext || !bridge.applyRecipe || !bridge.applyPlan)
      throw Error('Learned tracking requires project, selected-clip and undoable save bridges.');
    const style = document.createElement('style');
    style.textContent = `
      .learned-dialog{width:min(1060px,94vw);max-height:92vh;padding:0;border:1px solid #485061;border-radius:12px;background:#171b23;color:#e8edf5}
      .learned-dialog::backdrop{background:#05070cd9}.learned-dialog header,.learned-dialog footer{display:flex;gap:9px;align-items:center;padding:13px 17px;border-bottom:1px solid #343d4b}
      .learned-dialog header h2{flex:1;margin:0;font-size:18px}.learned-dialog footer{border-top:1px solid #343d4b;border-bottom:0;flex-wrap:wrap}.learned-body{padding:16px;max-height:72vh;overflow:auto}
      .learned-grid{display:grid;grid-template-columns:minmax(310px,1.45fr) minmax(260px,1fr);gap:17px}.learned-dialog label{font-size:12px;display:block;margin:8px 0 3px;color:#c5cfdd}
      .learned-dialog input,.learned-dialog select,.learned-dialog textarea{box-sizing:border-box;width:100%;padding:7px;border:1px solid #4b576a;border-radius:5px;background:#242c39;color:#eef4ff}
      .learned-dialog button{padding:7px 10px;border:1px solid #56667f;border-radius:5px;background:#2c3b50;color:#eef4ff;cursor:pointer}.learned-dialog button:disabled{opacity:.45;cursor:default}
      .learned-dialog canvas{width:100%;display:block;background:#080c12;cursor:crosshair;touch-action:none;border:1px solid #3a465a}.learned-dialog p{font-size:12px;line-height:1.5;color:#bdc9da}
      .learned-row{display:flex;gap:8px;align-items:end}.learned-row>*{flex:1;min-width:0}.learned-dialog textarea{font:12px/1.4 ui-monospace,monospace;min-height:110px;resize:vertical}
      .learned-dialog [hidden]{display:none!important}.learned-dialog progress{width:100%}.learned-dialog .learned-status{flex:1;font-size:12px}.learned-error{color:#ffaaa4!important}
      .learned-preview{max-width:100%;max-height:240px;object-fit:contain;background:repeating-conic-gradient(#222 0% 25%,#353535 0% 50%) 50%/16px 16px}.learned-dialog a{color:#a8caff;margin-right:12px}
      .learned-dialog summary{cursor:pointer;font-size:13px;margin:12px 0}.learned-dialog .learned-primary{background:#355f90}.learned-dialog .learned-inline{display:flex;align-items:center;gap:7px}.learned-inline input{width:auto}
      @media(max-width:760px){.learned-grid{grid-template-columns:1fr}}
    `;
    const dialog = document.createElement('dialog'); dialog.id='learned-tracking-dialog';dialog.className='learned-dialog';
    dialog.innerHTML=`<header><h2>Learned masks and point tracks</h2><button data-close>Close</button></header><div class="learned-body">
      <p data-source></p><div class="learned-grid"><section><canvas data-canvas width="512" height="288" tabindex="0" aria-label="Choose object prompts or point queries on the actual source frame"></canvas>
      <div class="learned-row"><label>Source clip frame<input data-frame type="number" min="0" step="1" value="0"></label><button data-load>Load source frame</button></div>
      <label>Canvas action<select data-action><option value="foreground">SAM foreground point</option><option value="background">SAM background point</option><option value="box">SAM object box · drag</option><option value="query">Learned point query</option><option value="correction">Correct selected learned point</option></select></label>
      <p data-canvas-help>Choose a foreground point or drag a box. Add background points and prompts on later frames to correct the same object.</p>
      <div class="learned-row"><button data-remove-frame>Clear this frame’s prompts</button><button data-clear-prompts>Clear all prompts</button></div>
      <details><summary>Edit the exact prompt recipe</summary><textarea data-recipe spellcheck="false" aria-label="Learned prompt recipe JSON"></textarea><button data-read-recipe>Use edited recipe</button></details>
      <div data-result hidden><h3>Measured result</h3><img class="learned-preview" data-preview alt="Actual learned mask or point trajectory preview"><p data-measurement></p><div data-downloads></div></div>
      </section><section><label>Model<select data-backend><option value="sam2">SAM2.1 Tiny · object segmentation</option><option value="tapir">TAPIR · learned point tracking</option><option value="tapnext">TAPNext · recurrent learned point tracking</option></select></label>
      <div class="learned-row"><label>First clip frame<input data-start type="number" min="0" step="1" value="0"></label><label>Frame count<input data-count type="number" min="1" max="32" step="1" value="10"></label></div>
      <p data-runtime>Checking the installed model checkpoints…</p><button data-save>Save prompts · undoable</button><button data-run class="learned-primary">Run learned inference</button>
      <progress data-progress hidden max="1" value="0"></progress><button data-cancel hidden>Cancel owned analysis</button>
      <section data-mask-apply hidden><h3>Apply the actual alpha matte</h3><label class="learned-inline"><input data-invert type="checkbox">Invert mask</label>
      <label data-hold-label class="learned-inline" hidden><input data-hold-still type="checkbox">Hold this measured image mask across the still clip</label>
      <p>The cutout multiplies the selected clip’s alpha by the actual SAM mask. The measured range uses its original conformed frame positions. Outside that range the mask is transparent, unless you explicitly hold a measured still-image mask across the clip.</p><button data-apply-mask>Apply foreground cutout · undoable</button></section>
      <section data-point-apply hidden><h3>Apply a measured point</h3><label>Point<select data-point></select></label>
      <div class="learned-row"><label>Apply from frame<input data-apply-start type="number" min="0" step="1"></label><label>Apply frames<input data-apply-count type="number" min="1" max="32" step="1"></label></div>
      <p>Hidden or uncertain samples remain gaps. Choose a fully visible range, or load a frame and explicitly correct its point. Corrections retain the model’s confidence and are recorded with the applied motion.</p>
      <textarea data-corrections spellcheck="false" aria-label="Explicit manually corrected point samples">[]</textarea><button data-apply-point>Apply stabilization · undoable</button></section>
      <p>Analysis uses up to 32 source-conformed frames at a 512-pixel edge. SAM2 propagates one prompted object; TAPIR and TAPNext track up to 16 queries with learned visibility. The current managed runtime uses CPU.</p>
      </section></div></div><footer><span class="learned-status" data-status role="status" aria-live="polite">Choose a source clip.</span></footer>`;
    host.append(style,dialog);
    const el=selector=>dialog.querySelector(selector),canvas=el('[data-canvas]'),ctx=canvas.getContext('2d');
    let context=null,recipe=null,sourceImage=null,sourceFrame=null,capabilities=null,busy=false,serial=0,jobId=null,result=null,resultJob=null,drag=null;
    let selectedPoint=null,pointCorrections=new Map(),capabilitySerial=0;
    const status=(message,error=false)=>{el('[data-status]').textContent=message;el('[data-status]').classList.toggle('learned-error',error);};
    const current=()=>{const value=bridge.getContext();const project=bridge.getProject();return {context:value,project,clip:project?.clips?.find(c=>c.id===(value?.clipId||value?.clip?.id))};};
    const check=()=>{const value=current();if(!value.project||!value.clip||value.project.id!==context?.projectId||value.clip.id!==context?.clipId)throw Error('The selected project or clip changed. Reopen learned tracking for that clip.');return value;};
    const path=name=>`/api/projects/${encodeURIComponent(context.projectId)}/${name}`;
    function modelReady(){return recipe?.backend==='tapnext'?capabilities?.tapnext?.available:capabilities?.available;}
    async function refreshRuntime(){
      const selected=recipe.backend,ticket=++capabilitySerial,identity=context.projectId+':'+context.clipId;
      const result=await bridge.request(selected==='tapnext'?'/api/tapnext-capabilities':'/api/learned-capabilities');
      if(ticket!==capabilitySerial||!dialog.open||recipe.backend!==selected||identity!==context.projectId+':'+context.clipId)return;
      capabilities??={};
      if(selected==='tapnext')capabilities.tapnext=result;else Object.assign(capabilities,result);
      el('[data-runtime]').textContent=result.available?(selected==='tapnext'?'Verified independent TAPNext checkpoint ready · CPU':'Verified SAM2.1 Tiny and TAPIR checkpoints ready · CPU'):result.reason||'Install the pinned runtime for this model.';
      controls();
    }
    function controls() {
      for(const input of dialog.querySelectorAll('button,input,select,textarea'))input.disabled=busy;
      el('[data-cancel]').hidden=!jobId;el('[data-cancel]').disabled=!jobId;
      el('[data-run]').disabled=busy||!modelReady();
      el('[data-progress]').hidden=!busy;
    }
    function syncRecipe() {
      el('[data-backend]').value=recipe.backend;el('[data-start]').value=recipe.frame_start;el('[data-count]').value=recipe.frame_count;
      el('[data-recipe]').value=JSON.stringify(recipe,null,2);
      el('[data-action]').value=recipe.backend==='sam2'?'foreground':'query';
      el('[data-canvas-help]').textContent=recipe.backend==='sam2'?'Choose foreground/background points or drag an object box. Later prompt frames correct the same object.':'Choose a textured point in the actual loaded frame. Every query retains its own reference frame.';
      draw();
    }
    function range() {
      const {clip}=check();recipe.frame_start=Number(el('[data-start]').value);recipe.frame_count=Number(el('[data-count]').value);
      if(!Number.isInteger(recipe.frame_start)||!Number.isInteger(recipe.frame_count)||recipe.frame_start<0||recipe.frame_count<1||recipe.frame_count>32||recipe.frame_start+recipe.frame_count>clip.duration)throw Error('Choose 1–32 frames inside the selected clip.');
      return recipe;
    }
    function frame() {const value=Number(el('[data-frame]').value),{clip}=check();if(!Number.isInteger(value)||value<0||value>=clip.duration)throw Error('Choose an existing source-conformed clip frame.');return value;}
    function promptAt(index) {let value=recipe.prompts.find(p=>p.frame===index);if(!value){value={frame:index,points:[]};recipe.prompts.push(value);recipe.prompts.sort((a,b)=>a.frame-b.frame);}return value;}
    function draw() {
      ctx.fillStyle='#0b1018';ctx.fillRect(0,0,canvas.width,canvas.height);if(sourceImage)ctx.drawImage(sourceImage,0,0,canvas.width,canvas.height);
      if(!recipe)return;ctx.lineWidth=2;ctx.font='12px sans-serif';
      const points=recipe.backend==='sam2'?(recipe.prompts.find(p=>p.frame===sourceFrame)?.points||[]):recipe.points.filter(p=>p.frame===sourceFrame);
      for(const point of points){const x=point.x*canvas.width,y=point.y*canvas.height;ctx.strokeStyle=point.label===0?'#ff7676':'#63edaa';ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.stroke();if(point.id){ctx.fillStyle='#ffffff';ctx.fillText(point.id,x+7,y-7);}}
      const box=drag?.box||recipe.prompts?.find(p=>p.frame===sourceFrame)?.box;
      if(box){ctx.strokeStyle='#ffe69c';ctx.strokeRect(box[0]*canvas.width,box[1]*canvas.height,(box[2]-box[0])*canvas.width,(box[3]-box[1])*canvas.height);}
      const tracks=result?.measurement?.measurement?.tracks||[];ctx.strokeStyle='#6fcaff';
      for(const item of tracks){ctx.beginPath();let previous=false;for(const sample of item.track.samples){if(!sample.visible){previous=false;continue;}const x=sample.x*canvas.width,y=sample.y*canvas.height;previous?ctx.lineTo(x,y):ctx.moveTo(x,y);previous=true;}ctx.stroke();}
    }
    const pointFrom=event=>{const rect=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))};};
    async function cancel(id=jobId){if(id)await bridge.request(`/api/jobs/${encodeURIComponent(id)}/cancel`,{method:'POST',body:{}});}
    async function execute(action,payload,ticket) {
      const job=await bridge.request(path(action),{method:'POST',body:payload});
      if(ticket!==serial){await cancel(job.id);return null;}
      jobId=job.id;controls();let row=job;
      try{
        while(['queued','running'].includes(row.state)){
          await pause(200);if(ticket!==serial)return null;
          row=await bridge.request(`/api/jobs/${encodeURIComponent(job.id)}`);if(ticket!==serial)return null;
          el('[data-progress]').value=row.progress||0;
        }
        if(row.state!=='completed')throw Error(row.error||'The owned learned analysis did not complete.');
        return {id:job.id,result:row.result};
      }catch(error){await cancel(job.id).catch(()=>{});throw error;}
      finally{if(jobId===job.id){jobId=null;controls();}}
    }
    async function loadFrame() {
      if(busy)return;const value=check(),selected=frame(),ticket=++serial;busy=true;controls();status('Decoding the actual selected source frame…');
      try{
        const row=await execute('learned-frame',{project:clone(value.project),clip_id:context.clipId,settings:{frame_start:selected,frame_count:1}},ticket);
        if(!row||ticket!==serial)return;
        const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('The actual source frame could not be displayed.'));image.src=row.result.url;});
        if(ticket!==serial)return;check();sourceImage=image;sourceFrame=selected;canvas.width=row.result.width;canvas.height=row.result.height;draw();status(`Source clip frame ${selected} is ready for prompts.`);
      }catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    }
    function showResult(response,id) {
      result=response;resultJob=id;const measured=response.measurement?.measurement;
      if(!measured)throw Error('The completed job lacks its learned measurement.');
      el('[data-result]').hidden=false;el('[data-mask-apply]').hidden=measured.backend!=='sam2';el('[data-point-apply]').hidden=!['tapir','tapnext'].includes(measured.backend);
      el('[data-hold-label]').hidden=response.measurement.source_stream?.kind!=='image';el('[data-hold-still]').checked=false;
      const prefix=`/api/projects/${encodeURIComponent(context.projectId)}/learned/outputs/${id}/`;
      const urls=response.artifact_urls||{};
      const preview=urls['preview.png']||response.display_url;
      if(typeof preview==='string'&&preview===prefix+'preview.png'){el('[data-preview]').src=preview;el('[data-preview]').hidden=false;}else el('[data-preview]').hidden=true;
      el('[data-downloads]').replaceChildren();
      for(const [name,url]of Object.entries(urls))if(['result.json','receipt.json','preview.png','mask.mkv'].includes(name)&&url===prefix+name){const link=document.createElement('a');link.href=url;link.download=name;link.textContent=name;el('[data-downloads]').append(link);}
      el('[data-measurement]').textContent=measured.backend==='sam2'?`${measured.frame_count} actual masks · ${measured.width} × ${measured.height} · binary object alpha`:`${measured.tracks.length} learned point${measured.tracks.length===1?'':'s'} · ${measured.frame_count} frames with explicit visibility`;
      el('[data-point]').replaceChildren();for(const item of measured.tracks||[]){const option=document.createElement('option');option.value=item.id;option.textContent=item.id;el('[data-point]').append(option);}
      selectedPoint=el('[data-point]').value;pointCorrections=new Map();
      el('[data-apply-start]').value=response.measurement.recipe.frame_start;el('[data-apply-count]').value=response.measurement.recipe.frame_count;el('[data-corrections]').value='[]';draw();
    }
    async function run() {
      if(busy)return;const value=check(),frozen=clone(validateRecipe(range())),ticket=++serial;busy=true;controls();status('Running the verified checkpoint on the frozen source range…');
      try{
        const row=await execute('learned-track',{project:clone(value.project),clip_id:context.clipId,recipe:frozen},ticket);
        if(!row||ticket!==serial)return;check();await bridge.onComplete?.(row.result,clone(context));if(ticket!==serial)return;
        context={...bridge.getContext(),projectId:context.projectId,clipId:context.clipId};showResult(row.result,row.id);status('Actual learned inference completed. Review and apply it as an undoable edit.');
      }catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    }
    async function save() {
      if(busy)return;check();const value=clone(validateRecipe(range()));busy=true;controls();
      try{await bridge.applyRecipe(value,clone(context));context={...bridge.getContext(),projectId:context.projectId,clipId:context.clipId};status('Prompt recipe saved as one undoable clip edit.');}
      catch(error){status(error.message,true);}finally{busy=false;controls();}
    }
    async function apply(action) {
      if(busy||!resultJob)return;const value=check();busy=true;controls();
      try{
        const body={project:clone(value.project),clip_id:context.clipId,job_id:resultJob,action};
        if(action==='mask'){body.invert=el('[data-invert]').checked;body.hold_still=el('[data-hold-still]').checked;}
        else Object.assign(body,{point_id:el('[data-point]').value,corrections:JSON.parse(el('[data-corrections]').value),frame_start:Number(el('[data-apply-start]').value),frame_count:Number(el('[data-apply-count]').value)});
        const plan=await bridge.request(path('learned-apply-plan'),{method:'POST',body});
        await bridge.applyPlan(plan,clone(context));context={...bridge.getContext(),projectId:context.projectId,clipId:context.clipId};status(action==='mask'?'Actual SAM alpha cutout saved. Undo restores the previous graph.':'Measured stabilization and explicit point corrections saved. Undo restores the previous motion.');
      }catch(error){status(error.message,true);}finally{busy=false;controls();}
    }
    function canvasEdit(event,point) {
      check();if(sourceFrame===null||!sourceImage)throw Error('Load the exact source frame before adding a prompt.');
      range();if(sourceFrame<recipe.frame_start||sourceFrame>=recipe.frame_start+recipe.frame_count)throw Error('The loaded frame is outside the analysis range.');
      const action=el('[data-action]').value;
      if(action==='correction'){
        if(!result||result.backend!=='tapir')throw Error('Run a Learned point query before correcting it.');
        const corrections=JSON.parse(el('[data-corrections]').value);if(!Array.isArray(corrections))throw Error('Corrections must be an explicit JSON sample list.');
        const next=corrections.filter(item=>item.frame!==sourceFrame);next.push({frame:sourceFrame,x:point.x,y:point.y});next.sort((a,b)=>a.frame-b.frame);el('[data-corrections]').value=JSON.stringify(next,null,2);status(`Explicit point correction recorded at clip frame ${sourceFrame}.`);return;
      }
      if(recipe.backend==='sam2'&&['foreground','background'].includes(action)){
        const prompt=promptAt(sourceFrame);if(prompt.points.length>=32)throw Error('This frame already has 32 prompts.');prompt.points.push({...point,label:action==='foreground'?1:0});
      }else if(['tapir','tapnext'].includes(recipe.backend)&&action==='query'){
        if(recipe.points.length>=16)throw Error('This recipe already has 16 point queries.');let index=1;while(recipe.points.some(p=>p.id===`point_${index}`))index++;recipe.points.push({id:`point_${index}`,frame:sourceFrame,...point});
      }else throw Error('Choose a canvas action for the selected model.');
      el('[data-recipe]').value=JSON.stringify(recipe,null,2);draw();
    }
    canvas.addEventListener('pointerdown',event=>{if(busy||!sourceImage)return;try{const point=pointFrom(event);if(el('[data-action]').value==='box'&&recipe.backend==='sam2'){check();range();if(sourceFrame<recipe.frame_start||sourceFrame>=recipe.frame_start+recipe.frame_count)throw Error('Load a frame inside the analysis range.');drag={origin:point,box:[point.x,point.y,point.x,point.y]};canvas.setPointerCapture(event.pointerId);}else canvasEdit(event,point);}catch(error){status(error.message,true);}});
    canvas.addEventListener('pointermove',event=>{if(!drag)return;const p=pointFrom(event),o=drag.origin;drag.box=[Math.min(o.x,p.x),Math.min(o.y,p.y),Math.max(o.x,p.x),Math.max(o.y,p.y)];draw();});
    canvas.addEventListener('pointerup',event=>{if(!drag)return;try{if(drag.box[2]-drag.box[0]<.005||drag.box[3]-drag.box[1]<.005)throw Error('Drag a visible object box.');promptAt(sourceFrame).box=drag.box;el('[data-recipe]').value=JSON.stringify(recipe,null,2);}catch(error){status(error.message,true);}finally{drag=null;draw();if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);}});
    canvas.addEventListener('pointercancel',()=>{drag=null;draw();});
    el('[data-load]').addEventListener('click',()=>loadFrame().catch(error=>status(error.message,true)));
    el('[data-run]').addEventListener('click',()=>run().catch(error=>status(error.message,true)));
    el('[data-save]').addEventListener('click',()=>save().catch(error=>status(error.message,true)));
    el('[data-apply-mask]').addEventListener('click',()=>apply('mask').catch(error=>status(error.message,true)));
    el('[data-apply-point]').addEventListener('click',()=>apply('point').catch(error=>status(error.message,true)));
    el('[data-point]').addEventListener('change',()=>{
      if(selectedPoint)pointCorrections.set(selectedPoint,el('[data-corrections]').value);
      selectedPoint=el('[data-point]').value;
      el('[data-corrections]').value=pointCorrections.get(selectedPoint)||'[]';
    });
    el('[data-cancel]').addEventListener('click',()=>cancel().catch(error=>status(error.message,true)));
    el('[data-backend]').addEventListener('change',()=>{recipe={version:1,backend:el('[data-backend]').value,frame_start:Number(el('[data-start]').value),frame_count:Number(el('[data-count]').value),...(el('[data-backend]').value==='sam2'?{prompts:[]}:{points:[]})};result=null;resultJob=null;el('[data-result]').hidden=true;el('[data-mask-apply]').hidden=true;el('[data-point-apply]').hidden=true;syncRecipe();controls();refreshRuntime().catch(error=>status(error.message,true));});
    el('[data-read-recipe]').addEventListener('click',()=>{try{const next=validateRecipe(JSON.parse(el('[data-recipe]').value));recipe=clone(next);syncRecipe();controls();refreshRuntime().catch(error=>status(error.message,true));status('Edited recipe loaded. Save it or run the actual model.');}catch(error){status(error.message,true);}});
    el('[data-remove-frame]').addEventListener('click',()=>{if(recipe.backend==='sam2')recipe.prompts=recipe.prompts.filter(p=>p.frame!==sourceFrame);else recipe.points=recipe.points.filter(p=>p.frame!==sourceFrame);syncRecipe();});
    el('[data-clear-prompts]').addEventListener('click',()=>{if(recipe.backend==='sam2')recipe.prompts=[];else recipe.points=[];syncRecipe();});
    async function close(){const previous=jobId;++serial;++capabilitySerial;jobId=null;busy=false;await cancel(previous).catch(error=>bridge.notify?.(error.message,true));dialog.close();controls();}
    el('[data-close]').addEventListener('click',()=>close());dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    async function open() {
      const value=current();if(!value.project||!value.clip)throw Error('Select a picture clip before learned analysis.');
      const asset=value.project.assets?.find(a=>a.id===value.clip.asset_id);if(!['video','image'].includes(asset?.kind)||value.clip.track<0)throw Error('Learned analysis requires an owned video or image picture clip.');
      context={...value.context,projectId:value.project.id,clipId:value.clip.id};recipe=clone(value.clip.learned_recipe||{version:1,backend:'sam2',frame_start:0,frame_count:asset.kind==='image'?1:Math.min(10,value.clip.duration),prompts:[]});
      for(const backend of ['tapir','tapnext'])el('[data-backend] option[value="'+backend+'"]').disabled=asset.kind==='image';el('[data-count]').max=asset.kind==='image'?1:32;
      sourceImage=null;sourceFrame=null;result=null;resultJob=null;capabilities=null;selectedPoint=null;pointCorrections=new Map();el('[data-result]').hidden=true;el('[data-mask-apply]').hidden=true;el('[data-point-apply]').hidden=true;
      el('[data-source]').textContent=`${asset.name||'Selected video'} · ${value.clip.duration} conformed clip frames`;el('[data-frame]').value=Math.min(recipe.frame_start,value.clip.duration-1);el('[data-frame]').max=value.clip.duration-1;syncRecipe();dialog.showModal();
      const ticket=++serial;busy=true;controls();
      try{await refreshRuntime();if(ticket!==serial)return;status(modelReady()?'Load a source frame, then choose object prompts or point queries.':'Prompts remain editable; the actual checkpoints are required to run inference.');}
      catch(error){if(ticket===serial)status(error.message,true);}finally{if(ticket===serial){busy=false;controls();}}
      if(ticket===serial)await loadFrame();
    }
    return {open,close,destroy:async()=>{await close();dialog.remove();style.remove();},getRecipe:()=>clone(recipe)};
  }
  window.CinematicumLearnedTracking={mount,validateRecipe};
})();

/* Measured source-space tracking. Own jobs, explicit visibility, reversible edits. */
(() => {
  'use strict';
  const clone=v=>JSON.parse(JSON.stringify(v));
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  function equal(a,b) {
    if(a===b)return true;
    if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;
    const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(key=>Object.hasOwn(b,key)&&equal(a[key],b[key]));
  }
  function sourceIdentity(project,clip,asset) {
    return {asset_id:asset.id,sha256:asset.sha256,width:asset.width,height:asset.height,clip_id:clip.id,
      in:clip.in??0,duration:clip.duration,speed:clip.speed??1,reverse:clip.reverse??false,
      animation_offset:clip.animation_offset??0,frame_rate:project.frame_rate||{numerator:project.fps,denominator:1}};
  }
  function authoredTransform(clip) {
    const fields=['x','y','scale','rotation'],value={};
    for(const key of fields)value[key]=clip[key]??(key==='scale'?1:0);
    value.keyframes=(clip.keyframes||[]).filter(frame=>fields.some(key=>Object.hasOwn(frame,key))).map(frame=>{
      const result={frame:frame.frame,interpolation:frame.interpolation||'linear'};
      for(const key of fields)if(Object.hasOwn(frame,key))result[key]=frame[key];
      return result;
    });
    value.stabilization={};
    for(const name of ['tracking','planar_motion'])if(clip[name])value.stabilization[name]={track_sha256:clip[name].source?.track_sha256??null,invalidated:clip[name].invalidated??null};
    return value;
  }
  function reconcilePlanarBindings(project) {
    // Runs inside the edit's history checkpoint. Preserve clips, media,
    // authored animation and measured keys, including when their driver goes.
    const report={invalidated:0,restored:0,remapped:0,stale:[]};
    if(!project)return report;
    const assets=new Map((project.assets||[]).map(asset=>[asset.id,asset]));
    for(const sequence of [project,...(project.sequences||[])]) {
      const clips=new Map((sequence.clips||[]).map(clip=>[clip.id,clip]));
      // A pin depends on its background's resolved stabilization state. Stored
      // array order must not delay restoration or invalidation by one edit.
      const ordered=[...clips.values()].sort((a,b)=>Number(a.planar_motion?.mode==='corner_pin')-Number(b.planar_motion?.mode==='corner_pin'));
      for(const clip of ordered) {
        const motion=clip.planar_motion;if(!motion)continue;
        const metadata=motion.source||{},source=metadata.source;
        const tracked=motion.mode==='stabilize'?clip:clips.get(source?.clip_id),asset=assets.get(tracked?.asset_id);
        let reason='';
        if(!tracked||!asset||asset.kind!=='video')reason='The measured background is missing. Remeasure or remove this motion.';
        else if(!source||!equal(source,sourceIdentity(project,tracked,asset)))reason='The measured source or timing changed. Remeasure this range.';
        else if(!equal(motion.canvas,{width:asset.width,height:asset.height}))reason='The measured source dimensions changed. Remeasure this range.';
        else if(motion.mode==='corner_pin') {
          if(assets.get(clip.asset_id)?.kind!=='image')reason='The corner-pin overlay must remain an imported image.';
          else if((clip.speed??1)!==1||clip.reverse)reason='The corner-pin image was retimed. Recreate this pin.';
          else if((clip.track??0)<=(tracked.track??0))reason='The corner-pin image must remain above its measured background.';
          else if(metadata.tracked_transform&&!equal(metadata.tracked_transform,authoredTransform(tracked)))reason='The background transform changed. Recreate this pin.';
          else {
            const offset=tracked.animation_offset??0,pinOffset=clip.animation_offset??0,oldStart=metadata.tracked_clip_start;
            if(tracked.start!==oldStart) {
              if(Number.isInteger(oldStart)&&clip.start-oldStart+offset===pinOffset) {
                clip.start+=tracked.start-oldStart;metadata.tracked_clip_start=tracked.start;report.remapped++;
              }else if(clip.start-tracked.start+offset===pinOffset) {
                metadata.tracked_clip_start=tracked.start;report.remapped++;
              }else reason='The corner-pin image moved out of sync. Recreate this pin.';
            }
            if(!reason&&clip.start-tracked.start+offset!==pinOffset)reason='The corner-pin image moved out of sync. Recreate this pin.';
          }
        }
        const lower=clip.animation_start??0,upper=clip.animation_duration??clip.duration;
        if(!reason&&(!Array.isArray(motion.keys)||motion.keys.some(key=>key.frame<lower||key.frame>=upper)))reason='The measured animation range changed. Remeasure this range.';
        if(reason) {
          if(!motion.invalidated)report.invalidated++;
          motion.invalidated=reason;report.stale.push({clip_id:clip.id,reason});
        }else if(motion.invalidated) {delete motion.invalidated;report.restored++;}
      }
    }
    return report;
  }
  function mount(bridge) {
    const dialog=document.createElement('dialog');dialog.id='tracking-dialog';dialog.className='tracking-dialog';
    const markup=`<div class="dialog-header"><div><span class="eyebrow">MEASURED MOTION</span><h2>Track a picture feature</h2></div><button data-track-close class="icon-button" aria-label="Close tracking">×</button></div><p data-track-source class="muted"></p><div class="tracking-layout"><div><div class="tracking-picture"><canvas data-track-canvas width="384" height="216" aria-label="Choose a textured tracking point in the source image" tabindex="0"></canvas></div><p class="note">Click a distinctive feature. The cyan path shows measured positions. Missing matches remain gaps.</p></div><div class="tracking-controls"><div class="field-row"><label>First clip frame<input data-track-start type="number" min="0" step="1"></label><label>Frames<input data-track-count type="number" min="1" max="480" step="1"></label></div><div class="field-row"><label>Patch radius · pixels<input data-track-radius type="number" min="4" max="48" step="1" value="12"></label><label>Match tolerance<input data-track-threshold type="number" min="0.001" max="0.5" step="0.01" value="0.15"></label></div><button data-track-seed class="full">Load starting frame</button><button data-track-run class="primary full" disabled>Measure motion</button><p data-track-status role="status" aria-live="polite">Loading source frame…</p><progress data-track-progress max="1" value="0" hidden></progress><button data-track-cancel class="full" hidden>Cancel measurement</button><div class="tracking-apply"><button data-track-stabilize disabled>Stabilize clip</button><button data-track-mask disabled>Create tracked mask</button><button data-track-clear>Remove stabilization</button></div></div></div><div class="tracking-footer"><button data-track-import>Import point track…</button><a data-track-download class="button" hidden download>Save measurements</a><input data-track-input type="file" accept="application/json,.json" hidden></div><p class="note">Template matching measures translation. Repeated patterns, occlusion, rotation, or scaling can lose the feature. Inspect the path before applying. Stabilization preserves your manual motion; the mask follows the point without identifying an object.</p>`;
    // Build before DOM assignment: innerHTML getters normalize bare data
    // attributes, which made the stale-status insertion disappear in WebKit.
    dialog.innerHTML=markup.replace('Track a picture feature','Track a feature or plane')
      .replace('<p data-track-source class="muted"></p>','<p data-track-source class="muted"></p><p data-track-stale class="error" role="alert" hidden></p>')
      .replace('<p class="note">Click a distinctive feature.','<p data-track-instructions class="note">Click a distinctive feature.')
      .replace('<div class="tracking-controls">','<div class="tracking-controls"><label>Measurement model<select data-track-model><option value="point">Point · translation</option><option value="affine">Plane · affine</option><option value="projective">Plane · projective</option></select></label>')
      .replace('<div class="field-row"><label>Patch radius','<div data-track-point-settings class="field-row"><label>Patch radius')
      .replace('<button data-track-seed','<button data-track-reset-plane class="full" hidden>Choose four corners again</button><button data-track-setup class="full" hidden>Install planar tracking runtime</button><button data-track-seed')
      .replace('<div class="tracking-apply">','<div data-track-pin-controls hidden><label>Corner-pin image<select data-track-image></select></label><button data-track-pin class="full" disabled>Pin image to measured plane</button></div><div class="tracking-apply">')
      .replace('Import point track…','Import measurements…')
      .replace('<p class="note">Template matching','<p data-track-limit class="note">Template matching');
    document.body.append(dialog);
    const $=s=>dialog.querySelector(s),canvas=$('[data-track-canvas]'),ctx=canvas.getContext('2d');
    let context=null,seed=null,point=null,quad=[],track=null,sourceImage=null,jobId=null,serial=0,busy=false,planarRuntime=null;
    const model=()=>['affine','projective'].includes($('[data-track-model]').value)?$('[data-track-model]').value:'point';
    const planar=()=>model()!=='point';
    function status(text,error=false){$('[data-track-status]').textContent=text;$('[data-track-status]').classList.toggle('error',error);}
    function controls() {
      for(const name of ['model','start','count','radius','threshold','seed','import','image','reset-plane','setup'])$(`[data-track-${name}]`).disabled=busy;
      const isPlanar=planar(),complete=track&&track.samples.every(sample=>sample.visible);
      $('[data-track-point-settings]').hidden=isPlanar;$('[data-track-reset-plane]').hidden=!isPlanar;
      $('[data-track-pin-controls]').hidden=!isPlanar;$('[data-track-mask]').hidden=isPlanar;
      $('[data-track-setup]').hidden=!isPlanar||Boolean(planarRuntime?.available);
      $('[data-track-count]').max=isPlanar?240:480;
      $('[data-track-run]').disabled=busy||!seed||(isPlanar?(quad.length!==4||!planarRuntime?.available):!point);
      $('[data-track-stabilize]').disabled=busy||!complete;
      $('[data-track-mask]').disabled=busy||!complete||isPlanar;
      $('[data-track-pin]').disabled=busy||!complete||!isPlanar||!$('[data-track-image]').value;
      $('[data-track-clear]').disabled=busy||!(context?.clip?.tracking||context?.clip?.planar_motion);
      $('[data-track-cancel]').hidden=!busy||!jobId;$('[data-track-progress]').hidden=!busy;
      $('[data-track-instructions]').textContent=isPlanar?'Click four corners clockwise: top left, top right, bottom right, bottom left. Use one textured plane. Arrow keys refine the last corner. Cyan paths show measured corners.':'Click a distinctive feature. The cyan path shows measured positions. Missing matches remain gaps.';
      $('[data-track-limit]').textContent=isPlanar?'Affine/projective measurement uses actual feature flow and geometric fitting, up to 240 conformed clip frames at a 640-pixel analysis edge. Lost support remains a gap; automatic re-identification is not implemented. Corner pins use an imported image.':'Template matching measures translation. Repeated patterns, occlusion, rotation, or scaling can lose the feature. Inspect the path before applying. Stabilization preserves your manual motion; the mask follows the point without identifying an object.';
      const stale=(context?.project?.clips||[]).filter(clip=>clip.planar_motion?.invalidated&&(clip.id===context.clip.id||clip.planar_motion.source?.source?.clip_id===context.clip.id));
      $('[data-track-stale]').hidden=!stale.length;
      $('[data-track-stale]').textContent=stale.length?'Stale planar motion. '+stale.map(clip=>clip.planar_motion.invalidated).join(' ')+' Remeasure or remove it before export.':'';
    }
    function polygon(points,color) {
      if(!points.length)return;ctx.strokeStyle=color;ctx.beginPath();
      points.forEach((p,i)=>{const x=p[0]*canvas.width,y=p[1]*canvas.height;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
      if(points.length===4)ctx.closePath();ctx.stroke();
    }
    function draw() {
      ctx.fillStyle='#111519';ctx.fillRect(0,0,canvas.width,canvas.height);if(sourceImage)ctx.drawImage(sourceImage,0,0,canvas.width,canvas.height);
      ctx.lineWidth=1.5;ctx.strokeStyle='#63ead1';
      if(track?.kind==='planar-track') {
        for(let corner=0;corner<4;corner++) {ctx.beginPath();let previous=false;for(const sample of track.samples){if(!sample.visible){previous=false;continue;}const [x,y]=sample.corners[corner];previous?ctx.lineTo(x*canvas.width,y*canvas.height):ctx.moveTo(x*canvas.width,y*canvas.height);previous=true;}ctx.stroke();}
        const last=track.samples.filter(sample=>sample.visible).at(-1);if(last)polygon(last.corners,'#63ead1');
      }else if(track) {
        ctx.beginPath();let previous=false;for(const sample of track.samples){if(!sample.visible){previous=false;continue;}const x=sample.x*canvas.width,y=sample.y*canvas.height;if(previous)ctx.lineTo(x,y);else ctx.moveTo(x,y);previous=true;}ctx.stroke();
      }
      if(planar()) {polygon(quad,'#ffffff');quad.forEach((p,index)=>{ctx.fillStyle='#ffffff';ctx.fillRect(p[0]*canvas.width-3,p[1]*canvas.height-3,6,6);ctx.fillText(String(index+1),p[0]*canvas.width+5,p[1]*canvas.height-5);});}
      else if(point) {const x=point.x*canvas.width,y=point.y*canvas.height,r=Number($('[data-track-radius]').value)||12;ctx.strokeStyle='#ffffff';ctx.strokeRect(x-r,y-r,r*2,r*2);ctx.beginPath();ctx.moveTo(x-5,y);ctx.lineTo(x+5,y);ctx.moveTo(x,y-5);ctx.lineTo(x,y+5);ctx.stroke();}
    }
    function settings(seedOnly=false) {
      const first=Number($('[data-track-start]').value),count=Number($('[data-track-count]').value),maximum=planar()?240:480;
      if(!Number.isInteger(first)||!Number.isInteger(count)||first<0||count<1||count>maximum||first+count>context.clip.duration)throw Error(`Choose a range of 1–${maximum} frames inside this clip.`);
      const value={mode:model(),frame_start:first,frame_count:count};
      if(planar()) {if(!seedOnly&&quad.length!==4)throw Error('Choose all four plane corners.');value.quad=clone(quad);}
      else Object.assign(value,{radius:Number($('[data-track-radius]').value),threshold:Number($('[data-track-threshold]').value),...point});
      return value;
    }
    const path=action=>`/api/projects/${encodeURIComponent(context.project.id)}/${action}`;
    function payload(extra={}){return {project:clone(context.project),clip_id:context.clip.id,...extra};}
    async function cancelJob(id){if(id)await bridge.request(`/api/jobs/${id}/cancel`,{method:'POST',body:{}}).catch(()=>{});}
    async function cancelOwned(){const previous=jobId;jobId=null;await cancelJob(previous);}
    async function execute(action,body,ticket){
      const job=await bridge.request(path(action),{method:'POST',body});
      if(ticket!==serial){await cancelJob(job.id);return null;}
      jobId=job.id;controls();
      try{
        let current=job;
        while(['queued','running'].includes(current.state)){
          await pause(180);if(ticket!==serial)return null;
          current=await bridge.request(`/api/jobs/${job.id}`);
          if(ticket!==serial)return null;
          $('[data-track-progress]').value=current.progress||0;
        }
        if(ticket!==serial)return null;
        if(current.state!=='completed')throw Error(current.error||'The measurement did not complete.');
        return current.result;
      }catch(error){await cancelJob(job.id);throw error;}
      finally{if(ticket===serial&&jobId===job.id)jobId=null;}
    }
    async function loadSeed() {
      if(busy)return;const ticket=++serial;busy=true;seed=null;track=null;point=null;quad=[];sourceImage=null;
      $('[data-track-download]').hidden=true;controls();draw();status('Decoding the exact starting source frame…');
      try {
        const result=await execute('tracking-frame',payload({settings:settings(true)}),ticket);if(!result||ticket!==serial)return;
        const picture=new Image();await new Promise((resolve,reject)=>{picture.onload=resolve;picture.onerror=()=>reject(Error('The source frame could not be displayed.'));picture.src=result.url;});if(ticket!==serial)return;
        sourceImage=picture;seed=result;canvas.width=result.width;canvas.height=result.height;
        $('[data-track-radius]').max=Math.min(48,Math.floor(Math.min(result.width,result.height)/2));
        $('[data-track-radius]').value=Math.min(Number($('[data-track-radius]').value),Number($('[data-track-radius]').max));
        status(planar()?'Choose the top-left corner of a textured plane.':'Click a textured feature in the source frame.');draw();
      }catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    }
    async function measure() {
      if(busy||!seed||(planar()?quad.length!==4:!point))return;
      const ticket=++serial;busy=true;track=null;controls();status('Measuring each source frame…');
      try {
        const request=settings();if(request.frame_start!==seed.frame_start||request.frame_count!==seed.frame_count)throw Error('Reload the starting frame after changing the range.');
        const result=await execute('tracking',payload({settings:request}),ticket);if(!result||ticket!==serial)return;
        track=result.track;const visible=track.samples.filter(sample=>sample.visible).length;
        status(`${visible} of ${track.samples.length} frames matched. ${visible===track.samples.length?'Review the measured motion, then apply it.':'Missing matches prevent application; use a shorter range or another feature/plane.'}`);
        $('[data-track-download]').href=result.url+'?download=1';$('[data-track-download]').hidden=false;draw();
      }catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    }
    async function apply(kind) {
      if(busy||!track)return;const ticket=serial;busy=true;controls();
      try {
        const latest=bridge.current(context.project.id,context.clip.id);if(!latest)throw Error('The selected clip changed. Reopen tracking.');
        const isPlanar=track.kind==='planar-track',mode=kind==='corner-pin'?'corner_pin':'stabilize';
        const result=await bridge.request(path('tracking-motion'),{method:'POST',body:{project:latest.project,clip_id:context.clip.id,track,mode}});if(ticket!==serial)return;
        const options={asset_id:$('[data-track-image]').value,frame_start:track.samples[0].frame,frame_count:track.samples.length};
        const action=kind==='stabilize'&&isPlanar?'planar-stabilize':kind;
        if(bridge.apply(action,result.motion,track.source,options)!==false) {
          context=bridge.current(context.project.id,context.clip.id);
          status(kind==='corner-pin'?'Corner-pin image added. Undo restores the previous timeline.':kind==='stabilize'?'Stabilization applied. Undo restores the prior motion.':'Animated mask added to this clip’s compositor. Undo removes it.');
        }
      }catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    }
    canvas.addEventListener('pointerdown',event=>{
      if(busy||!seed)return;const rect=canvas.getBoundingClientRect(),picked={x:Math.max(0,Math.min(.999999,(event.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(.999999,(event.clientY-rect.top)/rect.height))};
      if(planar()) {if(quad.length===4)quad=[];quad.push([picked.x,picked.y]);status(quad.length===4?'Plane selected. Measure its affine/projective motion.':`Choose corner ${quad.length+1} of 4, clockwise.`);}
      else {point=picked;status('Feature selected. Measure its motion across the chosen range.');}
      track=null;$('[data-track-download]').hidden=true;draw();controls();
    });
    canvas.addEventListener('keydown',event=>{
      if(busy||!seed||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter'].includes(event.key))return;event.preventDefault();
      if(event.key==='Enter'){measure();return;}
      if(planar()) {if(!quad.length)return;const selected=quad.at(-1);selected[0]=Math.max(0,Math.min(.999999,selected[0]+({'ArrowLeft':-1,'ArrowRight':1}[event.key]||0)/canvas.width));selected[1]=Math.max(0,Math.min(.999999,selected[1]+({'ArrowUp':-1,'ArrowDown':1}[event.key]||0)/canvas.height));}
      else {point??={x:.5,y:.5};point.x=Math.max(0,Math.min(.999999,point.x+({'ArrowLeft':-1,'ArrowRight':1}[event.key]||0)/canvas.width));point.y=Math.max(0,Math.min(.999999,point.y+({'ArrowUp':-1,'ArrowDown':1}[event.key]||0)/canvas.height));}
      track=null;$('[data-track-download]').hidden=true;draw();controls();
    });
    function resetSelection(){seed=null;track=null;point=null;quad=[];sourceImage=null;$('[data-track-download]').hidden=true;draw();controls();status('Load the starting frame for this range.');}
    for(const name of ['start','count'])$(`[data-track-${name}]`).addEventListener('change',resetSelection);
    $('[data-track-model]').onchange=()=>{if(planar())$('[data-track-count]').value=Math.min(240,Number($('[data-track-count]').value));resetSelection();loadSeed();};
    $('[data-track-reset-plane]').onclick=()=>{quad=[];track=null;$('[data-track-download]').hidden=true;draw();controls();status('Choose the top-left corner of a textured plane.');};
    $('[data-track-image]').onchange=controls;
    $('[data-track-pin]').onclick=()=>apply('corner-pin');
    $('[data-track-setup]').onclick=async()=>{
      if(busy)return;const ticket=++serial;busy=true;controls();status('Installing the isolated planar tracking runtime…');
      try {const result=await execute('tracking-setup',{},ticket);if(!result||ticket!==serial)return;planarRuntime=result.status;status(planarRuntime?.available?'Planar runtime verified. Choose four plane corners and measure.':planarRuntime?.reason||'The planar runtime is unavailable.',!planarRuntime?.available);}
      catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    };
    $('[data-track-radius]').addEventListener('input',draw);$('[data-track-seed]').onclick=loadSeed;$('[data-track-run]').onclick=measure;
    $('[data-track-stabilize]').onclick=()=>apply('stabilize');$('[data-track-mask]').onclick=()=>apply('mask');
    $('[data-track-clear]').onclick=()=>{if(bridge.apply('clear',null,track?.source||seed?.source)!==false){context=bridge.current(context.project.id,context.clip.id);controls();status('Stabilization removed. Manual motion is preserved.');}};
    $('[data-track-import]').onclick=()=>$('[data-track-input]').click();
    $('[data-track-input]').onchange=async event=>{
      const file=event.target.files[0];event.target.value='';if(!file||busy)return;const ticket=++serial;busy=true;controls();
      try {
        if(file.size>1024*1024)throw Error('Measurement documents must be under 1 MiB.');
        const latest=bridge.current(context.project.id,context.clip.id);if(!latest)throw Error('The selected clip changed.');
        const result=await bridge.request(path('tracking-validate'),{method:'POST',body:{project:latest.project,clip_id:context.clip.id,track:JSON.parse(await file.text())}});if(ticket!==serial)return;
        track=result.track;seed=null;sourceImage=null;point=null;quad=track.kind==='planar-track'?clone(track.reference_quad):[];
        $('[data-track-model]').value=track.kind==='planar-track'?track.model:'point';
        $('[data-track-start]').value=track.samples[0].frame;$('[data-track-count]').value=track.samples.length;
        $('[data-track-download]').hidden=true;draw();status(`Imported ${track.samples.length} measured frames. Source identity and frame coordinates match this clip.`);
      }catch(error){if(ticket===serial)status(error.message,true);}
      finally{if(ticket===serial){busy=false;controls();}}
    };
    $('[data-track-cancel]').onclick=async()=>{const ticket=++serial,pending=cancelOwned();controls();await pending;if(ticket!==serial)return;busy=false;controls();status('Measurement cancelled.');};
    $('[data-track-close]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{++serial;cancelOwned();busy=false;context=null;});
    return {open(value){
      if(dialog.open)return;context=clone(value);seed=null;track=null;point=null;quad=[];sourceImage=null;busy=false;
      planarRuntime=bridge.capabilities?.()?.planar_tracking||planarRuntime;
      $('[data-track-model]').value='point';const first=Math.max(0,Math.min(value.clip.duration-1,value.frame-value.clip.start));
      $('[data-track-start]').value=first;$('[data-track-start]').max=value.clip.duration-1;$('[data-track-count]').value=Math.min(240,value.clip.duration-first);
      $('[data-track-source]').textContent=value.asset.name+' · source coordinates · '+value.clip.duration+' clip frames';
      $('[data-track-image]').innerHTML='<option value="">Choose an imported image…</option>'+(value.project.assets||[]).filter(asset=>asset.kind==='image'&&!asset.name.startsWith('__title_')).map(asset=>`<option value="${esc(asset.id)}">${esc(asset.name)}</option>`).join('');
      $('[data-track-download]').hidden=true;dialog.showModal();loadSeed();
    },destroy(){++serial;cancelOwned();dialog.remove();}};
  }
  window.CinematicumTracking={mount,reconcilePlanarBindings};
})();

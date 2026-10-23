/* Ordinary authoring controls; the backend validates and returns one edit. */
(() => {
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  const selectedId=bridge=>{const value=bridge.getSelectedClip?.();return typeof value==='string'?value:value?.id;};
  function mount(host,bridge) {
    const model=window.CinematicumRetimeModel;if(!model)throw Error('The speed-ramp model is unavailable.');
    const dialog=document.createElement('dialog');dialog.className='cinematicum-retime';
    dialog.innerHTML=`<div class="retime-heading"><h2>Speed ramp & motion interpolation</h2><button type="button" data-retime-close aria-label="Close speed ramp">×</button></div><p data-retime-source></p><p class="retime-note" data-retime-eligibility></p><div class="retime-options"><label>Output duration · frames<input data-retime-duration type="number" min="1" max="240" step="1"></label><label>Picture interpolation<select data-retime-method><option value="nearest">Nearest source frame</option><option value="optical_flow">Optical flow</option></select></label><label>Ramp sound<select data-retime-audio><option value="varispeed">Varispeed · pitch follows speed</option><option value="pitch_preserve">Preserve pitch · rendered sound</option><option value="mute">Mute this clip</option></select></label></div><svg data-retime-chart viewBox="0 0 640 116" role="img" aria-label="Authored speed curve over output frames"></svg><div class="retime-keys"><table><thead><tr><th>Output frame</th><th>Speed</th><th></th></tr></thead><tbody data-retime-keys></tbody></table></div><button type="button" data-retime-add>Add speed key</button><p data-retime-summary role="status"></p><p class="retime-note">Speeds change linearly between keys. Negative speeds reverse the source; zero speed holds a picture with silent sound. Source time follows the signed area under the speed curve. Use rendered playback to hear and inspect the edit. Varispeed changes pitch. Preserve pitch supports positive 0.25–4× curves with stereo-linked spectral processing; transients can soften. Review rendered speech and music.</p><p class="retime-note">Optical flow estimates motion between source frames. Occlusion, fast movement, flashes and cuts can distort the generated pictures. Review the rendered result.</p><div class="retime-actions"><button type="button" data-retime-apply>Apply speed ramp</button><button type="button" data-retime-remove>Remove speed ramp</button></div><p data-retime-status role="status"></p>`;
    const style=document.createElement('style');style.textContent='.cinematicum-retime{width:min(780px,92vw);max-height:90vh;overflow:auto;color:#e8ebef;background:#171a20;border:1px solid #48525f;border-radius:10px;padding:22px}.retime-heading{display:flex;justify-content:space-between;gap:18px;align-items:start}.retime-heading h2{font-size:18px;margin:0 0 8px}.cinematicum-retime button,.cinematicum-retime input,.cinematicum-retime select{font:inherit;color:inherit;background:#252b35;border:1px solid #566170;border-radius:4px;padding:7px}.cinematicum-retime button{cursor:pointer}.cinematicum-retime button:disabled{opacity:.45;cursor:default}.retime-options{display:flex;flex-wrap:wrap;gap:16px;margin:16px 0}.retime-options label{display:flex;flex-direction:column;gap:7px;font-size:12px}.retime-options input{width:125px}.retime-keys{max-height:28vh;overflow:auto;margin:8px 0}.retime-keys table{width:100%;border-collapse:collapse;font-size:12px}.retime-keys th,.retime-keys td{text-align:left;padding:7px;border-bottom:1px solid #38414d}.retime-keys input{max-width:130px}.retime-note{color:#b6bfca;font-size:12px;line-height:1.5}.retime-actions{display:flex;gap:10px;margin-top:16px}[data-retime-apply]{background:#b28342!important;color:#fff!important}[data-retime-chart]{width:100%;height:116px;background:#12161c;border:1px solid #38414d;border-radius:4px}[data-retime-summary]{font-size:13px;line-height:1.5;min-height:38px}[data-retime-status]{min-height:20px;color:#b8ccff}[data-retime-status].error,[data-retime-summary].error,[data-retime-eligibility].error{color:#ffb7a9}';
    host.append(style,dialog);
    const $=selector=>dialog.querySelector(selector),removers=[];
    let snapshot=null,expected=null,clip=null,asset=null,busy=false,disposed=false,serial=0,blocked='',valid=false;
    const listen=(element,event,fn)=>{element.addEventListener(event,fn);removers.push(()=>element.removeEventListener(event,fn));};
    const message=(value,error=false)=>{$('[data-retime-status]').textContent=value;$('[data-retime-status]').classList.toggle('error',error);};
    function current(){const now=bridge.getContext();if(!snapshot||bridge.getProject()?.id!==snapshot.id||now.projectId!==expected.projectId||now.revision!==expected.revision||selectedId(bridge)!==clip?.id)throw Error('The selected edit changed. Reopen Speed ramp to use the current clip.');}
    function number(element,label){if(!element.value.trim())throw Error(label+' is required.');const value=Number(element.value);if(!Number.isFinite(value))throw Error(label+' must be finite.');return value;}
    function keys(){return [...dialog.querySelectorAll('[data-retime-key]')].map(row=>({frame:number(row.querySelector('[data-retime-frame]'),'Key frame'),speed:number(row.querySelector('[data-retime-speed]'),'Key speed')}));}
    function draft(){
      const duration=number($('[data-retime-duration]'),'Output duration');
      if(!Number.isInteger(duration)||duration<1||duration>240)throw Error('Output duration must be 1–240 whole frames.');
      const recipe={version:1,method:$('[data-retime-method]').value,audio:$('[data-retime-audio]').value,offset:0,source_origin:clip?model.sourceOrigin(clip):{numerator:'0',denominator:'1'},keys:keys()};model.validate(recipe);
      if(recipe.keys[recipe.keys.length-1].frame!==duration)throw Error('The final speed key must meet the output duration.');
      return {duration,recipe};
    }
    function controls(){
      for(const element of dialog.querySelectorAll('input,select,[data-retime-add],[data-retime-delete]'))element.disabled=busy||Boolean(blocked);
      const rows=[...dialog.querySelectorAll('[data-retime-key]')];
      rows.forEach((row,index)=>{const endpoint=index===0||index===rows.length-1;row.querySelector('[data-retime-frame]').disabled=busy||Boolean(blocked)||endpoint;row.querySelector('[data-retime-delete]').disabled=busy||Boolean(blocked)||endpoint;});
      $('[data-retime-add]').disabled=busy||Boolean(blocked)||rows.length>=32||!valid||!rows.some((row,i)=>i&&Number(row.querySelector('[data-retime-frame]').value)-Number(rows[i-1].querySelector('[data-retime-frame]').value)>=2);
      $('[data-retime-apply]').disabled=busy||Boolean(blocked)||!valid;
      $('[data-retime-remove]').disabled=busy||!clip?.retime;
      $('[data-retime-audio]').disabled=busy||Boolean(blocked)||!asset?.has_audio;
      $('[data-retime-method]').disabled=busy||Boolean(blocked)||asset?.kind==='audio';
    }
    function row(key){return `<tr data-retime-key><td><input type="number" data-retime-frame min="0" max="240" step="1" value="${key.frame}" aria-label="Speed key output frame"></td><td><input type="number" data-retime-speed min="-4" max="4" step="0.05" value="${key.speed}" aria-label="Speed key multiplier"></td><td><button type="button" data-retime-delete>Delete key</button></td></tr>`;}
    function curve(recipe,duration){
      const x=frame=>28+frame/duration*592,y=speed=>99-(speed+4)/8*82;
      const points=recipe.keys.map(key=>`${x(key.frame).toFixed(2)},${y(key.speed).toFixed(2)}`).join(' ');
      $('[data-retime-chart]').innerHTML=`<path d="M28 17V99H620M28 58H620" fill="none" stroke="#657386"/><text x="3" y="22" fill="#aeb9c8" font-size="10">4×</text><text x="1" y="101" fill="#aeb9c8" font-size="9">−4×</text><text x="5" y="61" fill="#aeb9c8" font-size="9">0×</text><text x="28" y="112" fill="#aeb9c8" font-size="9">0</text><text x="620" y="112" text-anchor="end" fill="#aeb9c8" font-size="9">${duration}</text><polyline points="${points}" fill="none" stroke="#e1b46e" stroke-width="2"/>${recipe.keys.map(key=>`<circle cx="${x(key.frame).toFixed(2)}" cy="${y(key.speed).toFixed(2)}" r="3" fill="#f4d5a0"/>`).join('')}`;
    }
    function update(){
      valid=false;
      try{
        const {duration,recipe}=draft(),consumed=model.integral(recipe,duration),range=model.sourceBounds({retime:recipe,duration},0,duration);
        if(!clip||!asset)throw Error('Select a direct video or audio clip.');
        const fps=snapshot.frame_rate?snapshot.frame_rate.numerator/snapshot.frame_rate.denominator:snapshot.fps,available=asset.duration*fps;
        if(range.min<0)throw Error('The speed curve crosses before source frame zero. Move the source in or shorten the reverse interval.');
        if(range.max>available+1e-7)throw Error(`The ramp needs source frame ${range.max.toFixed(3)}, beyond the available ${available.toFixed(3)}. Reduce duration or speed.`);
        curve(recipe,duration);
        $('[data-retime-summary]').textContent=`${duration} output frames · net source displacement ${consumed.toFixed(3)} frames · full source range ${range.min.toFixed(3)}–${range.max.toFixed(3)}. ${recipe.audio==='mute'?'This clip is silent.':recipe.audio==='pitch_preserve'?'Original pitch is preserved; review rendered transients.':'Pitch and direction follow speed; zero-speed holds are silent.'}`;
        $('[data-retime-summary]').classList.remove('error');valid=true;
      }catch(error){$('[data-retime-summary]').textContent=error.message;$('[data-retime-summary]').classList.add('error');$('[data-retime-chart]').innerHTML='';}
      controls();
    }
    function unsupported(){
      if(!clip||!asset||!['video','audio'].includes(asset.kind)||clip.sequence_id)return 'Select a direct video or audio clip. Nested sequence clips are unsupported.';
      if((snapshot.settings?.image_precision||'standard8')!=='standard8')return 'Speed ramps currently require Standard 8-bit SDR processing.';
      if((snapshot.tracks||[]).some(track=>track.id===clip.track&&track.locked))return 'Unlock the selected track before editing its speed ramp.';
      if(clip.reverse)return 'Reverse and speed ramps cannot be combined. Disable Reverse first.';
      if((clip.speed??1)!==1)return 'Return the selected clip to forward 1× before adding a variable-speed curve.';
      if(clip.multicam)return 'Multicamera-bound clips cannot use a speed ramp.';
      if(snapshot.clips.some(other=>other.planar_motion?.source?.source?.clip_id===clip.id))return 'Remove dependent measured corner pins before applying a speed ramp to their background.';
      if(clip.tracking||clip.planar_motion||clip.learned_bindings||clip.learned_recipe||clip.compositor?.nodes?.some(node=>node.tracking_source))return 'Remove measured tracking before applying a speed ramp. Undo preserves the previous edit.';
      if(Math.max(asset.width||0,asset.height||0)>1280)return 'Speed ramps support sources with a maximum 1,280-pixel edge.';
      return '';
    }
    function open(){
      if(disposed)return;
      const project=bridge.getProject();if(!project)throw Error('Open a project before editing speed.');
      serial++;busy=false;snapshot=clone(project);expected=clone(bridge.getContext());clip=snapshot.clips.find(value=>value.id===selectedId(bridge))||null;asset=snapshot.assets.find(value=>value.id===clip?.asset_id)||null;
      blocked=unsupported();$('[data-retime-eligibility]').textContent=blocked||'Up to 240 output frames and 32 speed keys. Standard 8-bit SDR; source edge at most 1,280 pixels.';$('[data-retime-eligibility]').classList.toggle('error',Boolean(blocked));
      $('[data-retime-source]').textContent=asset?asset.name:'No eligible source selected';
      const duration=Math.max(1,Math.min(240,clip?.duration||24));$('[data-retime-duration]').value=duration;
      let points=[{frame:0,speed:clip?.speed??1},{frame:duration,speed:clip?.speed??1}];
      try{if(clip?.retime)points=model.localKeys(clip);}catch(error){blocked=error.message;$('[data-retime-eligibility]').textContent=blocked;$('[data-retime-eligibility]').classList.add('error');}
      $('[data-retime-method]').value=asset?.kind==='audio'?'nearest':clip?.retime?.method||'nearest';
      $('[data-retime-audio]').value=asset?.has_audio?(clip?.retime?.audio||'varispeed'):'mute';
      $('[data-retime-keys]').innerHTML=points.map(row).join('');message('');update();if(!dialog.open)dialog.showModal();
    }
    function close(){serial++;busy=false;dialog.close();}
    async function action(name){
      if(disposed||busy)return;
      let values;
      try{current();if(name==='retime_apply'){if(blocked)throw Error(blocked);const {duration,recipe}=draft();values={clip_id:clip.id,duration,method:recipe.method,audio:recipe.audio,keys:recipe.keys};}else values={clip_id:clip.id};}
      catch(error){message(error.message,true);return;}
      const token=++serial;busy=true;controls();message('Applying speed edit…');
      try{
        const result=await bridge.request(`/api/projects/${encodeURIComponent(snapshot.id)}/editorial`,{method:'POST',body:{project:clone(snapshot),action:name,values}});
        if(disposed||token!==serial||!dialog.open)return;current();
        if(result.project?.id!==snapshot.id)throw Error('The speed edit returned a different project.');
        if(await bridge.onApply(clone(result.project),clone(expected),{action:name})===false)throw Error('The project changed before the speed edit could be applied.');
        if(disposed||token!==serial)return;close();bridge.notify?.('Speed edit applied. Undo restores the previous edit; Save retains it.');
      }catch(error){if(!disposed&&token===serial)message(error.message,true);}
      finally{if(!disposed&&token===serial){busy=false;controls();}}
    }
    function changed(event){
      if(busy)return;
      if(event.target.matches('[data-retime-duration]')){const rows=[...dialog.querySelectorAll('[data-retime-key]')];if(rows.length)rows[rows.length-1].querySelector('[data-retime-frame]').value=event.target.value;}
      if(event.target.matches('input,select')){message('');update();}
    }
    listen(dialog,'input',changed);listen(dialog,'change',changed);
    listen(dialog,'click',event=>{
      const button=event.target.closest('button');if(!button)return;
      if(button.hasAttribute('data-retime-close')){close();return;}if(busy)return;
      if(button.hasAttribute('data-retime-add')){
        try{const points=keys();if(points.length>=32)throw Error('The ramp already has 32 keys.');let index=1;for(let i=2;i<points.length;i++)if(points[i].frame-points[i-1].frame>points[index].frame-points[index-1].frame)index=i;
          const a=points[index-1],b=points[index];if(b.frame-a.frame<2)throw Error('No whole output frame remains between the existing keys.');const frame=Math.floor((a.frame+b.frame)/2),speed=a.speed+(b.speed-a.speed)*(frame-a.frame)/(b.frame-a.frame);points.splice(index,0,{frame,speed});$('[data-retime-keys]').innerHTML=points.map(row).join('');update();
        }catch(error){message(error.message,true);}
      }
      if(button.hasAttribute('data-retime-delete')){const rows=[...dialog.querySelectorAll('[data-retime-key]')],index=rows.indexOf(button.closest('[data-retime-key]'));if(index>0&&index<rows.length-1){rows[index].remove();update();}}
      if(button.hasAttribute('data-retime-apply'))void action('retime_apply');
      if(button.hasAttribute('data-retime-remove'))void action('retime_remove');
    });
    listen(dialog,'cancel',event=>{event.preventDefault();close();});listen(dialog,'close',()=>{serial++;busy=false;});listen(dialog,'keydown',event=>event.stopPropagation());
    return {open,close,destroy(){disposed=true;serial++;removers.forEach(remove=>remove());dialog.remove();style.remove();}};
  }
  window.CinematicumRetime={mount};
})();

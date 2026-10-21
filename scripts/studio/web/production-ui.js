/* Production requirements bind to existing project media and produce one shared
 * undoable edit. Filenames/directories in the plan are never opened or fetched. */
(() => {
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  // Shot IDs are user-authored strings, including legitimate names such as
  // "__proto__" and "constructor". They must never be JavaScript properties
  // inherited from, or assigned through, Object.prototype.
  const bindingMap=value=>Object.assign(Object.create(null),clone(value??{}));
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const css=`
.cinematicum-production{width:min(1080px,calc(100vw - 40px));max-width:1080px;max-height:calc(100vh - 40px);padding:0;overflow:hidden;box-sizing:border-box;background:#181e26;border:1px solid #465365;border-radius:9px;color:#dbe4ef;box-shadow:0 20px 90px #000a;font:12px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.cinematicum-production::backdrop{background:#05090dbb}.cinematicum-production[open]{display:flex;flex-direction:column}.cinematicum-production *{box-sizing:border-box}.cinematicum-production [hidden]{display:none!important}.cinematicum-production header{padding:17px 20px;display:flex;align-items:start;justify-content:space-between;gap:18px;border-bottom:1px solid #35404e}.cinematicum-production h2{margin:0;font-size:18px}.cinematicum-production h3{margin:0;font-size:13px}.cinematicum-production p{margin:5px 0;color:#a2b0c3}.cinematicum-production button,.cinematicum-production input,.cinematicum-production select,.cinematicum-production a{font:inherit}.cinematicum-production button,.cinematicum-production a{min-height:30px;border:1px solid #455266;border-radius:4px;padding:5px 10px;background:#26313f;color:#dbe4ef;text-decoration:none;cursor:pointer}.cinematicum-production button:disabled{opacity:.4;cursor:default}.cinematicum-production button.primary{background:#e7b66f;border-color:#e7b66f;color:#211a10;font-weight:650}.cinematicum-production input,.cinematicum-production select{min-height:30px;width:100%;padding:5px 7px;color:#dbe4ef;background:#101720;border:1px solid #435166;border-radius:4px}.cinematicum-production input[type=checkbox]{width:auto;min-height:0;margin:0 5px 0 0}.cinematicum-production label{font-size:11px;color:#a4b4ca}.production-body{min-height:0;overflow:auto;padding:16px 20px}.production-top{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.production-top label{flex:1;min-width:240px}.production-top input{margin-top:5px}.production-summary{padding:12px 0 6px;color:#d5e0ed!important}.production-help{font-size:11px;line-height:1.6}.production-shots{margin-top:12px;border:1px solid #354354;border-radius:5px;overflow:hidden}.production-row{display:grid;grid-template-columns:minmax(170px,1.1fr) minmax(180px,1.3fr) 74px 74px 65px;gap:9px;align-items:start;padding:12px;border-bottom:1px solid #303d4d}.production-row:last-child{border-bottom:0}.production-row strong{display:block;font-weight:550;font-size:11px;overflow-wrap:anywhere}.production-row small{display:block;font-size:10px;color:#8297b2;overflow-wrap:anywhere}.production-row .shot-description{margin-top:4px;line-height:1.5}.production-row label input,.production-row label select{margin-top:5px;font-size:11px}.production-row .alternate-take{display:flex;align-items:center;margin-top:7px;font-size:10px}.production-row .alternate-take input{margin-top:0}.production-source-actions{display:flex;align-items:center;gap:8px;margin-top:6px}.production-source-actions button{min-height:23px;font-size:10px;padding:2px 7px}.production-row .shot-status{grid-column:1/-1;font-size:10px;color:#9bb2c5;overflow-wrap:anywhere}.production-row .shot-status.error{color:#efb3ae}.production-row .shot-status.ready{color:#a3cdb4}.production-length{margin-top:25px;font:11px ui-monospace,SFMono-Regular,monospace;color:#d7c49f}.production-preview{margin:14px 0;border:1px solid #405068;border-radius:5px;padding:10px;background:#101720}.production-preview>div{display:flex;align-items:center;justify-content:space-between;gap:10px}.production-preview video{display:block;width:100%;max-height:260px;margin-top:10px;background:#000}.production-footer{flex:none;padding:13px 20px 16px;border-top:1px solid #354151;background:#1b222c}.production-footer-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.production-footer-actions .production-spacer{flex:1}.production-status{min-height:18px;padding-top:6px;overflow-wrap:anywhere;font-size:11px}.production-status.error{color:#efb3ae}.production-replace{margin:0 0 10px;font-size:11px;color:#b9c8d8}.production-format{display:flex;align-items:center;margin:8px 0 12px;color:#edc38d!important;font-size:11px}.production-plan-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px}.production-plan-actions a{font-size:11px}.production-plan-actions small{font-size:10px;color:#879bb5}@media(max-width:800px){.production-row{grid-template-columns:1fr 1fr 70px 70px 60px;gap:7px;padding:10px}.production-row>div:first-child{grid-column:1/-1}.production-row>div:nth-child(2){grid-column:1/3}.production-row .shot-description{display:none}.cinematicum-production{width:calc(100vw - 24px);max-height:calc(100vh - 24px)}}
`;
  function mount(host,bridge={}) {
    const doc=host.ownerDocument||document,style=doc.createElement('style');style.textContent=css;doc.head.append(style);
    const dialog=doc.createElement('dialog');dialog.className='cinematicum-production';dialog.setAttribute('aria-label','Production shot plan');
    dialog.innerHTML=`<header><div><h2>Production shot plan</h2><p data-production-project></p></div><button type="button" data-production-close>Close</button></header>
      <div class="production-body"><div class="production-top"><label>Shotlist JSON<input type="file" accept=".json,application/json" data-production-file></label><button type="button" data-production-match disabled>Match imported filenames</button></div>
      <p class="production-help">Import your shot requirements, choose footage from this project's media bin, and set each source range. The plan's shot order and lengths become an editable cut.</p>
      <p class="production-summary" data-production-summary>Choose a shotlist JSON file, up to 2 MiB.</p><div class="production-plan-actions"><button type="button" data-production-export disabled>Export shot requirements</button><a data-production-download hidden>Download JSON</a><small>Source selections and trims stay with the saved project.</small></div>
      <div class="production-preview" data-production-preview hidden><div><span data-production-preview-label></span><button type="button" data-production-stop-preview>Close preview</button></div><video controls playsinline preload="metadata" data-production-video></video><p class="production-help">Source preview uses the selected media. Use the assembled timeline's rendered preview to judge final processing.</p></div>
      <div class="production-shots" data-production-shots hidden></div></div>
      <footer class="production-footer"><p class="production-replace" data-production-replace>Save the plan now and bind missing footage later. Assembly requires every shot to have a valid video range.</p>
      <label class="production-format" data-production-format-wrap hidden><input type="checkbox" data-production-format>Replace this edit's format with the plan's resolution and frame rate</label>
      <div class="production-footer-actions"><button type="button" data-production-save disabled>Save plan to project</button><button type="button" data-production-review disabled>Check selected takes</button><span class="production-spacer"></span><button type="button" class="primary" data-production-conform disabled>Assemble planned cut</button></div>
      <p role="status" class="production-status" data-production-status></p></footer>`;
    host.append(dialog);
    const $=selector=>dialog.querySelector(selector),removers=[];
    let disposed=false,busy=false,serial=0,snapshot=null,expected=null,source='',plan=null,selected=bindingMap(),report=null,previewRange=null;
    const listen=(element,event,handler)=>{element.addEventListener(event,handler);removers.push(()=>element.removeEventListener(event,handler));};
    const context=()=>clone(bridge.getContext?.()||{projectId:bridge.getProject?.()?.id,revision:bridge.getProject?.()?.revision});
    function current(){const now=context();if(snapshot?.id!==bridge.getProject?.()?.id||now.projectId!==expected?.projectId||now.revision!==expected?.revision)throw Error('The project changed while Production was open. Close and reopen it to use the current edit.');}
    function message(value,error=false){$('[data-production-status]').textContent=value;$('[data-production-status]').classList.toggle('error',error);}
    function validRange(binding){return Number.isSafeInteger(binding?.in_frame)&&binding.in_frame>=0&&binding.in_frame<=Math.floor(21600*plan.frame_rate.numerator/plan.frame_rate.denominator);}
    function validRanges(){return !plan||Object.values(selected).every(validRange);}
    function formatChange(){return Boolean(plan&&(snapshot.clips.length||snapshot.titles.length)&&(snapshot.width!==plan.width||snapshot.height!==plan.height||Math.abs(snapshot.fps-plan.fps)>1e-9));}
    function controls(){
      for(const element of dialog.querySelectorAll('input,select,[data-production-match],[data-production-save],[data-production-review],[data-production-conform],[data-production-export],[data-production-preview-shot]'))element.disabled=busy;
      for(const selector of ['match','save','review','export'])$(`[data-production-${selector}]`).disabled=busy||!plan;
      for(const selector of ['save','review'])$(`[data-production-${selector}]`).disabled=busy||!plan||!validRanges();
      for(const button of dialog.querySelectorAll('[data-production-preview-shot]')){const binding=selected[plan?.shots[Number(button.dataset.productionPreviewShot)]?.id];button.disabled=busy||!binding?.asset_id||!validRange(binding);}
      $('[data-production-conform]').disabled=busy||!report?.ready||!validRanges()||(formatChange()&&!$('[data-production-format]').checked);
      $('[data-production-format-wrap]').hidden=!formatChange();
    }
    function payload(){const body={project:clone(snapshot),document:source,bindings:clone(selected)};if(new TextEncoder().encode(JSON.stringify(body)).length>8*1024*1024)throw Error('The project and shot plan exceed the 8 MiB request limit.');return body;}
    function endpoint(operation){return `/api/projects/${encodeURIComponent(snapshot.id)}/production-${operation}`;}
    function releaseDownload(){$('[data-production-download]').hidden=true;$('[data-production-download]').removeAttribute('href');}
    function stopPreview(){const video=$('[data-production-video]');previewRange=null;video.pause();video.removeAttribute('src');video.load();$('[data-production-preview]').hidden=true;}
    function invalidate(){report=null;for(const element of dialog.querySelectorAll('[data-production-row-status]')){element.textContent='Selection changed. Check the selected takes before assembly.';element.className='shot-status';}controls();}
    function renderRows(){
      const assets=(snapshot?.assets||[]).filter(asset=>asset.kind==='video');
      $('[data-production-shots]').hidden=!plan;
      if(!plan){$('[data-production-shots]').replaceChildren();return;}
      const byId=new Map((report?.shots||[]).map(row=>[row.id,row]));
      $('[data-production-shots]').innerHTML=plan.shots.map((shot,index)=>{
        const binding=selected[shot.id]||{asset_id:null,in_frame:0,allow_name_mismatch:false},row=byId.get(shot.id);
        const status=row?(row.errors.length?row.errors.join(' '):`Ready · ${row.available_frames} source frames · ${row.head_handle_frames} head / ${row.tail_handle_frames} tail handle frames.`)+(row.warnings.length?' '+row.warnings.join(' '):''):'Choose footage and check its available handles.';
        return `<section class="production-row" data-production-row="${index}"><div><strong>${esc(shot.id)}</strong><small>${esc(shot.filename)} · timeline ${shot.start_frame}–${shot.start_frame+shot.duration_frames}</small><small class="shot-description">${esc(shot.description)}</small></div>
        <div><label>Source take<select data-production-source="${index}"><option value="">Select imported video…</option>${assets.map(asset=>`<option value="${esc(asset.id)}" ${asset.id===binding.asset_id?'selected':''}>${esc(asset.name)}</option>`).join('')}</select></label><label class="alternate-take"><input type="checkbox" data-production-alternate="${index}" ${binding.allow_name_mismatch?'checked':''}>Use this alternate filename</label><div class="production-source-actions"><button type="button" data-production-preview-shot="${index}" ${binding.asset_id?'':'disabled'}>Preview take</button></div></div>
        <label>In · frames<input type="number" min="0" max="1296000" step="1" value="${esc(binding.in_frame)}" data-production-in="${index}"></label><label>Out · excl.<input type="number" min="${shot.duration_frames}" max="1296000" step="1" value="${esc(binding.in_frame+shot.duration_frames)}" data-production-out="${index}"></label><div><small>Length</small><div class="production-length">${shot.duration_frames} fr</div></div>
        <div class="shot-status ${row?.ready?'ready':row?'error':''}" data-production-row-status="${index}">${esc(status)}</div></section>`;
      }).join('');
      const rate=plan.frame_rate.denominator===1?String(plan.frame_rate.numerator):`${plan.frame_rate.numerator}/${plan.frame_rate.denominator}`;
      $('[data-production-summary]').textContent=`${plan.film} · ${plan.shots.length} shots · ${plan.runtime_frames} frames · ${(plan.runtime_frames/plan.fps).toFixed(3)} s · ${plan.width} × ${plan.height} · ${rate} fps`;
      const replacing=(snapshot.clips.length||snapshot.titles.length)>0;
      $('[data-production-conform]').textContent=replacing?'Replace timeline with planned cut':'Assemble planned cut';
      $('[data-production-replace]').textContent=replacing?`Assembly replaces ${snapshot.clips.length} clips and ${snapshot.titles.length} titles with the complete planned cut. Save plan changes only the plan. Both actions can be undone.`:'Save the plan now and bind missing footage later. Assembly requires every shot to have a valid video range.';
      controls();
    }
    function updateSelection(element){
      const raw=element.dataset.productionSource??element.dataset.productionAlternate??element.dataset.productionIn??element.dataset.productionOut;
      if(raw===undefined||!plan)return;const index=Number(raw),shot=plan.shots[index];if(!shot)return;
      const row=$(`[data-production-row="${index}"]`),input=row.querySelector('[data-production-in]'),out=row.querySelector('[data-production-out]');
      const changingOut=element.hasAttribute('data-production-out'),text=changingOut?out.value:input.value;
      const number=text.trim()===''?NaN:Number(text),inFrame=changingOut?number-shot.duration_frames:number;
      const valid=validRange({in_frame:inFrame});
      if(changingOut)input.value=valid?String(inFrame):'';
      else out.value=valid?String(inFrame+shot.duration_frames):'';
      selected[shot.id]={asset_id:row.querySelector('[data-production-source]').value||null,in_frame:valid?inFrame:null,allow_name_mismatch:row.querySelector('[data-production-alternate]').checked};
      stopPreview();invalidate();message(valid?'Check the selected takes to update source availability.':'Enter a whole, nonnegative source In frame. Blank or fractional ranges cannot be previewed, saved or assembled.',!valid);
    }
    async function inspect(){
      if(disposed||busy||!source||!validRanges())return;const operation=++serial;busy=true;controls();message('Checking source ranges and content identities…');
      try{current();const result=await bridge.request(endpoint('review'),{method:'POST',body:payload()});if(disposed||operation!==serial)return;current();
        if(!Array.isArray(result?.plan?.shots)||!Array.isArray(result.shots))throw Error('The shot-plan review returned invalid data.');
        plan=clone(result.plan);report=clone(result);selected=bindingMap(result.bindings||selected);renderRows();
        message(result.ready?'Every planned shot has a valid source range. Review the takes, then assemble the cut.':`${result.shots.filter(row=>row.ready).length} of ${result.shots.length} shots ready. Bind missing footage or save the plan to continue later.`,!result.ready);
      }catch(error){if(!disposed&&operation===serial){report=null;message(error.message||'The production plan could not be checked.',true);}}
      finally{if(!disposed&&operation===serial){busy=false;controls();}}
    }
    async function readFile(){
      if(busy||disposed)return;const file=$('[data-production-file]').files[0];if(!file)return;const operation=++serial;busy=true;controls();releaseDownload();stopPreview();
      try{current();if(!/\.json$/i.test(file.name)||file.size>2*1024*1024)throw Error('Choose a shotlist JSON file up to 2 MiB.');
        const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());if(disposed||operation!==serial)return;current();
        source=text;plan=null;selected=bindingMap();report=null;renderRows();message('Reading selected shot plan…');
      }catch(error){if(!disposed&&operation===serial){source='';plan=null;report=null;renderRows();message(error.message||'The file could not be read.',true);}}
      finally{if(!disposed&&operation===serial){busy=false;controls();}}
      if(!disposed&&operation===serial&&source)await inspect();
    }
    function matchNames(){
      if(busy||!plan)return;current();let count=0,ambiguous=0;
      for(const shot of plan.shots){const matches=(snapshot.assets||[]).filter(asset=>asset.kind==='video'&&asset.name===shot.filename);if(matches.length===1){selected[shot.id]={asset_id:matches[0].id,in_frame:selected[shot.id]?.in_frame||0,allow_name_mismatch:false};count++;}else if(matches.length>1)ambiguous++;}
      stopPreview();report=null;renderRows();message(`${count} exact imported filenames selected${ambiguous?`; ${ambiguous} names are ambiguous and need a manual choice`:''}. Check the selected takes before assembly.`);
    }
    async function apply(action){
      if(busy||!plan||!validRanges()||(action==='conform'&&!report?.ready))return;const operation=++serial;busy=true;controls();message(action==='conform'?'Building the complete editable cut…':'Keeping the plan and source selections in this project…');
      try{current();const body=payload();if(action==='conform')body.replace_format=$('[data-production-format]').checked;
        const result=await bridge.request(endpoint(action==='conform'?'conform':'plan'),{method:'POST',body});if(disposed||operation!==serial)return;current();
        if(result?.project?.id!==snapshot.id)throw Error('The production operation returned a different project.');
        const accepted=await bridge.onApply(clone(result.project),clone(expected),{action:action==='conform'?'conform':'save_plan',replaceTimeline:action==='conform'});
        if(disposed||operation!==serial)return;if(accepted===false)throw Error('The project changed before the production edit could be applied.');
        close();bridge.notify?.(action==='conform'?'Planned cut assembled from selected footage. Undo restores the previous edit.':'Production plan and source selections kept in the project. Save the project to commit them.');
      }catch(error){if(!disposed&&operation===serial)message(error.message||'The production edit could not be applied.',true);}
      finally{if(!disposed&&operation===serial){busy=false;controls();}}
    }
    async function exportRequirements(){
      if(disposed||busy||!plan)return;const operation=++serial;busy=true;controls();releaseDownload();
      try{current();const project=clone(snapshot);project.settings={...(project.settings||{}),production:{version:1,plan:clone(plan)}};
        const result=await bridge.request(endpoint('export'),{method:'POST',body:{project}});if(disposed||operation!==serial)return;current();
        if(!result?.document||!Array.isArray(result.document.shots))throw Error('No portable shot requirements were returned.');
        const prefix=`/api/projects/${encodeURIComponent(snapshot.id)}/exports/`;
        if(typeof result.url!=='string'||!result.url.startsWith(prefix)||!/^[a-f0-9]{32}-shot-plan\.json\?download=1$/.test(result.url.slice(prefix.length)))throw Error('The export did not return a project-owned shot-plan download.');
        const link=$('[data-production-download]');link.href=result.url;link.download=result.filename||'CINEMATICUM-shot-plan.json';link.hidden=false;message('Shot requirements are ready to download. Media and project-specific bindings remain in this project.');
      }catch(error){if(!disposed&&operation===serial)message(error.message||'The plan could not be exported.',true);}
      finally{if(!disposed&&operation===serial){busy=false;controls();}}
    }
    function preview(index){
      if(busy||!plan)return;current();const shot=plan.shots[index],binding=shot&&selected[shot.id],asset=binding&&(snapshot.assets||[]).find(item=>item.id===binding.asset_id&&item.kind==='video');if(!asset||!validRange(binding))return;
      stopPreview();const video=$('[data-production-video]');previewRange={start:binding.in_frame/plan.fps,end:(binding.in_frame+shot.duration_frames)/plan.fps};
      $('[data-production-preview-label]').textContent=`${shot.id} · ${asset.name} · source frames ${binding.in_frame}–${binding.in_frame+shot.duration_frames}`;
      video.src=`/api/projects/${encodeURIComponent(snapshot.id)}/media/${encodeURIComponent(asset.id)}`;$('[data-production-preview]').hidden=false;
      $('[data-production-preview]').scrollIntoView({block:'nearest'});
    }
    function close(){serial++;busy=false;stopPreview();releaseDownload();dialog.close();controls();}
    function open(){
      if(disposed)return;const project=bridge.getProject?.();if(!project)throw Error('Open a project before assembling a production plan.');
      serial++;busy=false;snapshot=clone(project);expected=context();source='';plan=null;selected=bindingMap();report=null;stopPreview();releaseDownload();$('[data-production-file]').value='';$('[data-production-format]').checked=false;
      $('[data-production-project]').textContent=snapshot.name;$('[data-production-summary]').textContent='Choose a shotlist JSON file, up to 2 MiB.';message('');
      const saved=snapshot.settings?.production;if(saved?.plan&&typeof saved.plan==='object'){source=JSON.stringify(saved.plan);selected=bindingMap(saved.bindings);}
      renderRows();controls();if(!dialog.open)dialog.showModal();if(source)void inspect();
    }
    listen($('[data-production-close]'),'click',close);listen(dialog,'cancel',event=>{event.preventDefault();close();});listen(dialog,'keydown',event=>event.stopPropagation());
    listen($('[data-production-file]'),'change',readFile);listen($('[data-production-match]'),'click',()=>{try{matchNames();}catch(error){message(error.message,true);}});
    listen($('[data-production-shots]'),'change',event=>{if(!busy)updateSelection(event.target);});
    listen($('[data-production-shots]'),'click',event=>{const button=event.target.closest('[data-production-preview-shot]');if(button)try{preview(Number(button.dataset.productionPreviewShot));}catch(error){message(error.message,true);}});
    listen($('[data-production-format]'),'change',controls);listen($('[data-production-review]'),'click',inspect);listen($('[data-production-save]'),'click',()=>apply('plan'));listen($('[data-production-conform]'),'click',()=>apply('conform'));listen($('[data-production-export]'),'click',exportRequirements);
    listen($('[data-production-stop-preview]'),'click',stopPreview);
    listen($('[data-production-video]'),'loadedmetadata',()=>{if(previewRange)$('[data-production-video]').currentTime=previewRange.start;});
    listen($('[data-production-video]'),'play',()=>{const video=$('[data-production-video]');if(previewRange&&(video.currentTime<previewRange.start||video.currentTime>=previewRange.end))video.currentTime=previewRange.start;});
    listen($('[data-production-video]'),'timeupdate',()=>{const video=$('[data-production-video]');if(previewRange&&!video.paused&&video.currentTime>=previewRange.end)video.pause();});
    listen($('[data-production-video]'),'error',()=>{if(previewRange)message('This source codec cannot play in the interactive viewer. The backend still validates it; use rendered timeline playback after assembly.',true);});
    return {open,close,destroy(){disposed=true;serial++;stopPreview();releaseDownload();for(const remove of removers)remove();dialog.remove();style.remove();}};
  }
  window.CinematicumProduction={mount};
})();

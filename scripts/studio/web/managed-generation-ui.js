/* A cancellable, app-owned video engine. Installation and model execution are
   separate states; readiness is always read from the live Store. */
(() => {
  'use strict';
  const defaults={width:480,height:272,length:17,steps:20,cfg:6,fps:16};
  const bytes=value=>Number.isFinite(value)?`${(value/1e9).toFixed(2)} GB`:'Unknown';
  function mount(host,bridge){
    const dialog=document.createElement('dialog');dialog.id='managed-generation-dialog';dialog.className='cinematicum-generation';
    dialog.innerHTML=`<style>
      .cinematicum-generation{box-sizing:border-box;width:min(820px,96vw);max-height:92vh;padding:0;overflow:hidden;color:#e6ebf2;background:#151a20;border:1px solid #485260;border-radius:12px;font:13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 24px 80px #000a}
      .cinematicum-generation[open]{display:flex;flex-direction:column}.cinematicum-generation::backdrop{background:#05080cb8}
      .cinematicum-generation header,.cinematicum-generation footer{display:flex;flex:0 0 auto;gap:12px;align-items:center;justify-content:space-between;padding:16px 20px;background:#202730}
      .cinematicum-generation h2,.cinematicum-generation h3,.cinematicum-generation p{margin:0}.cinematicum-generation h2{font-size:18px}.cinematicum-generation h3{font-size:13px;color:#c4d5e6}
      .cinematicum-generation .generation-body{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;padding:20px;display:grid;grid-template-columns:minmax(0,1fr) minmax(230px,.85fr);gap:24px}
      .cinematicum-generation section{display:grid;align-content:start;gap:14px}.cinematicum-generation .generation-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.cinematicum-generation .generation-buttons{display:flex;gap:8px;flex-wrap:wrap}
      .cinematicum-generation label{display:grid;gap:6px;color:#b8c3d1}.cinematicum-generation input,.cinematicum-generation select{box-sizing:border-box;min-width:0;width:100%;padding:8px;background:#0e1319;color:#e9eff7;border:1px solid #3f4c5d;border-radius:6px;font:inherit}
      .cinematicum-generation button{padding:8px 12px;color:#e7edf5;background:#303d4b;border:1px solid #506479;border-radius:6px;font:inherit;cursor:pointer}.cinematicum-generation button:disabled{opacity:.4;cursor:default}.cinematicum-generation .generation-primary{background:#2d6f80;border-color:#5cabb9}.cinematicum-generation [hidden]{display:none!important}
      .cinematicum-generation .generation-note{font-size:12px;color:#a3b0bf}.cinematicum-generation .generation-phase{color:#b2d9e5;min-height:20px;overflow-wrap:anywhere}.cinematicum-generation .generation-error{color:#ffab9a;overflow-wrap:anywhere}.cinematicum-generation .generation-badge{display:inline-block;justify-self:start;padding:4px 9px;border:1px solid #4e6177;border-radius:20px;color:#c7d7ea}.cinematicum-generation .generation-badge.ready{color:#a7ebd0;border-color:#468a71}
      .cinematicum-generation progress{width:100%;height:12px;accent-color:#5bb6c5}.cinematicum-generation .generation-models{margin:0;padding:0;list-style:none;display:grid;gap:8px}.cinematicum-generation .generation-models li{display:grid;gap:2px;font-size:11px;color:#8fa2b8;overflow-wrap:anywhere}.cinematicum-generation .generation-models span:first-child{color:#c3cedb}.cinematicum-generation details{border-top:1px solid #344252;padding-top:10px}.cinematicum-generation summary{color:#adc0d4;cursor:pointer}.cinematicum-generation details>div{display:grid;gap:10px;padding-top:10px}.cinematicum-generation .generation-footer-note{flex:1;min-width:0;font-size:12px;color:#9eb0c3}
      @media(max-width:630px){.cinematicum-generation .generation-body{grid-template-columns:1fr;gap:25px}.cinematicum-generation header,.cinematicum-generation footer{padding:13px 16px}.cinematicum-generation .generation-body{padding:16px}}
    </style>
    <header><div><h2>Local video generation</h2><p class="generation-note">Wan 2.1 · 1.3B · text to video</p></div><button type="button" data-generation-close aria-label="Close local generation">Close</button></header>
    <div class="generation-body">
      <section aria-label="Local generation engine">
        <span class="generation-badge" data-generation-state>Checking installation</span>
        <p class="generation-phase" data-generation-phase role="status" aria-live="polite">Reading the local runtime status…</p>
        <progress data-generation-progress max="1" value="0" aria-label="Generation setup progress" hidden></progress>
        <p class="generation-note" data-generation-progress-detail hidden></p>
        <p class="generation-error" data-generation-error role="alert" hidden></p>
        <div class="generation-buttons"><button type="button" class="generation-primary" data-generation-setup>Install local engine</button><button type="button" data-generation-start>Start engine</button><button type="button" data-generation-stop>Stop engine</button><button type="button" data-generation-cancel hidden>Cancel operation</button><button type="button" data-generation-refresh>Refresh</button></div>
        <p class="generation-note" data-generation-space></p>
        <p class="generation-note">Setup keeps verified downloads so interrupted transfers can resume. You can close this window while setup continues.</p>
        <details><summary>Installed source and models</summary><div><p class="generation-note" data-generation-source></p><ul class="generation-models" data-generation-models></ul><p class="generation-note">Starting verifies the source and model hashes, checks the GPU and encoder, and validates the live workflow. A generated take is accepted only after the finished video passes its media checks.</p></div></details>
      </section>
      <section aria-label="Generated shot settings">
        <h3>Shot settings</h3>
        <label>Canvas<select data-generation-canvas><option value="480x272">480 × 272 · landscape</option><option value="272x480">272 × 480 · portrait</option><option value="384x384">384 × 384 · square</option><option value="832x480">832 × 480 · landscape</option><option value="custom">Custom dimensions</option></select></label>
        <div class="generation-row" data-generation-custom hidden><label>Width<input type="number" data-generation-width min="192" max="832" step="16" value="480"></label><label>Height<input type="number" data-generation-height min="128" max="480" step="16" value="272"></label></div>
        <div class="generation-row"><label>Frames<input type="number" data-generation-length min="9" max="81" step="4" value="17"></label><label>Frames per second<input type="number" data-generation-fps min="1" max="60" step="1" value="16"></label><label>Sampling steps<input type="number" data-generation-steps min="4" max="50" step="1" value="20"></label><label>Prompt guidance<input type="number" data-generation-cfg min="1" max="12" step="0.5" value="6"></label></div>
        <p class="generation-note" data-generation-duration></p>
        <p class="generation-note">Larger frames, longer clips and more sampling steps need more memory and time. The first take loads the models; its speed and quality depend on this Mac.</p>
        <button type="button" class="generation-primary" data-generation-workflow>Use these settings in this project</button>
        <p class="generation-phase" data-generation-workflow-status aria-live="polite"></p>
        <p class="generation-note">Then enter the shot prompt and seed in Generate. The completed video is added to the project for editing.</p>
      </section>
    </div><footer><p class="generation-footer-note" data-generation-footer>Local generation is managed by this CINEMATICUM session.</p><button type="button" data-generation-close>Done</button></footer>`;
    host.append(dialog);
    const $=selector=>dialog.querySelector(selector);
    let snapshot=null,busy=null,cancelRequested=false,cancelSending=false,disposed=false,poll=null,requesting=false,epoch=0,error='',statusError='',savedOptions=null;
    const fields=['width','height','length','steps','cfg','fps'];
    function options(){const result={};for(const name of fields)result[name]=Number($(`[data-generation-${name}]`).value);return result;}
    function validOptions(){
      const value=options();
      return fields.every(name=>Number.isFinite(value[name]))&&Number.isInteger(value.width)&&value.width>=192&&value.width<=832&&value.width%16===0
        &&Number.isInteger(value.height)&&value.height>=128&&value.height<=480&&value.height%16===0&&value.width*value.height<=832*480
        &&Number.isInteger(value.length)&&value.length>=9&&value.length<=81&&value.length%4===1
        &&Number.isInteger(value.steps)&&value.steps>=4&&value.steps<=50&&value.cfg>=1&&value.cfg<=12&&value.fps>=1&&value.fps<=60;
    }
    function activeJob(){const job=bridge.getJob?.();return job&&['queued','running'].includes(String(job.state).toLowerCase())?job:null;}
    function runtimeJob(){const job=activeJob();return job&&['generation-setup','generation-start'].includes(job.kind)?job:null;}
    function render(){
      if(disposed)return;
      const current=snapshot||{},job=activeJob(),ownedJob=runtimeJob(),working=!!(busy||current.operation||ownedJob),blocked=working||!!job;
      const phase=$('[data-generation-phase]'),badge=$('[data-generation-state]');
      badge.textContent=current.ready?'Engine ready':current.operation==='install'||busy==='setup'?'Installing':current.operation==='start'||busy==='start'?'Starting':current.running?'Engine starting':current.installed?'Installed · stopped':snapshot?'Not installed':'Checking installation';
      badge.classList.toggle('ready',!!current.ready);
      phase.textContent=current.detail||(!snapshot?'Reading the local runtime status…':current.ready?'The local engine is ready for a generated take.':current.installed?'Start the local engine, then apply the shot settings.':'Install the local engine and its three model files.');
      if(busy==='workflow')phase.textContent='Saving this project’s shot workflow…';
      if(cancelRequested)phase.textContent='Cancelling the owned operation…';
      const problem=error||statusError||current.reason||'';const alert=$('[data-generation-error]');alert.textContent=problem;alert.hidden=!problem;
      const progress=$('[data-generation-progress]');progress.hidden=!working||busy==='workflow';progress.value=Math.max(0,Math.min(1,Number(current.progress)||Number(ownedJob?.progress)||0));
      const progressDetail=$('[data-generation-progress-detail]');progressDetail.hidden=progress.hidden;progressDetail.textContent=`${Math.round(progress.value*100)}%${current.downloaded_bytes>0&&(!current.operation||current.operation==='install')?` · ${bytes(current.downloaded_bytes)} of ${bytes(current.download_bytes)}`:''}`;
      const install=$('[data-generation-setup]');install.textContent=current.installed?'Verify installation':'Install local engine';install.disabled=!snapshot||!current.supported||blocked||current.running;
      $('[data-generation-start]').disabled=!current.installed||!current.supported||blocked||current.running;
      $('[data-generation-stop]').disabled=!current.running||blocked;
      $('[data-generation-refresh]').disabled=requesting;
      const cancel=$('[data-generation-cancel]');cancel.hidden=!bridge.cancel||!(ownedJob||busy==='setup'||busy==='start');cancel.disabled=cancelSending||!ownedJob;cancel.textContent=cancelRequested?'Retry cancellation':'Cancel operation';
      for(const field of dialog.querySelectorAll('input,select'))field.disabled=!!busy;
      $('[data-generation-workflow]').disabled=!validOptions()||blocked;
      $('[data-generation-space]').textContent=snapshot?`${bytes(current.download_bytes)} total download · ${bytes(current.free_disk_bytes)} disk space available.${!current.installed?` First installation needs ${bytes(current.first_install_required_bytes)} free, including working space.`:''}`:'';
      $('[data-generation-source]').textContent=snapshot?`Engine ${current.source_version||''} · pinned model and dependency files${current.installed?' · installation receipt present':''}.`:'';
      const models=$('[data-generation-models]');
      if(models.dataset.identity!==String(current.runtime_id||'')){
        models.replaceChildren();for(const model of current.models||[]){const row=document.createElement('li'),name=document.createElement('span'),size=document.createElement('span');name.textContent=model.name;size.textContent=bytes(model.bytes);row.append(name,size);models.append(row);}models.dataset.identity=String(current.runtime_id||'');
      }
      const value=options();$('[data-generation-duration]').textContent=validOptions()?`${value.width} × ${value.height} · ${value.length} frames · ${(value.length/value.fps).toFixed(2)} seconds. Frames must be 4n + 1.`:'Use dimensions divisible by 16, and 9–81 frames in steps of four.';
      const unchanged=savedOptions&&JSON.stringify(savedOptions)===JSON.stringify(value);
      $('[data-generation-workflow-status]').textContent=unchanged?'These settings are saved in this project.':savedOptions?'Settings changed. Apply them to update this project.':'';
      $('[data-generation-footer]').textContent=ownedJob?`Job ${ownedJob.state}. Closing this window keeps the operation running.`:current.ready?'Use Generate to create a take with this local engine.':'Local generation is managed by this CINEMATICUM session.';
    }
    async function refresh(){
      if(disposed||requesting)return;
      const ticket=epoch;requesting=true;render();
      try{const result=await bridge.getStatus();if(disposed||ticket!==epoch)return;snapshot=result;statusError='';}
      catch(failure){if(!disposed&&ticket===epoch)statusError=failure?.message||String(failure);}
      finally{requesting=false;if(!disposed&&ticket===epoch)render();}
    }
    async function act(name){
      if(disposed||busy)return;
      busy=name;cancelRequested=false;error='';render();
      try{
        if(name==='workflow'){
          if(!validOptions())throw Error('Choose valid Wan frame dimensions and shot settings.');
          const chosen=options();await bridge.useWorkflow(chosen);savedOptions=chosen;
        }else{
          const result=await bridge[name]();if(result&&typeof result==='object'&&'installed' in result)snapshot=result;
        }
      }catch(failure){
        error=cancelRequested?'Operation cancelled. Retry setup to resume its owned downloads.':failure?.message||String(failure);
        if(!cancelRequested)bridge.onError?.(failure);
      }finally{busy=null;cancelRequested=false;render();await refresh();}
    }
    async function cancel(){
      if(cancelSending||!runtimeJob())return;
      cancelRequested=true;cancelSending=true;render();
      try{await bridge.cancel();}catch(failure){cancelRequested=false;error=failure?.message||String(failure);bridge.onError?.(failure);}
      finally{cancelSending=false;render();}
    }
    function close(){
      epoch++;if(poll!==null){clearInterval(poll);poll=null;}
      if(dialog.open)dialog.close();
    }
    function open(){
      if(disposed)return;if(!dialog.open){epoch++;savedOptions=null;error='';dialog.showModal();}
      if(poll===null)poll=setInterval(()=>{render();void refresh();},1200);
      render();void refresh();
    }
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.addEventListener('click',event=>{
      const control=event.target.closest('button');if(!control||control.disabled)return;
      if(control.hasAttribute('data-generation-close'))close();
      else if(control.hasAttribute('data-generation-refresh'))void refresh();
      else if(control.hasAttribute('data-generation-cancel'))void cancel();
      else for(const action of ['setup','start','stop','workflow'])if(control.hasAttribute('data-generation-'+action)){void act(action);break;}
    });
    $('[data-generation-canvas]').addEventListener('change',()=>{
      const selected=$('[data-generation-canvas]').value;const custom=selected==='custom';$('[data-generation-custom]').hidden=!custom;
      if(!custom){const [width,height]=selected.split('x').map(Number);$('[data-generation-width]').value=width;$('[data-generation-height]').value=height;}render();
    });
    for(const name of fields)$(`[data-generation-${name}]`).addEventListener('input',render);
    for(const name of fields)$(`[data-generation-${name}]`).value=defaults[name];
    render();
    return {open,close,refresh,destroy(){disposed=true;close();dialog.remove();}};
  }
  window.CinematicumManagedGeneration={mount};
})();

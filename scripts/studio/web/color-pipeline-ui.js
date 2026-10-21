/* CINEMATICUM's colour editor. Every enabled operation changes the shared
   pixel renderer; LUT files are parsed and owned by the project server. */
(() => {
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  const whites={D65:[.3127,.329],D60:[.32168,.33767],D50:[.3457,.3585],A:[.44757,.40745]};
  const presets={
    rec709:{label:'Rec.709 video',transfer:'rec709',primaries:'rec709',white:'D65'},
    srgb:{label:'sRGB image',transfer:'srgb',primaries:'rec709',white:'D65'},
    linear:{label:'Linear Rec.709',transfer:'linear',primaries:'rec709',white:'D65'},
    logc3:{label:'ARRI LogC3 · EI 800 · Wide Gamut 3',transfer:'logc3_ei800',primaries:'arri_wide_gamut3',white:'D65'},
    acescg:{label:'ACEScg · linear AP1',transfer:'linear',primaries:'acescg',white:'D60'},
    rec2020:{label:'Linear Rec.2020',transfer:'linear',primaries:'rec2020',white:'D65'}
  };
  const defaults=()=>({version:1,enabled:true,input_transfer:'rec709',input_primaries:'rec709',source_white:[...whites.D65],target_white:[...whites.D65],lut:null});
  function mount(host,bridge) {
    const dialog=document.createElement('dialog');dialog.className='cinematicum-color-pipeline';
    dialog.innerHTML=`<style>
      .cinematicum-color-pipeline{box-sizing:border-box;width:min(760px,94vw);max-height:90vh;padding:0;overflow:hidden;color:#e6e8ed;background:#171a20;border:1px solid #48505d;border-radius:12px;font:13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 24px 80px #0009}
      .cinematicum-color-pipeline[open]{display:flex;flex-direction:column}
      .cinematicum-color-pipeline::backdrop{background:#05080caf}
      .cinematicum-color-pipeline header,.cinematicum-color-pipeline footer{display:flex;flex:0 0 auto;gap:12px;align-items:center;justify-content:space-between;padding:16px 20px;background:#1d222a}
      .cinematicum-color-pipeline h2,.cinematicum-color-pipeline h3,.cinematicum-color-pipeline p{margin:0}
      .cinematicum-color-pipeline h2{font-size:17px}.cinematicum-color-pipeline h3{font-size:12px;color:#a7bbd5;letter-spacing:.06em;text-transform:uppercase;margin-bottom:12px}
      .cinematicum-color-pipeline .color-body{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;padding:20px;display:grid;gap:18px}.cinematicum-color-pipeline .color-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
      .cinematicum-color-pipeline label{display:grid;gap:6px;color:#b4bdca}.cinematicum-color-pipeline select,.cinematicum-color-pipeline input[type=number]{min-width:0;width:100%;box-sizing:border-box;padding:8px;background:#10141a;color:#e5eaf2;border:1px solid #3c4451;border-radius:6px;font:inherit}
      .cinematicum-color-pipeline .color-xy{display:grid;grid-template-columns:1fr 1fr;gap:8px}.cinematicum-color-pipeline .color-note{font-size:12px;color:#919eaf}.cinematicum-color-pipeline .color-enable{display:flex;gap:8px;align-items:center}
      .cinematicum-color-pipeline button{padding:8px 12px;color:#e7edf5;background:#303846;border:1px solid #505d70;border-radius:6px;cursor:pointer}.cinematicum-color-pipeline button:disabled{opacity:.45;cursor:default}.cinematicum-color-pipeline .color-primary{background:#3569ab;border-color:#568bcd}
      .cinematicum-color-pipeline .color-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.cinematicum-color-pipeline .color-status{min-height:18px;color:#a8c6ee}.cinematicum-color-pipeline .color-status.error{color:#ffad9e}.cinematicum-color-pipeline .color-detail{padding:10px;background:#10141a;border-radius:6px;white-space:pre-wrap;font-size:12px;color:#a9b9cd;overflow-wrap:anywhere}
      @media(max-width:600px){.cinematicum-color-pipeline .color-row{grid-template-columns:1fr}}
    </style>
    <header><div><h2>Color pipeline</h2><p class="color-note" data-color-clip></p></div><button type="button" data-color-close aria-label="Close color pipeline">Close</button></header>
    <div class="color-body">
      <label class="color-enable"><input type="checkbox" data-color-enabled> Enable this clip's color pipeline</label>
      <section><h3>Input interpretation</h3><label>Source preset<select data-color-preset></select></label>
        <div class="color-row" style="margin-top:12px"><label>Transfer function<select data-color-transfer><option value="rec709">Rec.709 OETF</option><option value="srgb">sRGB</option><option value="linear">Linear</option><option value="logc3_ei800">LogC3 · SUP 3.x · EI 800</option></select></label>
        <label>RGB primaries<select data-color-primaries><option value="rec709">Rec.709 / sRGB</option><option value="rec2020">Rec.2020</option><option value="acescg">ACEScg / AP1 · D60</option><option value="arri_wide_gamut3">ARRI Wide Gamut 3</option></select></label></div>
      </section>
      <section><h3>White balance · Bradford adaptation</h3><div class="color-row">
        <div><label>Source illuminant<select data-color-source-preset></select></label><div class="color-xy" style="margin-top:8px"><label>CIE x<input type="number" min="0.001001" max="0.998" step="0.00001" data-color-source-x></label><label>CIE y<input type="number" min="0.001001" max="0.998" step="0.00001" data-color-source-y></label></div></div>
        <div><label>Target illuminant<select data-color-target-preset></select></label><div class="color-xy" style="margin-top:8px"><label>CIE x<input type="number" min="0.001001" max="0.998" step="0.00001" data-color-target-x></label><label>CIE y<input type="number" min="0.001001" max="0.998" step="0.00001" data-color-target-y></label></div></div>
      </div></section>
      <section><h3>Creative LUT · after the input transform</h3><div class="color-row"><label>Project LUT<select data-color-lut><option value="">None</option></select></label><label>Interpolation<select data-color-interpolation></select></label></div>
        <div class="color-tools" style="margin-top:10px"><button type="button" data-color-import>Import .cube</button><input type="file" accept=".cube,text/plain" data-color-file hidden><button type="button" data-color-remove>Remove LUT</button><span class="color-note">1D up to 65,536 · 3D up to 65³</span></div>
        <p data-color-lut-detail class="color-detail" style="margin-top:10px">No creative LUT selected.</p>
      </section>
      <p class="color-note">Processing: decode input → adapt white and primaries in float RGB → encode Rec.709 → LUT → clip effects. Preview and export use the same pipeline. Output remains SDR; highlights and colours outside the output range are clipped by the SDR compositor. ACEScg here is a primary conversion without an ACES display transform.</p>
      <p data-color-status role="status" aria-live="polite" class="color-status"></p>
    </div><footer><button type="button" data-color-reset>Reset input and LUT</button><button type="button" class="color-primary" data-color-apply>Apply to clip</button></footer>`;
    host.append(dialog);
    const $=selector=>dialog.querySelector(selector);
    const option=(select,value,label)=>{const node=document.createElement('option');node.value=value;node.textContent=label;select.append(node);};
    for(const [key,preset] of Object.entries(presets))option($('[data-color-preset]'),key,preset.label);
    option($('[data-color-preset]'),'custom','Custom input interpretation');
    for(const side of ['source','target']){const select=$(`[data-color-${side}-preset]`);for(const key of Object.keys(whites))option(select,key,key==='A'?'Illuminant A · tungsten':key);option(select,'custom','Custom xy');}
    let disposed=false,serial=0,busy=false,context=null,candidate=defaults(),luts=[];
    const endpoint=action=>`/api/projects/${encodeURIComponent(context.projectId)}/${action}`;
    const status=(message,error=false)=>{const node=$('[data-color-status]');node.textContent=message;node.classList.toggle('error',error);};
    const contextValid=()=>{const now=bridge.getContext();return context&&now.projectId===context.projectId&&now.revision===context.revision&&now.clipId===context.clipId;};
    const ensureContext=()=>{if(!contextValid())throw Error('The project or selected clip changed. Reopen Color pipeline for the current edit.');};
    const active=token=>!disposed&&dialog.open&&token===serial;
    function setBusy(value){busy=value;for(const control of dialog.querySelectorAll('button,input,select'))if(!control.hasAttribute('data-color-close'))control.disabled=value;updateLUT();}
    function setWhite(side,value){$(`[data-color-${side}-x]`).value=String(value[0]);$(`[data-color-${side}-y]`).value=String(value[1]);$(`[data-color-${side}-preset]`).value=Object.keys(whites).find(key=>whites[key].every((v,i)=>Math.abs(v-value[i])<1e-7))||'custom';}
    function chosenLUT(){return luts.find(lut=>lut.sha256===$('[data-color-lut]').value);}
    function updateLUT(){
      const lut=chosenLUT(),select=$('[data-color-interpolation]'),old=select.value;
      select.replaceChildren();
      for(const mode of lut?.dimension===1?['linear','nearest']:['tetrahedral','trilinear','nearest'])option(select,mode,mode[0].toUpperCase()+mode.slice(1));
      select.value=[...select.options].some(o=>o.value===old)?old:(lut?.dimension===1?'linear':'tetrahedral');
      select.disabled=busy||!lut;$('[data-color-remove]').disabled=busy||!$('[data-color-lut]').value;
      $('[data-color-lut-detail]').textContent=lut?`${lut.title}\n${lut.shaper_size?'1D shaper '+lut.shaper_size+' → ':''}${lut.dimension}D · ${lut.size}${lut.dimension===3?'³':''} · ${lut.rows.toLocaleString()} rows\n${lut.shaper_size?'Shaper domain: ['+lut.shaper_domain_min.join(', ')+'] → ['+lut.shaper_domain_max.join(', ')+'] · linear\n':''}Domain: [${lut.domain_min.join(', ')}] → [${lut.domain_max.join(', ')}]\nProject LUT: ${lut.sha256.slice(0,12)}`:($('[data-color-lut]').value?'This LUT is missing from the current project. Import the same file or remove the reference.':'No creative LUT selected.');
      $('[data-color-apply]').disabled=busy||Boolean($('[data-color-lut]').value&&!lut);
    }
    function fillLUTs(){
      const select=$('[data-color-lut]'),selected=candidate.lut?.sha256||'';
      select.replaceChildren();option(select,'','None');for(const lut of luts)option(select,lut.sha256,`${lut.title} · ${lut.shaper_size?'1D + ':''}${lut.dimension}D ${lut.size}${lut.dimension===3?'³':''}`);
      if(selected&&!luts.some(lut=>lut.sha256===selected))option(select,selected,'Missing project LUT · '+selected.slice(0,12));
      select.value=selected;updateLUT();if(candidate.lut?.sha256===selected&&candidate.lut.interpolation)$('[data-color-interpolation]').value=candidate.lut.interpolation;
    }
    function fill(){
      $('[data-color-enabled]').checked=candidate.enabled!==false;
      $('[data-color-transfer]').value=candidate.input_transfer;$('[data-color-primaries]').value=candidate.input_primaries;
      $('[data-color-preset]').value=Object.keys(presets).find(key=>presets[key].transfer===candidate.input_transfer&&presets[key].primaries===candidate.input_primaries)||'custom';
      setWhite('source',candidate.source_white);setWhite('target',candidate.target_white);fillLUTs();
    }
    function read(){
      const p=defaults();p.enabled=$('[data-color-enabled]').checked;p.input_transfer=$('[data-color-transfer]').value;p.input_primaries=$('[data-color-primaries]').value;
      for(const side of ['source','target']){const x=Number($(`[data-color-${side}-x]`).value),y=Number($(`[data-color-${side}-y]`).value);if(!Number.isFinite(x)||!Number.isFinite(y)||x<=.001||y<=.001||x+y>=.999)throw Error(`${side==='source'?'Source':'Target'} white requires positive CIE x/y with x + y below 0.999.`);p[side+'_white']=[x,y];}
      const cone=([x,y])=>{const xyz=[x/y,1,(1-x-y)/y];return [[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]].map(row=>row.reduce((sum,v,i)=>sum+v*xyz[i],0));};
      const a=cone(p.source_white),b=cone(p.target_white);if([...a,...b].some(v=>v<=.000001)||a.some((v,i)=>b[i]/v<1/64||b[i]/v>64))throw Error('The whitepoints are outside the stable Bradford adaptation range.');
      const lut=chosenLUT();if($('[data-color-lut]').value&&!lut)throw Error('The selected LUT is missing from this project.');
      p.lut=lut?{sha256:lut.sha256,interpolation:$('[data-color-interpolation]').value}:null;return p;
    }
    function close(){serial++;dialog.close();busy=false;}
    $('[data-color-close]').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    $('[data-color-preset]').onchange=()=>{const preset=presets[$('[data-color-preset]').value];if(!preset)return;$('[data-color-transfer]').value=preset.transfer;$('[data-color-primaries]').value=preset.primaries;setWhite('source',whites[preset.white]);setWhite('target',whites.D65);};
    $('[data-color-transfer]').onchange=()=>{$('[data-color-preset]').value='custom';};
    $('[data-color-primaries]').onchange=()=>{$('[data-color-preset]').value='custom';setWhite('source',whites[$('[data-color-primaries]').value==='acescg'?'D60':'D65']);};
    for(const side of ['source','target']){
      $(`[data-color-${side}-preset]`).onchange=()=>{const value=whites[$(`[data-color-${side}-preset]`).value];if(value)setWhite(side,value);};
      for(const axis of ['x','y'])$(`[data-color-${side}-${axis}]`).oninput=()=>{$(`[data-color-${side}-preset]`).value='custom';};
    }
    $('[data-color-lut]').onchange=()=>{candidate.lut=null;updateLUT();};
    $('[data-color-remove]').onclick=()=>{candidate.lut=null;$('[data-color-lut]').value='';updateLUT();};
    $('[data-color-reset]').onclick=()=>{candidate=defaults();$('[data-color-lut]').value='';fill();status('Reset is ready. Apply to change the clip.');};
    $('[data-color-import]').onclick=()=>{$('[data-color-file]').click();};
    $('[data-color-file]').onchange=async event=>{
      const file=event.target.files?.[0];event.target.value='';if(!file||busy)return;const token=serial;
      try{ensureContext();if(!/\.cube$/i.test(file.name))throw Error('Choose a .cube LUT file.');if(file.size>24*1024*1024)throw Error('The LUT file exceeds the 24 MiB limit.');setBusy(true);status('Parsing and importing '+file.name+'…');const text=await file.text();if(!active(token))return;ensureContext();const response=await bridge.request(endpoint('color-lut-import'),{method:'POST',body:{text}});if(!active(token))return;ensureContext();if(!response.lut?.sha256)throw Error('The LUT import did not return a verified project identity.');luts=luts.filter(item=>item.sha256!==response.lut.sha256);luts.push(response.lut);candidate.lut={sha256:response.lut.sha256,interpolation:response.lut.dimension===1?'linear':'tetrahedral'};fillLUTs();status('Imported '+response.lut.title+'. Apply to use it on this clip.');}
      catch(error){if(active(token))status(error.message,true);}finally{if(active(token))setBusy(false);}
    };
    $('[data-color-apply]').onclick=async()=>{
      if(busy)return;const token=serial;
      try{ensureContext();const value=read();setBusy(true);const result=await bridge.onApply(clone(value),clone(context));if(!active(token))return;if(result===false)throw Error('The color pipeline could not be applied to the selected clip.');close();bridge.notify?.('Color pipeline applied. Preview and export use the same transform.');}
      catch(error){if(active(token)){status(error.message,true);setBusy(false);}}
    };
    async function open(){
      const clip=bridge.getClip();if(!clip||clip.track<0){bridge.notify?.('Select a picture clip to edit its color pipeline.',true);return;}
      context=clone(bridge.getContext());context.clipId=context.clipId||clip.id;
      candidate={...defaults(),...clone(clip.color_pipeline||{})};luts=[];const token=++serial;
      $('[data-color-clip]').textContent=clip.name||clip.id;fill();if(!dialog.open)dialog.showModal();setBusy(true);status('Loading this project’s LUTs…');
      try{const response=await bridge.request(endpoint('color-luts'));if(!active(token))return;ensureContext();luts=Array.isArray(response.luts)?response.luts:[];fillLUTs();status('Choose input interpretation, white balance and an optional LUT. Apply makes one undoable clip edit.');}
      catch(error){if(active(token))status(error.message,true);}finally{if(active(token))setBusy(false);}
    }
    return {open,close,destroy(){disposed=true;serial++;dialog.remove();}};
  }
  window.CinematicumColorPipeline={mount};
})();

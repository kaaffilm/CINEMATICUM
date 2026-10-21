/* CINEMATICUM camera matching. The selected files are data, not instructions.
 * The backend validates their camera math. Applying one reviewed pose is one
 * undoable camera replacement supplied by the owning scene editor bridge. */
(() => {
  'use strict';
  const MAX_BINARY=5*1024*1024,MAX_JSON=1024*1024,MAX_TEXT=3*1024*1024,MAX_REQUEST=8*1024*1024;
  const clone=value=>JSON.parse(JSON.stringify(value));
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function base64(bytes) {
    const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';let result='';
    for(let i=0;i<bytes.length;i+=3){const a=bytes[i],b=bytes[i+1],c=bytes[i+2],word=(a<<16)|((b||0)<<8)|(c||0);result+=alphabet[(word>>>18)&63]+alphabet[(word>>>12)&63]+(i+1<bytes.length?alphabet[(word>>>6)&63]:'=')+(i+2<bytes.length?alphabet[word&63]:'=');}
    return result;
  }
  async function readFiles(fileList,mode='fspy',scale=1,upAxis='Z') {
    const files=Array.from(fileList||[]);
    if(!Number.isFinite(scale)||scale<.000001||scale>1000)throw Error('Translation scale must be between 0.000001 and 1000.');
    if(!['Z','Y'].includes(upAxis))throw Error('Choose a source world up axis.');
    const common={scale,up_axis:upAxis};let result;
    if(mode==='colmap'){
      if(files.length!==2)throw Error('Select both cameras.txt and images.txt from the same COLMAP text export.');
      const names=files.map(file=>file.name.toLowerCase());
      if(names.filter(n=>n==='cameras.txt').length!==1||names.filter(n=>n==='images.txt').length!==1)throw Error('The two selected files must be named cameras.txt and images.txt.');
      if(files.some(file=>file.size>MAX_TEXT))throw Error('Each COLMAP text file must be at most 3 MiB.');
      const text=await Promise.all(files.map(async file=>new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer())));
      result={format:'colmap',cameras_text:text[names.indexOf('cameras.txt')],images_text:text[names.indexOf('images.txt')],...common};
    }else if(mode==='fspy'){
      if(files.length!==1)throw Error('Select one .fspy project or exported camera .json file.');
      const file=files[0],binary=/\.fspy$/i.test(file.name);
      if(!binary&&!/\.json$/i.test(file.name))throw Error('Choose an .fspy or .json camera file.');
      if(file.size>(binary?MAX_BINARY:MAX_JSON))throw Error(binary?'The fSpy file exceeds 5 MiB. Export camera JSON for a larger project.':'Camera JSON must be at most 1 MiB.');
      const bytes=new Uint8Array(await file.arrayBuffer());
      if(bytes.length!==file.size)throw Error('The selected file changed while it was read. Choose it again.');
      result=binary?{format:'fspy',name:file.name,data_base64:base64(bytes),...common}:{format:'fspy_json',name:file.name,text:new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes),...common};
    }else throw Error('Choose fSpy or COLMAP camera import.');
    if(new TextEncoder().encode(JSON.stringify(result)).length>MAX_REQUEST)throw Error('The selected camera files exceed the 8 MiB request limit after encoding.');
    return result;
  }
  const css=`.cinematicum-camera-io{box-sizing:border-box;width:min(680px,calc(100vw - 36px));max-height:calc(100vh - 36px);overflow:auto;padding:22px;color:#dde6f1;background:#19212b;border:1px solid #4a5a70;border-radius:10px;box-shadow:0 18px 70px #000b;font:12px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.cinematicum-camera-io::backdrop{background:#05090dbb}.cinematicum-camera-io *{box-sizing:border-box}.cinematicum-camera-io [hidden]{display:none!important}.cinematicum-camera-io header{display:flex;align-items:start;justify-content:space-between;gap:15px;margin-bottom:14px}.cinematicum-camera-io h2{font-size:19px;margin:0 0 4px}.cinematicum-camera-io h3{font-size:13px;margin:0 0 9px}.cinematicum-camera-io p{color:#a4b4c8;margin:7px 0 13px}.cinematicum-camera-io button,.cinematicum-camera-io input,.cinematicum-camera-io select{font:inherit;color:inherit}.cinematicum-camera-io button{padding:7px 12px;border:1px solid #4c5c70;border-radius:5px;background:#283646;cursor:pointer}.cinematicum-camera-io button:disabled{opacity:.4;cursor:default}.cinematicum-camera-io button:hover:enabled{background:#364b60}.cinematicum-camera-io .primary{color:#241b0f;background:#dfb773;border-color:#dfb773;font-weight:600}.cinematicum-camera-io label{display:flex;flex-direction:column;gap:5px;margin:9px 0;color:#c4d1e2}.cinematicum-camera-io input,.cinematicum-camera-io select{padding:8px;width:100%;min-height:34px;border:1px solid #45566d;border-radius:4px;background:#101923}.cinematicum-camera-io .camera-io-row{display:grid;grid-template-columns:1fr 1fr;gap:15px}.cinematicum-camera-io .camera-io-review{margin-top:18px;padding-top:16px;border-top:1px solid #3a4a5e}.cinematicum-camera-io .camera-io-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#354459;border:1px solid #354459;border-radius:4px;overflow:hidden;margin:12px 0}.cinematicum-camera-io .camera-io-summary span{padding:9px 10px;background:#202c39;font-size:12px}.cinematicum-camera-io .camera-io-summary small{display:block;color:#91a6c0;font-size:10px;margin-bottom:3px}.cinematicum-camera-io .camera-io-note{font-size:10px;color:#8399b5}.cinematicum-camera-io .camera-io-warnings{padding:11px 12px 11px 28px;background:#302a20;border:1px solid #645138;border-radius:5px;color:#ddc094;font-size:11px}.cinematicum-camera-io .camera-io-warnings li+li{margin-top:6px}.cinematicum-camera-io .camera-io-status{min-height:18px;margin:14px 0 0;overflow-wrap:anywhere;color:#a8bdd7}.cinematicum-camera-io .camera-io-status.error{color:#ffafb3}.cinematicum-camera-io .camera-io-position{font-size:11px;overflow-wrap:anywhere}@media(max-width:520px){.cinematicum-camera-io .camera-io-row{grid-template-columns:1fr;gap:0}.cinematicum-camera-io .camera-io-summary{grid-template-columns:repeat(2,1fr)}}`;
  const layoutCss=`
.cinematicum-camera-io{padding:0;overflow:hidden;min-height:0}
.cinematicum-camera-io[open]{display:flex;flex-direction:column}
.cinematicum-camera-io header{flex:0 0 auto;margin:0;padding:18px 22px 14px;border-bottom:1px solid #354459}
.cinematicum-camera-io header p{margin:2px 0 0}
.cinematicum-camera-io .camera-io-body{position:relative;flex:1 1 auto;min-height:0;overflow:auto;padding:8px 22px 18px;overscroll-behavior:contain}
.cinematicum-camera-io .camera-io-footer{flex:0 0 auto;padding:12px 22px 14px;border-top:1px solid #354459;background:#19212b}
.cinematicum-camera-io .camera-io-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.cinematicum-camera-io .camera-io-replace-notice{font-size:11px;line-height:1.5;margin:0 0 10px;color:#c9d5e4}
.cinematicum-camera-io .camera-io-status{font-size:11px;line-height:1.5;margin:9px 0 0;min-height:17px}
.cinematicum-camera-io input,.cinematicum-camera-io select{min-width:0}
@media(max-height:740px){.cinematicum-camera-io header{padding:13px 20px 11px}.cinematicum-camera-io .camera-io-body{padding-left:20px;padding-right:20px}.cinematicum-camera-io .camera-io-footer{padding:10px 20px 12px}}
`;
  function mount(host,bridge={}) {
    const doc=host.ownerDocument||document,style=doc.createElement('style');style.textContent=css+layoutCss;doc.head.append(style);
    const dialog=doc.createElement('dialog');dialog.className='cinematicum-camera-io';dialog.setAttribute('aria-label','Match a calibrated camera');
    dialog.innerHTML=`<header><div><h2>Match a calibrated camera</h2><p data-camera-project></p></div><button type="button" data-camera-close>Close</button></header><div class="camera-io-body"><p>Bring a solved camera into your scene, including its lens, position, orientation, roll and principal point.</p><label>Calibration source<select data-camera-format><option value="fspy">fSpy project or camera JSON</option><option value="colmap">COLMAP text reconstruction</option></select></label><label>Camera files<input data-camera-files type="file" accept=".fspy,.json"></label><p class="camera-io-note" data-camera-file-help>A .fspy project up to 5 MiB, or camera JSON up to 1 MiB. The reference photograph stays in its source file.</p><div class="camera-io-row"><label>Source world up axis<select data-camera-axis><option value="Z">Z-up · keep source axes</option><option value="Y">Y-up · rotate into Z-up</option></select></label><label>Translation scale<input data-camera-scale type="number" min="0.000001" max="1000" step="any" value="1"></label></div><p class="camera-io-note">Scale converts source distances to your scene units. Match this choice when importing geometry. Image aspect must match the project; uniform resizing is supported.</p><section class="camera-io-review" data-camera-result hidden><h3>Calibrated scene camera</h3><label>Registered image pose<select data-camera-choice></select></label><div class="camera-io-summary" data-camera-summary></div><p class="camera-io-position" data-camera-position></p><ul class="camera-io-warnings" data-camera-warnings></ul></section></div><footer class="camera-io-footer"><p class="camera-io-replace-notice" data-camera-replace-notice hidden>This replaces the current scene camera and all of its animation keys. Undo restores the previous camera.</p><div class="camera-io-actions"><button type="button" data-camera-review>Read camera calibration</button><button type="button" class="primary" data-camera-apply hidden>Replace scene camera</button></div><p class="camera-io-status" role="status" data-camera-status></p></footer>`;
    host.append(dialog);const $=selector=>dialog.querySelector(selector),removers=[];
    let disposed=false,busy=false,token=0,expected=null,candidates=[],warnings=[];
    const listen=(element,event,handler)=>{element.addEventListener(event,handler);removers.push(()=>element.removeEventListener(event,handler));};
    const context=()=>clone(bridge.getContext?.()||{});
    const current=()=>{const now=context();if(!expected?.projectId||now.projectId!==expected.projectId||now.revision!==expected.revision||now.width!==expected.width||now.height!==expected.height)throw Error('The project changed while camera matching was open. Close and reopen it to use the current scene.');};
    const message=(text,error=false)=>{$('[data-camera-status]').textContent=text;$('[data-camera-status]').classList.toggle('error',error);};
    function controls(){for(const el of dialog.querySelectorAll('input,select,[data-camera-review],[data-camera-apply]'))el.disabled=busy;$('[data-camera-apply]').disabled=busy||!candidates.length;}
    function invalidate(){candidates=[];warnings=[];$('[data-camera-result]').hidden=true;$('[data-camera-replace-notice]').hidden=true;$('[data-camera-apply]').hidden=true;controls();}
    function selected(){return candidates.find(item=>item.id===$('[data-camera-choice]').value);}
    function renderCandidate(){const item=selected();if(!item)return;const c=item.camera,fmt=n=>Number(n).toFixed(3).replace(/\.?0+$/,'');
      $('[data-camera-summary]').innerHTML=[['Source image',`${item.width} × ${item.height}`],['Vertical field of view',`${fmt(c.fov)}°`],['Roll',`${fmt(c.roll)}°`],['Horizontal lens shift',fmt(c.shift_x)],['Vertical lens shift',fmt(c.shift_y)],['Focal ratio · fx / fy',fmt(c.focal_ratio)]].map(([label,value])=>`<span><small>${esc(label)}</small>${esc(value)}</span>`).join('');
      $('[data-camera-position]').textContent=`Position: ${c.position.map(fmt).join(', ')} · Aim: ${c.target.map(fmt).join(', ')}`;
    }
    function sourceChanged(){if(busy)return;invalidate();message('');$('.camera-io-body').scrollTop=0;const colmap=$('[data-camera-format]').value==='colmap',files=$('[data-camera-files]');files.multiple=colmap;files.accept=colmap?'.txt':'.fspy,.json';files.value='';$('[data-camera-file-help]').textContent=colmap?'Select cameras.txt and images.txt together, up to 3 MiB each. PINHOLE and SIMPLE_PINHOLE are supported; undistort other models before importing.':'A .fspy project up to 5 MiB, or camera JSON up to 1 MiB. The reference photograph stays in its source file.';}
    async function review(){if(busy||disposed)return;const serial=++token;busy=true;invalidate();controls();message('Reading and validating the camera projection…');
      try{current();const payload=await readFiles($('[data-camera-files]').files,$('[data-camera-format]').value,Number($('[data-camera-scale]').value),$('[data-camera-axis]').value);if(disposed||serial!==token)return;current();const result=await bridge.onImport(payload);if(disposed||serial!==token)return;current();
        if(!Array.isArray(result?.cameras)||!result.cameras.length||result.cameras.length>128)throw Error('No supported camera poses were returned.');
        candidates=clone(result.cameras);warnings=Array.isArray(result.warnings)?result.warnings:[];
        $('[data-camera-choice]').innerHTML=candidates.map(item=>`<option value="${esc(item.id)}">${esc(item.name)}${candidates.length>1?' · pose '+esc(item.id):''}</option>`).join('');
        const list=$('[data-camera-warnings]');list.replaceChildren();for(const text of warnings){const li=doc.createElement('li');li.textContent=String(text);list.append(li);}list.hidden=!warnings.length;
        renderCandidate();$('[data-camera-result]').hidden=false;$('[data-camera-replace-notice]').hidden=false;$('[data-camera-apply]').hidden=false;message(`${candidates.length} calibrated pose${candidates.length===1?'':'s'} ready. Review the selected pose, then replace the scene camera.`);$('.camera-io-body').scrollTop=$('[data-camera-result]').offsetTop;
      }catch(error){if(!disposed&&serial===token){invalidate();message(error.message||'Camera calibration could not be imported.',true);}}
      finally{if(!disposed&&serial===token){busy=false;controls();}}
    }
    async function apply(){if(busy||disposed||!selected())return;const serial=++token,item=clone(selected());busy=true;controls();
      try{current();const accepted=await bridge.onApply(item.camera,clone(expected),item.source);if(disposed||serial!==token)return;if(accepted===false)throw Error('The camera could not be applied because the scene changed or another operation is active.');close();bridge.notify?.('Calibrated camera applied. Undo restores the previous camera.');}
      catch(error){if(!disposed&&serial===token)message(error.message||'The scene camera could not be replaced.',true);}
      finally{if(!disposed&&serial===token){busy=false;controls();}}
    }
    function close(){token++;busy=false;dialog.close();controls();}
    function open(){if(disposed)return;expected=context();if(!expected.projectId)throw Error('Open a project before matching a camera.');token++;busy=false;sourceChanged();$('[data-camera-scale]').value='1';$('[data-camera-axis]').value='Z';$('[data-camera-project]').textContent=`Project image · ${expected.width} × ${expected.height}`;invalidate();message('');if(!dialog.open)dialog.showModal();}
    listen($('[data-camera-close]'),'click',close);listen(dialog,'cancel',event=>{event.preventDefault();close();});listen(dialog,'keydown',event=>event.stopPropagation());
    listen($('[data-camera-format]'),'change',sourceChanged);listen($('[data-camera-files]'),'change',()=>{if(!busy){invalidate();message('');}});
    for(const el of [$('[data-camera-axis]'),$('[data-camera-scale]')])listen(el,'change',()=>{if(!busy){invalidate();message('Calibration settings changed. Read the files again before applying.');}});
    listen($('[data-camera-choice]'),'change',renderCandidate);listen($('[data-camera-review]'),'click',review);listen($('[data-camera-apply]'),'click',apply);
    return {open,close,destroy(){disposed=true;token++;for(const remove of removers)remove();dialog.remove();style.remove();}};
  }
  window.CinematicumCameraIO={mount,readFiles};
})();

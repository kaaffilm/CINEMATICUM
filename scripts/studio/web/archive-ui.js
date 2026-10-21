/* Archive jobs run in the application bridge. Keep the selected File intact:
 * a large project archive must never be copied into a browser ArrayBuffer. */
(() => {
  'use strict';
  const MAX_ARCHIVE_BYTES=64*1024*1024*1024;
  const clone=value=>JSON.parse(JSON.stringify(value));
  const css=`
.cinematicum-archive{width:min(700px,calc(100vw - 32px));max-width:700px;max-height:calc(100vh - 40px);padding:0;overflow:auto;box-sizing:border-box;background:#181e26;border:1px solid #465365;border-radius:9px;color:#dbe4ef;box-shadow:0 20px 90px #000a;font:12px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.cinematicum-archive::backdrop{background:#05090dbb}.cinematicum-archive *{box-sizing:border-box}.cinematicum-archive [hidden]{display:none!important}.cinematicum-archive header{display:flex;align-items:start;justify-content:space-between;gap:18px;padding:18px 20px;border-bottom:1px solid #35404e}.cinematicum-archive h2{margin:0;font-size:18px}.cinematicum-archive h3{margin:0 0 5px;font-size:14px}.cinematicum-archive p{margin:6px 0;color:#a7b6c9}.cinematicum-archive button,.cinematicum-archive input{font:inherit}.cinematicum-archive button{min-height:32px;padding:5px 12px;border:1px solid #455266;border-radius:4px;background:#26313f;color:#dbe4ef;cursor:pointer}.cinematicum-archive button:disabled{opacity:.45;cursor:default}.cinematicum-archive .primary{background:#e7b66f;border-color:#e7b66f;color:#211a10;font-weight:650}.cinematicum-archive main{padding:0 20px}.cinematicum-archive section{padding:18px 0}.cinematicum-archive section+section{border-top:1px solid #35404e}.cinematicum-archive label{display:block;margin:12px 0 6px;color:#bdcadd}.cinematicum-archive input[type=file]{display:block;width:100%;min-height:38px;margin-top:5px;padding:5px 7px;color:#dbe4ef;background:#101720;border:1px solid #435166;border-radius:4px}.cinematicum-archive .archive-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:13px}.cinematicum-archive .archive-note{font-size:11px;color:#8fa3bd}.cinematicum-archive .archive-file-info{overflow-wrap:anywhere;font-size:11px;min-height:18px}.cinematicum-archive .archive-file-info.error,.cinematicum-archive .archive-status.error{color:#efb3ae}.cinematicum-archive footer{padding:12px 20px 16px;border-top:1px solid #35404e;background:#1b222c}.cinematicum-archive .archive-status{margin:0;min-height:19px;overflow-wrap:anywhere;color:#c8d6e6}
`;
  function mount(host,bridge={}) {
    const doc=host.ownerDocument||document;
    const style=doc.createElement('style');style.textContent=css;doc.head.append(style);
    const dialog=doc.createElement('dialog');dialog.className='cinematicum-archive';dialog.setAttribute('aria-label','Project archive');
    dialog.innerHTML=`<header><div><h2>Project archive</h2><p data-archive-project></p></div><button type="button" data-archive-close>Close</button></header>
      <main><section><h3>Back up this project</h3><p>Create a portable archive of the editable cut and project-owned media, LUTs, saved 3D scenes and imaging masters.</p><p class="archive-note">External engines, AI models and files outside the project are not embedded. Save the downloaded archive somewhere you can recover it.</p><div class="archive-actions"><button type="button" class="primary" data-archive-export>Create project archive</button><span class="archive-note">Saves the current edit before archiving.</span></div></section>
      <section><h3>Restore an archive</h3><p>Restore into a new project. Your current project is kept. When the restore job finishes, use <strong>Open restored project</strong> in the job bar.</p><label>Selected project archive<input type="file" accept=".zip,application/zip" data-archive-file></label><p class="archive-file-info" data-archive-file-info>Choose a CINEMATICUM .zip archive, up to 64 GiB.</p><div class="archive-actions"><button type="button" data-archive-restore disabled>Restore as a new project</button><span class="archive-note">Archive contents are validated during restore.</span></div></section></main>
      <footer><p role="status" aria-live="polite" class="archive-status" data-archive-status>Job progress, errors and completed downloads appear in the job bar.</p></footer>`;
    host.append(dialog);
    const $=selector=>dialog.querySelector(selector),removers=[];
    let disposed=false,busy=false,serial=0,snapshot=null,expected=null,selectedFile=null;
    const listen=(element,event,handler)=>{element.addEventListener(event,handler);removers.push(()=>element.removeEventListener(event,handler));};
    const context=()=>clone(bridge.getContext?.()||{projectId:bridge.getProject?.()?.id,revision:bridge.getProject?.()?.revision});
    function current(){
      const project=bridge.getProject?.(),now=context();
      if(!project||project.id!==snapshot?.id||now.projectId!==expected?.projectId||now.revision!==expected?.revision)throw Error('The project changed while Archive was open. Close and reopen Archive to use the current edit.');
    }
    function message(value,error=false){const status=$('[data-archive-status]');status.textContent=value;status.classList.toggle('error',error);}
    function controls(){
      $('[data-archive-file]').disabled=busy;
      $('[data-archive-export]').disabled=busy||typeof bridge.onExport!=='function';
      $('[data-archive-restore]').disabled=busy||!selectedFile||typeof bridge.onRestore!=='function';
      dialog.setAttribute('aria-busy',String(busy));
    }
    function selected(){
      if(disposed||busy)return;
      selectedFile=null;
      const file=$('[data-archive-file]').files?.[0],info=$('[data-archive-file-info]');info.classList.remove('error');
      try {
        current();
        if(!file){info.textContent='Choose a CINEMATICUM .zip archive, up to 64 GiB.';return;}
        if(!/\.zip$/i.test(file.name)||file.name.length>1024)throw Error('Choose a CINEMATICUM .zip or .cinematicum.zip archive.');
        if(!Number.isSafeInteger(file.size)||file.size<=0)throw Error('The selected archive is empty or its size is invalid.');
        if(file.size>MAX_ARCHIVE_BYTES)throw Error('The selected archive exceeds the 64 GiB restore limit.');
        selectedFile=file;
        const size=file.size<1024*1024?`${Math.ceil(file.size/1024)} KiB`:`${(file.size/(1024*1024)).toLocaleString(undefined,{maximumFractionDigits:1})} MiB`;
        info.textContent=`${file.name} · ${size}`;
        message('Ready to upload the selected archive and validate it in a new project.');
      } catch(error){info.textContent=error.message||'The selected file is invalid.';info.classList.add('error');}
      finally{controls();}
    }
    async function submit(kind){
      if(disposed||busy||!snapshot||(kind==='restore'&&!selectedFile))return;
      const operation=++serial;
      busy=true;controls();message(kind==='export'?'Saving the edit and submitting the archive job…':'Saving the current edit and uploading the selected archive…');
      try {
        current();
        const callback=kind==='export'?bridge.onExport:bridge.onRestore;
        if(typeof callback!=='function')throw Error('Archive operations are unavailable in this application session.');
        // The bridge owns save/POST, real progress, errors, downloads and opening
        // the restored project. No media bytes are read or fabricated here.
        const result=await callback(kind==='export'?clone(snapshot):selectedFile,clone(expected));
        if(disposed||operation!==serial)return;
        current();
        if(result===false)throw Error('The archive job could not be submitted. Review the job bar and try again.');
        close();
        bridge.notify?.(kind==='export'?'Archive job submitted. Download the completed archive from the job bar.':'Restore job submitted. Open the new project from the job bar when validation finishes.');
      } catch(error){if(!disposed&&operation===serial)message(error.message||'The archive operation could not be submitted.',true);}
      finally{if(!disposed&&operation===serial){busy=false;controls();}}
    }
    function close(){serial++;busy=false;selectedFile=null;$('[data-archive-file]').value='';if(dialog.open)dialog.close();controls();}
    function open(){
      if(disposed)return;
      const project=bridge.getProject?.();if(!project)throw Error('Open a project before using project archives.');
      serial++;busy=false;snapshot=clone(project);expected=context();selectedFile=null;
      $('[data-archive-project]').textContent=snapshot.name||'Current project';
      $('[data-archive-file]').value='';
      const info=$('[data-archive-file-info]');info.textContent='Choose a CINEMATICUM .zip archive, up to 64 GiB.';info.classList.remove('error');
      message('Job progress, errors and completed downloads appear in the job bar.');controls();if(!dialog.open)dialog.showModal();
    }
    listen($('[data-archive-close]'),'click',close);
    listen(dialog,'cancel',event=>{event.preventDefault();close();});
    listen(dialog,'keydown',event=>event.stopPropagation());
    listen($('[data-archive-file]'),'change',selected);
    listen($('[data-archive-export]'),'click',()=>submit('export'));
    listen($('[data-archive-restore]'),'click',()=>submit('restore'));
    return {open,close,destroy(){disposed=true;serial++;selectedFile=null;snapshot=null;expected=null;for(const remove of removers)remove();if(dialog.open)dialog.close();dialog.remove();style.remove();}};
  }
  window.CinematicumArchive={mount};
})();

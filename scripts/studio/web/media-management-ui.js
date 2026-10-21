/* Preview derivatives remain separate from immutable original media. */
'use strict';
window.CinematicumMediaManagement=(()=>{
  const copy=v=>JSON.parse(JSON.stringify(v));
  function mount(o){
    const dialog=document.createElement('dialog');dialog.className='media-management-dialog';
    dialog.innerHTML='<div class="dialog-header"><div><span class="eyebrow">MEDIA</span><h2>Originals & preview proxies</h2></div><button type="button" class="icon-button" data-close aria-label="Close media management">×</button></div><p class="muted">Preview proxies preserve picture count and timing. Export always renders original media.</p><label class="field-row"><span>Use available preview proxies</span><input type="checkbox" data-enabled></label><label>Preview long edge<select data-edge><option value="640">640 px</option><option value="960" selected>960 px</option><option value="1280">1280 px</option><option value="1920">1920 px</option></select></label><label style="margin-top:16px">Media<select data-source></select></label><p class="note" data-description></p><div class="field-row"><button type="button" data-build>Create proxy</button><button type="button" data-relink>Relink exact original…</button><button type="button" data-refresh>Refresh</button></div><progress data-progress max="1" value="0" hidden></progress><p class="note" role="status" data-status></p><button type="button" data-cancel hidden>Cancel proxy job</button><input type="file" data-file hidden>';
    document.body.append(dialog);
    const q=s=>dialog.querySelector(s), cache=new Map();let operation=0,job=null,disposed=false;
    const context=()=>o.getContext(), root=id=>`/api/projects/${encodeURIComponent(id)}`;
    const same=c=>context().project?.id===c.project.id;
    function status(text){q('[data-status]').textContent=text;}
    function selected(){return cache.get(context().project?.id)?.assets.find(a=>a.id===q('[data-source]').value);}
    function controls(){
      const c=context(), row=selected(), edge=Number(q('[data-edge]').value), proxy=row?.proxies.find(p=>p.long_edge===edge);
      q('[data-build]').disabled=Boolean(job)||!row||row.kind!=='video'||!row.present;
      q('[data-relink]').disabled=Boolean(job)||!row;
      q('[data-source]').disabled=Boolean(job);q('[data-edge]').disabled=Boolean(job);
      q('[data-refresh]').disabled=Boolean(job);q('[data-cancel]').hidden=!job;
      q('[data-description]').textContent=row?`${row.present?(row.size_matches?'Original is present.':'Original size changed; relink the recorded original.'):'Original is missing.'} ${proxy?`Verified ${proxy.width} × ${proxy.height} proxy · ${proxy.frames} pictures.`:'No proxy at the selected size.'}`:'';
      q('[data-enabled]').checked=Boolean(c.project?.settings?.preview_proxies?.enabled);
    }
    async function refresh(){
      const c=context(), id=c.project?.id;if(!id)return;
      const data=await o.request(root(id)+'/media-inventory');if(!same(c)||disposed)return;
      cache.set(id,data);const chosen=q('[data-source]').value||c.selectedAsset;
      q('[data-source]').replaceChildren(...data.assets.filter(a=>!a.name.startsWith('__title_')).map(a=>{const option=document.createElement('option');option.value=a.id;option.textContent=a.name;return option;}));
      if(data.assets.some(a=>a.id===chosen))q('[data-source]').value=chosen;
      q('[data-edge]').value=String(c.project.settings?.preview_proxies?.long_edge||960);
      controls();o.onPlaybackChange?.();return data;
    }
    async function open(){if(context().blocked)return;dialog.showModal();status('Inspecting imported media…');try{await refresh();status('');}catch(e){status(e.message);}}
    function settings(){const edge=Number(q('[data-edge]').value),enabled=q('[data-enabled]').checked;o.setSettings({enabled,long_edge:edge});controls();o.onPlaybackChange?.();}
    async function build(){
      const c=context(), row=selected();if(!row||job||c.blocked)return;const owner=++operation;
      try{
        status('Preparing proxy job…');job={id:null,projectId:c.project.id};controls();
        const initial=await o.request(root(c.project.id)+'/media-proxy',{method:'POST',body:{asset_id:row.id,long_edge:Number(q('[data-edge]').value)}});
        job={...(initial.job||initial),projectId:c.project.id};q('[data-progress]').hidden=false;
        while(owner===operation&&!disposed){
          const j=await o.request('/api/jobs/'+encodeURIComponent(job.id));
          if(owner!==operation||disposed)return;
          const result=j.job||j;job={...result,projectId:c.project.id};controls();
          q('[data-progress]').value=result.progress||0;status(result.state==='running'?'Encoding and verifying every picture timestamp…':result.state);
          if(result.state==='completed'){
            if(same(c)){await refresh();status(`Proxy ready · ${result.result.frames} pictures · originals retained for export.`);}
            return;
          }
          if(['failed','cancelled','interrupted'].includes(result.state))throw Error(result.error||`Proxy job ${result.state}.`);
          await new Promise(resolve=>setTimeout(resolve,500));
        }
      }catch(e){status(e.message);o.notify(e.message,true);}
      finally{if(owner===operation){job=null;q('[data-progress]').hidden=true;controls();}}
    }
    async function relink(file){
      const c=context(),row=selected();if(!file||!row||job)return;
      status('Checking original bytes…');q('[data-relink]').disabled=true;
      try{const result=await o.request(root(c.project.id)+'/media-relink?asset_id='+encodeURIComponent(row.id),{method:'POST',raw:true,body:file});if(same(c)){await refresh();status(result.already_present?'The recorded original is already present.':'Original restored; edit and asset identity retained.');o.onPlaybackChange?.();}}
      catch(e){status(e.message);o.notify(e.message,true);}finally{q('[data-file]').value='';controls();}
    }
    q('[data-close]').onclick=()=>dialog.close();q('[data-refresh]').onclick=()=>refresh().catch(e=>status(e.message));
    q('[data-source]').onchange=controls;q('[data-edge]').onchange=settings;q('[data-enabled]').onchange=settings;
    q('[data-build]').onclick=build;q('[data-relink]').onclick=()=>q('[data-file]').click();q('[data-file]').onchange=e=>relink(e.target.files[0]);
    q('[data-cancel]').onclick=async()=>{if(!job?.id)return;try{await o.request('/api/jobs/'+encodeURIComponent(job.id)+'/cancel',{method:'POST',body:{}});status('Cancellation requested.');}catch(e){status(e.message);}};
    o.button?.addEventListener('click',open);
    function playbackUrl(asset,fallback){
      const c=context(),setting=c.project?.settings?.preview_proxies;
      if(!setting?.enabled||asset.kind!=='video')return fallback;
      const row=cache.get(c.project.id)?.assets.find(a=>a.id===asset.id&&a.source_sha256===asset.sha256),edge=setting.long_edge||960;
      return row?.proxies.some(p=>p.long_edge===edge)?root(c.project.id)+'/media-proxy/'+encodeURIComponent(asset.id)+'?long_edge='+edge:fallback;
    }
    return {open,refresh,playbackUrl,reset(){dialog.close();refresh().catch(()=>{});},destroy(){disposed=true;operation++;dialog.remove();}};
  }
  return {mount};
})();

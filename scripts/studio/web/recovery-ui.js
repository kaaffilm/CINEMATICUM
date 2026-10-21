/* Revision-bound disk checkpoints; recovery is an explicit undoable edit. */
'use strict';
window.CinematicumRecovery=(()=>{
  const clone=x=>JSON.parse(JSON.stringify(x));
  const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function mount({getContext,request,onRecover,notify,button,status}) {
    let editor='',sequence=0,epoch=0,timer=null,firstPending=0,pending=null,again=false,lastWritten=-1,failed=false,selection=null;
    const dialog=document.createElement('dialog');dialog.id='recovery-dialog';
    dialog.innerHTML='<div class="dialog-header"><div><span class="eyebrow">PROJECT RECOVERY</span><h2>Recover your edits</h2></div><button type="button" class="icon-button" data-close aria-label="Close recovery">×</button></div><p class="muted">Disk checkpoints retain unsaved edits. Recovering a draft or saved version creates an undoable edit; Save commits it.</p><div data-entries></div>';
    document.body.append(dialog);
    const endpoint=id=>'/api/projects/'+encodeURIComponent(id);
    const label=value=>{status.textContent=value;};
    const receipt=()=>({editor_id:editor,sequence:Math.max(1,sequence)});
    function schedule() {
      const c=getContext();if(!c?.project||!c.dirty)return;
      const now=Date.now();if(!firstPending)firstPending=now;
      clearTimeout(timer);label('Recovery pending');
      timer=setTimeout(flush,Math.max(0,Math.min(750,3000-(now-firstPending))));
    }
    async function flush() {
      clearTimeout(timer);timer=null;
      const c=getContext();if(!c?.project||!c.dirty){firstPending=0;return;}
      if(c.saving){timer=setTimeout(flush,300);return;}
      if(pending){again=true;return pending;}
      if(lastWritten===c.revision){firstPending=0;return;}
      const token=epoch,id=c.project.id,revision=c.revision;
      const payload={editor_id:editor,sequence:++sequence,project:clone(c.project)};
      firstPending=0;again=false;
      const work=(async()=>{
        try {
          await request(endpoint(id)+'/checkpoint',{method:'POST',body:payload});
          if(token!==epoch)return;
          failed=false;lastWritten=revision;
          if(getContext().revision===revision)label('Recovery checkpointed');
        } catch(error) {
          if(token!==epoch)return;
          label('Recovery unavailable');
          if(!failed)notify('Recovery checkpoint failed: '+error.message+'. Your current edits are still open; save them when possible.',true,12000);
          failed=true;
        }
      })();
      pending=work;
      await work;
      if(pending===work)pending=null;
      if(token===epoch&&(again||getContext().revision!==revision))schedule();
    }
    async function refresh(announce=false) {
      const c=getContext();if(!c?.project)return null;
      const token=epoch,result=await request(endpoint(c.project.id)+'/recovery');
      if(token!==epoch)return null;
      button.textContent=result.drafts.length?'Recover · '+result.drafts.length:'History';
      button.title='Review crash checkpoints and the last 20 saved versions';
      if(announce&&result.drafts.length)notify('Unsaved disk checkpoints are available. Open Recover to review them.',false,10000);
      return result;
    }
    async function open() {
      const c=getContext();if(!c?.project||c.blocked)return;
      const snapshot={projectId:c.project.id,revision:c.revision,savedRevision:c.project.revision};
      const result=await refresh();if(!result)return;
      selection=snapshot;
      const entries=dialog.querySelector('[data-entries]');
      const rows=(values,kind)=>values.map(value=>'<div class="recovery-entry"><div><strong>'+escape(value.name)+'</strong><small>'+escape(new Date(value.written_at*1000).toLocaleString())+' · '+value.clips+' clips · '+value.titles+' titles · revision '+value.base_revision+(value.stale?' · saved project has newer edits':'')+'</small></div><button data-restore="'+kind+'" data-key="'+escape(value.key)+'" data-sequence="'+(value.sequence||'')+'">Recover</button>'+(kind==='draft'?'<button class="quiet" data-discard="'+escape(value.key)+'" data-sequence="'+value.sequence+'">Discard</button>':'')+'</div>').join('');
      entries.innerHTML='<h3>Unsaved checkpoints</h3>'+(rows(result.drafts,'draft')||'<p class="muted">No unsaved checkpoints.</p>')+'<h3>Saved versions</h3>'+(rows(result.versions,'version')||'<p class="muted">Previous saves appear here.</p>')+(result.unreadable?'<p class="note">'+result.unreadable+' unreadable recovery records were preserved.</p>':'');
      if(!dialog.open)dialog.showModal();
    }
    dialog.addEventListener('click',async event=>{
      if(event.target.closest('[data-close]')){dialog.close();return;}
      const item=event.target.closest('[data-restore],[data-discard]');if(!item)return;
      const c=getContext();if(!selection||c.blocked||c.project.id!==selection.projectId||c.revision!==selection.revision||c.project.revision!==selection.savedRevision){notify('The project changed. Reopen recovery before applying a version.',true);return;}
      item.disabled=true;
      try {
        const discard=item.hasAttribute('data-discard');
        const body={action:discard?'discard':'restore',kind:item.dataset.restore,key:discard?item.dataset.discard:item.dataset.key,sequence:Number(item.dataset.sequence)||undefined};
        const result=await request(endpoint(c.project.id)+'/recovery',{method:'POST',body});
        if(discard){await open();return;}
        onRecover(result.project,selection);
        dialog.close();notify('Recovered as an unsaved edit. Undo returns to the previous timeline.');
        refresh().catch(()=>{});
      } catch(error){notify(error.message,true);} finally {item.disabled=false;}
    });
    button.addEventListener('click',()=>open().catch(error=>notify(error.message,true)));
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')flush();});
    return {schedule,flush,receipt,open,
      reset(){epoch++;editor=crypto.randomUUID().replace(/-/g,'');sequence=0;firstPending=0;lastWritten=-1;failed=false;again=false;pending=null;clearTimeout(timer);timer=null;label('');if(dialog.open)dialog.close();refresh(true).catch(error=>{label('Recovery unavailable');notify(error.message,true);});},
      saved(){clearTimeout(timer);firstPending=0;label('');if(getContext().dirty)schedule();refresh().catch(()=>{});}
    };
  }
  return {mount};
})();

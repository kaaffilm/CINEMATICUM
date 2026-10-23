/* Typed bus/aux authoring; one validated edit enters the ordinary undo history. */
(()=>{
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const defaults=()=>({version:1,buses:[],tracks:[],master:{gain:1,loudness:{enabled:false,integrated_lufs:-23,true_peak_dbfs:-1,range_lu:7}}});
  const inserts={highpass:{type:'highpass',frequency_hz:120},lowpass:{type:'lowpass',frequency_hz:12000},delay:{type:'delay',milliseconds:120},compressor:{type:'compressor',threshold_db:-18,ratio:4,attack_ms:10,release_ms:150,makeup_db:0}};
  function mount(host,bridge){
    const dialog=document.createElement('dialog');dialog.className='cinematicum-audio-mixer';
    const style=document.createElement('style');style.textContent='.cinematicum-audio-mixer{width:min(980px,94vw);max-height:91vh;overflow:auto;background:#171a20;color:#e8ebef;border:1px solid #526070;border-radius:10px;padding:22px}.mix-heading{display:flex;justify-content:space-between;gap:18px}.mix-heading h2{margin:0;font-size:19px}.cinematicum-audio-mixer button,.cinematicum-audio-mixer input,.cinematicum-audio-mixer select{font:inherit;color:inherit;background:#252b35;border:1px solid #566170;border-radius:4px;padding:7px}.cinematicum-audio-mixer button{cursor:pointer}.cinematicum-audio-mixer button:disabled{opacity:.45;cursor:default}.mix-note{color:#b6bfca;font-size:12px;line-height:1.5}.mix-row{display:flex;flex-wrap:wrap;align-items:end;gap:10px}.mix-row label{display:flex;flex-direction:column;gap:5px;font-size:12px}.mix-row input[type=number]{width:92px}.mix-row input[type=checkbox]{width:auto}.mix-bus,.mix-track,.mix-master{border:1px solid #3d4857;padding:13px;margin:12px 0;border-radius:6px}.mix-bus h3,.mix-track h3,.mix-master h3{margin:0 0 9px;font-size:14px}.mix-insert,.mix-send{padding:9px 0;border-top:1px solid #37414e;margin-top:9px}.mix-actions{display:flex;gap:10px;margin-top:16px}[data-mix-apply]{background:#b28342!important;color:white!important}[data-mix-status].error{color:#ffb7a9}[data-mix-meter]{white-space:pre-wrap;line-height:1.6;color:#d1dded;font-size:13px}';
    host.append(style,dialog);
    let project=null,expected=null,mixer=null,busy=false,disposed=false,serial=0;
    const reports=new Map(),$=selector=>dialog.querySelector(selector);
    const status=(message,error=false)=>{const element=$('[data-mix-status]');if(element){element.textContent=message;element.classList.toggle('error',error);}};
    function tracks(){const ids=new Set([...(project.tracks||[]).map(t=>t.id),...(project.clips||[]).map(c=>c.track??0)]);return [...ids].sort((a,b)=>a-b).map(id=>({id,name:project.tracks?.find(t=>t.id===id)?.name||(id<0?'A'+Math.abs(id):'V'+(id+1))}));}
    function route(track){let value=mixer.tracks.find(r=>r.track===track);if(!value){value={track,output:'master',sends:[]};mixer.tracks.push(value);}return value;}
    function destinations(value,{none=false,exclude=''}={}){return [{id:'master',name:'Master'},...(none?[{id:'none',name:'Sends only'}]:[]),...mixer.buses.filter(b=>b.id!==exclude)].map(b=>`<option value="${esc(b.id)}" ${b.id===value?'selected':''}>${esc(b.name||b.id)}</option>`).join('');}
    function number(label,key,value,min,max,step='.01'){return `<label>${label}<input type="number" required data-mix-param="${key}" value="${value}" min="${min}" max="${max}" step="${step}"></label>`;}
    function insertFields(value){if(value.type==='delay')return number('Wet delay · ms','milliseconds',value.milliseconds,0,2000,1);if(value.type==='highpass'||value.type==='lowpass')return number('Cutoff · Hz','frequency_hz',value.frequency_hz,20,20000,1);return number('Threshold · dB','threshold_db',value.threshold_db,-60,0,.1)+number('Ratio','ratio',value.ratio,1,20,.1)+number('Attack · ms','attack_ms',value.attack_ms,.01,2000,.01)+number('Release · ms','release_ms',value.release_ms,.01,9000,.01)+number('Makeup · dB','makeup_db',value.makeup_db,0,24,.1);}
    function meter(){
      const report=reports.get(project.id)||bridge.getReport?.();const r=report?.audio_meter;
      if(!r)return 'Render preview or export this mix to measure its actual integrated loudness and true peak.';
      const display=(v,suffix)=>Number.isFinite(v)?v.toFixed(1)+' '+suffix:'Silence';
      const levels=r.silent?'Exact silence'+(report.audio_normalization?.some(a=>a.target_unreachable)?' · normalization target unreachable':''):`Integrated: ${display(r.integrated_lufs,'LUFS')} · Range: ${display(r.loudness_range_lu,'LU')} · True peak: ${display(r.true_peak_dbfs,'dBFS')}`;
      return `Last completed export${report.filename?' · '+report.filename:''}\n${levels}\nMeasured file: ${(r.measured_export_sha256||report.sha256||'').slice(0,16)}…`;
    }
    function render(){
      dialog.innerHTML=`<div class="mix-heading"><h2>Buses, aux returns & loudness</h2><button type="button" data-mix-close aria-label="Close audio mixer">×</button></div><p class="mix-note">Sends follow clip gain, pan, fades and track faders. Preview and exports use this complete mix. Delay returns stay inside the sequence out point; extend it to retain a longer tail.</p><div data-mix-buses>${mixer.buses.map((bus,index)=>`<section class="mix-bus" data-mix-bus="${index}"><h3>${esc(bus.name)}</h3><div class="mix-row"><label>Bus name<input data-mix-bus-name maxlength="80" required value="${esc(bus.name)}"></label>${number('Gain ×','gain',bus.gain,0,4)}<label>Output<select data-mix-bus-output>${destinations(bus.output,{exclude:bus.id})}</select></label><label>Mute<input type="checkbox" data-mix-bus-mute ${bus.mute?'checked':''}></label><button type="button" data-mix-delete-bus>Remove bus</button></div>${bus.inserts.map((insert,ordinal)=>`<div class="mix-insert mix-row" data-mix-insert="${ordinal}"><label>Insert<select data-mix-insert-type>${Object.keys(inserts).map(type=>`<option ${type===insert.type?'selected':''}>${type}</option>`).join('')}</select></label>${insertFields(insert)}<button type="button" data-mix-delete-insert>Remove insert</button></div>`).join('')}<button type="button" data-mix-add-insert ${bus.inserts.length>=4?'disabled':''}>Add insert</button></section>`).join('')}</div><div class="mix-row"><button type="button" data-mix-add-bus ${mixer.buses.length>=8?'disabled':''}>Add bus</button><button type="button" data-mix-add-return ${mixer.buses.length>=8?'disabled':''}>Add delay return</button></div><h3>Track outputs & post-fader sends</h3>${tracks().map(track=>{const r=route(track.id);return `<section class="mix-track" data-mix-track="${track.id}"><h3>${esc(track.name)}</h3><div class="mix-row"><label>Output<select data-mix-track-output>${destinations(r.output,{none:true})}</select></label><button type="button" data-mix-add-send ${!mixer.buses.length||r.sends.length>=Math.min(4,mixer.buses.length)?'disabled':''}>Add send</button></div>${r.sends.map((send,ordinal)=>`<div class="mix-send mix-row" data-mix-send="${ordinal}"><label>Return bus<select data-mix-send-bus>${mixer.buses.map(b=>`<option value="${esc(b.id)}" ${b.id===send.bus?'selected':''}>${esc(b.name)}</option>`).join('')}</select></label>${number('Send ×','gain',send.gain,0,4)}<button type="button" data-mix-delete-send>Remove send</button></div>`).join('')}</section>`;}).join('')}<section class="mix-master"><h3>Master</h3><div class="mix-row" data-mix-master>${number('Gain ×','gain',mixer.master.gain,0,4)}<label>Normalize loudness<input type="checkbox" data-mix-normalize ${mixer.master.loudness.enabled?'checked':''}></label></div><div class="mix-row" data-mix-loudness>${number('Integrated · LUFS','integrated_lufs',mixer.master.loudness.integrated_lufs,-36,-9,.1)}${number('True-peak ceiling · dBFS','true_peak_dbfs',mixer.master.loudness.true_peak_dbfs,-9,-.3,.1)}${number('Range target · LU','range_lu',mixer.master.loudness.range_lu,1,20,.1)}</div><p class="mix-note">Normalization uses the actual mixed signal. Read the measured export below to assess the delivered result.</p><div data-mix-meter>${esc(meter())}</div></section><div class="mix-actions"><button type="button" data-mix-apply>Apply audio mix</button><button type="button" data-mix-clear ${project.audio_mixer?'':'disabled'}>Use direct track mix</button></div><p data-mix-status role="status"></p>`;
      controls();
    }
    function controls(){for(const e of dialog.querySelectorAll('input,select,button')){if(e.hasAttribute('data-mix-close'))continue;if(busy){e.dataset.mixPreviousDisabled=String(e.disabled);e.disabled=true;}else if(e.dataset.mixPreviousDisabled!==undefined){e.disabled=e.dataset.mixPreviousDisabled==='true';delete e.dataset.mixPreviousDisabled;}}}
    function current(){const now=bridge.getContext();if(!project||bridge.getProject()?.id!==project.id||now.projectId!==expected.projectId||now.revision!==expected.revision)throw Error('The project changed. Reopen the audio mixer.');}
    function validate(){
      for(const e of dialog.querySelectorAll('input'))if(!e.checkValidity())throw Error('Enter a valid '+(e.closest('label')?.textContent||'mixer value').trim()+'.');
      const buses=new Map(mixer.buses.map(b=>[b.id,b]));
      for(const bus of mixer.buses){let next=bus.id;const seen=new Set();while(next!=='master'){if(seen.has(next))throw Error('Bus outputs cannot form a feedback loop.');seen.add(next);next=buses.get(next)?.output;if(!next)throw Error('A bus output is missing.');}}
      for(const r of mixer.tracks)if(new Set(r.sends.map(s=>s.bus)).size!==r.sends.length)throw Error('Choose a different return bus for each send.');
    }
    function open(){if(disposed)return;project=clone(bridge.getProject());if(!project?.id)throw Error('Open a project before editing its mix.');expected=clone(bridge.getContext());mixer=clone(project.audio_mixer||defaults());serial++;busy=false;render();if(!dialog.open)dialog.showModal();}
    function close(){serial++;busy=false;dialog.close();}
    async function apply(clear=false){if(busy||disposed)return;try{current();if(!clear)validate();}catch(error){status(error.message,true);return;}
      const token=++serial;busy=true;controls();status('Applying audio mix…');
      try{const result=await bridge.request('/api/projects/'+encodeURIComponent(project.id)+'/editorial',{method:'POST',body:{project:clone(project),action:'audio_mixer_apply',values:{mixer:clear?null:clone(mixer)}}});if(disposed||token!==serial||!dialog.open)return;current();if(result.project?.id!==project.id)throw Error('The audio edit returned another project.');if(await bridge.onApply(clone(result.project),clone(expected))===false)throw Error('The project changed before the audio mix could apply.');if(disposed||token!==serial)return;close();bridge.notify?.('Audio mix applied. Undo restores the previous mix; Save retains it.');}
      catch(error){if(!disposed&&token===serial)status(error.message,true);}finally{if(!disposed&&token===serial){busy=false;controls();}}
    }
    function change(event){if(busy)return;const e=event.target,busElement=e.closest('[data-mix-bus]'),bus=busElement?mixer.buses[Number(busElement.dataset.mixBus)]:null,trackElement=e.closest('[data-mix-track]'),r=trackElement?route(Number(trackElement.dataset.mixTrack)):null;
      try{if(e.matches('input')&&!e.checkValidity())throw Error('Enter a value inside its displayed range.');
        if(e.hasAttribute('data-mix-bus-name'))bus.name=e.value;
        else if(e.hasAttribute('data-mix-bus-output'))bus.output=e.value;
        else if(e.hasAttribute('data-mix-bus-mute'))bus.mute=e.checked;
        else if(e.hasAttribute('data-mix-track-output'))r.output=e.value;
        else if(e.hasAttribute('data-mix-send-bus'))r.sends[Number(e.closest('[data-mix-send]').dataset.mixSend)].bus=e.value;
        else if(e.hasAttribute('data-mix-normalize'))mixer.master.loudness.enabled=e.checked;
        else if(e.hasAttribute('data-mix-insert-type'))bus.inserts[Number(e.closest('[data-mix-insert]').dataset.mixInsert)]=clone(inserts[e.value]);
        else if(e.dataset.mixParam){const key=e.dataset.mixParam,value=Number(e.value),insert=e.closest('[data-mix-insert]'),send=e.closest('[data-mix-send]');if(insert)bus.inserts[Number(insert.dataset.mixInsert)][key]=value;else if(send)r.sends[Number(send.dataset.mixSend)][key]=value;else if(bus)bus[key]=value;else if(e.closest('[data-mix-loudness]'))mixer.master.loudness[key]=value;else mixer.master[key]=value;}
        render();validate();
      }catch(error){status(error.message,true);}
    }
    function click(event){const e=event.target.closest('button');if(!e)return;if(e.hasAttribute('data-mix-close')){close();return;}if(busy)return;
      const busElement=e.closest('[data-mix-bus]'),bus=busElement?mixer.buses[Number(busElement.dataset.mixBus)]:null,track=e.closest('[data-mix-track]'),r=track?route(Number(track.dataset.mixTrack)):null;
      if(e.hasAttribute('data-mix-apply')){void apply();return;}if(e.hasAttribute('data-mix-clear')){void apply(true);return;}
      if(e.hasAttribute('data-mix-add-bus')||e.hasAttribute('data-mix-add-return')){if(mixer.buses.length>=8)return;let n=1;while(mixer.buses.some(b=>b.id==='bus'+n))n++;const delay=e.hasAttribute('data-mix-add-return');mixer.buses.push({id:'bus'+n,name:delay?'Delay return '+n:'Bus '+n,output:'master',gain:1,mute:false,inserts:delay?[clone(inserts.delay)]:[]});}
      else if(e.hasAttribute('data-mix-delete-bus')){mixer.buses=mixer.buses.filter(b=>b!==bus);for(const b of mixer.buses)if(b.output===bus.id)b.output='master';for(const t of mixer.tracks){if(t.output===bus.id)t.output='master';t.sends=t.sends.filter(s=>s.bus!==bus.id);}}
      else if(e.hasAttribute('data-mix-add-insert')){if(bus.inserts.length<4)bus.inserts.push(clone(inserts.highpass));}
      else if(e.hasAttribute('data-mix-delete-insert'))bus.inserts.splice(Number(e.closest('[data-mix-insert]').dataset.mixInsert),1);
      else if(e.hasAttribute('data-mix-add-send')){const target=mixer.buses.find(b=>!r.sends.some(s=>s.bus===b.id));if(target&&r.sends.length<4)r.sends.push({bus:target.id,gain:.25});}
      else if(e.hasAttribute('data-mix-delete-send'))r.sends.splice(Number(e.closest('[data-mix-send]').dataset.mixSend),1);
      render();
    }
    dialog.addEventListener('change',change);dialog.addEventListener('click',click);const cancel=event=>{event.preventDefault();close();};dialog.addEventListener('cancel',cancel);const key=event=>event.stopPropagation();dialog.addEventListener('keydown',key);
    return {open,close,setReport(projectId,report){if(report?.audio_meter)reports.set(projectId,clone(report));if(dialog.open&&project?.id===projectId)$('[data-mix-meter]').textContent=meter();},destroy(){disposed=true;serial++;dialog.removeEventListener('change',change);dialog.removeEventListener('click',click);dialog.removeEventListener('cancel',cancel);dialog.removeEventListener('keydown',key);dialog.remove();style.remove();}};
  }
  function requiresRendered(project){
    if(!project)return false;const library=new Map((project.sequences||[]).map(s=>[s.id,s])),seen=new Set();
    const visit=sequence=>{if(seen.has(sequence))return false;seen.add(sequence);return Boolean(sequence.audio_mixer)||(sequence.clips||[]).some(c=>c.sequence_id&&library.has(c.sequence_id)&&visit(library.get(c.sequence_id)));};
    return visit(project);
  }
  window.CinematicumAudioMixer={mount,requiresRendered};
})();

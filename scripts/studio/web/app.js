/* CINEMATICUM Studio. All editable time values are integer frames; ends are exclusive. */
'use strict';
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = (v) => JSON.parse(JSON.stringify(v));
const uid = () => crypto.randomUUID();
const finite = (v, fallback = 0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const state = {token:'',project:null,projects:[],capabilities:{},selected:null,selectedAsset:null,mode:'edit',frame:0,zoom:48,playing:false,dirty:false,revision:0,history:[],future:[],media:new Map(),job:null,workflowPath:'',rendered:false,lastRenderUrl:'',savePromise:null,drag:null,projectOps:0,navigating:false,editBusy:false};
let toastTimer, animation, playbackOrigin, playbackFrame, audioContext;
let playbackAudioFrame=0,playbackEpoch=0,playbackRequest=0,playbackPreparing=false,playbackAudioUnavailable=false;
let compositorEditor=null, trackingEditor=null, interchangeEditor=null, colorPipelineEditor=null, imagingEditor=null, cameraImporter=null, sceneEditor=null, sceneProjectId='', generationReadiness=null, readinessRequest=0;
const editing=window.CinematicumEditing;
const TRACK_WIDTH=128;
let frameViewer=null, recoveryEditor=null, productionEditor=null, archiveEditor=null, mediaEditor=null, editorialEditor=null, generationEditor=null;
const waveforms=new Map(),waveformPending=new Set(),waveformQueue=[];let waveformActive=0;
const canvas = $('#preview-canvas');
const ctx = canvas.getContext('2d', {alpha:false});
function toast(message, error=false, ms=5500) { const el=$('#toast'); el.textContent=message;el.classList.toggle('error',error);el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{el.hidden=true;},ms); }
async function api(path, {method='GET',body,raw=false}={}) {
  const headers={};if(method!=='GET'){headers['X-Cinematicum-Token']=state.token;headers['Content-Type']=raw?'application/octet-stream':'application/json';}
  const r=await fetch(path,{method,headers,body:body===undefined?undefined:(raw?body:JSON.stringify(body)),cache:'no-store'});
  const data=await r.json().catch(()=>({error:`Server returned ${r.status}`}));
  if(!r.ok)throw Object.assign(Error(typeof data.error==='string'?data.error:(data.message||JSON.stringify(data.error||data))),{status:r.status}); return data;
}
const projectUrl = () => `/api/projects/${encodeURIComponent(state.project.id)}`;
const projectPath = id => `/api/projects/${encodeURIComponent(id)}`;
function projectBusyUI() {
  const busy=state.projectOps>0,editingBlocked=state.navigating||state.editBusy;
  $('#project-select').disabled=busy;$('#new-project').disabled=busy;
  $('#project-form button[type=submit]').disabled=busy;
  $('.workspace').inert=editingBlocked;$('.timeline-panel').inert=editingBlocked;
  $('#recovery-button').disabled=editingBlocked;$('#save-project').disabled=editingBlocked;$('#rename-project').disabled=editingBlocked;
  $('#archive-button').disabled=busy||editingBlocked;
  $('#export-button').disabled=editingBlocked||!Boolean(state.capabilities.ffmpeg?.available??state.capabilities.ffmpeg);
  $$('[data-recipe]').forEach(button=>button.disabled=editingBlocked);
}
function beginProjectOperation() {state.projectOps++;projectBusyUI();return state.project.id;}
function endProjectOperation() {state.projectOps=Math.max(0,state.projectOps-1);projectBusyUI();}
function projectOperationBlocked() {if(state.navigating||state.editBusy){toast('Wait for the current project operation to finish.');return true;}return false;}

const assetById = id => state.project?.assets.find(a=>a.id===id);
const sourceFor = c => c?.sequence_id?window.CinematicumEditorial.sequenceAsset(state.project,c.sequence_id):assetById(c?.asset_id);
const projectSequences = p => [{...p,id:p.sequence_id||'main'},...(p.sequences||[])];
const allTitles = p => projectSequences(p).flatMap(s=>s.titles||[]);
function mergePreparedTitles(target,prepared){const views=projectSequences(target);for(const seq of projectSequences(prepared)){const view=views.find(s=>s.id===seq.id);if(!view)continue;for(const plate of seq.titles||[]){const live=(view.titles||[]).find(t=>t.id===plate.id);if(live&&plate.raster_key===titleKey(live,target)){live.asset_id=plate.asset_id;live.raster_key=plate.raster_key;}}}}
const mediaUrl = a => `${projectUrl()}/media/${encodeURIComponent(a.id)}`;
const thumbnailUrl = a => `${projectUrl()}/thumbnail/${encodeURIComponent(a.id)}`;
const durationFrames = () => Math.max(state.project?.sequence_duration||0,...(state.project?.clips||[]).map(c=>c.start+c.duration),...(state.project?.titles||[]).map(c=>c.start+c.duration),...(state.project?.captions||[]).map(c=>c.start+c.duration));
const fmt = f => window.CinematicumEditorial.formatTimecode(f,state.project||{fps:24});
const rateLabel = (p=state.project) => p?.frame_rate?.denominator>1?`${p.fps.toFixed(3)} fps · ${p.settings?.timecode_mode==='df'?'DF':'NDF'}`:`${p?.fps||24} fps`;
const secondsLabel = s => `${Math.floor(s/60)}:${String(Math.floor(s)%60).padStart(2,'0')}`;
function normalizeProject(p) {p=clone(p.project||p);p.assets??=[];p.clips??=[];p.titles??=[];p.settings??={};p.tracks??=[];p.version??=1;if(p.frame_rate)p.fps=p.frame_rate.numerator/p.frame_rate.denominator;for(const seq of projectSequences(p))(seq.clips||[]).forEach(editing.ensureAnimationDomain);return p;}
function selectedItem() {if(!state.selected)return null;return (state.selected.type==='title'?state.project.titles:state.project.clips).find(c=>c.id===state.selected.id)||null;}
function checkpoint() {state.history.push(clone(state.project));if(state.history.length>80)state.history.shift();state.future=[];}
function changed({timeline=true,inspector=false,bin=false}={}) {pruneMedia();state.frame=clamp(state.frame,0,Math.max(0,durationFrames()-1));if(state.rendered)switchPreview(false);state.dirty=true;state.revision++;$('#save-state').textContent='UNSAVED';$('#save-state').classList.add('dirty');$('#undo-button').disabled=!state.history.length;$('#redo-button').disabled=!state.future.length;if(timeline)renderTimeline();if(inspector)renderInspector();if(bin)renderMedia();updateTransport();drawPreview();frameViewer?.invalidate();recoveryEditor?.schedule();}
function mutate(fn,opts) {checkpoint();fn();changed(opts);}
function undo(redo=false) {
  const from=redo?state.future:state.history,to=redo?state.history:state.future;if(!from.length)return;
  stop();to.push(clone(state.project));
  // Imported and rendered media are immutable inventory, independent of edit history.
  const savedRevision=state.project.revision,assetInventory=state.project.assets;
  state.project=from.pop();state.project.revision=savedRevision;state.project.assets=assetInventory;
  clearMedia();canvas.width=state.project.width;canvas.height=state.project.height;canvas.style.aspectRatio=`${state.project.width}/${state.project.height}`;state.workflowPath=state.project.settings.comfy_workflow_path||'';generationReadiness=null;readinessRequest++;
  if(!selectedItem())state.selected=null;changed({inspector:true,bin:true});renderAll();
}
function titleKey(title,project=state.project) {return JSON.stringify([project.width,project.height,title.text,title.size,title.color,title.x,title.y]);}
async function prepareTitleAssets(project) {
  for(const title of allTitles(project)){
    const signature=titleKey(title,project);
    if(title.asset_id&&title.raster_key===signature&&project.assets.some(a=>a.id===title.asset_id))continue;
    const plate=document.createElement('canvas');plate.width=project.width;plate.height=project.height;
    const draw=plate.getContext('2d');draw.clearRect(0,0,plate.width,plate.height);draw.fillStyle=title.color||'#ffffff';draw.font=`${title.size||48}px sans-serif`;draw.textAlign='center';draw.textBaseline='middle';
    const lines=String(title.text||'').split('\n'),height=(title.size||48)*1.2;
    lines.forEach((line,i)=>draw.fillText(line,plate.width*(.5+(title.x||0)),plate.height*(.5+(title.y||0))+(i-(lines.length-1)/2)*height));
    const blob=await new Promise((resolve,reject)=>plate.toBlob(b=>b?resolve(b):reject(Error('Could not prepare title image.')),'image/png'));
    const imported=await api(`/api/projects/${encodeURIComponent(project.id)}/import?name=${encodeURIComponent('__title_'+title.id+'.png')}`,{method:'POST',raw:true,body:blob});
    const asset=imported.asset||imported;if(!project.assets.some(a=>a.id===asset.id))project.assets.push(asset);
    title.asset_id=asset.id;title.raster_key=signature;
  }
}
async function saveProject(show=true) {
  if(!state.project)return;
  if(state.savePromise){const pendingId=state.project.id,result=await state.savePromise;if(state.project.id!==pendingId)return result;if(state.dirty)return saveProject(show);return result;}
  const projectId=beginProjectOperation();
  $('#save-state').textContent='SAVING…';
  state.savePromise=(async()=>{
    const revision=state.revision,payload=clone(state.project);if(recoveryEditor)payload._recovery=recoveryEditor.receipt();
    await prepareTitleAssets(payload);
    const result=await api(projectPath(payload.id),{method:'PUT',body:payload});
    const saved=normalizeProject(result);
    if(state.project.id===projectId){
      if(revision===state.revision){state.project=saved;state.dirty=false;$('#save-state').classList.remove('dirty');$('#save-state').textContent='SAVED LOCALLY';}
      else {state.project.revision=saved.revision;for(const asset of saved.assets)if(!state.project.assets.some(a=>a.id===asset.id))state.project.assets.push(asset);mergePreparedTitles(state.project,saved);$('#save-state').textContent='UNSAVED';}
    }
    if(show)toast('Project saved.');return result;
  })();
  try{return await state.savePromise;}catch(e){if(state.project.id===projectId)$('#save-state').textContent='SAVE FAILED';throw e;}finally{state.savePromise=null;recoveryEditor?.saved();endProjectOperation();}
}
function releaseMedia(id) {
  const m=state.media.get(id);if(!m)return;
  window.CinematicumAudioRouting?.release(m);
  state.media.delete(id);m.disposed=true;
  for(const [event,listener]of m.listeners||[])m.el.removeEventListener(event,listener);
  m.el.onload=null;m.el.pause?.();
  for(const key of ['source','gain','left','right','split','merge','stereo']){try{m[key]?.disconnect();}catch(error){}}
  m.el.removeAttribute('src');m.el.load?.();
}
function clearMedia() {for(const id of [...state.media.keys()])releaseMedia(id);window.CinematicumSequencePlayback?.clear();}
function pruneMedia(activeIds=null) {
  if(activeIds===null){
    activeIds=new Set((state.project?.clips||[]).filter(c=>state.frame>=c.start&&state.frame<c.start+c.duration).map(c=>c.id));
    for(const [id,m]of state.media)if(!m.nested&&m.ownerClipId&&activeIds.has(m.ownerClipId))activeIds.add(id);
  }
  const clips=new Map((state.project?.clips||[]).map(c=>[c.id,c]));
  for(const [id,m]of state.media){if(m.nested){const asset=assetById(m.assetId);if(!activeIds.has(id)||m.revision!==state.revision||!asset||asset.path!==m.path)releaseMedia(id);continue;}const clip=clips.get(m.ownerClipId||id),asset=clip&&assetById(clip.asset_id);if(!clip||!asset||m.assetId!==asset.id||m.path!==asset.path)releaseMedia(id);}
  // Keep at most twelve inactive decoders warm; active layers are never evicted.
  const inactive=[...state.media.keys()].filter(id=>!activeIds.has(id));
  for(const id of inactive.slice(0,Math.max(0,inactive.length-12)))releaseMedia(id);
}
function adoptProject(p) {stop();clearMedia();generationReadiness=null;readinessRequest++;state.project=normalizeProject(p);state.selected=null;state.selectedAsset=null;state.frame=0;state.dirty=false;state.history=[];state.future=[];state.revision=0;state.workflowPath=state.project.settings.comfy_workflow_path||'';state.lastRenderUrl='';switchPreview(false);$('#rendered-preview').disabled=true;canvas.width=state.project.width;canvas.height=state.project.height;canvas.style.aspectRatio=`${state.project.width}/${state.project.height}`;$('#save-state').textContent='LOCAL PROJECT';$('#save-state').classList.remove('dirty');renderAll();frameViewer?.invalidate();recoveryEditor?.reset();mediaEditor?.reset();}
function renderProjectList() {const found=state.projects.some(p=>p.id===state.project.id);if(!found)state.projects.push({id:state.project.id,name:state.project.name});$('#project-select').innerHTML=state.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.id===state.project.id?state.project.name:p.name)}</option>`).join('');$('#project-select').value=state.project.id;}
function renderAll() {renderProjectList();renderMedia();renderTimeline();renderInspector();updateTransport();renderCapabilities();drawPreview();$('#viewer-project').textContent=state.project.name;$('#project-format').textContent=`${state.project.width} × ${state.project.height}   /   ${rateLabel()}`;}
function renderCapabilities() {const ff=Boolean(state.capabilities.ffmpeg?.available??state.capabilities.ffmpeg);$('#generate-center').textContent=state.capabilities.comfyui?.available?'Generate a shot':'Set up video generation';$('#empty-engine-note').textContent=state.capabilities.comfyui?.available?'YOUR MEDIA · YOUR SCENE · CONNECTED VIDEO ENGINE':'CREATE WITH YOUR MEDIA OR 3D · VIDEO GENERATION REQUIRES SETUP';$('#preview-render').disabled=!ff;$('#export-button').disabled=!ff;$('#preview-render').title=ff?'Render exact timeline preview':'FFmpeg is not installed';$$('[data-export]').forEach(b=>{b.disabled=!ff||state.capabilities[b.dataset.export]===false;b.title=b.disabled?'This encoder is not available in the installed FFmpeg':'';});}
function renderMedia() {
  const all=state.project.assets.filter(a=>!a.name.startsWith('__title_')),term=$('#media-search').value.toLowerCase();const list=all.filter(a=>a.name.toLowerCase().includes(term));
  $('#asset-count').textContent=all.length;
  $('#media-bin').innerHTML=list.length?list.map(a=>`<div class="media-item ${state.selectedAsset===a.id?'selected':''}" data-asset="${esc(a.id)}" draggable="true" tabindex="0" aria-label="${esc(a.name)}; double-click to add to timeline"><div class="media-thumbnail">${['video','image'].includes(a.kind)?`<img loading="lazy" src="${thumbnailUrl(a)}" alt="">`:`<span class="file-icon">${a.kind==='scene'?'◇':'♫'}</span>`}<span class="media-badge">${a.kind==='image'?'STILL':a.kind==='scene'?'3D':secondsLabel(a.duration||0)}</span></div><div class="media-name" title="${esc(a.name)}">${esc(a.name)}</div><button class="media-add" data-add="${esc(a.id)}" title="${a.kind==='scene'?'Select for 3D rendering':'Add to timeline'}" aria-label="Add ${esc(a.name)}">＋</button></div>`).join(''):`<div class="media-empty"><strong>${all.length?'No matching files':'A place for your material.'}</strong>${all.length?'Try a different search.':'Drop video, audio, images,<br>or Blender scenes here.'}</div>`;
}
function defaultClip(a,start=durationFrames(),track=a.kind==='audio'?-1:0) {
  const clip={id:uid(),asset_id:a.id,track,start:Math.round(start),in:0,duration:Math.max(1,a.kind==='image'?Math.round(state.project.fps*5):Math.floor((a.duration||5)*state.project.fps)),volume:1,speed:1,reverse:false,audio:{fade_in:0,fade_out:0,pan:0},opacity:1,x:0,y:0,scale:1,rotation:0,grade:{exposure:0,contrast:1,saturation:1,temperature:0},effects:{blur:0,sharpen:0,vignette:false,chroma_key:''},keyframes:[]};
  // Develop's display image has already passed through its OCIO view. Decode
  // only its sRGB transfer for the timeline's Rec.709 output; do not run the
  // scene view or tone mapping again.
  if(a.provenance?.type==='cinematicum-imaging'&&a.provenance?.version===1&&a.provenance?.display_encoding==='sRGB')clip.color_pipeline={version:1,enabled:true,input_transfer:'srgb',input_primaries:'rec709'};
  return clip;
}
function addAsset(id,start,track) {const a=assetById(id);if(!a)return;if(a.path?.toLowerCase().endsWith('.exr')){state.selectedAsset=id;openImaging('ocio');return;}const destination=track??(a.kind==='audio'?-1:0);if(editing.track(state.project,destination).locked){toast('Unlock the destination track before adding media.');return;}if(a.kind==='scene'){state.selectedAsset=id;setMode('3d');openBlendDialog();return;}const c=defaultClip(a,start??durationFrames(),destination);mutate(()=>{state.project.clips.push(c);state.selected={type:'clip',id:c.id};state.frame=c.start;},{inspector:true});switchPreview(false);}
function select(type,id) {state.selected={type,id};state.selectedAsset=null;renderTimeline();renderInspector();updateTransport();}
function addTitle() {const title={id:uid(),text:'Your title',start:state.frame,duration:Math.round(state.project.fps*3),x:0,y:.32,size:Math.round(state.project.height*.065),color:'#ffffff',fade:Math.round(state.project.fps*.25)};mutate(()=>{state.project.titles.push(title);state.selected={type:'title',id:title.id};},{inspector:true});switchPreview(false);}
function deleteSelected() {if(!selectedItem()||selectionLocked())return;mutate(()=>{const key=state.selected.type==='title'?'titles':'clips';state.project[key]=state.project[key].filter(c=>c.id!==state.selected.id);state.selected=null;},{inspector:true});}
function duplicateSelected() {const item=selectedItem();if(!item||selectionLocked())return;const type=state.selected.type;mutate(()=>{const c=clone(item);c.id=uid();c.start+=c.duration;delete c.planar_motion;state.project[type==='title'?'titles':'clips'].push(c);state.selected={type,id:c.id};},{inspector:true});}
function transformAt(c,frame) {return editing.pose(c,frame);}
function visibleKeys(c) {return (c.keyframes||[]).filter(k=>k.frame-(c.animation_offset??0)>=0&&k.frame-(c.animation_offset??0)<c.duration);}
function preserveAnimation(c,original,offset=0) {
  return editing.preserveAnimation(c,original,offset);
}
function keyPosition(c,local) {
  const frame=Math.round(local+(c.animation_offset??0));
  c.animation_start=Math.min(c.animation_start??0,frame);
  c.animation_duration=Math.max(c.animation_duration??c.duration,frame+1);
  return frame;
}
function splitSelected() {
  const c=selectedItem();if(!c||selectionLocked())return;
  const offset=state.frame-c.start;if(offset<1||offset>=c.duration){toast('Place the playhead inside the selected clip to split it.');return;}
  const type=state.selected.type;
  mutate(()=>{
    const original=clone(c),right=clone(c);right.id=uid();right.start=state.frame;right.duration=c.duration-offset;c.duration=offset;
    if(type==='clip'){
      if(sourceFor(c)?.kind==='image')right.in=0;
      else if(c.reverse){right.in=c.in;c.in+=right.duration*(c.speed??1);}
      else right.in=c.in+offset*(c.speed??1);
      preserveAnimation(c,original);preserveAnimation(right,original,offset);
      if(original.planar_motion?.mode==='stabilize'){delete c.planar_motion;delete right.planar_motion;}
    }else{c.fade=Math.min(c.fade,Math.floor(c.duration/2));right.fade=Math.min(right.fade,Math.floor(right.duration/2));}
    state.project[type==='title'?'titles':'clips'].push(right);state.selected={type,id:right.id};
  },{inspector:true});
}

let trimEditContext=null;
function clearSourceMeasurements(clip,original,local=0) {
  let cleared=Boolean(clip.tracking||clip.planar_motion);delete clip.tracking;delete clip.planar_motion;
  for(const node of clip.compositor?.nodes||[])if(node.tracking_source){
    const previous=original.compositor?.nodes.find(n=>n.id===node.id),params=window.CinematicumCompositor.paramsAt(previous||node,local+(original.animation_offset??0));
    node.params.x=params.x;node.params.y=params.y;
    if(node.animation){delete node.animation.x;delete node.animation.y;if(!Object.keys(node.animation).length)delete node.animation;}
    delete node.tracking_source;cleared=true;
  }
  return cleared;
}
function trimEditPlan() {
  if(!trimEditContext||state.project.id!==trimEditContext.projectId||state.revision!==trimEditContext.revision)throw Error('The project changed. Close and reopen the trim controls.');
  return editing.trimEdit(state.project,trimEditContext.clipId,$('#trim-edit-kind').value,Number($('#trim-edit-delta').value));
}
function updateTrimEdit() {
  try{
    const result=trimEditPlan(),help={slip:'Advance the source along its playback direction. Position, duration, and authored animation stay fixed.',slide:'Move the selected shot and trim both neighbors. The shot’s source and the total sequence duration stay fixed.',roll:'Move the cut after the selected clip. Both source handles and the total sequence duration are respected.'};
    $('#trim-edit-summary').textContent=help[result.kind]+` Applied offset: ${result.delta>0?'+':''}${result.delta} frames.`+(result.limited?' Limited by available source handles or a one-frame neighbor.':'')+' '+result.clips.map(c=>`${sourceFor(c)?.name||'Clip'}: ${c.start}–${c.start+c.duration}`).join(' · ');
    $('#apply-trim-edit').disabled=!result.delta;
  }catch(error){$('#trim-edit-summary').textContent=error.message;$('#apply-trim-edit').disabled=true;}
}
function openTrimEdit() {
  const clip=selectedItem();if(!clip||state.selected.type!=='clip'||selectionLocked()||projectOperationBlocked())return;
  stop();trimEditContext={projectId:state.project.id,revision:state.revision,clipId:clip.id};
  $('#trim-edit-delta').value=1;updateTrimEdit();$('#trim-edit-dialog').showModal();
}
function applyTrimEdit(event) {
  event.preventDefault();
  try{
    const result=trimEditPlan();if(!result.delta)return;
    const original=state.project.clips.find(c=>c.id===trimEditContext.clipId),local=clamp(state.frame-original.start,0,original.duration-1);
    let cleared=false;
    if(result.kind==='slip')cleared=clearSourceMeasurements(result.clips[0],original,local);
    for(const next of result.clips){
      const before=state.project.clips.find(c=>c.id===next.id);
      if(next.planar_motion?.mode==='stabilize'&&before&&['in','duration','speed','reverse','animation_offset'].some(key=>(next[key]??0)!==(before[key]??0))){delete next.planar_motion;cleared=true;}
    }
    const replacements=new Map(result.clips.map(c=>[c.id,c]));
    mutate(()=>{state.project.clips=state.project.clips.map(c=>replacements.get(c.id)||c);if(result.kind==='slide'&&state.frame>=original.start&&state.frame<original.start+original.duration)state.frame+=result.delta;},{inspector:true});
    $('#trim-edit-dialog').close();trimEditContext=null;
    toast(`${result.kind[0].toUpperCase()+result.kind.slice(1)} applied · ${result.delta>0?'+':''}${result.delta} frames.`+(cleared?' Source tracking was cleared; measure the new range again.':''));
  }catch(error){toast(error.message,true);updateTrimEdit();}
}

function setFrame(frame) {state.frame=clamp(Math.round(frame),0,Math.max(0,durationFrames()-1));playbackAudioFrame=state.frame;playbackEpoch++;if(state.playing){playbackFrame=state.frame;playbackOrigin=performance.now();}updateTransport();drawPreview();frameViewer?.invalidate();if(!state.playing&&!state.drag&&state.selected)renderInspector();}
function updateTransport() {const selected=selectedItem();if(state.mode==='composite'&&selected&&state.selected.type==='clip')compositorEditor?.setFrame(clamp(state.frame-selected.start,0,selected.duration-1)+(selected.animation_offset??0));$('#timecode').textContent=fmt(state.frame);$('#duration').textContent=fmt(durationFrames());$('#timeline-stats').textContent=`${state.project?.clips.length||0} clips · ${state.project?.titles.length||0} titles`;const c=selectedItem();$('#split-button').disabled=!c;$('#trim-edit-button').disabled=!c||state.selected?.type!=='clip';$('#duplicate-button').disabled=!c;$('#delete-button').disabled=!c;$('#undo-button').disabled=!state.history.length;$('#redo-button').disabled=!state.future.length;$('#play-button').disabled=!durationFrames();const playhead=$('.timeline-playhead');if(playhead)playhead.style.left=`${TRACK_WIDTH+state.frame/state.project.fps*state.zoom}px`;$('#empty-viewer').hidden=Boolean(state.project?.clips.length||state.project?.titles.length||state.rendered);}
function setMode(mode) {if(projectOperationBlocked())return;state.mode=mode;$$('.mode').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));if(mode==='3d'){stop();$('#render-video').pause();}renderInspector();updatePreviewNote();frameViewer?.invalidate();$('#color-scopes').hidden=mode!=='color';}
function updatePreviewNote() {
  $('#preview-note').textContent=state.rendered?'Rendered timeline · saved render snapshot':state.project?.clips.some(c=>c.reverse)?'Reverse audio plays in rendered preview · paused picture uses the export graph':(state.mode==='color'||state.mode==='composite')?'Current-frame rendering uses the export graph':'Interactive picture and sound · render for final effects';
}
function syncWorkspaces() {
  const isScene=state.mode==='3d',isComposite=state.mode==='composite';
  $('#app').dataset.workspace=state.mode;$('.viewer-panel').hidden=isScene;$('.inspector-panel').hidden=isScene;$('#scene-workspace').hidden=!isScene;$('#compositor-workspace').hidden=!isComposite;
  if(isComposite&&window.CinematicumCompositor){
    const mediaRecord=a=>a?{id:a.id,name:a.name,kind:a.kind,duration:a.duration,width:a.width,height:a.height,color_transfer:a.color_transfer,path:a.path,imaging_source:a.imaging_source,thumbnailUrl:thumbnailUrl(a)}:null;
    compositorEditor??=window.CinematicumCompositor.mount($('#compositor-workspace'),{toast,renderAvailable:()=>Boolean(state.capabilities.ffmpeg?.available??state.capabilities.ffmpeg),listMedia:()=>state.project.assets.filter(a=>['video','image'].includes(a.kind)&&!a.name.startsWith('__title_')).map(mediaRecord),getMedia:id=>mediaRecord(assetById(id)),getSceneCamera:()=>({camera:state.project.settings.scene?.camera,width:state.project.width,height:state.project.height}),onImport:()=>$('#media-input').click(),onRender:()=>startRender('preview'),onSeek:domain=>{const item=selectedItem();if(!item||state.selected?.type!=='clip')return false;stop();switchPreview(false);setFrame(clamp(item.start+domain-(item.animation_offset??0),item.start,item.start+item.duration-1));return state.frame-item.start+(item.animation_offset??0);},onChange:(graph,key)=>{if(projectOperationBlocked())return false;const item=selectedItem();if(!item||state.selected.type!=='clip'||key!==state.project.id+':'+item.id||selectionLocked())return false;mutate(()=>{item.compositor=graph;},{timeline:false});return true;}});
    const item=selectedItem(),asset=item?.asset_id?assetById(item.asset_id):null,valid=state.selected?.type==='clip'&&item.track>=0&&['video','image'].includes(asset?.kind);
    compositorEditor.setContext(valid?{key:state.project.id+':'+item.id,graph:item.compositor,sourceLabel:asset.name,sourceThumb:thumbnailUrl(asset),sourceAssetId:asset.id,graphWidth:Math.max(2,Math.trunc(asset.width*Math.min(state.project.width/asset.width,state.project.height/asset.height)/2)*2),graphHeight:Math.max(2,Math.trunc(asset.height*Math.min(state.project.width/asset.width,state.project.height/asset.height)/2)*2),fps:state.project.fps,clipDuration:item.duration,clipOffset:item.animation_offset??0,frame:clamp(state.frame-item.start,0,item.duration-1)+(item.animation_offset??0),animationStart:item.animation_start??0,animationDuration:item.animation_duration??item.duration}:{key:''});
  }
  if(isScene&&window.CinematicumSceneEditor){
    const project=state.project,options={width:project.width,height:project.height,fps:project.fps,renderAvailable:Boolean(state.capabilities.blender?.available??state.capabilities.blender)},scene=project.settings.scene||window.CinematicumSceneEditor.defaultScene({width:project.width,height:project.height,frame_end:Math.round(project.fps*4)});
    if(!sceneEditor||sceneProjectId!==project.id){sceneEditor?.destroy();sceneProjectId=project.id;const capturedId=project.id;sceneEditor=window.CinematicumSceneEditor.mount($('#scene-module'),{...options,scene,onChange:next=>{if(state.project.id!==capturedId||projectOperationBlocked())return false;mutate(()=>{state.project.settings.scene=clone(next);},{timeline:false});return true;},onImportMesh:payload=>{if(state.project.id!==capturedId||projectOperationBlocked())throw Error('The project changed before mesh import.');return api(projectPath(capturedId)+'/scene/import-obj',{method:'POST',body:payload});},onModelMesh:payload=>startModelMesh(payload,capturedId),onImportCamera:()=>{if(state.project.id!==capturedId)throw Error('The project changed before camera import.');openCameraImport();},onRender:payload=>{if(state.project.id!==capturedId)throw Error('The project changed before scene submission.');return startSceneRender(payload);}});}
    else sceneEditor.setScene(scene,options);
  }
}
function openBlendDialog() {
  const ready=Boolean(state.capabilities.blender?.available??state.capabilities.blender),scenes=state.project.assets.filter(asset=>asset.kind==='scene');
  $('#blend-dialog-content').innerHTML=`<p class="muted">Render an existing .blend with its camera, lighting, materials, and animation. Pack linked resources in Blender before importing.</p><label>Scene<select id="blender-scene">${scenes.length?scenes.map(scene=>`<option value="${esc(scene.path)}" ${scene.id===state.selectedAsset?'selected':''}>${esc(scene.name)}</option>`).join(''):'<option value="">Import a .blend file first</option>'}</select></label><button id="import-scene" class="full" style="margin-top:12px">Import .blend</button><div class="field-row"><label>Start frame<input id="blender-start" type="number" min="1" max="100000" step="1" value="1"></label><label>End frame<input id="blender-end" type="number" min="1" max="100000" step="1" value="120"></label></div><button id="blender-button" class="primary full" style="margin-top:18px" ${!ready||!scenes.length?'disabled':''}>Render scene</button>${ready?'':'<p class="muted">Blender is not available on the configured path.</p>'}`;
  $('#blend-dialog').showModal();
}
function openProduction() {
  if(projectOperationBlocked())return;stop();
  productionEditor??=window.CinematicumProduction.mount(document.body,{
    request:api,getProject:()=>clone(state.project),getContext:()=>({projectId:state.project.id,revision:state.revision}),notify:toast,
    onApply:(candidate,expected)=>{
      if(projectOperationBlocked()||state.project.id!==expected.projectId||state.revision!==expected.revision||candidate.revision!==state.project.revision)throw Error('The project changed. Reopen Production before applying.');
      mutate(()=>{state.project=normalizeProject(candidate);state.selected=null;state.selectedAsset=null;clearMedia();canvas.width=state.project.width;canvas.height=state.project.height;canvas.style.aspectRatio=`${state.project.width}/${state.project.height}`;},{inspector:true,bin:true});
      renderAll();return true;
    }
  });productionEditor.open();
}
async function submitArchive(kind, selected, expected) {
  if(state.projectOps||projectOperationBlocked())throw Error('Wait for the current project operation to finish.');
  if(state.job&&['queued','running'].includes(String(state.job.state).toLowerCase()))throw Error('Wait for the current job or cancel it first.');
  if(state.project.id!==expected.projectId||state.revision!==expected.revision)throw Error('The edit changed. Reopen Archive before submitting.');
  state.editBusy=true;const projectId=beginProjectOperation();stop();
  try {
    const saved=state.dirty?normalizeProject(await saveProject(false)):clone(state.project);
    if(saved.id!==projectId||state.project.id!==projectId||state.revision!==expected.revision)throw Error('The project changed before the archive could be submitted.');
    const restoring=kind==='archive-restore';
    const job=await api(projectPath(projectId)+'/'+kind,{method:'POST',raw:restoring,body:restoring?selected:{project:saved}});
    trackJob(job,restoring?'Restoring project archive':'Creating project archive',kind,projectId);
    return job;
  } finally {state.editBusy=false;endProjectOperation();}
}
function openArchive() {
  if(state.projectOps||projectOperationBlocked())return;stop();
  archiveEditor??=window.CinematicumArchive.mount(document.body,{
    request:api,getProject:()=>clone(state.project),getContext:()=>({projectId:state.project.id,revision:state.revision}),notify:toast,
    onExport:(snapshot,expected)=>submitArchive('archive-export',snapshot,expected),
    onRestore:(file,expected)=>submitArchive('archive-restore',file,expected)
  });archiveEditor.open();
}
async function openRestoredProject() {
  const id=$('#open-restored-project').dataset.projectId;
  if(!/^[a-f0-9]{32}$/.test(id||'')||state.projectOps||projectOperationBlocked())return;
  state.navigating=true;beginProjectOperation();
  try {if(state.dirty)await saveProject(false);adoptProject(await api(projectPath(id)));$('#open-restored-project').hidden=true;toast('Restored project opened.');}
  catch(error){toast(error.message,true);}
  finally{state.navigating=false;endProjectOperation();}
}
function openCameraImport() {
  if(projectOperationBlocked()||!window.CinematicumCameraIO)return;
  stop();
  cameraImporter??=window.CinematicumCameraIO.mount(document.body,{
    getContext:()=>({projectId:state.project.id,revision:state.revision,width:state.project.width,height:state.project.height}),
    onImport:payload=>api(projectPath(state.project.id)+'/scene/import-camera',{method:'POST',body:payload}),
    onApply:(camera,expected,source)=>{
      if(projectOperationBlocked()||state.project.id!==expected.projectId||state.revision!==expected.revision)throw Error('The project changed. Reopen camera import before applying.');
      const next=clone(state.project.settings.scene||sceneEditor?.getScene()||window.CinematicumSceneEditor.defaultScene({width:state.project.width,height:state.project.height,frame_end:Math.round(state.project.fps*4)}));
      next.camera=clone(camera);next.camera.keyframes=[];
      mutate(()=>{state.project.settings.scene=next;state.project.settings.camera_import={source:clone(source||{}),imported_at:new Date().toISOString()};},{timeline:false,inspector:true});
      sceneEditor?.showCamera();
      return true;
    },notify:toast
  });
  cameraImporter.open();
}
function openColorPipeline() {
  const clip=selectedItem(),asset=assetById(clip?.asset_id);
  if(projectOperationBlocked()||selectionLocked()||state.selected?.type!=='clip'||clip.track<0||!['video','image'].includes(asset?.kind))return;
  if(!window.CinematicumColorPipeline)throw Error('Color controls did not load. Reopen CINEMATICUM.');
  stop();
  colorPipelineEditor??=window.CinematicumColorPipeline.mount(document.body,{
    request:api,getClip:()=>clone(selectedItem()),
    getContext:()=>({projectId:state.project.id,revision:state.revision,clipId:state.selected?.id}),
    onApply:(pipeline,expected)=>{
      const current=selectedItem();
      if(projectOperationBlocked()||selectionLocked()||state.project.id!==expected.projectId||state.revision!==expected.revision||state.selected?.type!=='clip'||current?.id!==expected.clipId)throw Error('The selected clip changed. Reopen its color controls before applying.');
      mutate(()=>{if(pipeline===null)delete current.color_pipeline;else current.color_pipeline=clone(pipeline);},{timeline:false,inspector:true});
      return true;
    },notify:toast
  });
  colorPipelineEditor.open();
}
function openImaging(operation) {
  if(projectOperationBlocked()||!window.CinematicumImaging)return;
  stop();
  imagingEditor??=window.CinematicumImaging.mount(document.body,{
    request:api,getProject:()=>state.project,getContext:()=>({projectId:state.project.id,revision:state.revision}),notify:toast,
    onComplete:async(result,context)=>{
      if(state.project.id!==context.projectId)return;
      const fresh=await api(projectPath(context.projectId));
      if(state.project.id!==context.projectId)return;
      const known=new Set(state.project.assets.map(a=>a.id));
      for(const asset of fresh.assets||[])if(!known.has(asset.id)){state.project.assets.push(asset);known.add(asset.id);}
      if(result.asset?.id)state.selectedAsset=result.asset.id;
      renderMedia();toast('Processed image is in Media. Double-click it to add it to the timeline.');
    }
  });
  const asset=assetById(state.selectedAsset)||assetById(selectedItem()?.asset_id);
  imagingEditor.open({operation,assetId:asset?.kind==='image'?asset.id:undefined});
}
async function startModelMesh(payload,expectedProjectId) {
  if(projectOperationBlocked()||state.project.id!==expectedProjectId)throw Error('The project changed before mesh evaluation.');
  if(state.job&&['queued','running'].includes(state.job.state))throw Error('Wait for the current job or cancel it first.');
  const revision=state.revision,projectId=beginProjectOperation();
  try{
    const initial=await api(projectPath(projectId)+'/scene/model-mesh',{method:'POST',body:payload});
    const job=await trackJob(initial,'Evaluating mesh','scene-modeling',projectId);
    if(job?.state!=='completed')throw Error(job?.error||'Mesh evaluation did not complete.');
    if(state.project.id!==projectId||state.revision!==revision)throw Error('The project changed during mesh evaluation. Repeat the edit on the current scene.');
    return job.result;
  }finally{endProjectOperation();}
}
async function startSceneRender({scene,frame_start,frame_end}) {
  if(projectOperationBlocked())throw Error('Wait for the current project operation to finish.');
  if(state.job&&['queued','running'].includes(String(state.job.state).toLowerCase()))throw Error('Wait for the current job or cancel it first.');
  const projectId=beginProjectOperation(),snapshot=clone(scene);
  try{if(JSON.stringify(state.project.settings.scene)!==JSON.stringify(snapshot))mutate(()=>{state.project.settings.scene=snapshot;},{timeline:false});await saveProject(false);const job=await api(`${projectPath(projectId)}/scene`,{method:'POST',body:{scene:snapshot,frame_start,frame_end}});trackJob(job,'Rendering your 3D scene','scene',projectId);}catch(error){toast(error.message,true,10000);throw error;}finally{endProjectOperation();}
}
const field = (label,path,value,{min=0,max=999999,step=1,type='number'}={}) => `<label>${label}<input type="${type}" data-field="${path}" value="${esc(value)}" min="${min}" max="${max}" step="${step}"></label>`;
const range = (label,path,value,min,max,step=0.01) => `<div class="range-field"><div class="control-row"><label for="ctrl-${path.replaceAll('.','-')}">${label}</label><output>${finite(value).toFixed(step>=1?0:2)}</output></div><input id="ctrl-${path.replaceAll('.','-')}" type="range" data-field="${path}" value="${value}" min="${min}" max="${max}" step="${step}"></div>`;
function renderInspector() {
  syncWorkspaces();
  const el=$('#inspector'),c=selectedItem(),a=state.selected?.type==='clip'?sourceFor(c):null;
  $('#inspector-heading').textContent={edit:'Inspector',color:'Color',composite:'Composite',generate:'Generate', '3d':'3D',audio:'Audio mixer'}[state.mode];$('#selection-kind').textContent=c?(state.selected.type==='title'?'TITLE':a?.kind?.toUpperCase()||''):'';
  if(state.mode==='audio'){el.innerHTML=renderMixer();return;}
  if(state.mode==='generate'){const ready=Boolean(state.capabilities.comfyui?.available),check=generationReadiness?.projectId===state.project.id?generationReadiness:null;el.innerHTML=`<div class="inspector-name">Generate into your project</div><button id="manage-generation" class="full">Local generation setup</button><p class="note">Generate a take, then edit its picture and sound in this project.</p><div class="engine-note ${ready?'ready':''}">${ready?'Video generation engine connected.':esc(state.capabilities.comfyui?.reason||'Use Local generation setup to install and start the video engine.')}</div><label>Prompt<textarea id="generate-prompt" placeholder="Describe the shot, its movement, and its light.">${esc(state.project.settings.last_prompt||'')}</textarea></label><label>Negative prompt${state.project.settings.comfy_bindings?.negative===false?' · fixed by workflow':''}<textarea ${state.project.settings.comfy_bindings?.negative===false?'disabled':''} id="generate-negative" style="min-height:50px" placeholder="Elements to avoid">${esc(state.project.settings.last_negative||'')}</textarea></label><div class="field-row"><label>Seed${state.project.settings.comfy_bindings?.seed===false?' · fixed by workflow':''}<input ${state.project.settings.comfy_bindings?.seed===false?'disabled':''} id="generate-seed" type="number" min="0" max="2147483647" step="1" value="${finite(state.project.settings.last_seed,42)}"></label><label>Workflow<button id="choose-workflow" class="full" style="margin-top:6px">Import API JSON</button></label></div><p id="workflow-label" class="note">${state.workflowPath?'Workflow selected.':'Apply shot settings in Local generation setup, or import an API workflow.'}</p><button id="validate-workflow" class="full" style="margin-top:12px" ${!ready||!state.workflowPath?'disabled':''}>Validate workflow</button>${check?`<div class="engine-note ${check.ready?'ready':''}">${check.ready?`Workflow checked · ${check.checked_nodes||0} nodes available.`:esc(check.reason||check.errors?.[0]||'Workflow is not ready.')}${check.errors?.length>1?'<br>'+check.errors.slice(1,4).map(esc).join('<br>'):''}</div>`:''}<button id="generate-button" class="primary full" style="margin-top:16px" ${!ready||!state.workflowPath||check?.ready===false?'disabled':''}>Generate media</button><p class="note">Local generation setup supplies the Wan model and shot workflow. You can also import a compatible API workflow for a separately configured engine.</p>`;return;}
  if(state.mode==='3d')return;
  if(!c){el.innerHTML=`<div class="inspector-empty"><svg width="29" height="29" viewBox="0 0 30 30" fill="none" aria-hidden="true"><path d="M7 4v22l6-7 6 1L7 4Z" stroke="currentColor" stroke-width="1.3"/></svg><strong>Select a clip to ${state.mode==='color'?'grade it':state.mode==='composite'?'shape the image':'start editing'}.</strong>Click a clip in the timeline.<br>Changes are saved with your project.</div>${state.mode==='composite'?'<div class="inspector-section"><h3>MOTION GRAPHICS</h3><button class="full" data-action="add-title">Add a title</button></div>':''}`;return;}
  if(c.caption_id){el.innerHTML=`<div class="inspector-name">Caption</div><p class="note">${esc(c.text)}</p><p class="note">${fmt(c.start)} → ${fmt(c.start+c.duration)}</p><button class="full" data-action="captions">Edit cue and caption appearance</button>`;return;}
  const timing=`<div class="inspector-section"><h3>TIMING · FRAMES</h3><div class="field-row">${field('Timeline start','start',c.start)}${state.selected.type==='clip'&&a?.kind!=='image'?field('Source in','in',c.in,{step:.01}):''}</div><div class="field-row">${field('Duration','duration',c.duration,{min:1})}<label>Timeline end<input readonly value="${c.start+c.duration}" title="Exclusive end frame"></label></div><p class="note">${fmt(c.start)} → ${fmt(c.start+c.duration)} · ${rateLabel()}</p></div>`;
  if(state.selected.type==='title'){el.innerHTML=`<div class="inspector-name">Title</div><div class="inspector-section"><label>Text<textarea data-field="text" maxlength="2000">${esc(c.text)}</textarea></label><div class="field-row">${field('Size (px)','size',c.size,{min:6,max:500})}${field('Fade (frames)','fade',c.fade,{min:0,max:Math.floor(c.duration/2)})}</div><div class="color-control"><label>Text color</label><input type="color" data-field="color" value="${esc(c.color)}"></div>${range('Horizontal position','x',c.x,-1,1)}${range('Vertical position','y',c.y,-1,1)}</div>${timing}<div class="inspector-actions"><button data-action="duplicate">Duplicate</button><button data-action="delete">Delete</button></div>`;return;}
  const top=`<div class="inspector-name">${esc(a?.name||'Missing media')}</div><div class="inspector-meta">${a?.width?`${a.width} × ${a.height} · `:''}${a?.kind||'media'} · ${(c.duration/state.project.fps).toFixed(2)}s</div>${a?.kind==='video'&&c.track>=0?'<button class="full tracking-open" data-action="track">Track motion'+(c.tracking||c.planar_motion?.mode==='stabilize'?' · stabilized':'')+'</button>':''}${c.planar_motion?'<button class="full" data-action="clear-planar">Remove planar '+(c.planar_motion.mode==='corner_pin'?'corner pin':'stabilization')+'</button>':''}`;
  if(state.mode==='color'){if(c.track<0||a?.kind==='audio'){el.innerHTML=`${top}<p class="note">Select a picture clip to change its color.</p>`;return;}const g=c.grade||{};el.innerHTML=`${top}<div class="inspector-section"><h3>COLOR PIPELINE</h3><button class="full" data-action="color-pipeline">Input transform, white balance & LUT</button><p class="note">${c.color_pipeline?.enabled?esc(c.color_pipeline.input_transfer+' / '+c.color_pipeline.input_primaries)+(c.color_pipeline.lut?' · LUT applied':''):'Rec.709 SDR · no input transform'}</p></div><div class="inspector-section"><h3>PRIMARY CORRECTION</h3>${range('Exposure · stops','grade.exposure',g.exposure??0,-3,3)}${range('Contrast','grade.contrast',g.contrast??1,0,3)}${range('Saturation','grade.saturation',g.saturation??1,0,3)}${range('Temperature','grade.temperature',g.temperature??0,-1,1)}</div><div class="inspector-actions"><button data-action="reset-color">Reset primary correction</button><button data-action="preview">Render preview</button></div><p class="note">The viewer renders the current frame through the export graph. The scopes measure that rendered image.</p>`;return;}
  if(state.mode==='composite'){const e=c.effects||{},pose=transformAt(c,state.frame-c.start);el.innerHTML=`${top}<div id="node-inspector" class="node-inspector"></div><details class="clip-transform-details"><summary>Clip placement & motion</summary><div class="inspector-section"><h3>TRANSFORM & MOTION</h3>${range('Horizontal position','x',pose.x,-2,2)}${range('Vertical position','y',pose.y,-2,2)}${range('Scale','scale',pose.scale,.02,4)}${range('Rotation · degrees','rotation',pose.rotation||0,-360,360,1)}${range('Opacity','opacity',pose.opacity,0,1)}<button data-action="keyframe" class="full" style="margin-top:14px">◇ Set pose & gain keyframe</button><div class="keyframe-list">${visibleKeys(c).map(k=>`<span class="keyframe-chip"><button data-jump-key="${k.frame}">${k.frame-(c.animation_offset??0)}f</button><select aria-label="Interpolation after frame ${k.frame}" data-key-easing="${k.frame}">${Object.keys(editing.easings).map(mode=>`<option value="${mode}" ${(k.interpolation||'linear')===mode?'selected':''}>${mode.replaceAll('_',' ')}</option>`).join('')}</select> <button data-remove-key="${k.frame}" aria-label="Delete keyframe at frame ${k.frame}">×</button></span>`).join('')}</div><p class="note">Keyframes animate position, scale, rotation, opacity, and gain. With keyframes present, changing a slider writes one at the playhead.</p></div><div class="inspector-section"><h3>EFFECTS</h3>${range('Blur','effects.blur',e.blur||0,0,30,.1)}${range('Sharpen','effects.sharpen',e.sharpen||0,0,3,.05)}<label class="check-field"><input type="checkbox" data-field="effects.vignette" ${e.vignette?'checked':''}> Vignette</label><div class="color-control"><label class="check-field"><input type="checkbox" id="chroma-enabled" ${e.chroma_key?'checked':''}> Chroma key</label><input id="chroma-color" type="color" value="${esc(e.chroma_key||'#00ff00')}" aria-label="Chroma key color"></div></div><div class="inspector-actions"><button data-action="reset-transform">Reset transform</button><button data-action="preview">Render preview</button></div><p class="note">Render preview evaluates chroma key, sharpening, vignette, and the complete composite.</p></details>`;compositorEditor?.renderInspector($('#node-inspector'));return;}
  el.innerHTML=`${top}${timing}<div class="inspector-section"><h3>RETIME</h3>${field('Playback speed','speed',c.speed??1,{min:.25,max:4,step:.25})}<label class="check-field"><input type="checkbox" data-field="reverse" ${c.reverse?'checked':''}> Reverse selected source range</label><p class="note">Changing speed preserves the selected source range. Rendered playback includes reversed sound.</p></div><div class="inspector-section"><h3>AUDIO</h3>${range('Clip gain','volume',transformAt(c,state.frame-c.start).volume,0,4)}${range('Stereo balance','audio.pan',c.audio?.pan||0,-1,1,.01)}<div class="field-row">${field('Fade in · frames','audio.fade_in',c.audio?.fade_in||0,{min:0,max:Math.max(c.duration,c.audio?.fade_duration||0)})}${field('Fade out · frames','audio.fade_out',c.audio?.fade_out||0,{min:0,max:Math.max(c.duration,c.audio?.fade_duration||0)})}</div><p class="note">${a?.has_audio||a?.kind==='audio'?'Gain 1.00 is original level. Gain 0.00 mutes this clip.':'This source has no audio stream.'}</p></div><div class="inspector-section"><h3>LAYER</h3><label>Track<select data-field="track">${[...new Set(editing.tracks(state.project).filter(t=>a?.kind==='audio'?t.id<0:t.id>=0).map(t=>t.id).concat(c.track))].map(t=>`<option value="${t}" ${c.track===t?'selected':''}>${t<0?'A'+Math.abs(t):'V'+(t+1)}${t===0?' · base picture':''}</option>`).join('')}</select></label></div><div class="inspector-actions"><button data-action="duplicate">Duplicate</button><button data-action="delete">Delete</button></div>`;
}
function normalizeFades(clip,field='') {
  if(!clip.audio)return;
  const a=clip.audio;
  if(field==='audio.fade_in'||field==='audio.fade_out'){a.fade_duration=clip.duration;a.fade_offset=0;}
  const domain=a.fade_duration??clip.duration;
  a.fade_in=Math.min(a.fade_in||0,domain);a.fade_out=Math.min(a.fade_out||0,domain);
  const sum=a.fade_in+a.fade_out;if(sum<=domain)return;
  if(field==='audio.fade_in')a.fade_out=domain-a.fade_in;
  else if(field==='audio.fade_out')a.fade_in=domain-a.fade_out;
  else {a.fade_in=Math.round(a.fade_in/sum*domain);a.fade_out=domain-a.fade_in;}
}
function trackingContext(projectId=state.project.id,clipId=state.selected?.id) {
  if(state.project.id!==projectId||state.selected?.type!=='clip'||state.selected.id!==clipId)return null;
  const clip=selectedItem(),asset=assetById(clip?.asset_id);if(!clip||asset?.kind!=='video'||clip.track<0)return null;
  return {project:clone(state.project),clip:clone(clip),asset:clone(asset),frame:state.frame};
}
function applyTracking(kind,motion,source,options={}) {
  const context=trackingContext();if(!context||projectOperationBlocked()||selectionLocked())return false;
  const clip=selectedItem(),asset=context.asset,p=state.project;
  if(source){const identity={asset_id:asset.id,sha256:asset.sha256,width:asset.width,height:asset.height,clip_id:clip.id,in:clip.in,duration:clip.duration,speed:clip.speed??1,reverse:clip.reverse??false,animation_offset:clip.animation_offset??0,frame_rate:p.frame_rate||{numerator:p.fps,denominator:1}};if(Object.keys(identity).some(key=>JSON.stringify(identity[key])!==JSON.stringify(source[key]))){toast('The clip timing changed. Measure this source range again.',true);return false;}}
  if(kind==='planar-stabilize'){
    if(!motion||motion.mode!=='stabilize'){toast('The measurement did not return planar stabilization.',true);return false;}
    mutate(()=>{clip.planar_motion=clone(motion);delete clip.tracking;},{inspector:true});
  }else if(kind==='corner-pin'){
    const image=assetById(options.asset_id),first=options.frame_start,count=options.frame_count;
    if(image?.kind!=='image'||!Number.isInteger(first)||!Number.isInteger(count)||first<0||count<1||first+count>clip.duration||motion?.mode!=='corner_pin'){toast('Choose an imported image and a valid measured plane range.',true);return false;}
    const start=clip.start+first,end=start+count;let track=clip.track+1;
    while(track<16&&(editing.track(p,track).locked||p.clips.some(c=>c.track===track&&c.start<end&&c.start+c.duration>start)))track++;
    if(track>=16){toast('A free video track above this clip is required for the corner-pin image.',true);return false;}
    const overlay=defaultClip(image,start,track);overlay.duration=count;overlay.volume=0;
    overlay.animation_start=clip.animation_start??0;overlay.animation_duration=clip.animation_duration??clip.duration;
    overlay.animation_offset=(clip.animation_offset??0)+first;overlay.planar_motion=clone(motion);
    for(const key of ['x','y','scale','rotation'])overlay[key]=clip[key]??(key==='scale'?1:0);
    overlay.keyframes=(clip.keyframes||[]).map(key=>Object.fromEntries(Object.entries(key).filter(([name])=>['frame','interpolation','x','y','scale','rotation'].includes(name)))).filter(key=>Object.keys(key).some(name=>['x','y','scale','rotation'].includes(name)));
    mutate(()=>{p.clips.push(overlay);},{inspector:true});
  }else if(kind==='mask'){
    const graph=clone(clip.compositor||window.CinematicumCompositor.defaultGraph()),anchor=motion.source.reference_point;
    const id='tracked_'+uid().replaceAll('-',''),keys=motion.keys;
    const params={shape:'ellipse',x:anchor[0]-editing.measuredValue(keys,'x',0),y:anchor[1]-editing.measuredValue(keys,'y',0),width:.2,height:.2,rotation:0,feather:.1,invert:false,points:[[.1,.85],[.5,.1],[.9,.85]]};
    graph.nodes.push({id,type:'mask',inputs:[graph.output],params,tracking_source:{version:1,sha256:motion.source.track_sha256,backend:motion.source.track_backend},position:{x:240+graph.nodes.length*190,y:62},animation:{x:keys.map(k=>({frame:k.frame,value:anchor[0]-k.x,interpolation:'linear'})),y:keys.map(k=>({frame:k.frame,value:anchor[1]-k.y,interpolation:'linear'}))}});graph.output=id;
    const issue=window.CinematicumCompositor.validate(graph,{animationStart:clip.animation_start??0,animationDuration:clip.animation_duration??clip.duration});if(issue){toast(issue,true);return false;}
    mutate(()=>{clip.compositor=graph;},{inspector:true});
  }else if(kind==='clear')mutate(()=>{delete clip.tracking;delete clip.planar_motion;},{inspector:true});
  else mutate(()=>{clip.tracking=clone(motion);},{inspector:true});
  return true;
}
function openTracking() {
  if(projectOperationBlocked()||selectionLocked())return;const context=trackingContext();if(!context)return;
  stop();trackingEditor??=window.CinematicumTracking.mount({request:api,current:trackingContext,apply:applyTracking,capabilities:()=>state.capabilities});trackingEditor.open(context);
}
function writeField(path,value,{checkpointFirst=true}={}) {
  const c=selectedItem();if(!c||selectionLocked())return;
  if(path==='track'&&editing.track(state.project,value).locked){toast('Unlock the destination track before moving this clip.');return;}
  const animated=editing.properties.includes(path)&&c.keyframes?.length;
  const local=clamp(state.frame-c.start,0,c.duration-1),domainFrame=local+(c.animation_offset??0);
  if(animated&&c.keyframes.length>=128&&!c.keyframes.some(k=>k.frame===domainFrame)){toast('This clip already has 128 keyframes.');return;}
  const previous=clone(c);if(checkpointFirst)checkpoint();
  const keys=path.split('.');let target=c;for(const k of keys.slice(0,-1)){target[k]??={};target=target[k];}target[keys.at(-1)]=value;
  if(state.selected.type==='title'&&['text','size','color','x','y'].includes(path)){delete c.asset_id;delete c.raster_key;}
  if(['start','duration','track','size','fade','audio.fade_in','audio.fade_out'].includes(path))target[keys.at(-1)]=Math.round(value);
  if(c.start!==undefined)c.start=Math.max(0,Math.round(c.start));if(c.in!==undefined)c.in=Math.max(0,c.in);c.duration=Math.max(1,Math.round(c.duration));
  if(state.selected.type==='clip'){
    if(path==='speed'){
      const ratio=(previous.speed??1)/c.speed;c.duration=Math.max(1,Math.floor(previous.duration*ratio));
      c.animation_start=Math.round((previous.animation_start??0)*ratio);
      c.animation_offset=Math.round((previous.animation_offset??0)*ratio);
      c.animation_duration=Math.max(1,Math.round((previous.animation_duration??previous.duration)*ratio));
      c.keyframes=(previous.keyframes||[]).map(k=>({...k,frame:Math.round(k.frame*ratio)})).filter((k,i,arr)=>arr.findIndex(x=>x.frame===k.frame)===i);
      c.animation_duration=Math.max(c.animation_duration,...c.keyframes.map(k=>k.frame+1));editing.retimeExtraChannels(c,ratio);
      if(c.audio){c.audio.fade_duration=Math.max(1,Math.round((previous.audio?.fade_duration??previous.duration)*ratio));c.audio.fade_offset=Math.round((previous.audio?.fade_offset??0)*ratio);c.audio.fade_in=Math.round((previous.audio?.fade_in||0)*ratio);c.audio.fade_out=Math.round((previous.audio?.fade_out||0)*ratio);}
    }else if(['in','duration'].includes(path))preserveAnimation(c,previous);
    const a=sourceFor(c);
    if(path==='duration'&&a){const trimmed=editing.trim(previous,'right',previous.start+c.duration,['video','audio','sequence'].includes(a.kind)?a.duration*state.project.fps:Infinity,a.kind==='image');c.in=trimmed.in;c.duration=trimmed.duration;}
    if((['in','reverse'].includes(path)||c.planar_motion&&['speed','duration'].includes(path))&&value!==previous[path]){
      const cleared=clearSourceMeasurements(c,previous,local);
      if(cleared)toast('Source timing changed. Measured motion was cleared; track this range again. Undo restores it.');
    }
    if(a?.kind==='image')c.in=0;
    if(a&&['video','audio','sequence'].includes(a.kind)){const max=a.duration*state.project.fps,speed=c.speed??1;c.in=Math.min(c.in,Math.max(0,max-speed));c.duration=Math.min(c.duration,Math.max(1,Math.floor((max-c.in)/speed+1e-8)));}
    if(animated){
      const frame=keyPosition(c,local),existing=c.keyframes.find(k=>k.frame===frame),interpolation=existing?.interpolation||'linear';
      c[path]=previous[path];c.keyframes=c.keyframes.filter(k=>k.frame!==frame);c.keyframes.push({...existing,frame,interpolation,[path]:value});c.keyframes.sort((a,b)=>a.frame-b.frame);
    }
    normalizeFades(c,path);
  }else c.fade=Math.min(c.fade,Math.floor(c.duration/2));
  changed({timeline:!['grade','effects'].some(k=>path.startsWith(k)),inspector:false});
}

function renderTimeline() {
  if(!state.project)return;
  const sec=Math.max(15,durationFrames()/state.project.fps+4),width=Math.max($('#timeline-scroll').clientWidth-TRACK_WIDTH,Math.ceil(sec*state.zoom));
  const tickStep=state.zoom<23?5:state.zoom<55?2:1;let ticks='';
  for(let t=0;t<=width/state.zoom;t+=tickStep)ticks+=`<span class="ruler-tick" style="left:${t*state.zoom}px">${secondsLabel(t)}</span>`;
  const rows=[{id:'titles',name:'Titles'},...editing.tracks(state.project)];
  const content=rows.map(track=>{
    const title=track.id==='titles',items=title?state.project.titles:state.project.clips.filter(c=>c.track===track.id);
    const controls=title?'':`<div class="track-controls">${[['mute','M','Mute'],['solo','S','Solo'],['locked','L','Lock']].map(([key,label,hint])=>`<button data-track-control="${key}" data-track-id="${track.id}" class="${track[key]?'active':''}" aria-pressed="${Boolean(track[key])}" title="${hint} ${esc(track.name)}">${label}</button>`).join('')}</div>`;
    return `<div class="track-row ${track.mute?'muted-track':''} ${track.locked?'locked-track':''}" data-track="${track.id}"><div class="track-label"><strong title="${esc(track.name)}">${esc(track.name)}</strong>${controls}</div><div class="track-lane" data-track="${track.id}" style="width:${width}px;flex:none">${items.map(c=>{
      const a=title?null:sourceFor(c),selected=state.selected?.id===c.id;
      const wave=a?.has_audio&&a.kind!=='sequence'?waveforms.get(waveformKey(a,c)):null;
      if(a?.has_audio&&a.kind!=='sequence')ensureWaveform(a,c);
      const path=wave?editing.envelopePath(wave,c,state.project):'';
      const keys=visibleKeys(c).map(k=>`<i class="clip-key" style="left:${(k.frame-(c.animation_offset??0))/c.duration*100}%" title="Keyframe ${k.frame-(c.animation_offset??0)}"></i>`).join('');
      return `<div class="timeline-clip ${title?'title':c.track<0?'audio':''} ${selected?'selected':''}" data-clip="${esc(c.id)}" data-type="${title?'title':'clip'}" style="left:${c.start/state.project.fps*state.zoom}px;width:${Math.max(3,c.duration/state.project.fps*state.zoom)}px" tabindex="0" aria-label="${esc(title?c.text:a?.name||'Missing media')}; ${fmt(c.start)} to ${fmt(c.start+c.duration)}">${a&&['video','image'].includes(a.kind)&&c.track>=0?`<span class="clip-image" style="background-image:url('${thumbnailUrl(a)}')"></span>`:''}${path?`<svg class="clip-waveform" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Decoded source audio waveform"><path d="${path}"></path></svg>`:''}<span class="clip-name">${c.reverse?'◀ ':''}${esc(title?c.text:a?.name||'Missing media')}${c.speed&&c.speed!==1?' · '+c.speed+'×':''}</span>${keys}<span class="clip-edge left" data-edge="left"></span><span class="clip-edge right" data-edge="right"></span></div>`;
    }).join('')}</div></div>`;
  }).join('');
  $('#timeline-content').style.width=`${TRACK_WIDTH+width}px`;
  $('#timeline-content').innerHTML=`<div class="ruler-row"><div class="track-label">${rateLabel()}</div><div class="ruler-lane" style="width:${width}px;flex:none">${ticks}</div></div>${content}<div class="timeline-playhead" style="left:${TRACK_WIDTH+state.frame/state.project.fps*state.zoom}px"></div>`;
  updateTransport();
}
function waveformKey(asset,clip) {return state.project.id+':'+asset.id+':'+JSON.stringify([clip?.audio?.stream_index??null,clip?.audio?.channels??null]);}
function ensureWaveform(asset,clip) {
  const id=state.project.id,key=waveformKey(asset,clip);if(waveforms.has(key)||waveformPending.has(key))return;
  const query=new URLSearchParams({bins:'512'});if(clip?.audio?.stream_index!=null)query.set('stream_index',clip.audio.stream_index);if(clip?.audio?.channels){query.set('left',clip.audio.channels[0]);query.set('right',clip.audio.channels[1]);}
  waveformPending.add(key);waveformQueue.push({id,key,assetId:asset.id,query:query.toString()});pumpWaveforms();
}
async function pumpWaveforms() {
  if(waveformActive||!waveformQueue.length)return;
  const item=waveformQueue.shift();
  if(state.project.id!==item.id){waveformPending.delete(item.key);pumpWaveforms();return;}
  waveformActive++;
  try{const wave=await api(`${projectPath(item.id)}/waveform/${encodeURIComponent(item.assetId)}?${item.query}`);waveforms.set(item.key,wave);if(state.project.id===item.id)renderTimeline();}
  catch(error){waveforms.set(item.key,null);}
  finally{waveformPending.delete(item.key);waveformActive--;pumpWaveforms();}
}

function selectionLocked() {
  const c=selectedItem();if(c?.caption_id){toast('Edit this cue in Captions so its picture and sidecar stay synchronized.');return true;}if(state.selected?.type==='clip'&&c&&editing.track(state.project,c.track).locked){toast('Unlock this track to edit its clips.');return true;}return false;
}
function changeTrack(id,key,value) {
  mutate(()=>{let t=state.project.tracks.find(t=>t.id===id);if(!t){t={...editing.track(state.project,id)};state.project.tracks.push(t);}t[key]=value;},{inspector:true});
}
function addTrack(audio=false) {
  const used=new Set(editing.tracks(state.project).map(t=>t.id));let id=audio?-1:0;
  while(used.has(id))id+=audio?-1:1;
  if(id<-16||id>15){toast('This project supports 16 picture and 16 audio tracks.');return;}
  mutate(()=>{if(!state.project.tracks.length)state.project.tracks=editing.tracks(state.project);state.project.tracks.push({id,name:audio?'Audio '+Math.abs(id):'Video '+(id+1),gain:1,mute:false,solo:false,locked:false});},{inspector:true});
}
function rippleDelete() {
  const c=selectedItem();if(!c||selectionLocked())return;
  const type=state.selected.type,start=c.start,duration=c.duration,track=c.track;
  mutate(()=>{const collection=type==='title'?'titles':'clips';state.project[collection]=state.project[collection].filter(x=>x.id!==c.id);for(const other of state.project[collection])if(!other.caption_id&&(type==='title'||other.track===track)&&other.start>=start+duration)other.start-=duration;state.selected=null;},{inspector:true});
}
function renderMixer() {
  return `<div class="inspector-name">Track mixer</div><p class="note">The same gain, mute and solo states feed playback and export.</p>`+editing.tracks(state.project).map(t=>`<section class="mixer-strip"><div class="mixer-strip-title"><input aria-label="Track name" data-track-name="${t.id}" maxlength="80" value="${esc(t.name)}"><span>${t.id<0?'A'+Math.abs(t.id):'V'+(t.id+1)}</span></div><label class="range-field"><span class="control-row"><span>Track gain</span><output>${(20*Math.log10(Math.max(.0001,t.gain??1))).toFixed(1)} dB</output></span><input type="range" data-track-gain="${t.id}" min="0" max="4" step="0.01" value="${t.gain??1}"></label><div class="mixer-buttons">${[['mute','Mute'],['solo','Solo'],['locked','Lock']].map(([key,label])=>`<button data-mixer-toggle="${key}" data-track-id="${t.id}" class="${t[key]?'active':''}" aria-pressed="${Boolean(t[key])}">${label}</button>`).join('')}</div></section>`).join('');
}
function mediaFor(c,a) {
  const originalUrl=mediaUrl(a),requestUrl=a.kind==='audio'?originalUrl:(mediaEditor?.playbackUrl(a,originalUrl)||originalUrl);
  let m=state.media.get(c.id);
  if(m&&(m.assetId!==a.id||m.path!==a.path||m.sourceHash!==a.sha256||m.requestUrl!==requestUrl)){releaseMedia(c.id);m=null;}
  if(m){state.media.delete(c.id);state.media.set(c.id,m);return m;}
  const el=a.kind==='image'?new Image():a.kind==='audio'?window.CinematicumPCMPlayback.createDecoder():document.createElement('video');
  m={el,kind:a.kind,assetId:a.id,path:a.path,sourceHash:a.sha256,requestUrl,url:a.kind==='audio'?'':requestUrl,source:null,gain:null,warned:false,disposed:false,listeners:[]};
  const listen=(event,handler)=>{const bound=()=>{if(!m.disposed&&state.media.get(c.id)===m)handler();};m.listeners.push([event,bound]);el.addEventListener(event,bound);};
  if(a.kind!=='image'){el.crossOrigin='anonymous';el.preload='auto';el.playsInline=true;for(const event of ['seeked','loadeddata'])listen(event,()=>{if(!state.playing&&!state.rendered)drawPreview();});}
  else listen('load',()=>drawPreview());
  listen('error',()=>{if(!m.warned){m.warned=true;toast(`Source preview cannot decode ${a.name}. Try Render preview.`,true);}});
  state.media.set(c.id,m);if(a.kind!=='audio')el.src=requestUrl;return m;
}
function ensureAudio(m,clip,asset,{playbackRate=clip.speed??1,sourceTime=0}={}) {
  if(playbackAudioUnavailable)return {state:'unsupported',ready:false,message:'Live audio could not start. Use Render preview.'};
  window.CinematicumAudioRouting.configure({request:api,getProject:()=>state.project});
  return window.CinematicumAudioRouting.ensure(m,audioContext,clip,asset,toast,{prepare:state.playing||playbackPreparing,playbackRate,sourceTime});
}
function drawPreview() {
  if(!state.project||state.rendered)return;
  const p=state.project,W=p.width,H=p.height,activeIds=new Set();
  ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#000';ctx.fillRect(0,0,W,H);
  window.CinematicumSequencePlayback.draw({project:p,frame:state.frame,audioFrame:state.playing?playbackAudioFrame:state.frame,transportEpoch:playbackEpoch,context:ctx,width:W,height:H,mediaFor,ensureAudio,playing:state.playing,activeIds,revision:state.revision});
  for(const [id,m]of state.media)if(!activeIds.has(id)&&m.kind!=='image'&&!m.el.paused)m.el.pause();
  pruneMedia(activeIds);ctx.restore();
}
function stop() {state.playing=false;playbackPreparing=false;playbackRequest++;playbackEpoch++;playbackAudioFrame=state.frame;cancelAnimationFrame(animation);$('#play-button').textContent='▶';$('#play-button').setAttribute('aria-label','Play timeline');for(const m of state.media.values())if(m.kind!=='image'&&!m.el.paused)m.el.pause();window.CinematicumAudioRouting?.suspend();frameViewer?.invalidate();}
async function play() {
  frameViewer?.hide();
  if(state.rendered){const v=$('#render-video');if(v.paused)await v.play();else v.pause();return;}
  if(state.playing||playbackPreparing){stop();return;}if(!durationFrames())return;
  const request=++playbackRequest,projectId=state.project.id;playbackPreparing=true;
  $('#play-button').textContent='…';$('#play-button').setAttribute('aria-label','Cancel playback preparation');
  try{audioContext??=new(window.AudioContext||window.webkitAudioContext)();await audioContext.resume();if(audioContext.state!=='running')throw Error('The audio context did not start.');playbackAudioUnavailable=false;}
  catch(e){playbackAudioUnavailable=true;toast('Live audio could not start. Picture playback remains available; use Render preview for sound.',true,9000);}
  if(request!==playbackRequest||state.project.id!==projectId)return;
  if(state.frame>=durationFrames()-1)state.frame=0;
  playbackAudioFrame=state.frame;playbackEpoch++;
  // Build source routes and finish initial seeks while paused. Normal playback
  // then follows the selected source's audio clock instead of repeatedly
  // seeking a delayed native decoder toward the animation-frame wall clock.
  do{
    drawPreview();if(window.CinematicumSequencePlayback.ready())break;
    await new Promise(resolve=>setTimeout(resolve,25));
    if(request!==playbackRequest||state.project.id!==projectId)return;
  }while(true);
  if(request!==playbackRequest)return;
  playbackPreparing=false;state.playing=true;playbackOrigin=performance.now();playbackFrame=state.frame;
  $('#play-button').textContent='Ⅱ';$('#play-button').setAttribute('aria-label','Pause timeline');drawPreview();
  function tick(now){
    if(!state.playing||request!==playbackRequest)return;
    const clock=window.CinematicumSequencePlayback.clock();
    const next=clock?(clock.waiting?playbackAudioFrame:clock.frame):playbackFrame+(now-playbackOrigin)/1000*state.project.fps;
    playbackAudioFrame=Math.max(playbackAudioFrame,Number.isFinite(next)?next:playbackAudioFrame);
    playbackFrame=playbackAudioFrame;playbackOrigin=now;state.frame=Math.floor(playbackAudioFrame+1e-7);
    if(state.frame>=durationFrames()){state.frame=Math.max(0,durationFrames()-1);stop();updateTransport();drawPreview();return;}
    updateTransport();drawPreview();animation=requestAnimationFrame(tick);
  }
  animation=requestAnimationFrame(tick);
}
function switchPreview(rendered) {frameViewer?.hide();stop();state.rendered=rendered&&Boolean(state.lastRenderUrl);canvas.hidden=state.rendered;$('#render-video').hidden=!state.rendered;$('#source-preview').classList.toggle('active',!state.rendered);$('#rendered-preview').classList.toggle('active',state.rendered);if(state.rendered){if($('#render-video').getAttribute('src')!==state.lastRenderUrl)$('#render-video').src=state.lastRenderUrl;$('#preview-note').textContent='Rendered output · snapshot at render time';}else{$('#render-video').pause();updatePreviewNote();}updateTransport();drawPreview();frameViewer?.invalidate();}
async function importFiles(files) {
  if(!files.length||projectOperationBlocked())return;
  const projectId=beginProjectOperation();stop();$('#media-footer-label').textContent='Importing…';
  try{await saveProject(false);for(let i=0;i<files.length;i++){const file=files[i];if(state.project.id===projectId)$('#media-footer-label').textContent=`Importing ${i+1}/${files.length}…`;const r=await api(`${projectPath(projectId)}/import?name=${encodeURIComponent(file.name)}`,{method:'POST',raw:true,body:file});const a=r.asset||r;if(!a.id)throw Error('Import returned no media asset.');if(state.project.id===projectId){if(!state.project.assets.some(x=>x.id===a.id))state.project.assets.push(a);if(a.kind==='scene')state.selectedAsset=a.id;renderMedia();}}
    if(state.project.id===projectId){state.revision++;state.dirty=true;await saveProject(false);renderInspector();}toast(`${files.length} file${files.length===1?'':'s'} imported. Double-click media to add it to the timeline.`);
  }catch(e){toast(e.message,true,9000);}finally{if(state.project.id===projectId)$('#media-footer-label').textContent='Files stay on this computer';$('#media-input').value='';endProjectOperation();}
}
async function startRender(profile) {
  if(projectOperationBlocked())return;
  if(state.job&&['queued','running'].includes(String(state.job.state).toLowerCase())){toast('Wait for the current job or cancel it first.');return;}
  if(!durationFrames()){toast('Add clips or a title to the timeline first.');return;}
  const projectId=beginProjectOperation();stop();$('#export-dialog').close();
  try{const saved=await saveProject(false);const snapshot=saved?normalizeProject(saved):clone(state.project);if(snapshot.id!==projectId)throw Error('The project changed before the render could be submitted.');const job=await api(`${projectPath(projectId)}/render`,{method:'POST',body:{profile,project:snapshot}});trackJob(job,profile==='preview'?'Rendering preview':profile==='master16'?'Exporting 16-bit master':profile==='prores'?'Exporting ProRes':'Exporting H.264','render',projectId);}catch(e){toast(e.message,true,9000);}finally{endProjectOperation();}
}
async function startGenerate() {
  if(projectOperationBlocked())return;
  if(state.job&&['queued','running'].includes(String(state.job.state).toLowerCase())){toast('Wait for the current job or cancel it first.');return;}
  const prompt=$('#generate-prompt').value.trim();if(!prompt){toast('Describe the shot first.');return;}
  const negative=$('#generate-negative').value,seed=Math.round(finite($('#generate-seed').value,42)),workflow_path=state.workflowPath,projectId=beginProjectOperation();
  try{state.project.settings.last_prompt=prompt;state.project.settings.last_negative=negative;state.project.settings.last_seed=seed;state.dirty=true;state.revision++;await saveProject(false);const job=await api(`${projectPath(projectId)}/generate`,{method:'POST',body:{prompt,negative,seed,workflow_path}});trackJob(job,'Generating media','generate',projectId);}catch(e){toast(e.message,true,9000);}finally{endProjectOperation();}
}
async function validateGenerationWorkflow() {
  const projectId=state.project.id,request=++readinessRequest,button=$('#validate-workflow');
  if(button){button.disabled=true;button.textContent='Checking workflow…';}
  try{const result=await api(`${projectPath(projectId)}/generation-readiness`);if(state.project.id!==projectId||request!==readinessRequest)return;generationReadiness={projectId,...result};renderInspector();toast(result.ready?'Workflow nodes and configured models are available.':result.reason||result.errors?.[0]||'The workflow is not ready.',!result.ready,9000);}catch(error){if(state.project.id===projectId&&request===readinessRequest){generationReadiness={projectId,ready:false,errors:[error.message],reason:error.message};renderInspector();toast(error.message,true);}}
}
async function startBlender() {
  if(projectOperationBlocked())return;
  if(state.job&&['queued','running'].includes(String(state.job.state).toLowerCase())){toast('Wait for the current job or cancel it first.');return;}
  const scene_path=$('#blender-scene').value,frame_start=Number($('#blender-start').value),frame_end=Number($('#blender-end').value);if(!scene_path||!Number.isInteger(frame_start)||!Number.isInteger(frame_end)||frame_end<frame_start){toast('Choose a scene and a valid inclusive frame range.',true);return;}
  const projectId=beginProjectOperation();$('#blend-dialog').close();try{await saveProject(false);const job=await api(`${projectPath(projectId)}/blender`,{method:'POST',body:{scene_path,frame_start,frame_end}});trackJob(job,'Rendering Blender scene','blender',projectId);}catch(e){toast(e.message,true,9000);}finally{endProjectOperation();}
}
async function trackJob(initial,label,kind,originProjectId=state.project.id) {
  const raw=initial.job||initial,id=raw.id||raw.job_id;
  if(!id){toast('Server returned no job identifier.',true);return null;}
  const owned={...raw,id,kind,label,projectId:raw.project_id||originProjectId,pollingPaused:false};
  state.job=owned;$('#job-bar').hidden=false;$('#job-label').textContent=label;$('#job-detail').textContent='Queued';
  $('#job-indicator').className='job-indicator running';$('#job-progress').hidden=false;$('#job-progress').value=0;
  $('#cancel-job').hidden=false;$('#cancel-job').disabled=false;$('#retry-job').hidden=true;$('#download-job').hidden=true;$('#download-scene').hidden=true;$('#download-masters').hidden=true;$('#open-restored-project').hidden=true;delete $('#open-restored-project').dataset.projectId;$('#view-job').hidden=true;$('#close-job').hidden=true;
  let errors=0;
  while(state.job===owned){
    try{
      const response=await api(`/api/jobs/${encodeURIComponent(id)}`);
      // A response for a previous owner must never replace a newer job or UI.
      if(state.job!==owned)return null;
      errors=0;Object.assign(owned,response.job||response);
      const status=String(owned.state||owned.status||'queued').toLowerCase(),progress=finite(owned.progress,0);
      $('#job-progress').value=progress<=1?progress*100:progress;
      $('#job-detail').textContent=owned.message||`${status==='queued'?'Queued':Math.round($('#job-progress').value)+'%'} · ${owned.projectId===state.project.id?state.project.name:'Project render'}`;
      if(['completed','complete','succeeded','success','done'].includes(status)){await finishJob(owned);return owned;}
      if(['failed','error','cancelled','canceled','interrupted'].includes(status)){
        $('#job-label').textContent=status.startsWith('cancel')?'Job cancelled':'Job failed';$('#job-detail').textContent=owned.error||owned.message||'No output was admitted.';
        $('#job-indicator').className='job-indicator error';$('#cancel-job').hidden=true;$('#close-job').hidden=false;$('#job-progress').hidden=true;
        if(!status.startsWith('cancel'))toast(String(owned.error||'The job failed. Check its source media and configured engine.'),true,12000);
        return owned;
      }
    }catch(error){
      if(state.job!==owned)return null;
      errors++;$('#job-detail').textContent='Connection interrupted · retrying';
      if(error.status===404){owned.state='interrupted';owned.error='This job is no longer present in the workspace. Review saved outputs and start it again.';$('#job-label').textContent='Job interrupted';$('#job-detail').textContent=owned.error;$('#cancel-job').hidden=true;$('#close-job').hidden=false;return owned;}
      if(errors>=12){
        owned.pollingPaused=true;$('#job-label').textContent='Job connection interrupted';$('#job-detail').textContent='The owned job may still be running. Retry its status or request cancellation.';
        $('#job-indicator').className='job-indicator error';$('#cancel-job').hidden=false;$('#retry-job').hidden=false;$('#close-job').hidden=false;
        toast('Unable to read the job result. Retry status or cancel this job before starting another.',true);return owned;
      }
    }
    await new Promise(resolve=>setTimeout(resolve,400));
  }
  return null;
}
async function cancelOwnedJob() {
  const owned=state.job;if(!owned)return;
  $('#cancel-job').disabled=true;
  try{
    const response=await api(`/api/jobs/${encodeURIComponent(owned.id)}/cancel`,{method:'POST',body:{}});
    if(state.job!==owned)return;
    Object.assign(owned,response.job||response);$('#job-detail').textContent='Cancellation requested';
    // A paused poller has already returned. Resume that same job so its final
    // cancellation state releases the busy guard without a second user action.
    if(owned.pollingPaused)await trackJob(owned,owned.label,owned.kind,owned.projectId);
  }catch(error){if(state.job===owned)toast(error.message,true);}
  finally{if(state.job?.id===owned.id)$('#cancel-job').disabled=false;}
}
async function finishJob(job) {const r=job.result||{},url=r.url||r.download_url,master16=job.kind==='render'&&(r.profile==='master16'||/\.mkv(?:$|[?#])/i.test(url||'')),prores=job.kind==='render'&&(r.profile==='prores'||/\.mov(?:$|[?#])/i.test(url||'')),downloadMaster=master16||prores;$('#job-label').textContent=job.kind==='render'?(master16?'16-bit master complete':prores?'ProRes export complete':'Render complete'):'Media ready';$('#job-detail').textContent=downloadMaster?`Download ${master16?'MKV':'MOV'} · use Render preview for playback`:r.width?`${r.width} × ${r.height} · ${Number(r.duration||r.duration_seconds||0).toFixed(2)}s`:'Finished and saved locally';$('#job-progress').value=100;$('#job-indicator').className='job-indicator';$('#cancel-job').hidden=true;$('#close-job').hidden=false;
  if(job.kind==='scene-modeling'){$('#job-label').textContent='Mesh evaluated';$('#job-detail').textContent='Geometry ready for the current scene';return;}
  if(job.kind==='generation-setup'||job.kind==='generation-start'){$('#job-label').textContent=job.kind==='generation-setup'?'Local generation installed':'Local generation running';$('#job-detail').textContent=job.kind==='generation-setup'?'Open Local generation setup to start the engine.':'Ready to validate the project workflow.';return;}
  if(job.kind==='archive-export'){
    $('#job-label').textContent='Project archive ready';$('#job-detail').textContent=`${r.files} verified files · ${(Number(r.size||0)/1048576).toFixed(1)} MiB · download to keep a backup`;
    if(!url)throw Error('The archive job returned no download.');
    $('#download-job').href=url+'?download=1';$('#download-job').download=r.filename||'';$('#download-job').hidden=false;return;
  }
  if(job.kind==='archive-restore'){
    if(!/^[a-f0-9]{32}$/.test(r.project_id||''))throw Error('The restore job returned no valid project.');
    $('#job-label').textContent='Project restored';$('#job-detail').textContent=`${r.name} · ${r.files} verified files`;
    $('#open-restored-project').dataset.projectId=r.project_id;$('#open-restored-project').hidden=false;
    state.projects=await api('/api/projects');if(!Array.isArray(state.projects))state.projects=state.projects.projects||[];renderProjectList();return;
  }
  if(r.masters_url){$('#download-masters').href=r.masters_url+'?download=1';$('#download-masters').download=r.masters_filename||'';$('#download-masters').hidden=false;}
  if(r.scene_url){$('#download-scene').href=r.scene_url+(r.scene_url.includes('?')?'&':'?')+'download=1';$('#download-scene').download=r.scene_filename||'';$('#download-scene').hidden=false;}
  if(url){$('#download-job').href=url+(url.includes('?')?'&':'?')+'download=1';$('#download-job').hidden=false;$('#download-job').download=r.filename||'';if(job.kind==='render'&&!downloadMaster&&job.projectId===state.project.id){state.lastRenderUrl=url;$('#rendered-preview').disabled=false;$('#view-job').hidden=false;switchPreview(true);}}
  if(job.kind!=='render'&&job.projectId===state.project.id){try{const projectId=job.projectId,fresh=normalizeProject(await api(projectPath(projectId)));if(state.project.id!==projectId)return;const ids=new Set(state.project.assets.map(a=>a.id));for(const a of fresh.assets)if(!ids.has(a.id))state.project.assets.push(a);renderMedia();renderInspector();toast('Generated media is in the bin. Double-click it to add it to the timeline.');}catch(e){toast(`Media completed, but refresh failed: ${e.message}`,true);}}}
async function automate(recipe) {
  if(projectOperationBlocked())return;
  if(!state.project.clips.length){toast('Add clips to the timeline first.');return;}
  const selected=selectedItem();let operation;
  if(recipe==='monochrome')operation={action:'grade',values:{saturation:0}};
  else if(recipe==='mute')operation={action:'volume',value:0};
  else {const track=state.selected?.type==='clip'?selected.track:0;const ids=state.project.clips.filter(c=>c.track===track).map(c=>c.id);if(!ids.length){toast('The selected track has no clips.');return;}operation={action:'sequence',start:0,track,clip_ids:ids};}
  state.editBusy=true;const projectId=beginProjectOperation();
  try{await saveProject(false);checkpoint();const result=await api(`${projectPath(projectId)}/automate`,{method:'POST',body:{project:clone(state.project),operations:[operation]}});if(state.project.id!==projectId)throw Error('Automation completed in the previous project. Reopen it to review the edit.');state.project=normalizeProject(result);state.revision++;state.dirty=false;$('#save-state').textContent='SAVED LOCALLY';$('#save-state').classList.remove('dirty');renderTimeline();renderInspector();switchPreview(false);$('#automation-dialog').close();toast(recipe==='monochrome'?'All clips converted to monochrome.':recipe==='mute'?'All clip audio muted.':'Track arranged without gaps.');}catch(e){toast(e.message,true);}finally{state.editBusy=false;endProjectOperation();}
}

function snapFrame(frame,excludeId) {if(!$('#snap-toggle').checked)return Math.max(0,frame);const points=[0,state.frame];for(const c of [...state.project.clips,...state.project.titles])if(c.id!==excludeId)points.push(c.start,c.start+c.duration);let best=Math.max(0,frame),dist=7/state.zoom*state.project.fps;for(const p of points){const d=Math.abs(p-frame);if(d<dist){best=p;dist=d;}}return best;}
function timelinePointer(e) {if(e.button!==0)return;const bar=e.target.closest('.timeline-clip'),lane=e.target.closest('.track-lane,.ruler-lane');if(!lane)return;if(bar){if(editing.track(state.project,Number(lane.dataset.track)).locked){toast('Unlock this track before moving or trimming clips.');return;}e.preventDefault();stop();switchPreview(false);const type=bar.dataset.type,id=bar.dataset.clip;state.selected={type,id};const c=selectedItem();state.drag=c.caption_id?null:{type,id,edge:e.target.dataset.edge||'move',startX:e.clientX,original:clone(c),snapshot:clone(state.project),moved:false};renderInspector();updateTransport();$$('.timeline-clip').forEach(x=>x.classList.toggle('selected',x.dataset.clip===id));}else{const rect=lane.getBoundingClientRect();stop();switchPreview(false);setFrame((e.clientX-rect.left)/state.zoom*state.project.fps);state.drag={scrub:true,lane};}}
function timelineMove(e) {
  const d=state.drag;if(!d)return;
  if(d.scrub){const lane=$('.ruler-lane');setFrame((e.clientX-lane.getBoundingClientRect().left)/state.zoom*state.project.fps);return;}
  if(!d.moved&&Math.abs(e.clientX-d.startX)<3)return;
  d.moved=true;const c=selectedItem();if(!c)return;
  const o=d.original,delta=Math.round((e.clientX-d.startX)/state.zoom*state.project.fps),a=d.type==='clip'?sourceFor(c):null;
  const max=a&&['video','audio','sequence'].includes(a.kind)?a.duration*state.project.fps:Infinity;
  if(d.edge==='left'||d.edge==='right'){
    const original=d.edge==='left'?o.start:o.start+o.duration;
    const requested=e.altKey?original+delta:snapFrame(original+delta,c.id);
    const result=editing.trim(o,d.edge,requested,max,a?.kind==='image'||d.type==='title');
    c.start=result.start;c.duration=result.duration;if(d.type==='clip')c.in=result.in;
    if(d.type==='clip'){
      preserveAnimation(c,o,result.offset);
      if(o.planar_motion?.mode==='stabilize'&&['in','duration','animation_offset'].some(key=>(c[key]??0)!==(o[key]??0)))delete c.planar_motion;
    }
  }else{
    c.start=e.altKey?Math.max(0,o.start+delta):snapFrame(o.start+delta,c.id);
    const hover=document.elementFromPoint(e.clientX,e.clientY)?.closest('.track-lane');
    if(d.type==='clip'&&hover&&hover.dataset.track!=='titles'){
      const track=Number(hover.dataset.track);
      if((a?.kind==='audio'?track<0:track>=0)&&!editing.track(state.project,track).locked)c.track=track;
    }
  }
  if(d.type==='title')c.fade=Math.min(c.fade,Math.floor(c.duration/2));renderTimeline();drawPreview();
}

function timelineUp() {const d=state.drag;if(!d)return;state.drag=null;if(d.scrub){renderInspector();frameViewer?.invalidate();}if(d.moved){state.history.push(d.snapshot);if(state.history.length>80)state.history.shift();state.future=[];changed({inspector:true});}}
function fitTimeline() {state.zoom=clamp(($('#timeline-scroll').clientWidth-TRACK_WIDTH-40)/Math.max(5,durationFrames()/state.project.fps+1),12,160);$('#timeline-zoom').value=state.zoom;renderTimeline();}
async function bootstrap() {try{recoveryEditor??=window.CinematicumRecovery.mount({request:api,notify:toast,button:$('#recovery-button'),status:$('#recovery-state'),getContext:()=>({project:state.project,revision:state.revision,dirty:state.dirty,saving:Boolean(state.savePromise),blocked:state.navigating||state.editBusy||state.projectOps>0}),onRecover:(project,expected)=>{if(state.project.id!==expected.projectId||state.revision!==expected.revision||state.project.revision!==expected.savedRevision||project.revision!==state.project.revision)throw Error('The project changed. Reopen it before recovering this version.');stop();mutate(()=>{state.project=normalizeProject(project);state.selected=null;clearMedia();canvas.width=state.project.width;canvas.height=state.project.height;canvas.style.aspectRatio=`${state.project.width}/${state.project.height}`;state.workflowPath=state.project.settings.comfy_workflow_path||'';generationReadiness=null;readinessRequest++;},{inspector:true,bin:true});renderAll();}});const b=await api('/api/bootstrap');state.token=b.token;state.projects=b.projects||[];state.capabilities=b.capabilities||{};if(!b.project)throw Error('The server did not provide a project.');adoptProject(b.project);const active=(b.jobs||[]).find(j=>j.project_id===state.project.id&&j.kind!=='frame-preview'&&['queued','running'].includes(j.state));if(active)trackJob(active,active.kind==='render'?'Rendering timeline':active.kind==='blender'?'Rendering Blender scene':active.kind==='scene'?'Rendering your 3D scene':'Generating media',active.kind||'render');if(!state.capabilities.ffmpeg)toast('Install FFmpeg and ffprobe to render media, then check engines.',true,8000);}catch(e){toast(`Could not open CINEMATICUM: ${e.message}`,true,30000);$('#preview-note').textContent='Server connection failed';}}

// UI bindings stay local; no project data leaves this server.
for(const id of ['import-button','import-footer','import-center'])$('#'+id).addEventListener('click',()=>$('#media-input').click());
$('#create-scene-center').addEventListener('click',()=>setMode('3d'));
$('#generate-center').addEventListener('click',()=>{setMode('generate');$('#generate-prompt')?.focus();});
$('#open-blend-dialog').addEventListener('click',openBlendDialog);
$('#close-blend-dialog').addEventListener('click',()=>$('#blend-dialog').close());
$('#blend-dialog-content').addEventListener('click',event=>{if(event.target.id==='blender-button')startBlender();if(event.target.id==='import-scene'){$('#blend-dialog').close();$('#media-input').click();}});
$('#media-input').addEventListener('change',e=>importFiles([...e.target.files]));
$('#media-search').addEventListener('input',renderMedia);
$('#media-bin').addEventListener('click',e=>{const add=e.target.closest('[data-add]');if(add){addAsset(add.dataset.add);return;}const item=e.target.closest('[data-asset]');if(item){state.selectedAsset=item.dataset.asset;renderMedia();if(assetById(item.dataset.asset)?.kind==='scene')setMode('3d');}});
$('#media-bin').addEventListener('dblclick',e=>{const item=e.target.closest('[data-asset]');if(item&&!e.target.closest('[data-add]'))addAsset(item.dataset.asset);});
$('#media-bin').addEventListener('keydown',e=>{if(e.key==='Enter'){const item=e.target.closest('[data-asset]');if(item)addAsset(item.dataset.asset);}});
$('#media-bin').addEventListener('dragstart',e=>{const item=e.target.closest('[data-asset]');if(item){e.dataTransfer.setData('application/cinematicum-asset',item.dataset.asset);e.dataTransfer.effectAllowed='copy';}});
for(const target of [$('#media-bin'),$('#viewer-stage')]){target.addEventListener('dragover',e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();target.classList.add('dragover');}});target.addEventListener('dragleave',()=>target.classList.remove('dragover'));target.addEventListener('drop',e=>{if(e.dataTransfer.files.length){e.preventDefault();target.classList.remove('dragover');importFiles([...e.dataTransfer.files]);}});}
$('#timeline-content').addEventListener('dragover',e=>{const lane=e.target.closest('.track-lane');if(lane&&lane.dataset.track!=='titles'){e.preventDefault();$$('.drop-target').forEach(x=>x.classList.remove('drop-target'));lane.classList.add('drop-target');}});
$('#timeline-content').addEventListener('dragleave',e=>e.target.closest('.track-lane')?.classList.remove('drop-target'));
$('#timeline-content').addEventListener('drop',e=>{e.preventDefault();$$('.drop-target').forEach(x=>x.classList.remove('drop-target'));const lane=e.target.closest('.track-lane'),id=e.dataTransfer.getData('application/cinematicum-asset');if(id&&lane&&lane.dataset.track!=='titles'){const a=assetById(id);let track=Number(lane.dataset.track);if(a.kind==='audio'&&track>=0)track=-1;if(a.kind!=='audio'&&track<0)track=0;addAsset(id,snapFrame(Math.round((e.clientX-lane.getBoundingClientRect().left)/state.zoom*state.project.fps)),track);}else if(e.dataTransfer.files.length)importFiles([...e.dataTransfer.files]);});
$('#timeline-content').addEventListener('pointerdown',timelinePointer);window.addEventListener('pointermove',timelineMove);window.addEventListener('pointerup',timelineUp);
$('#timeline-content').addEventListener('keydown',e=>{if(e.key==='Enter'){const b=e.target.closest('.timeline-clip');if(b)select(b.dataset.type,b.dataset.clip);}});
$$('.mode').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));
$('#production-button').addEventListener('click',()=>{try{openProduction();}catch(error){toast(error.message,true);}});
$('#archive-button').addEventListener('click',()=>{try{openArchive();}catch(error){toast(error.message,true);}});
$('#open-restored-project').addEventListener('click',openRestoredProject);
$('#save-project').addEventListener('click',()=>saveProject().catch(e=>toast(e.message,true)));
$('#undo-button').addEventListener('click',()=>undo());$('#redo-button').addEventListener('click',()=>undo(true));$('#split-button').addEventListener('click',splitSelected);$('#duplicate-button').addEventListener('click',duplicateSelected);$('#delete-button').addEventListener('click',deleteSelected);$('#add-title').addEventListener('click',addTitle);
$('#play-button').addEventListener('click',()=>play().catch(e=>toast(e.message,true)));$('#jump-start').addEventListener('click',()=>{stop();switchPreview(false);setFrame(0);});$('#jump-end').addEventListener('click',()=>{stop();switchPreview(false);setFrame(durationFrames()-1);});$('#step-back').addEventListener('click',()=>{stop();switchPreview(false);setFrame(state.frame-1);});$('#step-forward').addEventListener('click',()=>{stop();switchPreview(false);setFrame(state.frame+1);});
$('#source-preview').addEventListener('click',()=>switchPreview(false));$('#rendered-preview').addEventListener('click',()=>switchPreview(true));$('#preview-render').addEventListener('click',()=>startRender('preview'));
$('#timeline-zoom').addEventListener('input',e=>{state.zoom=Number(e.target.value);renderTimeline();});for(const [id,m]of [['zoom-in',1.25],['zoom-out',.8]])$('#'+id).addEventListener('click',()=>{state.zoom=clamp(state.zoom*m,12,160);$('#timeline-zoom').value=state.zoom;renderTimeline();});$('#fit-timeline').addEventListener('click',fitTimeline);
let rangeCheckpoint=null;$('#inspector').addEventListener('pointerdown',e=>{if(e.target.matches('input[type=range][data-field]')){rangeCheckpoint=e.target.dataset.field;checkpoint();}});
$('#inspector').addEventListener('input',e=>{const input=e.target;if(['generate-prompt','generate-negative','generate-seed'].includes(input.id)){const key={'generate-prompt':'last_prompt','generate-negative':'last_negative','generate-seed':'last_seed'}[input.id];state.project.settings[key]=input.id==='generate-seed'?Number(input.value):input.value;state.dirty=true;state.revision++;$('#save-state').textContent='UNSAVED';$('#save-state').classList.add('dirty');recoveryEditor?.schedule();return;}if(!input.matches('input[type=range][data-field]'))return;const value=Number(input.value);if(!Number.isFinite(value))return;const output=input.parentElement.querySelector('output');if(output)output.textContent=value.toFixed(Number(input.step)>=1?0:2);if(rangeCheckpoint!==input.dataset.field){checkpoint();rangeCheckpoint=input.dataset.field;}writeField(input.dataset.field,value,{checkpointFirst:false});});
$('#inspector').addEventListener('change',e=>{const input=e.target;if(input.dataset.field){if(input.type==='range'){rangeCheckpoint=null;return;}let value=input.type==='checkbox'?input.checked:input.type==='number'||input.tagName==='SELECT'?Number(input.value):input.value;if(typeof value==='number'&&!Number.isFinite(value)){renderInspector();return;}if(input.type==='number')value=clamp(value,finite(input.min,-Infinity),finite(input.max,Infinity));writeField(input.dataset.field,value);renderInspector();}else if(input.id==='chroma-enabled'||input.id==='chroma-color'){writeField('effects.chroma_key',$('#chroma-enabled').checked?$('#chroma-color').value:'');}});
$('#inspector').addEventListener('click',e=>{
  const action=e.target.closest('[data-action]')?.dataset.action,key=e.target.closest('[data-remove-key]');
  if((['reset-color','reset-transform','keyframe'].includes(action)||key)&&selectionLocked())return;
  if(action==='delete')deleteSelected();
  else if(action==='duplicate')duplicateSelected();
  else if(action==='add-title')addTitle();
  else if(action==='captions')openEditorial('captions');
  else if(action==='preview')startRender('preview');
  else if(action==='track')openTracking();
  else if(action==='clear-planar'){if(!selectedItem()||selectionLocked())return;stop();mutate(()=>{delete selectedItem().planar_motion;},{inspector:true});}
  else if(action==='color-pipeline')openColorPipeline();
  else if(action==='reset-color')mutate(()=>{selectedItem().grade={exposure:0,contrast:1,saturation:1,temperature:0};},{inspector:true});
  else if(action==='reset-transform')mutate(()=>{const c=selectedItem(),soundKeys=(c.keyframes||[]).filter(k=>k.volume!==undefined).map(k=>({frame:k.frame,volume:k.volume,interpolation:k.interpolation||'linear'}));Object.assign(c,{x:0,y:0,scale:1,rotation:0,opacity:1,keyframes:soundKeys});},{inspector:true});
  else if(action==='keyframe'){
    const c=selectedItem(),frame=state.frame-c.start;
    if(frame<0||frame>=c.duration){toast('Move the playhead inside this clip to set a keyframe.');return;}
    const domainFrame=frame+(c.animation_offset??0);if(c.keyframes.length>=128&&!c.keyframes.some(k=>k.frame===domainFrame)){toast('This clip already has 128 keyframes.');return;}
    const interpolation=c.keyframes.find(k=>k.frame===domainFrame)?.interpolation||'linear';
    mutate(()=>{const pose=transformAt(c,frame),position=keyPosition(c,frame);c.keyframes=c.keyframes.filter(k=>k.frame!==position);c.keyframes.push({frame:position,...pose,interpolation});c.keyframes.sort((a,b)=>a.frame-b.frame);},{inspector:true});
  }
  if(key&&selectedItem())mutate(()=>{selectedItem().keyframes=selectedItem().keyframes.filter(k=>k.frame!==Number(key.dataset.removeKey));},{inspector:true});
  if(e.target.id==='choose-workflow')$('#workflow-input').click();
  if(e.target.id==='manage-generation')openManagedGeneration();
  if(e.target.id==='generate-button')startGenerate();
  if(e.target.id==='validate-workflow')validateGenerationWorkflow();
  if(e.target.id==='blender-button')startBlender();
  if(e.target.id==='import-scene')$('#media-input').click();
});

let pendingWorkflow=null;
function workflowInputs(graph) {const values=[];for(const [nodeId,node]of Object.entries(graph)){for(const [input,value]of Object.entries(node.inputs||{})){if(typeof value==='string'||Number.isInteger(value))values.push({nodeId,input,value,label:`${nodeId} · ${node._meta?.title||node.class_type} · ${input}`,key:JSON.stringify([nodeId,input])});}}return values;}
async function saveWorkflow(graph) {if(projectOperationBlocked())throw Error('Wait for the current project operation to finish.');const projectId=beginProjectOperation();try{const r=await api(`${projectPath(projectId)}/workflow`,{method:'POST',body:graph});if(state.project.id!==projectId)throw Error('Workflow was imported into the previous project. Reopen that project to use it.');state.workflowPath=r.workflow_path;generationReadiness=null;readinessRequest++;const serial=JSON.stringify(Object.values(graph).map(n=>n.inputs));state.project.settings.comfy_workflow_path=state.workflowPath;state.project.settings.comfy_bindings={negative:serial.includes('CINEMATICUM_NEGATIVE_PROMPT'),seed:serial.includes('CINEMATICUM_SEED')};state.dirty=true;state.revision++;await saveProject(false);renderInspector();toast('API workflow imported.');}finally{endProjectOperation();}}
$('#workflow-input').addEventListener('change',async e=>{const file=e.target.files[0],projectId=state.project.id;if(!file)return;try{let graph=JSON.parse(await file.text());if(state.project.id!==projectId)throw Error('The project changed while reading the workflow. Import it again in the intended project.');if(graph.prompt&&typeof graph.prompt==='object')graph=graph.prompt;if(!graph||Array.isArray(graph)||typeof graph!=='object'||graph.nodes)throw Error('Export this workflow from ComfyUI in API format, then import it here.');if(!Object.values(graph).every(n=>n&&typeof n.class_type==='string'&&n.inputs&&typeof n.inputs==='object'))throw Error('Every API workflow node needs a class_type and inputs object.');const inputValues=workflowInputs(graph);if(JSON.stringify(Object.values(graph).map(n=>n.inputs)).includes('CINEMATICUM_POSITIVE_PROMPT')){await saveWorkflow(graph);return;}const strings=inputValues.filter(v=>typeof v.value==='string'),numbers=inputValues.filter(v=>Number.isInteger(v.value));if(!strings.length)throw Error('This API workflow has no text input to bind to the prompt.');pendingWorkflow={graph,projectId};const options=list=>list.map(v=>`<option value="${esc(v.key)}">${esc(v.label+' — '+String(v.value).slice(0,65))}</option>`).join('');$('#workflow-positive').innerHTML='<option value="">Select the positive prompt input</option>'+options(strings);$('#workflow-negative').innerHTML='<option value="">Keep the workflow’s existing negative prompt</option>'+options(strings);$('#workflow-seed').innerHTML='<option value="">Keep the workflow’s existing seed</option>'+options(numbers);$('#workflow-dialog').showModal();}catch(e){toast(e.message,true,9000);}finally{$('#workflow-input').value='';}});
$('#workflow-form').addEventListener('submit',async e=>{e.preventDefault();if(!pendingWorkflow)return;if(pendingWorkflow.projectId!==state.project.id){pendingWorkflow=null;$('#workflow-dialog').close();toast('Import the workflow again in the intended project.',true);return;}const positive=$('#workflow-positive').value,negative=$('#workflow-negative').value,seed=$('#workflow-seed').value;if(!positive)return;if(positive===negative){toast('Choose different positive and negative prompt inputs.',true);return;}const graph=clone(pendingWorkflow.graph);for(const [key,marker]of [[positive,'CINEMATICUM_POSITIVE_PROMPT'],[negative,'CINEMATICUM_NEGATIVE_PROMPT'],[seed,'CINEMATICUM_SEED']])if(key){const [nodeId,input]=JSON.parse(key);graph[nodeId].inputs[input]=marker;}try{await saveWorkflow(graph);pendingWorkflow=null;$('#workflow-dialog').close();}catch(e){toast(e.message,true,9000);}});
$('#close-workflow').addEventListener('click',()=>{pendingWorkflow=null;$('#workflow-dialog').close();});
$('#refresh-engines').addEventListener('click',async()=>{try{state.capabilities=await api('/api/capabilities');generationReadiness=null;readinessRequest++;renderCapabilities();renderInspector();toast('Engine availability refreshed.');}catch(e){toast(e.message,true);}});
function openInterchange() {
  if(projectOperationBlocked())return;stop();
  interchangeEditor??=window.CinematicumInterchange.mount(document.body,{request:api,getProject:()=>clone(state.project),getContext:()=>({projectId:state.project.id,revision:state.revision}),notify:toast,onApply:(candidate,expected)=>{
    if(state.project.id!==expected.projectId||state.revision!==expected.revision||projectOperationBlocked())return false;
    if(editing.tracks(state.project).some(track=>track.locked)){toast('Unlock the timeline tracks before replacing this edit.');return false;}
    const inventory=state.project.assets,savedRevision=state.project.revision;
    stop();clearMedia();mutate(()=>{state.project=normalizeProject(candidate);state.project.id=expected.projectId;state.project.assets=inventory;state.project.revision=savedRevision;state.selected=null;state.selectedAsset=null;state.frame=0;state.workflowPath=state.project.settings.comfy_workflow_path||'';generationReadiness=null;readinessRequest++;canvas.width=state.project.width;canvas.height=state.project.height;canvas.style.aspectRatio=`${state.project.width}/${state.project.height}`;},{inspector:true,bin:true});renderAll();return true;
  }});
  interchangeEditor.open();
}
$('#develop-image').addEventListener('click',()=>openImaging());
$('#trim-edit-button').addEventListener('click',openTrimEdit);
$('#close-trim-edit').addEventListener('click',()=>{$('#trim-edit-dialog').close();trimEditContext=null;});
$('#trim-edit-kind').addEventListener('change',updateTrimEdit);
$('#trim-edit-delta').addEventListener('input',updateTrimEdit);
$('#trim-edit-form').addEventListener('submit',applyTrimEdit);
$('#interchange-button').addEventListener('click',openInterchange);
function syncExportProcessing() {
  const high=state.project.settings.image_precision==='high16';
  $('#movie-precision').value=high?'high16':'standard8';
  $('#movie-precision').disabled=state.capabilities.high_depth_movie===false;
  $('#movie-transparent').checked=high&&Boolean(state.project.settings.transparent_background);
  $('#movie-transparent').disabled=!high;
  const master=$('[data-export=master16]');master.disabled=!high||state.capabilities.master16===false;
  master.title=!high?'Choose High 16-bit SDR processing first.':state.capabilities.master16===false?'The installed media engine does not support this profile.':'';
  $('#export-summary').textContent=`${state.project.width} × ${state.project.height} · ${rateLabel()} · ${fmt(durationFrames())}`;
}
$('#movie-precision').addEventListener('change',()=>{if(projectOperationBlocked())return;stop();mutate(()=>{state.project.settings.image_precision=$('#movie-precision').value;if(state.project.settings.image_precision!=='high16')state.project.settings.transparent_background=false;});syncExportProcessing();});
$('#movie-transparent').addEventListener('change',()=>{if(projectOperationBlocked())return;stop();mutate(()=>{state.project.settings.transparent_background=$('#movie-transparent').checked&&state.project.settings.image_precision==='high16';});syncExportProcessing();});
$('#export-button').addEventListener('click',()=>{syncExportProcessing();$('#export-dialog').showModal();});$('#close-export').addEventListener('click',()=>$('#export-dialog').close());$$('[data-export]').forEach(b=>b.addEventListener('click',()=>startRender(b.dataset.export)));
$('#retry-job').addEventListener('click',()=>{const job=state.job;if(job?.pollingPaused)trackJob(job,job.label,job.kind,job.projectId);});
$('#cancel-job').addEventListener('click',cancelOwnedJob);$('#close-job').addEventListener('click',()=>{$('#job-bar').hidden=true;});$('#view-job').addEventListener('click',()=>switchPreview(true));
$('#new-project').addEventListener('click',()=>{if(state.projectOps){toast('Wait for the current project operation to finish.');return;}$('#project-dialog').showModal();});$('#cancel-project').addEventListener('click',()=>$('#project-dialog').close());
$('#project-form').addEventListener('submit',async e=>{e.preventDefault();if(state.projectOps){toast('Wait for the current project operation to finish.');return;}const properties={name:$('#new-name').value.trim()||'Untitled film',width:Number($('#new-width').value),height:Number($('#new-height').value),frame_rate:{numerator:Number($('#new-fps').value.split('/')[0]),denominator:Number($('#new-fps').value.split('/')[1]||1)}};state.navigating=true;beginProjectOperation();try{if(state.dirty)await saveProject(false);const p=await api('/api/projects',{method:'POST',body:properties});state.projects=await api('/api/projects');if(!Array.isArray(state.projects))state.projects=state.projects.projects||[];adoptProject(p);$('#project-dialog').close();toast('Project created.');}catch(e){toast(e.message,true);}finally{state.navigating=false;endProjectOperation();}});
$('#project-select').addEventListener('change',async e=>{const id=e.target.value;if(state.projectOps){e.target.value=state.project.id;toast('Wait for the current project operation to finish.');return;}state.navigating=true;beginProjectOperation();try{if(state.dirty)await saveProject(false);adoptProject(await api(projectPath(id)));}catch(e){toast(e.message,true);$('#project-select').value=state.project.id;}finally{state.navigating=false;endProjectOperation();}});
$('#rename-project').addEventListener('click',()=>{const name=prompt('Project name',state.project.name);if(name?.trim()){mutate(()=>{state.project.name=name.trim().slice(0,120);});renderProjectList();$('#viewer-project').textContent=state.project.name;}});
window.addEventListener('keydown',e=>{if(e.defaultPrevented||!state.project||state.navigating||state.editBusy)return;const editing=Boolean(e.target?.matches?.('input,textarea,select,[contenteditable]')),dialog=Boolean($('dialog[open]'));if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveProject().catch(e=>toast(e.message,true));return;}if(editing||dialog)return;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();undo(e.shiftKey);return;}if(e.code==='Space'){e.preventDefault();play().catch(e=>toast(e.message,true));}else if(e.key.toLowerCase()==='s')splitSelected();else if(['Delete','Backspace'].includes(e.key)){e.preventDefault();deleteSelected();}else if(e.key==='ArrowRight'){e.preventDefault();stop();switchPreview(false);setFrame(state.frame+(e.shiftKey?state.project.fps:1));}else if(e.key==='ArrowLeft'){e.preventDefault();stop();switchPreview(false);setFrame(state.frame-(e.shiftKey?state.project.fps:1));}else if(e.key==='Escape'){stop();state.selected=null;renderTimeline();renderInspector();}});
window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue='';}});window.addEventListener('resize',()=>{if(state.project)renderTimeline();});
$('#automation-button').addEventListener('click',()=>$('#automation-dialog').showModal());$('#close-automation').addEventListener('click',()=>$('#automation-dialog').close());$$('[data-recipe]').forEach(b=>b.addEventListener('click',()=>automate(b.dataset.recipe)));
frameViewer=new window.CinematicumFrameViewer({request:api,getState:()=>state,image:$('#processed-frame'),status:$('#frame-status'),scopes:$('#scope-canvas'),scopeMode:$('#scope-mode'),prepareSnapshot:async()=>{
  const project=clone(state.project),revision=state.revision;await prepareTitleAssets(project);
  if(state.project.id===project.id){for(const asset of project.assets)if(!state.project.assets.some(a=>a.id===asset.id))state.project.assets.push(asset);if(state.revision===revision)mergePreparedTitles(state.project,project);}
  return project;
}});

async function managedGenerationJob(action){
  if(projectOperationBlocked())throw Error('Wait for the current project operation to finish.');
  if(state.job&&['queued','running'].includes(String(state.job.state).toLowerCase()))throw Error('Finish or cancel the current job first.');
  const projectId=beginProjectOperation();let initial;
  try{initial=await api(projectPath(projectId)+'/generation-'+action,{method:'POST',body:{}});}finally{endProjectOperation();}
  const job=await trackJob(initial,action==='setup'?'Installing local generation':'Starting local generation','generation-'+action,projectId);
  if(job?.state!=='completed')throw Error(job?.error||'Generation runtime operation did not complete.');
  state.capabilities=await api('/api/capabilities');generationReadiness=null;readinessRequest++;renderInspector();return job.result;
}
function openManagedGeneration(){
  if(projectOperationBlocked())return;
  generationEditor??=window.CinematicumManagedGeneration.mount(document.body,{
    getStatus:()=>api('/api/generation-runtime'),setup:()=>managedGenerationJob('setup'),start:()=>managedGenerationJob('start'),
    getJob:()=>state.job,cancel:()=>cancelOwnedJob(),
    stop:async()=>{const result=await api(projectPath(state.project.id)+'/generation-stop',{method:'POST',body:{}});state.capabilities=await api('/api/capabilities');generationReadiness=null;readinessRequest++;renderInspector();return result;},
    useWorkflow:async options=>{
      if(projectOperationBlocked())throw Error('Wait for the current project operation to finish.');
      const projectId=beginProjectOperation();
      try{
        const result=await api(projectPath(projectId)+'/generation-workflow',{method:'POST',body:options||{}});
        if(state.project.id!==projectId)throw Error('The project changed. Reopen it to use its new workflow.');
        state.workflowPath=result.workflow_path;generationReadiness=null;readinessRequest++;
        mutate(()=>{state.project.settings.comfy_workflow_path=result.workflow_path;state.project.settings.comfy_bindings={negative:true,seed:true};},{timeline:false});
        await saveProject(false);renderInspector();return result;
      }finally{endProjectOperation();}
    },onError:error=>toast(error?.message||String(error),true,10000)
  });generationEditor.open();
}
function openEditorial(tab='sequences'){
  if(projectOperationBlocked())return;stop();
  editorialEditor??=window.CinematicumEditorial.mount(document.body,{
    request:api,getProject:()=>clone(state.project),getContext:()=>({projectId:state.project.id,revision:state.revision}),
    getFrame:()=>state.frame,getSelectedClip:()=>state.selected?.type==='clip'?selectedItem():null,onSeek:setFrame,notify:toast,
    onApply:(candidate,expected)=>{
      if(projectOperationBlocked()||state.project.id!==expected.projectId||state.revision!==expected.revision)return false;
      const inventory=state.project.assets,savedRevision=state.project.revision;
      stop();clearMedia();mutate(()=>{state.project=normalizeProject(candidate);state.project.assets=inventory;state.project.revision=savedRevision;state.selected=null;state.selectedAsset=null;state.frame=Math.min(state.frame,Math.max(0,durationFrames()-1));},{inspector:true,bin:true});renderAll();return true;
    }
  });editorialEditor.open(tab);
}
$('#editorial-button').addEventListener('click',()=>openEditorial());
$('#captions-button').addEventListener('click',()=>openEditorial('captions'));
$('#multicam-button').addEventListener('click',()=>openEditorial('multicam'));
$('#source-audio-button').addEventListener('click',()=>openEditorial('audio'));
mediaEditor=window.CinematicumMediaManagement.mount({button:$('#media-management-button'),request:api,notify:toast,
  getContext:()=>({project:state.project,selectedAsset:state.selectedAsset,blocked:state.navigating||state.editBusy}),
  setSettings:settings=>{if(!state.project||projectOperationBlocked())return;mutate(()=>{state.project.settings.preview_proxies=settings;},{timeline:false});},
  onPlaybackChange:()=>{if(!state.project)return;stop();clearMedia();drawPreview();}
});

bootstrap();

// Track and keyframe authoring use the same project history as every clip edit.
$('#add-video-track').addEventListener('click',()=>addTrack(false));
$('#add-audio-track').addEventListener('click',()=>addTrack(true));
$('#ripple-delete').addEventListener('click',rippleDelete);
$('#timeline-content').addEventListener('click',event=>{const b=event.target.closest('[data-track-control]');if(b){const id=Number(b.dataset.trackId),key=b.dataset.trackControl;changeTrack(id,key,!editing.track(state.project,id)[key]);}});
let trackGainCheckpoint=null;
$('#inspector').addEventListener('pointerdown',event=>{if(event.target.dataset.trackGain!==undefined){checkpoint();trackGainCheckpoint=event.target.dataset.trackGain;}});
$('#inspector').addEventListener('input',event=>{
 const input=event.target;if(input.dataset.trackGain===undefined)return;
 if(trackGainCheckpoint!==input.dataset.trackGain){checkpoint();trackGainCheckpoint=input.dataset.trackGain;}
 const id=Number(input.dataset.trackGain);let t=state.project.tracks.find(t=>t.id===id);if(!t){t={...editing.track(state.project,id)};state.project.tracks.push(t);}t.gain=Number(input.value);
 input.parentElement.querySelector('output').textContent=(t.gain?20*Math.log10(t.gain):-80).toFixed(1)+' dB';changed({timeline:false,inspector:false});
});
$('#inspector').addEventListener('change',event=>{
 const input=event.target;
 if(input.dataset.trackGain!==undefined)trackGainCheckpoint=null;
 if(input.dataset.trackName!==undefined)changeTrack(Number(input.dataset.trackName),'name',input.value.trim()||'Track');
 if(input.dataset.keyEasing!==undefined){const c=selectedItem();if(!c||selectionLocked())return;mutate(()=>{const k=c.keyframes.find(k=>k.frame===Number(input.dataset.keyEasing));if(k&&editing.easings[input.value])k.interpolation=input.value;},{timeline:false});}
});
$('#inspector').addEventListener('click',event=>{
 const toggle=event.target.closest('[data-mixer-toggle]');if(toggle){const id=Number(toggle.dataset.trackId),key=toggle.dataset.mixerToggle;changeTrack(id,key,!editing.track(state.project,id)[key]);}
 const jump=event.target.closest('[data-jump-key]');if(jump&&selectedItem())setFrame(selectedItem().start+Number(jump.dataset.jumpKey)-(selectedItem().animation_offset??0));
});

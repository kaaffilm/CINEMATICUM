/* Simultaneous muted camera pictures follow the editor's shared timeline clock.
 * Actual sound continues through the verified source-PCM transport. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const canonical = value => JSON.stringify(value, (_key, item) => item && !Array.isArray(item) && typeof item === 'object' ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
  const number = value => typeof value === 'number' && Number.isFinite(value);
  let invalid = null, lastWarning = '';
  function groupFor(project, clip) {
    if (!clip?.multicam) return {group: null, angle: null};
    const group = project.multicam_groups?.find(g => g.id === clip.multicam.group_id), angle = group?.angles.find(a => a.id === clip.multicam.angle_id);
    if (!angle || angle.asset_id !== clip.asset_id) throw Error('The multicamera clip has a stale source binding. Undo the edit or reopen its saved project.');
    return {group, angle};
  }
  function resolveAudio(project, clip, original) {
    try {
      const {group, angle} = groupFor(project, clip), lock = group?.audio_lock;
      if (!lock) return {clip, asset: original};
      const assets = new Map(project.assets.map(a => [a.id, a])), rate = project.frame_rate || {numerator: project.fps, denominator: 1};
      const expected = {group_id: group.id, project_rate: rate, angles: group.angles.map(a => ({id: a.id, asset_id: a.asset_id, source_sha256: assets.get(a.asset_id)?.sha256, in: a.in}))};
      if (lock.version !== 1 || canonical(lock.clock) !== canonical(expected)) throw Error('The multicamera audio lock is stale after a source or synchronization edit. Undo the edit before playback.');
      const sound = group.angles.find(a => a.id === lock.angle_id), asset = assets.get(sound?.asset_id);
      const stream = asset?.audio_streams?.find(s => s.index === lock.stream_index), map = lock.channels;
      if (!asset?.has_audio || !stream || !Number.isInteger(lock.stream_index) || (map !== null && (!Array.isArray(map) || map.length !== 2 || map.some(v => !Number.isInteger(v) || v < 0 || v >= stream.channels)))) throw Error('The locked sound camera or channel mapping is unavailable.');
      const sourceIn = clip.in + sound.in - angle.in, end = sourceIn + clip.duration * clip.speed;
      if (!number(sourceIn) || sourceIn < -1e-8 || end > Math.min(asset.duration, stream.duration) * project.fps + .5) throw Error('The camera edit extends beyond its locked source audio. Shorten the trim before playback.');
      const effective = {...clip, asset_id: asset.id, in: Math.max(0, sourceIn), audio: {...clip.audio}};
      delete effective.audio.stream_index; delete effective.audio.channels;
      effective.audio.stream_index = lock.stream_index; if (map !== null) effective.audio.channels = [...map];
      return {clip: effective, asset, group, clockOrigin: sourceIn - clip.start * clip.speed};
    } catch (error) {
      if (lastWarning !== error.message) {lastWarning = error.message; invalid?.(error.message);}
      return {error: error.message};
    }
  }
  function mount(host, bridge) {
    const dialog = document.createElement('dialog'); dialog.id = 'multicam-monitor-dialog';
    dialog.innerHTML = `<style>
#multicam-monitor-dialog{width:min(1180px,95vw);max-height:94vh;background:#171b22;color:#e5e9ef;border:1px solid #485366;border-radius:10px;padding:18px}#multicam-monitor-dialog header,.multicam-monitor-transport{display:flex;align-items:center;gap:12px;flex-wrap:wrap}#multicam-monitor-dialog header h2{flex:1;margin:0}#multicam-monitor-dialog button,#multicam-monitor-dialog select,#multicam-monitor-dialog input{font:inherit;color:inherit;background:#242c38;border:1px solid #4d5b6e;border-radius:4px;padding:7px}#multicam-monitor-dialog button:disabled{opacity:.5}#multicam-monitor-dialog [data-monitor-grid]{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;max-height:64vh;overflow:auto;margin:12px 0}#multicam-monitor-dialog figure{margin:0;border:2px solid #45505e;border-radius:5px;padding:5px}#multicam-monitor-dialog figure[data-selected=true]{border-color:#9cbeff}#multicam-monitor-dialog video{width:100%;height:150px;object-fit:contain;background:#000;pointer-events:none}#multicam-monitor-dialog figcaption{display:flex;justify-content:space-between;gap:8px;font-size:12px}#multicam-monitor-dialog [data-monitor-clock]{font-variant-numeric:tabular-nums}#multicam-monitor-dialog [data-monitor-seek]{flex:1;min-width:160px}#multicam-monitor-dialog [data-monitor-status].error{color:#ffb6a7}#multicam-monitor-dialog label{display:inline-flex;gap:7px;align-items:center;margin-right:12px}.multicam-monitor-note{font-size:13px;color:#c0c8d5}
</style><header><h2>Camera monitor</h2><button data-monitor-close aria-label="Close camera monitor">×</button></header>
<p class="multicam-monitor-note">Every angle follows the same edit clock. Click a camera to cut picture at the playhead. The sound choice below applies to this group's clips; clip gain, balance and fades remain authored on the timeline.</p>
<div class="multicam-monitor-transport"><button data-monitor-play>Play</button><input type="range" data-monitor-seek min="0" max="1" step="1" aria-label="Camera monitor playhead"><span data-monitor-clock></span><button data-monitor-save>Save</button></div>
<div data-monitor-grid></div><label>Sound <select data-monitor-audio aria-label="Multicamera sound source"></select></label><button data-monitor-lock>Apply sound choice</button>
<p data-monitor-status role="status"></p>`;
    host.append(dialog); const $ = s => dialog.querySelector(s);
    let snapshot = null, context = null, plan = null, groupId = null, track = null, serial = 0, busy = false, raf = null, disposed = false;
    const videos = new Map(), status = (text, error = false) => { $('[data-monitor-status]').textContent = text; $('[data-monitor-status]').classList.toggle('error', error); };
    const current = () => {const now = bridge.getContext(); return context && now.projectId === context.projectId && now.revision === context.revision && bridge.getProject()?.id === context.projectId;};
    function activeClip(frame = bridge.getFrame()) {
      return bridge.getProject()?.clips.filter(c => c.multicam?.group_id === groupId && c.track === track && frame >= c.start && frame < c.start + c.duration).sort((a,b) => b.start - a.start)[0];
    }
    function controls() {
      for (const node of dialog.querySelectorAll('button,select,input')) node.disabled = busy;
      $('[data-monitor-close]').disabled = false;
    }
    function stopVideos() {for (const video of videos.values()) video.pause();}
    function close() {
      serial++; busy = false; cancelAnimationFrame(raf); raf = null; stopVideos(); bridge.stop?.();
      for (const video of videos.values()) {video.removeAttribute('src'); video.load();} videos.clear();
      if (dialog.open) dialog.close(); plan = null;
    }
    function draw() {
      if (!dialog.open || disposed) return;
      if (!current()) {stopVideos(); bridge.stop?.(); status('The project changed outside this monitor. Reopen the monitor to use the current edit.', true); for (const node of dialog.querySelectorAll('button,select,input')) node.disabled = node !== $('[data-monitor-close]'); return;}
      const project = bridge.getProject(), frame = bridge.getFrame(), clip = activeClip(frame), playing = bridge.isPlaying();
      $('[data-monitor-play]').textContent = playing ? 'Pause' : 'Play'; $('[data-monitor-clock]').textContent = window.CinematicumEditorial.formatTimecode(frame, project); $('[data-monitor-seek]').value = Math.round(frame);
      const group = project.multicam_groups.find(g => g.id === groupId), selected = group?.angles.find(a => a.id === clip?.multicam?.angle_id);
      for (const [id, video] of videos) {
        const angle = group?.angles.find(a => a.id === id), asset = project.assets.find(a => a.id === angle?.asset_id), figure = video.closest('figure'), button = figure.querySelector('button');
        const sourceFrame = clip && selected && angle ? angle.in + window.CinematicumEditing.sourceFrame(clip, frame) - selected.in : NaN;
        const available = number(sourceFrame) && sourceFrame >= 0 && sourceFrame < (asset?.duration || 0) * project.fps;
        figure.dataset.selected = String(id === selected?.id); figure.dataset.sourceFrame = available ? String(sourceFrame) : '';
        const cuttable = clip && clip.speed === 1 && !clip.reverse && !clip.tracking && !clip.compositor;
        button.disabled = busy || !available || !cuttable || id === selected?.id;
        figure.querySelector('[data-monitor-source-clock]').textContent = available ? `Source ${(sourceFrame / project.fps).toFixed(3)} s` : 'Outside source range';
        const missingPicture = video.readyState >= 1 && (!video.videoWidth || !video.videoHeight);
        if (!available || video.error || missingPicture) {video.pause(); if (video.error || missingPicture) figure.querySelector('[data-monitor-source-clock]').textContent = 'Preview unavailable · create a playback proxy'; continue;}
        // Media setters quantize seconds. An exact rational frame boundary
        // can round just below its timestamp and display the preceding frame.
        const seconds = Math.min(asset.duration - 1e-6, sourceFrame / project.fps + (playing ? 0 : 1e-4));
        if (video.readyState >= 1 && !video.seeking && Math.abs(video.currentTime - seconds) > (playing ? Math.max(1 / project.fps, .025) : .005)) {try {video.currentTime = seconds;} catch (_error) {}}
        const speed = clip.speed || 1; if (video.playbackRate !== speed) video.playbackRate = speed;
        if (playing && !clip.reverse && video.readyState >= 2 && !video.seeking) {if (video.paused) video.play().catch(() => {});} else video.pause();
      }
      raf = requestAnimationFrame(draw);
    }
    async function refresh(clip) {
      snapshot = clone(bridge.getProject()); context = clone(bridge.getContext());
      const ticket = serial, frame = Math.max(clip.start, Math.min(clip.start + clip.duration - 1, bridge.getFrame()));
      const response = await bridge.request(`/api/projects/${context.projectId}/editorial`, {method:'POST',body:{project:snapshot,action:'multicam_monitor',values:{clip_id:clip.id,frame}}});
      if (ticket !== serial || !dialog.open) return false;
      if (!current()) throw Error('The project changed while its synchronized monitor was being prepared.');
      plan = response.monitor;
      if (!plan || plan.project_id !== context.projectId || plan.clip_id !== clip.id || plan.group_id !== clip.multicam.group_id) throw Error('The monitor plan has a different project or camera identity.');
      groupId = plan.group_id; track = clip.track;
      const related = snapshot.clips.filter(c => c.multicam?.group_id === groupId && c.track === track);
      $('[data-monitor-seek]').min = Math.min(...related.map(c=>c.start)); $('[data-monitor-seek]').max = Math.max(...related.map(c=>c.start+c.duration-1));
      $('h2').textContent = plan.name;
      $('[data-monitor-audio]').innerHTML = '<option value="">Follow picture camera</option>' + plan.angles.filter(a=>snapshot.assets.find(s=>s.id===a.asset_id)?.has_audio).map(a=>`<option value="${esc(a.id)}">Lock to ${esc(a.name)}</option>`).join('');
      $('[data-monitor-audio]').value = plan.audio_lock?.angle_id || '';
      if (!videos.size) {
        $('[data-monitor-grid]').innerHTML = plan.angles.map(a=>`<figure data-monitor-angle="${esc(a.id)}"><video muted playsinline preload="auto" aria-label="${esc(a.name)} synchronized angle"></video><figcaption><button data-monitor-cut="${esc(a.id)}">${esc(a.name)}</button><span data-monitor-source-clock></span></figcaption></figure>`).join('');
        for (const angle of plan.angles) {
          const video = $(`[data-monitor-angle="${angle.id}"] video`), asset = snapshot.assets.find(a=>a.id===angle.asset_id);
          video.muted = true; video.src = bridge.playbackUrl?.(asset, angle.url) || angle.url; videos.set(angle.id, video);
        }
      }
      status(plan.audio_lock ? 'Sound stays on the selected camera across picture cuts. Source audio controls edit its stream and channel mapping.' : 'Sound follows the picture camera. Choose a fixed camera to keep its sound across cuts.');
      return true;
    }
    async function action(name, values) {
      if (busy || !current()) return; const ticket = serial; busy = true; controls();
      try {
        const project = clone(bridge.getProject()), expected = clone(context), clip = activeClip();
        if (!clip) throw Error('Place the playhead inside this camera group before editing.');
        if (name === 'multicam_audio_lock') bridge.stop?.();
        const response = await bridge.request(`/api/projects/${project.id}/editorial`, {method:'POST',body:{project,action:name,values:{clip_id:clip.id,...values}}});
        if (ticket !== serial || !dialog.open) return;
        if (!current() || response.project?.id !== project.id) throw Error('The project changed before the camera edit could be applied.');
        if (await bridge.onApply(clone(response.project), expected, {action:name}) === false) throw Error('The camera edit was refused because the project changed.');
        context = clone(bridge.getContext());
        const next = activeClip() || bridge.getProject().clips.find(c=>c.multicam?.group_id===groupId && c.track===track);
        if (await refresh(next)) {cancelAnimationFrame(raf); draw();}
      } catch (error) {status(error.message, true);}
      finally {if (ticket === serial) {busy = false; controls();}}
    }
    $('[data-monitor-close]').addEventListener('click', close); dialog.addEventListener('cancel', e=>{e.preventDefault();close();});
    dialog.addEventListener('keydown', event=>event.stopPropagation());
    $('[data-monitor-play]').addEventListener('click', ()=>{if (!busy) Promise.resolve(bridge.play()).catch(error=>status(error.message,true));});
    $('[data-monitor-seek]').addEventListener('input', event=>{bridge.stop?.();bridge.seek(Number(event.target.value));});
    $('[data-monitor-save]').addEventListener('click', ()=>{if (!busy) Promise.resolve(bridge.save()).then(()=>status('Camera edit saved.')).catch(error=>status(error.message,true));});
    $('[data-monitor-lock]').addEventListener('click', ()=>action('multicam_audio_lock',{angle_id:$('[data-monitor-audio]').value||null}));
    $('[data-monitor-grid]').addEventListener('click', event=>{const button=event.target.closest('[data-monitor-cut]');if(button&&!button.disabled)void action('multicam_cut',{angle_id:button.dataset.monitorCut,frame:Math.floor(bridge.getFrame())});});
    return {async open(clip) {
      close(); if (!clip?.multicam) {bridge.notify?.('Select a multicamera timeline clip to open its monitor.',true);return;}
      dialog.showModal(); busy=true;controls();status('Opening the verified synchronized cameras…');
      try {bridge.seek(Math.max(clip.start,Math.min(clip.start+clip.duration-1,bridge.getFrame())));if(await refresh(clip))draw();}
      catch(error){status(error.message,true);}finally{busy=false;controls();}
    }, close, reset:close, destroy(){close();disposed=true;dialog.remove();}};
  }
  window.CinematicumMulticam = {resolveAudio,groupFor,mount,configure(callback){invalid=callback;lastWarning='';}};
})();

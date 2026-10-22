// Executes only shipped UI controls and reads the actual owned backend.
// Fixture admission uses the real file input; it does not invent imported assets.
const SYNC_FIXTURE = /* ENGINE_TEST_CONFIG */ {};
return await (async () => {
  const began = performance.now(), deadline = began + 14000, steps = [];
  const result = {operation: SYNC_FIXTURE.operation}, $ = selector => document.querySelector(selector);
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const detail = () => `; project=${$('#project-select')?.value}; sync=${$('[data-sync-status]')?.textContent}; job=${$('#job-detail')?.textContent}; toast=${$('#toast')?.textContent}`;
  function require(value, message) {if (!value) throw Error(message + detail());}
  function control(selector) {
    const node = $(selector); require(node && !node.disabled && !node.closest('[inert]'), `Unavailable control ${selector}`);
    node.scrollIntoView({block: 'nearest'}); return node;
  }
  const click = selector => control(selector).click();
  function set(selector, value) {
    const node = control(selector);
    if (node.type === 'checkbox') node.checked = Boolean(value); else node.value = String(value);
    node.dispatchEvent(new Event('input', {bubbles: true}));
    node.dispatchEvent(new Event('change', {bubbles: true}));
  }
  async function until(fn, label, ms = 1800) {
    const end = Math.min(deadline, performance.now() + ms);
    while (performance.now() < end) {if (fn()) return; await pause(20);}
    throw Error(label + detail());
  }
  async function get(url) {const r = await fetch(url); require(r.ok, `GET failed ${url}`); return r.json();}
  const readProject = () => get(`/api/projects/${SYNC_FIXTURE.project_id}`);
  async function selectProject(id, name) {
    if ($('#project-select').value !== id) set('#project-select', id);
    await until(() => $('#project-select')?.value === id && !$('#project-select').disabled && $('#viewer-project')?.textContent === name, 'Exact fixture project did not open', 2600);
  }
  async function save() {click('#save-project'); await until(() => $('#save-state')?.textContent === 'SAVED LOCALLY', 'The actual edit did not save');}
  async function reopen() {
    await selectProject(SYNC_FIXTURE.sentinel_id, SYNC_FIXTURE.sentinel_name);
    await selectProject(SYNC_FIXTURE.project_id, SYNC_FIXTURE.project_name);
  }
  function selectClip(id) {
    const node = control(`.timeline-clip[data-clip="${id}"]`), r = node.getBoundingClientRect();
    node.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, buttons: 1, pointerId: 41, isPrimary: true, clientX: r.left + 15, clientY: r.top + 12}));
    window.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, button: 0, buttons: 0, pointerId: 41, isPrimary: true}));
  }
  async function author() {
    const initial = await readProject(); require(!initial.assets.length && !initial.clips.length, 'Import fixture was not empty');
    const transfer = new DataTransfer();
    for (let i = 0; i < SYNC_FIXTURE.cameras.length; i++) {
      const response = await fetch(`/__engine_test__/camera/${i}`); require(response.ok, 'The original fixture camera could not be read');
      transfer.items.add(new File([await response.blob()], SYNC_FIXTURE.cameras[i].name, {type: 'video/x-matroska'}));
    }
    const input = control('#media-input'); input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles: true}));
    await until(() => $('#asset-count')?.textContent.trim() === '3' && $('#media-footer-label')?.textContent === 'Media is copied into your project', 'Actual three-camera import did not finish', 9500);
    const admitted = await readProject();
    require(admitted.assets.length === 3 && admitted.assets.every(a => a.kind === 'video' && a.width === 64 && a.height === 48 && SYNC_FIXTURE.cameras.some(c => c.name === a.name && c.identity.sha256 === a.sha256)), 'Imported camera bytes or format differ');
    require(!admitted.clips.length, 'Import unexpectedly created a timeline edit');
    steps.push('three_original_camera_files_imported_through_shipped_input', 'import_did_not_silently_assemble_a_cut');
    await reopen(); require(same((await readProject()).assets, admitted.assets), 'Admitted source inventory did not reopen');
    steps.push('admitted_sources_saved_and_reopened'); return {};
  }
  async function synchronize() {
    const initial = await readProject(); require(initial.assets.length === 3 && !initial.clips.length && !(initial.multicam_groups || []).length, 'The untouched three-camera fixture did not survive restart');
    click('#multicam-button'); await until(() => $('.editorial-dialog')?.open, 'Multicam controls did not open');
    click('[data-auto-sync]'); await until(() => $('.multicam-sync-dialog')?.open && !$('[data-sync-analyze]')?.disabled, 'The actual correlation runtime did not become available', 3500);
    const assets = Object.fromEntries(initial.assets.map(a => [a.name, a]));
    for (const camera of SYNC_FIXTURE.cameras) set(`[data-sync-source="${assets[camera.name].id}"] [data-sync-use]`, true);
    const reference = assets['ENGINE_TEST_reference.mkv'], multi = assets['ENGINE_TEST_multi.mkv'];
    set('[data-sync-reference]', reference.id); set('[data-sync-window]', 12); set('[data-sync-lag]', 2);
    set(`[data-sync-source="${multi.id}"] [data-sync-stream]`, 2); set(`[data-sync-source="${multi.id}"] [data-sync-channel]`, 1);
    const button = control('[data-sync-analyze]'), rect = button.getBoundingClientRect(), hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    require(hit === button || button.contains(hit), 'The synchronization control is not visibly hit-testable');
    click('[data-sync-analyze]'); await until(() => $('[data-sync-status]')?.textContent.startsWith('Audio offsets verified.') && !$('[data-sync-apply]')?.disabled, 'Actual selected-channel synchronization did not pass', 8500);
    const links = [...document.querySelectorAll('[data-sync-results] a')], receiptLink = links.find(a => new URL(a.href).pathname.endsWith('/receipt.json'));
    require(receiptLink, 'No owned source receipt was shown');
    const match = new URL(receiptLink.href).pathname.match(/^\/api\/projects\/([a-f0-9]{32})\/multicam-sync\/outputs\/([a-f0-9]{32})\/receipt\.json$/);
    require(match?.[1] === SYNC_FIXTURE.project_id, 'The displayed receipt belongs to another project'); result.job_id = match[2];
    const job = await get(`/api/jobs/${result.job_id}`), measured = job.result;
    require(job.kind === 'multicam-sync' && job.state === 'completed' && job.project_id === SYNC_FIXTURE.project_id && measured?.accepted === true, 'Displayed measurement is not an owned completed job');
    const values = Object.fromEntries(measured.analysis.angles.map(a => [a.asset_id, a]));
    require(values[multi.id].offset_samples === 11819 && values[assets['ENGINE_TEST_negative.mkv'].id].offset_samples === -7517 && values[assets['ENGINE_TEST_negative.mkv'].id].polarity === -1, 'Measured sample offsets or inverted polarity are wrong');
    require(document.querySelectorAll('[data-sync-plots] canvas').length === 3 && [...document.querySelectorAll('[data-sync-plots] canvas')].every(c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data.some(v => v !== 0)), 'Actual measured waveforms were not drawn');
    require(same(await readProject(), initial), 'Measurement silently mutated the saved project');
    steps.push('selected_nondefault_stream_channel_and_signed_offsets_measured', 'three_actual_waveforms_drawn_without_silent_edit');
    result.clicked_downloads = [];
    for (const name of ['analysis.json', 'waveforms.json', 'receipt.json']) {
      const link = links.find(a => new URL(a.href).pathname.endsWith('/' + name)); require(link, 'Missing measured artifact');
      const url = new URL(link.href); require(url.origin === location.origin && !url.search && !url.hash, 'Artifact link escaped the owned server');
      result.clicked_downloads.push({name, url: url.pathname}); link.click(); await pause(25);
    }
    set('[data-sync-name]', 'ENGINE TEST measured cameras'); click('[data-sync-apply]');
    await until(() => $('[data-sync-status]')?.textContent.startsWith('Synchronized cut created.'), 'The measured candidate did not apply');
    require(same(await readProject(), initial), 'Apply unexpectedly saved before the Save action');
    click('[data-sync-close]'); await save(); const saved = await readProject();
    require(saved.clips.length === 1 && saved.clips[0].duration === 278 && saved.clips[0].asset_id === reference.id && saved.multicam_groups.length === 1, 'The common-window reference cut is incorrect');
    require(saved.clips[0].in === 11819 / 2000, 'The fractional source-frame offset was rounded');
    require(saved.clips[0].audio?.stream_index == null && saved.clips[0].audio?.channels == null, 'Analysis selection changed the playback mix');
    click('#undo-button'); await save(); const undone = await readProject();
    require(!undone.clips.length && !(undone.multicam_groups || []).length && same(undone.assets, initial.assets), 'One undo did not restore the previous edit and preserve source inventory');
    click('#redo-button'); await save(); require(same((await readProject()).clips, saved.clips) && same((await readProject()).multicam_groups, saved.multicam_groups), 'Redo lost the exact measured cut');
    await reopen(); const reopened = await readProject(); require(same(reopened.clips, saved.clips) && same(reopened.multicam_groups, saved.multicam_groups), 'Save/reopen lost the measured edit');
    steps.push('source_sample_precision_and_default_playback_mix_preserved', 'one_undo_redo_save_and_reopen_of_synchronized_edit', 'three_real_measurement_downloads_requested');
    return {expect_download: true};
  }
  async function render() {
    const initial = await readProject(), group = initial.multicam_groups?.[0];
    require(group?.angles.length === 3 && initial.clips.length === 1 && initial.clips[0].duration === 278, 'The saved sample-accurate group did not survive backend restart');
    const multi = initial.assets.find(a => a.name === 'ENGINE_TEST_multi.mkv'), target = group.angles.find(a => a.asset_id === multi.id);
    click('#jump-start'); for (let frame = 0; frame < 120; frame++) click('#step-forward');
    require($('#timecode').textContent === '00:00:05:00', 'The authored camera cut is not at frame 120'); selectClip(initial.clips[0].id);
    click('#multicam-button'); await until(() => $('.editorial-dialog')?.open && $(`[data-angle="${target.id}"]`), 'Measured camera angles did not open');
    click(`[data-angle="${target.id}"]`); await until(() => $('.editorial-dialog [data-status]')?.textContent.startsWith('Applied.'), 'Actual multicamera cut did not apply');
    click('.editorial-dialog [aria-label="Close editorial controls"]'); await save();
    const cut = await readProject(), second = cut.clips.find(c => c.start === 120);
    require(cut.clips.length === 2 && second?.asset_id === multi.id && second.in === 120 && second.duration === 158 && cut.clips.find(c => c.start === 0).duration === 120, 'Camera cut lost its exact common sample clock');
    require(second.audio?.stream_index == null && second.audio?.channels == null, 'Analysis channels silently replaced the new camera playback mix');
    selectClip(second.id); click('#source-audio-button'); await until(() => $('.editorial-dialog')?.open && $('[data-audio-stream]'), 'Selected camera source audio did not open');
    set('[data-audio-stream]', 2); set('[data-audio-left]', 1); set('[data-audio-right]', 1); click('[data-apply-audio]');
    await until(() => $('.editorial-dialog [data-status]')?.textContent.startsWith('Applied.'), 'Explicit camera playback mapping did not apply');
    click('.editorial-dialog [aria-label="Close editorial controls"]'); await save();
    const mapped = await readProject(), audio = mapped.clips.find(c => c.id === second.id).audio;
    require(audio.stream_index === 2 && same(audio.channels, [1, 1]), 'The explicit nondefault playback channel mapping was not saved');
    await reopen(); require(same((await readProject()).clips, mapped.clips) && same((await readProject()).multicam_groups, group && [group]), 'Reopen lost the measured cut or explicit mapping');
    steps.push('saved_measured_group_survived_backend_restart', 'camera_switch_at_frame_120_preserved_sample_alignment', 'analysis_did_not_change_mix_and_explicit_playback_mapping_saved');
    click('#export-button'); click('[data-export="prores"]');
    await until(() => !$('#download-job')?.hidden && $('#job-label')?.textContent === 'ProRes export complete', 'The actual ProRes/PCM camera cut did not finish', 9000);
    const link = control('#download-job'), url = new URL(link.href);
    require(url.origin === location.origin && url.pathname.startsWith(`/api/projects/${SYNC_FIXTURE.project_id}/exports/`) && url.pathname.endsWith('.mov'), 'Rendered download escaped the owned export');
    result.download_href = url.pathname + url.search; result.download_name = link.download; link.click();
    steps.push('actual_prores_pcm_render_and_download_requested'); return {expect_download: true};
  }
  try {
    await until(() => $('#project-select') && !$('#project-select').disabled && [...$('#project-select').options].some(o => o.value === SYNC_FIXTURE.project_id), 'The exact owned project did not bootstrap', 3000);
    await selectProject(SYNC_FIXTURE.project_id, SYNC_FIXTURE.project_name);
    const operation = {author, synchronize, render}[SYNC_FIXTURE.operation]; require(operation, 'Unknown multicamera phase');
    const extra = await operation(); return {...result, ...extra, passed: true, steps, elapsed_ms: Math.round(performance.now() - began)};
  } catch (error) {return {...result, passed: false, steps, error: String(error), elapsed_ms: Math.round(performance.now() - began)};}
})();

// Real shipped controls only. The coordinator supplies exact owned fixture IDs,
// original photograph names/hashes and a prior completed job ID when applicable.
const RECON_FIXTURE = /* ENGINE_TEST_CONFIG */ {};
return await (async () => {
  const began = performance.now(), deadline = began + 13500, steps = [];
  const result = {operation: RECON_FIXTURE.operation};
  const $ = selector => document.querySelector(selector);
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const detail = () => `; project=${$('#project-select')?.value || ''}; status=${$('[data-recon-status]')?.textContent || ''}; toast=${$('#toast')?.textContent || ''}`;
  function require(value, label) { if (!value) throw Error(label + detail()); }
  function control(selector) {
    const node = $(selector);
    require(node && !node.disabled && !node.closest('[inert]'), `Unavailable control ${selector}`);
    node.scrollIntoView({block: 'nearest'}); return node;
  }
  const click = selector => control(selector).click();
  function set(selector, value) {
    const node = control(selector);
    if (node.type === 'checkbox') node.checked = Boolean(value); else node.value = String(value);
    node.dispatchEvent(new Event('input', {bubbles: true}));
    node.dispatchEvent(new Event('change', {bubbles: true}));
  }
  async function until(fn, label, ms = 1600) {
    const end = Math.min(deadline, performance.now() + ms);
    while (performance.now() < end) { if (fn()) return; await pause(20); }
    throw Error(label + detail());
  }
  async function get(url) {
    const response = await fetch(url); require(response.ok, `GET failed: ${url}`); return response.json();
  }
  const readProject = () => get(`/api/projects/${RECON_FIXTURE.project_id}`);
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  async function selectProject(id, name) {
    if ($('#project-select').value !== id) set('#project-select', id);
    await until(() => $('#project-select')?.value === id && !$('#project-select').disabled && $('#viewer-project')?.textContent === name, 'Exact owned project did not open', 2200);
  }
  async function saveProject() {
    click('#save-project');
    await until(() => $('#save-state')?.textContent === 'SAVED LOCALLY', 'The edit did not save to the real backend');
  }
  async function openTool() {
    click('#authoring-tools');
    await until(() => $('#authoring-tools-dialog')?.open, 'Studio tools did not open');
    click('[data-authoring-tool="reconstruction"]');
    await until(() => $('#reconstruction-dialog')?.open && !$('[data-recon-run]')?.disabled, 'The installed COLMAP tool did not become ready', 3500);
    require(/COLMAP 4\.2\.1/.test($('[data-recon-runtime]').textContent), 'The actual pinned COLMAP runtime was not detected');
    const dialog = control('#reconstruction-dialog'), run = control('[data-recon-run]');
    const box = dialog.getBoundingClientRect(), rect = run.getBoundingClientRect();
    require(box.left >= 0 && box.right <= innerWidth + .5 && box.top >= 0 && box.bottom <= innerHeight + .5, 'The reconstruction panel exceeds the viewport');
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    require(hit === run || run.contains(hit), 'The reconstruction run control is not visibly hit-testable');
    result.control_geometry = {viewport: [innerWidth, innerHeight], button: [rect.x, rect.y, rect.width, rect.height]};
  }
  async function openSaved() {
    await openTool();
    await until(() => [...$('[data-recon-history]').options].some(option => option.value === RECON_FIXTURE.job_id), 'The exact prior result is absent from durable history');
    set('[data-recon-history]', RECON_FIXTURE.job_id); click('[data-recon-open-saved]');
    await until(() => $('[data-recon-status]')?.textContent.includes('Saved measured reconstruction reopened') && $('[data-recon-camera]')?.options.length === 8, 'The actual eight-camera result did not reopen');
    require($('[data-recon-history]').value === RECON_FIXTURE.job_id, 'A different reconstruction result was selected');
  }
  async function author() {
    const initial = await readProject();
    require(initial.assets.length === 0 && !initial.reconstruction && initial.width === 640 && initial.height === 360, 'The author phase did not start with the exact new empty fixture');
    const transfer = new DataTransfer();
    for (let index = 0; index < RECON_FIXTURE.photos.length; index++) {
      const response = await fetch(`/__engine_test__/photo/${index}`);
      require(response.ok, 'The original independent photograph could not be read');
      const blob = await response.blob();
      transfer.items.add(new File([blob], RECON_FIXTURE.photos[index].name, {type: 'image/png'}));
    }
    const input = control('#media-input'); input.files = transfer.files;
    input.dispatchEvent(new Event('change', {bubbles: true}));
    await until(() => $('#asset-count')?.textContent.trim() === '8' && $('#media-footer-label')?.textContent === 'Media is copied into your project', 'The shipped media importer did not admit all eight photographs', 6500);
    const imported = await readProject();
    require(imported.assets.length === 8 && imported.assets.every(asset => asset.kind === 'image' && asset.width === 640 && asset.height === 480 && RECON_FIXTURE.photos.some(photo => photo.name === asset.name && photo.identity.sha256 === asset.sha256)), 'Actual image admission changed source bytes or geometry');
    steps.push('imported_eight_original_photographs_through_shipped_file_input');
    await openTool(); click('[data-recon-select-all]');
    set('[data-recon-model]', 'PINHOLE'); set('[data-recon-params]', '650, 650, 320, 240');
    set('[data-recon-refine]', false); set('[data-recon-max-image-size]', 640); set('[data-recon-marker-limit]', 150);
    click('[data-recon-save]');
    await until(() => $('[data-recon-status]')?.textContent.includes('settings saved') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'The authored calibration did not save');
    const edited = await readProject();
    require(edited.reconstruction.asset_ids.length === 8 && edited.reconstruction.camera_model === 'PINHOLE' && same(edited.reconstruction.camera_params, [650, 650, 320, 240]) && edited.reconstruction.refine_intrinsics === false && edited.reconstruction.marker_limit === 150, 'The exact calibrated settings did not persist');
    steps.push('saved_typed_eight_photo_calibration');
    click('[data-recon-close]'); click('#undo-button'); await saveProject();
    const undone = await readProject();
    require(!undone.reconstruction && same(undone.assets, imported.assets) && same(undone.settings.scene, initial.settings.scene), 'One Undo changed admitted photos or failed to remove only the authored settings');
    click('#redo-button'); await saveProject();
    require(same((await readProject()).reconstruction, edited.reconstruction), 'Redo did not restore the exact calibration');
    await selectProject(RECON_FIXTURE.sentinel_id, RECON_FIXTURE.sentinel_name);
    await selectProject(RECON_FIXTURE.project_id, RECON_FIXTURE.project_name);
    await openTool();
    require($('[data-recon-model]').value === 'PINHOLE' && $('[data-recon-params]').value === '650, 650, 320, 240' && !$('[data-recon-refine]').checked && Number($('[data-recon-marker-limit]').value) === 150, 'Reopening lost the authored numeric calibration');
    steps.push('calibration_undo_redo_and_exact_project_reopen');
    return {};
  }
  async function solve() {
    const initial = await readProject();
    require(initial.reconstruction?.asset_ids.length === 8 && initial.height === 360, 'The saved calibration did not survive backend restart');
    steps.push('saved_calibration_survived_backend_restart');
    await openTool(); click('[data-recon-run]');
    await until(() => $('[data-recon-status]')?.textContent.includes('Actual COLMAP reconstruction completed') && !$('[data-recon-run]')?.disabled, 'Actual CPU COLMAP extraction, matching and bundle adjustment did not complete', 11000);
    await until(() => $('[data-recon-preview]')?.complete && $('[data-recon-preview]')?.naturalWidth > 0, 'The actual corrected-photo preview did not decode');
    const link = [...$('[data-recon-links]').querySelectorAll('a')].find(a => a.download === 'provenance.json');
    require(link, 'The actual solver receipt link is absent');
    const url = new URL(link.href), match = url.pathname.match(/^\/api\/projects\/([a-f0-9]{32})\/reconstruction\/outputs\/([a-f0-9]{32})\/provenance\.json$/);
    require(url.origin === location.origin && match?.[1] === RECON_FIXTURE.project_id, 'The result belongs to an unexpected project');
    result.job_id = match[2];
    const receipt = await get(url.pathname), job = await get(`/api/jobs/${result.job_id}`);
    require(job.id === result.job_id && job.project_id === RECON_FIXTURE.project_id && job.kind === 'reconstruction' && job.state === 'completed', 'The displayed result is not the owned actual completed reconstruction job');
    const stats = receipt.statistics;
    require(receipt.engine.name === 'COLMAP' && receipt.engine.device === 'CPU' && stats.registered_images === 8 && stats.points3D > 1000 && stats.observations > 5000 && stats.reprojection.rms_pixels < .5, 'The actual sparse solution failed the measured geometry bounds');
    const after = await readProject();
    require(same(after.settings.scene, initial.settings.scene) && after.width === 640 && after.height === 360 && same(after.reconstruction, initial.reconstruction), 'Job completion silently applied or changed the saved scene/calibration');
    require($('[data-recon-camera]').options.length === 8 && !$('[data-recon-resize]').checked, 'The result did not expose eight measured cameras with resize initially unchecked');
    result.statistics = stats;
    steps.push('actual_cpu_colmap_eight_view_solve_and_decoded_preview', 'completion_did_not_silently_apply_the_scene');
    return {};
  }
  async function apply() {
    const initial = await readProject();
    require(initial.width === 640 && initial.height === 360 && !initial.settings.scene.objects.some(o => o.id.startsWith('reconstruction_points_')), 'The immutable prior result was already applied');
    await openSaved();
    require(!$('[data-recon-resize-label]').hidden && !$('[data-recon-resize]').checked, 'Resize consent was not initially explicit and unchecked');
    click('[data-recon-apply-result]');
    await until(() => $('[data-recon-status]')?.textContent.includes('resolution differs'), 'The unchecked resolution mismatch was not rejected');
    require(same(await readProject(), initial), 'Rejected resolution change mutated the saved project');
    steps.push('saved_result_reopened_after_backend_restart', 'unchecked_resolution_change_refused_without_mutation');
    const links = [...$('[data-recon-links]').querySelectorAll('a')];
    result.clicked_downloads = [];
    for (const name of ['sparse.ply', 'undistorted-images.zip', 'provenance.json']) {
      const link = links.find(a => a.download === name); require(link, `Missing actual artifact ${name}`);
      const url = new URL(link.href), expected = `/api/projects/${RECON_FIXTURE.project_id}/reconstruction/outputs/${RECON_FIXTURE.job_id}/${name}`;
      require(url.origin === location.origin && url.pathname === expected && !url.search && !url.hash, 'Download escaped its exact owned result');
      result.clicked_downloads.push({name, url: url.pathname}); link.click(); await pause(30);
    }
    steps.push('clicked_three_real_owned_artifact_downloads');
    const selectedCamera = $('[data-recon-camera]').value;
    set('[data-recon-resize]', true); click('[data-recon-apply-result]');
    await until(() => $('[data-recon-status]')?.textContent.includes('Measured camera and sparse point markers saved') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'The checked camera/canvas edit did not save atomically');
    const applied = await readProject(), marker = `reconstruction_points_${RECON_FIXTURE.job_id.slice(0, 16)}`;
    require(applied.width === 640 && applied.height === 480 && applied.settings.scene.width === 640 && applied.settings.scene.height === 480 && applied.settings.scene.objects.filter(o => o.id === marker).length === 1, 'The explicit resize, measured camera and markers were not one saved edit');
    require(same(applied.settings.scene.objects.filter(o => o.id !== marker), initial.settings.scene.objects), 'Application changed existing authored objects');
    result.selected_camera_id = selectedCamera; result.marker_id = marker;
    click('[data-recon-close]'); click('#undo-button'); await saveProject();
    const undone = await readProject();
    require(undone.width === 640 && undone.height === 360 && same(undone.settings.scene, initial.settings.scene), 'One Undo did not restore both the entire preceding scene and canvas');
    click('#redo-button'); await saveProject();
    require(same((await readProject()).settings.scene, applied.settings.scene) && (await readProject()).height === 480, 'Redo did not restore the measured scene and canvas');
    await selectProject(RECON_FIXTURE.sentinel_id, RECON_FIXTURE.sentinel_name);
    await selectProject(RECON_FIXTURE.project_id, RECON_FIXTURE.project_name);
    require(same((await readProject()).settings.scene, applied.settings.scene) && (await readProject()).height === 480, 'The actual saved measured scene did not reopen');
    steps.push('explicit_camera_canvas_application_one_undo_redo_and_reopen');
    await openSaved(); click('[data-recon-apply-result]');
    await until(() => $('[data-recon-status]')?.textContent.includes('already exist'), 'Duplicate sparse markers were not refused');
    require((await readProject()).settings.scene.objects.filter(o => o.id === marker).length === 1, 'Duplicate application changed the sparse marker count');
    steps.push('duplicate_marker_application_refused');
    return {expect_download: true};
  }
  try {
    await until(() => $('#project-select') && !$('#project-select').disabled && [...$('#project-select').options].some(option => option.value === RECON_FIXTURE.project_id), 'The owned fixture project did not bootstrap', 2600);
    await selectProject(RECON_FIXTURE.project_id, RECON_FIXTURE.project_name);
    steps.push('selected_exact_owned_fixture_project');
    const run = {author, solve, apply}[RECON_FIXTURE.operation]; require(run, 'Unknown native reconstruction phase');
    const extras = await run();
    return {...result, ...extras, passed: true, steps, elapsed_ms: Math.round(performance.now() - began)};
  } catch (error) {
    return {...result, passed: false, steps, error: String(error), elapsed_ms: Math.round(performance.now() - began)};
  }
})();

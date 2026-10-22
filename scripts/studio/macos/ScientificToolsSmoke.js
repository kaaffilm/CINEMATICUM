// Real shipped controls in an owned synthetic project. The native coordinator
// supplies identifiers only; this script never injects application state/jobs.
const SCIENTIFIC_FIXTURE = /* ENGINE_TEST_CONFIG */ {};
return await (async () => {
  const began = performance.now(), deadline = began + 13500, steps = [];
  const result = {operation: SCIENTIFIC_FIXTURE.operation};
  const $ = selector => document.querySelector(selector);
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const detail = () => `; project=${$('#project-select')?.value || ''}; status=${$('[data-optics-status]')?.textContent || $('[data-physical-status]')?.textContent || ''}; toast=${$('#toast')?.textContent || ''}`;
  function require(value, message) { if (!value) throw Error(message + detail()); }
  function control(selector) {
    const node = $(selector);
    require(node && !node.disabled && !node.closest('[inert]'), `Unavailable control ${selector}`);
    node.scrollIntoView({block: 'nearest'}); return node;
  }
  const click = selector => control(selector).click();
  function set(selector, value) {
    const node = control(selector); node.value = String(value);
    node.dispatchEvent(new Event('input', {bubbles: true}));
    node.dispatchEvent(new Event('change', {bubbles: true}));
  }
  async function until(fn, label, ms = 1400) {
    const end = Math.min(deadline, performance.now() + ms);
    while (performance.now() < end) { if (fn()) return; await pause(20); }
    throw Error(label + detail());
  }
  async function get(url) {
    const response = await fetch(url); require(response.ok, `GET failed: ${url}`);
    return response.json();
  }
  const readProject = () => get(`/api/projects/${SCIENTIFIC_FIXTURE.project_id}`);
  async function selectProject(id, name) {
    if ($('#project-select').value !== id) set('#project-select', id);
    await until(() => $('#project-select')?.value === id && !$('#project-select').disabled && $('#viewer-project')?.textContent === name, 'Exact owned project did not open', 2000);
  }
  async function saveProject() {
    click('#save-project');
    await until(() => $('#save-state')?.textContent === 'SAVED LOCALLY', 'Saved edit did not reach the real backend');
  }
  async function open(tool, dialog, button) {
    click('#authoring-tools');
    await until(() => $('#authoring-tools-dialog')?.open, 'Studio tools did not open');
    click(`[data-authoring-tool="${tool}"]`);
    await until(() => $(dialog)?.open && !$(button)?.disabled, 'Actual installed engine did not make the tool ready', 7000);
    const box = control(dialog).getBoundingClientRect(), run = control(button), rect = run.getBoundingClientRect();
    require(box.left >= 0 && box.right <= innerWidth + .5 && box.top >= 0 && box.bottom <= innerHeight + .5, 'Scientific tool exceeds native viewport');
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    require(hit === run || run.contains(hit), 'Run control is not visibly hit-testable');
    result.control_geometry = {viewport: [innerWidth, innerHeight], button: [rect.x, rect.y, rect.width, rect.height]};
  }
  async function undoRedoReopen(field, closeSelector) {
    click(closeSelector); click('#undo-button'); await saveProject();
    require(!(await readProject())[field], 'One Undo did not restore the preceding absent authored document');
    click('#redo-button'); await saveProject();
    require((await readProject())[field], 'Redo did not persist the authored document');
    await selectProject(SCIENTIFIC_FIXTURE.sentinel_id, SCIENTIFIC_FIXTURE.sentinel_name);
    await selectProject(SCIENTIFIC_FIXTURE.project_id, SCIENTIFIC_FIXTURE.project_name);
    steps.push('one_saved_edit_undo_redo_and_exact_project_reopen');
  }
  function downloadLink(selector, filename) {
    const link = [...control(selector).querySelectorAll('a')].find(a => a.download === filename);
    require(link, 'The actual result has no requested download link');
    const url = new URL(link.href);
    require(url.origin === location.origin && url.pathname.startsWith(`/api/projects/${SCIENTIFIC_FIXTURE.project_id}/`), 'Download belongs to an unexpected project');
    result.download_url = url.pathname + url.search; result.download_filename = filename;
    result.output_id = url.pathname.split('/').at(-2);
    return link;
  }
  async function opticsEdit() {
    const dialog = '#ray-optics-dialog', run = '[data-optics-analyze]';
    await open('ray-optics', dialog, run);
    require($('[data-optics-surfaces]').children.length === 2 && $('[data-optics-waves]').children.length === 3, 'Actual default prescription did not load');
    set('[data-optics-name]', 'ENGINE TEST Native edited crown singlet');
    set('[data-optics-aperture]', 8);
    set('[data-optics-surfaces] [data-id="s1"] [data-key="radius"]', 60);
    set('[data-optics-surfaces] [data-id="s1"] [data-key="thickness"]', 4);
    set('[data-optics-surfaces] [data-id="s2"] [data-key="radius"]', -60);
    set('[data-optics-surfaces] [data-id="s2"] [data-key="thickness"]', 57.2);
    // One explicit on-axis field keeps a complete optical analysis within this
    // foreground UI acceptance. The separate physics suite covers off-axis fields.
    click('[data-optics-fields] tr:nth-child(3) button');
    click('[data-optics-fields] tr:nth-child(2) button');
    require($('[data-optics-surfaces] [data-id="s1"] [data-key="material"]').value === 'schott:N-BK7', 'The exact packaged glass was not retained');
    click('[data-optics-save]');
    await until(() => $('[data-optics-status]')?.textContent.includes('prescription saved') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'Edited prescription did not save');
    const first = await readProject();
    require(first.ray_optics?.surfaces[0].radius === 60 && first.ray_optics.aperture.value === 8, 'Saved numeric prescription differs from controls');
    steps.push('authored_and_saved_actual_optical_prescription');
    await undoRedoReopen('ray_optics', '[data-optics-close]');
    require(JSON.stringify((await readProject()).ray_optics) === JSON.stringify(first.ray_optics), 'The exact reopened project lost its saved optical prescription');
    steps.push('reopened_project_retains_exact_optical_document');
    return {};
  }
  async function opticsRender() {
    const dialog = '#ray-optics-dialog', run = '[data-optics-analyze]';
    const first = await readProject();
    require(first.ray_optics?.surfaces[0].radius === 60 && first.ray_optics.aperture.value === 8, 'The saved optical fixture did not survive backend restart');
    steps.push('saved_optical_document_survives_backend_restart');
    await open('ray-optics', dialog, run);
    require(Number($('[data-optics-aperture]').value) === 8 && Number($('[data-optics-surfaces] [data-id="s1"] [data-key="radius"]').value) === 60 && Number($('[data-optics-surfaces] [data-id="s2"] [data-key="thickness"]').value) === 57.2, 'Exact reopened optical document lost its edits');
    set('[data-optics-rings]', 2); set('[data-optics-fans]', 9);
    set('[data-optics-pupil]', 16); set('[data-optics-grid]', 64);
    steps.push('reopened_numeric_controls_match_saved_prescription');
    click(run);
    await until(() => !$(run)?.disabled && !$('[data-optics-results]')?.hidden && $('[data-optics-status]')?.textContent.includes('analysis completed'), 'Actual Optiland job did not complete', 7500);
    await until(() => [...$('[data-optics-images]').querySelectorAll('img')].length === 4 && [...$('[data-optics-images]').querySelectorAll('img')].every(img => img.complete && img.naturalWidth > 0), 'Actual ray/spot/PSF/MTF images did not decode');
    const link = downloadLink('[data-optics-artifacts]', 'psf.npz');
    const base = new URL(link.href).pathname.replace(/psf\.npz$/, '');
    const receipt = await get(base + 'receipt.json'), analysis = await get(base + 'analysis.json');
    require(receipt.recipe.prescription.surfaces[0].radius === 60 && receipt.recipe.analysis.fft_grid === 64 && receipt.runtime.packages.optiland === '0.6.3', 'Real optical receipt does not bind the authored settings/runtime');
    require(analysis.spots.length === 3 && analysis.diffraction.length === 1 && analysis.fans.length === 6, 'The actual on-axis, three-wavelength analysis is incomplete');
    require([...$('[data-optics-history]').options].some(option => option.value === result.output_id), 'Completed optical analysis is absent from saved result history');
    require(JSON.stringify((await readProject()).ray_optics) === JSON.stringify(first.ray_optics), 'Analysis silently changed the saved optical prescription');
    result.measurements = {efl_mm: analysis.paraxial.effective_focal_length_mm, f_number: analysis.paraxial.f_number, spots: analysis.spots.length, diffraction_fields: analysis.diffraction.length};
    steps.push('actual_optiland_worker_complete_numerics_images_and_history');
    link.click(); steps.push('clicked_real_scientific_artifact_download');
    return {expect_download: true};
  }
  async function physical() {
    const dialog = '#physical-rendering-dialog', run = '[data-physical-run]';
    await open('physical-rendering', dialog, run);
    require($('[data-physical-object]').value === 'surface', 'The owned physical scene did not expose its surface');
    set('[data-physical-mode]', 'rgb'); set('[data-physical-spp]', 64);
    set('[data-physical-depth]', 4); set('[data-physical-seed]', 17);
    set('[data-physical-material-type]', 'diffuse');
    set('[data-physical-material-fields] textarea', '0.15, 0.35, 0.65');
    click('#physical-rendering-dialog details summary');
    set('[data-physical-world-mode]', 'physical');
    set('[data-physical-world] select', 'uniform');
    set('[data-physical-world] textarea', '1');
    click('[data-physical-save]');
    await until(() => $('[data-physical-status]')?.textContent.includes('settings saved') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'Physical material edit did not save');
    const first = await readProject();
    require(first.physical_rendering?.material_overrides.surface.reflectance.value.join(',') === '0.15,0.35,0.65' && first.physical_rendering.world_spectrum.value === 1, 'Saved material and illumination differ from controls');
    steps.push('authored_and_saved_actual_physical_material_and_light');
    await undoRedoReopen('physical_rendering', '[data-physical-close]');
    await open('physical-rendering', dialog, run);
    require($('[data-physical-mode]').value === 'rgb' && $('[data-physical-material-type]').value === 'diffuse' && $('[data-physical-material-fields] textarea').value === '0.15, 0.35, 0.65' && Number($('[data-physical-seed]').value) === 17, 'Reopened physical settings lost authored values');
    steps.push('reopened_material_controls_match_saved_settings');
    click(run);
    await until(() => !$(run)?.disabled && $('[data-physical-status]')?.textContent.includes('Processing completed') && !$('[data-physical-preview]')?.hidden && $('[data-physical-preview]')?.complete && $('[data-physical-preview]')?.naturalWidth === 32, 'Actual Mitsuba job/preview did not complete', 6500);
    const link = downloadLink('[data-physical-artifacts]', 'render.exr');
    const receipt = await get(new URL(link.href).pathname.replace(/render\.exr$/, 'provenance.json'));
    require(receipt.engine?.name === 'Mitsuba' && receipt.engine.variant === 'llvm_ad_rgb' && receipt.metrics.dtype === 'float32' && receipt.metrics.channels.join(',') === 'R,G,B', 'Actual render receipt is not CPU Mitsuba float32 RGB');
    require(receipt.settings.material_overrides.surface.reflectance.value.join(',') === '0.15,0.35,0.65' && receipt.settings.world_spectrum.value === 1, 'Worker ignored the authored physical settings');
    const current = await readProject();
    require(JSON.stringify(current.physical_rendering) === JSON.stringify(first.physical_rendering), 'Rendering silently changed the physical settings');
    const asset = current.assets.find(item => item.provenance?.type === 'cinematicum-physical-rendering' && item.provenance.output_id === result.output_id);
    require(asset && asset.provenance.display_encoding === 'sRGB', 'The actual display preview was not admitted with its transfer identity');
    result.asset_id = asset.id; result.measurements = {engine: receipt.engine, metrics: receipt.metrics};
    const img = $('[data-physical-preview]'), canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data, sums = [0, 0, 0];
    for (let i = 0; i < pixels.length; i += 4) for (let c = 0; c < 3; c++) sums[c] += pixels[i + c];
    result.preview_rgb_mean = sums.map(value => value / (canvas.width * canvas.height));
    steps.push('actual_mitsuba_worker_float_output_and_admitted_srgb_preview');
    link.click(); steps.push('clicked_real_scientific_artifact_download');
    return {expect_download: true};
  }
  try {
    await until(() => $('#project-select') && !$('#project-select').disabled && [...$('#project-select').options].some(item => item.value === SCIENTIFIC_FIXTURE.project_id), 'Owned project list did not bootstrap', 2600);
    await selectProject(SCIENTIFIC_FIXTURE.project_id, SCIENTIFIC_FIXTURE.project_name);
    steps.push('select_exact_owned_fixture_project');
    require(['optics-edit', 'optics-render', 'physical'].includes(SCIENTIFIC_FIXTURE.operation), 'Unknown scientific phase');
    const extras = SCIENTIFIC_FIXTURE.operation === 'optics-edit' ? await opticsEdit() : SCIENTIFIC_FIXTURE.operation === 'optics-render' ? await opticsRender() : await physical();
    return {...result, ...extras, passed: true, steps, elapsed_ms: Math.round(performance.now() - began)};
  } catch (error) {
    return {...result, passed: false, steps, error: String(error), elapsed_ms: Math.round(performance.now() - began)};
  }
})();

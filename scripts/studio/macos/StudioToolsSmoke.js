// Shipped Studio tools controls only; test fixture declaration is supplied by
// test_studio_tools_ui_macos.py. No application state or callback is injected.
const STUDIO_TOOLS_FIXTURE = /* ENGINE_TEST_CONFIG */ {};
return await (async () => {
  const began = performance.now(), deadline = began + 12500, steps = [];
  const result = {operation: STUDIO_TOOLS_FIXTURE.operation};
  const $ = selector => document.querySelector(selector);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const detail = () => `; project=${$('#project-select')?.value || ''}; status=${$('.learned-dialog[open] [data-status]')?.textContent || $('.deep-dialog [data-status]')?.textContent || ''}; job=${$('#job-label')?.textContent || ''}; toast=${$('#toast')?.textContent || ''}`;
  function require(value, message) { if (!value) throw Error(message + detail()); }
  function control(selector) {
    const node = $(selector);
    require(node && !node.disabled && !node.closest('[inert]'), `Unavailable control ${selector}`);
    node.scrollIntoView({block: 'nearest'});
    return node;
  }
  const click = selector => control(selector).click();
  function set(selector, value) {
    const node = control(selector); node.value = String(value);
    node.dispatchEvent(new Event('input', {bubbles: true}));
    node.dispatchEvent(new Event('change', {bubbles: true}));
  }
  async function until(fn, label, ms = 1700) {
    const end = Math.min(deadline, performance.now() + ms);
    while (performance.now() < end) { if (fn()) return; await sleep(20); }
    throw Error(label + detail());
  }
  async function fetchJSON(url) {
    const response = await fetch(url); require(response.ok, `GET failed: ${url}`);
    return await response.json();
  }
  function canonical(value) {
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
    return JSON.stringify(value);
  }
  function visibleFooter(dialogSelector, runSelector) {
    const dialog = control(dialogSelector), run = control(runSelector);
    const bounds = dialog.getBoundingClientRect(), rect = run.getBoundingClientRect();
    require(bounds.left >= 0 && bounds.right <= innerWidth + .5 && bounds.top >= 0 && bounds.bottom <= innerHeight + .5, 'Studio tool exceeds the native viewport');
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    require(hit === run || run.contains(hit), 'Render button is not hit-testable');
    result.render_visibility = {viewport: [innerWidth, innerHeight], button: [rect.x, rect.y, rect.width, rect.height]};
  }
  async function openDeep() {
    click('#authoring-tools');
    await until(() => $('#authoring-tools-dialog')?.open, 'Studio tools chooser did not open');
    click('[data-authoring-tool="deep-compositing"]');
    await until(() => $('.deep-dialog')?.open && !$('.deep-dialog [data-render]')?.disabled, 'Deep controls/runtime did not become ready', 2200);
  }
  async function save() {
    click('#save-project');
    await until(() => $('#save-state')?.textContent === 'SAVED LOCALLY', 'Project did not finish saving');
  }
  async function selectProject(id, label) {
    if ($('#project-select').value !== id) set('#project-select', id);
    await until(() => $('#project-select')?.value === id && !$('#project-select').disabled && $('#viewer-project')?.textContent === label, 'Exact owned project did not open', 2200);
  }
  async function deepPhase() {
    await openDeep();
    visibleFooter('.deep-dialog', '.deep-dialog [data-render]');
    const response = await fetch('/__engine_test__/deep-source');
    require(response.ok, 'Genuine multipart deep fixture was unavailable');
    const bytes = await response.arrayBuffer();
    require(bytes.byteLength > 512, 'Deep EXR fixture is unexpectedly small');
    const transfer = new DataTransfer();
    transfer.items.add(new File([bytes], STUDIO_TOOLS_FIXTURE.source_name, {type: 'image/x-exr'}));
    const input = control('.deep-dialog [data-file]');
    input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles: true}));
    await until(() => !$('.deep-dialog [data-add-source]')?.disabled && $('.deep-dialog [data-source]')?.options.length === 2,
      'Real deep EXR import did not return both views', 2400);
    const entries = [...$('.deep-dialog [data-source]').options];
    require(entries[0].textContent.includes('left') && entries[1].textContent.includes('right'), 'Source views were not preserved in controls');
    result.source_id = entries[0].value.split(':')[0];
    require(result.source_id === STUDIO_TOOLS_FIXTURE.source_sha256, 'Admitted source hash differs from actual fixture');
    set('.deep-dialog [data-source]', entries[0].value); click('.deep-dialog [data-add-source]');
    set('.deep-dialog [data-source]', entries[1].value); click('.deep-dialog [data-add-source]');
    set('.deep-dialog [data-operation]', 'channels'); click('.deep-dialog [data-add]');
    set('.deep-dialog [data-channel]', JSON.stringify({rename: {}, remove: [], scale: {R: {multiply: 2, add: 0}}, create: {'custom.scalar': {type: 'half', value: 1.5}}}));
    set('.deep-dialog [data-preview-output]', 1);
    click('.deep-dialog [data-update]');
    require($('.deep-dialog [data-outputs]').value === 'source1, channels1', 'Graph output branches are not explicit');
    steps.push('real_deep_file_input_two_views_and_editable_channel_graph');
    click('.deep-dialog [data-apply]');
    await until(() => $('.deep-dialog [data-status]')?.textContent.includes('Graph applied') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'Undoable graph application did not persist');
    click('.deep-dialog [data-close]');
    click('#undo-button'); await save();
    let project = await fetchJSON(`/api/projects/${STUDIO_TOOLS_FIXTURE.project_id}`);
    require(!project.deep_compositing, 'Undo did not remove the one graph edit');
    await openDeep();
    require($('.deep-dialog [data-nodes]').children.length === 0, 'Undone graph is still in the tool');
    click('.deep-dialog [data-close]');
    click('#redo-button'); await save();
    project = await fetchJSON(`/api/projects/${STUDIO_TOOLS_FIXTURE.project_id}`);
    require(project.deep_compositing?.nodes.length === 3, 'Redo did not restore the saved graph');
    await selectProject(STUDIO_TOOLS_FIXTURE.sentinel_id, STUDIO_TOOLS_FIXTURE.sentinel_name);
    await selectProject(STUDIO_TOOLS_FIXTURE.project_id, STUDIO_TOOLS_FIXTURE.project_name);
    await openDeep();
    const reopened = JSON.parse($('.deep-dialog [data-json]').value);
    require(reopened.nodes.find(n => n.id === 'channels1')?.scale.R.multiply === 2 && reopened.outputs.join(',') === 'source1,channels1', 'Saved channel graph did not survive project reopen');
    steps.push('graph_apply_save_undo_redo_and_exact_project_reopen');
    visibleFooter('.deep-dialog', '.deep-dialog [data-render]');
    click('.deep-dialog [data-render]');
    await until(() => !$('.deep-dialog [data-render]')?.disabled && !$('.deep-dialog [data-result]')?.hidden && $('.deep-dialog [data-image]')?.complete && $('.deep-dialog [data-image]')?.naturalWidth === 16,
      'Actual deep worker did not produce its displayed artifact', 4200);
    const links = [...$('.deep-dialog [data-links]').querySelectorAll('a')];
    require(links.length === 3, 'The three actual artifacts are not available');
    result.exr_url = new URL(links[0].href).pathname;
    result.receipt_url = new URL(links[1].href).pathname;
    result.preview_url = new URL(links[2].href).pathname;
    result.output_id = result.exr_url.split('/').at(-2);
    const receipt = await fetchJSON(result.receipt_url);
    require(receipt.output.parts.length === 2 && receipt.output.parts.every(p => p.deep) && receipt.output.parts.map(p => p.view).join(',') === 'left,right', 'Actual EXR receipt lost deep data or views');
    result.receipt_summary = {versions: receipt.versions, parts: receipt.output.parts, recipe: receipt.recipe, artifacts: receipt.artifacts};
    const payload = await fetch(result.exr_url); require(payload.ok, 'Actual EXR download route failed');
    const encoded = new Uint8Array(await payload.arrayBuffer());
    require(encoded[0] === 118 && encoded[1] === 47 && encoded[2] === 49 && encoded[3] === 1, 'Download is not an EXR');
    result.exr_bytes = encoded.byteLength;
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d'); ctx.drawImage($('.deep-dialog [data-image]'), 8, 8, 1, 1, 0, 0, 1, 1);
    result.preview_pixel = [...ctx.getImageData(0, 0, 1, 1).data];
    project = await fetchJSON(`/api/projects/${STUDIO_TOOLS_FIXTURE.project_id}`);
    const asset = project.assets.find(a => a.provenance?.type === 'cinematicum-deep-compositing' && a.provenance.output_id === result.output_id);
    require(asset && $(`.media-item[data-asset="${asset.id}"]`), 'Rendered preview was not admitted into actual project Media');
    result.asset_id = asset.id;
    steps.push('actual_deep_worker_preview_receipt_and_media_admission');
    links[0].click();
    steps.push('clicked_real_exr_wkdownload');
    return {expect_download: true};
  }
  function selectClip() {
    const node = control(`.timeline-clip[data-clip="${STUDIO_TOOLS_FIXTURE.clip_id}"]`);
    node.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
    require($(`.timeline-clip[data-clip="${STUDIO_TOOLS_FIXTURE.clip_id}"]`)?.classList.contains('selected'), 'The actual timeline clip was not selected');
  }
  function canvasPoint(x, y, pointerId) {
    const canvas = control('.learned-dialog [data-canvas]'), rect = canvas.getBoundingClientRect();
    canvas.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, buttons: 1, isPrimary: true, pointerId,
      clientX: rect.left + x * rect.width, clientY: rect.top + y * rect.height}));
    canvas.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, button: 0, buttons: 0, isPrimary: true, pointerId}));
  }
  async function readClip() {
    const project = await fetchJSON(`/api/projects/${STUDIO_TOOLS_FIXTURE.project_id}`);
    const clip = project.clips.find(value => value.id === STUDIO_TOOLS_FIXTURE.clip_id);
    require(clip, 'The owned learned fixture clip disappeared');
    return {project, clip};
  }
  function hasApplied(clip) {
    const bindings = clip.learned_bindings || [];
    return bindings.length === 1 && bindings[0].backend === STUDIO_TOOLS_FIXTURE.backend && !bindings[0].invalidated &&
      bindings[0].source.sha256 === STUDIO_TOOLS_FIXTURE.source_sha256 &&
      (STUDIO_TOOLS_FIXTURE.backend === 'sam2' ? clip.compositor?.nodes.some(node => node.type === 'alpha_mask') && bindings[0].target.hold_still === true :
        clip.tracking?.source?.learned_corrections?.length === 3);
  }
  async function showSavedApplication() {
    selectClip();
    if (STUDIO_TOOLS_FIXTURE.backend === 'sam2') {
      click('[data-mode="composite"]');
      await until(() => $('.compositor-node[data-node-type="alpha_mask"]') && $('.compositor-node[data-node-type="media_source"]'), 'The saved SAM alpha/matte nodes did not reopen in the actual compositor');
    } else {
      click('[data-mode="edit"]');
      await until(() => $('#inspector [data-action="track"]')?.textContent.includes('stabilized'), 'The saved TAPIR motion did not reopen in the actual clip inspector');
    }
  }
  async function learnedEditPhase() {
    const isMask = STUDIO_TOOLS_FIXTURE.backend === 'sam2';
    selectClip(); click('#authoring-tools');
    await until(() => $('#authoring-tools-dialog')?.open, 'Studio tools chooser did not open');
    click('#learned-tracking-button');
    await until(() => $('.learned-dialog')?.open && !$('.learned-dialog [data-run]')?.disabled &&
      $('.learned-dialog [data-status]')?.textContent === 'Source clip frame 0 is ready for prompts.', 'The actual checkpoint capability/source frame did not become ready', 4500);
    require($('.learned-dialog [data-canvas]').width === 256 && $('.learned-dialog [data-canvas]').height === 160, 'The displayed source is not the actual source frame dimensions');
    require($('.learned-dialog [data-runtime]').textContent.includes('Verified SAM2.1 Tiny and TAPIR'), 'The actual managed checkpoints are not ready');
    visibleFooter('.learned-dialog', '.learned-dialog [data-run]');
    if (!isMask) set('.learned-dialog [data-backend]', 'tapir');
    require($('.learned-dialog [data-backend]').value === STUDIO_TOOLS_FIXTURE.backend, 'The chosen actual model differs from this phase');
    set('.learned-dialog [data-count]', isMask ? 1 : 10);
    canvasPoint(45 / 256, 85 / 160, 181);
    if (!isMask) canvasPoint(52 / 256, 85 / 160, 182);
    let recipe = JSON.parse($('.learned-dialog [data-recipe]').value);
    if (isMask) {
      require(recipe.prompts.length === 1 && recipe.prompts[0].points.length === 1 && Math.abs(recipe.prompts[0].points[0].x - 45 / 256) < 1e-8, 'Canvas foreground prompt was not stored at its actual source coordinate');
      recipe.prompts[0].box = [20 / 256, 60 / 160, 70 / 256, 110 / 160];
      set('.learned-dialog [data-recipe]', JSON.stringify(recipe)); click('.learned-dialog [data-read-recipe]');
      require($('.learned-dialog [data-backend] option[value="tapir"]').disabled, 'The still image incorrectly offers a video-only TAPIR analysis');
    } else {
      require(recipe.points.length === 2 && recipe.points.map(point => point.id).join(',') === 'point_1,point_2', 'The two actual canvas point queries were not kept distinct');
    }
    steps.push('actual_source_frame_and_canvas_prompts');
    click('.learned-dialog [data-save]');
    await until(() => !$('.learned-dialog [data-save]')?.disabled && $('.learned-dialog [data-status]')?.textContent.includes('Prompt recipe saved') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'The edited prompt recipe did not save as an undoable edit');
    const savedPrompt = (await readClip()).clip;
    require(canonical(savedPrompt.learned_recipe) === canonical(JSON.parse($('.learned-dialog [data-recipe]').value)), 'The saved prompt recipe differs from the edited controls');
    steps.push('undoable_recipe_saved');
    click('.learned-dialog [data-run]');
    await until(() => !$('.learned-dialog [data-run]')?.disabled && !$('.learned-dialog [data-result]')?.hidden &&
      $('.learned-dialog [data-status]')?.textContent.includes('Actual learned inference completed'), 'The actual checkpoint inference did not complete', 8000);
    const links = [...$('.learned-dialog [data-downloads]').querySelectorAll('a')];
    const receiptLink = links.find(link => link.download === 'receipt.json'), resultLink = links.find(link => link.download === 'result.json');
    require(receiptLink && resultLink, 'The actual learned result/receipt is not available');
    result.receipt_url = new URL(receiptLink.href).pathname;
    result.result_url = new URL(resultLink.href).pathname;
    result.output_id = result.receipt_url.split('/').at(-2);
    const receipt = await fetchJSON(result.receipt_url), measured = await fetchJSON(result.result_url);
    require(receipt.output_id === result.output_id && receipt.source.sha256 === STUDIO_TOOLS_FIXTURE.source_sha256 && measured.measurement.backend === STUDIO_TOOLS_FIXTURE.backend,
      'Actual checkpoint output is not bound to the chosen source and backend');
    let state = await readClip();
    require(!state.clip.learned_bindings?.length && !state.clip.tracking && !state.clip.compositor, 'Inference silently altered the editable source clip');
    steps.push('actual_checkpoint_result_without_silent_application');
    if (isMask) {
      require(!$('.learned-dialog [data-hold-label]').hidden, 'The actual image result lacks explicit held-mask choice');
      const hold = control('.learned-dialog [data-hold-still]'); hold.checked = true;
      hold.dispatchEvent(new Event('change', {bubbles: true}));
      click('.learned-dialog [data-apply-mask]');
    } else {
      const tracks = measured.measurement.tracks;
      require(tracks.length === 2 && tracks[0].track.samples.filter(sample => !sample.visible).map(sample => sample.frame).join(',') === '4,5,6', 'Actual learned occlusion differs from the controlled source geometry');
      const before = canonical(state.clip);
      click('.learned-dialog [data-apply-point]');
      await until(() => !$('.learned-dialog [data-apply-point]')?.disabled && $('.learned-dialog [data-status]')?.textContent.includes('loses'), 'An uncorrected actual occlusion was silently applied');
      require(canonical((await readClip()).clip) === before, 'Rejected occlusion application changed the project');
      steps.push('learned_occlusion_requires_explicit_corrections');
      const correctionText = JSON.stringify(STUDIO_TOOLS_FIXTURE.corrections);
      set('.learned-dialog [data-corrections]', correctionText);
      set('.learned-dialog [data-point]', 'point_2');
      require($('.learned-dialog [data-corrections]').value === '[]', 'Manual point_1 corrections leaked into point_2');
      set('.learned-dialog [data-corrections]', JSON.stringify([{frame: 4, x: 108 / 256, y: 85 / 160}]));
      set('.learned-dialog [data-point]', 'point_1');
      require($('.learned-dialog [data-corrections]').value === correctionText, 'Point-specific corrections were lost when changing the selected query');
      steps.push('point_corrections_stay_bound_to_selected_query');
      click('.learned-dialog [data-apply-point]');
    }
    await until(() => !$('.learned-dialog [data-run]')?.disabled && $('.learned-dialog [data-status]')?.textContent.includes(isMask ? 'Actual SAM alpha cutout saved' : 'Measured stabilization and explicit point corrections saved') && $('#save-state')?.textContent === 'SAVED LOCALLY', 'The actual learned edit did not apply/save');
    state = await readClip(); require(hasApplied(state.clip), 'The saved learned application lacks its exact source-bound graph/motion');
    result.applied_binding = state.clip.learned_bindings[0];
    click('.learned-dialog [data-close]');
    await until(() => !$('.learned-dialog')?.open, 'Learned controls did not close');
    click('#undo-button'); await save();
    const undone = (await readClip()).clip;
    require(!undone.learned_bindings?.length && !undone.tracking && !undone.compositor && undone.learned_recipe?.backend === STUDIO_TOOLS_FIXTURE.backend, 'One Undo did not restore the prior saved clip while retaining its prompt recipe');
    click('#redo-button'); await save();
    require(hasApplied((await readClip()).clip), 'Redo did not restore the exact measured application');
    await selectProject(STUDIO_TOOLS_FIXTURE.sentinel_id, STUDIO_TOOLS_FIXTURE.sentinel_name);
    await selectProject(STUDIO_TOOLS_FIXTURE.project_id, STUDIO_TOOLS_FIXTURE.project_name);
    await showSavedApplication();
    require(hasApplied((await readClip()).clip), 'The applied learned graph/motion did not survive exact project reopen');
    steps.push('applied_edit_undo_redo_and_exact_reopen');
    return {};
  }
  async function learnedRenderPhase() {
    await showSavedApplication();
    const state = await readClip();
    require(hasApplied(state.clip), 'The actual saved learned application did not survive backend restart');
    require(state.project.settings.image_precision === 'high16' && state.project.settings.transparent_background, 'The saved project lost its requested full-precision transparent movie settings');
    steps.push('saved_binding_reopened_after_backend_restart');
    click('#export-button'); click('[data-export="master16"]');
    await until(() => ['16-bit master complete', 'Job failed', 'Job cancelled'].includes($('#job-label')?.textContent), 'Actual source-bound learned export did not finish', 9000);
    require($('#job-label').textContent === '16-bit master complete', 'The source-bound learned export failed');
    await until(() => !$('#download-job').hidden && $('#download-job').getAttribute('href')?.includes('.mkv?download=1'), 'The actual learned master download is not available');
    require($('#view-job').hidden && $('#rendered-preview').disabled, 'The FFV1 master was sent to the browser movie decoder');
    result.download_href = $('#download-job').getAttribute('href'); result.download_filename = $('#download-job').download;
    steps.push('native_export_dialog_completed_actual_ffv1_master');
    click('#download-job'); steps.push('clicked_real_native_master_download');
    return {expect_download: true};
  }
  try {
    await until(() => $('#project-select') && !$('#project-select').disabled && [...$('#project-select').options].some(o => o.value === STUDIO_TOOLS_FIXTURE.project_id), 'Studio fixture project list did not bootstrap', 3000);
    await selectProject(STUDIO_TOOLS_FIXTURE.project_id, STUDIO_TOOLS_FIXTURE.project_name);
    steps.push('select_exact_owned_fixture_project');
    const operation = STUDIO_TOOLS_FIXTURE.operation;
    require(operation === 'deep' || ['learned-sam-edit','learned-sam-render','learned-tapir-edit','learned-tapir-render'].includes(operation), 'This native acceptance phase is not yet implemented');
    const extras = operation === 'deep' ? await deepPhase() : operation.endsWith('-edit') ? await learnedEditPhase() : await learnedRenderPhase();
    return {...result, ...extras, passed: true, steps, elapsed_ms: Math.round(performance.now() - began)};
  } catch (error) {
    return {...result, passed: false, steps, error: String(error), elapsed_ms: Math.round(performance.now() - began)};
  }
})();

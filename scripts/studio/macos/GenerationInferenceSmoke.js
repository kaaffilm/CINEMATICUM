// Real, serial Wan inference through the shipped native editor controls.
// No mocked engine, imported substitute media, or mutated application state.
return await (async () => {
  const steps = [], takes = [], began = performance.now();
  const $ = selector => document.querySelector(selector);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const detail = () => '; toast=' + ($('#toast')?.textContent || '') + '; job=' + ($('#job-status')?.textContent || '');
  function require(value, message) { if (!value) throw Error(message + detail()); }
  function click(selector) {
    const node = $(selector);
    require(node && !node.disabled && !node.hidden, 'Unavailable control ' + selector);
    node.scrollIntoView({block: 'nearest'}); node.click();
  }
  async function until(predicate, message, seconds = 15) {
    const end = performance.now() + seconds * 1000;
    while (performance.now() < end) { if (predicate()) return; await sleep(100); }
    throw Error(message + detail());
  }
  function input(selector, value) {
    const node = $(selector); require(node && !node.disabled, 'Missing input ' + selector);
    node.value = String(value); node.dispatchEvent(new Event('input', {bubbles: true}));
    node.dispatchEvent(new Event('change', {bubbles: true}));
  }
  try {
    const parameters = new URL(location.href).searchParams;
    const repeats = Number(parameters.get('acceptance_repeats') || '2');
    const frames = Number(parameters.get('acceptance_frames') || '17');
    require(Number.isInteger(repeats) && repeats >= 1 && repeats <= 3, 'Invalid acceptance repetition count');
    require(frames === 17 || frames === 33, 'Invalid acceptance frame count');
    const perTakeDeadline = frames === 17 ? 1200 : 2400;
    await until(() => $('#viewer-project')?.textContent.includes('ENGINE TEST'), 'Generation project did not open');
    click('[data-mode="generate"]'); click('#manage-generation');
    await until(() => $('[data-generation-state]')?.textContent.includes('Installed'), 'Pinned runtime is not installed', 25);
    require(Number($('[data-generation-width]').value) === 480 && Number($('[data-generation-height]').value) === 272
      && Number($('[data-generation-length]').value) === 17 && Number($('[data-generation-steps]').value) === 20
      && Number($('[data-generation-fps]').value) === 16 && Number($('[data-generation-cfg]').value) === 6,
      'Normal generation defaults changed');
    if (frames === 33) {
      input('[data-generation-length]', frames);
      require(Number($('[data-generation-length]').value) === frames, 'Longer frame count was not entered');
      steps.push('requested_33_frames_through_native_length_input');
    }
    click('[data-generation-workflow]');
    await until(() => $('[data-generation-workflow-status]')?.textContent.includes('saved'), 'Requested workflow was not saved');
    click('[data-generation-start]');
    await until(() => $('[data-generation-state]')?.textContent === 'Engine ready', 'Actual engine did not become ready', 240);
    steps.push('verified_pinned_engine_started_from_native_controls');
    click('[data-generation-close]');
    for (let take = 0; take < repeats; take++) {
      click('[data-mode="generate"]');
      await until(() => $('#generate-button') && !$('#generate-button').disabled, 'Generate controls did not become ready');
      input('#generate-prompt', 'A cinematic tracking shot through an empty old cinema, warm practical lights, detailed red velvet seats, natural subtle camera motion, photorealistic.');
      input('#generate-negative', 'text, watermark, flicker, distorted geometry, oversaturated colors');
      input('#generate-seed', 42 + take);
      const previousIds = new Set([...document.querySelectorAll('.media-item[data-asset]')].map(node => node.dataset.asset));
      const previousJobId = state.job?.id;
      click('#generate-button');
      await until(() => state.job?.kind === 'generate' && state.job.id !== previousJobId && ['queued', 'running', 'completed'].includes(state.job.state), 'Actual generation job was not submitted');
      const jobId = state.job.id;
      await until(() => state.job?.id === jobId && ['completed', 'failed', 'cancelled', 'interrupted'].includes(state.job.state), 'Requested inference exceeded its acceptance deadline', perTakeDeadline);
      require(state.job.state === 'completed', 'Actual generation failed: ' + (state.job.error || state.job.state));
      await until(() => [...document.querySelectorAll('.media-item[data-asset]')].some(node => !previousIds.has(node.dataset.asset)), 'Completed take was not admitted to the media bin');
      const assetId = [...document.querySelectorAll('.media-item[data-asset]')].find(node => !previousIds.has(node.dataset.asset)).dataset.asset;
      takes.push({job_id: jobId, asset_id: assetId, seed: 42 + take, requested_frames: frames});
      steps.push('actual_' + (frames === 17 ? 'normal' : 'longer_bounded') + '_take_' + (take + 1) + '_completed_and_admitted');
    }
    click('#save-project');
    await until(() => $('#save-state').textContent === 'SAVED LOCALLY', 'Generation project was not saved');
    return {passed: true, steps, takes, requested_frames: frames, project_id: $('#project-select').value, elapsed_seconds: (performance.now() - began) / 1000};
  } catch (error) {
    return {passed: false, steps, takes, error: String(error), elapsed_seconds: (performance.now() - began) / 1000};
  }
})();

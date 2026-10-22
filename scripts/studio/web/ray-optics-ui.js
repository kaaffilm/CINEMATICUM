/* Sequential lens authoring backed by actual Optiland CPU jobs. Results are
   immutable; saving an edited or optimized prescription is an explicit undo. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const stable = value => JSON.stringify(value, function(key, item) {return item && !Array.isArray(item) && typeof item === 'object' ? Object.fromEntries(Object.keys(item).sort().map(k => [k, item[k]])) : item;});
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const number = (input, name, optional = false) => {
    if (optional && input.value.trim() === '') return null;
    if (input.value.trim() === '' || !Number.isFinite(Number(input.value))) throw Error(`${name} needs a finite number.`);
    return Number(input.value);
  };
  const materialText = material => material.type === 'air' ? 'air' : material.type === 'constant' ? `n:${material.index}` : `${material.catalog}:${material.name}`;
  function parseMaterial(text) {
    text = text.trim();
    if (text === 'air') return {type: 'air'};
    if (text.startsWith('n:')) {
      const value = Number(text.slice(2));
      if (!text.slice(2).trim() || !Number.isFinite(value)) throw Error('A constant material needs n: followed by a refractive index.');
      return {type: 'constant', index: value};
    }
    const split = text.indexOf(':');
    if (split <= 0 || split === text.length - 1) throw Error('Choose air, n:1.5, or an exact catalogue:glass such as schott:N-BK7.');
    return {type: 'catalog', catalog: text.slice(0, split), name: text.slice(split + 1)};
  }
  function mount(host, bridge) {
    const dialog = document.createElement('dialog');
    dialog.id = 'ray-optics-dialog'; dialog.className = 'cinematicum-optics';
    dialog.innerHTML = `<style>
      .cinematicum-optics{box-sizing:border-box;width:min(1230px,97vw);max-height:94vh;padding:0;overflow:hidden;background:#151b22;color:#e4eaf2;border:1px solid #526171;border-radius:12px;font:13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}.cinematicum-optics[open]{display:flex;flex-direction:column}.cinematicum-optics::backdrop{background:#05090cbb}.cinematicum-optics header,.cinematicum-optics footer{display:flex;align-items:center;gap:12px;padding:15px 20px;background:#202a35}.cinematicum-optics header>div,.cinematicum-optics footer>div{flex:1;min-width:0}.cinematicum-optics h2,.cinematicum-optics h3,.cinematicum-optics p{margin:0}.cinematicum-optics h2{font-size:18px}.cinematicum-optics h3{font-size:14px}.cinematicum-optics .optics-body{padding:20px;overflow:auto;display:grid;gap:20px}.cinematicum-optics .optics-line{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.cinematicum-optics label{display:grid;gap:5px;flex:1;min-width:120px}.cinematicum-optics input,.cinematicum-optics select{box-sizing:border-box;min-width:0;width:100%;background:#0c141c;color:#eff3f7;border:1px solid #43566a;border-radius:5px;padding:7px;font:inherit}.cinematicum-optics input[type=radio]{width:auto}.cinematicum-optics button,.cinematicum-optics a{font:inherit;padding:7px 11px;color:#e4eef7;background:#314456;border:1px solid #56728c;border-radius:5px;cursor:pointer;text-decoration:none}.cinematicum-optics button:disabled{opacity:.4;cursor:default}.cinematicum-optics [hidden]{display:none!important}.cinematicum-optics section{display:grid;gap:10px}.cinematicum-optics .optics-scroll{overflow:auto}.cinematicum-optics table{border-collapse:collapse;width:100%;text-align:left}.cinematicum-optics th,.cinematicum-optics td{padding:5px;border-bottom:1px solid #314354}.cinematicum-optics th{font-weight:500;color:#a7bccf}.cinematicum-optics td input{min-width:78px}.cinematicum-optics td .optics-material{min-width:175px}.cinematicum-optics td .optics-coeff{min-width:135px}.cinematicum-optics td button{padding:5px 7px;white-space:nowrap}.cinematicum-optics td.optics-buttons{display:flex;gap:4px}.cinematicum-optics .optics-note{font-size:12px;color:#a4b4c5}.cinematicum-optics .optics-columns{display:grid;grid-template-columns:1fr 1fr;gap:18px}.cinematicum-optics .optics-status{color:#b4dbe8;overflow-wrap:anywhere}.cinematicum-optics .optics-status.error{color:#ffb4a0}.cinematicum-optics progress{width:100%;accent-color:#5db8c8}.cinematicum-optics .optics-artifacts{display:flex;gap:8px;flex-wrap:wrap}.cinematicum-optics .optics-images{display:grid;grid-template-columns:1fr 1fr;gap:12px}.cinematicum-optics figure{margin:0;background:white;border-radius:6px;overflow:hidden}.cinematicum-optics figure img{display:block;width:100%;max-height:320px;object-fit:contain}.cinematicum-optics figcaption{padding:7px;color:#354456;background:#e7eff5}.cinematicum-optics pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101720;padding:12px;border-radius:5px;max-height:240px;overflow:auto}.cinematicum-optics .optics-primary{background:#236778;border-color:#63a9b8}
      @media(max-width:750px){.cinematicum-optics .optics-columns,.cinematicum-optics .optics-images{grid-template-columns:1fr}.cinematicum-optics footer{flex-wrap:wrap}}
    </style>
    <header><div><h2>Lens design</h2><p class="optics-note">Optical prescriptions, glass dispersion, real rays and diffraction</p></div><button type="button" data-optics-close>Close</button></header>
    <div class="optics-body">
      <section><div class="optics-line"><label>Lens name<input data-optics-name maxlength="100"></label><label>Entrance pupil · mm<input data-optics-aperture type="number" min="0.01" max="1000" step="any"></label><label>Object distance · mm<input data-optics-object type="number" min="0.01" step="any" placeholder="Infinity (blank)"></label></div><p class="optics-note">Distances and radii are in millimetres. Object and flat image planes are implicit. The image plane follows the last surface by its stated air gap; analysis does not refocus it.</p></section>
      <section><div class="optics-line"><h3>Refracting surfaces</h3><button type="button" data-optics-add-surface>Add surface</button><button type="button" data-optics-import>Import prescription JSON…</button><input type="file" data-optics-file accept=".json,application/json" hidden></div><div class="optics-scroll"><table><thead><tr><th>Surface</th><th>Radius · mm</th><th>Following gap · mm</th><th>Material after surface</th><th>Conic</th><th>Even-asphere coefficients</th><th>Stop</th><th>Order</th></tr></thead><tbody data-optics-surfaces></tbody></table></div><p class="optics-note">A blank radius is a plane. Coefficients are comma-separated r⁴ through r¹⁸ terms in the millimetre sag equation. Material is air, n:1.5 (constant index), or catalogue:name. The final surface must exit into air. One surface is the aperture stop.</p><div class="optics-line"><label>Find packaged glass<input data-optics-glass-query placeholder="N-BK7 or ohara" maxlength="100"></label><button type="button" data-optics-glass-search>Search glass catalogues</button><span class="optics-note" data-optics-glass-status></span></div><datalist id="optics-glasses"></datalist></section>
      <div class="optics-columns"><section><div class="optics-line"><h3>Field angles</h3><button type="button" data-optics-add-field>Add field</button></div><table><thead><tr><th>x · degrees</th><th>y · degrees</th><th>Weight</th><th></th></tr></thead><tbody data-optics-fields></tbody></table></section><section><div class="optics-line"><h3>Wavelengths</h3><button type="button" data-optics-add-wave>Add wavelength</button></div><table><thead><tr><th>Wavelength · µm</th><th>Weight</th><th>Primary</th><th></th></tr></thead><tbody data-optics-waves></tbody></table></section></div>
      <section><h3>Sampling</h3><div class="optics-line"><label>Pupil rings<input data-optics-rings type="number" min="2" max="12" step="1" value="4"></label><label>Fan samples<input data-optics-fans type="number" min="9" max="129" step="1" value="33"></label><label>FFT pupil samples<input data-optics-pupil type="number" min="16" max="128" step="1" value="32"></label><label>FFT grid<select data-optics-grid><option>64</option><option selected>128</option><option>256</option><option>512</option></select></label></div><p class="optics-note">Geometric analysis covers every field and wavelength. Scalar PSF/MTF uses the primary wavelength. Finite sampling is explicit; higher sampling can change a result and takes longer.</p></section>
      <section><div class="optics-line"><h3>Local optimization</h3><button type="button" data-optics-add-variable>Add variable</button></div><table><thead><tr><th>Surface</th><th>Parameter</th><th>Lower bound</th><th>Upper bound</th><th></th></tr></thead><tbody data-optics-variables></tbody></table><div class="optics-line"><label>Evaluation budget<input data-optics-evaluations type="number" min="5" max="200" value="60"></label><label>Target focal length · mm (optional)<input data-optics-efl type="number" min="0.1" step="any" placeholder="Unconstrained"></label><label>Focal-length merit weight<input data-optics-efl-weight type="number" min="0.001" max="100" step="any" value="1"></label></div><p class="optics-note">Minimizes weighted centroid RMS spot size with optional focal-length residual. Keep physical variable bounds. The result is a proposed prescription; Apply optimized prescription saves one undoable edit.</p></section>
      <section><h3>Saved analyses</h3><div class="optics-line"><label>Project result history<select data-optics-history></select></label><button type="button" data-optics-load-result>Open saved analysis</button></div><p class="optics-note">Results remain with the project after reopening or restoring a portable archive.</p></section>
      <section data-optics-results hidden><div class="optics-line"><h3>Measured results</h3><button type="button" data-optics-apply-result hidden>Apply optimized prescription</button></div><p data-optics-summary></p><p data-optics-result-status class="optics-note"></p><div class="optics-images" data-optics-images></div><pre data-optics-aberrations></pre><div class="optics-artifacts" data-optics-artifacts></div><p class="optics-note">Prescription JSON is editable interchange. Optiland state JSON preserves upstream infinity with explicit tagged values; restore tags before Optic.from_dict. PSF NPZ contains numerical energy-normalized arrays. These calculations do not certify manufacturing tolerances or a finished physical lens.</p></section>
    </div><footer><div><p class="optics-status" role="status" aria-live="polite" data-optics-status></p><progress data-optics-progress max="1" value="0" hidden></progress></div><button type="button" data-optics-cancel hidden>Cancel job</button><button type="button" data-optics-save>Save prescription</button><button type="button" data-optics-optimize>Optimize</button><button type="button" class="optics-primary" data-optics-analyze>Analyze</button></footer>`;
    host.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    let context = null, model = null, caps = null, result = null, resultInput = '', busy = false, jobId = null, serial = 0, disposed = false, variables = [], history = [];
    const active = ticket => !disposed && dialog.open && ticket === serial;
    const status = (text, error = false) => { const node = $('[data-optics-status]'); node.textContent = text; node.classList.toggle('error', error); };
    const path = action => `/api/projects/${encodeURIComponent(context.projectId)}/${action}`;
    function ensureContext() { if (bridge.getContext().projectId !== context.projectId) throw Error('The project changed. Reopen Lens design for the current project.'); }
    function controls() {
      for (const node of dialog.querySelectorAll('input,select,button')) if (!node.hasAttribute('data-optics-close') && !node.hasAttribute('data-optics-cancel')) node.disabled = busy;
      $('[data-optics-analyze]').disabled = busy || !caps?.available || !model;
      $('[data-optics-optimize]').disabled = busy || !caps?.available || !model;
      $('[data-optics-save]').disabled = busy || !model;
      $('[data-optics-glass-search]').disabled = busy || !caps?.available;
      $('[data-optics-cancel]').hidden = !jobId; $('[data-optics-progress]').hidden = !jobId;
      $('[data-optics-load-result]').disabled = busy || !history.length;
      $('[data-optics-apply-result]').disabled = busy || !result || !resultInput || (() => {try{return stable(readModel()) !== resultInput;}catch{return true;}})();
    }
    function inputCell(row, key, value, type = 'number', label = key) {
      const td = document.createElement('td'), input = document.createElement('input');
      input.type = type; input.dataset.key = key; input.value = value == null ? '' : value; input.setAttribute('aria-label', label);
      if (type === 'number') input.step = 'any';
      td.append(input); row.append(td); return input;
    }
    function buttonCell(row, text, callback) {
      const td = document.createElement('td'), button = document.createElement('button'); button.type = 'button'; button.textContent = text;
      button.onclick = () => {try {callback();} catch(error) {status(error.message, true);}}; td.append(button); row.append(td); return button;
    }
    function readModel() {
      const value = {version: 1, units: 'mm', name: $('[data-optics-name]').value, object_distance: number($('[data-optics-object]'), 'Object distance', true), aperture: {type: 'EPD', value: number($('[data-optics-aperture]'), 'Entrance pupil')}, surfaces: [], fields: [], wavelengths: []};
      for (const row of $('[data-optics-surfaces]').children) {
        const get = key => row.querySelector(`[data-key="${key}"]`);
        const coefficients = get('coefficients').value.trim();
        value.surfaces.push({id: row.dataset.id, radius: number(get('radius'), 'Radius', true), thickness: number(get('thickness'), 'Following gap'), conic: number(get('conic'), 'Conic'), material: parseMaterial(get('material').value), stop: get('stop').checked, coefficients: coefficients ? coefficients.split(',').map(v => { if (!v.trim() || !Number.isFinite(Number(v))) throw Error('Asphere coefficients must be finite comma-separated numbers.'); return Number(v); }) : []});
      }
      for (const row of $('[data-optics-fields]').children) value.fields.push(Object.fromEntries(['x', 'y', 'weight'].map(k => [k, number(row.querySelector(`[data-key="${k}"]`), `Field ${k}`)])));
      for (const row of $('[data-optics-waves]').children) value.wavelengths.push({value: number(row.querySelector('[data-key="value"]'), 'Wavelength'), weight: number(row.querySelector('[data-key="weight"]'), 'Wavelength weight'), primary: row.querySelector('[data-key="primary"]').checked});
      return value;
    }
    function readVariables() { return [...$('[data-optics-variables]').children].map(row => ({surface: row.querySelector('[data-var-surface]').value, parameter: row.querySelector('[data-var-parameter]').value, min: number(row.querySelector('[data-key="min"]'), 'Lower bound'), max: number(row.querySelector('[data-key="max"]'), 'Upper bound')})); }
    function renderVariables() {
      const body = $('[data-optics-variables]'); body.replaceChildren();
      for (const [index, variable] of variables.entries()) {
        const row = document.createElement('tr');
        for (const [key, items] of [['surface', model.surfaces.map(s => s.id)], ['parameter', ['thickness', 'radius', 'conic']]]) {
          const td = document.createElement('td'), select = document.createElement('select'); select.setAttribute(`data-var-${key}`, ''); select.setAttribute('aria-label', `Variable ${key}`);
          for (const value of items) {const option = document.createElement('option'); option.value = value; option.textContent = value; select.append(option);}
          select.value = variable[key]; td.append(select); row.append(td);
        }
        inputCell(row, 'min', variable.min); inputCell(row, 'max', variable.max);
        buttonCell(row, 'Remove', () => {variables = readVariables(); variables.splice(index, 1); renderVariables(); controls();}); body.append(row);
      }
    }
    function editStructure(change) {model = readModel(); variables = readVariables(); change(); variables = variables.filter(v => model.surfaces.some(s => s.id === v.surface)); renderEditor(); controls();}
    function renderEditor() {
      $('[data-optics-name]').value = model.name; $('[data-optics-object]').value = model.object_distance ?? ''; $('[data-optics-aperture]').value = model.aperture.value;
      const surfaces = $('[data-optics-surfaces]'); surfaces.replaceChildren();
      for (const [index, surface] of model.surfaces.entries()) {
        const row = document.createElement('tr'); row.dataset.id = surface.id;
        const label = document.createElement('td'); label.textContent = surface.id; row.append(label);
        inputCell(row, 'radius', surface.radius); inputCell(row, 'thickness', surface.thickness);
        const material = inputCell(row, 'material', materialText(surface.material), 'text', 'Material after surface'); material.setAttribute('list', 'optics-glasses'); material.className = 'optics-material';
        inputCell(row, 'conic', surface.conic); inputCell(row, 'coefficients', surface.coefficients.join(', '), 'text', 'Even-asphere coefficients').className = 'optics-coeff';
        const stop = inputCell(row, 'stop', '', 'radio', `Aperture stop at ${surface.id}`); stop.name = 'optics-stop'; stop.checked = surface.stop;
        const cell = document.createElement('td'); cell.className = 'optics-buttons';
        for (const [text, action] of [['↑', () => {if(index > 0) [model.surfaces[index - 1], model.surfaces[index]] = [model.surfaces[index], model.surfaces[index - 1]];}], ['↓', () => {if(index + 1 < model.surfaces.length) [model.surfaces[index + 1], model.surfaces[index]] = [model.surfaces[index], model.surfaces[index + 1]];}], ['Remove', () => {if(model.surfaces.length <= 2) throw Error('Keep at least two refracting surfaces.'); model.surfaces.splice(index, 1);}]] ) {
          const button = document.createElement('button'); button.type = 'button'; button.textContent = text; button.setAttribute('aria-label', `${text} surface ${surface.id}`); button.onclick = () => {try {editStructure(action);}catch(error){status(error.message, true);}}; cell.append(button);
        }
        row.append(cell); surfaces.append(row);
      }
      const fields = $('[data-optics-fields]'); fields.replaceChildren();
      for (const [index, field] of model.fields.entries()) {const row = document.createElement('tr'); for (const key of ['x', 'y', 'weight']) inputCell(row, key, field[key]); buttonCell(row, 'Remove', () => editStructure(() => {if(model.fields.length <= 1) throw Error('Keep at least one field.'); model.fields.splice(index, 1);})); fields.append(row);}
      const waves = $('[data-optics-waves]'); waves.replaceChildren();
      for (const [index, wave] of model.wavelengths.entries()) {const row = document.createElement('tr'); inputCell(row, 'value', wave.value); inputCell(row, 'weight', wave.weight); const primary = inputCell(row, 'primary', '', 'radio', 'Primary wavelength'); primary.name = 'optics-primary-wave'; primary.checked = wave.primary; buttonCell(row, 'Remove', () => editStructure(() => {if(model.wavelengths.length <= 1) throw Error('Keep at least one wavelength.'); model.wavelengths.splice(index, 1);})); waves.append(row);}
      renderVariables();
    }
    function readRecipe(operation) {
      const recipe = {version: 1, operation, prescription: readModel(), analysis: {rings: number($('[data-optics-rings]'), 'Pupil rings'), fan_samples: number($('[data-optics-fans]'), 'Fan samples'), pupil_samples: number($('[data-optics-pupil]'), 'FFT pupil samples'), fft_grid: Number($('[data-optics-grid]').value)}};
      if (operation === 'optimize') recipe.optimization = {variables: readVariables(), max_evaluations: number($('[data-optics-evaluations]'), 'Evaluation budget'), target_efl: number($('[data-optics-efl]'), 'Target focal length', true), efl_weight: number($('[data-optics-efl-weight]'), 'Focal-length merit weight')};
      return recipe;
    }
    function safeURL(value) {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin || !url.pathname.startsWith(path(`optics/outputs/${encodeURIComponent(result.output_id)}/`))) throw Error('The optical artifact is outside this project result.');
      return url.href;
    }
    function artifactURL(name) { const item = result.artifacts?.[name]; if (!item) throw Error(`Optical result is missing ${name}.`); return safeURL(result.artifact_urls?.[name] || item.url || path(`optics/outputs/${encodeURIComponent(result.output_id)}/${encodeURIComponent(name)}`)); }
    async function loadHistory(ticket) {
      const response = await bridge.request(path('studio-results')); if(!active(ticket)) return;
      history = (response.results || []).filter(item => item.tool === 'ray-optics');
      const select = $('[data-optics-history]'); select.replaceChildren();
      if(!history.length) {const option = document.createElement('option'); option.textContent = 'No saved optical analyses'; option.value = ''; select.append(option);}
      for(const item of history) {const option = document.createElement('option'); option.value = item.output_id; option.textContent = `${new Date(item.modified_at * 1000).toLocaleString()} · ${item.output_id.slice(0,8)}`; select.append(option);}
    }
    async function openSavedResult() {
      if(busy) return; const item = history.find(record => record.output_id === $('[data-optics-history]').value); if(!item) return;
      const ticket = serial; busy = true; controls();
      try {
        ensureContext(); result = {output_id: item.output_id, artifact_urls: item.artifact_urls};
        const base = path(`optics/outputs/${encodeURIComponent(item.output_id)}/`);
        const [receipt, analysis, prescription] = await Promise.all(['receipt.json','analysis.json','prescription.json'].map(name => bridge.request(safeURL(item.artifact_urls?.[name] || base + name))));
        if(!active(ticket)) return; ensureContext();
        result = {...result, receipt, analysis, prescription, artifacts: {...receipt.artifacts, 'receipt.json': {}}};
        resultInput = stable(receipt.recipe.prescription); showResult();
        status('Saved optical result reopened. Its numerical artifacts and original input recipe are preserved.');
      } catch(error) {if(active(ticket)) {result = null; status(error.message, true);}} finally {if(active(ticket)) {busy = false; controls();}}
    }
    function showResult() {
      $('[data-optics-results]').hidden = false;
      const a = result.analysis, opt = a.optimization;
      $('[data-optics-summary]').textContent = `EFL ${a.paraxial.effective_focal_length_mm.toPrecision(7)} mm · f/${a.paraxial.f_number.toPrecision(4)} · ${a.spots.length} field/wavelength spot measurements · primary ${a.diffraction[0].wavelength_um} µm`;
      $('[data-optics-result-status]').textContent = opt ? `Merit ${opt.before.toPrecision(6)} → ${opt.after.toPrecision(6)} · ${opt.function_evaluations} evaluations · ${opt.converged ? 'Converged' : 'Budget/termination limit; inspect proposal'} · ${opt.message}` : 'Completed at the authored image plane. Download the numerical arrays and provenance receipt for independent analysis.';
      $('[data-optics-aberrations]').textContent = JSON.stringify({third_order_seidel_sums: a.third_order_seidel_sums, spot_rms_mm: a.spots.map(s => ({field: s.field_index + 1, wavelength_um: s.wavelength_um, rms: s.rms_radius_mm})), primary_strehl: a.diffraction.map(d => ({field: d.field_index + 1, ratio: d.strehl_ratio}))}, null, 2);
      const images = $('[data-optics-images]'); images.replaceChildren();
      for (const [name, caption] of [['layout.svg', 'Actual sequential rays and lens surfaces'], ['spot.svg', 'Centroid geometric spots by wavelength'], ['psf.png', 'Scalar FFT point-spread function · logarithmic preview'], ['mtf.svg', 'Primary-wavelength sagittal and tangential MTF']]) { const figure = document.createElement('figure'), image = document.createElement('img'), label = document.createElement('figcaption'); image.src = artifactURL(name); image.alt = caption; label.textContent = caption; figure.append(image, label); images.append(figure); }
      const links = $('[data-optics-artifacts]'); links.replaceChildren();
      for (const [name, label] of [['prescription.json', 'Prescription JSON'], ['analysis.json', 'Numerical analysis'], ['rays.csv', 'Traced rays CSV'], ['mtf.csv', 'MTF CSV'], ['psf.npz', 'PSF arrays NPZ'], ['optiland.json', 'Optiland state JSON'], ['receipt.json', 'Provenance receipt']]) {const link = document.createElement('a'); link.textContent = label; link.href = artifactURL(name); link.download = name; links.append(link);}
      $('[data-optics-apply-result]').hidden = !opt;
    }
    async function apply(value, message) {
      if (busy) throw Error('Wait for the current optical request to finish.');
      const ticket = serial; ensureContext(); busy = true; controls();
      try {
        await bridge.applyPrescription(clone(value), clone(context)); if (!active(ticket)) return; ensureContext();
        context = clone(bridge.getContext()); model = clone(bridge.getProject().ray_optics || value); renderEditor();
        resultInput = ''; status(message); bridge.notify?.(message);
      } finally {if (active(ticket)) {busy = false; controls();}}
    }
    async function run(operation) {
      if (busy) return; const ticket = serial; let submitted = null;
      try {
        ensureContext(); const recipe = readRecipe(operation); resultInput = stable(recipe.prescription); result = null;
        busy = true; controls(); $('[data-optics-results]').hidden = true; status(operation === 'optimize' ? 'Optimizing the real optical prescription…' : 'Tracing rays and computing diffraction…');
        submitted = await bridge.request(path('ray-optics'), {method: 'POST', body: {recipe}});
        if (!active(ticket)) {await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method: 'POST', body: {}}); return;}
        jobId = submitted.id; controls(); let job = submitted;
        while (['queued', 'running'].includes(job.state)) {await pause(250); if (!active(ticket)) return; job = await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}`); if (!active(ticket)) return; $('[data-optics-progress]').value = job.progress || 0;}
        if (job.state !== 'completed') throw Error(job.error || 'Optical calculation did not complete.');
        ensureContext(); result = job.result;
        if (!result?.analysis?.diffraction?.length || !result.prescription || !result.output_id || !result.receipt) throw Error('Optiland did not return a complete bound optical result.');
        showResult(); await loadHistory(ticket); status(operation === 'optimize' ? 'Optimization proposal is ready. Inspect the measured results, then apply if wanted.' : 'Optical analysis completed. The authored prescription is unchanged.');
      } catch (error) {if (active(ticket)) status(error.message, true); if (submitted?.id) await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method: 'POST', body: {}}).catch(() => {});}
      finally {if (active(ticket)) {jobId = null; busy = false; controls();}}
    }
    async function searchGlass() {
      const ticket = serial, query = $('[data-optics-glass-query]').value; busy = true; controls();
      try {const data = await bridge.request('/api/ray-optics-catalog?q=' + encodeURIComponent(query)); if (!active(ticket)) return; ensureContext(); const list = $('#optics-glasses'); list.replaceChildren(); for (const material of data.materials || []) {const option = document.createElement('option'); option.value = `${material.catalog}:${material.name}`; list.append(option);} $('[data-optics-glass-status]').textContent = `${data.total_matches} matches${data.truncated ? ' · refine search for more' : ''}; choose in a material field.`;}
      catch(error) {if(active(ticket)) status(error.message, true);} finally {if(active(ticket)) {busy = false; controls();}}
    }
    function close() {if (busy) {status(jobId ? 'Cancel the optical job before closing.' : 'Wait for the current optical request to finish.'); return;} serial++; dialog.close();}
    $('[data-optics-close]').onclick = close; dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    $('[data-optics-analyze]').onclick = () => run('analyze'); $('[data-optics-optimize]').onclick = () => run('optimize');
    $('[data-optics-cancel]').onclick = async () => {if (!jobId) return; try {await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: 'POST', body: {}}); status('Cancellation requested…');} catch(error) {status(error.message, true);}};
    $('[data-optics-save]').onclick = async () => {try {await apply(readModel(), 'Optical prescription saved; Undo restores the previous prescription.');} catch(error) {status(error.message, true);}};
    $('[data-optics-apply-result]').onclick = async () => {try {if (!result || stable(readModel()) !== resultInput) throw Error('The editor changed since this result. Recalculate before applying the optimization.'); await apply(result.prescription, 'Optimized optical prescription applied as one undoable edit.');} catch(error) {status(error.message, true);}};
    $('[data-optics-load-result]').onclick = openSavedResult;
    $('[data-optics-glass-search]').onclick = searchGlass;
    $('[data-optics-add-surface]').onclick = () => {try {editStructure(() => {if(model.surfaces.length >= 32) throw Error('The sequential workflow admits at most 32 surfaces.'); let id = 1; while(model.surfaces.some(s => s.id === `s${id}`)) id++; model.surfaces.splice(model.surfaces.length - 1, 0, {id: `s${id}`, radius: null, thickness: 2, conic: 0, coefficients: [], material: {type: 'air'}, stop: false});});} catch(error) {status(error.message, true);}};
    $('[data-optics-add-field]').onclick = () => {try {editStructure(() => {if(model.fields.length >= 9) throw Error('Use at most nine fields.'); model.fields.push({x: 0, y: 1, weight: 1});});} catch(error) {status(error.message, true);}};
    $('[data-optics-add-wave]').onclick = () => {try {editStructure(() => {if(model.wavelengths.length >= 9) throw Error('Use at most nine wavelengths.'); model.wavelengths.push({value: .55, weight: 1, primary: false});});} catch(error) {status(error.message, true);}};
    $('[data-optics-add-variable]').onclick = () => {try {model = readModel(); variables = readVariables(); if(variables.length >= 8) throw Error('Use at most eight optimization variables.'); const s = model.surfaces.at(-1); variables.push({surface: s.id, parameter: 'thickness', min: Math.max(.001, s.thickness * .8), max: Math.max(.01, s.thickness * 1.2)}); renderVariables(); controls();} catch(error) {status(error.message, true);}};
    $('[data-optics-import]').onclick = () => $('[data-optics-file]').click();
    $('[data-optics-file]').onchange = async event => {const file = event.target.files?.[0]; event.target.value = ''; if(!file || busy) return; const ticket = serial; try {if(file.size > 128 * 1024) throw Error('Prescription JSON must be at most 128 KiB.'); const incoming = JSON.parse(await file.text()); if(!active(ticket)) return; ensureContext(); if(incoming.version !== 1 || !Array.isArray(incoming.surfaces) || !Array.isArray(incoming.fields) || !Array.isArray(incoming.wavelengths) || !incoming.aperture) throw Error('Choose a CINEMATICUM optical prescription JSON file.'); await apply(incoming, 'Imported optical prescription saved as one undoable edit.'); result = null; $('[data-optics-results]').hidden = true;} catch(error) {if(active(ticket)) status(error.message, true);}};
    dialog.addEventListener('input', () => {if(!busy) controls();});
    async function open() {
      if(disposed || dialog.open) return; const project = bridge.getProject(); if(!project) {bridge.notify?.('Open a project before designing a lens.', true); return;}
      context = clone(bridge.getContext()); context.projectId ||= project.id; model = project.ray_optics ? clone(project.ray_optics) : null;
      const ticket = ++serial; busy = true; caps = null; result = null; resultInput = ''; jobId = null; variables = []; history = []; $('[data-optics-results]').hidden = true; dialog.showModal(); controls(); status('Checking the installed Optiland runtime…');
      try {caps = await bridge.request('/api/ray-optics-capabilities'); if(!active(ticket)) return; ensureContext(); model ||= clone(caps.default_prescription); if(!model) throw Error('No optical authoring prescription is available.'); const last = model.surfaces.at(-1); variables = [{surface: last.id, parameter: 'thickness', min: Math.max(.001,last.thickness*.8), max: Math.max(.01,last.thickness*1.2)}]; renderEditor(); await loadHistory(ticket); if(!active(ticket)) return; status(caps.available ? 'Edit the prescription, save it, then analyze or optimize with real rays.' : caps.reason || 'Install the Optics runtime to trace this editable prescription.', !caps.available);}
      catch(error) {if(active(ticket)) {if(model) renderEditor(); status(error.message, true);}} finally {if(active(ticket)) {busy = false; controls();}}
    }
    return {open, close, destroy() {disposed = true; serial++; if(jobId) bridge.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: 'POST', body: {}}).catch(() => {}); dialog.remove();}};
  }
  window.CinematicumRayOptics = {mount};
})();

/* Editable physical settings, owned CPU jobs, explicit undoable application.
   A render never changes a material or imports a scene without its Apply action. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const artifacts = new Set(['render.exr', 'preview.png', 'spectral.exr', 'scene.pbrt', 'scene.json', 'optimized-settings.json', 'optimization.json', 'provenance.json']);
  const defaults = () => ({version: 1, mode: 'spectral', frame: 1, spp: 64, max_depth: 8, seed: 0, spectral_bands: [], material_overrides: {}, light_spectra: {}, world_spectrum: null, optimization: {object_id: null, iterations: 32, learning_rate: .05}});
  function number(input, name) {
    if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw Error(`${name} needs a finite number.`);
    return Number(input.value);
  }
  const linear = color => [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  function mount(host, bridge) {
    const dialog = document.createElement('dialog'); dialog.id = 'physical-rendering-dialog'; dialog.className = 'cinematicum-physical';
    dialog.innerHTML = `<style>
      .cinematicum-physical{box-sizing:border-box;width:min(1200px,97vw);max-height:94vh;padding:0;overflow:hidden;color:#e4edf4;background:#151c24;border:1px solid #546779;border-radius:12px;font:13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}.cinematicum-physical[open]{display:flex;flex-direction:column}.cinematicum-physical::backdrop{background:#040910bc}.cinematicum-physical header,.cinematicum-physical footer{display:flex;align-items:center;gap:12px;padding:16px 20px;background:#202c38}.cinematicum-physical header>div,.cinematicum-physical footer>div{flex:1;min-width:0}.cinematicum-physical h2,.cinematicum-physical h3,.cinematicum-physical p{margin:0}.cinematicum-physical h2{font-size:18px}.cinematicum-physical h3{font-size:14px}.cinematicum-physical .physical-body{padding:20px;overflow:auto;display:grid;grid-template-columns:minmax(320px,1fr) minmax(320px,1fr);gap:24px}.cinematicum-physical section{display:grid;align-content:start;gap:12px}.cinematicum-physical .physical-controls{display:grid;align-content:start;gap:22px}.cinematicum-physical .physical-row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.cinematicum-physical label{display:grid;gap:5px;flex:1;min-width:90px;color:#c3d0df}.cinematicum-physical input,.cinematicum-physical select,.cinematicum-physical textarea{box-sizing:border-box;width:100%;min-width:0;background:#0e151e;color:#edf4fa;border:1px solid #40566d;border-radius:5px;padding:8px;font:inherit}.cinematicum-physical textarea{resize:vertical;min-height:90px;line-height:1.5}.cinematicum-physical textarea.physical-code{font:12px/1.5 ui-monospace,monospace;min-height:180px}.cinematicum-physical input[type=checkbox]{width:auto}.cinematicum-physical button,.cinematicum-physical a{padding:8px 11px;background:#30485f;color:#e5f0fa;border:1px solid #547794;border-radius:5px;font:inherit;text-decoration:none;cursor:pointer}.cinematicum-physical button:disabled{opacity:.4;cursor:default}.cinematicum-physical [hidden]{display:none!important}.cinematicum-physical .physical-note{font-size:12px;color:#a6b9cc}.cinematicum-physical .physical-spectrum{padding:10px;border:1px solid #31495f;border-radius:5px;display:grid;gap:8px}.cinematicum-physical .physical-spectrum textarea{min-height:64px}.cinematicum-physical .physical-status{color:#b0ddeb;overflow-wrap:anywhere}.cinematicum-physical .physical-status.error{color:#ffb8a2}.cinematicum-physical progress{width:100%;accent-color:#63c4cf}.cinematicum-physical .physical-primary{background:#206e7e;border-color:#65bdc8}.cinematicum-physical .physical-picture{width:100%;max-height:400px;object-fit:contain;background:#0c131b;border-radius:6px}.cinematicum-physical .physical-links{display:flex;gap:8px;flex-wrap:wrap}.cinematicum-physical .physical-summary{white-space:pre-wrap;overflow-wrap:anywhere;background:#101923;padding:12px;border-radius:5px}.cinematicum-physical .physical-band{display:grid;grid-template-columns:1fr 85px 85px auto;gap:6px}.cinematicum-physical .physical-band input{padding:6px}.cinematicum-physical details{border-top:1px solid #324a60;padding-top:10px}.cinematicum-physical summary{cursor:pointer;color:#b8d3e9;margin-bottom:12px}
      @media(max-width:780px){.cinematicum-physical .physical-body{grid-template-columns:1fr}.cinematicum-physical footer{flex-wrap:wrap}.cinematicum-physical .physical-band{grid-template-columns:1fr 65px 65px auto}}
    </style>
    <header><div><h2>Physical rendering</h2><p class="physical-note">Spectral radiance, polarized light, material fitting and PBRT scenes</p></div><button type="button" data-physical-close>Close</button></header>
    <div class="physical-body"><div class="physical-controls">
      <section><label>Operation<select data-physical-operation><option value="render">Render with Mitsuba</option><option value="inverse">Fit a diffuse material to an image</option><option value="pbrt_export">Export PBRT-v4 scene</option><option value="pbrt_import">Import PBRT-v4 scene</option><option value="pbrt_render">Render with PBRT-v4</option></select></label>
        <div class="physical-row"><label>Light transport<select data-physical-mode><option value="spectral">Spectral</option><option value="polarized">Spectral + Stokes polarization</option><option value="rgb">Linear RGB</option></select></label><label>Scene frame<input type="number" data-physical-frame min="1" max="7200" step="1" value="1"></label></div>
        <div class="physical-row"><label>Samples per pixel<input type="number" data-physical-spp min="1" max="4096" step="1" value="64"></label><label>Path depth<input type="number" data-physical-depth min="2" max="64" step="1" value="8"></label><label>Seed<input type="number" data-physical-seed min="0" max="2147483647" step="1" value="0"></label></div>
        <p class="physical-note" data-physical-scene-info></p><p class="physical-note">One selected frame is rendered on the CPU. The float32 EXR preserves linear radiance, including values outside display range. The PNG preview clips to sRGB. Cycles denoising and per-lobe settings do not apply.</p>
      </section>
      <section data-physical-material-section><h3>Physical materials</h3><label>Scene object<select data-physical-object></select></label><label>Scattering model<select data-physical-material-type><option value="scene">Authored scene material</option><option value="diffuse">Diffuse reflectance</option><option value="coated_diffuse">Coated diffuse</option><option value="dielectric">Dielectric</option><option value="conductor">Conductor · eta and k</option><option value="polarizer">Linear polarizer</option><option value="retarder">Linear retarder</option></select></label><div data-physical-material-fields></div><p class="physical-note">Physical materials override the selected object's scattering model. Polarizer and retarder axes follow the surface UV coordinates; a plane provides a consistent axis. Typed roughness is microfacet alpha. Changes are saved only by Save settings or Apply fitted material.</p></section>
      <details><summary>Spectral lighting and sensor response</summary><section><label>World illumination<select data-physical-world-mode><option value="scene">Authored world color and strength</option><option value="physical">Explicit radiance spectrum</option></select></label><div data-physical-world></div><label>Scene light<select data-physical-light></select></label><label>Light spectrum<select data-physical-light-mode><option value="scene">Authored light color</option><option value="physical">Explicit spectrum</option></select></label><div data-physical-light-spectrum></div><p class="physical-note">Light power and size still come from the animated scene. Spectral values replace its color. World spectral values are radiance. RGB values are scene-linear; sampled wavelengths are in nanometres.</p><h3>Additional spectral bands</h3><div data-physical-bands></div><button type="button" data-physical-add-band>Add response band</button><p class="physical-note">Spectral mode records each rectangular response band as a separate EXR channel, integrated over its wavelength interval. Polarized mode instead records RGB S0, S1, S2 and S3 in the camera reference frame.</p></section></details>
      <section data-physical-inverse hidden><h3>Fit diffuse RGB reflectance</h3><label>Object to fit<select data-physical-fit-object></select></label><label>Reference image<select data-physical-target></select></label><div class="physical-row"><label>Iterations<input data-physical-iterations type="number" min="1" max="200" step="1" value="32"></label><label>Learning rate<input data-physical-rate type="number" min="0.00001" max="0.5" step="0.005" value="0.05"></label></div><p class="physical-note">Choose Linear RGB transport and an explicit diffuse RGB material. The opaque target must match the scene dimensions. PNG/JPEG targets are decoded as sRGB; EXR targets are assumed linear sRGB. Actual image gradients fit reflectance only. Geometry, lighting and the camera remain fixed during the fit.</p></section>
      <section data-physical-import hidden><h3>PBRT-v4 scene text</h3><input type="file" accept=".pbrt,text/plain" data-physical-file><textarea class="physical-code" data-physical-pbrt spellcheck="false" aria-label="PBRT-v4 scene"></textarea><p class="physical-note">The importer accepts a strict v4 subset: explicit perspective camera, independent sampler, box filter, volpath integrator, triangle meshes, typed materials and supported lights. Use Scale -1 1 1 before LookAt for the authored camera convention, film filename render.exr and savefp16 false. Unsupported commands, implicit renderer defaults, textures, media, Includes, animation and output paths cause an explicit error.</p></section>
    </div><div class="physical-controls"><section><h3>Result</h3><p class="physical-note" data-physical-runtime></p><img class="physical-picture" data-physical-preview hidden alt="Actual physical renderer output"><p data-physical-empty>No result for this operation yet.</p><div class="physical-summary" data-physical-summary hidden></div><div class="physical-links" data-physical-artifacts></div><button type="button" data-physical-apply-result hidden>Apply fitted material</button><p class="physical-note">Results and source identities remain in the project's saved results. Rendering and import analysis create immutable outputs; applying a proposed material or imported scene is one undoable, saved edit.</p></section><section><h3>Current scope</h3><p class="physical-note">This is a still renderer. It does not establish movie HDR management, production noise convergence, arbitrary renderer plugins, volumes or full PBRT interchange. Authored primitives are tessellated; validated mesh topology and evaluated modifier results are retained. A pass supports up to 16,777,216 pixel samples within a ten-minute job limit.</p></section></div></div>
    <footer><div><p class="physical-status" data-physical-status role="status" aria-live="polite"></p><progress data-physical-progress max="1" value="0" hidden></progress></div><button type="button" data-physical-cancel hidden>Cancel job</button><button type="button" data-physical-save>Save settings</button><button type="button" class="physical-primary" data-physical-run>Run</button></footer>`;
    host.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    let project = null, context = null, model = null, caps = null, busy = false, jobId = null, serial = 0, disposed = false;
    let selectedObject = '', selectedLight = '', materialReaders = {}, worldEditor = null, lightEditor = null, result = null, resultInput = '';
    const active = ticket => !disposed && dialog.open && ticket === serial;
    const operation = () => $('[data-physical-operation]').value;
    const status = (text, error = false) => {const node = $('[data-physical-status]'); node.textContent = text; node.classList.toggle('error', error);};
    function ensureContext() {
      const now = bridge.getContext();
      if (now.projectId !== context.projectId || now.revision !== context.revision) throw Error('The project changed. Reopen Physical rendering before applying or running this document.');
    }
    function path() {return `/api/projects/${encodeURIComponent(context.projectId)}/physical-rendering`;}
    function labelInput(container, title, value, options = {}) {
      const label = document.createElement('label'), input = document.createElement('input'); label.textContent = title;
      input.type = 'number'; input.step = 'any'; input.value = String(value); Object.assign(input, options); label.append(input); container.append(label); return input;
    }
    function spectrumEditor(container, value) {
      container.replaceChildren(); container.classList.add('physical-spectrum');
      const label = document.createElement('label'); label.textContent = 'Spectrum representation';
      const type = document.createElement('select');
      for (const [key, text] of [['rgb', 'Linear RGB'], ['uniform', 'Uniform spectrum'], ['sampled', 'Sampled wavelengths']]) type.add(new Option(text, key));
      type.value = value?.type || 'rgb'; label.append(type); container.append(label);
      const field = document.createElement('label'), text = document.createElement('textarea'); field.append(text); container.append(field);
      function fill(v) {
        const note = document.createElement('span'); note.textContent = type.value === 'sampled' ? 'One wavelength and value per line · 360–830 nm' : type.value === 'rgb' ? 'Red, green, blue · scene-linear' : 'Value across all wavelengths';
        field.replaceChildren(note, text);
        text.value = type.value === 'sampled' ? (v?.wavelengths || [360, 830]).map((w, i) => `${w} ${(v?.values || [1, 1])[i]}`).join('\n') : type.value === 'uniform' ? String(typeof v?.value === 'number' ? v.value : 1) : (Array.isArray(v?.value) ? v.value : [.5, .5, .5]).join(', ');
      }
      type.onchange = () => {fill(null); changed();}; fill(value);
      return {read() {
        if (type.value === 'sampled') {
          const rows = text.value.trim().split(/\n+/).map(row => row.trim().split(/[\s,]+/).map(Number));
          if (rows.some(row => row.length !== 2 || row.some(v => !Number.isFinite(v)))) throw Error('Every spectral row needs a wavelength and a finite value.');
          return {type: 'sampled', wavelengths: rows.map(row => row[0]), values: rows.map(row => row[1])};
        }
        const values = text.value.trim().split(/[\s,]+/).map(Number);
        if (!text.value.trim() || values.some(v => !Number.isFinite(v)) || values.length !== (type.value === 'rgb' ? 3 : 1)) throw Error('Enter the required finite spectral values.');
        return {type: type.value, value: type.value === 'rgb' ? values : values[0]};
      }};
    }
    function materialDefault(kind) {
      const obj = project.settings?.scene?.objects?.find(item => item.id === selectedObject);
      const rgb = linear(obj?.material?.color || '#bcbcbc');
      if (kind === 'diffuse') return {type: kind, reflectance: {type: 'rgb', value: rgb}};
      if (kind === 'coated_diffuse') return {type: kind, reflectance: {type: 'rgb', value: rgb}, ior: 1.5, roughness: .1};
      if (kind === 'dielectric') return {type: kind, ior: 1.5, roughness: 0};
      if (kind === 'conductor') return {type: kind, eta: {type: 'uniform', value: .2}, k: {type: 'uniform', value: 3}, roughness: .1};
      return {type: kind, angle: 0, transmittance: 1, ...(kind === 'retarder' ? {retardance: 90} : {})};
    }
    function showMaterial() {
      const value = model.material_overrides[selectedObject], fields = $('[data-physical-material-fields]'); fields.replaceChildren(); materialReaders = {};
      $('[data-physical-material-type]').value = value?.type || 'scene';
      if (!value) return;
      for (const key of ['reflectance', 'eta', 'k', 'emission']) if (value[key]) {
        const section = document.createElement('section'), heading = document.createElement('h3'); heading.textContent = key === 'k' ? 'Extinction k' : key[0].toUpperCase() + key.slice(1);
        const box = document.createElement('div'); section.append(heading, box); fields.append(section); materialReaders[key] = spectrumEditor(box, value[key]);
      }
      const row = document.createElement('div'); row.className = 'physical-row'; fields.append(row);
      for (const [key, title] of [['ior', 'Index of refraction'], ['roughness', 'Microfacet alpha'], ['angle', 'Axis angle · degrees'], ['retardance', 'Retardance · degrees'], ['transmittance', 'Transmittance']]) if (value[key] != null) {
        const input = labelInput(row, title, value[key]); materialReaders[key] = {read: () => number(input, title)};
      }
      const emission = document.createElement('button'); emission.type = 'button'; emission.textContent = value.emission ? 'Remove emission override' : 'Add spectral emission'; fields.append(emission);
      emission.onclick = () => {try {commitMaterial(); if (model.material_overrides[selectedObject].emission) delete model.material_overrides[selectedObject].emission; else model.material_overrides[selectedObject].emission = {type: 'uniform', value: 1}; showMaterial(); changed();} catch (error) {status(error.message, true);}};
    }
    function commitMaterial() {
      if (!selectedObject) return;
      const value = model.material_overrides[selectedObject]; if (!value) return;
      for (const [key, reader] of Object.entries(materialReaders)) value[key] = reader.read();
    }
    function commitLight() {
      if (!selectedLight) return;
      if ($('[data-physical-light-mode]').value === 'physical') model.light_spectra[selectedLight] = lightEditor.read();
      else delete model.light_spectra[selectedLight];
    }
    function showLight() {
      const value = model.light_spectra[selectedLight]; $('[data-physical-light-mode]').value = value ? 'physical' : 'scene';
      lightEditor = spectrumEditor($('[data-physical-light-spectrum]'), value || {type: 'rgb', value: [1, 1, 1]});
      $('[data-physical-light-spectrum]').hidden = !value || !selectedLight;
    }
    function showBands() {
      const container = $('[data-physical-bands]'); container.replaceChildren();
      for (const band of model.spectral_bands) {
        const row = document.createElement('div'); row.className = 'physical-band';
        const name = document.createElement('input'); name.value = band.name; name.setAttribute('aria-label', 'Band name'); row.append(name);
        const low = document.createElement('input'), high = document.createElement('input'); low.type = high.type = 'number'; low.value = band.min_nm; high.value = band.max_nm; low.setAttribute('aria-label', 'Band start nm'); high.setAttribute('aria-label', 'Band end nm'); row.append(low, high);
        const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove'; row.append(remove); container.append(row);
        row.read = () => ({name: name.value.trim(), min_nm: number(low, 'Band start'), max_nm: number(high, 'Band end')});
        remove.onclick = () => {row.remove(); changed();};
      }
    }
    function readModel() {
      commitMaterial(); commitLight(); const value = clone(model);
      for (const [key, selector, title] of [['frame', 'frame', 'Frame'], ['spp', 'spp', 'Samples'], ['max_depth', 'depth', 'Depth'], ['seed', 'seed', 'Seed']]) value[key] = number($(`[data-physical-${selector}]`), title);
      value.mode = $('[data-physical-mode]').value;
      value.spectral_bands = Array.from($('[data-physical-bands]').children, row => row.read());
      value.world_spectrum = $('[data-physical-world-mode]').value === 'physical' ? worldEditor.read() : null;
      value.optimization = {object_id: $('[data-physical-fit-object]').value || null, iterations: number($('[data-physical-iterations]'), 'Iterations'), learning_rate: number($('[data-physical-rate]'), 'Learning rate')};
      return value;
    }
    function readRecipe() {
      const recipe = {operation: operation(), settings: readModel()};
      if (recipe.operation === 'inverse') {recipe.target_asset_id = $('[data-physical-target]').value; if (!recipe.target_asset_id) throw Error('Choose an admitted reference image.');}
      if (recipe.operation === 'pbrt_import') {recipe.pbrt_text = $('[data-physical-pbrt]').value; if (!recipe.pbrt_text.trim()) throw Error('Choose or paste a PBRT-v4 scene.');}
      return recipe;
    }
    function controls() {
      for (const input of dialog.querySelectorAll('input,select,textarea,button')) if (!input.hasAttribute('data-physical-close') && !input.hasAttribute('data-physical-cancel')) input.disabled = busy;
      $('[data-physical-inverse]').hidden = operation() !== 'inverse'; $('[data-physical-import]').hidden = operation() !== 'pbrt_import';
      $('[data-physical-run]').disabled = busy || !caps?.operations?.includes(operation()) || (!project?.settings?.scene && operation() !== 'pbrt_import');
      $('[data-physical-save]').disabled = busy || !project?.settings?.scene;
      $('[data-physical-material-section]').hidden = !project?.settings?.scene?.objects?.length;
      $('[data-physical-progress]').hidden = !jobId; $('[data-physical-cancel]').hidden = !jobId;
      $('[data-physical-light]').disabled = busy || !project?.settings?.scene?.lights?.length;
      $('[data-physical-light-mode]').disabled = busy || !selectedLight;
      let unchanged = false; try {unchanged = !!resultInput && JSON.stringify(readRecipe()) === resultInput;} catch (_) { /* Invalid edits cannot apply an old result. */ }
      $('[data-physical-apply-result]').disabled = busy || !result || !unchanged;
    }
    function changed() {if (model && !busy) controls();}
    function fillOptions(select, entries, chosen) {
      select.replaceChildren(); for (const [id, text] of entries) select.add(new Option(text, id));
      if (entries.some(([id]) => id === chosen)) select.value = chosen;
    }
    function populate() {
      const scene = project.settings?.scene;
      for (const [key, selector] of [['frame', 'frame'], ['spp', 'spp'], ['max_depth', 'depth'], ['seed', 'seed']]) $(`[data-physical-${selector}]`).value = model[key];
      $('[data-physical-mode]').value = model.mode; $('[data-physical-iterations]').value = model.optimization.iterations; $('[data-physical-rate]').value = model.optimization.learning_rate;
      fillOptions($('[data-physical-object]'), (scene?.objects || []).map(obj => [obj.id, obj.name || obj.id]), selectedObject); selectedObject = $('[data-physical-object]').value; showMaterial();
      fillOptions($('[data-physical-fit-object]'), [['', 'Choose an object'], ...(scene?.objects || []).map(obj => [obj.id, obj.name || obj.id])], model.optimization.object_id || '');
      fillOptions($('[data-physical-target]'), [['', 'Choose an image'], ...(project.assets || []).filter(asset => asset.kind === 'image').map(asset => [asset.id, asset.name || asset.id])]);
      fillOptions($('[data-physical-light]'), (scene?.lights || []).map(light => [light.id, light.name || light.id]), selectedLight); selectedLight = $('[data-physical-light]').value; showLight();
      $('[data-physical-world-mode]').value = model.world_spectrum ? 'physical' : 'scene'; worldEditor = spectrumEditor($('[data-physical-world]'), model.world_spectrum || {type: 'uniform', value: 1}); $('[data-physical-world]').hidden = !model.world_spectrum;
      showBands(); $('[data-physical-scene-info]').textContent = scene ? `${scene.width} × ${scene.height} · ${scene.objects.length} objects · frames 1–${scene.frame_end}` : 'Create a 3D scene or import a PBRT scene to begin.';
    }
    function clearResult() {result = null; resultInput = ''; $('[data-physical-preview]').hidden = true; $('[data-physical-preview]').removeAttribute('src'); $('[data-physical-empty]').hidden = false; $('[data-physical-summary]').hidden = true; $('[data-physical-artifacts]').replaceChildren(); $('[data-physical-apply-result]').hidden = true;}
    function safeURL(value, filename) {
      const url = new URL(value, location.origin), prefix = `/api/projects/${encodeURIComponent(context.projectId)}/physical/outputs/${encodeURIComponent(result.output_id)}/`;
      if (!artifacts.has(filename) || url.origin !== location.origin || url.pathname !== prefix + encodeURIComponent(filename) || url.search || url.hash) throw Error('A physical result artifact belongs to an unexpected destination.');
      return url.href;
    }
    function showResult() {
      $('[data-physical-empty]').hidden = true; const container = $('[data-physical-artifacts]'); container.replaceChildren();
      for (const [name, value] of Object.entries(result.artifact_urls || {})) {
        const url = safeURL(value, name), link = document.createElement('a'); link.href = url; link.download = name; link.textContent = name; container.append(link);
        if (name === 'preview.png') {$('[data-physical-preview]').src = url; $('[data-physical-preview]').hidden = false;}
      }
      const metrics = result.receipt?.metrics || result.provenance?.metrics || {}, optimization = metrics.optimization;
      const lines = [];
      if (metrics.width) lines.push(`${metrics.width} × ${metrics.height} · ${metrics.dtype} · ${metrics.channels?.join(', ')}`);
      if (Number.isFinite(metrics.min)) lines.push(`Linear radiance ${Number(metrics.min).toPrecision(5)} to ${Number(metrics.max).toPrecision(5)}`);
      if (metrics.spectral) lines.push(`Spectral bands: ${metrics.spectral.channels.join(', ')}`);
      if (optimization) lines.push(`Mean squared image error: ${Number(optimization.initial_loss).toPrecision(6)} → ${Number(optimization.final_loss).toPrecision(6)}\n${optimization.iterations} actual gradient steps`);
      if (result.scene) lines.push(`Imported proposal: ${result.scene.objects.length} objects, ${result.scene.lights.length} lights. Apply imported scene to edit it.`);
      if (!lines.length) lines.push('The retained scene and receipt are ready to download.');
      $('[data-physical-summary]').textContent = lines.join('\n'); $('[data-physical-summary]').hidden = false;
      $('[data-physical-apply-result]').hidden = !(result.optimized_settings || result.scene); $('[data-physical-apply-result]').textContent = result.scene ? 'Apply imported scene' : 'Apply fitted material';
    }
    async function cancel() {
      if (!jobId) return; const id = jobId;
      try {await bridge.request(`/api/jobs/${encodeURIComponent(id)}/cancel`, {method: 'POST', body: {}}); if (id === jobId) status('Cancellation requested…');} catch (error) {if (id === jobId) status(error.message, true);}
    }
    async function run() {
      if (busy) return; const ticket = serial, savedContext = clone(context); let submitted = null;
      try {
        ensureContext(); const recipe = readRecipe(); clearResult(); resultInput = JSON.stringify(recipe); busy = true; controls(); status('Running the selected physical workflow…');
        submitted = await bridge.request(path(), {method: 'POST', body: {recipe}});
        if (!active(ticket)) {if (submitted?.id) await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method: 'POST', body: {}}); return;}
        jobId = submitted.id; controls(); let job = submitted;
        while (['queued', 'running'].includes(job.state)) {
          await pause(220); if (!active(ticket)) return;
          job = await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}`); if (!active(ticket)) return;
          $('[data-physical-progress]').value = job.progress || 0;
        }
        if (job.state !== 'completed') throw Error(job.error || 'Physical processing did not complete.');
        ensureContext(); result = job.result; if (!result?.output_id || !result.artifact_urls?.['provenance.json']) throw Error('The processor did not return verified owned artifacts.');
        await bridge.onComplete?.(result, savedContext); if (!active(ticket)) return; ensureContext(); project = clone(bridge.getProject()); showResult(); status('Processing completed. The result is preserved in this project.');
      } catch (error) {if (active(ticket)) status(error.message, true); if (submitted?.id) await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method: 'POST', body: {}}).catch(() => {});}
      finally {if (active(ticket)) {jobId = null; busy = false; controls();}}
    }
    async function save(useResult = false) {
      if (busy) return; const ticket = serial;
      try {
        ensureContext(); const current = useResult ? readRecipe() : {settings: readModel()};
        if (useResult && (!result || JSON.stringify(current) !== resultInput)) throw Error('The inputs changed. Run the workflow again before applying its proposal.');
        busy = true; controls(); status('Saving an undoable physical settings edit…');
        if (useResult && result.scene) await bridge.applyScene(clone(result.scene), clone(result.settings), clone(context));
        else await bridge.applySettings(clone(useResult ? result.optimized_settings : current.settings), clone(context));
        if (!active(ticket)) return;
        context = clone(bridge.getContext()); project = clone(bridge.getProject()); model = clone(project.physical_rendering || (useResult ? result.optimized_settings || result.settings : current.settings));
        clearResult(); populate(); status('Physical settings saved. Undo restores the preceding document.');
      } catch (error) {if (active(ticket)) status(error.message, true);}
      finally {if (active(ticket)) {busy = false; controls();}}
    }
    function close() {if (busy) {status(jobId ? 'Cancel the active job before closing.' : 'Wait for the current request to finish.'); return;} serial++; dialog.close();}
    $('[data-physical-close]').onclick = close; dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    $('[data-physical-run]').onclick = run; $('[data-physical-cancel]').onclick = cancel; $('[data-physical-save]').onclick = () => save(); $('[data-physical-apply-result]').onclick = () => save(true);
    $('[data-physical-operation]').onchange = () => {clearResult(); controls(); status(caps?.operations?.includes(operation()) ? 'Choose the workflow settings, then Run.' : caps?.reason || 'The selected optional engine is unavailable.');};
    $('[data-physical-object]').onchange = () => {try {commitMaterial(); selectedObject = $('[data-physical-object]').value; showMaterial(); changed();} catch (error) {$('[data-physical-object]').value = selectedObject; status(error.message, true);}};
    $('[data-physical-material-type]').onchange = () => {const type = $('[data-physical-material-type]').value; if (!selectedObject) return; if (type === 'scene') delete model.material_overrides[selectedObject]; else model.material_overrides[selectedObject] = materialDefault(type); showMaterial(); changed();};
    $('[data-physical-world-mode]').onchange = () => {$('[data-physical-world]').hidden = $('[data-physical-world-mode]').value !== 'physical'; changed();};
    $('[data-physical-light]').onchange = () => {try {commitLight(); selectedLight = $('[data-physical-light]').value; showLight(); changed();} catch (error) {$('[data-physical-light]').value = selectedLight; status(error.message, true);}};
    $('[data-physical-light-mode]').onchange = () => {$('[data-physical-light-spectrum]').hidden = $('[data-physical-light-mode]').value !== 'physical'; changed();};
    $('[data-physical-add-band]').onclick = () => {try {model.spectral_bands = Array.from($('[data-physical-bands]').children, row => row.read()); if (model.spectral_bands.length >= 16) throw Error('At most 16 bands are supported.'); model.spectral_bands.push({name: `band_${model.spectral_bands.length + 1}`, min_nm: 400, max_nm: 500}); showBands(); changed();} catch (error) {status(error.message, true);}};
    $('[data-physical-file]').onchange = async event => {const file = event.target.files?.[0]; event.target.value = ''; if (!file || busy) return; const ticket = serial; try {if (file.size > 8 * 1024 * 1024) throw Error('PBRT scenes are limited to 8 MiB.'); const text = await file.text(); if (active(ticket)) {$('[data-physical-pbrt]').value = text; changed();}} catch (error) {if (active(ticket)) status(error.message, true);}};
    dialog.addEventListener('input', changed);
    async function open(options = {}) {
      if (disposed || dialog.open) return; project = clone(bridge.getProject()); context = clone(bridge.getContext());
      if (!project || !context.projectId) {bridge.notify?.('Open a project before physical rendering.', true); return;}
      model = clone(project.physical_rendering || defaults()); model.light_spectra ||= {}; selectedObject = selectedLight = ''; caps = null; jobId = null; busy = true;
      const ticket = ++serial; $('[data-physical-operation]').value = ['render', 'inverse', 'pbrt_export', 'pbrt_import', 'pbrt_render'].includes(options.operation) ? options.operation : 'render';
      clearResult(); populate(); dialog.showModal(); controls(); status('Checking the installed physical rendering engines…');
      try {caps = await bridge.request('/api/physical-rendering-capabilities'); if (!active(ticket)) return; const versions = caps.versions; $('[data-physical-runtime]').textContent = versions ? `Mitsuba ${versions.mitsuba} · Dr.Jit ${versions.drjit} · CPU LLVM${caps.pbrt_available ? ' · PBRT executable available' : ' · PBRT rendering unavailable'}` : caps.reason || 'Optional renderer unavailable'; status(caps.available ? 'Choose the scene frame, physical settings and operation.' : caps.reason, !caps.available);}
      catch (error) {if (active(ticket)) status(error.message, true);}
      finally {if (active(ticket)) {busy = false; controls();}}
    }
    function destroy() {const id = jobId; serial++; disposed = true; if (id) bridge.request(`/api/jobs/${encodeURIComponent(id)}/cancel`, {method: 'POST', body: {}}).catch(() => {}); dialog.remove();}
    return {open, close, destroy};
  }
  window.CinematicumPhysicalRendering = {mount};
})();

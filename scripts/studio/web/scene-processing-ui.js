/* Editable data-only scene graphs and explicitly paired distributed rendering.
   Credentials stay in the Store's private manager. Invitations are displayed
   only after an explicit owner action and are never sent automatically. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const stable = value => JSON.stringify(value, (_, item) => item && !Array.isArray(item) && typeof item === 'object' ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const operations = ['source', 'group', 'merge', 'transform', 'material', 'attributes', 'set', 'prune', 'camera', 'context', 'time_warp', 'variant'];
  const inputs = node => node.op === 'merge' ? node.inputs || [] : node.op === 'variant' ? (node.choices || []).map(item => item.input) : node.input ? [node.input] : [];
  const descriptions = {
    source: 'Embed a validated standalone scene asset at an absolute hierarchy path.',
    group: 'Prefix every path and apply one inherited affine transform.',
    merge: 'Combine distinct paths. Global render/world settings must agree; the first input supplies the active camera.',
    transform: 'Edit each matched local transform in local or parent space. Descendants inherit parent edits.',
    material: 'Edit renderable object materials selected by paths or named sets.',
    attributes: 'Author inherited values. Boolean visibility affects rendering; other attributes remain queryable metadata.',
    set: 'Replace, union or subtract matched locations from a named set.',
    prune: 'Remove matched locations and their descendants, including set membership.',
    camera: 'Choose an existing camera path as the output camera.',
    context: 'Override typed variables only upstream of this node; sibling branches remain isolated.',
    time_warp: 'Evaluate the upstream frame as frame × scale + offset. Time is frame/fps.',
    variant: 'Choose a named input explicitly or by a deterministic SHA-256 seed/key rule.'
  };
  function mount(host, bridge) {
    const dialog = document.createElement('dialog'); dialog.id = 'scene-processing-dialog'; dialog.className = 'scene-processing';
    dialog.innerHTML = `<style>
      .scene-processing{box-sizing:border-box;width:min(1260px,97vw);max-height:95vh;padding:0;overflow:hidden;border:1px solid #516275;border-radius:12px;background:#151c24;color:#e5ecf4;font:13px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}.scene-processing[open]{display:flex;flex-direction:column}.scene-processing::backdrop{background:#04080dba}.scene-processing header,.scene-processing footer{display:flex;align-items:center;gap:12px;padding:14px 18px;background:#202b37}.scene-processing header>div,.scene-processing footer>div{flex:1;min-width:0}.scene-processing h2,.scene-processing h3,.scene-processing p{margin:0}.scene-processing h2{font-size:18px}.scene-processing h3{font-size:14px}.scene-processing .sp-body{overflow:auto;padding:18px;display:grid;gap:19px}.scene-processing section{display:grid;gap:10px}.scene-processing .sp-line{display:flex;gap:10px;align-items:end;flex-wrap:wrap}.scene-processing .sp-columns{display:grid;grid-template-columns:1fr 1fr;gap:16px}.scene-processing label{display:grid;gap:5px;flex:1;min-width:100px}.scene-processing input,.scene-processing select,.scene-processing textarea{box-sizing:border-box;width:100%;min-width:0;background:#0c141c;color:#eaf2fa;border:1px solid #43586d;border-radius:5px;padding:7px;font:inherit}.scene-processing textarea{font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;resize:vertical;min-height:140px}.scene-processing button,.scene-processing a{font:inherit;padding:7px 10px;color:#edf5ff;background:#30475c;border:1px solid #59728a;border-radius:5px;text-decoration:none;cursor:pointer}.scene-processing button:disabled{opacity:.45;cursor:default}.scene-processing input[type=checkbox],.scene-processing input[type=radio]{width:auto}.scene-processing [hidden]{display:none!important}.scene-processing table{width:100%;border-collapse:collapse;text-align:left}.scene-processing td,.scene-processing th{padding:5px 7px;border-bottom:1px solid #304151}.scene-processing th{font-weight:500;color:#a6bacd}.scene-processing .sp-table{overflow:auto;max-height:260px}.scene-processing .sp-selected{background:#254053}.scene-processing .sp-note{font-size:12px;color:#a3b9cd}.scene-processing .sp-status{color:#b6deeb;overflow-wrap:anywhere}.scene-processing .sp-status.error{color:#ffb9a5}.scene-processing .sp-primary{background:#236b7c;border-color:#67aabb}.scene-processing .sp-artifacts{display:flex;flex-wrap:wrap;gap:8px}.scene-processing progress{width:100%;accent-color:#6bc6d6}.scene-processing pre{margin:0;max-height:240px;overflow:auto;background:#101820;padding:10px;border-radius:5px;white-space:pre-wrap;overflow-wrap:anywhere}.scene-processing video{width:100%;max-height:300px;background:#05090f;border:1px solid #3f5468}.scene-processing details{border:1px solid #34495a;border-radius:6px;padding:10px}.scene-processing summary{cursor:pointer;color:#c1d8eb}.scene-processing details[open]>summary{margin-bottom:12px}.scene-processing .sp-workers label{display:flex;align-items:center;gap:8px;flex:none;min-width:0}.scene-processing .sp-invitation{min-height:100px}.scene-processing .sp-warning{color:#ffd292}
      @media(max-width:800px){.scene-processing .sp-columns{grid-template-columns:1fr}.scene-processing footer{flex-wrap:wrap}}
    </style>
    <header><div><h2>Scene processing</h2><p class="sp-note">Paths, sets, isolated contexts, asset variants and paired Cycles workers</p></div><button type="button" data-sp-close>Close</button></header>
    <div class="sp-body">
      <section><div class="sp-line"><label>Graph name<input data-sp-name maxlength="120"></label><label>Output node<select data-sp-output></select></label><button type="button" data-sp-import>Import graph JSON…</button><input type="file" data-sp-import-file accept=".json,application/json" hidden></div><p class="sp-note">128 nodes, 32 embedded assets, 512 evaluated locations and 32 hierarchy levels. The graph is versioned scene data. Rendering uses the actual installed Blender Cycles engine.</p></section>
      <section><div class="sp-line"><h3>Embedded scene assets</h3><label>Asset<select data-sp-asset></select></label><button type="button" data-sp-capture>Capture current 3D scene</button><button type="button" data-sp-new-asset>Add current scene as asset</button></div><details><summary>Edit embedded scene JSON</summary><textarea data-sp-asset-json rows="9" spellcheck="false" aria-label="Embedded scene JSON"></textarea><button type="button" data-sp-asset-update>Update asset draft</button></details><p class="sp-note">Assets retain geometry, materials, cameras, lights and sampled animation. Apply mesh modifiers before capture. Source asset bytes are embedded; workers do not follow paths or load project files.</p></section>
      <div class="sp-columns"><section><div class="sp-line"><h3>Scene nodes</h3><label>Add operation<select data-sp-operation></select></label><button type="button" data-sp-add>Add node</button></div><div class="sp-table"><table><thead><tr><th>Node</th><th>Operation</th><th>Inputs</th></tr></thead><tbody data-sp-nodes></tbody></table></div><div class="sp-line"><button type="button" data-sp-duplicate>Duplicate selected</button><button type="button" data-sp-delete>Delete selected</button></div></section><section><h3 data-sp-node-title>Node parameters</h3><p class="sp-note" data-sp-node-help></p><textarea data-sp-node-json rows="11" spellcheck="false" aria-label="Selected scene node JSON"></textarea><button type="button" data-sp-node-update>Update node draft</button><p class="sp-note">Filters use absolute path patterns (* one segment, ** descendants) and named set algebra: hero | background, hero & visible, all - hidden. Values may reference a declared variable with {"context":"name"} or typed arithmetic operations.</p></section></div>
      <section><h3>Evaluation context</h3><div class="sp-line" data-sp-context></div><details><summary>Edit typed context schema</summary><textarea data-sp-schema rows="6" spellcheck="false" aria-label="Typed context schema"></textarea><button type="button" data-sp-schema-update>Update context schema draft</button></details><p class="sp-note">Frame may be fractional. Source animation clamps outside its authored keys. Time is read-only frame/fps. Context nodes affect only their upstream branches. Evaluation and rendering preserve the graph until Save graph is selected.</p></section>
      <section><div class="sp-line"><h3>Saved graph outputs</h3><label>History<select data-sp-history></select></label><button type="button" data-sp-load>Open saved result</button></div></section>
      <section data-sp-results hidden><div class="sp-line"><h3>Evaluated scene</h3><button type="button" data-sp-apply-scene>Apply evaluated scene to 3D</button></div><p data-sp-summary></p><p class="sp-note sp-warning" data-sp-baked></p><div class="sp-columns"><div><video data-sp-preview controls preload="metadata" hidden></video><div class="sp-table"><table><thead><tr><th>Absolute path</th><th>Kind</th></tr></thead><tbody data-sp-paths></tbody></table></div></div><div><h3>Sets and selected location</h3><pre data-sp-sets></pre><pre data-sp-location></pre></div></div><div class="sp-artifacts" data-sp-artifacts></div></section>
      <details data-sp-distributed><summary>Distributed render workers and durable batches</summary><section><p class="sp-note">Pair workers explicitly over pinned TLS. Each task is one real evaluated frame. Batches preserve context order, then frame order. Private credentials stay outside the project and its archive. Listening starts only when Start / resume is selected.</p><div class="sp-line"><label>Worker name<input data-sp-worker-name value="local" maxlength="80"></label><label>Bind IPv4<input data-sp-host value="127.0.0.1"></label><label>Port (0 = choose)<input data-sp-port type="number" min="0" max="65535" value="0"></label><label>Advertised host (if needed)<input data-sp-advertise placeholder="Explicit peer address"></label><label>Parallel slots<select data-sp-slots><option>1</option><option>2</option></select></label><button type="button" data-sp-start>Start / resume local worker</button></div><div class="sp-line"><button type="button" data-sp-refresh-workers>Refresh workers</button><button type="button" data-sp-stop>Stop selected local worker</button><button type="button" data-sp-invite>Create one-use invitation</button></div><div class="sp-workers sp-line" data-sp-workers></div><pre class="sp-note" data-sp-worker-details></pre><div class="sp-columns"><label>One-use invitation (explicit copy only)<textarea class="sp-invitation" data-sp-invitation readonly spellcheck="false"></textarea></label><div><label>Invitation to pair<textarea class="sp-invitation" data-sp-pair-invitation spellcheck="false" placeholder="Paste the owner's one-use worker invitation JSON"></textarea></label><div class="sp-line"><label>Participant name<input data-sp-participant value="Editor" maxlength="80"></label><button type="button" data-sp-pair>Pair worker</button></div></div></div><details><summary>Revoke an issued worker credential</summary><div class="sp-line"><label>Client identity<input data-sp-revoke-id maxlength="32" placeholder="Exact paired client ID"></label><button type="button" data-sp-revoke>Revoke client</button></div></details><div class="sp-line"><label>Frames · comma-separated<input data-sp-frames value="1, 2, 3" placeholder="1, 2, 3"></label><label>Context variations · JSON array<textarea data-sp-variations rows="3" spellcheck="false">[{}]</textarea></label><button type="button" data-sp-dispatch>Dispatch real frames</button></div><p class="sp-note">At most 64 tasks per batch across 1–8 paired workers. Context variations exclude frame; unspecified values come from the graph defaults. A cancelled or interrupted batch needs explicit Retry. Resume reconnects to already accepted task identities.</p><div class="sp-line"><label>Owned batches<select data-sp-batches></select></label><button type="button" data-sp-batch-refresh>Refresh batches</button><button type="button" data-sp-batch-resume>Resume collection</button><button type="button" data-sp-batch-retry>Retry interrupted tasks</button><button type="button" data-sp-batch-cancel>Cancel batch</button></div><pre data-sp-batch-detail></pre></section></details>
    </div><footer><div><p class="sp-status" role="status" aria-live="polite" data-sp-status></p><progress data-sp-progress value="0" max="1" hidden></progress></div><button type="button" data-sp-cancel hidden>Cancel job</button><button type="button" data-sp-save>Save graph</button><button type="button" data-sp-evaluate>Evaluate graph</button><button type="button" class="sp-primary" data-sp-render>Render current context</button></footer>`;
    host.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    let model = null, selected = null, asset = null, context = null, overrides = {}, capabilities = null;
    let busy = false, jobId = null, batchId = null, serial = 0, disposed = false, result = null, resultInput = '', history = [], workers = [], batches = [];
    const alive = ticket => !disposed && dialog.open && ticket === serial;
    const message = (text, error = false) => {const node = $('[data-sp-status]'); node.textContent = text; node.classList.toggle('error', error);};
    const path = action => `/api/projects/${encodeURIComponent(context.projectId)}/${action}`;
    function ensureProject() {if (bridge.getContext().projectId !== context.projectId) throw Error('The active project changed. Reopen Scene processing for that project.');}
    function controlState() {
      for (const node of dialog.querySelectorAll('input,select,textarea,button')) if (!node.hasAttribute('data-sp-close') && !node.hasAttribute('data-sp-cancel')) node.disabled = busy;
      $('[data-sp-save]').disabled = busy || !model; $('[data-sp-evaluate]').disabled = busy || !model;
      $('[data-sp-render]').disabled = busy || !model || !capabilities?.available;
      $('[data-sp-load]').disabled = busy || !history.length;
      $('[data-sp-apply-scene]').disabled = busy || !result?.scene || !resultInput;
      $('[data-sp-cancel]').hidden = !jobId; $('[data-sp-progress]').hidden = !jobId;
      $('[data-sp-dispatch]').disabled = busy || !model || !workers.length;
      for (const name of ['resume', 'retry', 'cancel']) $(`[data-sp-batch-${name}]`).disabled = busy || !batches.length;
    }
    function option(select, value, text, chosen = false) {const node = document.createElement('option'); node.value = value; node.textContent = text; node.selected = chosen; select.append(node);}
    function readNode() {
      if (!selected) return;
      const index = model.nodes.findIndex(node => node.id === selected); if (index < 0) return;
      const value = JSON.parse($('[data-sp-node-json]').value);
      if (!value || typeof value !== 'object' || Array.isArray(value) || !/^[A-Za-z_][A-Za-z0-9_-]{0,79}$/.test(value.id) || !operations.includes(value.op)) throw Error('A node needs a portable ID and supported operation.');
      if (model.nodes.some((node, i) => i !== index && node.id === value.id)) throw Error('Node IDs must be distinct.');
      if (value.id !== selected) {
        for (const node of model.nodes) {
          if (node.input === selected) node.input = value.id;
          if (node.inputs) node.inputs = node.inputs.map(input => input === selected ? value.id : input);
          if (node.choices) node.choices = node.choices.map(choice => ({...choice, input: choice.input === selected ? value.id : choice.input}));
        }
        if (model.output === selected) model.output = value.id;
      }
      model.nodes[index] = value; selected = value.id;
    }
    function readContext() {
      const values = {};
      for (const input of $('[data-sp-context]').querySelectorAll('[data-context]')) {
        const key = input.dataset.context; if (!model.context[key]) continue; const type = model.context[key].type;
        if (type === 'bool') values[key] = input.checked;
        else if (type === 'string') values[key] = input.value;
        else if (type === 'vector3') {values[key] = JSON.parse(input.value); if (!Array.isArray(values[key]) || values[key].length !== 3 || values[key].some(value => !Number.isFinite(value))) throw Error(`${key} requires a JSON vector of three numbers.`);}
        else {values[key] = Number(input.value); if (!input.value.trim() || !Number.isFinite(values[key]) || type === 'int' && !Number.isInteger(values[key])) throw Error(`${key} requires a finite ${type}.`);}
      }
      overrides = values; return clone(values);
    }
    function readGraph() {
      model.output = $('[data-sp-output]').value || model.output; readNode(); model.name = $('[data-sp-name]').value;
      if (asset) {const selectedAsset = model.assets.find(item => item.id === asset); if (selectedAsset) selectedAsset.scene = JSON.parse($('[data-sp-asset-json]').value);}
      const schema = JSON.parse($('[data-sp-schema]').value);
      if (!schema || typeof schema !== 'object' || Array.isArray(schema)) throw Error('Context schema must be an object.');
      model.context = schema;
      return clone(model);
    }
    function renderContext() {
      const holder = $('[data-sp-context]'); holder.replaceChildren();
      for (const [key, spec] of Object.entries(model.context || {})) {
        const label = document.createElement('label'), text = document.createElement('span'), input = document.createElement('input');
        text.textContent = `${key} · ${spec.type}`; input.dataset.context = key;
        const value = overrides[key] ?? spec.default;
        input.type = spec.type === 'bool' ? 'checkbox' : ['int', 'float'].includes(spec.type) ? 'number' : 'text';
        if (spec.type === 'bool') input.checked = Boolean(value);
        else {input.value = spec.type === 'vector3' ? JSON.stringify(value) : value; if (input.type === 'number') {input.step = spec.type === 'int' ? '1' : 'any'; if (spec.min != null) input.min = spec.min; if (spec.max != null) input.max = spec.max;}}
        label.append(text, input); holder.append(label);
      }
    }
    function renderNode() {
      const node = model.nodes.find(item => item.id === selected) || model.nodes[0]; selected = node?.id || null;
      $('[data-sp-node-title]').textContent = node ? `Parameters · ${node.id}` : 'Node parameters';
      $('[data-sp-node-help]').textContent = descriptions[node?.op] || '';
      $('[data-sp-node-json]').value = node ? JSON.stringify(node, null, 2) : '';
    }
    function renderAsset() {
      const item = model.assets.find(value => value.id === asset) || model.assets[0]; asset = item?.id || null;
      $('[data-sp-asset]').replaceChildren(); for (const item of model.assets) option($('[data-sp-asset]'), item.id, item.id, item.id === asset);
      $('[data-sp-asset-json]').value = item ? JSON.stringify(item.scene, null, 2) : '';
    }
    function renderGraph() {
      $('[data-sp-name]').value = model.name; $('[data-sp-schema]').value = JSON.stringify(model.context, null, 2);
      const rows = $('[data-sp-nodes]'); rows.replaceChildren(); const output = $('[data-sp-output]'); output.replaceChildren();
      for (const node of model.nodes) {
        option(output, node.id, `${node.id} · ${node.op}`, node.id === model.output);
        const row = document.createElement('tr'); row.classList.toggle('sp-selected', node.id === selected); row.tabIndex = 0;
        for (const text of [node.id, node.op, inputs(node).join(', ')]) {const td = document.createElement('td'); td.textContent = text; row.append(td);}
        const select = () => {if (busy) return; try {const same = selected === node.id; readGraph(); overrides = readContext(); if (!same) selected = node.id; renderGraph();} catch (error) {message(error.message, true);}};
        row.onclick = select; row.onkeydown = event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); select();}};
        rows.append(row);
      }
      renderNode(); renderAsset(); renderContext(); controlState();
    }
    function nextID(prefix, values) {let number = 1; while (values.includes(prefix + number)) number++; return prefix + number;}
    function addNode() {
      readGraph(); readContext(); if (model.nodes.length >= 128) throw Error('This graph supports at most 128 nodes.');
      const id = nextID('node', model.nodes.map(node => node.id)), op = $('[data-sp-operation]').value, upstream = model.output;
      const node = {id, op, input: upstream};
      if (op === 'source') {delete node.input; node.asset = model.assets[0].id; node.root = '/' + id;}
      else if (op === 'merge') {delete node.input; const other = model.nodes.find(item => item.id !== upstream); if (!other) throw Error('Add another source or branch before a merge.'); node.inputs = [upstream, other.id];}
      else if (op === 'group') {node.prefix = '/' + id; node.transform = {position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1]};}
      else if (['transform', 'material', 'attributes', 'set', 'prune'].includes(op)) {
        node.filter = op === 'prune' ? {paths: ['/unmatched']} : {sets: '__objects'};
        if (op === 'transform') {node.space = 'local'; node.transform = {position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1]};}
        if (op === 'material') node.values = {color: '#c0c0c0'};
        if (op === 'attributes') node.values = {visibility: true};
        if (op === 'set') {node.name = nextID('set', model.nodes.filter(value => value.op === 'set').map(value => value.name)); node.mode = 'replace';}
      } else if (op === 'camera') node.path = '/world/camera';
      else if (op === 'context') node.values = {frame: {context: 'frame'}};
      else if (op === 'time_warp') {node.scale = 1; node.offset = 0;}
      else if (op === 'variant') {delete node.input; node.mode = 'select'; node.selector = 'default'; node.choices = [{name: 'default', input: upstream}];}
      model.nodes.push(node); model.output = id; selected = id; renderGraph(); message('Node added to the draft. Edit its parameters, then evaluate or save.');
    }
    function safeArtifact(url) {
      const parsed = new URL(url, location.href);
      const base = path(`scene-processing/outputs/${encodeURIComponent(result.output_id)}/`);
      if (parsed.origin !== location.origin || !parsed.pathname.startsWith(base) || parsed.search || parsed.hash) throw Error('The artifact is outside this project output.');
      return parsed.href;
    }
    function showResult() {
      $('[data-sp-results]').hidden = false;
      const evaluation = result.evaluation;
      $('[data-sp-summary]').textContent = evaluation ? `${evaluation.locations.length} locations · ${Object.keys(evaluation.sets).length} sets · context frame ${evaluation.context.frame} at ${evaluation.context.fps} fps · camera ${evaluation.active_camera}` : `${result.receipt.task_count} actual frame tasks across ${result.receipt.worker_count} workers · output order is retained in dispatch.json`;
      $('[data-sp-baked]').textContent = result.receipt.baked_transforms?.length ? `${result.receipt.baked_transforms.length} affine transforms required baked mesh geometry. See the receipt for exact meshes and any bounded primitive tessellation.` : '';
      const paths = $('[data-sp-paths]'); paths.replaceChildren();
      for (const item of evaluation?.locations || []) {
        const row = document.createElement('tr'), pathCell = document.createElement('td'), kindCell = document.createElement('td');
        pathCell.textContent = item.path; kindCell.textContent = item.kind; row.append(pathCell, kindCell); row.tabIndex = 0;
        const inspect = () => {$('[data-sp-location]').textContent = JSON.stringify({path: item.path, parent: item.parent, transform: item.transform, world_transform: item.world_transform, inherited_attributes: item.inherited_attributes}, null, 2);};
        row.onclick = inspect; row.onkeydown = event => {if (event.key === 'Enter') inspect();}; paths.append(row);
      }
      $('[data-sp-sets]').textContent = JSON.stringify(evaluation?.sets || {}, null, 2); $('[data-sp-location]').textContent = '';
      const preview = $('[data-sp-preview]'); preview.pause(); preview.removeAttribute('src'); preview.hidden = !result.artifact_urls?.['preview.mp4'];
      if (!preview.hidden) preview.src = safeArtifact(result.artifact_urls['preview.mp4']);
      const links = $('[data-sp-artifacts]'); links.replaceChildren();
      for (const [name, url] of Object.entries(result.artifact_urls || {})) {const link = document.createElement('a'); link.textContent = name; link.href = safeArtifact(url); link.download = name; links.append(link);}
      controlState();
    }
    async function refreshHistory(ticket) {
      const value = await bridge.request(path('studio-results')); if (!alive(ticket)) return;
      history = (value.results || []).filter(item => item.tool === 'scene-processing');
      const select = $('[data-sp-history]'); select.replaceChildren();
      if (!history.length) option(select, '', 'No saved scene outputs');
      for (const item of history) option(select, item.output_id, `${new Date(item.modified_at * 1000).toLocaleString()} · ${item.output_id.slice(0, 8)}`);
    }
    async function refreshWorkers(ticket) {
      const response = await bridge.request('/api/scene-workers'); if (!alive(ticket)) return;
      const chosen = new Set([...$('[data-sp-workers]').querySelectorAll('input:checked')].map(input => input.value));
      workers = response.workers || []; const container = $('[data-sp-workers]'); container.replaceChildren();
      for (const worker of workers) {const label = document.createElement('label'), box = document.createElement('input'), text = document.createElement('span'); box.type = 'checkbox'; box.value = worker.name; box.checked = chosen.size ? chosen.has(worker.name) : true; text.textContent = worker.name + (worker.running === false ? ' · stopped' : ''); label.append(box, text); container.append(label);}
      $('[data-sp-worker-details]').textContent = JSON.stringify(workers.map(worker => ({name: worker.name, local: worker.local, running: worker.running, worker_id: worker.worker_id, client_id: worker.client_id, certificate_sha256: worker.certificate_sha256})), null, 2);
      controlState();
    }
    async function refreshBatches(ticket) {
      const response = await bridge.request(path('scene-dispatch')); if (!alive(ticket)) return;
      batches = response.batches || []; const previous = $('[data-sp-batches]').value, select = $('[data-sp-batches]'); select.replaceChildren();
      if (!batches.length) option(select, '', 'No owned distributed batches');
      for (const batch of batches) option(select, batch.id, `${batch.id.slice(0, 8)} · ${batch.status}`, previous === batch.id || batchId === batch.id);
      showBatch(); controlState();
    }
    function showBatch() {const batch = batches.find(item => item.id === $('[data-sp-batches]').value); $('[data-sp-batch-detail]').textContent = batch ? JSON.stringify(batch, null, 2) : '';}
    async function watchJob(submitted, ticket) {
      jobId = submitted.id; controlState(); let job = submitted;
      while (['queued', 'running'].includes(job.state)) {await wait(250); if (!alive(ticket)) return null; job = await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}`); if (!alive(ticket)) return null; $('[data-sp-progress]').value = job.progress || 0;}
      if (job.state !== 'completed') throw Error(job.error || 'Scene operation did not complete.');
      return job.result;
    }
    async function run(operation) {
      if (busy) return; const ticket = serial; let submitted;
      try {
        ensureProject(); const document = readGraph(), values = readContext(); resultInput = stable({graph: document, context: values});
        busy = true; result = null; $('[data-sp-results]').hidden = true; controlState(); message(operation === 'render' ? 'Rendering this actual evaluated scene with Cycles…' : 'Evaluating scene paths, sets and contexts…');
        submitted = await bridge.request(path('scene-processing'), {method: 'POST', body: {recipe: {operation, graph: document, context: values}}});
        if (!alive(ticket)) return;
        result = await watchJob(submitted, ticket); if (!alive(ticket) || !result) return;
        ensureProject(); if (!result.receipt || !result.evaluation || !result.scene || !result.output_id) throw Error('The scene job returned an incomplete bound result.');
        showResult(); await bridge.onComplete?.(result, clone(context)); if (!alive(ticket)) return;
        context = clone(bridge.getContext()); await refreshHistory(ticket); message(operation === 'render' ? 'Actual Cycles frame and editable .blend saved with their byte receipts.' : 'Graph evaluation saved. Inspect locations and sets, or apply the sampled scene as one 3D edit.');
      } catch (error) {if (alive(ticket)) message(error.message, true); if (submitted?.id) await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method: 'POST', body: {}}).catch(() => {});}
      finally {if (alive(ticket)) {busy = false; jobId = null; controlState();}}
    }
    async function saveGraph(applyScene = false) {
      if (busy) return; const ticket = serial;
      try {
        ensureProject(); const document = readGraph(), values = readContext();
        if (applyScene && (!result?.scene || resultInput !== stable({graph: document, context: values}))) throw Error('The graph or context changed after this result. Evaluate again before applying the sampled scene.');
        busy = true; controlState();
        if (applyScene) await bridge.applyScene(clone(result.scene), document, clone(context)); else await bridge.applyRecipe(document, clone(context));
        if (!alive(ticket)) return; ensureProject(); context = clone(bridge.getContext()); model = clone(bridge.getProject().scene_processing || document); renderGraph();
        message(applyScene ? 'Evaluated single-frame scene and graph saved as one undoable 3D edit.' : 'Scene graph saved as one undoable edit.');
      } catch (error) {if (alive(ticket)) message(error.message, true);}
      finally {if (alive(ticket)) {busy = false; controlState();}}
    }
    async function openSaved() {
      if (busy) return; const item = history.find(value => value.output_id === $('[data-sp-history]').value); if (!item) return;
      const ticket = serial; busy = true; controlState();
      try {
        ensureProject(); result = {output_id: item.output_id, artifact_urls: item.artifact_urls};
        const receipt = await bridge.request(safeArtifact(item.artifact_urls['receipt.json']));
        if (!alive(ticket)) return;
        result.receipt = receipt;
        if (item.artifact_urls['evaluation.json']) {
          const [evaluation, scene, document] = await Promise.all(['evaluation.json', 'scene.json', 'graph.json'].map(name => bridge.request(safeArtifact(item.artifact_urls[name]))));
          if (!alive(ticket)) return; result.evaluation = evaluation; result.scene = scene;
          const values = Object.fromEntries(Object.entries(evaluation.context).filter(([key]) => key !== 'time'));
          resultInput = stable({graph: document, context: values});
        } else resultInput = '';
        showResult(); message('Saved result reopened from the project’s verified artifact inventory.');
      } catch (error) {if (alive(ticket)) {result = null; message(error.message, true);}}
      finally {if (alive(ticket)) {busy = false; controlState();}}
    }
    async function workerAction(action) {
      if (busy) return; const ticket = serial; busy = true; controlState();
      try {
        const name = $('[data-sp-worker-name]').value.trim(); let body = {name};
        if (action === 'start') {
          const existing = workers.find(worker => worker.name === name);
          if (!existing) {const port = Number($('[data-sp-port]').value); if (!Number.isInteger(port) || port < 0 || port > 65535) throw Error('Choose a valid worker port.'); body = {name, host: $('[data-sp-host]').value.trim(), port, slots: Number($('[data-sp-slots]').value)}; const advertise = $('[data-sp-advertise]').value.trim(); if (advertise) body.advertise_host = advertise;}
        } else if (action === 'pair') body = {name, invitation: JSON.parse($('[data-sp-pair-invitation]').value), participant_name: $('[data-sp-participant]').value};
        else if (action === 'revoke') body.client_id = $('[data-sp-revoke-id]').value.trim();
        const response = await bridge.request('/api/scene-workers/' + action, {method: 'POST', body}); if (!alive(ticket)) return;
        if (action === 'invite') $('[data-sp-invitation]').value = JSON.stringify(response.invitation || response, null, 2);
        if (action === 'pair') $('[data-sp-pair-invitation]').value = '';
        await refreshWorkers(ticket); message(action === 'invite' ? 'One-use invitation created. Copy it explicitly for the intended peer; it has not been sent.' : `Worker ${action} completed.`);
      } catch (error) {if (alive(ticket)) message(error.message, true);}
      finally {if (alive(ticket)) {busy = false; controlState();}}
    }
    async function dispatchBatch(action = 'submit') {
      if (busy) return; const ticket = serial; let submitted;
      try {
        ensureProject(); let url, body;
        if (action === 'submit') {
          const document = readGraph(), frames = $('[data-sp-frames]').value.split(',').map(value => {if (!value.trim() || !Number.isFinite(Number(value))) throw Error('Frames must be finite comma-separated numbers.'); return Number(value);});
          const contexts = JSON.parse($('[data-sp-variations]').value), selectedWorkers = [...$('[data-sp-workers]').querySelectorAll('input:checked')].map(input => input.value);
          if (!selectedWorkers.length) throw Error('Select at least one explicitly paired worker.');
          if (!Array.isArray(contexts) || !contexts.length || contexts.length * frames.length > 64) throw Error('Choose 1–64 context/frame tasks.');
          body = {graph: document, contexts, frames, workers: selectedWorkers, operation_id: crypto.randomUUID().replaceAll('-', '')}; url = path('scene-dispatch');
        } else {batchId = $('[data-sp-batches]').value; if (!batchId) throw Error('Select an owned batch.'); url = path(`scene-dispatch/${encodeURIComponent(batchId)}/${action}`); body = {};}
        busy = true; controlState(); message(action === 'submit' ? 'Submitting actual frames to the selected pinned workers…' : `Requesting batch ${action}…`);
        const response = await bridge.request(url, {method: 'POST', body}); if (!alive(ticket)) return;
        batchId = response.batch?.id || response.id || batchId;
        submitted = response.job;
        if (submitted && action !== 'cancel') {
          result = await watchJob(submitted, ticket); if (!alive(ticket) || !result) return;
          resultInput = ''; showResult(); await bridge.onComplete?.(result, clone(context));
          if (!alive(ticket)) return; context = clone(bridge.getContext()); await refreshHistory(ticket);
        }
        await refreshBatches(ticket); message(action === 'cancel' ? 'Cancellation requested. The retained batch status distinguishes settled tasks from unconfirmed peer work.' : 'Distributed result collected with actual task artifacts and byte receipts.');
      } catch (error) {if (alive(ticket)) {message(error.message, true); await refreshBatches(ticket).catch(() => {});}}
      finally {if (alive(ticket)) {busy = false; jobId = null; controlState();}}
    }
    function close() {if (busy) {message(jobId ? 'Cancel or finish the owned render job before closing.' : 'Wait for the current scene request to finish.'); return;} serial++; $('[data-sp-preview]').pause(); $('[data-sp-invitation]').value = ''; $('[data-sp-pair-invitation]').value = ''; dialog.close();}
    $('[data-sp-close]').onclick = close; dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    for (const op of operations) option($('[data-sp-operation]'), op, op.replaceAll('_', ' '));
    $('[data-sp-add]').onclick = () => {try {addNode();} catch (error) {message(error.message, true);}};
    $('[data-sp-node-update]').onclick = () => {try {readGraph(); overrides = readContext(); renderGraph(); message('Node draft updated. Evaluate to validate the resulting scene.');} catch (error) {message(error.message, true);}};
    $('[data-sp-duplicate]').onclick = () => {try {readGraph(); overrides = readContext(); if (model.nodes.length >= 128) throw Error('At most 128 scene nodes are supported.'); const node = clone(model.nodes.find(item => item.id === selected)); node.id = nextID('node', model.nodes.map(item => item.id)); model.nodes.push(node); selected = node.id; renderGraph();} catch (error) {message(error.message, true);}};
    $('[data-sp-delete]').onclick = () => {try {readGraph(); overrides = readContext(); if (model.output === selected || model.nodes.some(item => item.id !== selected && inputs(item).includes(selected))) throw Error('Reconnect dependent nodes and choose another output before deleting this node.'); model.nodes = model.nodes.filter(item => item.id !== selected); selected = model.output; renderGraph();} catch (error) {message(error.message, true);}};
    $('[data-sp-output]').onchange = () => {model.output = $('[data-sp-output]').value;};
    $('[data-sp-schema-update]').onclick = () => {try {overrides = readContext(); const schema = JSON.parse($('[data-sp-schema]').value); if (!schema || Array.isArray(schema) || typeof schema !== 'object') throw Error('Use an object of typed variable declarations.'); model.context = schema; overrides = Object.fromEntries(Object.entries(overrides).filter(([key]) => key in schema)); renderContext(); message('Typed context schema updated in the draft.');} catch (error) {message(error.message, true);}};
    $('[data-sp-asset]').onchange = () => {try {const previous = model.assets.find(item => item.id === asset); if (previous) previous.scene = JSON.parse($('[data-sp-asset-json]').value); asset = $('[data-sp-asset]').value; renderAsset();} catch (error) {message(error.message, true);}};
    $('[data-sp-asset-update]').onclick = () => {try {model.assets.find(item => item.id === asset).scene = JSON.parse($('[data-sp-asset-json]').value); message('Embedded scene draft updated. Backend validation runs before save or render.');} catch (error) {message(error.message, true);}};
    function capture(newAsset) {readGraph(); const scene = bridge.getProject()?.settings?.scene; if (!scene) throw Error('Author a scene in the 3D workspace before capturing it.'); if (newAsset) {if (model.assets.length >= 32) throw Error('At most 32 embedded assets are supported.'); asset = nextID('asset', model.assets.map(item => item.id)); model.assets.push({id: asset, scene: clone(scene)});} else model.assets.find(item => item.id === asset).scene = clone(scene); renderAsset(); message('Current 3D scene captured in the graph draft. Save graph to persist it.');}
    $('[data-sp-capture]').onclick = () => {try {capture(false);} catch (error) {message(error.message, true);}};
    $('[data-sp-new-asset]').onclick = () => {try {capture(true);} catch (error) {message(error.message, true);}};
    $('[data-sp-evaluate]').onclick = () => run('evaluate'); $('[data-sp-render]').onclick = () => run('render');
    $('[data-sp-save]').onclick = () => saveGraph(); $('[data-sp-apply-scene]').onclick = () => saveGraph(true); $('[data-sp-load]').onclick = openSaved;
    $('[data-sp-cancel]').onclick = async () => {if (!jobId) return; try {await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: 'POST', body: {}}); message('Owned job cancellation requested; waiting for actual children and paired task receipts to settle…');} catch (error) {message(error.message, true);}};
    for (const action of ['start', 'stop', 'invite', 'pair', 'revoke']) $(`[data-sp-${action}]`).onclick = () => workerAction(action);
    $('[data-sp-refresh-workers]').onclick = () => refreshWorkers(serial).catch(error => message(error.message, true));
    $('[data-sp-dispatch]').onclick = () => dispatchBatch();
    for (const action of ['cancel', 'retry', 'resume']) $(`[data-sp-batch-${action}]`).onclick = () => dispatchBatch(action);
    $('[data-sp-batch-refresh]').onclick = () => refreshBatches(serial).catch(error => message(error.message, true)); $('[data-sp-batches]').onchange = showBatch;
    $('[data-sp-import]').onclick = () => $('[data-sp-import-file]').click();
    $('[data-sp-import-file]').onchange = async event => {const file = event.target.files?.[0]; event.target.value = ''; if (!file || busy) return; const ticket = serial; try {if (file.size > 8 * 1024 * 1024) throw Error('Graph JSON must be at most 8 MiB.'); const document = JSON.parse(await file.text()); if (!alive(ticket)) return; if (document.version !== 1 || !Array.isArray(document.nodes) || !Array.isArray(document.assets) || !document.context) throw Error('Choose a CINEMATICUM version 1 scene graph.'); ensureProject(); busy = true; controlState(); await bridge.applyRecipe(document, clone(context)); if (!alive(ticket)) return; context = clone(bridge.getContext()); model = clone(bridge.getProject().scene_processing || document); selected = model.output; asset = model.assets[0]?.id; overrides = {}; renderGraph(); message('Imported graph validated and saved as one undoable edit.');} catch (error) {if (alive(ticket)) message(error.message, true);} finally {if (alive(ticket)) {busy = false; controlState();}}};
    async function open() {
      if (disposed || dialog.open) return; const project = bridge.getProject(); if (!project) {bridge.notify?.('Open a project before editing a scene graph.', true); return;}
      context = clone(bridge.getContext()); context.projectId ||= project.id; const ticket = ++serial;
      model = project.scene_processing ? clone(project.scene_processing) : null; selected = null; asset = null; overrides = {}; result = null; resultInput = ''; history = []; workers = []; batches = []; jobId = null; batchId = null;
      busy = true; $('[data-sp-results]').hidden = true; $('[data-sp-invitation]').value = ''; dialog.showModal(); controlState(); message('Opening the scene graph and private worker status…');
      try {
        capabilities = await bridge.request('/api/scene-processing-capabilities'); if (!alive(ticket)) return;
        model ||= clone(capabilities.default_graph); if (!model) throw Error('No graph authoring model is available.');
        if (!project.scene_processing && project.settings?.scene) model.assets[0].scene = clone(project.settings.scene);
        selected = model.output; asset = model.assets[0]?.id; renderGraph();
        await Promise.all([refreshHistory(ticket), refreshWorkers(ticket), refreshBatches(ticket)]); if (!alive(ticket)) return;
        message(capabilities.available ? 'Edit sources and nodes, evaluate paths and sets, then render locally or on explicitly paired workers.' : 'Graph evaluation is available. Install Blender and FFmpeg to render locally, or explicitly pair an available worker.');
      } catch (error) {if (alive(ticket)) {if (model) renderGraph(); message(error.message, true);}}
      finally {if (alive(ticket)) {busy = false; controlState();}}
    }
    return {open, close, destroy() {disposed = true; serial++; $('[data-sp-preview]').pause(); if (jobId) bridge.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: 'POST', body: {}}).catch(() => {}); dialog.remove();}};
  }
  window.CinematicumSceneProcessing = {mount};
})();

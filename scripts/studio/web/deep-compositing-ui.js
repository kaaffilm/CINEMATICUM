/* Editable deep EXR graphs. The bridge owns project undo/save and job admission. */
(() => {
  "use strict";
  const clone = value => JSON.parse(JSON.stringify(value));
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const ops = ["source", "merge", "over", "holdout", "flatten", "channels"];
  const defaults = () => ({version: 1, nodes: [], outputs: [], preview: {
    output: 0, channels: ["R", "G", "B"], alpha: "A", exposure: 0,
    transfer: "linear_to_srgb", auxiliary: "error"
  }});

  function validateGraph(graph) {
    if (!graph || graph.version !== 1 || !Array.isArray(graph.nodes) || !graph.nodes.length || graph.nodes.length > 48)
      throw Error("Add between 1 and 48 graph nodes.");
    const byId = new Map();
    for (const node of graph.nodes) {
      if (!node || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(node.id) || byId.has(node.id) || !ops.includes(node.op))
        throw Error("Every node needs a unique valid identifier and supported operation.");
      byId.set(node.id, node);
      if (node.op === "source" && (!/^[0-9a-f]{64}$/.test(node.source_id) || !Number.isInteger(node.part) || node.part < 0 || node.part > 15))
        throw Error("Select an admitted EXR source and logical part.");
    }
    if (!Array.isArray(graph.outputs) || !graph.outputs.length || graph.outputs.length > 16 || new Set(graph.outputs).size !== graph.outputs.length)
      throw Error("Choose between 1 and 16 distinct export nodes.");
    const visited = new Set(), visiting = new Set();
    const visit = id => {
      if (!byId.has(id)) throw Error("A graph connection references a missing node.");
      if (visiting.has(id)) throw Error("A graph cannot contain a cycle.");
      if (visited.has(id)) return;
      visiting.add(id);
      const node = byId.get(id);
      const inputs = ["merge", "over", "holdout"].includes(node.op) ? node.inputs : node.op === "source" ? [] : [node.input];
      if (!Array.isArray(inputs) || (["merge", "over", "holdout"].includes(node.op) && inputs.length !== 2))
        throw Error("Binary nodes need two input connections.");
      inputs.forEach(visit);
      visiting.delete(id); visited.add(id);
    };
    graph.outputs.forEach(visit);
    if (visited.size !== byId.size) throw Error("Every node must contribute to an export output.");
    const preview = graph.preview;
    if (!preview || !Number.isInteger(preview.output) || preview.output < 0 || preview.output >= graph.outputs.length ||
        !Array.isArray(preview.channels) || preview.channels.length !== 3 || preview.channels.some(c => typeof c !== "string" || !c.trim()) ||
        !Number.isFinite(preview.exposure) || preview.exposure < -16 || preview.exposure > 16)
      throw Error("Choose a preview output, three channels and exposure between −16 and 16.");
    return graph;
  }

  function mount(host, bridge) {
    if (!host || !bridge || !bridge.request || !bridge.getProject || !bridge.getContext || !bridge.applyRecipe)
      throw Error("Deep compositing requires a project context, request and undoable recipe bridge.");
    const style = document.createElement("style");
    style.textContent = `
      .deep-dialog{color:#ecebf0;background:#17191f;border:1px solid #484c59;border-radius:12px;width:min(1120px,94vw);max-height:92vh;padding:0}
      .deep-dialog::backdrop{background:#05070ccc}.deep-dialog header,.deep-dialog footer{padding:14px 18px;display:flex;gap:10px;align-items:center;border-bottom:1px solid #363944}
      .deep-dialog header h2{margin:0;font-size:18px;flex:1}.deep-dialog footer{border-top:1px solid #363944;border-bottom:0;flex-wrap:wrap}
      .deep-body{padding:16px 18px;overflow:auto;max-height:72vh}.deep-grid{display:grid;grid-template-columns:minmax(220px,1fr) minmax(320px,2fr);gap:16px}
      .deep-dialog label{display:block;font-size:12px;color:#c6c9d1;margin:9px 0 4px}.deep-dialog input,.deep-dialog select,.deep-dialog textarea{box-sizing:border-box;width:100%;background:#242731;color:#f0f1f5;border:1px solid #484d5d;border-radius:5px;padding:7px}
      .deep-dialog button{background:#2c3240;color:#f0f1f5;border:1px solid #525a6d;border-radius:5px;padding:7px 10px;cursor:pointer}.deep-dialog button:disabled{opacity:.5;cursor:default}
      .deep-dialog .deep-primary{background:#415c87}.deep-dialog .deep-row{display:flex;gap:7px;align-items:end}.deep-dialog .deep-row>*{flex:1;min-width:0}
      .deep-dialog p{font-size:12px;line-height:1.5;color:#bec4d0}.deep-dialog .deep-nodes{display:grid;gap:5px;margin-top:10px}.deep-dialog .deep-nodes button{text-align:left;overflow-wrap:anywhere}
      .deep-dialog .deep-nodes button[aria-pressed=true]{border-color:#93bbff;background:#304562}.deep-dialog textarea{font:12px/1.5 ui-monospace,monospace;min-height:100px;resize:vertical}
      .deep-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace}.deep-dialog .deep-status{flex:1;font-size:12px}.deep-dialog .deep-error{color:#ffaca8}
      .deep-dialog .deep-preview{max-width:100%;max-height:320px;object-fit:contain;background:repeating-conic-gradient(#222 0% 25%,#353535 0% 50%) 50%/16px 16px}
      .deep-dialog a{color:#a8c9ff;margin-right:14px}.deep-dialog [hidden]{display:none!important}.deep-dialog summary{cursor:pointer;font-size:13px;padding:8px 0}
      @media(max-width:750px){.deep-grid{grid-template-columns:1fr}.deep-body{max-height:68vh}}
    `;
    const dialog = document.createElement("dialog");
    dialog.className = "deep-dialog";
    dialog.innerHTML = `
      <header><h2>Deep EXR compositing</h2><button type="button" data-close>Close</button></header>
      <div class="deep-body"><p>Each node processes one EXR part. Export separate branches for each view or layer. The EXR keeps deep samples and numeric channels; the displayed PNG is a separate SDR preview.</p>
      <div class="deep-grid"><section>
        <label>Admitted EXR source and part<select data-source></select></label>
        <div class="deep-row"><button type="button" data-import>Import EXR…</button><button type="button" data-add-source>Add source node</button></div>
        <input type="file" accept=".exr" data-file hidden><pre data-source-details></pre>
        <label>New operation<select data-operation><option value="merge">Merge samples</option><option value="over">Depth-aware over</option><option value="holdout">Opaque depth holdout</option><option value="flatten">Flatten samples</option><option value="channels">Edit channels</option></select></label>
        <button type="button" data-add>Add operation</button>
        <div class="deep-nodes" data-nodes></div>
      </section><section>
        <h3 data-node-title>Choose a node</h3><div data-editor hidden>
        <label data-source-label>Source part<select data-node-source></select></label>
        <label data-first-label>Input<select data-first></select></label>
        <label data-second-label>Second input / holdout matte<select data-second></select></label>
        <label data-aux-label>Auxiliary / UINT channel policy<select data-aux><option value="error">Reject ambiguous mixture</option><option value="front">Select front sample explicitly</option></select></label>
        <label data-channel-label>Channel edits — rename, remove, scale and create<textarea data-channel spellcheck="false"></textarea></label>
        <p data-node-help></p><div class="deep-row"><button type="button" data-update>Update node</button><button type="button" data-delete>Remove node</button></div>
        </div>
        <label>Export node identifiers, in part order<input data-outputs placeholder="left_over, right_over"></label>
        <details open><summary>Preview channels and display</summary>
          <label>Export output index<input type="number" min="0" max="15" step="1" data-preview-output></label>
          <label>Red, green and blue channels<input data-preview-channels placeholder="R, G, B"></label>
          <div class="deep-row"><label>Alpha (blank = opaque)<input data-preview-alpha></label><label>Exposure stops<input type="number" min="-16" max="16" step="0.25" data-exposure></label></div>
          <label>Display transfer<select data-transfer><option value="linear_to_srgb">Linear to sRGB preview</option><option value="identity">Identity — unmanaged preview</option></select></label>
          <label>Preview auxiliary policy<select data-preview-aux><option value="error">Reject ambiguous mixture</option><option value="front">Select front sample explicitly</option></select></label>
        </details>
      </section></div>
      <details><summary>Graph JSON</summary><p>Edit an existing graph or copy it to another project after admitting the same sources. Loading updates this dialog; Apply graph creates one undoable project edit.</p><textarea data-json spellcheck="false"></textarea><button type="button" data-load-json>Load edited graph</button></details>
      <details><summary>Processing rules and runtime</summary><pre data-capabilities></pre></details>
      <section data-result hidden><h3>Rendered artifact</h3><img class="deep-preview" data-image alt="Selected EXR channels displayed as an SDR preview"><pre data-result-info></pre><div data-links></div></section>
      </div><footer><button type="button" data-apply>Apply graph</button><button type="button" class="deep-primary" data-render>Render EXR</button><button type="button" data-cancel hidden>Cancel job</button><span class="deep-status" role="status" aria-live="polite" data-status></span></footer>
    `;
    host.append(style, dialog);
    const el = selector => dialog.querySelector(selector);
    let graph = defaults(), context = null, sources = [], caps = null;
    let selected = null, busy = false, jobId = null, serial = 0, disposed = false;
    const active = ticket => !disposed && dialog.open && ticket === serial;
    const endpoint = (action, saved = context) => `/api/projects/${encodeURIComponent(saved.projectId)}/${action}`;
    const notify = (message, error = false) => {
      el("[data-status]").textContent = message;
      el("[data-status]").classList.toggle("deep-error", error);
    };
    const ensureContext = () => {
      if (bridge.getContext().projectId !== context.projectId) throw Error("The current project changed. Reopen the deep graph in the intended project.");
    };
    const sourceOptions = () => sources.flatMap(source => (source.parts || []).map(part => ({
      value: `${source.id}:${part.index}`, source, part,
      label: `${source.name} · ${part.view || "no view"} · ${part.name} · ${part.deep ? "deep" : "flat"}`
    })));
    function options(select, items, selectedValue) {
      select.replaceChildren();
      for (const item of items) {
        const option = document.createElement("option");
        option.value = item.value; option.textContent = item.label;
        select.append(option);
      }
      if (selectedValue != null) select.value = selectedValue;
    }
    function setBusy(value) {
      busy = value;
      for (const control of dialog.querySelectorAll("button,input,select,textarea")) control.disabled = busy;
      el("[data-cancel]").hidden = !jobId;
      el("[data-cancel]").disabled = !jobId;
      el("[data-render]").disabled = busy || !caps?.available;
    }
    function refreshSourceDetails() {
      const entry = sourceOptions().find(item => item.value === el("[data-source]").value);
      el("[data-source-details]").textContent = entry ? `${entry.part.width} × ${entry.part.height} · ${entry.part.total_samples} samples\n${entry.part.channels.map(c => `${c.name} (${c.type})`).join(", ")}` : "Import an actual EXR source to begin.";
    }
    function renderEditor() {
      const node = graph.nodes.find(n => n.id === selected);
      el("[data-editor]").hidden = !node;
      el("[data-node-title]").textContent = node ? `${node.id} · ${node.op}` : "Choose a node";
      if (!node) return;
      const binary = ["merge", "over", "holdout"].includes(node.op);
      el("[data-source-label]").hidden = node.op !== "source";
      el("[data-first-label]").hidden = node.op === "source";
      el("[data-second-label]").hidden = !binary;
      el("[data-aux-label]").hidden = !["merge", "over", "holdout", "flatten"].includes(node.op);
      el("[data-channel-label]").hidden = node.op !== "channels";
      options(el("[data-node-source]"), sourceOptions(), `${node.source_id}:${node.part}`);
      const inputs = graph.nodes.filter(n => n.id !== node.id).map(n => ({value: n.id, label: `${n.id} · ${n.op}`}));
      options(el("[data-first]"), inputs, binary ? node.inputs?.[0] : node.input);
      options(el("[data-second]"), inputs, node.inputs?.[1]);
      el("[data-aux]").value = node.auxiliary || "error";
      el("[data-channel]").value = JSON.stringify({rename: node.rename || {}, remove: node.remove || [], scale: node.scale || {}, create: node.create || {}}, null, 2);
      el("[data-node-help]").textContent = caps?.semantics?.[node.op] || (node.op === "channels" ? "Scale uses final channel names after rename/remove/create. UINT edits must retain exact integers. Example: {\"scale\":{\"R\":{\"multiply\":2}},\"rename\":{\"velocity.x\":\"motion.X\"}}" : "Select the actual source part for this node.");
    }
    function redraw() {
      const sourceValue = el("[data-source]").value;
      options(el("[data-source]"), sourceOptions(), sourceValue || undefined);
      refreshSourceDetails();
      el("[data-nodes]").replaceChildren();
      for (const node of graph.nodes) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `${node.id} · ${node.op}${node.inputs ? ` ← ${node.inputs.join(", ")}` : node.input ? ` ← ${node.input}` : ""}`;
        button.setAttribute("aria-pressed", String(node.id === selected));
        button.addEventListener("click", () => { readPreview(); selected = node.id; redraw(); });
        el("[data-nodes]").append(button);
      }
      el("[data-outputs]").value = graph.outputs.join(", ");
      const preview = {...defaults().preview, ...graph.preview};
      graph.preview = preview;
      el("[data-preview-output]").value = String(preview.output);
      el("[data-preview-channels]").value = preview.channels.join(", ");
      el("[data-preview-alpha]").value = preview.alpha || "";
      el("[data-exposure]").value = String(preview.exposure);
      el("[data-transfer]").value = preview.transfer;
      el("[data-preview-aux]").value = preview.auxiliary;
      el("[data-json]").value = JSON.stringify(graph, null, 2);
      renderEditor(); setBusy(busy);
    }
    function readPreview() {
      graph.outputs = el("[data-outputs]").value.split(",").map(v => v.trim()).filter(Boolean);
      graph.preview = {output: Number(el("[data-preview-output]").value), channels: el("[data-preview-channels]").value.split(",").map(v => v.trim()),
        alpha: el("[data-preview-alpha]").value.trim() || null, exposure: Number(el("[data-exposure]").value),
        transfer: el("[data-transfer]").value, auxiliary: el("[data-preview-aux]").value};
    }
    function updateNode() {
      const node = graph.nodes.find(n => n.id === selected);
      if (!node) return;
      if (node.op === "source") {
        const value = sourceOptions().find(item => item.value === el("[data-node-source]").value);
        if (!value) throw Error("Choose an admitted source part.");
        node.source_id = value.source.id; node.part = value.part.index;
      } else if (["merge", "over", "holdout"].includes(node.op)) node.inputs = [el("[data-first]").value, el("[data-second]").value];
      else node.input = el("[data-first]").value;
      if (["merge", "over", "holdout", "flatten"].includes(node.op)) node.auxiliary = el("[data-aux]").value;
      if (node.op === "channels") {
        const data = JSON.parse(el("[data-channel]").value);
        if (!data || typeof data !== "object" || Array.isArray(data) || Object.keys(data).some(key => !["rename", "remove", "scale", "create"].includes(key)))
          throw Error("Channel edits accept rename, remove, scale and create only.");
        Object.assign(node, {rename: {}, remove: [], scale: {}, create: {}}, data);
      }
    }
    function nextId(prefix) {
      let index = 1;
      while (graph.nodes.some(node => node.id === `${prefix}${index}`)) index += 1;
      return `${prefix}${index}`;
    }
    const safe = callback => async event => {
      try { await callback(event); } catch (error) { notify(error.message || String(error), true); }
    };
    el("[data-source]").addEventListener("change", refreshSourceDetails);
    el("[data-add-source]").addEventListener("click", safe(() => {
      readPreview();
      const entry = sourceOptions().find(item => item.value === el("[data-source]").value);
      if (!entry) throw Error("Import an EXR source and choose its part first.");
      const node = {id: nextId("source"), op: "source", source_id: entry.source.id, part: entry.part.index};
      graph.nodes.push(node); graph.outputs.push(node.id); selected = node.id; redraw();
    }));
    el("[data-add]").addEventListener("click", safe(() => {
      readPreview();
      if (!graph.nodes.length) throw Error("Add a source node first.");
      const op = el("[data-operation]").value, input = selected || graph.nodes.at(-1).id;
      const node = {id: nextId(op), op};
      if (["merge", "over", "holdout"].includes(op)) {
        const second = graph.nodes.find(n => n.id !== input)?.id;
        if (!second) throw Error("This operation needs a second source or processing branch.");
        node.inputs = [input, second];
      } else node.input = input;
      if (op === "channels") Object.assign(node, {rename: {}, remove: [], scale: {}, create: {}});
      else node.auxiliary = "error";
      const consumed = node.inputs || [node.input];
      graph.outputs = graph.outputs.filter(id => !consumed.includes(id));
      graph.outputs.push(node.id); graph.nodes.push(node); selected = node.id; redraw();
    }));
    el("[data-update]").addEventListener("click", safe(() => { readPreview(); updateNode(); redraw(); notify("Node updated in this dialog. Apply graph saves one undoable project edit."); }));
    el("[data-delete]").addEventListener("click", safe(() => {
      readPreview();
      if (graph.nodes.some(n => n.id !== selected && (n.input === selected || n.inputs?.includes(selected))))
        throw Error("Reconnect or remove dependent nodes before deleting this node.");
      graph.nodes = graph.nodes.filter(n => n.id !== selected); graph.outputs = graph.outputs.filter(id => id !== selected);
      selected = graph.nodes[0]?.id || null; redraw();
    }));
    el("[data-load-json]").addEventListener("click", safe(() => {
      const value = JSON.parse(el("[data-json]").value);
      validateGraph(value); graph = clone(value); selected = graph.nodes[0].id; redraw(); notify("Graph loaded into this dialog.");
    }));
    el("[data-apply]").addEventListener("click", safe(async () => {
      ensureContext(); readPreview(); updateNode(); validateGraph(graph);
      const frozen = clone(graph), saved = clone(context);
      await bridge.applyRecipe(frozen, saved);
      const latest = bridge.getContext();
      if (latest.projectId === saved.projectId) context = clone(latest);
      redraw(); notify("Graph applied as one undoable project edit.");
    }));
    el("[data-import]").addEventListener("click", () => el("[data-file]").click());
    el("[data-file]").addEventListener("change", safe(async () => {
      const file = el("[data-file]").files[0]; el("[data-file]").value = "";
      if (!file) return;
      ensureContext();
      if (!/\.exr$/i.test(file.name) || file.size > (caps?.limits?.source_bytes || 268435456)) throw Error("Select an EXR within the source size limit.");
      const ticket = serial; setBusy(true); notify("Reading actual EXR headers and deep samples…");
      try {
        await bridge.request(endpoint("deep-import") + `?name=${encodeURIComponent(file.name)}`, {method: "POST", body: file, raw: true});
        const data = await bridge.request(endpoint("deep-sources"));
        if (!active(ticket)) return;
        sources = Array.isArray(data) ? data : data.sources || []; redraw(); notify("EXR admitted with its content identity and part/channel inventory.");
      } finally { if (active(ticket)) setBusy(false); }
    }));
    function safeUrl(value, saved) {
      if (typeof value !== "string") throw Error("The render did not return a valid artifact URL.");
      const url = new URL(value, location.href);
      const prefix = endpoint("deep/outputs/", saved);
      if (url.origin !== location.origin || !url.pathname.startsWith(prefix)) throw Error("The artifact URL is outside this project's deep outputs.");
      return url.href;
    }
    el("[data-render]").addEventListener("click", safe(async () => {
      ensureContext(); readPreview(); updateNode(); validateGraph(graph);
      const frozen = clone(graph), saved = clone(context), ticket = serial;
      setBusy(true); notify("Submitting the frozen EXR graph…");
      try {
        let job = await bridge.request(endpoint("deep-render", saved), {method: "POST", body: {recipe: frozen}});
        if (!active(ticket)) { if (job.id) await bridge.request(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, {method: "POST", body: {}}); return; }
        jobId = job.id; setBusy(true);
        while (["queued", "running"].includes(job.state)) {
          notify(`Deep EXR ${job.state} · ${Math.round((job.progress || 0) * 100)}%`);
          await wait(220);
          if (!active(ticket)) return;
          job = await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}`);
        }
        if (job.state !== "completed") throw Error(job.error || `Deep compositing ${job.state}.`);
        const result = job.result || {};
        const base = endpoint(`deep/outputs/${encodeURIComponent(result.output_id || jobId)}/`, saved);
        const preview = safeUrl(result.preview_url || result.display_url || base + "preview.png", saved);
        const exr = safeUrl(result.exr_url || base + "composite.exr", saved);
        const receipt = safeUrl(result.receipt_url || base + "receipt.json", saved);
        el("[data-image]").src = preview;
        const parts = result.receipt?.output?.parts || [];
        el("[data-result-info]").textContent = parts.map(p => `${p.name} · ${p.view || "no view"} · ${p.deep ? "deep" : "flat"} · ${p.total_samples} samples · ${p.channels.length} channels`).join("\n");
        el("[data-links]").replaceChildren();
        for (const [label, href] of [["Download actual EXR", exr], ["Download receipt", receipt], ["Download SDR preview", preview]]) {
          const link = document.createElement("a"); link.textContent = label; link.href = href; link.setAttribute("download", ""); el("[data-links]").append(link);
        }
        el("[data-result]").hidden = false;
        if (bridge.onComplete) await bridge.onComplete(result, saved);
        notify("EXR rendered. Sample/channel metadata and source hashes are recorded in the receipt.");
      } finally { jobId = null; if (active(ticket)) setBusy(false); }
    }));
    el("[data-cancel]").addEventListener("click", safe(async () => {
      if (!jobId) return;
      el("[data-cancel]").disabled = true;
      await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: "POST", body: {}});
      notify("Cancellation requested; waiting for the owned worker to settle.");
    }));
    function close() {
      if (busy) { notify("Cancel the active job and wait for it to settle before closing.", true); return; }
      serial += 1; dialog.close(); el("[data-image]").removeAttribute("src");
    }
    el("[data-close]").addEventListener("click", close);
    dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
    async function open() {
      if (disposed) return;
      if (dialog.open) { dialog.focus(); return; }
      if (busy) throw Error("Wait for the current deep operation to settle.");
      context = clone(bridge.getContext());
      if (!context.projectId) throw Error("Open a project first.");
      const ticket = ++serial;
      graph = clone(bridge.getProject()?.deep_compositing || defaults());
      selected = graph.nodes[0]?.id || null;
      dialog.showModal(); redraw(); el("[data-result]").hidden = true;
      setBusy(true); notify("Inspecting the installed EXR runtime…");
      try {
        const [runtime, inventory] = await Promise.all([bridge.request("/api/deep-capabilities"), bridge.request(endpoint("deep-sources"))]);
        if (!active(ticket)) return;
        caps = runtime; sources = Array.isArray(inventory) ? inventory : inventory.sources || [];
        el("[data-capabilities]").textContent = JSON.stringify({available: caps.available, versions: caps.versions, limits: caps.limits, semantics: caps.semantics}, null, 2);
        redraw(); notify(caps.available ? "Edit the graph, apply it to the project, or render a frozen copy." : caps.reason || "The isolated Imaging runtime is unavailable.", !caps.available);
      } catch (error) { if (active(ticket)) notify(error.message, true); }
      finally { if (active(ticket)) setBusy(false); }
    }
    function destroy() {
      if (disposed) return;
      disposed = true; serial += 1;
      if (jobId) bridge.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: "POST", body: {}}).catch(() => {});
      dialog.remove(); style.remove();
    }
    return {open, close, destroy};
  }
  window.CinematicumDeepCompositing = {mount, validateGraph};
})();

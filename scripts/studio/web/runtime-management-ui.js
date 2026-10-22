/* Fixed, pinned optional runtime setup through ordinary owned Studio jobs. */
(() => {
  'use strict';
  const ids = new Set(['optiland', 'physical', 'learned', 'reconstruction']);
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const size = value => Number.isFinite(value) ? `${(value / 1048576).toFixed(1)} MiB` : 'Size not available';
  function mount(host, bridge) {
    const dialog = document.createElement('dialog');
    dialog.id = 'runtime-management-dialog'; dialog.className = 'cinematicum-runtimes';
    dialog.innerHTML = `<style>
      .cinematicum-runtimes{box-sizing:border-box;width:min(1000px,96vw);max-height:92vh;padding:0;color:#e6eef6;background:#17212b;border:1px solid #536d84;border-radius:12px;font:13px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}.cinematicum-runtimes[open]{display:flex;flex-direction:column}.cinematicum-runtimes::backdrop{background:#03080dc0}.cinematicum-runtimes header,.cinematicum-runtimes footer{padding:16px 20px;display:flex;align-items:center;gap:12px;background:#223240}.cinematicum-runtimes header>div,.cinematicum-runtimes footer>div{flex:1;min-width:0}.cinematicum-runtimes h2,.cinematicum-runtimes h3,.cinematicum-runtimes p{margin:0}.cinematicum-runtimes h2{font-size:19px}.cinematicum-runtimes h3{font-size:15px}.cinematicum-runtimes .runtime-list{padding:18px 20px;overflow:auto;display:grid;gap:16px}.cinematicum-runtimes article{display:grid;gap:10px;border:1px solid #3d5368;border-radius:8px;padding:16px;background:#101b25}.cinematicum-runtimes .runtime-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.cinematicum-runtimes button{font:inherit;border:1px solid #648ba8;background:#2e536e;color:#e8f4ff;border-radius:5px;padding:8px 12px;cursor:pointer}.cinematicum-runtimes button:disabled{opacity:.45;cursor:default}.cinematicum-runtimes .runtime-note{font-size:12px;color:#aebfd0}.cinematicum-runtimes .runtime-path,.cinematicum-runtimes .runtime-lock{font:11px/1.5 ui-monospace,monospace;overflow-wrap:anywhere;color:#bed1e2}.cinematicum-runtimes .runtime-error{color:#ffb6a1}.cinematicum-runtimes details{border-top:1px solid #344b61;padding-top:9px}.cinematicum-runtimes summary{cursor:pointer;color:#c2d6e7}.cinematicum-runtimes .runtime-downloads{display:grid;gap:7px;margin-top:10px}.cinematicum-runtimes .runtime-download{border-left:2px solid #486c87;padding-left:10px}.cinematicum-runtimes progress{width:100%;accent-color:#68bbc9}.cinematicum-runtimes [hidden]{display:none!important}
    </style><header><div><h2>Runtime setup</h2><p class="runtime-note">Install and verify the pinned engines used by this build</p></div><button type="button" data-runtime-refresh>Refresh</button><button type="button" data-runtime-close>Close</button></header><div class="runtime-list" data-runtime-list></div><footer><div><p data-runtime-status role="status" aria-live="polite"></p><progress data-runtime-progress max="1" value="0" hidden></progress></div><button type="button" data-runtime-cancel hidden>Cancel job</button></footer>`;
    host.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    let disposed = false, serial = 0, busy = false, jobId = null, rows = [], projectId = null;
    const active = ticket => !disposed && dialog.open && ticket === serial;
    const status = (text, error = false) => {$('[data-runtime-status]').textContent = text; $('[data-runtime-status]').classList.toggle('runtime-error', error);};
    function controls() {
      $('[data-runtime-refresh]').disabled = busy;
      for (const node of dialog.querySelectorAll('[data-runtime-action]')) node.disabled = busy || node.dataset.available !== 'true';
      $('[data-runtime-cancel]').hidden = !jobId; $('[data-runtime-progress]').hidden = !jobId;
    }
    function paragraph(parent, text, className = 'runtime-note') {const node = document.createElement('p'); node.className = className; node.textContent = text; parent.append(node); return node;}
    function render() {
      const list = $('[data-runtime-list]'); list.replaceChildren();
      for (const entry of rows) {
        if (!ids.has(entry.id)) continue;
        const card = document.createElement('article'); card.dataset.runtimeId = entry.id;
        const title = document.createElement('h3'); title.textContent = entry.label; card.append(title);
        paragraph(card, entry.description);
        const state = entry.managed_state === 'verified' ? 'Verified with this pinned lock in the completed job' : entry.managed_state === 'present_unverified' ? 'Runtime files found · verification required' : entry.managed_state === 'pending' ? 'Setup paused · owned progress can be resumed' : entry.managed_state === 'not_installed' ? 'Not installed' : 'Unavailable in this build';
        paragraph(card, state, 'runtime-state');
        paragraph(card, `${size(entry.download_bytes)} of pinned downloads${entry.python ? ` · Python ${entry.python}` : ''}${entry.platform ? ` · ${entry.platform}` : ''}`);
        if (entry.destination) paragraph(card, entry.destination, 'runtime-path');
        if (entry.reason) paragraph(card, entry.reason, 'runtime-error');
        if (entry.prerequisites?.llvm) paragraph(card, 'Physical rendering requires a separately installed LLVM CPU library. Setup verifies real LLVM computation and will report a missing dependency without publishing an incomplete runtime.');
        if (entry.prerequisites?.pbrt) paragraph(card, 'PBRT scene import/export do not need PBRT. Rendering with PBRT requires its separate executable.');
        const actions = document.createElement('div'); actions.className = 'runtime-actions';
        for (const [operation, label, allowed] of [['install', entry.managed_state === 'pending' ? 'Resume setup' : entry.destination_exists ? 'Install / verify' : 'Install runtime', entry.can_install], ['check', 'Verify runtime', entry.installer_available && entry.destination_exists]]) {
          const button = document.createElement('button'); button.type = 'button'; button.textContent = label; button.dataset.runtimeAction = operation; button.dataset.available = String(!!allowed);
          button.onclick = () => run(entry, operation); actions.append(button);
        }
        card.append(actions);
        if (entry.lock_sha256) {
          const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Pinned package identities'; details.append(summary);
          paragraph(details, `Lock SHA-256 ${entry.lock_sha256}`, 'runtime-lock');
          const downloads = document.createElement('div'); downloads.className = 'runtime-downloads';
          for (const download of entry.downloads || []) {const block = document.createElement('div'); block.className = 'runtime-download'; paragraph(block, `${download.name}${download.version ? ` · ${download.version}` : ''} · ${size(download.bytes)}`); paragraph(block, `SHA-256 ${download.sha256}`, 'runtime-lock'); downloads.append(block);}
          details.append(downloads); card.append(details);
        }
        list.append(card);
      }
      controls();
    }
    async function refresh() {
      if (busy || disposed) return;
      const ticket = serial; status('Reading pinned runtime information…');
      try {const response = await bridge.request('/api/runtime-management'); if (!active(ticket)) return; rows = response.runtimes || []; render(); status('Choose a runtime. Existing unmanaged installations are preserved.');}
      catch (error) {if (active(ticket)) status(error.message, true);}
    }
    async function cancel() {
      const id = jobId; if (!id) return;
      try {await bridge.request(`/api/jobs/${encodeURIComponent(id)}/cancel`, {method:'POST', body:{}}); if (id === jobId) status('Cancellation requested. Waiting for the owned installer process to stop…');}
      catch (error) {if (id === jobId) status(error.message, true);}
    }
    async function run(entry, operation) {
      if (busy || !ids.has(entry.id)) return;
      const project = bridge.getProject();
      if (!project?.id || project.id !== projectId) {status('The project changed. Reopen Runtime setup for the current project.', true); return;}
      const ticket = serial; let submitted = null;
      busy = true; controls(); status(`${operation === 'check' ? 'Verifying' : 'Installing'} ${entry.label}…`);
      try {
        submitted = await bridge.request(`/api/projects/${encodeURIComponent(projectId)}/runtime-management/${entry.id}`, {method:'POST', body:{operation, lock_sha256:entry.lock_sha256}});
        if (!submitted?.id || !/^[a-f0-9]{32}$/.test(submitted.id) || submitted.project_id !== projectId || submitted.kind !== 'runtime-setup') throw Error('The server did not return an owned runtime job identity.');
        if (!active(ticket)) {await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method:'POST', body:{}}); return;}
        jobId = submitted.id; controls(); let job = submitted;
        while (['queued', 'running'].includes(job.state)) {
          await pause(700); if (!active(ticket)) return;
          job = await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}`); if (!active(ticket)) return;
          if (job.id !== jobId || job.project_id !== projectId || job.kind !== 'runtime-setup') throw Error('Runtime job ownership changed.');
          $('[data-runtime-progress]').value = Number.isFinite(job.progress) ? job.progress : 0;
        }
        if (job.state === 'cancelled') status('Runtime setup cancelled. Existing installations remain available; owned partial downloads may be resumed.');
        else if (job.state !== 'completed') throw Error(job.error || 'Runtime setup did not complete.');
        else {
          if (job.result?.runtime_id !== entry.id || job.result?.lock_sha256 !== entry.lock_sha256) throw Error('The result does not match the requested pinned runtime.');
          rows = rows.map(row => row.id === entry.id && row.lock_sha256 === entry.lock_sha256 ? {...row, managed_state:'verified', destination_exists:true, verified_job_id:job.id} : row);
          render();
          status(`${entry.label}: installation and actual engine verification passed.`); bridge.notify?.(`${entry.label} ready`);
        }
      } catch (error) {
        if (active(ticket)) status(error.message, true);
        if (submitted?.id) await bridge.request(`/api/jobs/${encodeURIComponent(submitted.id)}/cancel`, {method:'POST', body:{}}).catch(() => {});
      } finally {if (active(ticket)) {busy = false; jobId = null; controls();}}
    }
    function close() {if (busy) {status('Wait for the runtime job or cancel it before closing.'); return;} serial++; dialog.close();}
    async function open() {
      if (disposed || busy) return; const project = bridge.getProject(); projectId = project?.id || null;
      serial++; if (!dialog.open) dialog.showModal();
      if (!projectId) {status('Open a project to own runtime setup jobs.', true); return;}
      await refresh();
    }
    function destroy() {const id = jobId; serial++; disposed = true; if (id) bridge.request(`/api/jobs/${encodeURIComponent(id)}/cancel`, {method:'POST', body:{}}).catch(() => {}); dialog.remove();}
    $('[data-runtime-close]').onclick = close; $('[data-runtime-refresh]').onclick = refresh; $('[data-runtime-cancel]').onclick = cancel;
    dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    return {open, close, destroy};
  }
  window.CinematicumRuntimeManagement = {mount};
})();

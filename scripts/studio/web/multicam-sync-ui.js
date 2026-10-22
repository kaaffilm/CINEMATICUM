/* Actual, owned audio measurements create one undoable multicamera edit. */
(function () {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const RATE = 48000;
  function mount(host, bridge) {
    const dialog = document.createElement('dialog'); dialog.className = 'multicam-sync-dialog';
    dialog.innerHTML = `<style>
.multicam-sync-dialog{width:min(1050px,94vw);max-height:92vh;padding:22px;background:#171b22;color:#e5e9ef;border:1px solid #485366;border-radius:10px}.multicam-sync-dialog h2{font-size:20px;margin:0}.multicam-sync-dialog h3{font-size:15px}.multicam-sync-dialog header,.multicam-sync-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.multicam-sync-dialog p{line-height:1.5}.multicam-sync-dialog button,.multicam-sync-dialog input,.multicam-sync-dialog select{font:inherit;color:inherit;background:#242c38;border:1px solid #4d5b6e;border-radius:4px;padding:7px}.multicam-sync-dialog button{cursor:pointer}.multicam-sync-dialog button:disabled{opacity:.45;cursor:default}.multicam-sync-dialog label{display:inline-flex;align-items:center;gap:7px;margin:8px}.multicam-sync-dialog input[type=number]{width:90px}.multicam-sync-dialog table{width:100%;border-collapse:collapse;font-size:12px}.multicam-sync-dialog th,.multicam-sync-dialog td{padding:7px;text-align:left;border-bottom:1px solid #374150}.multicam-sync-dialog .sources{max-height:29vh;overflow:auto;margin:12px 0}.multicam-sync-dialog [data-sync-results]{max-height:33vh;overflow:auto}.multicam-sync-dialog canvas{width:100%;height:68px;background:#11151b;border:1px solid #323d4c}.multicam-sync-dialog figure{margin:13px 0}.multicam-sync-dialog figcaption{font-size:12px;margin:5px 0;color:#bfc9d7}.multicam-sync-dialog [data-sync-status]{min-height:24px;color:#b5c8ff}.multicam-sync-dialog [data-sync-status].error{color:#ffb7a7}.multicam-sync-dialog progress{width:100%;margin:12px 0}.multicam-sync-dialog a{color:#a7c5ff;margin-right:14px}.multicam-sync-note{color:#bbc5d2;font-size:13px}
</style><header><h2>Synchronize camera audio</h2><button type="button" data-sync-close aria-label="Close synchronization">×</button></header>
<p class="multicam-sync-note">Choose camera channels containing the same recorded sound. Analysis measures a constant sample offset and verifies separated parts of the recording. Silent, repeated or drifting sound must be resolved before a synchronized cut can be created.</p>
<div class="sources" data-sync-sources></div>
<div><label>Reference camera <select data-sync-reference aria-label="Reference camera"></select></label><label>Analyze <input data-sync-window type="number" min="5" max="120" step="1" value="60" aria-label="Analysis duration in seconds"> seconds</label><label>Search ± <input data-sync-lag type="number" min="0.1" max="60" step="0.1" value="30" aria-label="Maximum offset in seconds"> seconds</label></div>
<div class="multicam-sync-actions"><button type="button" data-sync-analyze>Measure audio offsets</button><button type="button" data-sync-cancel disabled>Cancel measurement</button></div>
<progress data-sync-progress max="1" value="0" hidden></progress><p data-sync-status role="status"></p>
<section data-sync-results hidden></section>
<div data-sync-apply-controls hidden><label>Group name <input data-sync-name maxlength="200" value="Synchronized multicam" aria-label="Synchronized group name"></label><button type="button" data-sync-apply disabled>Create synchronized cut at playhead</button><p class="multicam-sync-note">The cut covers only the verified common sound window. Source audio follows the chosen camera. Analysis channel selection does not change the camera's playback mix.</p></div>`;
    host.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    let project = null, context = null, capability = null, busy = false, disposed = false;
    let serial = 0, jobId = null, measured = null, applied = false;
    const alive = ticket => !disposed && dialog.open && serial === ticket;
    const status = (text, error = false) => { $('[data-sync-status]').textContent = text; $('[data-sync-status]').classList.toggle('error', error); };
    function current() {
      const now = bridge.getContext();
      if (!project || now.projectId !== context.projectId || now.revision !== context.revision || bridge.getProject()?.id !== project.id) throw Error('The project changed. Reopen synchronization to use the current edit.');
    }
    function controls() {
      dialog.querySelectorAll('input,select,[data-sync-analyze]').forEach(element => {element.disabled = busy || !capability?.available;});
      $('[data-sync-close]').disabled = false;
      $('[data-sync-cancel]').disabled = !busy || !jobId;
      $('[data-sync-apply]').disabled = busy || applied || measured?.accepted !== true;
      for (const row of dialog.querySelectorAll('[data-sync-source]')) {
        if (row.dataset.noAudio === 'true') row.querySelector('[data-sync-use]').disabled = true;
      }
    }
    function selectedRows() {return [...dialog.querySelectorAll('[data-sync-source]')].filter(row => row.querySelector('[data-sync-use]').checked);}
    function references() {
      const select = $('[data-sync-reference]'), previous = select.value;
      select.innerHTML = selectedRows().map(row => `<option value="${esc(row.dataset.syncSource)}">${esc(project.assets.find(asset => asset.id === row.dataset.syncSource)?.name || row.dataset.syncSource)}</option>`).join('');
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
    }
    function sourceTable() {
      const assets = project.assets.filter(asset => asset.kind === 'video');
      $('[data-sync-sources]').innerHTML = `<table><thead><tr><th>Use</th><th>Camera</th><th>Audio stream</th><th>Channel</th><th>Window begins (s)</th></tr></thead><tbody>${assets.map(asset => {
        const streams = asset.audio_streams || [], first = streams.find(stream => stream.index === asset.audio_stream_index) || streams[0];
        return `<tr data-sync-source="${esc(asset.id)}" data-no-audio="${first ? 'false' : 'true'}"><td><input type="checkbox" data-sync-use aria-label="Synchronize ${esc(asset.name)}" ${first ? '' : 'disabled'}></td><td>${esc(asset.name)}${first ? '' : ' · no audio'}</td><td><select data-sync-stream aria-label="Analysis stream for ${esc(asset.name)}">${streams.map(stream => `<option value="${stream.index}" ${stream.index === first?.index ? 'selected' : ''}>${stream.index} · ${stream.channels} ch · ${esc(stream.language || stream.codec || 'audio')}</option>`).join('')}</select></td><td><input data-sync-channel type="number" min="0" max="${Math.max(0, (first?.channels || 1) - 1)}" step="1" value="0" aria-label="Zero-based analysis channel for ${esc(asset.name)}"></td><td><input data-sync-start type="number" min="0" max="${Math.min(21600, asset.duration)}" step="0.001" value="0" aria-label="Window start in seconds for ${esc(asset.name)}"></td></tr>`;
      }).join('')}</tbody></table>`;
      references();
    }
    function recipe() {
      const rows = selectedRows();
      if (rows.length < 2 || rows.length > 16) throw Error('Select between two and sixteen cameras with shared sound.');
      const seconds = Number($('[data-sync-window]').value), lag = Number($('[data-sync-lag]').value);
      if (!Number.isFinite(seconds) || seconds < 5 || seconds > 120 || !Number.isFinite(lag) || lag < .1 || lag > Math.min(60, seconds - 4)) throw Error('Choose 5–120 seconds of sound and a search range leaving at least four seconds of overlap.');
      const angles = rows.map(row => {
        const stream = Number(row.querySelector('[data-sync-stream]').value), channel = Number(row.querySelector('[data-sync-channel]').value), start = Number(row.querySelector('[data-sync-start]').value);
        if (!Number.isInteger(stream) || !Number.isInteger(channel) || channel < 0 || !Number.isFinite(start) || start < 0 || start > 21600) throw Error('Each selected camera needs a valid source stream, zero-based channel and window start.');
        return {asset_id: row.dataset.syncSource, stream_index: stream, channel, start_sample: Math.round(start * RATE)};
      });
      return {version: 1, angles, reference_asset_id: $('[data-sync-reference]').value,
              window_samples: Math.round(seconds * RATE), max_lag_samples: Math.round(lag * RATE), min_overlap_samples: 4 * RATE};
    }
    function clearMeasurement() {
      measured = null; applied = false; $('[data-sync-results]').hidden = true;
      $('[data-sync-results]').replaceChildren(); $('[data-sync-apply-controls]').hidden = true; controls();
    }
    function showResult(result) {
      measured = clone(result); applied = false;
      const analysis = measured.analysis, accepted = measured.accepted === true && analysis?.accepted === true;
      if (!analysis || !Array.isArray(analysis.angles) || !Array.isArray(measured.waveforms?.sources)) throw Error('The audio job returned incomplete measurement evidence.');
      if (!/^[a-f0-9]{64}$/.test(measured.artifacts?.['receipt.json']?.sha256 || '') || !/^[A-Za-z0-9_-]{1,128}$/.test(measured.output_id || '')) throw Error('The audio result has no owned receipt identity.');
      const report = $('[data-sync-results]'); report.hidden = false;
      const root = `/api/projects/${encodeURIComponent(project.id)}/multicam-sync/outputs/${encodeURIComponent(measured.output_id)}/`;
      report.innerHTML = `<h3>${accepted ? 'Measured synchronization' : 'Synchronization needs review'}</h3><p>${accepted ? `${(analysis.common_overlap.samples / RATE).toFixed(3)} seconds of common sound verified.` : esc(analysis.reason === 'no_common_overlap' ? 'The pairwise matches have no shared window across every selected camera.' : 'At least one camera was rejected. No synchronized edit can be created from this result.')}</p><table><thead><tr><th>Camera</th><th>Offset from reference</th><th>Correlation</th><th>Verification</th></tr></thead><tbody>${analysis.angles.map(angle => `<tr><td>${esc(project.assets.find(asset => asset.id === angle.asset_id)?.name || angle.asset_id)}</td><td>${angle.accepted ? `${(angle.offset_samples / RATE * 1000).toFixed(3)} ms · ${angle.offset_samples} samples` : 'Unverified'}</td><td>${Number.isFinite(angle.correlation) ? Number(angle.correlation).toFixed(4) : '—'}</td><td>${angle.accepted ? (angle.reason === 'reference' ? 'Reference' : `Verified${angle.polarity === -1 ? ' · inverted waveform polarity' : ''}`) : esc(angle.message || angle.reason)}</td></tr>`).join('')}</tbody></table><p><a href="${root}analysis.json" download>Measurement report</a><a href="${root}waveforms.json" download>Measured waveforms</a><a href="${root}receipt.json" download>Source receipt</a></p><div data-sync-plots></div>`;
      const byId = new Map(analysis.angles.map(value => [value.asset_id, value]));
      const waves = measured.waveforms.sources;
      const begin = Math.min(...waves.map(wave => wave.start_sample + (accepted ? byId.get(wave.asset_id)?.offset_samples || 0 : 0)));
      const end = Math.max(...waves.map(wave => wave.start_sample + wave.samples + (accepted ? byId.get(wave.asset_id)?.offset_samples || 0 : 0)));
      for (const wave of waves) {
        const figure = document.createElement('figure'), caption = document.createElement('figcaption'), canvas = document.createElement('canvas');
        caption.textContent = `${project.assets.find(asset => asset.id === wave.asset_id)?.name || wave.asset_id} · ${accepted ? 'aligned to reference clock' : 'original window; alignment unverified'} · ${(wave.samples / RATE).toFixed(3)} s`;
        canvas.width = 900; canvas.height = 80; canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', caption.textContent);
        figure.append(caption, canvas); $('[data-sync-plots]').append(figure);
        const draw = canvas.getContext('2d'); if (!draw) continue;
        const offset = accepted ? byId.get(wave.asset_id)?.offset_samples || 0 : 0;
        const peak = Math.max(.001, Number(wave.peak) || 0);
        draw.strokeStyle = accepted ? '#94b6ff' : '#8f9bad'; draw.lineWidth = 1;
        draw.beginPath();
        for (const block of wave.blocks || []) {
          const x = (block.start_sample + block.samples / 2 + offset - begin) / Math.max(1, end - begin) * canvas.width;
          draw.moveTo(x, 40 - block.max / peak * 34); draw.lineTo(x, 40 - block.min / peak * 34);
        }
        draw.stroke();
      }
      $('[data-sync-apply-controls]').hidden = !accepted;
      status(accepted ? 'Audio offsets verified. Review the waveforms, then create the synchronized cut.' : 'Measurement completed with an explicit refusal. Choose a distinct shared sound window or align these cameras manually.', !accepted);
      controls();
    }
    async function cancel(id) {if (id) await bridge.request(`/api/jobs/${encodeURIComponent(id)}/cancel`, {method: 'POST', body: {}}).catch(() => {});}
    async function analyze() {
      if (busy || disposed) return;
      const ticket = ++serial; let submitted = null; busy = true; clearMeasurement(); controls();
      $('[data-sync-progress]').hidden = false; $('[data-sync-progress]').value = 0;
      try {
        current(); const request = recipe(); status('Decoding selected source samples and measuring their offsets…');
        submitted = await bridge.request(`/api/projects/${encodeURIComponent(project.id)}/multicam-sync`, {method: 'POST', body: {project: clone(project), recipe: request}});
        if (!submitted?.id) throw Error('The server did not create an owned audio measurement job.');
        if (!alive(ticket)) {await cancel(submitted.id); return;}
        jobId = submitted.id; controls(); let job = submitted;
        while (['queued', 'running'].includes(job.state)) {
          await pause(200); if (!alive(ticket)) return;
          current(); job = await bridge.request(`/api/jobs/${encodeURIComponent(jobId)}`); if (!alive(ticket)) return;
          $('[data-sync-progress]').value = job.progress || 0;
        }
        if (job.state !== 'completed') throw Error(job.error || 'Audio synchronization did not complete.');
        current(); showResult(job.result);
      } catch (error) {
        if (alive(ticket)) status(error.message, true);
        if (submitted?.id) await cancel(submitted.id);
      } finally {if (alive(ticket)) {busy = false; jobId = null; controls();}}
    }
    async function apply() {
      if (busy || applied || measured?.accepted !== true) return;
      const ticket = ++serial; busy = true; controls();
      try {
        current(); status('Verifying the original samples and preparing the synchronized edit…');
        const result = await bridge.request(`/api/projects/${encodeURIComponent(project.id)}/multicam-sync-apply`, {method: 'POST', body: {
          project: clone(project), output_id: measured.output_id, receipt_sha256: measured.artifacts['receipt.json'].sha256,
          name: $('[data-sync-name]').value.trim() || 'Synchronized multicam', start: Math.round(bridge.getFrame?.() || 0), track: 0}});
        if (!alive(ticket)) return; current();
        if (result.project?.id !== project.id) throw Error('The synchronized candidate belongs to another project.');
        const accepted = await bridge.onApply(clone(result.project), clone(context), {action: 'multicam_auto_sync_apply'});
        if (accepted === false) throw Error('The project changed before the synchronized cut could be applied.');
        if (!alive(ticket)) return;
        project = clone(bridge.getProject()); context = clone(bridge.getContext()); applied = true;
        status('Synchronized cut created. Undo restores the previous edit; Save commits it.');
      } catch (error) {if (alive(ticket)) status(error.message, true);}
      finally {if (alive(ticket)) {busy = false; controls();}}
    }
    function close() {
      const pending = jobId; serial++; jobId = null; busy = false;
      if (dialog.open) dialog.close(); void cancel(pending);
    }
    async function open() {
      close(); const ticket = ++serial;
      project = clone(bridge.getProject()); context = clone(bridge.getContext()); capability = null;
      sourceTable(); clearMeasurement(); status('Checking the actual sample-correlation runtime…'); dialog.showModal();
      try {
        const result = await bridge.request('/api/multicam-sync-capabilities');
        if (!alive(ticket)) return; current(); capability = result;
        status(result.available ? 'Select cameras containing at least four seconds of distinct common sound.' : result.reason || 'The sample-correlation runtime is unavailable.', !result.available);
      } catch (error) {if (alive(ticket)) status(error.message, true);}
      finally {if (alive(ticket)) controls();}
    }
    $('[data-sync-analyze]').addEventListener('click', analyze);
    $('[data-sync-apply]').addEventListener('click', apply);
    $('[data-sync-close]').addEventListener('click', close);
    $('[data-sync-cancel]').addEventListener('click', () => {if (jobId) {status('Cancellation requested; waiting for the owned audio process to stop…'); void cancel(jobId);}});
    dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    dialog.addEventListener('keydown', event => event.stopPropagation());
    dialog.addEventListener('change', event => {
      if (busy || event.target.matches('[data-sync-name]')) return;
      const row = event.target.closest('[data-sync-source]');
      if (event.target.matches('[data-sync-stream]') && row) {
        const asset = project.assets.find(item => item.id === row.dataset.syncSource), stream = asset.audio_streams.find(item => item.index === Number(event.target.value));
        const channel = row.querySelector('[data-sync-channel]'); channel.max = Math.max(0, (stream?.channels || 1) - 1); channel.value = Math.min(Number(channel.value) || 0, Number(channel.max));
      }
      if (event.target.matches('[data-sync-use]')) references();
      clearMeasurement(); status('Settings changed. Measure the selected sound windows before creating a cut.');
    });
    return {open, close, reset: close, destroy() {close(); disposed = true; dialog.remove();}};
  }
  window.CinematicumMulticamSync = {mount};
})();

// Async-function body for NativeSmoke.swift. Real installed editors only.
// Arguments: editorID, expectedProjectID, deadlineMilliseconds.
// This checks the embedded display transport, not editing/export feature parity.
return await (async () => {
  const began = performance.now();
  const deadline = began + deadlineMilliseconds;
  const steps = [];
  const $ = selector => document.querySelector(selector);
  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const redact = value => String(value || '')
    .replace(/\/native\/[A-Za-z0-9_-]+\//g, '/native/<session>/')
    .replace(/([?&](?:password|token|secret|auth)=)[^&\s"'<>]*/gi, '$1<redacted>')
    .replace(/\b((?:password|token|secret|auth)\s*[:=]\s*)["']?[^\s,"'<>]+/gi, '$1<redacted>')
    .replace(/\b((?:https?|wss?):\/\/[^\s?"'<>]+)\?[^\s"'<>]*/gi, '$1?<redacted>')
    .slice(0, 1400);
  async function until(predicate, label, limit = deadlineMilliseconds) {
    const end = Math.min(deadline, performance.now() + limit);
    while (performance.now() < end) {
      if (predicate()) return;
      await sleep(40);
    }
    throw new Error(label);
  }
  const mark = step => steps.push({step, elapsed_ms: Math.round(performance.now() - began)});
  function readObservation() {
    const frame = $('.native-editor-frame');
    if (!frame?.hasAttribute('src')) return {available: false};
    const url = new URL(frame.src, location.href);
    if (url.origin !== location.origin || !/^\/native\/[A-Za-z0-9_-]+\/(?:index\.html)?$/.test(url.pathname)) {
      throw new Error('Native viewer navigated outside the authorized same-origin proxy.');
    }
    try {
      const observation = frame.contentWindow.__cinematicumNativeQA;
      if (!observation) return {available: false, same_origin: true};
      return {available: true, same_origin: true,
        connected: observation.connected === true,
        native_window_count: Number(observation.native_window_count || 0),
        decoded_paints: Number(observation.decoded_paints || 0),
        decode_errors: Number(observation.decode_errors || 0),
        decoded_pixels: Number(observation.decoded_pixels || 0),
        direct_socket_open: Number(observation.direct_socket_open || 0),
        direct_socket_messages: Number(observation.direct_socket_messages || 0),
        direct_socket_bytes: Number(observation.direct_socket_bytes || 0),
        websocket_origin_valid: observation.websocket_origin_valid !== false,
        protocol_worker: observation.protocol_worker === true,
        audio_enabled: observation.audio_enabled === true,
        audio_state: redact(observation.audio_state || ''),
        audio_codec: redact(observation.audio_codec || ''),
        last_decode_error: redact(observation.last_decode_error || ''),
      };
    } catch (error) {
      throw new Error('Native iframe cannot be inspected through the same-origin proxy.');
    }
  }
  function viewport() {
    const frame = $('.native-editor-frame');
    if (!frame?.contentDocument) return null;
    const outer = frame.getBoundingClientRect();
    const candidates = [...frame.contentDocument.querySelectorAll('canvas')]
      .map(canvas => ({canvas, bounds: canvas.getBoundingClientRect()}))
      .filter(item => item.canvas.width >= 200 && item.canvas.height >= 100 &&
        item.bounds.width >= 200 && item.bounds.height >= 100)
      .sort((a, b) => b.bounds.width * b.bounds.height - a.bounds.width * a.bounds.height);
    if (!candidates.length) return null;
    const bounds = candidates[0].bounds;
    const left = Math.max(0, outer.left, outer.left + bounds.left);
    const top = Math.max(0, outer.top, outer.top + bounds.top);
    const right = Math.min(innerWidth, outer.right, outer.left + bounds.right);
    const bottom = Math.min(innerHeight, outer.bottom, outer.top + bounds.bottom);
    if (right - left < 200 || bottom - top < 100) return null;
    return {x: left, y: top, width: right - left, height: bottom - top,
      canvas_width: candidates[0].canvas.width, canvas_height: candidates[0].canvas.height};
  }
  try {
    await until(() => $('#project-select')?.value && window.cinematicumNativeEditors,
      'CINEMATICUM did not bootstrap its project and native workspace module.', 3500);
    if (expectedProjectID && $('#project-select').value !== expectedProjectID) {
      const select = $('#project-select');
      if (![...select.options].some(option => option.value === expectedProjectID)) {
        throw new Error('The requested ENGINE_TEST project is not listed in this workspace.');
      }
      select.value = expectedProjectID;
      select.dispatchEvent(new Event('change', {bubbles: true}));
      await until(() => !select.disabled && window.cinematicumNativeEditors.getProject()?.id === expectedProjectID,
        'The requested test project did not finish opening.', 2500);
    }
    const project = window.cinematicumNativeEditors.getProject();
    if (!project || !/^ENGINE[ _]TEST(?:\b|_)/.test(project.name || '')) {
      throw new Error('Refusing to operate a non-ENGINE_TEST project. Prepare a dedicated test project first.');
    }
    const projectID = project.id;
    mark('bootstrap_dedicated_test_project');

    const nativeButton = $('#native-workspace-button');
    const tab = $(`.native-editor-tab[data-editor="${editorID}"]`);
    if (!nativeButton || nativeButton.disabled || !tab || tab.disabled) {
      throw new Error('Requested native editor control is unavailable.');
    }
    // Click the specific real editor tab even when the mount begins hidden.
    // This avoids unnecessarily launching Kdenlive before another requested editor.
    tab.click();
    await until(() => {
      const error = $('.native-editor-activity.native-editor-error');
      if (error && error.textContent.trim()) throw new Error(redact(error.textContent));
      return tab.getAttribute('aria-pressed') === 'true' &&
        !window.cinematicumNativeEditors.opening &&
        window.cinematicumNativeEditors.viewerProject === projectID &&
        $('.native-editor-frame')?.hasAttribute('src');
    }, 'The actual native editor did not open through the application.');
    mark('native_editor_open_completed');

    await until(() => {
      const observed = readObservation();
      if (observed.websocket_origin_valid === false) throw new Error('Editor WebSocket attempted a foreign endpoint.');
      return observed.connected && observed.native_window_count > 0 && observed.decoded_paints > 0 && viewport();
    }, 'Xpra did not complete its real connection, decoded paint, and canvas display.');
    mark('xpra_handshake_and_decoded_native_paint');

    // Let the acknowledged paint reach the compositor before taking a snapshot.
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const observed = readObservation();
    const rect = viewport();
    if (!rect || !observed.connected || observed.native_window_count < 1 || observed.decoded_paints < 1) {
      throw new Error('The native display disconnected before screenshot capture.');
    }
    if (window.cinematicumNativeEditors.getProject()?.id !== projectID) {
      throw new Error('The test project changed during verification.');
    }
    mark('visible_native_canvas');
    return {passed: true, scope: 'native_editor_gui_transport_only', editor: editorID,
      project_id: projectID, steps, transport: observed, viewport: rect,
      note: 'No authoring, save/reopen, export, audio playback, or full-feature parity assertion is made by this transport test.',
      elapsed_ms: Math.round(performance.now() - began)};
  } catch (error) {
    let observed = {};
    try { observed = readObservation(); } catch (_) {}
    return {passed: false, scope: 'native_editor_gui_transport_only', editor: editorID,
      steps, error: redact(error?.message || error), transport: observed,
      activity: redact($('.native-editor-activity')?.textContent),
      elapsed_ms: Math.round(performance.now() - began)};
  }
})();

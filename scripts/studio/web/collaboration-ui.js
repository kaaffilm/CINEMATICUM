/* Explicit pairing and concurrent edits through the private Studio bridge.
   Credentials stay on the local server; invitations are shown only on request. */
(() => {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  function mount(host, bridge) {
    const dialog = document.createElement('dialog');
    dialog.id = 'collaboration-dialog';
    dialog.className = 'cinematicum-collaboration';
    dialog.innerHTML = `<style>
      .cinematicum-collaboration{box-sizing:border-box;width:min(800px,95vw);max-height:92vh;padding:0;background:#151d26;color:#e5edf6;border:1px solid #53677b;border-radius:12px;font:13px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;overflow:auto}.cinematicum-collaboration::backdrop{background:#060c13bd}.cinematicum-collaboration header,.cinematicum-collaboration footer{padding:17px 21px;background:#202e3c;display:flex;gap:12px;align-items:center}.cinematicum-collaboration header>div,.cinematicum-collaboration footer>div{flex:1}.cinematicum-collaboration h2,.cinematicum-collaboration h3,.cinematicum-collaboration p{margin:0}.cinematicum-collaboration h2{font-size:18px}.cinematicum-collaboration h3{font-size:14px}.cinematicum-collaboration .collab-body{padding:21px;display:grid;gap:22px}.cinematicum-collaboration section{display:grid;gap:11px}.cinematicum-collaboration .collab-row{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.cinematicum-collaboration label{display:grid;gap:5px;flex:1;min-width:140px}.cinematicum-collaboration input,.cinematicum-collaboration textarea,.cinematicum-collaboration select{box-sizing:border-box;width:100%;padding:8px;background:#0d1720;color:#edf6ff;border:1px solid #435c72;border-radius:5px;font:inherit}.cinematicum-collaboration textarea{resize:vertical;min-height:110px;font:12px/1.45 ui-monospace,monospace}.cinematicum-collaboration button{font:inherit;color:#e9f3fc;background:#304c63;border:1px solid #63829c;border-radius:5px;padding:7px 11px;cursor:pointer}.cinematicum-collaboration button:disabled{opacity:.45;cursor:default}.cinematicum-collaboration .collab-note{color:#a9bacb;font-size:12px}.cinematicum-collaboration .collab-status{overflow-wrap:anywhere}.cinematicum-collaboration .collab-status.error{color:#ffb3a5}.cinematicum-collaboration code{overflow-wrap:anywhere;white-space:normal}.cinematicum-collaboration .collab-conflict{border:1px solid #b97b57;background:#392a25;border-radius:7px;padding:14px}.cinematicum-collaboration .collab-conflict ul{margin:0;padding-left:20px;max-height:150px;overflow:auto}.cinematicum-collaboration .collab-members{display:grid;gap:6px}.cinematicum-collaboration .collab-member{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #34485a}.cinematicum-collaboration .collab-member span{flex:1}.cinematicum-collaboration [hidden]{display:none!important}.cinematicum-collaboration .collab-primary{background:#205e6e;border-color:#66a9b9}
    </style>
    <header><div><h2>Shared editing</h2><p class="collab-note">Paired TLS connection · durable project history · verified media</p></div><button type="button" data-collab-close>Close</button></header>
    <div class="collab-body">
      <section data-collab-session hidden><h3 data-collab-heading></h3><p data-collab-session-summary></p><p class="collab-note">Coordinator: <code data-collab-url></code></p><p class="collab-note">Paired certificate SHA-256: <code data-collab-fingerprint></code></p><div class="collab-row"><button type="button" data-collab-sync>Sync now</button><button type="button" data-collab-resume hidden>Resume host · retain open draft in recovery</button><button type="button" data-collab-invite hidden>Create one-use invitation</button><button type="button" data-collab-leave>Leave shared session</button></div><p class="collab-note">Saved edits merge by entity and property. A competing change to the same property pauses publishing for your choice. Automatic saves and incoming updates pause while the editor is busy. Resuming a stopped host retains any open draft in recovery before showing its shared state.</p></section>
      <section data-collab-unbound><h3>Start sharing this project</h3><div class="collab-row"><label>Your name<input data-collab-owner-name value="Owner" maxlength="100"></label><label>Listen on IPv4 address<input data-collab-host value="127.0.0.1" spellcheck="false"></label><label>Port · 0 selects an available port<input data-collab-port type="number" min="0" max="65535" step="1" value="0"></label></div><label>Advertised hostname or IP · optional<input data-collab-advertise placeholder="Required when listening on 0.0.0.0" spellcheck="false"></label><p class="collab-note">127.0.0.1 pairs clients on this computer. To pair a reachable peer, explicitly choose the host interface and advertised address. Keep the host application open. Only this separate TLS service is shared; the Studio file server stays local.</p><div><button type="button" data-collab-create class="collab-primary">Start shared session</button></div></section>
      <section data-collab-join-section><h3>Join an invited project</h3><label>Your name<input data-collab-peer-name value="Editor" maxlength="100"></label><label>Invitation JSON<textarea data-collab-invitation-input spellcheck="false" placeholder="Paste the host's one-use invitation"></textarea></label><p class="collab-note">Pair only an invitation from the intended host. Its certificate pins that coordinator’s identity. Joining downloads and verifies the project’s media into a new local project.</p><div><button type="button" data-collab-join>Join and open project</button></div></section>
      <section data-collab-invitation hidden><h3>One-use invitation</h3><p data-collab-invitation-expiry></p><textarea data-collab-invitation-output readonly spellcheck="false" aria-label="One-use pairing invitation"></textarea><div><button type="button" data-collab-copy>Copy invitation</button><button type="button" data-collab-hide-invitation>Hide invitation</button></div><p class="collab-note">Share this invitation directly with the intended participant. It expires and can be used once. It is not sent automatically.</p></section>
      <section data-collab-conflict class="collab-conflict" role="alert" hidden><h3>Publishing is paused; your draft is retained</h3><p data-collab-conflict-message></p><ul data-collab-conflict-paths></ul><p class="collab-note">You can edit the draft and retry. “Use latest shared version” first preserves a durable recovery checkpoint, then replaces the displayed draft. “Keep draft locally” disconnects this local project and saves the draft without changing the shared project.</p><div class="collab-row"><button type="button" data-collab-retry>Retry current draft</button><button type="button" data-collab-use-shared>Use latest shared version</button><button type="button" data-collab-keep-local>Keep draft locally</button></div></section>
      <section data-collab-history hidden><h3>Undo one of your committed edits</h3><div class="collab-row"><label>Your shared edit history<select data-collab-events></select></label><button type="button" data-collab-undo>Undo selected edit</button></div><p class="collab-note">Selective undo preserves other participants’ changes. If a later edit changed the same property, undo asks for a conflict decision. Other participants’ events cannot be undone here.</p></section>
      <section data-collab-members-section hidden><div class="collab-row"><h3>Participants</h3><button type="button" data-collab-refresh-members>Refresh participants</button></div><div class="collab-members" data-collab-members></div></section>
    </div><footer><div><p class="collab-status" data-collab-status role="status" aria-live="polite"></p></div></footer>`;
    host.append(dialog);
    const $ = selector => dialog.querySelector(selector);
    let projectId = null, session = null, blocked = null, busy = false, disposed = false, epoch = 0;
    let pollTimer = null, saveTimer = null, statusTask = null, lastSync = null;
    const contextId = () => bridge.getContext()?.projectId || bridge.getProject()?.id;
    const current = ticket => !disposed && ticket === epoch && projectId === contextId();
    const path = action => `/api/projects/${encodeURIComponent(projectId)}/collaboration${action ? '-' + action : ''}`;
    const status = (message, error = false) => { $('[data-collab-status]').textContent = message; $('[data-collab-status]').classList.toggle('error', error); };
    function clearTimers() {clearTimeout(pollTimer); clearTimeout(saveTimer); pollTimer = saveTimer = null;}
    function controls() {
      const active = Boolean(session?.active), hostStopped = active && session.owner && !session.host_running;
      for (const element of dialog.querySelectorAll('button,input,textarea,select')) element.disabled = busy || (session === null && !element.hasAttribute('data-collab-close'));
      $('[data-collab-session]').hidden = !active;
      $('[data-collab-unbound]').hidden = active;
      $('[data-collab-join-section]').hidden = active;
      $('[data-collab-history]').hidden = !active;
      $('[data-collab-members-section]').hidden = !active;
      $('[data-collab-resume]').hidden = !hostStopped;
      $('[data-collab-invite]').hidden = !active || !session.owner;
      $('[data-collab-invite]').disabled = busy || hostStopped || !!session?.pending_operation;
      $('[data-collab-undo]').disabled = busy || hostStopped || !!blocked || !session?.own_events?.length || !!bridge.isDirty();
      $('[data-collab-sync]').disabled = busy || hostStopped;
      $('[data-collab-use-shared]').disabled = busy || !bridge.discardDraftAndSync;
      $('[data-collab-conflict]').hidden = !blocked;
      if (active) {
        $('[data-collab-heading]').textContent = session.owner ? (hostStopped ? 'Shared host is stopped' : 'You host this shared project') : 'Connected shared project';
        $('[data-collab-session-summary]').textContent = `Shared revision ${session.shared_revision}${session.pending_operation ? ' · an operation is awaiting recovery' : ''}${lastSync ? ' · last synchronized ' + lastSync.toLocaleTimeString() : ''}`;
        $('[data-collab-url]').textContent = session.url || '';
        $('[data-collab-fingerprint]').textContent = session.certificate_sha256 || 'Available in the explicit pairing invitation';
        $('[data-collab-leave]').textContent = session.owner ? 'Stop hosting and keep local project' : 'Leave and keep local project';
        const selected = $('[data-collab-events]').value;
        $('[data-collab-events]').replaceChildren();
        for (const id of [...(session.own_events || [])].reverse()) {
          const option = document.createElement('option'); option.value = id; option.textContent = `Edit ${id}`;
          $('[data-collab-events]').append(option);
        }
        if ((session.own_events || []).includes(selected)) $('[data-collab-events]').value = selected;
      }
      if (blocked) {
        $('[data-collab-conflict-message]').textContent = blocked.message || 'The shared operation needs your attention.';
        const list = $('[data-collab-conflict-paths]'); list.replaceChildren();
        for (const item of blocked.conflicts || blocked.details?.conflicts || []) {
          const li = document.createElement('li'); li.textContent = `${item.path}: ${String(item.reason || 'conflicting change').replaceAll('_', ' ')}`; list.append(li);
        }
        const validation = blocked.validation_error || blocked.details?.validation_error;
        if (validation) {const li = document.createElement('li'); li.textContent = validation; list.append(li);}
      }
    }
    function failed(error) {
      if (disposed || !session?.active) return;
      blocked = error; clearTimers(); controls(); status(error.message || String(error), true);
      bridge.notify?.('Shared publishing paused. Your local draft is retained; open Shared editing to review.', true);
    }
    async function refreshStatus(ticket = epoch) {
      if (!projectId || disposed) return;
      if (statusTask) return statusTask;
      const task = (async () => {
        const value = await bridge.request(path(''));
        if (!current(ticket)) return;
        session = value; controls();
        if (session.active && !blocked) {if (bridge.isDirty()) changed(); else schedulePoll();}
        return value;
      })();
      statusTask = task;
      try {return await task;} finally {if (statusTask === task) statusTask = null;}
    }
    function schedulePoll(delay = 2000) {
      clearTimeout(pollTimer);
      if (disposed || !session?.active || blocked || (session.owner && !session.host_running)) return;
      pollTimer = setTimeout(async () => {
        if (disposed || blocked || !session?.active) return;
        if (busy || bridge.isBusy() || bridge.isDirty()) {schedulePoll(); return;}
        const ticket = epoch;
        busy = true; controls();
        try {
          if (!bridge.sync) throw Error('The editor does not provide an atomic shared synchronization bridge.');
          const response = await bridge.sync();
          if (current(ticket)) {session = response.status; lastSync = new Date(); status(`Shared revision ${session.shared_revision} synchronized.`);}
        } catch (error) {if (current(ticket)) failed(error);}
        finally {if (current(ticket)) {busy = false; controls(); schedulePoll();}}
      }, delay);
    }
    function changed() {
      clearTimeout(saveTimer);
      if (disposed || !session?.active || blocked || (session.owner && !session.host_running)) return;
      saveTimer = setTimeout(async () => {
        if (disposed || blocked || !session?.active || (session.owner && !session.host_running) || !bridge.isDirty()) return;
        if (busy || bridge.isBusy()) {changed(); return;}
        const ticket = epoch; busy = true; controls();
        try {await bridge.saveProject(); if (current(ticket)) {await refreshStatus(ticket); lastSync = new Date(); status('Your edit is saved in the shared project.');}}
        catch (error) {if (current(ticket)) failed(error);}
        finally {if (current(ticket)) {busy = false; controls(); if (!blocked && bridge.isDirty()) changed(); else schedulePoll();}}
      }, 700);
    }
    function saved(error) {
      if (error) {failed(error); return;}
      if (disposed || !session?.active) return;
      if (!bridge.isDirty()) blocked = null;
      const ticket = epoch;
      refreshStatus(ticket).then(() => {if (current(ticket)) {controls(); if (bridge.isDirty()) changed(); else schedulePoll();}}).catch(error => {if (current(ticket)) failed(error);});
    }
    async function action(callback, success, options = {}) {
      if (busy || bridge.isBusy()) {status('Wait for the current editor operation to finish.'); return;}
      const ticket = epoch; busy = true; clearTimers(); controls();
      try {
        if (!options.keepDraft && bridge.isDirty()) await bridge.saveProject();
        if (!current(ticket)) return;
        const response = await callback();
        if (!current(ticket)) return;
        if (response?.status) session = response.status;
        if (response?.project && !options.adopted && !options.keepDraft) await bridge.adoptRemote(response.project);
        if (!current(ticket) && projectId !== contextId()) return;
        blocked = null; lastSync = new Date(); status(success); controls();
        return response;
      } catch (error) {if (current(ticket)) {try {await refreshStatus(ticket);} catch {} if (current(ticket)) {if (session?.active) failed(error); else status(error.message || String(error), true);}} return null;}
      finally {if (current(ticket)) {busy = false; controls(); schedulePoll();}}
    }
    async function loadMembers() {
      if (!session?.active || (session.owner && !session.host_running)) return;
      const ticket = epoch;
      const response = await bridge.request(path('members'));
      if (!current(ticket)) return;
      const container = $('[data-collab-members]'); container.replaceChildren();
      for (const member of response.members || []) {
        const row = document.createElement('div'); row.className = 'collab-member';
        const name = document.createElement('span'); name.textContent = `${member.name} · ${member.role}${member.revoked ? ' · revoked' : ''}${member.id === session.participant_id ? ' · you' : ''}`; row.append(name);
        if (session.owner && member.role !== 'owner' && !member.revoked) {
          const revoke = document.createElement('button'); revoke.type = 'button'; revoke.textContent = 'Revoke access';
          revoke.onclick = () => action(async () => {await bridge.request(path('revoke'), {method:'POST', body:{client_id:member.id}}); await loadMembers();}, 'Participant access revoked.');
          row.append(revoke);
        }
        container.append(row);
      }
      controls();
    }
    function reset() {
      epoch++; clearTimers(); projectId = contextId(); session = null; blocked = null; busy = false; lastSync = null; statusTask = null;
      $('[data-collab-invitation]').hidden = true; $('[data-collab-invitation-output]').value = '';
      $('[data-collab-members]').replaceChildren(); status('Reading shared project status…'); controls();
      const ticket = epoch;
      if (projectId) refreshStatus(ticket).then(() => {if (current(ticket)) status(session?.active ? 'Shared project ready.' : 'This project is local. Start or join a shared session explicitly.');}).catch(error => {if (current(ticket)) status(error.message, true);});
    }
    async function open() {
      if (projectId !== contextId()) reset();
      if (!dialog.open) dialog.showModal();
      try {await refreshStatus(); if (session?.active && !(session.owner && !session.host_running)) await loadMembers();}
      catch (error) {status(error.message, true);}
      controls();
    }
    async function undoLatest() {
      await open();
      if (bridge.isDirty()) {status('Save or undo the local draft before selecting a committed shared edit.', true); return;}
      const event = session?.own_events?.at(-1);
      if (!event) {status('There is no committed edit by this participant to undo.'); return;}
      return undoEvent(event);
    }
    async function undoEvent(eventId) {
      return action(() => bridge.request(path('undo'), {method:'POST', body:{event_id:eventId, revision:bridge.getProject().revision}}), 'Your selected edit was undone; other participants’ changes were preserved.');
    }
    $('[data-collab-create]').onclick = () => action(async () => {
      const portText = $('[data-collab-port]').value, port = Number(portText);
      if (!portText.trim() || !Number.isInteger(port) || port < 0 || port > 65535) throw Error('Port must be an integer from 0 to 65535.');
      const body = {name:$('[data-collab-owner-name]').value.trim(), host:$('[data-collab-host]').value.trim(), port};
      if ($('[data-collab-advertise]').value.trim()) body.advertise_host = $('[data-collab-advertise]').value.trim();
      return bridge.request(path('create'), {method:'POST', body});
    }, 'Shared session started. Create an invitation for the intended participant.');
    $('[data-collab-join]').onclick = () => action(async () => {
      const text = $('[data-collab-invitation-input]').value;
      if (text.length > 32768) throw Error('The invitation is too large.');
      let invitation; try {invitation = JSON.parse(text);} catch {throw Error('Paste the complete invitation JSON from the host.');}
      const response = await bridge.request(path('join'), {method:'POST', body:{invitation,name:$('[data-collab-peer-name]').value.trim()}});
      $('[data-collab-invitation-input]').value = '';
      return response;
    }, 'Paired project opened with verified local media.');
    $('[data-collab-resume]').onclick = () => action(() => {
      if (!bridge.resumeShared) throw Error('The editor does not provide a recovery-safe host resume bridge.');
      return bridge.resumeShared();
    }, 'Saved host resumed. Any open draft was retained in recovery.', {keepDraft:true,adopted:true});
    $('[data-collab-sync]').onclick = () => action(() => bridge.sync(), 'Latest shared project synchronized.', {adopted:true});
    $('[data-collab-invite]').onclick = () => action(async () => {
      const response = await bridge.request(path('invite'), {method:'POST',body:{}});
      $('[data-collab-invitation-output]').value = JSON.stringify(response.invitation, null, 2);
      $('[data-collab-invitation-expiry]').textContent = 'Expires ' + new Date(response.invitation.expires_at * 1000).toLocaleString();
      $('[data-collab-invitation]').hidden = false; return response;
    }, 'One invitation is ready for you to share.');
    $('[data-collab-leave]').onclick = () => action(() => bridge.request(path('leave'), {method:'POST',body:{}}), 'Local project retained; shared editing is disconnected.');
    $('[data-collab-retry]').onclick = async () => {
      blocked = null; controls();
      await action(async () => {await bridge.saveProject(); return bridge.sync();}, 'Current draft saved and synchronized.', {keepDraft:true,adopted:true});
    };
    $('[data-collab-use-shared]').onclick = () => action(() => bridge.discardDraftAndSync(), 'Draft preserved in recovery; latest shared project opened.', {keepDraft:true,adopted:true});
    $('[data-collab-keep-local]').onclick = () => action(async () => {
      const response = await bridge.request(path('leave'), {method:'POST',body:{}});
      session = response.status; blocked = null; controls();
      await bridge.saveProject(); return {status:response.status};
    }, 'Your draft is saved as a local project. The shared project was not changed.', {keepDraft:true});
    $('[data-collab-undo]').onclick = () => undoEvent($('[data-collab-events]').value);
    $('[data-collab-refresh-members]').onclick = () => loadMembers().catch(error => status(error.message, true));
    $('[data-collab-copy]').onclick = async () => {
      try {await navigator.clipboard.writeText($('[data-collab-invitation-output]').value); status('Invitation copied.');}
      catch {$('[data-collab-invitation-output]').focus(); $('[data-collab-invitation-output]').select(); status('Invitation selected. Use the system Copy command.');}
    };
    $('[data-collab-hide-invitation]').onclick = () => {$('[data-collab-invitation-output]').value = ''; $('[data-collab-invitation]').hidden = true;};
    $('[data-collab-close]').onclick = () => {if (!busy) dialog.close();};
    dialog.addEventListener('cancel', event => {if (busy) event.preventDefault();});
    dialog.addEventListener('close', () => {$('[data-collab-invitation-output]').value = ''; $('[data-collab-invitation]').hidden = true;});
    reset();
    return {open,reset,changed,saved,failed,undoLatest,isActive:() => session === null ? null : !!session.active,
      getStatus:() => session === null ? null : clone(session),close:() => {if (!busy) dialog.close();},
      destroy:() => {disposed=true;epoch++;clearTimers();dialog.remove();}};
  }
  window.CinematicumCollaboration = {mount};
})();

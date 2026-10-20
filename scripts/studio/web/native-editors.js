/* Full native editing workspaces. The streamed editors own their documents. */
(() => {
  'use strict';

  const EDITORS = Object.freeze([
    {id: 'kdenlive', name: 'Kdenlive', purpose: 'Editing'},
    {id: 'shotcut', name: 'Shotcut', purpose: 'Editing'},
    {id: 'cinelerra', name: 'Cinelerra-GG', purpose: 'Editing & audio'},
    {id: 'natron', name: 'Natron', purpose: 'Compositing'},
    {id: 'friction', name: 'Friction', purpose: 'Motion graphics'},
    {id: 'glaxnimate', name: 'Glaxnimate', purpose: 'Vector animation'},
    {id: 'blender', name: 'Blender', purpose: '3D & VFX'},
  ]);
  const SUCCESS = new Set(['completed', 'complete', 'succeeded', 'success', 'done']);
  const FAILURE = new Set(['failed', 'error', 'cancelled', 'canceled', 'interrupted']);
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (className, text, action) => {
    const node = element('button', className, text);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  };

  class NativeEditors {
    constructor({request, getProject, onAssembly, onProjectUpdate, notify,
                 onProjectFiles, mount}) {
      if (typeof request !== 'function' || typeof getProject !== 'function' || !mount) {
        throw new TypeError('NativeEditors needs request, getProject, and a mount element.');
      }
      this.request = request;
      this.getProject = getProject;
      this.onAssembly = onAssembly || (() => {});
      this.onProjectUpdate = onProjectUpdate || (() => {});
      this.notify = notify || (() => {});
      this.onProjectFiles = onProjectFiles;
      this.mount = mount;
      this.visible = false;
      this.destroyed = false;
      this.status = null;
      this.selected = 'kdenlive';
      this.desired = null;
      this.opening = false;
      this.installing = false;
      this.importing = false;
      this.viewerProject = null;
      this.viewerLoaded = false;
      this.statusSerial = 0;
      this.refreshTimer = null;
      this.lastFailedAction = null;
      this.attemptedEditor = null;
      this._build();
    }

    _build() {
      this.mount.classList.add('native-editor-mount');
      this.root = element('section', 'native-editors');
      this.root.setAttribute('aria-label', 'Native editing workspaces');
      this.root.hidden = true;
      this.toolbar = element('div', 'native-editors-toolbar');
      this.tabs = element('nav', 'native-editor-tabs');
      this.tabs.setAttribute('aria-label', 'Choose native editor');
      this.tabButtons = new Map();
      for (const editor of EDITORS) {
        const tab = button('native-editor-tab', '', () => this.show(editor.id));
        tab.dataset.editor = editor.id;
        tab.title = `${editor.name} · ${editor.purpose}`;
        tab.setAttribute('aria-pressed', 'false');
        const dot = element('span', 'native-editor-dot');
        dot.setAttribute('aria-hidden', 'true');
        tab.append(dot, element('span', '', editor.name));
        this.tabButtons.set(editor.id, tab);
        this.tabs.append(tab);
      }
      this.assemblyButton = button('native-assembly-button', 'Assembly', () => {
        this.hide();
        this.onAssembly();
      });
      this.assemblyButton.title = 'Return to the CINEMATICUM assembly timeline';
      this.toolbar.append(this.tabs, this.assemblyButton);

      this.context = element('div', 'native-editor-context');
      this.projectLabel = element('span', 'native-project-name');
      this.runtimeLabel = element('span', 'native-runtime-label', 'Linux · CPU rendering');
      this.filesButton = button('native-context-button', 'Project files', () => this._projectFiles());
      this.filesButton.hidden = typeof this.onProjectFiles !== 'function';
      this.importButton = button('native-context-button', 'Import exports', () => this.importExports());
      this.importButton.title = 'Copy finished media from this native project’s exports folder into the assembly media bin';
      this.context.append(this.projectLabel, this.runtimeLabel, this.filesButton, this.importButton);

      this.stage = element('div', 'native-editor-stage');
      this.frame = element('iframe', 'native-editor-frame');
      this.frame.title = 'Native audiovisual editor';
      this.frame.setAttribute('allow', 'autoplay; fullscreen; clipboard-read; clipboard-write');
      this.frame.setAttribute('referrerpolicy', 'no-referrer');
      this.frame.setAttribute('allowfullscreen', '');
      this.frame.hidden = true;
      this.frame.addEventListener('load', () => {
        if (!this.frame.hasAttribute('src')) return;
        this.viewerLoaded = true;
        this.frame.hidden = false;
        if (!this.opening && !this.installing && !this.lastFailedAction) this.notice.hidden = true;
      });
      this.frame.addEventListener('error', () => {
        this._error(new Error('The editor connection could not be opened. Reconnect to the existing workspace.'), 'reconnect');
      });

      this.notice = element('div', 'native-editor-notice');
      this.noticeInner = element('div', 'native-editor-notice-inner');
      this.noticeTitle = element('h2', '', 'Opening editing workspace');
      this.noticeText = element('p', '');
      this.progress = element('progress', 'native-editor-progress');
      this.progress.max = 1;
      this.progress.setAttribute('aria-label', 'Preparing editing workspace');
      this.noticeActions = element('div', 'native-editor-notice-actions');
      this.installButton = button('native-install-button', 'Install editors', () => this.install());
      this.retryButton = button('native-retry-button', 'Retry', () => this._retry());
      this.noticeAssembly = button('native-context-button', 'Open assembly', () => {
        this.hide();
        this.onAssembly();
      });
      this.noticeActions.append(this.installButton, this.retryButton, this.noticeAssembly);
      this.noticeInner.append(this.noticeTitle, this.noticeText, this.progress, this.noticeActions);
      this.notice.append(this.noticeInner);
      this.stage.append(this.frame, this.notice);

      this.footer = element('div', 'native-editor-footer');
      this.activity = element('span', 'native-editor-activity', '');
      this.activity.setAttribute('role', 'status');
      this.activity.setAttribute('aria-live', 'polite');
      this.documentHint = element('span', 'native-editor-document-hint', 'Save editable projects in the native editor');
      this.reconnectButton = button('native-context-button', 'Reconnect', () => this.reconnect());
      this.reconnectButton.title = 'Reconnect the viewer without closing native editors';
      this.reconnectButton.hidden = true;
      this.footer.append(this.activity, this.documentHint, this.reconnectButton);
      this.root.append(this.toolbar, this.context, this.stage, this.footer);
      this.mount.append(this.root);
      this._setNotice('Opening editing workspace', '', {busy: true});
      this._updateProject();
    }

    _project() {
      const project = this.getProject();
      if (!project || typeof project.id !== 'string' || !/^[a-f0-9]{32}$/.test(project.id)) {
        throw new Error('Open or create a project first.');
      }
      return project;
    }

    _updateProject() {
      const project = this.getProject();
      if (this.viewerProject && this.viewerProject !== project?.id) {
        // A different project's editor must never remain interactive under the
        // new project label. Disconnect its viewer, preserving native processes.
        this.frame.removeAttribute('src');
        this.frame.hidden = true;
        this.viewerProject = null;
        this.viewerLoaded = false;
        this.reconnectButton.hidden = true;
      }
      this.projectLabel.textContent = project?.name || 'No project open';
      this.projectLabel.title = project?.name || '';
      this.importButton.disabled = this.importing || !this.status?.installed || !project;
    }

    _setNotice(title, detail, {busy = false, install = false, retry = false, overlay = false} = {}) {
      this.noticeTitle.textContent = title;
      this.noticeText.textContent = detail || '';
      this.noticeText.hidden = !detail;
      this.notice.hidden = false;
      this.notice.classList.toggle('native-editor-notice-overlay', overlay && this.viewerLoaded);
      this.progress.hidden = !busy;
      this.progress.removeAttribute('value');
      this.installButton.hidden = !install;
      this.retryButton.hidden = !retry;
      this.noticeAssembly.hidden = overlay && this.viewerLoaded;
      this.root.setAttribute('aria-busy', String(busy));
    }

    _error(error, action = 'open') {
      const message = error?.message || String(error);
      this.lastFailedAction = action;
      this.activity.textContent = message;
      this.activity.classList.add('native-editor-error');
      this._setNotice(action === 'install' ? 'Editor installation stopped' : 'Workspace needs attention',
        message, {retry: true, overlay: true});
      this.root.removeAttribute('aria-busy');
      this.notify(message, true);
    }

    async refreshStatus() {
      const serial = ++this.statusSerial;
      const response = await this.request('/api/native');
      if (this.destroyed || serial !== this.statusSerial) return this.status;
      this.status = response.runtime || response;
      for (const [id, tab] of this.tabButtons) {
        const editor = (this.status.editors || []).find(item => item.id === id);
        const running = editor?.running === true || editor?.state === 'running';
        tab.classList.toggle('native-editor-running', running);
        tab.classList.toggle('native-editor-unavailable', editor?.available === false);
      }
      this._updateProject();
      return this.status;
    }

    async show(editor = this.selected || 'kdenlive') {
      if (this.destroyed) return;
      if (!this.tabButtons.has(editor)) throw new Error('Unknown editing workspace.');
      this.visible = true;
      this.root.hidden = false;
      this.mount.hidden = false;
      this.mount.closest('.app')?.classList.add('native-active');
      this._updateProject();
      this.desired = {editor, projectId: this.getProject()?.id};
      if (this.opening || this.installing) return;
      try {
        this._project();
        const status = await this.refreshStatus();
        if (!this.visible || this.destroyed || !status) return;
        if (!status.installed) {
          this.activity.textContent = status.building ? 'Preparing native editors' : 'Native editors are not installed';
          this._setNotice(status.building ? 'Preparing native editors' : 'Install native editing workspaces',
            status.error || (status.available === false
              ? 'Start Docker Desktop, then retry. Your existing projects remain available in Assembly.'
              : 'Install the complete Linux editors. Native project files and finished exports stay in this project.'),
            {busy: Boolean(status.building), install: status.available !== false && !status.building,
              retry: status.available === false});
          if (status.building) this._watchInstallation();
          return;
        }
        await this._openDesired();
      } catch (error) {
        if (!this.destroyed) this._error(error);
      }
    }

    hide() {
      this.visible = false;
      this.root.hidden = true;
      this.mount.hidden = true;
      this.mount.closest('.app')?.classList.remove('native-active');
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
      // Retain the connection and native documents. Hiding never closes an editor.
    }

    async _openDesired() {
      if (this.opening || this.installing || !this.desired || this.destroyed) return;
      const wanted = this.desired;
      const project = this._project();
      if (project.id !== wanted.projectId) return;
      this.desired = null;
      this.opening = true;
      const editor = EDITORS.find(item => item.id === wanted.editor);
      this.attemptedEditor = editor.id;
      this.activity.classList.remove('native-editor-error');
      this.activity.textContent = `Opening ${editor.name}`;
      this._setNotice(`Opening ${editor.name}`, '', {busy: true, overlay: true});
      for (const [id, tab] of this.tabButtons) tab.classList.toggle('native-editor-pending', id === editor.id);
      try {
        const response = await this.request(`/api/projects/${encodeURIComponent(project.id)}/native/open`, {
          method: 'POST', body: {editor: editor.id},
        });
        await this._followJob(response, `Opening ${editor.name}`);
        if (this.destroyed || this.getProject()?.id !== project.id) return;
        if (this.viewerProject !== project.id || !this.frame.hasAttribute('src')) await this._connect(project.id);
        if (this.destroyed || this.getProject()?.id !== project.id) return;
        this.selected = editor.id;
        for (const [id, tab] of this.tabButtons) {
          const selected = id === editor.id;
          tab.classList.toggle('native-editor-selected', selected);
          tab.setAttribute('aria-pressed', String(selected));
        }
        this.frame.title = `${editor.name} — ${project.name || 'CINEMATICUM project'}`;
        this.activity.textContent = `${editor.name} · ${editor.purpose}`;
        this.notice.hidden = true;
        this.reconnectButton.hidden = false;
        this.lastFailedAction = null;
      } catch (error) {
        if (!this.destroyed && this.getProject()?.id === project.id) this._error(error);
      } finally {
        this.opening = false;
        this.root.removeAttribute('aria-busy');
        for (const tab of this.tabButtons.values()) tab.classList.remove('native-editor-pending');
        if (this.desired && this.visible && !this.destroyed) this._openDesired().catch(error => this._error(error));
      }
    }

    async _connect(projectId, force = false) {
      if (!force && this.viewerProject === projectId && this.frame.hasAttribute('src')) return;
      const access = await this.request(`/api/projects/${encodeURIComponent(projectId)}/native/access`, {
        method: 'POST', body: {},
      });
      if (this.destroyed || this.getProject()?.id !== projectId) return;
      const raw = access.viewer_url;
      if (typeof raw !== 'string' || !raw.startsWith('/native/')) {
        throw new Error('The server did not return an authorized local editor connection.');
      }
      const url = new URL(raw, window.location.href);
      if (url.origin !== window.location.origin || url.username || url.password ||
          !/^\/native\/[A-Za-z0-9_-]+\/(?:index\.html)?$/.test(url.pathname)) {
        throw new Error('The server returned an invalid editor connection.');
      }
      this.viewerLoaded = false;
      this.viewerProject = projectId;
      this.frame.hidden = false;
      this.frame.src = url.href;
      // Do not write access URLs or credentials to storage, job state, or logs.
    }

    async reconnect() {
      if (this.opening || this.installing || this.destroyed) return;
      try {
        const project = this._project();
        this._setNotice('Reconnecting to the editor', '', {busy: true, overlay: true});
        await this._connect(project.id, true);
        this.notice.hidden = true;
        this.activity.classList.remove('native-editor-error');
        this.activity.textContent = 'Editor connection reopened';
      } catch (error) {
        this._error(error, 'reconnect');
      } finally {
        this.root.removeAttribute('aria-busy');
      }
    }

    async _followJob(response, label) {
      let job = response.job || response;
      if (!job.id && !job.job_id) {
        if (job.runtime_ready === true || job.installed === true) return job;
        throw new Error('The server returned no operation identifier.');
      }
      const id = job.id || job.job_id;
      let failures = 0;
      while (!this.destroyed) {
        const phase = String(job.state || job.status || 'queued').toLowerCase();
        if (SUCCESS.has(phase)) return job.result || {};
        if (FAILURE.has(phase)) throw new Error(job.error || `${label} ${phase}.`);
        const progress = Number(job.progress);
        if (Number.isFinite(progress) && progress > 0) this.progress.value = Math.min(1, Math.max(0, progress));
        else this.progress.removeAttribute('value');
        this.activity.textContent = job.message || `${label}${phase === 'queued' ? ' · queued' : '…'}`;
        await wait(850);
        if (this.destroyed) return {};
        try {
          const next = await this.request(`/api/jobs/${encodeURIComponent(id)}`);
          job = next.job || next;
          failures = 0;
        } catch (error) {
          failures++;
          this.activity.textContent = 'Connection interrupted · retrying';
          if (failures >= 8) throw new Error('Could not read the operation result. It may still be running; reconnect before starting it again.');
        }
      }
      return {};
    }

    async install() {
      if (this.installing || this.opening || this.destroyed) return;
      this.installing = true;
      this.lastFailedAction = null;
      this.activity.classList.remove('native-editor-error');
      this._setNotice('Installing native editing workspaces', 'Downloading and preparing the full editors.', {busy: true});
      try {
        const project = this._project();
        this.desired = {editor: this.desired?.editor || this.attemptedEditor || this.selected, projectId: project.id};
        const response = await this.request('/api/native/install', {method: 'POST', body: {project_id: project.id}});
        await this._followJob(response, 'Installing editors');
        if (this.destroyed) return;
        await this.refreshStatus();
        if (!this.status?.installed) throw new Error('Installation finished without a verified editor runtime.');
      } catch (error) {
        if (!this.destroyed) this._error(error, 'install');
        return;
      } finally {
        this.installing = false;
        this.root.removeAttribute('aria-busy');
      }
      if (this.visible && !this.destroyed) await this._openDesired();
    }

    _watchInstallation() {
      clearTimeout(this.refreshTimer);
      if (!this.visible || this.destroyed || this.installing) return;
      this.refreshTimer = setTimeout(async () => {
        try {
          const status = await this.refreshStatus();
          if (!this.visible || this.destroyed || !status) return;
          if (status.installed) await this._openDesired();
          else if (status.building) this._watchInstallation();
          else await this.show(this.desired?.editor || this.selected);
        } catch (error) {
          if (!this.destroyed) this._error(error, 'install');
        }
      }, 3000);
    }

    async importExports() {
      if (this.importing || this.destroyed) return;
      this.importing = true;
      this._updateProject();
      try {
        const project = this._project();
        const response = await this.request(`/api/projects/${encodeURIComponent(project.id)}/native/exports`, {
          method: 'POST', body: {},
        });
        if (this.destroyed) return;
        if (response.project && this.getProject()?.id === project.id) await this.onProjectUpdate(response.project);
        const count = response.imported_count ?? (Array.isArray(response.imported) ? response.imported.length : null);
        this.notify(count === 0 ? 'No new finished media was found in this project’s exports folder.'
          : count === null ? 'Exported media imported into the assembly bin.'
            : `${count} exported ${count === 1 ? 'file' : 'files'} imported into the assembly bin.`);
      } catch (error) {
        this.notify(error.message || String(error), true);
      } finally {
        this.importing = false;
        this._updateProject();
      }
    }

    async _projectFiles() {
      if (!this.onProjectFiles || this.destroyed) return;
      try { await this.onProjectFiles(this._project()); }
      catch (error) { this.notify(error.message || String(error), true); }
    }

    _retry() {
      if (this.lastFailedAction === 'install') return this.install();
      if (this.lastFailedAction === 'reconnect') return this.reconnect();
      return this.show(this.desired?.editor || this.attemptedEditor || this.selected);
    }

    destroy() {
      this.destroyed = true;
      this.visible = false;
      this.statusSerial++;
      clearTimeout(this.refreshTimer);
      this.root.remove();
      this.mount.closest('.app')?.classList.remove('native-active');
      // Removing this viewer does not stop native processes or discard projects.
    }
  }

  window.CinematicumNativeEditors = NativeEditors;
})();

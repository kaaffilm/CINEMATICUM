// Same-file access only binds isolated startup and observes the unchanged
// production quit delegate. Actual NSApp termination and NSAlert buttons drive
// applicationShouldTerminate -> prepare-quit -> the real owned worker shutdown.
import CryptoKit

extension StudioAppDelegate {
    fileprivate func quitAcceptanceLaunch(python: String, script: String, workspacePath: String,
                                         log: FileHandle, onExit: @escaping (Int32) -> Void) throws {
        makeMenus(); makeWindow()
        let child = Process()
        child.executableURL = URL(fileURLWithPath: python)
        // Match the production launcher's sibling-import-compatible invocation.
        child.arguments = ["-B", "-u", script, "--workspace", workspacePath, "--port", "0"]
        child.currentDirectoryURL = URL(fileURLWithPath: script).deletingLastPathComponent()
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (environment["PATH"] ?? "")
        environment["PYTHONUNBUFFERED"] = "1"; environment["PYTHONDONTWRITEBYTECODE"] = "1"; environment["PYTHONNOUSERSITE"] = "1"
        environment.removeValue(forKey: "PYTHONPATH"); environment.removeValue(forKey: "PYTHONHOME")
        child.environment = environment; child.standardInput = FileHandle.nullDevice
        let pipe = Pipe(); outputPipe = pipe
        child.standardOutput = pipe; child.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { handle.readabilityHandler = nil; return }
            try? log.write(contentsOf: data)
            DispatchQueue.main.async { self?.consumeOutput(data) }
        }
        child.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.outputPipe?.fileHandleForReading.readabilityHandler = nil
                onExit(process.terminationStatus)
                if self.quitting { self.finishQuit() }
            }
        }
        server = child
        try child.run()
    }

    fileprivate var quitAcceptanceReady: Bool { isLocal(webView.url) && !webView.isLoading }
    fileprivate var quitAcceptanceSheet: NSWindow? { window.attachedSheet }
    fileprivate var quitAcceptanceRunning: Bool { server?.isRunning ?? false }
    fileprivate var quitAcceptanceChildPID: Int32 { server?.processIdentifier ?? 0 }
    fileprivate var quitAcceptanceRestored: Bool { !quitting && !webView.isHidden }
    fileprivate func quitAcceptanceRun(_ script: String, completion: @escaping (Result<Any, Error>) -> Void) {
        webView.callAsyncJavaScript(script, arguments: [:], in: nil, in: .page, completionHandler: completion)
    }
    fileprivate func quitAcceptanceCleanup() {
        if let child = server, child.isRunning { child.terminate(); child.waitUntilExit() }
    }
}

private func quitButtons(_ view: NSView?) -> [NSButton] {
    guard let view = view else { return [] }
    var result = (view as? NSButton).map { [$0] } ?? []
    for child in view.subviews { result.append(contentsOf: quitButtons(child)) }
    return result
}

private func quitText(_ view: NSView?) -> [String] {
    guard let view = view else { return [] }
    var result = (view as? NSTextField).map { [$0.stringValue] } ?? []
    for child in view.subviews { result.append(contentsOf: quitText(child)) }
    return result
}

private func quitPanelPicture(_ window: NSWindow, destination: URL) throws {
    guard let view = window.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
        throw NSError(domain: "QuitAcceptance", code: 1, userInfo: [NSLocalizedDescriptionKey: "Actual alert cannot be captured"])
    }
    view.cacheDisplay(in: view.bounds, to: bitmap)
    guard let data = bitmap.representation(using: .png, properties: [:]), data.count > 1000 else {
        throw NSError(domain: "QuitAcceptance", code: 2, userInfo: [NSLocalizedDescriptionKey: "Actual alert capture is empty"])
    }
    try data.write(to: destination, options: .withoutOverwriting)
}

final class ProductionQuitAcceptance: NSObject, NSApplicationDelegate {
    private let production = StudioAppDelegate()
    private let python: String, serverScript: String, workspacePath: String, script: String, restartScript: String
    private let directory: URL
    private let began = Date()
    private var timer: Timer?
    private var phase = "loading"
    private var finished = false
    private var workflow: [String: Any] = [:]
    private var checks: [String: Bool] = [:]
    private var alerts: [[String: Any]] = []
    private var report: [String: Any] = [:]
    private var childStatus: Int32?
    private var keepClickedAt: TimeInterval?
    private var log: FileHandle?

    init(python: String, serverScript: String, workspacePath: String, script: String, restartScript: String, directory: URL) {
        self.python = python; self.serverScript = serverScript; self.workspacePath = workspacePath
        self.script = script; self.restartScript = restartScript; self.directory = directory
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let logURL = directory.appendingPathComponent("owned-server.log")
            guard !FileManager.default.fileExists(atPath: logURL.path) else { throw error("Server log already exists") }
            FileManager.default.createFile(atPath: logURL.path, contents: Data())
            log = try FileHandle(forWritingTo: logURL)
            try production.quitAcceptanceLaunch(python: python, script: serverScript, workspacePath: workspacePath, log: log!) { [weak self] status in
                guard let self = self else { return }
                self.childStatus = status
                if !self.finished && self.phase != "confirming-cancel" { self.fail("Owned server exited outside the confirmed native cancellation path") }
            }
            report["owned_server_pid"] = production.quitAcceptanceChildPID
            timer = Timer(timeInterval: 0.04, repeats: true) { [weak self] _ in self?.tick() }
            RunLoop.main.add(timer!, forMode: .common)
        } catch { fail(error.localizedDescription) }
    }

    private func error(_ message: String) -> NSError {
        NSError(domain: "QuitAcceptance", code: 3, userInfo: [NSLocalizedDescriptionKey: message])
    }

    private func tick() {
        guard !finished else { return }
        if Date().timeIntervalSince(began) > 85 { fail("Timed out in actual ordinary-quit phase: " + phase); return }
        do {
            switch phase {
            case "loading":
                guard production.quitAcceptanceReady else { return }
                phase = "real-render"
                production.quitAcceptanceRun(script) { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success(let value):
                        guard let data = value as? [String: Any], data["passed"] as? Bool == true,
                              data["job_state"] as? String == "running" else { self.fail("Real render workflow returned no running job"); return }
                        self.workflow = data; self.checks["real_render_made_progress_before_quit"] = true
                        self.checks["ordinary_edit_is_unsaved_before_quit"] = data["dirty_before_quit"] as? Bool == true
                        self.phase = "keep-alert"
                        NSApp.terminate(nil)
                    case .failure(let error): self.fail(error.localizedDescription)
                    }
                }
            case "keep-alert", "cancel-alert":
                guard let sheet = production.quitAcceptanceSheet else { return }
                let buttons = quitButtons(sheet.contentView)
                let keep = buttons.filter { $0.title == "Keep Working" && $0.isEnabled }
                let cancel = buttons.filter { $0.title == "Cancel Jobs and Quit" && $0.isEnabled }
                guard keep.count == 1 && cancel.count == 1 else { return }
                let texts = quitText(sheet.contentView)
                guard texts.contains(where: { $0.contains("still running") && $0.contains("Saved projects and completed media will be preserved") }), production.quitAcceptanceRunning else { throw error("Active-job alert does not describe the actual running media work") }
                let keeping = phase == "keep-alert"
                let picture = directory.appendingPathComponent(keeping ? "keep-working-alert.png" : "cancel-jobs-alert.png")
                try quitPanelPicture(sheet, destination: picture)
                alerts.append(["action": keeping ? "Keep Working" : "Cancel Jobs and Quit", "text": texts,
                               "picture": picture.path, "window_class": String(describing: type(of: sheet))])
                if keeping {
                    checks["actual_first_active_job_alert"] = true; phase = "restored"
                    keepClickedAt = Date().timeIntervalSince1970
                    report["keep_working_click_at"] = keepClickedAt
                    keep[0].performClick(nil)
                } else {
                    checks["actual_second_active_job_alert"] = true; phase = "confirming-cancel"
                    cancel[0].performClick(nil)
                }
            case "restored":
                guard production.quitAcceptanceSheet == nil && production.quitAcceptanceRestored && production.quitAcceptanceRunning else { return }
                phase = "verify-preservation"
                guard let job = workflow["job_id"] as? String, let project = workflow["project_id"] as? String else { throw error("Workflow identities are missing") }
                let query = "const j=await api('/api/jobs/" + job + "'); const p=await api('/api/projects/" + project + "'); return {job:j,project:p,dirty:state.dirty,save_state:document.getElementById('save-state').textContent};"
                production.quitAcceptanceRun(query) { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success(let value):
                        guard let data = value as? [String: Any], let job = data["job"] as? [String: Any],
                              let clicked = self.keepClickedAt, let project = data["project"] as? [String: Any],
                              let settings = project["settings"] as? [String: Any], settings["transparent_background"] as? Bool == true,
                              data["dirty"] as? Bool == false else { self.fail("Keep Working did not preserve the real job and save the actual edit"); return }
                        let naturallyFinishedAfterClick = job["state"] as? String == "completed"
                            && (job["finished_at"] as? Double).map { $0.isFinite && $0 >= clicked } == true
                        guard job["state"] as? String == "running" || naturallyFinishedAfterClick else {
                            self.fail("First actual job was not running at Keep Working or did not survive that choice"); return
                        }
                        self.report["after_keep_working"] = data
                        self.checks["keep_working_restored_ui_and_preserved_actual_job"] = true
                        self.checks["production_quit_saved_dirty_project_before_alert"] = true
                        self.waitForFirstCompletion()
                    case .failure(let error): self.fail(error.localizedDescription)
                    }
                }
            default: break
            }
        } catch { fail(error.localizedDescription) }
    }

    private func waitForFirstCompletion() {
        guard let first = workflow["job_id"] as? String,
              first.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil else {
            fail("The actual first job identity is invalid"); return
        }
        phase = "first-render-completion"
        let query = """
        const end=performance.now()+60000;
        while(performance.now()<end){
          const j=await api('/api/jobs/\(first)');
          if(['failed','cancelled','interrupted'].includes(j.state))throw Error('First real render stopped after Keep Working: '+j.state+' '+j.error);
          if(j.state==='completed'&&state.job?.id===j.id&&state.job?.state==='completed'&&!document.getElementById('download-job').hidden)
            return {job:j,download_href:document.getElementById('download-job').getAttribute('href')};
          await new Promise(r=>setTimeout(r,80));
        }
        throw Error('First actual FFmpeg render did not complete after Keep Working');
        """
        production.quitAcceptanceRun(query) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(let value):
                do {
                    guard let data = value as? [String: Any], let job = data["job"] as? [String: Any],
                          job["id"] as? String == first, job["state"] as? String == "completed",
                          let receipt = job["result"] as? [String: Any],
                          let project = self.workflow["project_id"] as? String,
                          project.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil,
                          receipt["filename"] as? String == first + ".mkv",
                          let url = receipt["url"] as? String,
                          data["download_href"] as? String == url + "?download=1" else {
                        throw self.error("First actual render has no completed, downloadable master")
                    }
                    let path = URL(fileURLWithPath: self.workspacePath, isDirectory: true)
                        .appendingPathComponent("projects/" + project + "/exports/" + first + ".mkv")
                    let attributes = try path.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
                    guard attributes.isRegularFile == true, attributes.isSymbolicLink != true,
                          let size = attributes.fileSize, size > 0, size < 128 * 1024 * 1024 else {
                        throw self.error("First actual completed master is absent, unsafe, or exceeds the fixture bound")
                    }
                    let payload = try Data(contentsOf: path, options: .mappedIfSafe)
                    let digest = SHA256.hash(data: payload).map { String(format: "%02x", $0) }.joined()
                    guard receipt["sha256"] as? String == digest else { throw self.error("First completed master bytes differ from their actual job receipt") }
                    self.report["first_completed_before_second_job"] = data
                    self.report["completed_master_before_cancellation"] = ["path": path.path, "bytes": size, "sha256": digest]
                    self.checks["keep_working_allowed_first_actual_render_to_complete"] = true
                    self.checks["completed_media_hashed_before_second_job"] = true
                    self.startSecondRender(first)
                } catch { self.fail(error.localizedDescription) }
            case .failure(let error): self.fail(error.localizedDescription)
            }
        }
    }

    private func startSecondRender(_ first: String) {
        phase = "second-real-render"
        production.quitAcceptanceRun("const QUIT_FIRST_JOB_ID='" + first + "';\n" + restartScript) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(let value):
                guard let data = value as? [String: Any], data["passed"] as? Bool == true,
                      data["job_state"] as? String == "running", let second = data["job_id"] as? String,
                      second != first, second.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil else {
                    self.fail("A distinct actual render was not admitted after Keep Working"); return
                }
                self.report["second_render"] = data
                self.checks["keep_working_preserved_admission_for_second_actual_render"] = true
                self.phase = "cancel-alert"
                NSApp.terminate(nil)
            case .failure(let error): self.fail(error.localizedDescription)
            }
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard phase == "keep-alert" || phase == "cancel-alert" || phase == "confirming-cancel" else {
            fail("Unexpected application quit request outside the scheduled native acceptance action")
            return .terminateCancel
        }
        return production.applicationShouldTerminate(sender)
    }

    func applicationWillTerminate(_ notification: Notification) {
        checks["production_waited_for_owned_server_exit"] = phase == "confirming-cancel" && childStatus == 0 && !production.quitAcceptanceRunning
        production.applicationWillTerminate(notification)
        emit(nil)
    }

    private func fail(_ message: String) {
        guard !finished else { return }
        timer?.invalidate()
        // Failure cleanup terminates only this helper's real child. It is never
        // counted as ordinary-quit acceptance and never signals an existing app.
        finished = true
        production.quitAcceptanceCleanup()
        finished = false
        emit(message)
        exit(1)
    }

    private func emit(_ error: String?) {
        guard !finished else { return }
        finished = true; timer?.invalidate(); try? log?.close()
        report["scope"] = "Unchanged production ordinary-quit/alert/cancel methods and real NSAlert buttons with actual FFmpeg jobs; isolated server startup and child-exit forwarding, not production launcher or installed-app UI acceptance"
        report["workflow"] = workflow; report["checks"] = checks; report["alerts"] = alerts
        report["phase"] = phase; report["owned_server_exit_status"] = childStatus
        report["elapsed_seconds"] = Date().timeIntervalSince(began)
        if let error = error { report["error"] = error }
        report["passed"] = error == nil && checks.count == 10 && checks.values.allSatisfy { $0 }
        do {
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
        } catch { fputs("Native quit report serialization failed: \(error)\n", stderr) }
    }
}

private func quitArgument(_ name: String) -> String? {
    guard let index = CommandLine.arguments.firstIndex(of: name), index + 1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[index + 1]
}

guard let python = quitArgument("--python"), let serverScript = quitArgument("--server"),
      let workspacePath = quitArgument("--workspace"), let rawDirectory = quitArgument("--evidence"),
      let scriptPath = quitArgument("--script"), let restartPath = quitArgument("--restart-script"),
      [python, serverScript, workspacePath, rawDirectory, scriptPath, restartPath].allSatisfy({ $0.hasPrefix("/") }) else {
    fputs("Usage: production-quit-acceptance --python /python --server /server.py --workspace /isolated/workspace --evidence /new/directory --script /workflow.js --restart-script /restart.js\n", stderr)
    exit(2)
}
do {
    let script = try String(contentsOfFile: scriptPath, encoding: .utf8)
    let restart = try String(contentsOfFile: restartPath, encoding: .utf8)
    let delegate = ProductionQuitAcceptance(python: python, serverScript: serverScript, workspacePath: workspacePath,
                                            script: script, restartScript: restart, directory: URL(fileURLWithPath: rawDirectory, isDirectory: true))
    let quitApplication = NSApplication.shared
    quitApplication.delegate = delegate; quitApplication.setActivationPolicy(.regular)
    withExtendedLifetime(delegate) { quitApplication.run() }
} catch { fputs("Native quit acceptance startup failed: \(error)\n", stderr); exit(2) }

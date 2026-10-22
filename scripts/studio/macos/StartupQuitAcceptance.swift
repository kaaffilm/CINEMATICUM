// Appended to the byte-for-byte production class, replacing only its top-level
// application bootstrap. The isolated real server has explicit HTTP barriers.
// Ordinary NSApp termination and actual NSAlert buttons exercise product code.
import CryptoKit

extension StudioAppDelegate {
    fileprivate func startupTestLaunch(python: String, script: String, workspacePath: String,
                                      evidence: String, phase: String, log: FileHandle,
                                      line: @escaping (String) -> Void,
                                      exited: @escaping (Int32) -> Void) throws -> Pipe {
        makeMenus(); makeWindow()
        let child = Process(), input = Pipe(), output = Pipe()
        child.executableURL = URL(fileURLWithPath: python)
        child.arguments = ["-B", "-u", script, "--workspace", workspacePath, "--port", "0",
                           "--evidence", evidence, "--phase", phase]
        child.currentDirectoryURL = URL(fileURLWithPath: script).deletingLastPathComponent()
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (environment["PATH"] ?? "")
        environment["PYTHONUNBUFFERED"] = "1"; environment["PYTHONDONTWRITEBYTECODE"] = "1"; environment["PYTHONNOUSERSITE"] = "1"
        environment.removeValue(forKey: "PYTHONPATH"); environment.removeValue(forKey: "PYTHONHOME")
        child.environment = environment; child.standardInput = input
        outputPipe = output; child.standardOutput = output; child.standardError = output
        var pending = ""
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { handle.readabilityHandler = nil; return }
            try? log.write(contentsOf: data)
            DispatchQueue.main.async {
                self?.consumeOutput(data)
                pending += String(decoding: data, as: UTF8.self)
                while let newline = pending.firstIndex(of: "\n") {
                    let value = String(pending[..<newline]); pending.removeSubrange(...newline)
                    line(value)
                }
            }
        }
        child.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.outputPipe?.fileHandleForReading.readabilityHandler = nil
                exited(process.terminationStatus)
                if self.quitting { self.finishQuit() }
            }
        }
        server = child; try child.run(); return input
    }

    fileprivate var startupTestReady: Bool { editorDocumentReady && isLocal(webView.url) }
    fileprivate var startupTestLocal: Bool { isLocal(webView.url) }
    fileprivate var startupTestPending: Bool { quitting && !repliedToQuit }
    fileprivate var startupTestSheet: NSWindow? { window.attachedSheet }
    fileprivate var startupTestRunning: Bool { server?.isRunning ?? false }
    fileprivate var startupTestPID: Int32 { server?.processIdentifier ?? 0 }
    fileprivate var startupTestRestored: Bool { !quitting && !webView.isHidden }
    fileprivate func startupTestScript(_ script: String, completion: @escaping (Result<Any, Error>) -> Void) {
        webView.callAsyncJavaScript(script, arguments: [:], in: nil, in: .page, completionHandler: completion)
    }
    fileprivate func startupTestCleanup() {
        // Failure cleanup only. It is never reported as ordinary-quit success.
        if let child = server, child.isRunning { child.terminate() }
    }
}

private func startupButtons(_ view: NSView?) -> [NSButton] {
    guard let view = view else { return [] }
    return ((view as? NSButton).map { [$0] } ?? []) + view.subviews.flatMap { startupButtons($0) }
}

private func startupPicture(_ window: NSWindow, _ path: URL) throws {
    guard let view = window.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
        throw NSError(domain: "StartupQuit", code: 1, userInfo: [NSLocalizedDescriptionKey: "Actual alert cannot be captured"])
    }
    view.cacheDisplay(in: view.bounds, to: bitmap)
    guard let data = bitmap.representation(using: .png, properties: [:]), data.count > 1000 else {
        throw NSError(domain: "StartupQuit", code: 2, userInfo: [NSLocalizedDescriptionKey: "Actual alert picture is empty"])
    }
    try data.write(to: path, options: .withoutOverwriting)
}

final class StartupQuitAcceptance: NSObject, NSApplicationDelegate {
    private let production = StudioAppDelegate()
    private let python: String, serverScript: String, workspace: String, mode: String, workflow: String
    private let evidence: URL
    private let began = Date()
    private var state = "loading", finished = false
    private var timer: Timer?, input: Pipe?, log: FileHandle?
    private var fixture: [String: Any] = [:], report: [String: Any] = [:], checks: [String: Bool] = [:]
    private var childStatus: Int32?, jobID: String?, quitRequests = 0
    private var failure: String?, cleanupBegan: Date?

    init(python: String, server: String, workspace: String, evidence: URL, mode: String, workflow: String) {
        self.python = python; self.serverScript = server; self.workspace = workspace
        self.evidence = evidence; self.mode = mode; self.workflow = workflow
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let destination = evidence.appendingPathComponent("owned-server.log")
            guard !FileManager.default.fileExists(atPath: destination.path) else { throw problem("Evidence log already exists") }
            FileManager.default.createFile(atPath: destination.path, contents: Data())
            log = try FileHandle(forWritingTo: destination)
            input = try production.startupTestLaunch(python: python, script: serverScript, workspacePath: workspace,
                evidence: evidence.path, phase: mode, log: log!, line: { [weak self] value in self?.line(value) },
                exited: { [weak self] status in
                    guard let self = self else { return }
                    self.childStatus = status
                    if self.failure != nil { self.emit(); exit(1) }
                    if !self.production.startupTestPending { self.fail("Owned server exited outside ordinary native quit") }
                })
            report["owned_server_pid"] = production.startupTestPID
            timer = Timer(timeInterval: 0.025, repeats: true) { [weak self] _ in self?.tick() }
            RunLoop.main.add(timer!, forMode: .common)
        } catch { fail(error.localizedDescription) }
    }

    private func problem(_ message: String) -> NSError {
        NSError(domain: "StartupQuit", code: 3, userInfo: [NSLocalizedDescriptionKey: message])
    }

    private func line(_ value: String) {
        guard !finished, failure == nil else { return }
        if value.hasPrefix("ENGINE_TEST_FIXTURE: ") {
            do {
                let bytes = Data(value.dropFirst("ENGINE_TEST_FIXTURE: ".count).utf8)
                guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                      object["engine_test_only"] as? Bool == true, object["phase"] as? String == mode else {
                    throw problem("The actual isolated fixture identity is invalid")
                }
                fixture = object
            } catch { fail(error.localizedDescription) }
        }
        if value == "ENGINE_TEST_GATE: " + mode && state == "loading" {
            guard production.startupTestLocal else { fail("The startup barrier was reached before a local document existed"); return }
            state = "observing-barrier"
            production.startupTestScript("return {api_type:typeof api, document_state:document.readyState, token_empty:typeof state==='undefined'||state.token==='', project_absent:typeof state==='undefined'||state.project===null};") { [weak self] result in
                guard let self = self else { return }
                switch result {
                case .success(let value):
                    guard let observation = value as? [String: Any], observation["token_empty"] as? Bool == true,
                          observation["project_absent"] as? Bool == true,
                          observation["api_type"] as? String == (self.mode == "app-script" ? "undefined" : "function") else {
                        self.fail("Startup quit was not requested at the actual pre-bootstrap boundary"); return
                    }
                    self.report["before_ordinary_quit"] = observation
                    self.checks["quit_requested_before_bootstrap_token_and_project"] = true
                    self.checks["actual_local_document_at_request"] = self.production.startupTestLocal
                    self.state = "early-quit"
                    NSApp.terminate(nil)
                case .failure(let error): self.fail(error.localizedDescription)
                }
            }
        }
    }

    private func tick() {
        guard !finished else { return }
        if let since = cleanupBegan {
            if !production.startupTestRunning || Date().timeIntervalSince(since) > 2 { emit(); exit(1) }
            return
        }
        if Date().timeIntervalSince(began) > 13 { fail("Bounded native phase timed out at " + state); return }
        if mode != "protection" {
            if state == "early-quit" && production.startupTestSheet != nil { fail("Early ordinary quit opened a failure alert") }
            return
        }
        do {
            switch state {
            case "loading":
                guard production.startupTestReady, let project = fixture["project_id"] as? String else { return }
                state = "real-worker"
                let binding = try JSONSerialization.data(withJSONObject: ["project_id": project])
                let script = "const QUIT_TEST=" + String(decoding: binding, as: UTF8.self) + ";\n" + workflow
                production.startupTestScript(script) { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success(let value):
                        guard let data = value as? [String: Any], data["passed"] as? Bool == true,
                              data["job_state"] as? String == "running", data["dirty_before_quit"] as? Bool == true,
                              let job = data["job_id"] as? String,
                              job.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil else {
                            self.fail("The shipped workflow did not produce an actual running job and dirty edit"); return
                        }
                        self.jobID = job; self.report["workflow"] = data
                        self.checks["actual_ffmpeg_progress_and_unsaved_edit"] = true
                        self.state = "keep-alert"; NSApp.terminate(nil)
                    case .failure(let error): self.fail(error.localizedDescription)
                    }
                }
            case "keep-alert", "cancel-alert":
                guard let sheet = production.startupTestSheet else { return }
                let buttons = startupButtons(sheet.contentView)
                let keep = buttons.filter { $0.title == "Keep Working" && $0.isEnabled }
                let cancel = buttons.filter { $0.title == "Cancel Jobs and Quit" && $0.isEnabled }
                guard keep.count == 1, cancel.count == 1, production.startupTestRunning else {
                    throw problem("The active-work decision was replaced with an unexpected native alert")
                }
                let retaining = state == "keep-alert"
                try startupPicture(sheet, evidence.appendingPathComponent(retaining ? "keep-working.png" : "cancel-jobs.png"))
                checks[retaining ? "actual_keep_working_button" : "actual_cancel_jobs_button"] = true
                state = retaining ? "after-keep" : "confirmed-cancel"
                (retaining ? keep[0] : cancel[0]).performClick(nil)
            case "after-keep":
                guard production.startupTestSheet == nil, production.startupTestRestored,
                      let job = jobID, let project = fixture["project_id"] as? String else { return }
                state = "verify-preservation"
                production.startupTestScript("const j=await api('/api/jobs/\(job)'); const p=await api('/api/projects/\(project)'); return {job:j,project:p,dirty:state.dirty};") { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success(let value):
                        guard let data = value as? [String: Any], let job = data["job"] as? [String: Any],
                              job["state"] as? String == "running", let project = data["project"] as? [String: Any],
                              let settings = project["settings"] as? [String: Any], settings["transparent_background"] as? Bool == true,
                              data["dirty"] as? Bool == false else { self.fail("Keep Working did not preserve the real worker and save the dirty edit"); return }
                        self.report["after_keep_working"] = data
                        self.checks["keep_working_preserved_real_worker_and_restored_editor"] = true
                        self.checks["ordinary_dirty_edit_durably_saved_before_prompt"] = true
                        self.state = "cancel-alert"; NSApp.terminate(nil)
                    case .failure(let error): self.fail(error.localizedDescription)
                    }
                }
            default: break
            }
        } catch { fail(error.localizedDescription) }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard ["early-quit", "keep-alert", "cancel-alert", "confirmed-cancel"].contains(state), failure == nil else {
            fail("Unexpected native quit request outside its explicit acceptance phase"); return .terminateCancel
        }
        quitRequests += 1
        let response = production.applicationShouldTerminate(sender)
        checks["ordinary_quit_deferred_for_owned_shutdown"] = response == .terminateLater
        if state == "early-quit" {
            // Release by a causal event after the production delegate accepted
            // this actual quit request. No elapsed delay makes the test pass.
            DispatchQueue.main.async { [weak self] in
                guard let self = self, self.failure == nil else { return }
                self.checks["quit_stays_pending_before_barrier_release"] = self.production.startupTestPending
                try? self.input?.fileHandleForWriting.write(contentsOf: Data("RELEASE\n".utf8))
            }
        }
        return response
    }

    func applicationWillTerminate(_ notification: Notification) {
        checks["owned_server_exited_before_application"] = childStatus == 0 && !production.startupTestRunning
        checks["expected_ordinary_quit_count"] = quitRequests == (mode == "protection" ? 2 : 1)
        production.applicationWillTerminate(notification); emit()
    }

    private func fail(_ message: String) {
        guard !finished, failure == nil else { return }
        failure = message; cleanupBegan = Date(); state = "failure-cleanup"
        try? input?.fileHandleForWriting.write(contentsOf: Data("EXIT\n".utf8))
        production.startupTestCleanup()
        if !production.startupTestRunning { emit(); exit(1) }
    }

    private func emit() {
        guard !finished else { return }
        finished = true; timer?.invalidate(); try? log?.close(); try? input?.fileHandleForWriting.close()
        do {
            let events = try JSONSerialization.jsonObject(with: Data(contentsOf: evidence.appendingPathComponent("transport-events.json"))) as? [[String: Any]] ?? []
            let quit = events.filter { $0["event"] as? String == "quit-response" }
            checks["every_quit_request_authenticated"] = !quit.isEmpty && quit.allSatisfy { $0["authenticated"] as? Bool == true && $0["status"] as? Int == 200 }
            if mode == "protection" {
                checks["actual_active_work_requires_confirmation"] = quit.count == 3
                    && ((quit[0]["response"] as? [String: Any])?["ready"] as? Bool == false)
                    && ((quit[1]["response"] as? [String: Any])?["ready"] as? Bool == false)
                    && ((quit[2]["decision"] as? [String: Any])?["cancel_active"] as? Bool == true)
                    && ((quit[2]["response"] as? [String: Any])?["ready"] as? Bool == true)
            } else {
                checks["one_safe_quit_after_bootstrap"] = quit.count == 1
                    && ((quit[0]["decision"] as? [String: Any])?["cancel_active"] as? Bool == false)
                    && ((quit[0]["response"] as? [String: Any])?["ready"] as? Bool == true)
            }
            report["transport_events"] = events
        } catch { failure = failure ?? error.localizedDescription }
        report["schema"] = "cinematicum-native-startup-quit-v1"
        report["scope"] = "Unchanged production class ordinary quit, save and real NSAlert decisions; isolated real server transport barriers. Installed launcher and user projects are not exercised."
        report["engine_test_only"] = true; report["force_kill_used"] = false
        report["phase"] = mode; report["state"] = state; report["checks"] = checks
        report["ordinary_quit_requests"] = quitRequests; report["owned_server_exit_status"] = childStatus
        report["owned_server_still_running"] = production.startupTestRunning
        report["elapsed_seconds"] = Date().timeIntervalSince(began)
        report["passed"] = failure == nil && checks.count >= 8 && checks.values.allSatisfy { $0 }
        if let failure = failure { report["error"] = failure }
        do {
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            try data.write(to: evidence.appendingPathComponent("native-report.json"), options: .withoutOverwriting)
            FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
        } catch { fputs("Native startup-quit report could not be saved: \(error)\n", stderr) }
    }
}

private func startupArgument(_ name: String) -> String? {
    guard let i = CommandLine.arguments.firstIndex(of: name), i + 1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[i + 1]
}

guard let python = startupArgument("--python"), let server = startupArgument("--server"),
      let workspace = startupArgument("--workspace"), let directory = startupArgument("--evidence"),
      let mode = startupArgument("--phase"), ["app-script", "bootstrap", "protection"].contains(mode),
      let script = startupArgument("--workflow"), [python, server, workspace, directory, script].allSatisfy({ $0.hasPrefix("/") }) else {
    fputs("Required: --python /python --server /fixture.py --workspace /new/workspace --evidence /directory --phase app-script|bootstrap|protection --workflow /QuitWorkflow.js\n", stderr)
    exit(2)
}
do {
    let workflow = try String(contentsOfFile: script, encoding: .utf8)
    let delegate = StartupQuitAcceptance(python: python, server: server, workspace: workspace,
        evidence: URL(fileURLWithPath: directory), mode: mode, workflow: workflow)
    let native = NSApplication.shared
    native.delegate = delegate; native.setActivationPolicy(.regular)
    withExtendedLifetime(delegate) { native.run() }
} catch { fputs("Native startup-quit acceptance could not start: \(error)\n", stderr); exit(2) }

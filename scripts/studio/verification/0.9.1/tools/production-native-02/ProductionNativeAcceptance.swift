import CryptoKit

// This extension is in the same generated Swift file as the original class.
// Startup binding and observations are test-only; production delegate methods
// and their real NSSavePanel/WKDownload callbacks remain byte-identical.
extension StudioAppDelegate {
    fileprivate func acceptanceOpen(_ origin: URL) {
        makeMenus()
        makeWindow()
        serverURL = origin
        webView.load(URLRequest(url: origin))
    }

    fileprivate var acceptanceReady: Bool {
        return isLocal(webView.url) && !webView.isLoading
    }

    fileprivate func acceptanceRun(_ script: String, completion: @escaping (Result<Any, Error>) -> Void) {
        webView.callAsyncJavaScript(script, arguments: [:], in: nil, in: .page, completionHandler: completion)
    }

    fileprivate func acceptanceClickDownload(completion: @escaping (Result<Any, Error>) -> Void) {
        acceptanceRun("const a=document.getElementById('download-job'); if (!a || a.hidden || !a.href) throw Error('Actual download control is unavailable'); a.click(); return {href:a.getAttribute('href')};", completion: completion)
    }

    fileprivate var acceptancePanel: NSSavePanel? {
        return window.attachedSheet as? NSSavePanel
    }

    fileprivate var acceptanceSheet: NSWindow? { window.attachedSheet }

    fileprivate var acceptanceDownloadCount: Int { activeDownloads.count }
    fileprivate var acceptanceTemporaryCount: Int { downloadFiles.count }
    fileprivate var acceptanceSubtitle: String { window.subtitle }
}

private func acceptanceSHA(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func acceptanceButtons(_ view: NSView?) -> [NSButton] {
    guard let view = view else { return [] }
    var result = (view as? NSButton).map { [$0] } ?? []
    for child in view.subviews { result.append(contentsOf: acceptanceButtons(child)) }
    return result
}

private func acceptanceButton(_ panel: NSSavePanel, save: Bool) -> NSButton? {
    let buttons = acceptanceButtons(panel.contentView)
    if save, let cell = panel.defaultButtonCell, let button = cell.controlView as? NSButton,
       button.isEnabled && button.window === panel { return button }
    let matches = buttons.filter {
        $0.isEnabled && (save ? ($0.title == "Save" && $0.keyEquivalent == "\r") : ($0.title == "Cancel" || $0.keyEquivalent == "\u{1b}"))
    }
    return matches.count == 1 ? matches[0] : nil
}

private func acceptanceTextFields(_ view: NSView?) -> [String] {
    guard let view = view else { return [] }
    var result = (view as? NSTextField).map { [String($0.stringValue.prefix(500))] } ?? []
    for child in view.subviews { result.append(contentsOf: acceptanceTextFields(child)) }
    return Array(result.prefix(20))
}

private func acceptanceWindowDescription(_ window: NSWindow) -> [String: Any] {
    var value: [String: Any] = [
        "class": String(describing: type(of: window)), "window_number": window.windowNumber,
        "title": window.title, "visible": window.isVisible, "key": window.isKeyWindow,
        "sheet_parent_window_number": window.sheetParent?.windowNumber ?? -1,
        "attached_sheet_window_number": window.attachedSheet?.windowNumber ?? -1,
        "text_fields": acceptanceTextFields(window.contentView),
        "buttons": acceptanceButtons(window.contentView).map {
            ["title": $0.title, "enabled": $0.isEnabled, "key_equivalent": $0.keyEquivalent,
             "action": NSStringFromSelector($0.action ?? Selector("nil"))] as [String: Any]
        }
    ]
    if let panel = window as? NSSavePanel {
        value["directory"] = panel.directoryURL?.path ?? ""
        value["filename"] = panel.nameFieldStringValue
        value["selected_url"] = panel.url?.path ?? ""
        value["local_save_button"] = acceptanceButton(panel, save: true) != nil
        value["local_cancel_button"] = acceptanceButton(panel, save: false) != nil
    }
    return value
}

private func acceptanceKeyEvent(_ panel: NSSavePanel, save: Bool, type: NSEvent.EventType) throws -> NSEvent {
    let character = save ? "\r" : "\u{1b}"
    guard let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [],
                                      timestamp: ProcessInfo.processInfo.systemUptime,
                                      windowNumber: panel.windowNumber, context: nil,
                                      characters: character, charactersIgnoringModifiers: character,
                                      isARepeat: false, keyCode: save ? 36 : 53) else {
        throw NSError(domain: "ProductionAcceptance", code: 4,
                      userInfo: [NSLocalizedDescriptionKey: "Could not construct a public AppKit native key event"])
    }
    return event
}

private func acceptancePanelPicture(_ panel: NSSavePanel, destination: URL) throws -> [String: Any] {
    guard let view = panel.contentView,
          let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
        throw NSError(domain: "ProductionAcceptance", code: 1, userInfo: [NSLocalizedDescriptionKey: "Actual native panel view cannot be captured"])
    }
    view.cacheDisplay(in: view.bounds, to: bitmap)
    guard let png = bitmap.representation(using: .png, properties: [:]), png.count > 1000 else {
        throw NSError(domain: "ProductionAcceptance", code: 2, userInfo: [NSLocalizedDescriptionKey: "Actual native panel capture is empty"])
    }
    try png.write(to: destination, options: .withoutOverwriting)
    return ["path": destination.path, "bytes": png.count, "sha256": acceptanceSHA(png),
            "width": bitmap.pixelsWide, "height": bitmap.pixelsHigh,
            "method": "AppKit cacheDisplay of the actual NSSavePanel content view; not a screen-capture permission claim"]
}

final class ProductionDownloadAcceptance: NSObject, NSApplicationDelegate {
    private let production = StudioAppDelegate()
    private let origin: URL
    private let directory: URL
    private let script: String
    private let timeout: TimeInterval
    private let began = Date()
    private var timer: Timer?
    private var phase = "loading"
    private var phaseBegan = Date()
    private var startedScript = false
    private var finished = false
    private var ui: [String: Any]?
    private var checks: [String: Bool] = [:]
    private var panels: [[String: Any]] = []
    private var report: [String: Any] = [:]
    private var savedIdentity: [String: Any]?
    private var pendingPanel: NSSavePanel?
    private var observations: [[String: Any]] = []
    private var previousObservation = Data()
    private var discardedObservations = 0
    private var lastTick = ProcessInfo.processInfo.systemUptime
    private var largestTickGap: TimeInterval = 0
    private let savedName = "ENGINE_TEST_PRODUCTION_SAVED_MASTER.mkv"
    private let cancelledName = "ENGINE_TEST_PRODUCTION_CANCELLED_MASTER.mkv"

    init(origin: URL, directory: URL, script: String, timeout: TimeInterval) {
        self.origin = origin; self.directory = directory; self.script = script; self.timeout = timeout
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let values = try directory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard values.isDirectory == true && values.isSymbolicLink != true else { throw failure("Evidence directory must exist and must not be a symlink") }
            for name in [savedName, cancelledName, "save-panel.png", "cancel-panel.png"] {
                guard !FileManager.default.fileExists(atPath: directory.appendingPathComponent(name).path) else { throw failure("Refusing to overwrite existing acceptance evidence: " + name) }
            }
            guard try partials().isEmpty else { throw failure("Evidence directory already contains a partial download") }
            production.acceptanceOpen(origin)
            let polling = Timer(timeInterval: 0.04, repeats: true) { [weak self] _ in self?.tick() }
            timer = polling
            // Native panels may run modal/event-tracking modes. A default-mode
            // timer cannot reliably observe their lifecycle or dispatch input.
            RunLoop.main.add(polling, forMode: .common)
            RunLoop.main.add(polling, forMode: .modalPanel)
        } catch { finish(error.localizedDescription) }
    }

    private func failure(_ message: String) -> NSError {
        NSError(domain: "ProductionAcceptance", code: 3, userInfo: [NSLocalizedDescriptionKey: message])
    }

    private func advance(_ next: String) { phase = next; phaseBegan = Date() }

    private func observe(_ reason: String, force: Bool = false) {
        var value: [String: Any] = [
            "phase": phase, "active_downloads": production.acceptanceDownloadCount,
            "temporary_download_owners": production.acceptanceTemporaryCount,
            "subtitle": production.acceptanceSubtitle,
            "key_window_number": NSApp.keyWindow?.windowNumber ?? -1,
            "run_loop_mode": RunLoop.current.currentMode?.rawValue ?? "none"
        ]
        if let sheet = production.acceptanceSheet { value["attached_sheet"] = acceptanceWindowDescription(sheet) }
        if let panel = pendingPanel { value["retained_panel"] = acceptanceWindowDescription(panel) }
        let signature = (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])) ?? Data()
        guard force || signature != previousObservation else { return }
        previousObservation = signature
        value["reason"] = reason
        value["elapsed_seconds"] = Date().timeIntervalSince(began)
        if observations.count < 256 { observations.append(value) }
        else { discardedObservations += 1 }
    }

    private func visiblePendingPanel() throws -> NSSavePanel? {
        guard let panel = pendingPanel else { throw failure("No retained actual native panel") }
        guard panel === production.acceptancePanel && panel.isVisible else {
            if production.acceptanceDownloadCount == 0 {
                throw failure("Production download ended and its panel disappeared before native Save/Cancel input in phase: " + phase)
            }
            return nil
        }
        guard production.acceptanceDownloadCount == 1 && production.acceptanceTemporaryCount == 0 else {
            throw failure("Actual native chooser no longer owns exactly one pending destination decision")
        }
        return panel
    }

    private func beginConfiguration(_ panel: NSSavePanel, operation: String) {
        pendingPanel = panel
        observe("observed_" + operation + "_panel_before_configuration", force: true)
        advance(operation + "-directory")
        panel.directoryURL = directory
        observe("requested_" + operation + "_directory", force: true)
    }

    private func configureName(save: Bool) throws {
        guard Date().timeIntervalSince(phaseBegan) >= 0.15,
              let panel = try visiblePendingPanel(),
              panel.directoryURL?.standardizedFileURL == directory.standardizedFileURL else { return }
        panel.nameFieldStringValue = save ? savedName : cancelledName
        advance(save ? "save-button" : "cancel-button")
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKey()
        observe("requested_filename_and_native_panel_focus", force: true)
    }

    private func activatePanel(save: Bool) throws {
        guard Date().timeIntervalSince(phaseBegan) >= 0.15,
              let panel = try visiblePendingPanel(),
              panel.directoryURL?.standardizedFileURL == directory.standardizedFileURL,
              panel.nameFieldStringValue == (save ? savedName : cancelledName) else { return }
        let button = acceptanceButton(panel, save: save)
        // Current macOS file pickers may host their controls in another
        // process. Use the real focused panel's ordinary Return/Escape event
        // when no enabled local NSButton is exposed. Never call panel actions,
        // completion handlers, download delegates, or endSheet directly.
        if button == nil && !panel.isKeyWindow { return }
        let keyDown = button == nil ? try acceptanceKeyEvent(panel, save: save, type: .keyDown) : nil
        let keyUp = button == nil ? try acceptanceKeyEvent(panel, save: save, type: .keyUp) : nil
        let operation = save ? "save" : "cancel"
        let picture = try acceptancePanelPicture(panel, destination: directory.appendingPathComponent(operation + "-panel.png"))
        var action: [String: Any] = ["kind": button == nil ? "NSApplication.sendEvent" : "NSButton.performClick"]
        if let button = button {
            action["button_title"] = button.title
            action["button_action"] = NSStringFromSelector(button.action ?? Selector("nil"))
        } else {
            action["key"] = save ? "Return" : "Escape"
            action["key_code"] = save ? 36 : 53
            action["window_number"] = panel.windowNumber
            action["panel_was_key"] = panel.isKeyWindow
        }
        panels.append(["operation": operation, "class": String(describing: type(of: panel)), "title": panel.title,
                       "directory": panel.directoryURL!.path, "filename": panel.nameFieldStringValue,
                       "interaction": action, "picture": picture])
        checks[save ? "actual_production_save_panel_and_user_action" : "actual_production_cancel_user_action"] = true
        observe("before_native_" + operation + "_input", force: true)
        advance(save ? "saved-file" : "cancelled-download")
        if let button = button { button.performClick(nil) }
        else if let keyDown = keyDown, let keyUp = keyUp {
            NSApp.sendEvent(keyDown)
            NSApp.sendEvent(keyUp)
        }
        observe("after_native_" + operation + "_input", force: true)
    }

    private func partials() throws -> [String] {
        try FileManager.default.contentsOfDirectory(atPath: directory.path).filter { $0.hasPrefix(".cinematicum-download-") && $0.hasSuffix(".partial") }.sorted()
    }

    private func tick() {
        guard !finished else { return }
        let now = ProcessInfo.processInfo.systemUptime
        largestTickGap = max(largestTickGap, now - lastTick)
        lastTick = now
        observe("native_state_changed")
        if Date().timeIntervalSince(began) > timeout { finish("Timed out in actual native phase: " + phase); return }
        do {
            switch phase {
            case "loading":
                guard production.acceptanceReady && !startedScript else { return }
                startedScript = true
                advance("first-panel")
                production.acceptanceRun(script) { [weak self] result in
                    guard let self = self else { return }
                    switch result {
                    case .success(let value):
                        guard let result = value as? [String: Any], result["passed"] as? Bool == true else {
                            self.report["ui"] = value
                            self.finish("Actual web authoring/export controls failed before native panel acceptance")
                            return
                        }
                        self.ui = result
                    case .failure(let error): self.finish(error.localizedDescription)
                    }
                }
            case "first-panel":
                guard ui != nil, let panel = production.acceptancePanel, panel.isVisible else { return }
                guard panel.title == "Save CINEMATICUM export" && production.acceptanceDownloadCount == 1 else { throw failure("Expected exactly one production save-panel download") }
                guard panel.nameFieldStringValue == ui?["download_filename"] as? String else { throw failure("Production save panel did not receive the actual exported filename") }
                beginConfiguration(panel, operation: "save")
            case "save-directory":
                try configureName(save: true)
            case "save-button":
                try activatePanel(save: true)
            case "saved-file":
                let file = directory.appendingPathComponent(savedName)
                guard production.acceptancePanel == nil && production.acceptanceDownloadCount == 0 && production.acceptanceTemporaryCount == 0,
                      FileManager.default.fileExists(atPath: file.path) else { return }
                let data = try Data(contentsOf: file)
                guard !data.isEmpty else { throw failure("Production saved an empty download") }
                guard production.acceptanceSubtitle == "Saved " + savedName else { throw failure("Production save completion was not reported") }
                savedIdentity = ["path": file.path, "bytes": data.count, "sha256": acceptanceSHA(data)]
                checks["production_completed_download_and_published_destination"] = true
                checks["successful_download_released_temporary_and_owner"] = try partials().isEmpty
                advance("cancel-panel")
                production.acceptanceClickDownload { [weak self] result in
                    if case .failure(let error) = result { self?.finish(error.localizedDescription) }
                }
            case "cancel-panel":
                guard let panel = production.acceptancePanel, panel.isVisible else { return }
                guard panel.title == "Save CINEMATICUM export" && production.acceptanceDownloadCount == 1 else { throw failure("Cancel test did not enter the production save panel") }
                beginConfiguration(panel, operation: "cancel")
            case "cancel-directory":
                try configureName(save: false)
            case "cancel-button":
                try activatePanel(save: false)
            case "cancelled-download":
                guard production.acceptancePanel == nil && production.acceptanceDownloadCount == 0 && production.acceptanceTemporaryCount == 0 else { return }
                // Keep observing after the asynchronous download failure callback.
                guard Date().timeIntervalSince(phaseBegan) > 0.25 else { return }
                checks["cancel_creates_no_destination"] = !FileManager.default.fileExists(atPath: directory.appendingPathComponent(cancelledName).path)
                checks["cancel_releases_download_and_leaves_no_partial"] = try partials().isEmpty
                let saved = try Data(contentsOf: directory.appendingPathComponent(savedName))
                checks["cancel_preserves_completed_download"] = acceptanceSHA(saved) == savedIdentity?["sha256"] as? String
                finish(nil)
            default: throw failure("Unknown acceptance phase")
            }
        } catch { finish(error.localizedDescription) }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        finish("The acceptance application was asked to quit before the gate completed")
        return .terminateCancel
    }

    private func finish(_ error: String?) {
        guard !finished else { return }
        finished = true
        timer?.invalidate()
        observe("finished", force: true)
        if let error = error { report["error"] = error }
        if let ui = ui { report["ui"] = ui }
        if let savedIdentity = savedIdentity { report["saved_file"] = savedIdentity }
        report["helper_revision"] = 2
        report["scope"] = "Unchanged production StudioAppDelegate class: real NSSavePanel Save/Cancel through actual NSButton clicks or ordinary AppKit Return/Escape events, and real WKDownload; isolated startup, not installed-bundle UI"
        report["checks"] = checks
        report["panels"] = panels
        report["phase"] = phase
        report["active_downloads"] = production.acceptanceDownloadCount
        report["temporary_download_owners"] = production.acceptanceTemporaryCount
        report["subtitle"] = production.acceptanceSubtitle
        report["observations"] = observations
        report["discarded_observations"] = discardedObservations
        report["largest_polling_gap_seconds"] = largestTickGap
        if let sheet = production.acceptanceSheet { report["attached_sheet_diagnostics"] = acceptanceWindowDescription(sheet) }
        if let panel = pendingPanel { report["retained_panel_diagnostics"] = acceptanceWindowDescription(panel) }
        report["elapsed_seconds"] = Date().timeIntervalSince(began)
        report["passed"] = error == nil && checks.count == 7 && checks.values.allSatisfy { $0 }
        do {
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
        } catch {
            fputs("Could not serialize native acceptance result: \(error)\n", stderr)
            exit(2)
        }
        exit(report["passed"] as? Bool == true ? 0 : 1)
    }
}

private func acceptanceArgument(_ name: String) -> String? {
    guard let index = CommandLine.arguments.firstIndex(of: name), index + 1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[index + 1]
}

guard acceptanceArgument("--mode") == "download",
      let rawOrigin = acceptanceArgument("--url"), let origin = URL(string: rawOrigin),
      origin.scheme == "http", origin.host == "127.0.0.1", origin.port != nil,
      let rawDirectory = acceptanceArgument("--evidence"), rawDirectory.hasPrefix("/"),
      let scriptPath = acceptanceArgument("--script") else {
    fputs("Usage: production-native-acceptance --mode download --url http://127.0.0.1:PORT/ --evidence /owned/directory --script /fixture-workflow.js [--timeout 40]\n", stderr)
    exit(2)
}
do {
    let script = try String(contentsOfFile: scriptPath, encoding: .utf8)
    let delegate = ProductionDownloadAcceptance(origin: origin, directory: URL(fileURLWithPath: rawDirectory, isDirectory: true),
                                               script: script, timeout: Double(acceptanceArgument("--timeout") ?? "40") ?? 40)
    let acceptanceApplication = NSApplication.shared
    acceptanceApplication.delegate = delegate
    acceptanceApplication.setActivationPolicy(.regular)
    withExtendedLifetime(delegate) { acceptanceApplication.run() }
} catch {
    fputs("Native acceptance startup failed: \(error)\n", stderr)
    exit(2)
}

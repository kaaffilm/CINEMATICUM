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
            timer = Timer.scheduledTimer(withTimeInterval: 0.04, repeats: true) { [weak self] _ in self?.tick() }
        } catch { finish(error.localizedDescription) }
    }

    private func failure(_ message: String) -> NSError {
        NSError(domain: "ProductionAcceptance", code: 3, userInfo: [NSLocalizedDescriptionKey: message])
    }

    private func advance(_ next: String) { phase = next; phaseBegan = Date() }

    private func partials() throws -> [String] {
        try FileManager.default.contentsOfDirectory(atPath: directory.path).filter { $0.hasPrefix(".cinematicum-download-") && $0.hasSuffix(".partial") }.sorted()
    }

    private func tick() {
        guard !finished else { return }
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
                pendingPanel = panel
                panel.directoryURL = directory
                panel.nameFieldStringValue = savedName
                advance("save-button")
            case "save-button":
                guard Date().timeIntervalSince(phaseBegan) >= 0.15, let panel = pendingPanel,
                      panel === production.acceptancePanel, panel.isVisible else { return }
                guard panel.directoryURL?.standardizedFileURL == directory.standardizedFileURL,
                      let button = acceptanceButton(panel, save: true) else { return }
                let picture = try acceptancePanelPicture(panel, destination: directory.appendingPathComponent("save-panel.png"))
                panels.append(["operation": "save", "class": String(describing: type(of: panel)), "title": panel.title,
                               "directory": panel.directoryURL!.path, "filename": panel.nameFieldStringValue,
                               "button_title": button.title, "button_action": NSStringFromSelector(button.action ?? Selector("nil")),
                               "picture": picture])
                checks["actual_production_save_panel_and_button"] = true
                advance("saved-file")
                button.performClick(nil)
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
                pendingPanel = panel
                panel.directoryURL = directory
                panel.nameFieldStringValue = cancelledName
                advance("cancel-button")
            case "cancel-button":
                guard Date().timeIntervalSince(phaseBegan) >= 0.15, let panel = pendingPanel,
                      panel === production.acceptancePanel, panel.isVisible else { return }
                guard let button = acceptanceButton(panel, save: false) else { return }
                let picture = try acceptancePanelPicture(panel, destination: directory.appendingPathComponent("cancel-panel.png"))
                panels.append(["operation": "cancel", "class": String(describing: type(of: panel)), "title": panel.title,
                               "directory": panel.directoryURL?.path ?? "", "filename": panel.nameFieldStringValue,
                               "button_title": button.title, "button_action": NSStringFromSelector(button.action ?? Selector("nil")),
                               "picture": picture])
                checks["actual_production_cancel_button"] = true
                advance("cancelled-download")
                button.performClick(nil)
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
        if let error = error { report["error"] = error }
        if let ui = ui { report["ui"] = ui }
        if let savedIdentity = savedIdentity { report["saved_file"] = savedIdentity }
        report["scope"] = "Unchanged production StudioAppDelegate class: real NSSavePanel Save/Cancel buttons and real WKDownload; isolated startup, not installed-bundle UI"
        report["checks"] = checks
        report["panels"] = panels
        report["phase"] = phase
        report["active_downloads"] = production.acceptanceDownloadCount
        report["temporary_download_owners"] = production.acceptanceTemporaryCount
        if let panel = production.acceptancePanel {
            report["pending_panel_diagnostics"] = [
                "class": String(describing: type(of: panel)), "title": panel.title,
                "visible": panel.isVisible, "directory": panel.directoryURL?.path ?? "",
                "filename": panel.nameFieldStringValue,
                "buttons": acceptanceButtons(panel.contentView).map {
                    ["title": $0.title, "enabled": $0.isEnabled, "key_equivalent": $0.keyEquivalent,
                     "action": NSStringFromSelector($0.action ?? Selector("nil"))] as [String: Any]
                }
            ] as [String: Any]
        }
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

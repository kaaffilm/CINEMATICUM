import Cocoa
import WebKit

// A native window with an app-owned local media engine. The web view is never
// allowed to navigate to another server, port, local file, or automatic popup.
final class StudioAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
    WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var loadingLabel: NSTextField!
    private var spinner: NSProgressIndicator!
    private var server: Process?
    private var outputPipe: Pipe?
    private var serverURL: URL?
    private var pendingOutput = ""
    private var recentOutput = ""
    private var quitting = false
    private var repliedToQuit = false
    private var fatalErrorShown = false
    private var activeDownloads: [ObjectIdentifier: WKDownload] = [:]
    private var downloadFiles: [ObjectIdentifier: (temporary: URL, destination: URL)] = [:]
    private let workspace = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Movies/CINEMATICUM", isDirectory: true)

    func applicationDidFinishLaunching(_ notification: Notification) {
        makeMenus()
        makeWindow()
        launchServer()
    }

    private func makeWindow() {
        let visible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0,
                            width: min(1440, visible.width), height: min(880, visible.height - 30)),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "CINEMATICUM Studio"
        window.contentMinSize = NSSize(width: 1000, height: 700)
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(calibratedWhite: 0.06, alpha: 1)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        config.mediaTypesRequiringUserActionForPlayback = []
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = false
        window.contentView!.addSubview(webView)

        loadingLabel = NSTextField(labelWithString: "Starting CINEMATICUM…")
        loadingLabel.textColor = .secondaryLabelColor
        loadingLabel.font = .systemFont(ofSize: 16, weight: .medium)
        loadingLabel.translatesAutoresizingMaskIntoConstraints = false
        spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(loadingLabel)
        window.contentView!.addSubview(spinner)
        NSLayoutConstraint.activate([
            loadingLabel.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor),
            loadingLabel.centerYAnchor.constraint(equalTo: window.contentView!.centerYAnchor),
            spinner.centerXAnchor.constraint(equalTo: loadingLabel.centerXAnchor),
            spinner.bottomAnchor.constraint(equalTo: loadingLabel.topAnchor, constant: -18)
        ])
        showBusy("Starting CINEMATICUM…")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func showBusy(_ message: String?) {
        let busy = message != nil
        webView.isHidden = busy
        loadingLabel.isHidden = !busy
        spinner.isHidden = !busy
        if let message = message {
            loadingLabel.stringValue = message
            spinner.startAnimation(nil)
        } else {
            spinner.stopAnimation(nil)
        }
    }

    private func launchServer() {
        guard let runtime = Bundle.main.resourceURL?.appendingPathComponent("studio", isDirectory: true) else {
            fatal("The application bundle is incomplete.")
            return
        }
        let script = runtime.appendingPathComponent("server.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            fatal("The bundled media engine is missing. Rebuild CINEMATICUM Studio.")
            return
        }
        let candidates = ["/opt/homebrew/bin/python3", "/usr/bin/python3",
                          "/Applications/Xcode.app/Contents/Developer/usr/bin/python3", "/usr/local/bin/python3"]
        guard let python = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            fatal("Python 3.9 or newer is required to start the local media engine.")
            return
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-B", "-u", script.path, "--workspace", workspace.path, "--port", "0"]
        process.currentDirectoryURL = runtime
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
            + (environment["PATH"] ?? "")
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        environment.removeValue(forKey: "PYTHONPATH")
        environment.removeValue(forKey: "PYTHONHOME")
        process.environment = environment
        process.standardInput = FileHandle.nullDevice
        let pipe = Pipe()
        outputPipe = pipe
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.consumeOutput(data) }
        }
        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.outputPipe?.fileHandleForReading.readabilityHandler = nil
                if self.quitting {
                    self.finishQuit()
                } else {
                    self.fatal("The media engine stopped (exit \(process.terminationStatus)).\n\n" + self.recentOutput)
                }
            }
        }
        server = process
        do {
            try process.run()
        } catch {
            server = nil
            pipe.fileHandleForReading.readabilityHandler = nil
            fatal("Could not start the local media engine: \(error.localizedDescription)")
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            guard let self = self, self.serverURL == nil, !self.quitting, !self.fatalErrorShown else { return }
            self.fatal("The media engine did not start within 30 seconds.\n\n" + self.recentOutput)
        }
    }

    private func consumeOutput(_ data: Data) {
        let text = String(decoding: data, as: UTF8.self)
        recentOutput = String((recentOutput + text).suffix(8192))
        pendingOutput += text
        while let newline = pendingOutput.firstIndex(of: "\n") {
            let line = String(pendingOutput[..<newline]).trimmingCharacters(in: .whitespacesAndNewlines)
            pendingOutput.removeSubrange(...newline)
            let prefix = "CINEMATICUM editor: "
            guard serverURL == nil, line.hasPrefix(prefix) else { continue }
            let raw = String(line.dropFirst(prefix.count))
            guard let url = URL(string: raw), url.scheme == "http", url.host == "127.0.0.1",
                  let port = url.port, (1...65535).contains(port), url.user == nil, url.password == nil,
                  url.query == nil, url.fragment == nil, url.path.isEmpty || url.path == "/" else {
                fatal("The media engine returned an invalid local address.")
                return
            }
            serverURL = url
            if !quitting { webView.load(URLRequest(url: url)) }
        }
        if pendingOutput.count > 8192 { pendingOutput = String(pendingOutput.suffix(8192)) }
    }

    private func isLocal(_ url: URL?) -> Bool {
        guard let url = url, let base = serverURL else { return false }
        return url.scheme == "http" && url.host == "127.0.0.1" && url.port == base.port
            && url.user == nil && url.password == nil
    }

    private func isLocalBlob(_ url: URL?) -> Bool {
        guard let url = url, url.scheme == "blob", let base = serverURL else { return false }
        return url.absoluteString.hasPrefix("blob:" + base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/")
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        if navigationAction.shouldPerformDownload && (isLocal(url) || isLocalBlob(url)) {
            decisionHandler(.download)
        } else if isLocal(url) {
            decisionHandler(.allow)
        } else {
            decisionHandler(.cancel)
            if navigationAction.navigationType == .linkActivated, let url = url,
               ["https", "http"].contains(url.scheme ?? "") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        guard isLocal(navigationResponse.response.url) || isLocalBlob(navigationResponse.response.url) else {
            decisionHandler(.cancel); return
        }
        let response = navigationResponse.response as? HTTPURLResponse
        let attachment = response?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased().hasPrefix("attachment") == true
        decisionHandler(attachment || !navigationResponse.canShowMIMEType ? .download : .allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if !quitting && isLocal(webView.url) { showBusy(nil) }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled && !quitting {
            fatal("Could not open the local editor: \(error.localizedDescription)")
        }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        if !quitting { fatal("The editor view stopped. Reopen CINEMATICUM Studio to recover saved projects.") }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if isLocal(navigationAction.request.url) {
            webView.load(navigationAction.request)
        } else if navigationAction.navigationType == .linkActivated, let url = navigationAction.request.url,
                  ["http", "https"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        guard isLocal(frame.request.url), !quitting else { completionHandler(nil); return }
        let panel = NSOpenPanel()
        panel.title = "Import into CINEMATICUM"
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        guard isLocal(frame.request.url), !quitting else { completionHandler(); return }
        let alert = makeAlert(message)
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        guard isLocal(frame.request.url), !quitting else { completionHandler(false); return }
        let alert = makeAlert(message)
        alert.addButton(withTitle: "Continue")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { response in completionHandler(response == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        guard isLocal(frame.request.url), !quitting else { completionHandler(nil); return }
        let alert = makeAlert(prompt)
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 360, height: 24))
        input.stringValue = defaultText ?? ""
        alert.accessoryView = input
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.window.initialFirstResponder = input
        alert.beginSheetModal(for: window) { response in
            completionHandler(response == .alertFirstButtonReturn ? input.stringValue : nil)
        }
    }

    private func registerDownload(_ download: WKDownload) {
        activeDownloads[ObjectIdentifier(download)] = download
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        registerDownload(download)
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        registerDownload(download)
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard !quitting, isLocal(response.url) || isLocalBlob(response.url) else { completionHandler(nil); return }
        let panel = NSSavePanel()
        panel.title = "Save CINEMATICUM export"
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = URL(fileURLWithPath: suggestedFilename).lastPathComponent
        panel.directoryURL = FileManager.default.urls(for: .moviesDirectory, in: .userDomainMask).first
        panel.beginSheetModal(for: window) { [weak self] response in
            guard let self = self, response == .OK, let destination = panel.url else {
                completionHandler(nil); return
            }
            // WebKit requires a nonexistent destination. Download beside the
            // selected file and replace it only after successful completion.
            let temporary = destination.deletingLastPathComponent()
                .appendingPathComponent(".cinematicum-download-" + UUID().uuidString + ".partial")
            self.downloadFiles[ObjectIdentifier(download)] = (temporary, destination)
            completionHandler(temporary)
        }
    }

    func download(_ download: WKDownload, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest, decisionHandler: @escaping (WKDownload.RedirectPolicy) -> Void) {
        decisionHandler(isLocal(request.url) ? .allow : .cancel)
    }

    func downloadDidFinish(_ download: WKDownload) {
        let key = ObjectIdentifier(download)
        activeDownloads.removeValue(forKey: key)
        guard let files = downloadFiles.removeValue(forKey: key) else { return }
        do {
            if FileManager.default.fileExists(atPath: files.destination.path) {
                _ = try FileManager.default.replaceItemAt(files.destination, withItemAt: files.temporary)
            } else {
                try FileManager.default.moveItem(at: files.temporary, to: files.destination)
            }
            window.subtitle = "Saved " + files.destination.lastPathComponent
        } catch {
            showError("The export finished, but saving it failed: \(error.localizedDescription)\n\nThe complete file remains at \(files.temporary.path)")
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let key = ObjectIdentifier(download)
        activeDownloads.removeValue(forKey: key)
        if let files = downloadFiles.removeValue(forKey: key) {
            try? FileManager.default.removeItem(at: files.temporary)
        }
        if !quitting && (error as NSError).code != NSURLErrorCancelled {
            showError("The export could not be downloaded: \(error.localizedDescription)")
        }
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        NSApp.terminate(nil)
        return false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let process = server, process.isRunning else { return .terminateNow }
        if quitting { return .terminateLater }
        quitting = true
        showBusy("Saving and closing…")
        if isLocal(webView.url) && !fatalErrorShown {
            webView.callAsyncJavaScript(
                "if (typeof state !== 'undefined' && state.dirty && typeof saveProject === 'function') { await saveProject(false); } return true;",
                arguments: [:], in: nil, in: .page
            ) { [weak self] result in
                guard let self = self, !self.repliedToQuit else { return }
                switch result {
                case .success: self.stopOwnedServer()
                case .failure(let error):
                    self.quitting = false
                    self.showBusy(nil)
                    sender.reply(toApplicationShouldTerminate: false)
                    self.showError("Changes could not be saved. The editor is still open.\n\n\(error.localizedDescription)")
                }
            }
        } else {
            stopOwnedServer()
        }
        return .terminateLater
    }

    private func stopOwnedServer() {
        showBusy("Stopping media jobs…")
        for download in activeDownloads.values { download.cancel { _ in } }
        if let process = server, process.isRunning {
            // server.py handles SIGTERM, cancels its own workers, joins them,
            // then exits. Wait for that exit instead of orphaning a render.
            process.terminate()
        } else {
            // applicationShouldTerminate must return .terminateLater before
            // replying, including the race where the child just exited.
            DispatchQueue.main.async { [weak self] in self?.finishQuit() }
        }
    }

    private func finishQuit() {
        guard !repliedToQuit else { return }
        repliedToQuit = true
        NSApp.reply(toApplicationShouldTerminate: true)
    }

    func applicationWillTerminate(_ notification: Notification) {
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        if let process = server, process.isRunning { process.terminate() }
    }

    private func makeAlert(_ message: String) -> NSAlert {
        let alert = NSAlert()
        alert.messageText = "CINEMATICUM Studio"
        alert.informativeText = message
        return alert
    }

    private func showError(_ message: String) {
        let alert = makeAlert(message)
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window)
    }

    private func fatal(_ message: String) {
        guard !fatalErrorShown, !quitting else { return }
        fatalErrorShown = true
        showBusy("CINEMATICUM could not continue")
        spinner.stopAnimation(nil)
        let alert = makeAlert(message)
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Quit")
        alert.beginSheetModal(for: window) { _ in NSApp.terminate(nil) }
    }

    @objc private func saveProject(_ sender: Any?) {
        guard isLocal(webView.url), !quitting else { return }
        webView.evaluateJavaScript("document.getElementById('save-project')?.click()", completionHandler: nil)
    }

    @objc private func exportProject(_ sender: Any?) {
        guard isLocal(webView.url), !quitting else { return }
        webView.evaluateJavaScript("document.getElementById('export-button')?.click()", completionHandler: nil)
    }

    @objc private func showProjects(_ sender: Any?) {
        NSWorkspace.shared.open(workspace)
    }

    @objc private func undoProject(_ sender: Any?) { editHistory(redo: false) }
    @objc private func redoProject(_ sender: Any?) { editHistory(redo: true) }

    private func editHistory(redo: Bool) {
        guard isLocal(webView.url), !quitting else { return }
        webView.evaluateJavaScript("Boolean(document.activeElement?.matches('input,textarea,[contenteditable]'))") { [weak self] value, _ in
            guard let self = self else { return }
            if (value as? Bool) == true {
                NSApp.sendAction(Selector(redo ? "redo:" : "undo:"), to: nil, from: self)
            } else {
                self.webView.evaluateJavaScript("if (typeof undo === 'function') undo(\(redo ? "true" : "false"))", completionHandler: nil)
            }
        }
    }

    private func makeMenus() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About CINEMATICUM Studio", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide CINEMATICUM Studio", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit CINEMATICUM Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let fileItem = NSMenuItem(title: "File", action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: "File")
        let save = fileMenu.addItem(withTitle: "Save Project", action: #selector(saveProject(_:)), keyEquivalent: "s")
        save.target = self
        let export = fileMenu.addItem(withTitle: "Export…", action: #selector(exportProject(_:)), keyEquivalent: "e")
        export.target = self
        let projects = fileMenu.addItem(withTitle: "Show Projects in Finder", action: #selector(showProjects(_:)), keyEquivalent: "")
        projects.target = self
        fileMenu.addItem(.separator())
        fileMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        fileItem.submenu = fileMenu
        main.addItem(fileItem)

        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        let undo = editMenu.addItem(withTitle: "Undo", action: #selector(undoProject(_:)), keyEquivalent: "z")
        undo.target = self
        let redo = editMenu.addItem(withTitle: "Redo", action: #selector(redoProject(_:)), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        redo.target = self
        editMenu.addItem(.separator())
        for (title, action, key) in [("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editItem.submenu = editMenu
        main.addItem(editItem)

        let windowItem = NSMenuItem(title: "Window", action: nil, keyEquivalent: "")
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        let fullScreen = windowMenu.addItem(withTitle: "Toggle Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fullScreen.keyEquivalentModifierMask = [.control, .command]
        windowItem.submenu = windowMenu
        main.addItem(windowItem)
        NSApp.windowsMenu = windowMenu
        NSApp.mainMenu = main
    }
}

let application = NSApplication.shared
let applicationDelegate = StudioAppDelegate()
application.delegate = applicationDelegate
application.setActivationPolicy(.regular)
application.run()

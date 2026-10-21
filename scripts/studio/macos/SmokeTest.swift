// Native browser integration test; never linked into the production application.
// Compile separately on macOS:
// xcrun swiftc scripts/studio/macos/SmokeTest.swift -o /tmp/cinematicum-webkit-smoke
import AppKit
import Foundation
import WebKit
import Darwin

@available(macOS 11.3, *)
final class SmokeDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler, WKDownloadDelegate {
    let url: URL
    let output: URL
    let timeout: Double
    let scriptOverride: String?
    let downloadDirectory: URL?
    var window: NSWindow!
    var webView: WKWebView!
    var pageErrors = [String]()
    var started = false
    var finishing = false
    var finished = false
    var activeDownloads: [ObjectIdentifier: WKDownload] = [:]
    var downloadTargets: [ObjectIdentifier: URL] = [:]
    var downloadEvidence = [[String: Any]]()
    var downloadErrors = [String]()

    init(url: URL, output: URL, timeout: Double, scriptOverride: String? = nil, downloadDirectory: URL? = nil) {
        self.url = url
        self.output = output
        self.timeout = timeout
        self.scriptOverride = scriptOverride
        self.downloadDirectory = downloadDirectory?.standardizedFileURL.resolvingSymlinksInPath()
        super.init()
    }

    private func isLocal(_ candidate: URL?) -> Bool {
        guard let candidate = candidate else { return false }
        return candidate.scheme == url.scheme && candidate.host == url.host && candidate.port == url.port
            && candidate.user == nil && candidate.password == nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard downloadDirectory != nil else { decisionHandler(.allow); return }
        guard isLocal(navigationAction.request.url) else { decisionHandler(.cancel); return }
        decisionHandler(downloadDirectory != nil && navigationAction.shouldPerformDownload ? .download : .allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        guard downloadDirectory != nil else { decisionHandler(.allow); return }
        guard isLocal(navigationResponse.response.url) else { decisionHandler(.cancel); return }
        let response = navigationResponse.response as? HTTPURLResponse
        let attachment = response?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased().hasPrefix("attachment") == true
        decisionHandler(downloadDirectory != nil && (attachment || !navigationResponse.canShowMIMEType) ? .download : .allow)
    }

    private func register(_ download: WKDownload) {
        activeDownloads[ObjectIdentifier(download)] = download
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { register(download) }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { register(download) }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard let directory = downloadDirectory, isLocal(response.url) else { completionHandler(nil); return }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            // Test downloads are restricted to this explicit evidence directory.
            // A unique name cannot overwrite a user's or a prior test's file.
            let name = URL(fileURLWithPath: suggestedFilename).lastPathComponent
            let target = directory.appendingPathComponent("ENGINE_TEST_" + UUID().uuidString + "_" + name)
            guard target.deletingLastPathComponent().standardizedFileURL == directory,
                  !FileManager.default.fileExists(atPath: target.path) else {
                throw NSError(domain: "CinematicumSmoke", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "Unsafe or existing test download destination."])
            }
            let key = ObjectIdentifier(download)
            downloadTargets[key] = target
            downloadEvidence.append(["url": response.url?.absoluteString ?? "", "path": target.path,
                                     "suggested_filename": name, "state": "started"])
            completionHandler(target)
        } catch {
            downloadErrors.append(String(describing: error))
            completionHandler(nil)
        }
    }

    func download(_ download: WKDownload, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest, decisionHandler: @escaping (WKDownload.RedirectPolicy) -> Void) {
        decisionHandler(isLocal(request.url) ? .allow : .cancel)
    }

    func downloadDidFinish(_ download: WKDownload) {
        let key = ObjectIdentifier(download)
        activeDownloads.removeValue(forKey: key)
        guard let target = downloadTargets.removeValue(forKey: key) else { return }
        do {
            let size = try target.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            if let index = downloadEvidence.firstIndex(where: { ($0["path"] as? String) == target.path }) {
                downloadEvidence[index]["state"] = "completed"
                downloadEvidence[index]["bytes"] = size
            }
        } catch { downloadErrors.append(String(describing: error)) }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let key = ObjectIdentifier(download)
        activeDownloads.removeValue(forKey: key)
        if let target = downloadTargets.removeValue(forKey: key) { try? FileManager.default.removeItem(at: target) }
        downloadErrors.append(String(describing: error))
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.userContentController.add(self, name: "smokeError")
        configuration.userContentController.addUserScript(WKUserScript(source: """
        window.addEventListener('error', event => window.webkit.messageHandlers.smokeError.postMessage(String(event.message) + ' @ ' + String(event.filename) + ':' + event.lineno));
        window.addEventListener('unhandledrejection', event => window.webkit.messageHandlers.smokeError.postMessage('Unhandled rejection: ' + String(event.reason)));
        """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        // Test-only sizing allows native acceptance at the application's
        // minimum supported content size as well as the normal desktop size.
        let environment = ProcessInfo.processInfo.environment
        let width = Double(environment["CINEMATICUM_SMOKE_WIDTH"] ?? "1440") ?? 0
        let height = Double(environment["CINEMATICUM_SMOKE_HEIGHT"] ?? "960") ?? 0
        guard width.isFinite, height.isFinite, (1000...2560).contains(width), (700...1600).contains(height) else {
            emit(["passed": false, "error": "Native test viewport must be 1000–2560 by 700–1600 pixels."])
            return
        }
        webView = WKWebView(frame: NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)), configuration: configuration)
        webView.navigationDelegate = self
        window = NSWindow(contentRect: webView.frame, styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "CINEMATICUM browser test — synthetic test media"
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView.load(URLRequest(url: url))
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) { [weak self] in
            self?.captureAndFinish(["passed": false, "error": "Native browser test exceeded its time limit."])
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        pageErrors.append(String(describing: message.body))
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        captureAndFinish(["passed": false, "error": "Navigation failed: \(error)"])
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        captureAndFinish(["passed": false, "error": "Initial navigation failed: \(error)"])
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard !started else { return }
        started = true
        // Only DOM controls are operated. No application state or HTTP mutations
        // are called directly, and no production test globals are introduced.
        let script = scriptOverride ?? #"""
        const began = performance.now(), steps = [];
        const $ = selector => document.querySelector(selector);
        const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
        const until = async (predicate, label, milliseconds=1800) => {
          const end = performance.now() + milliseconds;
          while (performance.now() < end) {
            if (predicate()) return;
            await sleep(50);
          }
          throw new Error(label + '; toast=' + ($('#toast')?.textContent || '') + '; job=' + ($('#job-label')?.textContent || '') + ' / ' + ($('#job-detail')?.textContent || ''));
        };
        const click = selector => {
          const element = $(selector);
          if (!element || element.disabled) throw new Error('Unavailable control: ' + selector);
          element.click();
        };
        const field = (name, value) => {
          const element = $('[data-field="' + name + '"]');
          if (!element) throw new Error('Missing inspector field: ' + name);
          element.value = String(value);
          element.dispatchEvent(new Event(element.type === 'range' ? 'input' : 'change', {bubbles:true}));
          if (element.type === 'range') element.dispatchEvent(new Event('change', {bubbles:true}));
        };
        try {
          await until(() => $('.media-item[data-asset]') && $('#viewer-project')?.textContent.includes('ENGINE TEST'), 'Editor did not bootstrap the test project', 6500);
          steps.push('bootstrap');
          const asset = $('.media-item[data-asset]');
          const assetID = asset.dataset.asset;
          asset.dispatchEvent(new MouseEvent('dblclick', {bubbles:true, view:window, button:0}));
          await until(() => document.querySelectorAll('.timeline-clip[data-type="clip"]').length === 1, 'Double-click did not create a timeline clip');
          steps.push('add_clip_from_media_bin');
          click('#play-button');
          await until(() => $('#timecode').textContent !== '00:00:00:00', 'Source playback did not advance');
          if ($('#play-button').getAttribute('aria-label') === 'Pause timeline') click('#play-button');
          const playedTimecode = $('#timecode').textContent;
          steps.push('play_source');
          click('#jump-start');
          const ruler = $('.ruler-lane'), rect = ruler.getBoundingClientRect();
          ruler.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, button:0, pointerId:1, isPrimary:true, clientX:rect.left+24, clientY:rect.top+5}));
          window.dispatchEvent(new PointerEvent('pointerup', {bubbles:true, button:0, pointerId:1, isPrimary:true}));
          await until(() => $('#timecode').textContent === '00:00:00:06', 'Timeline ruler did not scrub to frame six');
          steps.push('scrub_timeline');
          await until(() => {
            const canvas = $('#preview-canvas'), pixels = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
            for (let i=0; i<pixels.length; i+=16) if (pixels[i]+pixels[i+1]+pixels[i+2]>80) return true;
            return false;
          }, 'Source viewer never decoded a picture');
          steps.push('decode_source_picture');
          click('[data-mode="composite"]');
          click('[data-graph-action="masked"]');
          await until(() => document.querySelectorAll('[data-node]').length === 4, 'Masked correction graph was not created');
          const featherSelector = '[data-node-param="feather"][type="number"]';
          const originalFeather = Number($(featherSelector).value);
          $(featherSelector).value = '.35';
          $(featherSelector).dispatchEvent(new Event('change', {bubbles:true}));
          click('#undo-button');
          await until(() => Number($(featherSelector)?.value) === originalFeather, 'Undo did not restore graph parameter');
          $(featherSelector).value = '.25';
          $(featherSelector).dispatchEvent(new Event('change', {bubbles:true}));
          const mergeOutput = $('[data-graph-output]').value;
          $('[data-graph-output]').value = 'source';
          $('[data-graph-output]').dispatchEvent(new Event('change', {bubbles:true}));
          click('#undo-button');
          await until(() => $('[data-graph-output]').value === mergeOutput, 'Undo did not restore graph output');
          steps.push('author_masked_node_graph_and_undo');
          click('[data-mode="color"]');
          field('grade.exposure', .75);
          if ($('#save-state').textContent !== 'UNSAVED') throw new Error('Grade edit did not mark the project dirty');
          steps.push('change_exposure');
          // Exercise the portable raster-title path used by Homebrew FFmpeg.
          click('#add-title');
          field('text', 'ENGINE TEST');
          field('size', 11);
          field('start', 0);
          field('duration', 12);
          field('fade', 2);
          steps.push('add_editable_title');
          click('#save-project');
          await until(() => $('#save-state').textContent === 'SAVED LOCALLY', 'Save did not finish', 4000);
          steps.push('save_project');
          click('#preview-render');
          await until(() => $('#job-label').textContent === 'Render complete', 'Preview render did not complete', 6500);
          const video = $('#render-video');
          await until(() => !video.hidden && video.readyState >= 2 && video.duration > 0, 'Rendered video did not decode', 2500);
          if (!video.getAttribute('src').includes('/exports/')) throw new Error('Preview is not an exported media file');
          steps.push('render_and_decode_export');
          await video.play();
          await until(() => video.currentTime > .05, 'Rendered video did not play');
          video.pause();
          steps.push('play_export');
          const playback = {src:video.getAttribute('src'), currentSrc:video.currentSrc,
                            duration:video.duration, time:video.currentTime};
          const editedClip = $('.timeline-clip[data-type="clip"]');
          editedClip.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,button:0,pointerId:2,isPrimary:true}));
          window.dispatchEvent(new PointerEvent('pointerup', {bubbles:true,button:0,pointerId:2,isPrimary:true}));
          click('[data-mode="composite"]');
          const graphBounds = $('.compositor-stage').getBoundingClientRect();
          if (graphBounds.width < 200 || graphBounds.height < 100 || document.querySelectorAll('[data-node]').length !== 4)
            throw new Error('Compositor workspace was not visibly laid out');
          steps.push('inspect_visible_node_workspace');
          return {passed:true, steps, project_id:$('#project-select').value, asset_id:assetID,
                  source_playback_timecode:playedTimecode, scrub_timecode:'00:00:00:06',
                  video_src:playback.src, video_current_src:playback.currentSrc,
                  video_duration:playback.duration, video_current_time:playback.time,
                  job_label:$('#job-label').textContent, toast:$('#toast').textContent,
                  elapsed_ms:Math.round(performance.now()-began)};
        } catch(error) {
          return {passed:false, steps, error:String(error), toast:$('#toast')?.textContent || '',
                  job_label:$('#job-label')?.textContent || '', job_detail:$('#job-detail')?.textContent || '',
                  timecode:$('#timecode')?.textContent || '', elapsed_ms:Math.round(performance.now()-began)};
        }
        """#
        webView.callAsyncJavaScript(script, arguments: [:], in: nil, in: .page) { [weak self] result in
            switch result {
            case .success(let value):
                self?.finishAfterDownloads(value as? [String: Any] ?? ["passed": false, "error": "JavaScript returned no test result."])
            case .failure(let error):
                self?.captureAndFinish(["passed": false, "error": "Browser execution failed: \(error)"])
            }
        }
    }

    func finishAfterDownloads(_ report: [String: Any], attempt: Int = 0) {
        guard !finishing else { return }
        let expectsDownload = report["expect_download"] as? Bool == true
        if expectsDownload && downloadErrors.isEmpty && (activeDownloads.count > 0 || downloadEvidence.isEmpty) && attempt < 80 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in
                self?.finishAfterDownloads(report, attempt: attempt + 1)
            }
            return
        }
        var result = report
        if expectsDownload && (downloadEvidence.isEmpty || !activeDownloads.isEmpty || !downloadErrors.isEmpty
            || downloadEvidence.contains(where: { ($0["state"] as? String) != "completed" })) {
            result["passed"] = false
            result["download_error"] = downloadErrors.isEmpty ? "Native download did not complete." : downloadErrors.joined(separator: "; ")
        }
        captureAndFinish(result)
    }

    func captureAndFinish(_ initial: [String: Any]) {
        guard !finishing else { return }
        finishing = true
        var report = initial
        report["page_errors"] = pageErrors
        if downloadDirectory != nil {
            report["downloads"] = downloadEvidence
            report["download_errors"] = downloadErrors
            report["download_destination_policy"] = "explicit test evidence directory; no save panel is simulated"
        }
        if !pageErrors.isEmpty { report["passed"] = false }
        report["screenshot"] = output.path
        let config = WKSnapshotConfiguration()
        config.rect = webView.bounds
        webView.takeSnapshot(with: config) { [weak self] image, error in
            guard let self = self else { return }
            do {
                guard let data = image?.tiffRepresentation,
                      let bitmap = NSBitmapImageRep(data: data),
                      let png = bitmap.representation(using: .png, properties: [:]) else {
                    throw NSError(domain: "CinematicumSmoke", code: 1, userInfo: [NSLocalizedDescriptionKey: "WebKit snapshot failed: \(String(describing: error))"])
                }
                try FileManager.default.createDirectory(at: self.output.deletingLastPathComponent(), withIntermediateDirectories: true)
                try png.write(to: self.output, options: .atomic)
                report["screenshot_bytes"] = png.count
            } catch {
                report["passed"] = false
                report["snapshot_error"] = String(describing: error)
            }
            self.emit(report)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            var fallback = report
            fallback["passed"] = false
            fallback["snapshot_error"] = "Timed out capturing WebKit view."
            self?.emit(fallback)
        }
    }

    func emit(_ result: [String: Any]) {
        guard !finished else { return }
        finished = true
        if let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), let line = String(data: data, encoding: .utf8) {
            print(line)
            fflush(stdout)
        }
        exit(result["passed"] as? Bool == true ? 0 : 1)
    }
}

func argument(_ name: String) -> String? {
    guard let index = CommandLine.arguments.firstIndex(of: name), index+1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[index+1]
}

if #available(macOS 11.3, *) {
    guard let raw = argument("--url"), let url = URL(string: raw), url.scheme == "http", ["127.0.0.1", "localhost"].contains(url.host ?? ""),
          let destination = argument("--output") else {
        fputs("Usage: cinematicum-webkit-smoke --url http://127.0.0.1:PORT --output screenshot.png [--timeout 14] [--download-dir explicit-test-directory]\n", stderr)
        exit(2)
    }
    var scriptOverride: String? = nil
    if let scriptPath = argument("--script") {
        do { scriptOverride = try String(contentsOfFile: scriptPath, encoding: .utf8) }
        catch { fputs("Could not read the requested test script: \(error)\n", stderr); exit(2) }
    }
    let downloads = argument("--download-dir").map { URL(fileURLWithPath: $0, isDirectory: true) }
    let delegate = SmokeDelegate(url: url, output: URL(fileURLWithPath: destination), timeout: Double(argument("--timeout") ?? "14") ?? 14, scriptOverride: scriptOverride, downloadDirectory: downloads)
    let application = NSApplication.shared
    application.setActivationPolicy(.regular)
    application.delegate = delegate
    withExtendedLifetime(delegate) {
        application.run()
    }
} else {
    fputs("The WebKit smoke test requires macOS 11.3 or newer.\n", stderr)
    exit(2)
}

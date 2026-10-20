// Native browser integration test; never linked into the production application.
// Compile separately on macOS:
// xcrun swiftc scripts/studio/macos/SmokeTest.swift -o /tmp/cinematicum-webkit-smoke
import AppKit
import Foundation
import WebKit
import Darwin

@available(macOS 11.0, *)
final class SmokeDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    let url: URL
    let output: URL
    let timeout: Double
    var window: NSWindow!
    var webView: WKWebView!
    var pageErrors = [String]()
    var started = false
    var finishing = false
    var finished = false

    init(url: URL, output: URL, timeout: Double) {
        self.url = url
        self.output = output
        self.timeout = timeout
        super.init()
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
        webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 1440, height: 960), configuration: configuration)
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
        let script = #"""
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
          return {passed:true, steps, project_id:$('#project-select').value, asset_id:assetID,
                  source_playback_timecode:playedTimecode, scrub_timecode:'00:00:00:06',
                  video_src:video.getAttribute('src'), video_current_src:video.currentSrc,
                  video_duration:video.duration, video_current_time:video.currentTime,
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
                self?.captureAndFinish(value as? [String: Any] ?? ["passed": false, "error": "JavaScript returned no test result."])
            case .failure(let error):
                self?.captureAndFinish(["passed": false, "error": "Browser execution failed: \(error)"])
            }
        }
    }

    func captureAndFinish(_ initial: [String: Any]) {
        guard !finishing else { return }
        finishing = true
        var report = initial
        report["page_errors"] = pageErrors
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

if #available(macOS 11.0, *) {
    guard let raw = argument("--url"), let url = URL(string: raw), url.scheme == "http", ["127.0.0.1", "localhost"].contains(url.host ?? ""),
          let destination = argument("--output") else {
        fputs("Usage: cinematicum-webkit-smoke --url http://127.0.0.1:PORT --output screenshot.png [--timeout 14]\n", stderr)
        exit(2)
    }
    let delegate = SmokeDelegate(url: url, output: URL(fileURLWithPath: destination), timeout: Double(argument("--timeout") ?? "14") ?? 14)
    let application = NSApplication.shared
    application.setActivationPolicy(.regular)
    application.delegate = delegate
    withExtendedLifetime(delegate) {
        application.run()
    }
} else {
    fputs("The WebKit smoke test requires macOS 11 or newer.\n", stderr)
    exit(2)
}

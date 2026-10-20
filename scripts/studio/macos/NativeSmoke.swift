// Actual WKWebView acceptance harness. Never linked into the application.
// Compile: xcrun swiftc -framework Cocoa -framework WebKit NativeSmoke.swift -o NativeSmoke
// Run: NativeSmoke BASE_URL OUTPUT_DIR EDITOR [ENGINE_TEST_PROJECT_ID]
// NativeSmoke.js is read beside this source file (or beside the executable).
// Start the actual editor in a dedicated ENGINE_TEST project before this bounded
// test. The harness proves GUI transport; it does not claim authoring/export parity.
import AppKit
import Foundation
import WebKit
import Darwin

@available(macOS 11.0, *)
final class NativeSmokeDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    let base: URL
    let output: URL
    let editor: String
    let projectID: String
    let script: String
    var window: NSWindow!
    var webView: WKWebView!
    var began = Date()
    var started = false
    var finishing = false
    var finished = false
    var events = [[String: String]]()
    var pageErrors = [String]()

    init(base: URL, output: URL, editor: String, projectID: String, script: String) {
        self.base = base
        self.output = output
        self.editor = editor
        self.projectID = projectID
        self.script = script
        super.init()
    }

    static func redact(_ value: String) -> String {
        var text = value
        for (pattern, replacement) in [
            (#"/native/[A-Za-z0-9_-]+/"#, "/native/<session>/"),
            (#"(?i)([?&](?:password|token|secret|auth)=)[^&\s\"'<>]*"#, "$1<redacted>"),
            (#"(?i)\b((?:password|token|secret|auth)\s*[:=]\s*)[\"']?[^\s,\"'<>]+"#, "$1<redacted>"),
            (#"(?i)\b((?:https?|wss?)://[^\s?\"'<>]+)\?[^\s\"'<>]*"#, "$1?<redacted>")
        ] {
            text = text.replacingOccurrences(of: pattern, with: replacement, options: .regularExpression)
        }
        return String(text.prefix(1600))
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        began = Date()
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        configuration.userContentController.add(self, name: "nativeSmoke")
        configuration.userContentController.addUserScript(WKUserScript(source: #"""
        (() => {
          const state = {connected:false,native_window_count:0,decoded_paints:0,decode_errors:0,
            decoded_pixels:0,direct_socket_open:0,direct_socket_messages:0,direct_socket_bytes:0,
            websocket_origin_valid:true,protocol_worker:false,audio_enabled:false,audio_state:'',audio_codec:''};
          Object.defineProperty(window,'__cinematicumNativeQA',{value:state});
          const parameters=new URLSearchParams(location.search);
          const sensitive=['password','token','secret','auth'].map(key=>parameters.get(key)).filter(Boolean);
          const redact=value=>sensitive.reduce((text,secret)=>text.split(secret).join('<redacted>'),String(value||''))
            .replace(/\/native\/[A-Za-z0-9_-]+\//g,'/native/<session>/')
            .replace(/([?&](?:password|token|secret|auth)=)[^&\s"'<>]*/gi,'$1<redacted>')
            .replace(/\b((?:password|token|secret|auth)\s*[:=]\s*)["']?[^\s,"'<>]+/gi,'$1<redacted>')
            .replace(/\b((?:https?|wss?):\/\/[^\s?"'<>]+)\?[^\s"'<>]*/gi,'$1?<redacted>').slice(0,1200);
          let emitted=0;
          const emit=(kind,message)=>{
            if(emitted++>=40)return;
            window.webkit.messageHandlers.nativeSmoke.postMessage({kind,message:redact(message),frame:location.pathname.startsWith('/native/')?'native':'host'});
          };
          addEventListener('error',event=>emit('uncaught',event.message||'Script error'));
          addEventListener('unhandledrejection',event=>emit('unhandled_rejection',event.reason?.message||event.reason));
          for(const name of ['warn','error']){
            const original=console[name];
            console[name]=function(...args){emit('console_'+name,args.map(value=>typeof value==='object'?'[object]':String(value)).join(' '));return Reflect.apply(original,this,args);};
          }
          try {
            const OriginalWebSocket=window.WebSocket;
            window.WebSocket=new Proxy(OriginalWebSocket,{construct(target,args,newTarget){
              const socket=Reflect.construct(target,args,newTarget);
              try{
                const endpoint=new URL(String(args[0]),location.href);
                if(endpoint.hostname!==location.hostname||endpoint.port!==location.port||!endpoint.pathname.startsWith('/native/'))state.websocket_origin_valid=false;
              }catch(_){state.websocket_origin_valid=false;}
              socket.addEventListener('open',()=>state.direct_socket_open++);
              socket.addEventListener('message',event=>{state.direct_socket_messages++;const data=event.data;state.direct_socket_bytes+=typeof data==='string'?data.length:(data?.byteLength||data?.size||0);});
              socket.addEventListener('error',()=>emit('socket_error','WebSocket reported an error'));
              return socket;
            }});
          }catch(_){emit('observation','Direct WebSocket observation unavailable; Xpra protocol state remains required.');}
          const hook=()=>{
            if(!location.pathname.startsWith('/native/'))return;
            // Read the real client's global lexical binding. This is not a fake
            // readiness flag and does not write connection or document state.
            let app=null;
            try{app=typeof client!=='undefined'?client:window.client;}catch(_){}
            try{
              const type=typeof XpraClient!=='undefined'?XpraClient:null;
              const target=type?.prototype||app;
              if(target&&!target.__cinematicumPaintObserved&&typeof target.do_send_damage_sequence==='function'){
                const original=target.do_send_damage_sequence;
                Object.defineProperty(target,'__cinematicumPaintObserved',{value:true});
                target.do_send_damage_sequence=function(sequence,wid,width,height,decodeTime,message){
                  if(Number(decodeTime)>=0){state.decoded_paints++;state.decoded_pixels+=Math.max(0,Number(width)||0)*Math.max(0,Number(height)||0);}
                  else {state.decode_errors++;state.last_decode_error=redact(message);}
                  return Reflect.apply(original,this,arguments);
                };
              }
            }catch(error){emit('observation','Could not observe decoded paint acknowledgments.');}
            if(!app)return;
            state.connected=app.connected===true;
            state.native_window_count=Object.keys(app.id_to_window||{}).length;
            state.protocol_worker=Boolean(app.protocol?.worker);
            state.audio_enabled=app.audio_enabled===true;
            state.audio_state=String(app.audio_state||'');
            state.audio_codec=String(app.audio_codec||'');
          };
          const timer=setInterval(hook,20);
          addEventListener('pagehide',()=>clearInterval(timer),{once:true});
          hook();
        })();
        """#, injectionTime: .atDocumentStart, forMainFrameOnly: false))
        webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 1440, height: 960), configuration: configuration)
        webView.navigationDelegate = self
        window = NSWindow(contentRect: webView.frame, styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "ENGINE_TEST — CINEMATICUM native editor transport"
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        var components = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        components.path = "/"
        components.queryItems = [URLQueryItem(name: "workspace", value: "assembly")]
        components.fragment = nil
        webView.load(URLRequest(url: components.url!))
        DispatchQueue.main.asyncAfter(deadline: .now() + 14.5) { [weak self] in
            self?.captureAndFinish(["passed": false, "error": "Native browser acceptance exceeded 14.5 seconds."])
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: String] else { return }
        let kind = String((body["kind"] ?? "unknown").prefix(50))
        let detail = Self.redact(body["message"] ?? "")
        if events.count < 40 { events.append(["kind": kind, "message": detail, "frame": body["frame"] ?? "unknown"]) }
        if ["uncaught", "unhandled_rejection"].contains(kind) && pageErrors.count < 20 { pageErrors.append(detail) }
    }

    func local(_ url: URL?) -> Bool {
        guard let url = url else { return false }
        return url.scheme == base.scheme && url.host == base.host && url.port == base.port && url.user == nil && url.password == nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if local(navigationAction.request.url) || navigationAction.request.url?.absoluteString == "about:blank" {
            decisionHandler(.allow)
        } else {
            events.append(["kind": "navigation_blocked", "message": "Non-local navigation blocked", "frame": "unknown"])
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled {
            captureAndFinish(["passed": false, "error": Self.redact("Navigation failed: " + error.localizedDescription)])
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled {
            captureAndFinish(["passed": false, "error": Self.redact("Initial navigation failed: " + error.localizedDescription)])
        }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        captureAndFinish(["passed": false, "error": "WebKit content process terminated."])
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard !started else { return }
        started = true
        webView.callAsyncJavaScript(script, arguments: ["editorID": editor,
            "expectedProjectID": projectID, "deadlineMilliseconds": 12500], in: nil, in: .page) { [weak self] result in
            switch result {
            case .success(let value):
                self?.captureAndFinish(value as? [String: Any] ?? ["passed": false, "error": "Browser returned no acceptance result."])
            case .failure(let error):
                self?.captureAndFinish(["passed": false, "error": Self.redact("Browser execution failed: " + error.localizedDescription)])
            }
        }
    }

    func writeImage(_ image: NSImage?, _ destination: URL) throws -> NSBitmapImageRep {
        guard let data = image?.tiffRepresentation, let bitmap = NSBitmapImageRep(data: data),
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw NSError(domain: "NativeSmoke", code: 1, userInfo: [NSLocalizedDescriptionKey: "WebKit returned no screenshot image."])
        }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        try png.write(to: destination, options: .atomic)
        return bitmap
    }

    func pixelEvidence(_ bitmap: NSBitmapImageRep) -> [String: Any] {
        var histogram = [Int: Int]()
        var total = 0
        for row in 0..<40 {
            for column in 0..<64 {
                let x = min(bitmap.pixelsWide - 1, (2 * column + 1) * bitmap.pixelsWide / 128)
                let y = min(bitmap.pixelsHigh - 1, (2 * row + 1) * bitmap.pixelsHigh / 80)
                guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                let r = max(0, min(31, Int(color.redComponent * 255) >> 3))
                let g = max(0, min(31, Int(color.greenComponent * 255) >> 3))
                let b = max(0, min(31, Int(color.blueComponent * 255) >> 3))
                let key = (r << 10) | (g << 5) | b
                histogram[key, default: 0] += 1
                total += 1
            }
        }
        let dominant = histogram.values.max() ?? 0
        return ["width": bitmap.pixelsWide, "height": bitmap.pixelsHigh,
                "samples": total, "quantized_colors": histogram.count,
                "non_dominant_samples": total - dominant,
                "passed": bitmap.pixelsWide >= 200 && bitmap.pixelsHigh >= 100 &&
                    total >= 1000 && histogram.count >= 8 && total - dominant >= 40]
    }

    func captureAndFinish(_ initial: [String: Any]) {
        guard !finishing else { return }
        finishing = true
        var report = initial
        report["editor"] = editor
        report["scope"] = "native_editor_gui_transport_only"
        report["page_errors"] = pageErrors
        report["events"] = events
        report["elapsed_total_ms"] = Int(Date().timeIntervalSince(began) * 1000)
        if !pageErrors.isEmpty { report["passed"] = false }
        let whole = output.appendingPathComponent("ENGINE_TEST_native_" + editor + ".png")
        let view = output.appendingPathComponent("ENGINE_TEST_native_" + editor + "_viewer.png")
        func fullSnapshot(_ current: [String: Any]) {
            let config = WKSnapshotConfiguration()
            config.rect = webView.bounds
            webView.takeSnapshot(with: config) { [weak self] image, error in
                guard let self = self else { return }
                var final = current
                do {
                    _ = try self.writeImage(image, whole)
                    final["screenshot"] = whole.path
                } catch {
                    final["passed"] = false
                    final["snapshot_error"] = Self.redact(error.localizedDescription)
                }
                self.emit(final)
            }
        }
        if let values = report["viewport"] as? [String: Any],
           let x = values["x"] as? NSNumber, let y = values["y"] as? NSNumber,
           let width = values["width"] as? NSNumber, let height = values["height"] as? NSNumber,
           width.doubleValue >= 200, height.doubleValue >= 100 {
            let config = WKSnapshotConfiguration()
            let requested = NSRect(x: x.doubleValue, y: y.doubleValue,
                                   width: width.doubleValue, height: height.doubleValue)
            config.rect = requested.intersection(webView.bounds)
            webView.takeSnapshot(with: config) { [weak self] image, error in
                guard let self = self else { return }
                var current = report
                do {
                    let bitmap = try self.writeImage(image, view)
                    let evidence = self.pixelEvidence(bitmap)
                    current["native_canvas_pixels"] = evidence
                    current["viewer_screenshot"] = view.path
                    if evidence["passed"] as? Bool != true {
                        current["passed"] = false
                        current["error"] = "The actual native canvas screenshot was empty or insufficiently varied."
                    }
                } catch {
                    current["passed"] = false
                    current["snapshot_error"] = Self.redact(error.localizedDescription)
                }
                fullSnapshot(current)
            }
        } else {
            report["passed"] = false
            if report["error"] == nil { report["error"] = "No visible native canvas was available to verify." }
            fullSnapshot(report)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
            var fallback = report
            fallback["passed"] = false
            fallback["snapshot_error"] = "Timed out capturing native workspace evidence."
            self?.emit(fallback)
        }
    }

    func emit(_ report: [String: Any]) {
        guard !finished else { return }
        finished = true
        var final = report
        let destination = output.appendingPathComponent("native_" + editor + "_report.json")
        do {
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys, .prettyPrinted])
            try data.write(to: destination, options: .atomic)
            final["report"] = destination.path
        } catch {
            final["passed"] = false
            final["report_error"] = Self.redact(error.localizedDescription)
        }
        if let data = try? JSONSerialization.data(withJSONObject: final, options: [.sortedKeys]),
           let line = String(data: data, encoding: .utf8) { print(line); fflush(stdout) }
        exit(final["passed"] as? Bool == true ? 0 : 1)
    }
}

if #available(macOS 11.0, *) {
    let args = CommandLine.arguments
    let editors: Set<String> = ["kdenlive", "shotcut", "cinelerra", "natron", "friction", "glaxnimate", "blender"]
    guard (4...5).contains(args.count), let base = URL(string: args[1]),
          base.scheme == "http", ["127.0.0.1", "localhost"].contains(base.host ?? ""),
          let port = base.port, (1...65535).contains(port), base.user == nil, base.password == nil,
          base.query == nil, base.fragment == nil, editors.contains(args[3]) else {
        fputs("Usage: NativeSmoke http://127.0.0.1:PORT OUTPUT_DIR EDITOR [ENGINE_TEST_PROJECT_ID]\n", stderr)
        exit(2)
    }
    let projectID = args.count > 4 ? args[4] : ""
    if !projectID.isEmpty && projectID.range(of: "^[a-f0-9]{32}$", options: .regularExpression) == nil {
        fputs("Project ID must be the identifier of a dedicated ENGINE_TEST project.\n", stderr)
        exit(2)
    }
    let sources = [URL(fileURLWithPath: args[0]).deletingLastPathComponent().appendingPathComponent("NativeSmoke.js"),
                   URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("NativeSmoke.js")]
    guard let source = sources.first(where: { FileManager.default.fileExists(atPath: $0.path) }),
          let script = try? String(contentsOf: source, encoding: .utf8) else {
        fputs("NativeSmoke.js must be beside the harness executable or its Swift source.\n", stderr)
        exit(2)
    }
    let delegate = NativeSmokeDelegate(base: base, output: URL(fileURLWithPath: args[2], isDirectory: true),
                                       editor: args[3], projectID: projectID, script: script)
    let application = NSApplication.shared
    application.setActivationPolicy(.regular)
    application.delegate = delegate
    withExtendedLifetime(delegate) { application.run() }
} else {
    fputs("NativeSmoke requires macOS 11 or newer.\n", stderr)
    exit(2)
}

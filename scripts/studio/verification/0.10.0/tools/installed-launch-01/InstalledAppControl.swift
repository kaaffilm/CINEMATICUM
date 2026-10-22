// Independent LaunchServices controller. This file contains no product class,
// injected JavaScript, simulated delegate, Accessibility request or force quit.
import Cocoa
import CoreGraphics
import CryptoKit

private let canonicalBundle = "/Users/midiakiasat/Applications/CINEMATICUM Studio.app"
private let canonicalHome = "/Users/midiakiasat"
private let identifier = "com.cinematicum.studio"
private let version = "0.10.0"
private let build = "11"

private func argument(_ name: String) -> String? {
    guard let index = CommandLine.arguments.firstIndex(of: name), index + 1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[index + 1]
}

private func problem(_ message: String) -> NSError {
    NSError(domain: "InstalledLaunchAcceptance", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
}

private func emit(_ object: [String: Any], status: Int32 = 0) -> Never {
    do {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    } catch { fputs("Installed-app controller could not serialize its metadata report.\n", stderr) }
    exit(status)
}

private func exactBundle(_ expectedHash: String) throws -> URL {
    guard FileManager.default.homeDirectoryForCurrentUser.path == canonicalHome else {
        throw problem("The controller is not running in the canonical application's user account")
    }
    let url = URL(fileURLWithPath: canonicalBundle, isDirectory: true)
    guard url.resolvingSymlinksInPath().path == canonicalBundle,
          let bundle = Bundle(url: url), bundle.bundleIdentifier == identifier,
          bundle.infoDictionary?["CFBundleShortVersionString"] as? String == version,
          bundle.infoDictionary?["CFBundleVersion"] as? String == build,
          let executable = bundle.executableURL,
          executable.path == canonicalBundle + "/Contents/MacOS/CINEMATICUMStudio" else {
        throw problem("Canonical installed bundle identity/version/build/executable differs")
    }
    let attributes = try executable.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    guard attributes.isRegularFile == true, attributes.isSymbolicLink != true,
          let size = attributes.fileSize, size > 0, size <= 128 * 1024 * 1024 else {
        throw problem("Canonical native executable is not a bounded regular file")
    }
    let payload = try Data(contentsOf: executable, options: .mappedIfSafe)
    let actualHash = SHA256.hash(data: payload).map { String(format: "%02x", $0) }.joined()
    guard expectedHash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil,
          actualHash == expectedHash else { throw problem("Canonical native executable hash differs from verified installation") }
    return url
}

private func existingProductionApps() -> [NSRunningApplication] {
    NSWorkspace.shared.runningApplications.filter {
        !$0.isTerminated && ($0.bundleIdentifier == identifier
            || $0.bundleURL?.resolvingSymlinksInPath().path == canonicalBundle
            || $0.executableURL?.resolvingSymlinksInPath().path == canonicalBundle + "/Contents/MacOS/CINEMATICUMStudio")
    }
}

private func observation(_ app: NSRunningApplication, expectedHash: String) throws -> [String: Any] {
    guard app.bundleIdentifier == identifier,
          app.bundleURL?.resolvingSymlinksInPath().path == canonicalBundle,
          app.executableURL?.resolvingSymlinksInPath().path == canonicalBundle + "/Contents/MacOS/CINEMATICUMStudio",
          let launched = app.launchDate else { throw problem("LaunchServices returned a different or unidentifiable application") }
    var result: [String: Any] = ["pid": app.processIdentifier, "launch_unix": launched.timeIntervalSince1970,
        "bundle_id": identifier, "bundle_path": canonicalBundle,
        "executable_path": canonicalBundle + "/Contents/MacOS/CINEMATICUMStudio",
        "native_sha256": expectedHash, "running": !app.isTerminated,
        "finished_launching": app.isFinishedLaunching, "hidden": app.isHidden,
        "activation_policy_regular": app.activationPolicy == .regular]
    // Window metadata is available without asking for screen pixels or AX.
    // Deliberately do not read window names, owner names or window content.
    if let entries = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] {
        let owned = entries.filter { ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == app.processIdentifier }
        let normal = owned.filter { row in
            guard (row[kCGWindowLayer as String] as? NSNumber)?.intValue == 0,
                  let bounds = row[kCGWindowBounds as String] as? [String: Any],
                  let width = bounds["Width"] as? NSNumber, let height = bounds["Height"] as? NSNumber else { return false }
            return width.doubleValue > 0 && height.doubleValue > 0
        }
        result["window_metadata_available"] = true
        result["onscreen_window_count"] = owned.count
        result["normal_window_count"] = normal.count
    } else {
        result["window_metadata_available"] = false
        result["window_observation_limit"] = "CoreGraphics returned no permission-free window inventory; no permission was requested"
    }
    return result
}

private func readOwnership(_ path: String, expectedHash: String) throws -> [String: Any] {
    let url = URL(fileURLWithPath: path)
    let attributes = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    guard path.hasPrefix("/"), attributes.isRegularFile == true, attributes.isSymbolicLink != true,
          (attributes.fileSize ?? 65537) <= 65536,
          let record = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any],
          record["bundle_id"] as? String == identifier, record["bundle_path"] as? String == canonicalBundle,
          record["native_sha256"] as? String == expectedHash,
          let pid = record["pid"] as? NSNumber, pid.int32Value > 1,
          let time = record["launch_unix"] as? NSNumber, time.doubleValue.isFinite, time.doubleValue > 0 else {
        throw problem("Explicit LaunchServices ownership receipt is invalid")
    }
    return record
}

private func ownedApp(_ record: [String: Any], expectedHash: String) throws -> NSRunningApplication? {
    let pid = (record["pid"] as! NSNumber).int32Value
    guard let app = NSRunningApplication(processIdentifier: pid), !app.isTerminated else { return nil }
    let current = try observation(app, expectedHash: expectedHash)
    guard let actual = current["launch_unix"] as? Double,
          let expected = (record["launch_unix"] as? NSNumber)?.doubleValue,
          abs(actual - expected) < 0.001 else { throw problem("Owned application PID has a different launch identity") }
    return app
}

guard let operation = argument("--operation"), let expectedHash = argument("--expected-native-sha256") else {
    emit(["passed": false, "error": "Required: --operation preflight|launch|observe|terminate --expected-native-sha256 HASH [--ownership /receipt.json]"], status: 2)
}

do {
    let bundle = try exactBundle(expectedHash)
    switch operation {
    case "preflight":
        let matches = existingProductionApps()
        emit(["passed": matches.isEmpty, "operation": operation, "existing_production_app_count": matches.count,
              "canonical_bundle_verified": true, "permissions_requested": false], status: matches.isEmpty ? 0 : 1)
    case "launch":
        guard existingProductionApps().isEmpty else { throw problem("A production application is already running; no existing instance will be adopted") }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        configuration.createsNewApplicationInstance = true
        var response: [String: Any]?
        let began = Date().timeIntervalSince1970
        NSWorkspace.shared.openApplication(at: bundle, configuration: configuration) { app, error in
            if let error = error {
                response = ["passed": false, "operation": operation, "error": error.localizedDescription]
                return
            }
            do {
                guard let app = app else { throw problem("LaunchServices returned no owned application") }
                let owned = try observation(app, expectedHash: expectedHash)
                guard let launch = owned["launch_unix"] as? Double, launch >= began - 2 else {
                    throw problem("LaunchServices did not create a new application for this request")
                }
                response = ["passed": true, "operation": operation, "owned": owned,
                            "launch_mechanism": "NSWorkspace.openApplication / LaunchServices",
                            "creates_new_instance": true, "permissions_requested": false]
            } catch { response = ["passed": false, "operation": operation, "error": error.localizedDescription] }
        }
        let deadline = Date(timeIntervalSinceNow: 20)
        while response == nil && Date() < deadline { RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.04)) }
        guard let report = response else { throw problem("LaunchServices did not return an owned application within 20 seconds") }
        emit(report, status: report["passed"] as? Bool == true ? 0 : 1)
    case "observe", "terminate":
        guard let path = argument("--ownership") else { throw problem("An explicit LaunchServices ownership receipt is required") }
        let ownership = try readOwnership(path, expectedHash: expectedHash)
        guard let app = try ownedApp(ownership, expectedHash: expectedHash) else {
            emit(["passed": operation == "observe", "operation": operation, "running": false,
                  "owned_pid_absent": true, "termination_requested": false], status: operation == "observe" ? 0 : 1)
        }
        if operation == "observe" {
            emit(["passed": true, "operation": operation, "owned": try observation(app, expectedHash: expectedHash)])
        }
        let requested = app.terminate()
        let deadline = Date(timeIntervalSinceNow: 15)
        while requested && !app.isTerminated && Date() < deadline { RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05)) }
        emit(["passed": requested && app.isTerminated, "operation": operation,
              "termination_requested": requested, "owned_app_terminated": app.isTerminated,
              "termination_mechanism": "NSRunningApplication.terminate", "force_termination_used": false],
             status: requested && app.isTerminated ? 0 : 1)
    default: throw problem("Unsupported installed-app control operation")
    }
} catch {
    emit(["passed": false, "operation": operation, "error": error.localizedDescription,
          "force_termination_used": false, "permissions_requested": false], status: 1)
}

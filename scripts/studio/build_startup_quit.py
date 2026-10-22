#!/usr/bin/env python3
"""Bind the exact production class to its independent native startup-quit harness."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BOOTSTRAP = b"\nlet application = NSApplication.shared\nlet applicationDelegate = StudioAppDelegate()\napplication.delegate = applicationDelegate\napplication.setActivationPolicy(.regular)\napplication.run()\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-production-sha256", required=True)
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve() / "scripts/studio/macos/StudioApp.swift"
    payload = source.read_bytes()
    if source.is_symlink() or digest(payload) != args.expected_production_sha256 or payload.count(BOOTSTRAP) != 1 or not payload.endswith(BOOTSTRAP):
        raise ValueError("Production source or top-level bootstrap identity differs")
    harness = Path(__file__).with_name("macos") / "StartupQuitAcceptance.swift"
    body = payload[:-len(BOOTSTRAP)]
    combined = body + b"\n// Independent native ENGINE TEST startup only.\n" + harness.read_bytes()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    generated = output / "StartupQuitAcceptance.swift"
    generated.write_bytes(combined)
    binary = output / "cinematicum-startup-quit-acceptance"
    report = {"schema": "cinematicum-native-startup-quit-build-v1", "compiled": False,
              "production_source_sha256": digest(payload), "unchanged_production_class_sha256": digest(body),
              "harness_sha256": digest(harness.read_bytes()), "generated_source_sha256": digest(combined)}
    if not args.emit_only:
        if sys.platform != "darwin":
            raise ValueError("Native compilation requires actual macOS")
        command = ["/usr/bin/xcrun", "swiftc", "-O", "-swift-version", "5", "-framework", "Cocoa", "-framework", "WebKit",
                   "-target", "arm64-apple-macos12.0", "-module-cache-path", str(output / "module-cache"),
                   str(generated), "-o", str(binary)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=18)
        (output / "compiler.stdout").write_text(process.stdout)
        (output / "compiler.stderr").write_text(process.stderr)
        if process.returncode:
            raise RuntimeError("Native startup-quit compilation failed: " + process.stderr[-8000:])
        report.update(compiled=True, binary=str(binary), binary_sha256=digest(binary.read_bytes()), command=command)
    (output / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()

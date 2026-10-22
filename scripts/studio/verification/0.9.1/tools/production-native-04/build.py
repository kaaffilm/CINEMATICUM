#!/usr/bin/env python3
"""Compile the exact production class with a separate acceptance bootstrap.

Only the seven-line top-level bootstrap is removed. No production class body,
download callback, save-panel callback or quit callback is rewritten.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BOOTSTRAP = b"\nlet application = NSApplication.shared\nlet applicationDelegate = StudioAppDelegate()\napplication.delegate = applicationDelegate\napplication.setActivationPolicy(.regular)\napplication.run()\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(source, output, expected, compile_native=True):
    source = source.absolute()
    output = output.absolute()
    production = source / "scripts/studio/macos/StudioApp.swift"
    if production.is_symlink() or not production.is_file():
        raise ValueError("Production native source must be a regular file")
    data = production.read_bytes()
    if sha(data) != expected:
        raise ValueError("Production native source differs from the explicit accepted hash")
    if data.count(BOOTSTRAP) != 1 or not data.endswith(BOOTSTRAP):
        raise ValueError("Production bootstrap differs; no class body will be rewritten")
    body = data[:-len(BOOTSTRAP)]
    harness = Path(__file__).with_name("ProductionNativeAcceptance.swift").read_bytes()
    combined = body + b"\n\n// Independent acceptance bootstrap follows the unchanged production class.\n" + harness
    output.mkdir(parents=True, exist_ok=False)
    generated = output / "ProductionAcceptance.swift"
    generated.write_bytes(combined)
    binary = output / "cinematicum-production-native-acceptance"
    record = {"schema": "cinematicum-production-class-acceptance-build-v1",
              "source": str(production), "production_source_sha256": sha(data),
              "unchanged_production_class_sha256": sha(body),
              "removed_bootstrap_sha256": sha(BOOTSTRAP),
              "harness_sha256": sha(harness), "generated_source_sha256": sha(combined),
              "scope": "Unchanged production StudioAppDelegate class; isolated acceptance startup, not an installed-app launch",
              "compiled": False}
    if compile_native:
        if sys.platform != "darwin":
            raise ValueError("Actual native compilation requires macOS; use --emit-only to inspect the combined source")
        command = ["/usr/bin/xcrun", "swiftc", "-O", "-swift-version", "5", "-framework", "Cocoa",
                   "-framework", "WebKit", "-target", "arm64-apple-macos12.0",
                   "-module-cache-path", str(output / "module-cache"), str(generated), "-o", str(binary)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=240)
        (output / "compiler.stdout").write_text(process.stdout)
        (output / "compiler.stderr").write_text(process.stderr)
        if process.returncode:
            raise RuntimeError("Native acceptance compilation failed: " + process.stderr[-10000:])
        record.update(compiled=True, binary=str(binary), binary_sha256=sha(binary.read_bytes()), command=command)
    (output / "build.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Exact frozen repository root")
    parser.add_argument("--output", required=True, type=Path, help="New independent build directory")
    parser.add_argument("--expected-production-sha256", required=True)
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()
    try:
        record = build(args.source, args.output, args.expected_production_sha256, not args.emit_only)
        print(json.dumps(record, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

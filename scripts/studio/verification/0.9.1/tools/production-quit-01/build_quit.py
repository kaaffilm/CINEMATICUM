#!/usr/bin/env python3
"""Build an unchanged production quit delegate with an isolated real-server bootstrap."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BOOTSTRAP = b"\nlet application = NSApplication.shared\nlet applicationDelegate = StudioAppDelegate()\napplication.delegate = applicationDelegate\napplication.setActivationPolicy(.regular)\napplication.run()\n"


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-production-sha256", required=True)
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()
    try:
        source = args.source.absolute() / "scripts/studio/macos/StudioApp.swift"
        data = source.read_bytes()
        if source.is_symlink() or sha(data) != args.expected_production_sha256 or data.count(BOOTSTRAP) != 1 or not data.endswith(BOOTSTRAP):
            raise ValueError("Production source/bootstrap identity differs; no class body is rewritten")
        harness = Path(__file__).with_name("ProductionQuitAcceptance.swift").read_bytes()
        body = data[:-len(BOOTSTRAP)]
        combined = body + b"\n\n// Independent actual-job quit acceptance bootstrap.\n" + harness
        output = args.output.absolute(); output.mkdir(parents=True, exist_ok=False)
        generated = output / "ProductionQuitAcceptance.swift"; generated.write_bytes(combined)
        binary = output / "cinematicum-production-quit-acceptance"
        report = {"schema": "cinematicum-production-class-quit-build-v1", "production_source_sha256": sha(data),
                  "unchanged_production_class_sha256": sha(body), "harness_sha256": sha(harness),
                  "generated_source_sha256": sha(combined), "compiled": False}
        if not args.emit_only:
            if sys.platform != "darwin": raise ValueError("Actual native compilation requires macOS")
            command = ["/usr/bin/xcrun", "swiftc", "-O", "-swift-version", "5", "-framework", "Cocoa", "-framework", "WebKit",
                       "-target", "arm64-apple-macos12.0", "-module-cache-path", str(output / "module-cache"), str(generated), "-o", str(binary)]
            process = subprocess.run(command, capture_output=True, text=True, timeout=240)
            (output / "compiler.stdout").write_text(process.stdout); (output / "compiler.stderr").write_text(process.stderr)
            if process.returncode: raise RuntimeError("Native quit compilation failed: " + process.stderr[-10000:])
            report.update(compiled=True, binary=str(binary), binary_sha256=sha(binary.read_bytes()), command=command)
        (output / "build.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2)); return 0
    except Exception as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr); return 1


if __name__ == "__main__": raise SystemExit(main())

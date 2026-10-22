#!/usr/bin/env python3
"""Compile an independent NSWorkspace/NSRunningApplication controller, no product code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    try:
        if sys.platform != "darwin":
            raise ValueError("Actual AppKit/LaunchServices compilation requires macOS")
        source = Path(__file__).with_name("InstalledAppControl.swift").absolute()
        if source.is_symlink() or not source.is_file():
            raise ValueError("Independent controller source must be a regular file")
        output.mkdir(parents=True, exist_ok=False)
        binary = output / "cinematicum-installed-app-control"
        command = ["/usr/bin/xcrun", "swiftc", "-O", "-swift-version", "5", "-framework", "Cocoa",
                   "-framework", "CoreGraphics", "-target", "arm64-apple-macos12.0",
                   "-module-cache-path", str(output / "module-cache"), str(source), "-o", str(binary)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=18)
        (output / "compiler.stdout").write_text(process.stdout)
        (output / "compiler.stderr").write_text(process.stderr)
        if process.returncode:
            raise RuntimeError("Independent native controller compilation failed: " + process.stderr[-8000:])
        report = {"schema": "cinematicum-installed-app-controller-build-v1", "compiled": True,
                  "scope": "Independent LaunchServices control only; no production source compiled or injected",
                  "source_sha256": sha(source), "binary_sha256": sha(binary), "command": command}
        (output / "build.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2)); return 0
    except Exception as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())

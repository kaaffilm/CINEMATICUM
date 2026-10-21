#!/usr/bin/env python3
"""Build the native CINEMATICUM Studio .app using the installed Xcode toolchain.

No dependencies are downloaded, no services are installed, and the app is not
launched. --build-only changes the default destination from ~/Applications to
the repository's dist/macos directory. --output always selects an exact bundle.
An existing bundle can be replaced only if its bundle identifier is ours; its
previous version is retained beside it after a successful replacement.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid


BUNDLE_ID = "com.cinematicum.studio"
APP_NAME = "CINEMATICUM Studio.app"
EXECUTABLE_NAME = "CINEMATICUMStudio"
STUDIO_SOURCE = Path(__file__).resolve().parent


def bundle_info():
    return {
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": "CINEMATICUM Studio",
        "CFBundleDisplayName": "CINEMATICUM Studio",
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.4.0",
        "CFBundleVersion": "4",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSAppTransportSecurity": {
            "NSAllowsLocalNetworking": True,
            "NSExceptionDomains": {
                "localhost": {"NSExceptionAllowsInsecureHTTPLoads": True, "NSIncludesSubdomains": False},
                "127.0.0.1": {"NSExceptionAllowsInsecureHTTPLoads": True, "NSIncludesSubdomains": False},
            },
        },
    }


def existing_bundle_identity(path):
    """Refuse unrelated/symlink targets and bind a checked existing bundle."""
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink app destination: %s" % path)
    if not path.exists():
        return None
    if not path.is_dir():
        raise ValueError("App destination exists and is not a directory: %s" % path)
    info = path / "Contents" / "Info.plist"
    if info.is_symlink() or not info.is_file():
        raise ValueError("Existing destination is not a recognized CINEMATICUM bundle.")
    raw = info.read_bytes()
    try:
        identifier = plistlib.loads(raw).get("CFBundleIdentifier")
    except (ValueError, TypeError, AttributeError, plistlib.InvalidFileException) as exc:
        raise ValueError("Existing app has an unreadable Info.plist; it was not changed.") from exc
    if identifier != BUNDLE_ID:
        raise ValueError("Refusing to replace an unrelated application (bundle ID %r)." % identifier)
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, hashlib.sha256(raw).hexdigest())


def copy_runtime(destination, source=STUDIO_SOURCE):
    destination.mkdir(parents=True)
    for name in ("server.py", "engine.py", "adapters.py", "compositor.py", "scene.py", "generation_readiness.py", "frame_preview.py", "waveform.py"):
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Required runtime source is missing or is a symlink: %s" % path)
        shutil.copy2(str(path), str(destination / name))
    web = source / "web"
    if web.is_symlink() or not web.is_dir():
        raise ValueError("The editor web assets are missing or are a symlink.")
    for path in web.rglob("*"):
        if path.is_symlink():
            raise ValueError("Refusing a symlink in bundled web assets: %s" % path)
    shutil.copytree(str(web), str(destination / "web"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))


def build_app(output, arch=None, source=STUDIO_SOURCE):
    if sys.platform != "darwin":
        raise RuntimeError("The native application must be compiled on macOS with Xcode or Command Line Tools.")
    xcrun = shutil.which("xcrun")
    if not xcrun:
        raise RuntimeError("xcrun is unavailable. Install or select the Xcode Command Line Tools first.")
    architecture = arch or platform.machine()
    if architecture == "aarch64":
        architecture = "arm64"
    if architecture not in ("arm64", "x86_64"):
        raise ValueError("Supported build architectures are arm64 and x86_64.")
    output = Path(os.path.abspath(os.path.expanduser(str(output))))
    if output.suffix.lower() != ".app":
        raise ValueError("--output must name a .app bundle, not its containing folder.")
    original = existing_bundle_identity(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    swift = source / "macos" / "StudioApp.swift"
    if swift.is_symlink() or not swift.is_file():
        raise ValueError("Native launcher source is missing or is a symlink.")
    backup = None
    with tempfile.TemporaryDirectory(prefix=".cinematicum-build-", dir=str(output.parent)) as temporary:
        work = Path(temporary)
        staged = work / APP_NAME
        contents = staged / "Contents"
        executable = contents / "MacOS" / EXECUTABLE_NAME
        executable.parent.mkdir(parents=True)
        copy_runtime(contents / "Resources" / "studio", source)
        with (contents / "Info.plist").open("wb") as target:
            plistlib.dump(bundle_info(), target, fmt=plistlib.FMT_XML, sort_keys=True)
        (contents / "PkgInfo").write_bytes(b"APPL????")
        target = architecture + "-apple-macos12.0"
        command = [xcrun, "swiftc", "-O", "-swift-version", "5", "-framework", "Cocoa",
                   "-framework", "WebKit", "-target", target, "-module-cache-path", str(work / "module-cache"),
                   str(swift), "-o", str(executable)]
        try:
            compiled = subprocess.run(command, check=True, capture_output=True, text=True, timeout=240)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("Native compilation failed; existing app was preserved.\n" + (exc.stderr or exc.stdout or "")[-12000:]) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Native compilation exceeded four minutes; existing app was preserved.") from exc
        if not executable.is_file() or executable.stat().st_size == 0:
            raise RuntimeError("Compiler returned without a native executable; existing app was preserved.")
        executable.chmod(0o755)
        if existing_bundle_identity(output) != original:
            raise RuntimeError("The app destination changed during the build; installation was not attempted.")
        if original is not None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = output.with_name(output.stem + ".backup-" + stamp + "-" + uuid.uuid4().hex[:8] + ".app")
            os.rename(str(output), str(backup))
        try:
            os.rename(str(staged), str(output))
        except BaseException:
            if backup is not None and not output.exists():
                os.rename(str(backup), str(output))
            raise
        return {"app": str(output), "bundle_id": BUNDLE_ID, "target": target,
                "backup": str(backup) if backup is not None else None,
                "compiler_warnings": compiled.stderr.strip(),
                "signing_performed": False, "launched": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the native CINEMATICUM Studio macOS application")
    parser.add_argument("--output", type=Path, help="Exact .app destination (default: ~/Applications/CINEMATICUM Studio.app)")
    parser.add_argument("--build-only", action="store_true", help="Default to dist/macos instead of ~/Applications; never launches the app")
    parser.add_argument("--arch", choices=("arm64", "x86_64"), help="Target architecture; defaults to this Mac")
    args = parser.parse_args(argv)
    if args.output is not None:
        output = args.output
    elif args.build_only:
        output = STUDIO_SOURCE.parents[1] / "dist" / "macos" / APP_NAME
    else:
        output = Path.home() / "Applications" / APP_NAME
    try:
        result = build_app(output, args.arch)
    except (OSError, ValueError, RuntimeError) as exc:
        print("CINEMATICUM build failed: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the native CINEMATICUM Studio .app using the installed Xcode toolchain.

No dependencies are downloaded, no services are installed, and the app is not
launched. --build-only changes the default destination from ~/Applications to
the repository's dist/macos directory. --output always selects an exact bundle.
An existing bundle can be replaced only if its bundle identifier is ours. Its
previous version is retained in a verified ZIP, outside application discovery.
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
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile


BUNDLE_ID = "com.cinematicum.studio"
APP_NAME = "CINEMATICUM Studio.app"
EXECUTABLE_NAME = "CINEMATICUMStudio"
STUDIO_SOURCE = Path(__file__).resolve().parent
RUNTIME_FILES = (
    "server.py", "engine.py", "adapters.py", "compositor.py", "scene.py",
    "generation_readiness.py", "managed_generation.py", "generation-runtime-lock.json",
    "model_inference.py", "camera_ctrl.py", "camera_ctrl_standalone.py", "camera_ctrl_worker.py", "camera_ctrl-source-lock.json",
    "diffusionlight.py", "diffusionlight_standalone.py", "diffusionlight_worker.py", "diffusionlight-source-lock.json",
    "frame_preview.py", "waveform.py", "audio_source.py", "audio_mixer.py", "timebase.py", "tracking.py",
    "planar_tracking.py", "planar_worker.py", "projective_warp.py", "install_tracking.py",
    "lens_calibration.py", "lens_calibration_worker.py",
    "tracking-macos-arm64-py313.lock.json", "spatial_import.py", "interchange.py", "fcpxml.py", "camera_io.py",
    "color_pipeline.py", "scene_modeling.py", "modeling_blender.py", "imaging.py", "image_worker.py",
    "still_photography.py", "still_photo_worker.py",
    "install_imaging.py", "imaging-macos-arm64-py313.lock.json", "lens_assets.py", "lens_geometry.py", "media_orientation.py",
    "recovery.py", "production.py", "project_archive.py", "editorial.py", "sequence_interchange.py", "otio_compositions.py", "retime.py", "retime_worker.py",
    "media_management.py", "roto.py", "roto_assets.py", "scene_hierarchy.py", "render_devices.py",
    "studio_tools.py", "deep_compositing.py", "deep_compositing_worker.py",
    "ray_optics.py", "ray_optics_worker.py", "physical_rendering.py", "physical_rendering_worker.py",
    "install_ray_optics.py", "ray-optics-macos-arm64-py313.lock.json",
    "collaboration.py", "collaboration_store.py",
    "learned_tools.py", "learned_tracking.py", "learned_tracking_worker.py", "learned-runtime-lock.json",
    "tapnext_runtime.py", "tapnext_worker.py", "install_tapnext.py", "tapnext-runtime-lock.json",
    "install_learned_tracking.py", "reconstruction.py", "reconstruction_worker.py",
    "alicevision.py", "alicevision-photogrammetry-2025.1.mg", "alicevision-graph-LICENSE.md",
    "install_reconstruction.py", "reconstruction-macos-arm64-py313.lock.json",
    "meshroom_reconstruction.py", "camera_ctrl.py", "diffusionlight.py",
    "scene_processing.py", "scene_processing_worker.py", "scene_dispatch.py", "scene_dispatch_store.py",
    "runtime_management.py", "install_physical_rendering.py", "physical-rendering-macos-arm64-py313.lock.json",
    "multicam_sync.py", "multicam_sync_worker.py", "multicam.py", "float_movie.py", "float_movie_worker.py",
)


def bundle_info():
    return {
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": "CINEMATICUM Studio",
        "CFBundleDisplayName": "CINEMATICUM Studio",
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.13.0",
        "CFBundleVersion": "14",
        "CFBundleIconFile": "StudioIcon.icns",
        "LSApplicationCategoryType": "public.app-category.video",
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
    for name in RUNTIME_FILES:
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


def runtime_manifest(directory):
    """Record every copied runtime byte; no ambient interpreter packages."""
    directory = Path(directory)
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("A bundled runtime may not contain symlinks.")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def bundle_manifest(path):
    """Bind recoverable bytes and permissions; never traverse bundle symlinks."""
    if existing_bundle_identity(path) is None:
        raise ValueError("The application to archive does not exist.")
    result, size = {}, 0
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError("Refusing a symlink inside the application archive: %s" % item)
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError("An application archive may contain regular files only.")
        size += item.stat().st_size
        if len(result) >= 10000 or size > 2 * 1024**3:
            raise ValueError("Application archive exceeds the 10,000-file / 2 GiB bound.")
        digest = hashlib.sha256()
        with item.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        result[item.relative_to(path).as_posix()] = {
            "sha256": digest.hexdigest(), "size": item.stat().st_size,
            "mode": stat.S_IMODE(item.stat().st_mode),
        }
    return result


def verify_archive(archive, name, expected):
    observed = {}
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            parts = Path(info.filename).parts
            if not parts or Path(info.filename).is_absolute() or ".." in parts or "\\" in info.filename:
                raise ValueError("Unsafe path in application archive.")
            if info.is_dir():
                continue
            if parts[0] == "__MACOSX":
                # ditto preserves extended attributes/resource forks here.
                source.read(info)  # Check the CRC before accepting the archive.
                continue
            if parts[0] != name or len(parts) < 2:
                raise ValueError("Application archive has an unexpected root.")
            key = "/".join(parts[1:])
            if key in observed or key not in expected or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Application archive contains an unexpected file or symlink.")
            digest = hashlib.sha256()
            with source.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            observed[key] = {"sha256": digest.hexdigest(), "size": info.file_size,
                             "mode": stat.S_IMODE(info.external_attr >> 16)}
    if observed != expected:
        raise ValueError("Application archive failed file, hash or permission verification.")


def archive_bundle(path, archive_dir):
    """Create and independently read back an archive before changing the app."""
    identity = existing_bundle_identity(path)
    expected = bundle_manifest(path)
    if archive_dir.is_symlink():
        raise ValueError("Refusing a symlink application archive directory.")
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = path.stem + "-" + stamp + "-" + uuid.uuid4().hex[:8] + ".zip"
    archive = archive_dir / name
    temporary = archive_dir / (".partial-" + uuid.uuid4().hex + ".zip")
    try:
        if sys.platform == "darwin":
            subprocess.run(["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                            str(path), str(temporary)], check=True, capture_output=True, timeout=60)
        else:
            # Also allows portable archive/rollback acceptance tests.
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as target:
                for relative in expected:
                    target.write(path / relative, path.name + "/" + relative)
        verify_archive(temporary, path.name, expected)
        if existing_bundle_identity(path) != identity or bundle_manifest(path) != expected:
            raise RuntimeError("The application changed while being archived; it was preserved.")
        os.rename(str(temporary), str(archive))
        receipt = {"original_path": str(path), "bundle_id": BUNDLE_ID,
                   "archive": archive.name, "files": expected}
        archive.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return archive, identity, expected
    finally:
        temporary.unlink(missing_ok=True)


def launch_services(path, register=False):
    tool = Path("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister")
    if sys.platform != "darwin" or not tool.is_file():
        return
    # Only this exact bundle is registered/unregistered. No global database reset.
    subprocess.run([str(tool), "-f" if register else "-u", str(path)],
                   capture_output=True, timeout=8, check=False)


def install_staged(staged, output, expected_identity):
    """Rollback preserves the original even if the destination move fails."""
    if existing_bundle_identity(output) != expected_identity:
        raise RuntimeError("The app destination changed during the build; installation was not attempted.")
    archive_dir = output.parent / ".CINEMATICUM-Backups.noindex"
    archive, hold = None, None
    if expected_identity is not None:
        archive, identity, expected = archive_bundle(output, archive_dir)
        if identity != expected_identity:
            raise RuntimeError("The application changed before replacement; it was preserved.")
        # Keep the rollback copy outside TemporaryDirectory cleanup and without
        # an .app suffix. A failed rollback therefore cannot delete the old app.
        hold = archive_dir / (".rollback-" + uuid.uuid4().hex)
        os.rename(str(output), str(hold))
    try:
        os.rename(str(staged), str(output))
    except BaseException:
        if hold is not None and not output.exists():
            os.rename(str(hold), str(output))
        raise
    if hold is not None:
        if bundle_manifest(hold) != expected:
            raise RuntimeError("New app installed; changed rollback copy preserved at %s" % hold)
        shutil.rmtree(hold)
    return archive


def consolidate_legacy_bundles(output):
    """Retire only recognized prior CINEMATICUM installers' sibling bundles."""
    archives, warnings = [], []
    candidates = sorted(set(output.parent.glob(output.stem + ".backup-*.app")) |
                        set(output.parent.glob(output.stem + ".rejected-*.app")))
    archive_dir = output.parent / ".CINEMATICUM-Backups.noindex"
    for path in candidates:
        try:
            archive, identity, expected = archive_bundle(path, archive_dir)
            if existing_bundle_identity(path) != identity or bundle_manifest(path) != expected:
                raise RuntimeError("Legacy application changed; it was preserved.")
            launch_services(path)
            retired = archive_dir / (".retired-" + uuid.uuid4().hex)
            os.rename(str(path), str(retired))
            if bundle_manifest(retired) != expected:
                os.rename(str(retired), str(path))
                raise RuntimeError("Legacy application changed while retiring; it was restored.")
            shutil.rmtree(retired)
            archives.append(str(archive))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
            warnings.append(str(path) + ": " + str(exc))
    return archives, warnings


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
    with tempfile.TemporaryDirectory(prefix=".cinematicum-build-", dir=str(output.parent)) as temporary:
        work = Path(temporary)
        staged = work / APP_NAME
        contents = staged / "Contents"
        executable = contents / "MacOS" / EXECUTABLE_NAME
        executable.parent.mkdir(parents=True)
        copy_runtime(contents / "Resources" / "studio", source)
        runtime_files = runtime_manifest(contents / "Resources" / "studio")
        source_record = {
            "format": "cinematicum-installed-source-v1",
            "version": bundle_info()["CFBundleShortVersionString"],
            "runtime_files": runtime_files,
            "native_sources": {name: hashlib.sha256((source / "macos" / name).read_bytes()).hexdigest()
                               for name in ("StudioApp.swift", "StudioIcon.swift")},
        }
        source_bytes = (json.dumps(source_record, sort_keys=True, indent=2) + "\n").encode()
        (contents / "Resources" / "source-manifest.json").write_bytes(source_bytes)
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
        icon_source = source / "macos" / "StudioIcon.swift"
        if icon_source.is_symlink() or not icon_source.is_file():
            raise ValueError("Native icon source is missing or is a symlink.")
        icon_tool = work / "draw-icon"
        icon_build = subprocess.run([xcrun, "swiftc", "-swift-version", "5", "-framework", "Cocoa",
                                    "-module-cache-path", str(work / "module-cache"), str(icon_source),
                                    "-o", str(icon_tool)], capture_output=True, text=True, timeout=60)
        if icon_build.returncode:
            raise RuntimeError("Native icon compilation failed; existing app preserved.\n" + icon_build.stderr[-4000:])
        iconset = work / "StudioIcon.iconset"
        subprocess.run([str(icon_tool), str(iconset)], check=True, capture_output=True, timeout=15)
        subprocess.run([xcrun, "iconutil", "-c", "icns", str(iconset), "-o",
                        str(contents / "Resources" / "StudioIcon.icns")], check=True, capture_output=True, timeout=15)
        backup = install_staged(staged, output, original)
        legacy, warnings = consolidate_legacy_bundles(output)
        if runtime_manifest(output / "Contents" / "Resources" / "studio") != runtime_files:
            raise RuntimeError("The installed runtime differs from the built source manifest.")
        launch_services(output, register=True)
        return {"app": str(output), "bundle_id": BUNDLE_ID, "target": target,
                "backup": str(backup) if backup is not None else None,
                "legacy_archives": legacy, "archive_warnings": warnings,
                "compiler_warnings": compiled.stderr.strip(),
                "source_manifest_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "runtime_files_verified": len(runtime_files),
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

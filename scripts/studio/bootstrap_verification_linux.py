#!/usr/bin/env python3
"""Build the actual isolated Linux engines required by whole-Studio verification.

This is a foreground CI/bootstrap command, not a product runtime or a substitute
for verification. Package, source and checkpoint downloads use the existing
immutable locks. Managed installers publish their own inventories only after
real numerical/model acceptance. PBRT is built from the pinned upstream commit
and pinned submodules; the compiler and LLVM library remain recorded host inputs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

STUDIO = Path(__file__).resolve().parent
PBRT_COMMIT = "b4ce9687e6c695f5582997c61b0c66cf064bdb4a"
PBRT_URL = "https://github.com/mmp/pbrt-v4.git"
IMATH_COMMIT = "c0396a055a01bc537d32f435aee11a9b7ed6f0b5"
CHROMIUM_URL = "https://playwright.download.prss.microsoft.com/dbazure/download/playwright/builds/chromium/1161/chromium-linux.zip"
CHROMIUM_SHA256 = "25db802cce762a2c5c082b115671b8c37f8ef87c2d08e367d216d56e955e2496"
CHROMIUM_BYTES = 172886340
BUILD_REQUIREMENTS = """cmake==3.31.10 --hash=sha256:3c17bb24dba15f8ecc3fd706afe04264410ef88796f4115c119327c961d5dc57 --hash=sha256:2f766bb46367e5e0559fa33184653754bce044583a06014dcaebf8e6dff8a1f1
ninja==1.13.0 --hash=sha256:fb46acf6b93b8dd0322adc3a4945452a4e774b75b91293bafcc7b7f8e6517dfa
"""


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    if path.is_symlink():
        raise ValueError("Bootstrap records cannot replace symbolic links")
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def run(argv, *, cwd=None, timeout=900, log=None):
    if log:
        with log.open("ab") as stream:
            stream.write((json.dumps({"command": [str(x) for x in argv], "started_unix_seconds": time.time()}) + "\n").encode())
            result = subprocess.run([str(x) for x in argv], cwd=cwd, timeout=timeout,
                                    stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError("Command failed; see " + str(log))
        return ""
    result = subprocess.run([str(x) for x in argv], cwd=cwd, timeout=timeout,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Command failed: " + result.stderr[-3000:] + result.stdout[-1000:])
    return result.stdout


def require_venv(path, python):
    if path.is_symlink():
        raise ValueError("Bootstrap venv destination cannot be a symbolic link")
    if not path.exists():
        run([python, "-I", "-B", "-m", "venv", path], timeout=90)
    config = path / "pyvenv.cfg"
    if not config.is_file() or "include-system-site-packages = false" not in config.read_text():
        raise ValueError("Bootstrap requires a real isolated venv")
    return path / "bin/python"


def install_base(root, python):
    interpreter = require_venv(root / "verification", python)
    run([interpreter, "-I", "-B", "-m", "pip", "--isolated", "install",
         "--require-hashes", "--only-binary=:all:", "--no-compile",
         "--report", root / "base-pip-report.json", "-r",
         STUDIO / "verification-linux-x86_64.requirements.txt"],
        log=root / "base-install.log")
    run([interpreter, "-I", "-B", "-m", "pip", "check"])
    raw = root / "ENGINE_TEST_RAW_KODAK_DC50.KDC"
    run([python, "-I", "-B", STUDIO / "fetch_verification_raw.py", "--output", raw])
    print("Installed hash-pinned base verification engines and genuine RAW fixture", flush=True)


def downloads(root, workers):
    import install_learned_tracking as learned
    import install_physical_rendering as physical
    import install_ray_optics as optics
    import install_reconstruction as reconstruction

    records = {}
    for installer in (physical, optics, reconstruction):
        for item in installer.load_lock()[0]["packages"]:
            if item["filename"] in records and records[item["filename"]]["sha256"] != item["sha256"]:
                raise ValueError("Locked artifact filenames collide")
            records[item["filename"]] = item
    for item in learned.load_lock()[0]["downloads"]:
        if item["filename"] in records and records[item["filename"]]["sha256"] != item["sha256"]:
            raise ValueError("Locked artifact filenames collide")
        records[item["filename"]] = item
    cache = root / "downloads"
    cache.mkdir(exist_ok=True)

    def fetch(item):
        path = cache / item["filename"]
        if path.is_symlink():
            raise ValueError("Download caches cannot contain symbolic links")
        if path.exists():
            if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                raise ValueError("Existing artifact differs from its pinned identity: " + path.name)
            return item
        partial = path.with_name(path.name + ".bootstrap-part")
        if partial.exists() or partial.is_symlink():
            raise ValueError("A prior incomplete download needs explicit recovery: " + partial.name)
        opener = urllib.request.build_opener(learned._TrustedRedirects())
        request = urllib.request.Request(item["url"], headers={"Accept-Encoding": "identity"})
        with opener.open(request, timeout=45) as response, partial.open("xb") as stream:
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > item["size"]:
                    raise ValueError("Artifact exceeded its pinned byte count")
                stream.write(block)
        if partial.stat().st_size != item["size"] or digest(partial) != item["sha256"]:
            raise ValueError("Artifact failed its pinned byte count/SHA-256: " + path.name)
        os.replace(partial, path)
        print("Verified download " + path.name, flush=True)
        return item

    with ThreadPoolExecutor(max_workers=workers) as pool:
        verified = list(pool.map(fetch, records.values()))
    save(root / "download-receipt.json", {"schema": "cinematicum-ci-locked-downloads-v1", "files": verified})


def install_engines(root, python):
    import install_learned_tracking as learned
    import install_physical_rendering as physical
    import install_ray_optics as optics
    import install_reconstruction as reconstruction

    cache = root / "downloads"
    for name, installer in (("optics", optics), ("physical", physical),
                            ("reconstruction", reconstruction), ("learned", learned)):
        kwargs = {"download_cache" if name == "learned" else "wheel_cache": cache}
        if name == "optics":
            # This foreground Linux CI job has a 60-minute outer deadline.
            # Keep the product/native CLI default at its 14-second boundary.
            kwargs["phase_budget_seconds"] = 60
        elif name == "learned":
            kwargs["package_check_seconds"] = 60
        result = installer.install(destination=root / name / "runtime", python=python,
            progress=lambda value, label=name: print(label + ": " + value.get("phase", value["status"]), flush=True), **kwargs)
        save(root / (name + "-bootstrap.json"), result)
        print("Accepted managed runtime " + name, flush=True)


def build_pbrt(root, python, jobs):
    tools_python = require_venv(root / "build-tools", python)
    requirements = root / "build-tools.requirements.txt"
    requirements.write_text(BUILD_REQUIREMENTS)
    run([tools_python, "-I", "-B", "-m", "pip", "--isolated", "install", "--require-hashes",
         "--only-binary=:all:", "--no-compile", "--report", root / "build-tools-pip-report.json", "-r", requirements],
        log=root / "build-tools-install.log")
    source = root / "pbrt-source"
    if not source.exists():
        run(["git", "clone", "--filter=blob:none", "--no-checkout", PBRT_URL, source])
        run(["git", "checkout", "--detach", PBRT_COMMIT], cwd=source)
        run(["git", "submodule", "update", "--init", "--recursive", "--depth=1"], cwd=source)
    if run(["git", "rev-parse", "HEAD"], cwd=source).strip() != PBRT_COMMIT:
        raise ValueError("Existing PBRT checkout is not the pinned source")
    if run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=source).strip():
        raise ValueError("PBRT source has unaccepted changes")
    submodules = run(["git", "submodule", "status", "--recursive"], cwd=source).splitlines()
    if not submodules or any(not line.startswith(" ") for line in submodules):
        raise ValueError("PBRT submodules differ from their committed revisions")
    cmake = root / "build-tools/bin/cmake"
    build = root / "pbrt-build"
    run([cmake, "-S", source, "-B", build, "-G", "Ninja",
         "-DCMAKE_MAKE_PROGRAM=" + str(root / "build-tools/bin/ninja"),
         "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CUDA_COMPILER=NOTFOUND",
         "-DGLFW_BUILD_WAYLAND=OFF", "-DPBRT_USE_PREGENERATED_RGB_TO_SPECTRUM_TABLES=OFF",
         "-DCMAKE_DISABLE_FIND_PACKAGE_OpenEXR=TRUE", "-DOPENEXR_FORCE_INTERNAL_IMATH=ON",
         "-DOPENEXR_IMATH_TAG=" + IMATH_COMMIT], log=root / "pbrt-configure.log")
    imath = build / "_deps/imath-src"
    if (run(["git", "rev-parse", "HEAD"], cwd=imath).strip() != IMATH_COMMIT
            or run(["git", "status", "--porcelain"], cwd=imath).strip()):
        raise ValueError("Imath dependency differs from its immutable upstream revision")
    run([cmake, "--build", build, "--target", "pbrt_exe", "--parallel", str(jobs)],
        timeout=2400, log=root / "pbrt-build.log")
    binary = build / "pbrt"
    help_result = subprocess.run([str(binary), "--help"], capture_output=True,
                                 text=True, timeout=15, check=True)
    # Upstream PBRT writes its successful help output to stderr.
    help_text = help_result.stdout + help_result.stderr
    if "--disable-wavelength-jitter" not in help_text:
        raise ValueError("Built PBRT lacks the expected spectral renderer interface")
    save(root / "pbrt-build-receipt.json", {"schema": "cinematicum-ci-pbrt-build-v1",
        "source": PBRT_URL, "commit": PBRT_COMMIT, "submodules": submodules, "imath_commit": IMATH_COMMIT,
        "binary": str(binary), "binary_sha256": digest(binary), "bytes": binary.stat().st_size,
        "compiler": run(["c++", "--version"]).splitlines()[0], "cmake": run([cmake, "--version"]).splitlines()[0],
        "help_sha256": hashlib.sha256(help_text.encode()).hexdigest()})
    print("Built pinned PBRT CPU renderer", flush=True)


def install_scene(root):
    import install_scene_processing_runtime as scene
    save(root / "scene-bootstrap.json", scene.install(root / "scene"))
    print("Accepted exact Blender Cycles runtime", flush=True)


def install_browser(root):
    """Exact independent browser fixture; no application media or user session."""
    driver = root / "browser-driver"
    driver.mkdir(exist_ok=True)
    for source, target in (("verification-browser-package.json", "package.json"),
                           ("verification-browser-package-lock.json", "package-lock.json")):
        destination = driver / target
        data = (STUDIO / source).read_bytes()
        if destination.exists() and (destination.is_symlink() or destination.read_bytes() != data):
            raise ValueError("Existing browser driver has a different package lock")
        destination.write_bytes(data)
    run(["npm", "ci", "--prefix", driver, "--ignore-scripts", "--no-audit", "--no-fund"],
        log=root / "browser-driver-install.log")
    archive = root / "chromium-1161-linux.zip"
    if not archive.exists():
        with urllib.request.urlopen(CHROMIUM_URL, timeout=45) as response, archive.open("xb") as stream:
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > CHROMIUM_BYTES:
                    raise ValueError("Chromium archive exceeded its pinned size")
                stream.write(block)
    if archive.is_symlink() or archive.stat().st_size != CHROMIUM_BYTES or digest(archive) != CHROMIUM_SHA256:
        raise ValueError("Chromium archive differs from the accepted upstream bytes")
    destination = root / "browser-runtime"
    if destination.exists():
        raise ValueError("Choose a fresh browser-runtime directory; existing browser files are never replaced")
    destination.mkdir()
    records = {}
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > 1000 or sum(item.file_size for item in members) > 1024 * 1024 * 1024:
            raise ValueError("Chromium archive exceeds its extraction bounds")
        for item in members:
            relative = PurePosixPath(item.filename)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "chrome-linux":
                raise ValueError("Chromium archive path is unsafe")
            path = destination.joinpath(*relative.parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            mode = (item.external_attr >> 16) & 0o777
            if (item.external_attr >> 16) & 0o170000 not in (0, 0o100000):
                raise ValueError("Chromium archive contains an unexpected linked or special file")
            path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, path.open("xb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            path.chmod(mode or 0o644)
            records[item.filename] = {"bytes": path.stat().st_size, "sha256": digest(path), "mode": path.stat().st_mode & 0o777}
    version = run([destination / "chrome-linux/chrome", "--version"], timeout=15).strip()
    if version != "Chromium 134.0.6998.35":
        raise ValueError("Independent Chromium runtime has a different version")
    save(root / "browser-runtime-receipt.json", {"schema": "cinematicum-ci-browser-v1", "url": CHROMIUM_URL,
        "archive_sha256": CHROMIUM_SHA256, "archive_bytes": CHROMIUM_BYTES, "version": version, "files": records})
    print("Accepted hash-pinned independent Chromium browser fixture", flush=True)


def environment(root):
    import install_scene_processing_runtime as scene
    values = {"CINEMATICUM_IMAGING_PYTHON": str(root / "verification/bin/python"),
        "CINEMATICUM_TRACKING_PYTHON": str(root / "verification/bin/python"),
        "CINEMATICUM_OPTICS_PYTHON": str(root / "optics/runtime/bin/python"),
        "CINEMATICUM_PHYSICAL_PYTHON": str(root / "physical/runtime/bin/python"),
        "CINEMATICUM_RECONSTRUCTION_PYTHON": str(root / "reconstruction/runtime/bin/python"),
        "CINEMATICUM_LEARNED_PYTHON": str(root / "learned/runtime/bin/python"),
        "CINEMATICUM_RAW_TEST_FILE": str(root / "ENGINE_TEST_RAW_KODAK_DC50.KDC"),
        "CINEMATICUM_PBRT": str(root / "pbrt-build/pbrt"),
        "CINEMATICUM_BROWSER": str(root / "browser-runtime/chrome-linux/chrome"),
        "NODE_PATH": str(root / "browser-driver/node_modules")}
    candidates = [Path("/usr/lib/x86_64-linux-gnu/libLLVM.so.20.1")]
    candidates += [Path(f"/usr/lib/llvm-{version}/lib/libLLVM.so") for version in (20, 19, 18, 17, 16, 15)]
    llvm = next((path.resolve() for path in candidates if path.is_file()), None)
    if llvm is not None:
        values["CINEMATICUM_PHYSICAL_LLVM"] = str(llvm)
    save(root / "verification-environment.json", values)
    paths = [str(root / "scene" / scene.ROOT_NAME)]
    save(root / "verification-path.json", paths)
    os.environ.update(values)
    os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])
    return values, paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", "base", "downloads", "engines", "pbrt", "scene", "browser"), default="all")
    parser.add_argument("--download-jobs", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--build-jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--github-path", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64" or sys.version_info[:2] != (3, 12):
        raise ValueError("Whole-build Linux verification requires native CPython 3.12 on x86_64")
    root = args.root.expanduser().absolute()
    if root.is_symlink() or ".." in root.parts or any(c in str(root) for c in "\r\n\0"):
        raise ValueError("Choose a real absolute bootstrap root without traversal or control characters")
    root.mkdir(parents=True, exist_ok=True)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(STUDIO))
    values, paths = environment(root)
    stages = {"base": lambda: install_base(root, sys.executable),
              "downloads": lambda: downloads(root, args.download_jobs),
              "engines": lambda: install_engines(root, sys.executable),
              "pbrt": lambda: build_pbrt(root, sys.executable, args.build_jobs),
              "scene": lambda: install_scene(root), "browser": lambda: install_browser(root)}
    for name in stages if args.stage == "all" else [args.stage]:
        started = time.monotonic()
        try:
            stages[name]()
        except Exception as exc:
            save(root / ("bootstrap-" + name + "-failure-" + str(time.time_ns()) + ".json"),
                 {"stage": name, "completed": False, "exception": type(exc).__name__, "error": str(exc),
                  "elapsed_seconds": round(time.monotonic() - started, 3), "bootstrap_sha256": digest(Path(__file__))})
            raise
    if args.github_env:
        with args.github_env.open("a") as stream:
            for key, value in values.items():
                stream.write(key + "=" + value + "\n")
    if args.github_path:
        with args.github_path.open("a") as stream:
            stream.write("\n".join(paths) + "\n")
    print(json.dumps({"stage": args.stage, "completed": True, "environment": str(root / "verification-environment.json")}))


if __name__ == "__main__":
    main()

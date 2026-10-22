#!/usr/bin/env python3
"""Run the entire discoverable suite in a pinned, isolated verification venv.

Use the venv's python with -I. Imaging/tracking use this interpreter; Optiland,
Mitsuba and learned inference use their separate pinned, isolated runtimes.
Every skip fails by default, including a skipped setUpClass. The complete
declared source inventory is verified and must remain unchanged during the run.
--allow-missing-raw permits only the named genuine-camera fixture test when no
RAW path was supplied; CI supplies a hash-verified fixture and never uses it.
Native macOS/Blender executable harnesses remain separate acceptance gates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest

STUDIO = Path(__file__).resolve().parent
ROOT = STUDIO.parents[1]
REQUIREMENTS = STUDIO / "verification-linux-x86_64.requirements.txt"
RAW_TEST = "test_imaging.ImagingRuntimeTests.test_genuine_camera_raw_development_and_white_balance"
RAW_REASON = "CINEMATICUM_RAW_TEST_FILE is needed for genuine camera fixture acceptance"


class VerificationResult(unittest.TextTestResult):
    def __init__(self, *args, allow_missing_raw=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_missing_raw = allow_missing_raw
        self.unexpected_skips = []
        self.allowed_skips = []

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        record = {"test": test.id(), "reason": reason}
        if self.allow_missing_raw and test.id() == RAW_TEST and reason == RAW_REASON:
            self.allowed_skips.append(record)
        else:
            self.unexpected_skips.append(record)

    def wasSuccessful(self):
        return super().wasSuccessful() and not self.unexpected_skips and not self.expectedFailures


def run_suite(suite, *, allow_missing_raw=False, stream=None):
    if not suite.countTestCases():
        raise ValueError("Verification discovered no tests")
    return unittest.TextTestRunner(verbosity=2, stream=stream,
        resultclass=lambda *args, **kwargs: VerificationResult(
            *args, allow_missing_raw=allow_missing_raw, **kwargs)).run(suite)


def _literal_requirements(path):
    for statement in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "RUNTIME_REQUIREMENTS"
                                                    for t in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError("Runtime version contract is missing from " + path.name)


def pinned_versions():
    pinned = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([0-9A-Za-z_.+-]+)", parts[0])
        if (not match or len(parts) < 2 or any(not re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", item) for item in parts[1:])
                or match[1] in pinned):
            raise ValueError("Verification requirements must pin unique versions and SHA-256 wheel hashes")
        pinned[match[1]] = match[2]
    for path in (STUDIO / "imaging.py", STUDIO / "install_tracking.py"):
        for name, version in _literal_requirements(path).items():
            if pinned.get(name) != version:
                raise ValueError("Verification and product runtime versions disagree for " + name)
    if "opentimelineio" not in pinned:
        raise ValueError("The independent OpenTimelineIO verifier must be installed")
    return pinned


def prepare_runtime(allow_missing_raw=False):
    prefix = Path(sys.prefix).resolve()
    if sys.prefix == sys.base_prefix or not sys.flags.isolated:
        raise ValueError("Run an isolated venv interpreter with -I; ambient/system packages are not verification evidence")
    config = prefix / "pyvenv.cfg"
    if not config.is_file() or not re.search(r"(?mi)^include-system-site-packages\s*=\s*false\s*$", config.read_text()):
        raise ValueError("The verification venv must exclude system site packages")
    for binary in ("git", "ffmpeg", "ffprobe", "node"):
        if not shutil.which(binary):
            raise ValueError("Required verification executable is unavailable: " + binary)
    versions = {}
    for name, expected in pinned_versions().items():
        distribution = importlib.metadata.distribution(name)
        if not Path(distribution.locate_file("")).resolve().is_relative_to(prefix):
            raise ValueError("Verification package is outside the isolated venv: " + name)
        if distribution.version != expected:
            raise ValueError(f"Verification requires {name}=={expected}; installed {distribution.version}")
        versions[name] = distribution.version
    raw = os.environ.get("CINEMATICUM_RAW_TEST_FILE")
    raw_record = None
    if raw:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise ValueError("The configured genuine RAW fixture does not exist")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        raw_record = {"name": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()}
        os.environ["CINEMATICUM_RAW_TEST_FILE"] = str(path)
    elif not allow_missing_raw:
        raise ValueError("Supply CINEMATICUM_RAW_TEST_FILE or explicitly choose --allow-missing-raw")
    os.environ["CINEMATICUM_IMAGING_PYTHON"] = sys.executable
    os.environ["CINEMATICUM_TRACKING_PYTHON"] = sys.executable
    return {"python": sys.version, "interpreter": sys.executable, "versions": versions,
            "raw_fixture": raw_record, "allow_missing_raw": allow_missing_raw and raw_record is None}


def _external_python_identity(executable, expected):
    """Measure the actual isolated interpreter and package origins, not a path label."""
    if not executable:
        raise ValueError("A required isolated worker interpreter is unavailable")
    program = r'''
import hashlib, importlib.metadata, json, pathlib, re, sys
prefix = pathlib.Path(sys.prefix).resolve()
if sys.prefix == sys.base_prefix or not sys.flags.isolated:
    raise ValueError("The verification worker must use an isolated venv")
config = prefix / "pyvenv.cfg"
if not config.is_file() or not re.search(r"(?mi)^include-system-site-packages\s*=\s*false\s*$", config.read_text()):
    raise ValueError("The verification worker must exclude system site packages")
versions = {}
for name, expected in json.loads(sys.argv[1]).items():
    distribution = importlib.metadata.distribution(name)
    if not pathlib.Path(distribution.locate_file("")).resolve().is_relative_to(prefix):
        raise ValueError("Verification worker package is outside its venv: " + name)
    if distribution.version != expected:
        raise ValueError("Verification worker package version differs: " + name)
    versions[name] = distribution.version
binary = pathlib.Path(sys.executable).resolve()
print(json.dumps({"python": sys.version, "interpreter": sys.executable,
                  "interpreter_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                  "prefix": str(prefix), "versions": versions}))
'''
    result = subprocess.run([executable, "-I", "-B", "-c", program, json.dumps(expected)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode or len(result.stdout) > 128 * 1024:
        raise ValueError("A required isolated worker identity check failed: " + result.stderr[-2000:])
    return json.loads(result.stdout)


def prepare_optional_runtimes():
    from install_ray_optics import PINNED_PACKAGES as optics_versions, load_lock as optics_lock
    from install_physical_rendering import PINNED_PACKAGES as physical_versions, load_lock as physical_lock
    from ray_optics import find_ray_optics_python, ray_optics_capabilities
    from physical_rendering import find_python, find_pbrt, capabilities as physical_capabilities
    from learned_tracking import find_learned_python, learned_capabilities
    from reconstruction import find_python as reconstruction_python, capabilities as reconstruction_capabilities
    from install_reconstruction import PINNED_PACKAGES as reconstruction_versions, load_lock as reconstruction_lock
    records = {}
    for name, interpreter, probe, expected, lock in (
            ("optiland", find_ray_optics_python(), ray_optics_capabilities, optics_versions, optics_lock),
            ("physical", find_python(), physical_capabilities, physical_versions, physical_lock),
            ("reconstruction", reconstruction_python(), reconstruction_capabilities, reconstruction_versions, reconstruction_lock)):
        identity = _external_python_identity(interpreter, expected)
        capability = probe(interpreter)
        if not capability.get("available"):
            raise ValueError("Required actual " + name + " worker failed: " + str(capability.get("reason")))
        records[name] = {"identity": identity, "capabilities": capability, "wheel_lock_sha256": lock()[1]}
    learned = learned_capabilities()
    if not learned.get("available"):
        raise ValueError("Required actual SAM2/TAPIR checkpoints failed: " + str(learned.get("reason")))
    records["learned"] = {"identity": _external_python_identity(find_learned_python(), learned["versions"]),
                          "capabilities": learned}
    binary = find_pbrt()
    if not binary:
        raise ValueError("Actual PBRT-v4 is required for transport and independent renderer acceptance")
    path = Path(binary)
    help_run = subprocess.run([str(path), "--help"], capture_output=True, timeout=15)
    if help_run.returncode or b"--disable-wavelength-jitter" not in help_run.stdout + help_run.stderr:
        raise ValueError("The configured PBRT executable did not expose its real spectral renderer interface")
    records["pbrt"] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "bytes": path.stat().st_size, "help_sha256": hashlib.sha256(help_run.stdout + help_run.stderr).hexdigest()}
    from adapters import find_blender
    from install_scene_processing_runtime import _verify_binary, VERSION as blender_version, BUILD as blender_build
    blender = find_blender()
    if not blender:
        raise ValueError("Actual pinned Blender Cycles is required for scene and distributed rendering acceptance")
    path = Path(blender)
    version_text = _verify_binary(path)
    records["blender"] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "bytes": path.stat().st_size, "version": blender_version, "build": blender_build,
                          "version_output": version_text}
    return records


def verify_managed_runtimes():
    """Reject changed installed bytes even when versions/imports still succeed."""
    import install_ray_optics
    import install_physical_rendering
    import install_learned_tracking
    import install_reconstruction
    from ray_optics import find_ray_optics_python
    from physical_rendering import find_python as physical_python
    from learned_tracking import find_learned_python
    from reconstruction import find_python as reconstruction_python
    records = {}
    for name, installer, interpreter in (
            ("optiland", install_ray_optics, find_ray_optics_python()),
            ("physical", install_physical_rendering, physical_python()),
            ("learned", install_learned_tracking, find_learned_python()),
            ("reconstruction", install_reconstruction, reconstruction_python())):
        if not interpreter:
            raise ValueError("Required managed runtime is absent: " + name)
        destination = Path(interpreter).expanduser().absolute().parent.parent
        # The installer validates the owned stable link, lock, external
        # prerequisites, complete inventory and real numerical probes.
        check = installer.install(destination=destination, check_only=True)
        runtime = destination.resolve(strict=True)
        receipt_path = runtime / installer.RECEIPT
        if receipt_path.is_symlink() or receipt_path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Invalid managed runtime receipt: " + name)
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
        inventory = installer._inventory(runtime)
        if inventory != receipt.get("inventory"):
            raise ValueError("Managed " + name + " runtime changed during its actual check")
        encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        records[name] = {
            "destination": str(destination), "runtime": str(runtime),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "inventory_sha256": hashlib.sha256(encoded).hexdigest(),
            "inventory_entries": len(inventory),
            "file_bytes": sum(value.get("bytes", 0) for value in inventory.values()),
            "check": check,
        }
    from adapters import find_blender
    import install_scene_processing_runtime as cycles
    binary = find_blender()
    if not binary:
        raise ValueError("The managed Cycles runtime is unavailable")
    destination = Path(binary).absolute().parent.parent
    check = cycles.install(destination, check=True)
    receipt_path = destination / "cinematicum-runtime.json"
    receipt_bytes = receipt_path.read_bytes()
    inventory = cycles._inventory(destination / cycles.ROOT_NAME)
    if inventory != json.loads(receipt_bytes).get("inventory"):
        raise ValueError("Managed Cycles runtime changed during its actual check")
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    records["blender"] = {
        "destination": str(destination), "runtime": str(destination / cycles.ROOT_NAME),
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "inventory_sha256": hashlib.sha256(encoded).hexdigest(),
        "inventory_entries": len(inventory["files"]), "file_bytes": inventory["bytes"], "check": check,
    }
    return records


def managed_identities(records):
    return {name: {key: item[key] for key in ("destination", "runtime", "receipt_sha256",
                   "inventory_sha256", "inventory_entries", "file_bytes")}
            for name, item in records.items()}


def frozen_source():
    from source_integrity import build_manifest, file_record, verify_manifest, MANIFEST
    check = verify_manifest(ROOT)
    if not check["passed"]:
        raise ValueError("The declared source manifest does not match this verification input: " + json.dumps(check, sort_keys=True))
    inventory = build_manifest(ROOT)
    inventory["manifest"] = file_record(ROOT, MANIFEST)
    data = json.dumps(inventory, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"sha256": hashlib.sha256(data).hexdigest(), "inventory": inventory}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-missing-raw", action="store_true", help="Permit only the absent genuine RAW fixture test; CI forbids all skips")
    parser.add_argument("--report", type=Path, help="Write a machine-readable execution result outside the source tree")
    args = parser.parse_args(argv)
    report_path = args.report.absolute() if args.report else None
    report = {"schema": "cinematicum-verification-run", "version": 2, "passed": False,
              "scope": "Complete discoverable Python/Node/media suite; native executable harnesses run separately"}
    started = time.monotonic()
    before = None
    runtime_before = None
    try:
        sys.path.insert(0, str(STUDIO))
        before = frozen_source()
        report["source"] = before
        report["runtime"] = prepare_runtime(args.allow_missing_raw)
        runtime_before = verify_managed_runtimes()
        report["managed_runtimes_before"] = runtime_before
        report["optional_runtimes"] = prepare_optional_runtimes()
        os.chdir(ROOT)
        suite = unittest.defaultTestLoader.discover(str(STUDIO), pattern="test_*.py")
        result = run_suite(suite, allow_missing_raw=report["runtime"]["allow_missing_raw"])
        report.update(passed=result.wasSuccessful(), tests_run=result.testsRun,
                      failures=[test.id() for test, _ in result.failures], errors=[test.id() for test, _ in result.errors],
                      expected_failures=[test.id() for test, _ in result.expectedFailures],
                      unexpected_successes=[test.id() for test in result.unexpectedSuccesses],
                      allowed_skips=result.allowed_skips, unexpected_skips=result.unexpected_skips)
        status = 0 if report["passed"] else 1
    except (OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
        report["preflight_error"] = str(exc)
        status = 2
    finally:
        if runtime_before is not None:
            try:
                runtime_after = verify_managed_runtimes()
                report["managed_runtimes_after"] = runtime_after
                report["managed_runtimes_unchanged"] = managed_identities(runtime_before) == managed_identities(runtime_after)
                if not report["managed_runtimes_unchanged"]:
                    report["passed"], status = False, 1
                    report["managed_runtime_error"] = "Managed runtime or its installation receipt changed during verification"
            except (OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
                report["passed"], status = False, 1
                report["managed_runtimes_unchanged"] = False
                report["managed_runtime_error"] = str(exc)
        if before is not None:
            try:
                after = frozen_source()
                report["source_unchanged"] = before == after
                report["source_after_sha256"] = after["sha256"]
                if not report["source_unchanged"]:
                    report["passed"], status = False, 1
                    report["source_error"] = "Declared source changed during verification"
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                report["passed"], status = False, 1
                report["source_unchanged"] = False
                report["source_error"] = str(exc)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    text = json.dumps(report, indent=2) + "\n"
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())

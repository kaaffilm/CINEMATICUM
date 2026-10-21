#!/usr/bin/env python3
"""Run the entire discoverable suite in a pinned, isolated verification venv.

Use the venv's python with -I. Both real worker runtimes are bound to that same
interpreter. Every skip fails by default, including a skipped setUpClass.
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-missing-raw", action="store_true", help="Permit only the absent genuine RAW fixture test; CI forbids all skips")
    parser.add_argument("--report", type=Path, help="Write a machine-readable execution result outside the source tree")
    args = parser.parse_args(argv)
    report_path = args.report.absolute() if args.report else None
    report = {"schema": "cinematicum-verification-run", "version": 1, "passed": False,
              "scope": "Complete discoverable Python/Node/media suite; native executable harnesses run separately"}
    started = time.monotonic()
    try:
        report["runtime"] = prepare_runtime(args.allow_missing_raw)
        os.chdir(ROOT)
        suite = unittest.defaultTestLoader.discover(str(STUDIO), pattern="test_*.py")
        result = run_suite(suite, allow_missing_raw=report["runtime"]["allow_missing_raw"])
        report.update(passed=result.wasSuccessful(), tests_run=result.testsRun,
                      failures=[test.id() for test, _ in result.failures], errors=[test.id() for test, _ in result.errors],
                      expected_failures=[test.id() for test, _ in result.expectedFailures],
                      unexpected_successes=[test.id() for test in result.unexpectedSuccesses],
                      allowed_skips=result.allowed_skips, unexpected_skips=result.unexpected_skips)
        status = 0 if report["passed"] else 1
    except (OSError, ValueError, ImportError) as exc:
        report["preflight_error"] = str(exc)
        status = 2
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    text = json.dumps(report, indent=2) + "\n"
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())

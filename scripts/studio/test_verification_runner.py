"""Exercise the release runner's protection against apparently green skips."""
import io
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from run_verification import RAW_REASON, RAW_TEST, run_suite
import run_verification as runner


class VerificationRunnerTests(unittest.TestCase):
    def fixture(self, ident, reason):
        class Fixture(unittest.TestCase):
            def runTest(self):
                self.skipTest(reason)

            def id(self):
                return ident
        return Fixture()

    def test_missing_runtime_skip_fails_even_when_raw_is_declared_optional(self):
        for optional in (False, True):
            result = run_suite(unittest.TestSuite([self.fixture("test_planar_tracking.PlanarInferenceTests.test_measure",
                "Actual OpenCV planar runtime unavailable")]), allow_missing_raw=optional, stream=io.StringIO())
            self.assertFalse(result.wasSuccessful())
            self.assertEqual(len(result.unexpected_skips), 1)
            self.assertEqual(result.allowed_skips, [])

    def test_class_setup_skip_is_not_hidden_by_zero_executed_tests(self):
        class MissingRuntime(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest("Unavailable engine")

            def test_inference(self):
                self.fail("Missing engine cannot reach inference")
        result = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(MissingRuntime), stream=io.StringIO())
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.testsRun, 0)
        self.assertEqual(len(result.unexpected_skips), 1)
        with self.assertRaisesRegex(ValueError, "no tests"):
            run_suite(unittest.TestSuite(), stream=io.StringIO())

    def test_only_exact_explicit_raw_exception_is_accepted(self):
        for ident, reason, optional, allowed in (
            (RAW_TEST, RAW_REASON, False, False), (RAW_TEST, RAW_REASON, True, True),
            (RAW_TEST, "Broken RAW engine", True, False), (RAW_TEST + "_other", RAW_REASON, True, False)):
            with self.subTest(ident=ident, reason=reason, optional=optional):
                result = run_suite(unittest.TestSuite([self.fixture(ident, reason)]),
                                   allow_missing_raw=optional, stream=io.StringIO())
                self.assertEqual(result.wasSuccessful(), allowed)

    def test_successful_tests_cannot_certify_source_changed_during_the_run(self):
        from source_integrity import write_manifest
        for regenerate in (False, True):
            with self.subTest(regenerate_manifest=regenerate), tempfile.TemporaryDirectory(prefix="cinematicum-runner-freeze-TEST-") as temporary:
                root = Path(temporary)
                files = {"README.md": "original release input\n",
                         ".github/workflows/studio-verification.yml": "name: fixture\n",
                         "scripts/studio/server.py": 'VERSION = "0.10.0"\n',
                         "scripts/studio/test_release_input_mutation_fixture.py": (
                             "import pathlib, unittest\n"
                             "class MutationFixture(unittest.TestCase):\n"
                             "    def test_changes_a_declared_source_after_verification_starts(self):\n"
                             "        root = pathlib.Path(__file__).resolve().parents[2]\n"
                             "        (root / 'README.md').write_text('changed release input\\n')\n"
                             + ("        from source_integrity import write_manifest\n        write_manifest(root)\n" if regenerate else ""))}
                for name, data in files.items():
                    destination = root / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(data)
                subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, timeout=10)
                subprocess.run(["git", "-C", str(root), "add", "--", *files], check=True, capture_output=True, timeout=10)
                write_manifest(root)
                report_path = root / "fixture-report.json"
                previous_directory, previous_path = Path.cwd(), list(sys.path)
                try:
                    with (patch.object(runner, "ROOT", root), patch.object(runner, "STUDIO", root / "scripts/studio"),
                          patch.object(runner, "prepare_runtime", return_value={"allow_missing_raw": False}),
                          patch.object(runner, "verify_managed_runtimes", return_value={}),
                          patch.object(runner, "prepare_optional_runtimes", return_value={}),
                          patch.object(runner.unittest, "defaultTestLoader", unittest.TestLoader()),
                          contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                        status = runner.main(["--report", str(report_path)])
                finally:
                    os.chdir(previous_directory)
                    sys.path[:] = previous_path
                    sys.modules.pop("test_release_input_mutation_fixture", None)
                report = json.loads(report_path.read_text())
                self.assertEqual(1, status)
                self.assertEqual(1, report["tests_run"])
                self.assertEqual([], report["failures"])
                self.assertEqual([], report["errors"])
                self.assertFalse(report["source_unchanged"])
                self.assertFalse(report["passed"])
                self.assertIn("source_error", report)

    def test_successful_tests_cannot_certify_changed_runtime_or_replaced_receipt(self):
        for target in ("runtime", "receipt"):
            with self.subTest(changed=target), tempfile.TemporaryDirectory(prefix="cinematicum-runner-runtime-TEST-") as temporary:
                root = Path(temporary)
                binary, receipt = root / "engine.bin", root / "receipt.json"
                binary.write_bytes(b"original engine")
                receipt.write_bytes(b"original receipt")

                def identities():
                    return {"fixture": {
                        "destination": str(root), "runtime": str(root),
                        "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                        "inventory_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                        "inventory_entries": 1, "file_bytes": binary.stat().st_size,
                    }}

                class MutationFixture(unittest.TestCase):
                    def runTest(self):
                        (binary if target == "runtime" else receipt).write_bytes(b"changed input")

                report_path = root / "report.json"
                previous_directory, previous_path = Path.cwd(), list(sys.path)
                try:
                    with (patch.object(runner, "ROOT", root), patch.object(runner, "STUDIO", root),
                          patch.object(runner, "frozen_source", return_value={"sha256": "unchanged source"}),
                          patch.object(runner, "prepare_runtime", return_value={"allow_missing_raw": False}),
                          patch.object(runner, "verify_managed_runtimes", side_effect=identities),
                          patch.object(runner, "prepare_optional_runtimes", return_value={}),
                          patch.object(runner.unittest.defaultTestLoader, "discover", return_value=unittest.TestSuite([MutationFixture()])),
                          contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                        status = runner.main(["--report", str(report_path)])
                finally:
                    os.chdir(previous_directory)
                    sys.path[:] = previous_path
                report = json.loads(report_path.read_text())
                self.assertEqual(status, 1)
                self.assertEqual(report["tests_run"], 1)
                self.assertEqual(report["failures"], [])
                self.assertEqual(report["errors"], [])
                self.assertTrue(report["source_unchanged"])
                self.assertFalse(report["managed_runtimes_unchanged"])
                self.assertFalse(report["passed"])
                self.assertIn("managed_runtime_error", report)


if __name__ == "__main__":
    unittest.main()

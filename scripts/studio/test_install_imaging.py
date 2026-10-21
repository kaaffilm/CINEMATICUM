"""Imaging installation publication, preservation and locked-wheel acceptance."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import install_imaging as installer


class ImagingInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-imaging-install-TEST-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.destination = self.root / "py313-v1"
        self.host = patch.object(installer, "_require_host")
        self.host.start()
        self.addCleanup(self.host.stop)
        self.python = patch.object(installer, "choose_python", return_value=Path("/absolute/python3.13"))
        self.python.start()
        self.addCleanup(self.python.stop)

    def test_lock_has_exact_runtime_pins_and_official_binary_wheel_hashes(self):
        lock, digest = installer.load_lock()
        self.assertEqual({p["name"]: p["version"] for p in lock["packages"]}, installer.RUNTIME_REQUIREMENTS)
        self.assertEqual(len(digest), 64)
        self.assertEqual({p["filename"].split("-", 2)[2] for p in lock["packages"]}, {"cp313-cp313-macosx_11_0_arm64.whl"})
        self.assertEqual(next(p for p in lock["packages"] if p["name"] == "OpenEXR")["sha256"],
                         "ac03f3cb7e274ad792b2f66df100f5605e9d586e6b3db0a2722e7c53a15acc42")

    def test_new_runtime_stays_at_verified_path_and_publishes_atomically(self):
        verification = {"versions": installer.RUNTIME_REQUIREMENTS.copy(), "checks": dict.fromkeys(installer.PROBE_CHECKS, True)}
        built = []
        def build(directory, python, lock):
            self.assertFalse(os.path.lexists(self.destination), "Stable runtime became visible before verification")
            (directory / "original-path.txt").write_text(str(directory))
            built.append(directory)
            return verification
        with patch.object(installer, "_build_runtime", side_effect=build):
            result = installer.install(self.destination)
        self.assertEqual(result["status"], "installed")
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(self.destination.resolve(), built[0])
        self.assertEqual((self.destination / "original-path.txt").read_text(), str(built[0]))
        receipt = json.loads((self.destination / installer.RECEIPT).read_text())
        self.assertEqual(receipt["runtime_directory"], str(built[0]))
        self.assertEqual(receipt["verification"], verification)
        with patch.object(installer, "probe_runtime", return_value=verification), patch.object(installer, "_build_runtime") as build_again:
            repeat = installer.install(self.destination)
            build_again.assert_not_called()
        self.assertEqual(repeat["status"], "unchanged")
        self.assertEqual(list(built[0].parent.iterdir()), built)

    def test_failed_new_install_removes_only_its_unpublished_runtime(self):
        sibling = self.root / "unrelated"
        sibling.mkdir()
        (sibling / "keep").write_bytes(b"important original")
        with patch.object(installer, "_build_runtime", side_effect=RuntimeError("Wheel hash mismatch")):
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                installer.install(self.destination)
        self.assertFalse(os.path.lexists(self.destination))
        self.assertEqual(list((self.root / installer.VERSIONS_DIRECTORY).iterdir()), [])
        self.assertEqual((sibling / "keep").read_bytes(), b"important original")

    def test_concurrent_destination_creation_is_never_replaced(self):
        def build(directory, python, lock):
            self.destination.write_bytes(b"arrived while installing")
            return {"healthy": True}
        with patch.object(installer, "_build_runtime", side_effect=build):
            with self.assertRaises(FileExistsError):
                installer.install(self.destination)
        self.assertEqual(self.destination.read_bytes(), b"arrived while installing")
        self.assertEqual(list((self.root / installer.VERSIONS_DIRECTORY).iterdir()), [])

    def test_unrelated_file_unmanaged_link_and_unhealthy_environment_are_preserved(self):
        self.destination.write_bytes(b"not ours")
        with self.assertRaisesRegex(ValueError, "unrelated file"):
            installer.install(self.destination)
        self.assertEqual(self.destination.read_bytes(), b"not ours")
        self.destination.unlink()
        unrelated = self.root / "someone-elses-runtime"
        unrelated.mkdir()
        self.destination.symlink_to(unrelated, target_is_directory=True)
        with patch.object(installer, "probe_runtime") as probe:
            with self.assertRaisesRegex(ValueError, "unrelated symlink"):
                installer.install(self.destination)
            probe.assert_not_called()
        self.assertTrue(self.destination.is_symlink())
        self.destination.unlink()
        self.destination.mkdir()
        (self.destination / "preserve").write_bytes(b"existing environment")
        with patch.object(installer, "probe_runtime", side_effect=ValueError("wrong versions")), patch.object(installer, "_build_runtime") as build:
            with self.assertRaisesRegex(ValueError, "wrong versions"):
                installer.install(self.destination)
            build.assert_not_called()
        self.assertEqual((self.destination / "preserve").read_bytes(), b"existing environment")

    def test_healthy_existing_real_directory_is_read_only_and_check_missing_does_not_install(self):
        with patch.object(installer, "_build_runtime") as build:
            with self.assertRaisesRegex(ValueError, "not installed"):
                installer.install(self.destination, check_only=True)
            build.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])
        self.destination.mkdir()
        (self.destination / "keep").write_bytes(b"older manual installation")
        with patch.object(installer, "probe_runtime", return_value={"healthy": True}), patch.object(installer, "_build_runtime") as build:
            result = installer.install(self.destination)
            build.assert_not_called()
        self.assertEqual(result["status"], "unchanged")
        self.assertIn("original wheel hashes not asserted", result["existing_wheel_provenance"])
        self.assertEqual(list(self.destination.iterdir()), [self.destination / "keep"])

    def test_pip_report_must_match_actual_url_version_and_sha256_for_every_wheel(self):
        lock, _ = installer.load_lock()
        report = {"install": [{"metadata": {"name": p["name"], "version": p["version"]},
                                "download_info": {"url": p["url"], "archive_info": {"hashes": {"sha256": p["sha256"]}}}}
                               for p in lock["packages"]]}
        path = self.root / "pip.json"
        path.write_text(json.dumps(report))
        installer.verify_pip_report(path, lock)
        for property_name in ("hash", "version", "url", "duplicate"):
            altered = copy.deepcopy(report)
            if property_name == "hash":
                altered["install"][0]["download_info"]["archive_info"]["hashes"]["sha256"] = "0" * 64
            elif property_name == "version":
                altered["install"][0]["metadata"]["version"] = "99.0"
            elif property_name == "url":
                altered["install"][0]["download_info"]["url"] = "https://example.org/same-name.whl"
            else:
                altered["install"][1] = altered["install"][0]
            path.write_text(json.dumps(altered))
            with self.subTest(property_name=property_name), self.assertRaises(ValueError):
                installer.verify_pip_report(path, lock)

    def test_actual_numerical_probe_when_optional_runtime_is_available(self):
        python = os.environ.get("CINEMATICUM_IMAGING_PYTHON")
        if not python or not Path(python).is_file():
            self.skipTest("Set CINEMATICUM_IMAGING_PYTHON to exercise actual dependency imports and pixels")
        # The numerical proof is platform-neutral; publication remains limited
        # to the locked macOS arm64 / CPython 3.13 wheel ABI.
        result = subprocess.run([python, "-I", "-c", installer.RUNTIME_PROBE], capture_output=True, text=True, timeout=18, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report["versions"], installer.RUNTIME_REQUIREMENTS)
        self.assertEqual(report["checks"], dict.fromkeys(installer.PROBE_CHECKS, True))
        self.assertEqual(report["scene_linear"], "ACEScg")
        self.assertEqual(report["libraw"], "0.22.1")


if __name__ == "__main__":
    unittest.main()

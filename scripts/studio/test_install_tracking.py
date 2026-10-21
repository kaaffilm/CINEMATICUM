"""Pinned tracking runtime publication, existing-file preservation and cancellation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import install_tracking as installer


class TrackingInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-tracking-install-TEST-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.destination = self.root / "py313-v1"

    def test_lock_and_pip_report_bind_actual_binary_wheels(self):
        lock, digest = installer.load_lock()
        self.assertEqual(len(digest), 64)
        self.assertEqual({p["name"]:p["version"] for p in lock["packages"]}, installer.RUNTIME_REQUIREMENTS)
        self.assertEqual(next(p for p in lock["packages"] if p["name"] == "opencv-python-headless")["sha256"],
                         "48128188ade4a7e517237c8e1e11a9cdf5c282761473383e77beb875bb1e61ca")
        report = {"install":[{"metadata":{"name":p["name"],"version":p["version"]},
                              "download_info":{"url":p["url"],"archive_info":{"hashes":{"sha256":p["sha256"]}}}}
                             for p in lock["packages"]]}
        path = self.root / "pip-report.json"
        path.write_text(json.dumps(report))
        installer.verify_pip_report(path, lock)
        for change in ("sha256", "version", "extra"):
            changed = copy.deepcopy(report)
            if change == "sha256":
                changed["install"][1]["download_info"]["archive_info"]["hashes"]["sha256"] = "0"*64
            elif change == "version":
                changed["install"][1]["metadata"]["version"] = "unlocked"
            else:
                changed["install"].append(changed["install"][0])
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                installer.verify_pip_report(path, lock)

    def test_publishes_verified_stable_path_and_preserves_existing_runtime(self):
        built = []
        verified = {"versions":installer.RUNTIME_REQUIREMENTS.copy(),"checks":dict.fromkeys(installer.PROBE_CHECKS,True)}
        def build(directory, python, lock):
            self.assertFalse(self.destination.exists())
            built.append(directory)
            (directory / "permanent.txt").write_text(str(directory))
            return verified
        with patch.object(installer,"_require_host"), patch.object(installer,"choose_python",return_value=Path("/owned/python3.13")), patch.object(installer,"_build_runtime",side_effect=build):
            result = installer.install(self.destination)
        self.assertEqual(result["status"],"installed")
        self.assertEqual(self.destination.resolve(),built[0])
        self.assertEqual((self.destination/"permanent.txt").read_text(),str(built[0]))
        with patch.object(installer,"_require_host"), patch.object(installer,"probe_runtime",return_value=verified), patch.object(installer,"_build_runtime") as builder:
            again = installer.install(self.destination)
        builder.assert_not_called()
        self.assertEqual(again["status"],"unchanged")
        self.assertEqual(list(built[0].parent.iterdir()),built)

    def test_failed_build_and_unrelated_destination_preserve_user_files(self):
        sibling = self.root / "user-file"
        sibling.write_bytes(b"preserve")
        with patch.object(installer,"_require_host"), patch.object(installer,"choose_python",return_value=Path("/owned/python3.13")), patch.object(installer,"_build_runtime",side_effect=RuntimeError("Hash mismatch")):
            with self.assertRaisesRegex(RuntimeError,"Hash mismatch"):
                installer.install(self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list((self.root/installer.VERSIONS_DIRECTORY).iterdir()),[])
        self.destination.symlink_to(sibling)
        with patch.object(installer,"_require_host"), patch.object(installer,"_build_runtime") as builder:
            with self.assertRaisesRegex(ValueError,"unrelated symlink"):
                installer.install(self.destination)
        builder.assert_not_called()
        self.assertEqual(sibling.read_bytes(),b"preserve")

    def test_running_owned_install_command_is_cancellable(self):
        event = threading.Event()
        token = installer._CANCEL_EVENT.set(event)
        timer = threading.Timer(.15,event.set)
        started=time.monotonic();timer.start()
        try:
            with self.assertRaisesRegex(Exception,"cancel"):
                installer._run([sys.executable,"-c","import time; time.sleep(15)"],20)
        finally:
            installer._CANCEL_EVENT.reset(token);timer.cancel();timer.join()
        self.assertLess(time.monotonic()-started,3)


if __name__ == "__main__":
    unittest.main()

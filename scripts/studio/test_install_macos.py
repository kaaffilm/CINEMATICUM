"""Archive recovery and failed-install preservation, without a macOS compiler."""
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import install_macos as installer


class ArchiveInstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cinematicum-INSTALL-TEST-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, name, content=b"old executable", identifier=installer.BUNDLE_ID):
        app = self.root / name
        (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": identifier}))
        executable = app / "Contents/MacOS/CINEMATICUMStudio"
        executable.write_bytes(content)
        executable.chmod(0o755)
        return app

    def test_replacement_archive_recovers_exact_executable_and_mode(self):
        old = self.bundle(installer.APP_NAME)
        staged = self.bundle("staged.app", b"new executable")
        expected = installer.bundle_manifest(old)
        archive = installer.install_staged(staged, old, installer.existing_bundle_identity(old))
        self.assertEqual(b"new executable", (old / "Contents/MacOS/CINEMATICUMStudio").read_bytes())
        self.assertEqual([old], list(self.root.glob(installer.APP_NAME)))
        installer.verify_archive(archive, old.name, expected)
        with zipfile.ZipFile(archive) as saved:
            name = old.name + "/Contents/MacOS/CINEMATICUMStudio"
            self.assertEqual(b"old executable", saved.read(name))
            self.assertEqual(0o755, (saved.getinfo(name).external_attr >> 16) & 0o777)
        receipt = json.loads(archive.with_suffix(".json").read_text())
        self.assertEqual(expected, receipt["files"])

    def test_failed_destination_move_restores_old_bundle(self):
        old = self.bundle(installer.APP_NAME)
        staged = self.bundle("staged.app", b"new executable")
        original_rename = installer.os.rename
        def fail_staged(source, destination):
            if source == str(staged):
                raise OSError("Simulated destination failure")
            return original_rename(source, destination)
        with patch.object(installer.os, "rename", side_effect=fail_staged):
            with self.assertRaisesRegex(OSError, "Simulated"):
                installer.install_staged(staged, old, installer.existing_bundle_identity(old))
        self.assertEqual(b"old executable", (old / "Contents/MacOS/CINEMATICUMStudio").read_bytes())
        self.assertTrue(staged.is_dir())

    def test_corrupt_archive_cannot_retire_original(self):
        old = self.bundle(installer.APP_NAME)
        staged = self.bundle("staged.app", b"new executable")
        with patch.object(installer, "verify_archive", side_effect=ValueError("Bad CRC")):
            with self.assertRaisesRegex(ValueError, "Bad CRC"):
                installer.install_staged(staged, old, installer.existing_bundle_identity(old))
        self.assertEqual(b"old executable", (old / "Contents/MacOS/CINEMATICUMStudio").read_bytes())
        self.assertFalse(list(self.root.rglob("*.zip")))

    def test_changed_or_unrelated_targets_and_symlinks_are_preserved(self):
        old = self.bundle(installer.APP_NAME)
        staged = self.bundle("staged.app", b"new executable")
        identity = installer.existing_bundle_identity(old)
        (old / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": installer.BUNDLE_ID, "changed": True}))
        with self.assertRaisesRegex(RuntimeError, "changed"):
            installer.install_staged(staged, old, identity)
        other = self.bundle("CINEMATICUM Studio.backup-other.app", identifier="other.owner")
        link = self.root / "CINEMATICUM Studio.backup-link.app"
        link.symlink_to(other, target_is_directory=True)
        archives, warnings = installer.consolidate_legacy_bundles(old)
        self.assertFalse(archives)
        self.assertEqual(2, len(warnings))
        self.assertTrue(other.exists())
        self.assertTrue(link.is_symlink())

    def test_legacy_versions_leave_only_canonical_app_and_recoverable_zips(self):
        current = self.bundle(installer.APP_NAME)
        for name in ("CINEMATICUM Studio.backup-001.app", "CINEMATICUM Studio.rejected-002.app"):
            self.bundle(name)
        archives, warnings = installer.consolidate_legacy_bundles(current)
        self.assertFalse(warnings)
        self.assertEqual(2, len(archives))
        self.assertEqual([current], list(self.root.glob("*.app")))
        for archive in archives:
            with zipfile.ZipFile(archive) as saved:
                self.assertIsNone(saved.testzip())
                self.assertEqual(2, len([item for item in saved.infolist()
                                        if not item.is_dir() and not item.filename.startswith('__MACOSX/')]))


if __name__ == "__main__":
    unittest.main()

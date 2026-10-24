"""Archive recovery and failed-install preservation, without a macOS compiler."""
import json
from pathlib import Path
import plistlib
import subprocess
import sys
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

    def test_native_media_engine_uses_native_owner_home_not_inherited_job_home(self):
        launcher = (installer.STUDIO_SOURCE / "macos/StudioApp.swift").read_text(encoding="utf-8")
        startup = launcher.split("private func launchServer()", 1)
        self.assertEqual(2, len(startup))
        environment = startup[1].split("process.environment = environment", 1)
        self.assertEqual(2, len(environment))
        assignment = 'environment["HOME"] = FileManager.default.homeDirectoryForCurrentUser.path'
        self.assertIn(assignment, environment[0])
        self.assertLess(environment[0].index("var environment = ProcessInfo.processInfo.environment"),
                        environment[0].index(assignment))

    def test_packaged_runtime_imports_without_the_development_checkout(self):
        """A source-tree pass must not hide missing bundled transitive imports."""
        runtime = self.root / "runtime"
        installer.copy_runtime(runtime)
        program = (
            "import sys,json,pathlib;sys.path.insert(0,sys.argv[1]);"
            "import server,planar_tracking,projective_warp,install_tracking,install_imaging,managed_generation;"
            "import studio_tools,collaboration,collaboration_store,learned_tools,learned_tracking,install_learned_tracking;"
            "import runtime_management,install_physical_rendering,install_ray_optics,install_reconstruction;"
            "import scene_processing,scene_dispatch,scene_dispatch_store,reconstruction;"
            "import meshroom_reconstruction,camera_ctrl,diffusionlight;"
            "assert not meshroom_reconstruction.capabilities()['available'] or "
            "meshroom_reconstruction.capabilities()['operations'];"
            "assert pathlib.Path(server.__file__).parent==pathlib.Path(sys.argv[1]);"
            "assert install_tracking.LOCK.is_file();assert install_imaging.LOCK.is_file();"
            "managed_generation.load_lock();print('PACKAGED_RUNTIME_IMPORTS_PASS')"
        )
        result = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(runtime)],
                                cwd=self.root, capture_output=True, text=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PACKAGED_RUNTIME_IMPORTS_PASS", result.stdout)
        self.assertTrue(installer.runtime_manifest(runtime))

    def test_packaged_isolated_workers_do_not_write_into_the_bundle(self):
        """The launcher's -B/environment must survive actual isolated children."""
        runtime = self.root / "runtime"
        installer.copy_runtime(runtime)
        before = installer.runtime_manifest(runtime)
        program = r'''
import importlib.util, json, os, pathlib, sys
runtime = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(runtime))
import imaging, planar_tracking
assert pathlib.Path(imaging.__file__).parent == runtime
assert pathlib.Path(planar_tracking.__file__).parent == runtime
os.environ["CINEMATICUM_IMAGING_PYTHON"] = sys.executable
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
launched = []
def observe(event, args):
    if event == "subprocess.Popen":
        for name in ("image_worker.py", "planar_worker.py", "compositor.py", "roto.py"):
            if str(runtime / name) in args[1]:
                launched.append(name)
sys.addaudithook(observe)
# These real doctor/probe children import imaging/media_orientation and
# projective_warp even when the optional codec/OpenCV packages are absent.
image = imaging._short_request({"command": "doctor"}, python=sys.executable)
assert image["versions"]["python"] == sys.version.split()[0]
plane = planar_tracking.planar_capabilities(python=sys.executable)
assert isinstance(plane["available"], bool)
assert "image_worker.py" in launched and "planar_worker.py" in launched
from lens_assets import prepare_lens_maps
scratch = runtime.parent / "worker-output"
scratch.mkdir()
lens = prepare_lens_maps({}, 16, 16, scratch)
assert len(lens["paths"]) == 6 and "compositor.py" in launched
roto_executed = importlib.util.find_spec("numpy") is not None
if roto_executed:
    from roto_assets import prepare_roto_mask
    mask = prepare_roto_mask({"type": "mask", "params": {"shape": "bezier"}}, 16, 16, scratch)
    assert mask["static"] and mask["path"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "roto.py" in launched
print(json.dumps({"launched": launched, "imaging_available": image["available"],
                  "planar_available": plane["available"], "roto_executed": roto_executed}))
'''
        result = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(runtime)],
                                cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        observed = json.loads(result.stdout)
        self.assertIn("image_worker.py", observed["launched"])
        self.assertIn("planar_worker.py", observed["launched"])
        self.assertIn("compositor.py", observed["launched"])
        if observed["roto_executed"]:
            self.assertIn("roto.py", observed["launched"])
        self.assertEqual([], list(runtime.rglob("__pycache__")),
                         "Actual isolated capability probes mutated the installed source tree")
        self.assertEqual(before, installer.runtime_manifest(runtime))

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

"""Meaningful trust-boundary checks for native runtime acquisition and control."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent / "full_runtime"


def module(name):
    spec = importlib.util.spec_from_file_location("cinematicum_full_" + name, ROOT / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prepare = module("prepare")
control = module("control")


class NativeBundleTrustTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def artifact(self):
        data = bytearray(120000)
        data[:4] = b"\x7fELF"
        data[18:20] = b"\x3e\x00"
        path = self.root / "friction--test.AppImage"
        path.write_bytes(data)
        return path, data

    def locked(self, path):
        item = {"id": "friction", "url": "https://example.invalid/test.AppImage",
                "kind": "appimage", "archive": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size, "verification": "https-acquisition-sha256"}
        (self.root / "engines.lock.json").write_text(json.dumps({
            "schema": 1, "platform": "linux/amd64", "engines": [item]}))
        return item

    def test_cached_bundle_tampering_cannot_be_resealed_by_resume(self):
        path, data = self.artifact()
        old = self.locked(path)
        data[-1] = 1
        path.write_bytes(data)
        catalog = {"engines": [{"id": "friction", "url": old["url"], "kind": "appimage"}]}
        source = self.root / "source"
        source.mkdir()
        (source / "engines.json").write_text(json.dumps(catalog))
        with patch.object(prepare, "HERE", source), patch.object(sys, "argv", [
            "prepare.py", "--output", str(self.root), "--only", "friction"]):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                prepare.main()
        self.assertEqual(json.loads((self.root / "engines.lock.json").read_text())["engines"][0]["sha256"], old["sha256"])

    def test_symlink_bundle_is_rejected_even_if_hash_matches(self):
        path, _ = self.artifact()
        self.locked(path)
        other = self.root / "outside"
        path.rename(other)
        path.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "regular file"):
            prepare.verify(self.root)

    def test_full_build_requires_all_seven_editors(self):
        path, _ = self.artifact()
        self.locked(path)
        with self.assertRaisesRegex(ValueError, "Incomplete locked editor set"):
            prepare.verify(self.root, prepare.IDS)

    def test_https_redirect_downgrade_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            prepare.check_url("http://download.example/app.AppImage")
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            prepare.check_url("https://user:secret@download.example/app.AppImage")

    def test_html_download_cannot_become_verified_appimage(self):
        path = self.root / "friction--test.AppImage"
        path.write_bytes(b"<html>" + b"x" * 120000)
        with self.assertRaisesRegex(ValueError, "amd64 ELF"):
            prepare.acquire({"id": "friction", "kind": "appimage", "url": "https://example.invalid/test.AppImage"}, self.root, time.monotonic() + 1)


class NativeControlBoundaryTests(unittest.TestCase):
    def test_project_symlink_cannot_escape_mount(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            projects, other = root / "projects", root / "other"
            projects.mkdir()
            other.mkdir()
            (projects / "escape").symlink_to(other, target_is_directory=True)
            with patch.object(control, "PROJECTS", projects):
                with self.assertRaises(ValueError):
                    control.project_path("escape")
                with self.assertRaises(ValueError):
                    control.project_path("../other")
                self.assertEqual(control.project_path("."), projects)

    def test_keys_are_not_sent_to_unknown_window(self):
        calls = []
        def run(argv, timeout=3):
            calls.append(argv)
            return {"exit_code": 0, "stdout": "123\n", "stderr": ""}
        with patch.object(control, "run", run), patch.object(control, "registry", return_value=({}, {})), patch.object(control, "processes", return_value=[]), patch.object(control, "windows", return_value=[]):
            with self.assertRaisesRegex(ValueError, "does not belong"):
                control.key_command("save")
        self.assertFalse(any("key" in command for command in calls))

    def test_command_allowlist_rejects_injected_keys(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            control.key_command("ctrl+s;sh")


if __name__ == "__main__":
    unittest.main()

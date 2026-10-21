"""Integrity gates against changed bytes, missing source and undeclared code."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import source_integrity as integrity


class SourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cinematicum-integrity-TEST-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q")
        self.sources = {
            "README.md": "Test checkout\n",
            ".github/workflows/studio-verification.yml": "name: TEST\n",
            "scripts/studio/server.py": 'VERSION = "0.9.1"\n',
            "scripts/studio/test_example.py": "# source fixture\n",
            "scripts/studio/macos/App.swift": "// source fixture\n",
            "scripts/studio/web/app.js": "// source fixture\n",
            "scripts/studio/research/topic.md": "Test documentation\n",
        }
        for name, data in self.sources.items():
            self.write(name, data)
        self.git("add", "--", *self.sources)
        integrity.write_manifest(self.root)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, timeout=10)

    def write(self, name, data):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")
        return target

    def test_reproduction_excludes_manifest_media_binaries_and_generated_fixtures(self):
        original = (self.root / integrity.MANIFEST).read_bytes()
        for name in ("scripts/studio/source.mkv", "scripts/studio/macos/SmokeTest",
                     "scripts/studio/cinematicum-test-fixture/recipe.json", "scripts/studio/evidence/report.json"):
            self.write(name, "GENERATED TEST INPUT; never source")
        integrity.write_manifest(self.root)
        self.assertEqual((self.root / integrity.MANIFEST).read_bytes(), original)
        self.assertEqual([r["path"] for r in json.loads(original)["files"]], sorted(self.sources))
        self.assertTrue(integrity.verify_manifest(self.root)["passed"])

    def test_same_size_tamper_and_missing_tracked_source_both_fail(self):
        self.write("scripts/studio/web/app.js", "// source fixturE\n")
        (self.root / "scripts/studio/macos/App.swift").unlink()
        result = integrity.verify_manifest(self.root)
        self.assertFalse(result["passed"])
        self.assertEqual(result["changed"], ["scripts/studio/web/app.js"])
        self.assertEqual(result["missing"], ["scripts/studio/macos/App.swift"])

    def test_new_tracked_untracked_and_ignored_source_cannot_escape_inventory(self):
        for name, staged in (("scripts/studio/new_package/worker.py", False),
                             ("scripts/studio/web/new.js", True),
                             ("scripts/studio/web/ignored.js", False),
                             ("scripts/studio/cinematicum-adapter.py", False)):
            self.write(name, "# NEW TEST SOURCE\n")
            if staged:
                self.git("add", "--", name)
        self.write(".gitignore", "scripts/studio/web/ignored.js\n")
        result = integrity.verify_manifest(self.root)
        self.assertFalse(result["passed"])
        self.assertEqual(result["unexpected"], ["scripts/studio/cinematicum-adapter.py", "scripts/studio/new_package/worker.py",
                                                 "scripts/studio/web/ignored.js", "scripts/studio/web/new.js"])
        with self.assertRaisesRegex(ValueError, "Stage intended new source"):
            integrity.write_manifest(self.root)
        self.git("add", "-f", "--", *result["untracked"])
        integrity.write_manifest(self.root)
        self.assertTrue(integrity.verify_manifest(self.root)["passed"])

    def test_source_symlink_and_manifest_scope_tamper_are_rejected(self):
        original = integrity.read_manifest(self.root)
        target = self.root / "scripts/studio/web/app.js"
        target.unlink()
        target.symlink_to(self.root / "README.md")
        result = integrity.verify_manifest(self.root)
        self.assertFalse(result["passed"])
        self.assertEqual([r["path"] for r in result["invalid"]], ["scripts/studio/web/app.js"])
        altered = copy.deepcopy(original)
        altered["scope"]["source_suffixes"].remove(".js")
        self.write(integrity.MANIFEST, json.dumps(altered))
        with self.assertRaisesRegex(ValueError, "source scope"):
            integrity.verify_manifest(self.root)


if __name__ == "__main__":
    unittest.main()

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class TestObjectRegistryFreshness(unittest.TestCase):
    def test_regenerator_check_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/regenerate-object-registry.py", "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("object_registry_fresh=true", result.stdout)

    def test_guard_law_is_registered(self):
        registry = json.loads((ROOT / "CINEMATICUM_OBJECT_REGISTRY.json").read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in registry["entries"]}
        self.assertIn("OBJECT_REGISTRY_REGENERATION_GUARD_LAW.json", paths)

    def test_guard_law_does_not_claim_issuance(self):
        law = json.loads((ROOT / "OBJECT_REGISTRY_REGENERATION_GUARD_LAW.json").read_text(encoding="utf-8"))
        self.assertFalse(law["currently_false_claims"]["release_candidate_ready"])
        self.assertFalse(law["currently_false_claims"]["issued"])
        self.assertFalse(law["currently_false_claims"]["media_present"])
        self.assertFalse(law["currently_false_claims"]["outsider_replay_passed"])

if __name__ == "__main__":
    unittest.main()

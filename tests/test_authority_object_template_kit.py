import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

class TestAuthorityObjectTemplateKit(unittest.TestCase):
    def test_template_kit_contract(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertEqual(data["required_authority_object_template_count"], 8)
        self.assertTrue(data["template_only"])
        self.assertTrue(data["templates_do_not_satisfy_authority_objects"])
        self.assertEqual(len(data["template_paths"]), 8)
        for path in data["template_paths"]:
            self.assertTrue(Path(path).exists(), path)

    def test_non_issuance_flags_remain_false(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json").read_text())
        for key in [
            "release_candidate_ready",
            "release_candidate_artifacts_bound",
            "issued",
            "media_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
            "may_advance_now",
            "issuance_unblocked",
        ]:
            self.assertFalse(data[key], key)
        self.assertEqual(data["next_required_object"], NEXT_OBJECT)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-template-kit.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT TEMPLATE KIT: PASS", out)
        self.assertIn("TEMPLATE_ONLY=true", out)
        self.assertIn("TEMPLATES_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true", out)

if __name__ == "__main__":
    unittest.main()

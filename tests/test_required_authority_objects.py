import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

class TestRequiredAuthorityObjects(unittest.TestCase):
    def test_stack_complete_but_release_candidate_not_ready(self):
        data = json.loads(Path("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertTrue(data["authority_object_stack_complete"])
        self.assertFalse(data["required_authority_objects_missing"])
        self.assertEqual(data["accepted_authority_object_count"], 8)
        self.assertEqual(data["instantiated_authority_object_count"], 8)
        self.assertEqual(data["unfilled_authority_object_slot_count"], 0)
        self.assertFalse(data["release_candidate_ready"])
        self.assertFalse(data["release_candidate_artifacts_bound"])
        self.assertFalse(data["issued"])
        self.assertFalse(data["media_present"])
        self.assertFalse(data["outsider_replay_passed"])
        self.assertFalse(data["admissibility_verdict_present"])
        self.assertFalse(data["terminal_closure_present"])
        self.assertFalse(data["may_advance_now"])
        self.assertFalse(data["issuance_unblocked"])
        self.assertEqual(data["next_required_object"], NEXT_OBJECT)

    def test_transition_candidate_is_blocked(self):
        data = json.loads(Path("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json").read_text())
        candidate = data["transition_candidates"][0]
        self.assertEqual(candidate["from_state"], TARGET)
        self.assertEqual(candidate["required_object"], NEXT_OBJECT)
        self.assertFalse(candidate["may_advance_now"])
        self.assertTrue(candidate["blocked"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-required-authority-objects.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM REQUIRED AUTHORITY OBJECT CHECKLIST: PASS", out)
        self.assertIn("AUTHORITY_OBJECT_STACK_COMPLETE=true", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)

if __name__ == "__main__":
    unittest.main()

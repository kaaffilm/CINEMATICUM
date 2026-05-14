import json
import subprocess
import unittest
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_ARTIFACTS_DOCKET"

class TestReleaseCandidateGapLedger(unittest.TestCase):
    def test_record(self):
        data = json.loads(Path(
            "CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_GAP_LEDGER/RELEASE_CANDIDATE_GAP_LEDGER.json"
        ).read_text(encoding="utf-8"))

        self.assertEqual(data["case_id"], CASE_ID)
        self.assertEqual(data["current_state"], CURRENT_STATE)
        self.assertTrue(data["authority_object_stack_complete"])
        self.assertEqual(data["accepted_authority_object_count"], 8)
        self.assertEqual(data["instantiated_authority_object_count"], 8)
        self.assertEqual(data["unfilled_authority_object_slot_count"], 0)
        self.assertFalse(data["release_candidate_ready"])
        self.assertFalse(data["issued"])
        self.assertFalse(data["media_present"])
        self.assertFalse(data["outsider_replay_passed"])
        self.assertFalse(data["admissibility_verdict_present"])
        self.assertFalse(data["terminal_closure_present"])
        self.assertEqual(data["required_release_candidate_gap_count"], 6)
        self.assertEqual(data["next_required_object"], NEXT)

    def test_verifier(self):
        out = subprocess.run(
            ["bash", "scripts/verify-release-candidate-gap-ledger.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM RELEASE CANDIDATE GAP LEDGER: PASS", out)
        self.assertIn(f"NEXT_REQUIRED_OBJECT={NEXT}", out)

if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

class TestTransitionAttemptRejectionLedger(unittest.TestCase):
    def test_no_transition_attempt_is_present(self):
        data = json.loads(Path("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertEqual(data["transition_attempts_recorded"], 0)
        self.assertFalse(data["valid_transition_attempt_present"])
        self.assertFalse(data["may_advance_now"])
        self.assertFalse(data["issuance_unblocked"])
        self.assertEqual(data["next_required_object"], NEXT_OBJECT)

    def test_non_issuance_flags_remain_false(self):
        data = json.loads(Path("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json").read_text())
        for key in [
            "release_candidate_ready",
            "release_candidate_artifacts_bound",
            "issued",
            "media_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
        ]:
            self.assertFalse(data[key], key)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-transition-attempt-rejection-ledger.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM TRANSITION ATTEMPT REJECTION LEDGER: PASS", out)
        self.assertIn("TRANSITION_ATTEMPTS_RECORDED=0", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)

if __name__ == "__main__":
    unittest.main()

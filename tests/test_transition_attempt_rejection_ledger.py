import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "RELEASE_CANDIDATE_READY"
CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestTransitionAttemptRejectionLedger(unittest.TestCase):
    def test_ledger_matches_active_release_candidate_ready_state(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/TRANSITION_ATTEMPT_REJECTION_STATUS.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

        self.assertIn(index["active_case_states"][CASE_ID], {TARGET, "ISSUED_ADMISSIBLE_MOTION_PICTURE"})
        self.assertEqual(case["current_state"], index["active_case_states"][CASE_ID])

        for obj in (ledger, status):
            self.assertEqual(obj["current_state"], TARGET)
            self.assertEqual(obj["transition_attempts_recorded"], 0)
            self.assertFalse(obj["valid_transition_attempt_present"])
            self.assertTrue(obj["release_candidate_ready"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issuance_unblocked"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

    def test_no_transition_attempt_is_present(self):
        ledger = load("CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json")
        self.assertEqual(ledger["transition_attempts_recorded"], 0)
        self.assertFalse(ledger["valid_transition_attempt_present"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-transition-attempt-rejection-ledger.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM TRANSITION ATTEMPT REJECTION LEDGER: PASS", out)
        self.assertIn("CURRENT_STATE=RELEASE_CANDIDATE_READY", out)
        self.assertIn("RELEASE_CANDIDATE_READY=true", out)

if __name__ == "__main__":
    unittest.main()

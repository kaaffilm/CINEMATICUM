import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

class TestOutsiderCloneReplay(unittest.TestCase):
    def test_clone_replay_contract(self):
        data = json.loads(Path("OUTSIDER_CLONE_REPLAY.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertTrue(data["fresh_checkout_can_verify"])
        self.assertFalse(data["private_access_required"])
        self.assertFalse(data["network_required_after_clone"])
        self.assertFalse(data["media_or_model_payload_present"])

    def test_non_issuance_flags_remain_false(self):
        data = json.loads(Path("OUTSIDER_CLONE_REPLAY.json").read_text())
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
            ["bash", "scripts/verify-outsider-clone-replay.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM OUTSIDER CLONE REPLAY: PASS", out)
        self.assertIn("FRESH_CHECKOUT_CAN_VERIFY=true", out)
        self.assertIn("NETWORK_REQUIRED_AFTER_CLONE=false", out)

if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
NEXT_OBJECT = 'RELEASE_CANDIDATE_GAP_LEDGER'

class TestPublicPerimeterSentinel(unittest.TestCase):
    def test_public_perimeter_is_closed(self):
        data = json.loads(Path("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertFalse(data["private_access_required"])
        self.assertFalse(data["network_required_after_clone"])
        self.assertFalse(data["media_or_model_payload_present"])
        self.assertFalse(data["forbidden_private_file_present"])
        self.assertFalse(data["valid_transition_attempt_present"])

    def test_non_issuance_flags_remain_false(self):
        data = json.loads(Path("CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json").read_text())
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
            ["bash", "scripts/verify-public-perimeter-sentinel.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM PUBLIC PERIMETER SENTINEL: PASS", out)
        self.assertIn("PRIVATE_ACCESS_REQUIRED=false", out)
        self.assertIn("VALID_TRANSITION_ATTEMPT_PRESENT=false", out)

if __name__ == "__main__":
    unittest.main()

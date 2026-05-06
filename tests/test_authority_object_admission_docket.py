import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
FALSE_KEYS = ['release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

class TestAuthorityObjectAdmissionDocket(unittest.TestCase):
    def test_docket_contract(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertTrue(data["authority_object_admission_docket_passed"])
        self.assertTrue(data["authority_objects_admitted"])
        self.assertTrue(data["authority_object_stack_complete"])
        self.assertFalse(data["required_authority_objects_missing"])
        self.assertEqual(data["accepted_authority_object_count"], 8)
        self.assertEqual(data["instantiated_authority_object_count"], 8)
        self.assertEqual(data["unfilled_authority_object_slot_count"], 0)

    def test_docket_does_not_advance_to_release_or_issuance(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json").read_text())
        for key in FALSE_KEYS:
            self.assertFalse(data[key], key)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-docket.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION DOCKET: PASS", out)
        self.assertIn("AUTHORITY_OBJECTS_ADMITTED=true", out)
        self.assertIn("INSTANTIATED_AUTHORITY_OBJECT_COUNT=8", out)

if __name__ == "__main__":
    unittest.main()

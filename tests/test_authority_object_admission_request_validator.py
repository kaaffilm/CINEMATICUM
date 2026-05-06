import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
FALSE_KEYS = ['admission_requests_present', 'valid_admission_request_present', 'invalid_admission_requests_present', 'release_candidate_ready', 'release_candidate_artifacts_bound', 'issued', 'media_present', 'outsider_replay_passed', 'admissibility_verdict_present', 'terminal_closure_present', 'may_advance_now', 'issuance_unblocked']

class TestAuthorityObjectAdmissionRequestValidator(unittest.TestCase):
    def test_contract(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json").read_text())
        self.assertEqual(data["current_state"], TARGET)
        self.assertTrue(data['admission_request_validation_passed'])
        self.assertFalse(data["admission_requests_present"])
        self.assertFalse(data["valid_admission_request_present"])
        self.assertTrue(data["schema_non_authoritative"])
        self.assertTrue(data["validator_non_authoritative"])
        self.assertTrue(data["authority_object_stack_complete"])

    def test_non_advancing_surface(self):
        data = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json").read_text())
        for key in FALSE_KEYS:
            self.assertFalse(data[key], key)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-request-validator.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION REQUEST VALIDATOR: PASS", out)
        self.assertIn("ADMISSION_REQUESTS_PRESENT=false", out)
        self.assertIn("SCHEMAS_DO_NOT_SATISFY_AUTHORITY_OBJECTS=true", out)

if __name__ == "__main__":
    unittest.main()

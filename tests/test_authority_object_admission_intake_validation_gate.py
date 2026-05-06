import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'

class TestAuthorityObjectAdmissionIntakeValidationGate(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["authority_object_admission_intake_validation_gate_passed"])
        self.assertTrue(status["intake_validation_gate_passed"])
        self.assertFalse(status["admission_requests_present"])
        self.assertFalse(status["valid_admission_request_present"])
        self.assertFalse(status["invalid_admission_request_present"])
        self.assertTrue(status["schema_non_authoritative"])
        self.assertTrue(status["validator_non_authoritative"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["issuance_unblocked"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_counts(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_STATUS.json").read_text())
        self.assertEqual(status["accepted_authority_object_count"], 8)
        self.assertEqual(status["instantiated_authority_object_count"], 8)
        self.assertEqual(status["unfilled_authority_object_slot_count"], 0)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-validation-gate.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE VALIDATION GATE: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)

if __name__ == "__main__":
    unittest.main()

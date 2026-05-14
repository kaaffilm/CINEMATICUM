import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'

class TestAuthorityObjectAdmissionIntakeOrder(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["authority_object_admission_intake_order_passed"])
        self.assertTrue(status["intake_order_closed"])
        self.assertFalse(status["intake_accepts_new_requests"])
        self.assertFalse(status["admission_requests_present"])
        self.assertFalse(status["valid_admission_request_present"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["issuance_unblocked"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_counts(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_STATUS.json").read_text())
        self.assertEqual(status["accepted_authority_object_count"], 8)
        self.assertEqual(status["instantiated_authority_object_count"], 8)
        self.assertEqual(status["unfilled_authority_object_slot_count"], 0)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-order.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE ORDER: PASS", out)
        self.assertIn(f"CURRENT_STATE={TARGET}", out)

if __name__ == "__main__":
    unittest.main()

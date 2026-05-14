import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'

class TestAuthorityObjectAdmissionIntakeReopeningRequestSchema(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["reopening_request_schema_present"])
        self.assertTrue(status["reopening_request_schema_only"])
        self.assertTrue(status["schema_non_authoritative"])
        self.assertFalse(status["reopening_request_present"])
        self.assertFalse(status["valid_reopening_request_present"])
        self.assertFalse(status["intake_reopening_allowed"])
        self.assertFalse(status["current_snapshot_reopened"])
        self.assertFalse(status["new_snapshot_created"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["issuance_unblocked"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_counts(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_STATUS.json").read_text())
        self.assertEqual(status["accepted_authority_object_count"], 8)
        self.assertEqual(status["instantiated_authority_object_count"], 8)
        self.assertEqual(status["unfilled_authority_object_slot_count"], 0)
        self.assertEqual(status["live_reopening_request_count"], 0)
        self.assertEqual(status["accepted_reopening_request_count"], 0)
        self.assertEqual(status["rejected_reopening_request_count"], 0)

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-schema.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST SCHEMA: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)

if __name__ == "__main__":
    unittest.main()

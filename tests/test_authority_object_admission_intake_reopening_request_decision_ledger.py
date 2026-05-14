import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'

class TestAuthorityObjectAdmissionIntakeReopeningRequestDecisionLedger(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["reopening_request_decision_ledger_present"])
        self.assertTrue(status["reopening_request_decision_ledger_sealed"])
        self.assertTrue(status["ledger_non_authoritative"])
        self.assertFalse(status["reopening_request_present"])
        self.assertFalse(status["valid_reopening_request_present"])
        self.assertEqual(status["decision_record_count"], 0)
        self.assertEqual(status["accepted_decision_count"], 0)
        self.assertEqual(status["rejected_decision_count"], 0)
        self.assertTrue(status["all_live_reopening_requests_have_decisions"])
        self.assertFalse(status["intake_reopening_allowed"])
        self.assertFalse(status["current_snapshot_reopened"])
        self.assertFalse(status["new_snapshot_created"])

    def test_ledger_contract(self):
        ledger = json.loads(Path("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_DECISION_LEDGER.json").read_text())
        self.assertEqual(ledger["current_state"], TARGET)
        self.assertTrue(ledger["decision_ledger_non_authoritative"])
        self.assertTrue(ledger["ledger_does_not_satisfy_authority_objects"])
        self.assertFalse(ledger["release_candidate_ready"])
        self.assertFalse(ledger["may_advance_now"])
        self.assertFalse(ledger["issued"])
        self.assertFalse(ledger["media_present"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-decision-ledger.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST DECISION LEDGER: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)
        self.assertIn("DECISION_RECORD_COUNT=0", out)

if __name__ == "__main__":
    unittest.main()

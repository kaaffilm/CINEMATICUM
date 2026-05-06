import json
import subprocess
import unittest
from pathlib import Path

TARGET = 'REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS'
PREFIX = 'AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_FUTURE_SNAPSHOT_FORK_LEDGER_NON_ISSUANCE_SEAL'

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonIssuanceSeal(unittest.TestCase):
    def test_status_contract(self):
        status = json.loads(Path(f"CASES/CASE_001_THE_LAST_RENDER/{PREFIX}_STATUS.json").read_text())
        self.assertEqual(status["current_state"], TARGET)
        self.assertTrue(status["future_snapshot_fork_ledger_non_issuance_sealed"])
        self.assertTrue(status["non_issuance_seal_passed_for_current_zero_ledger"])
        self.assertFalse(status["non_issuance_seal_passed_for_future_fork"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-issuance-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("NON-ISSUANCE SEAL: PASS", out)
        self.assertIn("CURRENT_STATE=" + TARGET, out)
        self.assertIn("ISSUED=false", out)

if __name__ == "__main__":
    unittest.main()

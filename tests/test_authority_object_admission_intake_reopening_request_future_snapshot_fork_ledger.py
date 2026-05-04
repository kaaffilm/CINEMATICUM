import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedger(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER: PASS",
            result.stdout,
        )
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_PRESENT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_FINAL=true", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_MUTABLE=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_FORKED_NOW=false", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_RECORD_COUNT=0", result.stdout)
        self.assertIn("NEW_SNAPSHOT_RECORD_COUNT=0", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_EMPTY=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_CLOSED_FOR_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_RECORDS_CREATE_NEW_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_RECORDS_DO_NOT_MUTATE_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_RECORDS_DO_NOT_REOPEN_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

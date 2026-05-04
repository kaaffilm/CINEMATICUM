import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerTerminalSeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-terminal-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER TERMINAL SEAL: PASS",
            result.stdout,
        )
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_PRESENT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_EMPTY=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_CLOSED_FOR_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_CLOSURE_SEAL_PRESENT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEAL_PRESENT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_FINALITY_SEALED=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_TERMINALLY_SEALED=true", result.stdout)
        self.assertIn("CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_FINAL=true", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_MUTABLE=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_FORKED_NOW=false", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_RECORD_COUNT=0", result.stdout)
        self.assertIn("NEW_SNAPSHOT_RECORD_COUNT=0", result.stdout)
        self.assertIn("NO_UNFINALIZED_FORK_RECORDS=true", result.stdout)
        self.assertIn("NO_UNADJUDICATED_FORK_RECORDS=true", result.stdout)
        self.assertIn("NO_UNTERMINALIZED_FORK_RECORDS=true", result.stdout)
        self.assertIn("TERMINAL_SEAL_DOES_NOT_REOPEN_INTAKE=true", result.stdout)
        self.assertIn("TERMINAL_SEAL_DOES_NOT_OPEN_FUTURE_FORK_GATE=true", result.stdout)
        self.assertIn("TERMINAL_SEAL_DOES_NOT_CREATE_NEW_SNAPSHOT=true", result.stdout)
        self.assertIn("TERMINAL_SEAL_DOES_NOT_MUTATE_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

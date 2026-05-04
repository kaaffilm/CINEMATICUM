import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerTerminalClosureSeal(unittest.TestCase):
    def test_future_snapshot_fork_ledger_terminal_closure_seal_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-terminal-closure-seal.sh"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER TERMINAL CLOSURE SEAL: PASS",
            result.stdout,
        )
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_TERMINAL_CLOSURE_SEALED=true", result.stdout)
        self.assertIn("TERMINAL_CLOSURE_DOES_NOT_CREATE_NEW_SNAPSHOT=true", result.stdout)
        self.assertIn("TERMINAL_CLOSURE_DOES_NOT_MUTATE_PERMANENT_LEDGER=true", result.stdout)


if __name__ == "__main__":
    unittest.main()

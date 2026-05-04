import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonAuthoritySatisfactionSeal(unittest.TestCase):
    def test_non_authority_satisfaction_seal_passes_and_preserves_non_advancement(self):
        result = subprocess.run(
            [
                "bash",
                "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-authority-satisfaction-seal.sh",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        out = result.stdout
        self.assertIn("NON-AUTHORITY-SATISFACTION SEAL: PASS", out)
        self.assertIn("CURRENT_ZERO_LEDGER_DOES_NOT_SATISFY_AUTHORITY=true", out)
        self.assertIn("CURRENT_ZERO_LEDGER_AUTHORITY_SATISFIED=false", out)
        self.assertIn("CURRENT_ZERO_LEDGER_MAY_ADVANCE_NOW=false", out)
        self.assertIn("NON_AUTHORITY_SATISFACTION_SEAL_DOES_NOT_SATISFY_AUTHORITY=true", out)
        self.assertIn("NON_AUTHORITY_SATISFACTION_SEAL_DOES_NOT_ADVANCE_STATE=true", out)
        self.assertIn("FUTURE_VALID_FORK_MUST_SATISFY_AUTHORITY_INDEPENDENTLY=true", out)


if __name__ == "__main__":
    unittest.main()

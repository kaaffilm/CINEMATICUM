import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonIssuanceSeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-issuance-seal.sh"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("NON-ISSUANCE SEAL: PASS", result.stdout)
        self.assertIn("ISSUED=false", result.stdout)
        self.assertIn("MEDIA_PRESENT=false", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)


if __name__ == "__main__":
    unittest.main()

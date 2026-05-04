import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonAdvancementSeal(unittest.TestCase):
    def test_verify_non_advancement_seal(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-advancement-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-ADVANCEMENT SEAL: PASS",
            result.stdout,
        )
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)
        self.assertIn("ISSUED=false", result.stdout)


if __name__ == "__main__":
    unittest.main()

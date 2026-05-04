import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonReleaseCandidateSeal(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            [
                "bash",
                "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-release-candidate-seal.sh",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

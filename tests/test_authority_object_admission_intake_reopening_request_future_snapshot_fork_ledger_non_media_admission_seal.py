import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonMediaAdmissionSeal(unittest.TestCase):
    def test_non_media_admission_seal_verifier_passes(self):
        subprocess.run(
            [
                "bash",
                "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-media-admission-seal.sh",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

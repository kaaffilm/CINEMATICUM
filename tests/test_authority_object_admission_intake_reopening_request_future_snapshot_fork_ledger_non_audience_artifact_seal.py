import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonAudienceArtifactSeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            [
                "bash",
                "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-audience-artifact-seal.sh",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-AUDIENCE-ARTIFACT SEAL: PASS",
            result.stdout,
        )
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_NON_MEDIA_ADMISSION_SEALED=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_NON_AUDIENCE_ARTIFACT_SEALED=true", result.stdout)
        self.assertIn("CURRENT_ZERO_LEDGER_AUDIENCE_ARTIFACT_PRESENT=false", result.stdout)
        self.assertIn("NON_AUDIENCE_ARTIFACT_SEAL_DOES_NOT_CREATE_AUDIENCE_ARTIFACT=true", result.stdout)
        self.assertIn("AUDIENCE_ARTIFACT_PRESENT=false", result.stdout)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest


SCRIPT = "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-proof-artifact-seal.sh"


class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerNonProofArtifactSeal(unittest.TestCase):
    def test_non_proof_artifact_seal(self):
        result = subprocess.run(["bash", SCRIPT], check=True, text=True, capture_output=True)
        out = result.stdout

        required = [
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER NON-PROOF-ARTIFACT SEAL: PASS",
            "CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED",
            "NON_PROOF_ARTIFACT_SCOPE=CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_AUDIENCE_ARTIFACT_SEALED=true",
            "FUTURE_SNAPSHOT_FORK_LEDGER_NON_PROOF_ARTIFACT_SEALED=true",
            "CURRENT_ZERO_LEDGER_PROOF_ARTIFACT_BLOCKED=true",
            "CURRENT_ZERO_LEDGER_PROOF_ARTIFACT_PRESENT=false",
            "NON_AUDIENCE_ARTIFACT_DOES_NOT_CREATE_PROOF_ARTIFACT=true",
            "NON_PROOF_ARTIFACT_SEAL_PASSED_FOR_CURRENT_ZERO_LEDGER=true",
            "NON_PROOF_ARTIFACT_SEAL_PASSED_FOR_FUTURE_FORK=false",
            "NON_PROOF_ARTIFACT_ARTIFACT_REQUIRED_FOR_FUTURE_FORK=true",
            "NON_PROOF_ARTIFACT_ARTIFACT_PRESENT_FOR_FUTURE_FORK=false",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_OPEN_FUTURE_FORK_GATE=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_CREATE_NEW_SNAPSHOT=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_MUTATE_CURRENT_SNAPSHOT=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_MUTATE_PERMANENT_LEDGER=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_SATISFY_AUTHORITY=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_ADVANCE_STATE=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_ISSUE_MOTION_PICTURE=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_CREATE_RELEASE_CANDIDATE=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_ADMIT_MEDIA=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_CREATE_AUDIENCE_ARTIFACT=true",
            "NON_PROOF_ARTIFACT_SEAL_DOES_NOT_CREATE_PROOF_ARTIFACT=true",
            "FUTURE_VALID_FORK_MUST_ESTABLISH_PROOF_ARTIFACT_INDEPENDENTLY=true",
            "FUTURE_VALID_FORK_PROOF_ARTIFACT_MUST_TARGET_NEW_SNAPSHOT=true",
            "PROOF_ARTIFACT_PRESENT=false",
            "AUTHORITY_SATISFIED=false",
            "MAY_ADVANCE_NOW=false",
            "RELEASE_CANDIDATE_READY=false",
            "ISSUED=false",
            "MEDIA_PRESENT=false",
        ]

        for item in required:
            self.assertIn(item, out)


if __name__ == "__main__":
    unittest.main()

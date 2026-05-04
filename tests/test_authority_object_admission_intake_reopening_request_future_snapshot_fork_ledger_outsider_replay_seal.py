import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkLedgerOutsiderReplaySeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-outsider-replay-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK LEDGER OUTSIDER REPLAY SEAL: PASS",
            result.stdout,
        )
        self.assertIn("REPLAY_SCOPE=CURRENT_ZERO_FUTURE_SNAPSHOT_FORK_LEDGER_ONLY", result.stdout)
        self.assertIn("CONTINUITY_SCOPE_PRESERVED=FUTURE_VALID_REOPENING_REQUEST_SNAPSHOT_FORKS_ONLY", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_PRESENT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_FUTURE_CONTINUITY_SEALED=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_LEDGER_OUTSIDER_REPLAY_SEALED=true", result.stdout)
        self.assertIn("CURRENT_ZERO_LEDGER_REPLAYABLE_WITHOUT_FUTURE_FORK_RECORDS=true", result.stdout)
        self.assertIn("CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_PRIVATE_ACCESS=false", result.stdout)
        self.assertIn("CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_NETWORK=false", result.stdout)
        self.assertIn("CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_MEDIA_PAYLOAD=false", result.stdout)
        self.assertIn("CURRENT_ZERO_LEDGER_REPLAY_REQUIRES_MODEL_WEIGHTS=false", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_PASSED_NOW=false", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_FINAL=true", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_MUTABLE=false", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_RECORD_COUNT=0", result.stdout)
        self.assertIn("NEW_SNAPSHOT_RECORD_COUNT=0", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_SEAL_PASSED_FOR_CURRENT_ZERO_LEDGER=true", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_SEAL_PASSED_FOR_FUTURE_FORK=false", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_ARTIFACT_REQUIRED_FOR_FUTURE_FORK=true", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_ARTIFACT_PRESENT_FOR_FUTURE_FORK=false", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_DOES_NOT_OPEN_FUTURE_FORK_GATE=true", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_DOES_NOT_CREATE_NEW_SNAPSHOT=true", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_DOES_NOT_MUTATE_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("OUTSIDER_REPLAY_DOES_NOT_MUTATE_PERMANENT_LEDGER=true", result.stdout)
        self.assertIn("FUTURE_VALID_FORK_OUTSIDER_REPLAY_MUST_TARGET_NEW_SNAPSHOT=true", result.stdout)
        self.assertIn("PRIVATE_ACCESS_REQUIRED=false", result.stdout)
        self.assertIn("NETWORK_REQUIRED_AFTER_CLONE=false", result.stdout)
        self.assertIn("MEDIA_OR_MODEL_PAYLOAD_PRESENT=false", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

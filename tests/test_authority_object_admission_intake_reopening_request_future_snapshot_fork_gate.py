import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureSnapshotForkGate(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-gate.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE SNAPSHOT FORK GATE: PASS",
            result.stdout,
        )
        self.assertIn("FUTURE_CONTINUITY_SEAL_PRESENT=true", result.stdout)
        self.assertIn("PERMANENCE_SEAL_PRESENT=true", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_MUTABLE=false", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST=false", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_CREATE_NEW_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_FORK_FROM_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_DO_NOT_MUTATE_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_DO_NOT_REOPEN_CURRENT_SNAPSHOT=true", result.stdout)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_PASSED=false", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

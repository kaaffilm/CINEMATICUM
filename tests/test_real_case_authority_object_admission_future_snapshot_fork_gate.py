import subprocess
import unittest

class TestRealCaseAuthorityObjectAdmissionFutureSnapshotForkGate(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-future-snapshot-fork-gate.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        out = result.stdout
        self.assertIn("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION FUTURE SNAPSHOT FORK GATE: PASS", out)
        self.assertIn("FUTURE_CONTINUITY_SEAL_PRESENT=true", out)
        self.assertIn("PERMANENCE_SEAL_PRESENT=true", out)
        self.assertIn("CURRENT_ZERO_ADMISSION_SNAPSHOT_MUTABLE=false", out)
        self.assertIn("CURRENT_ZERO_ADMISSION_SNAPSHOT_REOPENABLE_BY_FUTURE_REQUEST=false", out)
        self.assertIn("FUTURE_VALID_ADMISSION_REQUESTS_CREATE_NEW_SNAPSHOT=true", out)
        self.assertIn("FUTURE_VALID_ADMISSION_REQUESTS_FORK_FROM_CURRENT_ZERO_SNAPSHOT=true", out)
        self.assertIn("FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_CURRENT_ZERO_SNAPSHOT=true", out)
        self.assertIn("FUTURE_VALID_ADMISSION_REQUESTS_DO_NOT_MUTATE_TERMINAL_SNAPSHOT=true", out)
        self.assertIn("CANONICAL_FIRST_FUTURE_AUTHORITY_SLOT_ID=director_final_cut_authority", out)
        self.assertIn("CANONICAL_FIRST_FUTURE_AUTHORITY_OBJECT=DIRECTOR_FINAL_CUT_AUTHORITY_OBJECT", out)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_PASSED=false", out)
        self.assertIn("FUTURE_SNAPSHOT_FORK_GATE_OPEN_NOW=false", out)
        self.assertIn("AUTHORITY_SATISFIED=false", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)

if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestFutureContinuitySeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-future-continuity-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FUTURE CONTINUITY SEAL: PASS",
            result.stdout,
        )
        self.assertIn("PERMANENCE_SEAL_PRESENT=true", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_MUTABLE=false", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_REQUIRE_EXPLICIT_REQUEST=true", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_REQUIRE_VALIDATION=true", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_REQUIRE_DECISION=true", result.stdout)
        self.assertIn("FUTURE_VALID_REOPENING_REQUESTS_REQUIRE_ENFORCEMENT_GATE=true", result.stdout)
        self.assertIn("FUTURE_CONTINUITY_SEAL_DOES_NOT_REOPEN_INTAKE=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

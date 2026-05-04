import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestFinalitySeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-finality-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST FINALITY SEAL: PASS",
            result.stdout,
        )
        self.assertIn("REOPENING_REQUEST_FINALITY_SEALED=true", result.stdout)
        self.assertIn("FINALITY_SEAL_DOES_NOT_REOPEN_INTAKE=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestTerminalSeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-terminal-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST TERMINAL SEAL: PASS",
            result.stdout,
        )
        self.assertIn("REOPENING_REQUEST_TERMINALLY_SEALED=true", result.stdout)
        self.assertIn("TERMINAL_SEAL_DOES_NOT_REOPEN_INTAKE=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

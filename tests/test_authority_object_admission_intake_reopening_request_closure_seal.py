import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestClosureSeal(unittest.TestCase):
    def test_verify_closure_seal_passes(self):
        completed = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-closure-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST CLOSURE SEAL: PASS",
            completed.stdout,
        )
        self.assertIn("REOPENING_REQUEST_STACK_CLOSED=true", completed.stdout)
        self.assertIn("CLOSURE_SEAL_DOES_NOT_REOPEN_INTAKE=true", completed.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", completed.stdout)
        self.assertIn("ISSUED=false", completed.stdout)
        self.assertIn("MEDIA_PRESENT=false", completed.stdout)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest

class TestAuthorityObjectAdmissionIntakeReopeningRequestPermanenceSeal(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-permanence-seal.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST PERMANENCE SEAL: PASS",
            result.stdout,
        )
        self.assertIn("REOPENING_REQUEST_PERMANENCE_SEALED=true", result.stdout)
        self.assertIn("CURRENT_SNAPSHOT_MUTABLE=false", result.stdout)
        self.assertIn("SILENT_SNAPSHOT_MUTATION_FORBIDDEN=true", result.stdout)
        self.assertIn("PERMANENCE_SEAL_DOES_NOT_REOPEN_INTAKE=true", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("MAY_ADVANCE_NOW=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

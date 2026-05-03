import subprocess
import unittest


class AuthorityObjectAdmissionIntakeReopeningRequestRejectionTaxonomyTest(unittest.TestCase):
    def test_verifier_script_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-rejection-taxonomy.sh"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION TAXONOMY: PASS",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()

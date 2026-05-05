import subprocess
import unittest


class TestFirstFutureDirectorFinalCutAuthorityObjectAdmissionRequestValidationRecord(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            [
                "bash",
                "scripts/verify-first-future-director-final-cut-authority-object-admission-request-validation-record.sh",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM FIRST FUTURE DIRECTOR FINAL CUT AUTHORITY OBJECT ADMISSION REQUEST VALIDATION RECORD: PASS",
            result.stdout,
        )
        self.assertIn("VALIDATION_RECORD_ACCEPTS_REQUEST=false", result.stdout)
        self.assertIn("AUTHORITY_SATISFIED=false", result.stdout)
        self.assertIn("ISSUED=false", result.stdout)
        self.assertIn("MEDIA_PRESENT=false", result.stdout)


if __name__ == "__main__":
    unittest.main()

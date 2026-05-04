import subprocess
import unittest


class TestRealCaseAuthorityObjectAdmissionRequestSchema(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-request-schema.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST SCHEMA: PASS",
            result.stdout,
        )
        self.assertIn("SCHEMA_ONLY=true", result.stdout)
        self.assertIn("LIVE_ADMISSION_REQUEST_COUNT=0", result.stdout)
        self.assertIn("SCHEMA_DOES_NOT_SATISFY_AUTHORITY=true", result.stdout)
        self.assertIn("SCHEMA_DOES_NOT_ADVANCE_STATE=true", result.stdout)
        self.assertIn("ISSUED=false", result.stdout)
        self.assertIn("MEDIA_PRESENT=false", result.stdout)

    def test_schema_is_not_authority_object(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-request-schema.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("SCHEMA_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true", result.stdout)
        self.assertIn("ACCEPTED_AUTHORITY_OBJECT_COUNT=0", result.stdout)


if __name__ == "__main__":
    unittest.main()

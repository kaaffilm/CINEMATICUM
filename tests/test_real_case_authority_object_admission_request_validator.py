import json
import subprocess
import unittest
from pathlib import Path


class RealCaseAuthorityObjectAdmissionRequestValidatorTest(unittest.TestCase):
    def test_validator_verifier_passes_and_seals_non_capability(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-request-validator.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        output = result.stdout

        self.assertIn(
            "CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST VALIDATOR: PASS",
            output,
        )
        self.assertIn("ZERO_REQUESTS_VALID=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_CREATE_LIVE_REQUESTS=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_ACCEPT_REQUESTS=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_REJECT_REQUESTS=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_INSTANTIATE_AUTHORITY_OBJECTS=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_SATISFY_AUTHORITY=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_ADVANCE_STATE=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_ISSUE_MOTION_PICTURE=true", output)
        self.assertIn("VALIDATOR_DOES_NOT_ADMIT_MEDIA=true", output)
        self.assertIn("AUTHORITY_SATISFIED=false", output)
        self.assertIn("MAY_ADVANCE_NOW=false", output)
        self.assertIn("ISSUED=false", output)
        self.assertIn("MEDIA_PRESENT=false", output)

    def test_validator_json_artifacts_parse(self):
        paths = [
            "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json",
            "CINEMATICUM_REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_LAW.json",
            "CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS.json",
        ]

        for path in paths:
            with self.subTest(path=path):
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main()

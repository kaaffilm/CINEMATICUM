import subprocess
import unittest


class TestRealCaseAuthorityIntakeDocket(unittest.TestCase):
    def test_verifier_contract_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-intake-docket.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        out = result.stdout
        self.assertIn("CINEMATICUM REAL CASE AUTHORITY INTAKE DOCKET: PASS", out)
        self.assertIn("REAL_CASE_AUTHORITY_INTAKE_DOCKET_PRESENT=true", out)
        self.assertIn("REAL_CASE_AUTHORITY_INTAKE_OPEN=true", out)
        self.assertIn("AUTHORITY_OBJECT_SLOT_COUNT=8", out)
        self.assertIn("AUTHORITY_SATISFIED=false", out)
        self.assertIn("MAY_ADVANCE_NOW=false", out)
        self.assertIn("ISSUED=false", out)
        self.assertIn("MEDIA_PRESENT=false", out)

    def test_docket_is_non_advancing_intake_structure(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-intake-docket.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        out = result.stdout
        self.assertIn("DOCKET_DOES_NOT_SATISFY_AUTHORITY=true", out)
        self.assertIn("DOCKET_DOES_NOT_ADVANCE_STATE=true", out)
        self.assertIn("DOCKET_DOES_NOT_ISSUE_MOTION_PICTURE=true", out)
        self.assertIn("DOCKET_DOES_NOT_ADMIT_MEDIA=true", out)
        self.assertIn("DOCKET_DOES_NOT_CREATE_RELEASE_CANDIDATE=true", out)


if __name__ == "__main__":
    unittest.main()

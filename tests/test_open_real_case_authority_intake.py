import subprocess
import unittest


class TestOpenRealCaseAuthorityIntake(unittest.TestCase):
    def test_open_real_case_authority_intake_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-open-real-case-authority-intake.sh"],
            check=True,
        )

    def test_verify_all_includes_open_real_case_authority_intake(self):
        with open("scripts/verify-all.sh", "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("verify-open-real-case-authority-intake.sh", text)


if __name__ == "__main__":
    unittest.main()

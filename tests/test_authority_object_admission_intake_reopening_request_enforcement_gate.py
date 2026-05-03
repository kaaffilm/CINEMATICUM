import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestEnforcementGate(unittest.TestCase):
    def test_reopening_request_enforcement_gate(self):
        subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-enforcement-gate.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

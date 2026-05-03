import subprocess
import unittest


class TestAuthorityObjectAdmissionIntakeReopeningRequestDecisionLedger(unittest.TestCase):
    def test_reopening_request_decision_ledger_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-authority-object-admission-intake-reopening-request-decision-ledger.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn(
            "CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST DECISION LEDGER: PASS",
            result.stdout,
        )
        self.assertIn("ALL_LIVE_REOPENING_REQUESTS_HAVE_DECISIONS=true", result.stdout)
        self.assertIn("ACCEPTED_REOPENING_REQUEST_PRESENT=false", result.stdout)
        self.assertIn("DECISION_LEDGER_DOES_NOT_REOPEN_INTAKE=true", result.stdout)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest


class TestFirstFutureDirectorFinalCutAuthorityObjectAdmissionDecisionRecord(unittest.TestCase):
    def test_decision_record_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-first-future-director-final-cut-authority-object-admission-decision-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

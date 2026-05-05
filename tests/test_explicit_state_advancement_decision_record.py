import subprocess
import unittest


class ExplicitStateAdvancementDecisionRecordTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-explicit-state-advancement-decision-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest


class ReleaseCandidateReadyStateAdvancementRequestTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-release-candidate-ready-state-advancement-request.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

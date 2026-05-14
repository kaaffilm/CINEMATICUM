import subprocess
import unittest


class ExplicitStateAdvancementRequestTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-explicit-state-advancement-request.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

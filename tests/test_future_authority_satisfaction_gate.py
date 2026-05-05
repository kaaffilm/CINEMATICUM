import subprocess
import unittest


class FutureAuthoritySatisfactionGateTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-future-authority-satisfaction-gate.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

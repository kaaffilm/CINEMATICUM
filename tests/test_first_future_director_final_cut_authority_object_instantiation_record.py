import subprocess
import unittest


class TestFirstFutureDirectorFinalCutAuthorityObjectInstantiationRecord(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-first-future-director-final-cut-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

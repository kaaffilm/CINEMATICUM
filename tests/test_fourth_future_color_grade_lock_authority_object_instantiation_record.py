import subprocess
import unittest


class FourthFutureColorGradeLockAuthorityObjectInstantiationRecordTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-fourth-future-color-grade-lock-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

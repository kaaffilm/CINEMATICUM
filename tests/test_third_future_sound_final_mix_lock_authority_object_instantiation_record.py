import subprocess
import unittest


class ThirdFutureSoundFinalMixLockAuthorityObjectInstantiationRecordTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-third-future-sound-final-mix-lock-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

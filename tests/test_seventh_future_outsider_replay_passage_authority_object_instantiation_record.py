import subprocess
import unittest


class SeventhFutureOutsiderReplayPassageAuthorityObjectInstantiationRecordTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-seventh-future-outsider-replay-passage-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

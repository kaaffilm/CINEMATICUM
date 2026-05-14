import subprocess
import unittest


class TestSecondFutureEditorialTimelineAuthorityObjectInstantiationRecord(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-second-future-editorial-timeline-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

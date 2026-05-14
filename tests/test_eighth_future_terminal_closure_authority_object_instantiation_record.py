import subprocess
import unittest


class EighthFutureTerminalClosureAuthorityObjectInstantiationRecordTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-eighth-future-terminal-closure-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

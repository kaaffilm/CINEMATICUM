import subprocess
import unittest


class TestSixthFutureArchivistProofChainLockAuthorityObjectInstantiationRecord(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-sixth-future-archivist-proof-chain-lock-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest


class FifthFutureReleaseDeliveryArtifactsLockAuthorityObjectInstantiationRecordTest(unittest.TestCase):
    def test_verifier_passes(self):
        subprocess.run(
            ["bash", "scripts/verify-fifth-future-release-delivery-artifacts-lock-authority-object-instantiation-record.sh"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()

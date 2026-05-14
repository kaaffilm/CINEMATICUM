import subprocess
import unittest

class TestMediaSubstanceGate(unittest.TestCase):
    def test_current_admitted_payload_does_not_pass_substance_gate(self):
        result = subprocess.run(
            ["bash", "scripts/verify-media-substance.sh"],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MEDIA_SUBSTANCE_PASS=false", result.stdout)

if __name__ == "__main__":
    unittest.main()

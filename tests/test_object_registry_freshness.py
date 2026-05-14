import subprocess
import unittest

class TestObjectRegistryFreshness(unittest.TestCase):
    def test_regenerator_check_passes(self):
        result = subprocess.run(
            ["python3", "scripts/regenerate-object-registry.py", "--check"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()

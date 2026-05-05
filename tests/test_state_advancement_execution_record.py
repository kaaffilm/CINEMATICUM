import subprocess
import unittest

class TestStateAdvancementExecutionRecord(unittest.TestCase):
    def test_verifier_passes(self):
        result = subprocess.run(
            ["bash", "scripts/verify-state-advancement-execution-record.sh"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("CINEMATICUM STATE ADVANCEMENT EXECUTION RECORD: PASS", result.stdout)
        self.assertIn("NEXT_REQUIRED_OBJECT=CURRENT_STATE_INDEX_ADVANCEMENT_RECORD", result.stdout)

if __name__ == "__main__":
    unittest.main()

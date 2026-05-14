import subprocess
import unittest

class TestMissionDone(unittest.TestCase):
    def test_mission_done(self):
        out = subprocess.run(
            ["bash", "scripts/verify-mission-done.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("MISSION_DONE=true", out)
        self.assertIn("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE", out)
        self.assertIn("ISSUED=true", out)
        self.assertIn("MEDIA_PRESENT=true", out)
        self.assertIn("RAW_MEDIA_STORED_IN_GIT=false", out)

if __name__ == "__main__":
    unittest.main()

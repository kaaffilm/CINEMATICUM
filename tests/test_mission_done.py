import subprocess
import unittest


class TestMissionDone(unittest.TestCase):
    def test_mission_done_or_substance_blocked(self):
        result = subprocess.run(
            ["bash", "scripts/verify-mission-done.sh"],
            text=True,
            capture_output=True,
        )

        out = result.stdout + result.stderr

        if "MEDIA_SUBSTANCE_PASS=false" in out or "BLOCKED_BY=MEDIA_SUBSTANCE_GATE" in out:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSION_DONE=false", out)
            self.assertIn("BLOCKED_BY=MEDIA_SUBSTANCE_GATE", out)
            return

        self.assertEqual(result.returncode, 0, out)
        self.assertIn("MISSION_DONE=true", out)
        self.assertIn("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE", out)
        self.assertIn("ISSUED=true", out)
        self.assertIn("MEDIA_PRESENT=true", out)


if __name__ == "__main__":
    unittest.main()

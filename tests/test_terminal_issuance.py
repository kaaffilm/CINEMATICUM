import json
import subprocess
import unittest
from pathlib import Path

CASE = "CASE_001_THE_LAST_RENDER"
ISSUED = "ISSUED_ADMISSIBLE_MOTION_PICTURE"
OBJ = "ADMISSIBLE_MOTION_PICTURE"

def read(path):
    return json.loads(Path(path).read_text())

class TestTerminalIssuance(unittest.TestCase):
    def test_current_state_index_is_issued(self):
        index = read("CINEMATICUM_CURRENT_STATE_INDEX.json")
        self.assertEqual(index["active_current_state"], ISSUED)
        self.assertEqual(index["active_case_states"][CASE], ISSUED)
        self.assertTrue(index["issued"])
        self.assertEqual(index["issued_object"], OBJ)
        self.assertFalse(index["media_present"])
        self.assertFalse(index["raw_media_stored_in_git"])
        self.assertIsNone(index["blocked_by"])

    def test_repository_status_seal_is_issued(self):
        seal = read("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        self.assertEqual(seal["current_state"], ISSUED)
        self.assertTrue(seal["issued"])
        self.assertEqual(seal["issued_object"], OBJ)
        self.assertFalse(seal["media_present"])
        self.assertFalse(seal["raw_media_stored_in_git"])

    def test_mission_done_verifier(self):
        out = subprocess.run(
            ["bash", "scripts/verify-mission-done.sh"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("MISSION_DONE=true", out)
        self.assertIn(f"ACTIVE_CURRENT_STATE={ISSUED}", out)

    def test_core_verifiers(self):
        for script in [
            "scripts/verify-current-state-index.sh",
            "scripts/verify-repository-status-seal.sh",
            "scripts/verify-object-registry.sh",
        ]:
            subprocess.run(["bash", script], check=True)

    def test_public_status(self):
        text = Path("PUBLIC_STATUS.md").read_text()
        self.assertIn(ISSUED, text)
        self.assertIn("mission_done=true", text)
        self.assertIn("issued=true", text)
        self.assertIn("raw_media_stored_in_git=false", text)

if __name__ == "__main__":
    unittest.main()

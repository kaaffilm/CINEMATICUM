import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
RECORD_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_STATE = "ISSUED_ADMISSIBLE_MOTION_PICTURE"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestRequiredAuthorityObjects(unittest.TestCase):
    def test_record_authority_stack_is_complete(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/REQUIRED_AUTHORITY_OBJECTS_STATUS.json")
        self.assertEqual(status["current_state"], RECORD_STATE)
        self.assertFalse(status["required_authority_objects_missing"])
        self.assertTrue(status["authority_object_stack_complete"])
        self.assertEqual(status["accepted_authority_object_count"], 8)
        self.assertEqual(status["instantiated_authority_object_count"], 8)
        self.assertEqual(status["unfilled_authority_object_slot_count"], 0)
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_active_state_has_advanced(self):
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(index["active_case_states"][CASE_ID], ACTIVE_STATE)
        self.assertEqual(index["active_current_state"], ACTIVE_STATE)
        self.assertEqual(case["current_state"], ACTIVE_STATE)
        self.assertTrue(case["release_candidate_ready"])
        self.assertTrue(case["issued"])
        self.assertTrue(case["media_present"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-required-authority-objects.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM REQUIRED AUTHORITY OBJECT CHECKLIST: PASS", out)
        self.assertIn("RECORD_CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", out)
        self.assertIn("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE", out)
        self.assertIn("AUTHORITY_OBJECT_STACK_COMPLETE=true", out)
        self.assertIn("RELEASE_CANDIDATE_READY=true", out)

if __name__ == "__main__":
    unittest.main()

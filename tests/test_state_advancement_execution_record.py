import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
FROM_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
TO_STATE = "RELEASE_CANDIDATE_READY"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestStateAdvancementExecutionRecord(unittest.TestCase):
    def test_record_remains_historical_from_state(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/STATE_ADVANCEMENT_EXECUTION_RECORD_STATUS.json")
        self.assertEqual(status["current_state"], FROM_STATE)
        self.assertTrue(status["state_mutation_execution_authorized"])
        self.assertTrue(status["current_state_index_mutation_authorized"])
        self.assertTrue(status["current_state_index_change_deferred_to_next_object"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_active_state_has_advanced(self):
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(index["active_case_states"][CASE_ID], "RELEASE_CANDIDATE_READY")
        self.assertEqual(index["active_current_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(case["current_state"], "RELEASE_CANDIDATE_READY")
        self.assertTrue(case["release_candidate_ready"])
        self.assertFalse(case["issued"])
        self.assertFalse(case["media_present"])

    def test_verifier_passes(self):
        out = subprocess.run(
            ["bash", "scripts/verify-state-advancement-execution-record.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("CINEMATICUM STATE ADVANCEMENT EXECUTION RECORD: PASS", out)
        self.assertIn("RECORD_CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", out)
        self.assertIn("ACTIVE_CURRENT_STATE=RELEASE_CANDIDATE_READY", out)
        self.assertIn("CURRENT_STATE_INDEX_MUTATION_EXECUTED=true", out)

if __name__ == "__main__":
    unittest.main()

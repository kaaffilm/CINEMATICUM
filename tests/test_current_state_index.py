import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE = "CASE_001_THE_LAST_RENDER"
RELEASE = "RELEASE_CANDIDATE_READY"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestCurrentStateIndex(unittest.TestCase):
    def test_root_index_is_active_current_state_owner(self):
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        self.assertEqual(index["surface_type"], "ACTIVE_CURRENT_STATE")
        self.assertEqual(index["active_case_states"][CASE], RELEASE)
        self.assertEqual(index["issued_films"], [])
        self.assertEqual(index["release_candidate_ready_cases"], [CASE])
        self.assertEqual(index["media_admitted_cases"], [])
        self.assertFalse(index["issued"])
        self.assertFalse(index["media_present"])
        self.assertFalse(index["media_substance_passed"])
        self.assertEqual(index["blocked_by"], "MEDIA_SUBSTANCE_GATE")

    def test_case_current_state_is_release_candidate_blocked_by_substance(self):
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(case["surface_type"], "ACTIVE_CURRENT_STATE")
        self.assertEqual(case["current_state"], RELEASE)
        self.assertTrue(case["release_candidate_ready"])
        self.assertFalse(case["issued"])
        self.assertFalse(case["media_present"])
        self.assertFalse(case["media_substance_passed"])
        self.assertEqual(case["blocked_by"], "MEDIA_SUBSTANCE_GATE")

    def test_prior_status_files_are_layer_records(self):
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        for file in case.get("prior_layer_status_files", []):
            layer = load(file)
            self.assertEqual(layer["surface_type"], "LAYER_STATUS_RECORD")
            self.assertFalse(layer["current_truth_owner"])
            self.assertTrue(layer["does_not_outrank_current_state_index"])

    def test_single_active_case_state_file(self):
        active = []
        for path in (ROOT / "CASES").rglob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("case_id") == CASE and data.get("surface_type") == "ACTIVE_CURRENT_STATE":
                active.append(str(path.relative_to(ROOT)))
        self.assertEqual(active, ["CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"])

if __name__ == "__main__":
    unittest.main()

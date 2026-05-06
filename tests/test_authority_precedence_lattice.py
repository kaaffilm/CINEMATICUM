import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityPrecedenceLattice(unittest.TestCase):
    def test_current_state_owners_are_rank_one(self):
        lattice = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
        order = lattice["precedence_order"]
        self.assertEqual(order[0]["rank"], 1)
        self.assertEqual(order[0]["authority_class"], "ACTIVE_CURRENT_STATE")
        self.assertTrue(order[0]["may_override_current_state"])

    def test_lower_surfaces_cannot_override_current_state(self):
        lattice = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
        for entry in lattice["precedence_order"][1:]:
            self.assertFalse(entry["may_override_current_state"], entry["authority_class"])

    def test_lattice_matches_current_state_objects(self):
        lattice = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(lattice["current_state"], "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], lattice["current_state"])
        self.assertEqual(case["current_state"], lattice["current_state"])

    def test_status_blocks_all_override_paths(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_PRECEDENCE_STATUS.json")
        for key in [
            "readme_prose_may_override_current_state",
            "schema_may_override_current_state",
            "registry_may_override_current_state",
            "status_seal_may_override_current_state",
            "public_inspection_may_override_current_state",
            "negative_proof_may_override_current_state",
        ]:
            self.assertFalse(status[key], key)

    def test_false_claims_remain_false(self):
        lattice = load("CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json")
        for key in [
            "release_candidate_ready",
            "issued",
            "media_present",
            "generation_present",
            "engine_present",
            "model_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
        ]:
            self.assertFalse(lattice["current_false_values"][key], key)

    def test_authority_precedence_doc_is_bounded(self):
        text = (ROOT / "AUTHORITY_PRECEDENCE.md").read_text(encoding="utf-8")
        self.assertIn("The active current-state objects control", text)
        self.assertIn("README prose", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)

if __name__ == "__main__":
    unittest.main()

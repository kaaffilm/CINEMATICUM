import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestRequiredAuthorityObjects(unittest.TestCase):
    def test_checklist_matches_current_state(self):
        checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(checklist["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], checklist["current_state"])
        self.assertEqual(case["current_state"], checklist["current_state"])

    def test_all_required_objects_are_missing(self):
        checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
        all_items = checklist["required_for_release_candidate_ready"] + checklist["required_for_issued_admissible_motion_picture"]
        self.assertGreater(len(all_items), 0)
        for item in all_items:
            self.assertEqual(item["status"], "missing", item["required_object_type"])

    def test_checklist_blocks_advancement(self):
        checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
        self.assertFalse(checklist["may_advance_now"])
        self.assertFalse(checklist["release_candidate_ready_unblocked"])
        self.assertFalse(checklist["issuance_unblocked"])
        self.assertTrue(checklist["required_authority_objects_missing"])
        self.assertTrue(checklist["schemas_do_not_satisfy_authority_objects"])

    def test_required_sets_match_transition_gate(self):
        checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
        gate = load("CINEMATICUM_STATE_TRANSITION_GATE.json")
        release_set = {item["required_object_type"] for item in checklist["required_for_release_candidate_ready"]}
        issuance_set = {item["required_object_type"] for item in checklist["required_for_issued_admissible_motion_picture"]}

        gate_release = set()
        gate_issuance = set()
        for transition in gate["transition_candidates"]:
            if transition["to"] == "RELEASE_CANDIDATE_READY":
                gate_release.update(transition["missing_required_authority_objects"])
            if transition["to"] == "ISSUED_ADMISSIBLE_MOTION_PICTURE":
                gate_issuance.update(transition["missing_required_authority_objects"])

        self.assertEqual(release_set, gate_release)
        self.assertEqual(issuance_set, gate_issuance)

    def test_exact_required_authority_objects_do_not_exist(self):
        checklist = load("CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json")
        required = {
            item["required_object_type"]
            for item in checklist["required_for_release_candidate_ready"] + checklist["required_for_issued_admissible_motion_picture"]
        }

        present = set()
        for path in ROOT.rglob("*.json"):
            if ".git" in path.parts:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            object_type = data.get("object_type")
            if object_type:
                present.add(object_type)

        self.assertTrue(required.isdisjoint(present), required & present)

    def test_required_authority_doc_is_bounded(self):
        text = (ROOT / "REQUIRED_AUTHORITY_OBJECTS.md").read_text(encoding="utf-8")
        self.assertIn("A schema does not satisfy an authority object", text)
        self.assertIn("MOTION_PICTURE_ISSUANCE_ACT_OBJECT", text)
        self.assertIn("OUTSIDER_REPLAY_PASS_OBJECT", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)

if __name__ == "__main__":
    unittest.main()

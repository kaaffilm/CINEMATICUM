import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectTemplateKit(unittest.TestCase):
    def test_kit_is_template_only(self):
        kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
        self.assertTrue(kit["template_only"])
        self.assertFalse(kit["authority_satisfied"])
        self.assertTrue(kit["templates_do_not_satisfy_authority_objects"])
        self.assertFalse(kit["may_advance_now"])

    def test_templates_exist_and_are_inert(self):
        kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
        self.assertGreaterEqual(len(kit["templates"]), 8)
        for item in kit["templates"]:
            path = ROOT / item["path"]
            self.assertTrue(path.exists(), item["path"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["object_type"].endswith("_TEMPLATE"))
            self.assertTrue(payload["template_only"])
            self.assertFalse(payload["authority_satisfied"])
            self.assertFalse(payload["may_advance_state"])
            self.assertFalse(payload["issued"])
            self.assertFalse(payload["media_present"])

    def test_actual_authority_objects_absent(self):
        kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
        for item in kit["templates"]:
            self.assertFalse((ROOT / item["future_authority_object"]).exists(), item["future_authority_object"])

    def test_current_state_unchanged(self):
        kit = load("CINEMATICUM_AUTHORITY_OBJECT_TEMPLATE_KIT.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        current = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
        self.assertEqual(kit["current_state"], current)
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], current)
        self.assertEqual(case["current_state"], current)

    def test_markdown_boundary(self):
        text = (ROOT / "AUTHORITY_OBJECT_TEMPLATES.md").read_text(encoding="utf-8")
        self.assertIn("Templates are not authority objects", text)
        self.assertIn("may_advance_now=false", text)
        self.assertIn("issued=false", text)
        self.assertIn("media_present=false", text)

if __name__ == "__main__":
    unittest.main()

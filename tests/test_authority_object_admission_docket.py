import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectAdmissionDocket(unittest.TestCase):
    def test_docket_is_empty_and_non_authorizing(self):
        docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
        self.assertFalse(docket["admission_requests_present"])
        self.assertEqual(docket["admission_request_count"], 0)
        self.assertFalse(docket["accepted_admission_requests_present"])
        self.assertFalse(docket["rejected_admission_requests_present"])
        self.assertEqual(docket["rejected_admission_request_count"], 0)
        self.assertFalse(docket["instantiated_authority_objects_present"])
        self.assertFalse(docket["authority_satisfied"])
        self.assertFalse(docket["may_advance_now"])
        self.assertFalse(docket["issued"])
        self.assertFalse(docket["media_present"])

    def test_no_request_or_authority_json_exists(self):
        self.assertEqual(sorted((ROOT / "authority_object_admission_requests").glob("*.json")), [])
        self.assertEqual(sorted((ROOT / "authority_objects").glob("*.json")), [])

    def test_request_schema_minimum_fields(self):
        docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
        required = {
            "object_type",
            "schema_version",
            "case_id",
            "target_authority_object",
            "source_template",
            "requesting_actor",
            "request_timestamp_utc",
            "authority_basis",
            "evidence_references",
            "requested_state_effect",
            "requested_admission_status",
        }
        self.assertTrue(required.issubset(set(docket["request_schema_minimum_fields"])))

    def test_current_state_unchanged(self):
        docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        current = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED"
        self.assertEqual(docket["current_state"], current)
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], current)
        self.assertEqual(case["current_state"], current)

    def test_forbidden_silent_targets_absent(self):
        docket = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json")
        for future in docket["currently_forbidden_silent_targets"]:
            self.assertFalse((ROOT / future).exists(), future)
            self.assertFalse((ROOT / "authority_objects" / future).exists(), future)

    def test_markdown_boundary(self):
        text = (ROOT / "AUTHORITY_OBJECT_ADMISSION_DOCKET.md").read_text(encoding="utf-8")
        self.assertIn("The admission docket is not an authority object", text)
        self.assertIn("admission_requests_present=false", text)
        self.assertIn("admission_request_count=0", text)
        self.assertIn("may_advance_now=false", text)

if __name__ == "__main__":
    unittest.main()

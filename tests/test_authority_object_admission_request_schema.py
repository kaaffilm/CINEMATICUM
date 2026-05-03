import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectAdmissionRequestSchema(unittest.TestCase):
    def test_schema_declares_required_fields(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        required = set(schema["required_fields"])
        for key in [
            "object_type",
            "schema_version",
            "request_id",
            "case_id",
            "requested_authority_object_type",
            "requested_authority_template",
            "requester_assertion",
            "evidence_references",
            "media_payload_present",
            "model_weight_payload_present",
            "private_access_required",
            "requested_admission_status",
            "authority_satisfied_by_request",
            "may_advance_state_by_request",
        ]:
            self.assertIn(key, required)

    def test_fixed_values_do_not_advance_authority(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        fixed = schema["required_fixed_values"]
        self.assertEqual(fixed["object_type"], "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST")
        self.assertEqual(fixed["case_id"], "CASE_001_THE_LAST_RENDER")
        self.assertFalse(fixed["media_payload_present"])
        self.assertFalse(fixed["model_weight_payload_present"])
        self.assertFalse(fixed["private_access_required"])
        self.assertEqual(fixed["requested_admission_status"], "PENDING")
        self.assertFalse(fixed["authority_satisfied_by_request"])
        self.assertFalse(fixed["may_advance_state_by_request"])

    def test_zero_requests_remain_zero(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA_STATUS.json")
        for obj in [schema, status]:
            self.assertFalse(obj["admission_requests_present"])
            self.assertEqual(obj["admission_request_count"], 0)
            self.assertFalse(obj["accepted_admission_requests_present"])
            self.assertFalse(obj["rejected_admission_requests_present"])
            self.assertFalse(obj["pending_admission_requests_present"])
            self.assertFalse(obj["authority_satisfied"])
            self.assertFalse(obj["may_advance_now"])
            self.assertFalse(obj["issued"])
            self.assertFalse(obj["media_present"])

    def test_no_request_files_exist_yet(self):
        request_dir = ROOT / "authority_object_admission_requests"
        files = sorted(request_dir.glob("AUTHORITY_OBJECT_ADMISSION_REQUEST_*.json"))
        self.assertEqual(files, [])

    def test_schema_matches_current_state(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(schema["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], schema["current_state"])
        self.assertEqual(case["current_state"], schema["current_state"])

if __name__ == "__main__":
    unittest.main()

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectAdmissionRequestValidator(unittest.TestCase):
    def test_validator_matches_schema(self):
        validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        self.assertEqual(validator["schema_owner"], "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        self.assertEqual(validator["request_directory"], schema["request_directory"])
        self.assertEqual(validator["request_file_pattern"], schema["request_file_pattern"])

    def test_zero_requests_valid(self):
        validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR_STATUS.json")
        for obj in [validator, status]:
            self.assertTrue(obj["zero_requests_valid"])
            self.assertFalse(obj["admission_requests_present"])
            self.assertEqual(obj["admission_request_count"], 0)
            self.assertEqual(obj["valid_admission_request_count"], 0)
            self.assertEqual(obj["invalid_admission_request_count"], 0)

    def test_no_authority_effect(self):
        validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
        for key in [
            "accepted_admission_requests_present",
            "rejected_admission_requests_present",
            "pending_admission_requests_present",
            "instantiated_authority_objects_present",
            "authority_satisfied",
            "may_advance_now",
            "release_candidate_ready",
            "issued",
            "media_present",
        ]:
            self.assertFalse(validator[key], key)

    def test_request_directory_empty_for_now(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        request_dir = ROOT / schema["request_directory"]
        files = sorted(request_dir.glob(schema["request_file_pattern"]))
        self.assertEqual(files, [])

    def test_current_state_not_advanced(self):
        validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(validator["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], validator["current_state"])
        self.assertEqual(case["current_state"], validator["current_state"])

if __name__ == "__main__":
    unittest.main()

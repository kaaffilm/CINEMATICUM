import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectAdmissionRequestRejectionCorpus(unittest.TestCase):
    def test_corpus_is_not_live_directory(self):
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        self.assertEqual(corpus["live_request_directory"], schema["request_directory"])
        self.assertNotEqual(corpus["fixture_directory"], corpus["live_request_directory"])
        self.assertFalse(corpus["fixtures_are_live_requests"])

    def test_fixtures_all_rejected(self):
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
        fixture_dir = ROOT / corpus["fixture_directory"]
        files = sorted(fixture_dir.glob("*.json"))
        self.assertEqual(len(files), corpus["rejection_fixture_count"])
        reasons = sorted(json.loads(p.read_text(encoding="utf-8"))["expected_rejection_reason"] for p in files)
        self.assertEqual(reasons, sorted(corpus["expected_rejection_reasons"]))

    def test_live_request_directory_still_empty(self):
        schema = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json")
        live_dir = ROOT / schema["request_directory"]
        files = sorted(live_dir.glob(schema["request_file_pattern"]))
        self.assertEqual(files, [])

    def test_no_authority_effect(self):
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
        for key in [
            "admission_requests_present",
            "accepted_admission_requests_present",
            "rejected_fixtures_are_admission_requests",
            "instantiated_authority_objects_present",
            "authority_satisfied",
            "may_advance_now",
            "release_candidate_ready",
            "issued",
            "media_present",
        ]:
            self.assertFalse(corpus[key], key)

    def test_current_state_not_advanced(self):
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(corpus["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], corpus["current_state"])
        self.assertEqual(case["current_state"], corpus["current_state"])

if __name__ == "__main__":
    unittest.main()

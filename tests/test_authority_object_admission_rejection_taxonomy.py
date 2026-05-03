import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectAdmissionRejectionTaxonomy(unittest.TestCase):
    def test_canonical_reason_set(self):
        taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
        codes = [item["code"] for item in taxonomy["canonical_rejection_reasons"]]
        self.assertEqual(len(codes), 9)
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(codes), {
            "missing_case_id",
            "wrong_case_id",
            "wrong_current_state",
            "unknown_authority_object_type",
            "authority_satisfied_by_request_true",
            "may_advance_state_by_request_true",
            "media_payload_present_true",
            "model_weight_payload_present_true",
            "private_access_required_true",
        })

    def test_corpus_covers_required_reasons(self):
        taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
        corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json")
        self.assertEqual(set(corpus["expected_rejection_reasons"]), set(taxonomy["covered_rejection_reasons"]))
        self.assertEqual(corpus["rejection_fixture_count"], taxonomy["required_corpus_reason_count"])

    def test_taxonomy_has_no_authority_effect(self):
        taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
        for key in [
            "fixtures_are_live_requests",
            "admission_requests_present",
            "accepted_admission_requests_present",
            "instantiated_authority_objects_present",
            "authority_satisfied",
            "may_advance_now",
            "release_candidate_ready",
            "issued",
            "media_present",
        ]:
            self.assertFalse(taxonomy[key], key)
        self.assertEqual(taxonomy["admission_request_count"], 0)

    def test_current_state_not_advanced(self):
        taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(taxonomy["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], taxonomy["current_state"])
        self.assertEqual(case["current_state"], taxonomy["current_state"])

    def test_status_matches_taxonomy_counts(self):
        taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json")
        status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY_STATUS.json")
        self.assertEqual(status["canonical_rejection_reason_count"], taxonomy["canonical_rejection_reason_count"])
        self.assertEqual(status["covered_rejection_reason_count"], len(taxonomy["covered_rejection_reasons"]))
        self.assertEqual(status["uncovered_rejection_reason_count"], len(taxonomy["uncovered_rejection_reasons"]))
        self.assertTrue(status["taxonomy_complete_for_current_validator"])
        self.assertTrue(status["corpus_complete_for_required_reasons"])

if __name__ == "__main__":
    unittest.main()

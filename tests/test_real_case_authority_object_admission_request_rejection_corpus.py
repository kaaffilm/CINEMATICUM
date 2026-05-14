import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
RECORD_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
ACTIVE_STATE = "ISSUED_ADMISSIBLE_MOTION_PICTURE"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class RealCaseAuthorityObjectAdmissionRequestRejectionCorpusTest(unittest.TestCase):
    def test_record_is_closed_non_capability_surface(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/REAL_CASE_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS_STATUS.json")
        self.assertEqual(status["current_state"], RECORD_STATE)
        self.assertEqual(status["corpus_scope"], "REAL_CASE_AUTHORITY_OBJECTS_ONLY")
        self.assertFalse(status["fixtures_are_live_requests"])
        self.assertEqual(status["live_admission_request_count"], 0)
        self.assertEqual(status["valid_admission_request_count"], 0)
        self.assertEqual(status["accepted_admission_request_count"], 0)
        self.assertEqual(status["accepted_authority_object_count"], 0)
        self.assertEqual(status["instantiated_authority_object_count"], 0)
        self.assertTrue(status["all_fixtures_rejected"])
        self.assertTrue(status["corpus_does_not_satisfy_authority"])
        self.assertTrue(status["corpus_does_not_advance_state"])
        self.assertTrue(status["corpus_does_not_issue_motion_picture"])
        self.assertTrue(status["corpus_does_not_admit_media"])
        self.assertFalse(status["authority_satisfied"])
        self.assertFalse(status["may_advance_now"])
        self.assertFalse(status["release_candidate_ready"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])

    def test_active_state_has_advanced(self):
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(index["active_case_states"][CASE_ID], ACTIVE_STATE)
        self.assertEqual(index["active_current_state"], ACTIVE_STATE)
        self.assertEqual(case["current_state"], ACTIVE_STATE)
        self.assertTrue(case["release_candidate_ready"])
        self.assertTrue(case["issued"])
        self.assertTrue(case["media_present"])

    def test_verifier_passes_and_reports_closed_non_capability_surface(self):
        result = subprocess.run(
            ["bash", "scripts/verify-real-case-authority-object-admission-request-rejection-corpus.sh"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("CINEMATICUM REAL CASE AUTHORITY OBJECT ADMISSION REQUEST REJECTION CORPUS: PASS", result.stdout)
        self.assertIn("RECORD_CURRENT_STATE=REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", result.stdout)
        self.assertIn("ACTIVE_CURRENT_STATE=ISSUED_ADMISSIBLE_MOTION_PICTURE", result.stdout)
        self.assertIn("FIXTURES_ARE_LIVE_REQUESTS=false", result.stdout)
        self.assertIn("ALL_FIXTURES_REJECTED=true", result.stdout)
        self.assertIn("CORPUS_DOES_NOT_ADVANCE_STATE=true", result.stdout)
        self.assertIn("RELEASE_CANDIDATE_READY=true", result.stdout)

if __name__ == "__main__":
    unittest.main()

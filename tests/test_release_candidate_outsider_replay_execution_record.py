import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_OUTSIDER_REPLAY_PASSAGE_RECORD"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestReleaseCandidateOutsiderReplayExecutionRecord(unittest.TestCase):
    def test_execution_record_present_after_planning_perimeter(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD.json")
        self.assertEqual(obj["case_id"], CASE_ID)
        self.assertEqual(obj["current_state"], CURRENT_STATE)
        self.assertTrue(obj["release_candidate_gap_ledger_present"])
        self.assertTrue(obj["release_candidate_artifacts_docket_present"])
        self.assertTrue(obj["release_candidate_manifest_present"])
        self.assertTrue(obj["release_candidate_evidence_bundle_present"])
        self.assertTrue(obj["release_candidate_public_inspection_dossier_present"])
        self.assertTrue(obj["release_candidate_outsider_replay_plan_present"])
        self.assertTrue(obj["release_candidate_terminal_closure_plan_present"])
        self.assertTrue(obj["release_candidate_planning_perimeter_complete"])
        self.assertTrue(obj["all_required_release_candidate_gap_objects_present"])
        self.assertTrue(obj["release_candidate_outsider_replay_execution_record_present"])
        self.assertTrue(obj["release_candidate_outsider_replay_execution_record_sealed"])
        self.assertTrue(obj["outsider_replay_execution_record_present"])
        self.assertTrue(obj["outsider_replay_execution_record_sealed"])
        self.assertTrue(obj["outsider_replay_execution_declared"])
        self.assertTrue(obj["outsider_replay_execution_completed"])
        self.assertEqual(obj["outsider_replay_execution_command"], "bash scripts/verify-all.sh")
        self.assertEqual(obj["outsider_replay_execution_result"], "PASS")
        self.assertEqual(obj["next_required_object"], NEXT)

    def test_execution_record_does_not_pass_or_advance(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD.json")
        for key in [
            "outsider_replay_passage_record_present",
            "admissibility_verdict_record_present",
            "terminal_closure_record_present",
            "release_candidate_ready",
            "issued",
            "media_present",
            "outsider_replay_passed",
            "admissibility_verdict_present",
            "terminal_closure_present",
            "authority_satisfied",
            "may_advance_now",
        ]:
            self.assertFalse(obj[key], key)

        self.assertTrue(obj["execution_record_is_not_passage_record"])
        self.assertTrue(obj["execution_record_does_not_pass_outsider_replay"])
        self.assertTrue(obj["execution_record_does_not_create_admissibility_verdict"])
        self.assertTrue(obj["execution_record_does_not_create_terminal_closure"])
        self.assertTrue(obj["execution_record_does_not_create_release_candidate"])
        self.assertTrue(obj["execution_record_does_not_issue_motion_picture"])
        self.assertTrue(obj["execution_record_does_not_admit_media"])
        self.assertTrue(obj["execution_record_does_not_mutate_current_state"])

    def test_public_clone_replay_perimeter_preserved(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD.json")
        self.assertTrue(obj["fresh_checkout_can_verify"])
        self.assertFalse(obj["private_access_required"])
        self.assertFalse(obj["network_required_after_clone"])
        self.assertFalse(obj["media_or_model_payload_present"])
        self.assertFalse(obj["forbidden_private_file_present"])

    def test_case_record_identity(self):
        obj = load(f"CASES/{CASE_ID}/RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD/RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD.json")
        self.assertEqual(obj["record_id"], "OUTSIDER_REPLAY_EXECUTION_RECORD_001_RELEASE_CANDIDATE")
        self.assertEqual(obj["object_type"], "CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD")

if __name__ == "__main__":
    unittest.main()

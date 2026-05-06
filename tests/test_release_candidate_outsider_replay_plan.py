import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_TERMINAL_CLOSURE_PLAN"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestReleaseCandidateOutsiderReplayPlan(unittest.TestCase):
    def test_outsider_replay_plan_present_and_bounded(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_PLAN.json")
        self.assertEqual(obj["case_id"], CASE_ID)
        self.assertEqual(obj["current_state"], CURRENT_STATE)
        self.assertTrue(obj["release_candidate_gap_ledger_present"])
        self.assertTrue(obj["release_candidate_artifacts_docket_present"])
        self.assertTrue(obj["release_candidate_manifest_present"])
        self.assertTrue(obj["release_candidate_evidence_bundle_present"])
        self.assertTrue(obj["release_candidate_public_inspection_dossier_present"])
        self.assertTrue(obj["release_candidate_outsider_replay_plan_present"])
        self.assertTrue(obj["release_candidate_outsider_replay_plan_sealed"])
        self.assertTrue(obj["authority_object_stack_complete"])
        self.assertTrue(obj["future_authority_satisfaction_gate_passed"])
        self.assertEqual(obj["accepted_authority_object_count"], 8)
        self.assertEqual(obj["instantiated_authority_object_count"], 8)
        self.assertEqual(obj["unfilled_authority_object_slot_count"], 0)
        self.assertTrue(obj["outsider_replay_plan_declared"])
        self.assertFalse(obj["outsider_replay_plan_private_access_required"])
        self.assertFalse(obj["outsider_replay_plan_media_or_model_payload_required"])
        self.assertFalse(obj["outsider_replay_plan_network_required_after_clone"])
        self.assertFalse(obj["outsider_replay_execution_record_present"])
        self.assertFalse(obj["outsider_replay_passage_record_present"])
        self.assertEqual(obj["required_remaining_release_candidate_gap_count"], 1)
        self.assertEqual(obj["next_required_object"], NEXT)

    def test_outsider_replay_plan_does_not_pass_replay_or_advance(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_PLAN.json")
        for key in [
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

        self.assertTrue(obj["outsider_replay_plan_does_not_execute_replay"])
        self.assertTrue(obj["outsider_replay_plan_does_not_pass_outsider_replay"])
        self.assertTrue(obj["outsider_replay_plan_does_not_create_admissibility_verdict"])
        self.assertTrue(obj["outsider_replay_plan_does_not_create_terminal_closure"])
        self.assertTrue(obj["outsider_replay_plan_does_not_issue_motion_picture"])
        self.assertTrue(obj["outsider_replay_plan_does_not_admit_media"])
        self.assertTrue(obj["outsider_replay_plan_does_not_mutate_current_state"])

    def test_case_record_identity(self):
        obj = load(f"CASES/{CASE_ID}/RELEASE_CANDIDATE_OUTSIDER_REPLAY_PLAN/RELEASE_CANDIDATE_OUTSIDER_REPLAY_PLAN.json")
        self.assertEqual(obj["record_id"], "OUTSIDER_REPLAY_PLAN_001_RELEASE_CANDIDATE")
        self.assertEqual(obj["object_type"], "CINEMATICUM_RELEASE_CANDIDATE_OUTSIDER_REPLAY_PLAN")
        self.assertEqual(obj["required_remaining_release_candidate_objects"], [NEXT])

if __name__ == "__main__":
    unittest.main()

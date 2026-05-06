import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_OUTSIDER_REPLAY_EXECUTION_RECORD"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestReleaseCandidateTerminalClosurePlan(unittest.TestCase):
    def test_terminal_closure_plan_present_and_gap_ledger_exhausted(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_PLAN.json")
        self.assertEqual(obj["case_id"], CASE_ID)
        self.assertEqual(obj["current_state"], CURRENT_STATE)
        self.assertTrue(obj["release_candidate_gap_ledger_present"])
        self.assertTrue(obj["release_candidate_artifacts_docket_present"])
        self.assertTrue(obj["release_candidate_manifest_present"])
        self.assertTrue(obj["release_candidate_evidence_bundle_present"])
        self.assertTrue(obj["release_candidate_public_inspection_dossier_present"])
        self.assertTrue(obj["release_candidate_outsider_replay_plan_present"])
        self.assertTrue(obj["release_candidate_terminal_closure_plan_present"])
        self.assertTrue(obj["release_candidate_terminal_closure_plan_sealed"])
        self.assertTrue(obj["authority_object_stack_complete"])
        self.assertTrue(obj["future_authority_satisfaction_gate_passed"])
        self.assertEqual(obj["accepted_authority_object_count"], 8)
        self.assertEqual(obj["instantiated_authority_object_count"], 8)
        self.assertEqual(obj["unfilled_authority_object_slot_count"], 0)
        self.assertTrue(obj["terminal_closure_plan_declared"])
        self.assertEqual(obj["required_remaining_release_candidate_gap_count"], 0)
        self.assertEqual(obj["required_remaining_release_candidate_objects"], [])
        self.assertTrue(obj["release_candidate_planning_perimeter_complete"])
        self.assertTrue(obj["all_required_release_candidate_gap_objects_present"])
        self.assertEqual(obj["next_required_object"], NEXT)

    def test_terminal_closure_plan_does_not_close_or_advance(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_PLAN.json")
        for key in [
            "outsider_replay_execution_record_present",
            "outsider_replay_passage_record_present",
            "admissibility_verdict_record_present",
            "terminal_closure_execution_record_present",
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

        self.assertTrue(obj["terminal_closure_plan_does_not_execute_replay"])
        self.assertTrue(obj["terminal_closure_plan_does_not_pass_outsider_replay"])
        self.assertTrue(obj["terminal_closure_plan_does_not_create_admissibility_verdict"])
        self.assertTrue(obj["terminal_closure_plan_does_not_create_terminal_closure"])
        self.assertTrue(obj["terminal_closure_plan_does_not_create_release_candidate"])
        self.assertTrue(obj["terminal_closure_plan_does_not_issue_motion_picture"])
        self.assertTrue(obj["terminal_closure_plan_does_not_admit_media"])
        self.assertTrue(obj["terminal_closure_plan_does_not_mutate_current_state"])

    def test_case_record_identity(self):
        obj = load(f"CASES/{CASE_ID}/RELEASE_CANDIDATE_TERMINAL_CLOSURE_PLAN/RELEASE_CANDIDATE_TERMINAL_CLOSURE_PLAN.json")
        self.assertEqual(obj["record_id"], "TERMINAL_CLOSURE_PLAN_001_RELEASE_CANDIDATE")
        self.assertEqual(obj["object_type"], "CINEMATICUM_RELEASE_CANDIDATE_TERMINAL_CLOSURE_PLAN")
        self.assertEqual(obj["required_remaining_release_candidate_objects"], [])

if __name__ == "__main__":
    unittest.main()

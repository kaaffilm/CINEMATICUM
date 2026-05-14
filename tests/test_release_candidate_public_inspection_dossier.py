import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_OUTSIDER_REPLAY_PLAN"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestReleaseCandidatePublicInspectionDossier(unittest.TestCase):
    def test_public_inspection_dossier_present_and_bounded(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_PUBLIC_INSPECTION_DOSSIER.json")
        self.assertEqual(obj["case_id"], CASE_ID)
        self.assertEqual(obj["current_state"], CURRENT_STATE)
        self.assertTrue(obj["release_candidate_gap_ledger_present"])
        self.assertTrue(obj["release_candidate_artifacts_docket_present"])
        self.assertTrue(obj["release_candidate_manifest_present"])
        self.assertTrue(obj["release_candidate_evidence_bundle_present"])
        self.assertTrue(obj["release_candidate_public_inspection_dossier_present"])
        self.assertTrue(obj["release_candidate_public_inspection_dossier_sealed"])
        self.assertTrue(obj["authority_object_stack_complete"])
        self.assertTrue(obj["future_authority_satisfaction_gate_passed"])
        self.assertEqual(obj["accepted_authority_object_count"], 8)
        self.assertEqual(obj["instantiated_authority_object_count"], 8)
        self.assertEqual(obj["unfilled_authority_object_slot_count"], 0)
        self.assertFalse(obj["public_inspection_private_access_required"])
        self.assertFalse(obj["public_inspection_media_or_model_payload_present"])
        self.assertFalse(obj["public_inspection_verdict_present"])
        self.assertEqual(obj["required_remaining_release_candidate_gap_count"], 2)
        self.assertEqual(obj["next_required_object"], NEXT)

    def test_public_inspection_dossier_does_not_advance_or_issue(self):
        obj = load("CINEMATICUM_RELEASE_CANDIDATE_PUBLIC_INSPECTION_DOSSIER.json")
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

    def test_case_record_identity(self):
        obj = load(f"CASES/{CASE_ID}/RELEASE_CANDIDATE_PUBLIC_INSPECTION_DOSSIER/RELEASE_CANDIDATE_PUBLIC_INSPECTION_DOSSIER.json")
        self.assertEqual(obj["record_id"], "PUBLIC_INSPECTION_DOSSIER_001_RELEASE_CANDIDATE")
        self.assertEqual(obj["object_type"], "CINEMATICUM_RELEASE_CANDIDATE_PUBLIC_INSPECTION_DOSSIER")
        self.assertEqual(obj["required_remaining_release_candidate_objects"][0], NEXT)

if __name__ == "__main__":
    unittest.main()

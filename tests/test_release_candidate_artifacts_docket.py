import json
import unittest
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"
CURRENT_STATE = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
NEXT = "RELEASE_CANDIDATE_MANIFEST"

class ReleaseCandidateArtifactsDocketTest(unittest.TestCase):
    def load(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_root_object_is_sealed_non_advancing_docket(self):
        obj = self.load("CINEMATICUM_RELEASE_CANDIDATE_ARTIFACTS_DOCKET.json")
        self.assertEqual(obj["case_id"], CASE_ID)
        self.assertEqual(obj["current_state"], CURRENT_STATE)
        self.assertTrue(obj["release_candidate_artifacts_docket_present"])
        self.assertTrue(obj["release_candidate_artifacts_docket_sealed"])
        self.assertFalse(obj["release_candidate_ready"])
        self.assertFalse(obj["issued"])
        self.assertFalse(obj["media_present"])
        self.assertFalse(obj["may_advance_now"])
        self.assertEqual(obj["next_required_object"], NEXT)

    def test_case_record_identity(self):
        obj = self.load(f"CASES/{CASE_ID}/RELEASE_CANDIDATE_ARTIFACTS_DOCKET/RELEASE_CANDIDATE_ARTIFACTS_DOCKET.json")
        self.assertEqual(obj["record_id"], "DOCKET_001_RELEASE_CANDIDATE_ARTIFACTS")
        self.assertEqual(obj["required_remaining_release_candidate_gap_count"], 5)
        self.assertEqual(obj["required_remaining_release_candidate_objects"][0], NEXT)

    def test_docket_does_not_satisfy_release_candidate_requirements(self):
        obj = self.load("CINEMATICUM_RELEASE_CANDIDATE_ARTIFACTS_DOCKET.json")
        for key in [
            "docket_does_not_create_release_candidate",
            "docket_does_not_create_manifest",
            "docket_does_not_create_evidence_bundle",
            "docket_does_not_create_public_inspection_dossier",
            "docket_does_not_pass_outsider_replay",
            "docket_does_not_create_terminal_closure",
            "docket_does_not_issue_motion_picture",
            "docket_does_not_admit_media",
            "docket_does_not_mutate_current_state",
        ]:
            self.assertTrue(obj[key])
        self.assertFalse(obj["authority_satisfied"])

if __name__ == "__main__":
    unittest.main()

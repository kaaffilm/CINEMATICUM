import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestMotionPictureIssuanceAct(unittest.TestCase):
    def test_motion_picture_issuance_act_issues_hash_bound_external_media(self):
        act = load("MOTION_PICTURE_ISSUANCE_ACT.json")
        prior = load("RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD.json")

        self.assertEqual(act["object_type"], "MOTION_PICTURE_ISSUANCE_ACT")
        self.assertEqual(act["schema_version"], "cinematicum.motion_picture_issuance_act.v1")
        self.assertEqual(act["case_id"], CASE_ID)
        self.assertEqual(act["current_state"], "RELEASE_CANDIDATE_READY")

        self.assertTrue(prior.get("issuance_unblocked"))
        self.assertTrue(act["release_candidate_ready"])
        self.assertTrue(act["issuance_unblocked"])
        self.assertTrue(act["motion_picture_issuance_act_present"])

        # Semantic boundary: media is issued only as hash-bound external media.
        self.assertEqual(act["issued_object"], "HASH_BOUND_MOTION_PICTURE_MEDIA")
        self.assertTrue(act["issued"])
        self.assertTrue(act["admissible_motion_picture_issued"])
        self.assertTrue(act.get("motion_picture_issued", False))
        self.assertTrue(act.get("motion_picture_media_issued", False))
        self.assertTrue(act["media_present"])
        self.assertTrue(act.get("motion_picture_media_issuance_ready", False))
        self.assertTrue(act["media_admitted"])
        self.assertFalse(act.get("media_payload_present", False))
        self.assertFalse(act["raw_media_stored_in_git"])
        self.assertEqual(
            act["motion_picture_media_admission_record"],
            "records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json",
        )
        self.assertEqual(
            act["media_sha256"],
            "1822a3c1f7a1718fbd38e6ecabb74f9f0abff6369553051569cdd4178971f5a8",
        )

        self.assertFalse(act["generation_admitted"])
        self.assertFalse(act["engine_admitted"])
        self.assertFalse(act["raw_media_in_git"])
        self.assertFalse(act["model_weights_in_git"])
        self.assertFalse(act["may_advance_now"])
        self.assertEqual(act["next_required_object"], "NONE")

    def test_motion_picture_issuance_act_status_preserves_declared_keys(self):
        act = load("MOTION_PICTURE_ISSUANCE_ACT.json")
        status = load(f"CASES/{CASE_ID}/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json")

        # Status records are allowed to be thinner than the canonical act.
        for key in [
            "issued",
            "issuance_unblocked",
            "media_present",
            "next_required_object",
        ]:
            self.assertIn(key, status)
            self.assertEqual(status[key], act[key], key)

        for key in [
            "admissible_motion_picture_issued",
            "motion_picture_issued",
            "media_payload_present",
            "motion_picture_media_issuance_ready",
        ]:
            if key in status:
                self.assertEqual(status[key], act.get(key), key)

if __name__ == "__main__":
    unittest.main()

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestMotionPictureIssuanceAct(unittest.TestCase):
    def test_motion_picture_issuance_act_is_not_media_body_issuance(self):
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

        # Semantic boundary: no admitted media/audience body exists here.
        self.assertFalse(act["issued"])
        self.assertFalse(act["admissible_motion_picture_issued"])
        self.assertFalse(act.get("motion_picture_issued", False))
        self.assertFalse(act["media_present"])
        self.assertFalse(act.get("media_payload_present", False))
        self.assertFalse(act.get("motion_picture_media_issuance_ready", False))

        self.assertFalse(act["media_admitted"])
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

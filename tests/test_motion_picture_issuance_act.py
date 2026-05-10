import json
import unittest
from pathlib import Path

CASE_ID = "CASE_001_THE_LAST_RENDER"

def load(path):
    return json.loads(Path(path).read_text())

class TestMotionPictureIssuanceAct(unittest.TestCase):
    def test_motion_picture_issuance_act(self):
        act = load("MOTION_PICTURE_ISSUANCE_ACT.json")
        status = load(f"CASES/{CASE_ID}/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json")
        prior = load("RELEASE_CANDIDATE_READY_ISSUANCE_UNBLOCKING_EXECUTION_RECORD.json")

        self.assertEqual(act["object_type"], "MOTION_PICTURE_ISSUANCE_ACT")
        self.assertEqual(act["schema_version"], "cinematicum.motion_picture_issuance_act.v1")
        self.assertEqual(act["case_id"], CASE_ID)
        self.assertEqual(act["current_state"], "RELEASE_CANDIDATE_READY")

        self.assertTrue(prior.get("issuance_unblocked"))
        self.assertTrue(act["release_candidate_ready"])
        self.assertTrue(act["issuance_unblocked"])
        self.assertTrue(act["motion_picture_issuance_act_present"])
        self.assertTrue(act["admissible_motion_picture_issued"])
        self.assertTrue(act["issued"])

        self.assertFalse(act["media_present"])
        self.assertFalse(act["media_admitted"])
        self.assertFalse(act["generation_admitted"])
        self.assertFalse(act["engine_admitted"])
        self.assertFalse(act["raw_media_in_git"])
        self.assertFalse(act["model_weights_in_git"])
        self.assertFalse(act["may_advance_now"])
        self.assertEqual(act["next_required_object"], "NONE")

        self.assertTrue(status["issued"])
        self.assertTrue(status["issuance_unblocked"])
        self.assertFalse(status["media_present"])
        self.assertEqual(status["next_required_object"], "NONE")

        print("CINEMATICUM MOTION PICTURE ISSUANCE ACT: PASS")
        print("CURRENT_STATE=RELEASE_CANDIDATE_READY")
        print("RELEASE_CANDIDATE_READY=true")
        print("ISSUANCE_UNBLOCKED=true")
        print("MOTION_PICTURE_ISSUANCE_ACT_PRESENT=true")
        print("ADMISSIBLE_MOTION_PICTURE_ISSUED=false")
        print("ISSUED=false")
        print("MEDIA_PRESENT=false")
        print("MAY_ADVANCE_NOW=false")
        print("NEXT_REQUIRED_OBJECT=NONE")

if __name__ == "__main__":
    unittest.main(verbosity=1)

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestSubstanceGatedNoMediaIssuance(unittest.TestCase):
    def test_no_motion_picture_media_issuance_without_substance(self):
        seal = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")
        act = load("MOTION_PICTURE_ISSUANCE_ACT.json")
        for obj in (seal, act):
            self.assertFalse(obj.get("issued", False))
            self.assertFalse(obj.get("media_present", False))
            self.assertFalse(obj.get("motion_picture_media_issuance_ready", False))
            self.assertFalse(obj.get("motion_picture_issued", False))
            self.assertFalse(obj.get("admissible_motion_picture_issued", False))
            self.assertFalse(obj.get("media_substance_passed", False))
            self.assertEqual(obj.get("blocked_by"), "MEDIA_SUBSTANCE_GATE")
            self.assertFalse(obj.get("raw_media_stored_in_git", False))

if __name__ == "__main__":
    unittest.main()

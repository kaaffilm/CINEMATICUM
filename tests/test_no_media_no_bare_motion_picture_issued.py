import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestNoMediaNoBareMotionPictureIssued(unittest.TestCase):
    def test_protocol_issuance_is_named_and_media_issuance_is_hash_bound(self):
        seal = json.loads((ROOT / "CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())

        self.assertTrue(seal["protocol_issued"])
        self.assertTrue(seal["protocol_perimeter_issued"])
        self.assertTrue(seal["protocol_film_issued"])

        self.assertTrue(seal["issued"])
        self.assertTrue(seal["media_present"])
        self.assertFalse(seal["raw_media_stored_in_git"])

    def test_hash_bound_media_is_not_raw_git_media(self):
        seal = json.loads((ROOT / "CINEMATICUM_REPOSITORY_STATUS_SEAL.json").read_text())

        self.assertTrue(seal["motion_picture_media_issuance_ready"])
        self.assertTrue(seal["admissible_motion_picture_issued"])
        self.assertTrue(seal["motion_picture_issued"])
        self.assertFalse(seal["raw_media_stored_in_git"])

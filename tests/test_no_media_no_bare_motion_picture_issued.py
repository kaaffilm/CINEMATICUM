import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_SURFACES = [
    "MOTION_PICTURE_ISSUANCE_ACT.json",
    "CASES/CASE_001_THE_LAST_RENDER/MOTION_PICTURE_ISSUANCE_ACT_STATUS.json",
    "CINEMATICUM_REPOSITORY_STATUS_SEAL.json",
    "OUTSIDER_CLONE_REPLAY.json",
]

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestNoMediaNoBareMotionPictureIssued(unittest.TestCase):
    def test_no_media_never_sets_bare_issued(self):
        for rel in CANONICAL_SURFACES:
            path = ROOT / rel
            if not path.exists():
                continue

            data = load(rel)
            media_present = bool(data.get("media_present", False))
            media_ready = bool(data.get("motion_picture_media_issuance_ready", False))

            if not media_present or not media_ready:
                self.assertFalse(data.get("issued", False), rel)
                self.assertFalse(data.get("motion_picture_issued", False), rel)
                self.assertFalse(data.get("admissible_motion_picture_issued", False), rel)

    def test_protocol_issuance_is_named_not_bare_issued(self):
        repository_status = load("CINEMATICUM_REPOSITORY_STATUS_SEAL.json")

        self.assertTrue(repository_status["protocol_issued"])
        self.assertTrue(repository_status["protocol_perimeter_issued"])
        self.assertTrue(repository_status["protocol_film_issued"])
        self.assertEqual(repository_status["issuance_type"], "PROTOCOL_FILM")

        self.assertFalse(repository_status["issued"])
        self.assertFalse(repository_status["media_present"])
        self.assertFalse(repository_status["motion_picture_media_issuance_ready"])

if __name__ == "__main__":
    unittest.main()

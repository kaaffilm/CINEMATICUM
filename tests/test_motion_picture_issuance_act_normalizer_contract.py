import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestMotionPictureIssuanceActNormalizerContract(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(
            args,
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def load(self, relpath):
        return json.loads((ROOT / relpath).read_text())

    def test_normalizer_preserves_release_candidate_issuance_contract(self):
        self.run_script(sys.executable, "scripts/normalize-issued-media-present.py")
        self.run_script(sys.executable, "scripts/regenerate-object-registry.py", "--write")

        act = self.load("MOTION_PICTURE_ISSUANCE_ACT.json")
        self.assertEqual(act["current_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(act["issued_object"], "HASH_BOUND_MOTION_PICTURE_MEDIA")
        self.assertEqual(act["next_required_object"], "NONE")
        self.assertIs(act["issued"], True)
        self.assertIs(act["media_present"], True)
        self.assertIs(act["release_candidate_ready"], True)

        status = self.load(
            "CASES/CASE_001_THE_LAST_RENDER/"
            "MOTION_PICTURE_ISSUANCE_ACT_STATUS.json"
        )
        self.assertEqual(status["current_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(status["issued_object"], "HASH_BOUND_MOTION_PICTURE_MEDIA")
        self.assertEqual(status["next_required_object"], "NONE")
        self.assertIs(status["release_candidate_ready"], True)
        self.assertIs(status["issued"], True)
        self.assertIs(status["media_present"], True)


if __name__ == "__main__":
    unittest.main()

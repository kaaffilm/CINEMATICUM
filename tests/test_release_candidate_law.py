import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class TestReleaseCandidateLaw(unittest.TestCase):
    def test_release_candidate_law_is_not_issuance(self):
        law = load("RELEASE_CANDIDATE_OBJECT_LAW.json")
        self.assertEqual(law["object_type"], "CINEMATICUM_RELEASE_CANDIDATE_OBJECT_LAW")
        self.assertEqual(law["law_boundary"], "RELEASE_CANDIDATE_OBJECT_LAW_ONLY")
        self.assertFalse(law["issued_film"])
        self.assertFalse(law["media_present"])
        self.assertFalse(law["generation_present"])
        self.assertEqual(law["forbidden_pr3_transition"], "ISSUED_ADMISSIBLE_MOTION_PICTURE")

    def test_release_manifest_schema_forbids_embedded_media_and_secrets(self):
        schema = load("RELEASE_MANIFEST_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_RELEASE_ARTIFACT")
        self.assertIn("raw_media_blob", schema["forbidden_fields"])
        self.assertIn("private_key", schema["forbidden_fields"])
        self.assertIn("cloud_render_token", schema["forbidden_fields"])

    def test_hash_manifest_schema_is_hash_only(self):
        schema = load("MEDIA_HASH_MANIFEST_SCHEMA.json")
        self.assertEqual(schema["boundary"], "HASH_SCHEMA_ONLY_NO_MEDIA")
        self.assertEqual(schema["hash_algorithm"], "sha256")
        self.assertIn("media bytes", schema["forbidden_material"])
        self.assertIn("model weights", schema["forbidden_material"])

    def test_outsider_replay_requires_no_private_access(self):
        replay = load("OUTSIDER_REPLAY_REQUIREMENTS.json")
        self.assertFalse(replay["private_access_required"])
        self.assertFalse(replay["issued_film"])
        self.assertFalse(replay["media_present"])
        self.assertIn("release_manifest_object", replay["minimum_future_replay_inputs"])

    def test_case_status_is_not_ready_and_not_issued(self):
        case = load("CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_STATUS.json")
        self.assertEqual(case["case_id"], "CASE_001_THE_LAST_RENDER")
        self.assertEqual(case["current_state"], "RELEASE_CANDIDATE_LAW_DECLARED")
        self.assertFalse(case["release_candidate_ready"])
        self.assertFalse(case["issued"])
        self.assertFalse(case["media_present"])
        self.assertFalse(case["outsider_replay_passed"])

    def test_locked_picture_boundary_is_future_only(self):
        text = (ROOT / "CASES/CASE_001_THE_LAST_RENDER/LOCKED_PICTURE_BOUNDARY.md").read_text(encoding="utf-8")
        self.assertIn("PR3 does not create a locked picture.", text)
        self.assertIn("footage", text)
        self.assertIn("final media", text)


if __name__ == "__main__":
    unittest.main()

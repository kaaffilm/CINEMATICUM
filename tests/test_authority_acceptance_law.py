import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class TestAuthorityAcceptanceLaw(unittest.TestCase):
    def test_law_is_schema_only_and_not_ready(self):
        law = load("AUTHORITY_ACCEPTANCE_OBJECT_LAW.json")
        self.assertEqual(law["object_type"], "CINEMATICUM_AUTHORITY_ACCEPTANCE_OBJECT_LAW")
        self.assertEqual(law["law_boundary"], "AUTHORITY_ACCEPTANCE_OBJECT_LAW_ONLY")
        self.assertFalse(law["issued_film"])
        self.assertFalse(law["release_candidate_ready"])
        self.assertFalse(law["media_present"])
        self.assertEqual(law["pr4_state_transition"]["not_to"], "RELEASE_CANDIDATE_READY")

    def test_director_acceptance_schema_forbids_media_and_keys(self):
        schema = load("DIRECTOR_ACCEPTANCE_OBJECT_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_ACCEPTANCE_OBJECT")
        self.assertIn("embedded_media", schema["forbidden_fields"])
        self.assertIn("private_key", schema["forbidden_fields"])
        self.assertIn("model_weights", schema["forbidden_fields"])

    def test_timeline_lock_schema_is_digest_only(self):
        schema = load("FINAL_CUT_TIMELINE_LOCK_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_TIMELINE_OBJECT")
        self.assertIn("timeline_digest", schema["required_fields"])
        self.assertIn("raw_video", schema["forbidden_fields"])

    def test_sound_and_grade_locks_do_not_embed_assets(self):
        sound = load("SOUND_MIX_LOCK_SCHEMA.json")
        grade = load("COLOR_GRADE_LOCK_SCHEMA.json")
        self.assertEqual(sound["boundary"], "SCHEMA_ONLY_NO_AUDIO_OBJECT")
        self.assertEqual(grade["boundary"], "SCHEMA_ONLY_NO_IMAGE_OBJECT")
        self.assertIn("raw_audio", sound["forbidden_fields"])
        self.assertIn("raw_image", grade["forbidden_fields"])

    def test_terminal_closure_candidate_is_not_issuance(self):
        closure = load("TERMINAL_CLOSURE_CANDIDATE_SCHEMA.json")
        self.assertEqual(closure["boundary"], "SCHEMA_ONLY_NO_TERMINAL_CLOSURE")
        self.assertIn("closure_candidate_is_not_issuance", closure["required_assertions"])
        self.assertIn("media_bytes", closure["forbidden_fields"])

    def test_case_authority_acceptance_status_is_not_ready(self):
        case = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_ACCEPTANCE_STATUS.json")
        self.assertEqual(case["current_state"], "AUTHORITY_ACCEPTANCE_LAW_DECLARED")
        self.assertFalse(case["release_candidate_ready"])
        self.assertFalse(case["issued"])
        self.assertFalse(case["media_present"])
        self.assertFalse(case["director_acceptance_present"])
        self.assertFalse(case["terminal_closure_candidate_present"])

    def test_boundary_doc_refuses_issuance(self):
        text = (ROOT / "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_ACCEPTANCE_BOUNDARY.md").read_text(encoding="utf-8")
        self.assertIn("It does not issue the film.", text)
        self.assertIn("Forbidden in PR4", text)


if __name__ == "__main__":
    unittest.main()

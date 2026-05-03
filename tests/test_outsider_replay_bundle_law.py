import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class TestOutsiderReplayBundleLaw(unittest.TestCase):
    def test_law_is_schema_only_and_not_passed(self):
        law = load("OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW.json")
        self.assertEqual(law["object_type"], "CINEMATICUM_OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW")
        self.assertEqual(law["law_boundary"], "OUTSIDER_REPLAY_BUNDLE_OBJECT_LAW_ONLY")
        self.assertFalse(law["issued_film"])
        self.assertFalse(law["release_candidate_ready"])
        self.assertFalse(law["outsider_replay_passed"])
        self.assertFalse(law["media_present"])
        self.assertIn("actual replay pass", law["forbidden_pr5_outputs"])

    def test_replay_bundle_schema_is_public_and_no_media(self):
        schema = load("OUTSIDER_REPLAY_BUNDLE_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_REPLAY_BUNDLE")
        self.assertFalse(schema["private_access_required"])
        self.assertIn("bundle_contains_no_media_bytes", schema["required_assertions"])
        self.assertIn("embedded_media", schema["forbidden_fields"])
        self.assertIn("private_key", schema["forbidden_fields"])

    def test_replay_execution_report_schema_does_not_execute_replay(self):
        schema = load("REPLAY_EXECUTION_REPORT_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_REPLAY_EXECUTION")
        self.assertIn("digest_match_check", schema["required_checks"])
        self.assertIn("media_bytes", schema["forbidden_fields"])

    def test_admissibility_verdict_schema_forbids_unbounded_ai_judgment(self):
        schema = load("ADMISSIBILITY_VERDICT_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_VERDICT")
        self.assertIn("ADMISSIBLE", schema["allowed_verdicts"])
        self.assertIn("UNRESOLVED", schema["allowed_verdicts"])
        self.assertIn("unbounded_ai_judgment", schema["forbidden_fields"])
        self.assertIn("social_trust_only", schema["forbidden_fields"])

    def test_public_replay_index_schema_is_not_media_or_verdict(self):
        schema = load("PUBLIC_REPLAY_INDEX_SCHEMA.json")
        self.assertEqual(schema["boundary"], "SCHEMA_ONLY_NO_PUBLIC_INDEX")
        self.assertIn("index_does_not_embed_media", schema["required_assertions"])
        self.assertIn("index_does_not_override_verdict", schema["required_assertions"])
        self.assertIn("media_bytes", schema["forbidden_fields"])

    def test_case_replay_bundle_status_is_not_ready(self):
        case = load("CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_REPLAY_BUNDLE_STATUS.json")
        self.assertEqual(case["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertFalse(case["release_candidate_ready"])
        self.assertFalse(case["issued"])
        self.assertFalse(case["media_present"])
        self.assertFalse(case["outsider_replay_bundle_present"])
        self.assertFalse(case["admissibility_verdict_present"])
        self.assertFalse(case["outsider_replay_passed"])

    def test_boundary_doc_refuses_replay_pass_and_issuance(self):
        text = (ROOT / "CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_REPLAY_BUNDLE_BOUNDARY.md").read_text(encoding="utf-8")
        self.assertIn("It does not execute replay.", text)
        self.assertIn("It does not issue the film.", text)
        self.assertIn("replay-pass claims", text)


if __name__ == "__main__":
    unittest.main()

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestPublicInspectionDossier(unittest.TestCase):
    def test_dossier_matches_current_state(self):
        dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(dossier["current_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], "ISSUED_ADMISSIBLE_MOTION_PICTURE")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], "ISSUED_ADMISSIBLE_MOTION_PICTURE")
        self.assertEqual(case["current_state"], "ISSUED_ADMISSIBLE_MOTION_PICTURE")

    def test_dossier_requires_no_private_access(self):
        dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
        case_path = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_INSPECTION_PATH.json")
        self.assertFalse(dossier["private_access_required"])
        self.assertFalse(case_path["private_access_required"])

    def test_expected_false_claims_remain_false(self):
        dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
        for key in dossier["expected_current_claims"]:
            self.assertFalse(dossier["expected_current_claims"][key], key)

    def test_inspection_commands_include_verify_all(self):
        dossier = load("PUBLIC_INSPECTION_DOSSIER.json")
        self.assertIn("bash scripts/verify-all.sh", dossier["inspection_commands"])
        self.assertIn("bash scripts/verify-public-inspection-dossier.sh", dossier["inspection_commands"])

    def test_public_inspection_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_INSPECTION.md").read_text(encoding="utf-8")
        self.assertIn("REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", text)
        self.assertIn("release_candidate_ready=false", text)
        self.assertIn("issued=false", text)
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)

if __name__ == "__main__":
    unittest.main()

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestPublicInspectionNegativeProof(unittest.TestCase):
    def test_negative_proof_current_state(self):
        proof = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(proof["current_state"], "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], proof["current_state"])
        self.assertEqual(case["current_state"], proof["current_state"])

    def test_absence_proofs_are_true_while_values_false(self):
        proof = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")
        for key, proves_absence in proof["proves_absence_of"].items():
            self.assertTrue(proves_absence, key)
            self.assertFalse(proof["current_false_values"][key], key)

    def test_required_absent_authority_objects_are_named(self):
        proof = load("PUBLIC_INSPECTION_NEGATIVE_PROOF.json")
        for name in [
            "MOTION_PICTURE_ISSUANCE_ACT_OBJECT",
            "RELEASE_CANDIDATE_READY_OBJECT",
            "OUTSIDER_REPLAY_PASS_OBJECT",
            "ADMISSIBILITY_VERDICT_OBJECT",
            "TERMINAL_CLOSURE_OBJECT",
            "MEDIA_ADMISSION_OBJECT",
        ]:
            self.assertIn(name, proof["required_absent_authority_objects"])

    def test_status_record_is_not_current_truth(self):
        status = load("CASES/CASE_001_THE_LAST_RENDER/PUBLIC_NEGATIVE_PROOF_STATUS.json")
        self.assertEqual(status["surface_type"], "LAYER_STATUS_RECORD")
        self.assertFalse(status["current_truth_owner"])
        self.assertFalse(status["issued"])
        self.assertFalse(status["media_present"])
        self.assertFalse(status["outsider_replay_passed"])

    def test_public_negative_proof_doc_is_bounded(self):
        text = (ROOT / "PUBLIC_NEGATIVE_PROOF.md").read_text(encoding="utf-8")
        self.assertIn("does not issue a film", text)
        self.assertIn("does not admit media", text)
        self.assertIn("does not prove replay passed", text)
        self.assertIn("does not produce an admissibility verdict", text)

if __name__ == "__main__":
    unittest.main()

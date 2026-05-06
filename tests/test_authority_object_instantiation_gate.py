import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestAuthorityObjectInstantiationGate(unittest.TestCase):
    def test_gate_is_non_authorizing(self):
        gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
        self.assertFalse(gate["instantiated_authority_objects_present"])
        self.assertFalse(gate["authority_satisfied"])
        self.assertTrue(gate["required_authority_objects_missing"])
        self.assertFalse(gate["may_advance_now"])
        self.assertFalse(gate["issued"])
        self.assertFalse(gate["media_present"])

    def test_no_authority_object_json_exists(self):
        authority_json = sorted((ROOT / "authority_objects").glob("*.json"))
        self.assertEqual(authority_json, [])

    def test_forbidden_instantiations_absent(self):
        gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
        for future in gate["currently_forbidden_instantiations"]:
            self.assertFalse((ROOT / future).exists(), future)
            self.assertFalse((ROOT / "authority_objects" / future).exists(), future)

    def test_promotion_requirements_are_explicit(self):
        gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
        required = {
            "copy template outside templates/authority_objects",
            "change template_only to false",
            "provide authority_actor",
            "provide authority_timestamp_utc",
            "provide authority_basis",
            "provide explicit_acceptance_or_rejection",
            "provide object_hashes_or_references",
            "provide signature_or_public_accountable_record",
            "pass dedicated authority-object verifier",
            "pass scripts/verify-all.sh",
        }
        self.assertTrue(required.issubset(set(gate["promotion_requirements"])))

    def test_current_state_unchanged(self):
        gate = load("CINEMATICUM_AUTHORITY_OBJECT_INSTANTIATION_GATE.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        current = "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS"
        self.assertEqual(gate["current_state"], current)
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], current)
        self.assertEqual(case["current_state"], current)

    def test_markdown_boundary(self):
        text = (ROOT / "AUTHORITY_OBJECT_INSTANTIATION_GATE.md").read_text(encoding="utf-8")
        self.assertIn("The instantiation gate is not an authority object", text)
        self.assertIn("instantiated_authority_objects_present=false", text)
        self.assertIn("authority_satisfied=false", text)
        self.assertIn("may_advance_now=false", text)

if __name__ == "__main__":
    unittest.main()

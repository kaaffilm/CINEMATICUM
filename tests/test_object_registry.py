import json
import hashlib
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestObjectRegistry(unittest.TestCase):
    def test_registry_has_required_core_objects(self):
        registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
        paths = {entry["path"] for entry in registry["entries"]}
        for path in [
            "CINEMATICUM_CURRENT_STATE_INDEX.json",
            "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json",
            "CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json",
            "ADMISSIBILITY_VERDICT_SCHEMA.json",
        ]:
            self.assertIn(path, paths)

    def test_only_one_active_case_state(self):
        registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
        active = [
            entry for entry in registry["entries"]
            if entry.get("case_id") == "CASE_001_THE_LAST_RENDER"
            and entry["surface_class"] == "ACTIVE_CURRENT_STATE"
        ]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["path"], "CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")

    def test_schema_and_law_entries_do_not_claim_issuance(self):
        registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
        for entry in registry["entries"]:
            if entry["surface_class"] in {"SCHEMA_OBJECT", "LAW_OBJECT", "LAYER_STATUS_RECORD"}:
                self.assertFalse(entry["issued"], entry["path"])
                self.assertFalse(entry["release_candidate_ready"], entry["path"])
                self.assertFalse(entry["media_present"], entry["path"])
                self.assertFalse(entry["outsider_replay_passed"], entry["path"])

    def test_catalog_boundaries_false(self):
        catalog = load("CINEMATICUM_SURFACE_CLASS_CATALOG.json")
        self.assertFalse(catalog["hard_boundary"]["issued"])
        self.assertFalse(catalog["hard_boundary"]["release_candidate_ready"])
        self.assertFalse(catalog["hard_boundary"]["media_present"])
        self.assertFalse(catalog["hard_boundary"]["outsider_replay_passed"])


    def test_registry_entries_are_hash_bound_to_object_bytes(self):
        registry = load("CINEMATICUM_OBJECT_REGISTRY.json")

        for entry in registry["entries"]:
            path = ROOT / entry["path"]
            self.assertTrue(path.exists(), entry["path"])

            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(entry.get("sha256"), expected, entry["path"])

    def test_registry_current_state_matches_index(self):
        registry = load("CINEMATICUM_OBJECT_REGISTRY.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        self.assertEqual(registry["current_active_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(
            index["active_case_states"]["CASE_001_THE_LAST_RENDER"],
            "ISSUED_ADMISSIBLE_MOTION_PICTURE",
        )

if __name__ == "__main__":
    unittest.main()

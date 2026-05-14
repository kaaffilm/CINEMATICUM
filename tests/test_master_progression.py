import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class TestMasterProgression(unittest.TestCase):
    def test_matrix_matches_index_and_case(self):
        matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(matrix["current_active_state"], "RELEASE_CANDIDATE_READY")
        self.assertEqual(index["active_case_states"]["CASE_001_THE_LAST_RENDER"], matrix["current_active_state"])
        self.assertEqual(case["current_state"], matrix["current_active_state"])

    def test_future_states_not_reached(self):
        matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
        self.assertIn("RELEASE_CANDIDATE_READY", matrix["states_reached"])
        self.assertTrue(matrix["currently_false_claims"]["release_candidate_ready"])
        self.assertFalse(matrix["currently_false_claims"]["issued"])
        self.assertFalse(matrix["currently_false_claims"]["media_present"])
        self.assertTrue(matrix["currently_false_claims"]["outsider_replay_passed"])

    def test_manifest_lists_master_battery(self):
        manifest = load("CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json")
        self.assertIn("scripts/verify-master-progression.sh", manifest["required_scripts"])
        self.assertIn("scripts/verify-all.sh", manifest["required_scripts"])
        self.assertIn("tests/test_master_progression.py", manifest["required_unittests"])
        self.assertIn("master-progression", manifest["required_ci_workflows"])

    def test_graph_has_one_active_node(self):
        graph = load("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json")
        active_nodes = [node for node in graph["nodes"] if node["status"] == "active"]
        self.assertEqual(len(active_nodes), 1)
        self.assertEqual(active_nodes[0]["state"], "RELEASE_CANDIDATE_READY")

    def test_graph_blocks_release_and_issuance(self):
        graph = load("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json")
        states = {node["state"]: node["status"] for node in graph["nodes"]}
        self.assertEqual(states["RELEASE_CANDIDATE_READY"], "active")
        self.assertEqual(states["RELEASE_CANDIDATE_READY"], "active")
        self.assertTrue(graph["false_now"]["release_candidate_ready"])
        self.assertFalse(graph["false_now"]["issued"])
        self.assertFalse(graph["false_now"]["media_present"])
        self.assertTrue(graph["false_now"]["outsider_replay_passed"])

if __name__ == "__main__":
    unittest.main()

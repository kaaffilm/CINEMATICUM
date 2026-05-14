import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASE = "CASE_001_THE_LAST_RENDER"
RELEASE = "RELEASE_CANDIDATE_READY"
ISSUED = "ISSUED_ADMISSIBLE_MOTION_PICTURE"

def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def graph_states(graph):
    states = {}
    obj = graph.get("nodes") or graph.get("states") or []
    if isinstance(obj, dict):
        for key, value in obj.items():
            states[key] = value.get("status") if isinstance(value, dict) else value
    else:
        for node in obj:
            if isinstance(node, dict):
                states[node.get("state") or node.get("id") or node.get("name")] = node.get("status")
    return states

class TestMasterProgression(unittest.TestCase):
    def test_matrix_matches_index_and_case(self):
        matrix = load("CINEMATICUM_GOVERNED_PROGRESSION_MATRIX.json")
        index = load("CINEMATICUM_CURRENT_STATE_INDEX.json")
        case = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")
        self.assertEqual(matrix["current_active_state"], RELEASE)
        self.assertEqual(index["active_case_states"][CASE], RELEASE)
        self.assertEqual(case["current_state"], RELEASE)
        self.assertFalse(index["issued"])
        self.assertFalse(index["media_present"])
        self.assertFalse(index["media_substance_passed"])

    def test_graph_has_one_active_node(self):
        graph = load("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json")
        states = graph_states(graph)
        active = [state for state, status in states.items() if status == "active"]
        self.assertEqual(active, [RELEASE])

    def test_graph_blocks_release_and_issuance(self):
        graph = load("CASES/CASE_001_THE_LAST_RENDER/CASE_PROGRESSION_GRAPH.json")
        states = graph_states(graph)
        self.assertEqual(states[RELEASE], "active")
        self.assertIn(states.get(ISSUED), ("blocked", "pending", "not_reached", None))

if __name__ == "__main__":
    unittest.main()

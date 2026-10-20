"""Read-only preflight tests; no model or paid API is invoked."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch

from adapters import AdapterError
from generation_readiness import workflow_readiness


WORKFLOW = {
    "loader": {"class_type": "ModelLoader", "inputs": {"model_name": "video.safetensors"}},
    "text": {"class_type": "Prompt", "inputs": {"text": "CINEMATICUM_POSITIVE_PROMPT"}},
    "save": {"class_type": "SaveVideo", "inputs": {"model": ["loader", 0], "text": ["text", 0]}},
}
SCHEMAS = {
    "ModelLoader": {"input": {"required": {"model_name": [["video.safetensors"]]}}, "output": ["MODEL"]},
    "Prompt": {"input": {"required": {"text": ["STRING"]}}, "output": ["STRING"]},
    "SaveVideo": {"input": {"required": {"model": ["MODEL"], "text": ["STRING"]}}, "output": [], "output_node": True},
}


class ReadinessTests(unittest.TestCase):
    def inspect(self, workflow=None, schemas=None):
        with patch("generation_readiness.check_comfyui", return_value={"available": True}), \
             patch("generation_readiness._json_request", return_value=copy.deepcopy(SCHEMAS if schemas is None else schemas)) as request:
            result = workflow_readiness("http://127.0.0.1:8188", copy.deepcopy(WORKFLOW if workflow is None else workflow))
        self.assertEqual("/object_info", request.call_args.args[1])
        self.assertNotIn("payload", request.call_args.kwargs)
        return result

    def test_valid_preflight_does_not_submit_or_change_workflow(self):
        original = copy.deepcopy(WORKFLOW)
        result = self.inspect()
        self.assertTrue(result["ready"])
        self.assertEqual(3, result["checked_nodes"])
        self.assertIn("only after rendering", result["warnings"][0])
        self.assertEqual(original, WORKFLOW)

    def test_connectivity_alone_is_not_workflow_readiness(self):
        with patch("generation_readiness.check_comfyui", return_value={"available": True}), \
             patch("generation_readiness._json_request") as request:
            result = workflow_readiness("http://127.0.0.1:8188")
        self.assertTrue(result["available"])
        self.assertFalse(result["ready"])
        request.assert_not_called()

    def test_missing_model_and_node_are_explained(self):
        schemas = copy.deepcopy(SCHEMAS)
        schemas["ModelLoader"]["input"]["required"]["model_name"] = [[]]
        del schemas["Prompt"]
        errors = self.inspect(schemas=schemas)["errors"]
        self.assertTrue(any("Model unavailable" in e and "video.safetensors" in e for e in errors))
        self.assertTrue(any("Missing engine node: Prompt" in e for e in errors))

    def test_new_combo_schema_and_api_node_do_not_hide_blockers(self):
        schemas = copy.deepcopy(SCHEMAS)
        schemas["ModelLoader"]["input"]["required"]["model_name"] = ["COMBO", {"options": ["another.gguf"]}]
        schemas["SaveVideo"]["api_node"] = True
        errors = self.inspect(schemas=schemas)["errors"]
        self.assertTrue(any("Model unavailable" in e for e in errors))
        self.assertTrue(any("paid/API" in e for e in errors))

    def test_link_required_input_and_output_errors_are_actionable(self):
        workflow = copy.deepcopy(WORKFLOW)
        del workflow["save"]["inputs"]["model"]
        workflow["save"]["inputs"]["text"] = ["missing", 0]
        errors = self.inspect(workflow=workflow)["errors"]
        self.assertTrue(any("save.model is required" in e for e in errors))
        self.assertTrue(any("missing node missing" in e for e in errors))
        workflow["save"]["inputs"]["text"] = ["text", 4]
        self.assertTrue(any("invalid output index" in e for e in self.inspect(workflow=workflow)["errors"]))

    def test_cycles_and_unbound_prompt_refuse(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["text"]["inputs"]["text"] = ["save", 0]
        errors = self.inspect(workflow=workflow)["errors"]
        self.assertTrue(any("dependency cycle" in e for e in errors))
        self.assertTrue(any("positive prompt" in e for e in errors))

    def test_offline_and_metadata_failure_are_not_success(self):
        with patch("generation_readiness.check_comfyui", return_value={"available": False, "reason": "Connection refused"}), \
             patch("generation_readiness._json_request") as request:
            result = workflow_readiness("http://127.0.0.1:8188", WORKFLOW)
        self.assertFalse(result["ready"])
        self.assertEqual("Connection refused", result["reason"])
        request.assert_not_called()
        with patch("generation_readiness.check_comfyui", return_value={"available": True}), \
             patch("generation_readiness._json_request", side_effect=AdapterError("metadata unavailable")):
            result = workflow_readiness("http://127.0.0.1:8188", WORKFLOW)
        self.assertFalse(result["ready"])
        self.assertIn("metadata unavailable", result["errors"])


if __name__ == "__main__":
    unittest.main()

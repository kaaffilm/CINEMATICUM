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
    "generate": {"class_type": "Generate", "inputs": {"model": ["loader", 0], "text": ["text", 0], "frames": 24, "seed": 0}},
    "save": {"class_type": "SaveVideo", "inputs": {"video": ["generate", 0], "format": "mp4"}},
}
SCHEMAS = {
    "ModelLoader": {"input": {"required": {"model_name": [["video.safetensors"]]}}, "output": ["MODEL"]},
    "Prompt": {"input": {"required": {"text": ["STRING"]}}, "output": ["STRING"]},
    "Generate": {"input": {"required": {"model": ["MODEL"], "text": ["STRING"], "frames": ["INT", {"min": 1, "max": 120}],
                                           "seed": ["INT", {"min": 0, "max": 2**32 - 1}]}}, "output": ["VIDEO"]},
    "SaveVideo": {"input": {"required": {"video": ["VIDEO"], "format": [["auto", "mp4", "webm", "mkv"]]}},
                  "output": ["VIDEO"], "output_node": True},
}


class ReadinessTests(unittest.TestCase):
    def inspect(self, workflow=None, schemas=None, **bindings):
        with patch("generation_readiness.check_comfyui", return_value={"available": True}), \
             patch("generation_readiness._json_request", return_value=copy.deepcopy(SCHEMAS if schemas is None else schemas)) as request:
            result = workflow_readiness("http://127.0.0.1:8188", copy.deepcopy(WORKFLOW if workflow is None else workflow), **bindings)
        self.assertEqual("/object_info", request.call_args.args[1])
        self.assertNotIn("payload", request.call_args.kwargs)
        return result

    def test_valid_preflight_does_not_submit_or_change_workflow(self):
        original = copy.deepcopy(WORKFLOW)
        result = self.inspect()
        self.assertTrue(result["ready"])
        self.assertEqual(4, result["checked_nodes"])
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
        del workflow["generate"]["inputs"]["model"]
        workflow["save"]["inputs"]["video"] = ["missing", 0]
        errors = self.inspect(workflow=workflow)["errors"]
        self.assertTrue(any("generate.model is required" in e for e in errors))
        self.assertTrue(any("missing node missing" in e for e in errors))
        workflow["save"]["inputs"]["video"] = ["text", 4]
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

    def test_socket_types_numeric_ranges_and_literal_types_reject(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["generate"]["inputs"]["model"] = ["text", 0]
        errors = self.inspect(workflow)["errors"]
        self.assertTrue(any("incompatible socket types: STRING → MODEL" in e for e in errors))
        for value in (-1, 121, True, 1.5, "24"):
            with self.subTest(frames=value):
                workflow = copy.deepcopy(WORKFLOW)
                workflow["generate"]["inputs"]["frames"] = value
                result = self.inspect(workflow)
                self.assertFalse(result["ready"])
                self.assertTrue(any("generate.frames" in e for e in result["errors"]))

    def test_choices_are_checked_for_non_model_inputs_too(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["save"]["inputs"]["format"] = "unavailable"
        self.assertTrue(any("save.format has an unavailable choice" in e for e in self.inspect(workflow)["errors"]))

    def test_image_output_and_unrecognized_output_do_not_claim_video(self):
        for class_name in ("SaveImage", "Output", "CustomVideoSaver"):
            workflow, schemas = copy.deepcopy(WORKFLOW), copy.deepcopy(SCHEMAS)
            workflow["save"]["class_type"] = class_name
            schemas[class_name] = schemas.pop("SaveVideo")
            with self.subTest(class_name=class_name):
                result = self.inspect(workflow, schemas)
                self.assertFalse(result["ready"])
                self.assertTrue(any("No verified MP4" in e for e in result["errors"]))

    def test_video_saver_needs_supported_format_and_connected_prompt(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["save"]["inputs"]["format"] = "mkv"
        self.assertFalse(self.inspect(workflow)["ready"])
        workflow = copy.deepcopy(WORKFLOW)
        workflow["generate"]["inputs"]["text"] = "fixed text"
        result = self.inspect(workflow)
        self.assertFalse(result["ready"])
        self.assertTrue(any("positive prompt is disconnected" in e for e in result["errors"]))

    def test_supported_webm_and_vhs_savers_require_picture_link(self):
        for saver, inputs, definitions in (
                ("SaveWEBM", {}, {}),
                ("VHS_VideoCombine", {"format": "video/h264-mp4"}, {"format": [["video/h264-mp4", "image/gif"]]})):
            workflow, schemas = copy.deepcopy(WORKFLOW), copy.deepcopy(SCHEMAS)
            schemas["Generate"]["output"] = ["IMAGE"]
            schemas[saver] = {"input": {"required": {"images": ["IMAGE"], **definitions}}, "output": [], "output_node": True}
            workflow["save"] = {"class_type": saver, "inputs": {"images": ["generate", 0], **inputs}}
            with self.subTest(saver=saver):
                self.assertTrue(self.inspect(workflow, schemas)["ready"])
                if saver == "VHS_VideoCombine":
                    workflow["save"]["inputs"]["format"] = "image/gif"
                    self.assertFalse(self.inspect(workflow, schemas)["ready"])

    def test_seed_marker_is_typed_and_bound_range_is_checked_before_submit(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["generate"]["inputs"]["seed"] = "CINEMATICUM_SEED"
        result = self.inspect(workflow)
        self.assertTrue(result["ready"])
        self.assertTrue(any("seed is checked" in w for w in result["warnings"]))
        self.assertTrue(self.inspect(workflow, prompt="actual prompt", negative="", seed=5)["ready"])
        bad = self.inspect(workflow, prompt="actual prompt", negative="", seed=2**32)
        self.assertFalse(bad["ready"])
        self.assertTrue(any("generate.seed is outside" in e for e in bad["errors"]))
        workflow["generate"]["inputs"]["seed"] = "seed=CINEMATICUM_SEED"
        self.assertFalse(self.inspect(workflow)["ready"])

    def test_unknown_inputs_and_bad_link_shapes_are_errors(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["generate"]["inputs"]["typo_frames"] = 24
        self.assertTrue(any("not declared" in e for e in self.inspect(workflow)["errors"]))
        for link in (["loader", True], ["loader", 0, 1], ["loader", -1]):
            workflow = copy.deepcopy(WORKFLOW)
            workflow["generate"]["inputs"]["model"] = link
            with self.subTest(link=link):
                self.assertFalse(self.inspect(workflow)["ready"])

    def test_declared_union_and_wildcard_sockets_are_accepted(self):
        for socket in ("MODEL, STRING", "*"):
            workflow, schemas = copy.deepcopy(WORKFLOW), copy.deepcopy(SCHEMAS)
            schemas["Generate"]["input"]["required"]["model"] = [socket]
            workflow["generate"]["inputs"]["model"] = ["text", 0]
            with self.subTest(socket=socket):
                self.assertTrue(self.inspect(workflow, schemas)["ready"])

    def test_modern_dynamic_combo_flattens_selected_schema_and_enforces_nested_bounds(self):
        schemas, workflow = copy.deepcopy(SCHEMAS), copy.deepcopy(WORKFLOW)
        schemas["SaveVideo"]["input"]["required"]["format"] = ["COMFY_DYNAMICCOMBO_V3", {"options": [
            {"key": "mp4", "inputs": {"required": {"codec": ["COMFY_DYNAMICCOMBO_V3", {"options": [
                {"key": "h264", "inputs": {"optional": {"crf": ["FLOAT", {"min": 0, "max": 51}]}}},
                {"key": "auto", "inputs": {"required": {}}}] } ]}}},
            {"key": "webm", "inputs": {"required": {}}}]}]
        workflow["save"]["inputs"].update({"format.codec": "h264", "format.codec.crf": 23})
        self.assertTrue(self.inspect(workflow, schemas)["ready"])
        workflow["save"]["inputs"]["format.codec.crf"] = 100
        bad = self.inspect(workflow, schemas)
        self.assertFalse(bad["ready"])
        self.assertTrue(any("save.format.codec.crf is outside" in e for e in bad["errors"]))
        workflow["save"]["inputs"]["format"] = "webm"
        self.assertTrue(any("not declared" in e for e in self.inspect(workflow, schemas)["errors"]))


if __name__ == "__main__":
    unittest.main()

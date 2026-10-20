"""Read-only ComfyUI workflow preflight against the configured engine.

Node schemas come from /object_info, not a hardcoded catalogue. A successful
preflight is not a claim that model execution or video output has succeeded.
No prompt is submitted and no model is downloaded by this module.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath

from adapters import (AdapterError, POSITIVE_MARKER, _base_url, _json_request,
                      check_comfyui, validate_workflow)


MODEL_INPUTS = {"ckpt_name", "unet_name", "clip_name", "clip_name1", "clip_name2",
                "clip_name3", "vae_name", "lora_name", "model_name", "control_net_name",
                "style_model_name", "diffusion_model", "text_encoder_name"}
MODEL_SUFFIXES = {".safetensors", ".ckpt", ".gguf", ".pth", ".pt", ".bin"}


def workflow_readiness(url, workflow=None):
    """Report observed blockers; never infer success from mere connectivity."""
    result = {"available": False, "ready": False, "checked_nodes": 0,
              "errors": [], "warnings": [], "reason": ""}
    if workflow is None:
        result["errors"].append("Import a ComfyUI API workflow that saves video.")
    else:
        try:
            workflow = validate_workflow(workflow)
        except AdapterError as exc:
            result["errors"].append(str(exc))
            workflow = None
    connection = check_comfyui(url)
    result["available"] = connection["available"]
    if not connection["available"]:
        result["errors"].insert(0, connection["reason"])
        result["reason"] = result["errors"][0]
        return result
    if workflow is None:
        result["reason"] = result["errors"][0]
        return result
    if not any(POSITIVE_MARKER in json.dumps(n["inputs"]) for n in workflow.values()):
        result["errors"].append("Bind the positive prompt to a workflow input before generating.")
    try:
        schemas = _json_request(_base_url(url), "/object_info", timeout=5)
    except AdapterError as exc:
        result["errors"].append(str(exc))
        result["reason"] = result["errors"][0]
        return result

    dependencies = {node_id: set() for node_id in workflow}
    output_nodes = []
    for node_id, node in workflow.items():
        class_name = node["class_type"]
        schema = schemas.get(class_name)
        if not isinstance(schema, dict):
            result["errors"].append("Missing engine node: %s (workflow node %s)." % (class_name, node_id))
            continue
        result["checked_nodes"] += 1
        if schema.get("api_node"):
            # Local workflows must not silently route an apparently local
            # generation into a separately billed partner API.
            result["errors"].append("%s is a paid/API node; this local-engine adapter does not submit paid workflows." % class_name)
        if schema.get("output_node") is True:
            output_nodes.append(node_id)
        inputs = schema.get("input", {})
        required = inputs.get("required", {}) if isinstance(inputs, dict) else {}
        optional = inputs.get("optional", {}) if isinstance(inputs, dict) else {}
        definitions = {**(required if isinstance(required, dict) else {}),
                       **(optional if isinstance(optional, dict) else {})}
        for name in required if isinstance(required, dict) else ():
            if name not in node["inputs"]:
                result["errors"].append("%s.%s is required by the installed engine." % (node_id, name))
        for name, value in node["inputs"].items():
            if (isinstance(value, list) and len(value) == 2
                    and isinstance(value[0], str) and isinstance(value[1], int)
                    and not isinstance(value[1], bool)):
                source_id, index = value
                if source_id not in workflow:
                    result["errors"].append("%s.%s refers to missing node %s." % (node_id, name, source_id))
                    continue
                dependencies[node_id].add(source_id)
                source_schema = schemas.get(workflow[source_id]["class_type"], {})
                outputs = source_schema.get("output") if isinstance(source_schema, dict) else None
                if index < 0 or isinstance(outputs, list) and index >= len(outputs):
                    result["errors"].append("%s.%s refers to an invalid output index." % (node_id, name))
                continue
            spec = definitions.get(name)
            options = spec[0] if isinstance(spec, list) and spec else None
            # Newer combo definitions can supply options in their second item.
            if options == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
                options = spec[1].get("options")
            is_model = (name in MODEL_INPUTS or isinstance(value, str)
                        and PurePosixPath(value).suffix.lower() in MODEL_SUFFIXES)
            if is_model and isinstance(options, list) and isinstance(value, str) and value not in options:
                result["errors"].append("Model unavailable: %s = %s (node %s)." % (name, value, node_id))
    # Iterative topological reduction avoids recursion limits on large workflows.
    remaining = {key: set(value) for key, value in dependencies.items()}
    while remaining:
        leaves = {key for key, value in remaining.items() if not value}
        if not leaves:
            result["errors"].append("Workflow contains a dependency cycle.")
            break
        remaining = {key: value - leaves for key, value in remaining.items() if key not in leaves}
    if not output_nodes:
        result["errors"].append("No output node is advertised by this workflow's installed node definitions.")
    result["errors"] = list(dict.fromkeys(result["errors"]))[:100]
    result["warnings"].append("Preflight checks node definitions and model choices. Video execution and output are verified only after rendering.")
    result["ready"] = not result["errors"]
    result["reason"] = result["errors"][0] if result["errors"] else "Workflow preflight passed."
    return result

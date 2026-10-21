"""Read-only ComfyUI workflow preflight against the configured engine.

Node schemas come from /object_info, not a hardcoded catalogue. A successful
preflight is not a claim that model execution or video output has succeeded.
No prompt is submitted and no model is downloaded by this module.
"""
from __future__ import annotations

import json
import math
from pathlib import PurePosixPath

from adapters import (AdapterError, POSITIVE_MARKER, NEGATIVE_MARKER, SEED_MARKER,
                      _base_url, _bind_workflow, _json_request, check_comfyui, validate_workflow)


MODEL_INPUTS = {"ckpt_name", "unet_name", "clip_name", "clip_name1", "clip_name2",
                "clip_name3", "vae_name", "lora_name", "model_name", "control_net_name",
                "style_model_name", "diffusion_model", "text_encoder_name"}
MODEL_SUFFIXES = {".safetensors", ".ckpt", ".gguf", ".pth", ".pt", ".bin"}


def _link(value):
    return (isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)
            and isinstance(value[1], int) and not isinstance(value[1], bool))


def _definitions(schema, values, label, errors):
    """Flatten the selected V3 dynamic combo branches, using engine metadata.

    ComfyUI serializes V3 inputs with dotted API keys, not nested values. This
    handles its dynamic combos/slots without executing any custom-node code.
    Unknown dynamic forms fail explicitly rather than being treated as valid.
    """
    definitions, required = {}, set()
    pending = [(schema.get("input", {}), "", 0)]
    while pending:
        groups, prefix, depth = pending.pop()
        if not isinstance(groups, dict) or depth > 16 or len(definitions) > 10000:
            errors.append("%s has unsupported or excessively nested input metadata." % label)
            continue
        for category in ("required", "optional"):
            entries = groups.get(category, {})
            if not isinstance(entries, dict):
                errors.append("%s has invalid %s input metadata." % (label, category))
                continue
            for name, spec in entries.items():
                if not isinstance(name, str) or not isinstance(spec, list) or not spec:
                    errors.append("%s has an invalid input definition." % label)
                    continue
                name = prefix + name
                kind, options = spec[0], spec[1] if len(spec) > 1 else {}
                if not isinstance(options, dict) or not isinstance(kind, (str, list)):
                    errors.append("%s.%s has invalid input metadata." % (label, name))
                    continue
                if name in definitions:
                    errors.append("%s.%s has ambiguous input metadata." % (label, name))
                    continue
                if category == "required":
                    required.add(name)
                if kind == "COMFY_DYNAMICCOMBO_V3":
                    choices = options.get("options")
                    if (not isinstance(choices, list) or not choices or any(not isinstance(c, dict)
                            or not isinstance(c.get("key"), str) or not isinstance(c.get("inputs"), dict) for c in choices)):
                        errors.append("%s.%s has invalid dynamic-combo metadata." % (label, name))
                        continue
                    keys = [c["key"] for c in choices]
                    if len(set(keys)) != len(keys):
                        errors.append("%s.%s has duplicate dynamic-combo choices." % (label, name))
                    definitions[name] = [keys, {k: v for k, v in options.items() if k != "options"}]
                    for choice in choices:
                        if values.get(name) == choice["key"]:
                            pending.append((choice["inputs"], name + ".", depth + 1))
                            break
                elif kind == "COMFY_DYNAMICSLOT_V3":
                    slot_kind = options.get("slotType")
                    if not isinstance(slot_kind, str) or not isinstance(options.get("inputs"), dict):
                        errors.append("%s.%s has invalid dynamic-slot metadata." % (label, name))
                        continue
                    definitions[name] = [slot_kind, {k: v for k, v in options.items() if k not in ("slotType", "inputs")}]
                    if name in values:
                        pending.append((options["inputs"], name + ".", depth + 1))
                else:
                    if isinstance(kind, str) and kind.startswith("COMFY_DYNAMIC"):
                        errors.append("%s.%s uses a dynamic input form this preflight cannot validate." % (label, name))
                    definitions[name] = spec
    return definitions, required


def _compatible(source, destination):
    """ComfyUI socket unions accept overlap; '*' remains an explicit wildcard."""
    if isinstance(destination, list):
        destination = "COMBO"
    if isinstance(source, list):
        source = "COMBO"
    if not isinstance(source, str) or not isinstance(destination, str):
        return False
    source_types, dest_types = set(source.split(",")), set(destination.split(","))
    source_types, dest_types = {t.strip() for t in source_types}, {t.strip() for t in dest_types}
    return bool(source_types & dest_types or "*" in source_types or "*" in dest_types)


def _literal(value, spec, name, label, errors, warnings):
    kind, options = spec[0], spec[1] if len(spec) > 1 else {}
    choices = kind if isinstance(kind, list) else options.get("options") if kind == "COMBO" else None
    if isinstance(choices, list):
        if not any(type(value) is type(choice) and value == choice for choice in choices):
            is_model = name.split(".")[-1] in MODEL_INPUTS or isinstance(value, str) and PurePosixPath(value).suffix.lower() in MODEL_SUFFIXES
            errors.append(("Model unavailable: %s = %s." if is_model else "%s has an unavailable choice: %s.") % (label, str(value)[:200]))
        return
    if kind == "COMBO":
        errors.append("%s has no enumerable choices in the installed node metadata." % label)
        return
    if options.get("forceInput"):
        errors.append("%s requires a node connection, not a literal value." % label)
        return
    if value == SEED_MARKER and kind == "INT":
        warnings.append("%s: the seed is checked against the declared range when generation is submitted." % label)
        return
    if isinstance(value, str) and SEED_MARKER in value:
        errors.append("%s must bind CINEMATICUM_SEED as a whole INT input." % label)
        return
    accepted = {"INT": isinstance(value, int) and not isinstance(value, bool),
                "FLOAT": isinstance(value, (int, float)) and not isinstance(value, bool),
                "STRING": isinstance(value, str), "BOOLEAN": isinstance(value, bool)}
    kinds = {t.strip() for t in kind.split(",")} if isinstance(kind, str) else set()
    if "*" not in kinds and not any(accepted.get(k, False) for k in kinds):
        errors.append("%s expects %s; connect a compatible output or provide a typed literal." % (label, kind))
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            errors.append("%s must be finite." % label)
            return
        for bound, comparison in (("min", lambda a, b: a < b), ("max", lambda a, b: a > b)):
            limit = options.get(bound)
            if limit is not None and (isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit)):
                errors.append("%s has invalid numeric bounds in the installed metadata." % label)
            elif limit is not None and comparison(value, limit):
                errors.append("%s is outside the declared %s of %s." % (label, bound, limit))


def _video_output(node, definitions):
    """Only output contracts with an adapter-compatible file result count.

    OUTPUT_NODE alone also describes SaveImage/PreviewImage. These contracts
    follow core SaveVideo/SaveWEBM and VideoHelperSuite's VideoCombine, not
    class-name substring guesses. Unrecognized savers need a reviewed adapter
    contract; type metadata alone cannot prove they return a downloadable file.
    """
    kind, values = node["class_type"], node["inputs"]
    if kind == "SaveVideo":
        return (_link(values.get("video")) and "video" in definitions
                and _compatible("VIDEO", definitions["video"][0])
                and values.get("format", "auto") in ("auto", "mp4", "webm", "mov"))
    if kind == "SaveWEBM":
        return (_link(values.get("images")) and "images" in definitions
                and _compatible("IMAGE", definitions["images"][0]))
    if kind == "VHS_VideoCombine":
        format_name = values.get("format", "")
        return (_link(values.get("images")) and "images" in definitions
                and _compatible("IMAGE", definitions["images"][0]) and isinstance(format_name, str)
                and format_name.startswith("video/") and format_name.rsplit("-", 1)[-1] in ("mp4", "webm", "mov"))
    return False


def workflow_readiness(url, workflow=None, *, prompt=None, negative=None, seed=None):
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
    prompt_nodes = set()
    if workflow is not None:
        prompt_nodes = {ident for ident, node in workflow.items() if POSITIVE_MARKER in json.dumps(node["inputs"])}
        if any(value is not None for value in (prompt, negative, seed)):
            try:
                workflow, _ = _bind_workflow(workflow, prompt, negative, seed)
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
    if not prompt_nodes:
        result["errors"].append("Bind the positive prompt to a workflow input before generating.")
    try:
        schemas = _json_request(_base_url(url), "/object_info", timeout=5)
    except AdapterError as exc:
        result["errors"].append(str(exc))
        result["reason"] = result["errors"][0]
        return result

    dependencies = {node_id: set() for node_id in workflow}
    output_nodes, video_nodes = [], []
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
        definitions, required = _definitions(schema, node["inputs"], node_id, result["errors"])
        if schema.get("output_node") is True and _video_output(node, definitions):
            video_nodes.append(node_id)
        for name in required:
            if name not in node["inputs"]:
                result["errors"].append("%s.%s is required by the installed engine." % (node_id, name))
        for name, value in node["inputs"].items():
            spec = definitions.get(name)
            if spec is None:
                result["errors"].append("%s.%s is not declared by the installed engine schema." % (node_id, name))
            if _link(value):
                source_id, index = value
                if source_id not in workflow:
                    result["errors"].append("%s.%s refers to missing node %s." % (node_id, name, source_id))
                    continue
                dependencies[node_id].add(source_id)
                source_schema = schemas.get(workflow[source_id]["class_type"], {})
                outputs = source_schema.get("output") if isinstance(source_schema, dict) else None
                if not isinstance(outputs, list) or index < 0 or index >= len(outputs):
                    result["errors"].append("%s.%s refers to an invalid output index." % (node_id, name))
                elif spec and not _compatible(outputs[index], spec[0]):
                    result["errors"].append("%s.%s has incompatible socket types: %s → %s." % (node_id, name, outputs[index], spec[0]))
                continue
            if isinstance(value, list):
                result["errors"].append("%s.%s contains a malformed node connection." % (node_id, name))
            elif spec:
                _literal(value, spec, name, "%s.%s" % (node_id, name), result["errors"], result["warnings"])
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
    if not video_nodes:
        result["errors"].append("No verified MP4, WebM or MOV output route. Use SaveVideo, SaveWEBM, or VHS_VideoCombine with a supported video format; image-only and unrecognized output nodes do not supply a film shot.")
    else:
        reachable, pending = set(), list(video_nodes)
        while pending:
            ident = pending.pop()
            if ident not in reachable:
                reachable.add(ident)
                pending.extend(dependencies[ident])
        if not reachable.intersection(prompt_nodes):
            result["errors"].append("The positive prompt is disconnected from every compatible video output.")
    result["video_output_nodes"] = video_nodes
    result["errors"] = list(dict.fromkeys(result["errors"]))[:100]
    result["warnings"].insert(0, "Preflight checks declared input types, ranges, choices and video routes. Custom validation, model execution and video output are verified only after rendering.")
    result["ready"] = not result["errors"]
    result["reason"] = result["errors"][0] if result["errors"] else "Workflow preflight passed."
    return result

"""Data-only scene graphs, isolated typed contexts and real Cycles rendering.

The graph is a CINEMATICUM document, not a Gaffer/Python/plugin interpreter.
Scene paths are identities, never filesystem paths. Evaluation is pure and
branch-local; only the explicit render operation starts the existing renderer.
"""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from adapters import _cancelled, find_blender
from scene import (camera_basis, camera_basis_at, default_scene, pose_at,
                   render_scene, validate_scene)
from scene_hierarchy import local_matrix, matrix_product, transform_point
from scene_modeling import primitive_cage
from spatial_import import validate_mesh

VERSION = 1
MAX_GRAPH_BYTES = 8 * 1024 * 1024
MAX_EVALUATION_BYTES = 64 * 1024 * 1024
MAX_NODES = 128
MAX_ASSETS = 32
MAX_LOCATIONS = 512
MAX_DEPTH = 32
MAX_TASKS = 64
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024 * 1024
ARTIFACT_NAMES = frozenset({"graph.json", "evaluation.json", "scene.json", "preview.mp4",
    "authored.blend", "linear-masters.zip", "dispatch.json", "tasks.zip", "receipt.json"})
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,79}\Z")
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}\Z")
_BUILTINS = {"frame": {"type": "float", "default": 1., "min": -7200., "max": 7200.},
             "fps": {"type": "float", "default": 24., "min": 1., "max": 60.}}
_IDENTITY = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
_NODE_KEYS = {
    "source": {"asset", "root"}, "merge": {"inputs"},
    "group": {"input", "prefix", "transform"},
    "transform": {"input", "filter", "transform", "space"},
    "material": {"input", "filter", "values"},
    "attributes": {"input", "filter", "values"},
    "set": {"input", "name", "filter", "mode"},
    "prune": {"input", "filter"}, "camera": {"input", "path"},
    "context": {"input", "values"}, "time_warp": {"input", "scale", "offset"},
    "variant": {"choices", "mode", "selector", "seed", "key"},
}


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"{label} has unsupported fields.")
    return value


def _number(value, label, low=-1e6, high=1e6, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high
            or integer and int(value) != value):
        raise ValueError(f"{label} must be a finite {'integer ' if integer else ''}between {low} and {high}.")
    return int(value) if integer else (0. if value == 0 else float(value))


def _identifier(value, label="Identity"):
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError(f"{label} must be a portable identifier of at most 80 characters.")
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError("Scene graph name must be printable text of at most 120 characters.")
    return value.strip()


def validate_path(value, pattern=False):
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 2048:
        raise ValueError("A scene path must be an absolute portable hierarchy path.")
    if value == "/":
        return value
    parts = value[1:].split("/")
    if len(parts) > MAX_DEPTH:
        raise ValueError("Scene paths support at most 32 levels.")
    for part in parts:
        if part in {"", ".", ".."}:
            raise ValueError("Scene paths cannot contain empty, dot or parent segments.")
        if pattern and (part == "**" or re.fullmatch(r"[A-Za-z0-9_.*?-]{1,80}", part)):
            if "**" in part and part != "**":
                raise ValueError("The recursive wildcard ** must occupy an entire path segment.")
        elif not _SEGMENT.fullmatch(part):
            raise ValueError("Scene paths contain an unsupported segment.")
    return value


def _parent(path):
    return path.rsplit("/", 1)[0] or "/" if path != "/" else None


def _join(prefix, path):
    return validate_path((prefix.rstrip("/") + "/" + path.lstrip("/")).rstrip("/") or "/")


def _is_descendant(path, ancestor):
    return path == ancestor or ancestor == "/" or path.startswith(ancestor + "/")


def _match_path(path, pattern):
    parts = [] if path == "/" else path[1:].split("/")
    tokens = [] if pattern == "/" else pattern[1:].split("/")
    memo = {}

    def match(i, j):
        if (i, j) in memo:
            return memo[i, j]
        result = (i == len(parts)) if j == len(tokens) else (
            match(i, j + 1) or i < len(parts) and match(i + 1, j) if tokens[j] == "**" else
            i < len(parts) and fnmatch.fnmatchcase(parts[i], tokens[j]) and match(i + 1, j + 1))
        memo[i, j] = bool(result)
        return bool(result)
    return match(0, 0)


def _set_tokens(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 1024:
        raise ValueError("A set expression needs 1–1024 characters.")
    tokens, offset = [], 0
    lexer = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*|[|&()\-])")
    while offset < len(expression):
        if not expression[offset:].strip():
            break
        match = lexer.match(expression, offset)
        if not match:
            raise ValueError("Set expressions use names, parentheses, union |, intersection & and difference -.")
        tokens.append(match.group(1)); offset = match.end()
        if len(tokens) > 128:
            raise ValueError("A set expression supports at most 128 tokens.")
    return tokens


def set_expression(expression, sets, syntax_only=False):
    """Parse explicit set algebra. Intersection/difference bind before union."""
    tokens, offset = _set_tokens(expression), 0

    def primary(depth=0):
        nonlocal offset
        if depth > 32 or offset >= len(tokens):
            raise ValueError("Incomplete or excessively nested set expression.")
        token = tokens[offset]; offset += 1
        if token == "(":
            value = union(depth + 1)
            if offset >= len(tokens) or tokens[offset] != ")":
                raise ValueError("Set expression parentheses must be balanced.")
            offset += 1
            return value
        if token in {"|", "&", "-", ")"}:
            raise ValueError("A set name is required here.")
        if not syntax_only and token not in sets:
            raise ValueError("Unknown scene set: " + token)
        return set(sets.get(token, ()))

    def intersection(depth):
        nonlocal offset
        value = primary(depth)
        while offset < len(tokens) and tokens[offset] in {"&", "-"}:
            op = tokens[offset]; offset += 1
            right = primary(depth)
            value = value & right if op == "&" else value - right
        return value

    def union(depth):
        nonlocal offset
        value = intersection(depth)
        while offset < len(tokens) and tokens[offset] == "|":
            offset += 1; value |= intersection(depth)
        return value
    result = union(0)
    if offset != len(tokens):
        raise ValueError("Set expression has trailing or unbalanced tokens.")
    return result


def _context_value(value, spec, name):
    kind = spec["type"]
    if kind in {"int", "float"}:
        return _number(value, "Context " + name, spec.get("min", -1e6), spec.get("max", 1e6), kind == "int")
    if kind == "bool":
        if type(value) is not bool:
            raise ValueError("Context " + name + " must be boolean.")
        return value
    if kind == "string":
        if not isinstance(value, str) or len(value) > 256 or any(ord(c) < 32 for c in value):
            raise ValueError("Context " + name + " must be printable text of at most 256 characters.")
        return value
    if kind == "vector3":
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError("Context " + name + " needs three finite coordinates.")
        return [_number(v, "Context " + name) for v in value]
    raise ValueError("Unsupported context type.")


def _context_schema(value):
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError("Declare at most 32 typed context variables.")
    result = copy.deepcopy(_BUILTINS)
    for name, spec in value.items():
        _identifier(name, "Context name")
        if name == "time":
            raise ValueError("Context time is derived as frame/fps and is read-only.")
        spec = _mapping(spec, {"type", "default", "min", "max"}, "Context schema")
        if not isinstance(spec.get("type"), str) or spec["type"] not in {"bool", "int", "float", "string", "vector3"} or "default" not in spec:
            raise ValueError("Each context variable needs a supported type and a default.")
        if name in _BUILTINS and spec.get("type") != _BUILTINS[name]["type"]:
            raise ValueError("Frame and fps retain their built-in numeric types.")
        item = {"type": spec["type"]}
        if item["type"] in {"int", "float"}:
            bounds = _BUILTINS.get(name, {"min": -1e6, "max": 1e6})
            item["min"] = _number(spec.get("min", bounds["min"]), "Context minimum", bounds["min"], bounds["max"])
            item["max"] = _number(spec.get("max", bounds["max"]), "Context maximum", item["min"], bounds["max"])
        elif "min" in spec or "max" in spec:
            raise ValueError("Only numeric context variables accept min/max bounds.")
        item["default"] = _context_value(spec["default"], item, name)
        result[name] = item
    return result


def validate_context(value, schema=None):
    schema = _context_schema(schema or {})
    if not isinstance(value, dict) or set(value) - set(schema):
        raise ValueError("Context overrides must name declared variables; time is derived.")
    result = {name: _context_value(value.get(name, spec["default"]), spec, name) for name, spec in schema.items()}
    result["time"] = result["frame"] / result["fps"]
    return result


def _expression(value, schema, depth=0):
    if depth > 12:
        raise ValueError("Context expressions support at most twelve levels.")
    if value is None or type(value) is bool or isinstance(value, str):
        if isinstance(value, str) and (len(value) > 256 or any(ord(c) < 32 for c in value)):
            raise ValueError("Expression strings must be bounded printable text.")
        return value
    if isinstance(value, (int, float)):
        return _number(value, "Expression constant")
    if isinstance(value, list) and len(value) in {2, 3, 4}:
        return [_expression(x, schema, depth + 1) for x in value]
    if not isinstance(value, dict):
        raise ValueError("An expression must be a literal, vector, context reference or typed operation.")
    if set(value) == {"context"}:
        if not isinstance(value["context"], str) or value["context"] not in schema and value["context"] != "time":
            raise ValueError("Expression references an undeclared context variable.")
        return dict(value)
    if set(value) != {"op", "args"}:
        raise ValueError("Expression operations require op and args only.")
    op, args = value["op"], value["args"]
    counts = {"add": (2, 8), "subtract": (2, 2), "multiply": (2, 8), "divide": (2, 2),
              "min": (2, 8), "max": (2, 8), "clamp": (3, 3), "floor": (1, 1),
              "sin": (1, 1), "cos": (1, 1), "equal": (2, 2), "if": (3, 3), "concat": (2, 8)}
    if not isinstance(op, str) or op not in counts or not isinstance(args, list) or not counts[op][0] <= len(args) <= counts[op][1]:
        raise ValueError("Unsupported expression operation or argument count.")
    return {"op": op, "args": [_expression(x, schema, depth + 1) for x in args]}


def _evaluate_expression(value, context):
    if isinstance(value, list):
        return [_evaluate_expression(x, context) for x in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    if "context" in value:
        return copy.deepcopy(context[value["context"]])
    op = value["op"]
    if op == "if":
        condition = _evaluate_expression(value["args"][0], context)
        if type(condition) is not bool:
            raise ValueError("The if condition must be boolean.")
        return _evaluate_expression(value["args"][1 if condition else 2], context)
    args = [_evaluate_expression(x, context) for x in value["args"]]
    if op == "equal":
        numeric = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in args)
        return (numeric or type(args[0]) is type(args[1])) and args[0] == args[1]
    if op == "concat":
        if not all(isinstance(x, str) for x in args) or len("".join(args)) > 256:
            raise ValueError("Concat accepts only strings with a total of at most 256 characters.")
        return "".join(args)
    args = [_number(x, "Numeric expression result", -1e12, 1e12) for x in args]
    if op == "add": result = sum(args)
    elif op == "subtract": result = args[0] - args[1]
    elif op == "multiply": result = math.prod(args)
    elif op == "divide":
        if args[1] == 0: raise ValueError("Context expression division by zero.")
        result = args[0] / args[1]
    elif op == "min": result = min(args)
    elif op == "max": result = max(args)
    elif op == "clamp":
        if args[1] > args[2]: raise ValueError("Clamp minimum exceeds maximum.")
        result = min(args[2], max(args[1], args[0]))
    elif op == "floor": result = math.floor(args[0])
    elif op == "sin": result = math.sin(args[0])
    else: result = math.cos(args[0])
    return _number(result, "Context expression result", -1e12, 1e12)


def _filter(value):
    value = _mapping(value, {"paths", "sets", "descendants"}, "Scene filter")
    paths = value.get("paths", [])
    if not isinstance(paths, list) or len(paths) > 64:
        raise ValueError("A filter supports at most 64 path patterns.")
    result = {"paths": [validate_path(x, True) for x in paths], "descendants": value.get("descendants", False)}
    if type(result["descendants"]) is not bool:
        raise ValueError("Filter descendants must be boolean.")
    if "sets" in value:
        set_expression(value["sets"], {}, syntax_only=True)
        result["sets"] = value["sets"].strip()
    if not paths and "sets" not in result:
        raise ValueError("A scene filter needs a path pattern or set expression.")
    return result


def _transform(value, schema):
    value = _mapping(value, {"position", "rotation", "scale"}, "Transform")
    return {key: _expression(value.get(key, default), schema) for key, default in
            (("position", [0, 0, 0]), ("rotation", [0, 0, 0]), ("scale", [1, 1, 1]))}


def _evaluated_transform(value, context):
    result = {key: _evaluate_expression(expr, context) for key, expr in value.items()}
    for key, low, high in (("position", -1000, 1000), ("rotation", -3600, 3600), ("scale", .01, 100)):
        if not isinstance(result[key], list) or len(result[key]) != 3:
            raise ValueError("Transform " + key + " requires three coordinates.")
        result[key] = [_number(x, "Transform " + key, low, high) for x in result[key]]
    return local_matrix(result)


def default_scene_graph(scene=None):
    scene = validate_scene(scene if scene is not None else default_scene())
    return {"version": VERSION, "name": "Scene graph", "context": copy.deepcopy(_BUILTINS),
            "assets": [{"id": "main", "scene": scene}],
            "nodes": [{"id": "source", "op": "source", "asset": "main", "root": "/world"}], "output": "source"}


def _input_ids(node):
    if node["op"] == "merge": return node["inputs"]
    if node["op"] == "variant": return [choice["input"] for choice in node["choices"]]
    return [node["input"]] if "input" in node else []


def validate_scene_graph(value):
    value = _mapping(value, {"version", "name", "context", "assets", "nodes", "output"}, "Scene graph")
    if type(value.get("version")) is not int or value["version"] != VERSION:
        raise ValueError("Unsupported scene graph version.")
    if len(canonical_bytes(value)) > MAX_GRAPH_BYTES:
        raise ValueError("A scene graph must fit within 8 MiB, including embedded geometry.")
    schema = _context_schema(value.get("context", {}))
    assets = value.get("assets")
    if not isinstance(assets, list) or not 1 <= len(assets) <= MAX_ASSETS:
        raise ValueError("A scene graph requires 1–32 embedded data-only scene assets.")
    normalized_assets, asset_ids = [], set()
    for asset in assets:
        asset = _mapping(asset, {"id", "scene"}, "Scene asset")
        ident = _identifier(asset.get("id"), "Asset identity")
        if ident in asset_ids:
            raise ValueError("Scene asset identities must be distinct.")
        scene = validate_scene(asset.get("scene"))
        if any(obj.get("modeling", {}).get("modifiers") for obj in scene["objects"]):
            raise ValueError("Apply object modifiers before embedding the scene as a graph asset; cached modifier meshes are not trusted as rendering evidence.")
        asset_ids.add(ident); normalized_assets.append({"id": ident, "scene": scene})
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("A scene graph requires 1–128 nodes.")
    normalized_nodes, node_ids = [], set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("op"), str) or node["op"] not in _NODE_KEYS:
            raise ValueError("Choose a supported scene operation.")
        op = node["op"]
        _mapping(node, {"id", "op", *_NODE_KEYS[op]}, "Scene node")
        ident = _identifier(node.get("id"), "Node identity")
        if ident in node_ids: raise ValueError("Scene node identities must be distinct.")
        out = {"id": ident, "op": op}
        if "input" in _NODE_KEYS[op]: out["input"] = _identifier(node.get("input"), "Input identity")
        if "filter" in _NODE_KEYS[op]: out["filter"] = _filter(node.get("filter"))
        if "transform" in _NODE_KEYS[op]: out["transform"] = _transform(node.get("transform", {}), schema)
        if op == "source":
            if not isinstance(node.get("asset"), str) or node["asset"] not in asset_ids: raise ValueError("A source must reference an existing embedded asset.")
            out.update(asset=node["asset"], root=validate_path(node.get("root", "/world")))
        elif op == "merge":
            inputs = node.get("inputs")
            if not isinstance(inputs, list) or not 2 <= len(inputs) <= 16 or not all(isinstance(x, str) for x in inputs) or len(set(inputs)) != len(inputs):
                raise ValueError("Merge requires 2–16 distinct input nodes.")
            out["inputs"] = [_identifier(x, "Merge input") for x in inputs]
        elif op == "group":
            out["prefix"] = validate_path(node.get("prefix"))
            if out["prefix"] == "/": raise ValueError("Group needs a non-root prefix.")
        elif op == "transform":
            out["space"] = node.get("space", "local")
            if not isinstance(out["space"], str) or out["space"] not in {"local", "parent"}: raise ValueError("Transform space must be local or parent.")
        elif op in {"attributes", "material", "context"}:
            values = node.get("values")
            if not isinstance(values, dict) or not 1 <= len(values) <= 32:
                raise ValueError("A property edit needs 1–32 explicit values.")
            if op == "material" and set(values) - {"color", "roughness", "metallic", "transmission", "ior", "emission_color", "emission_strength"}:
                raise ValueError("Unsupported scene material property.")
            if op == "context" and set(values) - set(schema): raise ValueError("A context node can only override declared variables; time is derived.")
            out["values"] = {_identifier(key, "Property name"): _expression(v, schema) for key, v in values.items()}
        elif op == "set":
            out["name"] = _identifier(node.get("name"), "Set name")
            if "-" in out["name"] or out["name"].startswith("__"): raise ValueError("User set names exclude hyphens and the reserved __ prefix.")
            out["mode"] = node.get("mode", "replace")
            if not isinstance(out["mode"], str) or out["mode"] not in {"replace", "union", "difference"}: raise ValueError("Set mode must be replace, union or difference.")
        elif op == "camera": out["path"] = validate_path(node.get("path"))
        elif op == "time_warp":
            out["scale"] = _expression(node.get("scale", 1), schema)
            out["offset"] = _expression(node.get("offset", 0), schema)
        elif op == "variant":
            choices = node.get("choices")
            if not isinstance(choices, list) or not 1 <= len(choices) <= 32: raise ValueError("Variant requires 1–32 named inputs.")
            out["choices"] = []
            for choice in choices:
                _mapping(choice, {"name", "input"}, "Variant choice")
                out["choices"].append({"name": _identifier(choice.get("name"), "Variant name"), "input": _identifier(choice.get("input"), "Variant input")})
            if len({x["name"] for x in out["choices"]}) != len(choices): raise ValueError("Variant names must be distinct.")
            out["mode"] = node.get("mode", "select")
            if out["mode"] == "select":
                if "seed" in node or "key" in node: raise ValueError("Selected variants use selector, not hash seed/key.")
                out["selector"] = _expression(node.get("selector", choices[0]["name"]), schema)
            elif out["mode"] == "hash":
                if "selector" in node: raise ValueError("Hashed variants use seed and key, not selector.")
                out["seed"] = _expression(node.get("seed", 0), schema)
                out["key"] = _expression(node.get("key", ""), schema)
            else: raise ValueError("Variant mode must be select or hash.")
        node_ids.add(ident); normalized_nodes.append(out)
    by_id = {node["id"]: node for node in normalized_nodes}
    visiting, depths = set(), {}

    def visit(ident):
        if ident not in by_id: raise ValueError("Scene graph references a missing node: " + str(ident))
        if ident in visiting: raise ValueError("Scene graph contains a cycle.")
        if ident in depths: return depths[ident]
        visiting.add(ident)
        depth = 1 + max((visit(upstream) for upstream in _input_ids(by_id[ident])), default=0)
        if depth > MAX_DEPTH: raise ValueError("Scene graph branches support at most 32 upstream nodes.")
        visiting.remove(ident); depths[ident] = depth
        return depth
    for ident in by_id: visit(ident)
    output = _identifier(value.get("output"), "Output identity")
    if output not in by_id: raise ValueError("Scene graph output does not identify a node.")
    result = {"version": VERSION, "name": _name(value.get("name", "Scene graph")), "context": schema,
              "assets": normalized_assets, "nodes": normalized_nodes, "output": output}
    if len(canonical_bytes(result)) > MAX_GRAPH_BYTES: raise ValueError("Normalized scene graph exceeds 8 MiB.")
    return result


def _ensure_groups(locations, path):
    if path == "/": return
    parent = _parent(path)
    _ensure_groups(locations, parent)
    if path not in locations:
        locations[path] = {"path": path, "kind": "group", "transform": list(_IDENTITY), "attributes": {}}


def _source(asset, root, context):
    scene, frame = asset["scene"], context["frame"]
    locations, paths = {}, {}
    _ensure_groups(locations, root)
    objects = {item["id"]: item for item in scene["objects"]}
    def path_for(ident):
        if ident not in paths:
            item = objects[ident]
            prefix = path_for(item["parent_id"]) if item.get("parent_id") else _join(root, "objects")
            paths[ident] = _join(prefix, ident)
        return paths[ident]
    for ident, item in objects.items():
        path = path_for(ident); _ensure_groups(locations, _parent(path))
        payload = copy.deepcopy(item)
        payload.pop("parent_id", None); payload.pop("keyframes", None); payload.pop("modeling", None)
        locations[path] = {"path": path, "kind": "object", "transform": local_matrix(pose_at(item, frame)),
                           "attributes": {}, "object": payload, "source_asset": asset["id"], "source_object": ident}
    camera_path = _join(root, "camera")
    if camera_path in locations: raise ValueError("Source camera path collides with another location.")
    camera = copy.deepcopy(scene["camera"]); camera.update(pose_at(camera, frame, "camera")); camera.pop("keyframes", None)
    locations[camera_path] = {"path": camera_path, "kind": "camera", "transform": list(_IDENTITY), "attributes": {},
                              "camera": camera, "camera_basis": camera_basis_at(scene["camera"], frame)}
    for item in scene["lights"]:
        path = _join(root, "lights/" + item["id"]); _ensure_groups(locations, _parent(path))
        light = copy.deepcopy(item); light.update(pose_at(item, frame, "light")); light.pop("keyframes", None)
        locations[path] = {"path": path, "kind": "light", "transform": list(_IDENTITY), "attributes": {}, "light": light}
    globals_ = {key: copy.deepcopy(scene[key]) for key in ("version", "width", "height", "samples", "render", "world", "output")}
    return {"locations": locations, "sets": {}, "globals": globals_, "active_camera": camera_path}


def _sets(state):
    return {**state["sets"], **{"__" + plural: {p for p, location in state["locations"].items() if location["kind"] == kind}
            for plural, kind in (("objects", "object"), ("lights", "light"), ("cameras", "camera"), ("groups", "group"))}}


def _selected(state, filt):
    selected = {path for path in state["locations"] if any(_match_path(path, pattern) for pattern in filt["paths"])}
    if "sets" in filt: selected |= set_expression(filt["sets"], _sets(state))
    if filt["descendants"]:
        selected = {path for path in state["locations"] if any(_is_descendant(path, ancestor) for ancestor in selected)}
    return selected


def _worlds(state):
    result = {"/": list(_IDENTITY)}
    def world(path):
        if path not in result:
            location = state["locations"][path]
            result[path] = matrix_product(world(_parent(path)), location["transform"])
        return result[path]
    for path in state["locations"]: world(path)
    return result


def _evaluate(normalized, context, output):
    nodes = {item["id"]: item for item in normalized["nodes"]}
    assets = {item["id"]: item for item in normalized["assets"]}
    cache, trace, cache_bytes = {}, [], 0
    def evaluate(ident, ctx):
        nonlocal cache_bytes
        key = (ident, digest(ctx))
        if key in cache: return copy.deepcopy(cache[key])
        node = nodes[ident]; op = node["op"]
        record = {"node": ident, "op": op, "context_sha256": key[1], "context": copy.deepcopy(ctx)}
        if op == "source": state = _source(assets[node["asset"]], node["root"], ctx)
        elif op in {"context", "time_warp"}:
            derived = {k: copy.deepcopy(v) for k, v in ctx.items() if k != "time"}
            values = node["values"] if op == "context" else {"frame": {"op": "add", "args": [
                {"op": "multiply", "args": [{"context": "frame"}, node["scale"]]}, node["offset"]]}}
            derived.update({k: _evaluate_expression(v, ctx) for k, v in values.items()})
            derived = validate_context(derived, normalized["context"])
            record["upstream_context_sha256"] = digest(derived)
            state = evaluate(node["input"], derived)
        elif op == "variant":
            choices = sorted(node["choices"], key=lambda item: item["name"])
            if node["mode"] == "select":
                name = _evaluate_expression(node["selector"], ctx)
                selected = next((x for x in choices if x["name"] == name), None)
                if selected is None: raise ValueError("Variant selector does not identify a named input.")
            else:
                seed, key_value = _evaluate_expression(node["seed"], ctx), _evaluate_expression(node["key"], ctx)
                selection_hash = digest({"algorithm": "sha256-modulo-v1", "node": ident, "seed": seed, "key": key_value})
                selected = choices[int(selection_hash, 16) % len(choices)]
                record["selection_sha256"] = selection_hash
            record["selected_variant"] = selected["name"]
            state = evaluate(selected["input"], ctx)
        elif op == "merge":
            states = [evaluate(upstream, ctx) for upstream in node["inputs"]]
            state = states[0]
            for other in states[1:]:
                if canonical_bytes(other["globals"]) != canonical_bytes(state["globals"]):
                    raise ValueError("Merged scene sources must have identical resolution, world, render and output settings.")
                for path, location in other["locations"].items():
                    if path in state["locations"] and not (location["kind"] == "group" and location == state["locations"][path]):
                        raise ValueError("Merged scene paths collide: " + path)
                    state["locations"][path] = location
                for name, paths in other["sets"].items(): state["sets"].setdefault(name, set()).update(paths)
        else:
            state = evaluate(node["input"], ctx)
            if op == "group":
                prefix = node["prefix"]
                locations = {}
                for path, location in state["locations"].items():
                    new_path = _join(prefix, path); locations[new_path] = {**location, "path": new_path}
                _ensure_groups(locations, prefix)
                locations[prefix]["transform"] = _evaluated_transform(node["transform"], ctx)
                state["locations"] = locations
                state["active_camera"] = _join(prefix, state["active_camera"])
                state["sets"] = {name: {_join(prefix, path) for path in paths} for name, paths in state["sets"].items()}
            elif op == "camera":
                if node["path"] not in state["locations"] or state["locations"][node["path"]]["kind"] != "camera":
                    raise ValueError("Active camera must identify a camera location.")
                state["active_camera"] = node["path"]
            else:
                selected = _selected(state, node["filter"])
                record["matched_paths"] = sorted(selected)
                if op == "set":
                    old = state["sets"].get(node["name"], set())
                    state["sets"][node["name"]] = selected if node["mode"] == "replace" else old | selected if node["mode"] == "union" else old - selected
                elif op == "prune":
                    removed = {path for path in state["locations"] if any(_is_descendant(path, ancestor) for ancestor in selected)}
                    state["locations"] = {path: loc for path, loc in state["locations"].items() if path not in removed}
                    state["sets"] = {name: paths - removed for name, paths in state["sets"].items()}
                elif op == "transform":
                    matrix = _evaluated_transform(node["transform"], ctx)
                    for path in selected:
                        old = state["locations"][path]["transform"]
                        state["locations"][path]["transform"] = matrix_product(old, matrix) if node["space"] == "local" else matrix_product(matrix, old)
                elif op in {"material", "attributes"}:
                    values = {k: _evaluate_expression(v, ctx) for k, v in node["values"].items()}
                    if "visibility" in values and type(values["visibility"]) is not bool: raise ValueError("Visibility is a boolean attribute.")
                    for path in selected:
                        location = state["locations"][path]
                        if op == "material":
                            if location["kind"] != "object": continue
                            location["object"]["material"].update(copy.deepcopy(values))
                        else: location["attributes"].update(copy.deepcopy(values))
        if len(state["locations"]) > MAX_LOCATIONS: raise ValueError("Evaluated scenes support at most 512 locations.")
        if len(state["sets"]) > 64: raise ValueError("Evaluated scenes support at most 64 user sets.")
        # This is an eager bounded graph, not Gaffer's lazy scene-plug runtime.
        # Bound retained geometry across branches as well as node/location count.
        cache_bytes += len(canonical_bytes({**state, "sets": {name: sorted(paths) for name, paths in state["sets"].items()}}))
        if cache_bytes > MAX_EVALUATION_BYTES: raise ValueError("Retained node/context scene data exceeds the 64 MiB evaluation bound.")
        cache[key] = copy.deepcopy(state); trace.append(record)
        if len(cache) > 512: raise ValueError("One evaluation supports at most 512 node/context pairs.")
        return state
    state = evaluate(output, context)
    matrices = _worlds(state)
    locations = []
    for path in sorted(state["locations"]):
        location = copy.deepcopy(state["locations"][path])
        location["parent"] = _parent(path); location["world_transform"] = matrices[path]
        chain, current = [], path
        while current != "/": chain.append(current); current = _parent(current)
        inherited = {}
        for ancestor in reversed(chain): inherited.update(state["locations"][ancestor]["attributes"])
        location["inherited_attributes"] = inherited
        locations.append(location)
    return {"version": VERSION, "graph_sha256": digest(normalized), "output": output, "context": context,
            "context_sha256": digest(context), "locations": locations,
            "sets": {name: sorted(paths) for name, paths in sorted(_sets(state).items())},
            "globals": state["globals"], "active_camera": state["active_camera"], "trace": trace}


def evaluate_scene_graph(graph, context=None, output=None):
    graph = validate_scene_graph(graph)
    ctx = validate_context(context or {}, graph["context"])
    output = graph["output"] if output is None else _identifier(output, "Output node")
    if output not in {x["id"] for x in graph["nodes"]}: raise ValueError("Unknown evaluation output.")
    return _evaluate(graph, ctx, output)


def query_scene(evaluation, path="/", set_query=None):
    validate_path(path)
    locations = {item["path"]: item for item in evaluation["locations"]}
    if path != "/" and path not in locations: raise ValueError("Scene path does not exist.")
    result = {"path": path, "children": sorted(item["path"] for item in locations.values() if item["parent"] == path),
              "location": copy.deepcopy(locations.get(path)), "sets": sorted(name for name, paths in evaluation["sets"].items() if path in paths)}
    if set_query is not None: result["matches"] = sorted(set_expression(set_query, evaluation["sets"]))
    return result


def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _vector(matrix, vector): return [sum(matrix[c * 4 + r] * vector[c] for c in range(3)) for r in range(3)]
def _unit(vector):
    length = math.hypot(*vector)
    if length < 1e-12: raise ValueError("A scene transform collapsed a direction.")
    return [x / length for x in vector]


def _decompose(matrix):
    axes = [[matrix[c * 4 + r] for r in range(3)] for c in range(3)]
    scales = [math.hypot(*axis) for axis in axes]
    if min(scales) < .01 or max(scales) > 100: return None
    axes = [[v / scales[i] for v in axis] for i, axis in enumerate(axes)]
    if any(abs(_dot(axes[a], axes[b])) > 1e-8 for a, b in ((0, 1), (0, 2), (1, 2))): return None
    y = math.asin(max(-1., min(1., -axes[0][2])))
    if abs(math.cos(y)) > 1e-8:
        x, z = math.atan2(axes[1][2], axes[2][2]), math.atan2(axes[0][1], axes[0][0])
    else: x, z = math.atan2(-axes[2][1], axes[1][1]), 0.
    pose = {"position": list(matrix[12:15]), "rotation": [math.degrees(v) for v in (x, y, z)], "scale": scales}
    rebuilt = local_matrix(pose)
    return pose if max(abs(a - b) for a, b in zip(rebuilt, matrix)) < 1e-6 else None


def _normal(matrix, normal):
    a, b, c = [[matrix[col * 4 + row] for row in range(3)] for col in range(3)]
    cross = lambda u, v: [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    cofactors = [cross(b, c), cross(c, a), cross(a, b)]
    determinant = _dot(a, cofactors[0])
    if determinant <= 1e-12: raise ValueError("Graph transforms must retain a positive nonsingular orientation.")
    return _unit([sum(cofactors[col][row] * normal[col] for col in range(3)) / determinant for row in range(3)])


def _bake_mesh(obj, matrix):
    if obj["type"] == "mesh": mesh = copy.deepcopy(obj["mesh"])
    else:
        vertices, faces = primitive_cage(obj["type"])
        mesh = {"version": 1, "vertices": vertices, "triangles": [[face[0], face[index], face[index + 1]] for face in faces for index in range(1, len(face) - 1)]}
    mesh.pop("sha256", None)
    mesh["vertices"] = [transform_point(matrix, point) for point in mesh["vertices"]]
    if mesh.get("normals"): mesh["normals"] = [_normal(matrix, value) for value in mesh["normals"]]
    return validate_mesh(mesh)


def _uniform(matrix):
    pose = _decompose(matrix)
    if pose is None or max(pose["scale"]) - min(pose["scale"]) > 1e-7:
        raise ValueError("Camera and light ancestors require rigid or uniform-scale transforms; nonuniform optics are not silently approximated.")
    return pose["scale"][0]


def compile_evaluation(evaluation):
    spec = copy.deepcopy(evaluation["globals"]); spec["frame_end"] = 1; spec["objects"] = []; spec["lights"] = []
    baked, object_paths = [], {}
    for location in evaluation["locations"]:
        if location["inherited_attributes"].get("visibility", True) is False: continue
        kind, matrix, path = location["kind"], location["world_transform"], location["path"]
        identity = "p_" + hashlib.sha256(path.encode()).hexdigest()[:24]
        if kind == "object":
            obj = copy.deepcopy(location["object"]); obj["id"] = identity
            obj.pop("parent_id", None); obj.pop("keyframes", None); obj.pop("modeling", None)
            pose = _decompose(matrix)
            if pose is None:
                obj["mesh"] = _bake_mesh(obj, matrix); obj["type"] = "mesh"
                pose = {"position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
                baked.append({"path": path, "source_type": location["object"]["type"], "mesh_sha256": obj["mesh"]["sha256"],
                              "primitive_tessellation": "sphere:32x16,cylinder:32" if location["object"]["type"] != "mesh" else None})
            obj.update(pose); spec["objects"].append(obj); object_paths[identity] = path
        elif kind == "light":
            light = copy.deepcopy(location["light"]); scale = _uniform(matrix)
            light["id"] = identity; light["position"] = transform_point(matrix, light["position"])
            light["target"] = transform_point(matrix, light["target"]); light["size"] *= scale
            spec["lights"].append(light)
        elif kind == "camera" and path == evaluation["active_camera"]:
            camera = copy.deepcopy(location["camera"]); scale = _uniform(matrix)
            camera["position"] = transform_point(matrix, camera["position"]); camera["target"] = transform_point(matrix, camera["target"])
            right = _unit(_vector(matrix, location["camera_basis"]["right"]))
            basis = camera_basis(camera["position"], camera["target"])
            camera["roll"] = math.degrees(math.atan2(_dot(right, basis["up"]), _dot(right, basis["right"])))
            camera["orientation_mode"] = "world_up"; camera["focus_distance"] *= scale
            spec["camera"] = camera
    if "camera" not in spec: raise ValueError("The active camera was removed or made invisible.")
    spec = validate_scene(spec)
    return {"scene": spec, "scene_sha256": digest(spec), "object_paths": object_paths,
            "baked_transforms": baked, "graph_sha256": evaluation["graph_sha256"], "context_sha256": evaluation["context_sha256"]}


def compile_scene_graph(graph, context=None):
    evaluation = evaluate_scene_graph(graph, context)
    return {**compile_evaluation(evaluation), "evaluation": evaluation}


def scene_processing_capabilities():
    blender = find_blender()
    return {"available": bool(blender and shutil.which("ffmpeg")), "graph_available": True,
            "renderer": "Blender Cycles", "blender": str(blender) if blender else None,
            "default_graph": default_scene_graph(), "operations": ["evaluate", "render", "dispatch"],
            "limits": {"nodes": MAX_NODES, "assets": MAX_ASSETS, "locations": MAX_LOCATIONS, "depth": MAX_DEPTH,
                       "dispatch_tasks": MAX_TASKS, "graph_bytes": MAX_GRAPH_BYTES, "evaluation_bytes": MAX_EVALUATION_BYTES},
            "scope": "Data-only scene paths, sets, typed contexts and variants; fixed-operation paired TLS rendering. No Gaffer/Python/plugin or USD/Alembic interchange.",
            "issuance_effect": "NONE"}


def validate_scene_processing_recipe(recipe, project=None):
    recipe = _mapping(recipe, {"operation", "graph", "context"}, "Scene-processing recipe")
    operation = recipe.get("operation", "evaluate")
    if not isinstance(operation, str) or operation not in {"evaluate", "render"}: raise ValueError("Use evaluate or render here; distributed batches use the private dispatcher API.")
    graph = validate_scene_graph(recipe.get("graph", (project or {}).get("scene_processing")))
    context = validate_context(recipe.get("context", {}), graph["context"])
    evaluation = _evaluate(graph, context, graph["output"])
    compiled = compile_evaluation(evaluation)
    if project is not None and (compiled["scene"]["width"], compiled["scene"]["height"]) != (project.get("width"), project.get("height")):
        raise ValueError("Scene graph output resolution differs from the project.")
    return {"operation": operation, "graph": graph, "context": {k: v for k, v in context.items() if k != "time"}}


def _hash_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def _write_json(path, value):
    with Path(path).open("xb") as stream:
        stream.write(canonical_bytes(value)); stream.flush(); os.fsync(stream.fileno())


def _publish_directory(staging, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink(): raise ValueError("Scene-processing outputs are immutable; choose a new owned output directory.")
    os.rename(staging, output)
    fd = os.open(output.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _artifact_inventory(directory):
    result = []
    for path in sorted(Path(directory).iterdir()):
        if path.name not in ARTIFACT_NAMES or path.name == "receipt.json" or not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("Unexpected or nonregular scene-processing output.")
        if path.stat().st_size > MAX_ARTIFACT_BYTES: raise ValueError("Scene-processing artifact exceeds 8 GiB.")
        result.append({"filename": path.name, "size": path.stat().st_size, "sha256": _hash_file(path)})
    return result


def run_scene_processing(project, project_dir, recipe, output_dir, progress=None, cancel_event=None):
    """Publish immutable evaluation/render artifacts. No project mutation occurs."""
    recipe = validate_scene_processing_recipe(recipe, project)
    output = Path(output_dir).absolute(); parent = output.parent
    if any(path.is_symlink() for path in (parent, *parent.parents)): raise ValueError("Scene-processing output parents cannot be symlinks.")
    parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink(): raise ValueError("Scene-processing output already exists.")
    progress = progress or (lambda value: None)
    _cancelled(cancel_event); progress(.03)
    compiled = compile_scene_graph(recipe["graph"], recipe["context"])
    with tempfile.TemporaryDirectory(prefix=".scene-processing-", dir=parent) as temporary:
        staged = Path(temporary) / "published"; staged.mkdir()
        _write_json(staged / "graph.json", recipe["graph"])
        _write_json(staged / "evaluation.json", compiled["evaluation"])
        _write_json(staged / "scene.json", compiled["scene"])
        renderer = None
        if recipe["operation"] == "render":
            rendered = render_scene(compiled["scene"], Path(temporary) / "render", fps=compiled["evaluation"]["context"]["fps"],
                                    frame_start=1, frame_end=1, progress=lambda p: progress(.1 + .8 * p), cancel_event=cancel_event)
            for key, name in (("path", "preview.mp4"), ("scene_path", "authored.blend"), ("masters_path", "linear-masters.zip")):
                if key in rendered: shutil.move(rendered[key], staged / name)
            renderer = rendered["provenance"]
        _cancelled(cancel_event)
        receipt = {"format": "CINEMATICUM_SCENE_PROCESSING", "version": VERSION, "operation": recipe["operation"],
                   "graph_sha256": compiled["graph_sha256"], "context_sha256": compiled["context_sha256"],
                   "scene_sha256": compiled["scene_sha256"], "context": compiled["evaluation"]["context"],
                   "location_count": len(compiled["evaluation"]["locations"]), "object_paths": compiled["object_paths"],
                   "baked_transforms": compiled["baked_transforms"], "renderer": renderer,
                   "artifacts": _artifact_inventory(staged), "issuance_effect": "NONE"}
        _write_json(staged / "receipt.json", receipt)
        _cancelled(cancel_event); _publish_directory(staged, output)
    progress(1)
    return {"operation": recipe["operation"], "receipt": receipt, "path": str(output / "preview.mp4") if renderer else None,
            "scene": compiled["scene"], "evaluation": compiled["evaluation"], "issuance_effect": "NONE"}

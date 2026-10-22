"""Owned, cancellable OpenEXR graph jobs; optional libraries stay in a worker.

This graph processes still EXR parts and actual deep sample arrays. It does not
change the timeline movie compositor, infer a color space, or run project code.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from imaging import (_hash_file, _identity, _json_bytes, _number, _owned,
                     _read_json, _stop_process, _text, _worker_env,
                     find_imaging_python)

RUNTIME_REQUIREMENTS = {"numpy": "2.3.5", "OpenEXR": "3.4.15"}
ARTIFACT_NAMES = {"composite.exr", "preview.png", "receipt.json"}
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SOURCES = 128
MAX_NODES = 48
MAX_PARTS = 16
MAX_CHANNELS = 64
MAX_PIXELS = 1_048_576
MAX_CHANNEL_PIXELS = 4_194_304
MAX_SAMPLES = 2_097_152
MAX_SAMPLE_VALUES = 16_777_216
MAX_SAMPLES_PER_PIXEL = 2048
MAX_SECONDS = 300
SEMANTICS = {
    "merge": "Depth-sort and concatenate actual samples; overlapping samples and auxiliary identities are retained.",
    "over": "Depth-aware optical-density composition: split volume intervals at every boundary, combine coincident absorption/emission, then retain tidy deep samples. Equal-depth points use the same symmetric mixture rule.",
    "holdout": "Opaque depth holdout: discard subject samples at/behind the nearest opaque matte, splitting crossing volumes by Beer-Lambert attenuation. Fractional matte alpha is rejected.",
    "flatten": "Tidy overlapping samples, then front-to-back associated-alpha over. Z/ZBack select the first/last retained sample boundaries; empty pixels use zero depth.",
    "auxiliary": "Arbitrary numeric auxiliary channels are never treated as color. front explicitly selects the earliest original sample (input order breaks ties); error rejects any ambiguous mixture/flatten. UINT IDs retain exact values.",
    "color": "Color channels must already contain premultiplied linear-light values in a mutually compatible space. No OCIO conversion is inferred. Per-layer and AR/AG/AB alpha association follows OpenEXR conventions.",
    "preview": "The separately flattened preview is an explicitly selected RGB channel triplet, exposure and display transfer, clipped to SDR PNG. The EXR retains float values and actual deep/multipart data.",
    "bounds": "Still images, full-resolution numeric channels, scanline or single-level tiled parts. No sequences, subpixel coverage masks, scattering, arbitrary plugin code, mip/rip maps, or transparent holdouts.",
}


def channel_name(value):
    value = _text(value, "EXR channel", 255)
    if len(value.encode("utf-8")) > 255 or any(not part for part in value.split(".")):
        raise ValueError("EXR channel names need nonempty components and at most 255 UTF-8 bytes.")
    return value


def _node_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("Graph node identifiers must start with a letter and contain at most 64 letters, digits, underscores or hyphens.")
    return value


def _integer(value, label, lo, hi):
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValueError(f"{label} must be an integer in {lo}–{hi}.")
    return value


def _properties(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"{label} contains unsupported properties.")


def validate_deep_recipe(value):
    _properties(value, {"version", "nodes", "outputs", "preview"}, "Deep graph")
    if value.get("version") != 1 or isinstance(value.get("version"), bool):
        raise ValueError("Deep graph version must be 1.")
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError(f"A deep graph needs 1–{MAX_NODES} nodes.")
    normalized, ids = [], set()
    schemas = {"source": {"source_id", "part"}, "merge": {"inputs", "auxiliary"},
               "over": {"inputs", "auxiliary"}, "holdout": {"inputs", "auxiliary"},
               "flatten": {"input", "auxiliary"},
               "channels": {"input", "rename", "remove", "scale", "create"}}
    for original in nodes:
        if not isinstance(original, dict) or not isinstance(original.get("op"), str) or original["op"] not in schemas:
            raise ValueError("The graph contains an unsupported node operation.")
        op = original["op"]
        _properties(original, {"id", "op"} | schemas[op], "Deep node")
        ident = _node_id(original.get("id"))
        if ident in ids:
            raise ValueError("Graph node identifiers must be unique.")
        ids.add(ident)
        node = {"id": ident, "op": op}
        if op == "source":
            node.update(source_id=_identity(original.get("source_id"), "EXR source identity", True),
                        part=_integer(original.get("part", 0), "Source part", 0, MAX_PARTS - 1))
        elif op in {"merge", "over", "holdout"}:
            inputs = original.get("inputs")
            if not isinstance(inputs, list) or len(inputs) != 2:
                raise ValueError("A binary deep node requires exactly two input node identifiers.")
            node["inputs"] = [_node_id(item) for item in inputs]
        else:
            node["input"] = _node_id(original.get("input"))
        if op in {"merge", "over", "holdout", "flatten"}:
            auxiliary = original.get("auxiliary", "error")
            if auxiliary not in ("front", "error"):
                raise ValueError("Choose explicit front auxiliary selection or error on ambiguity.")
            node["auxiliary"] = auxiliary
        if op == "channels":
            rename, remove, scale, create = (original.get(k, {} if k != "remove" else []) for k in ("rename", "remove", "scale", "create"))
            if not isinstance(rename, dict) or len(rename) > MAX_CHANNELS:
                raise ValueError("Channel rename needs a bounded name mapping.")
            node["rename"] = {channel_name(k): channel_name(v) for k, v in rename.items()}
            if len(set(node["rename"].values())) != len(rename):
                raise ValueError("Channel renames cannot collide.")
            if not isinstance(remove, list) or len(remove) > MAX_CHANNELS:
                raise ValueError("Channel removal needs a bounded name list.")
            node["remove"] = [channel_name(k) for k in remove]
            if len(set(remove)) != len(remove) or set(remove) & set(rename):
                raise ValueError("Removed channels must be distinct and cannot also be renamed.")
            if not isinstance(scale, dict) or len(scale) > MAX_CHANNELS or not isinstance(create, dict) or len(create) > MAX_CHANNELS:
                raise ValueError("Channel operations exceed the channel bound.")
            node["scale"], node["create"] = {}, {}
            for name, parameters in scale.items():
                _properties(parameters, {"multiply", "add"}, "Channel scale")
                node["scale"][channel_name(name)] = {
                    "multiply": _number(parameters.get("multiply", 1), "Channel multiplier", -1e8, 1e8),
                    "add": _number(parameters.get("add", 0), "Channel offset", -1e12, 1e12)}
            for name, parameters in create.items():
                _properties(parameters, {"type", "value"}, "Channel creation")
                kind = parameters.get("type", "float")
                if kind not in ("half", "float", "uint"):
                    raise ValueError("EXR channels use half, float or uint samples.")
                val = parameters.get("value", 0)
                if kind == "uint":
                    val = _integer(val, "UINT channel value", 0, 2**32 - 1)
                else:
                    val = _number(val, "Channel value", -65504 if kind == "half" else -1e20,
                                  65504 if kind == "half" else 1e20)
                node["create"][channel_name(name)] = {"type": kind, "value": val}
        normalized.append(node)
    outputs = value.get("outputs")
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= MAX_PARTS:
        raise ValueError("Export 1–16 distinct graph output nodes.")
    outputs = [_node_id(v) for v in outputs]
    if len(set(outputs)) != len(outputs):
        raise ValueError("Export distinct graph output nodes.")
    by_id = {node["id"]: node for node in normalized}
    visited, visiting = set(), set()

    def visit(ident):
        if ident not in by_id:
            raise ValueError("A graph input/output references a missing node.")
        if ident in visiting:
            raise ValueError("Deep processing graphs must be acyclic.")
        if ident in visited:
            return
        visiting.add(ident)
        node = by_id[ident]
        for child in node.get("inputs", [node["input"]] if "input" in node else []):
            visit(child)
        visiting.remove(ident)
        visited.add(ident)
    for ident in outputs:
        visit(ident)
    if visited != ids:
        raise ValueError("Every graph node must contribute to an exported output.")
    preview = value.get("preview", {})
    _properties(preview, {"output", "channels", "alpha", "exposure", "transfer", "auxiliary"}, "EXR preview")
    channels = preview.get("channels", ["R", "G", "B"])
    if not isinstance(channels, list) or len(channels) != 3:
        raise ValueError("The preview needs three explicit channel names.")
    alpha = preview.get("alpha", "A")
    if alpha is not None:
        alpha = channel_name(alpha)
    transfer = preview.get("transfer", "linear_to_srgb")
    if transfer not in ("linear_to_srgb", "identity"):
        raise ValueError("Choose linear_to_srgb or identity for the SDR preview.")
    auxiliary = preview.get("auxiliary", "error")
    if auxiliary not in ("front", "error"):
        raise ValueError("Choose the preview's explicit auxiliary policy.")
    return {"version": 1, "nodes": normalized, "outputs": outputs,
            "preview": {"output": _integer(preview.get("output", 0), "Preview output", 0, len(outputs) - 1),
                        "channels": [channel_name(c) for c in channels], "alpha": alpha,
                        "exposure": _number(preview.get("exposure", 0), "Preview exposure", -16, 16),
                        "transfer": transfer, "auxiliary": auxiliary}}


def validate_project_deep(value):
    return None if value is None else validate_deep_recipe(value)


def _command(python=None):
    executable = find_imaging_python(python)
    if not executable:
        raise ValueError("The isolated CINEMATICUM Imaging runtime is not installed.")
    return [executable, "-I", "-B", str(Path(__file__).with_name("deep_compositing_worker.py"))]


def _short(request, python=None, timeout=45):
    try:
        result = subprocess.run(_command(python), input=_json_bytes(request), capture_output=True,
                                env=_worker_env(), timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("The deep EXR worker exceeded its admission time limit.") from exc
    if len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError("The EXR worker response exceeds its bound.")
    try:
        message = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("The deep EXR worker did not return valid JSON.") from exc
    if not isinstance(message, dict) or result.returncode or message.get("error"):
        raise ValueError(message.get("error", "The deep EXR worker failed.") if isinstance(message, dict) else "Invalid worker result.")
    return message


def deep_capabilities(python=None):
    base = {"available": False, "operations": [], "requirements": RUNTIME_REQUIREMENTS.copy(),
            "limits": {"source_bytes": MAX_SOURCE_BYTES, "sources": MAX_SOURCES, "nodes": MAX_NODES,
                       "parts": MAX_PARTS, "channels_per_part": MAX_CHANNELS, "pixels_per_part": MAX_PIXELS,
                       "channel_pixels_per_file": MAX_CHANNEL_PIXELS, "samples_per_file": MAX_SAMPLES,
                       "sample_values_per_file": MAX_SAMPLE_VALUES, "samples_per_pixel": MAX_SAMPLES_PER_PIXEL,
                       "job_seconds": MAX_SECONDS}, "semantics": SEMANTICS.copy()}
    try:
        return {**base, **_short({"command": "doctor"}, python, 15)}
    except (ValueError, OSError) as exc:
        return {**base, "reason": str(exc)}


def _source(project_dir, ident, verify=True):
    ident = _identity(ident, "EXR source identity", True)
    root = Path(project_dir).absolute()
    descriptor = _read_json(_owned(root, f"deep/sources/{ident}.json"), 2 * 1024 * 1024)
    if (not isinstance(descriptor, dict) or descriptor.get("id") != ident or descriptor.get("sha256") != ident
            or descriptor.get("path") != f"deep/sources/{ident}.exr" or not isinstance(descriptor.get("parts"), list)
            or not 1 <= len(descriptor["parts"]) <= MAX_PARTS):
        raise ValueError("The EXR source descriptor is invalid.")
    _text(descriptor.get("name"), "EXR source name", 240)
    _integer(descriptor.get("size"), "EXR source size", 1, MAX_SOURCE_BYTES)
    if verify and _hash_file(_owned(root, descriptor["path"]), MAX_SOURCE_BYTES) != (ident, descriptor["size"]):
        raise ValueError("The deep EXR source no longer matches its admitted identity.")
    return descriptor


def list_deep_sources(project_dir):
    root = Path(project_dir).absolute()
    if not (root / "deep" / "sources").exists():
        return []
    directory = _owned(root, "deep/sources", is_dir=True)
    names = sorted(p.stem for p in directory.iterdir() if p.suffix == ".json" and re.fullmatch(r"[0-9a-f]{64}", p.stem))
    if len(names) > MAX_SOURCES:
        raise ValueError("The project exceeds its EXR source bound.")
    return [_source(root, ident, verify=False) for ident in names]


def import_deep_source(project_dir, incoming_path, original_name, python=None):
    root, incoming = Path(project_dir).absolute(), Path(incoming_path).absolute()
    try:
        relative = incoming.relative_to(root)
    except ValueError as exc:
        raise ValueError("EXR uploads must be staged inside their project.") from exc
    source = _owned(root, relative)
    name = _text(original_name, "EXR source name", 240)
    if Path(name).name != name or "/" in name or "\\" in name or Path(name).suffix.lower() != ".exr" or source.suffix.lower() != ".exr":
        raise ValueError("Choose a plain .exr filename.")
    digest, size = _hash_file(source, MAX_SOURCE_BYTES)
    directory = _owned(root, "deep/sources", is_dir=True, create=True)
    if (directory / f"{digest}.json").exists():
        return _source(root, digest)
    if len(list_deep_sources(root)) >= MAX_SOURCES:
        raise ValueError("The project has reached its EXR source limit.")
    temporary = []
    try:
        fd, staging_name = tempfile.mkstemp(prefix=".incoming-", suffix=".exr", dir=directory)
        staging = Path(staging_name)
        temporary.append(staging)
        with os.fdopen(fd, "wb") as out, os.fdopen(os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as inp:
            shutil.copyfileobj(inp, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if _hash_file(staging, MAX_SOURCE_BYTES) != (digest, size):
            raise ValueError("The EXR upload changed during admission.")
        metadata = _short({"command": "probe", "project_dir": str(root),
                           "input": {"path": str(staging.relative_to(root)), "sha256": digest, "size": size}}, python)
        descriptor = {"version": 1, "id": digest, "sha256": digest, "size": size, "name": name,
                      "path": f"deep/sources/{digest}.exr", **metadata}
        fd, receipt_name = tempfile.mkstemp(prefix=".descriptor-", suffix=".json", dir=directory)
        receipt = Path(receipt_name)
        temporary.append(receipt)
        with os.fdopen(fd, "wb") as out:
            out.write(_json_bytes(descriptor))
            out.flush()
            os.fsync(out.fileno())
        destination = directory / f"{digest}.exr"
        try:
            os.link(staging, destination)
        except FileExistsError:
            if _hash_file(destination, MAX_SOURCE_BYTES) != (digest, size):
                raise ValueError("An existing EXR source identity is corrupt.")
        try:
            os.link(receipt, directory / f"{digest}.json")
        except FileExistsError:
            pass
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return _source(root, digest)


def run_deep_compositing(project, project_dir, recipe, output_dir, progress=None, cancel_event=None, python=None):
    del project  # Source authority is the independently verified owned EXR inventory.
    recipe = validate_deep_recipe(recipe)
    root, output = Path(project_dir).absolute(), Path(output_dir).absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Deep output must stay inside its project.") from exc
    if len(relative.parts) != 3 or relative.parts[:2] != ("deep", "outputs"):
        raise ValueError("Use deep/outputs/<job_id> for deep output.")
    output_id = _identity(relative.name, "Deep output identity")
    parent = _owned(root, "deep/outputs", is_dir=True, create=True)
    if output.exists() or output.is_symlink():
        raise ValueError("A deep output identity cannot be overwritten.")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Deep compositing cancelled.")
    source_ids = sorted({node["source_id"] for node in recipe["nodes"] if node["op"] == "source"})
    inputs = [{k: item[k] for k in ("id", "path", "sha256", "size", "name")}
              for item in (_source(root, ident) for ident in source_ids)]
    with tempfile.TemporaryDirectory(prefix=".building-", dir=parent) as temporary:
        scratch = Path(temporary)
        request = {"command": "render", "project_dir": str(root), "output_dir": str(scratch),
                   "recipe": recipe, "inputs": inputs}
        process = None
        with (scratch / "worker-result.json").open("wb") as log, (scratch / "worker-error.log").open("wb") as error:
            try:
                process = subprocess.Popen(_command(python), stdin=subprocess.PIPE, stdout=log, stderr=error,
                                           env=_worker_env(), start_new_session=True)
                process.stdin.write(_json_bytes(request))
                process.stdin.close()
                started, last = time.monotonic(), -1
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RuntimeError("Deep compositing cancelled.")
                    if time.monotonic() - started > MAX_SECONDS:
                        raise RuntimeError("Deep compositing exceeded its five-minute limit.")
                    if progress:
                        try:
                            value = _read_json(scratch / "progress.json", 256).get("progress", 0)
                            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > last:
                                progress(min(.98, max(0, value)))
                                last = value
                        except (OSError, ValueError):
                            pass
                    cancel_event.wait(.1) if cancel_event is not None else time.sleep(.1)
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Deep compositing cancelled.")
            finally:
                if process is not None:
                    _stop_process(process)
        result = _read_json(scratch / "worker-result.json", 2 * 1024 * 1024)
        if process.returncode or not isinstance(result, dict) or result.get("error"):
            raise RuntimeError(result.get("error", "Deep compositing worker failed.") if isinstance(result, dict) else "Invalid worker response.")
        generated = scratch / "result"
        if generated.is_symlink() or not generated.is_dir() or {p.name for p in generated.iterdir()} != ARTIFACT_NAMES:
            raise RuntimeError("The deep worker did not produce exactly its required artifacts.")
        artifacts = {}
        for key, filename in (("exr", "composite.exr"), ("preview", "preview.png"), ("receipt", "receipt.json")):
            digest, size = _hash_file(generated / filename, MAX_SOURCE_BYTES)
            artifacts[key] = {"filename": filename, "sha256": digest, "size": size}
        receipt = _read_json(generated / "receipt.json", 2 * 1024 * 1024)
        if receipt.get("recipe") != recipe or receipt.get("inputs") != inputs:
            raise RuntimeError("The deep receipt does not match its frozen graph and source identities.")
        if any(receipt.get("artifacts", {}).get(key) != artifacts[key] for key in ("exr", "preview")):
            raise RuntimeError("The deep artifacts do not match their receipt.")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Deep compositing cancelled.")
        os.rename(generated, output)
    if progress:
        progress(1)
    return {"path": str(output / "preview.png"), "exr_path": str(output / "composite.exr"),
            "receipt_path": str(output / "receipt.json"), "output_id": output_id, "artifacts": artifacts,
            "receipt": receipt, "provenance": {"type": "cinematicum-deep-compositing", "version": 1,
                  "output_id": output_id, "receipt_sha256": artifacts["receipt"]["sha256"],
                  "exr_sha256": artifacts["exr"]["sha256"], "recipe": copy.deepcopy(recipe),
                  "display_encoding": "sRGB" if recipe["preview"]["transfer"] == "linear_to_srgb" else "unmanaged",
                  "delivery_boundary": "SDR preview only; actual EXR sample data are a separate artifact"}}


validate_recipe = validate_deep_recipe
capabilities = deep_capabilities
run = run_deep_compositing

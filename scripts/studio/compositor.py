"""Typed, render-backed per-clip node graphs for CINEMATICUM Studio.

A graph receives one trimmed, project-rate, fit-sized RGBA picture stream.
Its output is then processed by the clip's ordinary transforms, grade, effects,
and timeline placement. Edges are image streams; merge inputs are ordered as
background and foreground. There are no user-provided FFmpeg expressions,
filenames, commands, or executable nodes.
"""
from __future__ import annotations

from collections import Counter
import math
import re


MAX_NODES = 32
MAX_WORKING_PIXELS = 268_435_456
INPUT_COUNTS = {"source": 0, "grade": 1, "blur": 1, "sharpen": 1,
                "chroma_key": 1, "mask": 1, "merge": 2}
PARAMETERS = {
    "source": {},
    "grade": {"exposure": (0, -3, 3), "contrast": (1, 0, 3),
              "saturation": (1, 0, 3), "temperature": (0, -1, 1)},
    "blur": {"sigma": (2, 0, 30)},
    "sharpen": {"amount": (1, 0, 3)},
    "chroma_key": {"similarity": (.18, .01, 1), "blend": (.08, 0, 1)},
    "mask": {"x": (.5, 0, 1), "y": (.5, 0, 1), "width": (1, .01, 2),
             "height": (1, .01, 2), "feather": (0, 0, 1)},
    "merge": {"opacity": (1, 0, 1)},
}


def _number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Compositor {label} must be a finite number.")
    if not low <= value <= high:
        raise ValueError(f"Compositor {label} must be between {low} and {high}.")
    return float(value)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Compositor node IDs must contain 1–128 letters, numbers, underscores or hyphens.")
    return value


def _walk(nodes, starts):
    """Topologically order starts and their ancestors, rejecting cycles."""
    colors, ordered = {}, []

    def visit(ident):
        if colors.get(ident) == 1:
            raise ValueError("Compositor connections contain a cycle.")
        if colors.get(ident) == 2:
            return
        colors[ident] = 1
        for source in nodes[ident]["inputs"]:
            visit(source)
        colors[ident] = 2
        ordered.append(ident)

    for ident in starts:
        visit(ident)
    return ordered


def validate_graph(graph, width=None, height=None):
    """Normalize a bounded graph without modifying the caller's object.

    Unused nodes are retained for editing and validated, but only ancestors of
    the selected output are compiled. Mask x/y are normalized centers; width
    and height are relative to the incoming picture. Feather is a normalized
    inward falloff from the edge (0 gives a hard edge, 1 falls off to center).
    """
    if (not isinstance(graph, dict) or set(graph) - {"version", "nodes", "output"}
            or type(graph.get("version")) is not int or graph["version"] != 1):
        raise ValueError("Compositor requires version 1, nodes, and an output node ID.")
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= MAX_NODES:
        raise ValueError(f"Compositor must contain 1–{MAX_NODES} nodes.")
    normalized, by_id = [], {}
    for raw in raw_nodes:
        if not isinstance(raw, dict) or set(raw) - {"id", "type", "inputs", "params", "position"}:
            raise ValueError("Compositor nodes support id, type, inputs, params, and position only.")
        ident = _identifier(raw.get("id"))
        if ident in by_id:
            raise ValueError("Compositor node IDs must be unique.")
        kind = raw.get("type")
        if not isinstance(kind, str) or kind not in INPUT_COUNTS:
            raise ValueError("Unsupported compositor node type.")
        inputs = raw.get("inputs", [])
        if not isinstance(inputs, list) or len(inputs) != INPUT_COUNTS[kind]:
            raise ValueError(f"Compositor {kind} requires {INPUT_COUNTS[kind]} image input(s).")
        inputs = [_identifier(value) for value in inputs]
        params = raw.get("params", {})
        extra = {"color"} if kind == "chroma_key" else {"shape", "invert"} if kind == "mask" else set()
        if not isinstance(params, dict) or set(params) - set(PARAMETERS[kind]) - extra:
            raise ValueError(f"Unsupported parameter for compositor {kind}.")
        clean = {key: _number(params.get(key, default), f"{kind}.{key}", low, high)
                 for key, (default, low, high) in PARAMETERS[kind].items()}
        if kind == "chroma_key":
            color = params.get("color", "#00ff00")
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise ValueError("Compositor key color must be an RGB hex color.")
            clean["color"] = color.lower()
        if kind == "mask":
            shape, invert = params.get("shape", "rectangle"), params.get("invert", False)
            if not isinstance(shape, str) or shape not in {"rectangle", "ellipse"} or not isinstance(invert, bool):
                raise ValueError("Compositor masks require rectangle/ellipse shape and boolean invert.")
            clean.update(shape=shape, invert=invert)
        node = {"id": ident, "type": kind, "inputs": inputs, "params": clean}
        if "position" in raw:
            position = raw["position"]
            if not isinstance(position, dict) or set(position) != {"x", "y"}:
                raise ValueError("Compositor node position requires x and y.")
            node["position"] = {key: _number(position[key], "position." + key, -100000, 100000) for key in ("x", "y")}
        normalized.append(node)
        by_id[ident] = node
    if sum(node["type"] == "source" for node in normalized) != 1:
        raise ValueError("Compositor requires exactly one clip source node.")
    for node in normalized:
        if any(ident not in by_id for ident in node["inputs"]):
            raise ValueError("Compositor connection refers to a missing node.")
    output = _identifier(graph.get("output"))
    if output not in by_id:
        raise ValueError("Compositor output refers to a missing node.")
    _walk(by_id, by_id)  # Invalid disconnected nodes must not hide cycles.
    active = _walk(by_id, [output])
    if width is not None and height is not None and width * height * len(active) > MAX_WORKING_PIXELS:
        raise ValueError("Compositor exceeds its working-image budget. Reduce graph complexity or project resolution.")
    return {"version": 1, "nodes": normalized, "output": output}


def _decimal(value):
    return format(float(value), ".10g")


def _mask_expression(params):
    dx = f"abs(((X+0.5)/W-{_decimal(params['x'])})/{_decimal(params['width']/2)})"
    dy = f"abs(((Y+0.5)/H-{_decimal(params['y'])})/{_decimal(params['height']/2)})"
    distance = f"max({dx},{dy})" if params["shape"] == "rectangle" else f"sqrt(pow({dx},2)+pow({dy},2))"
    feather = params["feather"]
    mask = f"lte({distance},1)" if feather == 0 else f"clip((1-({distance}))/{_decimal(feather)},0,1)"
    return f"(1-({mask}))" if params["invert"] else mask


def compile_graph(graph, input_label, prefix):
    """Return filter clauses and a single-use output label for a normalized graph.

    Explicit split nodes are emitted wherever an image feeds multiple ports,
    including a merge wired twice to the same node. Only reachable nodes run.
    The engine supplies input_label and prefix; payload IDs never enter FFmpeg.
    """
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", prefix) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", input_label):
        raise ValueError("Invalid internal compositor stream label.")
    graph = validate_graph(graph)
    nodes = {node["id"]: node for node in graph["nodes"]}
    order = _walk(nodes, [graph["output"]])
    uses = Counter(source for ident in order for source in nodes[ident]["inputs"])
    uses[graph["output"]] += 1
    filters, available = [], {}

    def preserve_alpha(source, target, chain):
        # Several FFmpeg color filters negotiate RGB/YUV formats without alpha.
        # Carry the original matte independently and rejoin it explicitly.
        rgb, matte, alpha, color = target + "rgb", target + "matte", target + "alpha", target + "color"
        filters.append(f"[{source}]split=2[{rgb}][{matte}]")
        filters.append(f"[{matte}]alphaextract[{alpha}]")
        filters.append(f"[{rgb}]" + ",".join(chain + ["format=rgb24"]) + f"[{color}]")
        filters.append(f"[{color}][{alpha}]alphamerge,format=rgba[{target}]")

    for index, ident in enumerate(order):
        node = nodes[ident]
        kind, params = node["type"], node["params"]
        incoming = [available[source].pop(0) for source in node["inputs"]]
        output = prefix + "n" + str(index)
        if kind == "source":
            output = input_label
        elif kind == "grade":
            chain = []
            if params["exposure"]:
                chain.append("exposure=exposure=" + _decimal(params["exposure"]))
            if params["contrast"] != 1 or params["saturation"] != 1:
                chain.append(f"eq=contrast={_decimal(params['contrast'])}:saturation={_decimal(params['saturation'])}")
            if params["temperature"]:
                warm = params["temperature"] * .12
                chain.append(f"colorbalance=rs={_decimal(warm)}:rm={_decimal(warm)}:rh={_decimal(warm)}:"
                             f"bs={_decimal(-warm)}:bm={_decimal(-warm)}:bh={_decimal(-warm)}")
            if chain:
                preserve_alpha(incoming[0], output, chain)
            else:
                filters.append(f"[{incoming[0]}]null[{output}]")
        elif kind in {"blur", "sharpen"}:
            amount = params["sigma" if kind == "blur" else "amount"]
            if amount:
                chain = [f"gblur=sigma={_decimal(amount)}"] if kind == "blur" else [f"unsharp=5:5:{_decimal(amount)}:5:5:0"]
                preserve_alpha(incoming[0], output, chain)
            else:
                filters.append(f"[{incoming[0]}]null[{output}]")
        elif kind == "chroma_key":
            rgb, original, keyed = output + "rgb", output + "original", output + "keyed"
            alpha, key_alpha, matte = output + "alpha", output + "keyalpha", output + "matte"
            filters.append(f"[{incoming[0]}]split=3[{rgb}][{original}][{keyed}]")
            filters.append(f"[{original}]alphaextract[{alpha}]")
            filters.append(f"[{keyed}]format=rgba,colorkey=0x{params['color'][1:]}:"
                           f"{_decimal(params['similarity'])}:{_decimal(params['blend'])},alphaextract[{key_alpha}]")
            filters.append(f"[{alpha}][{key_alpha}]blend=all_mode=multiply[{matte}]")
            filters.append(f"[{rgb}][{matte}]alphamerge,format=rgba[{output}]")
        elif kind == "mask":
            expression = _mask_expression(params)
            filters.append(f"[{incoming[0]}]geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                           f"a='alpha(X,Y)*({expression})',format=rgba[{output}]")
        elif kind == "merge":
            foreground = output + "foreground"
            filters.append(f"[{incoming[1]}]colorchannelmixer=aa={_decimal(params['opacity'])}[{foreground}]")
            filters.append(f"[{incoming[0]}][{foreground}]overlay=x=0:y=0:eof_action=endall:"
                           f"shortest=1:repeatlast=0:format=auto:alpha=straight,format=rgba[{output}]")
        count = uses[ident]
        if count > 1:
            labels = [prefix + "n" + str(index) + "use" + str(port) for port in range(count)]
            filters.append(f"[{output}]split={count}" + "".join(f"[{label}]" for label in labels))
            available[ident] = labels
        else:
            available[ident] = [output]
    return filters, available[graph["output"]].pop(0)

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
MAX_CURVE_POINTS = 12
MAX_POLYGON_POINTS = 24
CURVE_CHANNELS = ("master", "red", "green", "blue")
BLEND_MODES = {"normal", "multiply", "screen", "add", "difference"}
DEFAULT_POLYGON = [[.1, .85], [.5, .1], [.9, .85]]
INPUT_COUNTS = {"source": 0, "grade": 1, "curves": 1, "blur": 1, "sharpen": 1,
                "chroma_key": 1, "mask": 1, "merge": 2}
PARAMETERS = {
    "source": {},
    "curves": {},
    "grade": {"exposure": (0, -3, 3), "contrast": (1, 0, 3),
              "saturation": (1, 0, 3), "temperature": (0, -1, 1)},
    "blur": {"sigma": (2, 0, 30)},
    "sharpen": {"amount": (1, 0, 3)},
    "chroma_key": {"similarity": (.18, .01, 1), "blend": (.08, 0, 1)},
    "mask": {"x": (.5, 0, 1), "y": (.5, 0, 1), "width": (1, .01, 2),
             "height": (1, .01, 2), "feather": (0, 0, 1), "rotation": (0, -360, 360)},
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


def _points(value, label, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"Compositor {label} requires {minimum}–{maximum} points.")
    result = []
    for point in value:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f"Compositor {label} points require x and y coordinates.")
        result.append([_number(point[0], label + ".x", 0, 1),
                       _number(point[1], label + ".y", 0, 1)])
    return result


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
        extra = ({"color"} if kind == "chroma_key" else {"shape", "invert", "points"} if kind == "mask"
                 else {"mode"} if kind == "merge" else set(CURVE_CHANNELS) if kind == "curves" else set())
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
            if not isinstance(shape, str) or shape not in {"rectangle", "ellipse", "polygon"} or not isinstance(invert, bool):
                raise ValueError("Compositor masks require rectangle/ellipse/polygon shape and boolean invert.")
            points = _points(params.get("points", DEFAULT_POLYGON), "mask polygon", 3, MAX_POLYGON_POINTS)
            for first, second in zip(points, points[1:] + points[:1]):
                if math.hypot(first[0] - second[0], first[1] - second[1]) < .00001:
                    raise ValueError("Compositor polygon vertices must not overlap their neighbors.")
            clean.update(shape=shape, invert=invert, points=points)
        if kind == "curves":
            for channel in CURVE_CHANNELS:
                points = _points(params.get(channel, [[0, 0], [1, 1]]), "curves." + channel, 2, MAX_CURVE_POINTS)
                if points[0][0] != 0 or points[-1][0] != 1:
                    raise ValueError("Compositor curves must start at input 0 and end at input 1.")
                if any(right[0] - left[0] < 1 / 255 - 1e-9 for left, right in zip(points, points[1:])):
                    raise ValueError("Compositor curve inputs must increase by at least 1/255.")
                clean[channel] = points
        if kind == "merge":
            mode = params.get("mode", "normal")
            if not isinstance(mode, str) or mode not in BLEND_MODES:
                raise ValueError("Compositor blend mode must be normal, multiply, screen, add, or difference.")
            clean["mode"] = mode
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
    working_images = sum(5 if by_id[key]["type"] == "merge" and by_id[key]["params"]["mode"] != "normal"
                         else 2 if by_id[key]["type"] == "curves" else 1 for key in active)
    if width is not None and height is not None and width * height * working_images > MAX_WORKING_PIXELS:
        raise ValueError("Compositor exceeds its working-image budget. Reduce graph complexity or project resolution.")
    return {"version": 1, "nodes": normalized, "output": output}


def _decimal(value):
    return format(float(value), ".10g")


def _mask_alpha_expression(params):
    # Rotate in pixel space so a degree is a degree on non-square images, then
    # map into the mask's normalized local coordinate system. Positive angles
    # turn clockwise in the picture's downwards Y coordinate system.
    angle = math.radians(params["rotation"])
    cosine, sine = _decimal(math.cos(angle)), _decimal(math.sin(angle))
    px, py = f"(X+0.5-W*{_decimal(params['x'])})", f"(Y+0.5-H*{_decimal(params['y'])})"
    u = f"(({cosine}*{px}+{sine}*{py})/(W*{_decimal(params['width'])})+0.5)"
    v = f"((-{sine}*{px}+{cosine}*{py})/(H*{_decimal(params['height'])})+0.5)"
    setup = f"st(0,{u});st(1,{v});"
    feather = params["feather"]
    if params["shape"] == "polygon":
        points, crossings = params["points"], []
        distances = []
        for first, second in zip(points, points[1:] + points[:1]):
            x, y = first
            vx, vy = second[0] - x, second[1] - y
            if abs(vy) > 1e-12:
                crossings.append(f"not(eq(gt({_decimal(y)},ld(1)),gt({_decimal(second[1])},ld(1))))*"
                                 f"lt(ld(0),{_decimal(vx)}*(ld(1)-{_decimal(y)})/{_decimal(vy)}+{_decimal(x)})")
            if feather:
                t = (f"clip(((ld(0)-{_decimal(x)})*{_decimal(vx)}+(ld(1)-{_decimal(y)})*{_decimal(vy)})/"
                     f"{_decimal(vx * vx + vy * vy)},0,1)")
                distances.append(f"st(3,{t});st(4,min(ld(4),sqrt(pow(ld(0)-{_decimal(x)}-ld(3)*{_decimal(vx)},2)+"
                                 f"pow(ld(1)-{_decimal(y)}-ld(3)*{_decimal(vy)},2))));")
        setup += "st(2,mod(" + ("+".join(crossings) or "0") + ",2));"
        mask = "ld(2)"
        if feather:
            setup += "st(4,2);" + "".join(distances)
            mask += f"*clip(2*ld(4)/{_decimal(feather)},0,1)"
    else:
        dx, dy = "abs((ld(0)-0.5)*2)", "abs((ld(1)-0.5)*2)"
        distance = f"max({dx},{dy})" if params["shape"] == "rectangle" else f"sqrt(pow({dx},2)+pow({dy},2))"
        mask = f"lte({distance},1)" if feather == 0 else f"clip((1-({distance}))/{_decimal(feather)},0,1)"
    if params["invert"]:
        mask = f"1-({mask})"
    return setup + f"lum(X,Y)*({mask})"


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
        elif kind == "curves":
            # All coordinates are bounded numbers, never FFmpeg expressions.
            # PCHIP avoids spline overshoot between control points. FFmpeg
            # applies each channel curve first and the master curve afterward.
            options = [channel + "='" + " ".join(_decimal(x) + "/" + _decimal(y) for x, y in params[channel]) + "'"
                       for channel in CURVE_CHANNELS]
            preserve_alpha(incoming[0], output, ["curves=interp=pchip:" + ":".join(options)])
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
            expression = _mask_alpha_expression(params)
            color, matte, alpha = output + "color", output + "matte", output + "alpha"
            # Apply geometry only to an extracted grayscale matte. This avoids
            # RGB conversions and their unnecessary alpha quantization.
            filters.append(f"[{incoming[0]}]split=2[{color}][{matte}]")
            filters.append(f"[{matte}]alphaextract,geq=lum='{expression}'[{alpha}]")
            filters.append(f"[{color}][{alpha}]alphamerge,format=rgba[{output}]")
        elif kind == "merge":
            foreground = output + "foreground"
            background = incoming[0]
            if params["mode"] == "normal":
                filters.append(f"[{incoming[1]}]colorchannelmixer=aa={_decimal(params['opacity'])}[{foreground}]")
            else:
                # Alpha-aware separable blending, followed by source-over:
                # effective Cs = (1 - Ab) * Cs + Ab * blend(Cb, Cs).
                # The final overlay then preserves coverage As + Ab*(1-As),
                # including when either branch is only partially transparent.
                # Blending alpha as a color channel would be incorrect.
                names = {name: output + name for name in ("base", "bgcolor", "bgmatte", "fgcolor", "fgplain", "fgmatte",
                                                          "brgb", "frgb", "ba", "fa", "blended", "blendrgb", "blendrgba",
                                                          "opaque", "effective")}
                filters.append(f"[{incoming[0]}]split=3[{names['base']}][{names['bgcolor']}][{names['bgmatte']}]")
                filters.append(f"[{incoming[1]}]split=3[{names['fgcolor']}][{names['fgplain']}][{names['fgmatte']}]")
                filters.append(f"[{names['bgmatte']}]alphaextract[{names['ba']}]")
                filters.append(f"[{names['fgmatte']}]alphaextract,lut=y='val*{_decimal(params['opacity'])}'[{names['fa']}]")
                filters.append(f"[{names['bgcolor']}]format=gbrp[{names['brgb']}]")
                filters.append(f"[{names['fgcolor']}]format=gbrp[{names['frgb']}]")
                mode = "addition" if params["mode"] == "add" else params["mode"]
                filters.append(f"[{names['brgb']}][{names['frgb']}]blend=all_mode={mode}:shortest=1:repeatlast=0[{names['blended']}]")
                filters.append(f"[{names['blended']}]format=rgb24[{names['blendrgb']}]")
                filters.append(f"[{names['blendrgb']}][{names['ba']}]alphamerge,format=rgba[{names['blendrgba']}]")
                filters.append(f"[{names['fgplain']}]format=rgb24[{names['opaque']}]")
                filters.append(f"[{names['opaque']}][{names['blendrgba']}]overlay=x=0:y=0:eof_action=endall:"
                               f"shortest=1:repeatlast=0:format=rgb:alpha=straight,format=rgb24[{names['effective']}]")
                filters.append(f"[{names['effective']}][{names['fa']}]alphamerge,format=rgba[{foreground}]")
                background = names["base"]
            filters.append(f"[{background}][{foreground}]overlay=x=0:y=0:eof_action=endall:"
                           f"shortest=1:repeatlast=0:format=auto:alpha=straight,format=rgba[{output}]")
        count = uses[ident]
        if count > 1:
            labels = [prefix + "n" + str(index) + "use" + str(port) for port in range(count)]
            filters.append(f"[{output}]split={count}" + "".join(f"[{label}]" for label in labels))
            available[ident] = labels
        else:
            available[ident] = [output]
    return filters, available[graph["output"]].pop(0)

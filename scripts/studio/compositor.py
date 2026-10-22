"""Typed, render-backed per-clip node graphs for CINEMATICUM Studio.

A graph receives one trimmed, project-rate, fit-sized RGBA picture stream.
Additional project-media sources receive their own conformed RGBA streams;
this module selects their frame ranges without ever opening paths.
Its output is then processed by the clip's ordinary transforms, grade, effects,
and timeline placement. Edges are image streams; merge inputs are ordered as
background and foreground. There are no user-provided FFmpeg expressions,
filenames, commands, or executable nodes.
"""
from __future__ import annotations

from array import array
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import zlib


MAX_NODES = 32
MAX_MEDIA_SOURCES = 8
MAX_LENS_NODES = 2
MAX_LENS_PIXELS = 2_073_600
LENS_MAP_NAMES = ("x0", "x1", "y0", "y1", "wx", "wy")
LENS_CONTRACTION_LIMIT = .45
LENS_COEFFICIENTS = ("k1", "k2", "k3", "p1", "p2")
MAX_WORKING_PIXELS = 268_435_456
HIGH16_FORMAT = "gbrap16le"
# These are the actual high-depth kernels, not merely output encoder formats.
HIGH16_FILTERS = {"format", "geq", "blend", "mergeplanes", "split", "scale",
                  "pad", "crop", "tpad", "alphaextract", "premultiply",
                  "unpremultiply", "maskedmerge", "remap", "colorkey",
                  "gblur", "curves", "rotate", "fade", "lut1d", "lut3d"}
MAX_CURVE_POINTS = 12
MAX_POLYGON_POINTS = 24
MAX_BEZIER_POINTS = 32
MAX_ANIMATION_KEYS = 128
MAX_PATH_KEYS = 64
MAX_GRAPH_KEYS = 1024
MAX_ANIMATION_VALUES = 8192
MAX_ANIMATION_FRAME = 6 * 60 * 60 * 60
INTERPOLATIONS = {"linear", "constant", "ease_in", "ease_out", "ease_in_out", "cubic"}
CURVE_CHANNELS = ("master", "red", "green", "blue")
BLEND_MODES = {"normal", "multiply", "screen", "add", "difference"}
DEFAULT_POLYGON = [[.1, .85], [.5, .1], [.9, .85]]
# x/y anchor, incoming control x/y, outgoing control x/y, local feather scale.
# The four real cubic segments retain their handles; rendering never replaces
# the saved path with a polygon. Flattening is adaptive at the output resolution.
DEFAULT_BEZIER = [[.5, .1, .2790861, .1, .7209139, .1, 1],
                 [.9, .5, .9, .2790861, .9, .7209139, 1],
                 [.5, .9, .7209139, .9, .2790861, .9, 1],
                 [.1, .5, .1, .7209139, .1, .2790861, 1]]
MASKABLE = {"grade", "curves", "blur", "sharpen", "chroma_key", "lens_distortion"}
INPUT_COUNTS = {"source": 0, "media_source": 0, "grade": 1, "curves": 1, "blur": 1, "sharpen": 1,
                "chroma_key": 1, "mask": 1, "alpha_mask": 2, "merge": 2, "lens_distortion": 1}
PARAMETERS = {
    "source": {},
    "media_source": {},
    "alpha_mask": {},
    "lens_distortion": {"fx": (1, .1, 20), "fy": (1, .1, 20),
                        "cx": (.5, -2, 3), "cy": (.5, -2, 3),
                        "k1": (0, -1, 1), "k2": (0, -1, 1), "k3": (0, -1, 1),
                        "p1": (0, -.2, .2), "p2": (0, -.2, .2)},
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
ANIMATABLE = {kind: set(values) for kind, values in PARAMETERS.items()}
# unsharp does not expose a runtime amount command. Do not advertise a channel
# that the export engine cannot evaluate. RGB tone curves are static mappings.
ANIMATABLE["sharpen"] = set()
ANIMATABLE["lens_distortion"] = set()
ANIMATABLE["mask"].add("points")
ANIMATABLE["mask"].add("bezier")


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


def _frame(value, label, low, high):
    result = _number(value, label, low, high)
    if not result.is_integer():
        raise ValueError(f"Compositor {label} must be an integer frame.")
    return int(result)


def _polygon(value):
    result = _points(value, "mask polygon", 3, MAX_POLYGON_POINTS)
    if any(math.hypot(a[0] - b[0], a[1] - b[1]) < .00001
           for a, b in zip(result, result[1:] + result[:1])):
        raise ValueError("Compositor polygon vertices must not overlap their neighbors.")
    return result


def _bezier(value):
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_BEZIER_POINTS:
        raise ValueError(f"Compositor Bezier path needs 2–{MAX_BEZIER_POINTS} anchors.")
    result = []
    for anchor in value:
        if not isinstance(anchor, list) or len(anchor) != 7:
            raise ValueError("Bezier anchors require x/y, incoming and outgoing x/y handles, and feather scale.")
        result.append([_number(v, "Bezier coordinate", -2, 3) for v in anchor[:6]] +
                      [_number(anchor[6], "Bezier feather scale", 0, 4)])
    return result


def node_dependencies(node):
    """Image and optional mask edges participate equally in cycle/lifetime rules."""
    return node["inputs"] + ([node["mask_input"]] if node.get("mask_input") else [])


def lens_domain(params):
    """Full-canvas conservative contraction certificate for five-term Brown.

    Intrinsics are normalized by their image axis. The radial Jacobian's
    eigenvalue perturbations are bounded by 3|k1|R²+5|k2|R⁴+7|k3|R⁶;
    tangential terms add at most 8R(|p1|+|p2|) in spectral norm.
    q<1 makes the forward map strongly monotone on this convex rectangle and
    projected inverse iteration a contraction. No grid sampling is used to
    claim that unsampled image regions cannot fold.
    """
    x0,x1 = -params["cx"]/params["fx"], (1-params["cx"])/params["fx"]
    y0,y1 = -params["cy"]/params["fy"], (1-params["cy"])/params["fy"]
    radius = math.hypot(max(abs(x0),abs(x1)), max(abs(y0),abs(y1)))
    r2 = radius*radius
    q = (3*abs(params["k1"])*r2 + 5*abs(params["k2"])*r2*r2 +
         7*abs(params["k3"])*r2*r2*r2 + 8*radius*(abs(params["p1"])+abs(params["p2"])))
    if q > LENS_CONTRACTION_LIMIT + 1e-12:
        raise ValueError("Calibrated lens coefficients exceed the full-image invertibility limit for these intrinsics. "
                         "Use a milder calibration or a narrower field; folding/fisheye models are not supported.")
    # Successive iterates are at most 2R apart. q^n convergence and a 1e-10
    # normalized-coordinate threshold bound residual pixel error independently
    # of arbitrary iteration success. Identity is emitted as an exact no-op.
    tolerance = 1e-10 * (1-q)
    iterations = 0 if q == 0 else max(1, math.ceil(math.log(tolerance/max(2*radius,1e-30))/math.log(q))+2)
    if iterations > 48:
        raise ValueError("Calibrated lens inverse exceeds its bounded iteration budget.")
    return {"x0":x0,"x1":x1,"y0":y0,"y1":y1,"q":q,"iterations":iterations,"tolerance":tolerance}


def lens_sample_point(params, x, y, width, height):
    """Reference backward sample (pixel centers at integer x/y), or None.

    Undistort samples the distorted input with the forward Brown mapping.
    Distort samples an ideal input through the certified inverse. Sampling
    coordinates beyond the actual input image have explicit zero coverage.
    """
    return _lens_sampler(params, width, height)(x, y)


def _lens_sampler(params, width, height):
    """Prepare a dependency-free reference sampler with one certificate."""
    domain = lens_domain(params)
    def delta(a,b):
        r2=a*a+b*b;radial=r2*(params["k1"]+r2*(params["k2"]+r2*params["k3"]))
        return (a*radial+2*params["p1"]*a*b+params["p2"]*(r2+2*a*a),
                b*radial+params["p1"]*(r2+2*b*b)+2*params["p2"]*a*b)
    def sample(x, y):
        xd,yd=(x/width-params["cx"])/params["fx"],(y/height-params["cy"])/params["fy"]
        if params["direction"]=="undistort":
            dx,dy=delta(xd,yd);a,b=xd+dx,yd+dy
        else:
            a,b=xd,yd
            for _ in range(domain["iterations"]):
                dx,dy=delta(a,b)
                aa=max(domain["x0"],min(xd-dx,domain["x1"]))
                bb=max(domain["y0"],min(yd-dy,domain["y1"]))
                distance=math.hypot(aa-a,bb-b);a,b=aa,bb
                if distance<=domain["tolerance"]:break
            dx,dy=delta(a,b)
            if math.hypot(a+dx-xd,b+dy-yd)>2e-9:
                # A projected fixed point with residual lies on the boundary
                # and represents a ray outside the mapped source rectangle.
                if domain["x0"]+1e-8<a<domain["x1"]-1e-8 and domain["y0"]+1e-8<b<domain["y1"]-1e-8:
                    raise ValueError("Calibrated lens inverse failed its certified residual check.")
                return None
        u,v=(a*params["fx"]+params["cx"])*width,(b*params["fy"]+params["cy"])*height
        if -1e-7<=u<=width-1+1e-7 and -1e-7<=v<=height-1+1e-7:
            return max(0,min(u,width-1)),max(0,min(v,height-1))
        return None
    return sample


def _animation(raw, kind, params, start, duration):
    if not isinstance(raw, dict) or set(raw) - ANIMATABLE[kind]:
        raise ValueError(f"Unsupported animation channel for compositor {kind}.")
    clean, key_count, value_count = {}, 0, 0
    for name, keys in raw.items():
        limit = MAX_PATH_KEYS if name in {"points", "bezier"} else MAX_ANIMATION_KEYS
        if not isinstance(keys, list) or not 1 <= len(keys) <= limit:
            raise ValueError(f"Compositor {name} animation requires 1–{limit} keys.")
        seen, channel = set(), []
        for key in keys:
            if not isinstance(key, dict) or set(key) - {"frame", "value", "interpolation", "in_tangent", "out_tangent"}:
                raise ValueError("Compositor animation keys support frame, value, interpolation and cubic tangents only.")
            frame = _frame(key.get("frame"), "keyframe", start, duration - 1)
            if frame in seen:
                raise ValueError("Compositor animation key times must be unique within each channel.")
            seen.add(frame)
            interpolation = key.get("interpolation", "linear")
            if not isinstance(interpolation, str) or interpolation not in INTERPOLATIONS:
                raise ValueError("Unsupported compositor keyframe interpolation.")
            if name in {"points", "bezier"}:
                value = (_polygon if name == "points" else _bezier)(key.get("value"))
                if len(value) != len(params[name]):
                    raise ValueError("Animated path keys must preserve their anchor count and order.")
                value_count += len(value) * (2 if name == "points" else 7)
            else:
                _, low, high = PARAMETERS[kind][name]
                value = _number(key.get("value"), f"{kind}.{name} key value", low, high)
                value_count += 1
            entry = {"frame": frame, "value": value, "interpolation": interpolation}
            for tangent in ("in_tangent", "out_tangent"):
                if tangent in key:
                    entry[tangent] = _number(key[tangent], tangent, 0, 3)
            channel.append(entry)
        key_count += len(channel)
        clean[name] = sorted(channel, key=lambda key: key["frame"])
    return clean, key_count, value_count


def _key_points(base, keys):
    points = {0: {"frame": 0, "value": base, "interpolation": "linear"}}
    points.update({key["frame"]: key for key in keys})
    return sorted(points.values(), key=lambda key: key["frame"])


def _interpolate_values(a, b, amount):
    if isinstance(a, list):
        return [_interpolate_values(left, right, amount) for left, right in zip(a, b)]
    return a + (b - a) * amount


def animation_value(base, keys, frame):
    """Evaluate a validated independent channel at an animation-domain frame.

    The static value is an implicit frame-zero key. An explicit key at zero
    overrides it. Interpolation belongs to the outgoing segment; endpoint
    values hold outside the entire domain. Polygon coordinates use identical
    easing and stable point correspondence.
    """
    points = _key_points(base, keys)
    if frame <= points[0]["frame"]:
        return _interpolate_values(points[0]["value"], points[0]["value"], 0)
    for left, right in zip(points, points[1:]):
        if frame < right["frame"]:
            t = (frame - left["frame"]) / (right["frame"] - left["frame"])
            mode = left.get("interpolation", "linear")
            amount = (0 if mode == "constant" else t * t if mode == "ease_in"
                      else 1 - (1 - t) ** 2 if mode == "ease_out"
                      else t * t * (3 - 2 * t) if mode == "ease_in_out"
                      else ((left.get("out_tangent", 0) + right.get("in_tangent", 0) - 2) * t ** 3
                            + (3 - 2 * left.get("out_tangent", 0) - right.get("in_tangent", 0)) * t ** 2
                            + left.get("out_tangent", 0) * t) if mode == "cubic" else t)
            return _interpolate_values(left["value"], right["value"], amount)
    return _interpolate_values(points[-1]["value"], points[-1]["value"], 0)


def node_params_at(node, frame):
    """Return evaluated parameter data without mutating the saved node."""
    return {name: animation_value(value, node.get("animation", {}).get(name, []), frame)
            if name in node.get("animation", {}) else value for name, value in node["params"].items()}


def _walk(nodes, starts):
    """Topologically order starts and their ancestors, rejecting cycles."""
    colors, ordered = {}, []

    def visit(ident):
        if colors.get(ident) == 1:
            raise ValueError("Compositor connections contain a cycle.")
        if colors.get(ident) == 2:
            return
        colors[ident] = 1
        for source in node_dependencies(nodes[ident]):
            visit(source)
        colors[ident] = 2
        ordered.append(ident)

    for ident in starts:
        visit(ident)
    return ordered


def validate_graph(graph, width=None, height=None, *, animation_duration=None, animation_start=0,
                   precision="standard8"):
    """Normalize a bounded graph without modifying the caller's object.

    Unused nodes are retained for editing and validated, but only ancestors of
    the selected output are compiled. Mask x/y are normalized centers; width
    and height are relative to the incoming picture. Feather is a normalized
    inward falloff from the edge (0 gives a hard edge, 1 falls off to center).
    """
    if not isinstance(precision, str) or precision not in {"standard8", "high16"}:
        raise ValueError("Compositor precision must be standard8 or high16.")
    if (not isinstance(graph, dict) or set(graph) - {"version", "nodes", "output"}
            or type(graph.get("version")) is not int or graph["version"] != 1):
        raise ValueError("Compositor requires version 1, nodes, and an output node ID.")
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= MAX_NODES:
        raise ValueError(f"Compositor must contain 1–{MAX_NODES} nodes.")
    start = _frame(animation_start, "animation start", -MAX_ANIMATION_FRAME, 0)
    duration = MAX_ANIMATION_FRAME if animation_duration is None else _frame(
        animation_duration, "animation duration", 1, MAX_ANIMATION_FRAME)
    normalized, by_id = [], {}
    graph_keys = graph_values = 0
    for raw in raw_nodes:
        if not isinstance(raw, dict) or set(raw) - {"id", "type", "inputs", "params", "position", "animation", "tracking_source", "mask_input", "mask_invert"}:
            raise ValueError("Compositor nodes contain unsupported fields.")
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
        extra = ({"direction"} if kind == "lens_distortion"
                 else {"asset_id", "source_in", "duration", "offset", "outside"} if kind == "media_source"
                 else {"color"} if kind == "chroma_key" else {"shape", "invert", "points", "bezier"} if kind == "mask"
                 else {"invert"} if kind == "alpha_mask"
                 else {"mode"} if kind == "merge" else set(CURVE_CHANNELS) if kind == "curves" else set())
        if not isinstance(params, dict) or set(params) - set(PARAMETERS[kind]) - extra:
            raise ValueError(f"Unsupported parameter for compositor {kind}.")
        clean = {key: _number(params.get(key, default), f"{kind}.{key}", low, high)
                 for key, (default, low, high) in PARAMETERS[kind].items()}
        if kind == "lens_distortion":
            direction=params.get("direction","undistort")
            if not isinstance(direction,str) or direction not in {"undistort","distort"}:
                raise ValueError("Calibrated lens direction must be undistort or distort.")
            clean["direction"]=direction
            lens_domain(clean)
        if kind == "media_source":
            clean = {"asset_id": _identifier(params.get("asset_id")),
                     "source_in": _frame(params.get("source_in", 0), "media source in", 0, MAX_ANIMATION_FRAME - 1),
                     "duration": _frame(params.get("duration"), "media source duration", 1, MAX_ANIMATION_FRAME),
                     "offset": _frame(params.get("offset", 0), "media source offset", -MAX_ANIMATION_FRAME, MAX_ANIMATION_FRAME),
                     "outside": params.get("outside", "transparent")}
            if not isinstance(clean["outside"], str) or clean["outside"] not in {"transparent", "hold"}:
                raise ValueError("Compositor media source outside policy must be transparent or hold.")
            if clean["source_in"] + clean["duration"] > MAX_ANIMATION_FRAME:
                raise ValueError("Compositor media source range exceeds its frame limit.")
            if clean["offset"] + clean["duration"] > MAX_ANIMATION_FRAME:
                raise ValueError("Compositor media source placement exceeds its frame limit.")
        if kind == "chroma_key":
            color = params.get("color", "#00ff00")
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise ValueError("Compositor key color must be an RGB hex color.")
            clean["color"] = color.lower()
        if kind == "mask":
            shape, invert = params.get("shape", "rectangle"), params.get("invert", False)
            if not isinstance(shape, str) or shape not in {"rectangle", "ellipse", "polygon", "bezier"} or not isinstance(invert, bool):
                raise ValueError("Compositor masks require rectangle/ellipse/polygon/bezier shape and boolean invert.")
            points = _polygon(params.get("points", DEFAULT_POLYGON))
            clean.update(shape=shape, invert=invert, points=points)
            if "bezier" in params or shape == "bezier" or isinstance(raw.get("animation"), dict) and "bezier" in raw["animation"]:
                clean["bezier"] = _bezier(params.get("bezier", DEFAULT_BEZIER))
        if kind == "alpha_mask":
            if not isinstance(params.get("invert", False), bool):
                raise ValueError("Alpha-mask inversion must be boolean.")
            clean["invert"] = params.get("invert", False)
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
        if "mask_input" in raw:
            if kind not in MASKABLE:
                raise ValueError("An effect mask may connect only to an image-processing effect.")
            node["mask_input"] = _identifier(raw["mask_input"])
            invert = raw.get("mask_invert", False)
            if not isinstance(invert, bool):
                raise ValueError("Effect mask inversion must be boolean.")
            node["mask_invert"] = invert
        elif "mask_invert" in raw:
            raise ValueError("Effect mask inversion requires a mask connection.")
        if "tracking_source" in raw:
            source = raw["tracking_source"]
            if (kind != "mask" or not isinstance(source, dict)
                    or set(source) != {"version", "sha256", "backend"}
                    or type(source.get("version")) is not int or source["version"] != 1
                    or not isinstance(source.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-fA-F]{64}", source["sha256"])
                    or not isinstance(source.get("backend"), str) or len(source["backend"]) > 160):
                raise ValueError("Mask tracking_source requires version 1, a SHA-256 digest, and a backend name up to 160 characters.")
            # Provenance distinguishes derived XY motion when source timing
            # changes. It never contributes commands, paths, or image filters.
            node["tracking_source"] = {"version": 1, "sha256": source["sha256"].lower(), "backend": source["backend"]}
        animation, keys, values = _animation(raw.get("animation", {}), kind, clean, start, duration)
        graph_keys += keys
        graph_values += values
        if graph_keys > MAX_GRAPH_KEYS or graph_values > MAX_ANIMATION_VALUES:
            raise ValueError("Compositor exceeds its animation budget (1024 keys / 8192 coordinate values).")
        if animation:
            node["animation"] = animation
        if "position" in raw:
            position = raw["position"]
            if not isinstance(position, dict) or set(position) != {"x", "y"}:
                raise ValueError("Compositor node position requires x and y.")
            node["position"] = {key: _number(position[key], "position." + key, -100000, 100000) for key in ("x", "y")}
        normalized.append(node)
        by_id[ident] = node
    if sum(node["type"] == "source" for node in normalized) != 1:
        raise ValueError("Compositor requires exactly one clip source node.")
    if sum(node["type"] == "media_source" for node in normalized) > MAX_MEDIA_SOURCES:
        raise ValueError(f"Compositor supports at most {MAX_MEDIA_SOURCES} additional media sources.")
    if sum(node["type"] == "lens_distortion" for node in normalized) > MAX_LENS_NODES:
        raise ValueError(f"Compositor supports at most {MAX_LENS_NODES} calibrated lens nodes.")
    for node in normalized:
        if any(ident not in by_id for ident in node_dependencies(node)):
            raise ValueError("Compositor connection refers to a missing node.")
    output = _identifier(graph.get("output"))
    if output not in by_id:
        raise ValueError("Compositor output refers to a missing node.")
    _walk(by_id, by_id)  # Invalid disconnected nodes must not hide cycles.
    active = _walk(by_id, [output])
    if width is not None and height is not None and width*height>MAX_LENS_PIXELS and any(
            by_id[key]["type"]=="lens_distortion" and any(by_id[key]["params"][name] for name in LENS_COEFFICIENTS)
            for key in active):
        raise ValueError("Calibrated lens processing supports at most 2,073,600 pixels per graph canvas (1920 × 1080).")
    working_images = sum(5 if by_id[key]["type"] == "merge" and by_id[key]["params"]["mode"] != "normal"
                         else 22 if by_id[key]["type"]=="lens_distortion"
                         else 6 if by_id[key]["type"] == "alpha_mask"
                         else 2 if by_id[key]["type"] == "curves" else 1 for key in active)
    # Associated-colour interpolation keeps 16-bit RGB+alpha branches and
    # separate 8-bit source/effect mattes until the final alpha merge.
    working_images += 10 * sum(bool(by_id[key].get("mask_input")) for key in active)
    if precision == "high16":
        # Count the explicit alpha-aware streams at twice the legacy RGBA byte
        # size. No complete movie is buffered; these are concurrent frames.
        working_images = 2 * (working_images + 7 * sum(by_id[key]["type"] == "merge" for key in active))
    if width is not None and height is not None and width * height * working_images > MAX_WORKING_PIXELS:
        raise ValueError("Compositor exceeds its working-image budget. Reduce graph complexity or project resolution.")
    return {"version": 1, "nodes": normalized, "output": output}


def roto_nodes(graph, *, active_only=True):
    if graph is None:
        return []
    nodes = {node["id"]: node for node in graph["nodes"]}
    order = _walk(nodes, [graph["output"]]) if active_only else list(nodes)
    return [nodes[ident] for ident in order if nodes[ident]["type"] == "mask"
            and nodes[ident]["params"].get("shape") == "bezier"]


def media_sources(graph, *, active_only=True):
    """Return detached, canonical source nodes in deterministic graph order.

    A project validates the actual animation domain before using this helper;
    the broad bounds here preserve existing negative-domain animation keys.
    Each node needs its own external stream even when asset IDs coincide.
    """
    graph = validate_graph(graph, animation_start=-MAX_ANIMATION_FRAME)
    nodes = {node["id"]: node for node in graph["nodes"]}
    active = set(_walk(nodes, [graph["output"]])) if active_only else set(nodes)
    return [node for node in graph["nodes"] if node["type"] == "media_source" and node["id"] in active]


def lens_nodes(graph, *, active_only=True):
    """Return canonical non-identity calibrations needing static sample maps.

    Identity lenses remain editable graph nodes but require no resampling,
    extra inputs or external dependencies. Disconnected lenses are still
    schema/certificate validated and never prepared unless requested here.
    """
    graph = validate_graph(graph, animation_start=-MAX_ANIMATION_FRAME)
    nodes = {node["id"]: node for node in graph["nodes"]}
    active = set(_walk(nodes, [graph["output"]])) if active_only else set(nodes)
    return [node for node in graph["nodes"] if node["type"] == "lens_distortion"
            and node["id"] in active and any(node["params"][name] for name in LENS_COEFFICIENTS)]


def validate_media_sources(graph, assets, fps):
    """Validate every media reference against the project's probed asset map.

    This does not trust graph-provided paths or source metadata: those fields
    are not in the node schema. The engine retains file ownership/probing.
    Images are held from frame zero. Videos select project-rate frame counts
    with only the engine's half-frame metadata rounding tolerance.
    """
    fps = _number(fps, "media source frame rate", 1, 60)
    if not isinstance(assets, dict):
        raise ValueError("Compositor media validation requires the project asset map.")
    sources = media_sources(graph, active_only=False)
    for node in sources:
        p = node["params"]
        asset = assets.get(p["asset_id"])
        if not isinstance(asset, dict):
            raise ValueError(f"Compositor media source {node['id']} refers to missing project media.")
        if asset.get("kind") not in {"video", "image"}:
            raise ValueError("Compositor media sources require a video or still image asset.")
        if str(asset.get("path", "")).lower().endswith(".exr") or asset.get("codec") == "exr":
            raise ValueError("Compositor linear EXR masters require an explicit Develop conversion before use.")
        if asset.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
            raise ValueError("Compositor HDR PQ/HLG media needs an explicit SDR conversion before use.")
        if asset["kind"] == "image":
            if p["source_in"]:
                raise ValueError("Compositor still images have no source in point.")
        else:
            seconds = _number(asset.get("duration"), "source media duration", .000001, 1e9)
            if p["source_in"] + p["duration"] > seconds * fps + .5 + 1e-8:
                raise ValueError(f"Compositor media source {node['id']} extends beyond its source media. Shorten its range.")
    return sources


def media_frame_at(node, frame):
    """Reference sampling rule in the preserved animation frame domain.

    None means transparent. Hold clamps to the selected range, not to the
    complete asset. This pure function also documents trim/split semantics.
    """
    p = node["params"]
    relative = frame - p["offset"]
    if p["outside"] == "transparent" and not 0 <= relative < p["duration"]:
        return None
    return p["source_in"] + max(0, min(relative, p["duration"] - 1))


def _decimal(value):
    return format(float(value), ".10g")


def lens_map_request(params, width, height):
    """Canonical data-only worker request, with no filesystem references."""
    width = _frame(width, "lens image width", 2, 8192)
    height = _frame(height, "lens image height", 2, 8192)
    if width * height > MAX_LENS_PIXELS:
        raise ValueError("Calibrated lens maps support at most 2,073,600 pixels (1920 × 1080).")
    graph = {"version": 1, "nodes": [
        {"id": "source", "type": "source", "inputs": [], "params": {}},
        {"id": "lens", "type": "lens_distortion", "inputs": ["source"], "params": params}],
        "output": "lens"}
    clean = validate_graph(graph, width, height)["nodes"][1]["params"]
    return {"version": 1, "width": width, "height": height, "params": clean}


class _LensPNG:
    """Small streaming PNG writer: 16-bit grayscale or RGBA numeric maps.

    These are numeric maps, not display pictures. No color profile/gamma,
    metadata or arbitrary chunks are emitted. Deflate is dependency-free.
    """
    def __init__(self, path, width, height, channels):
        self.path, self.channels = path, channels
        self.file = path.open("xb")
        self.digest, self.size = hashlib.sha256(), 0
        self.compressor = zlib.compressobj(1)
        self._write(b"\x89PNG\r\n\x1a\n")
        self._chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 16, 0 if channels == 1 else 6, 0, 0, 0))

    def _write(self, data):
        self.file.write(data); self.digest.update(data); self.size += len(data)

    def _chunk(self, kind, data):
        self._write(struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    def rows(self, raw):
        compressed = self.compressor.compress(raw)
        if compressed: self._chunk(b"IDAT", compressed)

    def finish(self):
        self._chunk(b"IDAT", self.compressor.flush())
        self._chunk(b"IEND", b"")
        self.file.close()
        return {"file": self.path.name, "sha256": self.digest.hexdigest(), "bytes": self.size,
                "channels": self.channels, "bit_depth": 16}


def _lens_rows_python(params, width, height):
    sample = _lens_sampler(params, width, height)
    for y in range(height):
        rows = {name: array("H") for name in LENS_MAP_NAMES}
        for x in range(width):
            point = sample(x, y)
            if point is None:
                for name in LENS_MAP_NAMES[:4]: rows[name].append(65535)
                rows["wx"].extend((65535,65535,65535,0)); rows["wy"].extend((65535,65535,65535,0))
            else:
                u, v = point; x0, y0 = math.floor(u), math.floor(v)
                rows["x0"].append(x0); rows["x1"].append(min(x0 + 1, width - 1))
                rows["y0"].append(y0); rows["y1"].append(min(y0 + 1, height - 1))
                rows["wx"].extend((65535,65535,65535,round((u - x0) * 65535)))
                rows["wy"].extend((65535,65535,65535,round((v - y0) * 65535)))
        if sys.byteorder != "big":
            for row in rows.values(): row.byteswap()
        yield {name: b"\0" + row.tobytes() for name, row in rows.items()}


def _lens_rows_numpy(params, width, height, np):
    """Strip-vectorized accelerator, imported only by the isolated worker.

    Float64 preserves the reference residual and pixel-center convention.
    Strips bound memory independently of image height. The scalar fallback
    above and this accelerator are compared against a separate Newton oracle.
    """
    p, d = params, lens_domain(params)
    xs = (np.arange(width, dtype=np.float64)[None, :] / width - p["cx"]) / p["fx"]
    def delta(a, b):
        r2 = a*a + b*b; radial = r2*(p["k1"] + r2*(p["k2"] + r2*p["k3"]))
        return (a*radial + 2*p["p1"]*a*b + p["p2"]*(r2 + 2*a*a),
                b*radial + p["p1"]*(r2 + 2*b*b) + 2*p["p2"]*a*b)
    for first in range(0, height, 32):
        rows = min(32, height - first)
        ys = (np.arange(first, first + rows, dtype=np.float64)[:, None] / height - p["cy"]) / p["fy"]
        xd, yd = np.broadcast_arrays(xs, ys)
        if p["direction"] == "undistort":
            dx, dy = delta(xd, yd); a, b = xd + dx, yd + dy
            valid = np.ones((rows, width), dtype=bool)
        else:
            a, b = xd.copy(), yd.copy()
            for _ in range(d["iterations"]):
                dx, dy = delta(a, b)
                aa, bb = np.clip(xd - dx, d["x0"], d["x1"]), np.clip(yd - dy, d["y0"], d["y1"])
                distance = float(np.max(np.hypot(aa - a, bb - b))); a, b = aa, bb
                if distance <= d["tolerance"]: break
            dx, dy = delta(a, b)
            valid = np.hypot(a + dx - xd, b + dy - yd) <= 2e-9
            interior = (a > d["x0"] + 1e-8) & (a < d["x1"] - 1e-8) & (b > d["y0"] + 1e-8) & (b < d["y1"] - 1e-8)
            if np.any(~valid & interior):
                raise ValueError("Calibrated lens inverse failed its certified residual check.")
        u, v = (a*p["fx"] + p["cx"])*width, (b*p["fy"] + p["cy"])*height
        valid &= (u >= -1e-7) & (u <= width-1+1e-7) & (v >= -1e-7) & (v <= height-1+1e-7)
        u, v = np.clip(u, 0, width-1), np.clip(v, 0, height-1)
        x0, y0 = np.floor(u).astype(np.uint16), np.floor(v).astype(np.uint16)
        arrays = {"x0": x0, "x1": np.minimum(x0+1, width-1), "y0": y0, "y1": np.minimum(y0+1, height-1),
                  "wx": np.rint((u-x0)*65535).astype(np.uint16), "wy": np.rint((v-y0)*65535).astype(np.uint16)}
        result = {}
        for name, values in arrays.items():
            if name in {"wx", "wy"}:
                fraction = np.where(valid, values, 0)
                values = np.full((rows, width, 4), 65535, dtype=np.uint16)
                values[:, :, 3] = fraction
            else:
                values = np.where(valid, values, 65535)
            raw = values.astype(">u2").tobytes()
            stride = len(raw) // rows
            result[name] = b"".join(b"\0" + raw[i*stride:(i+1)*stride] for i in range(rows))
        yield result


def write_lens_maps(request, output_dir, *, backend="python"):
    """Worker entry: validated calibration -> six fixed, exclusive PNG files.

    The engine creates and owns output_dir; it is never taken from project
    data. Production invokes this in a cancellable subprocess. Importing the
    compositor itself requires only the Python standard library.
    """
    if (not isinstance(request, dict) or set(request) != {"version", "params", "width", "height"}
            or type(request["version"]) is not int or request["version"] != 1):
        raise ValueError("Lens map request requires version 1, numeric params, width and height only.")
    clean = lens_map_request(request["params"], request["width"], request["height"])
    if backend not in {"python", "numpy", "auto"}:
        raise ValueError("Unsupported lens map worker backend.")
    np = None
    if backend != "python":
        try:
            import numpy as np
        except ImportError:
            if backend == "numpy": raise ValueError("The accelerated lens worker requires NumPy.")
    backend = "numpy" if np is not None else "python"
    directory = Path(output_dir)
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("Lens output directory must be an existing, empty, owned directory.")
    width, height, params = clean["width"], clean["height"], clean["params"]
    writers = {}
    try:
        for name in LENS_MAP_NAMES:
            writers[name] = _LensPNG(directory / (name + ".png"), width, height, 4 if name in {"wx", "wy"} else 1)
        batches = _lens_rows_numpy(params, width, height, np) if np is not None else _lens_rows_python(params, width, height)
        for batch in batches:
            for name, raw in batch.items(): writers[name].rows(raw)
        maps = {name: writer.finish() for name, writer in writers.items()}
    except BaseException:
        for writer in writers.values():
            writer.file.close()
            writer.path.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {"version": 1, "width": width, "height": height, "backend": backend,
            "request_sha256": digest, "maps": maps}


def _channel_expression(node, name, variable, coordinate=None):
    """Compile finite key data to a balanced piecewise expression.

    Balanced branches keep parser/evaluation depth logarithmic even at the
    key limit. No input string or user node ID is inserted into an expression.
    """
    base = node["params"][name]
    points = _key_points(base, node.get("animation", {}).get(name, []))
    value = lambda key: key["value"] if coordinate is None else key["value"][coordinate[0]][coordinate[1]]
    leaves = [_decimal(value(points[0]))]
    for left, right in zip(points, points[1:]):
        a, b = value(left), value(right)
        mode = left["interpolation"]
        if a == b or mode == "constant":
            leaves.append(_decimal(a))
            continue
        t = f"(({variable})-({left['frame']}))/{right['frame'] - left['frame']}"
        amount = (f"pow({t},2)" if mode == "ease_in" else f"1-pow(1-({t}),2)" if mode == "ease_out"
                  else f"pow({t},2)*(3-2*({t}))" if mode == "ease_in_out" else t)
        if mode == "cubic":
            outgoing, incoming = left.get("out_tangent", 0), right.get("in_tangent", 0)
            amount = (f"({_decimal(outgoing+incoming-2)})*pow({t},3)+"
                      f"({_decimal(3-2*outgoing-incoming)})*pow({t},2)+({_decimal(outgoing)})*({t})")
        leaves.append(f"({_decimal(a)}+({_decimal(b-a)})*({amount}))")
    leaves.append(_decimal(value(points[-1])))

    def branch(low, high):
        if low == high:
            return leaves[low]
        middle = (low + high) // 2
        return f"if(lt({variable},{points[middle]['frame']}),{branch(low,middle)},{branch(middle+1,high)})"

    if len(points) == 1:
        return leaves[0]
    return branch(0, len(leaves) - 1)


def _animated_mask_alpha_expression(node, frame_offset):
    p, frame = node["params"], f"N+({frame_offset})"
    scalar = lambda name: _channel_expression(node, name, frame)
    # Registers 5–9 hold transforms until local coordinates are evaluated;
    # 5–8 are then reused for one polygon edge and 9 retains feather amount.
    setup = (f"st(5,{scalar('x')});st(6,{scalar('y')});st(7,{scalar('width')});"
             f"st(8,{scalar('height')});st(9,({scalar('rotation')})*PI/180);")
    px, py = "(X+0.5-W*ld(5))", "(Y+0.5-H*ld(6))"
    setup += (f"st(0,(cos(ld(9))*{px}+sin(ld(9))*{py})/(W*ld(7))+0.5);"
              f"st(1,(-sin(ld(9))*{px}+cos(ld(9))*{py})/(H*ld(8))+0.5);"
              f"st(9,{scalar('feather')});")
    if p["shape"] == "polygon":
        setup += "st(2,0);st(4,2);"
        count = len(p["points"])
        for index in range(count):
            for register, vertex, axis in ((5, index, 0), (6, index, 1),
                                           (7, (index + 1) % count, 0), (8, (index + 1) % count, 1)):
                setup += f"st({register},{_channel_expression(node, 'points', frame, (vertex, axis))});"
            dx, dy = "(ld(7)-ld(5))", "(ld(8)-ld(6))"
            # A deforming edge may momentarily collapse even when all saved
            # keyframes are valid. Never divide by its zero length or slope.
            setup += (f"st(2,ld(2)+if(not(eq(gt(ld(6),ld(1)),gt(ld(8),ld(1)))),"
                      f"lt(ld(0),{dx}*(ld(1)-ld(6))/if(eq({dy},0),1,{dy})+ld(5)),0));"
                      f"st(3,clip(((ld(0)-ld(5))*{dx}+(ld(1)-ld(6))*{dy})/"
                      f"max(1e-20,pow({dx},2)+pow({dy},2)),0,1));"
                      f"st(4,min(ld(4),sqrt(pow(ld(0)-ld(5)-ld(3)*{dx},2)+"
                      f"pow(ld(1)-ld(6)-ld(3)*{dy},2))));")
        mask = "mod(ld(2),2)*if(lte(ld(9),0),1,clip(2*ld(4)/max(1e-20,ld(9)),0,1))"
    else:
        dx, dy = "abs((ld(0)-0.5)*2)", "abs((ld(1)-0.5)*2)"
        distance = f"max({dx},{dy})" if p["shape"] == "rectangle" else f"sqrt(pow({dx},2)+pow({dy},2))"
        mask = f"if(lte(ld(9),0),lte({distance},1),clip((1-({distance}))/max(1e-20,ld(9)),0,1))"
    if p["invert"]:
        mask = f"1-({mask})"
    expression = setup + f"lum(X,Y)*({mask})"
    if len(expression) > 500_000:
        raise ValueError("Compositor animated mask exceeds its expression budget; reduce path keys or vertices.")
    return expression


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


def high16_geq(red="r(X,Y)", green="g(X,Y)", blue="b(X,Y)", alpha="alpha(X,Y)"):
    """Trusted planar UNORM16 expression; caller supplies generated math only."""
    return "geq=" + ":".join(c + "='" + v + "'" for c, v in zip("rgba", (red, green, blue, alpha))) + ":interpolation=nearest"


def high16_source_conversion(pixel_format=None):
    """Convert a decoded source while retaining its actual alpha semantics.

    swscale can synthesize 65532 (rather than 65535) when converting an opaque
    packed RGB source to planar UNORM16+alpha. No-alpha source formats have
    exact unit coverage, so restore that semantic before any compositing.
    Explicit alpha formats, palettes and unknown formats are never flattened.
    Nested rendered streams must omit pixel_format to preserve their alpha.
    """
    opaque = re.fullmatch(
        r"(?:0rgb|rgb0|0bgr|bgr0|rgb24|bgr24|"
        r"(?:rgb|bgr)(?:4|8|444|555|565|48)(?:be|le)?|"
        r"gbrp(?:(?:9|10|12|14|16|f32)(?:be|le))?|"
        r"yuvj?(?:410|411|420|422|440|444)p(?:(?:9|10|12|14|16)(?:be|le))?|"
        r"gray(?:8|(?:9|10|12|14|16|f32)(?:be|le))?|"
        r"nv(?:12|21|16|24|42|20be|20le)|"
        r"p(?:010|016|210|216|410|416)(?:be|le)|"
        r"yuyv422|uyvy422|yvyu422|uyyvyy411)", pixel_format or "")
    return ["format=gbrap16le"] + ([high16_geq(alpha="65535")] if opaque else [])


def high16_associate():
    # GEQ changes samples, not alpha-mode metadata. All arithmetic operands use
    # the same straight metadata, so FFmpeg 8 cannot silently multiply a weight
    # by its alpha a second time during format/alpha-mode negotiation.
    return high16_geq(*(f"floor({c}(X,Y)*alpha(X,Y)/65535+0.5)" for c in "rgb"))


def high16_unassociate():
    return high16_geq(*(f"if(gt(alpha(X,Y),0),floor(clip({c}(X,Y)*65535/alpha(X,Y),0,65535)+0.5),0)" for c in "rgb"))


def high16_attach_matte(filters, color, gray, output):
    """Replace alpha with a gray16 matte without FFmpeg's 8-bit alphamerge."""
    alpha = output + "replacementalpha"
    filters.append(f"[{gray}]format=gbrap16le," + high16_geq(alpha="r(X,Y)") + f"[{alpha}]")
    filters.append(f"[{color}][{alpha}]mergeplanes=0x00010213:format=gbrap16le[{output}]")


def _high16_weighted_values(filters, before, after, mask, output, invert=False):
    """Interpolate four 16-bit planes with an RGBA stream's alpha as weight."""
    weight = "65535-alpha(X,Y)" if invert else "alpha(X,Y)"
    filters.append(f"[{mask}]split=2[{output}m0][{output}m1]")
    filters.append(f"[{output}m0]" + high16_geq(*([f"65535-({weight})"] * 4)) + f"[{output}w0]")
    filters.append(f"[{output}m1]" + high16_geq(*([weight] * 4)) + f"[{output}w1]")
    for ordinal, source in enumerate((before, after)):
        filters.append(f"[{source}][{output}w{ordinal}]blend=all_expr='floor(A*B/65535+0.5)':shortest=1:repeatlast=0[{output}p{ordinal}]")
    filters.append(f"[{output}p0][{output}p1]blend=all_expr='min(65535,A+B)':shortest=1:repeatlast=0[{output}]")


def high16_masked_mix(filters, before, after, mask, output, invert=False):
    """Coverage-correct effect masking in associated 16-bit RGB and alpha."""
    for name, source in (("before", before), ("after", after)):
        filters.append(f"[{source}]format=gbrap16le," + high16_associate() + f"[{output}{name}]")
    _high16_weighted_values(filters, output + "before", output + "after", mask, output + "associated", invert)
    filters.append(f"[{output}associated]" + high16_unassociate() + f",format=gbrap16le[{output}]")


def high16_source_over(filters, background, foreground, output, mode="normal", opacity="1"):
    """Source-over with independent RGB/alpha math and no 8/10-bit overlay.

    All operands stay planar 16-bit. At fractional coverage each associated
    multiply rounds to the nearest UNORM16 code; repeated graph operations
    can accumulate this quantization. This is deliberately a bounded SDR path,
    not a claim of unbounded scene-linear or floating-point compositing.
    """
    if mode not in BLEND_MODES:
        raise ValueError("Unsupported high-depth blend mode.")
    filters.append(f"[{foreground}]format=gbrap16le," + high16_geq(alpha=f"floor(alpha(X,Y)*({opacity})+0.5)") + f"[{output}fg]")
    fg, bg = output + "fg", background
    if mode != "normal":
        filters.append(f"[{background}]split=3[{output}base][{output}bgcolor][{output}bgweight]")
        filters.append(f"[{fg}]split=3[{output}fgcolor][{output}fgplain][{output}fgmatte]")
        expression = {"multiply": "A*B/65535", "screen": "65535-(65535-A)*(65535-B)/65535",
                      "add": "min(65535,A+B)", "difference": "abs(A-B)"}[mode]
        filters.append(f"[{output}bgcolor][{output}fgcolor]blend=all_expr='{expression}':shortest=1:repeatlast=0[{output}blend]")
        _high16_weighted_values(filters, output + "fgplain", output + "blend", output + "bgweight", output + "effective")
        filters.append(f"[{output}effective][{output}fgmatte]mergeplanes=0x00010213:format=gbrap16le[{output}fgblend]")
        fg, bg = output + "fgblend", output + "base"
    filters.append(f"[{fg}]split=2[{output}fgp][{output}fga]")
    filters.append(f"[{output}fgp]" + high16_associate() + f"[{output}fgassociated]")
    filters.append(f"[{output}fga]" + high16_geq(*(["65535-alpha(X,Y)"] * 4)) + f"[{output}inverse]")
    filters.append(f"[{bg}]format=gbrap16le," + high16_associate() + f"[{output}bgassociated]")
    filters.append(f"[{output}bgassociated][{output}inverse]blend=all_expr='floor(A*B/65535+0.5)':shortest=1:repeatlast=0[{output}under]")
    filters.append(f"[{output}under][{output}fgassociated]blend=all_expr='min(65535,A+B)':shortest=1:repeatlast=0,"
                   + high16_unassociate() + f",format=gbrap16le[{output}]")


def high16_grade(exposure="0", contrast="1", saturation="1", temperature="0"):
    """SDR RGB grade: exposure, 0.5 pivot contrast, Rec.709 saturation, warmth.

    Generated scalar expressions may be animated. Values are clamped only at
    this node's UNORM16 output. Alpha is copied; no 8-bit YUV eq is negotiated.
    """
    setup = (f"st(0,pow(2,({exposure})));st(1,({contrast}));st(2,({saturation}));"
             f"st(3,({temperature})*0.12);"
             "st(4,(r(X,Y)/65535*ld(0)-0.5)*ld(1)+0.5);"
             "st(5,(g(X,Y)/65535*ld(0)-0.5)*ld(1)+0.5);"
             "st(6,(b(X,Y)/65535*ld(0)-0.5)*ld(1)+0.5);"
             "st(7,0.2126*ld(4)+0.7152*ld(5)+0.0722*ld(6));")
    return high16_geq(*(setup + f"65535*clip(ld(7)+(ld({slot})-ld(7))*ld(2){warm},0,1)"
                        for slot, warm in ((4, "+ld(3)"), (5, ""), (6, "-ld(3)"))))


def high16_place(chain, width, height, picture_width, picture_height, x, y):
    """Place a transformed sprite on a full canvas through inverse sampling.

    The pad is max(project,sprite), never the sum of their areas; the following
    crop restores project dimensions. Sample associated colors to avoid dark
    fringes. X/Y have integer pixel centers and offsets are in project units.
    """
    left, top = f"(({width}-({picture_width}))/2+{width}*({x}))", f"(({height}-({picture_height}))/2+{height}*({y}))"
    setup = f"st(0,X-({left}));st(1,Y-({top}));st(2,floor(ld(0)));st(3,floor(ld(1)));st(4,ld(0)-ld(2));st(5,ld(1)-ld(3));"
    inside = "gte(ld(0),0)*lte(ld(0),W-1)*gte(ld(1),0)*lte(ld(1),H-1)"
    def bilinear(c):
        return (f"(1-ld(5))*((1-ld(4))*{c}(ld(2),ld(3))+ld(4)*{c}(min(W-1,ld(2)+1),ld(3)))"
                f"+ld(5)*((1-ld(4))*{c}(ld(2),min(H-1,ld(3)+1))+ld(4)*{c}(min(W-1,ld(2)+1),min(H-1,ld(3)+1)))")
    chain += ["format=gbrap16le", high16_associate(),
              f"pad=w='max(iw,{width})':h='max(ih,{height})':x=0:y=0:color=black@0:eval=frame",
              high16_geq(*(setup + f"if({inside},floor(({bilinear(c)})+0.5),0)" for c in ("r", "g", "b", "alpha"))),
              f"crop={width}:{height}:0:0", high16_unassociate(), "format=gbrap16le"]


def compile_graph(graph, input_label, prefix, *, fps=24, frame_offset=0,
                  animation_duration=None, animation_start=0,
                  frame_count=None, external_labels=None, lens_labels=None, roto_labels=None,
                  precision="standard8"):
    """Return filter clauses and a single-use output label for a normalized graph.

    Explicit split nodes are emitted wherever an image feeds multiple ports,
    including a merge wired twice to the same node. Only reachable nodes run.
    The engine supplies input_label, prefix and external_labels; payload IDs
    never enter FFmpeg. Every external stream starts at source frame zero,
    uses project rate, square pixels, straight RGBA and the primary input's
    dimensions. The engine fits/pads source geometry and owns all file I/O.
    A media source emits exactly frame_count frames starting at frame_offset
    of the independent animation domain, including transparent/held gaps.
    Nonzero lens nodes require six already-decoded static map streams from the
    owned map worker, repeated by the engine for exactly frame_count frames.
    Coordinate maps are gray16. Weight PNGs contain white RGB and the 16-bit
    fraction in alpha; explicit premultiplication makes all planes numeric
    weights with the same alpha-mode metadata as the source branches.
    Neither graph parameters nor node IDs can supply executable input.
    """
    valid_label = lambda value: isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value)
    if not valid_label(prefix) or not valid_label(input_label):
        raise ValueError("Invalid internal compositor stream label.")
    graph = validate_graph(graph, animation_duration=animation_duration, animation_start=animation_start,
                           precision=precision)
    high = precision == "high16"
    rgba_format = HIGH16_FORMAT if high else "rgba"
    frame_offset = _frame(frame_offset, "animation offset", -MAX_ANIMATION_FRAME, MAX_ANIMATION_FRAME)
    _number(fps, "frame rate", 1, 60)
    nodes = {node["id"]: node for node in graph["nodes"]}
    order = _walk(nodes, [graph["output"]])
    required = {ident for ident in order if nodes[ident]["type"] == "media_source"}
    external_labels = {} if external_labels is None else external_labels
    if not isinstance(external_labels, dict) or set(external_labels) != required:
        raise ValueError("Compositor external labels must match its reachable media source nodes.")
    if (any(not valid_label(value) for value in external_labels.values())
            or len(set(external_labels.values())) != len(external_labels)
            or input_label in external_labels.values()
            or any(value.startswith(prefix + "n") for value in external_labels.values())):
        raise ValueError("Compositor external stream labels must be valid, distinct internal inputs.")
    required_lenses = {ident for ident in order if nodes[ident]["type"] == "lens_distortion"
                       and any(nodes[ident]["params"][name] for name in LENS_COEFFICIENTS)}
    lens_labels = {} if lens_labels is None else lens_labels
    if (not isinstance(lens_labels, dict) or set(lens_labels) != required_lenses
            or any(not isinstance(labels, dict) or set(labels) != set(LENS_MAP_NAMES)
                   for labels in lens_labels.values())):
        raise ValueError("Compositor lens map labels must match its reachable nonzero calibrations and six map planes.")
    map_labels = [value for labels in lens_labels.values() for value in labels.values()]
    if (any(not valid_label(value) for value in map_labels)
            or len(set(map_labels)) != len(map_labels)
            or set(map_labels) & ({input_label} | set(external_labels.values()))
            or any(value.startswith(prefix + "n") for value in map_labels)):
        raise ValueError("Compositor lens maps require valid, distinct internal input labels.")
    required_roto = {node["id"] for node in roto_nodes(graph)}
    roto_labels = {} if roto_labels is None else roto_labels
    if (not isinstance(roto_labels, dict) or set(roto_labels) != required_roto
            or any(not valid_label(value) for value in roto_labels.values())
            or len(set(roto_labels.values())) != len(roto_labels)
            or set(roto_labels.values()) & ({input_label} | set(external_labels.values()) | set(map_labels))
            or any(value.startswith(prefix + "n") for value in roto_labels.values())):
        raise ValueError("Bezier mask streams must match their reachable nodes and use distinct internal labels.")
    if required or required_lenses or required_roto:
        frame_count = _frame(frame_count, "output frame count", 1, MAX_ANIMATION_FRAME)
        if frame_offset + frame_count > MAX_ANIMATION_FRAME:
            raise ValueError("Compositor output exceeds its frame domain limit.")
    uses = Counter(source for ident in order for source in node_dependencies(nodes[ident]))
    uses[graph["output"]] += 1
    filters, available = [], {}
    if not any(nodes[ident]["type"] == "source" for ident in order):
        # The engine prepares the clip stream independently of graph topology.
        # An external-only output must still consume that unused source label.
        filters.append(f"[{input_label}]nullsink")

    def command_chain(node, commands):
        # sendcmd's expression counter is one-based on the first input frame;
        # geq's N is zero-based. Decoded-media tests protect this distinction.
        arguments = []
        for name, target, option, scale in commands:
            if name not in node.get("animation", {}):
                continue
            expr = _channel_expression(node, name, f"N-1+({frame_offset})")
            if scale != 1:
                expr = f"({expr})*{_decimal(scale)}"
            # The filtergraph and sendcmd parsers each consume one escaping
            # layer. Escape expression commas, not command separators.
            expr = expr.replace(",", "\\\\,")
            arguments.append(f"[expr] {target} {option} {expr}")
        return ["sendcmd=c='0 " + ",".join(arguments) + "'"] if arguments else []

    def preserve_alpha(source, target, chain):
        # Several FFmpeg color filters negotiate RGB/YUV formats without alpha.
        # Carry the original matte independently and rejoin it explicitly.
        rgb, matte, alpha, color = target + "rgb", target + "matte", target + "alpha", target + "color"
        filters.append(f"[{source}]split=2[{rgb}][{matte}]")
        if high:
            filters.append(f"[{rgb}]" + ",".join(chain + ["format=gbrap16le"]) + f"[{color}]")
            filters.append(f"[{color}][{matte}]mergeplanes=0x00010213:format=gbrap16le[{target}]")
            return
        filters.append(f"[{matte}]alphaextract[{alpha}]")
        filters.append(f"[{rgb}]" + ",".join(chain + ["format=rgb24"]) + f"[{color}]")
        filters.append(f"[{color}][{alpha}]alphamerge,format=rgba[{target}]")

    for index, ident in enumerate(order):
        node = nodes[ident]
        kind, params = node["type"], node["params"]
        incoming = [available[source].pop(0) for source in node["inputs"]]
        output = prefix + "n" + str(index)
        effect_base = effect_mask = None
        if node.get("mask_input"):
            effect_mask = available[node["mask_input"]].pop(0)
            effect_base, processed_input = output + "maskbase", output + "processin"
            filters.append(f"[{incoming[0]}]split=2[{effect_base}][{processed_input}]")
            incoming[0] = processed_input
        if kind == "source":
            output = input_label
        elif kind == "media_source":
            relative = frame_offset - params["offset"]
            lead, tail = max(0, -relative), max(0, relative + frame_count - params["duration"])
            window = max(0, relative)
            mode = "clone" if params["outside"] == "hold" else "add"
            # Frame counts, rather than duration seconds, preserve NTSC and
            # negative-domain boundaries. Reset PTS after both selections.
            chain = [f"trim=start_frame={params['source_in']}:end_frame={params['source_in'] + params['duration']}",
                     "setpts=PTS-STARTPTS"]
            if lead or tail:
                chain.append(f"tpad=start={lead}:stop={tail}:start_mode={mode}:stop_mode={mode}:color=black@0")
            chain += [f"trim=start_frame={window}:end_frame={window + frame_count}", "setpts=PTS-STARTPTS", "format=" + rgba_format]
            filters.append(f"[{external_labels[ident]}]" + ",".join(chain) + f"[{output}]")
        elif kind == "lens_distortion":
            if not any(params[name] for name in LENS_COEFFICIENTS):
                filters.append(f"[{incoming[0]}]null[{output}]")
            else:
                # Four nearest remaps select the exact bilinear corners. Two
                # horizontal and one vertical weighted merge preserve 1/65535
                # fractional weights, rather than rounding ray coordinates to
                # integer pixels. Alpha follows the same premultiplied path.
                filters.append(f"[{incoming[0]}]format=gbrap16le,premultiply=inplace=1,split=4"
                               + "".join(f"[{output}s{corner}]" for corner in ("00", "10", "01", "11")))
                for name in LENS_MAP_NAMES[:4]:
                    filters.append(f"[{lens_labels[ident][name]}]format=gray16le,split=2[{output}{name}a][{output}{name}b]")
                # FFmpeg 8 negotiates alpha modes across maskedmerge inputs.
                # Numeric weights stored as straight RGBA=(w,w,w,w) would be
                # auto-premultiplied into RGB=w². Store white+fractional alpha,
                # then explicitly premultiply once so values and metadata
                # agree with the premultiplied picture branches on all builds.
                filters.append(f"[{lens_labels[ident]['wx']}]format=gbrap16le,premultiply=inplace=1,split=2[{output}wxa][{output}wxb]")
                filters.append(f"[{lens_labels[ident]['wy']}]format=gbrap16le,premultiply=inplace=1[{output}wyy]")
                for corner, xmap, ymap in (("00", "x0a", "y0a"), ("10", "x1a", "y0b"),
                                           ("01", "x0b", "y1a"), ("11", "x1b", "y1b")):
                    filters.append(f"[{output}s{corner}][{output}{xmap}][{output}{ymap}]remap=fill=black@0[{output}c{corner}]")
                filters.append(f"[{output}c00][{output}c10][{output}wxa]maskedmerge[{output}top]")
                filters.append(f"[{output}c01][{output}c11][{output}wxb]maskedmerge[{output}bottom]")
                filters.append(f"[{output}top][{output}bottom][{output}wyy]maskedmerge,"
                               f"unpremultiply=inplace=1,format={rgba_format}[{output}]")
        elif kind == "grade":
            animated = node.get("animation", {})
            exposure, eq, balance = "exposure@" + output, "eq@" + output, "colorbalance@" + output
            commands = [("exposure", exposure, "exposure", 1), ("contrast", eq, "contrast", 1),
                        ("saturation", eq, "saturation", 1)]
            commands += [("temperature", balance, option, scale) for option, scale in
                         (("rs", .12), ("rm", .12), ("rh", .12), ("bs", -.12), ("bm", -.12), ("bh", -.12))]
            chain = command_chain(node, commands)
            if params["exposure"] or "exposure" in animated:
                chain.append(exposure + "=exposure=" + _decimal(params["exposure"]))
            if params["contrast"] != 1 or params["saturation"] != 1 or {"contrast", "saturation"} & set(animated):
                chain.append(f"{eq}=contrast={_decimal(params['contrast'])}:saturation={_decimal(params['saturation'])}")
            if params["temperature"] or "temperature" in animated:
                warm = params["temperature"] * .12
                chain.append(f"{balance}=rs={_decimal(warm)}:rm={_decimal(warm)}:rh={_decimal(warm)}:"
                             f"bs={_decimal(-warm)}:bm={_decimal(-warm)}:bh={_decimal(-warm)}")
            if high:
                if any(params[name] != PARAMETERS['grade'][name][0] for name in params) or animated:
                    chain = [high16_grade(*(_channel_expression(node, name, f"N+({frame_offset})")
                                          for name in ("exposure", "contrast", "saturation", "temperature")))]
                else:
                    chain = []
            if chain:
                preserve_alpha(incoming[0], output, chain)
            else:
                filters.append(f"[{incoming[0]}]null[{output}]")
        elif kind in {"blur", "sharpen"}:
            amount = params["sigma" if kind == "blur" else "amount"]
            if amount or node.get("animation"):
                target = "gblur@" + output
                chain = (command_chain(node, [("sigma", target, "sigma", 1), ("sigma", target, "sigmaV", 1)]) +
                         [f"{target}=sigma={_decimal(amount)}:sigmaV={_decimal(amount)}"]
                         if kind == "blur" else [f"unsharp=5:5:{_decimal(amount)}:5:5:0"])
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
            target = "colorkey@" + output
            commands = command_chain(node, [("similarity", target, "similarity", 1), ("blend", target, "blend", 1)])
            filters.append(f"[{keyed}]" + ",".join(commands + ["format=rgba"]) + f",{target}=0x{params['color'][1:]}:"
                           f"{_decimal(params['similarity'])}:{_decimal(params['blend'])},alphaextract[{key_alpha}]")
            filters.append(f"[{alpha}][{key_alpha}]blend=all_mode=multiply[{matte}]")
            if high:
                # colorkey supports packed rgba64; explicitly request it so
                # its alpha extraction also remains 16-bit.
                filters[-2] = filters[-2].replace("format=rgba,", "format=rgba64le,")
                high16_attach_matte(filters, rgb, matte, output)
            else:
                filters.append(f"[{rgb}][{matte}]alphamerge,format=rgba[{output}]")
        elif kind == "alpha_mask":
            # Image alpha is multiplied by the second stream's alpha. Its
            # RGB is irrelevant; keep the first stream's straight RGB planes
            # byte-for-byte, including fractional and zero source alpha.
            color, matte, original, weight, alpha = (output + suffix for suffix in
                                                     ("color", "matte", "original", "weight", "alpha"))
            maximum, gray = (65535, "gray16le") if high else (255, "gray")
            filters.append(f"[{incoming[0]}]split=2[{color}][{matte}]")
            filters.append(f"[{matte}]alphaextract,format={gray}[{original}]")
            filters.append(f"[{incoming[1]}]alphaextract,format={gray}[{weight}]")
            multiplier = f"({maximum}-B)" if params["invert"] else "B"
            filters.append(f"[{original}][{weight}]blend=all_expr='floor(A*{multiplier}/{maximum}+0.5)':"
                           f"shortest=1:repeatlast=0[{alpha}]")
            if high:
                high16_attach_matte(filters, color, alpha, output)
            else:
                filters.append(f"[{color}][{alpha}]alphamerge,format=rgba[{output}]")
        elif kind == "mask":
            color, matte, alpha = output + "color", output + "matte", output + "alpha"
            # Apply geometry only to an extracted grayscale matte. This avoids
            # RGB conversions and their unnecessary alpha quantization.
            filters.append(f"[{incoming[0]}]split=2[{color}][{matte}]")
            if params["shape"] == "bezier":
                original = output + "originalalpha"
                filters.append(f"[{matte}]alphaextract,format=gray16le[{original}]")
                filters.append(f"[{original}][{roto_labels[ident]}]blend=all_mode=multiply:shortest=1:repeatlast=0[{alpha}]")
            else:
                expression = _animated_mask_alpha_expression(node, frame_offset) if node.get("animation") else _mask_alpha_expression(params)
                filters.append(f"[{matte}]alphaextract,geq=lum='{expression}'" + (":interpolation=nearest" if high else "") + f"[{alpha}]")
            if high:
                high16_attach_matte(filters, color, alpha, output)
            else:
                filters.append(f"[{color}][{alpha}]alphamerge,format=rgba[{output}]")
        elif kind == "merge":
            foreground = output + "foreground"
            background = incoming[0]
            if high:
                high16_source_over(filters, incoming[0], incoming[1], output, params["mode"],
                                   _channel_expression(node, "opacity", f"N+({frame_offset})"))
            elif params["mode"] == "normal":
                target = "colorchannelmixer@" + output
                commands = command_chain(node, [("opacity", target, "aa", 1)])
                filters.append(f"[{incoming[1]}]" + ",".join(commands + [f"{target}=aa={_decimal(params['opacity'])}"]) + f"[{foreground}]")
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
                alpha_filter = ("geq=lum='lum(X,Y)*(" + _channel_expression(node, "opacity", f"N+({frame_offset})") + ")'"
                                if "opacity" in node.get("animation", {}) else f"lut=y='val*{_decimal(params['opacity'])}'")
                filters.append(f"[{names['fgmatte']}]alphaextract,{alpha_filter}[{names['fa']}]")
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
            if not high:
                filters.append(f"[{background}][{foreground}]overlay=x=0:y=0:eof_action=endall:"
                               f"shortest=1:repeatlast=0:format=auto:alpha=straight,format=rgba[{output}]")
        if effect_mask is not None and high:
            masked_output = output + "masked"
            high16_masked_mix(filters, effect_base, output, effect_mask, masked_output, node.get("mask_invert", False))
            output = masked_output
        elif effect_mask is not None:
            # Interpolate associated colour and alpha, then unassociate. A
            # keyed transparent result must not leak the hidden source RGB.
            # White RGB with mask alpha yields equal premultiplied weights in
            # all four planes and agrees with FFmpeg 8 alpha-mode negotiation.
            before, after, weight = output + "before", output + "after", output + "weight"
            masked_output = output + "masked"
            filters.append(f"[{effect_base}]split=2[{before}rgb][{before}matte]")
            filters.append(f"[{output}]split=2[{after}rgb][{after}matte]")
            filters.append(f"[{effect_mask}]split=2[{weight}rgb][{weight}matte]")
            filters.append(f"[{before}rgb]format=gbrap16le,premultiply=inplace=1[{before}]")
            filters.append(f"[{after}rgb]format=gbrap16le,premultiply=inplace=1[{after}]")
            filters.append(f"[{before}matte]alphaextract,format=gray[{before}alpha]")
            filters.append(f"[{after}matte]alphaextract,format=gray[{after}alpha]")
            invert_filter = ",lut=y='255-val'" if node.get("mask_invert") else ""
            filters.append(f"[{weight}matte]alphaextract,format=gray{invert_filter}[{weight}alpha]")
            filters.append(f"[{before}alpha][{after}alpha][{weight}alpha]maskedmerge[{masked_output}alpha]")
            alpha_expression = "65535-r(X,Y)" if node.get("mask_invert") else "r(X,Y)"
            filters.append(f"[{weight}rgb]alphaextract,format=gbrap16le,"
                           f"geq=r='65535':g='65535':b='65535':a='{alpha_expression}',"
                           f"premultiply=inplace=1[{weight}]")
            filters.append(f"[{before}][{after}][{weight}]maskedmerge,unpremultiply=inplace=1,format=rgb24[{masked_output}rgb]")
            filters.append(f"[{masked_output}rgb][{masked_output}alpha]alphamerge,format=rgba[{masked_output}]")
            output = masked_output
        count = uses[ident]
        if count > 1:
            labels = [prefix + "n" + str(index) + "use" + str(port) for port in range(count)]
            filters.append(f"[{output}]split={count}" + "".join(f"[{label}]" for label in labels))
            available[ident] = labels
        else:
            available[ident] = [output]
    return filters, available[graph["output"]].pop(0)


def _lens_worker_main():
    """Finite, isolated map worker; the host supplies the output directory."""
    import argparse
    parser = argparse.ArgumentParser(description="CINEMATICUM calibrated lens map worker")
    parser.add_argument("--lens-maps", required=True, metavar="OWNED_EMPTY_DIRECTORY")
    parser.add_argument("--backend", choices=("auto", "python", "numpy"), default="auto")
    args = parser.parse_args()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("Lens map JSON has a duplicate field.")
            result[key] = value
        return result
    try:
        raw = sys.stdin.buffer.read(16_385)
        if len(raw) > 16_384: raise ValueError("Lens map request exceeds 16 KiB.")
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        result = write_lens_maps(request, args.lens_maps, backend=args.backend)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print("Lens map worker: " + str(exc)[:1500], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_lens_worker_main())

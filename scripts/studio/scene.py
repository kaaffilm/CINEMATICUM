"""Data-only scene authoring and real Blender rendering for Studio.

The recipe is deliberately smaller than Blender's scene format. No recipe value
is evaluated as Python, a shader, an expression, a path, or a shell command.
The WebGL authoring view and renderer use Z-up coordinates, XYZ Euler rotations
in degrees, two-unit cube/plane/cylinder primitives, and unit-radius spheres.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import uuid
import zipfile

from adapters import AdapterError, _BLENDER_TIMEOUT, _cancelled, _run_owned, _sha256, find_blender
from spatial_import import validate_mesh, validate_scene_geometry
from scene_modeling import blender_modeling_source, validate_modeling, validate_modeling_budget
from timebase import parse_rate


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_COLOR = re.compile(r"#[a-fA-F0-9]{6}\Z")
MAX_OBJECTS = 96
MAX_LIGHTS = 16
MAX_FRAMES = 7200
INTERPOLATIONS = frozenset({"linear", "constant", "ease_in", "ease_out", "ease_in_out"})
ORIENTATION_MODES = frozenset({"world_up", "transport"})
PASS_CHANNELS = {"depth": ("Depth", ("Z",)), "normal": ("Normal", ("X", "Y", "Z")),
                 "vector": ("Vector", ("X", "Y", "Z", "W")),
                 "diffuse_color": ("DiffCol", ("R", "G", "B")),
                 "emission": ("Emit", ("R", "G", "B"))}
# Blender versions use both compact and full render-pass names. Preserve the
# actual channels in the files/manifest; these are validation aliases only.
PASS_PREFIX_ALIASES = {"diffuse_color": ("DiffCol", "Diffuse Color"),
                       "emission": ("Emit", "Emission")}
OUTPUT_DEFAULTS = {"linear_exr": False, "passes": []}
POSE_FIELDS = {
    "object": {"position": ([-0., 0., 1.], -1000, 1000), "rotation": ([0., 0., 0.], -3600, 3600),
               "scale": ([1., 1., 1.], .01, 100)},
    "camera": {"position": ([7., -9., 6.], -1000, 1000), "target": ([0., 0., 1.], -1000, 1000),
               "fov": (45., 10, 100), "roll": (0., -3600, 3600),
               "shift_x": (0., -2, 2), "shift_y": (0., -2, 2),
               "focus_distance": (10., .01, 10000),
               "f_stop": (5.6, .1, 128)},
    "light": {"position": ([3., -4., 7.], -1000, 1000), "target": ([0., 0., 0.], -1000, 1000),
              "power": (1000., 0, 10000), "size": (4., .01, 100)},
}
RENDER_DEFAULTS = {"max_bounces": 12, "diffuse_bounces": 4, "glossy_bounces": 4,
                   "transmission_bounces": 12, "transparent_max_bounces": 8,
                   "use_denoising": True, "seed": 0}
MATERIAL_DEFAULTS = {"color": "#d8a85f", "roughness": .45, "metallic": 0.,
                     "transmission": 0., "ior": 1.5, "emission_color": "#ffffff",
                     "emission_strength": 0.}


def focal_length_mm(camera, fov=None):
    """Vertical FOV is authoritative; sensor size fixes physical lens/aperture scale."""
    return camera.get("sensor_height_mm", 24.) / (2 * math.tan(math.radians(camera["fov"] if fov is None else fov) / 2))


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ValueError(label + " must be true or false.")
    return value


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a finite number." % label)
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("%s must be a finite number." % label)
    if value < low or value > high or integer and int(value) != value:
        raise ValueError("%s must be %sbetween %s and %s." % (label, "an integer " if integer else "", low, high))
    return int(value) if integer else float(value)


def _vector(value, label, low, high):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("%s must have three coordinates." % label)
    return [_number(v, label, low, high) for v in value]


def _color(value, label):
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise ValueError("%s must be a six-digit RGB color." % label)
    return value.lower()


def _object(value, label, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError("%s has unsupported properties." % label)
    return value


def _id(value, label):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError("%s is invalid." % label)
    return value


def _name(value, default):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError("Scene names must contain 1–120 printable characters.")
    return value.strip() or default


def _keyframes(item, kind, frame_end):
    """Normalize complete, bounded poses. A key owns its outgoing interpolation."""
    fields = POSE_FIELDS[kind]
    keys = item.setdefault("keyframes", [])
    if not isinstance(keys, list) or len(keys) > 128:
        raise ValueError("Each scene item supports at most 128 keyframes.")
    seen = set()
    for key in keys:
        if kind == "camera" and isinstance(key, dict) and "focal_ratio" in key:
            raise ValueError("Camera focal_ratio is static; change it on the camera, not in animation keys.")
        _object(key, kind.title() + " keyframe", {"frame", "interpolation", *fields})
        key["frame"] = _number(key.get("frame"), "Keyframe", 1, frame_end, True)
        if key["frame"] in seen:
            raise ValueError("Scene keyframes must use distinct frames.")
        seen.add(key["frame"])
        mode = key.setdefault("interpolation", "linear")
        if not isinstance(mode, str) or mode not in INTERPOLATIONS:
            raise ValueError("Keyframe interpolation must be linear, constant, ease_in, ease_out, or ease_in_out.")
        for prop, (default, low, high) in fields.items():
            value = key.get(prop, item[prop])
            key[prop] = (_vector(value, "Keyframe " + prop, low, high) if isinstance(default, list)
                         else _number(value, "Keyframe " + prop, low, high))
        if kind == "camera" or kind == "light" and item["type"] != "point":
            if sum((a - b) ** 2 for a, b in zip(key["position"], key["target"])) < .0001:
                raise ValueError("Animated camera and directional light positions must differ from their targets.")
    item["keyframes"] = sorted(keys, key=lambda key: key["frame"])


def _aim_poses(item):
    """Complete aim poses, including the implicit frame-one base pose."""
    base = {"frame": 1, "interpolation": "linear", "position": item["position"],
            "target": item["target"], "roll": item.get("roll", 0.)}
    poses = {1: base}
    for key in item.get("keyframes", []):
        poses[key["frame"]] = {**base, **key}
    return [poses[frame] for frame in sorted(poses)]


def _validate_aim_path(item, label):
    """Check the entire continuous aim path, not just keys or integer frames.

    Position and target share one monotone easing factor within a segment, so
    their difference traces a straight line. Its closest approach to the origin
    can be checked analytically, including subframes. A hold is a deliberate cut.
    """
    for left, right in zip(_aim_poses(item), _aim_poses(item)[1:]):
        if left.get("interpolation", "linear") == "constant":
            continue
        a = [p - t for p, t in zip(left["position"], left["target"])]
        b = [p - t for p, t in zip(right["position"], right["target"])]
        delta = [y - x for x, y in zip(a, b)]
        length2 = sum(v * v for v in delta)
        t = max(0., min(1., -sum(x * y for x, y in zip(a, delta)) / length2)) if length2 else 0.
        distance2 = sum((x + t * y) ** 2 for x, y in zip(a, delta))
        if distance2 < .0001:
            raise ValueError("%s aim path approaches its target within 0.01 m between frames %d and %d. "
                             "Offset the path or use Hold for an intentional cut; an aim direction is undefined at the target."
                             % (label, left["frame"], right["frame"]))


def default_scene(width=1280, height=720):
    """A camera and lighting setup; nothing is passed off as user-made footage."""
    return {"version": 1, "width": width, "height": height, "frame_end": 96, "samples": 32,
            "render": copy.deepcopy(RENDER_DEFAULTS),
            "world": {"color": "#263142", "strength": 0.35, "transparent": False},
            "output": copy.deepcopy(OUTPUT_DEFAULTS),
            "camera": {"position": [7, -9, 6], "target": [0, 0, 1], "fov": 45,
                       "orientation_mode": "transport",
                       "sensor_height_mm": 24., "roll": 0., "shift_x": 0., "shift_y": 0.,
                       "focal_ratio": 1., "dof_enabled": False, "focus_distance": 10., "f_stop": 5.6,
                       "aperture_blades": 0, "aperture_rotation": 0., "aperture_ratio": 1.},
            "objects": [],
            "lights": [
                {"id": "key", "name": "Key light", "type": "area", "position": [3, -4, 7],
                 "target": [0, 0, 0], "color": "#fff0dd", "power": 1100, "size": 5},
                {"id": "fill", "name": "Fill light", "type": "area", "position": [-4, 1, 4],
                 "target": [0, 0, 0], "color": "#b8d7ff", "power": 650, "size": 4},
            ]}


def validate_scene(scene, width=None, height=None):
    """Normalize a bounded recipe, rejecting unsupported behavior before launch."""
    src = copy.deepcopy(_object(scene, "Scene", {
        "version", "width", "height", "frame_end", "samples", "render", "world", "camera", "objects", "lights", "output"}))
    if src.get("version") != 1 or isinstance(src.get("version"), bool):
        raise ValueError("Unsupported 3D scene recipe version.")
    src["width"] = _number(src.get("width", 1280) if width is None else width, "Scene width", 16, 8192, True)
    src["height"] = _number(src.get("height", 720) if height is None else height, "Scene height", 16, 8192, True)
    if src["width"] % 2 or src["height"] % 2 or src["width"] * src["height"] > 16_777_216:
        raise ValueError("Scene dimensions must be even and at most 16.7 million pixels.")
    src["frame_end"] = _number(src.get("frame_end", 96), "Scene end frame", 1, MAX_FRAMES, True)
    src["samples"] = _number(src.get("samples", 32), "Render samples", 4, 256, True)
    render = _object(src.setdefault("render", {}), "Render settings", RENDER_DEFAULTS)
    for prop, default in RENDER_DEFAULTS.items():
        value = render.get(prop, default)
        render[prop] = (_boolean(value, "Denoising") if prop == "use_denoising"
                        else _number(value, "Render " + prop, 0, 2_147_483_647 if prop == "seed" else 64, True))
    output = _object(src.setdefault("output", {}), "Scene output", OUTPUT_DEFAULTS)
    output["linear_exr"] = _boolean(output.get("linear_exr", False), "Scene-linear EXR output")
    passes = output.setdefault("passes", [])
    if (not isinstance(passes, list) or len(passes) > len(PASS_CHANNELS)
            or any(not isinstance(p, str) or p not in PASS_CHANNELS for p in passes)
            or len(set(passes)) != len(passes)):
        raise ValueError("Choose distinct depth, normal, vector, diffuse_color or emission render passes.")
    output["passes"] = [p for p in PASS_CHANNELS if p in passes]
    if passes and not output["linear_exr"]:
        raise ValueError("Enable scene-linear EXR output before selecting render passes.")
    world = _object(src.setdefault("world", {}), "World", {"color", "strength", "transparent"})
    world["color"] = _color(world.get("color", "#263142"), "World color")
    world["strength"] = _number(world.get("strength", .35), "World strength", 0, 5)
    world["transparent"] = _boolean(world.get("transparent", False), "Transparent world")
    camera = _object(src.setdefault("camera", {}), "Camera", {
        *POSE_FIELDS["camera"], "keyframes", "sensor_height_mm", "focal_length_mm", "focal_ratio", "dof_enabled",
        "aperture_blades", "aperture_rotation", "aperture_ratio", "orientation_mode"})
    # Preserve framing of saved pre-0.8 recipes. New scenes/imports explicitly
    # choose transport; old authored roll remains reproducible until changed.
    mode = camera.setdefault("orientation_mode", "world_up")
    if not isinstance(mode, str) or mode not in ORIENTATION_MODES:
        raise ValueError("Camera orientation must be transport or world_up.")
    camera["sensor_height_mm"] = _number(camera.get("sensor_height_mm", 24), "Sensor height (mm)", 1, 100)
    camera["focal_ratio"] = _number(camera.get("focal_ratio", 1), "Focal ratio fx / fy", .1, 10)
    has_focal = "focal_length_mm" in camera
    supplied_focal = camera.pop("focal_length_mm", None)
    if has_focal:
        supplied_focal = _number(supplied_focal, "Focal length (mm)", 1, 1000)
        derived_fov = math.degrees(2 * math.atan(camera["sensor_height_mm"] / (2 * supplied_focal)))
        if "fov" in camera and not math.isclose(_number(camera["fov"], "Vertical field of view", 10, 100), derived_fov, rel_tol=1e-7, abs_tol=1e-7):
            raise ValueError("Camera focal_length_mm contradicts its vertical fov and sensor_height_mm.")
        camera["fov"] = derived_fov
    for prop, (default, low, high) in POSE_FIELDS["camera"].items():
        value = camera.get(prop, default)
        camera[prop] = (_vector(value, "Camera " + prop, low, high) if isinstance(default, list)
                        else _number(value, "Camera " + prop, low, high))
    camera["dof_enabled"] = _boolean(camera.get("dof_enabled", False), "Depth of field")
    camera["aperture_blades"] = _number(camera.get("aperture_blades", 0), "Aperture blades", 0, 16, True)
    if camera["aperture_blades"] in (1, 2):
        raise ValueError("Aperture blades must be zero for a circle, or between 3 and 16.")
    camera["aperture_rotation"] = _number(camera.get("aperture_rotation", 0), "Aperture rotation", -180, 180)
    camera["aperture_ratio"] = _number(camera.get("aperture_ratio", 1), "Aperture ratio", .1, 10)
    if sum((a - b) ** 2 for a, b in zip(camera["position"], camera["target"])) < .0001:
        raise ValueError("Camera position and target must differ.")
    _keyframes(camera, "camera", src["frame_end"])
    _validate_aim_path(camera, "Camera")
    if any(focal_length_mm(camera, pose["fov"]) < 1 for pose in [camera, *camera["keyframes"]]):
        raise ValueError("Camera focal length must be at least 1 mm at every keyframe; enlarge the sensor or narrow the field of view.")
    for key, limit in (("objects", MAX_OBJECTS), ("lights", MAX_LIGHTS)):
        if not isinstance(src.get(key, []), list) or len(src.get(key, [])) > limit:
            raise ValueError("Scene %s must be a list with at most %d items." % (key, limit))
        src.setdefault(key, [])
    identifiers = set()
    for obj in src["objects"]:
        _object(obj, "Scene object", {"id", "name", "type", "position", "rotation", "scale", "material", "keyframes", "mesh", "modeling"})
        ident = _id(obj.get("id"), "Object ID")
        if ident in identifiers:
            raise ValueError("Scene IDs must be unique.")
        identifiers.add(ident)
        obj["name"] = _name(obj.get("name", "Object"), "Object")
        if not isinstance(obj.get("type"), str) or obj["type"] not in {"cube", "sphere", "plane", "cylinder", "mesh"}:
            raise ValueError("Choose a supported primitive or import polygon mesh geometry.")
        if obj["type"] == "mesh":
            obj["mesh"] = validate_mesh(obj.get("mesh"))
        elif "mesh" in obj:
            raise ValueError("Only mesh objects may contain imported geometry.")
        validate_modeling(obj)
        for prop, default, low, high in (("position", [0, 0, 1], -1000, 1000),
                                         ("rotation", [0, 0, 0], -3600, 3600), ("scale", [1, 1, 1], .01, 100)):
            obj[prop] = _vector(obj.get(prop, default), "Object " + prop, low, high)
        mat = _object(obj.setdefault("material", {}), "Material", MATERIAL_DEFAULTS)
        mat["color"] = _color(mat.get("color", "#d8a85f"), "Material color")
        mat["roughness"] = _number(mat.get("roughness", .45), "Roughness", 0, 1)
        mat["metallic"] = _number(mat.get("metallic", 0), "Metallic", 0, 1)
        mat["transmission"] = _number(mat.get("transmission", 0), "Transmission", 0, 1)
        mat["ior"] = _number(mat.get("ior", 1.5), "Index of refraction", 1, 4)
        mat["emission_color"] = _color(mat.get("emission_color", "#ffffff"), "Emission color")
        mat["emission_strength"] = _number(mat.get("emission_strength", 0), "Emission strength", 0, 1000)
        _keyframes(obj, "object", src["frame_end"])
    validate_scene_geometry(src["objects"])
    validate_modeling_budget(src["objects"])
    for light in src["lights"]:
        _object(light, "Light", {"id", "name", "type", "position", "target", "color", "power", "size", "keyframes"})
        ident = _id(light.get("id"), "Light ID")
        if ident in identifiers:
            raise ValueError("Scene IDs must be unique.")
        identifiers.add(ident)
        light["name"] = _name(light.get("name", "Light"), "Light")
        if light.get("type") not in {"area", "point", "sun"}:
            raise ValueError("Choose an area, point, or sun light.")
        light["position"] = _vector(light.get("position", [3, -4, 7]), "Light position", -1000, 1000)
        light["target"] = _vector(light.get("target", [0, 0, 0]), "Light target", -1000, 1000)
        light["color"] = _color(light.get("color", "#ffffff"), "Light color")
        light["power"] = _number(light.get("power", 1000), "Light power", 0, 10000)
        light["size"] = _number(light.get("size", 4), "Light size", .01, 100)
        if light["type"] != "point" and sum((a - b) ** 2 for a, b in zip(light["position"], light["target"])) < .0001:
            raise ValueError("Directional light position and target must differ.")
        _keyframes(light, "light", src["frame_end"])
        if light["type"] != "point":
            _validate_aim_path(light, "Directional light " + light["name"])
    return src


def easing(t, mode="linear"):
    """Explicit polynomial easing, shared with the viewport and Blender handles."""
    if mode == "constant":
        return 0.0
    if mode == "ease_in":
        return t * t
    if mode == "ease_out":
        return t * (2 - t)
    if mode == "ease_in_out":
        return t * t * (3 - 2 * t)
    return t


def _dot3(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross3(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit3(value):
    size = math.hypot(*value)
    if size < 1e-12:
        raise ValueError("An aim direction is undefined at its target.")
    return [v / size for v in value]


def camera_basis(eye, target, roll=0.):
    """Legacy static framing, also the calibrated anchor for transported motion.

    The legacy pole convention is intentionally applied only once when seeding
    transported motion; changing it would rotate existing solved cameras.
    """
    backward = _unit3([a - b for a, b in zip(eye, target)])
    reference = [0., 1., 0.] if abs(backward[2]) > .999 else [0., 0., 1.]
    right = _unit3(_cross3(reference, backward))
    up = _cross3(backward, right)
    c, s = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    return {"right": [x * c + y * s for x, y in zip(right, up)],
            "up": [y * c - x * s for x, y in zip(right, up)],
            "forward": [-v for v in backward], "backward": backward}


def _transport_basis(basis, backward):
    """Rotate the basis along the shortest direction arc without adding roll."""
    axis = _cross3(basis["backward"], backward)
    sine = math.hypot(*axis)
    cosine = max(-1., min(1., _dot3(basis["backward"], backward)))
    right = basis["right"]
    if sine > 1e-12:
        axis = [v / sine for v in axis]
        tangent = _cross3(axis, right)
        along = _dot3(axis, right)
        right = [v * cosine + t * sine + a * along * (1 - cosine)
                 for v, t, a in zip(right, tangent, axis)]
    elif cosine < 0:
        raise ValueError("The interpolated aim path crosses its target. Use Hold for an intentional cut.")
    # Remove floating point drift; transport never depends on playback order.
    projection = _dot3(right, backward)
    right = _unit3([r - projection * z for r, z in zip(right, backward)])
    return {"right": right, "up": _cross3(backward, right),
            "forward": [-v for v in backward], "backward": backward}


def camera_basis_at(item, frame):
    """Deterministic camera orientation at a random-access frame or subframe.

    All eased position/target segments describe great-circle direction arcs.
    Transport the unrolled basis through those arcs, then apply the authored
    roll. A Hold boundary starts a new calibrated anchor, making cuts explicit.
    """
    poses = _aim_poses(item)
    base = poses[0]
    basis = camera_basis(base["position"], base["target"])
    pose = base
    for left, right in zip(poses, poses[1:]):
        if frame <= left["frame"]:
            break
        held = left.get("interpolation", "linear") == "constant"
        if frame < right["frame"]:
            t = easing((frame - left["frame"]) / (right["frame"] - left["frame"]), left.get("interpolation", "linear"))
            pose = {prop: [a + (b - a) * t for a, b in zip(left[prop], right[prop])]
                    for prop in ("position", "target")}
            pose["roll"] = left["roll"] + (right["roll"] - left["roll"]) * t
        else:
            pose = right
        if held:
            if frame >= right["frame"]:
                basis = camera_basis(right["position"], right["target"])
        else:
            backward = _unit3([p - t for p, t in zip(pose["position"], pose["target"])])
            basis = _transport_basis(basis, backward)
        if frame < right["frame"]:
            break
    if item.get("orientation_mode", "world_up") == "world_up":
        return camera_basis(pose["position"], pose["target"], pose["roll"])
    c, s = math.cos(math.radians(pose["roll"])), math.sin(math.radians(pose["roll"]))
    return {**basis, "right": [x * c + y * s for x, y in zip(basis["right"], basis["up"])],
            "up": [y * c - x * s for x, y in zip(basis["right"], basis["up"])]}


def _camera_math_source():
    """Embed these exact pure functions into retained Blender scenes."""
    return "\n\n".join(inspect.getsource(function) for function in (
        _aim_poses, easing, _dot3, _cross3, _unit3, camera_basis, _transport_basis, camera_basis_at))


def pose_at(obj, frame, kind="object"):
    """Evaluate an authored pose. XYZ Euler degrees deliberately do not wrap."""
    props = POSE_FIELDS[kind]
    first = {"frame": 1, "interpolation": "linear", **{key: copy.deepcopy(obj[key]) for key in props}}
    by_frame = {1: first}
    by_frame.update({key["frame"]: key for key in obj.get("keyframes", [])})
    keys = [by_frame[f] for f in sorted(by_frame)]
    if frame <= keys[0]["frame"]:
        return {prop: copy.deepcopy(keys[0][prop]) for prop in props}
    for left, right in zip(keys, keys[1:]):
        if frame < right["frame"]:
            t = easing((frame - left["frame"]) / (right["frame"] - left["frame"]), left.get("interpolation", "linear"))
            return {prop: ([a + (b - a) * t for a, b in zip(left[prop], right[prop])]
                           if isinstance(left[prop], list) else left[prop] + (right[prop] - left[prop]) * t)
                    for prop in props}
    return {prop: copy.deepcopy(keys[-1][prop]) for prop in props}


def _build_script(spec, blend_path, frames_dir, fps, frame_start, frame_end):
    """Paths are supplied by the renderer, never accepted from the recipe."""
    rate = parse_rate(fps, maximum=60)
    payload = json.dumps(spec, ensure_ascii=True, allow_nan=False, sort_keys=True)
    return '''import bpy, json, math
from mathutils import Vector, Matrix, Quaternion
%s
%s
SPEC = json.loads(%r)
BLEND_PATH = %r
FRAMES = %r
FPS = %r
FPS_BASE = %r
START = %r
END = %r
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = SPEC['samples']
for key, value in SPEC['render'].items():
    setattr(scene.cycles, key, value)
scene.render.resolution_x = SPEC['width']
scene.render.resolution_y = SPEC['height']
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.render.fps_base = FPS_BASE
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '16'
scene.render.film_transparent = SPEC['world']['transparent']
for pass_name, property_name in {'depth':'use_pass_z', 'normal':'use_pass_normal',
                                'vector':'use_pass_vector', 'diffuse_color':'use_pass_diffuse_color',
                                'emission':'use_pass_emit'}.items():
    setattr(scene.view_layers[0], property_name, pass_name in SPEC['output']['passes'])
scene.render.use_file_extension = True
# The .blend remains the complete authored source; START/END only select the
# delivery loop below. Neighboring keys also remain available to motion passes.
scene.frame_start = 1
scene.frame_end = SPEC['frame_end']
scene.frame_step = 1
scene.view_settings.view_transform = 'Standard'
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
if hasattr(bpy.context.preferences.edit, 'keyframe_new_interpolation_type'):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
def linear_color(value):
    color = [int(value[i:i+2], 16) / 255 for i in (1,3,5)]
    return [c/12.92 if c <= 0.04045 else ((c+.055)/1.055)**2.4 for c in color]
def aim(obj, target):
    direction = Vector(target) - obj.location
    if direction.length_squared < .0001:
        raise RuntimeError('An animated camera or directional light reached its target.')
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
def aim_camera(obj, frame):
    axes = camera_basis_at(SPEC['camera'], frame)
    basis = Matrix((axes['right'], axes['up'], axes['backward'])).transposed()
    obj.rotation_mode = 'QUATERNION'
    rotation = basis.to_quaternion()
    if obj.rotation_quaternion.dot(rotation) < 0:
        rotation.negate()
    obj.rotation_quaternion = rotation
def action_curves(obj):
    animation = obj.animation_data
    action = animation.action
    curves = []
    layers = list(getattr(action, 'layers', ()))
    # Blender 4.4+ can share one Action between an object and its data-block.
    # Their channels belong to different slots: lens baking must never reset
    # the camera object's eased location curves in another channelbag.
    if layers:
        handle = getattr(animation, 'action_slot_handle', None)
        if handle is None:
            handle = getattr(getattr(animation, 'action_slot', None), 'handle', None)
        for layer in layers:
            for strip in layer.strips:
                for bag in getattr(strip, 'channelbags', ()):
                    if handle is not None and bag.slot_handle == handle:
                        curves.extend(bag.fcurves)
    else:
        curves.extend(getattr(action, 'fcurves', ()))
    if not curves:
        raise RuntimeError('Blender did not expose the authored animation curves for this data-block.')
    return curves
def linearize_action(obj):
    for curve in action_curves(obj):
        curve.extrapolation = 'CONSTANT'
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'
def interpolate_action(obj, poses):
    linearize_action(obj)
    modes = {frame:pose.get('interpolation', 'linear') for frame,pose in poses}
    handles = {'ease_in':(0, 1/3), 'ease_out':(2/3, 1), 'ease_in_out':(0, 1)}
    for curve in action_curves(obj):
        points = sorted(curve.keyframe_points, key=lambda point:point.co[0])
        for point in points:
            point.handle_left_type = 'FREE'
            point.handle_right_type = 'FREE'
        for left,right in zip(points, points[1:]):
            mode = modes.get(round(left.co[0]), 'linear')
            if mode == 'constant': left.interpolation = 'CONSTANT'
            elif mode in handles:
                left.interpolation = 'BEZIER'
                dx = (right.co[0]-left.co[0])/3
                dy = right.co[1]-left.co[1]
                a,b = handles[mode]
                left.handle_right = (left.co[0]+dx, left.co[1]+dy*a)
                right.handle_left = (right.co[0]-dx, left.co[1]+dy*b)
def recipe_poses(item, properties):
    poses = {1:{'frame':1, 'interpolation':'linear', **{p:item[p] for p in properties}}}
    poses.update({pose['frame']:pose for pose in item.get('keyframes', [])})
    return sorted(poses.items())
def pose_at(poses, frame):
    def values(pose): return {p:value for p,value in pose.items() if p not in ('frame','interpolation')}
    if frame <= poses[0][0]: return values(poses[0][1])
    for (af,a),(bf,b) in zip(poses,poses[1:]):
        if frame < bf:
            t = (frame-af)/(bf-af)
            mode = a.get('interpolation', 'linear')
            if mode == 'constant': t = 0
            elif mode == 'ease_in': t = t*t
            elif mode == 'ease_out': t = t*(2-t)
            elif mode == 'ease_in_out': t = t*t*(3-2*t)
            return {p:([x+(y-x)*t for x,y in zip(value,b[p])] if isinstance(value,list)
                       else value+(b[p]-value)*t) for p,value in values(a).items()}
    return values(poses[-1][1])
def tracking_target(obj, name, position, constrain=True):
    target = bpy.data.objects.new(name, None)
    scene.collection.objects.link(target)
    target.location = position
    target.empty_display_type = 'PLAIN_AXES'
    target.empty_display_size = .3
    if constrain:
        track = obj.constraints.new('TRACK_TO')
        track.target = target
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'
    return target
world = bpy.data.worlds.new('CINEMATICUM World')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (*linear_color(SPEC['world']['color']), 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = SPEC['world']['strength']
scene.world = world
camera_data = bpy.data.cameras.new('Render Camera')
camera_data.sensor_fit = 'VERTICAL'
camera_data.sensor_height = SPEC['camera']['sensor_height_mm']
camera_data.dof.use_dof = SPEC['camera']['dof_enabled']
camera_data.dof.aperture_blades = SPEC['camera']['aperture_blades']
camera_data.dof.aperture_rotation = math.radians(SPEC['camera']['aperture_rotation'])
camera_data.dof.aperture_ratio = SPEC['camera']['aperture_ratio']
camera_data.clip_start = .05
camera_data.clip_end = 5000
camera = bpy.data.objects.new('Render Camera', camera_data)
scene.collection.objects.link(camera)
camera.location = SPEC['camera']['position']
scene.camera = camera
camera_poses = recipe_poses(SPEC['camera'], ('position','target','fov','roll','shift_x','shift_y','focus_distance','f_stop'))
camera_target = tracking_target(camera, 'Camera aim', SPEC['camera']['target'], constrain=False)
def apply_camera(pose, frame):
    camera.location = pose['position']
    camera_target.location = pose['target']
    aim_camera(camera, frame)
    camera_data.lens = camera_data.sensor_height / (2 * math.tan(math.radians(pose['fov'])/2))
    # VERTICAL sensor fit: Blender's x shift is normalized by effective sensor
    # height. CINEMATICUM principal shifts are normalized by output width/height.
    focal_ratio = SPEC['camera']['focal_ratio']
    camera_data.shift_x = -pose['shift_x'] * SPEC['width'] / SPEC['height'] / focal_ratio
    camera_data.shift_y = -pose['shift_y']
    # Blender marks output pixel aspect non-animatable. A calibrated focal
    # ratio is therefore static; validation rejects it in camera pose keys.
    scene.render.pixel_aspect_x = max(1, 1 / focal_ratio)
    scene.render.pixel_aspect_y = max(1, focal_ratio)
    camera_data.dof.focus_distance = pose['focus_distance']
    camera_data.dof.aperture_fstop = pose['f_stop']
apply_camera(pose_at(camera_poses, 1), 1)
if SPEC['camera'].get('keyframes'):
    for frame,pose in camera_poses:
        camera.location = pose['position']
        camera_target.location = pose['target']
        camera.keyframe_insert(data_path='location', frame=frame)
        camera_target.keyframe_insert(data_path='location', frame=frame)
    interpolate_action(camera, camera_poses)
    interpolate_action(camera_target, camera_poses)
    # Orientation, projection and thin-lens conversion are nonlinear. Bake
    # integer frames so the retained .blend independently replays each frame.
    # Translation keeps its original eased curves; only quaternion channels
    # are linearized on the camera object after this bake.
    for frame in range(1, SPEC['frame_end']+1):
        apply_camera(pose_at(camera_poses, frame), frame)
        camera.keyframe_insert(data_path='rotation_quaternion', frame=frame)
        for path in ('lens', 'shift_x', 'shift_y', 'dof.focus_distance', 'dof.aperture_fstop'):
            camera_data.keyframe_insert(data_path=path, frame=frame)
    for curve in action_curves(camera):
        if curve.data_path == 'rotation_quaternion':
            for key in curve.keyframe_points: key.interpolation = 'LINEAR'
    linearize_action(camera_data)
lights = []
for item in SPEC['lights']:
    light_data = bpy.data.lights.new(item['name'], item['type'].upper())
    light_data.color = linear_color(item['color'])
    light_data.energy = item['power']
    if item['type'] == 'area':
        light_data.shape = 'DISK'
        light_data.size = item['size']
    elif item['type'] == 'point':
        light_data.shadow_soft_size = item['size']/2
    else:
        light_data.angle = min(math.pi, math.radians(item['size']))
    light = bpy.data.objects.new(item['name'], light_data)
    scene.collection.objects.link(light)
    light.location = item['position']
    light_target = None
    if item['type'] != 'point':
        aim(light, item['target'])
        light_target = tracking_target(light, item['name'] + ' aim', item['target'])
    light_poses = recipe_poses(item, ('position','target','power','size'))
    size_path = {'area':'size', 'point':'shadow_soft_size', 'sun':'angle'}[item['type']]
    size_factor = {'area':1, 'point':.5, 'sun':math.pi/180}[item['type']]
    if item.get('keyframes'):
        for frame,pose in light_poses:
            light.location = pose['position']
            light.keyframe_insert(data_path='location', frame=frame)
            if light_target:
                light_target.location = pose['target']
                light_target.keyframe_insert(data_path='location', frame=frame)
            light_data.energy = pose['power']
            setattr(light_data, size_path, pose['size']*size_factor)
            light_data.keyframe_insert(data_path='energy', frame=frame)
            light_data.keyframe_insert(data_path=size_path, frame=frame)
        interpolate_action(light, light_poses)
        interpolate_action(light_data, light_poses)
        if light_target: interpolate_action(light_target, light_poses)
    lights.append((light, light_target, light_poses, size_path, size_factor))
objects = []
for item in SPEC['objects']:
    primitive = item['type']
    if primitive == 'cube': bpy.ops.mesh.primitive_cube_add(size=2)
    elif primitive == 'sphere': bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
    elif primitive == 'plane': bpy.ops.mesh.primitive_plane_add(size=2)
    elif primitive == 'cylinder': bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1, depth=2)
    if primitive == 'mesh':
        geometry = item['mesh']
        if item.get('modeling'):
            obj = cinematicum_model_object(item, scene.collection)
            cinematicum_verify_model(obj, item)
        else:
            mesh_data = bpy.data.meshes.new(item['name'] + ' Geometry')
            mesh_data.from_pydata(geometry['vertices'], [], geometry['triangles'])
            mesh_data.update()
            if len(mesh_data.vertices) != len(geometry['vertices']) or len(mesh_data.polygons) != len(geometry['triangles']):
                raise RuntimeError('Blender did not preserve the imported mesh topology.')
            if geometry['uvs']:
                uv_layer = mesh_data.uv_layers.new(name='UVMap')
                for polygon,indices in zip(mesh_data.polygons, geometry['uv_indices']):
                    for loop_index,uv_index in zip(polygon.loop_indices, indices):
                        uv_layer.data[loop_index].uv = geometry['uvs'][uv_index] if uv_index >= 0 else (0, 0)
            if geometry['normals']:
                for polygon in mesh_data.polygons: polygon.use_smooth = True
                mesh_data.normals_split_custom_set([geometry['normals'][index] for face in geometry['normal_indices'] for index in face])
            obj = bpy.data.objects.new(item['name'], mesh_data)
            scene.collection.objects.link(obj)
        obj['cinematicum_geometry_sha256'] = geometry['sha256']
        if geometry.get('source'):
            obj['cinematicum_source_sha256'] = geometry['source']['sha256']
            obj['cinematicum_source_name'] = geometry['source']['name']
    else:
        obj = bpy.context.object
    obj.name = item['name']
    obj['cinematicum_id'] = item['id']
    obj.rotation_mode = 'XYZ'
    obj.location = item['position']
    obj.rotation_euler = [math.radians(v) for v in item['rotation']]
    obj.scale = item['scale']
    if primitive == 'sphere':
        for polygon in obj.data.polygons: polygon.use_smooth = True
    material = bpy.data.materials.new(item['name'] + ' Material')
    material.use_nodes = True
    color = (*linear_color(item['material']['color']), 1)
    material.diffuse_color = color
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = color
    shader.inputs['Roughness'].default_value = item['material']['roughness']
    shader.inputs['Metallic'].default_value = item['material']['metallic']
    # Blender 4+ renamed these Principled inputs; retain Blender 3 compatibility.
    transmission = shader.inputs.get('Transmission Weight') or shader.inputs.get('Transmission')
    emission = shader.inputs.get('Emission Color') or shader.inputs.get('Emission')
    if transmission is None or emission is None:
        raise RuntimeError('This Blender Principled BSDF lacks required material inputs.')
    transmission.default_value = item['material']['transmission']
    shader.inputs['IOR'].default_value = item['material']['ior']
    emission.default_value = (*linear_color(item['material']['emission_color']), 1)
    shader.inputs['Emission Strength'].default_value = item['material']['emission_strength']
    obj.data.materials.append(material)
    poses = recipe_poses(item, ('position','rotation','scale'))
    if item['keyframes']:
        for frame, pose in poses:
            obj.location = pose['position']
            obj.rotation_euler = [math.radians(v) for v in pose['rotation']]
            obj.scale = pose['scale']
            for path in ('location','rotation_euler','scale'): obj.keyframe_insert(data_path=path, frame=frame)
        interpolate_action(obj, poses)
    objects.append((obj, poses))
scene.frame_set(START)
def set_output_format(kind):
    settings = scene.render.image_settings
    # Blender 5 separated image/multilayer/video media types from the codec.
    # Select the media type first: the accepted file-format enum depends on it.
    if hasattr(settings, 'media_type'):
        settings.media_type = 'MULTI_LAYER_IMAGE' if kind == 'OPEN_EXR_MULTILAYER' else 'IMAGE'
    settings.file_format = kind
    settings.color_mode = 'RGBA'
    settings.color_depth = '16' if kind == 'PNG' else '32'
    settings.color_management = 'FOLLOW_SCENE' if kind == 'PNG' else 'OVERRIDE'
    if kind != 'PNG':
        settings.exr_codec = 'ZIP'
        # Keep one scanline part for readers that do not support Blender 5's
        # default multipart storage. All requested float passes are retained.
        if hasattr(settings, 'use_exr_interleave'):
            settings.use_exr_interleave = True
        try: settings.linear_colorspace_settings.name = 'Linear Rec.709'
        except (TypeError, ValueError):
            raise RuntimeError('This Blender color configuration lacks Linear Rec.709 required for EXR masters.')
if SPEC['output']['linear_exr']:
    set_output_format('OPEN_EXR_MULTILAYER' if SPEC['output']['passes'] else 'OPEN_EXR')
scene.render.filepath = '//renders/frame_######'
text = bpy.data.texts.new('CINEMATICUM Scene Recipe.json')
text.write(json.dumps(SPEC, ensure_ascii=False, indent=2))
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, check_existing=False)
for frame in range(START, END+1):
    scene.frame_set(frame)
    for obj, poses in objects:
        pose = pose_at(poses, frame)
        obj.location = pose['position']
        obj.rotation_euler = [math.radians(v) for v in pose['rotation']]
        obj.scale = pose['scale']
    camera_pose = pose_at(camera_poses, frame)
    apply_camera(camera_pose, frame)
    for light,light_target,poses,size_path,size_factor in lights:
        pose = pose_at(poses, frame)
        light.location = pose['position']
        light.data.energy = pose['power']
        setattr(light.data, size_path, pose['size']*size_factor)
        if light_target:
            light_target.location = pose['target']
            aim(light, pose['target'])
    set_output_format('PNG')
    scene.render.filepath = FRAMES + '/frame_%%06d.png' %% frame
    bpy.ops.render.render(write_still=True)
    if SPEC['output']['linear_exr']:
        # Render Result still contains the scene-linear buffers. Saving an EXR
        # bypasses the PNG display transform; never reconstruct floats from PNG.
        result = bpy.data.images.get('Render Result')
        if result is None: raise RuntimeError('Blender did not retain its scene-linear render buffers.')
        set_output_format('OPEN_EXR')
        result.save_render(filepath=FRAMES + '/beauty_%%06d.exr' %% frame, scene=scene)
        if SPEC['output']['passes']:
            set_output_format('OPEN_EXR_MULTILAYER')
            result.save_render(filepath=FRAMES + '/passes_%%06d.exr' %% frame, scene=scene)
if SPEC['output']['linear_exr']:
    with open(FRAMES + '/render-info.json', 'w') as handle:
        json.dump({'engine': 'Blender Cycles', 'engine_version': bpy.app.version_string,
                   'color_space': scene.render.image_settings.linear_colorspace_settings.name,
                   'sample_type': 'float32', 'alpha': 'premultiplied',
                   'transparent_world': scene.render.film_transparent}, handle)
''' % (blender_modeling_source(), _camera_math_source(), payload, str(blend_path), str(frames_dir), rate.blender_fps, rate.blender_fps_base, frame_start, frame_end)


def inspect_exr_header(path):
    """Read bounded ordinary scanline EXR metadata without optional libraries.

    This proves dimensions/channel storage, not pixel semantics. Native render
    acceptance separately reads actual float samples with an EXR decoder.
    """
    limit = 4 * 1024 * 1024
    with Path(path).open('rb') as handle:
        def read(count):
            if handle.tell() + count > limit:
                raise AdapterError('The rendered EXR header exceeds the metadata limit.')
            value = handle.read(count)
            if len(value) != count:
                raise AdapterError('Blender produced a truncated EXR header.')
            return value

        def cstring():
            value = bytearray()
            while True:
                char = read(1)
                if char == b'\0':
                    break
                value.extend(char)
                if len(value) > 1024:
                    raise AdapterError('The rendered EXR header has an invalid attribute name.')
            return bytes(value).decode('utf-8', errors='strict')

        if read(4) != b'\x76\x2f\x31\x01':
            raise AdapterError('Blender did not produce an OpenEXR master.')
        version = struct.unpack('<I', read(4))[0]
        if version & 0xff != 2 or version & 0x1a00:
            raise AdapterError('The scene master must be an ordinary scanline EXR, not tiled, deep or multipart data.')
        attributes = {}
        while True:
            name = cstring()
            if not name:
                break
            kind = cstring()
            size = struct.unpack('<I', read(4))[0]
            if name in attributes:
                raise AdapterError('The rendered EXR repeats a header attribute.')
            attributes[name] = (kind, read(size))
    if attributes.get('dataWindow', ('',))[0] != 'box2i' or len(attributes['dataWindow'][1]) != 16:
        raise AdapterError('The rendered EXR has no valid pixel window.')
    x0, y0, x1, y1 = struct.unpack('<iiii', attributes['dataWindow'][1])
    if attributes.get('channels', ('',))[0] != 'chlist':
        raise AdapterError('The rendered EXR has no channel list.')
    if attributes.get('compression') != ('compression', b'\x03'):
        raise AdapterError('The scene master must use lossless ZIP compression.')
    data, offset, channels = attributes['channels'][1], 0, {}
    while offset < len(data) and data[offset]:
        end = data.find(b'\0', offset)
        if end < 0 or end + 17 > len(data):
            raise AdapterError('The rendered EXR has a malformed channel list.')
        name = data[offset:end].decode('utf-8', errors='strict')
        pixel_type, linear, xs, ys = struct.unpack('<iB3xii', data[end+1:end+17])
        if name in channels or pixel_type != 2 or xs != 1 or ys != 1:
            raise AdapterError('Every scene-master channel must contain full-resolution 32-bit floats.')
        channels[name] = {'sample_type': 'float32', 'linear_hint': bool(linear)}
        offset = end + 17
    if not channels or data[offset:] != b'\0' or x1 < x0 or y1 < y0:
        raise AdapterError('The rendered EXR channel list or dimensions are invalid.')
    return {'width': x1 - x0 + 1, 'height': y1 - y0 + 1, 'channels': channels}


def _package_scene_masters(spec, frames, destination, rate, start, end, cancel_event=None):
    """Publish no archive until every requested frame and pass is present."""
    info_path = frames/'render-info.json'
    if not info_path.is_file() or info_path.stat().st_size > 16384:
        raise AdapterError('Blender did not preserve scene-master rendering metadata.')
    info = json.loads(info_path.read_text(encoding='utf-8'))
    if (not isinstance(info, dict) or info.get('color_space') != 'Linear Rec.709'
            or info.get('sample_type') != 'float32' or info.get('alpha') != 'premultiplied'
            or not isinstance(info.get('engine_version'), str)
            or info.get('transparent_world') is not spec['world']['transparent']):
        raise AdapterError('The scene-master color, sample or alpha metadata did not match the render contract.')
    manifest = {'format': 'cinematicum-scene-masters', 'version': 1, 'renderer': info,
                'width': spec['width'], 'height': spec['height'], 'frame_rate': rate.as_dict(),
                'frame_start': start, 'frame_end': end, 'frame_end_inclusive': True,
                'frame_count': end - start + 1, 'passes': spec['output']['passes'],
                'beauty_channels': ['R', 'G', 'B', 'A'], 'compression': 'ZIP',
                'display_movie': 'Opaque H.264 display derivative; EXR files are the scene-linear masters.',
                'recipe_sha256': hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'files': []}
    names = []
    try:
        with zipfile.ZipFile(destination, 'x', allowZip64=True) as archive:
            for frame in range(start, end + 1):
                for role in ('beauty', 'passes') if spec['output']['passes'] else ('beauty',):
                    _cancelled(cancel_event)
                    source = frames / ('%s_%06d.exr' % (role, frame))
                    if not source.is_file() or source.is_symlink() or not source.stat().st_size:
                        raise AdapterError('Blender did not produce %s EXR frame %d.' % (role, frame))
                    header = inspect_exr_header(source)
                    if (header['width'], header['height']) != (spec['width'], spec['height']):
                        raise AdapterError('The scene-master dimensions differ from the saved scene.')
                    channels = set(header['channels'])
                    if role == 'beauty' and not {'R', 'G', 'B', 'A'} <= channels:
                        raise AdapterError('The scene-linear beauty master must preserve all RGBA channels.')
                    if role == 'passes':
                        for render_pass in spec['output']['passes']:
                            prefix, components = PASS_CHANNELS[render_pass]
                            prefixes = PASS_PREFIX_ALIASES.get(render_pass, (prefix,))
                            if not any(all(any(c == candidate+'.'+component or c.endswith('.'+candidate+'.'+component)
                                               for c in channels) for component in components) for candidate in prefixes):
                                raise AdapterError('The actual multilayer EXR is missing the requested %s pass.' % render_pass)
                    name = '%s/%s_%06d.exr' % (role, role, frame)
                    digest, size = hashlib.sha256(), 0
                    # EXR already uses lossless ZIP compression. Stream the
                    # container without a second expensive compression pass.
                    with source.open('rb') as incoming, archive.open(name, 'w', force_zip64=True) as outgoing:
                        while True:
                            _cancelled(cancel_event)
                            block = incoming.read(1024 * 1024)
                            if not block:
                                break
                            digest.update(block)
                            outgoing.write(block)
                            size += len(block)
                    names.append(name)
                    manifest['files'].append({'path': name, 'frame': frame, 'role': role, 'bytes': size,
                                              'sha256': digest.hexdigest(), 'channels': sorted(channels)})
            _cancelled(cancel_event)
            archive.writestr('manifest.json', json.dumps(manifest, sort_keys=True, indent=2), compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr('scene.json', json.dumps(spec, sort_keys=True, indent=2), compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(destination) as archive:
            if set(archive.namelist()) != set(names) | {'manifest.json', 'scene.json'}:
                raise AdapterError('The scene-master archive is incomplete.')
        _cancelled(cancel_event)
    except BaseException:
        Path(destination).unlink(missing_ok=True)
        raise
    return manifest


def render_scene(scene, output_dir, fps=24, frame_start=1, frame_end=None,
                 progress=lambda value: None, cancel_event=None):
    """Build the authored scene in Blender, render frames, and encode actual MP4."""
    _cancelled(cancel_event)
    spec = validate_scene(scene)
    if not spec["objects"]:
        raise ValueError("Add at least one object before rendering the 3D scene.")
    rate = parse_rate(fps, maximum=60)
    start = _number(frame_start, "Start frame", 1, spec["frame_end"], True)
    end = _number(spec["frame_end"] if frame_end is None else frame_end, "End frame", start, spec["frame_end"], True)
    binary, ffmpeg = find_blender(), shutil.which("ffmpeg")
    if not binary or not ffmpeg:
        raise AdapterError("Blender and FFmpeg are required to render the authored 3D scene.")
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    ident = uuid.uuid4().hex
    movie, blend = target / ("scene-" + ident + ".mp4"), target / ("scene-" + ident + ".blend")
    masters = target / ("scene-" + ident + "-masters.zip")
    masters_manifest = None
    total = end - start + 1
    if spec['output']['linear_exr']:
        # Keep headroom for the render buffers, PNG display sequence and the
        # final archive simultaneously. Compressed sizes are data-dependent.
        channels = 4 + (4 + sum(len(PASS_CHANNELS[p][1]) for p in spec['output']['passes'])
                         if spec['output']['passes'] else 0)
        reserve = total * spec['width'] * spec['height'] * (channels * 8 + 8) + 64 * 1024 * 1024
        if shutil.disk_usage(target).free < reserve:
            raise AdapterError('Scene-linear masters need approximately %.2f GiB of free working space for this frame range. '
                               'Choose a shorter range or a project volume with more space.' % (reserve / 1024 ** 3))
    progress(0)
    with tempfile.TemporaryDirectory(prefix=".scene-", dir=str(target)) as temporary:
        work = Path(temporary)
        frames = work / "frames"
        frames.mkdir()
        source = work / "authored.blend"
        script = work / "build_scene.py"
        script.write_text(_build_script(spec, source, frames, rate, start, end), encoding="utf-8")
        previous = [-1]

        def tick():
            count = len(list(frames.glob("frame_*.png")))
            if count != previous[0]:
                previous[0] = count
                progress(min(.85, .85 * count / total))

        _run_owned([binary, "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1", "--python", str(script)],
                   work / "blender.log", cancel_event, _BLENDER_TIMEOUT, tick)
        if not source.is_file() or not source.stat().st_size:
            raise AdapterError("Blender did not save the authored scene.")
        for frame in range(start, end + 1):
            file = frames / ("frame_%06d.png" % frame)
            if not file.is_file() or not file.stat().st_size:
                raise AdapterError("Blender did not produce scene frame %d." % frame)
        _cancelled(cancel_event)
        encoded = work / "encoded.mp4"
        encode = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-n", "-framerate", rate.ffmpeg,
                  "-start_number", str(start), "-i", str(frames / "frame_%06d.png")]
        if spec['world']['transparent']:
            encode.extend(['-f', 'lavfi', '-i', 'color=c=black:s=%dx%d:r=%s' % (spec['width'], spec['height'], rate.ffmpeg),
                           '-filter_complex', '[1:v][0:v]overlay=shortest=1:format=auto,setsar=1[out]', '-map', '[out]'])
        else:
            encode.extend(['-vf', 'setsar=1'])
        encode.extend(["-frames:v", str(total), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                       "-movflags", "+faststart", str(encoded)])
        _run_owned(encode, work / "encode.log", cancel_event, _BLENDER_TIMEOUT)
        if not encoded.is_file() or not encoded.stat().st_size:
            raise AdapterError("The authored scene did not produce a nonempty encoded movie.")
        _cancelled(cancel_event)
        archive = work / 'masters.zip'
        if spec['output']['linear_exr']:
            masters_manifest = _package_scene_masters(spec, frames, archive, rate, start, end, cancel_event)
        # The caller probes/adopts this movie before exposing it as timeline media.
        try:
            os.replace(str(source), str(blend))
            os.replace(str(encoded), str(movie))
            if masters_manifest is not None:
                os.replace(str(archive), str(masters))
        except BaseException:
            blend.unlink(missing_ok=True)
            movie.unlink(missing_ok=True)
            masters.unlink(missing_ok=True)
            raise
    result = {"path": str(movie), "scene_path": str(blend), "provenance": {
        "backend": "blender-authored-scene", "renderer": "Cycles CPU", "scene_version": 1,
        "recipe_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "output_sha256": _sha256(movie), "scene_sha256": _sha256(blend), "frame_start": start,
        "frame_end": end, "frame_end_inclusive": True, "fps": rate.fps, "frame_rate": rate.as_dict(), "autoexec_enabled": False,
        "objects": len(spec["objects"]), "lights": len(spec["lights"]), "viewport_is_approximate": True,
        "transparent_world": spec['world']['transparent'],
        "movie_has_alpha": False,
        "mesh_objects": sum(item["type"] == "mesh" for item in spec["objects"]),
        "mesh_vertices": sum(len(item["mesh"]["vertices"]) for item in spec["objects"] if item["type"] == "mesh"),
        "mesh_triangles": sum(len(item["mesh"]["triangles"]) for item in spec["objects"] if item["type"] == "mesh"),
        "mesh_geometry_sha256": [item["mesh"]["sha256"] for item in spec["objects"] if item["type"] == "mesh"],
        "modeled_objects": sum(bool(item.get("modeling")) for item in spec["objects"]),
        "evaluated_geometry_sha256": [item["modeling"]["evaluation"]["mesh"]["sha256"]
                                      for item in spec["objects"] if item.get("modeling")],
        "modeling_original_source_sha256": sorted({item["modeling"]["origin"]["source"]["sha256"]
                                      for item in spec["objects"] if item.get("modeling", {}).get("origin", {}).get("source")}),
        "mesh_source_sha256": sorted({item["mesh"]["source"]["sha256"] for item in spec["objects"]
                                      if item["type"] == "mesh" and item["mesh"].get("source")})}}
    if masters_manifest is not None:
        masters_digest = _sha256(masters)
        result.update(masters_path=str(masters), masters_sha256=masters_digest, masters_manifest=masters_manifest)
        result['provenance'].update(scene_linear_masters=True, masters_sha256=masters_digest,
                                    master_color_space='Linear Rec.709', master_sample_type='float32',
                                    master_alpha='premultiplied', render_passes=spec['output']['passes'])
    progress(1)
    return result

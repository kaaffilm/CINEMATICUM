"""Data-only scene authoring and real Blender rendering for Studio.

The recipe is deliberately smaller than Blender's scene format. No recipe value
is evaluated as Python, a shader, an expression, a path, or a shell command.
The WebGL authoring view and renderer use Z-up coordinates, XYZ Euler rotations
in degrees, two-unit cube/plane/cylinder primitives, and unit-radius spheres.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from adapters import AdapterError, _BLENDER_TIMEOUT, _cancelled, _run_owned, _sha256, find_blender


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_COLOR = re.compile(r"#[a-fA-F0-9]{6}\Z")
MAX_OBJECTS = 96
MAX_LIGHTS = 16
MAX_FRAMES = 7200
INTERPOLATIONS = frozenset({"linear", "constant", "ease_in", "ease_out", "ease_in_out"})
POSE_FIELDS = {
    "object": {"position": ([-0., 0., 1.], -1000, 1000), "rotation": ([0., 0., 0.], -3600, 3600),
               "scale": ([1., 1., 1.], .01, 100)},
    "camera": {"position": ([7., -9., 6.], -1000, 1000), "target": ([0., 0., 1.], -1000, 1000),
               "fov": (45., 10, 100)},
    "light": {"position": ([3., -4., 7.], -1000, 1000), "target": ([0., 0., 0.], -1000, 1000),
              "power": (1000., 0, 10000), "size": (4., .01, 100)},
}


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
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


def default_scene(width=1280, height=720):
    """A camera and lighting setup; nothing is passed off as user-made footage."""
    return {"version": 1, "width": width, "height": height, "frame_end": 96, "samples": 32,
            "world": {"color": "#263142", "strength": 0.35},
            "camera": {"position": [7, -9, 6], "target": [0, 0, 1], "fov": 45},
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
        "version", "width", "height", "frame_end", "samples", "world", "camera", "objects", "lights"}))
    if src.get("version") != 1 or isinstance(src.get("version"), bool):
        raise ValueError("Unsupported 3D scene recipe version.")
    src["width"] = _number(src.get("width", 1280) if width is None else width, "Scene width", 16, 8192, True)
    src["height"] = _number(src.get("height", 720) if height is None else height, "Scene height", 16, 8192, True)
    if src["width"] % 2 or src["height"] % 2 or src["width"] * src["height"] > 16_777_216:
        raise ValueError("Scene dimensions must be even and at most 16.7 million pixels.")
    src["frame_end"] = _number(src.get("frame_end", 96), "Scene end frame", 1, MAX_FRAMES, True)
    src["samples"] = _number(src.get("samples", 32), "Render samples", 4, 256, True)
    world = _object(src.setdefault("world", {}), "World", {"color", "strength"})
    world["color"] = _color(world.get("color", "#263142"), "World color")
    world["strength"] = _number(world.get("strength", .35), "World strength", 0, 5)
    camera = _object(src.setdefault("camera", {}), "Camera", {"position", "target", "fov", "keyframes"})
    camera["position"] = _vector(camera.get("position", [7, -9, 6]), "Camera position", -1000, 1000)
    camera["target"] = _vector(camera.get("target", [0, 0, 1]), "Camera target", -1000, 1000)
    camera["fov"] = _number(camera.get("fov", 45), "Vertical field of view", 10, 100)
    if sum((a - b) ** 2 for a, b in zip(camera["position"], camera["target"])) < .0001:
        raise ValueError("Camera position and target must differ.")
    _keyframes(camera, "camera", src["frame_end"])
    for key, limit in (("objects", MAX_OBJECTS), ("lights", MAX_LIGHTS)):
        if not isinstance(src.get(key, []), list) or len(src.get(key, [])) > limit:
            raise ValueError("Scene %s must be a list with at most %d items." % (key, limit))
        src.setdefault(key, [])
    identifiers = set()
    for obj in src["objects"]:
        _object(obj, "Scene object", {"id", "name", "type", "position", "rotation", "scale", "material", "keyframes"})
        ident = _id(obj.get("id"), "Object ID")
        if ident in identifiers:
            raise ValueError("Scene IDs must be unique.")
        identifiers.add(ident)
        obj["name"] = _name(obj.get("name", "Object"), "Object")
        if obj.get("type") not in {"cube", "sphere", "plane", "cylinder"}:
            raise ValueError("Choose a cube, sphere, plane, or cylinder primitive.")
        for prop, default, low, high in (("position", [0, 0, 1], -1000, 1000),
                                         ("rotation", [0, 0, 0], -3600, 3600), ("scale", [1, 1, 1], .01, 100)):
            obj[prop] = _vector(obj.get(prop, default), "Object " + prop, low, high)
        mat = _object(obj.setdefault("material", {}), "Material", {"color", "roughness", "metallic"})
        mat["color"] = _color(mat.get("color", "#d8a85f"), "Material color")
        mat["roughness"] = _number(mat.get("roughness", .45), "Roughness", 0, 1)
        mat["metallic"] = _number(mat.get("metallic", 0), "Metallic", 0, 1)
        _keyframes(obj, "object", src["frame_end"])
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
    payload = json.dumps(spec, ensure_ascii=True, allow_nan=False, sort_keys=True)
    return '''import bpy, json, math
from mathutils import Vector
SPEC = json.loads(%r)
BLEND_PATH = %r
FRAMES = %r
FPS = %r
START = %r
END = %r
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = SPEC['samples']
scene.cycles.use_denoising = True
scene.render.resolution_x = SPEC['width']
scene.render.resolution_y = SPEC['height']
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.render.fps_base = 1
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '16'
scene.render.film_transparent = False
scene.render.use_file_extension = True
scene.frame_start = START
scene.frame_end = END
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
def linearize_action(obj):
    action = obj.animation_data.action
    curves = []
    # Blender 4.4+ stores curves in channelbags on layered Actions. Each
    # authored object owns a newly created Action, so all its bags are ours.
    for layer in getattr(action, 'layers', ()):
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', ()):
                curves.extend(bag.fcurves)
    if not curves:
        curves.extend(getattr(action, 'fcurves', ()))
    if not curves:
        raise RuntimeError('Blender did not expose the authored animation curves.')
    for curve in curves:
        curve.extrapolation = 'CONSTANT'
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'
def action_curves(obj):
    action = obj.animation_data.action
    curves = []
    for layer in getattr(action, 'layers', ()):
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', ()):
                curves.extend(bag.fcurves)
    if not curves: curves.extend(getattr(action, 'fcurves', ()))
    return curves
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
def tracking_target(obj, name, position):
    target = bpy.data.objects.new(name, None)
    scene.collection.objects.link(target)
    target.location = position
    target.empty_display_type = 'PLAIN_AXES'
    target.empty_display_size = .3
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
camera_data.sensor_height = 24
camera_data.lens = 12 / math.tan(math.radians(SPEC['camera']['fov'])/2)
camera_data.clip_start = .05
camera_data.clip_end = 5000
camera = bpy.data.objects.new('Render Camera', camera_data)
scene.collection.objects.link(camera)
camera.location = SPEC['camera']['position']
aim(camera, SPEC['camera']['target'])
scene.camera = camera
camera_poses = recipe_poses(SPEC['camera'], ('position','target','fov'))
camera_target = tracking_target(camera, 'Camera aim', SPEC['camera']['target'])
if SPEC['camera'].get('keyframes'):
    for frame,pose in camera_poses:
        camera.location = pose['position']
        camera_target.location = pose['target']
        camera.keyframe_insert(data_path='location', frame=frame)
        camera_target.keyframe_insert(data_path='location', frame=frame)
    interpolate_action(camera, camera_poses)
    interpolate_action(camera_target, camera_poses)
    # FOV-to-lens conversion is nonlinear. Bake integer frames so re-opening
    # the saved .blend reproduces the authored camera at every rendered frame.
    for frame in range(1, SPEC['frame_end']+1):
        camera_data.lens = 12 / math.tan(math.radians(pose_at(camera_poses, frame)['fov'])/2)
        camera_data.keyframe_insert(data_path='lens', frame=frame)
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
    camera.location = camera_pose['position']
    camera_target.location = camera_pose['target']
    camera_data.lens = 12 / math.tan(math.radians(camera_pose['fov'])/2)
    aim(camera, camera_pose['target'])
    for light,light_target,poses,size_path,size_factor in lights:
        pose = pose_at(poses, frame)
        light.location = pose['position']
        light.data.energy = pose['power']
        setattr(light.data, size_path, pose['size']*size_factor)
        if light_target:
            light_target.location = pose['target']
            aim(light, pose['target'])
    scene.render.filepath = FRAMES + '/frame_%%06d.png' %% frame
    bpy.ops.render.render(write_still=True)
''' % (payload, str(blend_path), str(frames_dir), fps, frame_start, frame_end)


def render_scene(scene, output_dir, fps=24, frame_start=1, frame_end=None,
                 progress=lambda value: None, cancel_event=None):
    """Build the authored scene in Blender, render frames, and encode actual MP4."""
    _cancelled(cancel_event)
    spec = validate_scene(scene)
    if not spec["objects"]:
        raise ValueError("Add at least one object before rendering the 3D scene.")
    fps = _number(fps, "Scene frame rate", 1, 60, True)
    start = _number(frame_start, "Start frame", 1, spec["frame_end"], True)
    end = _number(spec["frame_end"] if frame_end is None else frame_end, "End frame", start, spec["frame_end"], True)
    binary, ffmpeg = find_blender(), shutil.which("ffmpeg")
    if not binary or not ffmpeg:
        raise AdapterError("Blender and FFmpeg are required to render the authored 3D scene.")
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    ident = uuid.uuid4().hex
    movie, blend = target / ("scene-" + ident + ".mp4"), target / ("scene-" + ident + ".blend")
    total = end - start + 1
    progress(0)
    with tempfile.TemporaryDirectory(prefix=".scene-", dir=str(target)) as temporary:
        work = Path(temporary)
        frames = work / "frames"
        frames.mkdir()
        source = work / "authored.blend"
        script = work / "build_scene.py"
        script.write_text(_build_script(spec, source, frames, fps, start, end), encoding="utf-8")
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
        _run_owned([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-n", "-framerate", str(fps),
                    "-start_number", str(start), "-i", str(frames / "frame_%06d.png"), "-frames:v", str(total),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(encoded)], work / "encode.log", cancel_event, _BLENDER_TIMEOUT)
        if not encoded.is_file() or not encoded.stat().st_size:
            raise AdapterError("The authored scene did not produce a nonempty encoded movie.")
        _cancelled(cancel_event)
        # The caller probes/adopts this movie before exposing it as timeline media.
        os.replace(str(source), str(blend))
        try:
            os.replace(str(encoded), str(movie))
        except BaseException:
            blend.unlink(missing_ok=True)
            raise
    progress(1)
    return {"path": str(movie), "scene_path": str(blend), "provenance": {
        "backend": "blender-authored-scene", "renderer": "Cycles CPU", "scene_version": 1,
        "recipe_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "output_sha256": _sha256(movie), "scene_sha256": _sha256(blend), "frame_start": start,
        "frame_end": end, "frame_end_inclusive": True, "fps": fps, "autoexec_enabled": False,
        "objects": len(spec["objects"]), "lights": len(spec["lights"]), "viewport_is_approximate": True}}

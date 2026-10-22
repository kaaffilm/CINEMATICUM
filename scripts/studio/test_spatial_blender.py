#!/usr/bin/env python3
"""Real OBJ import → saved Blender geometry → decoded video acceptance.

Run: python3 test_spatial_blender.py --output /path/to/ENGINE_TEST_spatial
The generated pyramid is test geometry. It is never presented as user footage.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from adapters import find_blender
from engine import probe_media
from scene import default_scene, pose_at, render_scene, validate_scene
from spatial_import import import_obj


OBJ = """mtllib ENGINE_TEST.mtl
o ENGINE TEST pyramid
v -1 -1 0
v 1 -1 0
v 1 1 0
v -1 1 0
v 0 0 2
vt 0 0
vt 1 0
vt 1 1
vt 0 1
vt .5 .5
vn 0 -.8 .6
usemtl Copper
f 1/1/1 2/2/1 5/5/1
f 2/1 3/2 5/5
f 3/1 4/2 5/5
f 4/1 1/2 5/5
usemtl BlueBase
f 4/4 3/3 2/2 1/1
"""
MTL = """newmtl Copper
Kd .7 .17 .04
Pr .3
Pm .65
newmtl BlueBase
Kd .02 .1 .6
Pr .6
Pm .1
"""


def fixture():
    imported = import_obj({"name": "ENGINE_TEST.obj", "obj": OBJ, "materials": {"ENGINE_TEST.mtl": MTL}})
    spec = default_scene(96, 64)
    spec.update(frame_end=3, samples=4)
    spec["objects"] = imported["objects"]
    for obj in spec["objects"]:
        obj["keyframes"] = [{"frame": 1, "interpolation": "ease_in"},
                            {"frame": 3, "position": [1.2, 0, 0], "rotation": [0, 0, 45], "scale": [1.2, .8, 1]}]
    spec["camera"].update(position=[5, -7, 4], target=[0, 0, .7])
    return validate_scene(spec)


def close(actual, expected, tolerance=3e-4):
    if isinstance(expected, (tuple, list)):
        return len(actual) == len(expected) and all(close(a, b, tolerance) for a, b in zip(actual, expected))
    return abs(actual - expected) <= tolerance


def linear_color(value):
    values = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in values]


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = find_blender()
    if not binary or not shutil.which("ffmpeg"):
        return {"status": "skipped", "reason": "Actual Blender and FFmpeg are required; no render was claimed."}
    result = {"passed": False, "fixture": "ENGINE TEST imported pyramid geometry — not a film", "checks": {}}
    checks = result["checks"]
    try:
        spec = fixture()
        rate = {"numerator": 24000, "denominator": 1001}
        rendered = render_scene(spec, output, fps=rate)
        result["render"] = rendered
        metadata = probe_media(rendered["path"])
        checks["three_real_movie_frames"] = metadata["frames"] == 3 and (metadata["width"], metadata["height"]) == (96, 64)
        checks["exact_frame_rate_provenance"] = rendered["provenance"]["frame_rate"] == rate
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate", "-of", "json", rendered["path"]], capture_output=True, text=True, check=True, timeout=5)
        stream = json.loads(probe.stdout)["streams"][0]
        checks["encoded_clock_is_24000_over_1001"] = stream["r_frame_rate"] == "24000/1001" and stream["avg_frame_rate"] == "24000/1001"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", rendered["path"], "-map", "0:v:0", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], check=True, capture_output=True, timeout=10).stdout
        frame_bytes = 96 * 64 * 3
        checks["decoded_three_frames"] = len(raw) == frame_bytes * 3
        checks["mesh_animation_changes_picture"] = len(raw) == frame_bytes * 3 and sum(abs(a-b) > 8 for a, b in zip(raw[:frame_bytes], raw[-frame_bytes:])) > 80
        replay_path = output / "ENGINE_TEST_saved_meshes.json"
        with tempfile.TemporaryDirectory(prefix="cinematicum-spatial-TEST-") as temporary:
            script = Path(temporary) / "inspect_saved_geometry.py"
            script.write_text("""import bpy, json, math
scene = bpy.context.scene
objects = []
for obj in scene.objects:
    if not obj.get('cinematicum_geometry_sha256'): continue
    mesh = obj.data
    material = mesh.materials[0]
    shader = material.node_tree.nodes.get('Principled BSDF')
    samples = []
    for frame in (1, 2, 3):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        samples.append({'frame':frame, 'position':list(obj.location), 'rotation':[math.degrees(v) for v in obj.rotation_euler], 'scale':list(obj.scale)})
    objects.append({'id':obj['cinematicum_id'], 'type':obj.type,
        'vertices':[list(v.co) for v in mesh.vertices], 'triangles':[list(face.vertices) for face in mesh.polygons],
        'uvs':[list(loop.uv) for loop in mesh.uv_layers.active.data],
        'normals':[list(normal.vector) for normal in mesh.corner_normals],
        'geometry_sha256':obj['cinematicum_geometry_sha256'], 'source_sha256':obj['cinematicum_source_sha256'],
        'color':list(shader.inputs['Base Color'].default_value)[:3],
        'roughness':shader.inputs['Roughness'].default_value, 'metallic':shader.inputs['Metallic'].default_value,
        'samples':samples})
with open(%r, 'w') as handle:
    json.dump({'objects':objects, 'recipe':json.loads(bpy.data.texts['CINEMATICUM Scene Recipe.json'].as_string()),
               'fps':scene.render.fps, 'fps_base':scene.render.fps_base},handle)
""" % str(replay_path), encoding="utf-8")
            process = subprocess.run([binary, "--background", "--factory-startup", "--disable-autoexec", rendered["scene_path"],
                                      "--python-exit-code", "1", "--python", str(script)], capture_output=True, text=True, timeout=45)
            if process.returncode:
                raise RuntimeError("Saved geometry replay failed: " + (process.stderr or process.stdout)[-2000:])
        replay = json.loads(replay_path.read_text())
        actual = {obj["id"]: obj for obj in replay["objects"]}
        checks["two_real_mesh_objects"] = len(actual) == 2 and all(obj["type"] == "MESH" for obj in actual.values())
        checks["saved_recipe_matches_authored_scene"] = replay["recipe"] == spec
        checks["saved_blender_clock_is_exact_ratio"] = replay["fps"] == 24 and abs(replay["fps_base"] - 1.001) < 1e-6
        checks.update({name: True for name in ("vertices_and_topology_preserved", "corner_uvs_preserved", "custom_and_flat_normals_preserved",
                                               "solid_materials_preserved", "source_and_geometry_hashes_preserved", "saved_mesh_animation_matches_recipe")})
        for expected in spec["objects"]:
            obj, mesh = actual[expected["id"]], expected["mesh"]
            checks["vertices_and_topology_preserved"] &= close(obj["vertices"], mesh["vertices"]) and obj["triangles"] == mesh["triangles"]
            checks["corner_uvs_preserved"] &= close(obj["uvs"], [mesh["uvs"][i] for face in mesh["uv_indices"] for i in face])
            checks["custom_and_flat_normals_preserved"] &= close(obj["normals"], [mesh["normals"][i] for face in mesh["normal_indices"] for i in face], tolerance=.002)
            checks["solid_materials_preserved"] &= close(obj["color"], linear_color(expected["material"]["color"])) and close(obj["roughness"], expected["material"]["roughness"]) and close(obj["metallic"], expected["material"]["metallic"])
            checks["source_and_geometry_hashes_preserved"] &= obj["geometry_sha256"] == mesh["sha256"] and obj["source_sha256"] == mesh["source"]["sha256"]
            checks["saved_mesh_animation_matches_recipe"] &= all(all(close(sample[prop], value) for prop, value in pose_at(expected, sample["frame"]).items()) for sample in obj["samples"])
        result["saved_scene_replay"] = str(replay_path)
        result["passed"] = all(checks.values())
        if not result["passed"]:
            result["error"] = "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
    except Exception as error:
        result["error"] = str(error)
    (output / "ENGINE_TEST_spatial_render_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    result = run(parser.parse_args().output)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get("passed") or result.get("status") == "skipped" else 1)

#!/usr/bin/env python3
"""Real headless render and saved-scene replay acceptance. Test geometry only.

Run: python3 test_scene_motion_blender.py --output /path/to/ENGINE_TEST_evidence
No embedded editor, mock process, or viewport screenshot is used as render proof.
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
from scene import camera_basis_at, default_scene, pose_at, render_scene, validate_scene


def fixture():
    spec = default_scene(96, 54)
    spec.update(frame_end=9, samples=4)
    spec["objects"] = [{"id": "ENGINE_TEST_cube", "name": "ENGINE TEST motion cube", "type": "cube",
                        "position": [0, 0, 1], "rotation": [0, 0, 0], "scale": [1, 1, 1],
                        "material": {"color": "#4d9bd8", "roughness": .35, "metallic": .2},
                        "keyframes": [{"frame": 1, "interpolation": "ease_in_out"},
                                      {"frame": 9, "position": [2, 0, 1], "rotation": [0, 0, 90], "scale": [1.3, 1, 1]}]}]
    spec["camera"]["keyframes"] = [{"frame": 1, "interpolation": "ease_in"},
                                     {"frame": 9, "position": [8, -8, 5], "target": [1, 0, 1], "fov": 55}]
    spec["lights"][0]["keyframes"] = [{"frame": 1, "interpolation": "ease_out"},
                                        {"frame": 9, "position": [2, -3, 6], "power": 1500, "size": 3}]
    return validate_scene(spec)


def close(actual, expected):
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(close(a, b) for a, b in zip(actual, expected))
    return abs(actual - expected) <= 2e-4


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = find_blender()
    if not binary or not shutil.which("ffmpeg"):
        return {"status": "skipped", "reason": "Actual Blender and FFmpeg are required; no render was claimed."}
    spec = fixture()
    result = {"passed": False, "fixture": "ENGINE TEST geometry — not a film", "checks": {}}
    checks = result["checks"]
    try:
        rendered = render_scene(spec, output, fps=12)
        result["render"] = rendered
        metadata = probe_media(rendered["path"])
        checks["nine_real_movie_frames"] = metadata["frames"] == 9 and (metadata["width"], metadata["height"]) == (96, 54)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", rendered["path"], "-map", "0:v:0",
                              "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], check=True,
                             capture_output=True, timeout=10).stdout
        size = 96 * 54 * 3
        checks["decoded_nine_frames"] = len(raw) == size * 9
        checks["authored_animation_changes_picture"] = len(raw) == size * 9 and sum(abs(a-b) > 10 for a, b in zip(raw[:size], raw[-size:])) > 100
        replay_path = output / "ENGINE_TEST_saved_scene_poses.json"
        with tempfile.TemporaryDirectory(prefix="cinematicum-motion-TEST-") as temporary:
            script = Path(temporary) / "inspect_saved_scene.py"
            script.write_text("""import bpy, json, math
from mathutils import Vector
scene = bpy.context.scene
cube = next(obj for obj in scene.objects if obj.get('cinematicum_id') == 'ENGINE_TEST_cube')
camera = scene.camera
target = bpy.data.objects['Camera aim']
light = bpy.data.objects['Key light']
light_target = bpy.data.objects['Key light aim']
samples = []
for frame in (1, 3, 5, 7, 9):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    backward=(camera.location-target.location).normalized()
    up=Vector((0,0,1))
    if abs(backward.dot(up))>.999: up=Vector((0,1,0))
    right=up.cross(backward).normalized()
    up=backward.cross(right)
    actual_right=camera.matrix_world.to_3x3().col[0]
    ratio=scene.render.pixel_aspect_y/scene.render.pixel_aspect_x
    samples.append({'frame':frame,
        'camera_basis':{'right':list(camera.matrix_world.to_3x3().col[0]), 'up':list(camera.matrix_world.to_3x3().col[1]), 'backward':list(camera.matrix_world.to_3x3().col[2])},
        'object':{'position':list(cube.location), 'rotation':[math.degrees(v) for v in cube.rotation_euler], 'scale':list(cube.scale)},
        'camera':{'position':list(camera.location), 'target':list(target.location), 'fov':math.degrees(2*math.atan(camera.data.sensor_height/(2*camera.data.lens))),
                  'roll':math.degrees(math.atan2(actual_right.dot(up),actual_right.dot(right))),
                  'shift_x':-camera.data.shift_x*scene.render.resolution_y/scene.render.resolution_x*ratio,
                  'shift_y':-camera.data.shift_y,'focal_ratio':ratio,
                  'focus_distance':camera.data.dof.focus_distance,'f_stop':camera.data.dof.aperture_fstop},
        'light':{'position':list(light.location), 'target':list(light_target.location), 'power':light.data.energy, 'size':light.data.size}})
with open(%r, 'w') as handle:
    json.dump({'samples':samples, 'recipe':json.loads(bpy.data.texts['CINEMATICUM Scene Recipe.json'].as_string())},handle)
""" % str(replay_path), encoding="utf-8")
            process = subprocess.run([binary, "--background", "--factory-startup", "--disable-autoexec", rendered["scene_path"],
                                      "--python-exit-code", "1", "--python", str(script)], capture_output=True, text=True, timeout=45)
            if process.returncode:
                raise RuntimeError("Saved Blender scene replay failed: " + (process.stderr or process.stdout)[-1800:])
        replay = json.loads(replay_path.read_text())
        checks["saved_recipe_matches_authored_scene"] = replay["recipe"] == spec
        checks["saved_scene_has_five_evaluated_samples"] = len(replay["samples"]) == 5
        for kind, item in (("object", spec["objects"][0]), ("camera", spec["camera"]), ("light", spec["lights"][0])):
            checks[kind + "_saved_animation_matches_recipe"] = all(
                all(close(sample[kind][prop], value) for prop, value in pose_at(item, sample["frame"], kind).items()
                    if kind != 'camera' or prop != 'roll')
                for sample in replay["samples"])
        checks['saved_camera_orientation_matches_transport_and_roll'] = all(
            all(close(sample['camera_basis'][axis], camera_basis_at(spec['camera'], sample['frame'])[axis])
                for axis in ('right', 'up', 'backward')) for sample in replay['samples'])
        result["saved_scene_replay"] = str(replay_path)
        result["passed"] = all(checks.values())
        if not result["passed"]:
            result["error"] = "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
    except Exception as error:
        result["error"] = str(error)
    (output / "ENGINE_TEST_motion_render_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    result = run(parser.parse_args().output)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get("passed") or result.get("status") == "skipped" else 1)

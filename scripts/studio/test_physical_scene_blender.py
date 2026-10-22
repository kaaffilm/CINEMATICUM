#!/usr/bin/env python3
"""Actual Cycles physical camera/material render and retained-source acceptance.

Run with --output /path/to/ENGINE_TEST_physical_evidence. The fixture is synthetic
test geometry, never film footage. A second Blender process reopens the retained
source, examines evaluated properties/projections, and renders DOF on/off frames.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from adapters import find_blender
from scene import default_scene, focal_length_mm, pose_at, render_scene, validate_scene


def fixture():
    spec = default_scene(128, 96)
    spec.update(frame_end=2, samples=16)
    spec["world"] = {"color": "#000000", "strength": 0}
    spec["lights"] = []
    spec["render"].update(max_bounces=7, diffuse_bounces=3, glossy_bounces=5,
                          transmission_bounces=6, transparent_max_bounces=4,
                          use_denoising=False, seed=37)
    spec["camera"].update(position=[0, -4, 1], target=[0, 2, 1], fov=30,
                          sensor_height_mm=36, roll=17, shift_x=.07, shift_y=-.04,
                          focal_ratio=1.2, dof_enabled=True, focus_distance=2, f_stop=.4,
                          aperture_blades=7, aperture_rotation=15, aperture_ratio=1.3,
                          keyframes=[{"frame": 1, "interpolation": "ease_in"},
                                     {"frame": 2, "fov": 33, "roll": 21, "shift_x": .08,
                                      "focus_distance": 3, "f_stop": .5}])
    def panel(ident, x, y, z, sx, sz, color):
        return {"id": ident, "name": "ENGINE TEST " + ident, "type": "plane",
                "position": [x, y, z], "rotation": [90, 0, 0], "scale": [sx, sz, 1],
                "material": {"color": color, "roughness": .5, "metallic": 0,
                             "emission_color": color, "emission_strength": 1}, "keyframes": []}
    spec["objects"] = [panel("black_backdrop", 0, 2.01, 1, 1.8, 1.5, "#000000")]
    # High contrast emissive bars isolate lens blur from stochastic illumination.
    for index in range(-5, 6):
        spec["objects"].append(panel("white_bar_" + str(index + 5), index * .22, 2, 1, .035, 1.2, "#ffffff"))
    spec["objects"].append({"id": "glass", "name": "ENGINE TEST physical glass", "type": "sphere",
                            "position": [-.8, .2, .35], "rotation": [0, 0, 0], "scale": [.23, .23, .23],
                            "material": {"color": "#d2eaff", "roughness": .13, "metallic": .05,
                                         "transmission": .8, "ior": 1.47,
                                         "emission_color": "#ff9d45", "emission_strength": .25}, "keyframes": []})
    return validate_scene(spec)


def expected_pixel(camera, point, width, height):
    """Independent pinhole formula for the fixture's known +Y optical axis."""
    angle = math.radians(camera["roll"])
    x, depth, y = point[0], point[1] + 4, point[2] - 1
    rx = math.cos(angle) * x + math.sin(angle) * y
    uy = -math.sin(angle) * x + math.cos(angle) * y
    fy = height / (2 * math.tan(math.radians(camera["fov"]) / 2))
    return [width * (.5 + camera["shift_x"]) + fy * camera["focal_ratio"] * rx / depth,
            height * (.5 - camera["shift_y"]) - fy * uy / depth]


def close(a, b, tolerance=2e-4):
    return abs(a - b) <= tolerance


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = find_blender()
    if not binary or not shutil.which("ffmpeg"):
        return {"status": "skipped", "reason": "Actual Blender and FFmpeg are required; no physical-render proof claimed."}
    began = time.monotonic()
    result = {"passed": False, "fixture": "SYNTHETIC ENGINE TEST — NOT A FILM", "checks": {}}
    checks = result["checks"]
    spec = fixture()
    points = [[0, 0, 1], [-.2, .7, 1.5], [.7, 2, 1.2]]
    replay_file = output / "ENGINE_TEST_physical_saved_scene.json"
    try:
        rendered = render_scene(spec, output, fps=12)
        result["render"] = rendered
        checks["retained_source_and_real_movie"] = all(Path(rendered[k]).is_file() and Path(rendered[k]).stat().st_size > 1000 for k in ("path", "scene_path"))
        with tempfile.TemporaryDirectory(prefix="cinematicum-physical-TEST-") as temporary:
            inspect = Path(temporary) / "reopen_physical_scene.py"
            inspect.write_text('''import bpy, json, math
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
scene=bpy.context.scene
camera=scene.camera
samples=[]
for frame in (1,2):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    samples.append({'frame':frame, 'lens':camera.data.lens, 'sensor_height_mm':camera.data.sensor_height,
        'focus_distance':camera.data.dof.focus_distance,'f_stop':camera.data.dof.aperture_fstop,
        'dof':camera.data.dof.use_dof,'blades':camera.data.dof.aperture_blades,
        'aperture_rotation':math.degrees(camera.data.dof.aperture_rotation),
        'aperture_ratio':camera.data.dof.aperture_ratio,'pixel_aspect':[scene.render.pixel_aspect_x,scene.render.pixel_aspect_y],
        'projected':[list(world_to_camera_view(scene,camera,Vector(point))) for point in %r]})
glass=next(obj for obj in scene.objects if obj.get('cinematicum_id')=='glass')
shader=glass.data.materials[0].node_tree.nodes['Principled BSDF']
material={'roughness':shader.inputs['Roughness'].default_value,'metallic':shader.inputs['Metallic'].default_value,
          'transmission':(shader.inputs.get('Transmission Weight') or shader.inputs.get('Transmission')).default_value,
          'ior':shader.inputs['IOR'].default_value,'emission_strength':shader.inputs['Emission Strength'].default_value,
          'emission_color':list((shader.inputs.get('Emission Color') or shader.inputs.get('Emission')).default_value)[:3]}
render={key:getattr(scene.cycles,key) for key in %r}
scene.frame_set(1)
bpy.context.view_layer.update()
images=[]
for dof,name in ((True,'ENGINE_TEST_physical_dof.png'),(False,'ENGINE_TEST_physical_sharp.png')):
    camera.data.dof.use_dof=dof
    scene.render.filepath=%r+'/'+name
    bpy.ops.render.render(write_still=True)
    image=bpy.data.images.load(scene.render.filepath,check_existing=False)
    pixels=list(image.pixels)
    if len(pixels)!=%r*4: raise RuntimeError('Actual render pixels were unavailable.')
    rgb=[sum(pixels[i:i+3])/3 for i in range(0,len(pixels),4)]
    images.append(rgb)
    bpy.data.images.remove(image)
w=%r; h=%r
def energy(values):
    return sum(abs(values[y*w+x]-values[y*w+x-1])+abs(values[y*w+x]-values[(y-1)*w+x])
               for y in range(1,h) for x in range(1,w))/((h-1)*(w-1))
blur,sharp=images
metrics={'mean_absolute_difference':sum(abs(a-b) for a,b in zip(blur,sharp))/len(blur),
         'blur_edge_energy':energy(blur),'sharp_edge_energy':energy(sharp),
         'changed_pixels':sum(abs(a-b)>.05 for a,b in zip(blur,sharp))}
with open(%r,'w') as f:json.dump({'samples':samples,'material':material,'render':render,
    'metrics':metrics,'recipe':json.loads(bpy.data.texts['CINEMATICUM Scene Recipe.json'].as_string())},f)
''' % (points, list(spec["render"]), str(output), spec["width"] * spec["height"], spec["width"], spec["height"], str(replay_file)), encoding="utf-8")
            process = subprocess.run([binary, "--background", "--factory-startup", "--disable-autoexec", rendered["scene_path"],
                                      "--python-exit-code", "1", "--python", str(inspect)], capture_output=True, text=True, timeout=45)
            if process.returncode:
                raise RuntimeError("Retained physical scene replay failed: " + (process.stderr or process.stdout)[-2500:])
        replay = json.loads(replay_file.read_text())
        result["replay"] = str(replay_file)
        result["pixel_metrics"] = replay["metrics"]
        checks["saved_recipe_retains_all_physical_authorship"] = replay["recipe"] == spec
        checks["independent_blender_path_limits"] = replay["render"] == spec["render"]
        checks["independent_principled_material_values"] = all(close(replay["material"][k], spec["objects"][-1]["material"][k]) for k in ("roughness", "metallic", "transmission", "ior", "emission_strength"))
        srgb = [int(spec["objects"][-1]["material"]["emission_color"][i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in srgb]
        checks["emission_color_is_scene_linear"] = all(close(a, b) for a, b in zip(replay["material"]["emission_color"], linear))
        projection_errors = []
        for sample in replay["samples"]:
            frame = sample["frame"]
            camera = {**pose_at(spec["camera"], frame, "camera"), "focal_ratio": spec["camera"]["focal_ratio"]}
            checks["physical_lens_and_focus_frame_" + str(frame)] = (close(sample["lens"], focal_length_mm(spec["camera"], camera["fov"]))
                and close(sample["sensor_height_mm"], 36) and close(sample["focus_distance"], camera["focus_distance"])
                and close(sample["f_stop"], camera["f_stop"]) and sample["dof"]
                and sample["blades"] == 7 and close(sample["aperture_rotation"], 15) and close(sample["aperture_ratio"], 1.3))
            for point, actual in zip(points, sample["projected"]):
                expected = expected_pixel(camera, point, spec["width"], spec["height"])
                actual_pixels = [actual[0] * spec["width"], (1 - actual[1]) * spec["height"]]
                projection_errors.extend(abs(a-b) for a, b in zip(actual_pixels, expected))
        result["maximum_projection_error_pixels"] = max(projection_errors)
        checks["saved_blender_roll_shift_focal_ratio_match_calibrated_projection"] = max(projection_errors) < .002
        metrics = replay["metrics"]
        checks["rendered_depth_of_field_changes_actual_pixels"] = metrics["mean_absolute_difference"] > .015 and metrics["changed_pixels"] > 300
        checks["depth_of_field_blurs_high_contrast_detail"] = metrics["sharp_edge_energy"] > metrics["blur_edge_energy"] * 1.15
        checks["dof_comparison_pngs_exist"] = all((output / name).is_file() for name in ("ENGINE_TEST_physical_dof.png", "ENGINE_TEST_physical_sharp.png"))
        result["passed"] = bool(checks) and all(checks.values())
        if not result["passed"]:
            result["error"] = "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
    except Exception as error:
        result["error"] = str(error)
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    (output / "ENGINE_TEST_physical_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    result = run(parser.parse_args().output)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get("passed") or result.get("status") == "skipped" else 1)

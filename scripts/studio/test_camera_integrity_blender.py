#!/usr/bin/env python3
"""Bounded real-Blender camera/UV regression, using synthetic test geometry.

One process renders one 16x16 frame, reopens its saved .blend, and independently
inspects all camera frames plus the actual mesh UV loops. No production media
is read or modified. Run with --output /owned/ENGINE_TEST_camera_integrity.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from adapters import find_blender
from scene import _build_script, default_scene, validate_scene
from scene_modeling import prepare_operation
from spatial_import import import_obj


def run(output, timeout=16):
    binary = find_blender()
    if not binary:
        return {'status': 'skipped', 'reason': 'Actual Blender is required; no native render proof claimed.'}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    spec = default_scene(16, 16)
    spec.update(frame_end=9, samples=4)
    spec['render'].update(use_denoising=False, seed=37)
    spec['camera'].update(position=[.1, 0, -1], target=[0, 0, 0], keyframes=[
        {'frame': 1, 'interpolation': 'ease_in_out'}, {'frame': 9, 'position': [-.1, 0, -1]}])
    spec['objects'] = [{'id': 'integrity_cube', 'name': 'ENGINE TEST camera cube', 'type': 'cube',
                        'position': [0, 0, .2], 'scale': [.1, .1, .1]}]
    spec = validate_scene(spec)
    imported = import_obj({'name': 'ENGINE_TEST_uv.obj', 'obj':
        'v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n'
        'vt 0 0\nvt 1 0\nvt 1 1\nvt .25 .25\nvt .75 .75\nvt .25 .75\n'
        'f 1/1 2/2 3/3\nf 1/4 3/5 4/6\n'})['objects'][0]
    editable, _ = prepare_operation(imported, {'type': 'convert'})
    moved, _ = prepare_operation(editable, {'type': 'move_vertices', 'indices': [0], 'delta': [0, 0, .5]})
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM', 'checks': {}}
    checks = result['checks']
    invalid = default_scene(16, 16)
    invalid['frame_end'] = 3
    invalid['camera'].update(position=[0, 0, 1], target=[0, 0, 0],
                              keyframes=[{'frame': 3, 'position': [0, 0, -1]}])
    try:
        validate_scene(invalid)
        checks['undefined_complete_path_rejected_before_blender'] = False
    except ValueError as error:
        checks['undefined_complete_path_rejected_before_blender'] = 'between frames 1 and 3' in str(error)
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='cinematicum-integrity-TEST-', dir=str(output)) as temporary:
        work = Path(temporary)
        frames = work / 'frames'
        frames.mkdir()
        blend, replay, script = work/'test.blend', work/'replay.json', work/'render.py'
        source = _build_script(spec, blend, frames, 24, 1, 1)
        source += '''
# Independent replay from the saved datablocks; no recipe evaluator is called.
bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
scene = bpy.context.scene
camera = scene.camera
samples = []
for frame in (1, 3, 5, 7, 9):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    matrix = camera.matrix_world.to_3x3()
    samples.append({'frame': frame, 'right': list(matrix.col[0]), 'up': list(matrix.col[1]),
                    'backward': list(matrix.col[2]), 'position': list(camera.location)})
item = json.loads(%r)
obj = cinematicum_model_object(item, scene.collection)
bpy.context.view_layer.update()
uv = obj.data.uv_layers.active
corners = [[list(uv.data[loop].uv) for loop in polygon.loop_indices] for polygon in obj.data.polygons]
record = {'engine_version': bpy.app.version_string, 'samples': samples, 'uv_corners': corners,
          'source_frame_range': [scene.frame_start, scene.frame_end],
          'moved_vertex': list(obj.data.vertices[0].co),
          'saved_recipe': json.loads(bpy.data.texts['CINEMATICUM Scene Recipe.json'].as_string())}
with open(%r, 'w') as handle: json.dump(record, handle)
''' % (json.dumps(moved), str(replay))
        script.write_text(source, encoding='utf-8')
        process = subprocess.Popen([binary, '--background', '--factory-startup', '--disable-autoexec',
                                    '--python-exit-code', '1', '--python', str(script)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            log = process.communicate(timeout=timeout)[0]
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            log = process.communicate(timeout=1)[0]
            result['error'] = 'Native regression exceeded its bounded deadline.'
        result['returncode'] = process.returncode
        checks['real_subset_frame_rendered'] = len(list(frames.glob('frame_*.png'))) == 1
        checks['source_saved_and_reopened'] = blend.is_file() and replay.is_file() and process.returncode == 0
        if checks['source_saved_and_reopened']:
            record = json.loads(replay.read_text(encoding='utf-8'))
            result['engine_version'] = record['engine_version']
            result['replay'] = record
            checks['saved_recipe_preserves_orientation_policy'] = record['saved_recipe'] == spec
            checks['source_playback_range_keeps_full_authored_animation'] = record['source_frame_range'] == [1, spec['frame_end']]
            checks['saved_frames_cross_pole_without_roll_jump'] = all(
                max(abs(a-b) for a, b in zip(sample['right'], [0, 1, 0])) < 2e-6
                for sample in record['samples'])
            checks['saved_camera_aim_matches_authored_position'] = all(
                max(abs(a-b/math.hypot(*sample['position'])) for a, b in zip(sample['backward'], sample['position'])) < 2e-6
                for sample in record['samples'])
            expected = [[imported['mesh']['uvs'][i] for i in face] for face in imported['mesh']['uv_indices']]
            checks['real_blender_uv_seams_survive_vertex_deformation'] = record['uv_corners'] == expected
            checks['real_blender_vertex_is_deformed'] = record['moved_vertex'] == [0, 0, .5]
        else:
            result['log_tail'] = log.decode('utf-8', errors='replace')[-2500:]
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    result['passed'] = bool(checks) and all(checks.values())
    (output/'ENGINE_TEST_camera_integrity_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=16)
    args = parser.parse_args()
    result = run(args.output, min(17., max(1., args.timeout)))
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get('passed') or result.get('status') == 'skipped' else 1)

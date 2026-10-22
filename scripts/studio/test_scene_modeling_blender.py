#!/usr/bin/env python3
"""Actual topology → modifier viewport mesh → retained Blender → pixel proof.

All assets are synthetic ENGINE TEST geometry, never presented as film footage.
The reopened source is inspected by an independent Blender script, not by the
modeling evaluator used to produce the cached viewport mesh.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from adapters import find_blender
from scene import default_scene, render_scene, validate_scene
from scene_modeling import model_mesh
from spatial_import import validate_mesh


def close(a, b, tolerance=3e-5):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    return abs(a - b) <= tolerance


REPLAY_SOURCE = '''import bpy, json, math
from pathlib import Path
scene = bpy.context.scene
obj = next(o for o in scene.objects if o.get('cinematicum_id') == 'modeled')
scene.frame_set(1)
bpy.context.view_layer.update()
evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
data = evaluated.to_mesh()
data.calc_loop_triangles()
actual = {'vertices':[list(v.co) for v in data.vertices], 'triangles':[list(t.vertices) for t in data.loop_triangles]}
evaluated.to_mesh_clear()
modifiers = []
for m in obj.modifiers:
    item = {'type':m.type,'viewport':m.show_viewport,'render':m.show_render}
    if m.type=='MIRROR': item.update(axis=list(m.use_axis),bisect=list(m.use_bisect_axis),merge=m.merge_threshold)
    elif m.type=='BEVEL': item.update(width=m.width,segments=m.segments,angle=math.degrees(m.angle_limit))
    elif m.type=='SUBSURF': item.update(levels=m.levels,render_levels=m.render_levels,method=m.subdivision_type)
    modifiers.append(item)
record={'engine_version':bpy.app.version_string,'base_vertices':[list(v.co) for v in obj.data.vertices],
        'base_faces':[list(p.vertices) for p in obj.data.polygons], 'evaluated':actual, 'modifiers':modifiers,
        'geometry_sha256':obj.get('cinematicum_geometry_sha256'),
        'evaluated_geometry_sha256':obj.get('cinematicum_evaluated_geometry_sha256'),
        'recipe':json.loads(bpy.data.texts['CINEMATICUM Scene Recipe.json'].as_string())}
images=[]
for enabled,name in ((True,'ENGINE_TEST_modifiers_enabled.png'),(False,'ENGINE_TEST_modifiers_disabled.png')):
    for m in obj.modifiers: m.show_render=enabled
    scene.render.filepath=%r+'/'+name
    bpy.ops.render.render(write_still=True)
    image=bpy.data.images.load(scene.render.filepath,check_existing=False)
    pixels=list(image.pixels)
    images.append([sum(pixels[i:i+3])/3 for i in range(0,len(pixels),4)])
    bpy.data.images.remove(image)
on,off=images
record['pixel_metrics']={'mean_absolute_difference':sum(abs(a-b) for a,b in zip(on,off))/len(on),
                          'changed_pixels':sum(abs(a-b)>.04 for a,b in zip(on,off)), 'pixels':len(on)}
Path(%r).write_text(json.dumps(record),encoding='utf-8')
'''


STAGES = ('convert', 'edit', 'topology', 'modifiers', 'render', 'replay', 'forged')


def run(output, stage='all'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = find_blender()
    if not binary or not shutil.which('ffmpeg'):
        return {'status': 'skipped', 'reason': 'Actual Blender and FFmpeg are required; no mesh-render proof claimed.'}
    if stage == 'all':
        for step in STAGES:
            result = run(output, step)
            if not result.get('passed'):
                return result
        return result
    began = time.monotonic()
    checkpoint = output / 'ENGINE_TEST_modeling_checkpoint.json'
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM', 'checks': {}}
    state = {}
    try:
        if stage != 'convert':
            state = json.loads(checkpoint.read_text(encoding='utf-8'))
            expected = STAGES[STAGES.index(stage) - 1]
            if state.get('last_stage') != expected:
                raise ValueError('Run stage ' + expected + ' before ' + stage + '.')
            result = state['result']
            result.pop('error', None)
            result['passed'] = False
        checks = result['checks']
        if stage == 'convert':
            spec = default_scene(128, 128)
            spec.update(frame_end=1, samples=8)
            spec['render'].update(seed=73, use_denoising=False)
            spec['camera'].update(position=[6, -8, 5], target=[0, 0, 1.3], fov=35)
            spec['world'] = {'color': '#111820', 'strength': .2}
            spec['objects'] = [{'id': 'modeled', 'name': 'ENGINE TEST live mesh stack', 'type': 'cube',
                                'material': {'color': '#e6a24c', 'roughness': .4,
                                             'emission_color': '#e6a24c', 'emission_strength': .6}}]
            state['spec'] = validate_scene(spec)
            state['object'] = state['spec']['objects'][0]
        obj = state['object']
        def apply(operation):
            nonlocal obj
            obj = model_mesh({'object': obj, 'operation': operation})['object']
            return obj
        if stage == 'convert':
            apply({'type': 'convert'})
            state['original_digest'] = obj['mesh']['sha256']
            checks['actual_engine_evaluation_after_conversion'] = bool(obj['modeling']['evaluation']['engine_version']) and len(obj['modeling']['evaluation']['mesh']['triangles']) == 12
        elif stage == 'edit':
            apply({'type': 'move_vertices', 'indices': [0], 'delta': [-.3, 0, 0]})
            checks['vertex_move_changes_cage_and_hash'] = obj['mesh']['vertices'][0][0] == -1.3 and obj['mesh']['sha256'] != state['original_digest']
            apply({'type': 'extrude_face', 'face': 1, 'distance': .7})
            checks['real_extrusion_depth_and_faces'] = len(obj['modeling']['faces']) == 10 and max(v[2] for v in obj['mesh']['vertices']) == 1.7
        elif stage == 'topology':
            apply({'type': 'subdivide_faces', 'faces': [1]})
            checks['real_subdivision_adds_connected_control_geometry'] = len(obj['modeling']['faces']) == 13 and len(obj['mesh']['vertices']) == 17
            before_delete = copy.deepcopy(obj)
            apply({'type': 'delete_faces', 'faces': [0]})
            checks['face_delete_reaches_evaluated_geometry'] = len(obj['modeling']['faces']) == 12 and len(obj['modeling']['evaluation']['mesh']['triangles']) < len(before_delete['modeling']['evaluation']['mesh']['triangles'])
            obj = before_delete
            state['base'] = copy.deepcopy(obj['mesh'])
        elif stage == 'modifiers':
            apply({'type': 'set_modifiers', 'modifiers': [
                {'id': 'symmetric', 'type': 'mirror', 'axis': 'X', 'bisect': True, 'flip': False, 'merge_distance': .001},
                {'id': 'rounded_edges', 'type': 'bevel', 'width': .18, 'segments': 3, 'angle': 28},
                {'id': 'smooth_surface', 'type': 'subdivision', 'levels': 1, 'method': 'CATMULL_CLARK'}]})
            evaluated = obj['modeling']['evaluation']['mesh']
            checks['modifiers_preserve_editable_base'] = obj['mesh'] == state['base']
            checks['actual_modifier_geometry_differs_from_cage'] = evaluated['sha256'] != state['base']['sha256'] and len(evaluated['vertices']) > len(state['base']['vertices'])
        elif stage == 'render':
            state['spec']['objects'] = [obj]
            state['spec'] = validate_scene(state['spec'])
            rendered = render_scene(state['spec'], output / 'render', fps=12)
            result['render'] = rendered
            checks['real_movie_and_retained_source'] = all(Path(rendered[key]).is_file() and Path(rendered[key]).stat().st_size > 1000 for key in ('path', 'scene_path'))
        elif stage == 'replay':
            rendered = result['render']
            inspection = output / 'ENGINE_TEST_modeling_reopened.json'
            with tempfile.TemporaryDirectory(prefix='cinematicum-modeling-independent-TEST-') as temporary:
                script = Path(temporary) / 'inspect_and_render.py'
                script.write_text(REPLAY_SOURCE % (str(output), str(inspection)), encoding='utf-8')
                process = subprocess.run([binary, '--background', '--factory-startup', '--disable-autoexec', rendered['scene_path'],
                                          '--python-exit-code', '2', '--python', str(script)], capture_output=True, text=True, timeout=120)
                if process.returncode:
                    raise RuntimeError('Retained modeling replay failed: ' + (process.stderr or process.stdout)[-2000:])
            replay = json.loads(inspection.read_text(encoding='utf-8'))
            evaluated, base = obj['modeling']['evaluation']['mesh'], state['base']
            checks['independent_reopened_base_cage_matches'] = close(replay['base_vertices'], obj['mesh']['vertices']) and replay['base_faces'] == obj['modeling']['faces']
            checks['independent_reopened_evaluated_geometry_matches_viewport'] = close(replay['evaluated']['vertices'], evaluated['vertices']) and replay['evaluated']['triangles'] == evaluated['triangles']
            checks['three_actual_live_modifiers_retained'] = [m['type'] for m in replay['modifiers']] == ['MIRROR', 'BEVEL', 'SUBSURF'] and all(m['viewport'] and m['render'] for m in replay['modifiers'])
            mirror, bevel, subdivision = replay['modifiers']
            checks['retained_modifier_settings_match_authorship'] = (mirror['axis'] == [True, False, False] and mirror['bisect'] == [True, False, False]
                and abs(mirror['merge'] - .001) < 1e-7 and abs(bevel['width'] - .18) < 1e-6 and bevel['segments'] == 3
                and abs(bevel['angle'] - 28) < .001 and subdivision['levels'] == subdivision['render_levels'] == 1 and subdivision['method'] == 'CATMULL_CLARK')
            checks['retained_recipe_and_both_hashes_match'] = replay['recipe'] == state['spec'] and replay['geometry_sha256'] == base['sha256'] and replay['evaluated_geometry_sha256'] == evaluated['sha256']
            checks['same_actual_engine_version'] = replay['engine_version'] == obj['modeling']['evaluation']['engine_version']
            metrics = replay['pixel_metrics']
            checks['modifiers_materially_change_real_rendered_pixels'] = metrics['pixels'] == 128 * 128 and metrics['changed_pixels'] > 100 and metrics['mean_absolute_difference'] > .005
            result['pixel_metrics'] = metrics
            result['engine_version'] = replay['engine_version']
        elif stage == 'forged':
            # A fresh checksum must not make a forged viewport cache pass.
            forged = copy.deepcopy(state['spec'])
            bad = forged['objects'][0]['modeling']['evaluation']['mesh']
            bad['vertices'][0][0] += .04
            bad.pop('sha256')
            forged['objects'][0]['modeling']['evaluation']['mesh'] = validate_mesh(bad)
            checks['forged_viewport_mesh_rejected_by_real_render'] = False
            try:
                render_scene(forged, output / 'forged_must_fail', fps=12)
            except Exception as error:
                checks['forged_viewport_mesh_rejected_by_real_render'] = 'differs from the saved viewport' in str(error) and not list((output / 'forged_must_fail').glob('*.mp4'))
        result['passed'] = bool(checks) and all(checks.values())
        result['stage'] = stage
        result['complete'] = stage == 'forged' and result['passed']
        result['status'] = 'complete' if result['complete'] else 'checkpoint'
        result['next_stage'] = STAGES[STAGES.index(stage) + 1] if stage != 'forged' else None
        if not result['passed']:
            result['error'] = 'Failed checks: ' + ', '.join(key for key, value in checks.items() if not value)
        else:
            state.update(object=obj, last_stage=stage, result=result)
            checkpoint.write_text(json.dumps(state, indent=2), encoding='utf-8')
    except Exception as error:
        result['passed'] = False
        result['error'] = str(error)
    result['stage_elapsed_seconds'] = round(time.monotonic() - began, 3)
    (output / 'ENGINE_TEST_modeling_render_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=('all', *STAGES), default='all')
    args = parser.parse_args()
    result = run(args.output, args.stage)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get('passed') or result.get('status') == 'skipped' else 1)

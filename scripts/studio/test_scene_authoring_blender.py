#!/usr/bin/env python3
"""Independent, bounded real-Blender acceptance for scene authoring.

Each stage launches one owned process and has a <=15.5 second deadline. The
geometry is explicitly synthetic acceptance material; no user project is read.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from adapters import find_blender
from render_devices import configure_cycles_device
import scene
import scene_modeling as modeling


def fixture():
    spec = scene.default_scene(16, 16)
    spec.update(frame_end=3, samples=4)
    spec['render'].update(use_denoising=False, seed=79)
    spec['objects'] = [
        {'id': 'child', 'name': 'ENGINE TEST child', 'type': 'cube', 'parent_id': 'parent',
         'position': [1, 2, 0], 'rotation': [0, 0, 30], 'scale': [.5, 2, 1]},
        {'id': 'parent', 'name': 'ENGINE TEST parent', 'type': 'cube',
         'position': [4, -2, 1], 'rotation': [0, 0, 90], 'scale': [2, 3, 1],
         'keyframes': [{'frame': 1, 'interpolation': 'ease_in_out'}, {'frame': 3, 'rotation': [0, 0, 180]}]},
        {'id': 'grandchild', 'name': 'ENGINE TEST grandchild', 'type': 'sphere',
         'parent_id': 'child', 'position': [-1, 0, 2]},
    ]
    return scene.validate_scene(spec)


def hierarchy_script(work, output):
    spec = fixture()
    frames = work/'frames'
    frames.mkdir()
    blend = output/'ENGINE_TEST_hierarchy.blend'
    result = work/'result.json'
    source = scene._build_script(spec, blend, frames, 24, 1, 1)
    source += '''
bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
scene = bpy.context.scene
by_id = {obj.get('cinematicum_id'): obj for obj in scene.objects if obj.get('cinematicum_id')}
samples = []
for moment in (1., 1.5, 2., 2.75, 3.):
    integer = math.floor(moment)
    scene.frame_set(integer, subframe=moment-integer)
    bpy.context.view_layer.update()
    samples.append({'frame': moment, 'objects': {key: [obj.matrix_world[r][c] for c in range(4) for r in range(4)] for key,obj in by_id.items()}})
record = {'engine_version': bpy.app.version_string, 'samples': samples,
          'parents': {key: obj.parent.get('cinematicum_id') if obj.parent else None for key,obj in by_id.items()},
          'device': json.loads(scene['cinematicum_render_device']),
          'recipe': json.loads(bpy.data.texts['CINEMATICUM Scene Recipe.json'].as_string())}
with open(%r, 'w') as handle: json.dump(record, handle)
''' % str(result)
    return source, result, {'spec': spec, 'blend': blend, 'frames': frames}


def modeling_script(work, output):
    cube = scene.default_scene()
    cube['objects'] = [{'id': 'uv_cube', 'name': 'ENGINE TEST UV cube', 'type': 'cube'}]
    base = modeling.prepare_operation(scene.validate_scene(cube)['objects'][0], {'type': 'convert'})[0]
    projected = modeling.prepare_operation(base, {'type': 'uv_project', 'method': 'box'})[0]
    projected = modeling.prepare_operation(projected, {'type': 'uv_transform', 'indices': [0, 1], 'delta': [.05, -.02]})[0]
    candidates = []
    for kind in ('array', 'solidify', 'decimate', 'smooth', 'simple_deform'):
        candidate = copy.deepcopy(base)
        candidate['id'] = 'test_' + kind
        candidate['name'] = 'ENGINE TEST ' + kind
        if kind == 'solidify':
            plane = scene.default_scene()
            plane['objects'] = [{'id': 'test_solidify', 'name': 'ENGINE TEST solidify', 'type': 'plane'}]
            candidate = modeling.prepare_operation(scene.validate_scene(plane)['objects'][0], {'type': 'convert'})[0]
        values = {'array': {'count': 2, 'offset': [3, 0, 0]}, 'solidify': {'thickness': .3},
                  'decimate': {'ratio': .5}, 'smooth': {'factor': .5},
                  'simple_deform': {'angle': 90}}[kind]
        candidate = modeling.prepare_operation(candidate, {'type': 'set_modifiers', 'modifiers': [{'id': kind, 'type': kind, **values}]})[0]
        candidates.append(candidate)
    result = work/'result.json'
    source = modeling.blender_modeling_source() + '\n'
    source += '''
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
projected = json.loads(%r)
obj = cinematicum_model_object(projected, bpy.context.scene.collection)
obj['cinematicum_id'] = 'projected'
uv = obj.data.uv_layers.active
corners = [[list(uv.data[loop].uv) for loop in polygon.loop_indices] for polygon in obj.data.polygons]
unwrapped = cinematicum_model_object(json.loads(%r), bpy.context.scene.collection)
unwrapped['cinematicum_id'] = 'unwrapped'
cinematicum_unwrap(unwrapped, 66, .02)
unwrap_mesh = cinematicum_control_uvs(unwrapped, json.loads(%r))
records = {}
for item in json.loads(%r):
    obj = cinematicum_model_object(item, bpy.context.scene.collection)
    obj['cinematicum_id'] = item['id']
    mesh = cinematicum_extract_model(obj)
    records[item['id']] = {'vertices': mesh['vertices'], 'triangles': len(mesh['triangles']),
                           'modifier': obj.modifiers[0].type}
bpy.ops.wm.save_as_mainfile(filepath=%r, check_existing=False)
bpy.ops.wm.open_mainfile(filepath=%r)
reopened = {obj.get('cinematicum_id'): obj for obj in bpy.context.scene.objects if obj.get('cinematicum_id')}
actual = reopened['projected']; uv = actual.data.uv_layers.active
replay_corners = [[list(uv.data[loop].uv) for loop in polygon.loop_indices] for polygon in actual.data.polygons]
record = {'engine_version': bpy.app.version_string, 'uv_corners': corners, 'replay_uv_corners': replay_corners,
          'unwrap_mesh': unwrap_mesh, 'modifiers': records,
          'reopened_modifiers': {key: [modifier.type for modifier in obj.modifiers] for key,obj in reopened.items()}}
with open(%r, 'w') as handle: json.dump(record, handle)
''' % (json.dumps(projected), json.dumps(base), json.dumps(base), json.dumps(candidates),
       str(output/'ENGINE_TEST_uv_modifiers.blend'), str(output/'ENGINE_TEST_uv_modifiers.blend'), str(result))
    return source, result, {'projected': projected}


def device_script(work, output, device):
    result = work/'result.json'
    source = 'import bpy, json\n' + inspect.getsource(configure_cycles_device) + '\n'
    source += '''
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
record = {'engine_version': bpy.app.version_string}
record['cpu'] = configure_cycles_device(bpy, scene, 'CPU')
try:
    record['selected'] = configure_cycles_device(bpy, scene, %r)
    record['cycles_device'] = scene.cycles.device
    scene['cinematicum_render_device'] = json.dumps(record['selected'])
    bpy.ops.wm.save_as_mainfile(filepath=%r, check_existing=False)
    bpy.ops.wm.open_mainfile(filepath=%r)
    record['reopened_device'] = bpy.context.scene.cycles.device
    record['reopened_receipt'] = json.loads(bpy.context.scene['cinematicum_render_device'])
except Exception as error:
    record['device_error'] = str(error)
with open(%r, 'w') as handle: json.dump(record, handle)
''' % (device, str(output/'ENGINE_TEST_render_device.blend'), str(output/'ENGINE_TEST_render_device.blend'), str(result))
    return source, result, {'device': device}


def device_render_script(work, output, device):
    spec = scene.default_scene(16, 16)
    spec.update(frame_end=1, samples=4)
    spec['render'].update(device=device, use_denoising=False)
    spec['objects'] = [{'id': 'gpu_test', 'name': 'ENGINE TEST GPU cube', 'type': 'cube'}]
    spec = scene.validate_scene(spec)
    frames = work/'frames'
    frames.mkdir()
    blend = output/'ENGINE_TEST_gpu_render.blend'
    result = work/'result.json'
    source = scene._build_script(spec, blend, frames, 24, 1, 1)
    source += '''
record = {'engine_version': bpy.app.version_string,
          'device': json.loads(scene['cinematicum_render_device']),
          'rendered_image': bool(bpy.data.images.get('Render Result')),
          'cycles_device': scene.cycles.device}
with open(%r, 'w') as handle: json.dump(record, handle)
''' % str(result)
    return source, result, {'device': device, 'blend': blend, 'frames': frames}


def verify(stage, record, context):
    checks = {}
    if stage == 'hierarchy':
        checks['actual_cpu_frame_rendered'] = len(list(context['frames'].glob('frame_*.png'))) == 1
        checks['retained_source_reopened'] = context['blend'].is_file()
        checks['local_recipe_retained'] = record.get('recipe') == context['spec']
        checks['three_level_parents_retained'] = record.get('parents') == {'child': 'parent', 'parent': None, 'grandchild': 'child'}
        errors = []
        for sample in record.get('samples', []):
            for ident, matrix in sample['objects'].items():
                wanted = scene.object_matrix_at(context['spec'], ident, sample['frame'])
                errors.extend(abs(a-b) for a, b in zip(matrix, wanted))
        record['maximum_world_matrix_error'] = max(errors, default=float('inf'))
        checks['retained_parent_animation_and_shear_match_at_subframes'] = len(record.get('samples', [])) == 5 and max(errors, default=1) < 5e-5
        checks['actual_device_recorded'] = record.get('device', {}).get('actual') == 'CPU'
    elif stage == 'modeling':
        projected = context['projected']
        expected, offset = [], 0
        for face in projected['modeling']['faces']:
            corners = {}
            for triangle, uv_indices in zip(projected['mesh']['triangles'][offset:offset+len(face)-2], projected['mesh']['uv_indices'][offset:offset+len(face)-2]):
                for vertex, index in zip(triangle, uv_indices):
                    corners[vertex] = projected['mesh']['uvs'][index]
            expected.append([corners[v] for v in face])
            offset += len(face)-2
        actual = record.get('uv_corners', [])
        checks['authored_uvs_reach_actual_quad_loops'] = len(actual) == len(expected) and all(
            len(a) == len(b) and all(max(abs(x-y) for x, y in zip(p,q)) < 2e-6 for p,q in zip(a,b))
            for a,b in zip(actual, expected))
        checks['uvs_survive_saved_source_replay'] = actual == record.get('replay_uv_corners')
        unwrap = record.get('unwrap_mesh', {})
        checks['actual_smart_unwrap_has_complete_finite_uvs'] = bool(unwrap.get('uvs')) and len(unwrap.get('uv_indices', [])) == 12 and all(
            math.isfinite(v) and -.001 <= v <= 1.001 for point in unwrap.get('uvs', []) for v in point)
        mods = record.get('modifiers', {})
        checks['five_live_modifier_types_saved_and_reopened'] = all(
            record.get('reopened_modifiers', {}).get(key) == [value['modifier']] for key,value in mods.items()) and len(mods) == 5
        array = mods.get('test_array', {})
        checks['array_generates_actual_second_copy'] = array.get('triangles') == 24 and abs(max((v[0] for v in array.get('vertices', [])), default=0)-4) < 2e-6
        shell = mods.get('test_solidify', {})
        checks['solidify_generates_actual_shell_depth'] = abs(min((v[2] for v in shell.get('vertices', [])), default=0)+.3) < 2e-6 and shell.get('triangles', 0) >= 8
        checks['decimate_reduces_actual_geometry'] = 0 < mods.get('test_decimate', {}).get('triangles', 0) < 12
        checks['smooth_changes_actual_vertex_positions'] = max((abs(c) for v in mods.get('test_smooth', {}).get('vertices', []) for c in v), default=1) < .999
        deform = mods.get('test_simple_deform', {})
        checks['twist_changes_actual_geometry'] = max((abs(v[0]) for v in deform.get('vertices', [])), default=0) > 1.1
    elif stage == 'device-render':
        images = list(context['frames'].glob('frame_*.png'))
        checks['actual_gpu_frame_written'] = len(images) == 1 and images[0].stat().st_size > 64 and record.get('rendered_image') is True
        checks['actual_requested_backend_rendered'] = record.get('cycles_device') == 'GPU' and record.get('device', {}).get('actual') == context['device']
        checks['actual_gpu_device_identified'] = bool(record.get('device', {}).get('devices'))
        checks['retained_source_written'] = context['blend'].is_file()
    else:
        checks['cpu_contract_executed'] = record.get('cpu', {}).get('actual') == 'CPU'
        checks['requested_device_enumerated'] = record.get('selected', {}).get('actual') == context['device']
        checks['gpu_selection_saved_and_reopened'] = (record.get('cycles_device') == 'GPU' and
            record.get('reopened_device') == 'GPU' and record.get('reopened_receipt') == record.get('selected'))
        checks['actual_gpu_device_identified'] = bool(record.get('selected', {}).get('devices'))
    return checks


def run(output, stage='hierarchy', device='METAL', timeout=15.5):
    binary = find_blender()
    if not binary:
        return {'status': 'skipped', 'reason': 'Actual Blender is required; no engine proof claimed.'}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'stage': stage, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM'}
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='cinematicum-authoring-TEST-', dir=output) as temporary:
        work = Path(temporary)
        source, record_file, context = (hierarchy_script(work, output) if stage == 'hierarchy' else
            modeling_script(work, output) if stage == 'modeling' else
            device_render_script(work, output, device) if stage == 'device-render' else device_script(work, output, device))
        script = work/'acceptance.py'
        script.write_text(source, encoding='utf-8')
        process = subprocess.Popen([binary, '--background', '--factory-startup', '--disable-autoexec', '--threads', '2',
                                    '--python-exit-code', '1', '--python', str(script)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            log = process.communicate(timeout=min(15.5, timeout))[0]
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            log = process.communicate(timeout=1)[0]
            result['error'] = 'The owned native stage exceeded its bounded deadline.'
        result['returncode'] = process.returncode
        if process.returncode == 0 and record_file.is_file():
            record = json.loads(record_file.read_text())
            checks = verify(stage, record, context)
            result.update(checks=checks, passed=all(checks.values()), evidence=record)
            if context.get('frames'):
                result['rendered_test_frames'] = []
                for frame in context['frames'].glob('frame_*.png'):
                    payload = frame.read_bytes()
                    retained = output/('ENGINE_TEST_'+stage+'_'+frame.name)
                    retained.write_bytes(payload)
                    result['rendered_test_frames'].append({'path': str(retained), 'sha256': hashlib.sha256(payload).hexdigest()})
        else:
            result['log_tail'] = log.decode('utf-8', errors='replace')[-3000:]
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    (output/('ENGINE_TEST_authoring_'+stage+'_report.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=['hierarchy', 'modeling', 'device', 'device-render'], default='hierarchy')
    parser.add_argument('--device', choices=['METAL', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI'], default='METAL')
    parser.add_argument('--timeout', type=float, default=15.5)
    args = parser.parse_args()
    result = run(args.output, args.stage, args.device, max(1, args.timeout))
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get('passed') or result.get('status') == 'skipped' else 1)

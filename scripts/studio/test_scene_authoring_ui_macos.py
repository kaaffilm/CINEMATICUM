#!/usr/bin/env python3
"""Bounded native authoring controls, real Blender jobs, save and undo acceptance.

Run the stages in order against one owned output directory. Each stage makes at
most one actual modeling job; browser actions and the production HTTP service
are used unchanged. The fixtures are synthetic, never user film media.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import threading
import time

from scene import default_scene, validate_scene
from server import Server, Store


STAGES = ('hierarchy', 'convert', 'project', 'uvmove', 'unwrap', 'array', 'arrayoffset', 'gpu')


def run(binary, output, stage):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM',
              'browser': 'WKWebView', 'stage': stage, 'checks': {}}
    checkpoint_path = output/'ENGINE_TEST_scene_authoring_ui_checkpoint.json'
    screenshot = output/('ENGINE_TEST_scene_authoring_ui_'+stage+'.png')
    store = Store(output/'ENGINE_TEST_scene_authoring_ui_workspace')
    server = thread = None
    try:
        if stage == STAGES[0]:
            project = store.new_project({'name': 'ENGINE TEST scene authoring', 'width': 160, 'height': 120, 'fps': 12})
            spec = default_scene(160, 120)
            spec.update(frame_end=4, samples=4)
            spec['objects'] = [
                {'id': 'modeled', 'name': 'ENGINE TEST child cube', 'type': 'cube', 'position': [1, 0, 1]},
                {'id': 'parent', 'name': 'ENGINE TEST parent', 'type': 'cube', 'rotation': [0, 0, 90],
                 'scale': [2, 2, 1], 'keyframes': [{'frame': 1}, {'frame': 4, 'rotation': [0, 0, 180]}]},
            ]
            project['settings']['scene'] = validate_scene(spec)
            project = store.save(project['id'], project)
            checkpoint = {'project_id': project['id'], 'stages': {}}
        else:
            checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
            previous = STAGES[STAGES.index(stage)-1]
            if checkpoint.get('last_stage') != previous:
                raise ValueError('Run scene authoring UI stage '+previous+' before '+stage+'.')
            project = store.get(checkpoint['project_id'])
        before = copy.deepcopy(project['settings']['scene'])
        child_before = next(obj for obj in before['objects'] if obj['id'] == 'modeled')
        script = output/('ENGINE_TEST_scene_authoring_ui_'+stage+'.js')
        fixture_data = {'stage': stage, 'uvs': child_before.get('mesh', {}).get('uvs', [])}
        script.write_text('const AUTHORING_TEST='+json.dumps(fixture_data)+';\n'+
            Path(__file__).with_name('macos').joinpath('SceneAuthoringSmoke.js').read_text(), encoding='utf-8')
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        thread.start()
        process = subprocess.run([str(Path(binary).resolve()), '--url', 'http://127.0.0.1:'+str(server.server_port),
                                  '--output', str(screenshot), '--script', str(script), '--timeout', '14'],
                                 capture_output=True, text=True, timeout=15.5)
        ui = None
        for line in reversed(process.stdout.splitlines()):
            try:
                value = json.loads(line)
                if isinstance(value, dict) and 'passed' in value:
                    ui = value
                    break
            except ValueError:
                pass
        if ui is None:
            raise RuntimeError('Native authoring helper returned no result: '+(process.stderr or process.stdout)[-2000:])
        result['ui'] = ui
        checks = result['checks']
        checks['native_controls_and_actual_jobs'] = process.returncode == 0 and ui.get('passed') is True
        saved = store.get(project['id'])['settings']['scene']
        checks['canonical_scene_saved'] = validate_scene(saved, width=160, height=120) == saved
        child = next(obj for obj in saved['objects'] if obj['id'] == 'modeled')
        checks['parent_links_and_local_pose_retained'] = child.get('parent_id') == 'parent' and all(
            abs(a-b) < 1e-9 for a, b in zip(child['position'], [1, -.125, 1]))
        checks['parent_animation_unchanged'] = saved['objects'][1] == before['objects'][1]
        checks['native_snapshot'] = screenshot.is_file() and screenshot.stat().st_size > 1000
        if stage != 'hierarchy':
            model = child['modeling']
            checks['actual_evaluated_geometry_saved'] = bool(model['evaluation']['engine_version']) and bool(model['evaluation']['mesh']['sha256'])
            checks['material_and_local_animation_retained'] = child['material'] == child_before['material'] and child['keyframes'] == child_before['keyframes']
            if stage not in {'convert'}:
                checks['control_geometry_retained'] = all(child['mesh'][key] == child_before['mesh'][key] for key in ('vertices', 'triangles', 'normals', 'normal_indices'))
        if stage == 'convert':
            checks['editable_quad_cage_saved'] = len(child['modeling']['faces']) == 6 and len(child['mesh']['vertices']) == 8
        elif stage == 'project':
            checks['six_face_atlas_saved'] = len(child['mesh']['uvs']) == 24 and all(i >= 0 for tri in child['mesh']['uv_indices'] for i in tri)
        elif stage == 'uvmove':
            wanted = copy.deepcopy(child_before['mesh']['uvs'])
            wanted[0][0] += .1
            wanted[0][1] -= .05
            checks['pointer_moves_only_selected_uv'] = len(child['mesh']['uvs']) == len(wanted) and all(
                abs(a-b) < 1e-6 for actual, expected in zip(child['mesh']['uvs'], wanted) for a, b in zip(actual, expected))
            checks['uv_corner_seams_unchanged'] = child['mesh']['uv_indices'] == child_before['mesh']['uv_indices']
        elif stage == 'unwrap':
            checks['real_unwrap_saved'] = bool(child['mesh']['uvs']) and all(math.isfinite(v) and -.001 <= v <= 1.001 for uv in child['mesh']['uvs'] for v in uv)
            checks['unwrap_changes_prior_mapping'] = child['mesh']['uvs'] != child_before['mesh']['uvs']
        elif stage in {'array', 'arrayoffset'}:
            model = child['modeling']
            offset = 2 if stage == 'array' else 3
            checks['live_array_saved'] = len(model['modifiers']) == 1 and model['modifiers'][0]['type'] == 'array' and model['modifiers'][0]['offset'] == [offset, 0, 0]
            checks['actual_repeated_geometry_saved'] = len(model['evaluation']['mesh']['triangles']) == 24 and abs(max(v[0] for v in model['evaluation']['mesh']['vertices'])-(1+offset)) < 1e-6
            checks['array_retains_authored_uvs'] = child['mesh']['uvs'] == child_before['mesh']['uvs']
        elif stage == 'gpu':
            checks['explicit_metal_request_saved'] = saved['render']['device'] == 'METAL'
            checks['compute_choice_preserves_scene_geometry'] = saved['objects'] == before['objects']
        result['passed'] = bool(checks) and all(checks.values())
        result['complete'] = stage == STAGES[-1] and result['passed']
        if result['passed']:
            checkpoint['stages'][stage] = result
            checkpoint['last_stage'] = stage
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding='utf-8')
            result['all_completed_stages_passed'] = all(item['passed'] for item in checkpoint['stages'].values())
            result['completed_stage_count'] = len(checkpoint['stages'])
        else:
            result['error'] = ui.get('error') or 'Failed checks: '+', '.join(key for key, passed in checks.items() if not passed)
    except Exception as error:
        result['error'] = str(error)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=.5)
        store.shutdown()
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    result['screenshot'] = str(screenshot) if screenshot.exists() else None
    (output/('ENGINE_TEST_scene_authoring_ui_'+stage+'_report.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=STAGES, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        print(json.dumps({'status': 'skipped', 'reason': 'Native scene authoring acceptance requires macOS WKWebView.'}))
        raise SystemExit(0)
    if not args.binary or not args.binary.is_file():
        parser.error('Compile macos/SmokeTest.swift and pass its executable with --binary.')
    result = run(args.binary, args.output, args.stage)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)

#!/usr/bin/env python3
"""Bounded native stages exercising real topology/modifier jobs and shared undo.

Run each --stage sequentially against the same --output test directory. A stage
performs at most one UI operation (Apply evaluates twice) and saves a genuine
project. No modeling endpoint or engine is mocked.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from scene import default_scene, validate_scene
from server import Server, Store


STAGES = ('convert', 'vertex', 'extrude', 'subdivide', 'delete', 'mirror', 'bevel',
          'subdivision', 'reorder', 'disable', 'enable', 'apply')


def run(binary, output, stage):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM', 'browser': 'WKWebView', 'stage': stage, 'checks': {}}
    checkpoint_path = output / 'ENGINE_TEST_mesh_ui_checkpoint.json'
    screenshot = output / ('ENGINE_TEST_mesh_ui_' + stage + '.png')
    store = Store(output / 'ENGINE_TEST_mesh_ui_workspace')
    server = thread = None
    try:
        if stage == 'convert':
            project = store.new_project({'name': 'ENGINE TEST mesh modeling', 'width': 160, 'height': 120, 'fps': 12})
            spec = default_scene(160, 120)
            spec.update(frame_end=2, samples=4)
            spec['objects'] = [{'id': 'modeled', 'name': 'ENGINE TEST editable cube', 'type': 'cube'}]
            project['settings']['scene'] = validate_scene(spec)
            project = store.save(project['id'], project)
            checkpoint = {'project_id': project['id'], 'stages': {}}
        else:
            checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
            previous = STAGES[STAGES.index(stage) - 1]
            if checkpoint.get('last_stage') != previous:
                raise ValueError('Run native UI stage ' + previous + ' before ' + stage + '.')
            project = store.get(checkpoint['project_id'])
        before = project['settings']['scene']['objects'][0]
        script = output / ('ENGINE_TEST_mesh_ui_' + stage + '.js')
        script.write_text('const MODELING_TEST=' + json.dumps({'stage': stage}) + ';\n' +
                          Path(__file__).with_name('macos').joinpath('MeshModelingSmoke.js').read_text(), encoding='utf-8')
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        thread.start()
        process = subprocess.run([str(Path(binary).resolve()), '--url', 'http://127.0.0.1:' + str(server.server_port),
                                  '--output', str(screenshot), '--script', str(script), '--timeout', '14'],
                                 capture_output=True, text=True, timeout=16)
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
            raise RuntimeError('Native modeling helper returned no result: ' + (process.stderr or process.stdout)[-2000:])
        result['ui'] = ui
        checks = result['checks']
        checks['actual_native_controls_and_jobs'] = process.returncode == 0 and ui.get('passed') is True
        saved = store.get(project['id'])
        spec = saved['settings']['scene']
        checks['canonical_scene_saved'] = validate_scene(spec, width=160, height=120) == spec
        checks['same_object_and_material_retained'] = len(spec['objects']) == 1 and spec['objects'][0]['id'] == 'modeled' and spec['objects'][0]['material'] == before['material']
        obj = spec['objects'][0]
        model = obj.get('modeling', {})
        checks['real_evaluation_saved'] = bool(model.get('evaluation', {}).get('engine_version')) and bool(model.get('evaluation', {}).get('mesh', {}).get('sha256'))
        checks['source_distinction_retained'] = model.get('origin') == {'kind': 'primitive', 'primitive': 'cube'} and 'source' not in obj.get('mesh', {})
        checks['native_snapshot'] = screenshot.is_file() and screenshot.stat().st_size > 1000
        if stage == 'convert':
            checks['eight_vertex_six_face_cage'] = len(obj['mesh']['vertices']) == 8 and len(model['faces']) == 6
        elif stage == 'vertex':
            checks['vertex_edit_saved'] = obj['mesh']['vertices'][0][0] == -1.3 and obj['mesh']['sha256'] != before['mesh']['sha256']
        elif stage == 'extrude':
            checks['extrusion_depth_saved'] = len(model['faces']) == 10 and max(p[2] for p in obj['mesh']['vertices']) == 1.7
        elif stage in {'subdivide', 'delete'}:
            checks['connected_subdivision_or_delete_undo_saved'] = len(model['faces']) == 13 and len(obj['mesh']['vertices']) == 17
        elif stage in {'mirror', 'bevel', 'subdivision'}:
            checks['new_live_modifier_saved'] = model['modifiers'][-1]['type'] == stage and len(model['modifiers']) == len(before['modeling']['modifiers']) + 1
            checks['cage_unchanged_by_modifier'] = obj['mesh'] == before['mesh']
        elif stage == 'reorder':
            checks['modifier_order_saved'] = [m['type'] for m in model['modifiers']] == ['bevel', 'mirror', 'subdivision']
        elif stage in {'disable', 'enable'}:
            checks['enable_state_and_changed_evaluated_geometry_saved'] = model['modifiers'][-1]['enabled'] == (stage == 'enable') and model['evaluation']['mesh']['sha256'] != before['modeling']['evaluation']['mesh']['sha256']
        elif stage == 'apply':
            checks['apply_undo_preserves_entire_original_cage_and_stack'] = obj == before
        result['passed'] = bool(checks) and all(checks.values())
        result['complete'] = stage == STAGES[-1] and result['passed']
        if result['passed']:
            checkpoint['stages'][stage] = result
            checkpoint['last_stage'] = stage
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding='utf-8')
            result['all_completed_stages_passed'] = all(v['passed'] for v in checkpoint['stages'].values())
            result['completed_stage_count'] = len(checkpoint['stages'])
        else:
            result['error'] = ui.get('error') or 'Failed checks: ' + ', '.join(k for k, v in checks.items() if not v)
    except Exception as error:
        result['error'] = str(error)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=.5)
        store.shutdown()
    result['elapsed_seconds'] = round(time.monotonic() - began, 3)
    result['screenshot'] = str(screenshot) if screenshot.exists() else None
    (output / ('ENGINE_TEST_mesh_ui_' + stage + '_report.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--stage', choices=STAGES, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        print(json.dumps({'status': 'skipped', 'reason': 'Native mesh authoring acceptance requires macOS WKWebView.'}))
        raise SystemExit(0)
    if not args.binary or not args.binary.is_file():
        parser.error('Compile macos/SmokeTest.swift and pass its executable with --binary.')
    result = run(args.binary, args.output, args.stage)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)

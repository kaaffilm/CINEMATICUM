#!/usr/bin/env python3
"""Native trim controls with an independent moving-picture frame oracle.

Run --stage slip, slide, roll and guards separately against one --output folder.
Each stage owns a separate test workspace and fresh three-shot timeline. The UI
stages save and export their actual edits; no trim or render code is used to
derive the expected source frames. The fixture is synthetic ENGINE TEST media.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from engine import probe_media, validate_project
from server import Server, Store


STAGES = ('slip', 'slide', 'roll', 'guards')
WIDTH, HEIGHT, SOURCE_FRAMES = 128, 96, 80
BASELINE = [(0, 8, 8), (8, 8, 24), (16, 8, 40)]
EXPECTED_TIMING = {
    'slip': [(0, 8, 8), (8, 8, 27), (16, 8, 40)],
    'slide': [(0, 10, 8), (10, 8, 24), (18, 6, 42)],
    'roll': [(0, 8, 8), (8, 6, 24), (14, 10, 38)],
    'guards': BASELINE,
}
# These explicit editorial oracles do not call the implementation under test.
EXPECTED_FRAMES = {
    'slip': list(range(8, 16)) + list(range(27, 35)) + list(range(40, 48)),
    'slide': list(range(8, 18)) + list(range(24, 32)) + list(range(42, 48)),
    'roll': list(range(8, 16)) + list(range(24, 30)) + list(range(38, 48)),
}


def create_fixture(path):
    """80 real moving frames, seven binary frame-index patches, and a color ramp."""
    data = bytearray()
    for frame in range(SOURCE_FRAMES):
        picture = bytearray(bytes((10 + 2 * frame, 32, 90)) * (WIDTH * HEIGHT))
        left = 8 + (3 * frame) % 96
        for y in range(16, 32):
            for x in range(left, left + 12):
                offset = (y * WIDTH + x) * 3
                picture[offset:offset + 3] = bytes((235, 235, 235))
        for bit in range(7):
            value = 220 if frame & (1 << bit) else 24
            for y in range(72, 88):
                for x in range(8 + bit * 16, 20 + bit * 16):
                    offset = (y * WIDTH + x) * 3
                    picture[offset:offset + 3] = bytes((value, value, value))
        data.extend(picture)
    subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-nostdin', '-y',
                    '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '128x96',
                    '-framerate', '24', '-i', 'pipe:0', '-an', '-c:v', 'libx264',
                    '-preset', 'ultrafast', '-crf', '0', '-g', '1', '-pix_fmt', 'yuv420p',
                    '-threads', '1', '-movflags', '+faststart', str(path)],
                   input=data, capture_output=True, check=True, timeout=4)


def decode_oracle(path, expected):
    data = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path),
                           '-map', '0:v:0', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                          capture_output=True, check=True, timeout=4).stdout
    size = WIDTH * HEIGHT * 3
    if len(data) != len(expected) * size:
        raise ValueError('Exported picture count is not exactly ' + str(len(expected)) + '.')
    observed, motion_errors, picture_hashes = [], [], []
    for index, source_frame in enumerate(expected):
        picture = data[index * size:(index + 1) * size]
        picture_hashes.append(hashlib.sha256(picture).hexdigest())
        frame_id = 0
        for bit in range(7):
            values = [picture[(y * WIDTH + x) * 3] for y in range(78, 82)
                      for x in range(12 + bit * 16, 16 + bit * 16)]
            mean = sum(values) / len(values)
            if not (mean < 64 or mean > 180):
                raise ValueError('Frame-index patch is not independently decodable.')
            frame_id |= int(mean > 128) << bit
        observed.append(frame_id)
        moving = [x for y in range(20, 28) for x in range(WIDTH)
                  if min(picture[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3]) > 190]
        if not moving:
            raise ValueError('The actual moving marker disappeared from export.')
        motion_errors.append(abs(sum(moving) / len(moving) - (8 + (3 * source_frame) % 96 + 5.5)))
    return {'source_frames': observed, 'expected_source_frames': expected,
            'exact_frame_order': observed == expected,
            'max_motion_error_pixels': max(motion_errors),
            'actual_motion_matches': max(motion_errors) < 1,
            'unique_decoded_frames': len(set(picture_hashes)),
            'decoded_frames': len(observed)}


def seed(store, fixture, stage):
    project = store.new_project({'name': 'ENGINE TEST native ' + stage + ' trim',
                                 'width': WIDTH, 'height': HEIGHT, 'fps': 24})
    incoming = fixture.with_name('ENGINE_TEST_' + stage + '_incoming.mp4')
    shutil.copyfile(fixture, incoming)
    asset = store.admit(project['id'], incoming, 'ENGINE TEST moving frame index.mp4',
                        {'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM'})
    project = store.get(project['id'])
    project['clips'] = [{
        'id': name, 'asset_id': asset['id'], 'track': 0, 'start': start,
        'duration': duration, 'in': source_in, 'speed': 1, 'reverse': False,
        'x': 0, 'y': 0, 'scale': 1, 'rotation': 0, 'opacity': 1, 'volume': 1,
        'grade': {'exposure': 0, 'contrast': 1, 'saturation': 1, 'temperature': 0},
        'audio': {'fade_in': 0, 'fade_out': 0, 'pan': 0}, 'keyframes': [],
    } for name, (start, duration, source_in) in zip(('before', 'middle', 'after'), BASELINE)]
    return store.save(project['id'], project)


def run(binary, output, stage):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM',
              'browser': 'WKWebView', 'stage': stage, 'checks': {}}
    screenshot = output / ('ENGINE_TEST_trim_' + stage + '.png')
    store = server = thread = None
    try:
        fixture = output / 'ENGINE_TEST_trim_moving_source.mp4'
        if not fixture.exists():
            create_fixture(fixture)
        # Each invocation starts with empty history and its own immutable media.
        workspace = output / ('ENGINE_TEST_trim_' + stage + '_workspace')
        if workspace.exists():
            raise ValueError('This native stage already owns a workspace; use a new output folder to repeat it.')
        store = Store(workspace)
        project = seed(store, fixture, stage)
        script = output / ('ENGINE_TEST_trim_' + stage + '.js')
        script.write_text('const TRIM_TEST=' + json.dumps({'stage': stage}) + ';\n' +
                          Path(__file__).with_name('macos').joinpath('TrimSmoke.js').read_text(), encoding='utf-8')
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        thread.start()
        process = subprocess.run([str(Path(binary).resolve()), '--url', 'http://127.0.0.1:' + str(server.server_port),
                                  '--output', str(screenshot), '--script', str(script), '--timeout', '13'],
                                 capture_output=True, text=True, timeout=15)
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
            raise RuntimeError('Native trim helper returned no result: ' + (process.stderr or process.stdout)[-2000:])
        result['ui'] = ui
        checks = result['checks']
        checks['actual_native_trim_controls'] = process.returncode == 0 and ui.get('passed') is True
        saved = store.get(project['id'])
        normalized = validate_project(saved, store.project_dir(project['id']))
        checks['saved_timing_independent_oracle'] = [(c['start'], c['duration'], c['in']) for c in saved['clips']] == EXPECTED_TIMING[stage]
        checks['three_original_clips_and_media'] = [c['id'] for c in saved['clips']] == ['before', 'middle', 'after'] and len(saved['assets']) == 1
        checks['saved_format_and_length'] = saved['width'] == WIDTH and saved['height'] == HEIGHT and saved['fps'] == 24 and max(c['start'] + c['duration'] for c in normalized['clips']) == 24
        checks['native_snapshot'] = screenshot.is_file() and screenshot.stat().st_size > 1000
        if stage == 'guards':
            checks['clamps_noop_and_lock_exercised'] = {'both_source_handle_limits_and_zero_noop', 'locked_track_rejected_without_edit_history'} <= set(ui.get('steps', []))
            checks['track_unlocked_after_rejected_edit'] = not any(t.get('locked') for t in saved.get('tracks', []))
        else:
            checks['one_undo_and_redo_exercised'] = stage + '_three_clip_timing_one_undo_and_redo' in ui.get('steps', [])
            with store.lock:
                jobs = [json.loads(json.dumps(job)) for job in store.jobs.values()
                        if job['project_id'] == project['id'] and job['kind'] == 'render']
            completed = [job for job in jobs if job['state'] == 'completed']
            checks['one_actual_export_job'] = len(jobs) == len(completed) == 1
            if len(completed) == 1:
                job = completed[0]
                movie = store.project_dir(project['id']) / 'exports' / job['result']['filename']
                report = probe_media(movie)
                checks['export_exact_video_format'] = (report['width'], report['height'], report['frames']) == (WIDTH, HEIGHT, 24)
                checks['export_exact_duration'] = abs(report['duration'] - 1) < .003
                oracle = decode_oracle(movie, EXPECTED_FRAMES[stage])
                result['decoded_oracle'] = oracle
                checks['all_24_export_frames_match_source_oracle'] = oracle['exact_frame_order'] and oracle['unique_decoded_frames'] == 24
                checks['actual_moving_picture_matches_oracle'] = oracle['actual_motion_matches']
                checks['download_is_actual_export'] = ui.get('metrics', {}).get('download') == job['result']['url'] + '?download=1'
                evidence_movie = output / ('ENGINE_TEST_trim_' + stage + '.mp4')
                shutil.copyfile(movie, evidence_movie)
                result['movie'] = str(evidence_movie)
        (output / ('ENGINE_TEST_trim_' + stage + '_saved_project.json')).write_text(json.dumps(saved, indent=2), encoding='utf-8')
        result['passed'] = bool(checks) and all(checks.values())
        if not result['passed']:
            result['error'] = ui.get('error') or 'Failed checks: ' + ', '.join(k for k, passed in checks.items() if not passed)
    except Exception as error:
        result['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr or b''
            result['process_error'] = (detail.decode(errors='replace') if isinstance(detail, bytes) else detail)[-2000:]
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=.5)
        if store:
            store.shutdown()
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    result['screenshot'] = str(screenshot) if screenshot.exists() else None
    (output / ('ENGINE_TEST_trim_' + stage + '_report.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--stage', required=True, choices=STAGES)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        print(json.dumps({'status': 'skipped', 'reason': 'Native trim acceptance requires macOS WKWebView.'}))
        raise SystemExit(0)
    if not args.binary or not args.binary.is_file():
        parser.error('Compile macos/SmokeTest.swift and pass its executable with --binary.')
    result = run(args.binary, args.output, args.stage)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)

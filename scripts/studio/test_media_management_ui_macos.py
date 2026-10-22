#!/usr/bin/env python3
"""Native proxy creation/cancellation, actual decoder switching and exact relink.

Run baseline, cancel, proxy, then relink against one fresh owned output folder.
Each stage has a 17-second whole-run acceptance bound. The shipped UI and HTTP
handlers execute unchanged. All media are generated synthetic test signals.
Export pictures and PCM are independently decoded, not inferred from a label.
"""
from __future__ import annotations

import argparse
import base64
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from media_management import digest_file, inventory, proxy_file
from server import Server, Store
from test_editing_ui_macos import read_helper_result


STAGES = ('baseline', 'cancel', 'proxy', 'relink')
WIDTH, HEIGHT, FPS, FRAMES = 160, 90, 24, 12
SOURCE_FRAMES = 60
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def run(binary, output, stage):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    began, store, server, thread = time.monotonic(), None, None, None
    deadline = began + 16.5
    result = {'passed': False, 'stage': stage, 'browser': 'WKWebView',
              'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM', 'checks': {}}
    checks = result['checks']
    checkpoint_path = output/'ENGINE_TEST_media_ui_checkpoint.json'
    screenshot = output/('ENGINE_TEST_media_ui_'+stage+'.png')

    def budget(maximum, reserve=0):
        remaining = deadline-time.monotonic()-reserve
        if remaining <= .1:
            raise TimeoutError('The native media stage exceeded its bounded execution budget.')
        return min(maximum, remaining)

    def command(arguments, maximum=3):
        return subprocess.run(arguments, check=True, capture_output=True, timeout=budget(maximum)).stdout

    try:
        ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:
            raise RuntimeError('Actual FFmpeg and ffprobe are required for media acceptance.')
        workspace = output/'ENGINE_TEST_media_ui_workspace'
        if stage == 'baseline' and workspace.exists():
            raise ValueError('Baseline requires a fresh owned output directory.')
        store = Store(workspace)
        fixture = output/'ENGINE_TEST_exact_original.mp4'
        if stage == 'baseline':
            command([ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-y', '-threads', '1', '-filter_complex_threads', '1',
                     '-f', 'lavfi', '-i', 'testsrc2=size=800x450:rate=24:duration=2.5',
                     '-f', 'lavfi', '-i', 'aevalsrc=0.12*sin(2*PI*440*t)|0.09*sin(2*PI*660*t):s=48000:d=2.5',
                     '-frames:v', str(SOURCE_FRAMES), '-t', '2.5', '-c:v', 'libx264', '-preset', 'ultrafast',
                     '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-threads', '1', '-movflags', '+faststart', str(fixture)], 4)
            project = store.new_project({'name': 'ENGINE TEST media management', 'width': WIDTH, 'height': HEIGHT, 'fps': FPS})
            incoming = output/'ENGINE_TEST_media_intake.mp4'
            shutil.copy2(fixture, incoming)
            asset = store.admit(project['id'], incoming, fixture.name, {'fixture': 'ENGINE TEST'})
            project = store.get(project['id'])
            project['clips'] = [{'id': 'engine_test_clip', 'asset_id': asset['id'], 'start': 0, 'in': 0,
                                 'duration': FRAMES, 'track': 0}]
            project = store.save(project['id'], project)
            checkpoint = {'project_id': project['id'], 'asset_id': asset['id'],
                          'original_sha256': digest_file(fixture), 'stages': {}}
        else:
            checkpoint = json.loads(checkpoint_path.read_text())
            previous = STAGES[STAGES.index(stage)-1]
            if checkpoint.get('last_stage') != previous:
                raise ValueError('Run native media stage '+previous+' before '+stage+'.')
            project = store.get(checkpoint['project_id'])
            asset = next(item for item in project['assets'] if item['id'] == checkpoint['asset_id'])
        directory = store.project_dir(project['id'])
        source = directory/asset['path']
        before = copy.deepcopy(project)
        inventory_bytes = (directory/'assets.json').read_bytes()
        initial_jobs = set(store.jobs)
        fixture_data = {'stage': stage, 'project_id': project['id'], 'asset_id': asset['id']}
        observed_relinks = []
        if stage == 'relink':
            if (not source.is_file() or source.is_symlink() or digest_file(source) != checkpoint['original_sha256']
                    or digest_file(fixture) != checkpoint['original_sha256']):
                raise ValueError('The owned synthetic original must be intact before the deliberate missing-file fixture.')
            fixture_data['original_base64'] = base64.b64encode(fixture.read_bytes()).decode('ascii')
            source.unlink()
            checks['owned_original_was_actually_missing'] = not source.exists()
            actual_relink = store.media_relink

            def observe_relink(project_id, asset_id, incoming):
                # Read-only evidence around the unchanged production method.
                # No return value, input, filesystem operation or error is replaced.
                metadata = (directory/'project.json').read_bytes()
                record = {'incoming_sha256': digest_file(incoming), 'incoming_size': Path(incoming).stat().st_size,
                          'present_before': source.exists(), 'project_id': project_id, 'asset_id': asset_id}
                observed_relinks.append(record)
                try:
                    value = actual_relink(project_id, asset_id, incoming)
                    record.update(result=copy.deepcopy(value), succeeded=True)
                    return value
                except Exception as error:
                    record.update(succeeded=False, error=str(error))
                    raise
                finally:
                    record['present_after'] = source.exists()
                    record['project_bytes_unchanged'] = metadata == (directory/'project.json').read_bytes()
                    record['inventory_bytes_unchanged'] = inventory_bytes == (directory/'assets.json').read_bytes()

            store.media_relink = observe_relink
        script = output/('ENGINE_TEST_media_ui_'+stage+'.js')
        script.write_text('const MEDIA_TEST='+json.dumps(fixture_data)+';\n'+
            Path(__file__).with_name('macos').joinpath('MediaManagementSmoke.js').read_text(), encoding='utf-8')
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        thread.start()
        native_timeout = budget(12.5, 2.2)
        process = subprocess.run([str(Path(binary).resolve()), '--url', 'http://127.0.0.1:'+str(server.server_port),
                                  '--output', str(screenshot), '--script', str(script), '--timeout', str(round(native_timeout, 2))],
                                 capture_output=True, text=True, timeout=budget(native_timeout+.5, 1.2))
        ui = read_helper_result(process)
        result.update(ui=ui, helper_exit_code=process.returncode)
        checks['native_controls_and_actual_browser_media'] = process.returncode == 0 and ui.get('passed') is True
        checks['no_unhandled_browser_errors'] = not ui.get('page_errors', [])
        checks['native_snapshot'] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(PNG_SIGNATURE)
        saved = store.get(project['id'])
        checks['one_same_asset_and_original_path'] = len(saved['assets']) == 1 and saved['assets'] == before['assets']
        checks['timeline_edit_identity_unchanged'] = all(saved.get(key) == before.get(key) for key in ('clips', 'titles', 'tracks', 'sequences', 'captions'))
        checks['original_bytes_intact'] = source.is_file() and digest_file(source) == checkpoint['original_sha256']
        checks['immutable_inventory_bytes_intact'] = inventory_bytes == (directory/'assets.json').read_bytes()
        with store.lock:
            jobs = copy.deepcopy([job for key, job in store.jobs.items() if key not in initial_jobs])
        result['jobs'] = [{'kind': job['kind'], 'state': job['state']} for job in jobs]
        proxies = [job for job in jobs if job['kind'] == 'media-proxy']
        rows = inventory(saved, directory)['assets']
        if stage == 'cancel':
            checks['one_actual_cancelled_proxy_job'] = len(proxies) == 1 and proxies[0]['state'] == 'cancelled'
            checks['cancelled_proxy_not_admitted'] = not rows[0]['proxies']
            checks['cancelled_working_files_removed'] = not list((directory/'proxies').glob('proxy-build-*'))
            checks['cancel_control_executed'] = 'real_proxy_job_cancel_control' in ui.get('steps', [])
        elif stage == 'proxy':
            checks['one_actual_completed_proxy_job'] = len(proxies) == 1 and proxies[0]['state'] == 'completed'
            preview, receipt = proxy_file(saved, directory, asset['id'], 640)
            checks['proxy_bytes_and_origin_verified'] = digest_file(preview) == receipt['sha256'] and receipt['source_sha256'] == checkpoint['original_sha256']
            checks['proxy_reduces_actual_picture_dimensions'] = (receipt['width'], receipt['height']) == (640, 360) and (asset['width'], asset['height']) == (800, 450)
            checks['actual_decoder_switched_url_and_dimensions'] = ui.get('metrics', {}).get('proxy_decoder', {}).get('width') == 640 and ui['metrics']['proxy_decoder']['url'] != ui['metrics'].get('original_decoder', {}).get('url')
            stamps = {}
            for name, path in [('original', source), ('proxy', preview)]:
                lines = command([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                 'frame=best_effort_timestamp_time', '-of', 'csv=p=0', str(path)]).decode().splitlines()
                stamps[name] = [Fraction(line.split(',', 1)[0]) for line in lines if line.split(',', 1)[0].strip()]
            checks['all_sixty_frame_timestamps_independently_match'] = len(stamps['original']) == len(stamps['proxy']) == SOURCE_FRAMES and all(
                abs(a-b) <= Fraction(2, 1_000_000) and abs(a-Fraction(index, FPS)) <= Fraction(1, 1_000_000)
                for index, (a, b) in enumerate(zip(stamps['original'], stamps['proxy'])))
            result['proxy'] = {'sha256': receipt['sha256'], 'source_sha256': receipt['source_sha256'],
                               'dimensions': [receipt['width'], receipt['height']], 'frames': receipt['frames']}
        elif stage == 'relink':
            result['relinks'] = observed_relinks
            checks['wrong_file_rejected_without_restoring_original'] = len(observed_relinks) == 2 and not observed_relinks[0]['succeeded'] and not observed_relinks[0]['present_after'] and 'SHA-256' in observed_relinks[0].get('error', '')
            checks['browser_upload_matches_exact_selected_original'] = len(observed_relinks) == 2 and observed_relinks[1]['incoming_sha256'] == checkpoint['original_sha256'] and observed_relinks[1]['incoming_size'] == asset['size'] and observed_relinks[1].get('result', {}).get('restored') is True
            checks['both_relink_attempts_preserve_saved_edit_and_inventory'] = len(observed_relinks) == 2 and all(record['project_bytes_unchanged'] and record['inventory_bytes_unchanged'] for record in observed_relinks)
            checks['restored_original_actually_decodes'] = ui.get('metrics', {}).get('restored_original_decoder', {}).get('width') == 800
            checks['verified_proxy_survives_original_relink'] = len(rows[0]['proxies']) == 1 and rows[0]['proxies'][0]['long_edge'] == 640
            checks['upload_temporary_files_removed'] = not list(directory.glob('relink-upload-*'))
        if stage in {'proxy', 'relink'}:
            checks['preview_proxy_preference_saved'] = saved['settings'].get('preview_proxies') == {'enabled': True, 'long_edge': 640}
        if stage != 'cancel':
            completed = [job for job in jobs if job['kind'] == 'render' and job['state'] == 'completed']
            checks['one_real_prores_export'] = len(completed) == 1 and completed[0]['result'].get('profile') == 'prores'
            if len(completed) == 1:
                receipt = completed[0]['result']
                movie = directory/'exports'/receipt['filename']
                metadata = probe_media(movie)
                checks['export_clock_and_dimensions'] = metadata['frames'] == FRAMES and (metadata['width'], metadata['height']) == (WIDTH, HEIGHT)
                checks['export_identity_and_download'] = digest_file(movie) == receipt['sha256'] and Path(urlsplit(ui.get('metrics', {}).get('movie', '')).path).name == movie.name
                raw = command([ffmpeg, '-v', 'error', '-nostdin', '-i', str(movie), '-map', '0:v:0', '-an', '-threads', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'])
                pcm = command([ffmpeg, '-v', 'error', '-nostdin', '-i', str(movie), '-map', '0:a:0', '-vn', '-ac', '2', '-ar', '48000', '-f', 's16le', 'pipe:1'])
                decoded = {'rgb_sha256': hashlib.sha256(raw).hexdigest(), 'rgb_bytes': len(raw),
                           'pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'pcm_bytes': len(pcm)}
                checks['all_original_export_pictures_and_samples_decode'] = len(raw) == FRAMES*WIDTH*HEIGHT*3 and len(pcm) == int(FRAMES/FPS*48000)*4 and any(pcm)
                if stage == 'baseline':
                    checkpoint['original_export_decoded'] = decoded
                else:
                    checks['every_decoded_export_picture_and_pcm_sample_unchanged'] = decoded == checkpoint.get('original_export_decoded')
                result['decoded'] = decoded
                shutil.copy2(movie, output/('ENGINE_TEST_'+stage+'_original_export.mov'))
        (output/('ENGINE_TEST_media_ui_'+stage+'_saved_project.json')).write_text(json.dumps(saved, indent=2), encoding='utf-8')
    except Exception as error:
        result['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            result['process_error'] = (error.stderr or b'').decode(errors='replace')[-1600:]
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=.2)
        if store:
            store.shutdown()
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    checks['bounded_whole_stage'] = result['elapsed_seconds'] < 17
    result['passed'] = bool(checks) and all(checks.values()) and 'error' not in result
    if result['passed']:
        checkpoint['last_stage'] = stage
        checkpoint['stages'][stage] = result
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding='utf-8')
        result['completed_stage_count'] = len(checkpoint['stages'])
        result['complete'] = stage == STAGES[-1]
    elif 'error' not in result:
        result['error'] = result.get('ui', {}).get('error') or 'Failed checks: '+', '.join(key for key, value in checks.items() if not value)
    (output/('ENGINE_TEST_media_ui_'+stage+'_report.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=STAGES, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        print(json.dumps({'status': 'skipped', 'reason': 'Actual macOS WKWebView is required; no native result is simulated.'}))
        raise SystemExit(0)
    if not args.binary or not args.binary.is_file():
        parser.error('Pass the compiled macos/SmokeTest.swift executable with --binary.')
    result = run(args.binary, args.output, args.stage)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)

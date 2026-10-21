#!/usr/bin/env python3
"""Real normal or longer bounded Wan inference via native controls, with retained evidence.

Explicit CLI acceptance only. It uses the installed pinned runtime, creates an
isolated project, executes one to three real takes serially, and independently
decodes their admitted media. No inference runs during unittest discovery.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from server import Server, Store
from test_editing_ui_macos import read_helper_result
from macos.verify_generated_take import verify_take

HERE = Path(__file__).resolve().parent


def write_json(path, value):
    temporary = path.with_suffix('.part')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    os.replace(temporary, path)


def run(binary, evidence, repeats=2, frames=17):
    if frames not in (17, 33):
        raise ValueError('Native inference acceptance supports 17 or 33 requested frames.')
    per_take_timeout = 1200 if frames == 17 else 2400
    evidence = Path(evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    store = server = thread = monitor = None
    finished = threading.Event()
    scope = 'normal-preset' if frames == 17 else 'longer bounded 33-frame'
    result = {'passed': False, 'scope': f'Actual {scope} Wan inference through WKWebView controls',
              'requested': {'width': 480, 'height': 272, 'frames': frames, 'steps': 20,
                            'fps': 16, 'cfg': 6, 'repeats': repeats},
              'per_take_timeout_seconds': per_take_timeout,
              'checks': {}, 'takes': []}
    checks = result['checks']
    source = {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(HERE.rglob('*')) if path.is_file() and path.suffix in {'.py', '.js', '.json', '.swift'}
              and '__pycache__' not in path.parts}
    write_json(evidence / 'source-files.json', source)
    try:
        store = Store(evidence / 'workspace')
        project = store.new_project({'name': 'ENGINE TEST — real ' + ('normal' if frames == 17 else 'longer bounded') + ' generation',
                                     'width': 480, 'height': 272, 'fps': 16})
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        thread.start()

        def observe():
            while not finished.is_set():
                with store.lock:
                    jobs = [{key: copy.deepcopy(job.get(key)) for key in ('id', 'kind', 'state', 'progress', 'error', 'created_at', 'finished_at')}
                            for job in store.jobs.values() if job['kind'] != 'frame-preview']
                write_json(evidence / 'status.json', {'state': 'RUNNING', 'elapsed_seconds': round(time.monotonic() - began, 1), 'jobs': jobs})
                finished.wait(2)

        monitor = threading.Thread(target=observe, daemon=True)
        monitor.start()
        timeout = 300 + repeats * per_take_timeout
        native = subprocess.run([str(Path(binary).resolve()), '--url', f'http://127.0.0.1:{server.server_port}/?acceptance_repeats={repeats}&acceptance_frames={frames}',
                                 '--output', str(evidence / 'ENGINE_TEST_generation_native.png'), '--timeout', str(timeout),
                                 '--script', str(HERE / 'macos/GenerationInferenceSmoke.js')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout + 15)
        (evidence / 'native.stdout').write_text(native.stdout)
        (evidence / 'native.stderr').write_text(native.stderr)
        ui = read_helper_result(native)
        result['ui'] = ui
        checks['native_generation_controls_completed'] = native.returncode == 0 and ui.get('passed') is True
        checks['no_uncaught_browser_errors'] = not ui.get('page_errors', [])
        with store.lock:
            jobs = copy.deepcopy(list(store.jobs.values()))
        generated = [job for job in jobs if job['kind'] == 'generate']
        checks['exact_requested_number_of_serial_completed_takes'] = len(generated) == repeats and all(job['state'] == 'completed' for job in generated)
        checks['one_actual_owned_engine_start'] = len([job for job in jobs if job['kind'] == 'generation-start' and job['state'] == 'completed']) == 1
        checks['native_and_durable_job_identities_match'] = {item.get('job_id') for item in ui.get('takes', [])} == {job['id'] for job in generated}
        for index, job in enumerate(generated):
            if job['state'] != 'completed':
                result['takes'].append({'job_id': job['id'], 'state': job['state'], 'error': job['error']})
                continue
            report, _ = verify_take(store.project_dir(project['id']), store.root / 'jobs' / (job['id'] + '.json'),
                                    evidence=evidence / ('take-%02d' % (index + 1)), timeout=12)
            result['takes'].append(report)
            checks['take_%d_independent_decode_and_receipts' % (index + 1)] = report['passed']
            request = report.get('requested', {})
            preset_check = 'normal_preset' if frames == 17 else 'longer_bounded_preset'
            checks['take_%d_%s' % (index + 1, preset_check)] = all(request.get(key) == expected for key, expected in
                {'width': 480, 'height': 272, 'frames': frames, 'steps': 20, 'fps': 16, 'cfg': 6}.items())
        checks['distinct_actual_take_media'] = len({take.get('source_sha256') for take in result['takes'] if take.get('passed')}) == repeats
        result['project_directory'] = str(store.project_dir(project['id']))
        result['jobs_directory'] = str(store.root / 'jobs')
        checks['no_rendered_or_imported_substitute_jobs'] = all(job['kind'] in {'generation-start', 'generate', 'frame-preview'} for job in jobs)
        if not all(checks.values()):
            result['error'] = ui.get('error') or 'Failed checks: ' + ', '.join(key for key, value in checks.items() if not value)
    except Exception as error:
        result['error'] = str(error)
    finally:
        finished.set()
        if monitor is not None: monitor.join(timeout=3)
        if server is not None: server.shutdown(); server.server_close()
        if thread is not None: thread.join(timeout=3)
        if store is not None: store.shutdown()
    result['elapsed_seconds'] = round(time.monotonic() - began, 3)
    result['passed'] = bool(checks) and all(checks.values()) and 'error' not in result
    write_json(evidence / 'report.json', result)
    write_json(evidence / 'status.json', {'state': 'PASSED' if result['passed'] else 'FAILED', 'elapsed_seconds': result['elapsed_seconds'],
                                        'report': str(evidence / 'report.json'), 'error': result.get('error')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=2)
    parser.add_argument('--frames', type=int, choices=(17, 33), default=17,
                        help='Keep the normal 17-frame preset or request one bounded longer 33-frame case.')
    args = parser.parse_args()
    if sys.platform != 'darwin': parser.error('Actual native inference acceptance requires macOS.')
    if not args.binary.is_file(): parser.error('Pass the compiled SmokeTest.swift helper.')
    result = run(args.binary, args.output, args.repeats, args.frames)
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

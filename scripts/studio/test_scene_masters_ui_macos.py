#!/usr/bin/env python3
"""WKWebView authorship → actual scene job → downloadable EXR archive proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile

from server import Server, Store


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM', 'browser': 'WKWebView', 'checks': {}}
    checks = result['checks']
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='cinematicum-masters-webkit-TEST-') as temporary:
        store = Store(Path(temporary)/'workspace')
        server = thread = None
        try:
            project = store.new_project({'name': 'ENGINE TEST scene master authoring', 'fps': 24, 'width': 32, 'height': 32})
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
            thread.start()
            origin = 'http://127.0.0.1:'+str(server.server_port)
            screenshot = output/'ENGINE_TEST_scene_master_controls.png'
            process = subprocess.run([str(Path(binary).resolve()), '--url', origin, '--output', str(screenshot),
                '--script', str(Path(__file__).parent/'macos'/'SceneMastersSmoke.js'), '--timeout', '16'],
                capture_output=True, text=True, timeout=18)
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
                raise RuntimeError('Native helper returned no result: '+(process.stderr or process.stdout)[-1800:])
            result['ui'] = ui
            checks['native_output_controls_and_undo'] = process.returncode == 0 and ui.get('passed') is True
            saved = store.get(project['id'])
            spec = saved['settings']['scene']
            checks['output_and_alpha_recipe_saved'] = (spec['world']['transparent'] is True and spec['output'] == {'linear_exr': True, 'passes': ['depth', 'normal']})
            checks['full_scene_and_camera_policy_preserved'] = spec['frame_end'] == 3 and spec['camera']['orientation_mode'] == 'transport'
            with store.lock:
                jobs = json.loads(json.dumps([j for j in store.jobs.values() if j['project_id'] == project['id'] and j['kind'] == 'scene']))
            completed = [job for job in jobs if job['state'] == 'completed']
            checks['actual_scene_job_completed'] = len(completed) == 1
            if completed:
                job = completed[0]
                snapshot = json.loads((store.root/'jobs'/(job['id']+'.snapshot')).read_text(encoding='utf-8'))
                checks['requested_range_is_one_frame_without_trimming_recipe'] = snapshot['frame_start'] == snapshot['frame_end'] == 2
                record = job['result']
                checks['native_master_download_link'] = ui.get('masters_href') == record['masters_url']+'?download=1'
                with urllib.request.urlopen(origin+record['masters_url']+'?download=1', timeout=2) as response:
                    data = response.read(16*1024*1024)
                    checks['archive_route_has_download_headers_and_digest'] = response.status == 200 and 'attachment' in response.headers.get('Content-Disposition', '') and hashlib.sha256(data).hexdigest() == record['masters_sha256']
                archive_path = output/'ENGINE_TEST_ui_scene_masters.zip'
                archive_path.write_bytes(data)
                with zipfile.ZipFile(archive_path) as archive:
                    manifest = json.loads(archive.read('manifest.json'))
                    checks['actual_exr_frame_and_passes_in_download'] = (archive.testzip() is None and manifest['frame_count'] == 1 and manifest['frame_start'] == 2
                        and len(manifest['files']) == 2 and manifest['passes'] == ['depth', 'normal'])
                checks['display_movie_admitted'] = any(a['id'] == record['asset']['id'] and a['kind'] == 'video' for a in saved['assets'])
            checks['native_snapshot'] = screenshot.is_file() and screenshot.stat().st_size > 1000
            result['passed'] = bool(checks) and all(checks.values())
            if not result['passed']:
                result['error'] = ui.get('error') or 'Failed checks: '+', '.join(k for k, v in checks.items() if not v)
        except Exception as error:
            result['error'] = str(error)
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=1)
            store.shutdown()
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    (output/'ENGINE_TEST_scene_masters_ui_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.binary, args.output)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get('passed') else 1)

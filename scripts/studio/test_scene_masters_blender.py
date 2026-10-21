#!/usr/bin/env python3
"""Actual Cycles scene-linear EXR, alpha and numerical pass acceptance.

Run with the managed imaging Python (NumPy/OpenEXR installed). The middle
frame of a tiny moving emission plane is rendered; this is not film footage.
The production renderer produces the MP4, retained .blend and EXR archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import zipfile

import scene
from adapters import AdapterError, find_blender


def run(output, timeout=16):
    try:
        import numpy as np
        import OpenEXR
    except ImportError:
        return {'status': 'skipped', 'reason': 'The managed imaging Python with NumPy and OpenEXR is required for independent pixel decoding.'}
    if not find_blender() or not shutil.which('ffmpeg'):
        return {'status': 'skipped', 'reason': 'Actual Blender and FFmpeg are required; no render proof claimed.'}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    spec = scene.default_scene(32, 32)
    spec.update(frame_end=3, samples=4)
    spec['world'] = {'color': '#000000', 'strength': 0., 'transparent': True}
    spec['lights'] = []
    spec['render'].update(use_denoising=False, seed=91)
    spec['output'] = {'linear_exr': True, 'passes': list(scene.PASS_CHANNELS)}
    spec['camera'].update(position=[0, 0, 3], target=[0, 0, 0], fov=45)
    spec['objects'] = [{'id': 'test_linear_plane', 'name': 'ENGINE TEST linear emission plane', 'type': 'plane',
                        'position': [0, 0, 0], 'rotation': [0, -30, 0], 'scale': [.7, .7, 1],
                        'keyframes': [{'frame': 1, 'position': [-.2, 0, 0]}, {'frame': 3, 'position': [.2, 0, 0]}],
                        # IOR 1 isolates the diffuse albedo: the default 1.5
                        # legitimately assigns energy to the specular layer.
                        'material': {'color': '#808080', 'ior': 1., 'emission_color': '#ffffff', 'emission_strength': 4}}]
    spec = scene.validate_scene(spec)
    result = {'passed': False, 'fixture': 'SYNTHETIC ENGINE TEST — NOT A FILM', 'checks': {}}
    checks = result['checks']
    began = time.monotonic()
    deadline = began + timeout
    execute = scene._run_owned
    def bounded_execute(argv, log, cancel, requested_timeout, tick=lambda: None):
        remaining = deadline - time.monotonic()
        if remaining <= .5:
            raise AdapterError('Native master regression exhausted its bounded deadline.')
        return execute(argv, log, cancel, min(requested_timeout, remaining), tick)
    try:
        scene._run_owned = bounded_execute
        rendered = scene.render_scene(spec, output, fps={'numerator': 24000, 'denominator': 1001}, frame_start=2, frame_end=2)
        result['artifacts'] = {key: Path(rendered[key]).name for key in ('path', 'scene_path', 'masters_path')}
        checks['real_movie_and_retained_scene_and_masters'] = all(Path(rendered[key]).is_file() and Path(rendered[key]).stat().st_size > 100
            for key in ('path', 'scene_path', 'masters_path'))
        checks['archive_digest_matches_actual_bytes'] = hashlib.sha256(Path(rendered['masters_path']).read_bytes()).hexdigest() == rendered['masters_sha256']
        with zipfile.ZipFile(rendered['masters_path']) as archive:
            checks['zip_crc_verified'] = archive.testzip() is None
            manifest = json.loads(archive.read('manifest.json'))
            checks['exact_fractional_clock_retained'] = manifest['frame_rate'] == {'numerator': 24000, 'denominator': 1001}
            checks['saved_recipe_matches_authorship'] = json.loads(archive.read('scene.json')) == spec
            checks['one_middle_frame_retains_complete_animation'] = (manifest['frame_start'] == manifest['frame_end'] == 2
                and manifest['frame_count'] == 1 and spec['frame_end'] == 3)
            checks['all_requested_files_and_actual_hashes_present'] = len(manifest['files']) == 2 and all(
                hashlib.sha256(archive.read(record['path'])).hexdigest() == record['sha256'] for record in manifest['files'])
            with tempfile.TemporaryDirectory(prefix='linear-decode-TEST-', dir=str(output)) as temporary:
                files = {}
                for role in ('beauty', 'passes'):
                    path = Path(temporary)/(role+'.exr')
                    record = next(record for record in manifest['files'] if record['role'] == role)
                    path.write_bytes(archive.read(record['path']))
                    with OpenEXR.File(str(path), separate_channels=True) as decoded:
                        files[role] = {name: channel.pixels.copy() for name, channel in decoded.channels().items()}
        checks['actual_channels_are_float32'] = all(values.dtype == np.float32 for channels in files.values() for values in channels.values())
        checks['actual_pixels_have_expected_dimensions'] = all(values.shape == (32, 32) for channels in files.values() for values in channels.values())
        beauty = files['beauty']
        alpha, red = beauty['A'], beauty['R']
        inside = alpha > .999
        checks['transparent_silhouette_retained'] = float(alpha.min()) == 0 and float(alpha.max()) > .999 and int(inside.sum()) > 30
        checks['bright_scene_linear_values_exceed_display_white'] = float(red[inside].min()) > 3.9
        checks['actual_alpha_is_premultiplied'] = float(np.max(np.abs(red - 4 * alpha))) < .02
        passes = files['passes']
        def channel(*names):
            return next(value for key, value in passes.items() if any(key == name or key.endswith('.'+name) for name in names))
        nx, nz, depth = channel('Normal.X'), channel('Normal.Z'), channel('Depth.Z')
        checks['normal_pass_preserves_negative_world_components'] = float(nx[inside].min()) < -.45 and float(nz[inside].min()) > .8
        checks['depth_pass_contains_actual_scene_distances'] = 2.5 < float(depth[inside].min()) < 3.5 and float(depth[inside].max()) < 4
        vectors = {c: channel('Vector.'+c)[inside] for c in 'XYZW'}
        # A 0.2 m horizontal step at ~3 m depth, 32px / 45-degree projection,
        # moves the plane ~2.6 pixels per frame. Both temporal vectors must
        # contain genuine pixel displacements, not normalized color or zero.
        horizontal_medians = {c: float(np.median(np.abs(vectors[c]))) for c in 'XZ'}
        checks['moving_motion_vectors_preserve_pixel_displacement'] = all(1.5 < value < 4 for value in horizontal_medians.values())
        checks['horizontal_motion_has_no_vertical_flow'] = all(float(np.max(np.abs(vectors[c]))) < .02 for c in 'YW')
        checks['emission_pass_preserves_unclipped_radiance'] = all(float(channel('Emission.'+c, 'Emit.'+c)[inside].min()) > 3.9 for c in 'RGB')
        linear_gray = ((128/255 + .055)/1.055)**2.4
        diffuse_red = channel('Diffuse Color.R', 'DiffCol.R')
        checks['diffuse_pass_preserves_linear_matte_albedo'] = abs(float(np.mean(diffuse_red[inside]))-linear_gray) < .002
        result['renderer'] = manifest['renderer']
        result['metrics'] = {'beauty_red_max': float(red.max()), 'alpha_min': float(alpha.min()), 'alpha_max': float(alpha.max()),
                              'premultiplied_error': float(np.max(np.abs(red - 4*alpha))),
                              'normal_x_min': float(nx[inside].min()), 'depth_min_m': float(depth[inside].min()),
                              'depth_max_m': float(depth[inside].max()), 'covered_pixels': int(inside.sum()),
                              'diffuse_red_mean': float(np.mean(diffuse_red[inside])),
                              'motion_vector_medians': {c: float(np.median(vectors[c])) for c in 'XYZW'},
                              'motion_vector_horizontal_abs_medians': horizontal_medians,
                              'pass_channels': sorted(passes)}
        result['passed'] = bool(checks) and all(checks.values())
        if not result['passed']:
            result['error'] = 'Failed checks: ' + ', '.join(key for key, value in checks.items() if not value)
    except Exception as error:
        result['error'] = str(error)
    finally:
        scene._run_owned = execute
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    (output/'ENGINE_TEST_scene_masters_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=16)
    args = parser.parse_args()
    result = run(args.output, min(17., max(1., args.timeout)))
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get('passed') or result.get('status') == 'skipped' else 1)

"""Real FFV1/PCM acceptance for bounded variable-speed and optical-flow retiming.

Every picture and tone is synthetic ENGINE TEST media. The independent oracles
use a literal quadratic source clock, analytically translated texture, and
continuous low-frequency sinusoids; they do not call the retimer's worker math.
Runtime-dependent cases require the actual pinned NumPy/OpenCV environment.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import threading
import unittest

import retime
from engine import RenderCancelled, probe_media, render_project, validate_project
from frame_preview import render_frame
from project_archive import export_archive, import_archive

try:
    import numpy as np
except ImportError:
    np = None


WIDTH, HEIGHT, SOURCE_FRAMES, SAMPLE_RATE = 96, 64, 24, 48_000
FFMPEG = shutil.which('ffmpeg')


def origin_document(value):
    value = Fraction(str(value))
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def recipe(duration=12, method='nearest', audio='varispeed', speed0=.5, speed1=1.5, origin=4):
    return {'version': 1, 'method': method, 'audio': audio, 'offset': 0,
            'source_origin': origin_document(origin),
            'keys': [{'frame': 0, 'speed': speed0},
                     {'frame': duration, 'speed': speed1}]}


def ramp_clip(duration=12, **changes):
    clip = {'id': 'ramp', 'asset_id': 'source', 'track': 0, 'start': 0,
            'in': 4, 'duration': duration, 'speed': 1, 'reverse': False,
            'audio': {'stream_index': 2, 'channels': [1, 0]},
            'retime': recipe(duration)}
    clip.update(changes)
    if clip['retime']['offset'] == 0:
        clip['retime'] = copy.deepcopy(clip['retime'])
        clip['retime']['source_origin'] = origin_document(clip['in'])
    return clip


class RetimeClockValidationTests(unittest.TestCase):
    def test_exact_quadratic_integral_endpoint_extension_and_split_identity(self):
        # speed(u) = 1/2 + u/12; F(u) = u/2 + u*u/24 inside [0,12].
        curve = recipe()
        for tick in range(-4, 53):
            u = Fraction(tick, 4)
            expected = u/2 if u < 0 else 12 + (u-12)*Fraction(3, 2) if u > 12 else u/2 + u*u/24
            with self.subTest(frame=str(u)):
                self.assertEqual(retime.integral(curve, u), expected)
        whole = ramp_clip()
        right = ramp_clip(duration=8, start=4, **{'in': float(Fraction(20, 3))})
        right['retime'] = copy.deepcopy(curve)
        right['retime']['offset'] = 4
        for tick in range(33):
            t = Fraction(tick, 4)
            # Compare deltas exactly; JSON numbers cannot encode 20/3 exactly.
            self.assertEqual(retime.source_delta(right, t),
                             retime.source_delta(whole, t+4)-Fraction(8, 3))
        self.assertEqual(retime.source_delta({'speed': 1.5}, Fraction(7, 3)), Fraction(7, 2))

    def test_piecewise_curve_uses_exact_area_and_unchanged_tail_domain(self):
        curve = recipe()
        curve['keys'] = [{'frame': 0, 'speed': .5}, {'frame': 4, 'speed': 1.5},
                         {'frame': 12, 'speed': .5}]
        self.assertEqual(retime.integral(curve, 4), 4)
        self.assertEqual(retime.integral(curve, 8), 9)
        self.assertEqual(retime.integral(curve, 12), 12)
        curve['offset'] = 4
        normalized = retime.validate_recipe(curve, 8)
        self.assertEqual(normalized['keys'], curve['keys'])
        self.assertEqual(normalized['offset'], 4)
        with self.assertRaisesRegex(ValueError, 'domain'):
            retime.validate_recipe(curve, 9)

    def test_recipe_refuses_unknown_operators_nonfinite_and_unbounded_curves(self):
        cases = []
        for key, value in (('version', True), ('version', 2), ('method', 'blend'),
                           ('audio', 'preserve_pitch'), ('offset', -1), ('offset', .5),
                           ('offset', 12), ('unknown_operator', True)):
            value_recipe = recipe()
            value_recipe[key] = value
            cases.append(value_recipe)
        for keys in ([], [{'frame': 0, 'speed': 1}],
                     [{'frame': i, 'speed': 1} for i in range(33)],
                     [{'frame': 1, 'speed': 1}, {'frame': 12, 'speed': 1}],
                     [{'frame': 0, 'speed': 1}, {'frame': 0, 'speed': 1}],
                     [{'frame': 0, 'speed': 1}, {'frame': 12.5, 'speed': 1}],
                     [{'frame': 0, 'speed': 1}, {'frame': 241, 'speed': 1}],
                     [{'frame': 0, 'speed': 1, 'ease': 'smooth'}, {'frame': 12, 'speed': 1}]):
            value_recipe = recipe()
            value_recipe['keys'] = keys
            cases.append(value_recipe)
        for speed in (0, .249, 4.001, float('nan'), float('inf'), True):
            value_recipe = recipe()
            value_recipe['keys'][0]['speed'] = speed
            cases.append(value_recipe)
        for origin in (None, {}, {'numerator': '0', 'denominator': '1', 'extra': 1},
                       {'numerator': 4, 'denominator': '1'},
                       {'numerator': '-1', 'denominator': '1'},
                       {'numerator': '01', 'denominator': '1'},
                       {'numerator': '0', 'denominator': '0'},
                       {'numerator': '1', 'denominator': '-1'},
                       {'numerator': '1.5', 'denominator': '1'},
                       {'numerator': '10000001', 'denominator': '1'},
                       {'numerator': '1', 'denominator': '9'*257}):
            value_recipe = recipe()
            value_recipe['source_origin'] = origin
            cases.append(value_recipe)
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                retime.validate_recipe(value, 12)
        self.assertEqual(retime.validate_recipe(recipe(speed0=.25, speed1=4), 12)['keys'][-1]['speed'], 4)

    def test_source_precision_binding_and_real_picture_handle_limits(self):
        # Metadata-only refusal tests are separate from decoded-media cases.
        project = {'fps': 24, 'settings': {}}
        source = {'kind': 'video', 'duration': 30, 'width': WIDTH, 'height': HEIGHT,
                  'sha256': '0'*64, 'pixel_format': 'gbrp'}
        cases = [({'settings': {'image_precision': precision}}, {}, {})
                 for precision in ('high16', 'float32')]
        cases += [({}, change, {}) for change in (
            {'speed': 2}, {'reverse': True}, {'sequence_id': 'nested'},
            {'multicam': {'group_id': 'bound'}}, {'tracking': {'samples': [1]}},
            {'planar_motion': {'keys': [1]}}, {'learned_recipe': {'model': 'bound'}},
            {'learned_bindings': [1]},
            {'compositor': {'nodes': [{'tracking_source': {'clip_id': 'ramp'}}]}})]
        cases += [({}, {}, change) for change in (
            {'kind': 'image'}, {'sha256': ''}, {'sha256': 'A'*64},
            {'width': 1281}, {'height': 15}, {'width': 1280, 'height': 721},
            {'pixel_format': 'gbrap16le'}, {'color_transfer': 'smpte2084'},
            {'color_transfer': 'arib-std-b67'}, {'duration': .1})]
        for index, (project_change, clip_change, source_change) in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                retime.validate_clip({**project, **project_change},
                                     ramp_clip(**clip_change), {**source, **source_change})
        audio = {**source, 'kind': 'audio', 'width': 0, 'height': 0}
        flow_clip = ramp_clip(retime=recipe(method='optical_flow'))
        with self.assertRaisesRegex(ValueError, 'requires video'):
            retime.validate_clip(project, flow_clip, audio)
        # The integrated endpoint fits, but nearest/flow would need frame 24.
        tail = ramp_clip(duration=1, **{'in': 23.6}, retime=recipe(1, speed0=.25, speed1=.25))
        for method in ('nearest', 'optical_flow'):
            tail['retime']['method'] = method
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'real final source-picture handle'):
                retime.validate_clip(project, tail, {**source, 'duration': 1})
        # Nearest 23.4 only needs 23; forcing an unnecessary ceil would reject it.
        tail['in'] = 23.4
        tail['retime']['source_origin'] = origin_document(23.4)
        tail['retime']['method'] = 'nearest'
        retime.validate_clip(project, tail, {**source, 'duration': 1})
        large = ramp_clip(duration=240, **{'in': 0}, retime=recipe(240, speed0=4, speed1=4))
        with self.assertRaisesRegex(ValueError, '512 MiB'):
            retime.validate_clip(project, large, {**source, 'duration': 60, 'width': 1280, 'height': 720})

    def test_timewarped_ancestors_and_expanded_ramp_instance_limits_are_explicit(self):
        project = {'sequence_id': 'main', 'sequence_name': 'Main',
                   'clips': [{'id': 'instance', 'sequence_id': 'child', 'speed': 1, 'reverse': False}],
                   'sequences': [{'id': 'child', 'name': 'Child', 'clips': [ramp_clip()]}]}
        retime.validate_project_ramps(project)
        for change in ({'speed': .5}, {'reverse': True}):
            invalid = copy.deepcopy(project)
            invalid['clips'][0].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'cannot be retimed/reversed'):
                retime.validate_project_ramps(invalid)
        project['clips'] *= 17
        with self.assertRaisesRegex(ValueError, '16 ramp instances'):
            retime.validate_project_ramps(project)
        project['clips'] = []
        project['sequences'][0]['clips'] *= 17
        with self.assertRaisesRegex(ValueError, '16 authored ramp clips'):
            retime.validate_project_ramps(project)

    def test_exact_origin_is_normalized_and_visible_in_cannot_replace_it(self):
        curve = recipe()
        curve['source_origin'] = {'numerator': '8', 'denominator': '2'}
        self.assertEqual(retime.validate_recipe(curve, 12)['source_origin'], origin_document(4))
        clip = ramp_clip()
        project = {'fps': 24, 'settings': {}}
        asset = {'kind': 'video', 'duration': 30, 'width': WIDTH, 'height': HEIGHT,
                 'sha256': '0'*64, 'pixel_format': 'gbrp'}
        clip['in'] += 1e-6
        with self.assertRaisesRegex(ValueError, 'retained speed-curve origin'):
            retime.validate_clip(project, clip, asset)

    def test_unchanged_local_curve_retains_exact_half_frame_and_hidden_handles(self):
        # This no-op formerly changed the nearest picture from source 4 to 3.
        curve = recipe(9, speed0=.75, speed1=.25, origin=0)
        curve['offset'] = 2
        clip = ramp_clip(duration=7, **{'in': float(Fraction(25, 18))}, retime=curve)
        project = {'fps': 24, 'tracks': [], 'clips': [clip]}
        old = copy.deepcopy(clip)
        self.assertEqual(retime.source_position(clip, 4), Fraction(7, 2))
        self.assertEqual(math.floor(retime.source_position(clip, 4)+Fraction(1, 2)), 4)
        local = retime.local_keys(clip)
        self.assertEqual(local[0]['speed'], .6388888888888888)
        retime.apply_edit(project, {'clip_id': clip['id'], 'duration': 7,
                                   'method': 'optical_flow', 'audio': 'mute', 'keys': local})
        self.assertEqual(clip['retime'], {**old['retime'], 'method': 'optical_flow', 'audio': 'mute'})
        self.assertEqual(clip['in'], old['in'])
        self.assertEqual(retime.source_position(clip, 4), Fraction(7, 2))
        # A genuine curve edit starts at the exact old source coordinate.
        changed = [{'frame': 0, 'speed': 1}, {'frame': 7, 'speed': 1}]
        retime.apply_edit(project, {'clip_id': clip['id'], 'duration': 7,
                                   'method': 'nearest', 'audio': 'varispeed', 'keys': changed})
        self.assertEqual(clip['retime']['offset'], 0)
        self.assertEqual(clip['retime']['source_origin'], {'numerator': '25', 'denominator': '18'})
        self.assertEqual(retime.source_position(clip, 0), Fraction(25, 18))

    def test_dependent_measured_corner_pin_cannot_survive_ramped_background(self):
        project = {'sequence_id': 'main', 'sequence_name': 'Main', 'clips': [ramp_clip(),
                   {'id': 'pin', 'planar_motion': {'source': {'source': {'clip_id': 'ramp'}}}}]}
        with self.assertRaisesRegex(ValueError, 'dependent measured corner pins'):
            retime.validate_project_ramps(project)

    @unittest.skipUnless(shutil.which('node'), 'Node required for the shipped exact browser clock')
    def test_browser_bigint_clock_and_splits_match_independent_rational_oracle(self):
        rng = random.Random(22907)
        cases = []
        inputs = [(9, Fraction(3, 4), Fraction(1, 4), 2, Fraction(0)),
                  (6, Fraction(1, 4), Fraction(5, 4), 1, Fraction(0))]
        for _ in range(96):
            duration = rng.randint(3, 24)
            inputs.append((duration, Fraction(rng.randint(1, 16), 4), Fraction(rng.randint(1, 16), 4),
                           rng.randint(1, duration-1), Fraction(rng.randint(0, 32), rng.randint(1, 17))))
        for duration, first, last, offset, anchor in inputs:
            curve = recipe(duration, speed0=float(first), speed1=float(last), origin=anchor)
            source = lambda t: anchor+first*t+(last-first)*t*t/(2*duration)
            origin = origin_document(source(offset))
            cases.append({'clip': {'in': float(anchor), 'start': 5, 'duration': duration, 'retime': curve},
                          'offset': offset, 'anchor_at_cut': origin,
                          'expected': [math.floor(source(offset+i)+Fraction(1, 2)) for i in range(duration-offset)]})
        script = r'''
        const fs=require('fs'),vm=require('vm'),assert=require('assert');
        global.window={};vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
        const model=window.CinematicumRetimeModel,cases=JSON.parse(fs.readFileSync(0,'utf8'));
        let frames=0;
        for(const item of cases){
          const original=item.clip,cut={...original,...model.slice(original,item.offset),start:original.start+item.offset,duration:original.duration-item.offset};
          assert.deepStrictEqual(cut.retime.source_origin,original.retime.source_origin);
          assert.deepStrictEqual(model.sourceOrigin(cut),item.anchor_at_cut);
          for(let t=0;t<cut.duration;t++){
            assert.strictEqual(model.nearestFrame(cut,t),item.expected[t]);
            assert.strictEqual(model.nearestFrame(original,item.offset+t),item.expected[t]);frames++;
          }
          const restored=model.trim(cut,'left',original.start,10000000);
          assert.strictEqual(restored.retime.offset,0);assert.strictEqual(restored.in,model.sourceFrame(original,0));
          assert.deepStrictEqual(restored.retime.source_origin,original.retime.source_origin);
        }
        process.stdout.write(JSON.stringify({cases:cases.length,frames}));
        '''
        result = subprocess.run([shutil.which('node'), '-e', script,
                                 str(Path(__file__).with_name('web')/'retime-model.js')],
                                input=json.dumps(cases), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['cases'], 98)
        self.assertGreater(report['frames'], 500)


@unittest.skipUnless(FFMPEG and shutil.which('ffprobe') and np is not None,
                     'Actual FFmpeg, ffprobe and NumPy are required')
class RetimeMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = retime.capabilities()
        if not cls.runtime.get('available'):
            raise unittest.SkipTest(cls.runtime.get('reason', 'Pinned Tracking runtime unavailable'))
        cls.temp = tempfile.TemporaryDirectory(prefix='cinematicum-retime-ENGINE-TEST-')
        cls.root = Path(cls.temp.name)
        (cls.root/'media').mkdir()
        cls.observations = {}
        # Integer motion has an independent halfway image: one-pixel shifted
        # original texture, without using any flow/interpolation implementation.
        rng = np.random.default_rng(190473)
        gray = rng.uniform(0, 255, (112, 192))
        for axis in (0, 1):
            gray = (np.roll(gray, -1, axis)+2*gray+np.roll(gray, 1, axis))/4
        cls.texture = np.stack((gray, np.roll(gray, 3, 0)*.8+17,
                                np.roll(gray, 4, 1)*.65+29), axis=2).round().astype('uint8')
        cls.frames = np.stack([cls.texture[24:24+HEIGHT, 24+2*f:24+2*f+WIDTH]
                               for f in range(SOURCE_FRAMES)])
        n = np.arange(SAMPLE_RATE, dtype=np.float64)
        cls.selected = cls.tones(n).astype('<f4')
        cls.other = np.stack((.2*np.sin(2*np.pi*14_000*n/SAMPLE_RATE),
                              .2*np.sin(2*np.pi*300*n/SAMPLE_RATE)), axis=1).astype('<f4')
        picture = cls.root/'picture.rgb'
        sound0, sound1 = cls.root/'other.f32', cls.root/'selected.f32'
        picture.write_bytes(cls.frames.tobytes())
        sound0.write_bytes(cls.other.tobytes())
        sound1.write_bytes(cls.selected.tobytes())
        cls.source = cls.root/'media/ENGINE_TEST_retime.mkv'
        cls.ffmpeg(['-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '96x64',
                    '-framerate', '24', '-i', str(picture),
                    '-f', 'f32le', '-ar', '48000', '-ac', '2', '-i', str(sound0),
                    '-f', 'f32le', '-ar', '48000', '-ac', '2', '-i', str(sound1),
                    '-map', '0:v:0', '-map', '1:a:0', '-map', '2:a:0',
                    '-c:v', 'ffv1', '-pix_fmt', 'gbrp', '-c:a', 'pcm_f32le', str(cls.source)])
        cls.asset = {**probe_media(cls.source), 'id': 'source', 'name': cls.source.name,
                     'path': 'media/'+cls.source.name,
                     'sha256': hashlib.sha256(cls.source.read_bytes()).hexdigest()}
        if not np.array_equal(cls.pictures(cls.source), cls.frames):
            raise AssertionError('FFV1 fixture did not preserve its independent RGB source pixels')
        if not np.array_equal(cls.pcm(cls.source, '0:2'), cls.selected):
            raise AssertionError('PCM fixture did not preserve its independent selected source samples')
        cls.audio_source = cls.root/'media/ENGINE_TEST_audio_only.wav'
        cls.ffmpeg(['-f', 'f32le', '-ar', '48000', '-ac', '2', '-i', str(sound1),
                    '-c:a', 'pcm_f32le', str(cls.audio_source)])
        cls.audio_asset = {**probe_media(cls.audio_source), 'id': 'audio', 'name': cls.audio_source.name,
                           'path': 'media/'+cls.audio_source.name,
                           'sha256': hashlib.sha256(cls.audio_source.read_bytes()).hexdigest()}

    @classmethod
    def tearDownClass(cls):
        destination = os.environ.get('CINEMATICUM_RETIME_TEST_REPORT')
        if destination:
            record = {'kind': 'retime-real-media-test-observations',
                      'runtime': cls.runtime, 'ffmpeg_executable': FFMPEG,
                      'ffmpeg_version': subprocess.check_output([FFMPEG, '-version'], text=True).splitlines()[0],
                      'source_sha256': cls.asset['sha256'],
                      'fixture': {'width': WIDTH, 'height': HEIGHT, 'frames': SOURCE_FRAMES,
                                  'sample_rate': SAMPLE_RATE, 'source_sample_frames': SAMPLE_RATE},
                      'observations': cls.observations}
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
        cls.temp.cleanup()

    @staticmethod
    def ffmpeg(arguments, data=None):
        return subprocess.run([FFMPEG, '-v', 'error', '-nostdin', '-y', '-threads', '1',
                               '-filter_threads', '1', '-filter_complex_threads', '1']+arguments,
                              input=data, capture_output=True, check=True, timeout=30).stdout

    @staticmethod
    def tones(positions):
        phase = 2*np.pi*np.asarray(positions, dtype=np.float64)/SAMPLE_RATE
        left = .13*np.sin(211*phase+.2)+.035*np.cos(73*phase)
        right = .19*np.sin(317*phase-.4)+.025*np.cos(107*phase+.3)
        return np.stack((left, right), axis=-1)

    @classmethod
    def pictures(cls, path, width=WIDTH, height=HEIGHT):
        data = cls.ffmpeg(['-i', str(path), '-map', '0:v:0', '-pix_fmt', 'rgb24',
                           '-f', 'rawvideo', '-threads', '1', 'pipe:1'])
        return np.frombuffer(data, dtype='uint8').reshape((-1, height, width, 3))

    @classmethod
    def pcm(cls, path, stream='0:a:0'):
        data = cls.ffmpeg(['-i', str(path), '-map', stream, '-vn', '-ac', '2',
                           '-ar', '48000', '-f', 'f32le', 'pipe:1'])
        return np.frombuffer(data, dtype='<f4').reshape((-1, 2))

    def project(self, clip=None, rate=Fraction(24), asset=None):
        asset = copy.deepcopy(asset or self.asset)
        project = {'version': 1, 'id': 'retime-test', 'name': 'ENGINE TEST retime',
                   'width': WIDTH, 'height': HEIGHT,
                   'frame_rate': {'numerator': rate.numerator, 'denominator': rate.denominator},
                   'assets': [asset], 'clips': [copy.deepcopy(clip or ramp_clip())],
                   'titles': [], 'tracks': [], 'settings': {}}
        return validate_project(project, self.root)

    def prepare(self, project, name, *, origin=0):
        before = copy.deepcopy(project)
        clip = project['clips'][0]
        asset = next(a for a in project['assets'] if a['id'] == clip['asset_id'])
        output, media, receipt = retime.prepare(project, clip, asset, self.root,
                                                self.root/name, audio_origin=origin)
        self.assertEqual(project, before, 'Temporary retiming must not rewrite the project recipe or original asset')
        source = self.root/asset['path']
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), asset['sha256'])
        self.assertTrue(receipt['source_unchanged'])
        self.assertTrue(receipt['runtime_operations_executed'])
        self.assertEqual(receipt['source_sha256'], asset['sha256'])
        self.assertEqual(receipt['runtime_versions'], {'numpy': '2.3.5', 'opencv-python-headless': '4.11.0.86'})
        self.assertEqual(media['codec'], 'ffv1')
        self.assertTrue(media['has_audio'])
        self.assertEqual(json.loads((output.parent/'retime-report.json').read_text()), receipt)
        return output, receipt

    @staticmethod
    def analytic_source_samples(count, rate, origin, start, source_in, offset=0):
        # Independent exact lattice followed by literal F(u)=u/2+u²/24.
        absolute = Fraction(origin)+start
        first = round(absolute*SAMPLE_RATE/rate)
        phase = Fraction(first)-absolute*SAMPLE_RATE/rate
        local = (np.arange(count, dtype=np.float64)+float(phase))*float(rate)/SAMPLE_RATE
        u = local+offset
        integral = u/2+u*u/24
        # Tiny positions before zero use the defined endpoint derivative.
        integral = np.where(u < 0, u/2, integral)
        integral = np.where(u > 12, 12+(u-12)*1.5, integral)
        return (source_in+integral-(offset/2+offset*offset/24))*SAMPLE_RATE/float(rate)

    def test_nearest_actual_pixels_follow_quadratic_clock_and_selected_pcm(self):
        project = self.project()
        output, receipt = self.prepare(project, 'nearest-quadratic')
        expected_indices = [math.floor(4+Fraction(i, 2)+Fraction(i*i, 24)+Fraction(1, 2)) for i in range(12)]
        self.assertTrue(np.array_equal(self.pictures(output), self.frames[expected_indices]), expected_indices)
        np.testing.assert_allclose(receipt['source_frame_positions'], [4+i/2+i*i/24 for i in range(12)], rtol=0, atol=2e-15)
        actual = self.pcm(output)
        self.assertEqual(actual.shape, (24_000, 2))
        positions = self.analytic_source_samples(len(actual), Fraction(24), 0, 0, 4)
        expected = self.tones(positions)[:, [1, 0]]
        maximum = float(np.max(np.abs(actual-expected)))
        self.assertLess(maximum, 2e-5, 'Every output sample must follow the analytic continuous source clock')
        self.assertEqual(receipt['picture']['flow_pairs'], 0)
        self.assertFalse(receipt['audio']['pitch_preserved'])
        self.observations[self._testMethodName] = {'decoded_frames': 12, 'decoded_stereo_samples': len(actual),
                                                  'source_indices': expected_indices, 'max_sample_error': maximum}

    def test_optical_flow_reconstructs_real_midpoints_beyond_nearest_and_blend(self):
        clip = ramp_clip(retime=recipe(method='optical_flow', speed0=.5, speed1=.5))
        output, receipt = self.prepare(self.project(clip), 'optical-flow-midpoints')
        actual = self.pictures(output)
        self.assertEqual(len(actual), 12)
        midpoint_errors, nearest_errors, blend_errors = [], [], []
        for frame in range(12):
            source = Fraction(4)+Fraction(frame, 2)
            x = 24+int(2*source)
            expected = self.texture[24:24+HEIGHT, x:x+WIDTH]
            if frame % 2 == 0:
                self.assertTrue(np.array_equal(actual[frame], expected))
                continue
            lower, upper = math.floor(source), math.ceil(source)
            # Interior crop isolates known translation from newly exposed edges.
            crop = np.s_[12:-12, 12:-12, :]
            reference = expected[crop].astype(np.float64)
            midpoint_errors.append(float(np.sqrt(np.mean((actual[frame][crop]-reference)**2))))
            nearest_errors.append(float(np.sqrt(np.mean((self.frames[upper][crop]-reference)**2))))
            blended = (self.frames[lower][crop].astype(np.float64)+self.frames[upper][crop])/2
            blend_errors.append(float(np.sqrt(np.mean((blended-reference)**2))))
        self.assertGreater(receipt['picture']['flow_pairs'], 0)
        self.assertEqual(receipt['picture']['interpolated_frames'], 6)
        self.assertEqual(receipt['picture']['cut_fallback_frames'], 0)
        self.assertLess(max(midpoint_errors), 3)
        self.assertLess(sum(midpoint_errors), sum(nearest_errors)*.25)
        self.assertLess(sum(midpoint_errors), sum(blend_errors)*.35)
        self.observations[self._testMethodName] = {'flow_pairs': receipt['picture']['flow_pairs'],
            'interpolated_frames': 6, 'midpoint_rmse': midpoint_errors,
            'nearest_rmse': nearest_errors, 'linear_blend_rmse': blend_errors}

    def test_fractional_clock_every_sample_and_split_preserve_routing_and_phase(self):
        rate, origin = Fraction(30_000, 1001), Fraction(5, 2)
        whole = ramp_clip(start=7, **{'in': 3})
        project = self.project(whole, rate)
        output, receipt = self.prepare(project, 'fractional-whole', origin=origin)
        actual = self.pcm(output)
        first = round((origin+7)*SAMPLE_RATE/rate)
        count = round((origin+19)*SAMPLE_RATE/rate)-first
        self.assertEqual(count, 19_219)
        self.assertEqual(len(actual), count)
        expected = self.tones(self.analytic_source_samples(count, rate, origin, 7, 3))[:, [1, 0]]
        maximum = float(np.max(np.abs(actual-expected)))
        self.assertLess(maximum, 2e-5)
        self.assertEqual(receipt['absolute_audio_origin'], '19/2')
        self.assertEqual(receipt['selected_audio']['stream_index'], 2)
        self.assertEqual(receipt['selected_audio']['channels'], [1, 0])
        left = copy.deepcopy(whole)
        left['duration'] = 4
        right = copy.deepcopy(whole)
        right.update(id='right', start=11, duration=8)
        right['in'] = float(Fraction(17, 3))  # 3 + F(4) = 3 + 8/3.
        right['retime']['offset'] = 4
        left_path, left_receipt = self.prepare(self.project(left, rate), 'fractional-left', origin=origin)
        right_path, right_receipt = self.prepare(self.project(right, rate), 'fractional-right', origin=origin)
        split = np.concatenate((self.pcm(left_path), self.pcm(right_path)))
        self.assertEqual(left_receipt['output_samples'], 6407)
        self.assertEqual(right_receipt['output_samples'], 12812)
        self.assertEqual(split.shape, actual.shape)
        split_error = float(np.max(np.abs(split-actual)))
        self.assertLess(split_error, 1e-7, 'A split must preserve every continuous source phase, including the changed rounded sample origin')
        self.assertTrue(np.array_equal(np.concatenate((self.pictures(left_path), self.pictures(right_path))), self.pictures(output)))
        self.observations[self._testMethodName] = {'rate': '30000/1001', 'absolute_origin_frames': '19/2',
            'decoded_stereo_samples': count, 'left_samples': 6407, 'right_samples': 12812,
            'max_analytic_sample_error': maximum, 'max_split_sample_error': split_error}

    def test_fast_varispeed_antialias_filter_rejects_high_band_and_keeps_low_tone(self):
        clip = ramp_clip(duration=4, **{'in': 3}, audio={'stream_index': 1},
                         retime=recipe(4, speed0=4, speed1=4))
        output, receipt = self.prepare(self.project(clip), 'alias-suppression')
        actual = self.pcm(output)
        self.assertEqual(actual.shape, (8000, 2))
        high_rms = float(np.sqrt(np.mean(actual[:, 0].astype(np.float64)**2)))
        source_rms = float(np.sqrt(np.mean(self.other[:, 0].astype(np.float64)**2)))
        low_expected = .2*np.sin(2*np.pi*300*(6000+4*np.arange(8000))/SAMPLE_RATE)
        low_error = float(np.max(np.abs(actual[:, 1]-low_expected)))
        self.assertGreater(source_rms, .14)
        self.assertLess(high_rms, 2e-5, '14 kHz source must not alias to a loud 8 kHz tone at 4x')
        self.assertLess(low_error, 3e-5)
        self.assertFalse(receipt['audio']['pitch_preserved'])
        self.observations[self._testMethodName] = {'source_14khz_rms': source_rms,
            'retimed_rejected_band_rms': high_rms, 'rejection_db': 20*math.log10(max(high_rms, 1e-30)/source_rms),
            '300hz_to_1200hz_max_sample_error': low_error, 'decoded_stereo_samples': 8000}

    def test_mute_is_exact_silence_with_full_fractional_sample_count(self):
        rate = Fraction(30_000, 1001)
        clip = ramp_clip(duration=7, start=2, retime=recipe(7, audio='mute'))
        output, receipt = self.prepare(self.project(clip, rate), 'mute')
        actual = self.pcm(output)
        expected_count = round(9*SAMPLE_RATE/rate)-round(2*SAMPLE_RATE/rate)
        self.assertEqual(actual.shape, (expected_count, 2))
        self.assertEqual(actual.tobytes(), bytes(expected_count*8))
        self.assertEqual(len(self.pictures(output)), 7)
        self.assertEqual(receipt['audio']['mode'], 'mute')
        self.assertEqual(receipt['output_samples'], expected_count)
        self.observations[self._testMethodName] = {'decoded_stereo_samples': expected_count, 'nonzero_samples': 0}

    def test_audio_only_original_uses_same_curve_and_exact_black_picture_count(self):
        clip = ramp_clip(asset_id='audio', track=-1, audio={'stream_index': 0, 'channels': [1, 0]})
        project = self.project(clip, asset=self.audio_asset)
        output, receipt = self.prepare(project, 'audio-only')
        actual = self.pcm(output)
        self.assertEqual(actual.shape, (24_000, 2))
        expected = self.tones(self.analytic_source_samples(len(actual), Fraction(24), 0, 0, 4))[:, [1, 0]]
        maximum = float(np.max(np.abs(actual-expected)))
        self.assertLess(maximum, 2e-5)
        frames = self.pictures(output, 16, 16)
        self.assertEqual(frames.shape, (12, 16, 16, 3))
        self.assertFalse(np.any(frames))
        self.assertEqual(receipt['picture']['flow_pairs'], 0)
        self.observations[self._testMethodName] = {'decoded_stereo_samples': len(actual), 'max_sample_error': maximum,
                                                  'black_frames': len(frames)}

    def test_engine_export_and_paused_frame_preserve_ramp_gain_pan_and_fades(self):
        clip = ramp_clip(start=2, volume=.6,
                         audio={'stream_index': 2, 'channels': [1, 0], 'pan': .25,
                                'fade_in': 2, 'fade_out': 2})
        project = self.project(clip)
        project['tracks'] = [{'id': 0, 'name': 'Picture and selected sound', 'gain': .5}]
        project = validate_project(project, self.root)
        before = copy.deepcopy(project)
        output = self.root/'ENGINE_TEST_integrated-ramp.mov'
        report = render_project(project, self.root, output, 'prores')
        actual_pcm = self.pcm(output)
        self.assertEqual(actual_pcm.shape, (28_000, 2))
        expected_pcm = np.zeros((28_000, 2), dtype=np.float64)
        source = self.analytic_source_samples(24_000, Fraction(24), 0, 2, 4)
        local = np.arange(24_000, dtype=np.float64)/2000
        fade = np.minimum(1, np.minimum(local/2, (12-local)/2))
        expected_pcm[4000:] = self.tones(source)[:, [1, 0]]*fade[:, None]*np.array([.225, .3])
        pcm_error = float(np.max(np.abs(actual_pcm-expected_pcm)))
        self.assertLess(pcm_error, 2e-5, 'Original selected channels, track/clip gain, balance and preserved fades must apply once')
        self.assertEqual(actual_pcm[:4000].tobytes(), bytes(4000*8))
        pictures = self.pictures(output)
        self.assertEqual(len(pictures), 14)
        self.assertLess(int(pictures[:2].max()), 3)
        indices = [math.floor(4+Fraction(i, 2)+Fraction(i*i, 24)+Fraction(1, 2)) for i in range(12)]
        best = [int(np.argmin(np.mean((self.frames.astype(np.float64)-frame)**2, axis=(1, 2, 3))))
                for frame in pictures[2:]]
        self.assertEqual(best, indices, 'ProRes compression must not obscure the independently prescribed source clock')
        picture_rmse = float(np.sqrt(np.mean((pictures[2:].astype(np.float64)-self.frames[indices])**2)))
        self.assertLess(picture_rmse, 12)
        paused = self.root/'ENGINE_TEST_ramp-paused.png'
        paused_receipt = render_frame(project, self.root, 9, paused)
        picture = self.pictures(paused)[0]
        paused_error = int(np.max(np.abs(picture.astype(int)-self.frames[indices[7]].astype(int))))
        self.assertLessEqual(paused_error, 4)
        self.assertEqual(paused_receipt['pipeline'], 'timeline-export-graph')
        self.assertEqual(report['retime_reports'][0]['source_sha256'], self.asset['sha256'])
        self.assertEqual(report['retime_reports'][0]['output_samples'], 24_000)
        self.assertEqual(project, before)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.asset['sha256'])
        self.observations[self._testMethodName] = {'decoded_frames': 14, 'decoded_stereo_samples': 28_000,
            'max_analytic_pcm_error': pcm_error, 'prores_picture_rmse': picture_rmse,
            'paused_png_max_channel_error': paused_error, 'source_indices': indices}

    def test_nested_fractional_trim_uses_parent_grid_without_second_phase_shift(self):
        rate = Fraction(30_000, 1001)
        project = self.project(ramp_clip(start=7, **{'in': 3}), rate)
        child = {'id': 'ramped-sequence', 'name': 'Ramped child',
                 'clips': copy.deepcopy(project['clips']), 'titles': [], 'tracks': [], 'sequence_duration': 20}
        project.update(sequence_id='main', sequence_name='Main', sequences=[child])
        project['clips'] = [{'id': 'parent', 'sequence_id': child['id'], 'track': 0,
                             'start': 3, 'in': .5, 'duration': 19, 'speed': 1, 'reverse': False}]
        project = validate_project(project, self.root)
        output = self.root/'ENGINE_TEST_nested-fractional-ramp.mov'
        receipt = render_project(project, self.root, output, 'prores')
        actual = self.pcm(output)
        total = round(Fraction(22)*SAMPLE_RATE/rate)
        first = round(Fraction(19, 2)*SAMPLE_RATE/rate)
        last = round(Fraction(43, 2)*SAMPLE_RATE/rate)
        self.assertEqual(actual.shape, (total, 2))
        expected = np.zeros((total, 2), dtype=np.float64)
        positions = self.analytic_source_samples(last-first, rate, Fraction(5, 2), 7, 3)
        expected[first:last] = self.tones(positions)[:, [1, 0]]
        maximum = float(np.max(np.abs(actual-expected)))
        self.assertLess(maximum, 2e-5, 'Nested fractional source trim must retain the globally anchored source phase')
        self.assertEqual(actual[:first].tobytes(), bytes(first*8))
        self.assertEqual(actual[last:].tobytes(), bytes((total-last)*8))
        self.assertEqual(receipt['retime_reports'][0]['absolute_audio_origin'], '19/2')
        self.assertEqual(receipt['retime_reports'][0]['output_samples'], 19_219)
        self.assertEqual(len(self.pictures(output)), 22)
        self.observations[self._testMethodName] = {'decoded_stereo_samples': total,
            'first_active_sample': first, 'exclusive_last_active_sample': last,
            'active_stereo_samples': last-first, 'max_analytic_pcm_error': maximum}

    def test_saved_trimmed_recipe_archives_original_and_reopens_for_identical_render(self):
        clip = ramp_clip(start=0, duration=8, **{'in': float(Fraction(17, 3))})
        clip['retime'] = recipe(origin=3)
        clip['retime']['offset'] = 4
        project = self.project(clip)
        state = self.root/'project.json'
        state.write_text(json.dumps(project, sort_keys=True, indent=2)+'\n')
        reopened = validate_project(json.loads(state.read_text()), self.root)
        self.assertEqual(reopened, project)
        movie = self.root/'ENGINE_TEST_before-archive.mov'
        render_project(reopened, self.root, movie, 'prores')
        original_pcm, original_pictures = self.pcm(movie), self.pictures(movie)
        positions = self.analytic_source_samples(16_000, Fraction(24), 0, 0, float(Fraction(17, 3)), 4)
        expected = self.tones(positions)[:, [1, 0]]
        self.assertEqual(original_pcm.shape, expected.shape)
        maximum = float(np.max(np.abs(original_pcm-expected)))
        self.assertLess(maximum, 2e-5)
        indices = [math.floor(3+Fraction(i+4, 2)+Fraction((i+4)**2, 24)+Fraction(1, 2)) for i in range(8)]
        best = [int(np.argmin(np.mean((self.frames.astype(np.float64)-frame)**2, axis=(1, 2, 3))))
                for frame in original_pictures]
        self.assertEqual(best, indices)
        archive = self.root/'ENGINE_TEST_speed-ramp.cinematicum.zip'
        package = export_archive(reopened, self.root, archive)
        inventory = {item['path'] for item in package['manifest']['files']}
        self.assertEqual(inventory, {'project.json', 'assets.json', self.asset['path']})
        self.assertEqual(package['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
        projects = self.root/'fresh-projects'
        projects.mkdir()
        restored = import_archive(archive, projects)
        fresh = projects/restored['id']
        self.assertNotEqual(restored['id'], project['id'])
        self.assertEqual(restored['clips'], project['clips'])
        self.assertEqual(restored['clips'][0]['retime']['offset'], 4)
        self.assertEqual(restored['clips'][0]['retime']['keys'], recipe()['keys'])
        self.assertEqual(restored['assets'], project['assets'])
        self.assertEqual(hashlib.sha256((fresh/self.asset['path']).read_bytes()).hexdigest(), self.asset['sha256'])
        offline = self.root/'ENGINE_TEST_original-offline.mkv'
        self.source.rename(offline)
        try:
            delivered = self.root/'ENGINE_TEST_after-archive.mov'
            report = render_project(restored, fresh, delivered, 'prores')
        finally:
            offline.rename(self.source)
        self.assertTrue(np.array_equal(self.pictures(delivered), original_pictures))
        self.assertTrue(np.array_equal(self.pcm(delivered), original_pcm))
        self.assertEqual(report['retime_reports'][0]['source_sha256'], self.asset['sha256'])
        self.observations[self._testMethodName] = {'archive_members': sorted(inventory),
            'decoded_frames': 8, 'decoded_stereo_samples': 16_000, 'max_analytic_pcm_error': maximum,
            'restored_picture_and_pcm_identical': True, 'original_source_offline_during_reopened_render': True}

    def test_changed_source_identity_and_precancel_publish_no_derivative(self):
        project = self.project()
        event = threading.Event()
        event.set()
        target = self.root/'cancelled-retime'
        with self.assertRaises(RenderCancelled):
            retime.prepare(project, project['clips'][0], project['assets'][0], self.root, target, cancel_event=event)
        self.assertFalse(target.exists())
        changed = self.root/'media/ENGINE_TEST_changed.mkv'
        shutil.copyfile(self.source, changed)
        with changed.open('ab') as stream:
            stream.write(b'ENGINE TEST changed admitted source')
        asset = copy.deepcopy(self.asset)
        asset['path'] = 'media/'+changed.name
        target = self.root/'changed-retime'
        with self.assertRaisesRegex(ValueError, 'changed after admission'):
            retime.prepare(project, project['clips'][0], asset, self.root, target)
        self.assertFalse((target/'retimed.mkv').exists())
        self.assertFalse((target/'retime-report.json').exists())
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.asset['sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

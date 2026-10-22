"""EXR output validation, archive integrity and cleanup boundaries.

Header fixtures test parsing only. Actual rendered float samples are covered by
test_scene_masters_blender.py; these fixtures are never claimed as media.
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

from adapters import AdapterCancelled, AdapterError
import scene
from test_scene import recipe, script_constants, write_device_fixture
from timebase import parse_rate


def exr_header(width, height, channels=('R', 'G', 'B', 'A'), sample_type=2, sampling=1):
    def attribute(name, kind, value):
        return name.encode()+b'\0'+kind.encode()+b'\0'+struct.pack('<I', len(value))+value
    chlist = b''.join(name.encode()+b'\0'+struct.pack('<iB3xii', sample_type, 0, sampling, sampling) for name in channels)+b'\0'
    return (b'\x76\x2f\x31\x01'+struct.pack('<I', 2)+attribute('channels', 'chlist', chlist)
            +attribute('dataWindow', 'box2i', struct.pack('<iiii', 0, 0, width-1, height-1))
            +attribute('compression', 'compression', b'\3')+b'\0TEST HEADER ONLY; NO PIXELS')


class SceneMasterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def spec(self):
        spec = recipe()
        spec['output'] = {'linear_exr': True, 'passes': ['depth', 'normal']}
        spec['world']['transparent'] = True
        return scene.validate_scene(spec)

    def write_frames(self, spec, frames, start=2, end=4):
        for frame in range(start, end+1):
            (frames/('beauty_%06d.exr' % frame)).write_bytes(exr_header(spec['width'], spec['height']))
            channels = ['ViewLayer.Combined.'+c for c in 'RGBA']
            for render_pass in spec['output']['passes']:
                prefix, components = scene.PASS_CHANNELS[render_pass]
                channels.extend('ViewLayer.'+prefix+'.'+c for c in components)
            (frames/('passes_%06d.exr' % frame)).write_bytes(exr_header(spec['width'], spec['height'], channels))
        (frames/'render-info.json').write_text(json.dumps({'engine': 'Blender Cycles', 'engine_version': 'TEST HEADER FIXTURE',
            'color_space': 'Linear Rec.709', 'sample_type': 'float32', 'alpha': 'premultiplied',
            'transparent_world': spec['world']['transparent']}))

    def test_output_schema_is_bounded_and_legacy_recipes_gain_opaque_defaults(self):
        old = recipe()
        old.pop('output', None)
        old['world'].pop('transparent', None)
        normalized = scene.validate_scene(old)
        self.assertEqual(normalized['output'], {'linear_exr': False, 'passes': []})
        self.assertFalse(normalized['world']['transparent'])
        for output in ({'linear_exr': 1}, {'linear_exr': False, 'passes': ['normal']},
                       {'linear_exr': True, 'passes': ['normal', 'normal']},
                       {'linear_exr': True, 'passes': ['arbitrary shader']},
                       {'linear_exr': True, 'path': '/unowned'}, {'linear_exr': True, 'passes': [{}]}):
            value = recipe()
            value['output'] = output
            with self.subTest(output=output), self.assertRaises(ValueError):
                scene.validate_scene(value)
        value = recipe()
        value['world']['transparent'] = 'yes'
        with self.assertRaises(ValueError):
            scene.validate_scene(value)

    def test_real_format_header_parser_rejects_half_integer_subsample_and_truncation(self):
        target = self.root/'test.exr'
        target.write_bytes(exr_header(160, 90))
        info = scene.inspect_exr_header(target)
        self.assertEqual((info['width'], info['height']), (160, 90))
        self.assertEqual(set(info['channels']), set('RGBA'))
        for data in (exr_header(160, 90, sample_type=1), exr_header(160, 90, sample_type=0),
                     exr_header(160, 90, sampling=2), exr_header(160, 90)[:17], b'NOT EXR'):
            target.write_bytes(data)
            with self.subTest(data=data[:20]), self.assertRaises(AdapterError):
                scene.inspect_exr_header(target)

    def test_archive_keeps_every_float_frame_pass_hash_and_exact_clock(self):
        spec = self.spec()
        self.write_frames(spec, self.root)
        destination = self.root/'masters.zip'
        manifest = scene._package_scene_masters(spec, self.root, destination, parse_rate({'numerator': 24000, 'denominator': 1001}), 2, 4)
        self.assertEqual(manifest['frame_count'], 3)
        self.assertEqual(manifest['frame_rate'], {'numerator': 24000, 'denominator': 1001})
        self.assertEqual(len(manifest['files']), 6)
        with zipfile.ZipFile(destination) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(json.loads(archive.read('manifest.json')), manifest)
            self.assertEqual(json.loads(archive.read('scene.json')), spec)
            self.assertEqual(len(archive.namelist()), 8)
            for record in manifest['files']:
                data = archive.read(record['path'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
                self.assertEqual(len(data), record['bytes'])
                self.assertFalse(record['path'].startswith('/'))
                self.assertNotIn('..', record['path'].split('/'))

    def test_missing_rgba_or_requested_pass_never_publishes_an_archive(self):
        for problem in ('alpha', 'normal', 'missing', 'dimensions'):
            spec = self.spec()
            self.write_frames(spec, self.root)
            if problem == 'alpha':
                (self.root/'beauty_000003.exr').write_bytes(exr_header(160, 90, 'RGB'))
            elif problem == 'normal':
                (self.root/'passes_000003.exr').write_bytes(exr_header(160, 90, ['ViewLayer.Depth.Z']))
            elif problem == 'missing':
                (self.root/'beauty_000003.exr').unlink()
            else:
                (self.root/'beauty_000003.exr').write_bytes(exr_header(90, 160))
            destination = self.root/'masters.zip'
            with self.subTest(problem=problem), self.assertRaises(AdapterError):
                scene._package_scene_masters(spec, self.root, destination, parse_rate(24), 2, 4)
            self.assertFalse(destination.exists())

    def test_native_full_pass_names_are_accepted_without_renaming_channels(self):
        spec = self.spec()
        spec['output']['passes'] = list(scene.PASS_CHANNELS)
        self.write_frames(spec, self.root, start=1, end=1)
        for prefixes in (('DiffCol', 'Emit'), ('Diffuse Color', 'Emission')):
            channels = ['ViewLayer.Combined.'+c for c in 'RGBA']
            for render_pass, (prefix, components) in scene.PASS_CHANNELS.items():
                prefix = {'diffuse_color': prefixes[0], 'emission': prefixes[1]}.get(render_pass, prefix)
                channels.extend('ViewLayer.'+prefix+'.'+c for c in components)
            (self.root/'passes_000001.exr').write_bytes(exr_header(spec['width'], spec['height'], channels))
            destination = self.root/('masters-'+prefixes[0]+'.zip')
            manifest = scene._package_scene_masters(spec, self.root, destination, parse_rate(24), 1, 1)
            record = next(record for record in manifest['files'] if record['role'] == 'passes')
            self.assertEqual(set(record['channels']), set(channels))

    def test_cancel_during_streaming_removes_partial_archive(self):
        spec = self.spec()
        self.write_frames(spec, self.root)
        destination = self.root/'masters.zip'
        event = threading.Event()
        original = scene.inspect_exr_header
        def cancel_after_inspection(path):
            result = original(path)
            event.set()
            return result
        with mock.patch.object(scene, 'inspect_exr_header', side_effect=cancel_after_inspection), self.assertRaises(AdapterCancelled):
            scene._package_scene_masters(spec, self.root, destination, parse_rate(24), 2, 4, event)
        self.assertFalse(destination.exists())

    def test_render_returns_all_owned_outputs_and_composites_display_over_black(self):
        calls = []
        def execute(argv, log, event, timeout, tick=lambda: None):
            calls.append(argv)
            if argv[0] == '/test/blender':
                values = script_constants(Path(argv[-1]).read_text())
                frames = Path(values['FRAMES'])
                Path(values['BLEND_PATH']).write_bytes(b'TEST ONLY BLEND')
                write_device_fixture(values)
                for frame in range(values['START'], values['END']+1):
                    (frames/('frame_%06d.png' % frame)).write_bytes(b'TEST ONLY PNG')
                self.write_frames(values['SPEC'], frames)
            else:
                Path(argv[-1]).write_bytes(b'TEST ONLY MOVIE')
        with mock.patch.object(scene, 'find_blender', return_value='/test/blender'), \
                mock.patch.object(scene.shutil, 'which', return_value='/test/ffmpeg'), \
                mock.patch.object(scene, '_run_owned', side_effect=execute):
            result = scene.render_scene(self.spec(), self.root, frame_start=2, frame_end=4)
        for field in ('path', 'scene_path', 'masters_path'):
            self.assertTrue(Path(result[field]).is_file())
        self.assertEqual(scene._sha256(Path(result['masters_path'])), result['masters_sha256'])
        self.assertTrue(result['provenance']['scene_linear_masters'])
        self.assertFalse(result['provenance']['movie_has_alpha'])
        self.assertIn('[1:v][0:v]overlay=shortest=1:format=auto,setsar=1[out]', calls[1])
        self.assertFalse(list(self.root.glob('.scene-*')))

    def test_disk_budget_fails_before_rendering_or_writing_partial_media(self):
        with mock.patch.object(scene, 'find_blender', return_value='/test/blender'), \
                mock.patch.object(scene.shutil, 'which', return_value='/test/ffmpeg'), \
                mock.patch.object(scene.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
                mock.patch.object(scene, '_run_owned') as execute:
            with self.assertRaisesRegex(AdapterError, 'free working space'):
                scene.render_scene(self.spec(), self.root)
            execute.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

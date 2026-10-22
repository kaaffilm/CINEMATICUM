"""Camera-path regressions: continuous collision checks, transport and calibration.

JavaScript cases execute the shipped viewport code. All inputs are mathematical
test fixtures; no screenshot is used as evidence of a rendered camera.
"""
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest

import scene
import camera_io
from test_camera_io import fspy_payload, fspy_state, rodrigues


HERE = Path(__file__).resolve().parent


def pole_scene():
    spec = scene.default_scene(16, 16)
    spec['frame_end'] = 9
    spec['camera'].update(position=[.1, 0, -1], target=[0, 0, 0], keyframes=[
        {'frame': 1, 'interpolation': 'ease_in_out'},
        {'frame': 9, 'position': [-.1, 0, -1], 'target': [0, 0, 0]}])
    return scene.validate_scene(spec)


class AimPathTests(unittest.TestCase):
    def test_target_crossing_is_rejected_before_launch_including_implicit_base(self):
        for kind in ('camera', 'area', 'sun'):
            for mode in ('linear', 'ease_in', 'ease_out', 'ease_in_out'):
                spec = scene.default_scene(16, 16)
                spec['frame_end'] = 8
                item = spec['camera'] if kind == 'camera' else spec['lights'][0]
                if kind != 'camera':
                    item['type'] = kind
                item.update(position=[0, 0, 1], target=[0, 0, 0], keyframes=[
                    {'frame': 8, 'position': [0, 0, -2], 'target': [0, 0, 0]}])
                if mode != 'linear':
                    item['keyframes'].insert(0, {'frame': 1, 'interpolation': mode})
                with self.subTest(kind=kind, mode=mode), self.assertRaisesRegex(ValueError, 'between frames 1 and 8'):
                    scene.validate_scene(spec)

    def test_subframe_collision_and_near_miss_are_not_hidden_by_integer_sampling(self):
        for target_y, accepted in ((0, False), (.009, False), (.011, True)):
            spec = scene.default_scene(16, 16)
            spec['frame_end'] = 2
            spec['camera'].update(position=[-1, 0, 0], target=[0, target_y, 0], keyframes=[
                {'frame': 2, 'position': [2, 0, 0]}])
            with self.subTest(target_y=target_y):
                if accepted:
                    scene.validate_scene(spec)
                else:
                    with self.assertRaisesRegex(ValueError, '0.01 m'):
                        scene.validate_scene(spec)

    def test_target_motion_is_included_and_constant_cut_remains_legal(self):
        spec = scene.default_scene(16, 16)
        spec['frame_end'] = 3
        spec['camera'].update(position=[0, 0, 0], target=[0, 0, 1], keyframes=[
            {'frame': 1, 'interpolation': 'linear'}, {'frame': 3, 'target': [0, 0, -1]}])
        with self.assertRaisesRegex(ValueError, 'aim path'):
            scene.validate_scene(spec)
        spec['camera']['keyframes'][0]['interpolation'] = 'constant'
        result = scene.validate_scene(spec)
        before = scene.camera_basis_at(result['camera'], 2.999)
        after = scene.camera_basis_at(result['camera'], 3)
        self.assertEqual(before['forward'], [0, 0, 1])
        self.assertEqual(after['forward'], [0, 0, -1])

    def test_point_lights_do_not_require_an_aim_direction(self):
        spec = scene.default_scene(16, 16)
        spec['lights'][0].update(type='point', position=[0, 0, 0], target=[0, 0, 0],
                                 keyframes=[{'frame': 9, 'position': [0, 0, 1]}])
        scene.validate_scene(spec)


class CameraTransportTests(unittest.TestCase):
    def assert_vector(self, actual, expected, tolerance=1e-10):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertLessEqual(abs(a - b), tolerance)

    def test_new_scenes_use_transport_and_legacy_recipes_remain_reproducible(self):
        fresh = pole_scene()
        self.assertEqual(fresh['camera']['orientation_mode'], 'transport')
        old = copy.deepcopy(fresh)
        old['camera'].pop('orientation_mode')
        old = scene.validate_scene(old)
        self.assertEqual(old['camera']['orientation_mode'], 'world_up')
        for at in (1, 3, 4, 5, 6, 7, 9):
            pose = scene.pose_at(old['camera'], at, 'camera')
            self.assertEqual(scene.camera_basis_at(old['camera'], at),
                             scene.camera_basis(pose['position'], pose['target'], pose['roll']))
        self.assertEqual(scene.validate_scene(old), old)
        bad = copy.deepcopy(fresh)
        bad['camera']['orientation_mode'] = 'anything'
        with self.assertRaisesRegex(ValueError, 'orientation'):
            scene.validate_scene(bad)

    def test_transport_crosses_the_actual_pole_without_roll_jump(self):
        camera = pole_scene()['camera']
        # All directions lie in XZ; transport about Y must preserve +Y right.
        for at in (1, 2, 3, 4, 4.999999, 5, 5.000001, 6, 7, 8, 9):
            with self.subTest(frame=at):
                pose = scene.pose_at(camera, at, 'camera')
                basis = scene.camera_basis_at(camera, at)
                self.assert_vector(basis['right'], [0, 1, 0])
                self.assert_vector(basis['backward'], [v / math.hypot(*pose['position']) for v in pose['position']])
                self.assertAlmostEqual(sum(a*b for a, b in zip(basis['right'], basis['up'])), 0)
                self.assertAlmostEqual(math.hypot(*basis['up']), 1)

    def test_audit_threshold_has_no_jump_during_transport(self):
        pos = lambda degrees: [math.sin(math.radians(degrees)), 0, -math.cos(math.radians(degrees))]
        spec = scene.default_scene(16, 16)
        spec['frame_end'] = 2
        spec['camera'].update(position=pos(2.57), target=[0, 0, 0], keyframes=[{'frame': 2, 'position': pos(2.55)}])
        camera = scene.validate_scene(spec)['camera']
        self.assert_vector(scene.camera_basis_at(camera, 1)['right'], scene.camera_basis_at(camera, 2)['right'])
        legacy = {**camera, 'orientation_mode': 'world_up'}
        a, b = [scene.camera_basis_at(legacy, t)['right'] for t in (1, 2)]
        self.assertAlmostEqual(sum(x*y for x, y in zip(a, b)), 0)

    def test_animated_roll_is_applied_to_transport_and_random_seek_is_deterministic(self):
        spec = pole_scene()
        spec['camera']['keyframes'][1]['roll'] = 80
        camera = scene.validate_scene(spec)['camera']
        for at in (9, 1, 5, 3, 7, 5):
            pose = scene.pose_at(camera, at, 'camera')
            angle = math.radians(pose['roll'])
            backward = [v/math.hypot(*pose['position']) for v in pose['position']]
            # Independent y-right orthogonal basis for this XZ fixture.
            base_up = [-backward[2], 0, backward[0]]
            expected = [base_up[0]*math.sin(angle), math.cos(angle), base_up[2]*math.sin(angle)]
            self.assert_vector(scene.camera_basis_at(camera, at)['right'], expected)
        self.assertEqual(scene.camera_basis_at(camera, 5), scene.camera_basis_at(json.loads(json.dumps(camera)), 5))

    def test_imports_seed_transport_with_the_exact_calibrated_orientation(self):
        for tilt in (0, .02, .05, .7):
            rotation = rodrigues([0, 1, 0], tilt)
            state = fspy_state(rotation=rotation)
            camera = camera_io.import_camera(fspy_payload(state), 1200, 800)['cameras'][0]['camera']
            self.assertEqual(camera['orientation_mode'], 'transport')
            # Column vectors of the independent input camera-to-world matrix.
            basis = scene.camera_basis_at(camera, 1)
            for col, axis in enumerate(('right', 'up', 'backward')):
                self.assert_vector(basis[axis], [row[col] for row in rotation])

    def test_python_embedded_in_blender_is_the_same_basis_evaluator(self):
        scope = {'math': math}
        exec(compile(scene._camera_math_source(), 'retained-camera-math', 'exec'), scope)
        camera = pole_scene()['camera']
        for frame in (1, 3, 5, 7, 9):
            self.assertEqual(scope['camera_basis_at'](camera, frame), scene.camera_basis_at(camera, frame))


@unittest.skipUnless(shutil.which('node'), 'Node is required to execute the shipped viewport math')
class ViewportCameraTests(unittest.TestCase):
    def run_viewport(self, source, payload):
        script = "const fs=require('fs'),vm=require('vm');global.window={};vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));const api=window.CinematicumSceneEditor;const input=JSON.parse(fs.readFileSync(0,'utf8'));" + source
        process = subprocess.run([shutil.which('node'), '-e', script, str(HERE/'web'/'scene-editor.js')],
                                 input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=10)
        return json.loads(process.stdout)

    def test_real_viewport_and_renderer_agree_at_poles_keys_easing_and_roll(self):
        spec = pole_scene()
        spec['camera']['keyframes'][1].update(roll=70, interpolation='ease_out')
        spec['frame_end'] = 17
        spec['camera']['keyframes'].append({'frame': 17, 'position': [-.1, .2, -1], 'roll': 140})
        spec = scene.validate_scene(spec)
        frames = [1, 3, 5, 7, 9, 13, 17, 8.5, 5]
        output = self.run_viewport('process.stdout.write(JSON.stringify(input.frames.map(f=>api.cameraBasisAt(input.camera,f))));',
                                   {'camera': spec['camera'], 'frames': frames})
        for frame, actual in zip(frames, output):
            expected = scene.camera_basis_at(spec['camera'], frame)
            for axis in expected:
                for a, b in zip(actual[axis], expected[axis]):
                    self.assertAlmostEqual(a, b, places=11)

    def test_viewport_prevents_undefined_paths_but_keeps_nearby_valid_motion(self):
        invalid = pole_scene()
        invalid['camera']['position'] = [0, 0, 1]
        invalid['camera']['keyframes'] = [{'frame': 9, 'position': [0, 0, -1]}]
        valid = pole_scene()
        output = self.run_viewport('process.stdout.write(JSON.stringify(input.map(s=>{try{api.validateAimPaths(s);return null;}catch(e){return e.message;}})));', [invalid, valid])
        self.assertIn('between frames 1 and 9', output[0])
        self.assertIsNone(output[1])


if __name__ == '__main__':
    unittest.main()

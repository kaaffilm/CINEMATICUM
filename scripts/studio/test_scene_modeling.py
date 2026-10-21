"""Independent topology, provenance, bounds and cache-binding checks."""
import ast
import copy
import json
import math
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch

from adapters import AdapterCancelled, AdapterError
import scene
import scene_modeling as modeling
from spatial_import import import_obj, validate_mesh


def cube():
    spec = scene.default_scene()
    spec['objects'] = [{'id': 'model', 'type': 'cube', 'name': 'TEST cage'}]
    return scene.validate_scene(spec)['objects'][0]


def prepared():
    return modeling.prepare_operation(cube(), {'type': 'convert'})[0]


def fake_evaluation(obj):
    """Data-validation fixture only. It is never a claimed Blender evaluation."""
    result = copy.deepcopy(obj)
    result['modeling']['evaluation'] = {'key': modeling.evaluation_key(result), 'engine_version': 'TEST ONLY',
                                      'mesh': copy.deepcopy(result['mesh'])}
    return result


def signed_volume(mesh):
    volume = 0
    for indices in mesh['triangles']:
        a, b, c = [mesh['vertices'][i] for i in indices]
        cross = [b[1] * c[2] - b[2] * c[1], b[2] * c[0] - b[0] * c[2], b[0] * c[1] - b[1] * c[0]]
        volume += sum(x * y for x, y in zip(a, cross)) / 6
    return volume


def edge_counts(faces):
    counts = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a, b)))
            counts[edge] = counts.get(edge, 0) + 1
    return counts


class ModelingTopologyTests(unittest.TestCase):
    def test_cube_cage_preserves_shape_winding_and_original_object(self):
        original = cube()
        before = copy.deepcopy(original)
        obj, warnings = modeling.prepare_operation(original, {'type': 'convert'})
        self.assertEqual(original, before)
        self.assertEqual((len(obj['mesh']['vertices']), len(obj['modeling']['faces']), len(obj['mesh']['triangles'])), (8, 6, 12))
        self.assertAlmostEqual(signed_volume(obj['mesh']), 8)
        self.assertEqual(set(edge_counts(obj['modeling']['faces']).values()), {2})
        self.assertEqual(obj['modeling']['origin'], {'kind': 'primitive', 'primitive': 'cube'})
        self.assertEqual(warnings, [])
        for key in ('id', 'position', 'rotation', 'scale', 'material', 'keyframes'):
            self.assertEqual(obj[key], original[key])

    def test_all_supported_primitive_cages_have_finite_valid_geometry(self):
        for kind in ('cube', 'plane', 'sphere', 'cylinder'):
            with self.subTest(kind=kind):
                source = cube()
                source['type'] = kind
                obj, _ = modeling.prepare_operation(source, {'type': 'convert'})
                self.assertEqual(validate_mesh(obj['mesh']), obj['mesh'])
                self.assertTrue(all(math.isfinite(v) for p in obj['mesh']['vertices'] for v in p))
                if kind != 'plane':
                    self.assertGreater(signed_volume(obj['mesh']), 0)
                    self.assertEqual(set(edge_counts(obj['modeling']['faces']).values()), {2})

    def test_vertex_move_changes_only_selected_control_coordinates_and_digest(self):
        before = prepared()
        moved, _ = modeling.prepare_operation(before, {'type': 'move_vertices', 'indices': [6], 'delta': [.4, .1, .2]})
        self.assertEqual(moved['mesh']['vertices'][6], [1.4, 1.1, 1.2])
        for index in set(range(8)) - {6}:
            self.assertEqual(moved['mesh']['vertices'][index], before['mesh']['vertices'][index])
        self.assertEqual(moved['modeling']['faces'], before['modeling']['faces'])
        self.assertNotEqual(moved['mesh']['sha256'], before['mesh']['sha256'])
        self.assertEqual(validate_mesh(moved['mesh']), moved['mesh'])

    def test_extrusion_has_real_depth_and_closed_connected_boundary(self):
        obj, _ = modeling.prepare_operation(prepared(), {'type': 'extrude_face', 'face': 1, 'distance': .75})
        self.assertEqual(len(obj['mesh']['vertices']), 12)
        self.assertEqual(len(obj['modeling']['faces']), 10)
        self.assertEqual(max(p[2] for p in obj['mesh']['vertices']), 1.75)
        self.assertAlmostEqual(signed_volume(obj['mesh']), 11)
        self.assertEqual(set(edge_counts(obj['modeling']['faces']).values()), {2})
        self.assertEqual(obj['modeling']['faces'][1], [8, 9, 10, 11])

    def test_subdivision_preserves_volume_and_splits_neighbour_edges_without_t_junctions(self):
        obj, _ = modeling.prepare_operation(prepared(), {'type': 'subdivide_faces', 'faces': [1]})
        self.assertEqual(len(obj['mesh']['vertices']), 13)
        self.assertEqual(len(obj['modeling']['faces']), 9)
        self.assertAlmostEqual(signed_volume(obj['mesh']), 8)
        self.assertEqual(set(edge_counts(obj['modeling']['faces']).values()), {2})
        self.assertEqual(len(obj['mesh']['triangles']), sum(len(face) - 2 for face in obj['modeling']['faces']))

    def test_delete_face_opens_surface_and_compacts_only_unused_vertices(self):
        obj, _ = modeling.prepare_operation(prepared(), {'type': 'delete_faces', 'faces': [1]})
        self.assertEqual(len(obj['modeling']['faces']), 5)
        self.assertEqual(sum(n == 1 for n in edge_counts(obj['modeling']['faces']).values()), 4)
        self.assertEqual({v for f in obj['modeling']['faces'] for v in f}, set(range(len(obj['mesh']['vertices']))))
        with self.assertRaisesRegex(ValueError, 'Keep at least one'):
            modeling.prepare_operation(prepared(), {'type': 'delete_faces', 'faces': list(range(6))})

    def test_import_conversion_and_edits_separate_origin_from_authored_geometry(self):
        obj = import_obj({'name': 'original.obj', 'obj': 'v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nf 1/1 2/2 3/3\n'})['objects'][0]
        before = copy.deepcopy(obj)
        editable, _ = modeling.prepare_operation(obj, {'type': 'convert'})
        self.assertEqual(obj, before)
        self.assertNotIn('source', editable['mesh'])
        self.assertEqual(editable['mesh']['sha256'], obj['mesh']['sha256'])
        origin = editable['modeling']['origin']
        self.assertEqual(origin['source'], obj['mesh']['source'])
        self.assertEqual(origin['mesh_sha256'], obj['mesh']['sha256'])
        changed, warnings = modeling.prepare_operation(editable, {'type': 'move_vertices', 'indices': [1], 'delta': [.25, 0, 0]})
        self.assertEqual(changed['modeling']['origin'], origin)
        self.assertEqual(changed['mesh']['uvs'], [])
        self.assertEqual(changed['mesh']['normals'], [])
        self.assertTrue(any('UV' in warning for warning in warnings))
        self.assertNotEqual(changed['mesh']['sha256'], obj['mesh']['sha256'])

    def test_concave_polygon_projection_is_ear_clipped_without_outside_fan(self):
        points = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [1, .5, 0], [0, 2, 0]]
        mesh = modeling._cage_mesh(points, [[0, 1, 2, 3, 4]])
        area = 0
        for a, b, c in mesh['triangles']:
            p, q, r = [mesh['vertices'][i] for i in (a, b, c)]
            area += abs((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])) / 2
        self.assertAlmostEqual(area, 2.5)

    def test_out_of_range_nonfinite_degenerate_and_script_like_operations_are_rejected(self):
        for operation in ({'type': 'move_vertices', 'indices': [True], 'delta': [0, 0, 0]},
                          {'type': 'move_vertices', 'indices': [0, 0], 'delta': [0, 0, 0]},
                          {'type': 'move_vertices', 'indices': [99], 'delta': [0, 0, 0]},
                          {'type': 'move_vertices', 'indices': [0], 'delta': [float('nan'), 0, 0]},
                          {'type': 'move_vertices', 'indices': [0], 'delta': [-1000, 0, 0]},
                          {'type': 'move_vertices', 'indices': [0], 'delta': [2, 0, 0]},
                          {'type': 'extrude_face', 'face': 1, 'distance': 0},
                          {'type': '__import__', 'path': '/tmp/anything'},
                          {'type': [], 'faces': [1]}, {'type': 'convert', 'script': 'print(1)'}):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                modeling.prepare_operation(prepared(), operation)


class ModelingRecipeTests(unittest.TestCase):
    def test_enabled_ordered_stack_is_bounded_and_part_of_evaluation_identity(self):
        obj = prepared()
        old = modeling.evaluation_key(obj)
        obj, _ = modeling.prepare_operation(obj, {'type': 'set_modifiers', 'modifiers': [
            {'id': 'mirror', 'type': 'mirror'}, {'id': 'bevel', 'type': 'bevel'}, {'id': 'subdivision', 'type': 'subdivision'}]})
        self.assertEqual([m['type'] for m in obj['modeling']['modifiers']], ['mirror', 'bevel', 'subdivision'])
        self.assertNotEqual(modeling.evaluation_key(obj), old)
        same = copy.deepcopy(obj)
        same['modeling']['modifiers'].reverse()
        self.assertNotEqual(modeling.evaluation_key(same), modeling.evaluation_key(obj))
        same = copy.deepcopy(obj)
        same['modeling']['modifiers'][0]['enabled'] = False
        self.assertNotEqual(modeling.evaluation_key(same), modeling.evaluation_key(obj))

    def test_bad_modifier_options_and_excessive_growth_are_rejected(self):
        cases = [[{'id': 'one', 'type': 'geometry-nodes', 'script': 'x'}],
                 [{'id': 'one', 'type': 'mirror', 'axis': []}],
                 [{'id': 'one', 'type': 'mirror', 'axis': 'W'}],
                 [{'id': 'one', 'type': 'bevel', 'segments': 7}],
                 [{'id': 'one', 'type': 'bevel', 'width': float('inf')}],
                 [{'id': 'one', 'type': 'subdivision', 'levels': 4}],
                 [{'id': 'one', 'type': 'subdivision', 'method': 'CUSTOM'}],
                 [{'id': 'one', 'type': 'mirror', 'enabled': 1}],
                 [{'id': 'same', 'type': 'mirror'}, {'id': 'same', 'type': 'bevel'}],
                 [{'id': str(i), 'type': 'mirror'} for i in range(5)],
                 [{'id': str(i), 'type': 'subdivision', 'levels': 3} for i in range(4)]]
        for modifiers in cases:
            with self.subTest(modifiers=modifiers), self.assertRaises(ValueError):
                modeling.prepare_operation(prepared(), {'type': 'set_modifiers', 'modifiers': modifiers})

    def test_saved_modeling_normalization_is_stable_and_stale_preview_is_rejected(self):
        spec = scene.default_scene()
        spec['objects'] = [fake_evaluation(prepared())]
        normalized = scene.validate_scene(spec)
        self.assertEqual(scene.validate_scene(json.loads(json.dumps(normalized))), normalized)
        bad = copy.deepcopy(spec)
        bad['objects'][0]['modeling']['evaluation']['key'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'stale'):
            scene.validate_scene(bad)
        bad = copy.deepcopy(spec)
        bad['objects'][0]['modeling']['faces'][0].reverse()
        with self.assertRaisesRegex(ValueError, 'triangles'):
            scene.validate_scene(bad)
        bad = copy.deepcopy(spec)
        bad['objects'][0]['modeling']['evaluation']['mesh']['vertices'][0][0] = -.5
        with self.assertRaisesRegex(ValueError, 'digest'):
            scene.validate_scene(bad)

    def test_source_masquerade_and_unknown_paths_are_rejected(self):
        obj = fake_evaluation(prepared())
        obj['mesh']['source'] = {'name': 'not-original.obj'}
        with self.assertRaisesRegex(ValueError, 'original source'):
            modeling.validate_modeling(obj)
        obj = fake_evaluation(prepared())
        obj['modeling']['evaluation']['script'] = 'external.py'
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            modeling.validate_modeling(obj)

    def test_real_worker_launch_has_owned_paths_timeout_and_one_evaluator(self):
        with patch.object(modeling, 'find_blender', return_value=None):
            with self.assertRaisesRegex(AdapterError, 'unavailable'):
                modeling.evaluate_object(prepared())
        event = threading.Event()
        event.set()
        with self.assertRaises(AdapterCancelled):
            modeling.evaluate_object(prepared(), event)
        self.assertTrue(modeling._EVALUATION_SLOT.acquire(blocking=False))
        try:
            with patch.object(modeling, 'find_blender', return_value='/owned/blender'):
                with self.assertRaisesRegex(AdapterError, 'Another mesh'):
                    modeling.evaluate_object(prepared())
        finally:
            modeling._EVALUATION_SLOT.release()

    def test_apply_stack_reevaluates_before_baking_untrusted_cached_geometry(self):
        obj, _ = modeling.prepare_operation(prepared(), {'type': 'set_modifiers', 'modifiers': [{'id': 'bevel', 'type': 'bevel'}]})
        obj = fake_evaluation(obj)
        calls = []
        def actual(candidate, cancel_event=None):
            calls.append(copy.deepcopy(candidate))
            return fake_evaluation(candidate)
        with patch.object(modeling, 'evaluate_object', side_effect=actual):
            result = modeling.model_mesh({'object': obj, 'operation': {'type': 'apply_modifiers'}})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['object']['modeling']['modifiers'], [])
        self.assertEqual(result['object']['modeling']['origin'], obj['modeling']['origin'])

    def test_retained_script_compiles_with_independent_evaluation_verification(self):
        spec = scene.default_scene()
        spec['objects'] = [fake_evaluation(prepared())]
        script = scene._build_script(scene.validate_scene(spec), '/owned/retained.blend', '/owned/frames', 24, 1, 1)
        tree = ast.parse(script)
        calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertIn('cinematicum_verify_model', calls)
        self.assertIn('cinematicum_extract_model', calls)
        self.assertIn('cinematicum_model_object', calls)
        self.assertNotIn('eval', calls)


if __name__ == '__main__':
    unittest.main()

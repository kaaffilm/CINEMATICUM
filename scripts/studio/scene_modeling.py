"""Bounded topology authorship and real, nondestructive mesh modifier evaluation.

The app owns the editing controls and control cage. Blender evaluates the exact
modifier stack into canonical triangles for the app's viewport; rendering then
independently verifies that same geometry and retains the live stack.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import threading

from adapters import AdapterError, _cancelled, _run_owned, find_blender
from spatial_import import (MAX_GEOMETRY_BYTES, MAX_SCENE_TRIANGLES, MAX_SCENE_VERTICES,
                            _json_bytes, _mesh_source, _triangulate, validate_mesh)

MAX_CAGE_VERTICES = 10000
MAX_CAGE_FACES = 10000
MAX_MODIFIERS = 4
MODELING_TIMEOUT = 45
_EVALUATION_SLOT = threading.BoundedSemaphore(1)
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')


def _mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + ' has unsupported properties.')
    return value


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + ' must be a finite number.')
    try:
        valid = math.isfinite(value) and low <= value <= high and (not integer or int(value) == value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError('%s must be %sbetween %s and %s.' % (label, 'an integer ' if integer else '', low, high))
    return int(value) if integer else float(value)


def _boolean(value, label):
    if type(value) is not bool:
        raise ValueError(label + ' must be true or false.')
    return value


def _vector(value, label, low=-1000, high=1000):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(label + ' must have three coordinates.')
    return [_number(v, label, low, high) for v in value]


def _faces(value, vertex_count):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CAGE_FACES:
        raise ValueError('The editable cage needs 1–10,000 faces.')
    total = 0
    result = []
    for face in value:
        if (not isinstance(face, list) or not 3 <= len(face) <= 64
                or any(type(index) is not int or not 0 <= index < vertex_count for index in face)
                or len(set(face)) != len(face)):
            raise ValueError('Control faces need 3–64 distinct existing vertex indices.')
        total += len(face)
        if total > 60000:
            raise ValueError('The editable cage exceeds 60,000 face corners.')
        result.append(list(face))
    return result


def cage_triangles(vertices, faces):
    """Ear-clip the dominant-plane projection, retaining polygon winding.

    Projection permits a nonplanar subdivision control face while rejecting
    crossed edges and avoiding degenerate fans at newly split neighbour edges.
    """
    result = []
    for face in faces:
        if len(face) == 3:
            result.append(list(face))
            continue
        points = [vertices[i] for i in face]
        normal = [0., 0., 0.]
        for p, q in zip(points, points[1:] + points[:1]):
            normal[0] += (p[1] - q[1]) * (p[2] + q[2])
            normal[1] += (p[2] - q[2]) * (p[0] + q[0])
            normal[2] += (p[0] - q[0]) * (p[1] + q[1])
        drop = max(range(3), key=lambda axis: abs(normal[axis]))
        projected = [[0. if axis == drop else point[axis] for axis in range(3)] for point in points]
        clipped = _triangulate([(i, -1, -1) for i in range(len(face))], projected)
        result.extend([[face[corner[0]] for corner in triangle] for triangle in clipped])
    return result


def _cage_mesh(vertices, faces):
    """Stable projected triangles describe the cage; Blender evaluates its polygons.

    Nonplanar control faces are valid for subdivision. The real evaluated mesh,
    including Blender's actual triangulation and corner normals, is always the
    shaded viewport/render geometry. The cage triangles serve picking only.
    """
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_CAGE_VERTICES:
        raise ValueError('An editable cage supports 3–10,000 vertices.')
    points = [_vector(v, 'Control vertex') for v in vertices]
    faces = _faces(faces, len(points))
    triangles = cage_triangles(points, faces)
    return validate_mesh({'version': 1, 'vertices': points, 'triangles': triangles})


def validate_modifiers(value):
    if not isinstance(value, list) or len(value) > MAX_MODIFIERS:
        raise ValueError('A mesh supports up to four nondestructive modifiers.')
    result, ids = [], set()
    for source in value:
        if not isinstance(source, dict) or not isinstance(source.get('type'), str) or source['type'] not in {'mirror', 'bevel', 'subdivision'}:
            raise ValueError('Choose a Mirror, Bevel, or Subdivision modifier.')
        kind = source['type']
        fields = {'mirror': {'axis', 'bisect', 'flip', 'merge_distance'},
                  'bevel': {'width', 'segments', 'angle'}, 'subdivision': {'levels', 'method'}}[kind]
        _mapping(source, {'id', 'type', 'enabled', *fields}, 'Modifier')
        ident = source.get('id')
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in ids:
            raise ValueError('Modifier IDs must be distinct plain identifiers.')
        ids.add(ident)
        item = {'id': ident, 'type': kind, 'enabled': _boolean(source.get('enabled', True), 'Modifier enabled')}
        if kind == 'mirror':
            axis = source.get('axis', 'X')
            if not isinstance(axis, str) or axis not in {'X', 'Y', 'Z'}:
                raise ValueError('Mirror axis must be X, Y, or Z.')
            item.update(axis=axis, bisect=_boolean(source.get('bisect', True), 'Mirror bisect'),
                        flip=_boolean(source.get('flip', False), 'Mirror flip'),
                        merge_distance=_number(source.get('merge_distance', .001), 'Mirror merge distance', .000001, .1))
        elif kind == 'bevel':
            item.update(width=_number(source.get('width', .1), 'Bevel width', .0001, 2),
                        segments=_number(source.get('segments', 2), 'Bevel segments', 1, 6, True),
                        angle=_number(source.get('angle', 30), 'Bevel angle', 0, 180))
        else:
            method = source.get('method', 'CATMULL_CLARK')
            if not isinstance(method, str) or method not in {'CATMULL_CLARK', 'SIMPLE'}:
                raise ValueError('Subdivision must use Catmull–Clark or Simple.')
            item.update(method=method, levels=_number(source.get('levels', 1), 'Subdivision level', 1, 3, True))
        result.append(item)
    return result


def _complexity(mesh, modifiers):
    estimate = len(mesh['triangles'])
    for item in modifiers:
        if not item['enabled']:
            continue
        if item['type'] == 'mirror':
            estimate *= 2
        elif item['type'] == 'subdivision':
            estimate *= 4 ** item['levels']
        else:
            estimate *= 2 + 12 * item['segments']
        if estimate > 150000:
            raise ValueError('This modifier stack can exceed the geometry budget. Reduce the cage, segments, or subdivision levels.')


def evaluation_key(obj):
    modeling = obj['modeling']
    return hashlib.sha256(_json_bytes({'version': 1, 'mesh': obj['mesh']['sha256'],
                                      'faces': modeling['faces'], 'modifiers': modeling['modifiers']})).hexdigest()


def _origin(value):
    _mapping(value, {'kind', 'primitive', 'mesh_sha256', 'source'}, 'Modeling origin')
    kind = value.get('kind')
    if kind == 'primitive':
        if (set(value) != {'kind', 'primitive'} or not isinstance(value.get('primitive'), str)
                or value['primitive'] not in {'cube', 'sphere', 'plane', 'cylinder'}):
            raise ValueError('Modeling primitive origin is invalid.')
        return dict(value)
    if not isinstance(kind, str) or kind not in {'import', 'authored'} or not isinstance(value.get('mesh_sha256'), str) or not _SHA256.fullmatch(value['mesh_sha256']):
        raise ValueError('Modeling origin needs its original geometry hash.')
    if 'primitive' in value or (kind == 'authored' and 'source' in value):
        raise ValueError('Modeling source provenance is invalid.')
    result = {'kind': kind, 'mesh_sha256': value['mesh_sha256']}
    if kind == 'import':
        result['source'] = _mesh_source(value.get('source'))
        if not result['source']:
            raise ValueError('Imported modeling origin needs the original source record.')
    return result


def validate_modeling(obj, require_evaluation=True):
    """Normalize the modeling addition without changing legacy mesh digests."""
    if 'modeling' not in obj:
        return obj
    if obj.get('type') != 'mesh':
        raise ValueError('Only a mesh can have a modeling control cage.')
    mesh = obj['mesh']
    value = _mapping(obj['modeling'], {'version', 'faces', 'origin', 'modifiers', 'evaluation'}, 'Modeling')
    if type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Unsupported modeling recipe version.')
    if len(mesh['vertices']) > MAX_CAGE_VERTICES:
        raise ValueError('An editable cage supports at most 10,000 vertices.')
    if 'source' in mesh:
        raise ValueError('Edited geometry must keep its original source in modeling.origin, separately from the authored mesh.')
    value['faces'] = _faces(value.get('faces'), len(mesh['vertices']))
    triangles = cage_triangles(mesh['vertices'], value['faces'])
    if triangles != mesh['triangles']:
        raise ValueError('Canonical cage triangles do not match the editable faces.')
    value['origin'] = _origin(value.get('origin'))
    value['modifiers'] = validate_modifiers(value.get('modifiers', []))
    _complexity(mesh, value['modifiers'])
    if not require_evaluation and 'evaluation' not in value:
        return obj
    evaluation = _mapping(value.get('evaluation'), {'key', 'engine_version', 'mesh'}, 'Modifier evaluation')
    if evaluation.get('key') != evaluation_key(obj):
        raise ValueError('The modifier preview is stale. Refresh the stack before saving or rendering.')
    version = evaluation.get('engine_version')
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9 .()+_-]{1,80}', version):
        raise ValueError('The modifier evaluation requires its actual Blender version.')
    evaluation['mesh'] = validate_mesh(evaluation.get('mesh'))
    if 'source' in evaluation['mesh']:
        raise ValueError('Evaluated geometry cannot impersonate imported source media.')
    if len(_json_bytes({'mesh': mesh, 'modeling': value})) > MAX_GEOMETRY_BYTES:
        raise ValueError('The control cage and evaluated modifier mesh together exceed 5 MiB.')
    return obj


def validate_modeling_budget(objects):
    if not any(obj.get('modeling') for obj in objects):
        return
    meshes = []
    records = []
    for obj in objects:
        if obj.get('type') == 'mesh':
            meshes.append(obj['mesh'])
            record = {'mesh': obj['mesh']}
            if obj.get('modeling'):
                meshes.append(obj['modeling']['evaluation']['mesh'])
                record['modeling'] = obj['modeling']
            records.append(record)
    if (sum(len(m['vertices']) for m in meshes) > MAX_SCENE_VERTICES
            or sum(len(m['triangles']) for m in meshes) > MAX_SCENE_TRIANGLES
            or len(_json_bytes(records)) > MAX_GEOMETRY_BYTES):
        raise ValueError('All control cages and evaluated geometry together must fit the scene geometry budget (100,000 vertices, 200,000 triangles, 5 MiB).')


def primitive_cage(kind):
    if kind == 'cube':
        return ([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                 [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]],
                [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
    if kind == 'plane':
        return ([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], [[0, 1, 2, 3]])
    if kind == 'cylinder':
        points = [[math.cos(i * math.tau / 32), math.sin(i * math.tau / 32), z] for z in (-1, 1) for i in range(32)]
        return points, [list(reversed(range(32))), list(range(32, 64)), *[[i, (i + 1) % 32, (i + 1) % 32 + 32, i + 32] for i in range(32)]]
    if kind == 'sphere':
        points = [[0., 0., 1.]]
        points.extend([[math.sin(lat * math.pi / 16) * math.cos(lon * math.tau / 32),
                        math.sin(lat * math.pi / 16) * math.sin(lon * math.tau / 32), math.cos(lat * math.pi / 16)]
                       for lat in range(1, 16) for lon in range(32)])
        points.append([0., 0., -1.])
        index = lambda lat, lon: 1 + (lat - 1) * 32 + lon % 32
        faces = [[0, index(1, i), index(1, i + 1)] for i in range(32)]
        faces.extend([[index(lat, i), index(lat + 1, i), index(lat + 1, i + 1), index(lat, i + 1)] for lat in range(1, 15) for i in range(32)])
        faces.extend([[len(points) - 1, index(15, i + 1), index(15, i)] for i in range(32)])
        return points, faces
    raise ValueError('Convert a supported primitive or imported mesh.')


def _indices(value, count, label, maximum=512):
    if (not isinstance(value, list) or not 1 <= len(value) <= maximum
            or any(type(v) is not int or not 0 <= v < count for v in value) or len(set(value)) != len(value)):
        raise ValueError(label + ' must select distinct existing elements (at most %d).' % maximum)
    return value


def _compact(points, faces):
    used = sorted({v for face in faces for v in face})
    remap = {old: new for new, old in enumerate(used)}
    return [points[v] for v in used], [[remap[v] for v in face] for face in faces]


def prepare_operation(obj, operation):
    """Pure topology stage; never updates the caller's object or source record."""
    obj = copy.deepcopy(obj)
    op = _mapping(operation, {'type', 'indices', 'delta', 'face', 'faces', 'distance', 'modifiers'}, 'Modeling operation')
    kind = op.get('type')
    allowed = {'convert': set(), 'move_vertices': {'indices', 'delta'}, 'extrude_face': {'face', 'distance'},
               'delete_faces': {'faces'}, 'subdivide_faces': {'faces'}, 'set_modifiers': {'modifiers'},
               'apply_modifiers': set(), 'refresh': set()}
    if not isinstance(kind, str) or kind not in allowed or set(op) - {'type', *allowed.get(kind, set())}:
        raise ValueError('Choose a supported modeling operation and its exact fields.')
    warnings = []
    if 'modeling' not in obj:
        if kind != 'convert':
            raise ValueError('Enter Edit mesh before changing its topology or modifier stack.')
        if obj['type'] == 'mesh':
            mesh = validate_mesh(obj['mesh'])
            origin = {'kind': 'import' if mesh.get('source') else 'authored', 'mesh_sha256': mesh['sha256']}
            if mesh.get('source'):
                origin['source'] = mesh.pop('source')
            faces = copy.deepcopy(mesh['triangles'])
        else:
            origin = {'kind': 'primitive', 'primitive': obj['type']}
            points, faces = primitive_cage(obj['type'])
            mesh = _cage_mesh(points, faces)
        obj['type'], obj['mesh'] = 'mesh', mesh
        obj['modeling'] = {'version': 1, 'faces': faces, 'origin': origin, 'modifiers': []}
    elif kind == 'convert':
        raise ValueError('This object is already an editable mesh.')
    modeling = obj['modeling']
    if kind == 'set_modifiers':
        modeling['modifiers'] = validate_modifiers(op.get('modifiers'))
    elif kind == 'apply_modifiers':
        if not modeling['modifiers']:
            raise ValueError('There is no modifier stack to apply.')
        # Baking must never accept a forged cached evaluation: the public
        # model_mesh entrypoint reevaluates this object before this operation.
        obj['mesh'] = copy.deepcopy(modeling['evaluation']['mesh'])
        modeling['faces'] = copy.deepcopy(obj['mesh']['triangles'])
        modeling['modifiers'] = []
    elif kind not in {'convert', 'refresh'}:
        points, faces = copy.deepcopy(obj['mesh']['vertices']), copy.deepcopy(modeling['faces'])
        if kind == 'move_vertices':
            selected = _indices(op.get('indices'), len(points), 'Vertex selection')
            delta = _vector(op.get('delta'), 'Vertex translation')
            for i in selected:
                points[i] = [v + d for v, d in zip(points[i], delta)]
        elif kind == 'extrude_face':
            index = _number(op.get('face'), 'Extruded face', 0, len(faces) - 1, True)
            distance = _number(op.get('distance'), 'Extrusion distance', -100, 100)
            if abs(distance) < 1e-6:
                raise ValueError('Extrusion distance must be at least 0.000001 m in magnitude.')
            face = faces[index]
            normal = [0., 0., 0.]
            for a, b in zip(face, face[1:] + face[:1]):
                p, q = points[a], points[b]
                normal[0] += (p[1] - q[1]) * (p[2] + q[2])
                normal[1] += (p[2] - q[2]) * (p[0] + q[0])
                normal[2] += (p[0] - q[0]) * (p[1] + q[1])
            size = math.hypot(*normal)
            if size < 1e-12:
                raise ValueError('Choose a face with a usable extrusion normal.')
            offset = [v * distance / size for v in normal]
            top = list(range(len(points), len(points) + len(face)))
            points.extend([[v + d for v, d in zip(points[i], offset)] for i in face])
            faces[index] = top
            faces.extend([[a, b, top[(i + 1) % len(face)], top[i]] for i, (a, b) in enumerate(zip(face, face[1:] + face[:1]))])
        elif kind == 'delete_faces':
            selected = set(_indices(op.get('faces'), len(faces), 'Face selection'))
            if len(selected) == len(faces):
                raise ValueError('Keep at least one face, or delete the whole object instead.')
            points, faces = _compact(points, [f for i, f in enumerate(faces) if i not in selected])
        else:
            selected = set(_indices(op.get('faces'), len(faces), 'Face selection'))
            midpoints = {}
            for i in sorted(selected):
                face = faces[i]
                for a, b in zip(face, face[1:] + face[:1]):
                    edge = tuple(sorted((a, b)))
                    if edge not in midpoints:
                        midpoints[edge] = len(points)
                        points.append([(x + y) / 2 for x, y in zip(points[a], points[b])])
            refined = []
            for i, face in enumerate(faces):
                edges = [midpoints.get(tuple(sorted((a, b)))) for a, b in zip(face, face[1:] + face[:1])]
                if i not in selected:
                    # Keep neighbouring faces connected to the new shared edge
                    # points instead of leaving T-junctions in the edit cage.
                    refined.append([v for pair in zip(face, edges) for v in pair if v is not None])
                elif len(face) == 3:
                    a, b, c = face
                    ab, bc, ca = edges
                    refined.extend([[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]])
                else:
                    center = len(points)
                    points.append([sum(points[v][axis] for v in face) / len(face) for axis in range(3)])
                    refined.extend([[v, edges[j], center, edges[j - 1]] for j, v in enumerate(face)])
            faces = refined
        previous = obj['mesh']
        rebuilt = _cage_mesh(points, faces)
        if kind == 'move_vertices':
            # Moving control points does not edit UVs. Imported cages are
            # triangles, so independent corners and seams retain exact indices.
            # For a polygon cage, retriangulation may change diagonals: remap
            # by face-local corners instead of welding coincident UV seams.
            if previous['uvs']:
                rebuilt['uvs'] = copy.deepcopy(previous['uvs'])
                rebuilt['uv_indices'] = []
                offset = 0
                for face in faces:
                    count = len(face) - 2
                    corners = {}
                    for triangle, indices in zip(previous['triangles'][offset:offset + count],
                                                 previous['uv_indices'][offset:offset + count]):
                        for vertex, uv in zip(triangle, indices):
                            if vertex in corners and corners[vertex] != uv and (
                                    corners[vertex] < 0 or uv < 0 or previous['uvs'][corners[vertex]] != previous['uvs'][uv]):
                                raise ValueError('This polygon has conflicting UVs at one control corner. Triangulate it before moving vertices.')
                            corners[vertex] = uv
                    rebuilt['uv_indices'].extend([[corners[vertex] for vertex in triangle]
                                                   for triangle in rebuilt['triangles'][offset:offset + count]])
                    offset += count
            if previous['normals']:
                if (not any(delta) or len(selected) == len(points)) and rebuilt['triangles'] == previous['triangles']:
                    rebuilt['normals'] = copy.deepcopy(previous['normals'])
                    rebuilt['normal_indices'] = copy.deepcopy(previous['normal_indices'])
                else:
                    warnings.append('Vertex deformation preserves UV corners and rebuilds surface normals from the changed geometry.')
            rebuilt.pop('sha256', None)
            rebuilt = validate_mesh(rebuilt)
        elif previous['uvs'] or previous['normals']:
            warnings.append('Topology edits rebuild surface normals and clear imported UV corners. Original source hashes remain in the mesh origin.')
        obj['mesh'] = rebuilt
        modeling['faces'] = faces
    modeling.pop('evaluation', None)
    validate_modeling(obj, require_evaluation=False)
    return obj, warnings


def blender_modeling_source():
    return Path(__file__).with_name('modeling_blender.py').read_text(encoding='utf-8')


def evaluate_object(obj, cancel_event=None):
    _cancelled(cancel_event)
    binary = find_blender()
    if not binary:
        raise AdapterError('The Blender geometry engine is unavailable. Configure Blender before editing meshes or modifiers.')
    candidate = copy.deepcopy(obj)
    candidate['mesh'] = validate_mesh(candidate['mesh'])
    candidate['modeling'].pop('evaluation', None)
    validate_modeling(candidate, require_evaluation=False)
    if not _EVALUATION_SLOT.acquire(blocking=False):
        raise AdapterError('Another mesh is being evaluated. Wait for that operation to finish.')
    try:
        with tempfile.TemporaryDirectory(prefix='cinematicum-owned-model-') as temporary:
            work = Path(temporary)
            spec, output, script = work / 'object.json', work / 'evaluation.json', work / 'evaluate.py'
            spec.write_bytes(_json_bytes(candidate))
            source = blender_modeling_source() + '\n'
            source += 'from pathlib import Path\n'
            source += 'bpy.ops.object.select_all(action="SELECT")\nbpy.ops.object.delete(use_global=False)\n'
            source += 'item = json.loads(Path(%r).read_text(encoding="utf-8"))\n' % str(spec)
            source += 'obj = cinematicum_model_object(item, bpy.context.scene.collection)\n'
            source += 'result = {"engine_version": bpy.app.version_string, "mesh": cinematicum_extract_model(obj)}\n'
            source += 'Path(%r).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")\n' % str(output)
            script.write_text(source, encoding='utf-8')
            _run_owned([binary, '--background', '--factory-startup', '--disable-autoexec', '--threads', '2',
                        '--python-exit-code', '2', '--python', str(script)], work / 'blender.log', cancel_event, MODELING_TIMEOUT)
            if not output.is_file() or output.stat().st_size > 12 * 1024 * 1024:
                raise AdapterError('The geometry engine produced no bounded mesh result.')
            result = json.loads(output.read_text(encoding='utf-8'))
            candidate['modeling']['evaluation'] = {'key': evaluation_key(candidate),
                                                   'engine_version': result['engine_version'],
                                                   'mesh': validate_mesh(result['mesh'])}
            validate_modeling(candidate)
            return candidate
    finally:
        _EVALUATION_SLOT.release()


def model_mesh(payload, cancel_event=None):
    """Read-only candidate operation; the caller commits one guarded undo entry."""
    _mapping(payload, {'object', 'operation'}, 'Mesh operation')
    # Import lazily to keep scene's data-only validation independent of worker
    # launch and avoid a module cycle.
    from scene import default_scene, validate_scene
    scene = default_scene()
    scene['frame_end'] = 7200
    scene['lights'] = []
    scene['objects'] = [payload.get('object')]
    obj = validate_scene(scene)['objects'][0]
    operation = payload.get('operation')
    if isinstance(operation, dict) and operation.get('type') == 'apply_modifiers':
        obj = evaluate_object(obj, cancel_event)
    candidate, warnings = prepare_operation(obj, operation)
    candidate = evaluate_object(candidate, cancel_event)
    mesh = candidate['modeling']['evaluation']['mesh']
    return {'object': candidate, 'warnings': warnings,
            'statistics': {'control_vertices': len(candidate['mesh']['vertices']),
                           'control_faces': len(candidate['modeling']['faces']),
                           'evaluated_vertices': len(mesh['vertices']), 'evaluated_triangles': len(mesh['triangles']),
                           'engine_version': candidate['modeling']['evaluation']['engine_version']}}

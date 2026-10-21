"""Finite object hierarchies and affine transforms, independent of Blender.

Object poses and their keys are local to ``parent_id``.  Matrices use the
column-major convention shared by WebGL.  Nonuniformly scaled ancestors can
produce shear: retain the complete matrix instead of decomposing it back to
Euler angles or pretending a world transform is another local pose.
"""
from __future__ import annotations

import math

MAX_PARENT_DEPTH = 24


def validate_hierarchy(objects):
    by_id = {item['id']: item for item in objects}
    for item in objects:
        parent = item.get('parent_id')
        if parent is None:
            item.pop('parent_id', None)
            continue
        if not isinstance(parent, str) or parent not in by_id:
            raise ValueError('Object parent must identify another object in this scene.')
        seen = {item['id']}
        while parent is not None:
            if not isinstance(parent, str) or parent not in by_id:
                raise ValueError('Object parent must identify another object in this scene.')
            if parent in seen:
                raise ValueError('Object parenting must not form a cycle.')
            seen.add(parent)
            if len(seen) > MAX_PARENT_DEPTH:
                raise ValueError('Object hierarchies support at most 24 levels.')
            parent = by_id[parent].get('parent_id')
    for item in objects:
        chain, current = [], item
        while current is not None:
            chain.append(current)
            current = by_id.get(current.get('parent_id'))
        largest, smallest, bound = 1., 1., 0.
        for current in reversed(chain):
            poses = [current, *current.get('keyframes', [])]
            bound += largest * max(math.hypot(*p.get('position', current['position'])) for p in poses)
            largest *= max(max(p.get('scale', current['scale'])) for p in poses)
            smallest *= min(min(p.get('scale', current['scale'])) for p in poses)
        if largest > 1e6 or smallest < 1e-6 or bound > 1e6:
            raise ValueError('Hierarchy transform exceeds the viewport range. Reduce inherited scale or translation.')


def matrix_product(a, b):
    return [sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
            for c in range(4) for r in range(4)]


def local_matrix(pose):
    x, y, z = [math.radians(v) for v in pose['rotation']]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    out = [cz*cy, sz*cy, -sy, 0., cz*sy*sx-sz*cx, sz*sy*sx+cz*cx, cy*sx, 0.,
           cz*sy*cx+sz*sx, sz*sy*cx-cz*sx, cy*cx, 0., *pose['position'], 1.]
    for c in range(3):
        for r in range(3):
            out[c * 4 + r] *= pose['scale'][c]
    return out


def world_matrix_at(objects, object_id, frame, pose_evaluator):
    by_id = {item['id']: item for item in objects}
    visited = set()

    def evaluate(ident):
        if ident not in by_id or ident in visited or len(visited) >= MAX_PARENT_DEPTH:
            raise ValueError('Invalid object hierarchy.')
        visited.add(ident)
        item = by_id[ident]
        matrix = local_matrix(pose_evaluator(item, frame))
        if item.get('parent_id'):
            matrix = matrix_product(evaluate(item['parent_id']), matrix)
        visited.remove(ident)
        return matrix

    return evaluate(object_id)


def transform_point(matrix, point):
    return [sum(matrix[c * 4 + r] * point[c] for c in range(3)) + matrix[12 + r]
            for r in range(3)]

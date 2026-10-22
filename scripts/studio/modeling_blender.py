"""Owned Blender definitions embedded into evaluation and retained-scene scripts.

Only normalized numeric geometry and a finite modifier vocabulary enter these
functions. This file has no CLI and does not load user scripts or external files.
"""

import bpy
import math
import json


def cinematicum_add_modifiers(obj, specifications):
    for index, spec in enumerate(specifications):
        kind = spec['type']
        modifier = obj.modifiers.new('CINEMATICUM %02d %s' % (index + 1, kind.title()),
                                    {'mirror': 'MIRROR', 'bevel': 'BEVEL', 'subdivision': 'SUBSURF',
                                     'solidify': 'SOLIDIFY', 'array': 'ARRAY', 'decimate': 'DECIMATE',
                                     'smooth': 'SMOOTH', 'simple_deform': 'SIMPLE_DEFORM'}[kind])
        modifier.show_viewport = spec['enabled']
        modifier.show_render = spec['enabled']
        if kind == 'mirror':
            axis = 'XYZ'.index(spec['axis'])
            modifier.use_axis = [i == axis for i in range(3)]
            modifier.use_bisect_axis = [spec['bisect'] and i == axis for i in range(3)]
            modifier.use_bisect_flip_axis = [spec['flip'] and i == axis for i in range(3)]
            modifier.use_mirror_merge = True
            modifier.merge_threshold = spec['merge_distance']
        elif kind == 'bevel':
            modifier.offset_type = 'OFFSET'
            modifier.width = spec['width']
            modifier.segments = spec['segments']
            modifier.limit_method = 'ANGLE'
            modifier.angle_limit = math.radians(spec['angle'])
            modifier.use_clamp_overlap = True
            modifier.affect = 'EDGES'
        elif kind == 'subdivision':
            modifier.subdivision_type = spec['method']
            modifier.levels = spec['levels']
            modifier.render_levels = spec['levels']
            modifier.quality = 3
            modifier.use_limit_surface = True
        elif kind == 'solidify':
            modifier.thickness = spec['thickness']
            modifier.offset = spec['offset']
            modifier.use_even_offset = spec['even']
            modifier.use_rim = spec['rim']
        elif kind == 'array':
            modifier.fit_type = 'FIXED_COUNT'
            modifier.count = spec['count']
            modifier.use_relative_offset = False
            modifier.use_constant_offset = True
            modifier.constant_offset_displace = spec['offset']
            modifier.use_merge_vertices = spec['merge']
            modifier.merge_threshold = spec['merge_distance']
        elif kind == 'decimate':
            modifier.decimate_type = 'COLLAPSE'
            modifier.ratio = spec['ratio']
            modifier.use_symmetry = spec['symmetry']
            modifier.symmetry_axis = spec['axis']
        elif kind == 'smooth':
            modifier.factor = spec['factor']
            modifier.iterations = spec['iterations']
            modifier.use_x, modifier.use_y, modifier.use_z = spec['axes']
        elif kind == 'simple_deform':
            modifier.deform_method = spec['method']
            modifier.deform_axis = spec['axis']
            if spec['method'] in ('TWIST', 'BEND'):
                modifier.angle = math.radians(spec['angle'])
            else:
                modifier.factor = spec['factor']


def cinematicum_model_object(item, collection):
    geometry, modeling = item['mesh'], item['modeling']
    data = bpy.data.meshes.new(item['name'] + ' Control cage')
    data.from_pydata(geometry['vertices'], [], modeling['faces'])
    data.update()
    if modeling['origin'].get('primitive') == 'sphere':
        for polygon in data.polygons:
            polygon.use_smooth = True
    if len(data.vertices) != len(geometry['vertices']) or len(data.polygons) != len(modeling['faces']):
        raise RuntimeError('The modeling control cage was not preserved by Blender.')
    # Canonical triangle UVs retain independent per-face corners even for an
    # editable quad/n-gon cage. Never weld coincident seam coordinates.
    if geometry['uvs']:
        uv = data.uv_layers.new(name='UVMap')
        offset = 0
        for polygon, face in zip(data.polygons, modeling['faces']):
            count, corners = len(face) - 2, {}
            for triangle, indices in zip(geometry['triangles'][offset:offset+count], geometry['uv_indices'][offset:offset+count]):
                for vertex, index in zip(triangle, indices):
                    value = geometry['uvs'][index] if index >= 0 else (0, 0)
                    if vertex in corners and tuple(corners[vertex]) != tuple(value):
                        raise RuntimeError('A control face has conflicting UV corners; triangulate it before UV editing.')
                    corners[vertex] = value
            for loop, vertex in zip(polygon.loop_indices, face):
                uv.data[loop].uv = corners[vertex]
            offset += count
    if modeling['faces'] == geometry['triangles']:
        if geometry['normals']:
            for polygon in data.polygons:
                polygon.use_smooth = True
            data.normals_split_custom_set([geometry['normals'][i] for face in geometry['normal_indices'] for i in face])
    obj = bpy.data.objects.new(item['name'], data)
    collection.objects.link(obj)
    cinematicum_add_modifiers(obj, modeling['modifiers'])
    obj['cinematicum_geometry_sha256'] = geometry['sha256']
    obj['cinematicum_control_faces'] = json.dumps(modeling['faces'], separators=(',', ':'))
    obj['cinematicum_modeling_origin'] = json.dumps(modeling['origin'], sort_keys=True)
    obj['cinematicum_modifier_recipe'] = json.dumps(modeling['modifiers'], sort_keys=True)
    origin = modeling['origin']
    if origin.get('source'):
        obj['cinematicum_original_source_sha256'] = origin['source']['sha256']
        obj['cinematicum_original_source_name'] = origin['source']['name']
    return obj


def cinematicum_extract_model(obj):
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=bpy.context.evaluated_depsgraph_get())
    try:
        data.calc_loop_triangles()
        if len(data.vertices) > 50000 or len(data.loop_triangles) > 100000:
            raise RuntimeError('The evaluated modifier stack exceeds the mesh geometry limit.')
        if hasattr(data, 'calc_normals_split'):
            data.calc_normals_split()
        normals = data.corner_normals if hasattr(data, 'corner_normals') else None
        uv_layer = data.uv_layers.active
        mesh = {'version': 1, 'vertices': [list(v.co) for v in data.vertices],
                'triangles': [], 'normals': [], 'normal_indices': [], 'uvs': [], 'uv_indices': []}
        normal_map, uv_map = {}, {}
        for triangle in data.loop_triangles:
            mesh['triangles'].append(list(triangle.vertices))
            ni, ui = [], []
            for loop in triangle.loops:
                value = tuple(normals[loop].vector if normals is not None else data.loops[loop].normal)
                length = math.sqrt(sum(v * v for v in value))
                if length < 1e-12:
                    raise RuntimeError('Modifier evaluation produced an invalid corner normal.')
                value = tuple(v / length for v in value)
                if value not in normal_map:
                    normal_map[value] = len(mesh['normals'])
                    mesh['normals'].append(list(value))
                ni.append(normal_map[value])
                if uv_layer is not None:
                    value = tuple(uv_layer.data[loop].uv)
                    if value not in uv_map:
                        uv_map[value] = len(mesh['uvs'])
                        mesh['uvs'].append(list(value))
                    ui.append(uv_map[value])
            mesh['normal_indices'].append(ni)
            if uv_layer is not None:
                mesh['uv_indices'].append(ui)
        return mesh
    finally:
        evaluated.to_mesh_clear()


def cinematicum_unwrap(obj, angle, margin):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin,
                                 correct_aspect=True)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    if obj.data.uv_layers.active is None:
        raise RuntimeError('The geometry engine produced no UV unwrap.')


def cinematicum_control_uvs(obj, item):
    geometry = json.loads(json.dumps(item['mesh']))
    geometry.pop('sha256', None)
    geometry['uvs'], geometry['uv_indices'] = [], []
    uv = obj.data.uv_layers.active
    offset, unique = 0, {}
    for polygon, face in zip(obj.data.polygons, item['modeling']['faces']):
        corners = {}
        for loop, vertex in zip(polygon.loop_indices, face):
            value = tuple(uv.data[loop].uv)
            # Share a UV point only across the same cage vertex and coordinate.
            # This retains disconnected or deliberately split islands.
            key = (vertex, value)
            if key not in unique:
                unique[key] = len(geometry['uvs'])
                geometry['uvs'].append(list(value))
            corners[vertex] = unique[key]
        count = len(face) - 2
        for triangle in geometry['triangles'][offset:offset+count]:
            geometry['uv_indices'].append([corners[vertex] for vertex in triangle])
        offset += count
    return geometry


def cinematicum_verify_model(obj, item):
    expected = item['modeling']['evaluation']
    if expected['engine_version'] != bpy.app.version_string:
        raise RuntimeError('The Blender version changed. Refresh this modifier stack in CINEMATICUM before rendering.')
    actual, wanted = cinematicum_extract_model(obj), expected['mesh']
    for channel in ('triangles', 'normal_indices', 'uv_indices'):
        if actual[channel] != wanted[channel]:
            raise RuntimeError('The retained modifier geometry differs from the saved viewport (' + channel + '). Refresh the stack.')
    for channel in ('vertices', 'normals', 'uvs'):
        if len(actual[channel]) != len(wanted[channel]) or any(
                len(a) != len(b) or any(abs(x - y) > 2e-6 * max(1, abs(x), abs(y)) for x, y in zip(a, b))
                for a, b in zip(actual[channel], wanted[channel])):
            raise RuntimeError('The retained modifier geometry differs from the saved viewport (' + channel + '). Refresh the stack.')
    obj['cinematicum_evaluated_geometry_sha256'] = wanted['sha256']
    obj['cinematicum_evaluation_key'] = expected['key']

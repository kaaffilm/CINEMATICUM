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
                                    {'mirror': 'MIRROR', 'bevel': 'BEVEL', 'subdivision': 'SUBSURF'}[kind])
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
        else:
            modifier.subdivision_type = spec['method']
            modifier.levels = spec['levels']
            modifier.render_levels = spec['levels']
            modifier.quality = 3
            modifier.use_limit_surface = True


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
    # Imported triangle cages retain their actual independent corner channels.
    if modeling['faces'] == geometry['triangles']:
        if geometry['uvs']:
            uv = data.uv_layers.new(name='UVMap')
            for polygon, indices in zip(data.polygons, geometry['uv_indices']):
                for loop, index in zip(polygon.loop_indices, indices):
                    uv.data[loop].uv = geometry['uvs'][index] if index >= 0 else (0, 0)
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

"""Explicit Cycles execution-device selection; never silently falls back.

The configure function is also embedded in the owned Blender scene builder.
It inspects the executing Blender build and its actual enumerated devices.
"""
RENDER_DEVICES = ('CPU', 'METAL', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI')


def configure_cycles_device(bpy_module, scene, requested):
    if requested == 'CPU':
        scene.cycles.device = 'CPU'
        return {'requested': 'CPU', 'actual': 'CPU', 'devices': []}
    if requested not in ('METAL', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI'):
        raise RuntimeError('Unsupported Cycles compute backend.')
    addon = bpy_module.context.preferences.addons.get('cycles')
    if addon is None:
        raise RuntimeError('This Blender build has no Cycles preferences.')
    preferences = addon.preferences
    try:
        preferences.compute_device_type = requested
        preferences.get_devices()
    except Exception as error:
        raise RuntimeError('Cycles %s is unavailable in this Blender build: %s' % (requested, error)) from error
    selected = []
    for device in preferences.devices:
        use = device.type == requested
        device.use = use
        if use:
            selected.append({'id': str(device.id), 'name': str(device.name), 'type': str(device.type)})
    if not selected:
        raise RuntimeError('Cycles %s has no usable device. Choose CPU or configure a supported GPU; no CPU fallback was performed.' % requested)
    scene.cycles.device = 'GPU'
    return {'requested': requested, 'actual': requested, 'devices': selected}

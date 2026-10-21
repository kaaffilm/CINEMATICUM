"""Bounded, data-only geometry interchange for the CINEMATICUM scene recipe.

This module never opens a path, follows an OBJ/MTL reference, invokes an engine,
or evaluates source text. Face-corner normal/UV indices remain independent of
position indices. Solved geometry interchange is not image reconstruction.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
import hashlib
import io
import json
import math
import re
import uuid


MAX_OBJ_BYTES = 5 * 1024 * 1024
MAX_MTL_BYTES = 1024 * 1024
MAX_GEOMETRY_BYTES = 5 * 1024 * 1024
MAX_VERTICES = 50_000
MAX_TRIANGLES = 100_000
MAX_SCENE_VERTICES = 100_000
MAX_SCENE_TRIANGLES = 200_000
MAX_PARTS = 96
MAX_FACE_CORNERS = 64
MAX_LINE_LENGTH = 16_384
MAX_COORDINATE = 1000
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_INTEGER = re.compile(r"-?[0-9]{1,12}\Z")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("ascii")


def _mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported properties.")
    return value


def _number(value, label, low=-MAX_COORDINATE, high=MAX_COORDINATE):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a finite number.")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(label + " must be a finite number.")
    if not low <= value <= high:
        raise ValueError("%s must be between %s and %s." % (label, low, high))
    return float(value)


def _text(value, label, max_bytes):
    if not isinstance(value, str):
        raise ValueError(label + " must be supplied as UTF-8 text.")
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError(label + " contains invalid Unicode.") from error
    if len(raw) > max_bytes:
        raise ValueError(label + " exceeds the supported file size.")
    if "\x00" in value or any(ord(c) < 32 and c not in "\t\r\n" for c in value):
        raise ValueError(label + " contains unsupported control characters.")
    return raw


def _name(value, label="Name", maximum=120):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(label + " must contain 1–%d printable characters." % maximum)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError(label + " contains invalid Unicode.") from error
    return value.strip()


def _filename(value, extension):
    value = _name(value, "File name")
    if any(c in value for c in ("/", "\\", ":")) or value in {".", ".."} or not value.lower().endswith(extension):
        raise ValueError("Choose a plain %s file name without a directory or URL." % extension)
    return value


def _lines(value, label):
    for number, raw in enumerate(io.StringIO(value.removeprefix("\ufeff")), 1):
        if len(raw) > MAX_LINE_LENGTH:
            raise ValueError("%s line %d is too long." % (label, number))
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            raise ValueError("%s line %d: continued lines are unsupported; export ordinary polygon faces." % (label, number))
        fields = line.split(None, 1)
        yield number, fields[0], fields[1] if len(fields) == 2 else ""


def _floats(value, count, label, low=-MAX_COORDINATE, high=MAX_COORDINATE):
    fields = value.split()
    if len(fields) != count:
        raise ValueError(label + " needs %d numeric values." % count)
    try:
        return [_number(float(field), label, low, high) for field in fields]
    except (OverflowError, ValueError) as error:
        raise ValueError(label + ": " + str(error)) from error


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(value, label):
    length = math.hypot(*value)
    if length < 1e-20:
        raise ValueError(label + " must not be zero.")
    return [v / length for v in value]


def _triangle_normal(a, b, c):
    ab, ac = _sub(b, a), _sub(c, a)
    normal = _cross(ab, ac)
    if math.hypot(*normal) <= max(math.hypot(*ab) * math.hypot(*ac) * 1e-12, 1e-24):
        raise ValueError("A face contains a degenerate triangle.")
    return normal


def _area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _triangulate(corners, vertices):
    """Ear-clip a simple planar polygon, retaining original corner tuples."""
    if not 3 <= len(corners) <= MAX_FACE_CORNERS:
        raise ValueError("Faces need 3–%d corners; triangulate larger faces before importing." % MAX_FACE_CORNERS)
    if len({corner[0] for corner in corners}) != len(corners):
        raise ValueError("A face repeats a vertex; remove duplicate corners before importing.")
    points = [vertices[corner[0]] for corner in corners]
    if len(corners) == 3:
        _triangle_normal(*points)
        return [corners]
    normal = [0., 0., 0.]
    for a, b in zip(points, points[1:] + points[:1]):
        normal[0] += (a[1] - b[1]) * (a[2] + b[2])
        normal[1] += (a[2] - b[2]) * (a[0] + b[0])
        normal[2] += (a[0] - b[0]) * (a[1] + b[1])
    unit = _unit(normal, "Polygon normal")
    extent = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
    if extent < 1e-12 or any(abs(_dot(_sub(p, points[0]), unit)) > max(extent * 1e-5, 1e-9) for p in points):
        raise ValueError("Nonplanar faces must be triangulated before importing.")
    drop = max(range(3), key=lambda i: abs(normal[i]))
    flat = [[p[i] for i in range(3) if i != drop] for p in points]
    eps = max(extent * extent * 1e-12, 1e-24)
    signed = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(flat, flat[1:] + flat[:1]))
    if abs(signed) <= eps:
        raise ValueError("A polygon has no usable area.")
    sign = 1 if signed > 0 else -1

    def on_segment(a, b, p):
        return (abs(_area2(a, b, p)) <= eps
                and min(a[0], b[0]) - 1e-12 <= p[0] <= max(a[0], b[0]) + 1e-12
                and min(a[1], b[1]) - 1e-12 <= p[1] <= max(a[1], b[1]) + 1e-12)

    for i in range(len(flat)):
        a, b = flat[i], flat[(i + 1) % len(flat)]
        if math.dist(a, b) <= max(extent * 1e-12, 1e-12):
            raise ValueError("A polygon contains coincident corners.")
        for j in range(i + 1, len(flat)):
            if j in {(i + 1) % len(flat), (i - 1) % len(flat)}:
                continue
            c, d = flat[j], flat[(j + 1) % len(flat)]
            ab_c, ab_d, cd_a, cd_b = _area2(a, b, c), _area2(a, b, d), _area2(c, d, a), _area2(c, d, b)
            if (ab_c * ab_d < -eps * eps and cd_a * cd_b < -eps * eps
                    or any((on_segment(a, b, c), on_segment(a, b, d), on_segment(c, d, a), on_segment(c, d, b)))):
                raise ValueError("Self-intersecting polygons cannot be imported.")
    remaining, triangles = list(range(len(corners))), []
    while len(remaining) > 3:
        ear = None
        for slot, current in enumerate(remaining):
            previous, following = remaining[slot - 1], remaining[(slot + 1) % len(remaining)]
            a, b, c = flat[previous], flat[current], flat[following]
            if _area2(a, b, c) * sign <= eps:
                continue
            if any(all(v * sign >= -eps for v in (_area2(a, b, flat[k]), _area2(b, c, flat[k]), _area2(c, a, flat[k])))
                   for k in remaining if k not in {previous, current, following}):
                continue
            ear = slot
            triangles.append([corners[previous], corners[current], corners[following]])
            break
        if ear is None:
            raise ValueError("The polygon cannot be triangulated without ambiguous or degenerate geometry.")
        del remaining[ear]
    final = [corners[i] for i in remaining]
    _triangle_normal(*(vertices[corner[0]] for corner in final))
    triangles.append(final)
    return triangles


def _index(text, count, label):
    if not _INTEGER.fullmatch(text):
        raise ValueError(label + " must be a bounded integer index.")
    value = int(text)
    index = value - 1 if value > 0 else count + value
    if value == 0 or not 0 <= index < count:
        raise ValueError(label + " references a missing value (zero/forward/out-of-range index).")
    return index


def _corner(text, counts):
    fields = text.split("/")
    if len(fields) > 3 or not fields[0] or len(fields) == 2 and not fields[1] or len(fields) == 3 and not fields[2]:
        raise ValueError("Faces must use v, v/vt, v//vn or v/vt/vn indices.")
    return tuple(_index(fields[i], counts[i], ("Vertex", "UV", "Normal")[i]) if i < len(fields) and fields[i] else -1
                 for i in range(3))


def _linear_hex(values):
    def byte(c):
        srgb = c * 12.92 if c <= .0031308 else 1.055 * c ** (1 / 2.4) - .055
        return min(255, max(0, round(srgb * 255)))
    return "#" + "".join("%02x" % byte(c) for c in values)


def _materials(files, warn):
    result, hashes = {}, {}
    total = 0
    if not isinstance(files, dict) or len(files) > 8:
        raise ValueError("Supply at most eight selected MTL files.")
    for filename, text in files.items():
        filename = _filename(filename, ".mtl")
        raw = _text(text, filename, MAX_MTL_BYTES)
        total += len(raw)
        if total > MAX_MTL_BYTES:
            raise ValueError("The selected MTL files together exceed 1 MiB.")
        hashes[filename] = hashlib.sha256(raw).hexdigest()
        current, roughness_explicit = None, set()
        for line, token, rest in _lines(text, filename):
            try:
                if token == "newmtl":
                    key = _name(rest, "Material name")
                    if key in result:
                        raise ValueError("Duplicate material names are ambiguous across the selected MTL files.")
                    if len(result) >= 192:
                        raise ValueError("At most 192 material definitions may be imported.")
                    current = {"color": "#bcbcbc", "roughness": .45, "metallic": 0.}
                    result[key] = current
                elif current is None:
                    raise ValueError("MTL properties must follow a newmtl definition.")
                elif token == "Kd":
                    current["color"] = _linear_hex(_floats(rest, 3, "Diffuse color", 0, 1))
                elif token in {"Pr", "Pm"}:
                    current["roughness" if token == "Pr" else "metallic"] = _floats(rest, 1, token, 0, 1)[0]
                    if token == "Pr":
                        roughness_explicit.add(key)
                elif token == "Ns":
                    shininess = _floats(rest, 1, "Specular exponent", 0, 10000)[0]
                    if key not in roughness_explicit:
                        current["roughness"] = math.sqrt(2 / (shininess + 2))
                elif token in {"d", "Tr"}:
                    alpha = _floats(rest, 1, "Opacity", 0, 1)[0]
                    if token == "Tr":
                        alpha = 1 - alpha
                    if alpha != 1:
                        warn("MTL transparency is not supported; imported parts use opaque materials.")
                elif token.lower().startswith("map_") or token.lower() in {"bump", "disp", "decal", "refl", "norm"}:
                    warn("Material texture images are not imported or opened. UV coordinates are retained for later texturing.")
                else:
                    warn("MTL %s is not represented by the current solid-color material controls." % token[:50])
            except ValueError as error:
                raise ValueError("%s line %d: %s" % (filename, line, error)) from error
    return result, hashes


def _mesh_source(value):
    if value is None:
        return None
    _mapping(value, {"format", "name", "sha256", "materials", "up_axis", "scale", "group", "material"}, "Mesh source")
    if value.get("format") != "wavefront-obj":
        raise ValueError("Unsupported mesh source format.")
    result = {"format": "wavefront-obj", "name": _filename(value.get("name"), ".obj")}
    if not isinstance(value.get("sha256"), str) or not _DIGEST.fullmatch(value["sha256"]):
        raise ValueError("Mesh source requires its SHA-256 digest.")
    result["sha256"] = value["sha256"]
    materials = value.get("materials", {})
    if not isinstance(materials, dict) or len(materials) > 8:
        raise ValueError("Mesh material provenance is invalid.")
    result["materials"] = {}
    for name, digest in materials.items():
        name = _filename(name, ".mtl")
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ValueError("Mesh material source requires a SHA-256 digest.")
        result["materials"][name] = digest
    result["up_axis"] = value.get("up_axis", "Z")
    if not isinstance(result["up_axis"], str) or result["up_axis"] not in {"Y", "Z"}:
        raise ValueError("Mesh up axis must be Y or Z.")
    result["scale"] = _number(value.get("scale", 1), "Import scale", 1e-6, 10000)
    result["group"] = _name(value.get("group", "Mesh"), "Mesh group")
    result["material"] = _name(value["material"], "Source material") if value.get("material") else ""
    return result


def validate_mesh(mesh):
    """Normalize a standalone indexed mesh before accepting it into a scene."""
    _mapping(mesh, {"version", "vertices", "triangles", "normals", "normal_indices", "uvs", "uv_indices", "sha256", "source"}, "Mesh")
    if type(mesh.get("version")) is not int or mesh["version"] != 1:
        raise ValueError("Unsupported mesh recipe version.")
    normalized = {"version": 1}
    for name, dimension, limit, bound in (("vertices", 3, MAX_VERTICES, MAX_COORDINATE),
                                         ("normals", 3, MAX_TRIANGLES * 3, 1.000001),
                                         ("uvs", 2, MAX_TRIANGLES * 3, 10000)):
        rows = mesh.get(name, [])
        if not isinstance(rows, list) or len(rows) > limit or name == "vertices" and len(rows) < 3:
            raise ValueError("Mesh %s must contain %s bounded entries." % (name, "3–%d" % limit if name == "vertices" else "at most %d" % limit))
        normalized[name] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != dimension:
                raise ValueError("Mesh %s need %d coordinates per entry." % (name, dimension))
            vector = [_number(value, "Mesh " + name, -bound, bound) for value in row]
            if name == "normals" and abs(math.hypot(*vector) - 1) > 1e-5:
                raise ValueError("Mesh normals must have unit length.")
            normalized[name].append(vector)
    triangles = mesh.get("triangles")
    if not isinstance(triangles, list) or not 1 <= len(triangles) <= MAX_TRIANGLES:
        raise ValueError("A mesh needs 1–%d triangles." % MAX_TRIANGLES)
    for name, count, minimum in (("triangles", len(normalized["vertices"]), 0),
                                 ("normal_indices", len(normalized["normals"]), 0),
                                 ("uv_indices", len(normalized["uvs"]), -1)):
        rows = triangles if name == "triangles" else mesh.get(name, [])
        required = name == "triangles" or bool(normalized["normals" if name == "normal_indices" else "uvs"])
        if not isinstance(rows, list) or len(rows) != (len(triangles) if required else 0):
            raise ValueError("Mesh %s must match its face corners." % name)
        normalized[name] = []
        for row in rows:
            if (not isinstance(row, list) or len(row) != 3
                    or any(type(index) is not int or not minimum <= index < count for index in row)):
                raise ValueError("Mesh %s contain an invalid index." % name)
            normalized[name].append(list(row))
    for triangle in normalized["triangles"]:
        _triangle_normal(*(normalized["vertices"][index] for index in triangle))
    geometry_bytes = _json_bytes(normalized)
    if len(geometry_bytes) > MAX_GEOMETRY_BYTES:
        raise ValueError("The canonical mesh exceeds the 5 MiB geometry limit. Reduce its topology before importing.")
    digest = hashlib.sha256(geometry_bytes).hexdigest()
    if "sha256" in mesh and mesh["sha256"] != digest:
        raise ValueError("Mesh geometry does not match its SHA-256 digest.")
    normalized["sha256"] = digest
    source = _mesh_source(mesh.get("source"))
    if source is not None:
        normalized["source"] = source
    return normalized


def validate_scene_geometry(objects):
    """One aggregate limit prevents many individually valid meshes exhausting a project."""
    meshes = [item["mesh"] for item in objects if item.get("type") == "mesh"]
    if sum(len(mesh["vertices"]) for mesh in meshes) > MAX_SCENE_VERTICES:
        raise ValueError("A scene supports at most %d imported vertices." % MAX_SCENE_VERTICES)
    if sum(len(mesh["triangles"]) for mesh in meshes) > MAX_SCENE_TRIANGLES:
        raise ValueError("A scene supports at most %d imported triangles." % MAX_SCENE_TRIANGLES)
    if len(_json_bytes(meshes)) > MAX_GEOMETRY_BYTES:
        raise ValueError("All imported scene geometry together must fit within 5 MiB. Reduce or remove a mesh.")


def import_obj(payload):
    """Parse explicitly supplied OBJ/MTL strings; return objects without saving a project."""
    _mapping(payload, {"name", "obj", "materials", "up_axis", "scale"}, "OBJ import")
    name = _filename(payload.get("name", "Model.obj"), ".obj")
    text = payload.get("obj")
    raw = _text(text, name, MAX_OBJ_BYTES)
    if not raw.strip():
        raise ValueError("The OBJ file is empty.")
    axis = payload.get("up_axis", "Z")
    if not isinstance(axis, str) or axis not in {"Y", "Z"}:
        raise ValueError("Choose Y or Z as the source up axis.")
    scale = _number(payload.get("scale", 1), "Import scale", 1e-6, 10000)
    warnings = []

    def warn(message):
        if message not in warnings:
            if len(warnings) < 24:
                warnings.append(message)
            elif len(warnings) == 24:
                warnings.append("Additional unsupported material properties were omitted.")

    materials, material_hashes = _materials(payload.get("materials", {}), warn)
    vertices, normals, uvs = [], [], []
    parts = OrderedDict()
    smooth_normals = defaultdict(lambda: [0., 0., 0.])
    group, material, smooth = name[:-4] or "Mesh", "", None
    triangle_count, polygon_count = 0, 0

    def convert(value, factor):
        xyz = value if axis == "Z" else [value[0], -value[2], value[1]]
        return [_number(v * factor, "Converted geometry coordinate") for v in xyz]

    for line, token, rest in _lines(text, name):
        try:
            if token == "v":
                if len(vertices) >= MAX_VERTICES:
                    raise ValueError("An OBJ file supports at most %d source vertices." % MAX_VERTICES)
                fields = rest.split()
                if len(fields) == 4:
                    _floats(fields[-1], 1, "Vertex weight", 1, 1)
                    rest = " ".join(fields[:3])
                values = _floats(rest, 3, "Vertex", -1e9, 1e9)
                vertices.append(convert(values, scale))
            elif token == "vn":
                if len(normals) >= MAX_TRIANGLES * 3:
                    raise ValueError("Too many OBJ normals.")
                normal = _unit(_floats(rest, 3, "Normal", -1e9, 1e9), "Normal")
                normals.append(convert(normal, 1))
            elif token == "vt":
                if len(uvs) >= MAX_TRIANGLES * 3:
                    raise ValueError("Too many OBJ UV coordinates.")
                values = rest.split()
                if not 1 <= len(values) <= 3:
                    raise ValueError("Texture coordinates need one, two or three numeric values.")
                coords = _floats(rest, len(values), "UV coordinate", -10000, 10000)
                if len(coords) == 3 and coords[2] != 0:
                    raise ValueError("Volumetric texture coordinates are unsupported.")
                uvs.append([coords[0], coords[1] if len(coords) > 1 else 0.])
            elif token in {"o", "g"}:
                group = _name(rest, "Object/group name") if rest else name[:-4] or "Mesh"
            elif token == "usemtl":
                material = _name(rest, "Material name")
            elif token == "mtllib":
                references = [rest] if rest in material_hashes else rest.split()
                if not references:
                    raise ValueError("mtllib needs a material file name.")
                for reference in references:
                    reference = _filename(reference, ".mtl")
                    if reference not in material_hashes:
                        warn("Referenced MTL %s was not selected; its material properties are unavailable." % reference)
            elif token == "s":
                if rest in {"off", "0"}:
                    smooth = None
                elif rest == "on":
                    smooth = "1"
                elif _INTEGER.fullmatch(rest) and 1 <= int(rest) <= 2_147_483_647:
                    smooth = str(int(rest))
                else:
                    raise ValueError("Smoothing group must be off, on or a positive integer.")
            elif token == "f":
                fields = rest.split()
                if len(fields) > MAX_FACE_CORNERS:
                    raise ValueError("Faces support at most %d corners; triangulate the source first." % MAX_FACE_CORNERS)
                corners = [_corner(field, (len(vertices), len(uvs), len(normals))) for field in fields]
                triangles = _triangulate(corners, vertices)
                triangle_count += len(triangles)
                if triangle_count > MAX_TRIANGLES:
                    raise ValueError("An OBJ file supports at most %d triangles." % MAX_TRIANGLES)
                key = (group, material)
                if key not in parts:
                    if len(parts) >= MAX_PARTS:
                        raise ValueError("An OBJ import supports at most %d object/material parts." % MAX_PARTS)
                    parts[key] = []
                for triangle in triangles:
                    face_normal = _triangle_normal(*(vertices[c[0]] for c in triangle))
                    parts[key].append((triangle, smooth, face_normal))
                    if smooth:
                        for corner in triangle:
                            accum = smooth_normals[(corner[0], smooth)]
                            for i in range(3):
                                accum[i] += face_normal[i]
                polygon_count += 1
            else:
                raise ValueError("OBJ directive %s is unsupported. Export polygon mesh geometry only." % token[:50])
        except ValueError as error:
            raise ValueError("%s line %d: %s" % (name, line, error)) from error
    if not parts:
        raise ValueError("The OBJ file contains no polygon faces.")
    source = {"format": "wavefront-obj", "name": name, "sha256": hashlib.sha256(raw).hexdigest(),
              "materials": material_hashes, "up_axis": axis, "scale": scale}
    objects = []
    for (group, material), faces in parts.items():
        mesh = {"version": 1, "vertices": [], "triangles": [], "normals": [], "normal_indices": [], "uvs": [], "uv_indices": []}
        vertex_map, normal_map, uv_map = {}, {}, {}
        has_uv = any(corner[1] >= 0 for triangle, _, _ in faces for corner in triangle)
        for triangle, smoothing, face_normal in faces:
            positions, corner_normals, corner_uvs = [], [], []
            for vertex_index, uv_index, normal_index in triangle:
                if vertex_index not in vertex_map:
                    vertex_map[vertex_index] = len(mesh["vertices"])
                    mesh["vertices"].append(vertices[vertex_index])
                positions.append(vertex_map[vertex_index])
                normal = (normals[normal_index] if normal_index >= 0 else
                          _unit(smooth_normals[(vertex_index, smoothing)] if smoothing else face_normal, "Generated normal"))
                normal_key = tuple(round(v, 10) for v in normal)
                if normal_key not in normal_map:
                    normal_map[normal_key] = len(mesh["normals"])
                    mesh["normals"].append(list(normal_key))
                corner_normals.append(normal_map[normal_key])
                if has_uv:
                    if uv_index >= 0 and uv_index not in uv_map:
                        uv_map[uv_index] = len(mesh["uvs"])
                        mesh["uvs"].append(uvs[uv_index])
                    corner_uvs.append(uv_map[uv_index] if uv_index >= 0 else -1)
            mesh["triangles"].append(positions)
            mesh["normal_indices"].append(corner_normals)
            if has_uv:
                mesh["uv_indices"].append(corner_uvs)
        if has_uv and any(index < 0 for indices in mesh["uv_indices"] for index in indices):
            warn("Some face corners have no UV coordinates; their saved UV value is (0, 0).")
        if material and material not in materials:
            warn("Material %s has no supplied definition; that part uses the default material." % material)
        mesh["source"] = {**source, "group": group, "material": material}
        obj = {"id": "m" + uuid.uuid4().hex, "name": (group + (" · " + material if material else ""))[:120],
               "type": "mesh", "mesh": validate_mesh(mesh), "position": [0., 0., 0.], "rotation": [0., 0., 0.],
               "scale": [1., 1., 1.], "material": dict(materials.get(material, {"color": "#bcbcbc", "roughness": .45, "metallic": 0.})),
               "keyframes": []}
        objects.append(obj)
    validate_scene_geometry(objects)
    return {"objects": objects, "warnings": warnings, "source": source,
            "statistics": {"objects": len(objects), "source_vertices": len(vertices), "source_polygons": polygon_count,
                           "vertices": sum(len(o["mesh"]["vertices"]) for o in objects), "triangles": triangle_count,
                           "uv_corners": sum(sum(i >= 0 for i in face) for o in objects for face in o["mesh"]["uv_indices"]),
                           "normal_corners": triangle_count * 3,
                           "geometry_bytes": len(_json_bytes([o["mesh"] for o in objects]))}}

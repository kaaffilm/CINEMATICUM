"""Bounded, data-only calibrated camera import for CINEMATICUM.

No source image, image name, JSON field, or text path is opened. fSpy is read as
its documented v1 byte container. COLMAP input is the explicitly selected pair
of cameras.txt and images.txt strings, not a reconstruction directory.

Canonical cameras use a Z-up world, local +X right, +Y up, -Z forward, vertical
field of view in degrees, and roll in degrees about local +Z. Principal point
offsets are image fractions: shift_x=cx/W-.5 and shift_y=.5-cy/H. focal_ratio is
fx/fy. An explicit Y-up conversion is a right-handed +90-degree X rotation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import struct


MAX_FSPY_BYTES = 5 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_TEXT_BYTES = 3 * 1024 * 1024
MAX_CAMERAS = 128
MAX_OBSERVATIONS = 100_000
MAX_LINE_BYTES = 2 * 1024 * 1024
_INTEGER = re.compile(r"[+-]?\d{1,16}\Z")
_FLOAT = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a finite number." % label)
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or not low <= value <= high or integer and int(value) != value:
        raise ValueError("%s must be %sbetween %s and %s." % (
            label, "an integer " if integer else "", low, high))
    return int(value) if integer else float(value)


def _float_token(value, label, low=-1e12, high=1e12):
    if len(value) > 100 or not _FLOAT.fullmatch(value):
        raise ValueError("%s contains an invalid number." % label)
    return _number(float(value), label, low, high)


def _int_token(value, label, low=0, high=2**53 - 1):
    if not _INTEGER.fullmatch(value):
        raise ValueError("%s contains an invalid integer." % label)
    return _number(int(value), label, low, high, True)


def _mapping(value, label, allowed=None):
    if not isinstance(value, dict) or allowed is not None and set(value) - set(allowed):
        raise ValueError("%s has unsupported properties." % label)
    return value


def _name(value, default):
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip() or len(value) > 512 or any(ord(c) < 32 for c in value):
        raise ValueError("Camera source names must contain 1–512 printable characters.")
    return value.strip()


def _text(value, label, maximum):
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("%s must be UTF-8 text without NUL characters." % label)
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise ValueError("%s must be valid UTF-8 text." % label)
    if len(encoded) > maximum:
        raise ValueError("%s exceeds the %s MiB input limit." % (label, maximum // (1024 * 1024)))
    return encoded


def _strict_json(text):
    _text(text, "fSpy JSON", MAX_JSON_BYTES)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON member: %s." % key[:80])
            result[key] = value
        return result

    def constant(_):
        raise ValueError("fSpy JSON must contain only finite numbers.")

    try:
        value = json.loads(text[1:] if text.startswith("\ufeff") else text, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, RecursionError, OverflowError):
        raise ValueError("The fSpy camera document is not supported JSON.")
    pending, visited = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > 20000 or depth > 32:
            raise ValueError("The fSpy document exceeds the supported structure limit.")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("fSpy JSON must contain only finite numbers.")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return _mapping(value, "fSpy camera document")


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError("The imported camera has a degenerate orientation.")
    return [v / length for v in a]


def _axis(vector, up_axis):
    return list(vector) if up_axis == "Z" else [vector[0], -vector[2], vector[1]]


def _rotation(matrix):
    for i in range(3):
        for j in range(3):
            if abs(_dot(matrix[i], matrix[j]) - (1 if i == j else 0)) > 1e-5:
                raise ValueError("The camera transform must contain an orthonormal rotation, without scale or shear.")
    if abs(_dot(matrix[0], _cross(matrix[1], matrix[2])) - 1) > 1e-5:
        raise ValueError("The camera transform must be right-handed, without a reflection.")
    return matrix


def _transform(value, label):
    rows = _mapping(value, label, {"rows"}).get("rows")
    if not isinstance(rows, list) or len(rows) != 4 or any(not isinstance(row, list) or len(row) != 4 for row in rows):
        raise ValueError("%s must contain four rows of four numbers." % label)
    result = [[_number(v, label, -1e9, 1e9) for v in row] for row in rows]
    if any(abs(result[3][i] - (1 if i == 3 else 0)) > 1e-9 for i in range(4)):
        raise ValueError("%s must be an affine transform." % label)
    _rotation([row[:3] for row in result[:3]])
    return result


def _dimensions(width, height, output_width, output_height):
    width = _number(width, "Source camera width", 1, 65536, True)
    height = _number(height, "Source camera height", 1, 65536, True)
    output_width = _number(output_width, "Project width", 16, 8192, True)
    output_height = _number(output_height, "Project height", 16, 8192, True)
    # Uniform scaling preserves all normalized calibration values; cropping,
    # letterboxing, and changing the image aspect require a different K matrix.
    if abs(width * output_height / (height * output_width) - 1) > 1e-6:
        raise ValueError("The calibrated image aspect (%s × %s) differs from the project (%s × %s). "
                         "Use a project with the same aspect before importing; no crop or stretch is assumed." % (
                             width, height, output_width, output_height))
    return width, height


def _camera(position, right, up, backward, width, height, fx, fy, cx, cy, scale, up_axis):
    # Verify the entire orientation, including signs, before converting to the
    # scene's target + roll representation. No implicit world-up is imposed.
    _rotation([[right[i], up[i], backward[i]] for i in range(3)])
    position = [_number(v * scale, "Scaled camera position", -1000, 1000) for v in _axis(position, up_axis)]
    right, up, backward = (_unit(_axis(v, up_axis)) for v in (right, up, backward))
    reference_up = [0., 1., 0.] if abs(backward[2]) > .999 else [0., 0., 1.]
    base_right = _unit(_cross(reference_up, backward))
    base_up = _cross(backward, base_right)
    roll = math.degrees(math.atan2(_dot(right, base_up), _dot(right, base_right)))
    target = [_number(position[i] - backward[i], "Camera target", -1000, 1000) for i in range(3)]
    fov = _number(math.degrees(2 * math.atan(height / (2 * fy))), "Imported vertical field of view", 10, 100)
    shift_x = _number(cx / width - .5, "Imported horizontal principal offset", -2, 2)
    shift_y = _number(.5 - cy / height, "Imported vertical principal offset", -2, 2)
    ratio = _number(fx / fy, "Imported focal ratio", .25, 4)
    return {"position": position, "target": target, "fov": fov, "roll": roll,
            "shift_x": shift_x, "shift_y": shift_y, "focal_ratio": ratio, "keyframes": []}


def _fspy(payload, width, height, scale, up_axis):
    binary = payload["format"] == "fspy"
    name = _name(payload.get("name"), "Imported fSpy camera")
    embedded_image_bytes = 0
    if binary:
        encoded = payload.get("data_base64")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_FSPY_BYTES + 2) // 3):
            raise ValueError("The fSpy file exceeds the 5 MiB limit. Export camera JSON for a larger project.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The fSpy upload contains invalid base64 data.")
        if len(data) < 16 or len(data) > MAX_FSPY_BYTES or data[:4] != b"fspy":
            raise ValueError("Choose a valid fSpy v1 project file, up to 5 MiB.")
        version, state_size, embedded_image_bytes = struct.unpack("<III", data[4:16])
        if version != 1:
            raise ValueError("Only the documented fSpy v1 container is supported.")
        if not 1 <= state_size <= MAX_JSON_BYTES or len(data) != 16 + state_size + embedded_image_bytes:
            raise ValueError("The fSpy container lengths do not match its complete file data.")
        try:
            text = data[16:16 + state_size].decode("utf-8")
        except UnicodeError:
            raise ValueError("The fSpy camera state must be valid UTF-8 JSON.")
    else:
        text = payload.get("text")
        data = _text(text, "fSpy JSON", MAX_JSON_BYTES)
    state = _strict_json(text)
    parameters = state.get("cameraParameters") if "cameraParameters" in state else state
    if parameters is None:
        raise ValueError("This fSpy project has no solved camera parameters. Resolve the vanishing points before importing.")
    params = _mapping(parameters, "fSpy camera parameters")
    source_width, source_height = _dimensions(params.get("imageWidth"), params.get("imageHeight"), width, height)
    transform = _transform(params.get("cameraTransform"), "fSpy cameraTransform")
    if "viewTransform" in params:
        view = _transform(params["viewTransform"], "fSpy viewTransform")
        for i in range(4):
            for j in range(4):
                if abs(sum(view[i][k] * transform[k][j] for k in range(4)) - (1 if i == j else 0)) > 1e-4:
                    raise ValueError("The fSpy view and camera transforms are not mutually inverse.")
    principal = _mapping(params.get("principalPoint"), "fSpy principal point", {"x", "y"})
    px = _number(principal.get("x"), "fSpy principal point X", -20, 20)
    py = _number(principal.get("y"), "fSpy principal point Y", -20, 20)
    # The upstream projection operates in ImagePlane coordinates whose largest
    # half-extent is 1. Its field name horizontalFieldOfView does not change for
    # portrait images. Convert that actual projection, not the misleading name.
    fov_major = _number(params.get("horizontalFieldOfView"), "fSpy normalized field of view (radians)", .001, math.pi - .001)
    normalized_focal = 1 / math.tan(fov_major / 2)
    if "relativeFocalLength" in params:
        supplied = _number(params["relativeFocalLength"], "fSpy relative focal length", .0001, 10000)
        if abs(supplied / normalized_focal - 1) > 1e-5:
            raise ValueError("The fSpy focal length and field of view disagree.")
    longest = max(source_width, source_height)
    focal = .5 * longest * normalized_focal
    cx, cy = source_width / 2 + px * longest / 2, source_height / 2 - py * longest / 2
    camera = _camera([row[3] for row in transform[:3]],
                     [row[0] for row in transform[:3]], [row[1] for row in transform[:3]],
                     [row[2] for row in transform[:3]], source_width, source_height,
                     focal, focal, cx, cy, scale, up_axis)
    warnings = ["The camera replaces the current camera and its animation keys as one undoable edit."]
    if embedded_image_bytes:
        warnings.append("The embedded fSpy photograph is not imported or decoded; import your reference media separately.")
    calibration = state.get("calibrationSettingsBase", {})
    _mapping(calibration, "fSpy calibration settings")
    reference_axis = calibration.get("referenceDistanceAxis")
    if reference_axis:
        unit = calibration.get("referenceDistanceUnit", "unspecified")
        if not isinstance(unit, str) or unit not in {"Meters", "Centimeters", "Millimeters", "Feet", "Inches", "None", "unspecified"}:
            unit = "unspecified"
        warnings.append("fSpy reference units: %s. The chosen import scale is the sole conversion to scene units." % unit)
    else:
        warnings.append("This fSpy solve has no reference distance. Camera translation uses arbitrary source units times the chosen scale.")
    source = {"format": payload["format"], "sha256": hashlib.sha256(data).hexdigest(), "name": name,
              "up_axis": up_axis, "scale": scale, "fx": focal, "fy": focal, "cx": cx, "cy": cy,
              "embedded_image_bytes": embedded_image_bytes}
    return {"format": payload["format"], "cameras": [{"id": "fspy", "name": name, "camera": camera,
            "width": source_width, "height": source_height, "source": source}], "warnings": warnings,
            "statistics": {"cameras": 1, "images": 1, "observations": 0}}


def _lines(text, label):
    data = _text(text, label, MAX_TEXT_BYTES)
    lines = (text[1:] if text.startswith("\ufeff") else text).splitlines()
    if len(lines) > MAX_OBSERVATIONS * 3 + MAX_CAMERAS * 4:
        raise ValueError("%s contains too many lines." % label)
    for line in lines:
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise ValueError("%s contains an oversized line." % label)
    return data, lines


def _colmap(payload, width, height, scale, up_axis):
    camera_data, camera_lines = _lines(payload.get("cameras_text"), "COLMAP cameras.txt")
    image_data, image_lines = _lines(payload.get("images_text"), "COLMAP images.txt")
    intrinsics = {}
    for line in camera_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        if len(tokens) < 5:
            raise ValueError("A COLMAP camera record is incomplete.")
        camera_id = _int_token(tokens[0], "COLMAP camera ID", 1)
        if camera_id in intrinsics:
            raise ValueError("COLMAP camera IDs must be unique.")
        if len(intrinsics) >= MAX_CAMERAS:
            raise ValueError("This import supports at most 128 cameras and 128 registered images.")
        model = tokens[1]
        if model not in {"SIMPLE_PINHOLE", "PINHOLE"}:
            raise ValueError("COLMAP model %s is not a distortion-free supported camera. "
                             "Undistort the source reconstruction and export PINHOLE or SIMPLE_PINHOLE; "
                             "distortion, fisheye and skew are never discarded." % model[:80])
        expected = 7 if model == "SIMPLE_PINHOLE" else 8
        if len(tokens) != expected:
            raise ValueError("COLMAP %s has the wrong number of intrinsic parameters." % model)
        w, h = _dimensions(_int_token(tokens[2], "COLMAP width", 1, 65536),
                           _int_token(tokens[3], "COLMAP height", 1, 65536), width, height)
        values = [_float_token(v, "COLMAP intrinsic parameter") for v in tokens[4:]]
        fx, fy, cx, cy = ([values[0], values[0], values[1], values[2]] if model == "SIMPLE_PINHOLE" else values)
        _number(fx, "COLMAP fx", .001, 1e8)
        _number(fy, "COLMAP fy", .001, 1e8)
        intrinsics[camera_id] = (w, h, fx, fy, cx, cy, model)
    if not intrinsics:
        raise ValueError("COLMAP cameras.txt contains no camera records.")
    result, identifiers, observations, index = [], set(), 0, 0
    while index < len(image_lines):
        line = image_lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        # The remaining name is data. Whitespace in names is legal upstream.
        tokens = line.split(maxsplit=9)
        if len(tokens) != 10:
            raise ValueError("A COLMAP image pose requires ID, quaternion, translation, camera ID and name.")
        image_id = _int_token(tokens[0], "COLMAP image ID", 1)
        if image_id in identifiers:
            raise ValueError("COLMAP image IDs must be unique.")
        identifiers.add(image_id)
        if len(identifiers) > MAX_CAMERAS:
            raise ValueError("This import supports at most 128 registered camera poses.")
        q = [_float_token(v, "COLMAP Hamilton quaternion", -2, 2) for v in tokens[1:5]]
        length = math.sqrt(_dot(q, q))
        if abs(length - 1) > .001:
            raise ValueError("COLMAP camera quaternions must be unit Hamilton quaternions (w, x, y, z).")
        qw, qx, qy, qz = [v / length for v in q]
        rotation = [[1 - 2 * (qy*qy + qz*qz), 2 * (qx*qy - qw*qz), 2 * (qx*qz + qw*qy)],
                    [2 * (qx*qy + qw*qz), 1 - 2 * (qx*qx + qz*qz), 2 * (qy*qz - qw*qx)],
                    [2 * (qx*qz - qw*qy), 2 * (qy*qz + qw*qx), 1 - 2 * (qx*qx + qy*qy)]]
        translation = [_float_token(v, "COLMAP translation", -1e9, 1e9) for v in tokens[5:8]]
        camera_id = _int_token(tokens[8], "COLMAP image camera ID", 1)
        if camera_id not in intrinsics:
            raise ValueError("A COLMAP image references a camera absent from cameras.txt.")
        name = _name(tokens[9], "COLMAP camera")
        if index >= len(image_lines):
            raise ValueError("Each COLMAP image pose requires a following POINTS2D line, which may be empty.")
        points = image_lines[index].split()
        index += 1
        if len(points) % 3:
            raise ValueError("COLMAP POINTS2D records must contain X, Y, POINT3D_ID triples.")
        observations += len(points) // 3
        if observations > MAX_OBSERVATIONS:
            raise ValueError("The COLMAP input exceeds 100,000 point observations.")
        for offset in range(0, len(points), 3):
            _float_token(points[offset], "COLMAP observed X")
            _float_token(points[offset+1], "COLMAP observed Y")
            _int_token(points[offset+2], "COLMAP observed point ID", -1)
        # COLMAP R,t are world->camera with X-right/Y-down/Z-forward.
        # R^T columns equal R rows; convert camera Y/Z signs, preserving world.
        center = [-sum(rotation[j][i] * translation[j] for j in range(3)) for i in range(3)]
        w, h, fx, fy, cx, cy, model = intrinsics[camera_id]
        camera = _camera(center, rotation[0], [-v for v in rotation[1]], [-v for v in rotation[2]],
                         w, h, fx, fy, cx, cy, scale, up_axis)
        source = {"format": "colmap", "camera_id": camera_id, "image_id": image_id, "model": model,
                  "up_axis": up_axis, "scale": scale, "fx": fx, "fy": fy, "cx": cx, "cy": cy,
                  "cameras_sha256": hashlib.sha256(camera_data).hexdigest(),
                  "images_sha256": hashlib.sha256(image_data).hexdigest()}
        result.append({"id": str(image_id), "name": name, "camera": camera, "width": w, "height": h, "source": source})
    if not result:
        raise ValueError("COLMAP images.txt contains no registered camera poses.")
    return {"format": "colmap", "cameras": result,
            "warnings": ["COLMAP world scale and up direction are not inferred. Apply the same scale and up-axis choice to imported geometry.",
                         "Select one registered image pose. It replaces the scene camera and its keys; image order is not assumed to be animation timing.",
                         "Image paths and point observations are not opened or imported. This operation imports solved camera data; it does not reconstruct footage."],
            "statistics": {"cameras": len(intrinsics), "images": len(result), "observations": observations}}


def import_camera(payload, width=1280, height=720):
    """Return reviewable canonical camera candidates without changing a scene.

    format=fspy: name, data_base64; format=fspy_json: name, text;
    format=colmap: cameras_text, images_text. All accept explicit scale/up_axis.
    Call the scene validator when applying/rendering. No I/O is performed here.
    """
    payload = _mapping(payload, "Camera import")
    kind = payload.get("format")
    formats = {"fspy": {"name", "data_base64"}, "fspy_json": {"name", "text"},
               "colmap": {"cameras_text", "images_text"}}
    if not isinstance(kind, str) or kind not in formats:
        raise ValueError("Choose fspy, fspy_json, or colmap camera import.")
    _mapping(payload, "Camera import", {"format", "scale", "up_axis"} | formats[kind])
    scale = _number(payload.get("scale", 1), "Camera translation scale", .000001, 1000)
    up_axis = payload.get("up_axis", "Z")
    if not isinstance(up_axis, str) or up_axis not in {"Z", "Y"}:
        raise ValueError("Choose Z-up or Y-up source world coordinates.")
    return (_colmap if kind == "colmap" else _fspy)(payload, width, height, scale, up_axis)


def brown_distort_point(x, y, coefficients):
    """Forward Brown-Conrady mapping of normalized camera coordinates.

    Five coefficients are [k1,k2,p1,p2,k3], with x-right/y-down. These are not
    Lensfun profile coefficients. This numerical helper does not apply a lens
    effect to footage and does not admit distorted cameras to the scene.
    """
    x, y = _number(x, "Normalized X", -10, 10), _number(y, "Normalized Y", -10, 10)
    if not isinstance(coefficients, (list, tuple)) or len(coefficients) != 5:
        raise ValueError("Brown distortion needs [k1, k2, p1, p2, k3].")
    k1, k2, p1, p2, k3 = [_number(v, "Brown coefficient", -5, 5) for v in coefficients]
    r2 = x*x + y*y
    radial = 1 + r2 * (k1 + r2 * (k2 + r2 * k3))
    return [x * radial + 2*p1*x*y + p2*(r2 + 2*x*x),
            y * radial + p1*(r2 + 2*y*y) + 2*p2*x*y]


def brown_undistort_point(xd, yd, coefficients):
    """Bounded Newton inverse; reject folds/singularities/non-convergence.

    An inverse is only returned when forward reprojection meets 1e-10 residual.
    No global bijection is promised for arbitrary polynomial coefficients.
    """
    brown_distort_point(xd, yd, coefficients)  # validates the input domain
    x, y = float(xd), float(yd)
    k1, k2, p1, p2, k3 = coefficients
    for _ in range(32):
        out = brown_distort_point(x, y, coefficients)
        ex, ey = out[0] - xd, out[1] - yd
        r2 = x*x + y*y
        radial = 1 + r2*(k1 + r2*(k2 + r2*k3))
        slope = k1 + 2*k2*r2 + 3*k3*r2*r2
        a = radial + 2*x*x*slope + 2*p1*y + 6*p2*x
        b = 2*x*y*slope + 2*p1*x + 2*p2*y
        d = radial + 2*y*y*slope + 6*p1*y + 2*p2*x
        determinant = a*d - b*b
        if not math.isfinite(determinant) or determinant <= 1e-12 or a <= 0 or d <= 0:
            raise ValueError("The lens inverse reaches a fold or singular mapping.")
        error = math.hypot(ex, ey)
        if error <= 1e-10:
            return [x, y]
        dx, dy = (d*ex - b*ey)/determinant, (-b*ex + a*ey)/determinant
        improved = False
        for attempt in range(12):
            step = 2.0 ** -attempt
            nx, ny = x - step*dx, y - step*dy
            if abs(nx) > 10 or abs(ny) > 10:
                continue
            trial = brown_distort_point(nx, ny, coefficients)
            if math.hypot(trial[0] - xd, trial[1] - yd) < error:
                x, y, improved = nx, ny, True
                break
        if not improved:
            break
    raise ValueError("The lens inverse did not converge within the supported domain.")

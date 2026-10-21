"""Project-owned LUTs and explicit input-to-Rec.709 SDR colour processing.

This module deliberately does not infer a camera colourspace, demosaic RAW,
perform HDR mastering, or claim an ACES display rendering transform. Transfer
functions and primary/white adaptation are evaluated in floating point before
the existing SDR compositor. Imported LUTs operate after that input transform.
Implementation is original; the pinned mathematical/source references and
unsupported cases are recorded in research/color-science.md.
"""
import hashlib
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


MAX_CUBE_BYTES = 24 * 1024 * 1024
MAX_1D_SIZE = 65536
MAX_3D_SIZE = 65
MAX_PROJECT_LUTS = 128
TRANSFERS = ("rec709", "srgb", "linear", "logc3_ei800")
WHITEPOINTS = {"D65": (0.3127, 0.3290), "D60": (0.32168, 0.33767),
               "D50": (0.3457, 0.3585), "A": (0.44757, 0.40745)}
PRIMARIES = {
    "rec709": (((0.64, 0.33), (0.30, 0.60), (0.15, 0.06)), WHITEPOINTS["D65"]),
    "rec2020": (((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)), WHITEPOINTS["D65"]),
    "acescg": (((0.713, 0.293), (0.165, 0.830), (0.128, 0.044)), WHITEPOINTS["D60"]),
    "arri_wide_gamut3": (((0.6840, 0.3130), (0.2210, 0.8480), (0.0861, -0.1020)), WHITEPOINTS["D65"]),
}
BRADFORD = ((0.8951, 0.2664, -0.1614), (-0.7502, 1.7135, 0.0367),
            (0.0389, -0.0685, 1.0296))
_HEX = re.compile(r"^[0-9a-f]{64}$")
_FLOAT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _finite(value, name="number", bound=1e6):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a finite number" % name)
    value = float(value)
    if not math.isfinite(value) or abs(value) > bound:
        raise ValueError("%s must be finite and within ±%g" % (name, bound))
    return 0.0 if value == 0 else value


def _triple(tokens, line):
    if len(tokens) != 3 or any(not _FLOAT.fullmatch(t) for t in tokens):
        raise ValueError("Cube line %d requires exactly three finite decimal numbers" % line)
    return tuple(_finite(float(t), "Cube line %d" % line) for t in tokens)


def _fmt(value):
    return format(0.0 if value == 0 else value, ".17g")


@dataclass(frozen=True)
class CubeLUT:
    dimension: int
    size: int
    domain_min: tuple
    domain_max: tuple
    values: tuple
    title: str = "Untitled LUT"

    def text(self, unit_domain=False):
        """Deterministic canonical identity; comments and source formatting vanish."""
        low = (0.0, 0.0, 0.0) if unit_domain else self.domain_min
        high = (1.0, 1.0, 1.0) if unit_domain else self.domain_max
        lines = ['TITLE "%s"' % self.title, "LUT_%dD_SIZE %d" % (self.dimension, self.size),
                 "DOMAIN_MIN " + " ".join(map(_fmt, low)),
                 "DOMAIN_MAX " + " ".join(map(_fmt, high))]
        lines.extend(" ".join(map(_fmt, row)) for row in self.values)
        return "\n".join(lines) + "\n"

    @property
    def sha256(self):
        return hashlib.sha256(self.text().encode("utf-8")).hexdigest()

    def descriptor(self):
        return {"sha256": self.sha256, "title": self.title, "dimension": self.dimension,
                "size": self.size, "domain_min": list(self.domain_min),
                "domain_max": list(self.domain_max), "rows": len(self.values)}


def parse_cube(text):
    """Strict Iridas .cube subset: one 3-channel 1D OR one 3D table.

    Red changes fastest in 3D rows. Arbitrary per-channel finite domains are
    supported. Endpoint clamping is explicit; output values may be outside 0–1.
    Combined Resolve shapers, range directives, includes and unknown headers
    are rejected rather than silently changing their meaning.
    """
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_CUBE_BYTES:
        raise ValueError("Cube text must be UTF-8 text of at most 24 MiB")
    if "\x00" in text:
        raise ValueError("Cube text contains a NUL character")
    text = text.lstrip("\ufeff")
    title, dimension, size = "Untitled LUT", None, None
    low, high, rows, headers = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), [], set()
    for line_number, raw in enumerate(text.splitlines(), 1):
        if len(raw) > 4096:
            raise ValueError("Cube line %d is too long" % line_number)
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # A title may contain #. Its complete quoted form is parsed separately.
        if line.startswith("TITLE"):
            match = re.fullmatch(r'TITLE\s+"([^"\\\x00-\x1f]{1,200})"\s*(?:#.*)?', line)
            if not match or "TITLE" in headers or rows:
                raise ValueError("Cube TITLE must be a unique quoted title before table data")
            title = match.group(1).strip()
            if not title:
                raise ValueError("Cube TITLE must not be blank")
            headers.add("TITLE")
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        key = tokens[0]
        if key in {"LUT_1D_SIZE", "LUT_3D_SIZE", "DOMAIN_MIN", "DOMAIN_MAX"}:
            if rows or key in headers:
                raise ValueError("Cube %s must occur once, before table data" % key)
            headers.add(key)
            if key.startswith("LUT_"):
                if dimension is not None:
                    raise ValueError("Combined 1D+3D shaper LUTs are not supported; import separate tables")
                dimension = 1 if key == "LUT_1D_SIZE" else 3
                limit = MAX_1D_SIZE if dimension == 1 else MAX_3D_SIZE
                if len(tokens) != 2 or not re.fullmatch(r"\d+", tokens[1]):
                    raise ValueError("Cube size must be an integer")
                size = int(tokens[1])
                if not 2 <= size <= limit:
                    raise ValueError("Cube %dD size must be between 2 and %d" % (dimension, limit))
            elif key == "DOMAIN_MIN":
                low = _triple(tokens[1:], line_number)
            else:
                high = _triple(tokens[1:], line_number)
            continue
        if dimension is None:
            raise ValueError("Declare LUT_1D_SIZE or LUT_3D_SIZE before table rows")
        row = _triple(tokens, line_number)
        rows.append(row)
        if len(rows) > size ** dimension:
            raise ValueError("Cube has more rows than its declared size")
    if dimension is None or len(rows) != size ** dimension:
        raise ValueError("Cube table row count must exactly equal its declared size")
    if any(b - a < 1e-9 for a, b in zip(low, high)):
        raise ValueError("Every Cube DOMAIN_MAX must exceed DOMAIN_MIN by at least 1e-9")
    return CubeLUT(dimension, size, low, high, tuple(rows), title)


def sample_lut(lut, rgb, interpolation=None):
    """Independent CPU reference evaluator, including tetrahedral ordering."""
    if not isinstance(lut, CubeLUT):
        raise ValueError("Expected a parsed CubeLUT")
    if len(rgb) != 3:
        raise ValueError("RGB must contain three channels")
    interpolation = interpolation or ("linear" if lut.dimension == 1 else "tetrahedral")
    allowed = ("linear", "nearest") if lut.dimension == 1 else ("nearest", "trilinear", "tetrahedral")
    if interpolation not in allowed:
        raise ValueError("Interpolation is unsupported for this LUT dimension")
    points = [min(1.0, max(0.0, (_finite(c) - a) / (b - a))) * (lut.size - 1)
              for c, a, b in zip(rgb, lut.domain_min, lut.domain_max)]
    indices = [int(math.floor(x)) for x in points]
    fractions = [x - i for x, i in zip(points, indices)]
    if lut.dimension == 1:
        result = []
        for channel, (index, fraction) in enumerate(zip(indices, fractions)):
            if interpolation == "nearest":
                result.append(lut.values[min(lut.size - 1, int(math.floor(points[channel] + 0.5)))][channel])
            else:
                a = lut.values[index][channel]
                b = lut.values[min(index + 1, lut.size - 1)][channel]
                result.append(a + fraction * (b - a))
        return tuple(result)

    def vertex(offset):
        r, g, b = [min(lut.size - 1, indices[c] + offset[c]) for c in range(3)]
        return lut.values[r + lut.size * (g + lut.size * b)]

    if interpolation == "nearest":
        return vertex([int(x >= 0.5) for x in fractions])
    if interpolation == "trilinear":
        result = [0.0, 0.0, 0.0]
        for b in (0, 1):
            for g in (0, 1):
                for r in (0, 1):
                    offset = (r, g, b)
                    weight = math.prod(fractions[c] if offset[c] else 1 - fractions[c] for c in range(3))
                    for c, value in enumerate(vertex(offset)):
                        result[c] += weight * value
        return tuple(result)
    # Sort fractional axes into the containing simplex; ties choose a stable
    # boundary whose adjacent tetrahedra give the same continuous value.
    order = sorted(range(3), key=lambda c: (-fractions[c], c))
    offsets, current = [(0, 0, 0)], [0, 0, 0]
    for c in order:
        current = list(current)
        current[c] = 1
        offsets.append(tuple(current))
    f0, f1, f2 = [fractions[c] for c in order]
    weights = (1 - f0, f0 - f1, f1 - f2, f2)
    vertices = [vertex(offset) for offset in offsets]
    return tuple(sum(weights[j] * vertices[j][c] for j in range(4)) for c in range(3))


def _lut_directory(project_dir, create=False):
    root = Path(project_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project directory is missing")
    directory = root
    for name in ("color", "luts"):
        directory = directory / name
        if directory.is_symlink():
            raise ValueError("Project LUT directories must not be symbolic links")
        if create:
            directory.mkdir(exist_ok=True)
        if directory.exists() and not directory.is_dir():
            raise ValueError("Project LUT storage is not a directory")
        if not directory.resolve().is_relative_to(root):
            raise ValueError("Project LUT storage escapes the project")
    return directory


def _read_lut(path, expected_sha):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Project LUT is missing or is a symbolic link")
    if path.stat().st_size > MAX_CUBE_BYTES:
        raise ValueError("Project LUT exceeds the size limit")
    # O_NOFOLLOW prevents the last pathname component being swapped to a link
    # after the check. Parent directories were rejected above as well.
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        payload = stream.read(MAX_CUBE_BYTES + 1)
    if len(payload) > MAX_CUBE_BYTES or hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError("Project LUT content no longer matches its SHA-256 identity")
    try:
        lut = parse_cube(payload.decode("utf-8"))
    except UnicodeError as error:
        raise ValueError("Project LUT must be UTF-8") from error
    if lut.sha256 != expected_sha:
        raise ValueError("Project LUT is not canonical")
    return lut


def load_lut(project_dir, sha256):
    if not isinstance(sha256, str) or not _HEX.fullmatch(sha256):
        raise ValueError("LUT identity must be a lowercase SHA-256 digest")
    return _read_lut(_lut_directory(project_dir) / (sha256 + ".cube"), sha256)


def import_cube(text, project_dir):
    lut = parse_cube(text)
    directory = _lut_directory(project_dir, create=True)
    sha = lut.sha256
    destination = directory / (sha + ".cube")
    if destination.exists() or destination.is_symlink():
        return _read_lut(destination, sha).descriptor()
    if len(list(directory.glob("*.cube"))) >= MAX_PROJECT_LUTS:
        raise ValueError("A project may contain at most 128 imported LUTs")
    fd, name = tempfile.mkstemp(prefix=".lut-", dir=str(directory))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(lut.text().encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        # Linking publishes a complete file without replacing an existing
        # content address. Concurrent imports of identical content are safe.
        try:
            os.link(name, str(destination))
        except FileExistsError:
            _read_lut(destination, sha)
    finally:
        Path(name).unlink(missing_ok=True)
    return load_lut(project_dir, sha).descriptor()


def list_luts(project_dir):
    directory = _lut_directory(project_dir)
    if not directory.exists():
        return []
    paths = sorted(directory.glob("*.cube"))
    if len(paths) > MAX_PROJECT_LUTS:
        raise ValueError("Project exceeds the 128 LUT limit")
    values = []
    for path in paths:
        if not _HEX.fullmatch(path.stem):
            raise ValueError("Unexpected file in project LUT storage")
        values.append(_read_lut(path, path.stem).descriptor())
    return sorted(values, key=lambda d: (d["title"].casefold(), d["sha256"]))


def _matmul(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def _matvec(a, b):
    return tuple(sum(row[i] * b[i] for i in range(3)) for row in a)


def _inverse(a):
    determinant = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                   - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                   + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if abs(determinant) < 1e-12:
        raise ValueError("Singular colour matrix")
    result = []
    for r in range(3):
        row = []
        for c in range(3):
            rows, cols = [i for i in range(3) if i != c], [i for i in range(3) if i != r]
            minor = a[rows[0]][cols[0]] * a[rows[1]][cols[1]] - a[rows[0]][cols[1]] * a[rows[1]][cols[0]]
            row.append(((-1) ** (r + c)) * minor / determinant)
        result.append(tuple(row))
    return tuple(result)


def _white(value, name):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("%s must contain CIE x and y" % name)
    x, y = [_finite(v, name, 1) for v in value]
    if x <= 0.001 or y <= 0.001 or x + y >= 0.999:
        raise ValueError("%s must be an interior physical chromaticity" % name)
    return (x, y)


def xy_to_xyz(xy):
    x, y = _white(xy, "Whitepoint")
    return (x / y, 1.0, (1 - x - y) / y)


def chromatic_adaptation_matrix(source_white, target_white):
    source, target = xy_to_xyz(source_white), xy_to_xyz(target_white)
    if tuple(source_white) == tuple(target_white):
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    cones_a, cones_b = _matvec(BRADFORD, source), _matvec(BRADFORD, target)
    if any(v <= 1e-6 for v in cones_a + cones_b):
        raise ValueError("Whitepoints are outside the stable Bradford adaptation domain")
    scales = [cones_b[i] / cones_a[i] for i in range(3)]
    if any(not 1 / 64 <= scale <= 64 for scale in scales):
        raise ValueError("Whitepoint adaptation is too extreme")
    diagonal = tuple(tuple(scales[r] if r == c else 0.0 for c in range(3)) for r in range(3))
    return _matmul(_matmul(_inverse(BRADFORD), diagonal), BRADFORD)


def rgb_to_xyz_matrix(primaries="rec709"):
    if primaries not in PRIMARIES:
        raise ValueError("Unsupported RGB primaries")
    points, white = PRIMARIES[primaries]
    columns = [(x / y, 1.0, (1 - x - y) / y) for x, y in points]
    basis = tuple(tuple(columns[c][r] for c in range(3)) for r in range(3))
    scales = _matvec(_inverse(basis), xy_to_xyz(white))
    return tuple(tuple(basis[r][c] * scales[c] for c in range(3)) for r in range(3))


def decode_transfer(value, transfer):
    v = _finite(value)
    if transfer == "linear":
        return v
    if transfer == "srgb":
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    if transfer == "rec709":
        return v / 4.5 if v < 1.099 * 0.018 ** 0.45 - 0.099 else ((v + 0.099) / 1.099) ** (1 / 0.45)
    if transfer == "logc3_ei800":
        cut, a, b, c, d, e, f = 0.010591, 5.555556, 0.052272, 0.247190, 0.385537, 5.367655, 0.092809
        if v > 3:
            raise ValueError("LogC3 input exceeds the supported numerical domain")
        return (10 ** ((v - d) / c) - b) / a if v > e * cut + f else (v - f) / e
    raise ValueError("Unsupported transfer function")


def encode_transfer(value, transfer):
    v = _finite(value)
    if transfer == "linear":
        return v
    if transfer == "srgb":
        return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    if transfer == "rec709":
        return 4.5 * v if v < 0.018 else 1.099 * v ** 0.45 - 0.099
    if transfer == "logc3_ei800":
        cut, a, b, c, d, e, f = 0.010591, 5.555556, 0.052272, 0.247190, 0.385537, 5.367655, 0.092809
        return c * math.log10(a * v + b) + d if v > cut else e * v + f
    raise ValueError("Unsupported transfer function")


def validate_pipeline(value, project_dir=None):
    if value is None:
        return None
    fields = {"version", "enabled", "input_transfer", "input_primaries", "source_white", "target_white", "lut"}
    if not isinstance(value, dict) or set(value) - fields or value.get("version") != 1 or isinstance(value.get("version"), bool):
        raise ValueError("Unsupported colour pipeline; expected version 1 and known fields")
    transfer = value.get("input_transfer", "rec709")
    primaries = value.get("input_primaries", "rec709")
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool) or not isinstance(transfer, str) or not isinstance(primaries, str) or transfer not in TRANSFERS or primaries not in PRIMARIES:
        raise ValueError("Invalid input colourspace or pipeline enable state")
    source = _white(value.get("source_white", PRIMARIES[primaries][1]), "Source white")
    target = _white(value.get("target_white", WHITEPOINTS["D65"]), "Target white")
    chromatic_adaptation_matrix(source, target)
    result = {"version": 1, "enabled": enabled, "input_transfer": transfer,
              "input_primaries": primaries, "source_white": list(source),
              "target_white": list(target), "lut": None}
    reference = value.get("lut")
    if reference is not None:
        if not isinstance(reference, dict) or set(reference) != {"sha256", "interpolation"}:
            raise ValueError("LUT reference requires only SHA-256 and interpolation")
        sha, interpolation = reference.get("sha256"), reference.get("interpolation")
        if not isinstance(sha, str) or not _HEX.fullmatch(sha):
            raise ValueError("LUT identity must be a lowercase SHA-256 digest")
        if interpolation not in ("nearest", "linear", "trilinear", "tetrahedral"):
            raise ValueError("Unsupported LUT interpolation")
        if project_dir is not None:
            lut = load_lut(project_dir, sha)
            allowed = ("linear", "nearest") if lut.dimension == 1 else ("nearest", "trilinear", "tetrahedral")
            if interpolation not in allowed:
                raise ValueError("Interpolation is unsupported for this LUT dimension")
        result["lut"] = {"sha256": sha, "interpolation": interpolation}
    return result


def input_matrix(pipeline):
    adaptation = chromatic_adaptation_matrix(pipeline["source_white"], pipeline["target_white"])
    return _matmul(_inverse(rgb_to_xyz_matrix("rec709")),
                   _matmul(adaptation, rgb_to_xyz_matrix(pipeline["input_primaries"])))


def transform_rgb(rgb, pipeline, lut=None):
    """Unclipped float CPU reference, with optional final LUT endpoint clamping."""
    p = validate_pipeline(pipeline)
    if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
        raise ValueError("RGB must contain three channels")
    rgb = tuple(_finite(c) for c in rgb)
    if p is None or not p["enabled"]:
        return rgb
    conversion = p["input_transfer"] != "rec709" or p["input_primaries"] != "rec709" or p["source_white"] != p["target_white"]
    output = rgb
    if conversion:
        linear = tuple(decode_transfer(c, p["input_transfer"]) for c in rgb)
        converted = _matvec(input_matrix(p), linear)
        output = tuple(encode_transfer(c, "rec709") for c in converted)
    if p["lut"] is not None:
        if lut is None or lut.sha256 != p["lut"]["sha256"]:
            raise ValueError("The reference evaluator requires the matching project LUT")
        output = sample_lut(lut, output, p["lut"]["interpolation"])
    return output


def _decode_expression(v, transfer):
    if transfer == "linear":
        return v
    if transfer == "srgb":
        return "if(lte(%s,0.04045),(%s)/12.92,pow(((%s)+0.055)/1.055,2.4))" % (v, v, v)
    if transfer == "rec709":
        return "if(lt(%s,0.08124794403514046),(%s)/4.5,pow(((%s)+0.099)/1.099,1/0.45))" % (v, v, v)
    return "if(gt(%s,0.149657834105),(pow(10,((%s)-0.385537)/0.247190)-0.052272)/5.555556,((%s)-0.092809)/5.367655)" % (v, v, v)


def _geq(expressions):
    return "geq=" + ":".join("%s='%s'" % (c, e) for c, e in zip("rgb", expressions)) + ":a='alpha(X,Y)':interpolation=nearest"


def _filter_path(path):
    # Escape the option grammar, then the enclosing filtergraph grammar.
    # These are FFmpeg's two tokenizers, not shell escaping.
    first = "".join("\\" + c if c in "\\':" else c for c in str(path))
    return "".join("\\" + c if c in "\\'[],;" else c for c in first)


def compile_pipeline(value, project_dir, temp_dir, prefix="color", *, input_unorm16=False):
    """Return trusted FFmpeg filters; the parent owns subsequent SDR conversion.

    GEQ uses planar float RGBA and explicitly copies alpha. Its output retains
    negative/highlight values until later effects or the SDR renderer clamp.
    Lut filters receive normalized coordinates and a unit-domain table, because
    FFmpeg's native Cube reader does not fully implement nonzero domains.

    input_unorm16 is a trusted renderer fact, never a project setting. The
    renderer may set it for its admitted 16-bit imaging display PNG. With only
    the sRGB -> Rec.709 encoding change, lutrgb precomputes 65,536 entries per
    component once instead of executing the general GEQ expression at every
    full-resolution pixel. Each result is rounded to its nearest UNORM16 code;
    alpha is copied exactly. All other transforms keep the float path.
    """
    if not isinstance(input_unorm16, bool):
        raise ValueError("Integer input capability must be a trusted boolean")
    p = validate_pipeline(value, project_dir)
    if p is None or not p["enabled"]:
        return []
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", prefix):
        raise ValueError("Invalid colour filter prefix")
    conversion = p["input_transfer"] != "rec709" or p["input_primaries"] != "rec709" or p["source_white"] != p["target_white"]
    if not conversion and p["lut"] is None:
        return []
    if (input_unorm16 and p["input_transfer"] == "srgb" and p["input_primaries"] == "rec709"
            and p["source_white"] == list(WHITEPOINTS["D65"])
            and p["target_white"] == list(WHITEPOINTS["D65"]) and p["lut"] is None):
        expression = ("st(0,val/65535);st(1,if(lte(ld(0),0.04045),ld(0)/12.92,"
                      "pow((ld(0)+0.055)/1.055,2.4)));floor(65535*if(lt(ld(1),0.018),"
                      "4.5*ld(1),1.099*pow(ld(1),0.45)-0.099)+0.5)")
        return ["format=rgba64le", "lutrgb=" + ":".join(c + "='" + expression + "'" for c in "rgb") + ":a='val'"]
    filters = ["format=gbrapf32le"]
    if conversion:
        matrix = input_matrix(p)
        declarations = ";".join("st(%d,%s)" % (i, _decode_expression("%s(X,Y)" % c, p["input_transfer"])) for i, c in enumerate("rgb"))
        expressions = []
        for row in matrix:
            product = "+".join("(%s)*ld(%d)" % (_fmt(coefficient), i) for i, coefficient in enumerate(row))
            expressions.append(declarations + ";st(3," + product + ");if(lt(ld(3),0.018),4.5*ld(3),1.099*pow(ld(3),0.45)-0.099)")
        filters.append(_geq(expressions))
    if p["lut"] is not None:
        lut = load_lut(project_dir, p["lut"]["sha256"])
        if lut.domain_min != (0, 0, 0) or lut.domain_max != (1, 1, 1):
            filters.append(_geq(["clip((%s(X,Y)-(%s))/(%s),0,1)" % (c, _fmt(a), _fmt(b - a))
                                 for c, a, b in zip("rgb", lut.domain_min, lut.domain_max)]))
        directory = Path(temp_dir).resolve(strict=True)
        # The contents come from a hash-validated parser, never a user pathname.
        path = directory / (prefix + "-" + lut.sha256 + ".cube")
        if path.is_symlink():
            raise ValueError("Temporary LUT path must not be a symbolic link")
        path.write_text(lut.text(unit_domain=True), encoding="utf-8")
        filters.append("lut%dd=file=%s:interp=%s" % (lut.dimension, _filter_path(path), p["lut"]["interpolation"]))
    return filters


def capabilities():
    return {"version": 1, "output": "Rec.709 SDR", "input_transfers": list(TRANSFERS),
            "input_primaries": list(PRIMARIES), "cube_1d_max": MAX_1D_SIZE,
            "cube_3d_max": MAX_3D_SIZE, "max_cube_bytes": MAX_CUBE_BYTES,
            "bradford_adaptation": True, "raw_development": False,
            "hdr_mastering": False, "aces_display_transform": False,
            "ocio_runtime": False}

"""Real OpenEXR deep/multiview processing in a disposable optional runtime.

The interpretation follows OpenEXR's InterpretingDeepPixels and
TheoryDeepPixels documents (https://openexr.com/en/latest/). File IO uses the
OpenEXR.File API; sample arrays remain deep until an explicit flatten node.
Auxiliary IDs are not emission and are never averaged as if they were RGB.
"""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deep_compositing import (ARTIFACT_NAMES, MAX_CHANNEL_PIXELS, MAX_CHANNELS,
    MAX_PARTS, MAX_PIXELS, MAX_SAMPLES, MAX_SAMPLES_PER_PIXEL, MAX_SAMPLE_VALUES,
    MAX_SOURCE_BYTES, RUNTIME_REQUIREMENTS, SEMANTICS, channel_name,
    validate_deep_recipe)
from imaging import _hash_file, _identity, _json_bytes, _owned


def modules():
    try:
        import numpy as np
        import OpenEXR as exr
    except ImportError as exc:
        raise ValueError("Deep compositing requires NumPy and OpenEXR in the isolated Imaging runtime.") from exc
    # The pinned reader includes fixes for malformed deep sample chunks.
    if not hasattr(exr, "File") or tuple(int(v) for v in exr.__version__.split(".")[:3]) < (3, 4, 15):
        raise ValueError("Deep compositing requires OpenEXR 3.4.15 or newer.")
    return np, exr


def doctor():
    np, exr = modules()
    return {"available": True, "operations": ["source", "merge", "over", "holdout", "flatten", "channels"],
            "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "OpenEXR": exr.__version__},
            "reader": "OpenEXR.File, separate_channels=True", "export": "actual multipart deep/flat OpenEXR"}


def _read_exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise ValueError("Truncated EXR structure.")
    return data


def _cstring(stream):
    result = bytearray()
    while len(result) <= 255:
        value = _read_exact(stream, 1)
        if value == b"\0":
            return bytes(result).decode("utf-8", errors="strict")
        result += value
    raise ValueError("An EXR attribute name exceeds 255 bytes.")


def preflight(path):
    """Bound allocation from real headers/chunk sizes before the C++ reader.

    Header-only OpenEXR inspection alone cannot bound deep sample allocation.
    This also checks the unpacked byte counts of every deep chunk, without
    decompressing it, and rejects incomplete/overlapping chunk tables.
    """
    size = Path(path).stat().st_size
    if not 1 <= size <= MAX_SOURCE_BYTES:
        raise ValueError("The EXR file exceeds its 256 MiB bound.")
    with open(path, "rb") as stream:
        magic, version = struct.unpack("<II", _read_exact(stream, 8))
        if magic != 20000630 or (version & 255) != 2 or version & ~0x1FFF:
            raise ValueError("Unsupported OpenEXR magic/version flags.")
        multipart = bool(version & 0x1000)
        parts = []
        while True:
            attributes = {}
            while True:
                name = _cstring(stream)
                if not name:
                    break
                kind = _cstring(stream)
                length = struct.unpack("<I", _read_exact(stream, 4))[0]
                if name in attributes or length > 1024 * 1024 or stream.tell() + length > 2 * 1024 * 1024:
                    raise ValueError("EXR headers exceed their bound or contain duplicate attributes.")
                attributes[name] = (kind, _read_exact(stream, length))
            if not attributes:
                if not multipart or not parts:
                    raise ValueError("The EXR has an empty header.")
                break
            if len(parts) >= MAX_PARTS:
                raise ValueError("The EXR exceeds its part bound.")
            try:
                window = struct.unpack("<4i", attributes["dataWindow"][1])
                display = struct.unpack("<4i", attributes["displayWindow"][1])
                compression = attributes["compression"][1][0]
                storage = attributes.get("type", ("string", b"tiledimage" if version & 0x200 else b"scanlineimage"))[1].decode("ascii")
            except (KeyError, IndexError, struct.error, UnicodeError) as exc:
                raise ValueError("The EXR is missing valid image header fields.") from exc
            width, height = window[2] - window[0] + 1, window[3] - window[1] + 1
            if not 1 <= width <= 16384 or not 1 <= height <= 16384 or width * height > MAX_PIXELS:
                raise ValueError("An EXR part exceeds the one-million-pixel working bound.")
            if display[2] < display[0] or display[3] < display[1]:
                raise ValueError("The EXR display window is invalid.")
            if storage not in {"scanlineimage", "tiledimage", "deepscanline", "deeptile"}:
                raise ValueError("Unsupported EXR storage type.")
            import io
            channels, channel_bytes = {}, 0
            channel_stream = io.BytesIO(attributes.get("channels", ("", b""))[1])
            while True:
                name = _cstring(channel_stream)
                if not name:
                    break
                channel_name(name)
                pixel_type, linear, xs, ys = struct.unpack("<iB3xii", _read_exact(channel_stream, 16))
                if name in channels or pixel_type not in (0, 1, 2) or xs != 1 or ys != 1 or linear not in (0, 1):
                    raise ValueError("EXR channels must be distinct, numeric and full resolution.")
                channels[name] = {"type": ("uint", "half", "float")[pixel_type], "pLinear": bool(linear)}
                channel_bytes += 2 if pixel_type == 1 else 4
            if not 1 <= len(channels) <= MAX_CHANNELS or channel_stream.read(1):
                raise ValueError("The EXR channel list is invalid or exceeds its bound.")
            deep = storage.startswith("deep")
            if deep and compression not in (0, 1, 2):
                raise ValueError("Deep sources need lossless NO, RLE or ZIPS compression.")
            tiled = storage.endswith("tile") or storage == "tiledimage"
            if tiled:
                try:
                    tw, th, mode = struct.unpack("<IIB", attributes["tiles"][1])
                except (KeyError, struct.error) as exc:
                    raise ValueError("The EXR tile descriptor is invalid.") from exc
                if not 1 <= tw <= 16384 or not 1 <= th <= 16384 or mode & 15:
                    raise ValueError("EXR processing supports single-level tiles, not mip/rip maps.")
                count = math.ceil(width / tw) * math.ceil(height / th)
            else:
                rows = {0: 1, 1: 1, 2: 1, 3: 16, 4: 32, 5: 16, 6: 32, 7: 32, 8: 32, 9: 256, 10: 256, 11: 32}.get(compression)
                if rows is None:
                    raise ValueError("Unsupported EXR compression identifier.")
                count = math.ceil(height / rows)
            declared = attributes.get("chunkCount")
            if declared and (len(declared[1]) != 4 or struct.unpack("<i", declared[1])[0] != count):
                raise ValueError("The EXR chunk count does not match its image geometry.")
            if (multipart or deep) and not declared:
                raise ValueError("A multipart/deep source requires a complete chunk table.")
            parts.append({"storage": storage, "deep": deep, "tiled": tiled, "count": count,
                          "channels": channels, "channel_bytes": channel_bytes,
                          "width": width, "height": height, "window": window, "display": display})
            if not multipart:
                break
        if sum(p["width"] * p["height"] * len(p["channels"]) for p in parts) > MAX_CHANNEL_PIXELS:
            raise ValueError("EXR channel/pixel allocation exceeds the working bound.")
        offset_start = stream.tell()
        table_end = offset_start + 8 * sum(p["count"] for p in parts)
        if table_end > size:
            raise ValueError("Truncated EXR chunk offset tables.")
        tables = [struct.unpack("<" + "Q" * p["count"], _read_exact(stream, 8 * p["count"])) for p in parts]
        regions, sample_total, value_total = [], 0, 0
        for index, (part, offsets) in enumerate(zip(parts, tables)):
            for offset in offsets:
                if not table_end <= offset < size:
                    raise ValueError("An EXR chunk points outside its image payload.")
                stream.seek(offset)
                if multipart and struct.unpack("<i", _read_exact(stream, 4))[0] != index:
                    raise ValueError("An EXR chunk points at a different part.")
                _read_exact(stream, 16 if part["tiled"] else 4)
                if part["deep"]:
                    packed_counts, packed_samples, unpacked = struct.unpack("<QQQ", _read_exact(stream, 24))
                    if unpacked % part["channel_bytes"]:
                        raise ValueError("The deep sample byte count is inconsistent with its channels.")
                    samples = unpacked // part["channel_bytes"]
                    sample_total += samples
                    value_total += samples * len(part["channels"])
                    if sample_total > MAX_SAMPLES or value_total > MAX_SAMPLE_VALUES:
                        raise ValueError("EXR unpacked deep samples exceed the allocation bound.")
                    end = stream.tell() + packed_counts + packed_samples
                else:
                    packed = struct.unpack("<I", _read_exact(stream, 4))[0]
                    end = stream.tell() + packed
                if end > size:
                    raise ValueError("A deep/flat EXR chunk exceeds its source file.")
                regions.append((offset, end))
        ordered = sorted(regions)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError("EXR chunks overlap or have repeated offsets.")
    return parts


@dataclass
class Image:
    header: dict
    channels: dict
    types: dict
    linear: dict
    deep: bool

    @property
    def shape(self):
        return next(iter(self.channels.values())).shape

    def clone(self, channels=None, types=None, deep=None):
        return Image(dict(self.header), self.channels.copy() if channels is None else channels,
                     self.types.copy() if types is None else types, self.linear.copy(),
                     self.deep if deep is None else deep)


def _kind(name):
    if name in {"Z", "ZBack"}:
        return "depth"
    base = name.rsplit(".", 1)[-1]
    if base in {"A", "AR", "AG", "AB"}:
        return "alpha"
    return "color" if base in {"R", "G", "B", "Y"} else "auxiliary"


def _associated(name, channels):
    parts = name.split(".")
    base, prefix = parts[-1], parts[:-1]
    while True:
        lead = ".".join(prefix) + ("." if prefix else "")
        candidates = ["A" + base, "A"] if base in {"R", "G", "B"} else ["A"]
        for suffix in candidates:
            if lead + suffix in channels:
                return lead + suffix
        if not prefix:
            break
        prefix.pop()
    raise ValueError(f"Channel {name!r} has no associated alpha channel.")


def _schema(image, require_deep=False):
    if require_deep and not image.deep:
        raise ValueError("This operation requires actual deep sample data; flat images are not implicitly deepened.")
    if image.header.get("cinematicumAlpha", "premultiplied") != "premultiplied":
        raise ValueError("Deep composition requires premultiplied channel values.")
    if image.deep and ("Z" not in image.channels or image.types["Z"] == "uint"):
        raise ValueError("A deep image needs a half/float Z channel.")
    associated = {name: _associated(name, image.channels) for name in image.channels if _kind(name) in {"color", "auxiliary"}}
    for name in image.channels:
        if _kind(name) in {"color", "alpha"} and image.types[name] == "uint":
            raise ValueError("Color/alpha composition requires half/float channels, not UINT data.")
    return associated


def _validate_pixels(image, np):
    if not image.channels or len(image.channels) > MAX_CHANNELS:
        raise ValueError("Invalid EXR channel count.")
    shape = image.shape
    if len(shape) != 2 or shape[0] * shape[1] > MAX_PIXELS:
        raise ValueError("Invalid EXR image shape.")
    counts = None
    total = 0
    for name, array in image.channels.items():
        channel_name(name)
        if array.shape != shape:
            raise ValueError("EXR channels have different image geometry.")
        if image.deep:
            if array.dtype != object:
                raise ValueError("A deep channel lost its actual sample arrays.")
            local_counts = np.zeros(shape, dtype=np.int32)
            dtype = np.dtype({"half": "float16", "float": "float32", "uint": "uint32"}[image.types[name]])
            values = []
            for position in np.ndindex(shape):
                item = array[position]
                if item is None:
                    item = np.empty(0, dtype=dtype)
                    array[position] = item
                if not isinstance(item, np.ndarray) or item.ndim != 1 or item.dtype != dtype or len(item) > MAX_SAMPLES_PER_PIXEL:
                    raise ValueError("Deep samples exceed their per-pixel bound or use inconsistent numeric types.")
                local_counts[position] = len(item)
                if len(item):
                    values.append(item)
            if counts is None:
                counts = local_counts
                total = int(counts.sum())
            elif not np.array_equal(counts, local_counts):
                raise ValueError("Deep channels must have identical sample counts in each pixel.")
            if total > MAX_SAMPLES or total * len(image.channels) > MAX_SAMPLE_VALUES:
                raise ValueError("Deep samples exceed the working allocation bound.")
        else:
            if array.dtype not in (np.dtype("float16"), np.dtype("float32"), np.dtype("uint32")):
                raise ValueError("Only half, float and UINT EXR channels are supported.")
            values = [array]
        for data in values:
            if not np.isfinite(data).all() or (data.dtype.kind == "f" and np.any(np.abs(data) > 1e20)):
                raise ValueError("EXR channel values must be finite and bounded.")
            if _kind(name) == "alpha" and (np.any(data < 0) or np.any(data > 1)):
                raise ValueError("EXR alpha must lie in [0,1].")
            if _kind(name) == "depth" and (np.any(data < 0) or np.any(data > 1e12)):
                raise ValueError("EXR depth must lie in [0,1e12].")
    if image.deep and "Z" not in image.channels:
        raise ValueError("A deep part requires a base Z channel.")
    return total


def _view_name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 120 or any(ord(c) < 33 for c in value) or "." in value:
        raise ValueError("EXR views need bounded names without periods or whitespace.")
    return value


def read_exr(path):
    np, exr = modules()
    info = preflight(path)
    result = []
    with exr.File(str(path), separate_channels=True) as source:
        if len(source.parts) != len(info):
            raise ValueError("EXR reader/header part counts differ.")
        for index, (part, item) in enumerate(zip(source.parts, info)):
            header = dict(part.header)
            channels = {name: channel.pixels for name, channel in part.channels.items()}
            if set(channels) != set(item["channels"]):
                raise ValueError("EXR channel decoding does not match its header.")
            image = Image(header, channels, {name: val["type"] for name, val in item["channels"].items()},
                          {name: val["pLinear"] for name, val in item["channels"].items()}, item["deep"])
            _validate_pixels(image, np)
            views = header.get("multiView")
            if views is not None:
                if len(info) != 1 or not isinstance(views, list) or not views or len(views) > MAX_PARTS:
                    raise ValueError("The legacy multiView declaration is invalid or mixed with multipart storage.")
                views = [_view_name(v) for v in views]
                if len(set(views)) != len(views):
                    raise ValueError("EXR view names must be unique.")
                groups = {view: {} for view in views}
                groups[None] = {}
                for name in channels:
                    pieces = name.split(".")
                    if len(pieces) == 1:
                        view, renamed = views[0], name
                    elif pieces[-2] in views:
                        view, renamed = pieces[-2], ".".join(pieces[:-2] + pieces[-1:])
                    else:
                        view, renamed = None, name
                    if renamed in groups[view]:
                        raise ValueError("Legacy multiview channel names collide after normalization.")
                    groups[view][renamed] = name
                for view, mapping in groups.items():
                    if not mapping:
                        continue
                    separated = image.clone({k: channels[v] for k, v in mapping.items()}, {k: image.types[v] for k, v in mapping.items()})
                    separated.linear = {k: image.linear[v] for k, v in mapping.items()}
                    separated.header.pop("multiView", None)
                    separated.header.pop("view", None)
                    if view is not None:
                        separated.header["view"] = view
                    separated.header["name"] = (header.get("name") or "part0") + ":" + (view or "unassigned")
                    _validate_pixels(separated, np)
                    result.append(separated)
            else:
                if "view" in header:
                    _view_name(header["view"])
                image.header.setdefault("name", f"part{index}")
                result.append(image)
    if not 1 <= len(result) <= MAX_PARTS:
        raise ValueError("Normalized EXR views exceed the part bound.")
    return result


def describe(images):
    np, _ = modules()
    parts = []
    for index, image in enumerate(images):
        sample_count = _validate_pixels(image, np)
        front = image.channels.get("Z")
        maximum = max((len(v) for v in front.flat), default=0) if image.deep else 1
        parts.append({"index": index, "name": str(image.header.get("name", f"part{index}")),
                      "view": image.header.get("view"), "deep": image.deep,
                      "width": image.shape[1], "height": image.shape[0],
                      "data_window": [list(map(int, v)) for v in image.header["dataWindow"]],
                      "display_window": [list(map(int, v)) for v in image.header["displayWindow"]],
                      "channels": [{"name": name, "type": image.types[name], "pLinear": image.linear.get(name, False)} for name in sorted(image.channels)],
                      "total_samples": sample_count if image.deep else image.shape[0] * image.shape[1],
                      "max_samples_per_pixel": maximum, "color_space": image.header.get("ocioColorSpace")})
    return {"parts": parts, "normalized_multiview": "multipart view attributes", "semantics": SEMANTICS}


def _compatible(a, b, same_channels=True):
    np, _ = modules()
    if a.deep != b.deep or a.shape != b.shape or a.header.get("view") != b.header.get("view"):
        raise ValueError("Binary EXR inputs must have the same deep/flat type, geometry and view.")
    if any(not np.array_equal(a.header[k], b.header[k]) for k in ("dataWindow", "displayWindow")):
        raise ValueError("Binary EXR inputs must have identical data/display windows.")
    for key in ("ocioColorSpace", "chromaticities"):
        if key in a.header and key in b.header and not np.array_equal(a.header[key], b.header[key]):
            raise ValueError("Binary EXR inputs declare incompatible color spaces/primaries.")
    if same_channels and set(a.channels) != set(b.channels):
        raise ValueError("Binary EXR inputs need the same channel names; use explicit channel nodes to align them.")
    if same_channels and any((a.types[k] == "uint") != (b.types[k] == "uint") for k in a.channels):
        raise ValueError("UINT identity channels cannot be implicitly mixed with floating-point channels.")


def _samples(image, position):
    names = list(image.channels)
    length = len(image.channels[names[0]][position])
    return [{name: image.channels[name][position][i].item() for name in names} for i in range(length)]


def _key(sample):
    return sample["Z"], max(sample["Z"], sample.get("ZBack", sample["Z"]))


def _alphas(names):
    return [name for name in names if _kind(name) == "alpha"]


def _split(sample, start, end, associated):
    front, back = _key(sample)
    result = dict(sample)
    if not front <= start < end <= back:
        raise ValueError("Invalid internal deep volume subdivision.")
    ratio = (end - start) / (back - front)
    result["Z"] = start
    result["ZBack"] = end
    for name in _alphas(sample):
        a = sample[name]
        result[name] = 1.0 if a == 1 else -math.expm1(math.log1p(-a) * ratio)
    for name, alpha in associated.items():
        if _kind(name) == "color":
            a = sample[alpha]
            result[name] = sample[name] * (result[alpha] / a if a else ratio)
    return result


def _mixture(samples, associated, policy):
    """Symmetric Beer-Lambert mixture for coincident points/volume intervals."""
    if len(samples) == 1:
        return dict(samples[0])
    auxiliary = [n for n in samples[0] if _kind(n) == "auxiliary"]
    if auxiliary and policy == "error":
        raise ValueError("Overlapping auxiliary/ID data require explicit front selection; no implicit averaging is permitted.")
    result = dict(samples[0])
    densities = {}
    for name in _alphas(result):
        alpha = [s[name] for s in samples]
        density = [math.inf if a == 1 else -math.log1p(-a) for a in alpha]
        total = sum(density)
        result[name] = 1.0 if math.isinf(total) else -math.expm1(-total)
        densities[name] = density, total
    for name, alpha in associated.items():
        if _kind(name) != "color":
            continue
        density, total = densities[alpha]
        opaque = [s[name] for s, d in zip(samples, density) if math.isinf(d)]
        if opaque:
            # OpenEXR convention: opaque coincident samples have lost their
            # original density; the symmetric limit is their arithmetic mean.
            result[name] = sum(opaque) / len(opaque)
        elif total == 0:
            result[name] = sum(s[name] for s in samples)
        else:
            emission = sum(s[name] * (d / s[alpha] if s[alpha] else 1.0)
                           for s, d in zip(samples, density))
            result[name] = emission * result[alpha] / total
    return result


def tidy(samples, associated, policy):
    if not samples:
        return []
    ordered = sorted(samples, key=_key)  # Stable source order is the auxiliary tie-break.
    boundaries = sorted({depth for sample in ordered for depth in _key(sample)})
    if len(boundaries) * len(ordered) > 1_000_000:
        raise ValueError("Deep interval overlap complexity exceeds the per-pixel processing bound.")
    output = []
    for index, start in enumerate(boundaries):
        points = [s for s in ordered if _key(s) == (start, start)]
        if points:
            point = _mixture(points, associated, policy)
            point["Z"] = start
            if "ZBack" in point:
                point["ZBack"] = start
            output.append(point)
        if index + 1 < len(boundaries):
            end = boundaries[index + 1]
            active = [s for s in ordered if s["Z"] <= start and _key(s)[1] >= end and _key(s)[1] > s["Z"]]
            if active:
                pieces = [_split(s, start, end, associated) for s in active]
                output.append(_mixture(pieces, associated, policy))
        if len(output) > MAX_SAMPLES_PER_PIXEL:
            raise ValueError("Deep interval splitting exceeds the per-pixel sample bound.")
    return output


def _arrays(image, pixels, types=None):
    np, _ = modules()
    types = image.types.copy() if types is None else types
    channels = {name: np.empty(image.shape, dtype=object) for name in types}
    count = 0
    for position, samples in zip(np.ndindex(image.shape), pixels):
        count += len(samples)
        if len(samples) > MAX_SAMPLES_PER_PIXEL or count > MAX_SAMPLES or count * len(types) > MAX_SAMPLE_VALUES:
            raise ValueError("The processed deep sample allocation exceeds its bound.")
        for name, kind in types.items():
            values = [sample.get(name, sample["Z"] if name == "ZBack" else 0) for sample in samples]
            if kind == "half" and any(abs(v) > 65504 for v in values):
                raise ValueError("A HALF channel operation overflows its finite range.")
            channels[name][position] = np.asarray(values, dtype={"half": "float16", "float": "float32", "uint": "uint32"}[kind])
    result = image.clone(channels, types)
    _validate_pixels(result, np)
    return result


def _processing_types(image):
    return {name: kind if kind == "uint" or _kind(name) == "auxiliary" else "float" for name, kind in image.types.items()}


def merge(a, b):
    np, _ = modules()
    _compatible(a, b)
    if not a.deep or "Z" not in a.channels:
        raise ValueError("Deep merge requires actual samples with a Z channel.")
    types = {name: a.types[name] if a.types[name] == b.types[name] else "float" for name in a.channels}
    return _arrays(a, (sorted(_samples(a, p) + _samples(b, p), key=_key) for p in np.ndindex(a.shape)), types)


def over(a, b, policy):
    np, _ = modules()
    _compatible(a, b)
    associated = _schema(a)
    _schema(b)
    if a.deep:
        types = _processing_types(a)
        # A selected front auxiliary can come from either image. Preserve a
        # FLOAT input exactly even when the other input declares HALF; schema
        # compatibility above rejects mixing UINT identities with floats.
        for name in types:
            if a.types[name] != b.types[name]:
                types[name] = "float"
        if "ZBack" in b.channels:
            types["ZBack"] = "float"
        return _arrays(a, (tidy(_samples(a, p) + _samples(b, p), associated, policy) for p in np.ndindex(a.shape)), types)
    auxiliary = [n for n in a.channels if _kind(n) == "auxiliary"]
    if auxiliary and policy == "error":
        raise ValueError("Flat over with auxiliary data requires explicit front selection.")
    channels, types = {}, _processing_types(a)
    for name in a.channels:
        kind = _kind(name)
        if kind in {"color", "alpha"}:
            alpha = name if kind == "alpha" else associated[name]
            channels[name] = (a.channels[name].astype(np.float64) + (1 - a.channels[alpha].astype(np.float64)) * b.channels[name]).astype(np.float32)
        else:
            channels[name] = a.channels[name].copy()
    result = a.clone(channels, types)
    _validate_pixels(result, np)
    return result


def holdout(subject, matte, policy):
    del policy  # No sample identities are mixed by opaque depth clipping.
    np, _ = modules()
    _compatible(subject, matte, same_channels=False)
    associated = _schema(subject, True)
    _schema(matte, True)
    if "A" not in matte.channels:
        raise ValueError("An opaque holdout matte requires a base A channel.")
    if any(np.any((v != 0) & (v != 1)) for v in matte.channels["A"].flat):
        raise ValueError("Opaque deep holdout requires binary matte A; fractional-alpha holdout is not implemented.")
    def pixels():
        for position in np.ndindex(subject.shape):
            masks = _samples(matte, position)
            cut = min((s["Z"] for s in masks if s["A"] == 1), default=math.inf)
            output = []
            for sample in sorted(_samples(subject, position), key=_key):
                front, back = _key(sample)
                if front >= cut:
                    continue
                output.append(_split(sample, front, cut, associated) if back > cut else sample)
            yield output
    return _arrays(subject, pixels(), _processing_types(subject))


def flatten(image, policy):
    np, _ = modules()
    associated = _schema(image, True)
    types = _processing_types(image)
    channels = {name: np.zeros(image.shape, dtype={"half": "float16", "float": "float32", "uint": "uint32"}[kind]) for name, kind in types.items()}
    for position in np.ndindex(image.shape):
        samples = tidy(_samples(image, position), associated, policy)
        if not samples:
            continue
        if len(samples) > 1 and policy == "error" and any(_kind(n) == "auxiliary" for n in image.channels):
            raise ValueError("Flattening multiple auxiliary/ID samples requires explicit front selection.")
        alphas = {name: 0.0 for name in _alphas(image.channels)}
        colors = {name: 0.0 for name in image.channels if _kind(name) == "color"}
        for sample in samples:
            for name in colors:
                colors[name] += (1 - alphas[associated[name]]) * sample[name]
            for name in alphas:
                alphas[name] += (1 - alphas[name]) * sample[name]
        for name in channels:
            if name in alphas:
                value = alphas[name]
            elif name in colors:
                value = colors[name]
            elif name == "ZBack":
                value = _key(samples[-1])[1]
            else:
                value = samples[0][name]
            channels[name][position] = value
    result = image.clone(channels, types, deep=False)
    _validate_pixels(result, np)
    return result


def channel_ops(image, node):
    np, _ = modules()
    if not (set(node["rename"]) | set(node["remove"])) <= set(image.channels):
        raise ValueError("A channel edit references a missing input channel.")
    retained = {node["rename"].get(name, name): name for name in image.channels if name not in node["remove"]}
    if len(retained) != len(image.channels) - len(node["remove"]) or set(retained) & set(node["create"]):
        raise ValueError("A channel edit would overwrite a different channel.")
    if not 1 <= len(retained) + len(node["create"]) <= MAX_CHANNELS:
        raise ValueError("A channel edit leaves an invalid channel count.")
    channels = {name: image.channels[old] for name, old in retained.items()}
    types = {name: image.types[old] for name, old in retained.items()}
    linear = {name: image.linear.get(old, False) for name, old in retained.items()}
    reference = next(iter(image.channels.values()))
    for name, spec in node["create"].items():
        dtype = {"half": np.float16, "float": np.float32, "uint": np.uint32}[spec["type"]]
        if image.deep:
            array = np.empty(image.shape, dtype=object)
            for position in np.ndindex(image.shape):
                array[position] = np.full(len(reference[position]), spec["value"], dtype=dtype)
        else:
            array = np.full(image.shape, spec["value"], dtype=dtype)
        channels[name], types[name], linear[name] = array, spec["type"], False
    for name, spec in node["scale"].items():
        if name not in channels:
            raise ValueError("Channel scale references a missing final channel name.")
        multiply, add, kind = spec["multiply"], spec["add"], types[name]
        def scale(data):
            values = data.astype(np.float64) * multiply + add
            if kind == "uint":
                if not np.isfinite(values).all() or np.any(values != np.floor(values)) or np.any(values < 0) or np.any(values > 2**32 - 1):
                    raise ValueError("UINT edits must retain exact integers in [0,2^32-1].")
            elif not np.isfinite(values).all() or np.any(np.abs(values) > (65504 if kind == "half" else 1e20)):
                raise ValueError("A channel edit exceeds its finite numeric range.")
            return values.astype(data.dtype)
        if image.deep:
            array = np.empty(image.shape, dtype=object)
            for position in np.ndindex(image.shape):
                array[position] = scale(channels[name][position])
            channels[name] = array
        else:
            channels[name] = scale(channels[name])
    result = image.clone(channels, types)
    result.linear = linear
    _validate_pixels(result, np)
    return result


def write_exr(path, images):
    np, exr = modules()
    parts, names = [], set()
    for index, image in enumerate(images):
        _validate_pixels(image, np)
        header = {k: v for k, v in image.header.items() if k not in {"channels", "chunkCount", "tiles", "deepImageState", "maxSamplesPerPixel", "version", "multiView"}}
        name = str(header.get("name", f"part{index}"))
        if name in names:
            name = f"{name}:output{index}"
        if name in names or len(name.encode("utf-8")) > 255:
            raise ValueError("EXR output part names are ambiguous or exceed the name bound.")
        names.add(name)
        header["name"] = name
        header["type"] = exr.deepscanline if image.deep else exr.scanlineimage
        header["compression"] = exr.ZIPS_COMPRESSION if image.deep else exr.ZIP_COMPRESSION
        header["cinematicumDeepSemantics"] = "v1: premultiplied; depth-aware optical density; explicit auxiliary policy"
        channels = {name: exr.Channel(name, array, 1, 1, image.linear.get(name, False)) for name, array in image.channels.items()}
        parts.append(exr.Part(header, channels))
    with exr.File(parts) as output:
        output.write(str(path))


def write_preview(path, image, spec):
    np, _ = modules()
    for name in spec["channels"] + ([spec["alpha"]] if spec["alpha"] is not None else []):
        if name not in image.channels:
            raise ValueError(f"The preview channel {name!r} is missing; select channels explicitly.")
        if image.types[name] == "uint":
            raise ValueError("UINT identity channels cannot be used as normalized preview RGB/alpha.")
    # A display channel projection is independent of the preserved EXR. IDs,
    # vectors and other unselected auxiliary channels do not enter this PNG,
    # so they must not force a lossy ID reduction merely to view RGB.
    selected = set(spec["channels"])
    if spec["alpha"]:
        selected.add(spec["alpha"])
    if image.deep:
        selected.update(name for name in ("Z", "ZBack") if name in image.channels)
        for name in list(selected):
            if _kind(name) in {"color", "auxiliary"}:
                selected.add(_associated(name, image.channels))
        projected = image.clone({name: image.channels[name] for name in selected},
                                {name: image.types[name] for name in selected})
        image = flatten(projected, spec["auxiliary"])
    rgb = np.stack([image.channels[c] for c in spec["channels"]], axis=-1).astype(np.float64)
    alpha = image.channels[spec["alpha"]].astype(np.float64) if spec["alpha"] else np.ones(image.shape, dtype=np.float64)
    if np.any(alpha < 0) or np.any(alpha > 1):
        raise ValueError("The selected preview alpha must lie in [0,1].")
    # Color may have distinct AR/AG/AB associations. Unpremultiply each using
    # its own associated alpha, then write one explicitly selected PNG alpha.
    for index, name in enumerate(spec["channels"]):
        if _kind(name) == "color" and image.header.get("cinematicumAlpha", "premultiplied") != "straight":
            try:
                associated = _associated(name, image.channels)
            except ValueError:
                if image.header.get("cinematicumAlpha") != "straight":
                    raise
            else:
                a = image.channels[associated]
                rgb[..., index] = np.divide(rgb[..., index], a, out=np.zeros(image.shape), where=a > 0)
    rgb *= 2.0 ** spec["exposure"]
    if spec["transfer"] == "linear_to_srgb":
        rgb = np.where(rgb <= .0031308, 12.92 * rgb, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - .055)
    clipped = int(np.count_nonzero((rgb < 0) | (rgb > 1)))
    rgba = np.rint(np.clip(np.dstack((rgb, alpha)), 0, 1) * 65535).astype(">u2")
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    rows = b"".join(b"\0" + row.tobytes() for row in rgba)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", image.shape[1], image.shape[0], 16, 6, 0, 0, 0))
    if spec["transfer"] == "linear_to_srgb":
        data += chunk(b"sRGB", b"\0")
    path.write_bytes(data + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return {"width": image.shape[1], "height": image.shape[0], "encoding": "16-bit SDR RGBA PNG, straight alpha",
            "display_transfer": spec["transfer"], "rgb_values_clipped": clipped,
            "source_channels": spec["channels"], "alpha_channel": spec["alpha"]}


def evaluate(recipe, sources, progress=None):
    np, _ = modules()
    nodes = {node["id"]: node for node in recipe["nodes"]}
    cache, references = {}, {ident: 0 for ident in nodes}
    for node in nodes.values():
        for child in node.get("inputs", [node["input"]] if "input" in node else []):
            references[child] += 1
    for ident in recipe["outputs"]:
        references[ident] += 1
    completed = 0
    def visit(ident):
        nonlocal completed
        if ident in cache:
            return cache[ident]
        node = nodes[ident]
        op = node["op"]
        inputs = node.get("inputs", [node["input"]] if "input" in node else [])
        arguments = [visit(child) for child in inputs]
        if op == "source":
            parts = sources[node["source_id"]]
            if node["part"] >= len(parts):
                raise ValueError("A source node references a missing logical EXR part/view.")
            image = parts[node["part"]].clone()
        elif op == "merge":
            image = merge(*arguments)
        elif op == "over":
            image = over(*arguments, node["auxiliary"])
        elif op == "holdout":
            image = holdout(*arguments, node["auxiliary"])
        elif op == "flatten":
            image = flatten(arguments[0], node["auxiliary"])
        else:
            image = channel_ops(arguments[0], node)
        cache[ident] = image
        for child in inputs:
            references[child] -= 1
            if references[child] == 0:
                cache.pop(child, None)
        # Bound retained graph arrays as well as each individual source.
        unique = {id(part): part for part in [*cache.values(), *[p for values in sources.values() for p in values]]}
        if sum(p.shape[0] * p.shape[1] * len(p.channels) for p in unique.values()) > MAX_CHANNEL_PIXELS * 4:
            raise ValueError("The retained graph exceeds its channel/pixel working bound.")
        completed += 1
        if progress:
            progress(.15 + .65 * completed / len(nodes))
        return image
    return [visit(ident) for ident in recipe["outputs"]]


def _verified(root, descriptor):
    if not isinstance(descriptor, dict):
        raise ValueError("EXR input descriptors must be objects.")
    path = _owned(root, descriptor.get("path"))
    digest = _identity(descriptor.get("sha256"), "EXR source hash", True)
    if _hash_file(path, MAX_SOURCE_BYTES) != (digest, descriptor.get("size")):
        raise ValueError("An EXR source changed after admission.")
    return path


def render(request):
    recipe = validate_deep_recipe(request.get("recipe"))
    root, scratch = Path(request["project_dir"]).absolute(), Path(request["output_dir"]).absolute()
    relative = scratch.relative_to(root)
    if len(relative.parts) != 3 or relative.parts[:2] != ("deep", "outputs") or not relative.name.startswith(".building-"):
        raise ValueError("The deep worker output is not a private project directory.")
    _owned(root, relative, is_dir=True)
    def progress(value):
        temporary = scratch / "progress.tmp"
        temporary.write_bytes(_json_bytes({"progress": value}))
        os.replace(temporary, scratch / "progress.json")
    inputs = request.get("inputs")
    wanted = sorted({n["source_id"] for n in recipe["nodes"] if n["op"] == "source"})
    if not isinstance(inputs, list) or [v.get("id") for v in inputs if isinstance(v, dict)] != wanted:
        raise ValueError("EXR inputs do not match the frozen source graph.")
    sources = {}
    progress(.02)
    for index, descriptor in enumerate(inputs):
        if descriptor.get("path") != f"deep/sources/{descriptor['id']}.exr" or descriptor.get("sha256") != descriptor["id"]:
            raise ValueError("Deep graph inputs must be admitted immutable EXR sources.")
        source = _verified(root, descriptor)
        snapshot = scratch / f"input-{index}.exr"
        with os.fdopen(os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as inp, snapshot.open("xb") as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
        if _hash_file(snapshot, MAX_SOURCE_BYTES) != (descriptor["sha256"], descriptor["size"]):
            raise ValueError("A deep source changed during snapshotting.")
        sources[descriptor["id"]] = read_exr(snapshot)
        if sum(p.shape[0] * p.shape[1] * len(p.channels) for values in sources.values() for p in values) > MAX_CHANNEL_PIXELS * 2:
            raise ValueError("Combined EXR source allocation exceeds the graph working bound.")
    images = evaluate(recipe, sources, progress)
    destination = scratch / "result"
    destination.mkdir()
    write_exr(destination / "composite.exr", images)
    progress(.86)
    # Decode the actual encoded artifact, not an in-memory representation, for
    # the result inventory and display. This also verifies all exported parts.
    exported = read_exr(destination / "composite.exr")
    preview = write_preview(destination / "preview.png", exported[recipe["preview"]["output"]], recipe["preview"])
    progress(.95)
    artifacts = {}
    for key, name in (("exr", "composite.exr"), ("preview", "preview.png")):
        digest, size = _hash_file(destination / name, MAX_SOURCE_BYTES)
        artifacts[key] = {"filename": name, "sha256": digest, "size": size}
    receipt = {"version": 1, "operation": "deep-compositing", "recipe": recipe, "inputs": inputs,
               "output": describe(exported), "preview": preview, "semantics": SEMANTICS,
               "versions": doctor()["versions"], "artifacts": artifacts, "created_at": time.time(),
               "issuance_effect": "NONE", "delivery_boundary": "Still EXR processing only. Timeline admission, if requested separately, uses the SDR preview; no HDR movie mastering or full production-scale deep pipeline is certified."}
    (destination / "receipt.json").write_bytes(_json_bytes(receipt))
    return {"ok": True, "parts": len(exported), "width": preview["width"], "height": preview["height"]}


def main():
    try:
        data = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("The deep request exceeds its bound.")
        request = json.loads(data)
        if not isinstance(request, dict):
            raise ValueError("A deep request must be an object.")
        command = request.get("command")
        if command == "doctor":
            result = doctor()
        elif command == "probe":
            path = _verified(request["project_dir"], request["input"])
            result = describe(read_exr(path))
            if _hash_file(path, MAX_SOURCE_BYTES) != (request["input"]["sha256"], request["input"]["size"]):
                raise ValueError("The EXR changed while reading its samples.")
        elif command == "render":
            result = render(request)
        else:
            raise ValueError("Unsupported deep worker command.")
        sys.stdout.buffer.write(_json_bytes(result))
        return 0
    except Exception as exc:
        sys.stdout.buffer.write(_json_bytes({"error": str(exc)[:6000], "type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Cubic roto geometry and a bounded, scanline-tiled 16-bit coverage rasterizer.

The saved document retains cubic anchors/handles and point feather values.
Flattening uses a 1/8 output-pixel control-polygon bound, then 2 x 2 coverage
sampling. Feather is an inward distance measured in output pixels. Frames are
processed one at a time; the entire animation is never held in memory.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

MAX_RASTER_PIXELS = 33_554_432
MAX_PATH_SEGMENTS = 32768
MAX_OUTPUT_BYTES = 4 * 1024 ** 3


def _mid(a, b):
    return ((a[0] + b[0]) * .5, (a[1] + b[1]) * .5)


def _distance_to_line(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / length


def flatten_path(params, width, height, tolerance=.125):
    """Return (x, y, feather_pixels) samples without modifying authored cubics."""
    angle = math.radians(params["rotation"])
    cosine, sine = math.cos(angle), math.sin(angle)
    sx, sy = width * params["width"], height * params["height"]
    feather = params["feather"] * min(sx, sy) * .5

    def point(x, y):
        a, b = (x - .5) * sx, (y - .5) * sy
        return (width * params["x"] + cosine * a - sine * b,
                height * params["y"] + sine * a + cosine * b)

    anchors = params["bezier"]
    output = []

    def subdivide(p0, p1, p2, p3, f0, f1, depth=0):
        # The curve lies inside its control hull. Distance to the chord plus
        # control-polygon length catches collinear reversals/cusps as well.
        chord = math.dist(p0, p3)
        polygon = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        flat = (max(_distance_to_line(p1, p0, p3), _distance_to_line(p2, p0, p3)) <= tolerance
                and polygon - chord <= tolerance)
        if flat:
            output.append((p0[0], p0[1], f0))
            if len(output) > MAX_PATH_SEGMENTS:
                raise ValueError("Bezier path exceeds the adaptive segment budget.")
            return
        if depth >= 16:
            raise ValueError("Bezier path could not meet the output-pixel precision bound.")
        a, b, c = _mid(p0, p1), _mid(p1, p2), _mid(p2, p3)
        d, e = _mid(a, b), _mid(b, c)
        center, fm = _mid(d, e), (f0 + f1) * .5
        subdivide(p0, a, d, center, f0, fm, depth + 1)
        subdivide(center, e, c, p3, fm, f1, depth + 1)

    for first, second in zip(anchors, anchors[1:] + anchors[:1]):
        subdivide(point(*first[:2]), point(*first[4:6]), point(*second[2:4]),
                  point(*second[:2]), first[6] * feather, second[6] * feather)
    return output


def _segments(points):
    return list(zip(points, points[1:] + points[:1]))


def sample_coverage(params, width, height, x, y):
    """Dependency-free independent point reference (no antialias averaging)."""
    points = flatten_path(params, width, height)
    inside, coverage = False, 1.0
    for a, b in _segments(points):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if (a[1] > y) != (b[1] > y) and x < a[0] + dx * (y - a[1]) / dy:
            inside = not inside
        length = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((x-a[0])*dx+(y-a[1])*dy)/length)) if length > 1e-20 else 0.0
        radius = a[2] + (b[2]-a[2]) * t
        if radius > 1e-9:
            distance = math.hypot(x-a[0]-t*dx, y-a[1]-t*dy)
            coverage = min(coverage, distance / radius)
    value = min(1.0, max(0.0, coverage)) if inside else 0.0
    return 1-value if params["invert"] else value


def raster_rows(params, width, height):
    """Yield native little-endian uint16 rows; temporary grids use <=64 rows.

    Numpy accelerates only numeric tiles. The scanline fill uses the even-odd
    rule, including self intersections. No document text becomes executable.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Bezier rendering needs NumPy in the CINEMATICUM imaging runtime.") from exc
    if (type(width) is not int or type(height) is not int or min(width, height) < 2
            or max(width, height) > 8192 or width * height > MAX_RASTER_PIXELS):
        raise ValueError("Bezier raster dimensions exceed the supported canvas.")
    edges = _segments(flatten_path(params, width, height))
    count_x = width * 2
    sample_x = (np.arange(count_x, dtype=np.float64) + .5) * .5
    for top in range(0, height, 64):
        rows = min(64, height-top)
        sample_y = top + (np.arange(rows*2, dtype=np.float64) + .5) * .5
        inside = np.zeros((rows*2, count_x), dtype=np.bool_)
        for row, y in enumerate(sample_y):
            crossings = sorted(a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1])
                               for a, b in edges if (a[1] > y) != (b[1] > y))
            for left, right in zip(crossings[::2], crossings[1::2]):
                start = max(0, min(count_x, math.ceil(2*left-.5)))
                end = max(0, min(count_x, math.ceil(2*right-.5)))
                inside[row, start:end] = True
        coverage = np.ones((rows*2, count_x), dtype=np.float64)
        for a, b in edges:
            radius = max(a[2], b[2])
            if radius <= 1e-9:
                continue
            x0 = max(0, min(count_x, math.ceil(2*(min(a[0], b[0])-radius)-.5)))
            x1 = max(0, min(count_x, math.floor(2*(max(a[0], b[0])+radius)-.5)+1))
            y0 = max(0, min(rows*2, math.ceil(2*(min(a[1], b[1])-radius-top)-.5)))
            y1 = max(0, min(rows*2, math.floor(2*(max(a[1], b[1])+radius-top)-.5)+1))
            if x0 >= x1 or y0 >= y1:
                continue
            x, y = sample_x[None, x0:x1], sample_y[y0:y1, None]
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = dx*dx+dy*dy
            t = np.clip(((x-a[0])*dx+(y-a[1])*dy)/max(length, 1e-20), 0, 1)
            feather = a[2]+(b[2]-a[2])*t
            distance = np.hypot(x-a[0]-t*dx, y-a[1]-t*dy)
            value = np.divide(distance, feather, out=np.ones_like(distance), where=feather > 1e-9)
            target = coverage[y0:y1, x0:x1]
            np.minimum(target, value, out=target)
        coverage *= inside
        pixels = np.clip(coverage.reshape(rows, 2, width, 2).mean(axis=(1, 3)), 0, 1)
        if params["invert"]:
            pixels = 1-pixels
        data = np.floor(pixels*65535+.5).astype("<u2")
        for row in data:
            yield row.tobytes()


def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag+data) & 0xffffffff)


def write_png(path, params, width, height):
    from array import array
    compressor = zlib.compressobj(6)
    with Path(path).open("wb") as output:
        output.write(b"\x89PNG\r\n\x1a\n")
        output.write(_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 16, 0, 0, 0, 0)))
        for row in raster_rows(params, width, height):
            values = array("H"); values.frombytes(row)
            if sys.byteorder == "little":
                values.byteswap()
            data = compressor.compress(b"\0"+values.tobytes())
            if data:
                output.write(_chunk(b"IDAT", data))
        output.write(_chunk(b"IDAT", compressor.flush()))
        output.write(_chunk(b"IEND", b""))


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for data in iter(lambda: source.read(1024*1024), b""):
            result.update(data)
    return result.hexdigest()


def _worker_main():
    # -I omits this script's directory; load only its own sibling implementation.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from compositor import node_params_at, validate_graph
    directory = Path(sys.argv[2]).resolve(strict=True)
    raw = sys.stdin.buffer.read(1024*1024+1)
    if len(raw) > 1024*1024:
        raise ValueError("Bezier request exceeds its size limit.")
    request = json.loads(raw)
    if not isinstance(request, dict) or set(request) != {"version", "node", "width", "height", "frame_offset", "frame_count", "animation_start", "animation_duration", "rate"} or request["version"] != 1:
        raise ValueError("Invalid Bezier worker request.")
    source = {"id":"source", "type":"source", "inputs":[], "params":{}}
    node = dict(request["node"]); node["id"] = "roto"; node["inputs"] = ["source"]
    node = validate_graph({"version":1,"nodes":[source,node],"output":"roto"},
                          request["width"], request["height"],
                          animation_start=request["animation_start"], animation_duration=request["animation_duration"])["nodes"][1]
    if node["type"] != "mask" or node["params"]["shape"] != "bezier":
        raise ValueError("Expected an authored Bezier mask.")
    width, height, count, offset = (request[k] for k in ("width", "height", "frame_count", "frame_offset"))
    if any(type(x) is not int for x in (width,height,count,offset)) or count < 1 or count > 1296000 or abs(offset) > 1296000 or offset+count > 1296000:
        raise ValueError("Invalid Bezier frame range.")
    from fractions import Fraction
    rate = Fraction(request["rate"])
    if not 1 <= rate <= 60:
        raise ValueError("Invalid Bezier frame rate.")
    animated = any(keys for name,keys in node.get("animation",{}).items() if name != "points")
    static = not animated or count == 1
    path = directory/("mask.png" if static else "mask.nut")
    if path.exists() or path.is_symlink():
        raise ValueError("Bezier worker output already exists.")
    if static:
        write_png(path, node_params_at(node, offset), width, height)
    else:
        executable = shutil.which("ffmpeg")
        if not executable:
            raise ValueError("FFmpeg is required to encode animated Bezier masks.")
        command = [executable,"-hide_banner","-loglevel","error","-nostdin","-n","-threads","2",
                   "-f","rawvideo","-pixel_format","gray16le","-video_size",f"{width}x{height}",
                   "-framerate",str(rate),"-i","pipe:0","-an","-c:v","ffv1","-level","3",
                   "-coder","1","-context","1","-g","1","-threads","2","-pix_fmt","gray16le","-f","nut",str(path)]
        import tempfile
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                for frame in range(count):
                    for row in raster_rows(node_params_at(node, offset+frame), width, height):
                        process.stdin.write(row)
                    if path.is_file() and path.stat().st_size > MAX_OUTPUT_BYTES:
                        raise ValueError("Animated Bezier matte exceeds 4 GiB; split this shot into shorter ranges.")
                process.stdin.close()
                process.wait(timeout=20)
                if process.returncode:
                    errors.seek(0)
                    raise ValueError("Bezier encoder failed: "+errors.read(2048).decode(errors="replace"))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError("Bezier matte exceeds its disk budget.")
    print(json.dumps({"version":1,"request_sha256":hashlib.sha256(raw).hexdigest(),"width":width,"height":height,
                      "frame_count":count,"frame_offset":offset,"rate":str(rate),"static":static,
                      "backend":"numpy-tiled-cubic","file":path.name,"bytes":path.stat().st_size,
                      "sha256":_digest(path),"bit_depth":16,"sampling":2,"flatten_error_pixels":.125}))


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "--render":
            raise ValueError("Use the owned Bezier rendering protocol.")
        _worker_main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)

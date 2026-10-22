"""The display geometry of a still image, using the same decoder as rendering.

JPEG/TIFF EXIF orientation is attached to the *decoded frame*, not necessarily
the container stream. FFmpeg's default autorotation applies that display
matrix, including reflections. Probe one frame, then let FFmpeg apply it once;
never rotate the pixels a second time based on the returned dimensions.
"""
from __future__ import annotations

import json
import math
import subprocess


def _matrix_orientation(value):
    """Recover the eight TIFF isometries when FFmpeg 8 omits frame tags.

    Display matrices use signed 16.16 coefficients in their first two rows.
    Reading both axes distinguishes a mirror from a rotation with the same
    angle. Translation has no effect on the orientation code.
    """
    if not isinstance(value, str):
        return None
    try:
        rows = [[int(cell) for cell in row.split(":", 1)[1].split()]
                for row in value.splitlines() if ":" in row]
        if len(rows) != 3 or any(len(row) != 3 for row in rows):
            return None
        key = (rows[0][0], rows[0][1], rows[1][0], rows[1][1])
        matrices = ((65536, 0, 0, 65536), (-65536, 0, 0, 65536),
                    (-65536, 0, 0, -65536), (65536, 0, 0, -65536),
                    (0, 65536, 65536, 0), (0, 65536, -65536, 0),
                    (0, -65536, -65536, 0), (0, -65536, 65536, 0))
        return next((index + 1 for index, matrix in enumerate(matrices)
                     if all(abs(a - b) <= 1 for a, b in zip(key, matrix))), None)
    except (ValueError, IndexError):
        return None


def still_display_info(path, ffprobe, stream, max_pixels=100_000_000):
    """Return pixel dimensions after FFmpeg autorotation and source provenance.

    Allocation bounds are checked before decoding even a single frame. Only
    orientation metadata is requested, so unrelated EXIF fields are not read
    into the application's metadata. Video stream orientation remains the
    responsibility of the normal container probe.
    """
    width, height = stream.get("width"), stream.get("height")
    if (isinstance(width, bool) or isinstance(height, bool)
            or not isinstance(width, int) or not isinstance(height, int)
            or width < 1 or height < 1 or width * height > max_pixels):
        raise ValueError("Unsupported source image dimensions.")
    try:
        result = subprocess.run(
            [str(ffprobe), "-v", "error", "-threads", "2", "-protocol_whitelist", "file,pipe",
             "-select_streams", "v:0", "-read_intervals", "%+#1", "-show_frames",
             "-show_entries", "frame=width,height:frame_tags=Orientation:frame_side_data=rotation,side_data_type,displaymatrix",
             "-of", "json", str(path)], capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Still-image orientation inspection failed or timed out.") from exc
    if result.returncode:
        raise ValueError("Cannot inspect image orientation: " + result.stderr.decode("utf-8", errors="replace")[-1000:].strip())
    try:
        frames = json.loads(result.stdout).get("frames", [])
        if len(frames) != 1 or not isinstance(frames[0], dict):
            raise ValueError("Expected one decoded still frame.")
        frame = frames[0]
        if frame.get("width") != width or frame.get("height") != height:
            raise ValueError("Still-image dimensions changed during decoding.")
        raw_orientation = frame.get("tags", {}).get("Orientation")
        # Frame display matrices take precedence over stream metadata. This is
        # also what ffmpeg does before its automatic transpose/flip filters.
        matrices = [s for s in frame.get("side_data_list", []) if "rotation" in s]
        if not matrices:
            matrices = [s for s in stream.get("side_data_list", []) if "rotation" in s]
        orientation = int(raw_orientation) if raw_orientation is not None else (
            _matrix_orientation(matrices[-1].get("displaymatrix")) if matrices else 1)
        if orientation is not None and not 1 <= orientation <= 8:
            raise ValueError("Unsupported EXIF orientation.")
        rotation = float(matrices[-1]["rotation"] if matrices else stream.get("tags", {}).get("rotate", 0) or 0)
        if not math.isfinite(rotation):
            raise ValueError("Invalid still-image display rotation.")
        # Reflections are applied by the decoder. Their translation-free
        # display matrix changes the sign of rotation, but not this swap test.
        transpose = abs(abs(rotation) % 180 - 90) < 1e-3
        if orientation not in (None, 1) and not matrices:
            raise ValueError("The installed codec did not expose the EXIF display matrix; update FFmpeg before using this image.")
    except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot determine the image's display orientation: " + str(exc)) from exc
    return {"width": height if transpose else width, "height": width if transpose else height,
            "coded_width": width, "coded_height": height, "exif_orientation": orientation,
            "orientation_applied": "ffmpeg_autorotate", "orientation_transposed": transpose}

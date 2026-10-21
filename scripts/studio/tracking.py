"""Measured point tracks and independent, reversible stabilization motion.

The built-in tracker uses FFmpeg's normalized template correlation. It is not
SAM 2, TAPIR or TAPNext. Imported point tracks use the same explicit frame,
coordinate, source-identity and visibility contract as measured local tracks.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

MAX_TRACK_FRAMES = 480
MAX_MOTION_KEYS = 128
ANALYSIS_EDGE = 384


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be a finite number")
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(label + " is outside the supported range")
    return int(value) if integer else float(value)


def validate_motion(value, animation_start, animation_duration):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("version") != 1 or value.get("mode") != "stabilize":
        raise ValueError("Unsupported tracking motion")
    keys = value.get("keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_MOTION_KEYS:
        raise ValueError("Tracking motion needs 1–128 keys")
    normalized, previous = [], None
    for key in keys:
        if not isinstance(key, dict):
            raise ValueError("Tracking keys must be objects")
        frame = _number(key.get("frame"), "Tracking frame", animation_start, animation_duration - 1, True)
        if previous is not None and frame <= previous:
            raise ValueError("Tracking key frames must be unique and increasing")
        if key.get("interpolation", "linear") != "linear":
            raise ValueError("Measured tracking motion uses linear interpolation")
        normalized.append({"frame": frame, "x": _number(key.get("x"), "Tracking X", -2, 2),
                           "y": _number(key.get("y"), "Tracking Y", -2, 2), "interpolation": "linear"})
        previous = frame
    source = value.get("source", {})
    if not isinstance(source, dict) or len(json.dumps(source, allow_nan=False).encode()) > 16384:
        raise ValueError("Tracking source metadata is invalid or oversized")
    return {"version": 1, "mode": "stabilize", "keys": normalized, "source": copy.deepcopy(source)}


def _identity(project, clip, asset):
    rate = project.get("frame_rate") or {"numerator": project["fps"], "denominator": 1}
    return {"asset_id": asset["id"], "sha256": asset.get("sha256"), "width": asset["width"],
            "height": asset["height"], "clip_id": clip["id"], "in": clip["in"],
            "duration": clip["duration"], "speed": clip["speed"], "reverse": clip["reverse"],
            "animation_offset": clip.get("animation_offset", 0), "frame_rate": copy.deepcopy(rate)}


def _prepare(project, project_dir, clip_id, request):
    if __package__:
        from .engine import validate_project, _media_path
    else:
        from engine import validate_project, _media_path
    project = validate_project(project, project_dir)
    clip = next((c for c in project["clips"] if c["id"] == clip_id), None)
    if clip is None:
        raise ValueError("Select a picture clip to track")
    asset = next(a for a in project["assets"] if a["id"] == clip["asset_id"])
    if asset["kind"] != "video" or clip["track"] < 0:
        raise ValueError("Point tracking requires a video picture clip")
    if not isinstance(request, dict):
        raise ValueError("Tracking settings must be an object")
    first = _number(request.get("frame_start", 0), "First tracking frame", 0, clip["duration"] - 1, True)
    count = _number(request.get("frame_count", min(240, clip["duration"] - first)), "Tracking frame count",
                    1, min(MAX_TRACK_FRAMES, clip["duration"] - first), True)
    window = copy.deepcopy(clip)
    # Conform from the original source origin before selecting integer output
    # frames. Moving the in point would reround half-frame timestamp ties and
    # can measure different pictures from those used by the timeline.
    window["reverse"] = False
    planar = request.get("mode") in {"affine", "projective"}
    factor = min(1, (640 if planar else ANALYSIS_EDGE) / max(asset["width"], asset["height"]))
    width = max(16, int(asset["width"] * factor / 2) * 2)
    height = max(16, int(asset["height"] * factor / 2) * 2)
    return project, clip, asset, _media_path(project_dir, asset["path"]), window, first, count, width, height


def _run(command, directory, label, cancel_event, deadline, output=None, env=None):
    errors = Path(directory) / (label + ".stderr")
    with errors.open("wb") as stderr:
        with (Path(output).open("wb") if output else open('/dev/null', 'wb')) as stdout:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       start_new_session=True, env=env)
            try:
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RuntimeError("Tracking cancelled")
                    if time.monotonic() > deadline:
                        raise RuntimeError("Tracking exceeded its two-minute processing limit; use a shorter range")
                    if errors.stat().st_size > 2 * 1024 * 1024:
                        raise RuntimeError("Tracking engine produced excessive diagnostic output")
                    time.sleep(.025)
                if process.returncode:
                    raise RuntimeError("Tracking engine failed: " + errors.read_text(errors="replace")[-3000:])
            finally:
                if process.poll() is None:
                    try:
                        import os
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=2)
                    except (ProcessLookupError, subprocess.TimeoutExpired):
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=2)


def _decode_first(prepared, directory, cancel_event, deadline):
    if __package__:
        from .engine import _video_timing, _executable
    else:
        from engine import _video_timing, _executable
    if __package__:
        from .timebase import project_rate
    else:
        from timebase import project_rate
    project, clip, asset, source, window, first, count, width, height = prepared
    begin = clip["duration"] - first - count if clip["reverse"] else first
    chain = _video_timing(window, project_rate(project)) + [
        f"trim=start_frame={begin}:end_frame={begin + count}",
        f"scale={width}:{height}:flags=area", "format=yuv420p"]
    if clip["reverse"]:
        # Reverse only the bounded analysis window, after downscaling. This
        # retains exact clip order without buffering the complete source clip.
        chain.append("reverse")
    chain.append("setpts=PTS-STARTPTS")
    output = Path(directory) / "first.yuv"
    command = [_executable("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-threads", "1",
               "-protocol_whitelist", "file,pipe", "-i", str(source), "-vf", ",".join(chain),
               "-map", f"0:{asset['video_stream_index']}", "-frames:v", "1", "-an", "-threads", "1",
               "-pix_fmt", "yuv420p", "-f", "rawvideo", "pipe:1"]
    _run(command, directory, "first-frame", cancel_event, deadline, output)
    data = output.read_bytes()
    if len(data) != width * height * 3 // 2:
        raise ValueError("No complete source frame exists at the selected tracking range")
    return chain, data[:width * height], output


def tracking_frame(project, project_dir, clip_id, request, output, cancel_event=None):
    """Extract the exact conformed seed frame; display coordinates match tracking."""
    if __package__:
        from .engine import _executable
    else:
        from engine import _executable
    prepared = _prepare(project, project_dir, clip_id, request)
    project, clip, asset, source, window, first, count, width, height = prepared
    deadline = time.monotonic() + 120
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cinematicum-track-frame-") as temporary:
        _, _, raw = _decode_first(prepared, temporary, cancel_event, deadline)
        staged = Path(temporary) / "preview.png"
        _run([_executable("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-f", "rawvideo",
              "-pixel_format", "yuv420p", "-video_size", f"{width}x{height}", "-i", str(raw),
              "-frames:v", "1", "-threads", "1", str(staged)], temporary, "preview", cancel_event, deadline)
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Tracking frame cancelled")
        output.write_bytes(staged.read_bytes())
    return {"width": width, "height": height, "frame_start": first, "frame_count": count,
            "source": _identity(project, clip, asset), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def track_clip(project, project_dir, clip_id, request, progress=None, cancel_event=None):
    if isinstance(request, dict) and request.get("mode") in {"affine", "projective"}:
        if __package__:
            from .planar_tracking import track_planar
        else:
            from planar_tracking import track_planar
        return track_planar(project, project_dir, clip_id, request, progress, cancel_event)
    if isinstance(request, dict) and request.get("mode", "point") != "point":
        raise ValueError("Choose point, affine or projective tracking")
    if __package__:
        from .engine import _executable, _quote_filter_path
    else:
        from engine import _executable, _quote_filter_path
    prepared = _prepare(project, project_dir, clip_id, request)
    project, clip, asset, source, window, first, count, width, height = prepared
    x = _number(request.get("x"), "Seed X", 0, 1)
    y = _number(request.get("y"), "Seed Y", 0, 1)
    radius = _number(request.get("radius", 12), "Template radius", 4, min(48, min(width, height) // 2), True)
    threshold = _number(request.get("threshold", .15), "Match tolerance", .001, .5)
    px, py = min(width - 1, x * width), min(height - 1, y * height)
    left, top = min(width - 2 * radius, max(0, round(px) - radius)), min(height - 2 * radius, max(0, round(py) - radius))
    offset_x, offset_y = px - left, py - top
    deadline = time.monotonic() + 120
    with tempfile.TemporaryDirectory(prefix="cinematicum-point-track-") as temporary:
        directory = Path(temporary)
        chain, plane, _ = _decode_first(prepared, directory, cancel_event, deadline)
        pattern = b"".join(plane[(top + row) * width + left:(top + row) * width + left + 2 * radius] for row in range(2 * radius))
        average = sum(pattern) / len(pattern)
        variance = sum((value - average) ** 2 for value in pattern) / len(pattern)
        if variance < 4:
            raise ValueError("Choose a textured feature; the selected patch has insufficient contrast")
        template = directory / "template.pgm"
        template.write_bytes(f"P5\n{2*radius} {2*radius}\n255\n".encode() + pattern)
        metadata = directory / "motion.txt"
        chain += ["metadata=mode=delete", f"find_rect=object='{_quote_filter_path(template)}':threshold={threshold}:mipmaps=1",
                  "metadata=mode=add:key=cinematicum.frame:value=1", f"metadata=mode=print:file='{_quote_filter_path(metadata)}':direct=1"]
        if progress:
            progress(.1)
        _run([_executable("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", "-threads", "1",
              "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", f"0:{asset['video_stream_index']}",
              "-vf", ",".join(chain), "-frames:v", str(count), "-an", "-threads", "1", "-f", "null", "-"],
             directory, "track", cancel_event, deadline)
        if not metadata.is_file() or metadata.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("The tracker returned no valid measurement log")
        measurements, current = {}, None
        for line in metadata.read_text().splitlines():
            match = re.match(r"frame:(\d+)\s+pts:", line)
            if match:
                current = int(match.group(1)); measurements[current] = {}
            elif current is not None and line.startswith("lavfi.rect.") and "=" in line:
                name, value = line.split("=", 1)
                measurements[current][name[11:]] = float(value)
        if set(measurements) != set(range(count)):
            raise ValueError("Tracking did not measure every requested frame")
        samples = []
        for index in range(count):
            measured = measurements[index]
            visible = all(key in measured for key in ("x", "y", "score"))
            samples.append({"frame": first + index, "visible": visible,
                            "x": (measured["x"] + offset_x) / width if visible else None,
                            "y": (measured["y"] + offset_y) / height if visible else None,
                            "confidence": max(0, 1 - measured["score"]) if visible else 0})
        initial = samples[0]
        if not initial["visible"] or abs(initial["x"] * width - px) > 1 or abs(initial["y"] * height - py) > 1:
            raise ValueError("The seed patch is ambiguous; choose a more distinctive feature (measured %s, seed %.3f,%.3f)" %
                             ((initial["x"], initial["y"]), px/width, py/height))
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Tracking cancelled")
        if progress:
            progress(1)
        return {"version": 1, "kind": "point-track", "backend": "ffmpeg-template-correlation",
                "coordinates": "normalized-source-xy-top-left", "source": _identity(project, clip, asset),
                "reference_frame": first, "analysis_width": width, "analysis_height": height,
                "template_radius": radius, "threshold": threshold, "samples": samples,
                "measurement_note": "Confidence is absolute normalized correlation, not an occlusion probability. Repeated textures, rotation, scale changes and occlusion can invalidate this track."}


def validate_track(track, expected_source):
    if not isinstance(track, dict) or track.get("version") != 1 or track.get("kind") != "point-track":
        raise ValueError("Expected a CINEMATICUM point-track JSON object")
    if track.get("coordinates") != "normalized-source-xy-top-left":
        raise ValueError("Point tracks must use normalized source XY coordinates with a top-left origin")
    if track.get("source") != expected_source:
        raise ValueError("The point track belongs to different media, timing or clip content. Track this range again")
    samples = track.get("samples")
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_TRACK_FRAMES:
        raise ValueError("A point track must contain 1–480 measured frames")
    result, previous = [], None
    for sample in samples:
        if not isinstance(sample, dict) or type(sample.get("visible")) is not bool:
            raise ValueError("Every tracking sample needs explicit visibility")
        frame = _number(sample.get("frame"), "Sample frame", 0, expected_source["duration"] - 1, True)
        if previous is not None and frame != previous + 1:
            raise ValueError("Track samples must be contiguous and increasing; do not hide missing frames")
        visible = sample["visible"]
        result.append({"frame": frame, "visible": visible,
                       "x": _number(sample.get("x"), "Track X", 0, 1) if visible else None,
                       "y": _number(sample.get("y"), "Track Y", 0, 1) if visible else None,
                       "confidence": _number(sample.get("confidence", 1 if visible else 0), "Track confidence", 0, 1)})
        previous = frame
    reference = _number(track.get("reference_frame"), "Reference frame", result[0]["frame"], result[-1]["frame"], True)
    return {"version": 1, "kind": "point-track", "backend": str(track.get("backend", "imported"))[:160],
            "coordinates": "normalized-source-xy-top-left", "source": copy.deepcopy(expected_source),
            "reference_frame": reference, "samples": result}


def validate_track_for_clip(project, project_dir, clip_id, track):
    if isinstance(track, dict) and track.get("kind") == "planar-track":
        if __package__:
            from .planar_tracking import validate_planar_for_clip
        else:
            from planar_tracking import validate_planar_for_clip
        return validate_planar_for_clip(project, project_dir, clip_id, track)
    prepared = _prepare(project, project_dir, clip_id, {"frame_count": 1})
    return validate_track(track, _identity(prepared[0], prepared[1], prepared[2]))


def stabilization_motion(project, project_dir, clip_id, track, mode="stabilize"):
    if isinstance(track, dict) and track.get("kind") == "planar-track":
        if __package__:
            from .planar_tracking import planar_motion
        else:
            from planar_tracking import planar_motion
        return planar_motion(project, project_dir, clip_id, track, mode)
    if mode != "stabilize":
        raise ValueError("Corner pinning requires a measured planar track")
    prepared = _prepare(project, project_dir, clip_id, {"frame_count": 1})
    project, clip, asset = prepared[:3]
    track = validate_track(track, _identity(project, clip, asset))
    samples = track["samples"]
    if any(not sample["visible"] for sample in samples):
        raise ValueError("The track loses the feature. Correct or shorten the range before applying stabilization")
    reference = next(sample for sample in samples if sample["frame"] == track["reference_frame"])
    # Time-parametrized simplification: error is measured at each original frame,
    # not by perpendicular distance in XY space (which would discard timing).
    selected = {0, len(samples) - 1}
    pending = [(0, len(samples) - 1)]
    while pending:
        begin, end = pending.pop()
        if end <= begin + 1:
            continue
        a, b = samples[begin], samples[end]
        errors = []
        for index in range(begin + 1, end):
            p = samples[index]; t = (p["frame"] - a["frame"]) / (b["frame"] - a["frame"])
            error = math.hypot((p["x"] - (a["x"] + t * (b["x"] - a["x"]))) * asset["width"],
                               (p["y"] - (a["y"] + t * (b["y"] - a["y"]))) * asset["height"])
            errors.append((error, index))
        error, index = max(errors)
        if error > .5:
            selected.add(index); pending.extend([(begin, index), (index, end)])
        if len(selected) > MAX_MOTION_KEYS:
            raise ValueError("This track needs more than 128 motion keys at half-pixel precision. Use a shorter range")
    offset = clip.get("animation_offset", 0)
    keys = [{"frame": samples[index]["frame"] + offset, "x": reference["x"] - samples[index]["x"],
             "y": reference["y"] - samples[index]["y"], "interpolation": "linear"} for index in sorted(selected)]
    motion = {"version": 1, "mode": "stabilize", "keys": keys,
              "source": {"track_backend": track["backend"], "reference_frame": track["reference_frame"],
                         "reference_point": [reference["x"], reference["y"]],
                         "source": track["source"], "max_simplification_error_pixels": .5,
                         "track_sha256": hashlib.sha256(json.dumps(track, sort_keys=True, allow_nan=False).encode()).hexdigest()}}
    return validate_motion(motion, clip.get("animation_start", 0), clip.get("animation_duration", clip["duration"]))

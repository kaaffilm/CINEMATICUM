"""CINEMATICUM's local, frame-based SDR media compositor.

Timeline positions are integer project frames; source in points may be
fractional after a retimed edit. All end points are exclusive. This
module renders imported media; it never substitutes generated filler for absent
footage or changes a film's issuance status. No shell commands are accepted.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

if __package__:
    from .compositor import compile_graph, validate_graph
    from .timebase import parse_rate, project_rate
    from .tracking import validate_motion
    from .color_pipeline import validate_pipeline, compile_pipeline
else:
    from compositor import compile_graph, validate_graph
    from timebase import parse_rate, project_rate
    from tracking import validate_motion
    from color_pipeline import validate_pipeline, compile_pipeline


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".mpg", ".mpeg", ".mxf"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg", ".aif", ".aiff", ".opus"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS
MAX_TIMELINE_SECONDS = 6 * 60 * 60
INTERPOLATIONS = {"linear", "constant", "ease_in", "ease_out", "ease_in_out"}
ANIMATED_PROPERTIES = {"x": (-4, 4), "y": (-4, 4), "scale": (.02, 4),
                       "opacity": (0, 1), "rotation": (-360, 360), "volume": (0, 4)}
_PROBE_CACHE = OrderedDict()
_PROBE_LOCK = threading.Lock()


class RenderCancelled(RuntimeError):
    """Only this render's child process was cancelled."""


def _executable(name):
    value = shutil.which(name)
    if not value:
        raise ValueError(f"{name} is required. Install FFmpeg with ffprobe before importing or rendering media.")
    return value


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be {'an integer' if integer else 'a number'}.")
    if not math.isfinite(value) or value < low or value > high or (integer and value != int(value)):
        raise ValueError(f"{label} must be {'an integer ' if integer else ''}between {low} and {high}.")
    return int(value) if integer else float(value)


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError(f"{label} must contain 1–128 letters, numbers, underscores or hyphens.")
    return value


def _media_path(project_dir, relative):
    if not isinstance(relative, str) or len(relative) > 1024 or "\x00" in relative or "\\" in relative:
        raise ValueError("Asset path is invalid.")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] != "media":
        raise ValueError("Asset paths must stay inside this project's media directory.")
    root = Path(project_dir).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root / "media") or not target.is_file():
        raise ValueError(f"Media is missing or escapes this project: {relative}")
    if target.suffix.lower() not in MEDIA_EXTENSIONS | {".blend"}:
        raise ValueError(f"Unsupported media file: {relative}")
    return target


def probe_media(path):
    """Inspect an actual local file. Container metadata is never trusted blindly."""
    path = Path(path).resolve()
    if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError("Choose a supported local video, audio or still image file.")
    stat = path.stat()
    cache_key = (str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    with _PROBE_LOCK:
        if cache_key in _PROBE_CACHE:
            _PROBE_CACHE.move_to_end(cache_key)
            return dict(_PROBE_CACHE[cache_key])
    try:
        result = subprocess.run(
            [_executable("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
             "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Media inspection failed or timed out.") from exc
    if result.returncode:
        raise ValueError("Cannot decode media: " + result.stderr[-1800:].strip())
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("ffprobe returned invalid media information.") from exc
    streams = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos and not audios:
        raise ValueError("The file has no decodable picture or audio stream.")
    image = path.suffix.lower() in IMAGE_EXTENSIONS
    video = videos[0] if videos else {}
    if image and not video:
        raise ValueError("The image has no decodable picture stream.")
    primary = video if videos else audios[0]
    duration_values = [primary.get("duration")]
    # Matroska commonly puts stream duration in a DURATION tag instead.
    tag_duration = primary.get("tags", {}).get("DURATION", "")
    if isinstance(tag_duration, str) and re.fullmatch(r"\d+:\d+:\d+(\.\d+)?", tag_duration):
        hours, minutes, seconds = tag_duration.split(":")
        duration_values.append(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    duration_values.append(data.get("format", {}).get("duration"))
    duration = 0.0
    for value in duration_values:
        try:
            candidate = float(value)
            if math.isfinite(candidate) and candidate > 0:
                duration = candidate
                break
        except (ValueError, TypeError):
            pass
    audio_duration = 0.0
    if audios:
        audio_values = [audios[0].get("duration")]
        audio_tag = audios[0].get("tags", {}).get("DURATION", "")
        if isinstance(audio_tag, str) and re.fullmatch(r"\d+:\d+:\d+(\.\d+)?", audio_tag):
            hours, minutes, seconds = audio_tag.split(":")
            audio_values.append(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
        audio_values.extend([data.get("format", {}).get("duration"), duration])
        for value in audio_values:
            try:
                candidate = float(value)
                if math.isfinite(candidate) and candidate > 0:
                    audio_duration = candidate
                    break
            except (ValueError, TypeError):
                pass
    if not image and duration <= 0:
        raise ValueError("Media must have a finite, positive duration.")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    sample_aspect = video.get("sample_aspect_ratio", "1:1")
    try:
        numerator, denominator = map(int, sample_aspect.split(":"))
        if numerator > 0 and denominator > 0:
            width = round(width * numerator / denominator)
    except (ValueError, AttributeError):
        pass
    rotation = float(video.get("tags", {}).get("rotate", 0) or 0)
    for item in video.get("side_data_list", []):
        if "rotation" in item:
            rotation = float(item["rotation"])
    if abs(round(rotation)) % 180 == 90:
        width, height = height, width
    if videos and (width < 1 or height < 1 or width * height > 100_000_000):
        raise ValueError("Unsupported source image dimensions.")
    try:
        frames = int(video.get("nb_frames", 0))
    except (ValueError, TypeError):
        frames = 0
    metadata = {
        "kind": "image" if image else "video" if videos else "audio",
        "duration": 0.0 if image else duration,
        "width": width, "height": height, "has_audio": bool(audios),
        "frames": frames, "codec": video.get("codec_name") or (audios[0].get("codec_name") if audios else None),
        "color_transfer": video.get("color_transfer", "unknown"),
        "fps": video.get("avg_frame_rate", "0/0"),
        "video_stream_index": video.get("index"),
        "audio_stream_index": audios[0].get("index") if audios else None,
        "audio_sample_rate": int(audios[0].get("sample_rate", 0) or 0) if audios else 0,
        "audio_channels": int(audios[0].get("channels", 0) or 0) if audios else 0,
        "audio_duration": audio_duration,
        "size": path.stat().st_size,
    }
    with _PROBE_LOCK:
        _PROBE_CACHE[cache_key] = metadata
        while len(_PROBE_CACHE) > 512:
            _PROBE_CACHE.popitem(last=False)
    return dict(metadata)


def validate_project(project, project_dir):
    """Return a normalized independent project, or fail before render starts."""
    if not isinstance(project, dict) or project.get("version") != 1:
        raise ValueError("Unsupported project format. Expected version 1.")
    p = copy.deepcopy(project)
    p["id"] = _identifier(p.get("id"), "Project id")
    if not isinstance(p.get("name"), str) or not p["name"].strip() or len(p["name"]) > 200:
        raise ValueError("Project name must contain 1–200 characters.")
    rate = project_rate(p)
    p["frame_rate"] = rate.as_dict()
    p["fps"] = fps = rate.fps
    p["width"] = width = _number(p.get("width", 1280), "Width", 16, 8192, True)
    p["height"] = height = _number(p.get("height", 720), "Height", 16, 8192, True)
    if width % 2 or height % 2 or width * height > 33_554_432:
        raise ValueError("Project dimensions must be even, with at most 33.5 million pixels.")
    for key, limit in (("assets", 512), ("clips", 256), ("titles", 128)):
        if not isinstance(p.get(key, []), list) or len(p.get(key, [])) > limit:
            raise ValueError(f"{key} must be a list with at most {limit} items.")
        p.setdefault(key, [])
    tracks = p.setdefault("tracks", [])
    if not isinstance(tracks, list) or len(tracks) > 32:
        raise ValueError("Tracks must be a list with at most 32 items.")
    track_ids = set()
    for track in tracks:
        if not isinstance(track, dict):
            raise ValueError("Invalid track settings.")
        track_id = _number(track.get("id"), "Track id", -16, 15, True)
        if track_id in track_ids:
            raise ValueError("Track ids must be unique.")
        track_ids.add(track_id)
        track["id"] = track_id
        default_name = "A" + str(abs(track_id)) if track_id < 0 else "V" + str(track_id + 1)
        name = track.setdefault("name", default_name)
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or "\x00" in name:
            raise ValueError("Track name must contain 1–100 characters.")
        for flag in ("mute", "solo", "locked"):
            track.setdefault(flag, False)
            if not isinstance(track[flag], bool):
                raise ValueError(f"Track {flag} must be true or false.")
        track["gain"] = _number(track.get("gain", 1), "Track gain", 0, 4)
    assets = {}
    for a in p["assets"]:
        if not isinstance(a, dict):
            raise ValueError("Invalid media asset.")
        ident = _identifier(a.get("id"), "Asset id")
        if ident in assets:
            raise ValueError("Asset ids must be unique.")
        media_path = _media_path(project_dir, a.get("path"))
        if media_path.suffix.lower() == ".blend":
            actual = {"kind": "scene", "duration": 0, "width": 0, "height": 0,
                      "has_audio": False, "size": media_path.stat().st_size}
        else:
            actual = probe_media(media_path)
        if a.get("kind", actual["kind"]) != actual["kind"]:
            raise ValueError(f"Asset {ident} has inconsistent media type.")
        a.update(actual)
        a["name"] = str(a.get("name") or Path(a["path"]).name)[:200]
        assets[ident] = a
    ids = set()
    maximum = rate.max_timeline_frames(MAX_TIMELINE_SECONDS)
    for c in p["clips"]:
        if not isinstance(c, dict):
            raise ValueError("Invalid timeline clip.")
        ident = _identifier(c.get("id"), "Clip id")
        if ident in ids:
            raise ValueError("Clip ids must be unique.")
        ids.add(ident)
        if c.get("asset_id") not in assets:
            raise ValueError(f"Clip {ident} refers to missing media.")
        a = assets[c["asset_id"]]
        if a["kind"] == "scene":
            raise ValueError("Render the Blender scene to a movie before placing it on the timeline.")
        c["track"] = _number(c.get("track", 0), "Track", -16, 15, True)
        if a["kind"] == "audio" and c["track"] >= 0:
            raise ValueError("Audio files belong on an audio track (negative track number).")
        if c["track"] < 0 and not a["has_audio"]:
            raise ValueError("An audio-track clip must contain audio.")
        for key, default, low in (("start", 0, 0), ("duration", rate.frames_for_seconds(1), 1)):
            c[key] = _number(c.get(key, default), f"Clip {key}", low, maximum, True)
        # Edits select a window of the original animation rather than fitting
        # new curves to sampled boundary values. Domain bounds remain fixed
        # through trims, even when a negative-domain key is no longer visible.
        c["animation_start"] = _number(c.get("animation_start", 0), "Animation start", -maximum, 0, True)
        c["animation_duration"] = _number(c.get("animation_duration", c["duration"]), "Animation duration", 1, maximum, True)
        c["animation_offset"] = _number(c.get("animation_offset", 0), "Animation offset", -maximum, maximum, True)
        # Extending a head or tail exposes additional animation coordinates.
        # Expand only the admissible domain; existing keys, interpolation and
        # fade envelopes keep their original coordinates and endpoint holds.
        c["animation_start"] = min(c["animation_start"], c["animation_offset"])
        c["animation_duration"] = _number(max(c["animation_duration"],
            c["animation_offset"] + c["duration"]), "Animation duration", 1, maximum, True)
        # Retime split/trim boundaries can fall between project frames in the
        # source. Timeline starts and durations remain integer project frames.
        c["in"] = _number(c.get("in", 0), "Clip in", 0, maximum)
        c["speed"] = _number(c.get("speed", 1), "Clip speed", .25, 4)
        c.setdefault("reverse", False)
        if not isinstance(c["reverse"], bool):
            raise ValueError("Clip reverse must be true or false.")
        if c["start"] + c["duration"] > maximum:
            raise ValueError("Timeline exceeds the six-hour limit.")
        # Permit only half a project frame of metadata rounding, never a freeze-frame fallback.
        if a["kind"] != "image" and (c["in"] + c["duration"] * c["speed"]) / fps > a["duration"] + 0.5 / fps:
            raise ValueError(f"Clip {ident} extends beyond its source media. Shorten the trim.")
        if a["kind"] == "image" and c["in"]:
            raise ValueError("Still images have no source in point.")
        for key, default, low, high in (("volume", 1, 0, 4), ("opacity", 1, 0, 1),
                                       ("x", 0, -4, 4), ("y", 0, -4, 4),
                                       ("scale", 1, .02, 4), ("rotation", 0, -360, 360)):
            c[key] = _number(c.get(key, default), key, low, high)
        audio = c.setdefault("audio", {})
        if not isinstance(audio, dict):
            raise ValueError("Clip audio settings must be an object.")
        audio["fade_duration"] = _number(audio.get("fade_duration", c["duration"]), "Audio fade duration", 1, maximum, True)
        audio["fade_offset"] = _number(audio.get("fade_offset", 0), "Audio fade offset", -maximum, maximum, True)
        for key in ("fade_in", "fade_out"):
            audio[key] = _number(audio.get(key, 0), f"Audio {key}", 0, audio["fade_duration"], True)
        if audio["fade_in"] + audio["fade_out"] > audio["fade_duration"]:
            raise ValueError("Audio fades cannot overlap beyond their fade duration.")
        audio["pan"] = _number(audio.get("pan", 0), "Audio stereo balance", -1, 1)
        grade = c.setdefault("grade", {})
        effects = c.setdefault("effects", {})
        if not isinstance(grade, dict) or not isinstance(effects, dict):
            raise ValueError("Grade and effects must be objects.")
        for key, default, low, high in (("exposure", 0, -3, 3), ("contrast", 1, 0, 3),
                                       ("saturation", 1, 0, 3), ("temperature", 0, -1, 1)):
            grade[key] = _number(grade.get(key, default), key, low, high)
        for key, high in (("blur", 30), ("sharpen", 3)):
            effects[key] = _number(effects.get(key, 0), key, 0, high)
        effects.setdefault("vignette", False)
        if not isinstance(effects["vignette"], bool):
            raise ValueError("Vignette must be true or false.")
        chroma = effects.setdefault("chroma_key", "")
        if not isinstance(chroma, str) or (chroma and not re.fullmatch(r"#[0-9a-fA-F]{6}", chroma)):
            raise ValueError("Chroma key must be an RGB hex color or empty.")
        keyframes = c.setdefault("keyframes", [])
        if not isinstance(keyframes, list) or len(keyframes) > 128:
            raise ValueError("A clip may contain at most 128 keyframes.")
        seen = set()
        for keyframe in keyframes:
            if not isinstance(keyframe, dict) or set(keyframe) - ({"frame", "interpolation"} | set(ANIMATED_PROPERTIES)):
                raise ValueError("Keyframes support frame, interpolation, x, y, scale, opacity, rotation and volume only.")
            frame = _number(keyframe.get("frame"), "Keyframe position", c["animation_start"], c["animation_duration"] - 1, True)
            if frame in seen:
                raise ValueError("Keyframes on a clip must have distinct positions.")
            seen.add(frame)
            keyframe["frame"] = frame
            interpolation = keyframe.get("interpolation", "linear")
            if not isinstance(interpolation, str) or interpolation not in INTERPOLATIONS:
                raise ValueError("Keyframe interpolation must be linear, constant, ease_in, ease_out or ease_in_out.")
            keyframe["interpolation"] = interpolation
            for key, (low, high) in ANIMATED_PROPERTIES.items():
                if key in keyframe:
                    keyframe[key] = _number(keyframe[key], f"Keyframe {key}", low, high)
        c["keyframes"] = sorted(keyframes, key=lambda k: k["frame"])
        if c.get("tracking") is not None:
            c["tracking"] = validate_motion(c["tracking"], c["animation_start"], c["animation_duration"])
        largest_scale = max([c["scale"]] + [k.get("scale", c["scale"]) for k in keyframes])
        if a["kind"] != "audio":
            fit = min(width / a["width"], height / a["height"])
            working_width, working_height = a["width"] * fit * largest_scale, a["height"] * fit * largest_scale
            working_pixels = working_width * working_height
            if any("rotation" in key for key in keyframes):
                extent = math.ceil(math.hypot(working_width, working_height) / 2) * 2
                working_pixels = max(working_pixels, extent * extent)
            elif c["rotation"]:
                angle = math.radians(c["rotation"])
                rotated_width = abs(working_width * math.cos(angle)) + abs(working_height * math.sin(angle))
                rotated_height = abs(working_width * math.sin(angle)) + abs(working_height * math.cos(angle))
                working_pixels = max(working_pixels, (math.ceil(rotated_width / 2) * 2) * (math.ceil(rotated_height / 2) * 2))
            if working_pixels > 67_108_864:
                raise ValueError("Clip transform exceeds the 67-million-pixel working-image limit. Reduce scale or project dimensions.")
        if c.get("compositor") is not None:
            if c["track"] < 0 or a["kind"] == "audio":
                raise ValueError("Compositor graphs belong to picture clips on video tracks.")
            fitted_width = max(2, int(a["width"] * fit / 2) * 2)
            fitted_height = max(2, int(a["height"] * fit / 2) * 2)
            c["compositor"] = validate_graph(c["compositor"], fitted_width, fitted_height,
                                             animation_duration=c["animation_duration"],
                                             animation_start=c["animation_start"])
        if c.get("color_pipeline") is not None:
            if c["track"] < 0 or a["kind"] == "audio":
                raise ValueError("Color pipelines belong to picture clips on video tracks.")
            c["color_pipeline"] = validate_pipeline(c["color_pipeline"], project_dir)
        if a["kind"] != "audio" and a.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
            raise ValueError("HDR PQ/HLG media needs an explicit SDR conversion. This workspace renders SDR Rec.709.")
    title_ids = set()
    for title in p["titles"]:
        if not isinstance(title, dict):
            raise ValueError("Invalid title.")
        ident = _identifier(title.get("id"), "Title id")
        if ident in title_ids:
            raise ValueError("Title ids must be unique.")
        title_ids.add(ident)
        if not isinstance(title.get("text"), str) or not title["text"] or len(title["text"]) > 4000 or "\x00" in title["text"]:
            raise ValueError("A title must contain 1–4,000 characters.")
        for key, default, low, high, integer in (("start", 0, 0, maximum, True), ("duration", rate.frames_for_seconds(3), 1, maximum, True),
                                               ("x", 0, -2, 2, False), ("y", 0, -2, 2, False),
                                               ("size", 48, 6, 500, True), ("fade", 0, 0, maximum, True)):
            title[key] = _number(title.get(key, default), f"Title {key}", low, high, integer)
        if title["start"] + title["duration"] > maximum or title["fade"] * 2 > title["duration"]:
            raise ValueError("Title timing or fade length is invalid.")
        title.setdefault("color", "#ffffff")
        if not isinstance(title["color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", title["color"]):
            raise ValueError("Title color must be an RGB hex color.")
        if title.get("asset_id") is not None:
            raster = assets.get(title["asset_id"])
            if not raster or raster["kind"] != "image" or Path(raster["path"]).suffix.lower() != ".png":
                raise ValueError("A raster title must refer to an imported PNG image.")
            if raster["width"] != width or raster["height"] != height:
                raise ValueError("Raster title size must match the project canvas. Rebuild the title after changing resolution.")
    return p


def get_capabilities():
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    filters, encoders = set(), set()
    if ffmpeg:
        for flag, target in (("-filters", filters), ("-encoders", encoders)):
            try:
                result = subprocess.run([ffmpeg, "-hide_banner", flag], capture_output=True, text=True, timeout=10)
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) > 1:
                        target.add(parts[1])
            except (OSError, subprocess.SubprocessError):
                pass
    return {"ffmpeg": bool(ffmpeg), "ffprobe": bool(ffprobe),
            "titles": "drawtext" in filters or "overlay" in filters,
            "drawtext": "drawtext" in filters, "raster_titles": "overlay" in filters,
            "h264": "libx264" in encoders,
            "prores": "prores_ks" in encoders, "color_space": "SDR Rec.709",
            "keyframes": list(ANIMATED_PROPERTIES), "interpolations": sorted(INTERPOLATIONS),
            "retime": all(name in filters for name in ("reverse", "areverse", "atempo")),
            "audio_mixer": all(name in filters for name in ("aeval", "afade", "pan", "amix")),
            "waveforms": all(name in filters for name in ("astats", "ametadata", "asetnsamples")),
            "filters": sorted(filters)}


def _decimal(value):
    return format(float(value), ".10g")


def _curve(clip, key, fps, variable="t", *, frame_variable=None, include_base=True):
    """Evaluate a fixed property curve through the clip's selected time window."""
    values = {0: (clip[key], "linear")} if include_base else {}
    for k in clip["keyframes"]:
        if key in k:
            values[k["frame"]] = (k[key], k.get("interpolation", "linear"))
    points = [(frame, value, interpolation) for frame, (value, interpolation) in sorted(values.items())]
    if len(points) == 1:
        return _decimal(points[0][1])
    # Keep key positions and offsets in integer frame units. Converting both
    # to decimal seconds could leave a held segment one frame late at 7/24 s.
    rate = parse_rate(fps)
    # Pictures are sampled at integer project frames. Rounding this coordinate
    # prevents floating point ulps after a split from changing integer scale
    # rounding or the exact boundary of a held segment. Audio supplies its
    # continuous, sample-based frame coordinate explicitly.
    variable = (frame_variable if frame_variable is not None else
                f"(round(({variable})*{rate.expression})+{clip.get('animation_offset', 0)})")
    expression = _decimal(points[-1][1])
    for (start, a, interpolation), (end, b, _) in reversed(list(zip(points, points[1:]))):
        u = f"(({variable}-{_decimal(start)})/{_decimal(end-start)})"
        factor = {"linear": u, "constant": "0", "ease_in": f"({u}*{u})",
                  "ease_out": f"(1-(1-{u})*(1-{u}))",
                  "ease_in_out": f"({u}*{u}*(3-2*{u}))"}[interpolation]
        value = f"({_decimal(a)}+({_decimal(b-a)})*{factor})"
        # Timestamp multiplication can still differ by a few ulps at a key.
        # The tolerance is far below one 48 kHz sample at every accepted fps.
        expression = f"if(lt({variable},{_decimal(end)}-0.0000001),{value},{expression})"
    return f"if(lt({variable},{_decimal(points[0][0])}),{_decimal(points[0][1])},{expression})"


def _fade_curve(clip, fps):
    """Sample-accurate linear fade envelope in its original frame domain."""
    audio = clip["audio"]
    rate = parse_rate(fps)
    position = _audio_frame_coordinate(clip, rate, audio["fade_offset"])
    factors = ["1"]
    if audio["fade_in"]:
        factors.append(f"max(0,{position}/{audio['fade_in']})")
    if audio["fade_out"]:
        factors.append(f"max(0,({audio['fade_duration']}-{position})/{audio['fade_out']})")
    expression = factors[0]
    for factor in factors[1:]:
        expression = f"min({expression},{factor})"
    return expression


def _audio_frame_coordinate(clip, rate, offset):
    """Evaluate the preserved domain on the same sample grid on both sides of a cut."""
    origin = rate.samples_for_frames(clip["start"] - offset)
    local_offset = rate.samples_for_frames(clip["start"]) - origin
    return f"((n+{local_offset})*{rate.numerator}/({rate.denominator}*48000))"


def track_state(project, track_id):
    """Return effective (enabled, audio_gain) without altering the saved mixer."""
    tracks = project.get("tracks", [])
    settings = next((t for t in tracks if t["id"] == track_id), {})
    has_solo = any(t.get("solo", False) for t in tracks if (t["id"] < 0) == (track_id < 0))
    enabled = not settings.get("mute", False) and (not has_solo or settings.get("solo", False))
    return enabled, settings.get("gain", 1.0)


def _tempo_filters(speed):
    """Keep each atempo stage inside [0.5, 2] for quality and build compatibility."""
    factors = []
    while speed < .5:
        factors.append(.5)
        speed /= .5
    while speed > 2:
        factors.append(2)
        speed /= 2
    if abs(speed - 1) > 1e-10:
        factors.append(speed)
    return ["atempo=" + _decimal(value) for value in factors]


def _video_timing(clip, fps):
    rate = parse_rate(fps)
    source_frames = Fraction(str(clip["in"]))
    consumed_frames = clip["duration"] * Fraction(str(clip["speed"]))
    # Keep the frame that overlaps a fractional in point. Trimming by its PTS
    # first would discard it and jump a slowed split forward by a source frame.
    # The fps filter drops earlier frames while retaining the one at time zero.
    # Frame-aligned ticks make every integer edit shift exact. Explicit rounding
    # avoids setpts' truncation toward zero changing half-frame decisions after
    # a fractional split, even when input PTS have only millisecond precision.
    speed = Fraction(str(clip["speed"]))
    speed_expression = f"({speed.numerator}/{speed.denominator})"
    chain = ["setpts=PTS-STARTPTS", f"trim=end={rate.seconds_decimal(source_frames + consumed_frames)}",
             f"settb=expr={rate.conform_time_base}",
             f"setpts=round((PTS-{rate.seconds_expression(source_frames)}/TB)/{speed_expression})",
             f"fps=fps={rate.ffmpeg}:start_time=0:round=near:eof_action=pass", f"trim=end_frame={clip['duration']}"]
    if clip["reverse"]:
        # Reverse after conforming the selected range so splitting a retimed
        # reverse clip preserves its exact output frame sequence.
        chain.extend(["reverse", "setpts=PTS-STARTPTS"])
    return chain


def _quote_filter_path(path):
    # FFmpeg's filter parser consumes backslashes before quotes/colons.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")


def _graph(project, project_dir, temp_dir):
    rate = project_rate(project)
    fps, width, height = rate.fps, project["width"], project["height"]
    frames = max([c["start"] + c["duration"] for c in project["clips"]] +
                 [t["start"] + t["duration"] for t in project["titles"]] + [0])
    if frames < 1:
        raise ValueError("Add footage, audio or a title before rendering.")
    duration = float(rate.seconds_for_frames(frames))
    assets = {a["id"]: a for a in project["assets"]}
    filters = [f"color=c=black:s={width}x{height}:r={rate.ffmpeg},trim=end_frame={frames},format=rgba[canvas0]"]
    filters += [f"anullsrc=r=48000:cl=stereo,atrim=end_sample={rate.samples_for_frames(frames)}[silence]"]
    inputs, audio, canvas = [], ["[silence]"], "canvas0"
    ordered = sorted(((i, clip) for i, clip in enumerate(project["clips"])
                      if track_state(project, clip["track"])[0]),
                     key=lambda item: (item[1]["track"], item[0]))
    for index, (_, clip) in enumerate(ordered):
        asset = assets[clip["asset_id"]]
        source = _media_path(project_dir, asset["path"])
        inputs += ["-threads", "2", "-protocol_whitelist", "file,pipe"]
        if asset["kind"] == "image":
            inputs += ["-loop", "1", "-framerate", rate.ffmpeg]
        inputs += ["-i", str(source)]
        start, length, source_in = clip["start"] / fps, clip["duration"] / fps, clip["in"] / fps
        if clip["track"] >= 0:
            fit = min(width / asset["width"], height / asset["height"])
            base_w, base_h = max(2, asset["width"] * fit), max(2, asset["height"] * fit)
            largest_scale = max([clip["scale"]] + [key["scale"] for key in clip["keyframes"] if "scale" in key])
            scale = _curve(clip, "scale", rate)
            timing = _video_timing(clip, rate)
            if clip.get("color_pipeline") is not None:
                # Decode/white-balance/gamut conversion and creative LUTs feed
                # both the compositor and the direct clip path identically.
                timing += compile_pipeline(clip["color_pipeline"], project_dir, temp_dir,
                                           prefix="color%d" % index)
            chain = timing + [f"scale=w='max(2,trunc({_decimal(base_w)}*({scale})/2)*2)':h='max(2,trunc({_decimal(base_h)}*({scale})/2)*2)':eval=frame:flags=lanczos", "setsar=1"]
            stream = f"{index}:{asset['video_stream_index']}"
            if clip.get("compositor") is not None:
                # Normalize once before the node DAG. All branches share the
                # same geometry/timing, then the existing clip controls apply.
                fitted_width, fitted_height = max(2, int(base_w / 2) * 2), max(2, int(base_h / 2) * 2)
                input_label = f"compositor{index}input"
                filters.append(f"[{stream}]" + ",".join(timing) + ","
                               f"scale={fitted_width}:{fitted_height}:flags=lanczos,"
                               f"setsar=1,format=rgba[{input_label}]")
                clauses, stream = compile_graph(clip["compositor"], input_label, f"compositor{index}",
                                                fps=rate.fps, frame_offset=clip["animation_offset"],
                                                animation_duration=clip["animation_duration"],
                                                animation_start=clip["animation_start"])
                filters.extend(clauses)
                chain = [f"scale=w='max(2,trunc({_decimal(base_w)}*({scale})/2)*2)':"
                         f"h='max(2,trunc({_decimal(base_h)}*({scale})/2)*2)':eval=frame:flags=lanczos", "setsar=1"]
            g, e = clip["grade"], clip["effects"]
            if g["exposure"]:
                chain += [f"exposure=exposure={_decimal(g['exposure'])}"]
            if g["contrast"] != 1 or g["saturation"] != 1:
                chain += [f"eq=contrast={_decimal(g['contrast'])}:saturation={_decimal(g['saturation'])}"]
            if g["temperature"]:
                warm = g["temperature"] * .12
                chain += [f"colorbalance=rs={_decimal(warm)}:rm={_decimal(warm)}:rh={_decimal(warm)}:bs={_decimal(-warm)}:bm={_decimal(-warm)}:bh={_decimal(-warm)}"]
            if e["blur"]:
                chain += [f"gblur=sigma={_decimal(e['blur'])}"]
            if e["sharpen"]:
                chain += [f"unsharp=5:5:{_decimal(e['sharpen'])}:5:5:0"]
            if e["vignette"]:
                chain += ["vignette=angle=PI/5"]
            chain += ["format=rgba"]
            if e["chroma_key"]:
                chain += [f"colorkey=0x{e['chroma_key'][1:]}:0.18:0.08"]
            if clip["rotation"] or any("rotation" in key or "scale" in key for key in clip["keyframes"]):
                # Pixel filters can cache geometry at configuration time. Keep
                # their input canvas fixed through scale animation so a trimmed
                # first frame cannot alter centers, alpha or working bounds.
                pad_width = max(2, int(base_w * largest_scale / 2) * 2)
                pad_height = max(2, int(base_h * largest_scale / 2) * 2)
                chain += [f"pad=w={pad_width}:h={pad_height}:x='(ow-iw)/2':y='(oh-ih)/2':color=black@0:eval=frame"]
            if any("rotation" in key for key in clip["keyframes"]):
                angle = _curve(clip, "rotation", rate)
                # Rotate configures its canvas once. Derive it from the whole
                # preserved scale domain, not from whichever input frame starts
                # this trimmed window; otherwise later scale keys get cropped.
                extent = math.ceil(math.hypot(base_w, base_h) * largest_scale / 2) * 2
                # `none` disables background initialization; it can retain old
                # picture data. Explicit zero alpha makes every frame clean.
                chain += [f"rotate=angle='({angle})*PI/180':ow={extent}:oh={extent}:c=black@0"]
            elif clip["rotation"]:
                angle = math.radians(clip["rotation"])
                rotated_width = math.ceil((abs(base_w * math.cos(angle)) + abs(base_h * math.sin(angle))) * largest_scale / 2) * 2
                rotated_height = math.ceil((abs(base_w * math.sin(angle)) + abs(base_h * math.cos(angle))) * largest_scale / 2) * 2
                chain += [f"rotate={_decimal(angle)}:ow={rotated_width}:oh={rotated_height}:c=black@0"]
            if any("opacity" in k for k in clip["keyframes"]):
                opacity = _curve(clip, "opacity", rate, "T")
                chain += [f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({opacity})'"]
            elif clip["opacity"] != 1:
                chain += [f"colorchannelmixer=aa={_decimal(clip['opacity'])}"]
            # Integer-frame placement avoids a rounded 5/24-second offset
            # becoming 4 ticks when FFmpeg converts the expression to PTS.
            chain += [f"settb=expr={rate.time_base}", f"setpts=PTS+{clip['start']}"]
            filters += [f"[{stream}]" + ",".join(chain) + f"[picture{index}]"]
            x = _curve(clip, "x", rate, f"(t-{rate.seconds_expression(clip['start'])})")
            y = _curve(clip, "y", rate, f"(t-{rate.seconds_expression(clip['start'])})")
            if clip.get("tracking"):
                # Tracking is an additive channel. It never replaces authored
                # position, scale, rotation, opacity or sound automation.
                local_time = f"(t-{rate.seconds_expression(clip['start'])})"
                motion = {"x": 0, "y": 0, "keyframes": clip["tracking"]["keys"],
                          "animation_offset": clip["animation_offset"]}
                dx = _curve(motion, "x", rate, local_time, include_base=False)
                dy = _curve(motion, "y", rate, local_time, include_base=False)
                current_scale = _curve(clip, "scale", rate, local_time)
                angle = f"({_curve(clip, 'rotation', rate, local_time)})*PI/180"
                dx = f"({dx})*max(2,trunc({_decimal(base_w)}*({current_scale})/2)*2)"
                dy = f"({dy})*max(2,trunc({_decimal(base_h)}*({current_scale})/2)*2)"
                x = f"({x})+(({dx})*cos({angle})-({dy})*sin({angle}))/{width}"
                y = f"({y})+(({dx})*sin({angle})+({dy})*cos({angle}))/{height}"
            next_canvas = f"canvas{index+1}"
            filters += [f"[{canvas}][picture{index}]overlay=x='(W-w)/2+W*({x})':y='(H-h)/2+H*({y})':"
                        f"enable='gte(t*{rate.expression},{clip['start']}-0.0000001)*lt(t*{rate.expression},{clip['start']+clip['duration']}-0.0000001)':eof_action=pass:repeatlast=0:format=auto[{next_canvas}]"]
            canvas = next_canvas
        track_gain = track_state(project, clip["track"])[1]
        largest_volume = max([clip["volume"]] + [k["volume"] for k in clip["keyframes"] if "volume" in k])
        if asset["has_audio"] and largest_volume > 0 and track_gain > 0:
            delay = rate.samples_for_frames(clip["start"])
            samples = rate.sample_span(clip["start"], clip["duration"])
            speed = Fraction(str(clip["speed"]))
            # Place every cut on the absolute project sample grid. Independent
            # duration rounding would add/drop a sample at many 29.97/59.94 cuts.
            phase = delay - rate.seconds_for_frames(clip["start"]) * 48000
            source_position = rate.seconds_for_frames(clip["in"]) * 48000
            source_samples = round(samples * speed)
            if clip["reverse"]:
                source_end = round(source_position + rate.seconds_for_frames(clip["duration"] * speed) * 48000 - phase * speed)
                source_begin = source_end - source_samples
            else:
                source_begin = round(source_position + phase * speed)
                source_end = source_begin + source_samples
            source_begin = max(0, source_begin)
            chain = ["asetpts=PTS-STARTPTS", "aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo",
                     f"atrim=start_sample={source_begin}:end_sample={source_end}", "asetpts=PTS-STARTPTS"]
            if clip["reverse"]:
                chain.append("areverse")
            chain.extend(_tempo_filters(clip["speed"]))
            # Tempo filters can finish a short analysis window early. Pad only
            # that resampler tail and constrain the clip to its exact duration.
            chain.extend([f"apad=whole_len={samples}", f"atrim=end_sample={samples}", "asetpts=PTS-STARTPTS"])
            audio_settings = clip["audio"]
            if any("volume" in key for key in clip["keyframes"]) or audio_settings["fade_in"] or audio_settings["fade_out"]:
                coordinate = _audio_frame_coordinate(clip, rate, clip.get("animation_offset", 0))
                gain = f"({_curve(clip, 'volume', rate, frame_variable=coordinate)})*{_decimal(track_gain)}"
                if audio_settings["fade_in"] or audio_settings["fade_out"]:
                    gain += f"*({_fade_curve(clip, rate)})"
                chain.append(f"aeval=exprs='val(0)*({gain})|val(1)*({gain})':channel_layout=stereo")
            else:
                chain.append(f"volume={_decimal(clip['volume'] * track_gain)}")
            if audio_settings["pan"]:
                left = min(1, 1 - audio_settings["pan"])
                right = min(1, 1 + audio_settings["pan"])
                chain.append(f"pan=stereo|c0={_decimal(left)}*c0|c1={_decimal(right)}*c1")
            chain.append(f"adelay={delay}S:all=1")
            filters += [f"[{index}:{asset['audio_stream_index']}]" + ",".join(chain) + f"[audio{index}]"]
            audio.append(f"[audio{index}]")
    for index, title in enumerate(project["titles"]):
        start, end, fade = title["start"] / fps, (title["start"] + title["duration"]) / fps, title["fade"] / fps
        if title.get("asset_id") is not None:
            # Browsers rasterize editable text using their installed font engine.
            # Its full-canvas PNG already contains the requested position/style.
            # Timing and opacity fades stay frame-based in this compositor.
            raster = assets[title["asset_id"]]
            source = _media_path(project_dir, raster["path"])
            input_index = len(ordered) + sum(1 for t in project["titles"][:index] if t.get("asset_id") is not None)
            inputs += ["-threads", "2", "-protocol_whitelist", "file,pipe", "-loop", "1", "-framerate", rate.ffmpeg, "-i", str(source)]
            chain = [f"trim=end_frame={title['duration']}", "setpts=PTS-STARTPTS", "format=rgba", "setsar=1"]
            if fade:
                chain += [f"fade=t=in:st=0:d={_decimal(fade)}:alpha=1",
                          f"fade=t=out:st={_decimal(end-start-fade)}:d={_decimal(fade)}:alpha=1"]
            chain += [f"settb=expr={rate.time_base}", f"setpts=PTS+{title['start']}"]
            filters += [f"[{input_index}:{raster['video_stream_index']}]" + ",".join(chain) + f"[raster{index}]"]
            output = f"title{index}"
            filters += [f"[{canvas}][raster{index}]overlay=x=0:y=0:"
                        f"enable='gte(t*{rate.expression},{title['start']}-0.0000001)*lt(t*{rate.expression},{title['start']+title['duration']}-0.0000001)':eof_action=pass:repeatlast=0:format=auto[{output}]"]
            canvas = output
            continue
        filename = Path(temp_dir) / f"title-{index}.txt"
        filename.write_text(title["text"], encoding="utf-8")
        alpha = "1" if not fade else f"min(1,min((t-{_decimal(start)})/{_decimal(fade)},({_decimal(end)}-t)/{_decimal(fade)}))"
        output = f"title{index}"
        filters += [f"[{canvas}]drawtext=textfile='{_quote_filter_path(filename)}':expansion=none:"
                    f"fontcolor={title['color']}:fontsize={title['size']}:"
                    f"x='(w-tw)/2+w*{_decimal(title['x'])}':y='(h-th)/2+h*{_decimal(title['y'])}':"
                    f"alpha='{alpha}':enable='gte(t*{rate.expression},{title['start']}-0.0000001)*lt(t*{rate.expression},{title['start']+title['duration']}-0.0000001)'[{output}]"]
        canvas = output
    filters += [f"[{canvas}]trim=end_frame={frames},setpts=PTS-STARTPTS,scale=out_color_matrix=bt709:out_range=tv[vout]"]
    filters += ["".join(audio) + f"amix=inputs={len(audio)}:duration=longest:normalize=0,"
                f"alimiter=limit=0.98:level=false:latency=true,atrim=end_sample={rate.samples_for_frames(frames)},asetpts=PTS-STARTPTS[aout]"]
    return inputs, ";\n".join(filters), frames


def render_project(project, project_dir, output_path, profile="h264", progress=None, cancel_event=None):
    """Render actual inputs and atomically replace output only after verification.

    progress receives a fraction from 0 to 1. Cancellation terminates only this
    subprocess. H.264 exports contain stereo 48 kHz AAC; ProRes uses PCM audio.
    """
    if profile not in {"preview", "h264", "prores"}:
        raise ValueError("Unknown render profile.")
    p = validate_project(project, project_dir)
    caps = get_capabilities()
    if not caps["ffmpeg"] or not caps["ffprobe"]:
        raise ValueError("FFmpeg and ffprobe are required to render.")
    if any(t.get("asset_id") is None for t in p["titles"]) and not caps["drawtext"]:
        raise ValueError("This FFmpeg build has no drawtext filter. Save the title in the editor to rasterize its text before rendering.")
    if not caps["prores" if profile == "prores" else "h264"]:
        raise ValueError(f"This FFmpeg build does not include the {profile} encoder.")
    output = Path(output_path).resolve()
    if output.suffix.lower() != (".mov" if profile == "prores" else ".mp4"):
        raise ValueError("Use .mov for ProRes or .mp4 for H.264/preview output.")
    # Never permit an output path to replace an imported source.
    if any(output == _media_path(project_dir, a["path"]) for a in p["assets"]):
        raise ValueError("An export cannot overwrite source media.")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.stem}-{uuid.uuid4().hex}.partial{output.suffix}")
    process = None
    reader = None
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="cinematicum-render-") as temp_dir:
            inputs, graph, frames = _graph(p, project_dir, temp_dir)
            rate = project_rate(p)
            duration = float(rate.seconds_for_frames(frames))
            graph_path = Path(temp_dir) / "filter.txt"
            graph_path.write_text(graph, encoding="utf-8")
            command = [_executable("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-filter_complex_threads", "1"]
            command += inputs + ["-filter_complex_script", str(graph_path), "-map", "[vout]", "-map", "[aout]",
                                 "-r", rate.ffmpeg, "-t", rate.seconds_decimal(frames), "-threads", "2"]
            # The graph itself limits the picture count. A second -frames:v
            # limit can stop muxing before the audio limiter flushes its final
            # 239 samples. A 48 kHz movie clock also preserves AAC edit-list
            # duration instead of rounding it to the MOV default millisecond.
            if profile == "prores":
                command += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le"]
            else:
                command += ["-c:v", "libx264", "-preset", "veryfast" if profile == "preview" else "medium",
                            "-crf", "26" if profile == "preview" else "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
            command += ["-ar", "48000", "-ac", "2", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                        "-movie_timescale", "48000", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(partial)]
            with tempfile.TemporaryFile(mode="w+b") as error_log:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_log, text=True, bufsize=1)
                messages = queue.Queue()
                def read_progress():
                    try:
                        for line in process.stdout:
                            messages.put(line)
                    finally:
                        messages.put(None)
                reader = threading.Thread(target=read_progress, daemon=True)
                reader.start()
                if progress:
                    progress(0.0)
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise RenderCancelled("Render cancelled; source media and completed exports are unchanged.")
                    try:
                        message = messages.get(timeout=.2)
                    except queue.Empty:
                        if process.poll() is not None:
                            break
                        continue
                    if message is None:
                        break
                    if message.startswith("out_time_us=") and progress:
                        try:
                            progress(min(.99, max(0, int(message.split("=", 1)[1]) / 1_000_000 / duration)))
                        except ValueError:
                            pass
                result = process.wait()
                reader.join(timeout=1)
                process.stdout.close()
                if result:
                    error_log.seek(0, os.SEEK_END)
                    size = error_log.tell()
                    error_log.seek(max(0, size - 6000))
                    detail = error_log.read().decode("utf-8", errors="replace").strip()
                    raise RuntimeError("FFmpeg render failed: " + detail)
            actual = probe_media(partial)
            if actual["width"] != p["width"] or actual["height"] != p["height"] or not actual["has_audio"]:
                raise RuntimeError("Rendered media does not match the requested picture/audio format.")
            try:
                actual_rate = Fraction(actual["fps"])
            except (ValueError, ZeroDivisionError, TypeError) as exc:
                raise RuntimeError("Rendered media has no verifiable frame rate.") from exc
            if actual_rate != rate.fraction:
                raise RuntimeError("Rendered media does not preserve the exact project frame rate.")
            if actual["frames"] and actual["frames"] != frames:
                raise RuntimeError("Rendered media has an unexpected frame count.")
            if abs(actual["duration"] - duration) > max(.1, 1 / p["fps"]):
                raise RuntimeError("Rendered media has an unexpected duration.")
            expected_audio = rate.samples_for_frames(frames) / 48000
            if abs(actual["audio_duration"] - expected_audio) > 2 / 48000:
                raise RuntimeError("Rendered audio does not preserve the exact timeline sample duration.")
            digest = hashlib.sha256()
            with partial.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            os.replace(partial, output)
            if progress:
                progress(1.0)
            return {"path": str(output), "sha256": digest.hexdigest(), "duration": duration,
                    "width": p["width"], "height": p["height"], "fps": p["fps"], "frame_rate": rate.as_dict(), "frames": frames,
                    "size": output.stat().st_size, "profile": profile, "color_space": "SDR Rec.709",
                    "elapsed_seconds": round(time.monotonic() - started, 3), "has_audio": True,
                    "issuance_status_changed": False}
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if reader is not None:
            reader.join(timeout=1)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        partial.unlink(missing_ok=True)

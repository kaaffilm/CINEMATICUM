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
    from .compositor import (compile_graph, validate_graph, media_sources, validate_media_sources, lens_nodes, LENS_MAP_NAMES,
                            roto_nodes, HIGH16_FILTERS, high16_geq, high16_grade, high16_place, high16_source_over, high16_associate, high16_unassociate, high16_source_conversion)
    from .projective_warp import validate_planar_motion, compile_planar_warp
    from .lens_assets import prepare_lens_maps
    from .roto_assets import prepare_roto_mask
    from .timebase import parse_rate, project_rate
    from .tracking import validate_motion
    from .color_pipeline import validate_pipeline, compile_pipeline
    from .media_orientation import still_display_info
else:
    from compositor import (compile_graph, validate_graph, media_sources, validate_media_sources, lens_nodes, LENS_MAP_NAMES,
                           roto_nodes, HIGH16_FILTERS, high16_geq, high16_grade, high16_place, high16_source_over, high16_associate, high16_unassociate, high16_source_conversion)
    from projective_warp import validate_planar_motion, compile_planar_warp
    from lens_assets import prepare_lens_maps
    from roto_assets import prepare_roto_mask
    from timebase import parse_rate, project_rate
    from tracking import validate_motion
    from color_pipeline import validate_pipeline, compile_pipeline
    from media_orientation import still_display_info


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".mpg", ".mpeg", ".mxf"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg", ".aif", ".aiff", ".opus"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".exr"}
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
            return copy.deepcopy(_PROBE_CACHE[cache_key])
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

    def tick_duration(stream):
        # FFprobe's decimal duration is rounded (80/24 becomes 3.333333).
        # Preserve AVStream's integer duration in its rational time base before
        # converting once to seconds, so a real last frame remains available.
        ticks, base = stream.get("duration_ts"), stream.get("time_base")
        if isinstance(ticks, str) and re.fullmatch(r"[0-9]{1,19}", ticks):
            ticks = int(ticks)
        if isinstance(ticks, bool) or not isinstance(ticks, int) or not 0 < ticks < 2 ** 63:
            return None
        if not isinstance(base, str) or not re.fullmatch(r"[1-9][0-9]{0,9}/[1-9][0-9]{0,9}", base):
            return None
        numerator, denominator = map(int, base.split("/"))
        if numerator >= 2 ** 31 or denominator >= 2 ** 31:
            return None
        return float(Fraction(ticks * numerator, denominator))

    duration_values = [tick_duration(primary), primary.get("duration")]
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
        audio_values = [tick_duration(audios[0]), audios[0].get("duration")]
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
    orientation = None
    if image:
        orientation = still_display_info(path, _executable("ffprobe"), video)
        if orientation["orientation_transposed"]:
            width, height = height, width
    elif abs(round(rotation)) % 180 == 90:
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
        "pixel_format": video.get("pix_fmt"),
        "color_transfer": video.get("color_transfer", "unknown"),
        "fps": video.get("avg_frame_rate", "0/0"),
        "video_stream_index": video.get("index"),
        "audio_stream_index": audios[0].get("index") if audios else None,
        "audio_sample_rate": int(audios[0].get("sample_rate", 0) or 0) if audios else 0,
        "audio_channels": int(audios[0].get("channels", 0) or 0) if audios else 0,
        "audio_duration": audio_duration,
        "audio_streams": [{"index": stream.get("index"), "channels": int(stream.get("channels", 0) or 0),
                           "container_id": str(stream["id"])[:128] if stream.get("id") is not None else None,
                           "sample_rate": int(stream.get("sample_rate", 0) or 0),
                           "codec": stream.get("codec_name"), "language": stream.get("tags", {}).get("language", ""),
                           "duration": tick_duration(stream) or float(stream.get("duration", 0) or 0) or duration}
                          for stream in audios],
        "size": path.stat().st_size,
    }
    if orientation is not None:
        metadata.update({key: orientation[key] for key in
                         ("coded_width", "coded_height", "exif_orientation", "orientation_applied")})
    with _PROBE_LOCK:
        _PROBE_CACHE[cache_key] = metadata
        while len(_PROBE_CACHE) > 512:
            _PROBE_CACHE.popitem(last=False)
    return copy.deepcopy(metadata)


def _validate_single_project(project, project_dir, sequence_assets=None):
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
    settings = p.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("Project settings must be an object.")
    precision = settings.get("image_precision", "standard8")
    if not isinstance(precision, str) or precision not in {"standard8", "high16"}:
        raise ValueError("Image precision must be standard8 or high16.")
    if not isinstance(settings.get("transparent_background", False), bool):
        raise ValueError("Transparent background must be true or false.")
    if settings.get("transparent_background") and precision != "high16":
        raise ValueError("A transparent movie background requires High 16-bit processing.")
    if precision == "high16" and width * height > 8_388_608:
        raise ValueError("High 16-bit movies support at most 8,388,608 canvas pixels (up to 3840 × 2160).")
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
    if "sequence_duration" in p:
        p["sequence_duration"] = _number(p["sequence_duration"], "Sequence out frame", 0, maximum, True)
    for c in p["clips"]:
        if not isinstance(c, dict):
            raise ValueError("Invalid timeline clip.")
        ident = _identifier(c.get("id"), "Clip id")
        if ident in ids:
            raise ValueError("Clip ids must be unique.")
        ids.add(ident)
        if c.get("sequence_id") is not None:
            if not sequence_assets or c["sequence_id"] not in sequence_assets or c.get("asset_id") is not None:
                raise ValueError(f"Clip {ident} refers to an invalid nested sequence.")
            a = sequence_assets[c["sequence_id"]]
        else:
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
        stream = None
        if audio.get("stream_index") is not None:
            selected_stream = _number(audio["stream_index"], "Source audio stream", 0, 255, True)
            stream = next((item for item in a.get("audio_streams", []) if item["index"] == selected_stream), None)
            if stream is None:
                raise ValueError("The selected audio stream does not exist in this source.")
            if (c["in"] + c["duration"] * c["speed"]) / fps > stream["duration"] + .5 / fps:
                raise ValueError("The clip extends beyond its selected audio stream.")
        if audio.get("channels") is not None:
            channels = audio["channels"]
            count = (stream or {}).get("channels", a.get("audio_channels", 0))
            if not isinstance(channels, list) or len(channels) != 2 or any(type(value) is not int or not 0 <= value < count for value in channels):
                raise ValueError("Map exactly two output channels to existing zero-based source channels.")
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
        if c.get("planar_motion") is not None:
            if c["track"] < 0 or a["kind"] == "audio":
                raise ValueError("Planar transforms belong to picture clips.")
            c["planar_motion"] = validate_planar_motion(c["planar_motion"], c["animation_start"], c["animation_duration"])
        largest_scale = max([c["scale"]] + [k.get("scale", c["scale"]) for k in keyframes])
        if a["kind"] != "audio":
            layout = c["planar_motion"]["canvas"] if c.get("planar_motion", {}).get("mode") == "corner_pin" else a
            fit = min(width / layout["width"], height / layout["height"])
            working_width, working_height = layout["width"] * fit * largest_scale, layout["height"] * fit * largest_scale
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
            if precision == "high16" and working_pixels > 16_777_216:
                raise ValueError("High 16-bit clip transforms support at most 16,777,216 working pixels. Reduce scale or rotation bounds.")
        if c.get("compositor") is not None:
            if c["track"] < 0 or a["kind"] == "audio":
                raise ValueError("Compositor graphs belong to picture clips on video tracks.")
            fitted_width = max(2, int(layout["width"] * fit / 2) * 2)
            fitted_height = max(2, int(layout["height"] * fit / 2) * 2)
            c["compositor"] = validate_graph(c["compositor"], fitted_width, fitted_height,
                                             animation_duration=c["animation_duration"],
                                             animation_start=c["animation_start"], precision=precision)
            validate_media_sources(c["compositor"], assets, fps)
        if Path(a["path"]).suffix.lower() == ".exr":
            raise ValueError("Develop this EXR through OCIO before adding its display image to the timeline. The float original stays preserved.")
        if c.get("color_pipeline") is not None:
            if c["track"] < 0 or a["kind"] == "audio":
                raise ValueError("Color pipelines belong to picture clips on video tracks.")
            c["color_pipeline"] = validate_pipeline(c["color_pipeline"], project_dir)
        if a["kind"] != "audio" and a.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
            raise ValueError("HDR PQ/HLG media needs an explicit SDR conversion. This workspace renders SDR Rec.709.")
        if "learned_recipe" in c or "learned_bindings" in c:
            if __package__:
                from .learned_tracking import validate_recipe, validate_learned_bindings
            else:
                from learned_tracking import validate_recipe, validate_learned_bindings
            if "learned_recipe" in c:
                c["learned_recipe"] = validate_recipe(c["learned_recipe"])
            if "learned_bindings" in c:
                c["learned_bindings"] = validate_learned_bindings(c["learned_bindings"], p, c, assets)
    if any(c.get("planar_motion") is not None for c in p["clips"]):
        if __package__:
            from .planar_tracking import validate_planar_binding
        else:
            from planar_tracking import validate_planar_binding
        for c in p["clips"]:
            if c.get("planar_motion") is not None:
                validate_planar_binding(c["planar_motion"], p, c, assets)
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
    if "caption_style" in p:
        style = p["caption_style"]
        if not isinstance(style, dict) or set(style) - {"size", "color", "y", "burn_in"}:
            raise ValueError("Caption style must contain supported appearance fields.")
        if "size" in style:
            style["size"] = _number(style["size"], "Caption size", 6, 500, True)
        if "y" in style:
            style["y"] = _number(style["y"], "Caption position", -2, 2)
        if "color" in style and (not isinstance(style["color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", style["color"])):
            raise ValueError("Caption color must be an RGB hex color.")
        if "burn_in" in style and not isinstance(style["burn_in"], bool):
            raise ValueError("Caption burn-in must be true or false.")
    if "captions" in p or any(title.get("caption_id") is not None for title in p["titles"]):
        if __package__:
            from .editorial import validate_captions
        else:
            from editorial import validate_captions
        p["captions"] = validate_captions(p.get("captions", []), rate, maximum)
        cues = {cue["id"]: cue for cue in p["captions"]}
        plates = set()
        for title in p["titles"]:
            if title.get("caption_id") is not None:
                cue = cues.get(_identifier(title["caption_id"], "Caption plate reference"))
                if not cue or any(title[key] != cue[key] for key in ("start", "duration", "text")):
                    raise ValueError("Caption plates must match their cue timing/text. Edit them through Captions.")
                if cue["id"] in plates:
                    raise ValueError("A caption cue cannot have duplicate burn-in plates.")
                plates.add(cue["id"])
        if p.get("caption_style", {}).get("burn_in") and plates != set(cues):
            raise ValueError("Caption burn-in needs one matching plate per cue. Reapply the caption edit.")
    settings = p.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("Project settings must be an object.")
    if "timecode_mode" in settings:
        mode = settings["timecode_mode"]
        if mode not in ("ndf", "df"):
            raise ValueError("Timecode mode must be ndf or df.")
        if mode == "df":
            if __package__:
                from .timebase import format_timecode
            else:
                from timebase import format_timecode
            format_timecode(0, rate, drop_frame=True)
    if __package__:
        from .studio_tools import validate_authoring_documents
    else:
        from studio_tools import validate_authoring_documents
    return validate_authoring_documents(p, project_dir)


def validate_project(project, project_dir):
    """Validate every owned sequence and its acyclic live dependencies."""
    if not isinstance(project, dict):
        raise ValueError("Project must be an object.")
    if not any(key in project for key in ("sequence_id", "sequence_name", "sequences", "multicam_groups")):
        return _validate_single_project(project, project_dir)
    if project.get("version") != 1:
        raise ValueError("Unsupported project format. Expected version 1.")
    project = copy.deepcopy(project)
    project["width"] = _number(project.get("width", 1280), "Width", 16, 8192, True)
    project["height"] = _number(project.get("height", 720), "Height", 16, 8192, True)
    rate = project_rate(project)
    stored = project.get("sequences", [])
    if not isinstance(stored, list):
        raise ValueError("Stored sequences must be a list.")
    for sequence in [project] + stored:
        if not isinstance(sequence, dict):
            raise ValueError("Stored sequences must be objects.")
        for field, seconds in (("clips", 1), ("titles", 3)):
            items = sequence.get(field, [])
            if not isinstance(items, list):
                raise ValueError("Sequence " + field + " must be a list.")
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Sequence items must be objects.")
                item.setdefault("start", 0)
                item.setdefault("duration", rate.frames_for_seconds(seconds))
    if __package__:
        from .editorial import validate_sequence_graph, sequence_asset, sequence_project, SEQUENCE_FIELDS
    else:
        from editorial import validate_sequence_graph, sequence_asset, sequence_project, SEQUENCE_FIELDS
    views = validate_sequence_graph(project)
    assets = {ident: sequence_asset(project, ident, views) for ident in views}
    normalized = {}
    for ident, sequence in views.items():
        normalized[ident] = _validate_single_project(sequence_project(project, sequence), project_dir, assets)
    active = project.get("sequence_id", "main")
    result = normalized[active]
    result["sequences"] = []
    for ident, value in normalized.items():
        if ident == active:
            continue
        item = {"id": ident, "name": value["sequence_name"]}
        for field in SEQUENCE_FIELDS:
            if field in value:
                item[field] = value[field]
        result["sequences"].append(item)
    groups = result.get("multicam_groups", [])
    if not isinstance(groups, list) or len(groups) > 64:
        raise ValueError("Multicamera groups must be a list of at most 64 entries.")
    group_ids = set()
    media = {asset["id"]: asset for asset in result["assets"]}
    for group in groups:
        if not isinstance(group, dict) or group.get("id") in group_ids:
            raise ValueError("Invalid or duplicate multicamera group.")
        group_ids.add(_identifier(group.get("id"), "Multicamera group id"))
        angles = group.get("angles")
        if not isinstance(angles, list) or not 2 <= len(angles) <= 16:
            raise ValueError("A multicamera group requires 2–16 angles.")
        angle_ids, source_ids = set(), set()
        for angle in angles:
            if not isinstance(angle, dict) or angle.get("id") in angle_ids or angle.get("asset_id") not in media or angle.get("asset_id") in source_ids or media[angle["asset_id"]]["kind"] != "video":
                raise ValueError("A multicamera angle must reference a distinct valid video angle.")
            angle_ids.add(_identifier(angle.get("id"), "Multicamera angle id"))
            source_ids.add(angle["asset_id"])
            # Measured audio offsets retain fractional project-frame positions;
            # timeline edits remain whole frames, while sound stays sample exact.
            source_frame = _number(angle.get("in", 0), "Multicamera source frame", 0, 10_000_000)
            if source_frame >= media[angle["asset_id"]]["duration"] * result["fps"]:
                raise ValueError("A multicamera synchronization point is beyond its source.")
    try:
        from .multicam_sync import validate_group_synchronization
    except ImportError:
        from multicam_sync import validate_group_synchronization
    for group in groups:
        validate_group_synchronization(group, media, project_rate(result))
    group_map = {group["id"]: group for group in groups}
    for value in normalized.values():
        for clip in value["clips"]:
            multicam = clip.get("multicam")
            if multicam is None:
                continue
            if not isinstance(multicam, dict) or not isinstance(multicam.get("group_id"), str):
                raise ValueError("Invalid multicamera clip binding.")
            group = group_map.get(multicam["group_id"])
            angle = next((angle for angle in (group or {}).get("angles", []) if angle["id"] == multicam.get("angle_id")), None)
            if not angle or angle["asset_id"] != clip.get("asset_id"):
                raise ValueError("A multicamera clip must retain its selected angle's source identity.")
    return result


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
            "master16": "ffv1" in encoders and HIGH16_FILTERS <= filters,
            "high_depth_movie": HIGH16_FILTERS <= filters,
            "image_precisions": ["standard8", "high16"] if HIGH16_FILTERS <= filters else ["standard8"],
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


def _video_timing(clip, fps, nested=False):
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
    if nested and speed == 1 and source_frames.denominator == 1:
        chain = [f"trim=start_frame={int(source_frames)}:end_frame={int(source_frames) + clip['duration']}",
                 "setpts=PTS-STARTPTS", f"settb=expr={rate.time_base}"]
        if clip["reverse"]:
            chain.extend(["reverse", "setpts=PTS-STARTPTS"])
        return chain
    # Nested pictures are already an exact project-frame stream. A time-based
    # trim on that coarse time base rounds a fractional end and can discard its
    # overlapping last frame before a slow retime. Count the admitted frames
    # directly; demuxed media keeps its timestamp-based boundary below.
    source_trim = (f"trim=end_frame={math.ceil(source_frames + consumed_frames)}" if nested
                   else f"trim=end={rate.seconds_decimal(source_frames + consumed_frames)}")
    chain = ["setpts=PTS-STARTPTS", source_trim,
             f"settb=expr={rate.conform_time_base}",
             f"setpts=round((PTS-{rate.seconds_expression(source_frames)}/TB)/{speed_expression})",
             f"fps=fps={rate.ffmpeg}:start_time=0:round=near:eof_action=pass", f"trim=end_frame={clip['duration']}"]
    if nested:
        # Filter-produced frames lack the demuxer's end-duration timestamp.
        # Supply one terminal sampling interval; the validated post-conform
        # frame count clips it before any extra picture can enter the edit.
        chain.insert(2, "tpad=stop_mode=clone:stop=1")
    if clip["reverse"]:
        # Reverse after conforming the selected range so splitting a retimed
        # reverse clip preserves its exact output frame sequence.
        chain.extend(["reverse", "setpts=PTS-STARTPTS"])
    return chain


def _quote_filter_path(path):
    # FFmpeg's filter parser consumes backslashes before quotes/colons.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")


def _graph(project, project_dir, temp_dir, cancel_event=None, _context=None, _namespace=""):
    if __package__:
        from .editorial import sequence_views, sequence_project, sequence_asset
    else:
        from editorial import sequence_views, sequence_project, sequence_asset
    if _context is None:
        if __package__:
            from .planar_tracking import verify_planar_source_files
            from .learned_tracking import assert_learned_export_ready, verify_learned_source_files
        else:
            from planar_tracking import verify_planar_source_files
            from learned_tracking import assert_learned_export_ready, verify_learned_source_files
        try:
            verify_planar_source_files(project, project_dir, cancel_event=cancel_event)
            assert_learned_export_ready(project)
            verify_learned_source_files(project, project_dir, cancel_event=cancel_event)
        except RuntimeError:
            if cancel_event is not None and cancel_event.is_set():
                raise RenderCancelled("Planar source verification cancelled")
            raise
        _context = {"next_input": 0, "next_sequence": 0, "root": project, "views": sequence_views(project)}
    rate = project_rate(project)
    fps, width, height = rate.fps, project["width"], project["height"]
    precision = project.get("settings", {}).get("image_precision", "standard8")
    high = precision == "high16"
    rgba_format = "gbrap16le" if high else "rgba"
    frames = max([c["start"] + c["duration"] for c in project["clips"]] +
                 [t["start"] + t["duration"] for t in project["titles"]] +
                 [t["start"] + t["duration"] for t in project.get("captions", [])] + [project.get("sequence_duration", 0)])
    if frames < 1:
        raise ValueError("Add footage, audio or a title before rendering.")
    duration = float(rate.seconds_for_frames(frames))
    assets = {a["id"]: a for a in project["assets"]}
    background = "black@0" if _namespace or project.get("settings", {}).get("transparent_background") else "black"
    filters = [f"color=c={background}:s={width}x{height}:r={rate.ffmpeg},format={rgba_format},trim=end_frame={frames}[canvas0]"]
    filters += [f"anullsrc=r=48000:cl=stereo,atrim=end_sample={rate.samples_for_frames(frames)}[silence]"]
    inputs, audio, canvas = [], ["[silence]"], "canvas0"
    prepared_lenses = {}

    def developed_display(asset):
        provenance = asset.get("provenance")
        return (asset.get("kind") == "image" and Path(asset.get("path", "")).suffix.lower() == ".png"
                and isinstance(provenance, dict) and provenance.get("type") == "cinematicum-imaging"
                and provenance.get("version") == 1 and provenance.get("display_encoding") == "sRGB")

    def add_input(asset):
        source = _media_path(project_dir, asset["path"])
        number = _context["next_input"]
        _context["next_input"] += 1
        inputs.extend(["-threads", "2", "-protocol_whitelist", "file,pipe"])
        if asset["kind"] == "image":
            inputs.extend(["-loop", "1", "-framerate", rate.ffmpeg])
        inputs.extend(["-i", str(source)])
        return number
    ordered = sorted(((i, clip) for i, clip in enumerate(project["clips"])
                      if track_state(project, clip["track"])[0]),
                     key=lambda item: (item[1]["track"], item[0]))
    for index, (_, clip) in enumerate(ordered):
        nested = clip.get("sequence_id") is not None
        if nested:
            asset = sequence_asset(_context["root"], clip["sequence_id"], _context["views"])
            _context["next_sequence"] += 1
            input_index = "__seq" + str(_context["next_sequence"])
            child_dir = Path(temp_dir) / input_index
            child_dir.mkdir()
            child_project = sequence_project(_context["root"], _context["views"][clip["sequence_id"]])
            child_inputs, child_graph, _ = _graph(child_project, project_dir, child_dir, cancel_event,
                                                _context=_context, _namespace=input_index)
            inputs.extend(child_inputs)
            filters.append(child_graph)
        else:
            asset = assets[clip["asset_id"]]
            input_index = add_input(asset)
        start, length, source_in = clip["start"] / fps, clip["duration"] / fps, clip["in"] / fps
        if clip["track"] >= 0:
            layout = clip["planar_motion"]["canvas"] if clip.get("planar_motion", {}).get("mode") == "corner_pin" else asset
            fit = min(width / layout["width"], height / layout["height"])
            base_w, base_h = max(2, layout["width"] * fit), max(2, layout["height"] * fit)
            fitted_width, fitted_height = max(2, int(base_w / 2) * 2), max(2, int(base_h / 2) * 2)
            largest_scale = max([clip["scale"]] + [key["scale"] for key in clip["keyframes"] if "scale" in key])
            scale = _curve(clip, "scale", rate)
            timing = _video_timing(clip, rate, nested=nested)
            if high:
                timing += high16_source_conversion(None if nested else asset.get("pixel_format"))
            if clip.get("color_pipeline") is not None:
                # Decode/white-balance/gamut conversion and creative LUTs feed
                # both the compositor and the direct clip path identically.
                timing += compile_pipeline(clip["color_pipeline"], project_dir, temp_dir,
                                           prefix="color%d" % index, input_unorm16=developed_display(asset), precision=precision)
            if high:
                timing.append("format=gbrap16le")
            if clip.get("planar_motion"):
                timing += compile_planar_warp(clip["planar_motion"], clip["animation_offset"],
                                              fitted_width, fitted_height, pixel_format=rgba_format)
            scaling = [f"scale=w='max(2,trunc({_decimal(base_w)}*({scale})/2)*2)':h='max(2,trunc({_decimal(base_h)}*({scale})/2)*2)':eval=frame:flags=lanczos", "setsar=1"]
            if high:
                # GEQ caches its input geometry. Stabilize the scale domain
                # before any per-pixel alpha/grade operation, not after it.
                if clip["rotation"] or any("rotation" in key or "scale" in key for key in clip["keyframes"]):
                    fixed_width = max(2, int(base_w * largest_scale / 2) * 2)
                    fixed_height = max(2, int(base_h * largest_scale / 2) * 2)
                    scaling += [f"pad=w={fixed_width}:h={fixed_height}:x='(ow-iw)/2':y='(oh-ih)/2':color=black@0:eval=frame"]
                scaling = ["format=gbrap16le", high16_associate()] + scaling + [high16_unassociate()]
            chain = timing + scaling
            stream = f"{input_index}_vout" if nested else f"{input_index}:{asset['video_stream_index']}"
            if clip.get("compositor") is not None:
                # Normalize once before the node DAG. All branches share the
                # same geometry/timing, then the existing clip controls apply.
                input_label = f"compositor{index}input"
                fit_filters = [f"scale={fitted_width}:{fitted_height}:flags=lanczos", "setsar=1", "format=" + rgba_format]
                if high:
                    fit_filters = ["format=gbrap16le", high16_associate()] + fit_filters + [high16_unassociate()]
                filters.append(f"[{stream}]" + ",".join(timing + fit_filters) + f"[{input_label}]")
                external_labels = {}
                for ordinal, node in enumerate(media_sources(clip["compositor"])):
                    external_asset = assets[node["params"]["asset_id"]]
                    external_index = add_input(external_asset)
                    label = f"compositor{index}media{ordinal}"
                    external_labels[node["id"]] = label
                    external_color = high16_source_conversion(external_asset.get("pixel_format")) if high else []
                    if developed_display(external_asset):
                        # The display view is already baked into Develop's PNG.
                        # Match a new direct clip's transfer conversion without
                        # applying another OCIO view or scene tone mapping.
                        external_color += compile_pipeline(
                            {"version": 1, "enabled": True, "input_transfer": "srgb", "input_primaries": "rec709"},
                            project_dir, temp_dir, prefix=f"externalcolor{index}_{ordinal}", input_unorm16=True, precision=precision)
                    # Each node has an independent project-rate source clock.
                    # Preserve zero-origin frame numbers before the DAG trims
                    # its selected range and applies domain offsets/padding.
                    filters.append(f"[{external_index}:{external_asset['video_stream_index']}]"
                                   "setpts=PTS-STARTPTS,"
                                   f"settb=expr={rate.conform_time_base},"
                                   f"fps=fps={rate.ffmpeg}:start_time=0:round=near:eof_action=pass,"
                                   + (",".join(external_color) + "," if external_color else "") +
                                   ("format=gbrap16le," + high16_associate() + "," if high else "") +
                                   f"scale={fitted_width}:{fitted_height}:force_original_aspect_ratio=decrease:flags=lanczos,"
                                   f"format={rgba_format},pad={fitted_width}:{fitted_height}:(ow-iw)/2:(oh-ih)/2:color=black@0,"
                                   + (high16_unassociate() + "," if high else "") +
                                   f"setsar=1[{label}]")
                lens_labels = {}
                for ordinal, node in enumerate(lens_nodes(clip["compositor"])):
                    signature = json.dumps([fitted_width, fitted_height, node["params"]],
                                           sort_keys=True, separators=(",", ":"), allow_nan=False)
                    if signature not in prepared_lenses:
                        try:
                            prepared_lenses[signature] = prepare_lens_maps(
                                node["params"], fitted_width, fitted_height, temp_dir,
                                cancel_event=cancel_event)
                        except RuntimeError:
                            if cancel_event is not None and cancel_event.is_set():
                                raise RenderCancelled("Lens preparation cancelled")
                            raise
                    labels = {}
                    for name in LENS_MAP_NAMES:
                        map_index = _context["next_input"]
                        _context["next_input"] += 1
                        # Decode each static map once, then repeat its frame in
                        # the graph. Image-input looping would decode six large
                        # PNGs on every picture frame.
                        inputs.extend(["-threads", "1", "-protocol_whitelist", "file,pipe",
                                       "-framerate", rate.ffmpeg, "-i",
                                       str(prepared_lenses[signature]["paths"][name])])
                        label = f"compositor{index}lens{ordinal}{name}"
                        labels[name] = label
                        filters.append(f"[{map_index}:v:0]loop=loop={clip['duration'] - 1}:size=1:start=0,"
                                       f"settb=expr={rate.time_base},setpts=N[{label}]")
                    lens_labels[node["id"]] = labels
                roto_labels = {}
                for ordinal, node in enumerate(roto_nodes(clip["compositor"])):
                    matte = prepare_roto_mask(node, fitted_width, fitted_height, temp_dir,
                                              frame_offset=clip["animation_offset"], frame_count=clip["duration"],
                                              animation_start=clip["animation_start"], animation_duration=clip["animation_duration"],
                                              rate=rate.ffmpeg, cancel_event=cancel_event)
                    matte_index = _context["next_input"]
                    _context["next_input"] += 1
                    inputs.extend(["-threads", "1", "-protocol_whitelist", "file,pipe"])
                    if matte["static"]:
                        inputs.extend(["-framerate", rate.ffmpeg])
                    inputs.extend(["-i", str(matte["path"])])
                    label = f"compositor{index}roto{ordinal}"
                    roto_labels[node["id"]] = label
                    repeat = f"loop=loop={clip['duration'] - 1}:size=1:start=0," if matte["static"] else ""
                    filters.append(f"[{matte_index}:v:0]" + repeat + f"settb=expr={rate.time_base},setpts=N,trim=end_frame={clip['duration']}[{label}]")
                clauses, stream = compile_graph(clip["compositor"], input_label, f"compositor{index}",
                                                fps=rate.fps, frame_offset=clip["animation_offset"],
                                                animation_duration=clip["animation_duration"],
                                                animation_start=clip["animation_start"],
                                                frame_count=clip["duration"], external_labels=external_labels,
                                                lens_labels=lens_labels, roto_labels=roto_labels, precision=precision)
                filters.extend(clauses)
                chain = scaling.copy()
            g, e = clip["grade"], clip["effects"]
            if high and any(g[name] != default for name, default in (("exposure", 0), ("contrast", 1), ("saturation", 1), ("temperature", 0))):
                chain += ["format=gbrap16le", high16_grade(*(_decimal(g[name]) for name in ("exposure", "contrast", "saturation", "temperature")))]
            if not high and g["exposure"]:
                chain += [f"exposure=exposure={_decimal(g['exposure'])}"]
            if not high and (g["contrast"] != 1 or g["saturation"] != 1):
                chain += [f"eq=contrast={_decimal(g['contrast'])}:saturation={_decimal(g['saturation'])}"]
            if not high and g["temperature"]:
                warm = g["temperature"] * .12
                chain += [f"colorbalance=rs={_decimal(warm)}:rm={_decimal(warm)}:rh={_decimal(warm)}:bs={_decimal(-warm)}:bm={_decimal(-warm)}:bh={_decimal(-warm)}"]
            if e["blur"]:
                chain += [f"gblur=sigma={_decimal(e['blur'])}" + (":planes=7" if high else "")]
            if e["sharpen"]:
                chain += [f"unsharp=5:5:{_decimal(e['sharpen'])}:5:5:0"]
            if e["vignette"]:
                if high:
                    # Cosine-fourth optical falloff on normalized image radius;
                    # explicit RGB math avoids vignette's rgb24 negotiation.
                    falloff = "pow(cos(min(PI/2,sqrt(pow((X-(W-1)/2)/W,2)+pow((Y-(H-1)/2)/H,2))*PI/5)),4)"
                    chain += ["format=gbrap16le", high16_geq(*(f"{c}(X,Y)*({falloff})" for c in "rgb"))]
                else:
                    chain += ["vignette=angle=PI/5"]
            chain += ["format=" + rgba_format]
            if e["chroma_key"]:
                if high:
                    # Multiply the keyed coverage by source alpha. colorkey
                    # otherwise replaces coverage, exposing hidden source RGB.
                    target = f"clipkey{index}"
                    filters.append(f"[{stream}]" + ",".join(chain) + f"[{target}input]")
                    key_graph = {"version": 1, "nodes": [{"id": "source", "type": "source", "inputs": [], "params": {}},
                        {"id": "key", "type": "chroma_key", "inputs": ["source"], "params": {"color": e["chroma_key"]}}], "output": "key"}
                    key_filters, stream = compile_graph(key_graph, target + "input", target, precision=precision)
                    filters.extend(key_filters)
                    chain = []
                else:
                    chain += [f"colorkey=0x{e['chroma_key'][1:]}:0.18:0.08"]
            picture_width = f"max(2,trunc({_decimal(base_w)}*({_curve(clip, 'scale', rate, 'T')})/2)*2)"
            picture_height = f"max(2,trunc({_decimal(base_h)}*({_curve(clip, 'scale', rate, 'T')})/2)*2)"
            rotates = clip["rotation"] or any("rotation" in key for key in clip["keyframes"])
            if high and rotates:
                chain += ["format=gbrap16le", high16_associate()]
            if clip["rotation"] or any("rotation" in key or "scale" in key for key in clip["keyframes"]):
                # Pixel filters can cache geometry at configuration time. Keep
                # their input canvas fixed through scale animation so a trimmed
                # first frame cannot alter centers, alpha or working bounds.
                pad_width = max(2, int(base_w * largest_scale / 2) * 2)
                pad_height = max(2, int(base_h * largest_scale / 2) * 2)
                if not high:
                    chain += [f"pad=w={pad_width}:h={pad_height}:x='(ow-iw)/2':y='(oh-ih)/2':color=black@0:eval=frame"]
                picture_width, picture_height = str(pad_width), str(pad_height)
            if any("rotation" in key for key in clip["keyframes"]):
                angle = _curve(clip, "rotation", rate)
                # Rotate configures its canvas once. Derive it from the whole
                # preserved scale domain, not from whichever input frame starts
                # this trimmed window; otherwise later scale keys get cropped.
                extent = math.ceil(math.hypot(base_w, base_h) * largest_scale / 2) * 2
                # `none` disables background initialization; it can retain old
                # picture data. Explicit zero alpha makes every frame clean.
                chain += [f"rotate=angle='({angle})*PI/180':ow={extent}:oh={extent}:c=black@0"]
                picture_width = picture_height = str(extent)
            elif clip["rotation"]:
                angle = math.radians(clip["rotation"])
                rotated_width = math.ceil((abs(base_w * math.cos(angle)) + abs(base_h * math.sin(angle))) * largest_scale / 2) * 2
                rotated_height = math.ceil((abs(base_w * math.sin(angle)) + abs(base_h * math.cos(angle))) * largest_scale / 2) * 2
                chain += [f"rotate={_decimal(angle)}:ow={rotated_width}:oh={rotated_height}:c=black@0"]
                picture_width, picture_height = str(rotated_width), str(rotated_height)
            if high and rotates:
                chain += ["format=gbrap16le", high16_unassociate()]
            if any("opacity" in k for k in clip["keyframes"]):
                opacity = _curve(clip, "opacity", rate, "T")
                chain += [high16_geq(alpha=f"alpha(X,Y)*({opacity})") if high else
                          f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({opacity})'"]
            elif clip["opacity"] != 1:
                chain += [f"colorchannelmixer=aa={_decimal(clip['opacity'])}"]
            # Integer-frame placement avoids a rounded 5/24-second offset
            # becoming 4 ticks when FFmpeg converts the expression to PTS.
            if not high:
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
            if high:
                # GEQ runs before timeline padding, so its T is clip-local.
                # The authored/tracking math above uses absolute overlay time.
                absolute = f"(T+{rate.seconds_expression(clip['start'])})"
                local_x, local_y = re.sub(r"\bt\b", absolute, x), re.sub(r"\bt\b", absolute, y)
                high16_place(chain, width, height, picture_width, picture_height, local_x, local_y)
                chain += [f"settb=expr={rate.time_base}", "setpts=N",
                          f"tpad=start={clip['start']}:stop={frames-clip['start']-clip['duration']}:color=black@0",
                          f"trim=end_frame={frames}", "setpts=N"]
                filters.append(f"[{stream}]" + ",".join(chain) + f"[picture{index}]")
                high16_source_over(filters, canvas, f"picture{index}", next_canvas)
            else:
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
            mapping = clip["audio"].get("channels")
            channel_map = [f"pan=stereo|c0=c{mapping[0]}|c1=c{mapping[1]}"] if mapping is not None else []
            chain = ["asetpts=PTS-STARTPTS", "aresample=48000"] + channel_map + ["aformat=sample_fmts=fltp:channel_layouts=stereo",
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
            audio_stream = f"{input_index}_aout" if nested else f"{input_index}:{clip['audio'].get('stream_index', asset['audio_stream_index'])}"
            filters += [f"[{audio_stream}]" + ",".join(chain) + f"[audio{index}]"]
            audio.append(f"[audio{index}]")
        elif nested:
            filters.append(f"[{input_index}_aout]anullsink")
        if nested and clip["track"] < 0:
            filters.append(f"[{input_index}_vout]nullsink")
    for index, title in enumerate(project["titles"]):
        start, end, fade = title["start"] / fps, (title["start"] + title["duration"]) / fps, title["fade"] / fps
        if title.get("asset_id") is not None:
            # Browsers rasterize editable text using their installed font engine.
            # Its full-canvas PNG already contains the requested position/style.
            # Timing and opacity fades stay frame-based in this compositor.
            raster = assets[title["asset_id"]]
            input_index = add_input(raster)
            chain = [f"trim=end_frame={title['duration']}", "setpts=PTS-STARTPTS", "format=" + rgba_format, "setsar=1"]
            if fade:
                if high:
                    chain += [high16_geq(alpha=f"alpha(X,Y)*clip(min(N/{title['fade']},({title['duration']}-N)/{title['fade']}),0,1)")]
                else:
                    chain += [f"fade=t=in:st=0:d={_decimal(fade)}:alpha=1",
                              f"fade=t=out:st={_decimal(end-start-fade)}:d={_decimal(fade)}:alpha=1"]
            if high:
                chain += ["format=gbrap16le", f"settb=expr={rate.time_base}", "setpts=N",
                          f"tpad=start={title['start']}:stop={frames-title['start']-title['duration']}:color=black@0",
                          f"trim=end_frame={frames}", "setpts=N"]
            else:
                chain += [f"settb=expr={rate.time_base}", f"setpts=PTS+{title['start']}"]
            filters += [f"[{input_index}:{raster['video_stream_index']}]" + ",".join(chain) + f"[raster{index}]"]
            output = f"title{index}"
            if high:
                high16_source_over(filters, canvas, f"raster{index}", output)
            else:
                filters += [f"[{canvas}][raster{index}]overlay=x=0:y=0:"
                            f"enable='gte(t*{rate.expression},{title['start']}-0.0000001)*lt(t*{rate.expression},{title['start']+title['duration']}-0.0000001)':eof_action=pass:repeatlast=0:format=auto[{output}]"]
            canvas = output
            continue
        filename = Path(temp_dir) / f"title-{index}.txt"
        filename.write_text(title["text"], encoding="utf-8")
        alpha = "1" if not fade else f"min(1,min((t-{_decimal(start)})/{_decimal(fade)},({_decimal(end)}-t)/{_decimal(fade)}))"
        output = f"title{index}"
        draw = (f"drawtext=textfile='{_quote_filter_path(filename)}':expansion=none:"
                f"fontcolor={title['color']}:fontsize={title['size']}:"
                f"x='(w-tw)/2+w*{_decimal(title['x'])}':y='(h-th)/2+h*{_decimal(title['y'])}':"
                f"alpha='{alpha}':enable='gte(t*{rate.expression},{title['start']}-0.0000001)*lt(t*{rate.expression},{title['start']+title['duration']}-0.0000001)'")
        if high:
            # drawtext's pixel blender writes associated color on a clear
            # plate. Unassociate it before the same source-over kernel used by
            # raster titles; drawing directly into a transparent canvas would
            # otherwise store dark, twice-multiplied antialiased glyph edges.
            straight = high16_unassociate()
            filters.append(f"color=c=black@0:s={width}x{height}:r={rate.ffmpeg},format=gbrap16le,"
                           f"trim=end_frame={frames},{draw},{straight}[{output}plate]")
            high16_source_over(filters, canvas, output + "plate", output)
        else:
            filters.append(f"[{canvas}]{draw}[{output}]")
        canvas = output
    display = ",format=gbrap16le" if high else "" if _namespace else ",scale=out_color_matrix=bt709:out_range=tv"
    filters += [f"[{canvas}]trim=end_frame={frames},setpts=PTS-STARTPTS{display}[vout]"]
    limiter = "" if _namespace else "alimiter=limit=0.98:level=false:latency=true,"
    filters += ["".join(audio) + f"amix=inputs={len(audio)}:duration=longest:normalize=0,"
                + limiter + f"atrim=end_sample={rate.samples_for_frames(frames)},asetpts=PTS-STARTPTS[aout]"]
    graph = ";\n".join(filters)
    if _namespace:
        # Input stream selectors and already-qualified descendants remain global.
        def qualify(match):
            label = match.group(1)
            if re.match(r"^[0-9]+:", label) or label.startswith("__seq"):
                return match.group(0)
            return "[" + _namespace + "_" + label + "]"
        graph = re.sub(r"\[([^]\n]+)\]", qualify, graph)
    return inputs, graph, frames


def _verify_master_packets(path, temp_dir, frames, samples, cancel_event=None):
    """Count FFV1 frames and PCM sample bytes independently of MKV time tags.

    Matroska timestamps have millisecond granularity on these FFmpeg builds;
    comparing its rounded DURATION tag to a 48 kHz sample count is invalid.
    FFV1 encodes one complete picture per packet, and interleaved stereo
    PCM16 encodes exactly four bytes per sample. Stream the packet inventory to
    a temporary file so a six-hour master does not become an in-memory list.
    """
    inventory = Path(temp_dir) / "master-packets.csv"
    with inventory.open("wb") as destination, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([_executable("ffprobe"), "-v", "error", "-show_packets",
            "-show_entries", "packet=stream_index,size", "-of", "csv=p=0", str(path)],
            stdin=subprocess.DEVNULL, stdout=destination, stderr=errors)
        began = time.monotonic()
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise RenderCancelled("Master verification cancelled")
                if time.monotonic() - began > 300:
                    raise RuntimeError("16-bit master packet verification exceeded five minutes.")
                time.sleep(.05)
            if process.returncode:
                raise RuntimeError("Cannot verify the 16-bit master's picture and PCM packets.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    pictures = audio_bytes = 0
    with inventory.open("r", encoding="ascii") as source:
        for line in source:
            fields = line.strip().split(",")
            if len(fields) != 2 or not all(value.isdigit() for value in fields):
                raise RuntimeError("Invalid packet inventory in the 16-bit master.")
            stream, size = map(int, fields)
            if stream == 0:
                pictures += 1
            elif stream == 1:
                audio_bytes += size
            else:
                raise RuntimeError("The 16-bit master contains an unexpected stream.")
    if pictures != frames or audio_bytes != samples * 4:
        raise RuntimeError("The 16-bit master's actual frame/sample counts do not match the timeline.")
    return {"video_packets": pictures, "pcm_samples": samples, "pcm_bytes": audio_bytes}


def render_project(project, project_dir, output_path, profile="h264", progress=None, cancel_event=None):
    """Render actual inputs and atomically replace output only after verification.

    progress receives a fraction from 0 to 1. Cancellation terminates only this
    subprocess. H.264 exports contain stereo 48 kHz AAC; ProRes uses PCM audio.
    """
    if profile not in {"preview", "h264", "prores", "master16"}:
        raise ValueError("Unknown render profile.")
    p = validate_project(project, project_dir)
    if __package__:
        from .planar_tracking import assert_planar_export_ready
        from .learned_tracking import assert_learned_export_ready
    else:
        from planar_tracking import assert_planar_export_ready
        from learned_tracking import assert_learned_export_ready
    assert_planar_export_ready(p)
    assert_learned_export_ready(p)
    high = p.get("settings", {}).get("image_precision", "standard8") == "high16"
    if profile == "master16" and not high:
        raise ValueError("Enable High 16-bit movie processing before exporting a 16-bit master.")
    caps = get_capabilities()
    if not caps["ffmpeg"] or not caps["ffprobe"]:
        raise ValueError("FFmpeg and ffprobe are required to render.")
    if any(t.get("asset_id") is None for t in p["titles"]) and not caps["drawtext"]:
        raise ValueError("This FFmpeg build has no drawtext filter. Save the title in the editor to rasterize its text before rendering.")
    if high and not caps["high_depth_movie"]:
        raise ValueError("This FFmpeg build lacks required high-depth compositor kernels.")
    if not caps[profile if profile in {"prores", "master16"} else "h264"]:
        raise ValueError(f"This FFmpeg build does not include the {profile} encoder.")
    output = Path(output_path).resolve()
    if output.suffix.lower() != (".mov" if profile == "prores" else ".mkv" if profile == "master16" else ".mp4"):
        raise ValueError("Use .mkv for 16-bit lossless masters, .mov for ProRes, or .mp4 for H.264/preview output.")
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
            inputs, graph, frames = _graph(p, project_dir, temp_dir, cancel_event=cancel_event)
            if high and profile != "master16":
                # RGB behind zero alpha must never become visible just because
                # a delivery encoder lacks alpha. Composite against black in
                # high depth, then make the one explicit delivery conversion.
                graph = graph.replace("[vout]", "[deliveryinput]")
                flatten = high16_geq(*(f"{c}(X,Y)*alpha(X,Y)/65535" for c in "rgb"), alpha="65535")
                graph += ";\n[deliveryinput]" + flatten + ",scale=out_color_matrix=bt709:out_range=tv[vout]"
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
            if profile == "master16":
                command += ["-c:v", "ffv1", "-level:v", "3", "-coder:v", "1", "-context:v", "1",
                            "-slicecrc:v", "1", "-pix_fmt", "gbrap16le", "-c:a", "pcm_s16le"]
            elif profile == "prores":
                command += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le"]
            else:
                command += ["-c:v", "libx264", "-preset", "veryfast" if profile == "preview" else "medium",
                            "-crf", "26" if profile == "preview" else "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
            command += ["-ar", "48000", "-ac", "2", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "rgb" if profile == "master16" else "bt709"]
            if profile == "master16":
                command += ["-color_range", "pc"]
            else:
                command += ["-movie_timescale", "48000", "-movflags", "+faststart"]
            command += ["-progress", "pipe:1", "-nostats", str(partial)]
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
            packet_receipt = None
            if profile == "master16":
                if (actual["codec"] != "ffv1" or actual["pixel_format"] != "gbrap16le"
                        or actual["audio_sample_rate"] != 48000 or actual["audio_channels"] != 2
                        or actual["audio_streams"][0]["codec"] != "pcm_s16le"):
                    raise RuntimeError("The master encoder did not preserve 16-bit RGB+alpha and stereo PCM.")
                packet_receipt = _verify_master_packets(partial, temp_dir, frames, rate.samples_for_frames(frames), cancel_event)
            elif abs(actual["audio_duration"] - expected_audio) > 2 / 48000:
                raise RuntimeError("Rendered audio does not preserve the exact timeline sample duration.")
            digest = hashlib.sha256()
            with partial.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    if cancel_event is not None and cancel_event.is_set():
                        raise RenderCancelled("Export verification cancelled; completed exports are unchanged.")
                    digest.update(chunk)
            if cancel_event is not None and cancel_event.is_set():
                raise RenderCancelled("Export verification cancelled; completed exports are unchanged.")
            os.replace(partial, output)
            if progress:
                progress(1.0)
            return {"path": str(output), "sha256": digest.hexdigest(), "duration": duration,
                    "width": p["width"], "height": p["height"], "fps": p["fps"], "frame_rate": rate.as_dict(), "frames": frames,
                    "size": output.stat().st_size, "profile": profile, "color_space": "SDR Rec.709",
                    "image_precision": "high16" if high else "standard8", "processing_bits": 16 if high else 8,
                    "pixel_format": actual["pixel_format"], "encoding": actual["codec"],
                    "alpha_mode": "straight" if profile == "master16" else "opaque",
                    "transparent_background": bool(p.get("settings", {}).get("transparent_background")) and profile == "master16",
                    "dynamic_range": "SDR UNORM; no scene-linear HDR/ACES movie mastering",
                    "packet_verification": packet_receipt,
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

"""CINEMATICUM's local, frame-based SDR media compositor.

All times are integer project frames and all end points are exclusive. This
module renders imported media; it never substitutes generated filler for absent
footage or changes a film's issuance status. No shell commands are accepted.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
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
else:
    from compositor import compile_graph, validate_graph


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".mpg", ".mpeg", ".mxf"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg", ".aif", ".aiff", ".opus"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS
MAX_TIMELINE_SECONDS = 6 * 60 * 60
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
    p["fps"] = fps = _number(p.get("fps", 24), "Frame rate", 1, 60, True)
    p["width"] = width = _number(p.get("width", 1280), "Width", 16, 8192, True)
    p["height"] = height = _number(p.get("height", 720), "Height", 16, 8192, True)
    if width % 2 or height % 2 or width * height > 33_554_432:
        raise ValueError("Project dimensions must be even, with at most 33.5 million pixels.")
    for key, limit in (("assets", 512), ("clips", 256), ("titles", 128)):
        if not isinstance(p.get(key, []), list) or len(p.get(key, [])) > limit:
            raise ValueError(f"{key} must be a list with at most {limit} items.")
        p.setdefault(key, [])
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
    maximum = fps * MAX_TIMELINE_SECONDS
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
        for key, default, low in (("start", 0, 0), ("in", 0, 0), ("duration", fps, 1)):
            c[key] = _number(c.get(key, default), f"Clip {key}", low, maximum, True)
        if c["start"] + c["duration"] > maximum:
            raise ValueError("Timeline exceeds the six-hour limit.")
        # Permit only half a project frame of metadata rounding, never a freeze-frame fallback.
        if a["kind"] != "image" and (c["in"] + c["duration"]) / fps > a["duration"] + 0.5 / fps:
            raise ValueError(f"Clip {ident} extends beyond its source media. Shorten the trim.")
        if a["kind"] == "image" and c["in"]:
            raise ValueError("Still images have no source in point.")
        for key, default, low, high in (("volume", 1, 0, 4), ("opacity", 1, 0, 1),
                                       ("x", 0, -4, 4), ("y", 0, -4, 4),
                                       ("scale", 1, .02, 4), ("rotation", 0, -360, 360)):
            c[key] = _number(c.get(key, default), key, low, high)
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
            if not isinstance(keyframe, dict) or set(keyframe) - {"frame", "x", "y", "scale", "opacity"}:
                raise ValueError("Keyframes support frame, x, y, scale and opacity only.")
            frame = _number(keyframe.get("frame"), "Keyframe position", 0, c["duration"] - 1, True)
            if frame in seen:
                raise ValueError("Keyframes on a clip must have distinct positions.")
            seen.add(frame)
            keyframe["frame"] = frame
            for key, low, high in (("x", -4, 4), ("y", -4, 4), ("scale", .02, 4), ("opacity", 0, 1)):
                if key in keyframe:
                    keyframe[key] = _number(keyframe[key], f"Keyframe {key}", low, high)
        c["keyframes"] = sorted(keyframes, key=lambda k: k["frame"])
        largest_scale = max([c["scale"]] + [k.get("scale", c["scale"]) for k in keyframes])
        if a["kind"] != "audio":
            fit = min(width / a["width"], height / a["height"])
            if a["width"] * a["height"] * (fit * largest_scale) ** 2 > 67_108_864:
                raise ValueError("Clip transform exceeds the 67-million-pixel working-image limit. Reduce scale or project dimensions.")
        if c.get("compositor") is not None:
            if c["track"] < 0 or a["kind"] == "audio":
                raise ValueError("Compositor graphs belong to picture clips on video tracks.")
            fitted_width = max(2, int(a["width"] * fit / 2) * 2)
            fitted_height = max(2, int(a["height"] * fit / 2) * 2)
            c["compositor"] = validate_graph(c["compositor"], fitted_width, fitted_height)
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
        for key, default, low, high, integer in (("start", 0, 0, maximum, True), ("duration", fps * 3, 1, maximum, True),
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
            "keyframes": ["x", "y", "scale", "opacity"], "filters": sorted(filters)}


def _decimal(value):
    return format(float(value), ".10g")


def _curve(clip, key, fps, variable="t"):
    points = [(0, clip[key])]
    for k in clip["keyframes"]:
        if key in k:
            if k["frame"] == 0:
                points[0] = (0, k[key])
            else:
                points.append((k["frame"] / fps, k[key]))
    expression = _decimal(points[-1][1])
    for (start, a), (end, b) in reversed(list(zip(points, points[1:]))):
        linear = f"({_decimal(a)}+({_decimal(b-a)})*({variable}-{_decimal(start)})/{_decimal(end-start)})"
        expression = f"if(lt({variable},{_decimal(end)}),{linear},{expression})"
    return expression


def _quote_filter_path(path):
    # FFmpeg's filter parser consumes backslashes before quotes/colons.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")


def _graph(project, project_dir, temp_dir):
    fps, width, height = project["fps"], project["width"], project["height"]
    frames = max([c["start"] + c["duration"] for c in project["clips"]] +
                 [t["start"] + t["duration"] for t in project["titles"]] + [0])
    if frames < 1:
        raise ValueError("Add footage, audio or a title before rendering.")
    duration = frames / fps
    assets = {a["id"]: a for a in project["assets"]}
    filters = [f"color=c=black:s={width}x{height}:r={fps}:d={_decimal(duration)},format=rgba[canvas0]"]
    filters += [f"anullsrc=r=48000:cl=stereo,atrim=duration={_decimal(duration)}[silence]"]
    inputs, audio, canvas = [], ["[silence]"], "canvas0"
    ordered = sorted(enumerate(project["clips"]), key=lambda item: (item[1]["track"], item[0]))
    for index, (_, clip) in enumerate(ordered):
        asset = assets[clip["asset_id"]]
        source = _media_path(project_dir, asset["path"])
        inputs += ["-threads", "2", "-protocol_whitelist", "file,pipe"]
        if asset["kind"] == "image":
            inputs += ["-loop", "1", "-framerate", str(fps)]
        inputs += ["-i", str(source)]
        start, length, source_in = clip["start"] / fps, clip["duration"] / fps, clip["in"] / fps
        if clip["track"] >= 0:
            fit = min(width / asset["width"], height / asset["height"])
            base_w, base_h = max(2, asset["width"] * fit), max(2, asset["height"] * fit)
            scale = _curve(clip, "scale", fps)
            chain = [f"trim=start={_decimal(source_in)}:duration={_decimal(length)}", "setpts=PTS-STARTPTS", f"fps={fps}",
                     f"scale=w='max(2,trunc({_decimal(base_w)}*({scale})/2)*2)':h='max(2,trunc({_decimal(base_h)}*({scale})/2)*2)':eval=frame:flags=lanczos", "setsar=1"]
            stream = f"{index}:{asset['video_stream_index']}"
            if clip.get("compositor") is not None:
                # Normalize once before the node DAG. All branches share the
                # same geometry/timing, then the existing clip controls apply.
                fitted_width, fitted_height = max(2, int(base_w / 2) * 2), max(2, int(base_h / 2) * 2)
                input_label = f"compositor{index}input"
                filters.append(f"[{stream}]trim=start={_decimal(source_in)}:duration={_decimal(length)},"
                               f"setpts=PTS-STARTPTS,fps={fps},scale={fitted_width}:{fitted_height}:flags=lanczos,"
                               f"setsar=1,format=rgba[{input_label}]")
                clauses, stream = compile_graph(clip["compositor"], input_label, f"compositor{index}")
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
            if clip["rotation"]:
                angle = _decimal(clip["rotation"] * math.pi / 180)
                chain += [f"rotate={angle}:ow='rotw({angle})':oh='roth({angle})':c=none"]
            if any("opacity" in k for k in clip["keyframes"]):
                opacity = _curve(clip, "opacity", fps, "T")
                chain += [f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({opacity})'"]
            elif clip["opacity"] != 1:
                chain += [f"colorchannelmixer=aa={_decimal(clip['opacity'])}"]
            chain += [f"setpts=PTS+{_decimal(start)}/TB"]
            filters += [f"[{stream}]" + ",".join(chain) + f"[picture{index}]"]
            x = _curve(clip, "x", fps, f"(t-{_decimal(start)})")
            y = _curve(clip, "y", fps, f"(t-{_decimal(start)})")
            next_canvas = f"canvas{index+1}"
            filters += [f"[{canvas}][picture{index}]overlay=x='(W-w)/2+W*({x})':y='(H-h)/2+H*({y})':"
                        f"enable='gte(t,{_decimal(start)})*lt(t,{_decimal(start+length)})':eof_action=pass:repeatlast=0:format=auto[{next_canvas}]"]
            canvas = next_canvas
        if asset["has_audio"] and clip["volume"] > 0:
            delay = round(start * 48000)
            filters += [f"[{index}:{asset['audio_stream_index']}]atrim=start={_decimal(source_in)}:duration={_decimal(length)},asetpts=PTS-STARTPTS,"
                        f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={_decimal(clip['volume'])},"
                        f"adelay={delay}S:all=1[audio{index}]"]
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
            inputs += ["-threads", "2", "-protocol_whitelist", "file,pipe", "-loop", "1", "-framerate", str(fps), "-i", str(source)]
            chain = [f"trim=duration={_decimal(end-start)}", "setpts=PTS-STARTPTS", "format=rgba", "setsar=1"]
            if fade:
                chain += [f"fade=t=in:st=0:d={_decimal(fade)}:alpha=1",
                          f"fade=t=out:st={_decimal(end-start-fade)}:d={_decimal(fade)}:alpha=1"]
            chain += [f"setpts=PTS+{_decimal(start)}/TB"]
            filters += [f"[{input_index}:{raster['video_stream_index']}]" + ",".join(chain) + f"[raster{index}]"]
            output = f"title{index}"
            filters += [f"[{canvas}][raster{index}]overlay=x=0:y=0:"
                        f"enable='gte(t,{_decimal(start)})*lt(t,{_decimal(end)})':eof_action=pass:repeatlast=0:format=auto[{output}]"]
            canvas = output
            continue
        filename = Path(temp_dir) / f"title-{index}.txt"
        filename.write_text(title["text"], encoding="utf-8")
        alpha = "1" if not fade else f"min(1,min((t-{_decimal(start)})/{_decimal(fade)},({_decimal(end)}-t)/{_decimal(fade)}))"
        output = f"title{index}"
        filters += [f"[{canvas}]drawtext=textfile='{_quote_filter_path(filename)}':expansion=none:"
                    f"fontcolor={title['color']}:fontsize={title['size']}:"
                    f"x='(w-tw)/2+w*{_decimal(title['x'])}':y='(h-th)/2+h*{_decimal(title['y'])}':"
                    f"alpha='{alpha}':enable='gte(t,{_decimal(start)})*lt(t,{_decimal(end)})'[{output}]"]
        canvas = output
    filters += [f"[{canvas}]trim=end_frame={frames},setpts=PTS-STARTPTS,scale=out_color_matrix=bt709:out_range=tv[vout]"]
    filters += ["".join(audio) + f"amix=inputs={len(audio)}:duration=longest:normalize=0,"
                f"alimiter=limit=0.98:level=false:latency=true,atrim=end_sample={round(duration*48000)},asetpts=PTS-STARTPTS[aout]"]
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
            duration = frames / p["fps"]
            graph_path = Path(temp_dir) / "filter.txt"
            graph_path.write_text(graph, encoding="utf-8")
            command = [_executable("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-filter_complex_threads", "1"]
            command += inputs + ["-filter_complex_script", str(graph_path), "-map", "[vout]", "-map", "[aout]",
                                 "-frames:v", str(frames), "-r", str(p["fps"]), "-t", _decimal(duration), "-threads", "2"]
            if profile == "prores":
                command += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le"]
            else:
                command += ["-c:v", "libx264", "-preset", "veryfast" if profile == "preview" else "medium",
                            "-crf", "26" if profile == "preview" else "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
            command += ["-ar", "48000", "-ac", "2", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                        "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(partial)]
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
            if actual["frames"] and actual["frames"] != frames:
                raise RuntimeError("Rendered media has an unexpected frame count.")
            if abs(actual["duration"] - duration) > max(.1, 1 / p["fps"]):
                raise RuntimeError("Rendered media has an unexpected duration.")
            digest = hashlib.sha256()
            with partial.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            os.replace(partial, output)
            if progress:
                progress(1.0)
            return {"path": str(output), "sha256": digest.hexdigest(), "duration": duration,
                    "width": p["width"], "height": p["height"], "fps": p["fps"], "frames": frames,
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

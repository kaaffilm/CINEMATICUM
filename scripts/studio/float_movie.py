"""Owned scene-linear movie orchestration; the server imports no numeric libraries.

The isolated worker performs real float compositing. Display derivatives and
float EXR masters have separate outputs. No operation changes film issuance.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import uuid
import zipfile

if __package__:
    from .imaging import DEFAULT_CONFIG, DEFAULT_DISPLAY, _hash_file, _json_bytes, _owned, _worker_env, find_imaging_python
else:
    from imaging import DEFAULT_CONFIG, DEFAULT_DISPLAY, _hash_file, _json_bytes, _owned, _worker_env, find_imaging_python

DEFAULTS = {"version": 1, "config": DEFAULT_CONFIG, "working_space": "ACEScg", "output_space": "ACEScg",
            "default_input_space": "Camera Rec.709", "display": DEFAULT_DISPLAY,
            "view": "ACES 2.0 - SDR 100 nits (Rec.709)"}
LINEAR_SPACES = ("ACEScg", "ACES2065-1", "Linear Rec.709 (sRGB)")
MAX_PIXELS = 8_388_608
MAX_SOURCE_PIXELS = 16_777_216
MAX_FRAMES = 14_400
MAX_OUTPUT_BYTES = 32 * 1024 ** 3
MAX_SOURCE_BYTES = 16 * 1024 ** 3
FORMAT = "cinematicum-scene-linear-movie"


def validate_color(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Float movie color settings contain unsupported fields.")
    color = {**DEFAULTS, **copy.deepcopy(value)}
    if type(color["version"]) is not int or color["version"] != 1:
        raise ValueError("Unsupported float movie color version.")
    if color["config"] != DEFAULT_CONFIG:
        raise ValueError("Float movies currently require the pinned ACES 2.1 Studio built-in OCIO configuration.")
    for field in ("working_space", "output_space"):
        if color[field] not in LINEAR_SPACES:
            raise ValueError("Float working and EXR output spaces must be ACEScg, ACES2065-1 or Linear Rec.709 (sRGB).")
    for field in ("default_input_space", "view"):
        text(color[field], field)
    if color["display"] != DEFAULT_DISPLAY or color["view"] == "Raw":
        raise ValueError("Float movie previews require an explicit supported sRGB display view.")
    return color


def text(value, label):
    if not isinstance(value, str) or not 1 <= len(value) <= 240 or any(ord(c) < 32 for c in value):
        raise ValueError(label + " must be bounded printable text.")
    return value


def validate_float_project(project):
    settings = project.setdefault("settings", {})
    if "float_color" in settings:
        settings["float_color"] = validate_color(settings["float_color"])
    for clip in project["clips"]:
        if "float_input_space" in clip:
            text(clip["float_input_space"], "Clip OCIO input space")
    if settings.get("image_precision") != "float32":
        return project
    settings["float_color"] = validate_color(settings.get("float_color", {}))
    if project["width"] * project["height"] > MAX_PIXELS:
        raise ValueError("Float32 movies support at most 8,388,608 canvas pixels.")
    assets = {a["id"]: a for a in project["assets"]}
    for clip in project["clips"]:
        if clip.get("retime"):
            raise ValueError("Float32 v1 does not flatten speed ramps or optical flow. Use Standard 8-bit SDR for this retime workflow.")
        if clip.get("sequence_id"):
            raise ValueError("Float32 v1 requires flattened sequence edits; live nested sequences are unsupported.")
        if clip["track"] < 0:
            continue
        asset = assets[clip["asset_id"]]
        if asset["width"] * asset["height"] > MAX_SOURCE_PIXELS:
            raise ValueError("Float32 input pictures exceed the 16,777,216-pixel source limit.")
        if any(clip.get(key) for key in ("compositor", "tracking", "planar_motion", "learned_bindings")):
            raise ValueError("Float32 v1 supports clip transforms and source-over; compositor graphs and measured tracking require a separate supported render.")
        if clip.get("color_pipeline", {}).get("enabled"):
            raise ValueError("Use the float movie OCIO input space instead of the SDR clip color pipeline.")
        if any(clip["effects"].get(key) for key in ("blur", "sharpen", "vignette", "chroma_key")):
            raise ValueError("Float32 v1 does not approximate SDR blur, sharpen, vignette or chroma-key effects.")
        grade = clip["grade"]
        if grade["contrast"] != 1 or grade["saturation"] != 1 or grade["temperature"] != 0:
            raise ValueError("Float32 v1 supports scene-linear exposure; reset SDR contrast, saturation and temperature.")
        if Path(asset["path"]).suffix.lower() == ".exr" and not clip.get("float_input_space"):
            raise ValueError("Choose an explicit OCIO input space for every EXR clip.")
        if asset.get("color_transfer") in {"smpte2084", "arib-std-b67"} and not clip.get("float_input_space"):
            raise ValueError("Choose an explicit OCIO input space for PQ/HLG source media.")
        if clip["reverse"] and clip["duration"] * asset["width"] * asset["height"] * 16 > 512 * 1024 ** 2:
            raise ValueError("Reversed float pictures exceed the bounded 512 MiB reverse buffer.")
    return project


def _cancel(event):
    if event is not None and event.is_set():
        from engine import RenderCancelled
        raise RenderCancelled("Float movie cancelled; sources and completed exports are unchanged.")


def _digest(path, event=None, maximum=MAX_SOURCE_BYTES):
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=maximum:
            raise ValueError("Float movie file is empty, nonregular or exceeds its byte bound.")
        digest=hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024),b""):
            _cancel(event);digest.update(block)
        after=os.fstat(stream.fileno())
        if any(getattr(before,k)!=getattr(after,k) for k in ("st_size","st_mtime_ns","st_ctime_ns","st_ino","st_dev")):
            raise ValueError("A float movie file changed during hashing.")
        return digest.hexdigest(),before.st_size


def _stop(process):
    # This process group was created for this invocation. Terminate descendants
    # even if a decoder error made the worker exit before it could reap them.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run(command, scratch, event=None, timeout=1800, request=None, progress=None, audio_audit=None):
    _cancel(event)
    scratch = Path(scratch)
    with tempfile.TemporaryFile(dir=scratch) as stdout, tempfile.TemporaryFile(dir=scratch) as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE if request is not None else subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, start_new_session=True, env=_worker_env())
        started = time.monotonic()
        try:
            if request is not None:
                process.stdin.write(_json_bytes(request)); process.stdin.close()
            while process.poll() is None:
                _cancel(event)
                if time.monotonic() - started > timeout:
                    raise RuntimeError("Float movie exceeded its owned foreground job time limit.")
                if progress:
                    progress()
                time.sleep(.04)
            _cancel(event)
            stdout.seek(0); result = stdout.read(2 * 1024 * 1024 + 1)
            stderr.seek(0, 2); size = stderr.tell(); stderr.seek(max(0, size - 6000)); detail = stderr.read().decode(errors="replace")
            if process.returncode:
                try:
                    detail = json.loads(result).get("error", detail)
                except (ValueError, AttributeError):
                    pass
                raise RuntimeError("Float movie processing failed: " + detail[-6000:])
            if len(result) > 2 * 1024 * 1024:
                raise RuntimeError("Float movie worker returned an oversized response.")
            if audio_audit is not None:
                from audio_mixer import accept_normalization_audits
                stderr.seek(0)
                audio_audit['receipts'] = accept_normalization_audits((line.decode('utf-8', errors='replace') for line in stderr), audio_audit['expected'])
            return result
        finally:
            _stop(process)


def _worker_command(python=None):
    runtime = find_imaging_python(python)
    if not runtime:
        raise ValueError("Install the isolated Imaging runtime for float32 movie processing.")
    return [runtime, "-I", "-B", str(Path(__file__).with_name("float_movie_worker.py"))]


def capabilities(python=None):
    base = {"available": False, "image_precision": "float32", "profile": "master32", "defaults": DEFAULTS,
            "max_pixels": MAX_PIXELS, "max_frames": MAX_FRAMES, "hdr_monitoring": False, "calibrated_display": False}
    try:
        with tempfile.TemporaryDirectory(prefix="cinematicum-float-doctor-") as scratch:
            return {**base, **json.loads(_run(_worker_command(python), scratch, request={"command": "doctor"}, timeout=20))}
    except (ValueError, RuntimeError, OSError) as exc:
        return {**base, "reason": str(exc)}


def _duration(project):
    return max([c["start"] + c["duration"] for c in project["clips"]] +
               [t["start"] + t["duration"] for t in project["titles"]] +
               [c["start"] + c["duration"] for c in project.get("captions", [])] + [project.get("sequence_duration", 0)])


def _source_audio(project, clip, assets):
    """Use the engine's authoritative sound plan, including fixed-camera locks."""
    import engine
    resolver = getattr(engine, "resolve_audio", None)
    if resolver is not None:
        return resolver(project, clip, assets)
    binding = clip.get("multicam", {})
    group = next((g for g in project.get("multicam_groups", []) if g.get("id") == binding.get("group_id")), None)
    if group and group.get("audio_lock") is not None:
        raise ValueError("This build cannot resolve the multicamera source-audio plan required by the float timeline.")
    return clip, assets[clip["asset_id"]]


def _source_ids(project):
    assets = {a["id"]: a for a in project["assets"]}
    ids = {c["asset_id"] for c in project["clips"]} | {t["asset_id"] for t in project["titles"] if t.get("asset_id")}
    # A locked multicamera clock binds every angle, including cameras not
    # selected by the current picture cut. Retain and rehash those identities.
    for group in project.get("multicam_groups", []):
        if group.get("audio_lock") is not None:
            ids.update(angle["asset_id"] for angle in group["angles"])
    for clip in project["clips"]:
        _, sound = _source_audio(project, clip, assets)
        ids.add(sound["id"])
    return ids


def _sources(project, root, event):
    ids = _source_ids(project)
    records = []
    for asset in project["assets"]:
        if asset["id"] not in ids:
            continue
        _cancel(event)
        source = _owned(root, asset["path"])
        identity, size = _digest(source, event)
        if asset.get("sha256") and asset["sha256"] != identity:
            raise ValueError("A float movie source changed after media admission: " + asset["name"])
        records.append({"asset_id": asset["id"], "path": asset["path"], "sha256": identity, "size": size})
    return records


def _verify_sources(root, sources, event):
    for source in sources:
        _cancel(event)
        if _digest(_owned(root, source["path"]), event) != (source["sha256"], source["size"]):
            raise ValueError("A float movie source changed during the render.")


def _audio(project, root, scratch, event):
    from engine import _graph, track_state
    from timebase import project_rate
    audio = copy.deepcopy(project)
    audio["settings"]["image_precision"] = "standard8"
    audio["settings"]["transparent_background"] = False
    audio["sequence_duration"] = _duration(project)
    audio["titles"] = []; audio["captions"] = []; audio["tracks"] = []
    assets = {a["id"]: a for a in audio["assets"]}
    kept = []; audio_tracks = {}
    for clip in audio["clips"]:
        enabled, gain = track_state(project, clip["track"])
        _, source_audio = _source_audio(project, clip, assets)
        if not enabled or not gain or not source_audio["has_audio"]:
            continue
        audio_tracks[clip["id"]] = clip["track"]
        clip["track"] = -1; clip["volume"] *= gain
        for key in clip["keyframes"]:
            if "volume" in key: key["volume"] *= gain
        kept.append(clip)
    audio["clips"] = kept
    inputs, graph, frames = _graph(audio, root, scratch, cancel_event=event, _audio_tracks=audio_tracks)
    graph += ";\n[vout]nullsink"
    script = scratch / "audio-graph.txt"; script.write_text(graph)
    normalization_expected = set(re.findall(r"astats@([A-Za-z0-9_]+)_input=", graph))
    audit = {'expected': normalization_expected, 'receipts': []}
    out = scratch / "mix.wav"
    _run([shutil.which("ffmpeg"), "-v", "info" if normalization_expected else "error", "-nostdin", "-y", "-filter_complex_threads", "1"] + inputs +
         ["-filter_complex_script", str(script), "-map", "[aout]", "-c:a", "pcm_f32le", "-ar", "48000", "-ac", "2", str(out)], scratch, event,
         audio_audit=audit if normalization_expected else None)
    if normalization_expected:
        (scratch / "audio-normalization-audit.json").write_bytes(_json_bytes(audit['receipts']))
    raw = scratch / "mix-check.f32"
    _run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-i", str(out), "-map", "0:a:0", "-c:a", "pcm_f32le", "-f", "f32le", str(raw)], scratch, event)
    samples = project_rate(project).samples_for_frames(frames)
    if raw.stat().st_size != samples * 8:
        raise RuntimeError("Float master audio does not preserve the exact timeline sample count.")
    raw.unlink()
    return out, {"sample_rate": 48000, "channels": 2, "samples": samples, "encoding": "pcm_f32le"}


def verify_master_package(path, snapshot=None, cancel_event=None):
    """Verify the bounded inert package and its exact source/recipe bindings.

    Pixel equality is checked by the worker at creation. This portable check
    establishes retained-byte integrity without loading an optional runtime.
    """
    from timebase import project_rate
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        if not 5 <= len(items) <= MAX_FRAMES + 5 or len({i.filename for i in items}) != len(items):
            raise ValueError("Float master package has an invalid or duplicate inventory.")
        if any(i.compress_type != zipfile.ZIP_STORED or i.file_size < 1 for i in items) or sum(i.file_size for i in items) > MAX_OUTPUT_BYTES:
            raise ValueError("Float master package has an unsupported compression or byte bound.")
        metadata = archive.getinfo("manifest.json")
        if metadata.file_size > 16 * 1024 * 1024: raise ValueError("Float master manifest is too large.")
        raw = archive.read(metadata); manifest = json.loads(raw)
        if _json_bytes(manifest) != raw or manifest.get("format") != FORMAT or manifest.get("version") != 1 or manifest.get("processing_bits") != 32:
            raise ValueError("Float master manifest format is invalid.")
        project = manifest.get("project"); validate_float_project(project)
        if manifest.get("project_sha256") != hashlib.sha256(_json_bytes(project)).hexdigest():
            raise ValueError("Float master snapshot identity is inconsistent.")
        if snapshot is not None and manifest["project_sha256"] != hashlib.sha256(_json_bytes(snapshot)).hexdigest():
            raise ValueError("Float master does not match its preserved project snapshot.")
        frames = manifest.get("frames"); rate = project_rate(project)
        if type(frames) is not int or not 1 <= frames <= MAX_FRAMES or frames != _duration(project) or manifest.get("frame_rate") != rate.as_dict():
            raise ValueError("Float master timeline binding is inconsistent.")
        color = validate_color({k: manifest.get("color", {}).get(k) for k in DEFAULTS})
        if color != project["settings"]["float_color"] or manifest.get("audio") != {"sample_rate":48000,"channels":2,"samples":rate.samples_for_frames(frames),"encoding":"pcm_f32le"}:
            raise ValueError("Float master color or audio timing differs from its snapshot.")
        entries = manifest.get("artifacts")
        expected = {"config.ocio", "display.png", "mix.wav"} | {"frames/frame-%08d.exr" % n for n in range(frames)}
        if not isinstance(entries,list) or len(entries)!=len(expected) or {e.get("path") for e in entries}!=expected or {i.filename for i in items}!=expected|{"manifest.json"}:
            raise ValueError("Float master frame/artifact inventory is incomplete or contains undeclared files.")
        for entry in entries:
            name=entry["path"]; item=archive.getinfo(name); identity=entry.get("sha256")
            if not isinstance(identity,str) or not re.fullmatch(r"[a-f0-9]{64}",identity) or entry.get("size")!=item.file_size:
                raise ValueError("Float master artifact identity is invalid.")
            digest=hashlib.sha256()
            with archive.open(item) as stream:
                for data in iter(lambda:stream.read(1024*1024),b""):
                    _cancel(cancel_event);digest.update(data)
            if digest.hexdigest()!=identity:raise ValueError("Float master artifact hash mismatch: "+name)
        config = next(e for e in entries if e["path"]=="config.ocio")
        if config["sha256"] != manifest["color"].get("config_sha256"):
            raise ValueError("Float master OCIO configuration changed.")
        assets={a["id"]:a for a in project["assets"]}
        used=_source_ids(project)
        sources=manifest.get("sources")
        if not isinstance(sources,list) or len(sources)!=len(used) or {s.get("asset_id") for s in sources}!=used:
            raise ValueError("Float master source inventory is incomplete.")
        for source in sources:
            asset=assets[source["asset_id"]]
            if source.get("path")!=asset["path"] or source.get("size")!=asset["size"] or not re.fullmatch(r"[a-f0-9]{64}",source.get("sha256", "")) or asset.get("sha256",source["sha256"])!=source["sha256"]:
                raise ValueError("Float master source identity differs from its snapshot.")
        return manifest


def render_float(project, project_dir, output_path, profile="master32", progress=None, cancel_event=None, frame=None, timeout=1800):
    from engine import _video_timing, probe_media
    from timebase import project_rate
    p = validate_float_project(copy.deepcopy(project))
    if p.get("settings", {}).get("image_precision") != "float32":
        raise ValueError("Select Scene-linear Float32 processing before exporting a float master.")
    if profile not in {"master32", "preview", "h264", "prores", "frame"}:
        raise ValueError("This profile cannot store scene-linear float movie output.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg and ffprobe are required for float movie processing.")
    frames = _duration(p); rate = project_rate(p)
    if not 1 <= frames <= MAX_FRAMES:
        raise ValueError("Float32 v1 exports require 1–14,400 project frames.")
    if any(not t.get("asset_id") for t in p["titles"]):
        raise ValueError("Save/rasterize the title in Studio before its float movie render.")
    if frame is not None and (type(frame) is not int or not 0 <= frame < frames or profile != "frame"):
        raise ValueError("The float preview frame must be inside this timeline.")
    root = Path(project_dir).absolute()
    output = Path(output_path).absolute()
    suffix = {"master32": ".zip", "preview": ".mp4", "h264": ".mp4", "prores": ".mov", "frame": ".png"}[profile]
    if output.suffix.lower() != suffix:
        raise ValueError("The float export extension does not match its profile.")
    if output.is_symlink() or any(output.resolve() == (root / a["path"]).resolve() for a in p["assets"]):
        raise ValueError("A float export cannot replace an imported source or symlink.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = _sources(p, root, cancel_event)
    with tempfile.TemporaryDirectory(prefix=".cinematicum-float-", dir=output.parent) as temporary:
        scratch = Path(temporary)
        package = scratch / "package"; package.mkdir()
        request = {"command": "render", "project_dir": str(root), "project": p, "sources": sources,
                   "output_dir": str(package), "profile": profile, "frame": frame,
                   "video_timing": {c["id"]: _video_timing(c, rate) for c in p["clips"] if c["track"] >= 0}}
        def report_progress():
            if progress:
                try: progress(min(.82, json.loads((package / "progress.json").read_text())["progress"] * .82))
                except (ValueError, OSError, KeyError): pass
        worker = json.loads(_run(_worker_command(), scratch, cancel_event, timeout, request, report_progress))
        if worker.get("format") != FORMAT or worker.get("version") != 1 or worker.get("frames") != (1 if frame is not None else frames):
            raise RuntimeError("Float movie worker returned an inconsistent processing receipt.")
        _verify_sources(root, sources, cancel_event)
        duration = float(rate.seconds_for_frames(frames))
        if profile == "frame":
            complete = package / "display.png"
            report = {"frame": frame, "width": p["width"], "height": p["height"], "processing_bits": 32,
                      "pixel_format": "rgba64be", "pipeline": "scene-linear-float32-ocio-display", "color": worker["color"]}
        else:
            mix, audio = _audio(p, root, scratch, cancel_event)
            audio_meter = None
            audio_normalization = json.loads((scratch / "audio-normalization-audit.json").read_text()) if (scratch / "audio-normalization-audit.json").exists() else []
            from audio_mixer import measure_media, configured_mixers
            audio_mixers = configured_mixers(p)
            if audio_mixers:
                if profile == "master32":
                    audio_meter = measure_media(mix, shutil.which("ffmpeg"), cancel_event=cancel_event)
            if progress: progress(.9)
            if profile == "master32":
                shutil.move(mix, package / "mix.wav")
                artifacts = []
                (package / "progress.json").unlink(missing_ok=True)
                for file in sorted(package.rglob("*")):
                    if file.is_file():
                        _cancel(cancel_event); identity, size = _digest(file, cancel_event, MAX_OUTPUT_BYTES)
                        artifacts.append({"path": file.relative_to(package).as_posix(), "sha256": identity, "size": size})
                if sum(a["size"] for a in artifacts) > MAX_OUTPUT_BYTES:
                    raise ValueError("Float master package exceeds the 32 GiB limit.")
                if audio_meter is not None:
                    audio_meter["measured_audio_sha256"] = next(item["sha256"] for item in artifacts if item["path"] == "mix.wav")
                receipt = {**worker, "sources": sources, "audio": audio, "artifacts": artifacts,
                           **({"audio_mixer": copy.deepcopy(p.get("audio_mixer")), "audio_mixers": audio_mixers, "audio_meter": audio_meter, "audio_normalization": audio_normalization} if audio_meter is not None else {}),
                           "project_sha256": hashlib.sha256(_json_bytes(p)).hexdigest(), "project": p,
                           "frame_rate": rate.as_dict(), "duration": duration, "issuance_effect": "NONE"}
                (package / "manifest.json").write_bytes(_json_bytes(receipt))
                complete = scratch / "complete.zip"
                with zipfile.ZipFile(complete, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                    for file in sorted(package.rglob("*")):
                        if file.is_file():
                            _cancel(cancel_event)
                            with file.open("rb") as source, archive.open(file.relative_to(package).as_posix(), "w", force_zip64=True) as target:
                                for data in iter(lambda: source.read(1024 * 1024), b""):
                                    _cancel(cancel_event); target.write(data)
                verify_master_package(complete, p, cancel_event)
                report = {"encoding": "OpenEXR ZIP FLOAT32 + PCM float32 WAV", "pixel_format": "float32 RGBA",
                          "alpha_mode": "premultiplied", "artifacts": len(artifacts), "audio": audio}
            else:
                complete = scratch / ("complete" + suffix)
                _run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(package / ("display" + suffix)),
                      "-i", str(mix), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                      "-c:a", "pcm_s16le" if profile == "prores" else "aac", "-ar", "48000", "-ac", "2",
                      "-movie_timescale", "48000", "-movflags", "+faststart", str(complete)], scratch, cancel_event)
                actual = probe_media(complete)
                if actual["width"] != p["width"] or actual["height"] != p["height"] or not actual["has_audio"] or actual["frames"] != frames:
                    raise RuntimeError("Float display derivative does not match the accepted timeline.")
                from fractions import Fraction
                if Fraction(actual["fps"]) != rate.fraction or abs(actual["audio_duration"]-audio["samples"]/48000)>2/48000:
                    raise RuntimeError("Float display derivative changed its exact picture/audio clock.")
                report = {"encoding": actual["codec"], "pixel_format": actual["pixel_format"], "alpha_mode": "opaque", "audio": audio}
                if audio_mixers:
                    audio_meter = measure_media(complete, shutil.which("ffmpeg"), cancel_event=cancel_event)
            if audio_meter is not None:
                report.update(audio_mixer=copy.deepcopy(p.get("audio_mixer")), audio_mixers=audio_mixers, audio_meter=audio_meter, audio_normalization=audio_normalization)
            report.update(width=p["width"], height=p["height"], fps=p["fps"], frame_rate=rate.as_dict(), frames=frames, duration=duration,
                          processing_bits=32, image_precision="float32", profile=profile, color=worker["color"], sources=sources,
                          project_sha256=hashlib.sha256(_json_bytes(p)).hexdigest(), dynamic_range="Scene-linear float EXR; SDR display derivatives",
                          hdr_monitoring=False, calibrated_display=False, issuance_effect="NONE")
        _verify_sources(root, sources, cancel_event)
        identity, size = _digest(complete, cancel_event, MAX_OUTPUT_BYTES)
        if profile != "frame" and report.get("audio_meter") is not None:
            report["audio_meter"]["measured_export_sha256"] = identity
        _cancel(cancel_event); os.replace(complete, output)
        if progress: progress(1)
        return {**report, "path": str(output), "sha256": identity, "size": size}

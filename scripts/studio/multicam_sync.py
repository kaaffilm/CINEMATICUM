"""Owned automatic multicamera audio synchronization and pure edit candidates.

Application imports remain standard-library only. Actual FFT calculations run
in an isolated NumPy worker; decoded samples retain the same 48 kHz, zero-based
source clock as CINEMATICUM movie export and live source audio.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid

VERSION = 1
ALGORITHM = "fft-normalized-48k-v1"
RATE = 48000
MAX_WINDOW = 120 * RATE
MIN_OVERLAP = 4 * RATE
MAX_LAG = 60 * RATE
MAX_START = 21600 * RATE
MAX_SOURCE_BYTES = 32 * 1024 ** 3
MAX_JSON_BYTES = 12 * 1024 ** 2
MAX_OUTPUT_BYTES = 16 * MAX_WINDOW * 4 + 2 * MAX_JSON_BYTES
TOTAL_SECONDS = 300
DIRECTORY = "multicam-sync"
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
BASE_ARTIFACTS = frozenset({"recipe.json", "analysis.json", "waveforms.json", "receipt.json"})
ARTIFACT_NAMES = BASE_ARTIFACTS | frozenset(f"samples_{index:02d}.f32le" for index in range(16))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer between {low} and {high}.")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(label + " must be a valid owned identifier.")
    return value


def _cancel(event=None, deadline=None):
    if event is not None and event.is_set():
        raise InterruptedError("Multicamera synchronization cancelled; no edit was applied.")
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("Multicamera synchronization exceeded its 300-second work bound.")


def _digest(path, limit=MAX_SOURCE_BYTES, event=None, deadline=None):
    digest, size = hashlib.sha256(), 0
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("Synchronization files must be bounded regular files.")
        while True:
            _cancel(event, deadline)
            block = stream.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > limit:
                raise ValueError("A synchronization file grew beyond its supported byte bound.")
            digest.update(block)
        after = os.fstat(stream.fileno())
    if _stat_identity(before) != _stat_identity(after) or size != before.st_size:
        raise ValueError("Synchronization source bytes changed while being verified.")
    return {"sha256": digest.hexdigest(), "size": size}


def _stat_identity(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _owned(root, relative, directory=False, create=False):
    root = Path(root).resolve(strict=True)
    text = str(relative)
    path = Path(text)
    if path.is_absolute() or "\\" in text or not path.parts or any(part in (".", "..") for part in path.parts):
        raise ValueError("Synchronization paths must stay inside their owning project.")
    current = root
    for index, part in enumerate(path.parts):
        current = current / part
        expected_dir = index < len(path.parts) - 1 or directory
        if current.is_symlink():
            raise ValueError("Synchronization paths cannot follow symbolic links.")
        if create and expected_dir:
            current.mkdir(exist_ok=True)
        if not current.exists() or (not current.is_dir() if expected_dir else not current.is_file()):
            raise ValueError("An owned synchronization file or directory is missing.")
    return current


def _read(path, limit=MAX_JSON_BYTES, expected=None):
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Synchronization records must be regular files.")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(data) > limit:
        raise ValueError("Synchronization record exceeds its byte bound.")
    if _stat_identity(before) != _stat_identity(after) or len(data) != before.st_size:
        raise ValueError("Synchronization record changed while being read.")
    identity = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    if expected is not None and any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("Synchronization receipt or analysis bytes changed after publication.")
    def constant(_value):
        raise ValueError("Synchronization records must contain finite JSON numbers.")
    return json.loads(data, parse_constant=constant)


def _write(path, value):
    with path.open("xb") as stream:
        stream.write(_json(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())


def _environment():
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "NUMBA", "MPL"))}
    env.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2")
    return env


def sync_capabilities(python=None):
    if python is not None:
        candidates = [python]
    else:
        from imaging import find_imaging_python
        candidates = [os.environ.get("CINEMATICUM_SYNC_PYTHON"), os.environ.get("CINEMATICUM_TRACKING_PYTHON"),
                      str(Path.home() / "Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python"),
                      find_imaging_python()]
    reasons, seen = [], set()
    for candidate in candidates:
        if not candidate or str(candidate) in seen:
            continue
        seen.add(str(candidate)); path = Path(candidate).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            continue
        try:
            result = subprocess.run([str(path), "-I", "-B", str(Path(__file__).with_name("multicam_sync_worker.py")), "--capabilities"],
                                    stdin=subprocess.DEVNULL, capture_output=True, timeout=8, env=_environment())
            if len(result.stdout) > 65536 or result.returncode:
                raise ValueError(result.stderr.decode(errors="replace")[-600:])
            value = json.loads(result.stdout)
            if value.get("available") is not True or value.get("runtime_operations_verified") is not True or value.get("algorithm") != ALGORITHM:
                raise ValueError("The selected runtime did not verify its actual FFT correlation operation.")
            return {**value, "python": str(path), "scope": "Constant-offset audio synchronization of 2–16 selected video channels; up to 120 seconds per source and 60 seconds lag, with silence, ambiguity and separated-window clock checks."}
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            reasons.append(str(exc))
    return {"available": False, "operations": [], "reason": "Install the managed Tracking or Imaging NumPy runtime for real sample correlation. " + (reasons[-1] if reasons else "No isolated NumPy interpreter was found.")}


def validate_sync_recipe(recipe, project):
    if not isinstance(recipe, dict) or set(recipe) - {"version", "angles", "reference_asset_id", "window_samples", "max_lag_samples", "min_overlap_samples"}:
        raise ValueError("Synchronization accepts selected camera channels and bounded sample windows.")
    if recipe.get("version", 1) != VERSION or isinstance(recipe.get("version"), bool):
        raise ValueError("Unsupported synchronization recipe version.")
    window = _integer(recipe.get("window_samples", 60 * RATE), "Analysis window", MIN_OVERLAP, MAX_WINDOW)
    overlap = _integer(recipe.get("min_overlap_samples", MIN_OVERLAP), "Minimum common sound", MIN_OVERLAP, window)
    lag = _integer(recipe.get("max_lag_samples", min(30 * RATE, window - MIN_OVERLAP)), "Offset search", RATE // 10, min(MAX_LAG, window - overlap))
    angles = recipe.get("angles")
    if not isinstance(angles, list) or not 2 <= len(angles) <= 16:
        raise ValueError("Choose 2–16 camera videos with recorded audio.")
    from media_management import asset_record
    result, ids = [], set()
    for value in angles:
        if not isinstance(value, dict) or set(value) - {"asset_id", "stream_index", "channel", "start_sample"}:
            raise ValueError("Each camera needs an admitted asset, audio stream, channel and first sample.")
        asset = asset_record(project, value.get("asset_id"))
        if asset.get("kind") != "video" or not asset.get("has_audio") or asset["id"] in ids:
            raise ValueError("Synchronization cameras must be distinct admitted videos containing audio.")
        stream_id = value.get("stream_index", asset.get("audio_stream_index"))
        _integer(stream_id, "Audio stream ID", 0, 255)
        stream = next((item for item in asset.get("audio_streams", []) if item.get("index") == stream_id), None)
        if stream is None or type(stream.get("channels")) is not int or not 1 <= stream["channels"] <= 32:
            raise ValueError("Choose a recorded audio stream with 1–32 source channels.")
        _integer(stream.get("sample_rate"), "Recorded sample rate", 8000, 384000)
        channel = _integer(value.get("channel", 0), "Source mono channel", 0, stream["channels"] - 1)
        start = _integer(value.get("start_sample", 0), "Analysis first 48 kHz sample", 0, MAX_START)
        if start / RATE >= asset["duration"]:
            raise ValueError("A synchronization window starts beyond its video source.")
        result.append({"asset_id": asset["id"], "stream_index": stream_id, "channel": channel, "start_sample": start})
        ids.add(asset["id"])
    reference = recipe.get("reference_asset_id", result[0]["asset_id"])
    if reference not in ids:
        raise ValueError("The reference camera must be one of the selected sources.")
    return {"version": VERSION, "angles": result, "reference_asset_id": reference,
            "window_samples": window, "max_lag_samples": lag, "min_overlap_samples": overlap}


def artifact_names(count):
    _integer(count, "Camera count", 2, 16)
    return BASE_ARTIFACTS | {f"samples_{index:02d}.f32le" for index in range(count)}


def validate_measurement_result(analysis, waveforms, recipe, sources, worker_sha256):
    """Check worker data types, identities and actual measured sample bounds."""
    def number(value, label, low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(label + " is outside the supported measured range.")
        return value
    ids = [source["asset_id"] for source in sources]
    if (not isinstance(analysis, dict) or type(analysis.get("version")) is not int or analysis["version"] != VERSION
            or analysis.get("algorithm") != ALGORITHM or type(analysis.get("rate")) is not int or analysis["rate"] != RATE
            or type(analysis.get("accepted")) is not bool or analysis.get("reference_asset_id") != recipe["reference_asset_id"]
            or not isinstance(analysis.get("angles"), list) or len(analysis["angles"]) != len(ids)
            or any(not isinstance(item, dict) for item in analysis["angles"])
            or [item.get("asset_id") for item in analysis["angles"]] != ids
            or not isinstance(analysis.get("runtime"), dict) or analysis["runtime"].get("worker_sha256") != worker_sha256):
        raise ValueError("Measured synchronization results do not bind to this request and worker.")
    anchor = next(source for source in sources if source["asset_id"] == recipe["reference_asset_id"])
    accepted_offsets = {}
    for source, measured in zip(sources, analysis["angles"]):
        if type(measured.get("accepted")) is not bool or not isinstance(measured.get("reason"), str) or len(measured["reason"]) > 100:
            raise ValueError("A camera measurement has an invalid acceptance result.")
        if not measured["accepted"]:
            continue
        lag = _integer(measured.get("lag_samples"), "Measured lag", -recipe["max_lag_samples"], recipe["max_lag_samples"])
        offset = _integer(measured.get("offset_samples"), "Measured offset", -MAX_START - MAX_LAG, MAX_START + MAX_LAG)
        if offset != anchor["start_sample"] - source["start_sample"] + lag:
            raise ValueError("A measured offset differs from its source sample clock.")
        correlation = number(measured.get("correlation"), "Measured correlation", -1, 1)
        if type(measured.get("polarity")) is not int or measured["polarity"] != (1 if correlation >= 0 else -1):
            raise ValueError("A measured waveform has inconsistent polarity.")
        if source is anchor:
            if lag != 0 or offset != 0 or measured["reason"] != "reference":
                raise ValueError("The reference camera must retain its zero sample offset.")
        else:
            checks = measured.get("window_checks")
            if (measured["reason"] != "measured" or abs(correlation) < .55 or not isinstance(checks, list)
                    or len(checks) != 3 or any(not isinstance(item, dict) for item in checks)):
                raise ValueError("An accepted camera lacks three actual separated-window measurements.")
            local_lags, centers = [], []
            for check in checks:
                local_lags.append(_integer(check.get("lag_samples"), "Local measured lag", -MAX_LAG - RATE, MAX_LAG + RATE))
                centers.append(_integer(check.get("reference_center_sample"), "Local reference sample", 0, MAX_WINDOW))
                _integer(check.get("samples"), "Local measured window", 1, MAX_WINDOW)
                local_score = number(check.get("correlation"), "Local correlation", -1, 1)
                if abs(local_score) < .55 or (1 if local_score >= 0 else -1) != measured["polarity"]:
                    raise ValueError("An accepted camera failed its independent waveform checks.")
            if (not centers[0] < centers[1] < centers[2] or max(local_lags) - min(local_lags) > 24
                    or any(abs(value - lag) > 24 for value in local_lags)
                    or measured.get("offset_spread_samples") != max(local_lags) - min(local_lags)):
                raise ValueError("An accepted camera's separated offsets are inconsistent.")
        accepted_offsets[source["asset_id"]] = offset
    common = analysis.get("common_overlap")
    if analysis["accepted"]:
        if len(accepted_offsets) != len(ids) or analysis.get("reason") != "measured":
            raise ValueError("The synchronized result contains rejected cameras.")
        begin = max(source["start_sample"] + accepted_offsets[source["asset_id"]] for source in sources)
        end = min(source["start_sample"] + source["samples"] + accepted_offsets[source["asset_id"]] for source in sources)
        expected = {"reference_start_sample": begin, "samples": end - begin,
                    "source_starts": {source["asset_id"]: begin - accepted_offsets[source["asset_id"]] for source in sources}}
        if (not isinstance(common, dict) or type(common.get("reference_start_sample")) is not int
                or type(common.get("samples")) is not int or not isinstance(common.get("source_starts"), dict)
                or any(type(value) is not int for value in common["source_starts"].values())):
            raise ValueError("The synchronized window requires exact integer sample positions.")
        if common != expected or end - begin < recipe["min_overlap_samples"]:
            raise ValueError("The synchronized window differs from actual shared source samples.")
    elif common is not None:
        raise ValueError("A rejected measurement cannot advertise a verified common sound window.")
    if (not isinstance(waveforms, dict) or type(waveforms.get("version")) is not int or waveforms["version"] != VERSION
            or type(waveforms.get("rate")) is not int or waveforms["rate"] != RATE
            or type(waveforms.get("channels")) is not int or waveforms["channels"] != 1 or not isinstance(waveforms.get("sources"), list)
            or len(waveforms["sources"]) != len(ids)):
        raise ValueError("The decoded waveform evidence has invalid bounds.")
    for source, wave in zip(sources, waveforms["sources"]):
        if (not isinstance(wave, dict) or wave.get("asset_id") != source["asset_id"] or wave.get("rate") != RATE
                or wave.get("start_sample") != source["start_sample"] or wave.get("samples") != source["samples"]
                or wave.get("sample_sha256") != source.get("sample_sha256", source.get("sha256"))
                or not isinstance(wave.get("blocks"), list) or not 1 <= len(wave["blocks"]) <= 1024):
            raise ValueError("The measured waveform does not bind to its decoded sample bytes.")
        end = source["start_sample"]
        for block in wave["blocks"]:
            if not isinstance(block, dict) or block.get("start_sample") != end:
                raise ValueError("The measured waveform has a missing or overlapping block.")
            end += _integer(block.get("samples"), "Waveform block samples", 1, MAX_WINDOW)
            low = number(block.get("min"), "Waveform minimum", -64, 64)
            high = number(block.get("max"), "Waveform maximum", low, 64)
            number(block.get("rms"), "Waveform RMS", 0, 64)
        if end != source["start_sample"] + source["samples"]:
            raise ValueError("The waveform does not cover every decoded source sample.")
    return analysis


def _run(argv, log, event, deadline, tick=lambda: None, env=None):
    from adapters import _terminate_owned
    _cancel(event, deadline)
    process = None
    with log.open("xb") as stream:
        try:
            process = subprocess.Popen([str(value) for value in argv], stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, env=env, start_new_session=True)
            while process.poll() is None:
                _cancel(event, deadline); tick()
                if log.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("The synchronization engine emitted excessive diagnostics.")
                event.wait(.05)
            _cancel(event, deadline); tick()
            if process.returncode:
                stream.flush()
                with log.open("rb") as source:
                    source.seek(max(0, log.stat().st_size - 2000))
                    detail = source.read().decode(errors="replace")
                raise ValueError("Synchronization engine failed: " + detail)
        finally:
            if process is not None:
                _terminate_owned(process)


def _source_clock(path, video_index, audio_index, event=None, deadline=None):
    """Refuse camera files whose decoded sound/picture origins need conforming.

    Source playback/export reset each decoded stream to zero. A container with
    an authored audio delay would otherwise make measured sound imply a false
    picture alignment. Exact first decoded PTS also handles AAC priming without
    mistaking a negative encoded packet timestamp for audible samples.
    """
    from engine import _executable
    _cancel(event, deadline)
    timeout = min(10., max(.1, deadline - time.monotonic())) if deadline is not None else 10.
    argv = [_executable("ffprobe"), "-v", "error", "-threads", "1", "-read_intervals", "%+#64",
            "-show_frames", "-show_streams", "-show_entries",
            "stream=index,time_base:frame=stream_index,media_type,pts,best_effort_timestamp", "-of", "json", str(path)]
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    _cancel(event, deadline)
    if result.returncode or len(result.stdout) > 2 * 1024 ** 2:
        raise ValueError("The camera's decoded picture/audio origins could not be verified within their probe bound.")
    value = json.loads(result.stdout)
    streams = {item["index"]: item for item in value.get("streams", []) if type(item.get("index")) is int}
    origins = {}
    for index, kind in ((video_index, "video"), (audio_index, "audio")):
        frame = next((item for item in value.get("frames", []) if item.get("stream_index") == index and item.get("media_type") == kind), None)
        base = streams.get(index, {}).get("time_base", "")
        tick = frame.get("best_effort_timestamp", frame.get("pts")) if frame else None
        if (type(tick) is not int or not -(2 ** 63) < tick < 2 ** 63 or not isinstance(base, str)
                or not re.fullmatch(r"[1-9][0-9]{0,9}/[1-9][0-9]{0,9}", base)):
            raise ValueError("The selected camera streams have no verified first decoded sample/picture clock.")
        origins[kind] = {"first_pts": tick, "time_base": base}
    difference = (Fraction(origins["audio"]["first_pts"]) * Fraction(origins["audio"]["time_base"])
                  - Fraction(origins["video"]["first_pts"]) * Fraction(origins["video"]["time_base"])) * RATE
    if abs(difference) > 1:
        raise ValueError("The selected recorded sound and picture start at different times. Conform this camera's track origins before audio synchronization.")
    return {**origins, "audio_minus_video_samples": str(difference)}


def _sources(recipe, project, root, event=None, deadline=None):
    from engine import probe_media
    from media_management import asset_record
    sources = []
    for angle in recipe["angles"]:
        asset = asset_record(project, angle["asset_id"])
        path = _owned(root, asset["path"])
        source_stat = _stat_identity(path.lstat())
        identity = _digest(path, event=event, deadline=deadline)
        if identity["sha256"] != asset["sha256"]:
            raise ValueError("Original camera bytes changed since admission; relink the exact source before synchronizing.")
        actual = probe_media(path)
        stream = next((item for item in actual["audio_streams"] if item["index"] == angle["stream_index"]), None)
        if actual["kind"] != "video" or stream is None or not 1 <= stream["channels"] <= 32 or not 8000 <= stream["sample_rate"] <= 384000 or angle["channel"] >= stream["channels"]:
            raise ValueError("The selected recorded stream/channel does not match actual camera media.")
        clock = _source_clock(path, actual["video_stream_index"], angle["stream_index"], event, deadline)
        if _stat_identity(path.lstat()) != source_stat:
            raise ValueError("Original camera source changed while verifying its recorded streams.")
        sources.append({"asset_id": asset["id"], "source_sha256": identity["sha256"], "source_bytes": identity["size"],
                        "stream_index": angle["stream_index"], "channel": angle["channel"],
                        "recorded_channels": stream["channels"], "recorded_sample_rate": stream["sample_rate"],
                        "video_duration": actual["duration"], "presentation_origin": clock,
                        "start_sample": angle["start_sample"], "path": path, "stat": source_stat})
    return sources


def run_multicam_sync(project, project_dir, recipe, output_dir, progress=None, cancel_event=None, python=None):
    """Analyze real source samples and publish an owned, immutable receipt.

    A completed analysis may explicitly reject an ambiguous/silent source. That
    evidence remains reviewable, but apply refuses it and performs no edit.
    """
    from engine import validate_project, _executable
    from timebase import project_rate
    event = cancel_event or threading.Event(); deadline = time.monotonic() + TOTAL_SECONDS
    _cancel(event, deadline)
    root = Path(project_dir).resolve(strict=True)
    project = validate_project(project, root)
    recipe = validate_sync_recipe(recipe, project)
    output = Path(output_dir)
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Synchronization output must belong to this project.") from exc
    if len(relative.parts) != 3 or relative.parts[:2] != (DIRECTORY, "outputs"):
        raise ValueError("Synchronization output must use multicam-sync/outputs/<owned-job-id>.")
    _identifier(relative.name, "Synchronization output")
    if output.exists() or output.is_symlink():
        raise ValueError("A synchronization output already exists at this identifier.")
    capabilities = sync_capabilities(python)
    if not capabilities["available"]:
        raise ValueError(capabilities["reason"])
    identities = {name: _digest(Path(__file__).with_name(name), 4 * 1024 ** 2)["sha256"]
                  for name in ("multicam_sync.py", "multicam_sync_worker.py")}
    sources = _sources(recipe, project, root, event, deadline)
    parent = _owned(root, f"{DIRECTORY}/outputs", directory=True, create=True)
    if shutil.disk_usage(parent).free < len(sources) * recipe["window_samples"] * 4 + 64 * 1024 ** 2:
        raise ValueError("Not enough free disk space for the bounded synchronization sample evidence.")
    if progress:
        progress(.03)
    with tempfile.TemporaryDirectory(prefix=f".{relative.name}-building-", dir=parent) as temporary:
        scratch = Path(temporary); generated = scratch / "result"; generated.mkdir()
        records = []
        for index, source in enumerate(sources):
            _cancel(event, deadline)
            filename = f"samples_{index:02d}.f32le"; pcm = generated / filename
            start = source["start_sample"]
            end = min(start + recipe["window_samples"], math.floor(Fraction(str(source["video_duration"])) * RATE))
            graph = f"asetpts=PTS-STARTPTS,aresample={RATE},pan=mono|c0=c{source['channel']},atrim=start_sample={start}:end_sample={end},asetpts=PTS-STARTPTS"
            argv = [_executable("ffmpeg"), "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
                    "-protocol_whitelist", "file,pipe", "-i", str(source["path"]), "-map", f"0:{source['stream_index']}",
                    "-vn", "-sn", "-dn", "-af", graph, "-c:a", "pcm_f32le", "-f", "f32le", str(pcm)]
            def tick():
                if pcm.exists() and pcm.stat().st_size > recipe["window_samples"] * 4:
                    raise ValueError("Decoded synchronization samples exceeded their exact window bound.")
                if progress:
                    progress(.03 + .42 * (index + .5) / len(sources))
            _run(argv, scratch / f"decode_{index:02d}.log", event, deadline, tick)
            identity = _digest(pcm, recipe["window_samples"] * 4, event, deadline)
            if not identity["size"] or identity["size"] % 4:
                raise ValueError("A selected camera channel decoded no complete samples in its requested window.")
            records.append({"asset_id": source["asset_id"], "filename": filename, "start_sample": start,
                            "samples": identity["size"] // 4, "sha256": identity["sha256"]})
        request = {"version": VERSION, "reference_asset_id": recipe["reference_asset_id"], "sources": records,
                   "max_lag_samples": recipe["max_lag_samples"], "min_overlap_samples": recipe["min_overlap_samples"]}
        manifest = scratch / "request.json"; _write(manifest, request)
        log = scratch / "worker.log"
        def report_progress():
            if not progress or not log.exists() or log.stat().st_size > 65536:
                return
            try:
                for line in reversed(log.read_text().splitlines()):
                    value = json.loads(line).get("progress")
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1:
                        progress(.45 + .45 * value); return
            except (ValueError, AttributeError, OSError):
                return
        _run([capabilities["python"], "-I", "-B", Path(__file__).with_name("multicam_sync_worker.py"),
              "--request", manifest, "--directory", generated], log, event, deadline, report_progress, _environment())
        analysis = _read(generated / "analysis.json")
        waveforms = _read(generated / "waveforms.json")
        validate_measurement_result(analysis, waveforms, recipe, records, identities["multicam_sync_worker.py"])
        source_records = []
        for source, decoded in zip(sources, records):
            if source["stat"] != _stat_identity(source["path"].lstat()):
                raise ValueError("Original camera source changed during synchronization.")
            source_records.append({key: value for key, value in source.items() if key not in ("path", "stat")} | {
                "samples": decoded["samples"], "sample_file": decoded["filename"], "sample_sha256": decoded["sha256"]})
        for name, digest in identities.items():
            if _digest(Path(__file__).with_name(name), 4 * 1024 ** 2)["sha256"] != digest:
                raise ValueError("Synchronization code changed during measurement.")
        _write(generated / "recipe.json", recipe)
        names = artifact_names(len(sources))
        if {p.name for p in generated.iterdir()} != names - {"receipt.json"}:
            raise ValueError("Synchronization produced an unexpected artifact inventory.")
        inventory = {name: _digest(generated / name, MAX_JSON_BYTES if name.endswith(".json") else MAX_WINDOW * 4, event, deadline)
                     for name in sorted(names - {"receipt.json"})}
        if sum(item["size"] for item in inventory.values()) > MAX_OUTPUT_BYTES:
            raise ValueError("Synchronization artifacts exceed their total byte bound.")
        receipt = {"format": "cinematicum-multicam-sync", "version": VERSION, "output_id": relative.name,
                   "project_id": project["id"], "sequence_id": project.get("sequence_id", "main"),
                   "project_rate": project_rate(project).as_dict(), "algorithm": ALGORITHM, "rate": RATE,
                   "recipe_sha256": hashlib.sha256(_json(recipe)).hexdigest(), "recipe": recipe,
                   "sources": source_records, "accepted": analysis["accepted"], "artifacts": inventory,
                   "runtime": analysis["runtime"], "implementation_sha256": identities,
                   "scope": "A constant measured sample offset and only the common decoded sound window; no clock-drift correction, timecode sync, or external audio lock."}
        _write(generated / "receipt.json", receipt)
        artifacts = {name: {**_digest(generated / name, MAX_JSON_BYTES if name.endswith(".json") else MAX_WINDOW * 4, event, deadline),
                            "path": str(relative / name)} for name in sorted(names)}
        _cancel(event, deadline)
        if output.exists() or output.is_symlink():
            raise ValueError("The synchronization destination appeared before publication.")
        os.rename(generated, output)
        fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    if progress:
        progress(1)
    return {"output_id": relative.name, "accepted": analysis["accepted"], "analysis": analysis,
            "waveforms": waveforms, "artifacts": artifacts, "receipt": receipt,
            "provenance": {"kind": "measured-multicam-audio", "recipe_sha256": receipt["recipe_sha256"], "runtime": receipt["runtime"]}}


def load_measurement(project, project_dir, output_id, receipt_sha256, cancel_event=None):
    """Verify an owned job receipt, every sample artifact, and original sources."""
    from timebase import project_rate
    root = Path(project_dir).resolve(strict=True)
    _identifier(output_id, "Synchronization output")
    if not isinstance(receipt_sha256, str) or not HASH.fullmatch(receipt_sha256):
        raise ValueError("Applying synchronization requires its published receipt SHA-256.")
    directory = _owned(root, f"{DIRECTORY}/outputs/{output_id}", directory=True)
    path = _owned(directory, "receipt.json")
    _cancel(cancel_event)
    receipt = _read(path, expected={"sha256": receipt_sha256})
    if (receipt.get("format") != "cinematicum-multicam-sync" or receipt.get("version") != VERSION
            or receipt.get("algorithm") != ALGORITHM or receipt.get("rate") != RATE
            or receipt.get("output_id") != output_id
            or receipt.get("sequence_id") != project.get("sequence_id", "main")
            or receipt.get("project_rate") != project_rate(project).as_dict()):
        raise ValueError("This measurement belongs to another project, sequence, or exact project clock.")
    recipe = validate_sync_recipe(receipt.get("recipe"), project)
    if recipe != receipt["recipe"] or hashlib.sha256(_json(recipe)).hexdigest() != receipt.get("recipe_sha256"):
        raise ValueError("The synchronization recipe does not match its published identity.")
    names = artifact_names(len(recipe["angles"]))
    if set(receipt.get("artifacts", {})) != names - {"receipt.json"} or {p.name for p in directory.iterdir()} != names:
        raise ValueError("The published synchronization inventory is incomplete or contains foreign files.")
    records = {}
    for name, expected in receipt["artifacts"].items():
        _cancel(cancel_event)
        if not isinstance(expected, dict) or set(expected) != {"sha256", "size"}:
            raise ValueError("The published synchronization artifact identity is invalid.")
        if name.endswith(".json"):
            records[name] = _read(_owned(directory, name), expected=expected)
        else:
            actual = _digest(_owned(directory, name), MAX_WINDOW * 4, cancel_event)
            if actual != expected:
                raise ValueError("Synchronization waveform or sample bytes changed after publication.")
    deadline = time.monotonic() + TOTAL_SECONDS
    sources = _sources(recipe, project, root, cancel_event, deadline)
    if len(receipt.get("sources", [])) != len(sources):
        raise ValueError("The synchronization source binding count changed.")
    for current, recorded, angle in zip(sources, receipt["sources"], recipe["angles"]):
        expected = {key: value for key, value in current.items() if key not in ("path", "stat")}
        if any(recorded.get(key) != value for key, value in expected.items()):
            raise ValueError("The measurement no longer binds to the selected original source samples.")
        sample_count = _integer(recorded.get("samples"), "Measured sample count", 1, recipe["window_samples"])
        sample_file = recorded.get("sample_file")
        if sample_file not in names or not sample_file.endswith(".f32le") or receipt["artifacts"][sample_file] != {"sha256": recorded.get("sample_sha256"), "size": sample_count * 4}:
            raise ValueError("The recorded mono sample identity is inconsistent.")
    analysis = records["analysis.json"]
    # Origin project IDs remain historical provenance when an exact portable
    # package is restored. Ownership is this project's real output directory;
    # actual source/sample hashes and the sequence clock are reverified above.
    worker_hash = receipt.get("implementation_sha256", {}).get("multicam_sync_worker.py")
    if not isinstance(worker_hash, str) or not HASH.fullmatch(worker_hash):
        raise ValueError("The measurement has no bound worker implementation identity.")
    validate_measurement_result(analysis, records["waveforms.json"], recipe, receipt["sources"], worker_hash)
    if receipt.get("accepted") is not True or analysis.get("accepted") is not True or analysis.get("reason") != "measured":
        raise ValueError("This analysis rejected synchronization; ambiguous, silent or inconsistent offsets cannot create a group.")
    if analysis.get("rate") != RATE or analysis.get("algorithm") != ALGORITHM:
        raise ValueError("Unsupported synchronization analysis clock or method.")
    return receipt, analysis


def validate_group_synchronization(group, assets, rate):
    """Engine hook: keep persisted measured offsets bound to their exact source."""
    value = group.get("synchronization")
    if value is None:
        return
    expected_keys = {"version", "method", "output_id", "receipt_sha256", "rate", "project_rate", "reference_asset_id", "verified_samples", "angles"}
    if (not isinstance(value, dict) or set(value) != expected_keys or type(value["version"]) is not int or value["version"] != VERSION
            or value["method"] != ALGORITHM or value["rate"] != RATE or value["project_rate"] != rate.as_dict()
            or not HASH.fullmatch(str(value["receipt_sha256"]))):
        raise ValueError("The measured multicamera synchronization binding is invalid or its project clock changed.")
    _identifier(value["output_id"], "Synchronization measurement")
    _integer(value["verified_samples"], "Verified multicamera overlap", MIN_OVERLAP, MAX_WINDOW)
    records = value["angles"]
    if not isinstance(records, list) or len(records) != len(group["angles"]):
        raise ValueError("Measured multicamera angle bindings are incomplete.")
    seen = set()
    for angle, record in zip(group["angles"], records):
        if not isinstance(record, dict) or set(record) != {"asset_id", "source_sha256", "source_in_samples", "offset_samples", "stream_index", "channel", "sample_sha256"}:
            raise ValueError("Invalid measured camera sample binding.")
        asset = assets.get(angle["asset_id"])
        if (record["asset_id"] != angle["asset_id"] or record["asset_id"] in seen or asset is None
                or record["source_sha256"] != asset.get("sha256") or not HASH.fullmatch(str(record["sample_sha256"]))):
            raise ValueError("Measured multicamera sources changed; remeasure the intended camera media.")
        seen.add(record["asset_id"])
        samples = _integer(record["source_in_samples"], "Measured source sample", 0, MAX_START + MAX_WINDOW)
        _integer(record["offset_samples"], "Measured signed offset", -MAX_START - MAX_LAG, MAX_START + MAX_LAG)
        if rate.samples_for_frames(angle["in"], RATE) != samples:
            raise ValueError("A measured multicamera source offset changed; clear its measured binding or remeasure.")
        _integer(record["stream_index"], "Measured audio stream", 0, 255)
        stream = next((item for item in asset.get("audio_streams", []) if item.get("index") == record["stream_index"]), None)
        if stream is None:
            raise ValueError("A measured camera audio stream is missing.")
        _integer(record["channel"], "Measured audio channel", 0, stream["channels"] - 1)
    if value["reference_asset_id"] not in seen:
        raise ValueError("The measured reference camera is missing.")
    reference = next(record for record in records if record["asset_id"] == value["reference_asset_id"])
    if reference["offset_samples"] != 0 or any(record["source_in_samples"] + record["offset_samples"] != reference["source_in_samples"] for record in records):
        raise ValueError("Measured camera samples do not describe one shared sound origin.")


def apply_synchronization(project, project_dir, output_id, receipt_sha256, *, name="Synchronized multicam", start=0, track=0):
    """Return one fully validated candidate, without saving or modifying input.

    The normal project validator preserves fractional source frames and checks
    every measured group against its admitted source and exact sample clock.
    """
    from engine import validate_project
    from editorial import _locked
    from timebase import project_rate
    candidate = validate_project(project, project_dir)
    _locked(candidate)
    rate = project_rate(candidate)
    receipt, analysis = load_measurement(candidate, project_dir, output_id, receipt_sha256)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200 or "\x00" in name:
        raise ValueError("A multicamera group name needs 1–200 characters.")
    start = _integer(start, "Multicamera start", 0, rate.max_timeline_frames(21600))
    track = _integer(track, "Multicamera picture track", 0, 15)
    common = analysis.get("common_overlap")
    if not isinstance(common, dict):
        raise ValueError("The analysis does not contain a verified common sound window.")
    length = _integer(common.get("samples"), "Verified overlap", MIN_OVERLAP, MAX_WINDOW)
    duration = rate.frames_for_seconds(Fraction(length, RATE), "floor")
    if duration < 1 or start + duration > rate.max_timeline_frames(21600):
        raise ValueError("The synchronized cut exceeds the project clock bounds.")
    measured = {item["asset_id"]: item for item in analysis["angles"]}
    sources = sorted(receipt["sources"], key=lambda item: item["asset_id"] != receipt["recipe"]["reference_asset_id"])
    groups = candidate.setdefault("multicam_groups", [])
    if len(groups) >= 64:
        raise ValueError("A project supports at most 64 multicamera groups.")
    angles, bindings = [], []
    assets = {asset["id"]: asset for asset in candidate["assets"]}
    for source in sources:
        asset_id = source["asset_id"]
        source_in = _integer(common["source_starts"].get(asset_id), "Synchronized source sample", 0, MAX_START + MAX_WINDOW)
        if source_in < source["start_sample"] or source_in + length > source["start_sample"] + source["samples"]:
            raise ValueError("The proposed cut extends beyond actual measured source samples.")
        frame = float(Fraction(source_in, RATE) * rate.fraction)
        if rate.samples_for_frames(frame, RATE) != source_in:
            raise ValueError("The project frame representation cannot preserve this source sample offset.")
        angles.append({"id": uuid.uuid4().hex, "asset_id": asset_id, "in": frame, "available": duration})
        bindings.append({"asset_id": asset_id, "source_sha256": source["source_sha256"], "source_in_samples": source_in,
                         "offset_samples": measured[asset_id]["offset_samples"], "stream_index": source["stream_index"],
                         "channel": source["channel"], "sample_sha256": source["sample_sha256"]})
    group = {"id": uuid.uuid4().hex, "name": name.strip(), "angles": angles,
             "synchronization": {"version": VERSION, "method": ALGORITHM, "output_id": output_id,
                                 "receipt_sha256": receipt_sha256, "rate": RATE, "project_rate": rate.as_dict(),
                                 "reference_asset_id": receipt["recipe"]["reference_asset_id"], "verified_samples": length,
                                 "angles": bindings}}
    validate_group_synchronization(group, assets, rate)
    groups.append(group)
    first = angles[0]
    clip = {"id": uuid.uuid4().hex, "asset_id": first["asset_id"], "track": track, "start": start,
            "duration": duration, "in": first["in"], "multicam": {"group_id": group["id"], "angle_id": first["id"]}}
    candidate.setdefault("clips", []).append(clip)
    candidate = validate_project(candidate, project_dir)
    return {"project": candidate, "group_id": group["id"], "clip_id": clip["id"], "output_id": output_id,
            "action": "multicam_auto_sync_apply", "duration": duration, "sample_rate": RATE}


def submit_analysis(store, project_id, payload):
    """Use the ordinary durable job queue without mutating an editor snapshot."""
    if not isinstance(payload, dict) or set(payload) - {"project", "recipe"}:
        raise ValueError("Camera synchronization accepts one project snapshot and sound selection.")
    project = store.analysis_snapshot(project_id, payload)
    recipe = validate_sync_recipe(payload.get("recipe"), project)
    directory = store.project_dir(project_id)
    def work(job_id, progress, event):
        result = run_multicam_sync(project, directory, recipe, directory / DIRECTORY / "outputs" / job_id,
                                  progress=progress, cancel_event=event)
        prefix = f"/api/projects/{project_id}/{DIRECTORY}/outputs/{job_id}/"
        for name, record in result["artifacts"].items():
            record["url"] = prefix + name
        return result
    return store.submit(project_id, "multicam-sync", work, {"project": project, "recipe": recipe})


def apply_plan(store, project_id, payload):
    if not isinstance(payload, dict) or set(payload) - {"project", "output_id", "receipt_sha256", "name", "start", "track"}:
        raise ValueError("Applying camera synchronization requires its exact measurement and proposed edit.")
    project = store.analysis_snapshot(project_id, payload)
    return apply_synchronization(project, store.project_dir(project_id), payload.get("output_id"), payload.get("receipt_sha256"),
                                 name=payload.get("name", "Synchronized multicam"), start=payload.get("start", 0), track=payload.get("track", 0))


def artifact(project_dir, output_id, name):
    """Resolve only an exact published artifact inside the current project."""
    _identifier(output_id, "Synchronization output")
    if name not in ARTIFACT_NAMES:
        raise ValueError("Unknown synchronization artifact.")
    root = Path(project_dir).resolve(strict=True)
    directory = _owned(root, f"{DIRECTORY}/outputs/{output_id}", directory=True)
    receipt_path = _owned(directory, "receipt.json")
    receipt = _read(receipt_path)
    if (not isinstance(receipt, dict) or receipt.get("format") != "cinematicum-multicam-sync"
            or receipt.get("version") != VERSION or receipt.get("output_id") != output_id
            or not isinstance(receipt.get("sources"), list)):
        raise ValueError("Invalid owned synchronization receipt.")
    names = artifact_names(len(receipt["sources"]))
    if (name not in names or not isinstance(receipt.get("artifacts"), dict)
            or set(receipt["artifacts"]) != names - {"receipt.json"}
            or {entry.name for entry in directory.iterdir()} != names):
        raise ValueError("The synchronization artifact inventory is incomplete or contains foreign files.")
    path = _owned(directory, name)
    actual = _digest(path, MAX_JSON_BYTES if name.endswith(".json") else MAX_WINDOW * 4)
    if name != "receipt.json" and actual != receipt["artifacts"][name]:
        raise ValueError("Synchronization artifact bytes changed after publication.")
    return path, actual

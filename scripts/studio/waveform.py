"""Cached waveforms measured from decoded source audio, in the mixer format.

FFmpeg reduces real 48 kHz stereo samples to min/max/RMS blocks. Python only
reads the small statistics file, never an entire movie's uncompressed audio.
The caller admits a source through its project media boundary before calling.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

if __package__:
    from .engine import RenderCancelled, _executable, _quote_filter_path, probe_media
else:
    from engine import RenderCancelled, _executable, _quote_filter_path, probe_media


SCHEMA = 2
SAMPLE_RATE = 48000
MAX_STATS_BYTES = 16 * 1024 * 1024


def _cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise RenderCancelled("Waveform decoding cancelled.")


def _cached_result(path, bins):
    if path.is_symlink():
        raise ValueError("A waveform cache file cannot be a symbolic link.")
    if not path.is_file() or path.stat().st_size > MAX_STATS_BYTES:
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        count = result["bins"]
        if (result["schema"] != SCHEMA or result["sample_rate"] != SAMPLE_RATE
                or result["channels"] != 2 or result["requested_bins"] != bins
                or not isinstance(count, int) or not 1 <= count <= 32768
                or len(result["sample_counts"]) != count
                or len(result["peaks"]) != 2):
            return None
        if any(not isinstance(n, int) or n < 1 for n in result["sample_counts"]):
            return None
        for channel in result["peaks"]:
            for name in ("min", "max", "rms"):
                values = channel[name]
                if len(values) != count or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                    return None
        result["cached"] = True
        return result
    except (OSError, KeyError, TypeError, ValueError):
        return None


def _parse_statistics(path, requested_bins, samples_per_bin):
    channels = [{"min": [], "max": [], "rms": []} for _ in range(2)]
    counts, current = [], {}

    def append_block():
        if not current:
            return
        try:
            count = int(float(current["lavfi.astats.Overall.Number_of_samples"]))
            if not 1 <= count <= samples_per_bin:
                raise ValueError("Unexpected decoded waveform block size.")
            values = []
            for index in (1, 2):
                prefix = f"lavfi.astats.{index}."
                low, high = float(current[prefix + "Min_level"]), float(current[prefix + "Max_level"])
                rms_db = float(current[prefix + "RMS_level"])
                rms = 0.0 if rms_db == -math.inf else 10 ** (rms_db / 20)
                if not all(math.isfinite(v) for v in (low, high, rms)):
                    raise ValueError("Source audio contains non-finite samples.")
                values.append((low, high, rms))
            counts.append(count)
            for channel, values in zip(channels, values):
                for name, value in zip(("min", "max", "rms"), values):
                    channel[name].append(round(value, 8))
        except (KeyError, OverflowError) as exc:
            raise ValueError("FFmpeg did not return complete waveform statistics.") from exc

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("frame:"):
                append_block()
                current = {}
            elif line.startswith("lavfi.astats.") and "=" in line:
                key, value = line.rstrip().split("=", 1)
                current[key] = value
        append_block()
    if not counts:
        raise ValueError("The source audio stream decoded no samples.")
    if len(counts) > 32768:
        raise ValueError("The source duration metadata is too inaccurate to build a waveform.")
    return {"schema": SCHEMA, "sample_rate": SAMPLE_RATE, "channels": 2,
            "duration": sum(counts) / SAMPLE_RATE,
            "samples_per_bin": samples_per_bin, "sample_counts": counts,
            "peaks": channels, "requested_bins": requested_bins,
            "bins": len(counts), "cached": False}


def extract_waveform(source, cache_dir, bins=512, cancel_event=None, *, stream_index=None, channels=None):
    """Measure an admitted source's selected audio stream/channel mapping.

    ``bins`` is the desired number of time blocks (32–4096). Container duration
    metadata chooses a block width; the returned duration and sample_counts
    come from decoded samples, including a final partial block. All amplitudes
    use normalized floating-point PCM. The two channels match export's stereo
    downmix, and values above 1 are retained if the source has that headroom.
    ``stream_index`` is the absolute container stream ID, not its audio ordinal.
    ``channels`` optionally selects the source channel feeding each stereo output,
    in the same order and with the same unity-gain pan as movie export.
    """
    _cancelled(cancel_event)
    if isinstance(bins, bool) or not isinstance(bins, int) or not 32 <= bins <= 4096:
        raise ValueError("Waveform bins must be an integer between 32 and 4096.")
    source = Path(source).resolve()
    metadata = probe_media(source)
    if not metadata.get("has_audio"):
        raise ValueError("This source has no audio stream.")
    selected_index = metadata["audio_stream_index"] if stream_index is None else stream_index
    if isinstance(selected_index, bool) or not isinstance(selected_index, int):
        raise ValueError("Waveform audio stream must be an integer source stream ID.")
    stream = next((item for item in metadata["audio_streams"] if item["index"] == selected_index), None)
    if stream is None:
        raise ValueError("Waveform audio stream is not present in this source.")
    if channels is not None:
        if (not isinstance(channels, list) or len(channels) != 2
                or any(isinstance(value, bool) or not isinstance(value, int)
                       or not 0 <= value < stream["channels"] for value in channels)):
            raise ValueError("Waveform channel mapping must select two valid source channel IDs.")
        channels = list(channels)
    duration = stream.get("duration") or metadata.get("audio_duration") or metadata["duration"]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("The audio stream has no finite duration.")
    samples_per_bin = max(1, math.ceil(duration * SAMPLE_RATE / bins))
    if samples_per_bin > 2_147_483_647:
        raise ValueError("The audio source is too long for waveform extraction.")
    cache_dir = Path(cache_dir)
    if cache_dir.is_symlink():
        raise ValueError("The waveform cache directory cannot be a symbolic link.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = cache_dir.resolve()
    stat = source.stat()
    fingerprint = [SCHEMA, str(source), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                   stat.st_ino, bins, SAMPLE_RATE, selected_index, channels]
    key = hashlib.sha256(json.dumps(fingerprint, separators=(",", ":")).encode()).hexdigest()
    cache_path = cache_dir / (key + ".json")
    cached = _cached_result(cache_path, bins)
    if cached is not None and cached.get("source_stream_index") == selected_index and cached.get("source_channels") == channels:
        _cancelled(cancel_event)
        return cached
    process = None
    with tempfile.TemporaryDirectory(prefix="cinematicum-waveform-") as temp_dir:
        stats_path = Path(temp_dir) / "stats.txt"
        channel_filter = "" if channels is None else f"pan=stereo|c0=c{channels[0]}|c1=c{channels[1]},"
        graph = (channel_filter + f"aresample={SAMPLE_RATE},aformat=sample_fmts=flt:channel_layouts=stereo,"
                 f"asetpts=PTS-STARTPTS,asetnsamples=n={samples_per_bin}:p=0,"
                 "astats=metadata=1:reset=1:measure_perchannel=Min_level+Max_level+RMS_level:"
                 "measure_overall=Number_of_samples,"
                 f"ametadata=mode=print:file='{_quote_filter_path(stats_path)}'")
        command = [_executable("ffmpeg"), "-v", "error", "-nostdin", "-threads", "2",
                   "-protocol_whitelist", "file,pipe", "-i", str(source),
                   "-map", f"0:{selected_index}", "-vn", "-af", graph,
                   "-f", "null", "-"]
        started = time.monotonic()
        try:
            with tempfile.TemporaryFile(mode="w+b") as errors:
                _cancelled(cancel_event)
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
                while process.poll() is None:
                    _cancelled(cancel_event)
                    if time.monotonic() - started > 180:
                        raise ValueError("Waveform decoding exceeded three minutes.")
                    if stats_path.exists() and stats_path.stat().st_size > MAX_STATS_BYTES:
                        raise ValueError("Waveform decoding produced excessive metadata.")
                    time.sleep(.05)
                _cancelled(cancel_event)
                if process.returncode:
                    errors.seek(0, os.SEEK_END)
                    errors.seek(max(0, errors.tell() - 3000))
                    detail = errors.read().decode("utf-8", errors="replace").strip()
                    raise ValueError("Waveform audio decoding failed: " + detail)
            if not stats_path.is_file() or stats_path.stat().st_size > MAX_STATS_BYTES:
                raise ValueError("Waveform decoding returned no bounded statistics file.")
            result = _parse_statistics(stats_path, bins, samples_per_bin)
            result.update(source_stream_index=selected_index, source_channels=channels)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    _cancelled(cancel_event)
    # A replacement/import during decoding must never poison the cached result.
    after = source.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino):
        raise ValueError("Source audio changed while building its waveform. Retry the request.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_dir,
                                         prefix="waveform-", suffix=".partial", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(result, stream, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        if cache_path.is_symlink():
            raise ValueError("A waveform cache file cannot be a symbolic link.")
        os.replace(temporary, cache_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result

"""Verified, selected-source PCM for the editor's live audio transport.

One immutable derivative contains one original container stream and its selected
source channels and an optional pitch-preserving source tempo. It never contains
clip gain, pan, placement or a rendered timeline mix.
The browser applies those edits to this single stereo source, avoiding platform
dependent multi-track media selection. Export continues to read original media.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
import time

from adapters import _cancelled, _run_owned
from engine import _media_path, _tempo_filters, probe_media
from media_management import (HASH, _owned_directory, _verified_bytes,
                              asset_record, digest_file)

VERSION = 2
RATE = 48_000
CHANNELS = 2
FRAME_BYTES = CHANNELS * 4
# A standard RIFF WAV is supported by the native media decoder. Do not silently
# wrap its 32-bit sizes, truncate a long source, or substitute an RF64 download.
MAX_PCM_BYTES = 0xFFFFFF00
MAX_FRAMES = MAX_PCM_BYTES // FRAME_BYTES
MAX_CACHE_BYTES = 16 * 1024 ** 3
DISK_RESERVE = 64 * 1024 ** 2
CACHE_DIRECTORY = "audio-sources"


def source_recipe(asset, stream_index=None, channels=None, playback_rate=1):
    """Validate against the admitted inventory without opening any user path."""
    if not asset.get("has_audio"):
        raise ValueError("This imported source has no audio stream.")
    index = asset.get("audio_stream_index") if stream_index is None else stream_index
    if type(index) is not int or not 0 <= index <= 255:
        raise ValueError("Choose an integer source audio stream ID.")
    stream = next((item for item in asset.get("audio_streams", [])
                   if item.get("index") == index), None)
    if stream is None:
        raise ValueError("The selected audio stream is not present in this source.")
    count = stream.get("channels")
    if type(count) is not int or not 1 <= count <= 32:
        raise ValueError("Live source audio supports between 1 and 32 source channels.")
    if channels is not None:
        if (not isinstance(channels, list) or len(channels) != 2
                or any(type(value) is not int or not 0 <= value < count for value in channels)):
            raise ValueError("Select exactly two existing, zero-based source audio channels.")
        channels = list(channels)
    if (isinstance(playback_rate, bool) or not isinstance(playback_rate, (int, float))
            or not math.isfinite(playback_rate) or not .01 <= playback_rate <= 64):
        raise ValueError("Live source audio speed must be between 0.01 and 64.")
    playback_rate = float(playback_rate)
    duration = asset.get("duration")
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration <= 0):
        raise ValueError("Live source audio requires a finite, positive source duration.")
    pad_frames = math.ceil(duration * RATE / playback_rate)
    if pad_frames > MAX_FRAMES:
        raise ValueError("This source exceeds the standard WAV live-audio size limit (about 3.1 hours).")
    return {"version": VERSION, "stream_index": index, "channels": channels,
            "source_channels": count, "rate": RATE, "output_channels": CHANNELS,
            "codec": "pcm_f32le", "pad_frames": pad_frames, "playback_rate": playback_rate}


def source_identity(asset, recipe):
    return hashlib.sha256(json.dumps({"source_sha256": asset["sha256"], "recipe": recipe},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _wav_header(frames):
    size = frames * FRAME_BYTES
    # IEEE float, fact sample count, and exact non-padded data size. Keeping this
    # header explicit also makes source_frames and padded_frames independently
    # checkable without a second lossy decode or a duration-metadata estimate.
    chunks = (b"fmt " + struct.pack("<IHHIIHHH", 18, 3, CHANNELS, RATE,
                                    RATE * FRAME_BYTES, FRAME_BYTES, 32, 0)
              + b"fact" + struct.pack("<II", 4, frames)
              + b"data" + struct.pack("<I", size))
    return b"RIFF" + struct.pack("<I", 4 + len(chunks) + size) + b"WAVE" + chunks


def _valid_wav(path, frames):
    header = _wav_header(frames)
    if path.stat().st_size != len(header) + frames * FRAME_BYTES:
        return False
    with path.open("rb") as stream:
        return stream.read(len(header)) == header


def _read_cache(project_dir, asset, recipe):
    key = source_identity(asset, recipe)
    directory = Path(project_dir) / CACHE_DIRECTORY
    if directory.is_symlink():
        raise ValueError("Source audio cache cannot be a symbolic link.")
    path, receipt_path = directory / (key + ".wav"), directory / (key + ".json")
    if (not path.is_file() or not receipt_path.is_file()
            or path.is_symlink() or receipt_path.is_symlink()):
        return None
    try:
        if receipt_path.stat().st_size > 64 * 1024:
            return None
        receipt = json.loads(receipt_path.read_text())
        frames, source_frames = receipt.get("frames"), receipt.get("source_frames")
        if (receipt.get("version") != VERSION or receipt.get("state") != "ready"
                or receipt.get("source_sha256") != asset["sha256"] or receipt.get("recipe") != recipe
                or receipt.get("cache_key") != key
                or type(frames) is not int or not 0 < frames <= MAX_FRAMES
                or type(source_frames) is not int or not 0 < source_frames <= frames
                or frames != max(source_frames, recipe["pad_frames"])
                or receipt.get("padded_frames") != frames - source_frames
                or receipt.get("byte_size") != path.stat().st_size
                or receipt.get("rate") != RATE or receipt.get("output_channels") != CHANNELS
                or receipt.get("codec") != "pcm_f32le"
                or receipt.get("playback_rate") != recipe["playback_rate"]
                or receipt.get("source_time_scale") != recipe["playback_rate"]
                or receipt.get("data_offset") != len(_wav_header(frames))
                or receipt.get("frame_bytes") != FRAME_BYTES
                or receipt.get("stream_index") != recipe["stream_index"]
                or receipt.get("channels") != recipe["channels"]
                or receipt.get("duration") != frames / RATE
                or not HASH.fullmatch(str(receipt.get("sha256", "")))
                or not _valid_wav(path, frames)
                or not _verified_bytes(path, receipt["sha256"])):
            return None
        return path, receipt
    except (OSError, ValueError, TypeError, OverflowError):
        return None


def cached_source(project, project_dir, asset_id, stream_index=None, channels=None, playback_rate=1):
    asset = asset_record(project, asset_id)
    recipe = source_recipe(asset, stream_index, channels, playback_rate)
    cached = _read_cache(project_dir, asset, recipe)
    if cached is None:
        return None
    original = _media_path(project_dir, asset["path"])
    if not _verified_bytes(original, asset["sha256"]):
        raise ValueError("The original audio source changed. Relink its recorded bytes before playback.")
    return {**cached[1], "asset_id": asset_id, "cached": True}


def source_file(project, project_dir, cache_key):
    if not isinstance(cache_key, str) or not HASH.fullmatch(cache_key):
        raise ValueError("Invalid source audio cache identity.")
    directory = Path(project_dir) / CACHE_DIRECTORY
    receipt_path = directory / (cache_key + ".json")
    if (directory.is_symlink() or receipt_path.is_symlink() or not receipt_path.is_file()
            or receipt_path.stat().st_size > 64 * 1024):
        raise FileNotFoundError("Verified source audio is not available.")
    try:
        receipt = json.loads(receipt_path.read_text())
        recipe = receipt["recipe"]
        candidates = [asset for asset in project.get("assets", [])
                      if asset.get("sha256") == receipt.get("source_sha256")]
        for asset in candidates:
            expected = source_recipe(asset, recipe.get("stream_index"), recipe.get("channels"), recipe.get("playback_rate", 1))
            if expected != recipe or source_identity(asset, expected) != cache_key:
                continue
            cached = _read_cache(project_dir, asset, expected)
            if cached and _verified_bytes(_media_path(project_dir, asset["path"]), asset["sha256"]):
                return cached
    except (KeyError, ValueError, TypeError, OSError):
        pass
    raise FileNotFoundError("The source audio cache no longer matches verified original media.")


def _cache_usage(directory):
    total = 0
    for entry in directory.iterdir():
        if entry.is_symlink():
            raise ValueError("Source audio cache contains an unowned symbolic link.")
        if entry.is_file():
            total += entry.stat().st_size
        elif entry.is_dir() and entry.name.startswith("build-"):
            for child in entry.iterdir():
                if child.is_symlink() or not child.is_file():
                    raise ValueError("Source audio build contains an unowned entry.")
                total += child.stat().st_size
    return total


def create_source(project, project_dir, asset_id, stream_index=None, channels=None,
                  progress=None, cancel_event=None, playback_rate=1):
    _cancelled(cancel_event)
    asset = asset_record(project, asset_id)
    recipe = source_recipe(asset, stream_index, channels, playback_rate)
    original = _media_path(project_dir, asset["path"])
    source_stat = original.stat()
    if digest_file(original, cancel_event) != asset["sha256"]:
        raise ValueError("The original audio source changed. Relink its recorded bytes before playback.")
    # Re-probe actual selected stream identity, not a caller's claimed metadata.
    metadata = probe_media(original)
    actual = source_recipe(metadata, recipe["stream_index"], recipe["channels"], recipe["playback_rate"])
    if actual["source_channels"] != recipe["source_channels"]:
        raise ValueError("Recorded and decoded source audio channel counts disagree.")
    cached = _read_cache(project_dir, asset, recipe)
    if cached is not None:
        return {**cached[1], "asset_id": asset_id, "cached": True}
    directory = _owned_directory(project_dir, CACHE_DIRECTORY)
    key = source_identity(asset, recipe)
    output, receipt_path = directory / (key + ".wav"), directory / (key + ".json")
    if output.is_symlink() or receipt_path.is_symlink():
        raise ValueError("Refusing a symbolic-link source audio destination.")
    expected = recipe["pad_frames"] * FRAME_BYTES
    if _cache_usage(directory) + 2 * expected > MAX_CACHE_BYTES:
        raise ValueError("Source audio cache exceeds its 16 GiB bound; remove unused project source caches before preparing more audio.")
    if shutil.disk_usage(directory).free < 2 * expected + DISK_RESERVE:
        raise ValueError("There is not enough free disk space to prepare this source audio safely.")
    with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as scratch:
        scratch = Path(scratch)
        raw, wav = scratch / "source.f32le", scratch / "source.wav"
        mapping = recipe["channels"]
        filters = ["asetpts=PTS-STARTPTS", f"aresample={RATE}"]
        if mapping is not None:
            filters.append(f"pan=stereo|c0=c{mapping[0]}|c1=c{mapping[1]}")
        filters.append("aformat=sample_fmts=flt:channel_layouts=stereo")
        if recipe["playback_rate"] != 1:
            filters.extend(_tempo_filters(recipe["playback_rate"]))
        command = [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-nostdin", "-y",
                   "-threads", "1", "-filter_threads", "1", "-protocol_whitelist", "file,pipe",
                   "-i", str(original), "-map", f"0:{recipe['stream_index']}", "-vn", "-sn", "-dn",
                   "-af", ",".join(filters), "-c:a", "pcm_f32le", "-f", "f32le", str(raw)]
        last_check = [0.0]

        def check_space():
            size = raw.stat().st_size if raw.exists() else 0
            if size > MAX_PCM_BYTES:
                raise ValueError("Decoded source audio exceeds the standard WAV size bound.")
            if time.monotonic() - last_check[0] >= .5:
                if _cache_usage(directory) > MAX_CACHE_BYTES or shutil.disk_usage(directory).free < DISK_RESERVE:
                    raise ValueError("Source audio preparation exhausted its cache or disk-space bound.")
                last_check[0] = time.monotonic()
            if progress:
                progress(.05 + .7 * min(1, size / max(1, expected)))

        _run_owned(command, scratch / "decode.log", cancel_event, 7200, on_tick=check_space)
        check_space()
        size = raw.stat().st_size
        if size <= 0 or size % FRAME_BYTES:
            raise ValueError("The selected source did not decode to complete stereo samples.")
        source_frames = size // FRAME_BYTES
        frames = max(source_frames, recipe["pad_frames"])
        if frames > MAX_FRAMES:
            raise ValueError("Decoded source audio exceeds the standard WAV size bound.")
        if _cache_usage(directory) + frames * FRAME_BYTES > MAX_CACHE_BYTES:
            raise ValueError("Source audio preparation exceeds its 16 GiB cache bound.")
        if shutil.disk_usage(directory).free < frames * FRAME_BYTES + DISK_RESERVE:
            raise ValueError("There is not enough free disk space to publish verified source audio.")
        with raw.open("rb") as source, wav.open("xb") as destination:
            destination.write(_wav_header(frames))
            while True:
                _cancelled(cancel_event)
                block = source.read(1024 * 1024)
                if not block:
                    break
                destination.write(block)
            remaining = (frames - source_frames) * FRAME_BYTES
            zeros = b"\0" * min(1024 * 1024, remaining)
            while remaining:
                _cancelled(cancel_event)
                count = min(remaining, len(zeros))
                destination.write(zeros[:count])
                remaining -= count
            destination.flush()
            os.fsync(destination.fileno())
        latest = original.stat()
        if ((source_stat.st_dev, source_stat.st_ino, source_stat.st_size,
             source_stat.st_mtime_ns, source_stat.st_ctime_ns)
                != (latest.st_dev, latest.st_ino, latest.st_size, latest.st_mtime_ns, latest.st_ctime_ns)):
            raise ValueError("The original media changed while preparing source audio.")
        receipt = {"version": VERSION, "state": "ready", "asset_id": asset_id,
                   "source_sha256": asset["sha256"], "cache_key": key, "recipe": recipe,
                   "stream_index": recipe["stream_index"], "channels": mapping,
                   "rate": RATE, "output_channels": CHANNELS, "codec": "pcm_f32le",
                   "playback_rate": recipe["playback_rate"], "source_time_scale": recipe["playback_rate"],
                   "data_offset": len(_wav_header(frames)), "frame_bytes": FRAME_BYTES,
                   "frames": frames, "source_frames": source_frames, "padded_frames": frames-source_frames,
                   "duration": frames / RATE, "sha256": digest_file(wav, cancel_event),
                   "byte_size": wav.stat().st_size, "created_at": time.time(), "export_source": "original"}
        if not _valid_wav(wav, frames):
            raise ValueError("Prepared source audio failed its exact PCM container check.")
        receipt_tmp = scratch / "receipt.json"
        with receipt_tmp.open("x") as stream:
            stream.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _cancelled(cancel_event)
        os.replace(wav, output)
        os.replace(receipt_tmp, receipt_path)
        fd = os.open(str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if progress:
            progress(1)
        return {**receipt, "cached": False}

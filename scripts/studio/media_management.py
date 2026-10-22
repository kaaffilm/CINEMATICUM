"""Owned preview proxies and byte-verified media relinking.

Proxy files never replace an asset's master path. Every proxy is tied to the
source bytes, the recipe and the decoded frame timestamps. Movie exports keep
using the original inventory. Relinking accepts the exact missing original;
an unrelated file with a matching name cannot silently change an edit.
"""
from __future__ import annotations

from fractions import Fraction
from collections import OrderedDict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time

from adapters import _run_owned, _cancelled
from engine import probe_media, _media_path

VERSION = 1
PROXY_EDGES = (640, 960, 1280, 1920)
HASH = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MAX_FRAMES = 1_300_000
_VERIFIED = OrderedDict()
_VERIFIED_LOCK = threading.Lock()


def digest_file(path, cancel_event=None):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            _cancelled(cancel_event)
            h.update(block)
    return h.hexdigest()


def asset_record(project, asset_id):
    if not isinstance(asset_id, str) or not ID.fullmatch(asset_id):
        raise ValueError("Invalid media asset identity.")
    asset = next((a for a in project.get("assets", []) if a.get("id") == asset_id), None)
    if asset is None or not HASH.fullmatch(str(asset.get("sha256", ""))):
        raise ValueError("Choose an imported asset with a recorded content identity.")
    return asset


def _owned_directory(project_dir, name):
    root = Path(project_dir).resolve()
    path = root / name
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("Media cache directory is not an owned directory.")
    path.mkdir(exist_ok=True)
    return path


def proxy_recipe(long_edge=960):
    if type(long_edge) is not int or long_edge not in PROXY_EDGES:
        raise ValueError("Proxy size must be 640, 960, 1280 or 1920 pixels.")
    return {"version": VERSION, "long_edge": long_edge, "codec": "h264",
            "crf": 18, "audio": "first-stream-mono-or-stereo-aac", "timestamp_scale": 1_000_000}


def _verified_bytes(path, expected):
    stat = path.stat()
    key = (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, expected)
    with _VERIFIED_LOCK:
        if key in _VERIFIED:
            _VERIFIED.move_to_end(key)
            return True
    if digest_file(path) != expected:
        return False
    with _VERIFIED_LOCK:
        _VERIFIED[key] = True
        while len(_VERIFIED) > 256:
            _VERIFIED.popitem(last=False)
    return True


def proxy_identity(asset, recipe):
    return hashlib.sha256(json.dumps({"source_sha256": asset["sha256"], "recipe": recipe},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_proxy(project_dir, asset, long_edge=960, verify_bytes=False):
    recipe = proxy_recipe(long_edge)
    key = proxy_identity(asset, recipe)
    directory = Path(project_dir) / "proxies"
    if directory.is_symlink():
        raise ValueError("Proxy cache cannot be a symlink.")
    path, receipt_path = directory / (key + ".mp4"), directory / (key + ".json")
    if not path.is_file() or not receipt_path.is_file() or path.is_symlink() or receipt_path.is_symlink():
        return None
    try:
        if receipt_path.stat().st_size > 128 * 1024:
            return None
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get("source_sha256") != asset["sha256"] or receipt.get("recipe") != recipe
                or receipt.get("identity") != key or receipt.get("size") != path.stat().st_size
                or not HASH.fullmatch(str(receipt.get("sha256", "")))):
            return None
        if not _verified_bytes(path, receipt["sha256"]):
            return None
        return path, receipt
    except (OSError, ValueError, TypeError):
        return None


def proxy_file(project, project_dir, asset_id, long_edge=960):
    asset = asset_record(project, asset_id)
    result = _read_proxy(project_dir, asset, long_edge)
    if result is None:
        raise FileNotFoundError("A verified preview proxy is not available for this source and size.")
    return result


def inventory(project, project_dir):
    root = Path(project_dir).resolve()
    rows = []
    for asset in project.get("assets", []):
        rel = Path(str(asset.get("path", "")))
        path = root / rel
        owned = (not rel.is_absolute() and len(rel.parts) == 2 and rel.parts[0] == "media"
                 and not path.is_symlink() and path.parent.resolve() == root / "media")
        present = owned and path.is_file()
        row = {"id": asset["id"], "name": asset.get("name", "Media"), "kind": asset.get("kind"),
               "source_sha256": asset.get("sha256"), "present": present,
               "size_matches": bool(present and path.stat().st_size == asset.get("size")), "proxies": []}
        if HASH.fullmatch(str(asset.get("sha256", ""))):
            for edge in PROXY_EDGES:
                cached = _read_proxy(root, asset, edge)
                if cached:
                    receipt = cached[1]
                    row["proxies"].append({k: receipt[k] for k in ("identity", "sha256", "width", "height", "size", "frames")})
                    row["proxies"][-1]["long_edge"] = edge
        rows.append(row)
    return {"assets": rows, "proxy_sizes": list(PROXY_EDGES), "export_source": "original"}


def _frame_times(path, scratch, label, event):
    output = Path(scratch) / (label + "-frames.csv")
    _run_owned([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(path)],
               output, event, 1800)
    if output.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Proxy timestamp verification exceeded its supported frame bound.")
    times = []
    with output.open() as stream:
        for line in stream:
            _cancelled(event)
            value = line.strip().split(",", 1)[0]
            if not value:
                continue
            try:
                stamp = Fraction(value)
            except (ValueError, ZeroDivisionError):
                raise ValueError("The decoder could not establish a source-frame timestamp.") from None
            if times and stamp <= times[-1]:
                raise ValueError("Preview proxies require strictly increasing decoded picture timestamps.")
            times.append(stamp)
            if len(times) > MAX_FRAMES:
                raise ValueError("Proxy source exceeds the supported decoded-frame bound.")
    if not times:
        raise ValueError("No source pictures were decoded for this proxy.")
    return times


def create_proxy(project, project_dir, asset_id, long_edge=960, progress=None, cancel_event=None):
    asset = asset_record(project, asset_id)
    if asset.get("kind") != "video":
        raise ValueError("Preview proxies are created from imported video assets.")
    recipe = proxy_recipe(long_edge)
    source = _media_path(project_dir, asset["path"])
    if digest_file(source, cancel_event) != asset["sha256"]:
        raise ValueError("The original media changed. Relink its recorded bytes before generating a proxy.")
    cached = _read_proxy(project_dir, asset, long_edge, verify_bytes=True)
    if cached:
        return {**cached[1], "asset_id": asset_id, "cached": True}
    directory = _owned_directory(project_dir, "proxies")
    key = proxy_identity(asset, recipe)
    output, receipt_path = directory / (key + ".mp4"), directory / (key + ".json")
    if output.is_symlink() or receipt_path.is_symlink():
        raise ValueError("Refusing a symlink proxy destination.")
    width, height = int(asset.get("width", 0)), int(asset.get("height", 0))
    if min(width, height) <= 0:
        raise ValueError("The source picture dimensions are unavailable.")
    factor = min(1, long_edge / max(width, height))
    target_width, target_height = max(2, math.floor(width * factor / 2) * 2), max(2, math.floor(height * factor / 2) * 2)
    with tempfile.TemporaryDirectory(prefix="proxy-build-", dir=directory) as scratch:
        scratch = Path(scratch)
        movie = scratch / "preview.mp4"
        if progress:
            progress(.05)
        command = [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-y",
                   "-threads", "1", "-filter_threads", "1", "-copyts", "-start_at_zero", "-i", str(source),
                   "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-vf",
                   f"scale={target_width}:{target_height}:flags=lanczos,setsar=1",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-fps_mode", "passthrough", "-enc_time_base", "1:1000000", "-video_track_timescale", "1000000",
                   "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1" if asset.get("audio_channels") == 1 else "2", "-threads", "1",
                   "-movflags", "+faststart", str(movie)]
        _run_owned(command, scratch / "encode.log", cancel_event, 7200)
        if progress:
            progress(.7)
        original_times = _frame_times(source, scratch, "source", cancel_event)
        preview_times = _frame_times(movie, scratch, "proxy", cancel_event)
        if len(original_times) != len(preview_times):
            raise ValueError("Proxy frame count differs from the original; the proxy was not admitted.")
        error = max(abs((a-original_times[0])-(b-preview_times[0])) for a,b in zip(original_times,preview_times))
        if error > Fraction(2, 1_000_000):
            raise ValueError("Proxy timestamps do not preserve the original frame cadence.")
        metadata = probe_media(movie)
        if (metadata["width"], metadata["height"]) != (target_width, target_height):
            raise ValueError("Proxy decoder dimensions do not match the render recipe.")
        _cancelled(cancel_event)
        receipt = {"version": VERSION, "identity": key, "source_sha256": asset["sha256"],
                   "recipe": recipe, "width": target_width, "height": target_height,
                   "size": movie.stat().st_size, "sha256": digest_file(movie, cancel_event),
                   "frames": len(preview_times), "relative_timestamp_error_seconds": float(error),
                   "source_first_timestamp": float(original_times[0]), "proxy_first_timestamp": float(preview_times[0]),
                   "created_at": time.time(), "export_source": "original"}
        receipt_tmp = scratch / "receipt.json"
        receipt_tmp.write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
        os.replace(movie, output)
        os.replace(receipt_tmp, receipt_path)
        if progress:
            progress(1)
        return {**receipt, "asset_id": asset_id, "cached": False}


def relink_original(project, project_dir, asset_id, incoming):
    """Restore exact bytes at the original owned path, preserving edit identity."""
    asset = asset_record(project, asset_id)
    root, incoming = Path(project_dir).resolve(), Path(incoming)
    rel = Path(str(asset.get("path", "")))
    if rel.is_absolute() or len(rel.parts) != 2 or rel.parts[0] != "media" or "\\" in str(rel):
        raise ValueError("The original asset has an invalid owned path.")
    media = root / "media"
    if media.is_symlink() or not media.is_dir() or incoming.is_symlink() or not incoming.is_file():
        raise ValueError("Relink requires an owned media directory and a selected regular file.")
    target = media / rel.name
    if target.is_symlink() or target.resolve().parent != media:
        raise ValueError("Refusing to relink through a symlink or external path.")
    if digest_file(incoming) != asset["sha256"]:
        raise ValueError("Selected bytes do not match the original SHA-256. Import a different take as new media.")
    if incoming.stat().st_size != asset.get("size"):
        raise ValueError("Selected original size does not match the recorded media.")
    if target.is_file() and digest_file(target) == asset["sha256"]:
        return {"asset_id": asset_id, "restored": False, "already_present": True, "sha256": asset["sha256"]}
    if target.exists():
        if not target.is_file():
            raise ValueError("The original destination is not a regular file.")
        quarantine = _owned_directory(root, "relinked-originals")
        backup = quarantine / (digest_file(target) + target.suffix)
        if backup.is_symlink():
            raise ValueError("Refusing an invalid relink backup destination.")
        if not backup.exists():
            shutil.copy2(target, backup)
    with tempfile.NamedTemporaryFile(prefix="restore-", suffix=target.suffix, dir=media, delete=False) as stream:
        temp = Path(stream.name)
        try:
            with incoming.open("rb") as source:
                shutil.copyfileobj(source, stream, 1024 * 1024)
            stream.flush(); os.fsync(stream.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        if digest_file(temp) != asset["sha256"]:
            raise ValueError("Original copy did not retain its recorded identity.")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return {"asset_id": asset_id, "restored": True, "already_present": False, "sha256": asset["sha256"]}

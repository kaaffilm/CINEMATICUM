"""Immutable TAPNext overlay; the existing SAM/TAPIR environment is untouched."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat

LOCK = Path(__file__).with_name("tapnext-runtime-lock.json")
NAMESPACE = b"# Isolated application-owned namespace for the exact upstream TAPNext modules.\n"


def default_destination():
    support = Path.home() / "Library/Application Support" if os.sys.platform == "darwin" else Path.home() / ".local/share"
    return support / "CINEMATICUM/TAPNext/cpu-v1"


def load_lock():
    raw = LOCK.read_bytes()
    if len(raw) > 128 * 1024:
        raise ValueError("TAPNext lock exceeds its bound")
    lock = json.loads(raw)
    if lock.get("schema") != "cinematicum-tapnext-runtime-lock" or lock.get("version") != 1 or lock.get("device") != "cpu":
        raise ValueError("Unsupported TAPNext runtime lock")
    records = lock.get("files")
    if not isinstance(records, list) or not 4 <= len(records) <= 128:
        raise ValueError("Missing TAPNext source inventory")
    paths = set()
    for record in records:
        name = record.get("path", "")
        if not isinstance(name, str):
            raise ValueError("Invalid TAPNext source path")
        path = Path(name)
        if (not isinstance(name, str) or path.is_absolute() or ".." in path.parts or path.as_posix() != name
                or not name.startswith(("tapnet/", "einops/")) or name in paths
                or not re.fullmatch(r"[a-f0-9]{64}", record.get("sha256", ""))
                or type(record.get("size")) is not int or not 0 <= record["size"] < 1024 * 1024):
            raise ValueError("Invalid TAPNext source identity")
        paths.add(name)
    model = lock.get("models", {}).get("tapnext", {})
    if (model.get("name") != "bootstapnext_ckpt.npz" or model.get("bytes") != 776980182
            or model.get("sha256") != "19de6b1495555c2afb4b56e823a3f3c2fd7236eea05c53d98feab3cccd1b4a28"):
        raise ValueError("Unsupported official TAPNext checkpoint")
    return lock, hashlib.sha256(raw).hexdigest()


def hash_file(path, maximum):
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("TAPNext bytes cannot traverse a symbolic link")
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= maximum:
            raise ValueError("TAPNext requires bounded regular files")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("TAPNext bytes changed during verification")
    return digest.hexdigest(), before.st_size


def verify_layout(directory=None):
    lock, lock_sha = load_lock()
    selected = directory or os.environ.get("CINEMATICUM_TAPNEXT_HOME") or default_destination()
    root = Path(selected).expanduser()
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Install the pinned TAPNext runtime before inference")
    root = root.resolve(strict=True)
    source = root / "source"
    expected = {record["path"] for record in lock["files"]}
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file() and p.suffix != ".pyc"}
    if actual != expected:
        raise ValueError("TAPNext source inventory differs from the pinned overlay")
    digest = hashlib.sha256()
    for record in lock["files"]:
        value, size = hash_file(source / record["path"], 1024 * 1024)
        if (value, size) != (record["sha256"], record["size"]):
            raise ValueError("TAPNext source differs from its pinned upstream bytes")
        digest.update((record["path"] + "\0" + value + "\n").encode())
    model = lock["models"]["tapnext"]
    checkpoint = root / model["name"]
    if hash_file(checkpoint, model["bytes"]) != (model["sha256"], model["bytes"]):
        raise ValueError("TAPNext checkpoint differs from the official SHA-256 identity")
    return {"root": root, "source": source, "checkpoint": checkpoint, "lock": lock,
            "lock_sha256": lock_sha, "upstream_source_sha256": digest.hexdigest()}

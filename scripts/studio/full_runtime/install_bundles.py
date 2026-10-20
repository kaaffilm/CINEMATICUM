#!/usr/bin/env python3
"""Build-time verified extraction. Never fetch or resolve versions at runtime."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from prepare import IDS, atomic_json, verify


def contained(root, path):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def extract_tar(archive, target):
    with tarfile.open(str(archive), "r:*") as bundle:
        members = bundle.getmembers()
        if len(members) > 300000:
            raise ValueError("Archive member limit exceeded")
        total = 0
        for member in members:
            path = target / member.name
            if member.name.startswith("/") or not contained(target, path):
                raise ValueError("Archive contains an escaping member")
            if member.isdev() or member.isfifo():
                raise ValueError("Archive device members are not supported")
            if member.issym() and not contained(target, path.parent / member.linkname):
                raise ValueError("Archive contains an escaping symlink")
            if member.islnk() and not contained(target, target / member.linkname):
                raise ValueError("Archive contains an escaping hardlink")
            total += max(0, member.size)
            if total > 12 * 1024 ** 3:
                raise ValueError("Expanded archive exceeds limit")
        # Python 3.12+ supplies the second path/symlink safety check at extraction.
        bundle.extractall(str(target), filter="data")


def find_entry(target, names):
    roots = [target] + [x for x in target.iterdir() if x.is_dir()]
    for root in roots:
        for name in names:
            entry = root / name
            if entry.is_file() and contained(target, entry):
                entry.chmod(entry.stat().st_mode | 0o111)
                return entry, root
    raise ValueError("Expected application entrypoint absent: " + ", ".join(names))


def install(source, destination, allow_partial=False):
    lock = verify(source, None if allow_partial else IDS)
    installed = []
    for item in lock["engines"]:
        target = destination / item["id"]
        target.mkdir(parents=True, exist_ok=False)
        archive = source / item["archive"]
        if item["kind"] == "appimage":
            archive.chmod(0o755)
            subprocess.run([str(archive), "--appimage-extract"], cwd=str(target),
                           stdout=subprocess.DEVNULL, check=True, timeout=300)
            extracted = target / "squashfs-root"
            if not extracted.is_dir():
                raise ValueError("AppImage did not produce squashfs-root")
            entry, appdir = find_entry(extracted, item["entrypoints"])
        elif item["kind"] == "tar":
            extract_tar(archive, target)
            entry, appdir = find_entry(target, item["entrypoints"])
        else:
            raise ValueError("Unsupported archive format")
        if not os.access(str(entry), os.X_OK):
            raise ValueError("Application entrypoint is not executable")
        value = dict(item)
        value.update({"executable": str(entry), "appdir": str(appdir)})
        installed.append(value)
    atomic_json(Path("/opt/cinematicum/installed.json"), {
        "schema": 1, "platform": "linux/amd64", "engines": installed,
        "mode": "native-editor-sessions", "gpu": "software-mesa",
        "complete_set": {x["id"] for x in installed} == IDS,
    })
    shutil.copy2(str(source / "engines.lock.json"), "/opt/cinematicum/engines.lock.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/bundles"))
    parser.add_argument("--destination", type=Path, default=Path("/opt/editors"))
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    install(args.source, args.destination, args.allow_partial)

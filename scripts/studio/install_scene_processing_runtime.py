#!/usr/bin/env python3
"""Install the exact upstream Linux Cycles runtime used by scene acceptance.

No package resolver, source build or caller-controlled download URL is used.
The upstream archive is SHA-256 pinned; every extracted file/link is inventoried
and checked on reuse. macOS continues to use the explicitly installed Blender
application via scene.find_blender; this helper does not certify a Mac runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request

VERSION = "4.5.14"
ARCHIVE_NAME = "blender-4.5.14-linux-x64.tar.xz"
ROOT_NAME = "blender-4.5.14-linux-x64"
URL = "https://download.blender.org/release/Blender4.5/" + ARCHIVE_NAME
SHA256 = "9ba871ff2ecd36526b77432745980b7e6664ecd0c7ca11c48849073dcfe06da3"
SIZE = 378045212
BUILD = "62c1db4208e8"
MAX_EXTRACTED = 2 * 1024 * 1024 * 1024


def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def _inventory(root):
    entries, total = [], 0
    for path in sorted(root.rglob("*")):
        info = path.lstat(); relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            if not path.resolve().is_relative_to(root.resolve()): raise ValueError("Runtime contains an escaping symbolic link.")
            entries.append({"path": relative, "kind": "symlink", "target": target})
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > MAX_EXTRACTED: raise ValueError("Extracted runtime exceeds its 2 GiB bound.")
            entries.append({"path": relative, "kind": "file", "size": info.st_size, "mode": stat.S_IMODE(info.st_mode), "sha256": _sha(path)})
        elif not stat.S_ISDIR(info.st_mode): raise ValueError("Runtime contains an unsupported filesystem object.")
    return {"files": entries, "bytes": total}


def _verify_binary(binary):
    result = subprocess.run([str(binary), "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
    text = result.stdout.decode("utf-8", "strict")
    if not text.startswith("Blender " + VERSION + " LTS\n") or "build hash: " + BUILD not in text:
        raise ValueError("Actual Blender executable does not report the pinned release/build identity.")
    return text


def install(directory, check=False):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise ValueError("This exact managed runtime targets Linux x86_64 only.")
    directory = Path(directory).absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)): raise ValueError("Runtime paths cannot contain symbolic links.")
    marker = directory / "cinematicum-runtime.json"
    binary = directory / ROOT_NAME / "blender"
    if directory.exists():
        if not marker.is_file() or marker.is_symlink(): raise ValueError("Choose a new empty/nonexistent directory or an existing managed scene runtime.")
        receipt = json.loads(marker.read_text())
        if receipt.get("archive_sha256") != SHA256 or receipt.get("archive_size") != SIZE: raise ValueError("Runtime archive identity is not the pinned release.")
        actual = _inventory(directory / ROOT_NAME)
        if actual != receipt.get("inventory"): raise ValueError("Managed Blender runtime files differ from the accepted archive inventory.")
        if {p.name for p in directory.iterdir()} != {ROOT_NAME, "cinematicum-runtime.json"}: raise ValueError("Managed runtime contains unexpected extra files.")
        _verify_binary(binary)
        return {"available": True, "checked": True, "blender": str(binary), "version": VERSION, "build": BUILD,
                "archive_sha256": SHA256, "file_count": len(actual["files"]), "runtime_bytes": actual["bytes"]}
    if check: raise ValueError("The managed scene runtime is not installed.")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".scene-runtime-install-", dir=directory.parent) as temporary:
        temp = Path(temporary); archive = temp / ARCHIVE_NAME
        digest, count = hashlib.sha256(), 0
        request = urllib.request.Request(URL, headers={"User-Agent": "CINEMATICUM/scene-runtime-1"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("xb") as stream:
            if response.geturl() != URL: raise ValueError("The pinned runtime download redirected to a different URL.")
            while True:
                block = response.read(4 * 1024 * 1024)
                if not block: break
                count += len(block)
                if count > SIZE: raise ValueError("Runtime archive exceeded its exact release size.")
                digest.update(block); stream.write(block)
            stream.flush(); os.fsync(stream.fileno())
        if count != SIZE or digest.hexdigest() != SHA256: raise ValueError("Official runtime download failed its pinned size/SHA-256 identity.")
        staged = temp / "staged"; staged.mkdir(mode=0o700)
        with tarfile.open(archive) as source:
            members = source.getmembers(); total = 0
            for item in members:
                path = PurePosixPath(item.name)
                if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != ROOT_NAME:
                    raise ValueError("Unexpected runtime archive path.")
                if not (item.isfile() or item.isdir() or item.issym() or item.islnk()): raise ValueError("Unexpected runtime archive object.")
                total += item.size
                if total > MAX_EXTRACTED: raise ValueError("Runtime archive exceeds its unpacked byte bound.")
            source.extractall(staged, members=members, filter="data")
        # Restore execution for this exact hash-bound entry point if extraction
        # or workspace policy stripped the archive's executable mode. Do not
        # grant execution to the rest of the runtime tree.
        executable = staged / ROOT_NAME / "blender"
        executable.chmod(stat.S_IMODE(executable.stat().st_mode) | 0o111)
        version_text = _verify_binary(executable)
        inventory = _inventory(staged / ROOT_NAME)
        receipt = {"format": "CINEMATICUM_SCENE_RUNTIME", "version": 1, "blender_version": VERSION, "build": BUILD,
                   "archive_url": URL, "archive_sha256": SHA256, "archive_size": SIZE,
                   "upstream_checksums": "https://download.blender.org/release/Blender4.5/blender-4.5.14.sha256",
                   "actual_version_output": version_text, "inventory": inventory}
        (staged / "cinematicum-runtime.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        if directory.exists(): raise ValueError("Runtime destination was created concurrently; no existing files were replaced.")
        os.rename(staged, directory)
    return install(directory, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.root, args.check), sort_keys=True, indent=2))


if __name__ == "__main__": main()

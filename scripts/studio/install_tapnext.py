"""Install an isolated pinned TAPNext overlay without changing SAM2/TAPIR."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tapnext_runtime import default_destination, load_lock, hash_file, NAMESPACE


@contextmanager
def setup_lock(parent):
    path = parent / ".setup.lock"
    if path.is_symlink():
        raise ValueError("TAPNext setup lock cannot be a link")
    with path.open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another TAPNext setup is running") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def download(record, cache, cancel_event=None):
    from adapters import _cancelled
    name = record.get("name", record.get("filename"))
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError("Invalid pinned TAPNext archive name")
    size = record.get("bytes", record.get("size"))
    target = cache / name
    _cancelled(cancel_event)
    if target.is_symlink():
        raise ValueError("TAPNext download cannot replace a link")
    if target.exists():
        if hash_file(target, size) != (record["sha256"], size):
            raise ValueError("Existing TAPNext cache differs from its pinned identity; it was preserved")
        return target
    partial = target.with_name(target.name + ".part")
    if partial.is_symlink():
        raise ValueError("TAPNext partial download cannot be a link")
    first = partial.stat().st_size if partial.exists() else 0
    if not 0 <= first <= size:
        raise ValueError("Existing TAPNext partial download exceeds its pinned bound")
    if first < size:
        request = urllib.request.Request(record["url"], headers={"Range": f"bytes={first}-{size-1}"})
        with urllib.request.urlopen(request, timeout=5) as response:
            ranged = response.status == 206 and response.headers.get("Content-Range") == f"bytes {first}-{size-1}/{size}"
            if not ranged and not (first == 0 and response.status == 200 and response.headers.get("Content-Length") in (None, str(size))):
                raise ValueError("TAPNext server returned a different archive range")
            with partial.open("ab") as stream:
                received = first
                while received < size:
                    _cancelled(cancel_event)
                    block = response.read(min(1024 * 1024, size - received))
                    if not block:
                        raise ValueError("TAPNext archive was truncated; verified progress can resume")
                    stream.write(block)
                    received += len(block)
                stream.flush()
                os.fsync(stream.fileno())
    if hash_file(partial, size) != (record["sha256"], size):
        raise ValueError("TAPNext archive SHA-256 differs from its official pinned identity")
    _cancelled(cancel_event)
    os.rename(partial, target)
    return target


def unpack_source(directory, lock, archive, wheel):
    source = directory / "source"
    source.mkdir()
    records = {record["path"]: record for record in lock["files"]}
    written = set()
    def write(name, data):
        record = records[name]
        if (hashlib.sha256(data).hexdigest(), len(data)) != (record["sha256"], record["size"]):
            raise ValueError("Extracted TAPNext module differs from the official pinned source")
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.add(name)
    for name in lock["generated_namespaces"]:
        write(name, NAMESPACE)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            name = "/".join(Path(member.name).parts[1:])
            if name in records and name.startswith("tapnet/tapnext/"):
                if not member.isfile() or member.size != records[name]["size"]:
                    raise ValueError("Unsupported TAPNext source archive entry")
                write(name, tar.extractfile(member).read())
    with zipfile.ZipFile(wheel) as archive:
        for name in records:
            if name.startswith("einops/"):
                write(name, archive.read(name))
    if written != set(records):
        raise ValueError("TAPNext source extraction omitted a pinned module")


def probe(directory, cancel_event=None):
    from adapters import _cancelled, _terminate_owned
    from learned_tracking import find_learned_python
    executable = find_learned_python()
    if not executable:
        raise ValueError("Install the pinned learned Torch runtime before TAPNext setup")
    command = [executable, "-I", "-B", str(Path(__file__).with_name("tapnext_worker.py")),
               "--runtime", str(directory), "--install-probe"]
    process = None
    _cancelled(cancel_event)
    try:
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 90
            while process.poll() is None:
                _cancelled(cancel_event)
                if time.monotonic() >= deadline:
                    raise RuntimeError("TAPNext numerical setup probe exceeded 90 seconds")
                if cancel_event is None:
                    time.sleep(.1)
                else:
                    cancel_event.wait(.1)
            _cancelled(cancel_event)
            size = log.seek(0, os.SEEK_END)
            log.seek(max(0, size - 65536))
            output = log.read().decode("utf-8", "replace")
        if process.returncode:
            raise ValueError("TAPNext numerical setup probe failed: " + output[-2000:])
        report = json.loads(output)
        if not report.get("available") or not report.get("checks") or not all(report["checks"].values()):
            raise ValueError("TAPNext did not pass its actual checkpoint motion oracle")
        return report
    finally:
        if process is not None:
            _terminate_owned(process)


def install(check_only=False, cancel_event=None, progress=None):
    from adapters import _cancelled
    lock, digest = load_lock()
    from learned_tracking import find_learned_python
    if not find_learned_python():
        raise ValueError("Install the pinned learned Torch runtime before TAPNext setup")
    destination = default_destination()
    _cancelled(cancel_event)
    if os.path.lexists(destination):
        verification = probe(destination, cancel_event)
        return {"status": "verified", "runtime": str(destination), "lock_sha256": digest, "verification": verification}
    if check_only:
        raise ValueError("The pinned TAPNext overlay is not installed")
    parent = destination.parent
    if parent.is_symlink():
        raise ValueError("TAPNext parent cannot be an unrelated link")
    parent.mkdir(parents=True, exist_ok=True)
    with setup_lock(parent):
        if os.path.lexists(destination):
            verification = probe(destination, cancel_event)
            return {"status": "verified", "runtime": str(destination), "lock_sha256": digest, "verification": verification}
        cache = parent / "downloads"
        if cache.is_symlink():
            raise ValueError("TAPNext download cache cannot be a link")
        cache.mkdir(exist_ok=True)
        if progress:
            progress({"phase": "download"})
        archive = download(lock["sources"][0], cache, cancel_event)
        wheel = download(lock["packages"][0], cache, cancel_event)
        checkpoint = download(lock["models"]["tapnext"], cache, cancel_event)
        versions = parent / ".versions"
        if versions.is_symlink():
            raise ValueError("TAPNext versions directory cannot be a link")
        versions.mkdir(exist_ok=True)
        staging = versions / ("cpu-v1-" + uuid.uuid4().hex)
        staging.mkdir(mode=0o700)
        published = False
        try:
            unpack_source(staging, lock, archive, wheel)
            shutil.copy2(checkpoint, staging / lock["models"]["tapnext"]["name"])
            if progress:
                progress({"phase": "verify"})
            verification = probe(staging, cancel_event)
            if verification.get("lock_sha256") != digest:
                raise ValueError("TAPNext verification used a different lock")
            receipt = {"schema": "cinematicum-tapnext-install", "version": 1,
                       "lock_sha256": digest, "verification": verification}
            (staging / "installation.json").write_text(json.dumps(receipt, indent=2) + "\n")
            _cancelled(cancel_event)
            os.symlink(str(Path(".versions") / staging.name), destination, target_is_directory=True)
            published = True
            return {"status": "installed", "runtime": str(destination), "lock_sha256": digest, "verification": verification}
        finally:
            if not published:
                shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(check_only=args.check), sort_keys=True))

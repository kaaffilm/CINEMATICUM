#!/usr/bin/env python3
"""Independent, read-only acceptance of one CINEMATICUM installation.

This is evidence tooling, not bundled product code. Both commands require the
same explicit paths. --source is the frozen repository root; --receipt is the
installer's JSON stdout file; --evidence is a separate evidence directory.
Run snapshot-before while the old app is closed, install, then verify-after
before reopening the app. No product module is imported or invoked here.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import stat
import struct
import subprocess
import sys
import time
import zipfile


BUNDLE_ID = "com.cinematicum.studio"
VERSION = "0.13.0"
BUILD = "14"
MAX_FILES = 10_000
MAX_ENTRIES = 20_000
MAX_TREE_BYTES = 4 * 1024**3
MAX_METADATA_BYTES = 16 * 1024**2
COPY_OMISSIONS = ("__pycache__", "*.pyc", ".DS_Store")
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def absolute(value):
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError("All paths must be explicit absolute paths without '..': " + str(value))
    return Path(os.path.abspath(value))  # Deliberately do not resolve symlinks.


def open_directory(path):
    """Open each component with NOFOLLOW; retain descriptor-based ownership."""
    path = absolute(Path(path))
    descriptor = os.open("/", DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            following = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def state_tuple(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_at(parent, name, *, collect=False, limit=MAX_TREE_BYTES):
    """Hash one regular file without following a leaf or ancestor symlink."""
    if name in {"", ".", ".."} or "/" in name or "\x00" in name:
        raise ValueError("Invalid file component")
    descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("File is not regular or exceeds its size limit: " + name)
        digest, content, size = hashlib.sha256(), bytearray() if collect else None, 0
        while True:
            block = os.read(descriptor, min(1024 * 1024, limit - size + 1))
            if not block:
                break
            size += len(block)
            if size > limit:
                raise ValueError("File grew beyond its size limit: " + name)
            digest.update(block)
            if collect:
                content.extend(block)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if state_tuple(before) != state_tuple(after) or state_tuple(after) != state_tuple(current):
            raise ValueError("File changed while inspecting it: " + name)
        if size != before.st_size:
            raise ValueError("File length changed while inspecting it: " + name)
        record = {"sha256": digest.hexdigest(), "size": size,
                  "mode": stat.S_IMODE(before.st_mode)}
        return record, bytes(content) if collect else None
    finally:
        os.close(descriptor)


def read_file(path, *, collect=False, limit=MAX_TREE_BYTES):
    path = absolute(Path(path))
    parent = open_directory(path.parent)
    try:
        return read_at(parent, path.name, collect=collect, limit=limit)
    finally:
        os.close(parent)


def tree(path, *, omit_copy_artifacts=False):
    files, count, total, visited = {}, 0, 0, 0

    def visit(descriptor, prefix="", depth=0):
        nonlocal count, total, visited
        require(depth <= 64, "Directory inventory exceeds its nesting limit")
        with os.scandir(descriptor) as entries:
            names = []
            for entry in entries:
                visited += 1
                require(visited <= MAX_ENTRIES, "Directory inventory exceeds its entry limit")
                names.append(entry.name)
        for name in sorted(names):
            relative = prefix + name
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("Symlink is outside the acceptance scope: " + relative)
            if omit_copy_artifacts and any(fnmatch.fnmatchcase(name, pattern) for pattern in COPY_OMISSIONS):
                continue
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
                try:
                    visit(child, relative + "/", depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                if name == ".env" or name.startswith(".env."):
                    raise ValueError("Credential-like environment file is not read: " + relative)
                count += 1
                if count > MAX_FILES:
                    raise ValueError("File inventory exceeds its count limit")
                record, _ = read_at(descriptor, name, limit=MAX_TREE_BYTES - total)
                total += record["size"]
                files[relative] = record
            else:
                raise ValueError("Nonregular entry is outside the acceptance scope: " + relative)

    descriptor = open_directory(path)
    try:
        visit(descriptor)
    finally:
        os.close(descriptor)
    return {"files": files, "file_count": count, "total_bytes": total,
            "inventory_sha256": identity(files)}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property: " + key)
        result[key] = value
    return result


def read_json(path):
    record, content = read_file(path, collect=True, limit=MAX_METADATA_BYTES)
    return record, json.loads(content, object_pairs_hook=unique_object)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def literal_assignment(document, name):
    assignments = [node.value for node in ast.parse(document).body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    require(len(assignments) == 1, "Expected one literal assignment for " + name)
    return ast.literal_eval(assignments[0])


def git_output(root, arguments):
    descriptor = open_directory(root)
    os.close(descriptor)
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    command = ["git", "-C", str(root), "-c", "core.fsmonitor=false",
               "-c", "core.untrackedCache=false", "-c", "status.renames=false", *arguments]
    result = subprocess.run(command, capture_output=True, check=True, timeout=20, env=environment)
    require(len(result.stdout) <= MAX_METADATA_BYTES, "Git result exceeds the metadata limit")
    return result.stdout


def source_snapshot(root):
    studio = root / "scripts" / "studio"
    installer_record, installer = read_file(studio / "install_macos.py", collect=True, limit=MAX_METADATA_BYTES)
    names = literal_assignment(installer, "RUNTIME_FILES")
    require(isinstance(names, (tuple, list)) and 0 < len(names) <= 256
            and all(isinstance(name, str) for name in names) and len(set(names)) == len(names),
            "Invalid literal installer runtime inventory")
    files = {}
    for name in names:
        require(PurePosixPath(name).name == name and name not in {".", ".."}
                and "\\" not in name and PurePosixPath(name).suffix in {".py", ".json"},
                "Unexpected runtime source path: " + name)
        files[name] = read_file(studio / name)[0]
    web = tree(studio / "web", omit_copy_artifacts=True)
    files.update({"web/" + name: record for name, record in web["files"].items()})
    native = {name: read_file(studio / "macos" / name)[0]
              for name in ("StudioApp.swift", "StudioIcon.swift")}
    _, server = read_file(studio / "server.py", collect=True, limit=MAX_METADATA_BYTES)
    require(literal_assignment(server, "VERSION") == VERSION, "Source is not the accepted 0.13.0 candidate")
    integrity, _ = read_file(studio / "source-integrity.json")
    code = {"runtime_files": files, "native_sources": native, "installer": installer_record}
    return {**code, "version": VERSION, "source_integrity": integrity,
            "code_identity_sha256": identity(code),
            "git_head": git_output(root, ["rev-parse", "--verify", "HEAD"]).decode("ascii").strip(),
            "runtime_file_count": len(files),
            "scope": "Copied runtime files, two native source files and installer; source-integrity JSON hashed separately"}


def bundle_snapshot(app):
    inventory = tree(app)
    _, data = read_file(app / "Contents" / "Info.plist", collect=True, limit=MAX_METADATA_BYTES)
    info = plistlib.loads(data)
    require(isinstance(info, dict) and info.get("CFBundleIdentifier") == BUNDLE_ID,
            "App target is not a recognized CINEMATICUM bundle")
    return {**inventory, "bundle_id": info["CFBundleIdentifier"],
            "version": info.get("CFBundleShortVersionString"), "build": info.get("CFBundleVersion")}


def owner_snapshot(root):
    makefile, _ = read_file(root / "Makefile", limit=MAX_METADATA_BYTES)
    status = git_output(root, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    return {"Makefile": makefile,
            "git_head": git_output(root, ["rev-parse", "--verify", "HEAD"]).decode("ascii").strip(),
            "git_status_sha256": hashlib.sha256(status).hexdigest(),
            "git_status_records": [entry.decode("utf-8", errors="surrogateescape")
                                   for entry in status.split(b"\0") if entry],
            "scope": "Makefile bytes/mode, HEAD and Git status; other owner-file contents and credentials are not inspected"}


def ensure_evidence_directory(path):
    parent = open_directory(path.parent)
    try:
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        descriptor = os.open(path.name, DIRECTORY_FLAGS, dir_fd=parent)
        os.close(descriptor)
    finally:
        os.close(parent)


def write_new_json(path, value):
    content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False).encode() + b"\n"
    parent = open_directory(path.parent)
    created = False
    try:
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            os.unlink(path.name, dir_fd=parent)
        raise
    finally:
        os.close(parent)
    return hashlib.sha256(content).hexdigest()


def path_exists(path):
    parent = open_directory(path.parent)
    try:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False
    finally:
        os.close(parent)


def check_paths(args):
    paths = {name: str(absolute(getattr(args, name)))
             for name in ("source", "app", "projects", "original_checkout", "receipt", "evidence")}
    for target in (Path(paths["evidence"]), Path(paths["receipt"])):
        for key in ("source", "app", "projects", "original_checkout"):
            require(not target.is_relative_to(Path(paths[key])),
                    "Evidence and receipt paths must be outside " + key)
    require(Path(paths["app"]).suffix == ".app", "App must identify an exact .app bundle")
    require(Path(paths["source"]) != Path(paths["original_checkout"]),
            "Accepted source and preserved original checkout must be distinct")
    return paths


def before(paths):
    require(not path_exists(Path(paths["receipt"])), "Installer receipt already exists; select a fresh receipt path")
    return {"schema": "cinematicum-installation-before-v1", "paths": paths,
            "created_at": datetime.now(timezone.utc).isoformat(), "created_unix_ns": time.time_ns(),
            "tool_sha256": read_file(Path(__file__).absolute())[0]["sha256"],
            "source": source_snapshot(Path(paths["source"])),
            "app": bundle_snapshot(Path(paths["app"])),
            "projects": tree(Path(paths["projects"])),
            "original_checkout": owner_snapshot(Path(paths["original_checkout"])),
            "limits": {"maximum_files_per_tree": MAX_FILES, "maximum_bytes_per_tree": MAX_TREE_BYTES},
            "external_runtimes": "Not read or modified; installation is not a self-contained runtime distribution"}


def changes(expected, observed):
    return {"missing": sorted(set(expected) - set(observed)),
            "unexpected": sorted(set(observed) - set(expected)),
            "changed": sorted(name for name in set(expected) & set(observed) if expected[name] != observed[name])}


def same_inventory(expected, observed, description):
    difference = changes(expected, observed)
    require(not any(difference.values()), description + ": " + json.dumps(difference, sort_keys=True))


def macho_arm64(path):
    record, data = read_file(path, collect=True, limit=128 * 1024**2)
    require(record["mode"] & 0o111, "Native executable has no execute permission")
    require(len(data) >= 32, "Native executable is truncated")
    endian = "<" if data[:4] == b"\xcf\xfa\xed\xfe" else ">" if data[:4] == b"\xfe\xed\xfa\xcf" else None
    require(endian is not None, "Native executable is not a thin 64-bit Mach-O")
    _, cpu, subtype, filetype, count, size, flags, _ = struct.unpack(endian + "8I", data[:32])
    require(cpu == 0x0100000c and filetype == 2, "Native Mach-O is not an arm64 executable")
    require(count <= 8192 and size <= 64 * 1024**2 and 32 + size <= len(data), "Invalid Mach-O load-command bounds")
    position, signature_command = 32, False
    for _ in range(count):
        require(position + 8 <= 32 + size, "Truncated Mach-O load command")
        command, length = struct.unpack(endian + "2I", data[position:position + 8])
        require(length >= 8 and length % 8 == 0 and position + length <= 32 + size,
                "Invalid Mach-O load-command size")
        signature_command |= command == 0x1d
        position += length
    require(position == 32 + size, "Mach-O load-command length does not match its header")
    return {**record, "architecture": "arm64", "cpu_type": cpu, "cpu_subtype": subtype,
            "file_type": "MH_EXECUTE", "code_signature_command_present": signature_command,
            "signature_note": "Presence of a signature command does not certify Developer ID signing or notarization"}


def verify_archive(archive, app_name, expected):
    archive_record, _ = read_file(archive)
    parent = open_directory(archive.parent)
    descriptor = os.open(archive.name, FILE_FLAGS, dir_fd=parent)
    os.close(parent)
    observed, metadata, total = {}, [], 0
    with os.fdopen(descriptor, "rb") as stream:
        initial = os.fstat(stream.fileno())
        require(stat.S_ISREG(initial.st_mode), "Backup is not a regular file")
        with zipfile.ZipFile(stream) as source:
            entries = source.infolist()
            require(len(entries) <= MAX_FILES * 3, "Backup ZIP has too many entries")
            seen = set()
            for entry in entries:
                name = entry.filename
                pure = PurePosixPath(name.rstrip("/"))
                require(name not in seen and "\\" not in name and "\x00" not in name
                        and not pure.is_absolute() and ".." not in pure.parts
                        and pure.as_posix() == name.rstrip("/") and pure.parts,
                        "Unsafe or duplicate backup ZIP member")
                seen.add(name)
                require(not stat.S_ISLNK(entry.external_attr >> 16), "Backup ZIP contains a symlink")
                if entry.is_dir():
                    require(stat.S_IFMT(entry.external_attr >> 16) in {0, stat.S_IFDIR},
                            "Backup ZIP directory has an unexpected member type")
                    require(pure.parts[0] in {app_name, "__MACOSX"}, "Unexpected backup ZIP directory root")
                    continue
                require(stat.S_IFMT(entry.external_attr >> 16) in {0, stat.S_IFREG},
                        "Backup ZIP contains a nonregular member")
                require(not (entry.flag_bits & 1), "Encrypted backup ZIP members are not accepted")
                total += entry.file_size
                require(entry.file_size >= 0 and total <= MAX_TREE_BYTES, "Backup ZIP exceeds decoded-byte limit")
                digest, size = hashlib.sha256(), 0
                with source.open(entry) as content:
                    while True:
                        block = content.read(min(1024 * 1024, entry.file_size - size + 1))
                        if not block:
                            break
                        size += len(block)
                        require(size <= entry.file_size, "Backup member exceeds its recorded size")
                        digest.update(block)
                require(size == entry.file_size, "Truncated backup ZIP member")
                record = {"sha256": digest.hexdigest(), "size": size,
                          "mode": stat.S_IMODE(entry.external_attr >> 16)}
                if pure.parts[0] == "__MACOSX":
                    metadata.append({"path": name, **record})
                else:
                    require(pure.parts[0] == app_name and len(pure.parts) > 1, "Unexpected backup ZIP file root")
                    observed["/".join(pure.parts[1:])] = record
        require(state_tuple(initial) == state_tuple(os.fstat(stream.fileno())), "Backup ZIP changed during verification")
    require(read_file(archive)[0] == archive_record, "Backup ZIP changed between inspection phases")
    same_inventory(expected, observed, "Prior app is not exactly recoverable from its backup")
    return {"path": str(archive), **archive_record, "verified_file_count": len(observed),
            "verified_file_inventory_sha256": identity(observed), "ditto_metadata": metadata}


def after(paths, snapshot, snapshot_record):
    require(snapshot.get("schema") == "cinematicum-installation-before-v1" and snapshot.get("paths") == paths,
            "Before snapshot belongs to different paths or an unsupported schema")
    result = {"schema": "cinematicum-installation-after-v1", "paths": paths,
              "created_at": datetime.now(timezone.utc).isoformat(), "before_sha256": snapshot_record["sha256"],
              "passed": True, "gates": [],
              "external_runtimes": "Not read or modified; Python/FFmpeg/Blender and optional runtimes remain separate prerequisites",
              "native_launch_certified": False, "developer_id_or_notarization_certified": False}

    def gate(name, function):
        try:
            result[name] = function()
            result["gates"].append({"name": name, "passed": True})
        except Exception as exc:
            result["passed"] = False
            result["gates"].append({"name": name, "passed": False, "error": str(exc)})

    def source_check():
        current = source_snapshot(Path(paths["source"]))
        require(current["code_identity_sha256"] == snapshot["source"]["code_identity_sha256"],
                "Accepted source code changed during installation")
        require(current["source_integrity"] == snapshot["source"]["source_integrity"],
                "Source-integrity manifest changed during installation")
        require(read_file(Path(__file__).absolute())[0]["sha256"] == snapshot["tool_sha256"],
                "Independent evidence helper changed between phases")
        return current

    def installed_check():
        app = Path(paths["app"])
        observed = tree(app / "Contents" / "Resources" / "studio")
        expected = snapshot["source"]
        same_inventory(expected["runtime_files"], observed["files"], "Installed runtime differs from frozen source")
        manifest_record, manifest = read_json(app / "Contents" / "Resources" / "source-manifest.json")
        expected_manifest = {"format": "cinematicum-installed-source-v1", "version": VERSION,
                             "runtime_files": {name: item["sha256"] for name, item in expected["runtime_files"].items()},
                             "native_sources": {name: item["sha256"] for name, item in expected["native_sources"].items()}}
        require(manifest == expected_manifest, "Embedded installed-source manifest differs from actual frozen source")
        bundle = bundle_snapshot(app)
        require(bundle["version"] == VERSION and bundle["build"] == BUILD,
                "Installed bundle must be version 0.13.0/build 14")
        _, plist = read_file(app / "Contents" / "Info.plist", collect=True, limit=MAX_METADATA_BYTES)
        require(plistlib.loads(plist).get("CFBundleExecutable") == "CINEMATICUMStudio", "Unexpected native executable name")
        executable = macho_arm64(app / "Contents" / "MacOS" / "CINEMATICUMStudio")
        return {"runtime": observed, "embedded_source_manifest": manifest_record,
                "bundle": bundle, "executable": executable}

    def receipt_and_backup_check():
        receipt_record, receipt = read_json(Path(paths["receipt"]))
        require(isinstance(receipt, dict) and receipt.get("app") == paths["app"]
                and receipt.get("bundle_id") == BUNDLE_ID and receipt.get("target") == "arm64-apple-macos12.0",
                "Installer receipt identifies another target")
        require(receipt.get("signing_performed") is False and receipt.get("launched") is False,
                "Installer receipt does not preserve the expected no-signing/no-launch boundary")
        require(receipt.get("runtime_files_verified") == snapshot["source"]["runtime_file_count"],
                "Installer runtime count differs from the independent expected inventory")
        actual_manifest, _ = read_file(Path(paths["app"]) / "Contents" / "Resources" / "source-manifest.json")
        require(receipt.get("source_manifest_sha256") == actual_manifest["sha256"], "Installer manifest hash does not match installed bytes")
        require(isinstance(receipt.get("backup"), str), "Replacement installation did not retain a prior-bundle backup")
        backup = absolute(Path(receipt["backup"]))
        require(backup.parent == Path(paths["app"]).parent / ".CINEMATICUM-Backups.noindex"
                and backup.suffix == ".zip", "Backup is outside the expected sibling archive directory")
        backup_receipt_record, backup_receipt = read_json(backup.with_suffix(".json"))
        require(backup_receipt == {"original_path": paths["app"], "bundle_id": BUNDLE_ID,
                                  "archive": backup.name, "files": snapshot["app"]["files"]},
                "Backup receipt disagrees with the independently captured original bundle")
        verified = verify_archive(backup, Path(paths["app"]).name, snapshot["app"]["files"])
        return {"installer_receipt": receipt_record, "installer_values": receipt,
                "backup_receipt": backup_receipt_record, "backup": verified,
                "signing_performed": False, "signing_claim_source": "Installer receipt; no distribution-signature certification"}

    def project_check():
        current = tree(Path(paths["projects"]))
        same_inventory(snapshot["projects"]["files"], current["files"], "Project file identities changed during installation")
        return current

    def owner_check():
        current = owner_snapshot(Path(paths["original_checkout"]))
        require(current == snapshot["original_checkout"], "Original checkout Makefile, HEAD or Git status changed")
        return current

    gate("source", source_check)
    gate("installed", installed_check)
    gate("receipt_and_backup", receipt_and_backup_check)
    gate("projects", project_check)
    gate("original_checkout", owner_check)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("snapshot-before", "verify-after"))
    for name in ("source", "app", "projects", "original-checkout", "receipt", "evidence"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        paths = check_paths(args)
        evidence = Path(paths["evidence"])
        ensure_evidence_directory(evidence)
        if args.phase == "snapshot-before":
            result = before(paths)
            destination = evidence / "installation-before.json"
        else:
            record, snapshot = read_json(evidence / "installation-before.json")
            result = after(paths, snapshot, record)
            destination = evidence / "installation-after.json"
        digest = write_new_json(destination, result)
        summary = {"phase": args.phase, "passed": result.get("passed", True),
                   "evidence": str(destination), "evidence_sha256": digest,
                   "source_code_identity_sha256": result.get("source", {}).get("code_identity_sha256"),
                   "source_integrity_sha256": result.get("source", {}).get("source_integrity", {}).get("sha256")}
        if args.phase == "snapshot-before":
            summary.update(prior_app_files=result["app"]["file_count"],
                           project_files=result["projects"]["file_count"], project_bytes=result["projects"]["total_bytes"],
                           expected_runtime_files=result["source"]["runtime_file_count"])
        else:
            summary["gates"] = result["gates"]
        print(json.dumps(summary, indent=2))
        return 0 if summary["passed"] else 1
    except Exception as exc:
        print(json.dumps({"phase": args.phase, "passed": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Reproduce or verify the tracked Studio source manifest without importing it.

Run from any directory in an intact Git checkout:
    python3 scripts/studio/source_integrity.py --check
    python3 scripts/studio/source_integrity.py --write

Stage intended new source files before --write. Untracked source is reported,
never adopted into a release manifest. Temporary media is outside this scope.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile

MANIFEST = "scripts/studio/source-integrity.json"
STUDIO = "scripts/studio"
SCOPE = {
    "root_files": [".github/workflows/studio-verification.yml", "README.md"],
    "studio_tree": STUDIO,
    "source_suffixes": [".css", ".entitlements", ".html", ".js", ".json", ".jsx", ".md",
                        ".mjs", ".plist", ".py", ".sh", ".svg", ".swift", ".ts", ".tsx",
                        ".txt", ".yaml", ".yml"],
    "excluded_directories": [".venv", "__pycache__", "build", "dist", "evidence", "fixtures",
                             "media", "output", "outputs", "venv", "verification"],
    "excluded_generated_directory_prefixes": ["ENGINE_TEST", "cinematicum-"],
    "excluded_generated_file_prefixes": ["ENGINE_TEST"],
    "excluded_files": [MANIFEST],
    "inventory": "Git tracked files; any untracked source in scope fails verification",
}


def in_scope(name):
    if not isinstance(name, str) or "\\" in name or any(ord(c) < 32 for c in name):
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        return False
    if name in SCOPE["excluded_files"]:
        return False
    if name in SCOPE["root_files"]:
        return True
    if not name.startswith(STUDIO + "/") or path.suffix not in SCOPE["source_suffixes"]:
        return False
    relative = path.parts[2:]
    if any(part in SCOPE["excluded_directories"] for part in relative[:-1]):
        return False
    if any(part.startswith(tuple(SCOPE["excluded_generated_directory_prefixes"])) for part in relative[:-1]):
        return False
    return not relative[-1].startswith(tuple(SCOPE["excluded_generated_file_prefixes"]))


def git_inventory(root):
    root = Path(root).resolve()
    command = ["git", "-C", str(root)]
    top = subprocess.run(command + ["rev-parse", "--show-toplevel"], capture_output=True,
                         text=True, check=True, timeout=10).stdout.strip()
    if Path(top).resolve() != root:
        raise ValueError("Choose the root of the Git checkout, not a source subdirectory")

    def paths(option):
        output = subprocess.run(command + ["ls-files", option, "-z", "--", STUDIO,
                                           *SCOPE["root_files"]], capture_output=True,
                                check=True, timeout=10).stdout.decode("utf-8")
        return {name for name in output.split("\0") if name and in_scope(name)}

    # Do not use --exclude-standard: an ignored .py/.js source in scope must
    # not silently affect a local run while escaping the integrity check.
    return paths("--cached"), paths("--others")


def file_record(root, name):
    root = Path(root)
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Source paths must not contain symbolic links: " + name)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Source must be a regular file: " + name)
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(source.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("Source changed while hashing: " + name)
    return {"path": name, "size": before.st_size, "sha256": digest.hexdigest()}


def source_version(root):
    source = Path(root) / STUDIO / "server.py"
    for statement in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION"
                                                    for t in statement.targets):
            value = ast.literal_eval(statement.value)
            if isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", value):
                return value
    raise ValueError("The Studio server must declare a literal release VERSION")


def build_manifest(root):
    tracked, untracked = git_inventory(root)
    if untracked:
        raise ValueError("Stage intended new source files before generating; untracked source: " + ", ".join(sorted(untracked)))
    if not set(SCOPE["root_files"]).issubset(tracked) or STUDIO + "/server.py" not in tracked:
        raise ValueError("Required README, Studio workflow or server source is absent from the Git index")
    records = [file_record(root, name) for name in sorted(tracked)]
    return {"format": 2, "schema": "cinematicum-source-integrity", "version": source_version(root),
            "scope": SCOPE, "files": records}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate integrity manifest property: " + key)
        result[key] = value
    return result


def read_manifest(root):
    path = Path(root) / MANIFEST
    file_record(root, MANIFEST)  # Refuse symlinks and nonregular manifest files.
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Integrity manifest exceeds its size limit")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if (not isinstance(value, dict) or set(value) != {"format", "schema", "version", "scope", "files"}
            or value["format"] != 2 or value["schema"] != "cinematicum-source-integrity"
            or value["scope"] != SCOPE or not isinstance(value["files"], list)):
        raise ValueError("Unsupported integrity manifest or changed source scope; regenerate it explicitly")
    names = []
    for record in value["files"]:
        if (not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}
                or not in_scope(record["path"]) or type(record["size"]) is not int or record["size"] < 0
                or not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise ValueError("Invalid source identity in the integrity manifest")
        names.append(record["path"])
    if names != sorted(set(names)):
        raise ValueError("Integrity source paths must be unique and sorted")
    return value


def verify_manifest(root):
    manifest = read_manifest(root)
    tracked, untracked = git_inventory(root)
    expected = {entry["path"]: entry for entry in manifest["files"]}
    missing, changed, invalid = set(expected) - tracked, [], []
    for name in sorted(tracked & expected.keys()):
        try:
            actual = file_record(root, name)
        except FileNotFoundError:
            missing.add(name)
        except (OSError, ValueError) as exc:
            invalid.append({"path": name, "reason": str(exc)})
        else:
            if actual != expected[name]:
                changed.append(name)
    unexpected = sorted((tracked - expected.keys()) | untracked)
    version_matches = not invalid and not missing and manifest["version"] == source_version(root)
    return {"passed": not (missing or changed or invalid or unexpected) and version_matches,
            "version": manifest["version"], "version_matches": version_matches,
            "checked_files": len(tracked & expected.keys()), "changed": changed,
            "missing": sorted(missing), "unexpected": unexpected, "untracked": sorted(untracked), "invalid": invalid}


def write_manifest(root):
    manifest = build_manifest(root)
    target = Path(root) / MANIFEST
    if target.is_symlink():
        raise ValueError("The integrity manifest must not be a symbolic link")
    data = json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".source-integrity-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Regenerate after staging intended source additions")
    mode.add_argument("--check", action="store_true", help="Verify tracked source and detect unexpected source (default)")
    args = parser.parse_args(argv)
    try:
        if args.write:
            manifest = write_manifest(args.root.resolve())
            print(json.dumps({"written": MANIFEST, "version": manifest["version"], "files": len(manifest["files"])}))
            return 0
        result = verify_manifest(args.root.resolve())
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as exc:
        print("Source integrity failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

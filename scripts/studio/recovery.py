"""Durable, revision-bound edit checkpoints. Never commits a recovered edit.

The Store serializes calls under its project lock. Checkpoints are separate from
the saved project and belong to an editor, so a late request from one window
cannot erase a newer draft or acknowledge another window's work.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import time

EDITOR = re.compile(r"^[a-f0-9]{32}$")
MAX_DRAFTS = 32
MAX_VERSIONS = 20


def identity(value):
    if not isinstance(value, str) or not EDITOR.fullmatch(value):
        raise ValueError("Invalid recovery editor identity.")
    return value


def sequence(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2**53 - 1:
        raise ValueError("Recovery sequence must be a positive integer.")
    return value


def digest(project):
    return hashlib.sha256(json.dumps(project, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def folder(directory, name):
    root = Path(directory) / name
    if root.is_symlink():
        raise ValueError("Recovery storage must be an owned directory.")
    root.mkdir(exist_ok=True)
    return root


def load(path):
    if path.is_symlink():
        raise ValueError("Recovery entries cannot be symlinks.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("project"), dict):
        raise ValueError("Unsupported recovery record.")
    if digest(value["project"]) != value.get("sha256"):
        raise ValueError("Recovery checksum does not match; the saved project was preserved.")
    return value


def put(directory, editor_id, serial, project, atomic_json):
    editor_id, serial = identity(editor_id), sequence(serial)
    root = folder(directory, "recovery")
    path = root / (editor_id + ".json")
    if path.exists() or path.is_symlink():
        previous = load(path)
        if previous["sequence"] >= serial:
            if previous["sequence"] == serial and previous["sha256"] != digest(project):
                raise ValueError("A recovery sequence cannot identify different edits.")
            return {"checkpointed": False, "sequence": previous["sequence"], "reason": "newer_checkpoint_exists"}
    elif len(list(root.glob("*.json"))) >= MAX_DRAFTS:
        raise ValueError("Recovery storage has 32 editor drafts. Review and discard an old draft before continuing checkpoints.")
    record = {"version": 1, "editor_id": editor_id, "sequence": serial,
              "base_revision": project["revision"], "written_at": time.time(),
              "sha256": digest(project), "project": project}
    atomic_json(path, record)
    return {"checkpointed": True, "sequence": serial, "written_at": record["written_at"]}


def acknowledge(directory, receipt, base_revision):
    if receipt is None:
        return
    editor_id, serial = identity(receipt.get("editor_id")), sequence(receipt.get("sequence"))
    path = folder(directory, "recovery") / (editor_id + ".json")
    if path.exists():
        record = load(path)
        if record["base_revision"] == base_revision and record["sequence"] <= serial:
            path.unlink()


def preserve_saved(directory, project, atomic_json):
    if not project:
        return
    root = folder(directory, "versions")
    revision = project.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Invalid saved revision.")
    path = root / (str(revision).zfill(12) + ".json")
    record = {"version": 1, "base_revision": revision, "written_at": time.time(),
              "sha256": digest(project), "project": project}
    if path.is_symlink():
        raise ValueError("Saved versions cannot be symlinks.")
    if path.exists():
        previous = load(path)
        # Admission extends immutable media inventory without changing the
        # timeline revision. An interrupted save may already have archived
        # that revision before the admission. Its editorial identity is still
        # the same; keep the first archive and reattach current assets on read.
        old_edit = {key: value for key, value in previous["project"].items() if key != "assets"}
        new_edit = {key: value for key, value in project.items() if key != "assets"}
        if digest(old_edit) != digest(new_edit):
            raise ValueError("Saved-version identity changed; refusing to overwrite its recovery copy.")
        return
    atomic_json(path, record)
    for old in sorted(root.glob("[0-9]*.json"))[:-MAX_VERSIONS]:
        if re.fullmatch(r"[0-9]{12}\.json", old.name) and not old.is_symlink():
            old.unlink()


def listing(directory, current):
    result = {"drafts": [], "versions": [], "unreadable": 0}
    for name, target in (("recovery", "drafts"), ("versions", "versions")):
        for path in folder(directory, name).glob("*.json"):
            try:
                record = load(path)
                p = record["project"]
                if p.get("id") != current["id"]:
                    raise ValueError("Recovery project identity does not match.")
                result[target].append({"key": path.stem, "sequence": record.get("sequence"),
                    "base_revision": record["base_revision"], "written_at": record["written_at"],
                    "stale": record["base_revision"] != current["revision"], "name": p.get("name"),
                    "clips": len(p.get("clips", [])), "titles": len(p.get("titles", []))})
            except (OSError, ValueError, KeyError, TypeError):
                result["unreadable"] += 1
        result[target].sort(key=lambda r: r["written_at"], reverse=True)
    return result


def candidate(directory, current, kind, key, expected_sequence=None):
    if kind == "draft":
        path = folder(directory, "recovery") / (identity(key) + ".json")
    elif kind == "version" and isinstance(key, str) and re.fullmatch(r"[0-9]{12}", key):
        path = folder(directory, "versions") / (key + ".json")
    else:
        raise ValueError("Invalid recovery selection.")
    record = load(path)
    if kind == "draft" and record.get("sequence") != sequence(expected_sequence):
        raise ValueError("This draft changed. Refresh recovery before selecting it.")
    p = copy.deepcopy(record["project"])
    if p.get("id") != current["id"]:
        raise ValueError("Recovery project identity does not match.")
    # Explicit recovery is an unsaved candidate against the CURRENT revision,
    # never a blind old-revision write. Store validation checks all media again.
    p["revision"] = current["revision"]
    p["assets"] = copy.deepcopy(current["assets"])
    return p, record


def discard(directory, editor_id, expected_sequence):
    path = folder(directory, "recovery") / (identity(editor_id) + ".json")
    record = load(path)
    if record["sequence"] != sequence(expected_sequence):
        raise ValueError("This draft changed. Refresh recovery before discarding it.")
    path.unlink()

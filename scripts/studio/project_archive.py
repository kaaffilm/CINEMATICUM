"""Portable CINEMATICUM authoring packages, with streamed identity verification.

This is a data format, not an installer. Restoring never executes a workflow,
loads Blender, fetches a URL, or replaces an existing project. Version 1 uses
uncompressed ZIP64: source media are normally compressed already, and refusing
compressed members makes the declared 64-GiB extraction bound enforceable
without a compression-ratio guessing rule.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import tempfile
import time
import unicodedata
import uuid
import zipfile

from adapters import validate_workflow
from color_pipeline import list_luts
from engine import MEDIA_EXTENSIONS, validate_project
from imaging import validate_imaging_recipe
from scene import validate_scene


FORMAT = "CINEMATICUM_PROJECT_ARCHIVE"
VERSION = 1
MANIFEST = "CINEMATICUM_ARCHIVE.json"
MAX_BYTES = 64 * 1024 ** 3
MAX_FILES = 10000
MAX_JSON = 8 * 1024 ** 2
MAX_DIRECTORY = 16 * 1024 ** 2
CHUNK = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_PATH_KEYS = {"path", "file", "filename", "url", "uri", "directory", "folder", "image", "video", "audio", "mask"}


class ArchiveCancelled(RuntimeError):
    pass


def _cancel(event):
    if event is not None and event.is_set():
        raise ArchiveCancelled("Project archive operation cancelled.")


def _progress(callback, value):
    if callback:
        callback(value)


def _json_bytes(value):
    try:
        result = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Archive metadata must contain finite JSON data.") from exc
    if len(result) > MAX_JSON:
        raise ValueError("An archive metadata document exceeds 8 MiB.")
    return result


def _json_load(payload):
    if len(payload) > MAX_JSON:
        raise ValueError("An archive metadata document exceeds 8 MiB.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Archive JSON contains duplicate keys.")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Archive JSON contains nonfinite numbers.")
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Archive metadata is not bounded UTF-8 JSON.") from exc


def _relative(value):
    if (not isinstance(value, str) or len(value) > 512 or "\\" in value or "\x00" in value
            or value.startswith("/") or not value or any(not _PART.fullmatch(p) or p.endswith(".")
                or p.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *{"COM%d" % n for n in range(1, 10)},
                                                 *{"LPT%d" % n for n in range(1, 10)}}
                for p in value.split("/"))):
        raise ValueError("Unsafe or nonportable archive path.")
    parts = PurePosixPath(value).parts
    if len(parts) > 5 or "/".join(parts) != value:
        raise ValueError("Unsafe or noncanonical archive path.")
    return value


def _allowed(value):
    _relative(value)
    parts = value.split("/")
    if value in {"project.json", "assets.json", "workflow.json"}:
        return True
    if len(parts) == 2 and parts[0] == "media":
        return Path(parts[1]).suffix.lower() in MEDIA_EXTENSIONS | {".blend"}
    if len(parts) == 3 and parts[:2] == ["color", "luts"]:
        return parts[2].endswith(".cube") and bool(_SHA.fullmatch(parts[2][:-5]))
    if len(parts) == 3 and parts[:2] == ["imaging", "sources"]:
        name = Path(parts[2])
        return name.suffix in {".raw", ".json"} and bool(_SHA.fullmatch(name.stem))
    if len(parts) == 4 and parts[:2] == ["imaging", "outputs"]:
        return bool(_ID.fullmatch(parts[2])) and parts[3] in {"display.png", "linear.exr", "receipt.json", "motion.png"}
    if len(parts) == 4 and parts[:2] == ["model-inference", "outputs"]:
        from model_inference import ARTIFACT_NAMES
        return bool(_ID.fullmatch(parts[2])) and parts[3] in ARTIFACT_NAMES
    if len(parts) == 4 and parts[:2] == ["lens-calibration", "outputs"]:
        from lens_calibration import ARTIFACT_NAMES
        return bool(re.fullmatch(r"[a-f0-9]{32}", parts[2])) and parts[3] in ARTIFACT_NAMES
    if len(parts) == 4 and parts[:2] == ["multicam-sync", "outputs"]:
        from multicam_sync import ARTIFACT_NAMES
        return bool(_ID.fullmatch(parts[2])) and parts[3] in ARTIFACT_NAMES
    if len(parts) == 3 and parts[:2] == ["deep", "sources"]:
        name = Path(parts[2])
        return name.suffix in {".exr", ".json"} and bool(_SHA.fullmatch(name.stem))
    if len(parts) == 4 and parts[1] == "outputs" and parts[0] in {"deep", "optics", "physical", "learned", "scene-processing", "reconstruction"}:
        from studio_tools import TOOLS, implementation
        tool = next(key for key, spec in TOOLS.items() if spec["directory"] == parts[0])
        _, module = implementation(tool)
        return bool(re.fullmatch(r"[a-f0-9]{32}", parts[2])) and parts[3] in module.ARTIFACT_NAMES
    if len(parts) == 2 and parts[0] == "exports":
        return bool(_ID.fullmatch(Path(parts[1]).stem)) and Path(parts[1]).suffix in {".blend", ".json", ".zip"}
    return False


def _root(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Archive operations require an existing, real directory.")
    return path.resolve()


@contextmanager
def _open_owned(root, relative):
    """Open through directory descriptors, refusing a symlink at every step."""
    _relative(relative)
    descriptor = os.open(str(root), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    source = None
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            next_descriptor = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=descriptor)
        source = os.fdopen(fd, "rb")
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError("Archive dependencies must be nonempty regular files within 64 GiB.")
        yield source
    except OSError as exc:
        raise ValueError("A project dependency is missing or contains a symbolic link: " + relative) from exc
    finally:
        if source:
            source.close()
        os.close(descriptor)


def _read_owned(root, relative):
    with _open_owned(root, relative) as source:
        payload = source.read(MAX_JSON + 1)
    return _json_load(payload), payload


def _portable_json(value, workflow=False, scene_graph=None):
    """Reject explicit machine/file/network references in managed path fields.

    Creative text is left intact. Model names and relative engine inputs are
    disclosed as external engine prerequisites, never fetched by this module.
    """
    pending, inspected = [(value, "", ())], 0
    while pending:
        item, key, location = pending.pop()
        inspected += 1
        if inspected > 500000:
            raise ValueError("Project metadata exceeds the portable inspection bound.")
        if isinstance(item, dict):
            for child_key, child in item.items():
                if not location and child_key == "scene_processing" and child is not None:
                    # A validated graph is data-only. Its absolute hierarchy
                    # identities and context strings are not filesystem paths.
                    from scene_processing import validate_scene_graph
                    validate_scene_graph(child)
                    continue
                if scene_graph is not None and not location and child_key == "context":
                    from scene_processing import validate_context
                    if not isinstance(child, dict):
                        raise ValueError("A scene receipt requires its typed evaluation context.")
                    normalized = validate_context({k: v for k, v in child.items() if k != "time"}, scene_graph["context"])
                    if normalized != child:
                        raise ValueError("A scene receipt context differs from its typed graph schema.")
                    continue
                pending.append((child, str(child_key), location + (child_key,)))
        elif isinstance(item, list):
            pending.extend((v, key, location + (index,)) for index, v in enumerate(item))
        elif isinstance(item, str):
            if (scene_graph is not None and len(location) == 3 and location[0] == "baked_transforms"
                    and type(location[1]) is int and location[2] == "path"):
                from scene_processing import validate_path
                validate_path(item)
                continue
            path_field = key.lower() in _PATH_KEYS or key.lower().endswith(("_path", "_file", "_filename", "_directory", "_url"))
            if workflow:
                path_field = path_field or key.lower().endswith("_name")
            if path_field and (item.startswith(("/", "~", "file:", "http:", "https:", "\\"))
                               or re.match(r"^[A-Za-z]:[\\/]", item) or ".." in item.replace("\\", "/").split("/")):
                raise ValueError("A managed %s field contains an external path or URL; import that dependency into the project before archiving." % key)


def _scan(root, relative, suffix):
    """Inspect a single managed namespace; never recursively collect a folder."""
    directory = root
    for part in relative.split("/"):
        directory = directory / part
        if directory.is_symlink():
            raise ValueError("A managed project directory is a symbolic link.")
        if not directory.exists():
            return []
        if not directory.is_dir():
            raise ValueError("A managed project directory is not a directory.")
    result = []
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_FILES:
                raise ValueError("A managed project directory exceeds 10,000 entries.")
            if entry.name.endswith(suffix):
                result.append(relative + "/" + entry.name)
    return sorted(result)


def _collect_authoring(root, project, add):
    """Retain EXR source identities and each atomically published tool result."""
    sources = set()
    for relative in _scan(root, "deep/sources", ".json"):
        descriptor, payload = _read_owned(root, relative)
        digest = Path(relative).stem
        if (not _SHA.fullmatch(digest) or not isinstance(descriptor, dict)
                or descriptor.get("version") != 1 or descriptor.get("id") != digest
                or descriptor.get("sha256") != digest or descriptor.get("path") != "deep/sources/" + digest + ".exr"):
            raise ValueError("A deep EXR source descriptor is inconsistent.")
        _portable_json(descriptor)
        add(relative, "deep-source-descriptor", data=payload)
        add(descriptor["path"], "deep-exr-source", digest, descriptor.get("size"))
        sources.add(digest)
    for node in (project.get("deep_compositing") or {}).get("nodes", []):
        if node.get("op") == "source" and node["source_id"] not in sources:
            raise ValueError("An authored deep graph references an absent EXR original.")

    from studio_tools import TOOLS, implementation
    for tool, spec in TOOLS.items():
        for relative in _scan(root, spec["directory"] + "/outputs", ""):
            if not re.fullmatch(r"[a-f0-9]{32}", Path(relative).name):
                continue
            _, module = implementation(tool)
            receipt_name = spec.get("receipt", "receipt.json")
            receipt, payload = _read_owned(root, relative + "/" + receipt_name)
            if not isinstance(receipt, dict):
                raise ValueError("An authoring output receipt must be an object.")
            scene_graph = None
            if tool == "scene-processing":
                from scene_processing import digest, validate_scene_graph
                document, _ = _read_owned(root, relative + "/graph.json")
                scene_graph = validate_scene_graph(document)
                if (receipt.get("format") != "CINEMATICUM_SCENE_PROCESSING" or receipt.get("version") != 1
                        or receipt.get("graph_sha256") != digest(scene_graph)):
                    raise ValueError("A scene-processing receipt differs from its validated graph identity.")
            _portable_json(receipt, scene_graph=scene_graph)
            add(relative + "/" + receipt_name, tool + "-receipt", data=payload)
            entries = receipt.get("artifacts")
            if isinstance(entries, dict):
                entries = [dict(value, filename=value.get("filename", key))
                           for key, value in entries.items() if isinstance(value, dict)]
            if not isinstance(entries, list) or not entries:
                raise ValueError("An authoring output lacks its artifact identities.")
            found = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("Invalid authoring artifact identity.")
                name = entry.get("filename")
                if name not in module.ARTIFACT_NAMES or name == receipt_name or name in found:
                    raise ValueError("An authoring receipt declares duplicate or unowned artifacts.")
                found.add(name)
                add(relative + "/" + name, tool + "-artifact", entry.get("sha256"), entry.get("size", entry.get("bytes")))
            actual = {Path(path).name for path in _scan(root, relative, "")}
            if actual != found | {receipt_name}:
                raise ValueError("An authoring output inventory no longer matches its receipt.")

    # Audio alignment is authored evidence, including its actual decoded mono
    # windows. Keep complete receipts across restore and shared-project transfer.
    from multicam_sync import ALGORITHM, RATE, artifact_names
    measured_bindings = {}
    for group in project.get("multicam_groups", []):
        binding = group.get("synchronization")
        if binding is not None:
            ident, digest = binding["output_id"], binding["receipt_sha256"]
            if ident in measured_bindings and measured_bindings[ident] != digest:
                raise ValueError("Measured camera groups disagree about their source receipt.")
            measured_bindings[ident] = digest
    found_measurements = set()
    for relative in _scan(root, "multicam-sync/outputs", ""):
        ident = Path(relative).name
        if not _ID.fullmatch(ident):
            continue
        receipt, payload = _read_owned(root, relative + "/receipt.json")
        if (not isinstance(receipt, dict) or receipt.get("format") != "cinematicum-multicam-sync"
                or receipt.get("version") != 1 or receipt.get("algorithm") != ALGORITHM or receipt.get("rate") != RATE
                or receipt.get("output_id") != ident or not isinstance(receipt.get("sources"), list)
                or not isinstance(receipt.get("artifacts"), dict)):
            raise ValueError("An owned camera synchronization receipt is invalid.")
        _portable_json(receipt)
        names = artifact_names(len(receipt["sources"]))
        if (set(receipt["artifacts"]) != names - {"receipt.json"}
                or {Path(path).name for path in _scan(root, relative, "")} != names):
            raise ValueError("A camera synchronization output inventory differs from its receipt.")
        digest = hashlib.sha256(payload).hexdigest()
        if ident in measured_bindings and measured_bindings[ident] != digest:
            raise ValueError("The measured camera synchronization receipt changed after applying its edit.")
        add(relative + "/receipt.json", "multicam-sync-receipt", digest, data=payload)
        for name, entry in receipt["artifacts"].items():
            if not isinstance(entry, dict) or set(entry) != {"sha256", "size"}:
                raise ValueError("A camera synchronization artifact has no exact content identity.")
            add(relative + "/" + name, "multicam-sync-artifact", entry["sha256"], entry["size"])
        found_measurements.add(ident)
    if set(measured_bindings) - found_measurements:
        raise ValueError("A measured camera group is missing its retained sample evidence.")


def _collect(project, project_dir, cancel_event=None):
    """Build the exact dependency closure of the current managed project state."""
    root = _root(project_dir)
    p = copy.deepcopy(project)
    if not isinstance(p, dict) or not isinstance(p.get("assets"), list):
        raise ValueError("Archive a saved CINEMATICUM project with its admitted media inventory.")
    p.pop("_recovery", None)
    p.pop("archive_restore", None)
    _portable_json(p)
    files, folded, warnings = {}, set(), []

    def add(relative, role, expected=None, size=None, data=None):
        _cancel(cancel_event)
        if not _allowed(relative):
            raise ValueError("A dependency is outside the portable project format: " + relative)
        if data is None and expected is None:
            raise ValueError("A source dependency is missing its SHA-256 identity: " + relative)
        if expected is not None and (not isinstance(expected, str) or not _SHA.fullmatch(expected)):
            raise ValueError("A project dependency has no valid SHA-256 identity: " + relative)
        if data is not None:
            entry = {"data": data, "size": len(data), "expected": expected, "role": role}
        else:
            with _open_owned(root, relative) as source:
                actual_size = os.fstat(source.fileno()).st_size
            if size is not None and (type(size) is not int or size != actual_size):
                raise ValueError("A dependency no longer matches its recorded size: " + relative)
            entry = {"size": actual_size, "expected": expected, "role": role}
        if relative in files:
            if files[relative].get("expected") != expected or files[relative].get("data") != data:
                raise ValueError("A dependency has conflicting identities: " + relative)
            return
        key = relative.casefold()
        if key in folded:
            raise ValueError("Project dependencies collide on case-insensitive filesystems.")
        folded.add(key)
        files[relative] = entry
        if len(files) > MAX_FILES or sum(x["size"] for x in files.values()) > MAX_BYTES:
            raise ValueError("The project archive exceeds 10,000 files or 64 GiB.")

    assets = {}
    for asset in p["assets"]:
        if not isinstance(asset, dict) or not isinstance(asset.get("id"), str) or asset["id"] in assets:
            raise ValueError("The archive media inventory contains an invalid or duplicate identity.")
        relative = asset.get("path")
        if not isinstance(relative, str) or not relative.startswith("media/"):
            raise ValueError("An admitted asset is outside the owned media directory.")
        if not isinstance(asset.get("sha256"), str) or not _SHA.fullmatch(asset["sha256"]):
            raise ValueError("Every archived asset needs its admitted SHA-256 identity.")
        add(relative, "admitted-media", asset["sha256"], asset.get("size"))
        assets[asset["id"]] = asset
        if Path(relative).suffix.lower() == ".blend":
            warnings.append("Imported Blender sources are retained as inert bytes. Their external datablocks are not inspected or bundled.")
    p = validate_project(p, root)
    settings = p.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("Project settings must be an object.")
    if settings.get("scene") is not None:
        settings["scene"] = validate_scene(settings["scene"], width=p["width"], height=p["height"])

    # Float movie exports retain their immutable snapshot, OCIO configuration,
    # all EXR frames and sample-exact mix. Bind the preserved ZIP and sources;
    # restore never extracts or executes its nested OCIO package.
    from float_movie import verify_master_package
    for relative in _scan(root, "exports", ".json"):
        document, _ = _read_owned(root, relative)
        result = document.get("result", {}) if isinstance(document, dict) else {}
        if not isinstance(result, dict) or result.get("profile") != "master32":
            continue
        name = result.get("filename")
        if not isinstance(name, str) or name != Path(relative).stem + ".zip" or not _ID.fullmatch(Path(name).stem):
            raise ValueError("A float movie master has an invalid owned filename.")
        snapshot = document.get("snapshot")
        _portable_json(snapshot)
        with _open_owned(root, "exports/" + name) as package:
            master = verify_master_package(package, snapshot, cancel_event)
        if result.get("project_sha256") != master["project_sha256"] or result.get("sources") != master["sources"]:
            raise ValueError("A float movie export receipt differs from its verified master.")
        for source in master["sources"]:
            add(source["path"], "admitted-media", source["sha256"], source["size"])
        portable = {"result": {key: result[key] for key in ("profile", "filename", "sha256", "size", "project_sha256", "sources", "image_precision", "processing_bits") if key in result},
                    "snapshot": snapshot, "issuance_effect": "NONE"}
        _portable_json(portable)
        add("exports/" + name, "float-movie-master", result.get("sha256"), result.get("size"))
        add(relative, "float-movie-receipt", data=_json_bytes(portable))

    # The owned LUT palette and RAW-source browser are project state even when
    # no current clip/recipe uses one of their entries.
    for lut in list_luts(root):
        add("color/luts/" + lut["sha256"] + ".cube", "color-lut", lut["sha256"])
    raw_sources = {}
    for relative in _scan(root, "imaging/sources", ".json"):
        descriptor, payload = _read_owned(root, relative)
        digest = Path(relative).stem
        if (not _SHA.fullmatch(digest) or not isinstance(descriptor, dict) or descriptor.get("id") != digest
                or descriptor.get("sha256") != digest or descriptor.get("path") != "imaging/sources/" + digest + ".raw"):
            raise ValueError("A RAW source descriptor is inconsistent.")
        _portable_json(descriptor)
        add(relative, "raw-descriptor", data=payload)
        add(descriptor["path"], "camera-raw-source", digest, descriptor.get("size"))
        raw_sources[digest] = descriptor

    _collect_authoring(root, p, add)
    from model_inference import archive_dependencies
    for entry in archive_dependencies(p, root, cancel_event):
        add(entry["path"], entry["role"], entry["sha256"], entry["bytes"])

    for asset in p["assets"]:
        provenance = asset.get("provenance", {})
        if not isinstance(provenance, dict):
            raise ValueError("Asset provenance must be data, not an external reference.")
        if provenance.get("type") != "cinematicum-imaging":
            continue
        ident = provenance.get("output_id")
        if provenance.get("version") != 1 or not isinstance(ident, str) or not _ID.fullmatch(ident):
            raise ValueError("An imaging output has invalid provenance.")
        prefix = "imaging/outputs/" + ident + "/"
        receipt, payload = _read_owned(root, prefix + "receipt.json")
        _portable_json(receipt)
        if not isinstance(receipt, dict):
            raise ValueError("An imaging receipt is invalid.")
        recipe = validate_imaging_recipe(receipt.get("recipe"))
        if recipe != validate_imaging_recipe(provenance.get("recipe")) or receipt.get("operation") != provenance.get("operation"):
            raise ValueError("The imaging receipt no longer matches its authored recipe.")
        if not isinstance(provenance.get("receipt_sha256"), str) or not _SHA.fullmatch(provenance["receipt_sha256"]):
            raise ValueError("An imaging receipt is missing its source SHA-256 identity.")
        add(prefix + "receipt.json", "imaging-receipt", provenance.get("receipt_sha256"), data=payload)
        artifacts = receipt.get("artifacts", {})
        expected_artifacts = {"linear", "display"} | ({"motion"} if recipe["operation"] == "hdr_merge" and recipe.get("deghost") == "reference" else set())
        if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
            raise ValueError("An imaging receipt has an unexpected artifact set.")
        for key, name in (("display", "display.png"), ("linear", "linear.exr")):
            descriptor = artifacts.get(key, {}) if isinstance(artifacts, dict) else {}
            if not isinstance(descriptor, dict) or descriptor.get("filename") != name:
                raise ValueError("An imaging artifact is missing its receipt identity.")
            expected = asset["sha256"] if key == "display" else provenance.get("linear_sha256")
            if descriptor.get("sha256") != expected:
                raise ValueError("An imaging master or display does not match asset provenance.")
            add(prefix + name, "imaging-" + key, expected, descriptor.get("size"))
        if "motion" in expected_artifacts:
            mask = artifacts["motion"]
            if not isinstance(mask, dict) or mask.get("filename") != "motion.png":
                raise ValueError("An HDR motion mask has no immutable receipt identity.")
            add(prefix + "motion.png", "imaging-motion", mask.get("sha256"), mask.get("size"))
        inputs = receipt.get("inputs")
        expected_ids = ([recipe["source_id"]] if recipe["operation"] == "raw" else [recipe["asset_id"]]
                        if recipe["operation"] == "ocio" else recipe["images"] if recipe["operation"] == "panorama"
                        else [b["asset_id"] for b in recipe["brackets"]])
        if not isinstance(inputs, list) or len(inputs) != len(expected_ids):
            raise ValueError("An imaging receipt has incomplete original input references.")
        for source, ident in zip(inputs, expected_ids):
            original = raw_sources.get(ident) if recipe["operation"] == "raw" else assets.get(ident)
            identity_key = "source_id" if recipe["operation"] == "raw" else "asset_id"
            if (not isinstance(source, dict) or original is None or source.get(identity_key) != ident
                    or any(source.get(k) != original.get(k) for k in ("path", "sha256", "size"))):
                raise ValueError("A preserved imaging input is missing or changed.")

    authored = {a["id"]: a for a in p["assets"] if isinstance(a.get("provenance"), dict)
                and a["provenance"].get("backend") == "blender-authored-scene"}
    found = set()
    if authored:
        for relative in _scan(root, "exports", ".json"):
            document, _ = _read_owned(root, relative)
            result = document.get("result", {}) if isinstance(document, dict) else {}
            advertised = result.get("asset", {}) if isinstance(result, dict) else {}
            asset = authored.get(advertised.get("id")) if isinstance(advertised, dict) else None
            if asset is None:
                continue
            digest = asset["provenance"].get("scene_sha256")
            name = result.get("scene_filename")
            if (advertised.get("sha256") != asset["sha256"] or result.get("scene_sha256") != digest
                    or not isinstance(name, str) or "/" in name or Path(name).suffix != ".blend"):
                raise ValueError("A preserved authored scene receipt has inconsistent identities.")
            snapshot = copy.deepcopy(document.get("snapshot", {}))
            if not isinstance(snapshot, dict):
                raise ValueError("A preserved scene recipe snapshot is invalid.")
            snapshot["scene"] = validate_scene(snapshot.get("scene"))
            _portable_json(snapshot)
            # Local HTTP URLs are session presentation, not source provenance.
            portable = {"result": {key: result[key] for key in
                        ("asset", "scene_filename", "scene_sha256", "project_revision", "masters_filename",
                         "masters_sha256", "masters_manifest") if key in result},
                        "snapshot": snapshot, "issuance_effect": "NONE"}
            _portable_json(portable)
            add("exports/" + name, "authored-blender-source", digest)
            if asset["provenance"].get("scene_linear_masters") or any(key in result for key in
                    ("masters_filename", "masters_sha256", "masters_manifest")):
                master_name = result.get("masters_filename")
                master_digest = result.get("masters_sha256")
                if (not isinstance(master_name, str) or "/" in master_name or Path(master_name).suffix != ".zip"
                        or master_digest != asset["provenance"].get("masters_sha256")
                        or not isinstance(result.get("masters_manifest"), dict)):
                    raise ValueError("Scene-linear masters are missing their preserved receipt identity.")
                # The inner archive remains inert and is never recursively extracted.
                add("exports/" + master_name, "authored-scene-masters", master_digest)
            add(relative, "authored-scene-receipt", data=_json_bytes(portable))
            found.add(asset["id"])
        if found != set(authored):
            raise ValueError("An authored 3D render is missing its preserved Blender source or recipe receipt.")
    for asset in p["assets"]:
        provenance = asset.get("provenance", {})
        if provenance.get("backend") == "blender" and not any(a.get("sha256") == provenance.get("scene_sha256")
                                                               and a.get("kind") == "scene" for a in p["assets"]):
            raise ValueError("A Blender render is missing its admitted original scene.")
        if provenance.get("backend") == "comfyui":
            warnings.append("Generated media are bundled. Historical bound workflows, model weights and custom-node runtimes are not stored with those media and are not regenerated by restoring.")
    workflow = root / "workflow.json"
    if workflow.exists() or workflow.is_symlink():
        graph, payload = _read_owned(root, "workflow.json")
        graph = validate_workflow(graph)
        _portable_json(graph, workflow=True)
        add("workflow.json", "generation-workflow", data=payload)
        warnings.append("The saved generation workflow is inert. It still requires its compatible ComfyUI nodes, model files and any engine-local inputs; these are not part of the project archive.")
    add("project.json", "authoring-project", data=_json_bytes(p))
    add("assets.json", "media-inventory", data=_json_bytes(p["assets"]))
    return p, files, list(dict.fromkeys(warnings))


def _unchanged(before, after):
    return all(getattr(before, key) == getattr(after, key) for key in ("st_size", "st_mtime_ns", "st_ctime_ns", "st_ino"))


def _digest(path, cancel_event=None):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            _cancel(cancel_event)
            block = source.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(path):
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def export_archive(project, project_dir, output, cancel_event=None, progress=None):
    """Write one immutable archive; an error never replaces an existing file."""
    _cancel(cancel_event)
    root = _root(project_dir)
    p, files, warnings = _collect(project, root, cancel_event)
    output = Path(output).absolute()
    parent = _root(output.parent)
    output = parent / output.name
    if output.exists() or output.is_symlink():
        raise ValueError("An existing archive cannot be overwritten.")
    total, copied = sum(entry["size"] for entry in files.values()), 0
    records = []
    fd, name = tempfile.mkstemp(prefix=".cinematicum-archive-", suffix=".partial", dir=str(parent))
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w+b") as target:
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for relative, entry in sorted(files.items()):
                    _cancel(cancel_event)
                    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    digest, size = hashlib.sha256(), 0
                    with archive.open(info, "w", force_zip64=True) as sink:
                        if "data" in entry:
                            payload = entry["data"]
                            digest.update(payload)
                            sink.write(payload)
                            size = len(payload)
                            copied += size
                        else:
                            with _open_owned(root, relative) as source:
                                before = os.fstat(source.fileno())
                                while True:
                                    _cancel(cancel_event)
                                    block = source.read(CHUNK)
                                    if not block:
                                        break
                                    size += len(block)
                                    copied += len(block)
                                    if size > entry["size"] or copied > MAX_BYTES:
                                        raise ValueError("A dependency grew while being archived.")
                                    sink.write(block)
                                    digest.update(block)
                                    _progress(progress, .85 * copied / max(1, total))
                                if not _unchanged(before, os.fstat(source.fileno())):
                                    raise ValueError("A dependency changed while being archived: " + relative)
                    if size != entry["size"] or entry["expected"] is not None and digest.hexdigest() != entry["expected"]:
                        raise ValueError("A dependency failed its admitted SHA-256/size identity: " + relative)
                    records.append({"path": relative, "sha256": digest.hexdigest(), "size": size, "role": entry["role"]})
                manifest = {"format": FORMAT, "version": VERSION, "project_id": p["id"], "project_revision": p.get("revision", 0),
                            "files": records, "total_bytes": total, "warnings": warnings,
                            "scope": "Owned authoring data and media; external engines, plugins and model weights are prerequisites.",
                            "issuance_effect": "NONE"}
                payload = _json_bytes(manifest)
                if total + len(payload) > MAX_BYTES:
                    raise ValueError("The archive including its inventory exceeds 64 GiB.")
                info = zipfile.ZipInfo(MANIFEST, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, payload)
            target.flush()
            os.fsync(target.fileno())
        _progress(progress, .9)
        if temporary.stat().st_size > MAX_BYTES:
            raise ValueError("The completed archive including ZIP metadata exceeds the 64 GiB file limit.")
        digest = _digest(temporary, cancel_event)
        _cancel(cancel_event)
        # link() is a no-replace publication, unlike rename/replace on POSIX.
        os.link(temporary, output)
        _fsync_directory(parent)
        report = {"path": str(output), "filename": output.name, "sha256": digest, "size": output.stat().st_size,
                  "files": len(records), "total_bytes": total, "warnings": warnings, "manifest": manifest,
                  "issuance_effect": "NONE"}
        _progress(progress, 1)
        return report
    finally:
        temporary.unlink(missing_ok=True)


def _central_directory_bound(source, size):
    """Bound ZipFile's central-directory allocation before it reads that data."""
    if size < 22 or size > MAX_BYTES:
        raise ValueError("Project archive size is outside its format limits.")
    source.seek(size - 22)
    end = source.read(22)
    if end[:4] != b"PK\x05\x06":
        raise ValueError("Project archives must have a canonical ZIP end record without trailing data or comments.")
    _, disk, first_disk, count_disk, count, cd_size, cd_offset, comment = struct.unpack("<4s4H2IH", end)
    if disk or first_disk or count_disk != count or comment:
        raise ValueError("Multipart/commented ZIP archives are unsupported.")
    directory_end = size - 22
    if count == 0xffff or cd_size == 0xffffffff or cd_offset == 0xffffffff:
        source.seek(size - 42)
        locator = source.read(20)
        if locator[:4] != b"PK\x06\x07":
            raise ValueError("Invalid ZIP64 archive locator.")
        _, zip_disk, offset, disks = struct.unpack("<4sIQI", locator)
        if zip_disk or disks != 1 or offset > size - 98:
            raise ValueError("Invalid ZIP64 archive layout.")
        source.seek(offset)
        record = source.read(56)
        if len(record) != 56 or record[:4] != b"PK\x06\x06":
            raise ValueError("Invalid ZIP64 archive header.")
        _, length, _, _, disk, first_disk, count_disk, count, cd_size, cd_offset = struct.unpack("<4sQ2H2I4Q", record)
        if length != 44 or disk or first_disk or count_disk != count:
            raise ValueError("Unsupported ZIP64 extension or multipart layout.")
        directory_end = offset
        if offset + 56 != size - 42:
            raise ValueError("Unsupported ZIP64 layout.")
    if not 3 <= count <= MAX_FILES + 1 or not 0 < cd_size <= MAX_DIRECTORY or cd_offset + cd_size != directory_end:
        raise ValueError("The archive central directory exceeds its declared file/count bounds.")
    # ZipFile trusts directory byte size while allocating ZipInfo objects. Check
    # the actual count and bounded member names before allowing that allocation.
    source.seek(cd_offset)
    consumed, found = 0, 0
    while consumed < cd_size:
        header = source.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise ValueError("Malformed archive central directory.")
        name_size, extra_size, comment_size = struct.unpack_from("<3H", header, 28)
        length = 46 + name_size + extra_size + comment_size
        if not 0 < name_size <= 512 or extra_size > 4096 or comment_size or consumed + length > cd_size:
            raise ValueError("Archive member metadata exceeds its format bounds.")
        source.seek(length - 46, os.SEEK_CUR)
        consumed += length
        found += 1
        if found > count:
            raise ValueError("Archive central directory contains an undeclared excess of entries.")
    if found != count:
        raise ValueError("Archive central directory file count is inconsistent.")
    source.seek(0)


def _archive_inventory(archive):
    items = archive.infolist()
    if not 3 <= len(items) <= MAX_FILES + 1:
        raise ValueError("The archive must contain its inventory and at most 10,000 dependency files.")
    seen, entries, total = set(), {}, 0
    for info in items:
        name = info.filename
        _relative(name)
        key = unicodedata.normalize("NFC", name).casefold()
        mode = info.external_attr >> 16
        if (info.orig_filename != name or key in seen or info.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                or info.flag_bits & 1 or info.compress_type != zipfile.ZIP_STORED
                or info.file_size != info.compress_size or not 0 < info.file_size <= MAX_BYTES):
            raise ValueError("Archive contains a duplicate, symlink, encrypted, compressed or invalid member.")
        if name != MANIFEST and not _allowed(name):
            raise ValueError("Archive contains a file outside the portable project format.")
        seen.add(key)
        entries[name] = info
        total += info.file_size
        if total > MAX_BYTES:
            raise ValueError("The archive expands beyond 64 GiB.")
    if MANIFEST not in entries or entries[MANIFEST].file_size > MAX_JSON:
        raise ValueError("The project archive has no bounded CINEMATICUM inventory.")
    manifest = _json_load(archive.read(entries[MANIFEST]))
    if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT or type(manifest.get("version")) is not int
            or manifest["version"] != VERSION or not isinstance(manifest.get("files"), list)
            or len(manifest["files"]) != len(entries) - 1):
        raise ValueError("Unsupported or incomplete CINEMATICUM archive inventory.")
    expected = {}
    for item in manifest["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256", "role"}:
            raise ValueError("Invalid archive inventory entry.")
        name = item["path"]
        if (not isinstance(name, str) or name not in entries or name == MANIFEST or name in expected or type(item["size"]) is not int
                or item["size"] != entries[name].file_size or not isinstance(item["sha256"], str) or not _SHA.fullmatch(item["sha256"])
                or not isinstance(item["role"], str) or len(item["role"]) > 80):
            raise ValueError("Archive member identity does not agree with its inventory.")
        expected[name] = item
    if set(entries) != set(expected) | {MANIFEST} or not {"project.json", "assets.json"} <= set(expected):
        raise ValueError("Archive dependencies do not match the declared file inventory.")
    if type(manifest.get("total_bytes")) is not int or manifest["total_bytes"] != total - entries[MANIFEST].file_size:
        raise ValueError("Archive total size does not agree with its inventory.")
    return manifest, expected, entries


def import_archive(archive_path, projects_root, cancel_event=None, progress=None):
    """Verify into private staging, then publish a fresh project UUID atomically."""
    _cancel(cancel_event)
    root = _root(projects_root)
    incoming = Path(archive_path).absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(str(incoming), flags)
    except OSError as exc:
        raise ValueError("Cannot open the uploaded project archive safely.") from exc
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Project archive input must be a regular file.")
        _central_directory_bound(source, before.st_size)
        with tempfile.TemporaryDirectory(prefix=".cinematicum-import-", dir=str(root.parent)) as temporary:
            staging = Path(temporary) / "project"
            staging.mkdir(mode=0o700)
            try:
                with zipfile.ZipFile(source, "r", allowZip64=True) as archive:
                    manifest, expected, entries = _archive_inventory(archive)
                    copied = 0
                    for relative in sorted(expected):
                        _cancel(cancel_event)
                        target = staging / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        digest, size = hashlib.sha256(), 0
                        with archive.open(entries[relative], "r") as member, target.open("xb") as sink:
                            while True:
                                _cancel(cancel_event)
                                block = member.read(CHUNK)
                                if not block:
                                    break
                                copied += len(block)
                                size += len(block)
                                if size > expected[relative]["size"] or copied > MAX_BYTES:
                                    raise ValueError("Archive extraction exceeded its declared bound.")
                                digest.update(block)
                                sink.write(block)
                                _progress(progress, .8 * copied / max(1, manifest["total_bytes"]))
                            sink.flush()
                            os.fsync(sink.fileno())
                        if size != expected[relative]["size"] or digest.hexdigest() != expected[relative]["sha256"]:
                            raise ValueError("Archive dependency SHA-256/size mismatch: " + relative)
                project, _ = _read_owned(staging, "project.json")
                assets, _ = _read_owned(staging, "assets.json")
                if (not isinstance(project, dict) or project.get("assets") != assets
                        or project.get("id") != manifest.get("project_id")):
                    raise ValueError("Archived project and media inventory disagree.")
                (staging / "media").mkdir(exist_ok=True)
                (staging / "exports").mkdir(exist_ok=True)
                normalized, required, warnings = _collect(project, staging, cancel_event)
                if set(required) != set(expected):
                    raise ValueError("The archive contains undeclared dependencies or is missing managed project state.")
                # _collect verifies semantic dependency references; the readback
                # also checks their recorded identities against the ZIP hashes.
                for relative, entry in required.items():
                    if entry["expected"] is not None and entry["expected"] != expected[relative]["sha256"]:
                        raise ValueError("A restored dependency disagrees with its source provenance: " + relative)
                    if entry["role"] != expected[relative]["role"]:
                        raise ValueError("A restored dependency has an inconsistent declared role: " + relative)
                    if ("data" in entry and relative not in {"project.json", "assets.json"}
                            and hashlib.sha256(entry["data"]).hexdigest() != expected[relative]["sha256"]):
                        raise ValueError("Archive dependency metadata is not in the canonical portable form: " + relative)
                if not _unchanged(before, os.fstat(source.fileno())):
                    raise ValueError("The archive changed during restoration.")
                source.seek(0)
                archive_digest = hashlib.sha256()
                while True:
                    _cancel(cancel_event)
                    block = source.read(CHUNK)
                    if not block:
                        break
                    archive_digest.update(block)
                if not _unchanged(before, os.fstat(source.fileno())):
                    raise ValueError("The archive changed during restoration.")
                ident = uuid.uuid4().hex
                normalized["id"] = ident
                normalized["revision"] = 1
                normalized["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                normalized["archive_restore"] = {"format": FORMAT, "version": VERSION,
                    "source_project_id": project["id"], "archive_sha256": archive_digest.hexdigest(),
                    "files": len(expected), "total_bytes": manifest["total_bytes"], "warnings": warnings,
                    "issuance_effect": "NONE"}
                for name, value in (("project.json", normalized), ("assets.json", normalized["assets"])):
                    with (staging / name).open("wb") as out:
                        out.write(_json_bytes(value))
                        out.flush()
                        os.fsync(out.fileno())
                for directory, _, _ in os.walk(staging, topdown=False):
                    _fsync_directory(directory)
                _cancel(cancel_event)
                destination = root / ident
                # mkdir is an exclusive identity reservation. We only replace
                # this newly created empty directory with the verified tree.
                try:
                    destination.mkdir(mode=0o700)
                except FileExistsError as exc:
                    raise ValueError("The new project identity already exists; no project was replaced.") from exc
                try:
                    os.rename(staging, destination)
                except BaseException:
                    destination.rmdir()
                    raise
                _fsync_directory(root)
                _progress(progress, 1)
                return normalized
            except (zipfile.BadZipFile, RuntimeError) as exc:
                if isinstance(exc, ArchiveCancelled):
                    raise
                raise ValueError("Project archive verification failed: " + str(exc)) from exc

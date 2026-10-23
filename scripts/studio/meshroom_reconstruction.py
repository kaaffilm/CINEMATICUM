"""Project-owned Meshroom photogrammetry: actual graph execution and dense-artifact admission.

No synthetic surface is substituted for missing output. A trusted operator must
install Meshroom/AliceVision and pin the absolute batch executable SHA-256.
Studio owns selected image copies, temporary outputs, cancellation, admission
and immutable provenance; the external engine owns reconstruction.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile

from adapters import _terminate_owned
from reconstruction import _cancel, _hash_file, _owned, _number

ARTIFACT_NAMES = frozenset({"graph.mg", "meshroom-output.zip", "surface.json", "provenance.json"})
MAX_ARTIFACT_BYTES = 3 * 1024 ** 3
MAX_BINARY_BYTES = 256 * 1024 ** 2
MAX_IMAGE_BYTES = 64 * 1024 ** 2
MAX_INPUT_BYTES = 1024 ** 3
MAX_PIXELS = 384 * 1024 ** 2
MAX_IMAGES = 96
MAX_FILES = 4096
MAX_SECONDS = 7200
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_OUTPUT = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode()


def default_settings():
    return {"version": 1, "asset_ids": [], "min_faces": 100, "max_seconds": 3600}


def validate_settings(value):
    defaults = default_settings()
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise ValueError("Meshroom settings contain unsupported properties.")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Unsupported Meshroom settings version.")
    result = copy.deepcopy(defaults)
    result.update(copy.deepcopy(value))
    ids = result["asset_ids"]
    if (not isinstance(ids, list) or len(ids) > MAX_IMAGES
            or any(not isinstance(v, str) or not _ID.fullmatch(v) for v in ids)
            or len(ids) != len(set(ids))):
        raise ValueError("Select unique, admitted photo identities (at most 96).")
    result["min_faces"] = _number(result["min_faces"], "Minimum surface faces", 100, 1000000, True)
    result["max_seconds"] = _number(result["max_seconds"], "Meshroom deadline", 60, MAX_SECONDS, True)
    return result


def validate_recipe(recipe, project):
    if not isinstance(recipe, dict) or set(recipe) != {"operation", "settings"}:
        raise ValueError("Meshroom requires an exact operation and settings.")
    if recipe["operation"] != "meshroom-photogrammetry":
        raise ValueError("Only the fixed Meshroom photogrammetry pipeline is admitted.")
    settings = validate_settings(recipe["settings"])
    if not 3 <= len(settings["asset_ids"]) <= MAX_IMAGES:
        raise ValueError("Select 3 to 96 overlapping photographs.")
    assets = project.get("assets", []) if isinstance(project, dict) else []
    pixels = 0
    bytes_total = 0
    for identity in settings["asset_ids"]:
        found = [item for item in assets if isinstance(item, dict) and item.get("id") == identity]
        if len(found) != 1 or found[0].get("kind") != "image":
            raise ValueError("Every image must be a unique admitted still asset.")
        item = found[0]
        if not isinstance(item.get("path"), str) or Path(item["path"]).suffix.lower() not in {
                ".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            raise ValueError("Meshroom inputs must be admitted JPEG, PNG or TIFF photographs.")
        width = _number(item.get("width"), "Photo width", 32, 8192, True)
        height = _number(item.get("height"), "Photo height", 32, 8192, True)
        pixels += width * height
        size = _number(item.get("size"), "Admitted photo bytes", 1, MAX_IMAGE_BYTES, True)
        bytes_total += size
        if not isinstance(item.get("sha256"), str) or not _SHA.fullmatch(item["sha256"]):
            raise ValueError("Each source photograph needs its admitted SHA-256.")
    if pixels > MAX_PIXELS or bytes_total > MAX_INPUT_BYTES:
        raise ValueError("Meshroom input exceeds its admitted image or byte budget.")
    return {"operation": "meshroom-photogrammetry", "settings": settings}


def _binary():
    value = os.environ.get("CINEMATICUM_MESHROOM_BATCH")
    expected = os.environ.get("CINEMATICUM_MESHROOM_BATCH_SHA256")
    if not value or not expected or not _SHA.fullmatch(expected):
        raise RuntimeError("A trusted Meshroom batch path and executable SHA-256 must be configured by the operator.")
    path = Path(value).expanduser()
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError("Meshroom batch executable must use a real absolute path, without symlinks.")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError("The configured Meshroom batch executable is unavailable.")
    actual, _ = _hash_file(path, MAX_BINARY_BYTES)
    if actual != expected:
        raise RuntimeError("Meshroom batch executable differs from the approved SHA-256.")
    return path, actual


def capabilities():
    result = {
        "available": False, "operations": [], "dense_available": False,
        "engine": "Meshroom / AliceVision", "pipeline": "photogrammetry",
        "pipeline_accepted": False, "reason": None,
        "limits": {"images": MAX_IMAGES, "aggregate_bytes": MAX_INPUT_BYTES,
                   "seconds": MAX_SECONDS, "output_bytes": MAX_ARTIFACT_BYTES},
        "scope": "Pinned external headless graph, actual triangulated textured mesh, immutable project outputs."
    }
    try:
        path, digest = _binary()
        result.update(available=True, operations=["meshroom-photogrammetry"],
                      dense_available=True, runner_sha256=digest,
                      reason="Executable hash verified; real reconstruction and image-set acceptance still require execution.")
    except (ValueError, RuntimeError, OSError) as exc:
        result["reason"] = str(exc)
    return result


def _execute(binary, images, results, graph, scratch, seconds, cancel_event):
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("PYTHON", "MESHROOM_", "ALICEVISION_", "LD_"))}
    environment["HOME"] = str(scratch)
    environment["TMPDIR"] = str(scratch)
    command = [str(binary), "--pipeline", "photogrammetry", "--input", str(images),
               "--output", str(results), "--save", str(graph)]
    log = scratch / "meshroom.stderr"
    with log.open("wb") as output:
        process = subprocess.Popen(command, cwd=scratch, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, env=environment,
                                   start_new_session=True)
        started = time.monotonic()
        try:
            while process.poll() is None:
                _cancel(cancel_event)
                if time.monotonic() - started > seconds:
                    raise TimeoutError("Meshroom exceeded its owned execution deadline.")
                if log.stat().st_size > 8 * 1024 ** 2:
                    raise RuntimeError("Meshroom exceeded the bounded diagnostic log.")
                if cancel_event is not None:
                    cancel_event.wait(.2)
                else:
                    time.sleep(.2)
            _cancel(cancel_event)
            if process.returncode:
                raise RuntimeError("Meshroom photogrammetry failed; external graph output was not admitted.")
        finally:
            _terminate_owned(process)


def _inspect_surface(output, minimum):
    files = []
    total = 0
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ValueError("Meshroom output contains an unsafe symbolic link.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Meshroom output contains an unsupported object.")
        if len(files) >= MAX_FILES:
            raise ValueError("Meshroom output exceeds the file budget.")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError("Meshroom output contains an empty artifact.")
        total += size
        if total > MAX_ARTIFACT_BYTES:
            raise ValueError("Meshroom output exceeds the bounded publication budget.")
        files.append(path)
    meshes = [p for p in files if p.suffix.lower() == ".obj"]
    textures = [p for p in files if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    materials = [p for p in files if p.suffix.lower() == ".mtl"]
    if not meshes or not textures or not materials:
        raise ValueError("Meshroom did not produce a textured OBJ surface and material assets.")
    for texture in textures:
        with texture.open("rb") as stream:
            header = stream.read(24)
        valid_png = (header.startswith(b"\x89PNG\r\n\x1a\n") and
                     header[12:16] == b"IHDR" and
                     int.from_bytes(header[16:20], "big") > 0 and
                     int.from_bytes(header[20:24], "big") > 0)
        valid_jpeg = header.startswith(b"\xff\xd8\xff")
        if not (valid_png or valid_jpeg):
            raise ValueError("Meshroom produced a malformed texture header.")
    mesh = max(meshes, key=lambda p: (p.name.lower() == "texturedmesh.obj", p.stat().st_size))
    vertex_count = 0
    face_count = 0
    faces = []
    material_names = []
    with mesh.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if len(line) > 8192:
                raise ValueError("Meshroom mesh exceeds the OBJ record limit.")
            if line.startswith("v "):
                points = line.split()[1:4]
                if len(points) != 3 or any(not math.isfinite(float(v)) for v in points):
                    raise ValueError("Meshroom mesh contains invalid vertices.")
                vertex_count += 1
            elif line.startswith("f "):
                indices = []
                for fragment in line.split()[1:]:
                    indices.append(int(fragment.split("/")[0]))
                if len(indices) < 3 or any(v == 0 for v in indices):
                    raise ValueError("Meshroom mesh has invalid faces.")
                faces.extend(indices)
                face_count += 1
            elif line.startswith("mtllib "):
                material_names.extend(line.split()[1:])
    if vertex_count < 3 or face_count < minimum or face_count > 10000000:
        raise ValueError("Meshroom did not produce the required nontrivial dense mesh.")
    if not material_names or not any(p.name in material_names for p in materials):
        raise ValueError("Meshroom OBJ does not reference an admitted material library.")
    if any(abs(index) > vertex_count for index in faces):
        raise ValueError("Meshroom mesh has faces outside its vertex inventory.")
    return {
        "vertices": vertex_count, "faces": face_count, "textures": len(textures),
        "material_libraries": len(materials), "output_files": len(files),
        "output_bytes": total, "mesh_member": mesh.relative_to(output).as_posix()
    }, sorted(files, key=lambda p: p.relative_to(output).as_posix())


def run(project, project_dir, recipe, output_dir, progress=None, cancel_event=None):
    request = validate_recipe(recipe, project)
    _cancel(cancel_event)
    executable, runner_sha = _binary()
    root = Path(project_dir).absolute()
    output = Path(output_dir).absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Meshroom publication must stay inside its project.") from exc
    if (len(relative.parts) != 3 or relative.parts[:2] != ("meshroom", "outputs")
            or not _OUTPUT.fullmatch(relative.name)):
        raise ValueError("Meshroom output must be an immutable owned job identity.")
    parent = _owned(root, "meshroom/outputs", directory=True, create=True)
    if os.path.lexists(output):
        raise ValueError("An existing Meshroom result cannot be overwritten.")
    settings = request["settings"]
    originals = []
    identities = []
    if progress:
        progress(.02)
    with tempfile.TemporaryDirectory(prefix=".meshroom-building-", dir=parent) as temporary:
        scratch = Path(temporary)
        images = scratch / "source"
        results = scratch / "result"
        publication = scratch / "publication"
        images.mkdir()
        results.mkdir()
        publication.mkdir()
        for index, identity in enumerate(settings["asset_ids"]):
            _cancel(cancel_event)
            asset = next(v for v in project["assets"] if v["id"] == identity)
            source = _owned(root, asset["path"])
            digest, size = _hash_file(source, MAX_IMAGE_BYTES)
            if (digest, size) != (asset["sha256"], asset["size"]):
                raise ValueError("Source photograph differs from its admitted identity.")
            candidate = images / (f"{index:03d}_" + identity + source.suffix.lower())
            shutil.copyfile(source, candidate)
            if _hash_file(candidate, MAX_IMAGE_BYTES) != (digest, size):
                raise ValueError("Source changed during isolated Meshroom copy.")
            originals.append((source, digest, size))
            identities.append({"asset_id": identity, "sha256": digest, "bytes": size,
                               "width": asset["width"], "height": asset["height"]})
        if progress:
            progress(.08)
        graph = scratch / "graph.mg"
        _execute(executable, images, results, graph, scratch, settings["max_seconds"], cancel_event)
        _cancel(cancel_event)
        if not graph.is_file() or graph.is_symlink() or not 0 < graph.stat().st_size < 128 * 1024 ** 2:
            raise ValueError("Meshroom did not preserve its complete graph.")
        surface, discovered = _inspect_surface(results, settings["min_faces"])
        for source, digest, size in originals:
            if _hash_file(source, MAX_IMAGE_BYTES) != (digest, size):
                raise ValueError("Original image changed during external reconstruction.")
        if _binary()[1] != runner_sha:
            raise RuntimeError("The pinned Meshroom runner changed during execution.")
        shutil.copyfile(graph, publication / "graph.mg")
        (publication / "surface.json").write_bytes(_json(surface))
        with zipfile.ZipFile(publication / "meshroom-output.zip", "w",
                             compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for file in discovered:
                _cancel(cancel_event)
                archive.write(file, file.relative_to(results).as_posix())
        artifacts = []
        for filename in sorted(ARTIFACT_NAMES - {"provenance.json"}):
            digest, size = _hash_file(publication / filename, MAX_ARTIFACT_BYTES)
            artifacts.append({"filename": filename, "sha256": digest, "bytes": size, "size": size})
        receipt = {
            "type": "cinematicum-meshroom-reconstruction", "version": 1,
            "operation": request["operation"], "settings": settings,
            "inputs": identities, "surface": surface,
            "engine": {"name": "Meshroom / AliceVision", "pipeline": "photogrammetry",
                       "batch_executable_sha256": runner_sha},
            "authority": {"source_photos_immutable": True, "surface_admission": "geometric_and_artifact_checks",
                          "camera_accuracy_acceptance": False, "production_footage_acceptance": False},
            "artifacts": artifacts,
            "source_sha256": {Path(__file__).name: _hash_file(Path(__file__))[0]}
        }
        (publication / "provenance.json").write_bytes(_json(receipt))
        receipt_sha, receipt_size = _hash_file(publication / "provenance.json")
        _cancel(cancel_event)
        os.rename(publication, output)
    if progress:
        progress(1)
    return {
        "output_id": relative.name, "settings": settings, "surface": surface,
        "receipt": receipt,
        "artifacts": [*artifacts, {"filename": "provenance.json",
                                  "sha256": receipt_sha, "bytes": receipt_size, "size": receipt_size}]
    }

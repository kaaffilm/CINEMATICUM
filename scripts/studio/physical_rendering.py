"""Owned physical still rendering and strict PBRT-v4 scene transport.

This module deliberately imports no optional renderer. Mitsuba/Dr.Jit execute
in a separate, isolated, bytecode-disabled process. Recipes contain data, never
plugin names, executable paths, Python expressions, texture filenames or URLs.
The authored scene is sampled at one frame; this is not an HDR movie pipeline.
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

from adapters import _terminate_owned
from scene import (MATERIAL_DEFAULTS, camera_basis, camera_basis_at, default_scene,
                   focal_length_mm, object_matrix_at, pose_at, validate_scene)
from scene_hierarchy import local_matrix, matrix_product, transform_point
from spatial_import import validate_mesh

ARTIFACT_NAMES = frozenset({"render.exr", "preview.png", "spectral.exr", "scene.pbrt",
                            "scene.json", "optimized-settings.json", "optimization.json", "provenance.json"})
OPERATIONS = frozenset({"render", "inverse", "pbrt_export", "pbrt_import", "pbrt_render"})
VARIANTS = {"rgb": "llvm_ad_rgb", "spectral": "llvm_ad_spectral",
            "polarized": "llvm_ad_spectral_polarized"}
MAX_PBRT_BYTES = 8 * 1024 * 1024
MAX_RENDER_SECONDS = 600
MAX_IMAGE_BYTES = 256 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported properties.")
    return value


def _number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a finite number.")
    try:
        valid = math.isfinite(value) and low <= value <= high and (not integer or int(value) == value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("%s must be %sbetween %s and %s." % (label, "an integer " if integer else "", low, high))
    return int(value) if integer else float(value)


def _identifier(value, label="Object identity"):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(label + " must be a plain identifier.")
    return value


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode()


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def srgb_to_linear(color):
    channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]


def _display_color(rgb):
    def encode(v):
        v = min(1., max(0., v))
        return round(255 * (12.92 * v if v <= .0031308 else 1.055 * v ** (1/2.4) - .055))
    return "#" + "".join("%02x" % encode(v) for v in rgb)


def validate_spectrum(value, label="Spectrum", reflectance=False):
    _mapping(value, {"type", "value", "wavelengths", "values"}, label)
    kind, high = value.get("type"), 1 if reflectance else 100000
    if kind == "rgb":
        if set(value) != {"type", "value"} or not isinstance(value["value"], list) or len(value["value"]) != 3:
            raise ValueError(label + " needs three scene-linear RGB values.")
        return {"type": kind, "value": [_number(v, label, 0, high) for v in value["value"]]}
    if kind == "uniform":
        if set(value) != {"type", "value"}:
            raise ValueError(label + " needs one uniform value.")
        return {"type": kind, "value": _number(value["value"], label, 0, high)}
    if kind == "sampled":
        if (set(value) != {"type", "wavelengths", "values"} or not isinstance(value["wavelengths"], list)
                or not isinstance(value["values"], list) or not 2 <= len(value["values"]) <= 128
                or len(value["wavelengths"]) != len(value["values"])):
            raise ValueError(label + " needs 2–128 matching wavelength/value samples.")
        wavelengths = [_number(v, "Wavelength (nm)", 360, 830) for v in value["wavelengths"]]
        if any(a >= b for a, b in zip(wavelengths, wavelengths[1:])):
            raise ValueError(label + " wavelengths must be strictly increasing.")
        return {"type": kind, "wavelengths": wavelengths,
                "values": [_number(v, label, 0, high) for v in value["values"]]}
    raise ValueError(label + " must use rgb, uniform or sampled data.")


def validate_material(value):
    if not isinstance(value, dict):
        raise ValueError("Physical material must be a data object.")
    kind = value.get("type")
    fields = {"diffuse": {"reflectance"}, "coated_diffuse": {"reflectance", "ior", "roughness"}, "dielectric": {"ior", "roughness"},
              "conductor": {"eta", "k", "roughness"},
              "polarizer": {"angle", "transmittance"},
              "retarder": {"angle", "retardance", "transmittance"}}.get(kind) if isinstance(kind, str) else None
    if fields is None:
        raise ValueError("Physical material must be diffuse, dielectric, conductor, polarizer or retarder.")
    _mapping(value, {"type", "emission", *fields}, "Physical material")
    result = {"type": kind}
    if kind in {"diffuse", "coated_diffuse"}:
        result["reflectance"] = validate_spectrum(value.get("reflectance", {"type": "rgb", "value": [.5]*3}), reflectance=True)
    if kind in {"dielectric", "coated_diffuse"}:
        result["ior"] = _number(value.get("ior", 1.5), "Index of refraction", 1.0001, 4)
    if kind in {"dielectric", "conductor", "coated_diffuse"}:
        result["roughness"] = _number(value.get("roughness", 0), "Roughness", 0, 1)
    if kind == "conductor":
        result["eta"] = validate_spectrum(value.get("eta"), "Conductor eta")
        result["k"] = validate_spectrum(value.get("k"), "Conductor extinction k")
    if kind in {"polarizer", "retarder"}:
        result["angle"] = _number(value.get("angle", 0), "Optical axis angle", -360, 360)
        result["transmittance"] = _number(value.get("transmittance", 1), "Transmittance", 0, 1)
    if kind == "retarder":
        result["retardance"] = _number(value.get("retardance", 90), "Retardance", -720, 720)
    if value.get("emission") is not None:
        result["emission"] = validate_spectrum(value["emission"], "Material emission")
    return result


def default_settings():
    return {"version": 1, "mode": "spectral", "frame": 1, "spp": 64, "max_depth": 8, "seed": 0,
            "spectral_bands": [], "material_overrides": {}, "light_spectra": {}, "world_spectrum": None,
            "optimization": {"object_id": None, "iterations": 32, "learning_rate": .05}}


def validate_settings(value, scene=None):
    defaults = default_settings()
    _mapping(value, defaults, "Physical renderer settings")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Unsupported physical renderer settings version.")
    mode = value.get("mode", "spectral")
    if not isinstance(mode, str) or mode not in VARIANTS:
        raise ValueError("Rendering mode must be rgb, spectral or polarized.")
    result = {"version": 1, "mode": mode}
    for key, low, high in (("frame", 1, 7200), ("spp", 1, 4096), ("max_depth", 2, 64), ("seed", 0, 2147483647)):
        result[key] = _number(value.get(key, defaults[key]), key, low, high, True)
    bands = value.get("spectral_bands", [])
    if not isinstance(bands, list) or len(bands) > 16:
        raise ValueError("Choose at most 16 spectral response bands.")
    result["spectral_bands"], names = [], set()
    for band in bands:
        _mapping(band, {"name", "min_nm", "max_nm"}, "Spectral band")
        name = _identifier(band.get("name"), "Spectral band name")
        if name in names or name in {"R", "G", "B", "A", "W"}:
            raise ValueError("Spectral band names must be unique and cannot use reserved RGB/A/W names.")
        names.add(name)
        low = _number(band.get("min_nm"), "Band start", 360, 829)
        high = _number(band.get("max_nm"), "Band end", low + 1, 830)
        result["spectral_bands"].append({"name": name, "min_nm": low, "max_nm": high})
    if bands and mode != "spectral":
        raise ValueError("Spectral band output requires spectral mode; polarized mode records RGB Stokes channels.")
    overrides = value.get("material_overrides", {})
    if not isinstance(overrides, dict) or len(overrides) > 96:
        raise ValueError("Choose at most 96 physical material overrides.")
    result["material_overrides"] = {_identifier(k): validate_material(v) for k, v in overrides.items()}
    lights = value.get("light_spectra", {})
    if not isinstance(lights, dict) or len(lights) > 16:
        raise ValueError("Choose at most 16 physical light spectra.")
    result["light_spectra"] = {_identifier(k, "Light identity"): validate_spectrum(v, "Light spectrum") for k, v in lights.items()}
    if any(m["type"] in {"polarizer", "retarder"} for m in result["material_overrides"].values()) and mode != "polarized":
        raise ValueError("Polarizer and retarder materials require polarized mode.")
    world = value.get("world_spectrum")
    result["world_spectrum"] = None if world is None else validate_spectrum(world, "World radiance")
    if mode == "rgb":
        def sampled(item):
            return isinstance(item, dict) and (item.get("type") == "sampled" or any(sampled(v) for v in item.values()))
        if sampled(result):
            raise ValueError("Sampled spectra require spectral or polarized rendering.")
    opt = value.get("optimization", defaults["optimization"])
    _mapping(opt, {"object_id", "iterations", "learning_rate"}, "Inverse optimization")
    ident = opt.get("object_id")
    result["optimization"] = {"object_id": None if ident is None else _identifier(ident),
                              "iterations": _number(opt.get("iterations", 32), "Optimization iterations", 1, 200, True),
                              "learning_rate": _number(opt.get("learning_rate", .05), "Learning rate", .00001, .5)}
    if scene is not None:
        scene = validate_scene(scene)
        ids = {obj["id"] for obj in scene["objects"]}
        if set(overrides) - ids or ident is not None and ident not in ids:
            raise ValueError("Physical materials and optimization must reference existing scene objects.")
        if set(lights) - {light["id"] for light in scene["lights"]}:
            raise ValueError("Physical light spectra must reference existing scene lights.")
        for obj in scene["objects"]:
            if result["material_overrides"].get(obj["id"], {}).get("type") in {"polarizer", "retarder"}:
                mesh = geometry_mesh(obj)
                if not mesh.get("uvs") or any(i < 0 for row in mesh["uv_indices"] for i in row):
                    raise ValueError("Optical-axis materials need a plane or a mesh with complete UV coordinates defining the physical axis.")
        if result["frame"] > scene["frame_end"]:
            raise ValueError("Physical render frame is outside the authored scene.")
    return result


def _scene_from_project(project):
    scene = project.get("settings", {}).get("scene")
    if scene is None:
        raise ValueError("Create or import a 3D scene before physical rendering.")
    return validate_scene(scene, width=project.get("width"), height=project.get("height"))


def _validate_scene_support(scene):
    camera = scene["camera"]
    if camera["focal_ratio"] != 1:
        raise ValueError("Physical rendering does not yet transport a non-unit camera focal ratio.")
    if camera["dof_enabled"] and (camera["aperture_blades"] or camera["aperture_ratio"] != 1 or camera["aperture_rotation"]):
        raise ValueError("Physical rendering supports a circular thin-lens aperture, not polygonal or anamorphic apertures.")
    if scene["world"]["transparent"]:
        raise ValueError("Physical radiance output currently requires an opaque world; transparent film is not transported.")
    if scene["output"]["passes"]:
        raise ValueError("Cycles-specific output passes are not transported. Clear them or render through Cycles.")
    if scene["width"] * scene["height"] > 4 * 1024 * 1024:
        raise ValueError("Physical still rendering is bounded to 4,194,304 pixels.")


def validate_recipe(recipe, project):
    _mapping(recipe, {"operation", "settings", "target_asset_id", "pbrt_text"}, "Physical render request")
    operation = recipe.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError("Choose a supported physical renderer operation.")
    scene = None if operation == "pbrt_import" else _scene_from_project(project)
    settings = validate_settings(recipe.get("settings", project.get("physical_rendering", default_settings())), scene)
    result = {"operation": operation, "settings": settings}
    if operation == "pbrt_import":
        source = recipe.get("pbrt_text")
        if not isinstance(source, str) or not source.strip() or len(source.encode()) > MAX_PBRT_BYTES or "\0" in source:
            raise ValueError("PBRT input must be nonempty UTF-8 text of at most 8 MiB.")
        if "target_asset_id" in recipe:
            raise ValueError("PBRT import cannot take an inverse target.")
        result["pbrt_text"] = source
        return result
    if "pbrt_text" in recipe:
        raise ValueError("Only PBRT import accepts scene text.")
    _validate_scene_support(scene)
    if operation in {"render", "inverse", "pbrt_render"} and scene["width"] * scene["height"] * settings["spp"] > 16777216:
        raise ValueError("One physical render pass is bounded to 16,777,216 pixel samples. Reduce resolution or samples.")
    if operation == "inverse":
        if settings["mode"] != "rgb":
            raise ValueError("The inverse solver currently optimizes linear RGB diffuse reflectance; choose RGB mode.")
        ident = settings["optimization"]["object_id"]
        material = settings["material_overrides"].get(ident, {})
        if material.get("type") != "diffuse" or material["reflectance"]["type"] != "rgb":
            raise ValueError("Inverse rendering needs a selected object with an explicit diffuse RGB physical material.")
        result["target_asset_id"] = _identifier(recipe.get("target_asset_id"), "Inverse target asset")
        if scene["width"] * scene["height"] * settings["spp"] * settings["optimization"]["iterations"] > 268435456:
            raise ValueError("Inverse optimization exceeds the 268-million pixel-sample iteration budget.")
    elif "target_asset_id" in recipe:
        raise ValueError("Only inverse rendering accepts a target image.")
    if operation.startswith("pbrt_"):
        if settings["mode"] == "polarized" or settings["spectral_bands"]:
            raise ValueError("PBRT transport does not support polarization or Mitsuba sensor-response bands.")
        if any(v["type"] in {"polarizer", "retarder"} for v in settings["material_overrides"].values()):
            raise ValueError("PBRT transport cannot represent optical polarization materials.")
    return result


def find_python(python=None):
    value = python if python is not None else os.environ.get("CINEMATICUM_PHYSICAL_PYTHON")
    relative = "Library/Application Support/CINEMATICUM/Physical/py313-v1/bin/python" if sys_platform_is_macos() else ".local/share/CINEMATICUM/Physical/py312-v1/bin/python"
    path = Path(value).expanduser() if value else Path.home() / relative
    return str(path) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else None


def find_pbrt():
    value = os.environ.get("CINEMATICUM_PBRT") or shutil.which("pbrt")
    relative = ("Library/Application Support" if sys_platform_is_macos() else ".local/share")
    managed = Path.home() / relative / "CINEMATICUM/Physical/pbrt-v4-b4ce9687-v1/bin/pbrt"
    path = Path(value).expanduser() if value else managed
    return str(path) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else None


def _command(python=None):
    executable = find_python(python)
    if not executable:
        raise RuntimeError("The optional Mitsuba runtime is not installed. Configure CINEMATICUM_PHYSICAL_PYTHON.")
    return [executable, "-I", "-B", str(Path(__file__).with_name("physical_rendering_worker.py"))]


def _env():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "MI_", "DRJIT_"))}
    env.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
    llvm = os.environ.get("CINEMATICUM_PHYSICAL_LLVM")
    if llvm:
        path = Path(llvm).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise RuntimeError("CINEMATICUM_PHYSICAL_LLVM must identify an existing absolute LLVM shared library.")
        env["DRJIT_LIBLLVM_PATH"] = str(path)
    elif sys_platform_is_macos():
        for candidate in ("/opt/homebrew/opt/llvm/lib/libLLVM.dylib", "/usr/local/opt/llvm/lib/libLLVM.dylib",
                          "/opt/homebrew/opt/llvm@20/lib/libLLVM.dylib", "/usr/local/opt/llvm@20/lib/libLLVM.dylib"):
            if Path(candidate).is_file():
                env["DRJIT_LIBLLVM_PATH"] = candidate
                break
    return env


def sys_platform_is_macos():
    import sys
    return sys.platform == "darwin"


def capabilities(python=None):
    result = {"available": False, "operations": ["pbrt_export", "pbrt_import"], "modes": [],
              "pbrt_available": bool(find_pbrt()), "reason": "The optional Mitsuba runtime is not installed.",
              "scope": "Single-frame CPU radiance, Stokes output, bounded material inverse optimization, strict PBRT-v4 transport."}
    try:
        response = subprocess.run(_command(python), input=_json({"command": "doctor"}), capture_output=True,
                                  timeout=25, env=_env())
        if len(response.stdout) > 65536:
            raise RuntimeError("Physical renderer probe returned oversized data.")
        doctor = json.loads(response.stdout)
        if response.returncode or not doctor.get("available"):
            raise RuntimeError(doctor.get("error", "Physical renderer probe failed."))
        result.update(available=True, modes=doctor["modes"], versions=doctor["versions"], reason=None,
                      operations=["render", "inverse", "pbrt_export", "pbrt_import"] + (["pbrt_render"] if find_pbrt() else []))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["reason"] = str(exc)
    return result


def _hash_file(path, limit=1024 * 1024 * 1024):
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        first = os.fstat(stream.fileno())
        if not stat.S_ISREG(first.st_mode) or not 0 < first.st_size <= limit:
            raise ValueError("Physical renderer data must be a bounded nonempty regular file.")
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        last = os.fstat(stream.fileno())
        if (first.st_ino, first.st_size, first.st_mtime_ns) != (last.st_ino, last.st_size, last.st_mtime_ns):
            raise ValueError("Physical renderer data changed during verification.")
    return digest.hexdigest(), first.st_size


def _owned(root, relative, directory=False, create=False):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Physical rendering needs an existing real project directory.")
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in {".", ".."} for p in path.parts):
        raise ValueError("Physical renderer paths must remain inside their project.")
    current = root
    for index, part in enumerate(path.parts):
        current /= part
        if current.is_symlink():
            raise ValueError("Physical renderer paths cannot contain symbolic links.")
        if index < len(path.parts)-1 or directory:
            if create:
                current.mkdir(exist_ok=True)
            if not current.is_dir():
                raise ValueError("A physical renderer directory is missing.")
    return current


def _target(project, root, ident, scene):
    assets = [a for a in project.get("assets", []) if a.get("id") == ident]
    if len(assets) != 1 or assets[0].get("kind") != "image":
        raise ValueError("Inverse rendering needs one admitted still-image target.")
    asset = assets[0]
    path = _owned(root, asset.get("path", ""))
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".exr"}:
        raise ValueError("Inverse targets must be admitted PNG, JPEG or linear RGB OpenEXR images.")
    digest, size = _hash_file(path, MAX_IMAGE_BYTES)
    if asset.get("sha256") != digest or asset.get("size") != size:
        raise ValueError("The inverse target no longer matches its admitted identity.")
    if asset.get("width") not in (None, scene["width"]) or asset.get("height") not in (None, scene["height"]):
        raise ValueError("Inverse target dimensions must equal the authored scene dimensions.")
    return path, {"asset_id": ident, "sha256": digest, "bytes": size, "extension": path.suffix.lower()}


def _check_cancel(event):
    if event is not None and event.is_set():
        raise RuntimeError("Physical rendering cancelled.")


def _run_worker(request, scratch, python, progress, event):
    result_path, error_path = scratch / "worker.json", scratch / "worker.stderr"
    command = _command(python)
    with result_path.open("wb") as out, error_path.open("wb") as err:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                   env=_env(), start_new_session=True)
        try:
            process.stdin.write(_json(request)); process.stdin.close()
            started, last = time.monotonic(), -1.
            while process.poll() is None:
                _check_cancel(event)
                if time.monotonic() - started > MAX_RENDER_SECONDS:
                    raise RuntimeError("Physical rendering exceeded its ten-minute execution limit.")
                if result_path.stat().st_size > 2*1024*1024 or error_path.stat().st_size > 4*1024*1024:
                    raise RuntimeError("Physical renderer exceeded its bounded diagnostic output.")
                if progress:
                    try:
                        value = json.loads((scratch / "progress.json").read_text())["progress"]
                        if isinstance(value, (int, float)) and math.isfinite(value) and value > last:
                            progress(min(.98, max(0, value))); last = value
                    except (OSError, ValueError, KeyError):
                        pass
                event.wait(.1) if event is not None else time.sleep(.1)
            _check_cancel(event)
        finally:
            _terminate_owned(process)
    try:
        result = json.loads(result_path.read_text())
    except (ValueError, OSError) as exc:
        raise RuntimeError("The physical renderer did not return a valid result: " + error_path.read_text(errors="replace")[-1200:]) from exc
    if process.returncode or result.get("error"):
        raise RuntimeError(result.get("error", "Physical renderer execution failed."))
    return result


def run(project, project_dir, recipe, output_dir, progress=None, cancel_event=None, python=None):
    recipe = validate_recipe(recipe, project)
    root, output = Path(project_dir).absolute(), Path(output_dir).absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Physical rendering output must remain inside its project.") from exc
    if len(relative.parts) != 3 or relative.parts[:2] != ("physical", "outputs"):
        raise ValueError("Use physical/outputs/<job_id> for physical renderer output.")
    _identifier(relative.name, "Physical output identity")
    parent = _owned(root, "physical/outputs", directory=True, create=True)
    if output.exists() or output.is_symlink():
        raise ValueError("A physical rendering output cannot be overwritten.")
    _check_cancel(cancel_event)
    scene = None if recipe["operation"] == "pbrt_import" else _scene_from_project(project)
    inputs = []
    with tempfile.TemporaryDirectory(prefix=".building-", dir=parent) as temporary:
        scratch = Path(temporary); generated = scratch / "result"; generated.mkdir()
        settings = recipe["settings"]
        result = {}
        if recipe["operation"] == "pbrt_import":
            scene, settings = import_pbrt(recipe["pbrt_text"])
            (generated / "scene.pbrt").write_text(recipe["pbrt_text"], encoding="utf-8")
            result["scene"] = scene
            inputs = [{"kind": "pbrt-v4", "sha256": hashlib.sha256(recipe["pbrt_text"].encode()).hexdigest(),
                       "bytes": len(recipe["pbrt_text"].encode())}]
        elif recipe["operation"] == "pbrt_export":
            (generated / "scene.pbrt").write_text(export_pbrt(scene, settings), encoding="utf-8")
        else:
            request = {"command": "render", "scene": scene, "recipe": recipe, "output_dir": str(generated),
                       "progress_path": str(scratch / "progress.json")}
            if recipe["operation"] == "inverse":
                target, identity = _target(project, root, recipe["target_asset_id"], scene)
                copied = scratch / ("target" + identity["extension"])
                shutil.copyfile(target, copied)
                if _hash_file(copied, MAX_IMAGE_BYTES) != (identity["sha256"], identity["bytes"]):
                    raise ValueError("Inverse target changed while preparing the worker.")
                request["target_path"] = str(copied); inputs = [identity]
            if recipe["operation"] == "pbrt_render":
                executable = find_pbrt()
                if not executable:
                    raise RuntimeError("PBRT-v4 is not installed. Configure CINEMATICUM_PBRT with the actual executable.")
                (generated / "scene.pbrt").write_text(export_pbrt(scene, settings), encoding="utf-8")
                request["pbrt"] = executable
            result = _run_worker(request, scratch, python, progress, cancel_event)
        (generated / "scene.json").write_bytes(_json({"scene": scene, "physical_rendering": settings}))
        expected = set(p.name for p in generated.iterdir())
        if not expected or expected - ARTIFACT_NAMES or "provenance.json" in expected:
            raise RuntimeError("Physical renderer produced unexpected artifacts.")
        artifacts = []
        for name in sorted(expected):
            digest, size = _hash_file(generated / name)
            artifacts.append({"filename": name, "sha256": digest, "bytes": size, "size": size,
                              "kind": {".exr": "linear-image", ".png": "display-image", ".pbrt": "scene"}.get(Path(name).suffix, "metadata")})
        request_identity = {k: v for k, v in recipe.items() if k != "pbrt_text"}
        receipt = {"type": "cinematicum-physical-rendering", "version": 1, "operation": recipe["operation"],
                   "recipe": request_identity, "settings": settings, "scene_sha256": _digest(scene), "inputs": inputs,
                   "artifacts": artifacts, "engine": result.get("engine"),
                   "metrics": result.get("metrics", {}), "scope": result.get("scope", PBRT_SCOPE),
                   "source_sha256": {p.name: _hash_file(p)[0] for p in (Path(__file__), Path(__file__).with_name("physical_rendering_worker.py"))}}
        (generated / "provenance.json").write_bytes(_json(receipt))
        digest, size = _hash_file(generated / "provenance.json")
        artifacts = [*artifacts, {"filename": "provenance.json", "sha256": digest, "bytes": size, "size": size, "kind": "receipt"}]
        _check_cancel(cancel_event)
        os.rename(generated, output)
    if progress:
        progress(1)
    provenance = {**receipt, "output_id": relative.name, "receipt_sha256": digest}
    answer = {"artifacts": artifacts, "settings": settings, "provenance": provenance,
              "receipt": receipt, "output_id": relative.name}
    for key in ("scene", "optimized_settings"):
        if key in result:
            answer[key] = result[key]
    if "preview.png" in {a["filename"] for a in artifacts}:
        answer["path"] = str(output / "preview.png")
        answer["provenance"]["display_encoding"] = "sRGB"
    return answer


PBRT_SCOPE = {"format": "pbrt-v4", "transport": "Static selected-frame scene; strict documented subset, unsupported commands and parameters are errors.",
              "supported": ["perspective/thin-lens circular camera", "triangle meshes with indexed normals/UVs", "diffuse/coateddiffuse/dielectric/conductor with explicit eta/k",
                            "constant environment, point, distant and diffuse area emitters", "RGB/uniform/sampled spectra"],
              "unsupported": ["Includes and external files", "textures and media", "instances and animation", "polarization", "arbitrary plugin graphs"],
              "primitive_geometry": "32 segments, 16 latitude divisions for authored spheres; 32 segments with caps for cylinders; exact planes/cubes and admitted/evaluated meshes.",
              "material_translation": "Un-overridden CINEMATICUM materials map to Mitsuba principled; PBRT accepts coated-diffuse or untinted full transmission, and explicit typed conductor eta/k. Models are not claimed pixel-identical across engines."}


def geometry_mesh(obj):
    """Deterministic primitive triangles; modifier results retain verified geometry."""
    if obj["type"] == "mesh":
        return obj.get("modeling", {}).get("evaluation", {}).get("mesh", obj["mesh"])
    vertices, faces, normals = [], [], []
    kind = obj["type"]
    if kind == "plane":
        vertices = [[-1,-1,0], [1,-1,0], [1,1,0], [-1,1,0]]
        faces = [[0,1,2], [0,2,3]]
    elif kind == "cube":
        vertices = [[-1,-1,-1], [1,-1,-1], [1,1,-1], [-1,1,-1], [-1,-1,1], [1,-1,1], [1,1,1], [-1,1,1]]
        for q in ([3,2,1,0], [4,5,6,7], [0,1,5,4], [1,2,6,5], [2,3,7,6], [3,0,4,7]):
            faces += [[q[0],q[1],q[2]], [q[0],q[2],q[3]]]
    elif kind == "sphere":
        vertices = [[0.,0.,1.]]
        for j in range(1,16):
            phi = math.pi*j/16
            vertices += [[math.sin(phi)*math.cos(2*math.pi*i/32), math.sin(phi)*math.sin(2*math.pi*i/32), math.cos(phi)] for i in range(32)]
        south = len(vertices); vertices.append([0.,0.,-1.])
        for i in range(32):
            n=(i+1)%32; faces.append([0,1+i,1+n]); faces.append([south,1+14*32+n,1+14*32+i])
        for j in range(14):
            for i in range(32):
                a=1+j*32+i; b=1+j*32+(i+1)%32; c=b+32; d=a+32
                faces += [[a,d,c], [a,c,b]]
        # Sphere side winding is outward; top/bottom fans follow their cap normals.
        normals = copy.deepcopy(vertices)
    elif kind == "cylinder":
        vertices = [[math.cos(2*math.pi*i/32), math.sin(2*math.pi*i/32), z] for z in (-1,1) for i in range(32)]
        vertices += [[0.,0.,-1.], [0.,0.,1.]]
        for i in range(32):
            n=(i+1)%32; faces += [[i,n,32+n], [i,32+n,32+i], [64,n,i], [65,32+i,32+n]]
    else:
        raise ValueError("Unsupported physical geometry.")
    mesh = {"version": 1, "vertices": vertices, "triangles": faces}
    if kind == "plane":
        # Optical-axis materials use dp/du and dp/dv. Missing UVs would give
        # triangle-dependent frames along the diagonal of an otherwise flat plane.
        mesh.update(uvs=[[0.,0.],[1.,0.],[1.,1.],[0.,1.]], uv_indices=copy.deepcopy(faces))
    if normals:
        mesh.update(normals=normals, normal_indices=copy.deepcopy(faces))
    return validate_mesh(mesh)


def _world_mesh(mesh, matrix):
    """Bake a full affine hierarchy, preserving corner indices and normal directions."""
    result = {k: copy.deepcopy(v) for k, v in mesh.items() if k not in {"sha256", "source"}}
    result["vertices"] = [transform_point(matrix, p) for p in mesh["vertices"]]
    if mesh.get("normals"):
        a,b,c = [matrix[i:i+3] for i in (0,4,8)]
        def cross(x,y): return [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
        cols=[cross(b,c),cross(c,a),cross(a,b)]
        det=sum(a[i]*cols[0][i] for i in range(3))
        if abs(det)<1e-15:
            raise ValueError("A physical mesh transform is singular.")
        result["normals"] = []
        for normal in mesh["normals"]:
            v=[sum(cols[k][r]*normal[k] for k in range(3))/det for r in range(3)]; length=math.hypot(*v)
            result["normals"].append([x/length for x in v])
    return result


def _flatten_mesh(mesh):
    """PBRT and Mitsuba share one vertex index; retain distinct UV/normal corners."""
    vertices, normals, uvs, triangles, table = [], [], [], [], {}
    has_n, has_uv = bool(mesh.get("normals")), bool(mesh.get("uvs"))
    if has_uv and any(i < 0 for row in mesh["uv_indices"] for i in row):
        raise ValueError("Physical mesh UVs must cover every face corner; partial UV assignments are not transported.")
    for face_index, face in enumerate(mesh["triangles"]):
        indices=[]
        for corner, vertex in enumerate(face):
            ni=mesh["normal_indices"][face_index][corner] if has_n else -1
            ti=mesh["uv_indices"][face_index][corner] if has_uv else -1
            key=(vertex,ni,ti)
            if key not in table:
                table[key]=len(vertices); vertices.append(mesh["vertices"][vertex])
                if has_n: normals.append(mesh["normals"][ni])
                if has_uv: uvs.append(mesh["uvs"][ti])
            indices.append(table[key])
        triangles.append(indices)
    return {"vertices": vertices, "normals": normals, "uvs": uvs, "triangles": triangles}


def _spectrum_text(name, spectrum):
    if spectrum["type"] == "rgb":
        return '"rgb %s" [%s]' % (name, _numbers(spectrum["value"]))
    if spectrum["type"] == "uniform":
        pairs=[360, spectrum["value"], 830, spectrum["value"]]
    else:
        pairs=[x for pair in zip(spectrum["wavelengths"], spectrum["values"]) for x in pair]
    return '"spectrum %s" [%s]' % (name, _numbers(pairs))


def _numbers(values):
    return " ".join(format(v, ".12g") for v in values)


def _pbrt_material(obj, settings):
    override=settings["material_overrides"].get(obj["id"])
    if override:
        kind=override["type"]
        if kind=="diffuse": return 'Material "diffuse" ' + _spectrum_text("reflectance", override["reflectance"])
        if kind=="coated_diffuse": return 'Material "coateddiffuse" %s "float eta" [%g] "float roughness" [%g] "bool remaproughness" [false]' % (_spectrum_text("reflectance",override["reflectance"]),override["ior"],override["roughness"])
        if kind=="dielectric": return 'Material "dielectric" "float eta" [%g] "float roughness" [%g] "bool remaproughness" [false]' % (override["ior"],override["roughness"])
        if kind=="conductor": return 'Material "conductor" %s %s "float roughness" [%g] "bool remaproughness" [false]' % (_spectrum_text("eta",override["eta"]),_spectrum_text("k",override["k"]),override["roughness"])
        raise ValueError("PBRT cannot transport material " + kind)
    material=obj["material"]
    rgb={"type":"rgb","value":srgb_to_linear(material["color"])}
    if material["metallic"]==0 and material["transmission"]==0:
        return 'Material "coateddiffuse" %s "float roughness" [%g] "float eta" [%g] "bool remaproughness" [false]' % (_spectrum_text("reflectance",rgb),material["roughness"]**2,material["ior"])
    if material["metallic"]==0 and material["transmission"]==1 and material["color"].lower()=="#ffffff":
        return 'Material "dielectric" "float eta" [%g] "float roughness" [%g] "bool remaproughness" [false]' % (material["ior"],material["roughness"]**2)
    raise ValueError("PBRT cannot faithfully transport artist metal/transmission mixtures or tinted glass. Choose an explicit physical material for " + obj["id"] + ".")


def material_emission(obj, settings):
    override=settings["material_overrides"].get(obj["id"], {})
    if "emission" in override: return override["emission"]
    m=obj["material"]
    return {"type":"rgb","value":[v*m["emission_strength"] for v in srgb_to_linear(m["emission_color"])]} if m["emission_strength"] else None


def export_pbrt(scene, settings):
    scene=validate_scene(scene); settings=validate_settings(settings,scene); _validate_scene_support(scene)
    if settings["mode"]=="polarized" or settings["spectral_bands"]:
        raise ValueError("PBRT transport cannot represent polarization or Mitsuba sensor-response bands.")
    frame=settings["frame"]; camera=pose_at(scene["camera"],frame,"camera"); basis=camera_basis_at(scene["camera"],frame)
    if camera["shift_x"] or camera["shift_y"]:
        raise ValueError("PBRT transport currently rejects shifted principal points.")
    aspect=scene["width"]/scene["height"]
    # PBRT's fov applies to the smaller film axis; CINEMATICUM stores vertical FOV.
    fov=math.degrees(2*math.atan(math.tan(math.radians(camera["fov"])/2)*min(1.,aspect)))
    # PBRT LookAt uses +Z forward and Cross(up, direction) for image right.
    # The authored/Mitsuba camera uses -Z forward. Reflect camera X before
    # LookAt so a world-space point on the authored right stays image-right.
    lines=['# CINEMATICUM physical still; PBRT-v4. Linear sRGB numeric colors.', 'ColorSpace "srgb"', 'Scale -1 1 1',
           'LookAt '+_numbers([*camera["position"],*camera["target"],*basis["up"]]),
           'Camera "perspective" "float fov" [%s]' % format(fov,".12g")]
    if scene["camera"]["dof_enabled"]:
        radius=focal_length_mm(scene["camera"],camera["fov"])/1000/(2*camera["f_stop"])
        lines[-1]+=' "float lensradius" [%g] "float focaldistance" [%g]' % (radius,camera["focus_distance"])
    lines += ['Film "rgb" "string filename" ["render.exr"] "integer xresolution" [%d] "integer yresolution" [%d] "bool savefp16" [false]' % (scene["width"],scene["height"]),
              'Sampler "independent" "integer pixelsamples" [%d] "integer seed" [%d]' % (settings["spp"],settings["seed"]),
              'PixelFilter "box"', 'Integrator "volpath" "integer maxdepth" [%d]' % settings["max_depth"], 'WorldBegin']
    world=settings["world_spectrum"] or {"type":"rgb","value":[v*scene["world"]["strength"] for v in srgb_to_linear(scene["world"]["color"])]}
    lines.append('LightSource "infinite" '+_spectrum_text("L",world))
    for light in scene["lights"]:
        p=pose_at(light,frame,"light"); color=settings["light_spectra"].get(light["id"], {"type":"rgb","value":srgb_to_linear(light["color"])})
        lines.append('AttributeBegin')
        if light["type"]=="point":
            lines.append('LightSource "point" "point3 from" [%s] %s' % (_numbers(p["position"]),_spectrum_text("I",scale_spectrum(color,p["power"]/(4*math.pi)))))
        elif light["type"]=="sun":
            lines.append('LightSource "distant" "point3 from" [%s] "point3 to" [%s] %s' % (_numbers(p["position"]),_numbers(p["target"]),_spectrum_text("L",scale_spectrum(color,p["power"]))))
        else:
            lines.append('AreaLightSource "diffuse" '+_spectrum_text("L",scale_spectrum(color,p["power"]/(math.pi*p["size"]**2))))
            lines.append('Material "diffuse" "rgb reflectance" [0 0 0]')
            mesh=area_mesh(p)
            lines.extend(_pbrt_mesh(mesh))
        lines.append('AttributeEnd')
    for obj in scene["objects"]:
        lines += ['AttributeBegin', '# object '+obj["id"], _pbrt_material(obj,settings)]
        emission=material_emission(obj,settings)
        if emission: lines.append('AreaLightSource "diffuse" '+_spectrum_text("L",emission))
        mesh=_world_mesh(geometry_mesh(obj),object_matrix_at(scene,obj["id"],frame))
        lines.extend(_pbrt_mesh(mesh)); lines.append('AttributeEnd')
    text="\n".join(lines)+"\n"
    if len(text.encode())>MAX_PBRT_BYTES: raise ValueError("The PBRT scene exceeds the 8 MiB transport budget.")
    return text


def area_mesh(pose):
    basis=camera_basis(pose["position"],pose["target"])
    right=[-v for v in basis["right"]]; up=basis["up"]; half=pose["size"]/2
    return {"vertices":[[pose["position"][i]+half*(x*right[i]+y*up[i]) for i in range(3)] for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]],
            "triangles":[[0,1,2],[0,2,3]],"normals":[],"uvs":[]}


def _pbrt_mesh(mesh):
    flat=_flatten_mesh(mesh)
    line='Shape "trianglemesh" "point3 P" [%s] "integer indices" [%s]' % (_numbers([v for p in flat["vertices"] for v in p]),_numbers([v for p in flat["triangles"] for v in p]))
    if flat["normals"]: line+=' "normal N" [%s]' % _numbers([v for p in flat["normals"] for v in p])
    if flat["uvs"]: line+=' "point2 uv" [%s]' % _numbers([v for p in flat["uvs"] for v in p])
    return [line]


def scale_spectrum(spectrum, factor):
    result=copy.deepcopy(spectrum)
    key="values" if spectrum["type"]=="sampled" else "value"
    result[key]=[v*factor for v in spectrum[key]] if isinstance(spectrum[key],list) else spectrum[key]*factor
    return result


_PBRT_TOKEN = re.compile(r'\s+|\#[^\n]*|"(?:[^"\\\r\n]|\\["\\nt])*"|\[|\]|[A-Za-z_][A-Za-z_0-9]*|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')
_IDENTITY_MATRIX = [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]


class _PBRTParser:
    """A closed, non-executing subset of PBRT-v4's published text grammar."""
    def __init__(self, source):
        if not isinstance(source,str) or len(source.encode())>MAX_PBRT_BYTES:
            raise ValueError("PBRT input exceeds the 8 MiB transport bound.")
        self.tokens=[]; offset=0
        for match in _PBRT_TOKEN.finditer(source):
            if match.start()!=offset: raise ValueError("Unsupported PBRT token at byte %d." % offset)
            offset=match.end(); token=match.group()
            if token.isspace() or token.startswith("#"): continue
            if token.startswith('"'):
                try: self.tokens.append(("string",json.loads(token)))
                except ValueError as exc: raise ValueError("Invalid PBRT string escape.") from exc
            elif token[0] in "[ ]".replace(" ",""):
                self.tokens.append((token,token))
            elif token[0].isalpha() or token[0]=="_": self.tokens.append(("word",token))
            else: self.tokens.append(("number",_number(float(token),"PBRT number",-1e9,1e9)))
        if offset!=len(source): raise ValueError("Unsupported PBRT token at byte %d." % offset)
        self.index=0

    def pop(self, kind=None):
        if self.index>=len(self.tokens): raise ValueError("The PBRT scene ended unexpectedly.")
        token=self.tokens[self.index]; self.index+=1
        if kind and token[0]!=kind: raise ValueError("PBRT expected %s, received %r." % (kind,token[1]))
        return token[1]

    def peek(self,kind=None):
        if self.index>=len(self.tokens): return False
        return self.tokens[self.index][0]==kind if kind else self.tokens[self.index]

    def numbers(self,count):
        array=self.peek("[")
        if array:self.pop("[")
        values=[self.pop("number") for _ in range(count)]
        if array:self.pop("]")
        return values

    def params(self):
        result={}
        while self.peek("string"):
            name=self.pop("string").split()
            if len(name)!=2 or name[0] not in {"float","integer","rgb","spectrum","point3","point2","normal","bool","string"}:
                raise ValueError("Unsupported PBRT parameter declaration.")
            kind,key=name
            if key in result: raise ValueError("Duplicate PBRT parameter " + key)
            array=self.peek("[")
            if array:self.pop("[")
            values=[]
            while True:
                if kind=="string": value=self.pop("string")
                elif kind=="bool":
                    value=self.pop()
                    if value not in ("true","false"): raise ValueError("PBRT bool must be true or false.")
                    value=value=="true"
                else: value=self.pop("number")
                if kind=="integer":
                    if int(value)!=value: raise ValueError("PBRT integer parameter has a fractional value.")
                    value=int(value)
                values.append(value)
                if not array or self.peek("]"):break
            if array:self.pop("]")
            result[key]=(kind,values)
        return result


def _params_only(params, expected, label):
    if set(params)-set(expected): raise ValueError(label+" has unsupported parameters: "+", ".join(sorted(set(params)-set(expected))))
    for name,(kind,values) in params.items():
        allowed=expected[name] if isinstance(expected[name],tuple) else (expected[name],)
        if kind not in allowed: raise ValueError(label+" has an unsupported type for "+name)


def _one(params,key,default=None):
    if key not in params:return default
    values=params[key][1]
    if len(values)!=1:raise ValueError("PBRT "+key+" needs exactly one value.")
    return values[0]


def _vec(params,key,default):
    values=params.get(key,(None,default))[1]
    if len(values)!=3:raise ValueError("PBRT "+key+" needs three coordinates.")
    return list(values)


def _parse_spectrum(params,key,default,reflectance=False):
    if key not in params:return copy.deepcopy(default)
    kind,values=params[key]
    if kind=="rgb":return validate_spectrum({"type":"rgb","value":values},"PBRT "+key,reflectance)
    if kind=="float" and len(values)==1:return validate_spectrum({"type":"uniform","value":values[0]},"PBRT "+key,reflectance)
    if kind!="spectrum" or len(values)<4 or len(values)%2:
        raise ValueError("PBRT spectra must be numeric wavelength/value pairs; external spectral files are unsupported.")
    return validate_spectrum({"type":"sampled","wavelengths":values[::2],"values":values[1::2]},"PBRT "+key,reflectance)


def _parse_material(kind,params):
    if kind not in {"diffuse","coateddiffuse","dielectric","conductor"}:
        raise ValueError("Unsupported PBRT material: "+kind)
    allowed={"reflectance":("rgb","spectrum","float")} if kind in {"diffuse","coateddiffuse"} else {}
    if kind!="diffuse": allowed.update(roughness="float",remaproughness="bool")
    if kind in {"dielectric","coateddiffuse"}:allowed["eta"]="float"
    if kind=="conductor":allowed.update(eta=("rgb","spectrum","float"),k=("rgb","spectrum","float"))
    _params_only(params,allowed,"PBRT "+kind)
    value={"type":{"coateddiffuse":"coated_diffuse"}.get(kind,kind)}
    if kind in {"diffuse","coateddiffuse"}:
        value["reflectance"]=_parse_spectrum(params,"reflectance",{"type":"rgb","value":[.5]*3},True)
    if kind in {"dielectric","coateddiffuse"}:value["ior"]=_one(params,"eta",1.5)
    if kind!="diffuse":
        roughness=_number(_one(params,"roughness",0),"PBRT roughness",0,1)
        value["roughness"]=math.sqrt(roughness) if _one(params,"remaproughness",True) else roughness
    if kind=="conductor":
        if "eta" not in params or "k" not in params:raise ValueError("Imported PBRT conductors need explicit eta and k spectra; implicit metal catalogues are not transported.")
        value["eta"]=_parse_spectrum(params,"eta",None);value["k"]=_parse_spectrum(params,"k",None)
    return validate_material(value)


def _rotation_matrix(angle,axis):
    length=math.hypot(*axis)
    if length<1e-12:raise ValueError("PBRT rotation axis cannot be zero.")
    x,y,z=[v/length for v in axis]; c=math.cos(math.radians(angle));s=math.sin(math.radians(angle));t=1-c
    return [t*x*x+c,t*x*y+s*z,t*x*z-s*y,0,t*x*y-s*z,t*y*y+c,t*y*z+s*x,0,
            t*x*z+s*y,t*y*z-s*x,t*z*z+c,0,0,0,0,1]


def import_pbrt(text):
    """Import actual v4 tokens; any unknown feature fails before project mutation.

    Includes, texture filenames, media, procedural plugins, arbitrary output paths,
    object instancing and animated transforms deliberately have no execution path.
    """
    parser=_PBRTParser(text); scene=default_scene(); scene.update(objects=[],lights=[])
    scene["world"].update(color="#000000",strength=0); scene["frame_end"]=1
    settings=default_settings(); settings.update(spp=16,max_depth=5)
    camera={"position":[0.,0.,0.],"target":[0.,0.,1.],"up":[0.,1.,0.],"fov":90.,"lensradius":0.,"focaldistance":10.}
    state={"matrix":list(_IDENTITY_MATRIX),"material":{"type":"diffuse","reflectance":{"type":"rgb","value":[.5]*3}},"emission":None,"reverse":False}
    stack=[]; named={}; world=False; seen=set(); world_light=False; camera_reflection=False
    while parser.peek():
        command=parser.pop("word")
        if command=="WorldBegin":
            if world:raise ValueError("PBRT WorldBegin can occur only once.")
            required={"LookAt","Camera","Film","Sampler","Integrator","PixelFilter"}
            if not required.issubset(seen):
                raise ValueError("PBRT transport needs explicit LookAt, Camera, Film, Sampler, Integrator and PixelFilter declarations; implicit renderer defaults are not transported.")
            if not camera_reflection:
                raise ValueError("PBRT transport requires Scale -1 1 1 before LookAt to preserve the authored camera handedness.")
            world=True; state["matrix"]=list(_IDENTITY_MATRIX);continue
        if command in {"AttributeBegin","AttributeEnd"}:
            if not world:raise ValueError("Attribute scopes must be inside PBRT WorldBegin.")
            if command=="AttributeBegin":
                if len(stack)>=24:raise ValueError("PBRT attribute nesting exceeds 24 levels.")
                stack.append(copy.deepcopy(state))
            else:
                if not stack:raise ValueError("PBRT AttributeEnd has no matching begin.")
                state=stack.pop()
            continue
        if command=="ReverseOrientation":
            if not world:raise ValueError("PBRT orientation must be inside the world.")
            state["reverse"]=not state["reverse"];continue
        if command in {"Identity","Transform","ConcatTransform","Translate","Scale","Rotate"}:
            if not world:
                if command!="Scale" or camera_reflection or "LookAt" in seen or "Camera" in seen or parser.numbers(3)!=[-1.,1.,1.]:
                    raise ValueError("PBRT camera transforms support only Scale -1 1 1 followed by LookAt; arbitrary pre-world transforms are unsupported.")
                camera_reflection=True;continue
            if command=="Identity":state["matrix"]=list(_IDENTITY_MATRIX);continue
            if command in {"Transform","ConcatTransform"}:
                values=parser.numbers(16)
                # PBRT text matrices are column-major (the parser transposes its internal row-major Matrix4x4).
                matrix=values
                if any(abs(matrix[i])>1e-12 for i in (3,7,11)) or abs(matrix[15]-1)>1e-12:
                    raise ValueError("Only affine PBRT transforms are supported.")
            elif command=="Translate":
                matrix=list(_IDENTITY_MATRIX);matrix[12:15]=parser.numbers(3)
            elif command=="Scale":
                values=parser.numbers(3)
                if any(abs(v)<1e-6 or abs(v)>1000 for v in values):raise ValueError("PBRT scale is singular or excessive.")
                matrix=list(_IDENTITY_MATRIX);matrix[0],matrix[5],matrix[10]=values
            else:
                values=parser.numbers(4);matrix=_rotation_matrix(values[0],values[1:])
            state["matrix"]=matrix if command=="Transform" else matrix_product(state["matrix"],matrix)
            continue
        if command=="LookAt":
            if world or command in seen or "Camera" in seen:raise ValueError("PBRT needs one pre-world LookAt before Camera.")
            seen.add(command); values=parser.numbers(9)
            camera.update(position=values[:3],target=values[3:6],up=values[6:]);continue
        if command=="NamedMaterial":
            if not world:raise ValueError("Named material must be inside the world.")
            name=parser.pop("string")
            if name not in named:raise ValueError("PBRT named material is undefined.")
            state["material"]=copy.deepcopy(named[name]);continue
        if command not in {"ColorSpace","Camera","Film","Sampler","Integrator","PixelFilter","Material","MakeNamedMaterial","LightSource","AreaLightSource","Shape"}:
            raise ValueError("Unsupported PBRT-v4 command: "+command)
        kind=parser.pop("string");params=parser.params()
        if command=="ColorSpace":
            if kind!="srgb" or params:raise ValueError("PBRT transport currently supports linear sRGB numeric colors only.")
            continue
        if command in {"Camera","Film","Sampler","Integrator","PixelFilter"}:
            if world or command in seen:raise ValueError("Duplicate or misplaced PBRT "+command)
            seen.add(command)
            if command=="Camera":
                if kind!="perspective":raise ValueError("Only PBRT perspective/thin-lens cameras are supported.")
                _params_only(params,{"fov":"float","lensradius":"float","focaldistance":"float"},"PBRT Camera")
                camera.update(fov=_one(params,"fov",90),lensradius=_one(params,"lensradius",0),focaldistance=_one(params,"focaldistance",10))
            elif command=="Film":
                if kind!="rgb":raise ValueError("Only PBRT RGB film import is supported; spectral sensor formats are not interchangeable.")
                _params_only(params,{"xresolution":"integer","yresolution":"integer","filename":"string","savefp16":"bool"},"PBRT Film")
                if _one(params,"filename")!="render.exr":raise ValueError("PBRT output filename must be explicitly render.exr; external/arbitrary destinations are not accepted.")
                if _one(params,"savefp16") is not False:raise ValueError("PBRT film must explicitly set savefp16 false; half-float output is not silently promoted.")
                scene["width"]=_one(params,"xresolution",1280);scene["height"]=_one(params,"yresolution",720)
            elif command=="Sampler":
                if kind!="independent":raise ValueError("Only the PBRT independent sampler is transported without changing sampling semantics.")
                _params_only(params,{"pixelsamples":"integer","seed":"integer"},"PBRT Sampler")
                settings.update(spp=_one(params,"pixelsamples",16),seed=_one(params,"seed",0))
            elif command=="Integrator":
                if kind!="volpath":raise ValueError("Only the PBRT volpath integrator is transported.")
                _params_only(params,{"maxdepth":"integer"},"PBRT Integrator");settings["max_depth"]=_one(params,"maxdepth",5)
            else:
                if kind!="box" or params:raise ValueError("Only an unmodified box pixel filter is transported.")
            continue
        if not world:raise ValueError("PBRT scene content must follow WorldBegin.")
        if command in {"Material","MakeNamedMaterial"}:
            if command=="MakeNamedMaterial":
                name=kind
                if len(name)>80 or name in named:raise ValueError("PBRT named materials must have unique bounded names.")
                if "type" not in params or params["type"][0]!="string":raise ValueError("Named PBRT material requires a string type.")
                kind=_one(params,"type");del params["type"]
                named[name]=_parse_material(kind,params)
            else:state["material"]=_parse_material(kind,params)
        elif command=="AreaLightSource":
            if kind!="diffuse":raise ValueError("Only diffuse PBRT area emission is transported.")
            _params_only(params,{"L":("rgb","spectrum","float")},"PBRT AreaLightSource")
            state["emission"]=_parse_spectrum(params,"L",{"type":"uniform","value":1})
        elif command=="LightSource":
            if kind=="infinite":
                _params_only(params,{"L":("rgb","spectrum","float")},"PBRT infinite light")
                if world_light:raise ValueError("Only one constant PBRT environment is supported.")
                world_light=True;settings["world_spectrum"]=_parse_spectrum(params,"L",{"type":"uniform","value":1})
            elif kind in {"point","distant"}:
                field="I" if kind=="point" else "L"
                _params_only(params,{field:("rgb","spectrum","float"),"from":"point3",**({"to":"point3"} if kind=="distant" else {})},"PBRT "+kind)
                ident="pbrt_light_%d" % (len(scene["lights"])+1)
                source=transform_point(state["matrix"],_vec(params,"from",[0,0,0]))
                target=transform_point(state["matrix"],_vec(params,"to",[0,0,1]))
                scene["lights"].append({"id":ident,"name":ident,"type":"point" if kind=="point" else "sun","position":source,"target":target,
                                        "power":4*math.pi if kind=="point" else 1.,"color":"#ffffff","size":1.})
                settings["light_spectra"][ident]=_parse_spectrum(params,field,{"type":"uniform","value":1})
            else:raise ValueError("Unsupported PBRT light: "+kind)
        else:
            if kind!="trianglemesh":raise ValueError("PBRT import currently accepts explicit trianglemesh geometry only; convert procedural shapes with the source renderer first.")
            _params_only(params,{"P":"point3","indices":"integer","N":"normal","uv":("point2","float")},"PBRT trianglemesh")
            if "P" not in params or "indices" not in params:raise ValueError("PBRT trianglemesh requires positions and indices.")
            def rows(name,size):
                values=params.get(name,(None,[]))[1]
                if len(values)%size:raise ValueError("PBRT mesh coordinate count is invalid.")
                return [values[i:i+size] for i in range(0,len(values),size)]
            vertices=rows("P",3);triangles=rows("indices",3);mesh={"version":1,"vertices":vertices,"triangles":triangles}
            for param,key,indices,size in (("N","normals","normal_indices",3),("uv","uvs","uv_indices",2)):
                if param in params:
                    vectors=rows(param,size)
                    if len(vectors)!=len(vertices):raise ValueError("PBRT per-vertex attribute count differs from its positions.")
                    mesh[key]=vectors;mesh[indices]=copy.deepcopy(triangles)
            mesh=validate_mesh(mesh);mesh=_world_mesh(mesh,state["matrix"])
            if state["reverse"]:
                mesh["triangles"]=[list(reversed(row)) for row in mesh["triangles"]]
                for key in ("normal_indices","uv_indices"):
                    if mesh.get(key):mesh[key]=[list(reversed(row)) for row in mesh[key]]
                mesh["normals"]=[[-v for v in row] for row in mesh["normals"]]
            mesh=validate_mesh(mesh)
            ident="pbrt_object_%d" % (len(scene["objects"])+1);material=copy.deepcopy(MATERIAL_DEFAULTS)
            physical=copy.deepcopy(state["material"])
            if physical.get("reflectance",{}).get("type")=="rgb":material["color"]=_display_color(physical["reflectance"]["value"])
            if state["emission"]:physical["emission"]=copy.deepcopy(state["emission"])
            scene["objects"].append({"id":ident,"name":ident,"type":"mesh","position":[0,0,0],"rotation":[0,0,0],"scale":[1,1,1],"material":material,"mesh":mesh})
            settings["material_overrides"][ident]=physical
    if not world or stack:raise ValueError("PBRT world/attribute scopes are incomplete.")
    aspect=scene["width"]/scene["height"]
    fov=math.degrees(2*math.atan(math.tan(math.radians(camera["fov"])/2)/min(1.,aspect)))
    basis=camera_basis(camera["position"],camera["target"])
    raw_up=camera["up"]; along=sum(a*b for a,b in zip(raw_up,basis["backward"]))
    up=[a-along*b for a,b in zip(raw_up,basis["backward"])];length=math.hypot(*up)
    if length<1e-12:raise ValueError("PBRT camera up is parallel to its aim.")
    up=[v/length for v in up]
    roll=math.degrees(math.atan2(-sum(a*b for a,b in zip(up,basis["right"])),sum(a*b for a,b in zip(up,basis["up"]))))
    scene["camera"].update(position=camera["position"],target=camera["target"],fov=fov,roll=roll,orientation_mode="world_up",
                           dof_enabled=camera["lensradius"]>0,focus_distance=camera["focaldistance"])
    radius=_number(camera["lensradius"],"PBRT lens radius",0,1)
    if radius:scene["camera"]["f_stop"]=focal_length_mm(scene["camera"])/1000/(2*radius)
    scene=validate_scene(scene);settings=validate_settings(settings,scene);_validate_scene_support(scene)
    return scene,settings

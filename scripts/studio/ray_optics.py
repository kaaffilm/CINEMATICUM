"""Validated sequential lens prescriptions and an isolated, real Optiland worker.

This module is deliberately standard-library only. Distances/radii are mm,
field angles are degrees, wavelengths are micrometres. Results never mutate a
project: applying a proposed optimized prescription is a separate undoable edit.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

from imaging import _hash_file, _json_bytes, _owned, _read_json

RUNTIME_REQUIREMENTS = {"optiland": "0.6.3", "numpy": "2.3.5", "scipy": "1.18.1"}
RUNTIME_ROOT = Path.home() / ("Library/Application Support/CINEMATICUM/Optics/py313-v1" if sys.platform == "darwin"
                            else ".local/share/CINEMATICUM/Optics/py312-v1")
MAX_SURFACES = 32
MAX_FIELDS = 9
MAX_WAVELENGTHS = 9
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
ARTIFACT_NAMES = frozenset({"prescription.json", "optiland.json", "analysis.json", "rays.csv",
                            "mtf.csv", "psf.npz", "layout.svg", "spot.svg", "psf.png", "mtf.svg", "receipt.json"})
_IDENT = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def _object(value, keys, name):
    if not isinstance(value, dict) or set(value) - set(keys):
        raise ValueError(f"{name} must be an object with only {', '.join(keys)}.")
    return value


def _number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{name} must be {'an integer ' if integer else ''}between {low} and {high}.")
    return int(value) if integer else float(value)


def _text(value, name, length=100):
    if not isinstance(value, str) or not value.strip() or len(value) > length or any(ord(x) < 32 for x in value):
        raise ValueError(f"{name} must be printable text of at most {length} characters.")
    return value.strip()


def _boolean(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false.")
    return value


def _material(value):
    value = _object(value, ("type", "catalog", "name", "index"), "Material")
    kind = value.get("type")
    if kind == "air" and set(value) == {"type"}:
        return {"type": "air"}
    if kind == "constant" and set(value) == {"type", "index"}:
        return {"type": "constant", "index": _number(value["index"], "Constant refractive index", 1, 4)}
    if kind == "catalog" and set(value) == {"type", "catalog", "name"}:
        catalog = _text(value["catalog"], "Glass catalogue", 50)
        name = _text(value["name"], "Glass name", 100)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", catalog) or any(c in name for c in "/\\"):
            raise ValueError("Material must name a built-in manufacturer catalogue and glass, not a path.")
        return {"type": "catalog", "catalog": catalog, "name": name}
    raise ValueError("Material must be air, a constant index, or an exact built-in catalogue/name pair.")


def default_prescription():
    return {"version": 1, "name": "50 mm crown singlet", "units": "mm", "object_distance": None,
            "aperture": {"type": "EPD", "value": 10.0},
            "fields": [{"x": 0., "y": y, "weight": 1.} for y in (0., 2., 4.)],
            "wavelengths": [{"value": w, "weight": 1., "primary": i == 1}
                            for i, w in enumerate((.4861327, .5875618, .6562725))],
            "surfaces": [
                {"id": "s1", "radius": 50., "thickness": 5., "conic": 0., "coefficients": [],
                 "material": {"type": "catalog", "catalog": "schott", "name": "N-BK7"}, "stop": True},
                {"id": "s2", "radius": -50., "thickness": 47.5362237858, "conic": 0., "coefficients": [],
                 "material": {"type": "air"}, "stop": False}]}


def validate_optical_prescription(value):
    value = _object(value, ("version", "name", "units", "object_distance", "aperture", "fields", "wavelengths", "surfaces"), "Optical prescription")
    if value.get("version") != 1 or isinstance(value.get("version"), bool) or value.get("units", "mm") != "mm":
        raise ValueError("Optical prescription version 1 uses millimetres.")
    distance = value.get("object_distance")
    if distance is not None:
        distance = _number(distance, "Object distance", .01, 1e9)
    aperture = _object(value.get("aperture"), ("type", "value"), "Aperture")
    if aperture.get("type") != "EPD":
        raise ValueError("This sequential workflow uses a physical entrance-pupil diameter (EPD).")
    aperture = {"type": "EPD", "value": _number(aperture.get("value"), "Entrance-pupil diameter", .01, 1000)}
    fields = value.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
        raise ValueError(f"Provide 1–{MAX_FIELDS} field angles.")
    normalized_fields = []
    for item in fields:
        item = _object(item, ("x", "y", "weight"), "Field")
        x = _number(item.get("x", 0), "Field x angle", -30, 30)
        y = _number(item.get("y", 0), "Field y angle", -30, 30)
        if math.hypot(x, y) > 30 or any((x, y) == (f["x"], f["y"]) for f in normalized_fields):
            raise ValueError("Field directions must be distinct and within a 30 degree radial angle.")
        normalized_fields.append({"x": x, "y": y, "weight": _number(item.get("weight", 1), "Field weight", .001, 100)})
    wavelengths = value.get("wavelengths")
    if not isinstance(wavelengths, list) or not 1 <= len(wavelengths) <= MAX_WAVELENGTHS:
        raise ValueError(f"Provide 1–{MAX_WAVELENGTHS} wavelengths.")
    normalized_waves = []
    for item in wavelengths:
        item = _object(item, ("value", "weight", "primary"), "Wavelength")
        wave = _number(item.get("value"), "Wavelength (µm)", .2, 2.5)
        if any(wave == w["value"] for w in normalized_waves):
            raise ValueError("Wavelengths must be distinct.")
        normalized_waves.append({"value": wave, "weight": _number(item.get("weight", 1), "Wavelength weight", .001, 100),
                                 "primary": _boolean(item.get("primary", False), "Primary wavelength")})
    if sum(w["primary"] for w in normalized_waves) != 1:
        raise ValueError("Choose exactly one primary wavelength.")
    surfaces = value.get("surfaces")
    if not isinstance(surfaces, list) or not 2 <= len(surfaces) <= MAX_SURFACES:
        raise ValueError(f"Provide 2–{MAX_SURFACES} refracting surfaces, excluding object and image planes.")
    normalized_surfaces = []
    for item in surfaces:
        item = _object(item, ("id", "radius", "thickness", "conic", "coefficients", "material", "stop"), "Surface")
        ident = item.get("id")
        if not isinstance(ident, str) or not _IDENT.fullmatch(ident) or any(s["id"] == ident for s in normalized_surfaces):
            raise ValueError("Each surface needs a distinct alphanumeric identifier.")
        radius = item.get("radius")
        if radius is not None:
            radius = _number(radius, "Surface radius", -1e6, 1e6)
            if abs(radius) < .1:
                raise ValueError("A finite radius must have magnitude at least 0.1 mm; null denotes a plane.")
        coeff = item.get("coefficients", [])
        if not isinstance(coeff, list) or len(coeff) > 8:
            raise ValueError("Use up to eight even-asphere coefficients (r^4 through r^18).")
        normalized_surfaces.append({"id": ident, "radius": radius,
                                   "thickness": _number(item.get("thickness"), "Following thickness", 0, 10000),
                                   "conic": _number(item.get("conic", 0), "Conic constant", -20, 20),
                                   "coefficients": [_number(c, "Even-asphere coefficient", -1, 1) for c in coeff],
                                   "material": _material(item.get("material")), "stop": _boolean(item.get("stop", False), "Aperture stop")})
    if sum(s["stop"] for s in normalized_surfaces) != 1:
        raise ValueError("Choose exactly one aperture-stop surface.")
    if normalized_surfaces[-1]["material"] != {"type": "air"} or normalized_surfaces[-1]["thickness"] <= 0:
        raise ValueError("The final refracting surface must be followed by a positive air gap to the image plane.")
    return {"version": 1, "name": _text(value.get("name", "Untitled lens"), "Lens name"), "units": "mm",
            "object_distance": distance, "aperture": aperture, "fields": normalized_fields,
            "wavelengths": normalized_waves, "surfaces": normalized_surfaces}


def validate_ray_optics_recipe(value):
    value = _object(value, ("version", "operation", "prescription", "analysis", "optimization"), "Ray-optics recipe")
    if value.get("version") != 1 or isinstance(value.get("version"), bool) or value.get("operation") not in ("analyze", "optimize"):
        raise ValueError("Choose a version 1 analyze or optimize operation.")
    prescription = validate_optical_prescription(value.get("prescription"))
    analysis = _object(value.get("analysis", {}), ("rings", "fan_samples", "pupil_samples", "fft_grid"), "Analysis settings")
    analysis = {"rings": _number(analysis.get("rings", 4), "Hexapolar pupil rings", 2, 12, True),
                "fan_samples": _number(analysis.get("fan_samples", 33), "Ray-fan samples", 9, 129, True),
                "pupil_samples": _number(analysis.get("pupil_samples", 32), "FFT pupil samples per side", 16, 128, True),
                "fft_grid": _number(analysis.get("fft_grid", 128), "FFT grid size", 64, 512, True)}
    if analysis["fft_grid"] & (analysis["fft_grid"] - 1) or analysis["fft_grid"] < analysis["pupil_samples"] * 2:
        raise ValueError("FFT grid must be a power of two and at least twice the pupil sampling.")
    normalized = {"version": 1, "operation": value["operation"], "prescription": prescription, "analysis": analysis}
    if value["operation"] == "analyze":
        if "optimization" in value:
            raise ValueError("Optimization settings require an optimize operation.")
        return normalized
    opt = _object(value.get("optimization"), ("variables", "max_evaluations", "target_efl", "efl_weight"), "Optimization settings")
    variables = opt.get("variables")
    if not isinstance(variables, list) or not 1 <= len(variables) <= 8:
        raise ValueError("Choose 1–8 bounded surface variables.")
    by_id = {s["id"]: s for s in prescription["surfaces"]}
    bounds = {"radius": (-1e6, 1e6), "thickness": (.001, 10000), "conic": (-20, 20)}
    normalized_variables = []
    seen = set()
    for item in variables:
        item = _object(item, ("surface", "parameter", "min", "max"), "Optimization variable")
        surface, parameter = item.get("surface"), item.get("parameter")
        if not isinstance(surface, str) or surface not in by_id or not isinstance(parameter, str) or parameter not in bounds:
            raise ValueError("Optimization variables must name a surface radius, thickness or conic.")
        if (surface, parameter) in seen or by_id[surface][parameter] is None:
            raise ValueError("Optimization variables must be distinct finite surface parameters.")
        seen.add((surface, parameter))
        lower = _number(item.get("min"), "Variable lower bound", *bounds[parameter])
        upper = _number(item.get("max"), "Variable upper bound", *bounds[parameter])
        if not lower < upper or not lower <= by_id[surface][parameter] <= upper:
            raise ValueError("The initial value must lie within distinct, increasing variable bounds.")
        if parameter == "radius" and (lower < .1 and upper > -.1):
            raise ValueError("Radius optimization bounds must stay away from zero and preserve curvature sign.")
        normalized_variables.append({"surface": surface, "parameter": parameter, "min": lower, "max": upper})
    target = opt.get("target_efl")
    if target is not None:
        target = _number(target, "Target effective focal length", .1, 100000)
    normalized["optimization"] = {"variables": normalized_variables,
                                  "max_evaluations": _number(opt.get("max_evaluations", 60), "Optimization evaluation budget", 5, 200, True),
                                  "target_efl": target, "efl_weight": _number(opt.get("efl_weight", 1), "Focal-length merit weight", .001, 100)}
    return normalized


def find_ray_optics_python(python=None):
    candidate = str(python or os.environ.get("CINEMATICUM_OPTICS_PYTHON") or (RUNTIME_ROOT / "bin/python"))
    path = Path(candidate)
    return str(path) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else None


def _command(python):
    executable = find_ray_optics_python(python)
    if not executable:
        raise ValueError("The isolated Optiland runtime is not installed. Set CINEMATICUM_OPTICS_PYTHON or install the managed Optics runtime.")
    return [executable, "-I", "-B", str(Path(__file__).with_name("ray_optics_worker.py"))]


def _environment(scratch):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "MPL", "NUMBA", "OPTILAND"))}
    # Scientific plots use the exact bundled fonts. Host font discovery can
    # invoke macOS system_profiler and exceed bounded cold-worker startup.
    env.update({"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "MPLBACKEND": "Agg",
                "MPL_IGNORE_SYSTEM_FONTS": "1",
                "MPLCONFIGDIR": str(Path(scratch) / "mpl"), "NUMBA_CACHE_DIR": str(Path(scratch) / "numba"),
                "XDG_CACHE_HOME": str(Path(scratch) / "cache")})
    return env


def _short_request(request, python=None):
    with tempfile.TemporaryDirectory(prefix="cinematicum-optics-probe-") as directory:
        result = subprocess.run(_command(python), input=_json_bytes(request), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=_environment(directory), timeout=35, check=False)
    if len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError("Optiland returned an oversized diagnostic response.")
    try:
        response = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Optiland did not return a valid diagnostic response.") from exc
    if result.returncode or not isinstance(response, dict) or response.get("error"):
        raise ValueError(str(response.get("error", "Optiland runtime failed."))[:2000] if isinstance(response, dict) else "Optiland runtime failed.")
    return response


def ray_optics_capabilities(python=None):
    try:
        return _short_request({"command": "doctor"}, python)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "operations": [], "reason": str(exc), "required": RUNTIME_REQUIREMENTS,
                "default_prescription": default_prescription()}


def ray_optics_catalog(query="", limit=100, python=None):
    if not isinstance(query, str) or len(query) > 100 or any(ord(x) < 32 for x in query):
        raise ValueError("Catalogue query must be at most 100 printable characters.")
    limit = _number(limit, "Catalogue result limit", 1, 500, True)
    return _short_request({"command": "catalog", "query": query, "limit": limit}, python)


def _stop(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def run_ray_optics(project, project_dir, recipe, output_dir, progress=None, cancel_event=None, python=None):
    recipe = validate_ray_optics_recipe(recipe)
    if not isinstance(project, dict):
        raise ValueError("An optical job needs a project snapshot.")
    project_hash = hashlib.sha256(_json_bytes(project)).hexdigest()
    recipe_hash = hashlib.sha256(_json_bytes(recipe)).hexdigest()
    root, output = Path(project_dir).absolute(), Path(output_dir).absolute()
    try:
        relative = output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Optical output must be inside the owning project.") from exc
    if len(relative.parts) != 3 or relative.parts[:2] != ("optics", "outputs") or not _IDENT.fullmatch(relative.name):
        raise ValueError("Optical output must use optics/outputs/<owned-job-id>.")
    parent = _owned(root, "optics/outputs", is_dir=True, create=True)
    if output.exists() or output.is_symlink():
        raise ValueError("An optical result already exists at this owned output identifier.")
    event = cancel_event or threading.Event()
    if event.is_set():
        raise InterruptedError("Optical job cancelled.")
    command = _command(python)
    # Name transient work by its owning job so cancellation/recovery can
    # distinguish it from another concurrently running optical calculation.
    with tempfile.TemporaryDirectory(prefix=f".{relative.name}-building-", dir=str(parent)) as temporary:
        scratch = Path(temporary)
        request = {"command": "run", "recipe": recipe, "recipe_sha256": recipe_hash,
                   "project_sha256": project_hash, "output_id": relative.name, "scratch": str(scratch)}
        start, process = time.monotonic(), None
        try:
            with (scratch / "worker.stdout").open("wb") as stdout, (scratch / "worker.stderr").open("wb") as stderr:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                           env=_environment(scratch), start_new_session=True)
                process.stdin.write(_json_bytes(request))
                process.stdin.close()
                while process.poll() is None:
                    if event.wait(.1):
                        raise InterruptedError("Optical job cancelled.")
                    if time.monotonic() - start > 300:
                        raise TimeoutError("The optical job exceeded its 300-second bounded CPU runtime.")
                    for log in (scratch / "worker.stdout", scratch / "worker.stderr"):
                        if log.stat().st_size > 2 * 1024 * 1024:
                            raise ValueError("Optiland emitted excessive diagnostic output.")
                    if progress and (scratch / "progress.json").is_file():
                        try:
                            p = _read_json(scratch / "progress.json", 4096)
                            amount = _number(p.get("fraction"), "Optical progress", 0, 1)
                            progress(min(.98, amount))
                        except (OSError, ValueError):
                            pass
        finally:
            if process:
                _stop(process)
        response = _read_json(scratch / "worker.stdout", 2 * 1024 * 1024)
        if process.returncode or not isinstance(response, dict) or response.get("error"):
            raise ValueError(str(response.get("error", "Optiland analysis failed."))[:2000] if isinstance(response, dict) else "Optiland analysis failed.")
        generated = _owned(scratch, "result", is_dir=True)
        if {p.name for p in generated.iterdir()} != ARTIFACT_NAMES:
            raise ValueError("Optiland produced an incomplete or unexpected artifact inventory.")
        receipt = _read_json(_owned(generated, "receipt.json"), 2 * 1024 * 1024)
        if (receipt.get("recipe_sha256") != recipe_hash or receipt.get("project_sha256") != project_hash or
                receipt.get("output_id") != relative.name or receipt.get("recipe") != recipe or
                receipt.get("runtime", {}).get("packages", {}).get("optiland") != RUNTIME_REQUIREMENTS["optiland"]):
            raise ValueError("Optical result provenance does not bind to this job, prescription and runtime.")
        artifacts = {}
        if set(receipt.get("artifacts", {})) != ARTIFACT_NAMES - {"receipt.json"}:
            raise ValueError("Optical receipt has an invalid artifact inventory.")
        for name in sorted(ARTIFACT_NAMES):
            digest, size = _hash_file(_owned(generated, name), MAX_ARTIFACT_BYTES)
            if name != "receipt.json" and receipt["artifacts"][name] != {"sha256": digest, "size": size}:
                raise ValueError("An optical artifact changed after the worker measured it.")
            artifacts[name] = {"sha256": digest, "size": size, "path": str(relative / name)}
        prescription = validate_optical_prescription(_read_json(generated / "prescription.json"))
        analysis = _read_json(generated / "analysis.json", 16 * 1024 * 1024)
        if event.is_set():
            raise InterruptedError("Optical job cancelled before publication.")
        if output.exists() or output.is_symlink():
            raise ValueError("The optical destination appeared while the worker was running.")
        os.rename(generated, output)
    return {"output_id": relative.name, "operation": recipe["operation"], "prescription": prescription,
            "analysis": analysis, "artifacts": artifacts, "receipt": receipt,
            "provenance": {"kind": "optiland-sequential-optics", "recipe_sha256": recipe_hash,
                           "project_sha256": project_hash, "runtime": receipt["runtime"]}}

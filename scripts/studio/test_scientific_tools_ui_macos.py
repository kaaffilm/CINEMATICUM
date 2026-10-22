#!/usr/bin/env python3
"""Actual Optiland/Mitsuba Studio controls in separate 18-second WK phases.

Each authoring operation creates its own new synthetic project workspace. It edits the
shipped tool, saves one undoable document, undoes/redoes it, reopens the exact
project, runs the real installed worker and clicks an actual WKDownload. The
download is inspected independently against optical/radiometric mathematics.
Optics authoring and analysis are distinct foreground operations: optics-edit
persists a successful, source-bound fixture; optics-render opens that same
project in a fresh backend and completes one actual analysis. There is no
paused/resumed worker and neither operation has a wider execution deadline.
The evidence download directory is explicit; this does not certify NSSavePanel,
physical input, the installed application launcher or production-scale quality.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from deep_compositing import find_imaging_python
from install_macos import RUNTIME_FILES
import physical_rendering
import ray_optics
from scene import default_scene, validate_scene
from server import Server, Store
from test_editing_ui_macos import read_helper_result

HERE = Path(__file__).resolve().parent
STUDIO_SOURCE = Path(sys.modules[Store.__module__].__file__).resolve().parent
KIND = "cinematicum-native-scientific-tools-v1"

OPTICAL_INSPECTION = r'''
import json,sys,numpy as np
with np.load(sys.argv[1],allow_pickle=False) as value:
    images=value['psf_energy_normalized']; output=[]
    for image in images:
        otf=np.abs(np.fft.fftshift(np.fft.fft2(image))); c=otf.shape[0]//2
        output.append({'sum':float(image.sum()),'min':float(image.min()),
          'finite':bool(np.isfinite(image).all()),'shape':list(image.shape),
          'tangential':(otf[c:,c]/otf[c,c]).tolist(),
          'sagittal':(otf[c,c:]/otf[c,c]).tolist()})
print(json.dumps(output))
'''

RADIOMETRIC_INSPECTION = r'''
import json,sys,numpy as np,OpenEXR
with OpenEXR.File(sys.argv[1],separate_channels=True) as image:
    part=image.parts[0]
    channels={name:part.channels[name].pixels for name in ('R','G','B')}
    pixels=np.stack(list(channels.values()),axis=-1)
    print(json.dumps({'parts':len(image.parts),'channels':sorted(part.channels),
      'types':{name:str(value.dtype) for name,value in channels.items()},
      'shape':list(pixels.shape),'finite':bool(np.isfinite(pixels).all()),
      'mean':pixels.mean(axis=(0,1),dtype=np.float64).tolist(),
      'min':float(pixels.min()),'max':float(pixels.max())}))
'''


def identity(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Scientific acceptance requires a bounded regular file")
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def source_inventory():
    names = set(RUNTIME_FILES) | {
        "install_macos.py", "test_scientific_tools_ui_macos.py",
        "test_editing_ui_macos.py", "macos/ScientificToolsSmoke.js", "macos/SmokeTest.swift",
    }
    for path in (STUDIO_SOURCE / "web").rglob("*"):
        if path.is_symlink():
            raise ValueError("Scientific acceptance refuses a symlink in shipped web source")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.name != ".DS_Store":
            names.add(path.relative_to(STUDIO_SOURCE).as_posix())
    return {name: identity(STUDIO_SOURCE / name) for name in sorted(names)}


def _json_digest(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode()).hexdigest()


def _optical_checks(directory, downloaded, receipt, checks, budget, output):
    analysis = json.loads((directory / "analysis.json").read_text())
    model = receipt["recipe"]["prescription"]
    first, second = model["surfaces"]
    material = analysis["materials"][0]
    primary = next(row["value"] for row in model["wavelengths"] if row["primary"])
    index = next(row["n"] for row in material["refractive_indices"] if row["wavelength_um"] == primary)
    power = (index - 1) * (1 / first["radius"] - 1 / second["radius"] +
                          (index - 1) * first["thickness"] / (index * first["radius"] * second["radius"]))
    expected_efl = 1 / power
    measured = analysis["paraxial"]
    checks["edited_lens_matches_independent_thick_lens_equation"] = abs(measured["effective_focal_length_mm"] - expected_efl) < 1e-9
    checks["edited_aperture_matches_independent_f_number"] = abs(measured["f_number"] - expected_efl / 8) < 1e-9
    checks["exact_packaged_crown_glass_dispersion"] = abs(index - 1.51680003) < 1e-7 and first["material"] == {"type": "catalog", "catalog": "schott", "name": "N-BK7"}
    with (directory / "rays.csv").open() as stream:
        rays = list(csv.DictReader(stream))
    marginal = [row for row in rays if row["field_index"] == "0" and float(row["wavelength_um"]) == primary]
    at_first = [abs(float(row["y_mm"])) for row in marginal if row["surface_index"] == "1"]
    at_image = [abs(float(row["y_mm"])) for row in marginal if row["surface_index"] == "3"]
    checks["actual_refracted_rays_converge_at_authored_plane"] = bool(at_first and at_image) and max(at_first) > 3.9 and max(at_image) < max(at_first) / 10
    checks["all_authored_wavelengths_have_complete_actual_ray_results"] = (len(analysis["spots"]) == 3 and len(analysis["fans"]) == 6 and
        len(rays) == sum(row["ray_count"] for row in analysis["spots"]) * (len(model["surfaces"]) + 1) and len(rays) > 50)
    inspected = subprocess.run([ray_optics.find_ray_optics_python(), "-I", "-B", "-c", OPTICAL_INSPECTION,
                                str(downloaded)], capture_output=True, text=True, check=True,
                               timeout=budget(1.5, .7), env=ray_optics._environment(output / "inspection-cache"))
    arrays = json.loads(inspected.stdout)
    checks["downloaded_psf_has_finite_nonnegative_normalized_energy"] = len(arrays) == 1 and all(row["finite"] and row["shape"] == [64, 64] and row["min"] >= 0 and abs(row["sum"] - 1) < 1e-12 for row in arrays)
    errors = []
    for array, measured_mtf in zip(arrays, analysis["diffraction"]):
        for axis in ("tangential", "sagittal"):
            expected, actual = array[axis], measured_mtf[axis + "_mtf"]
            if len(expected) != len(actual):
                errors.append(float("inf"))
            else:
                errors.extend(abs(a - b) for a, b in zip(expected, actual))
    checks["actual_mtf_matches_independent_fft_of_downloaded_psf"] = bool(errors) and max(errors) < 1e-10
    checks["optical_worker_receipt_binds_actual_current_worker"] = receipt["runtime"]["worker_sha256"] == identity(STUDIO_SOURCE / "ray_optics_worker.py")["sha256"]
    return {"expected_efl_mm": expected_efl, "measured_efl_mm": measured["effective_focal_length_mm"],
            "primary_refractive_index": index, "ray_rows": len(rays), "max_mtf_error": max(errors),
            "psf_energy_sums": [row["sum"] for row in arrays]}


def _physical_checks(directory, downloaded, receipt, ui, saved, checks, budget):
    python = find_imaging_python()
    if not python:
        raise RuntimeError("The independent actual OpenEXR reader runtime is required")
    inspected = subprocess.run([python, "-I", "-B", "-c", RADIOMETRIC_INSPECTION, str(downloaded)],
                               capture_output=True, text=True, check=True, timeout=budget(1.5, .7))
    data = json.loads(inspected.stdout)
    checks["download_is_actual_finite_float32_rgb_exr"] = data["parts"] == 1 and data["channels"] == ["B", "G", "R"] and data["shape"] == [32, 32, 3] and set(data["types"].values()) == {"float32"} and data["finite"]
    expected = [.15, .35, .65]
    checks["rendered_radiance_matches_authored_diffuse_reflectance"] = all(abs(a - b) < .008 for a, b in zip(data["mean"], expected))
    checks["independent_pixels_match_worker_reported_mean"] = all(abs(a - b) < 1e-5 for a, b in zip(data["mean"], receipt["metrics"]["mean"]))
    srgb = [255 * (12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055) for value in expected]
    checks["native_decoded_preview_matches_expected_srgb_radiance"] = len(ui.get("preview_rgb_mean", [])) == 3 and all(abs(a - b) < 3 for a, b in zip(ui["preview_rgb_mean"], srgb))
    checks["physical_receipt_binds_authored_scene_and_current_worker"] = receipt["scene_sha256"] == _json_digest(saved["settings"]["scene"]) and receipt["source_sha256"] == {name: identity(STUDIO_SOURCE / name)["sha256"] for name in ("physical_rendering.py", "physical_rendering_worker.py")}
    asset = next((row for row in saved["assets"] if row["id"] == ui.get("asset_id")), None)
    checks["real_preview_admitted_with_exact_bytes_and_srgb_identity"] = bool(asset) and asset["sha256"] == identity(directory / "preview.png")["sha256"] and asset["provenance"]["display_encoding"] == "sRGB"
    return {"expected_linear_rgb": expected, "decoded_exr": data, "expected_srgb": srgb, "runtime": receipt["engine"]}


def _verify_render(store, project, ui, operation, output, downloads, origin, screenshot, result, checks, budget, transport):
    with store.lock:
        jobs = copy.deepcopy([row for row in store.jobs.values() if row["project_id"] == project["id"]])
    tool = "ray-optics" if operation == "optics-render" else "physical-rendering"
    jobs = [row for row in jobs if row["kind"] == tool]
    checks["exactly_one_actual_completed_worker_job"] = len(jobs) == 1 and jobs[0]["state"] == "completed" and jobs[0]["id"] == ui.get("output_id")
    if not checks["exactly_one_actual_completed_worker_job"]:
        raise RuntimeError("The scientific phase did not own exactly one actual completed job")
    job = jobs[0]
    directory = store.project_dir(project["id"]) / ("optics" if operation == "optics-render" else "physical") / "outputs" / job["id"]
    saved = store.get(project["id"])
    receipt_name = "receipt.json" if operation == "optics-render" else "provenance.json"
    receipt = json.loads((directory / receipt_name).read_text())
    result["receipt_identity"] = identity(directory / receipt_name)
    field = "ray_optics" if operation == "optics-render" else "physical_rendering"
    frozen_document = receipt["recipe"]["prescription"] if operation == "optics-render" else receipt["settings"]
    checks["executed_document_exactly_matches_saved_reopened_edit"] = saved.get(field) == frozen_document
    artifacts = (receipt["artifacts"] if operation == "optics-render" else {row["filename"]: {"sha256": row["sha256"], "size": row["bytes"]} for row in receipt["artifacts"]})
    checks["all_published_artifact_bytes_match_actual_worker_receipt"] = set(path.name for path in directory.iterdir()) == set(artifacts) | {receipt_name} and all(identity(directory / name) == value for name, value in artifacts.items())
    filename = "psf.npz" if operation == "optics-render" else "render.exr"
    native_downloads = ui.get("downloads", [])
    checks["one_actual_completed_download"] = len(native_downloads) == 1 and native_downloads[0].get("state") == "completed"
    if not checks["one_actual_completed_download"]:
        raise RuntimeError("The actual scientific artifact download did not complete")
    path = Path(native_downloads[0].get("path", "")).absolute()
    native_name = bool(re.fullmatch(r"ENGINE_TEST_[A-Fa-f0-9-]{36}_" + re.escape(filename), path.name)) and native_downloads[0].get("suggested_filename") == filename
    correct_name = native_name if transport == "WKWebView" else path.name == filename
    checks["download_uses_exact_owned_evidence_destination"] = path.parent == downloads and correct_name and not path.is_symlink()
    checks["download_exactly_matches_worker_bytes_and_clicked_url"] = checks["download_uses_exact_owned_evidence_destination"] and identity(path) == identity(directory / filename) and native_downloads[0].get("url") == origin + ui.get("download_url", "")
    # Inspect the downloaded bytes, not an in-memory worker answer. The
    # downloaded file is independently equal to the owned worker artifact.
    if not checks["download_exactly_matches_worker_bytes_and_clicked_url"]:
        raise RuntimeError("The real download differs from its owned artifact")
    if operation == "optics-render":
        result["independent_measurements"] = _optical_checks(directory, path, receipt, checks, budget, output)
    else:
        result["independent_measurements"] = _physical_checks(directory, path, receipt, ui, saved, checks, budget)
    checks["actual_browser_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    result["executed_receipt"] = receipt


def _optics_fixture(path, sources, transport):
    if path is None:
        raise ValueError("Optical analysis requires its explicitly completed authored fixture")
    root = Path(path).absolute()
    if any(item.is_symlink() for item in (root, *root.parents)):
        raise ValueError("An optical fixture must not traverse symlinks")
    fence_path = root / "optics-edit-passed.json"
    identity(fence_path)
    fence = json.loads(fence_path.read_text())
    if (fence.get("kind") != KIND or fence.get("phase") != "optics-edit" or
            fence.get("source_inventory") != sources or fence.get("transport") != transport):
        raise ValueError("Optical analysis requires the exact source-bound successful authoring phase")
    for key in ("project", "sentinel"):
        record = fence[key]
        if not re.fullmatch(r"[a-f0-9]{32}", record.get("id", "")):
            raise ValueError("The owned optical fixture project identity is malformed")
        path = root / "workspace/projects" / record["id"] / "project.json"
        if any(item.is_symlink() for item in (path, *path.parents)):
            raise ValueError("The owned optical project must not traverse a symlink")
        if identity(path) != record["identity"]:
            raise ValueError("The authored optical fixture changed after its completed edit phase")
    if (root / "workspace/jobs").is_symlink():
        raise ValueError("The owned optical job directory must not be a symlink")
    for path in (root / "workspace/jobs").glob("*.json"):
        identity(path)
        job = json.loads(path.read_text())
        if job.get("state") in {"queued", "running"} or job.get("kind") == "ray-optics":
            raise ValueError("This fixture has prior unfinished work or an earlier optical analysis; preserve it and prepare a new fixture")
    return root, fence


def run(binary, output, operation, expected_sources, *, transport="WKWebView", fixture_workspace=None):
    began = time.monotonic()
    deadline = began + 18
    output = Path(output).absolute()
    if any(path.is_symlink() for path in (output, *output.parents)) or output.exists():
        raise ValueError("Choose a new evidence directory without symlink components; existing evidence is preserved")
    output.mkdir(parents=True)
    downloads = output / "native_downloads"
    downloads.mkdir()
    result = {"kind": KIND, "operation": operation, "browser": transport, "passed": False,
              "native_certified": transport == "WKWebView" and sys.platform == "darwin",
              "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT", "checks": {},
              "scope": "Shipped scientific Studio controls, explicit save/undo/redo/project reopen, real owned worker and byte-bound download. WKDownload uses an explicit evidence destination; physical input, NSSavePanel, installed launcher, production-scale performance and other physical transport modes are not certified."}
    if transport != "WKWebView":
        result["scope"] += " This is local Chromium transport validation only; no native acceptance is claimed."
    checks = result["checks"]
    store = server = thread = project = sentinel = None
    workspace_owner = output

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The scientific acceptance exhausted its 18-second foreground phase")
        return min(maximum, remaining)

    try:
        if operation not in {"optics-edit", "optics-render", "physical"}:
            raise ValueError("Choose an implemented scientific phase")
        before = source_inventory()
        result["source_before"] = before
        if expected_sources != before:
            raise ValueError("The scientific runtime/web/helper source differs from the exact frozen inventory")
        checks["source_matches_explicit_frozen_inventory"] = True
        result["helper_identity"] = identity(binary)
        if operation == "optics-render":
            workspace_owner, fence = _optics_fixture(fixture_workspace, before, transport)
            result["authored_fixture_fence_identity"] = identity(workspace_owner / "optics-edit-passed.json")
            store = Store(workspace_owner / "workspace")
            sentinel = store.get(fence["sentinel"]["id"])
            project = store.get(fence["project"]["id"])
            checks["exact_successful_authored_fixture_reopened_in_new_backend"] = True
        else:
            store = Store(output / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST Scientific sentinel", "width": 32, "height": 32, "fps": 12})
            project = store.new_project({"name": "ENGINE TEST Native " + operation, "width": 32, "height": 32, "fps": 12})
        if operation == "physical":
            scene = default_scene(32, 32)
            scene["camera"].update(position=[0, 0, 4], target=[0, 0, 0], fov=35)
            scene["lights"] = []
            scene["objects"] = [{"id": "surface", "name": "ENGINE TEST Surface", "type": "plane",
                                  "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [5, 5, 1]}]
            project["settings"]["scene"] = validate_scene(scene)
            project = store.save(project["id"], project)
        fixture = {"operation": operation, "project_id": project["id"], "project_name": project["name"],
                   "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"]}
        (output / "ENGINE_TEST_initial_project.json").write_text(json.dumps(project, indent=2))
        script = output / "ScientificToolsSmoke.js"
        script.write_text((HERE / "macos/ScientificToolsSmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps(fixture)))
        result["executed_javascript_identity"] = identity(script)
        server = Server(0, store)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        screenshot = output / "ENGINE_TEST_scientific_native.png"
        helper_timeout = budget(14.8, 2.0)
        completed = subprocess.run([str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot),
                                    "--script", str(script), "--download-dir", str(downloads),
                                    "--timeout", str(round(helper_timeout, 2))], capture_output=True, text=True,
                                   timeout=budget(helper_timeout + .3, 1.5))
        ui = read_helper_result(completed)
        (output / "ENGINE_TEST_browser_result.json").write_text(json.dumps(ui, indent=2))
        result.update(ui=ui, helper_exit_code=completed.returncode)
        if completed.stderr:
            result["helper_stderr_tail"] = completed.stderr[-1600:]
        checks["actual_shipped_controls_passed"] = completed.returncode == 0 and ui.get("passed") is True
        checks["no_browser_or_download_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
        expected_steps = ["select_exact_owned_fixture_project"]
        if operation == "optics-edit":
            expected_steps += ["authored_and_saved_actual_optical_prescription", "one_saved_edit_undo_redo_and_exact_project_reopen", "reopened_project_retains_exact_optical_document"]
        elif operation == "optics-render":
            expected_steps += ["saved_optical_document_survives_backend_restart", "reopened_numeric_controls_match_saved_prescription", "actual_optiland_worker_complete_numerics_images_and_history", "clicked_real_scientific_artifact_download"]
        else:
            expected_steps += ["authored_and_saved_actual_physical_material_and_light", "one_saved_edit_undo_redo_and_exact_project_reopen", "reopened_material_controls_match_saved_settings", "actual_mitsuba_worker_float_output_and_admitted_srgb_preview", "clicked_real_scientific_artifact_download"]
        for name in expected_steps:
            checks[name] = name in ui.get("steps", [])
        if not checks["actual_shipped_controls_passed"]:
            raise RuntimeError(ui.get("error", "Scientific native controls did not pass"))
        if operation == "optics-edit":
            saved = store.get(project["id"])
            with store.lock:
                submitted = [row for row in store.jobs.values() if row["project_id"] == project["id"]]
            model = saved.get("ray_optics", {})
            checks["authoring_phase_did_not_submit_analysis_or_render"] = not submitted and not ui.get("downloads")
            checks["saved_optical_edit_contains_exact_authored_numbers"] = (model.get("aperture", {}).get("value") == 8 and
                [(row["radius"], row["thickness"]) for row in model.get("surfaces", [])] == [(60, 4), (-60, 57.2)])
            checks["saved_optical_edit_retains_authored_field_wavelengths_and_glass"] = (model.get("fields") == [{"x": 0, "y": 0, "weight": 1}] and
                len(model.get("wavelengths", [])) == 3 and model["surfaces"][0]["material"] == {"type": "catalog", "catalog": "schott", "name": "N-BK7"})
            checks["actual_browser_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        else:
            _verify_render(store, project, ui, operation, output, downloads, origin, screenshot, result, checks, budget, transport)
    except Exception as exc:
        result["error"] = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            result["process_error"] = str(exc.stderr)[-1800:]
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=.3)
        if store:
            store.shutdown()
            if project:
                saved_path = workspace_owner / "workspace/projects" / project["id"] / "project.json"
                identity(saved_path)
                (output / "ENGINE_TEST_saved_project.json").write_bytes(saved_path.read_bytes())
            with store.lock:
                jobs = copy.deepcopy(list(store.jobs.values()))
            (output / "ENGINE_TEST_owned_jobs.json").write_text(json.dumps(jobs, indent=2))
            checks["all_owned_jobs_terminal_after_shutdown"] = all(row["state"] not in {"queued", "running"} for row in jobs)
        result["source_after"] = source_inventory()
        checks["runtime_web_and_helper_sources_unchanged"] = result.get("source_before") == result["source_after"]
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["phase_within_18_second_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if result["passed"] and operation == "optics-edit":
        fence = {"kind": KIND, "phase": operation, "transport": transport, "source_inventory": result["source_after"]}
        for key, record in (("project", project), ("sentinel", sentinel)):
            fence[key] = {"id": record["id"], "identity": identity(output / "workspace/projects" / record["id"] / "project.json")}
        (output / "optics-edit-passed.json").write_text(json.dumps(fence, indent=2))
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
    (output / "ENGINE_TEST_scientific_native_report.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--operation", required=True, choices=("optics-edit", "optics-render", "physical"))
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--fixture-workspace", type=Path, help="The exact successful optics-edit output directory, required for optics-render")
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"passed": False, "reason": "Actual macOS WKWebView is required; native execution is not simulated."}))
        return 1
    identity(args.binary)
    identity(args.source_manifest)
    result = run(args.binary, args.output, args.operation, json.loads(args.source_manifest.read_text()), fixture_workspace=args.fixture_workspace)
    print(json.dumps({"passed": result["passed"], "operation": args.operation, "checks": len(result["checks"]),
                      "elapsed_seconds": result["elapsed_seconds"], "error": result.get("error"),
                      "report": str(args.output / "ENGINE_TEST_scientific_native_report.json")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

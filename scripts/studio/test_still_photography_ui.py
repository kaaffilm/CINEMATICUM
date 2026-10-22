#!/usr/bin/env python3
"""Actual still-photography acceptance in five bounded foreground phases.

The native entry point requires macOS WKWebView. The browser driver executes
the identical shipped controls and numeric checks but does not certify native
macOS. Each phase owns a fresh server/helper and has an 18-second work bound.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from install_macos import RUNTIME_FILES
import imaging
from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result
from test_multicam_sync_macos import identity, safe_directory, write_json, read_json, _download_identity

HERE = Path(__file__).resolve().parent
KIND = "cinematicum-owned-still-photography-acceptance-v1"
PHASES = ("prepare", "import", "hdr", "panorama", "deliver")


def source_inventory():
    names = set(RUNTIME_FILES) | {"install_macos.py", "test_still_photography.py", "test_still_photography_ui.py",
        "test_still_photography_browser.cjs", "test_editing_ui_macos.py", "test_multicam_sync_macos.py", "test_multicam_sync_browser.cjs",
        "macos/StillPhotographySmoke.js", "macos/SmokeTest.swift"}
    names |= {str(path.relative_to(HERE)) for path in (HERE / "web").iterdir() if path.is_file()}
    return {name: identity(HERE / name) for name in sorted(names)}


def make_fixture(root):
    """Runs only in the explicitly selected actual NumPy imaging interpreter."""
    import numpy as np
    from test_still_photography import scene, sample, png
    root = Path(root)
    root.mkdir()
    (root / "photographs").mkdir()
    (root / "truth").mkdir()
    captures, transforms = [], [np.array([[1, 0, 7], [0, 1, -4], [0, 0, 1]]), np.eye(3), np.array([[1, 0, -6], [0, 1, 5], [0, 0, 1]])]
    gamma, times = np.array([2., 2.2, 2.4], np.float32), [.04, .16, .64]
    original = scene(np)
    for index, (matrix, exposure) in enumerate(zip(transforms, times)):
        world = original.copy()
        left = [45, 125, 205][index]
        world[68:98, left:left + 30] = [.8, .45, .2]
        if index == 1:
            np.save(root / "truth/hdr-reference.npy", world, allow_pickle=False)
        encoded = np.clip(sample(np, world, matrix, 320, 192) * exposure, 0, 1) ** (1 / gamma)
        name = "ENGINE_TEST_HDR_%d.png" % (index + 1)
        png(np, root / "photographs" / name, encoded)
        captures.append({"name": name, "role": "hdr", "exposure_time": exposure, "source_to_reference": matrix.tolist()})
    world = scene(np, 220, 640, 817)
    world = .03 + .8 * world / (1 + world)
    np.save(root / "truth/panorama-world.npy", world, allow_pickle=False)
    for index in range(3):
        matrix = np.array([[1, 0, index * 160], [0, 1, 0], [0, 0, 1]])
        pixels = sample(np, world, matrix, 320, 192)
        if index == 1:
            pixels *= .5
        name = "ENGINE_TEST_PANORAMA_%d.png" % (index + 1)
        png(np, root / "photographs" / name, pixels)
        captures.append({"name": name, "role": "panorama", "source_to_reference": matrix.tolist()})
    return {"photographs": [{**row, "identity": identity(root / "photographs" / row["name"])} for row in captures],
            "truth": {path.name: identity(path) for path in (root / "truth").iterdir()}, "gamma_rgb": gamma.tolist()}


def inspect_pixels(root, directory, output_id, operation):
    import numpy as np
    import OpenEXR
    import PyOpenColorIO as ocio
    from test_still_photography import sample
    root, directory = Path(root), Path(directory)
    fixture = read_json(root / "fixture.json")
    receipt = read_json(directory / "imaging/outputs" / output_id / "receipt.json")
    with OpenEXR.File(str(directory / "imaging/outputs" / output_id / "linear.exr")) as source:
        rgba = source.channels()["RGBA"].pixels.copy()
        space = source.header()["ocioColorSpace"]
    alpha = rgba[..., 3]
    rgb = np.ascontiguousarray(rgba[..., :3])
    np.divide(rgb, alpha[..., None], out=rgb, where=alpha[..., None] > 0)
    ocio.Config.CreateFromBuiltinConfig(receipt["recipe"]["config"]).getProcessor(space, "lin_rec709").getDefaultCPUProcessor().applyRGB(rgb)
    details = receipt["source_details"]
    measurements = details["alignment"]["measurements"] if operation == "hdr" else details["measurements"]
    points = np.array([[30, 30, 1], [280, 30, 1], [30, 160, 1], [280, 160, 1]], np.float64)
    errors = []
    for actual, expected in zip(measurements, [row for row in fixture["photographs"] if row["role"] == operation]):
        a, b = points @ np.asarray(actual["source_to_reference"]).T, points @ np.asarray(expected["source_to_reference"]).T
        errors.extend(np.linalg.norm(a[:, :2] / a[:, 2:] - b[:, :2] / b[:, 2:], axis=1).tolist())
    valid = alpha > .99
    valid[:12] = valid[-12:] = False
    valid[:, :12] = valid[:, -12:] = False
    result = {"geometric_error_max_pixels": max(errors), "transparent_pixels": int(np.count_nonzero(alpha == 0)),
              "linear_max": float(rgb.max()), "shape": list(rgba.shape)}
    if operation == "hdr":
        truth = np.load(root / "truth/hdr-reference.npy", allow_pickle=False) / ((128 / 255) ** np.asarray(fixture["gamma_rgb"]))
        result["median_relative_radiance_error"] = float(np.median(np.abs(rgb[valid] - truth[valid]) / np.maximum(truth[valid], .02)))
        area = np.zeros(valid.shape, bool)
        for left in (45, 125, 205):
            area[73:93, left + 5:left + 25] = True
        result["motion_region_relative_error"] = float(np.median(np.abs(rgb[area] - truth[area]) / np.maximum(truth[area], .02)))
        result["response_p95_residual_stops"] = details["response"]["p95_residual_stops"]
    else:
        world = np.load(root / "truth/panorama-world.npy", allow_pickle=False)
        left, top = details["canvas_origin_in_reference"]
        truth = sample(np, world, [[1, 0, left], [0, 1, top], [0, 0, 1]], rgb.shape[1], rgb.shape[0])
        result["median_linear_pixel_error"] = float(np.median(np.abs(rgb[valid] - truth[valid])))
        result["exposure_gains"] = [row["exposure_gain_rgb"] for row in details["measurements"]]
    return result


def inspect_movie(root, movie):
    import numpy as np
    root, movie = Path(root), Path(movie)
    def decode(path):
        run = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-threads", "1", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgba64le", "-threads", "1", "pipe:1"],
                             capture_output=True, check=True, timeout=3)
        return np.frombuffer(run.stdout, "<u2").reshape(-1, 96, 160, 4)
    frames, first, last = decode(movie), decode(root / "frame-hdr.png")[0], decode(root / "frame-panorama.png")[0]
    errors = [np.abs(frame.astype(float) - expected).ravel() for frame, expected in ((frames[0], first), (frames[-1], last))]
    probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt", "-of", "json", str(movie)],
                           capture_output=True, text=True, check=True, timeout=3)
    stream = json.loads(probe.stdout)["streams"][0]
    return {"frames": len(frames), "codec": stream["codec_name"], "pixel_format": stream["pix_fmt"],
            "first_last_max_16bit_rgba_errors": [float(error.max()) for error in errors]}


def run(binary, output, operation, fixture_workspace, expected_sources, *, transport="WKWebView"):
    began = time.monotonic()
    deadline = began + 18
    output = safe_directory(output, new=True)
    result = {"schema": KIND, "operation": operation, "browser": transport, "native_certified": transport == "WKWebView" and sys.platform == "darwin" and operation != "prepare",
              "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT", "checks": {}, "passed": False}
    checks = result["checks"]
    store = server = thread = root = fixture = project = None
    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The still-photography phase exhausted its 18-second foreground bound")
        return min(maximum, remaining)
    def runtime(function, *args, maximum=4):
        code = "import sys,json;sys.path.insert(0,sys.argv[1]);from test_still_photography_ui import " + function + ";print(json.dumps(" + function + "(*sys.argv[2:])))"
        run = subprocess.run([imaging.find_imaging_python(), "-I", "-B", "-c", code, str(HERE), *map(str, args)],
                             capture_output=True, text=True, check=True, timeout=budget(maximum, .5), env=imaging._worker_env())
        return json.loads(run.stdout)
    try:
        if operation not in PHASES:
            raise ValueError("Unknown photograph acceptance phase")
        result["source_before"] = source_inventory()
        if result["source_before"] != expected_sources:
            raise ValueError("The photograph acceptance source differs from its explicit frozen inventory")
        checks["source_matches_frozen_inventory"] = True
        if operation == "prepare":
            root = Path(fixture_workspace).absolute()
            if root.exists() or any(p.is_symlink() for p in (root, *root.parents)):
                raise ValueError("Preparation needs a new explicit owned fixture directory")
            root.parent.mkdir(parents=True, exist_ok=True)
            values = runtime("make_fixture", root, maximum=7)
            store = Store(root / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST photograph sentinel", "width": 160, "height": 96, "fps": 12})
            project = store.new_project({"name": "ENGINE TEST HDR and panorama", "width": 160, "height": 96, "fps": 12})
            fixture = {"schema": KIND, "acceptance_id": uuid.uuid4().hex, "project_id": project["id"], "project_name": project["name"],
                       "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"], **values}
            write_json(root / "fixture.json", fixture)
            checks["six_encoded_sources_have_independent_radiance_response_motion_and_geometry_truth"] = len(fixture["photographs"]) == 6 and len(fixture["truth"]) == 2
            checks["fresh_project_has_no_invented_import_or_edit"] = not project["assets"] and not project["clips"]
        else:
            root = safe_directory(fixture_workspace)
            fixture = read_json(root / "fixture.json")
            prior = read_json(root / (PHASES[PHASES.index(operation) - 1] + "-passed.json"))
            if prior.get("passed") is not True or prior.get("acceptance_id") != fixture["acceptance_id"] or prior.get("source_inventory") != expected_sources:
                raise ValueError("The prior passed phase does not certify these exact sources and fixture")
            if (root / (operation + "-passed.json")).exists():
                raise ValueError("The phase already passed; preserve it and prepare a fresh fixture for repetition")
            if identity(root / "workspace/projects" / fixture["project_id"] / "project.json") != prior["saved_project_identity"]:
                raise ValueError("The saved project changed after its preceding accepted phase")
            store = Store(root / "workspace")
            initial = store.get(fixture["project_id"])
            with store.lock:
                jobs_before = set(store.jobs)
            script = output / "StillPhotographySmoke.js"
            script.write_text((HERE / "macos/StillPhotographySmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps({**fixture, "operation": operation})))
            downloads = output / "native_downloads"
            downloads.mkdir()
            class FixtureHandler(Handler):
                def do_GET(self):
                    match = re.fullmatch(r"/__engine_test__/photo/([0-5])", self.path)
                    if match:
                        try:
                            self.guard()
                            row = fixture["photographs"][int(match[1])]
                            path = root / "photographs" / row["name"]
                            if identity(path) != row["identity"]:
                                raise ValueError("An independent original photograph changed")
                            return self.file(path)
                        except Exception as exc:
                            return self.json(400, {"error": str(exc)})
                    return super().do_GET()
            server = Server(0, store)
            server.RequestHandlerClass = FixtureHandler
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            screenshot = output / "ENGINE_TEST_still_photography.png"
            helper_timeout = budget(14.7, 2.5)
            argv = [str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot), "--script", str(script),
                    "--download-dir", str(downloads), "--timeout", str(round(helper_timeout, 2))]
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=budget(helper_timeout + .2, 2.2))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=.5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate(timeout=.5)
                raise TimeoutError("The owned photograph browser exceeded its foreground bound")
            (output / "helper.stdout").write_text(stdout)
            (output / "helper.stderr").write_text(stderr)
            ui = read_helper_result(subprocess.CompletedProcess(argv, process.returncode, stdout, stderr))
            result["ui"] = ui
            checks["actual_shipped_browser_controls_passed"] = process.returncode == 0 and ui.get("passed") is True
            if not checks["actual_shipped_browser_controls_passed"]:
                raise ValueError(ui.get("error", "The real browser workflow failed"))
            project = store.get(fixture["project_id"])
            directory = store.project_dir(project["id"])
            originals = [asset for asset in project["assets"] if any(row["name"] == asset["name"] for row in fixture["photographs"])]
            checks["all_six_admitted_source_bytes_match_independent_originals"] = len(originals) == 6 and all(
                identity(directory / asset["path"]) == next(row["identity"] for row in fixture["photographs"] if row["name"] == asset["name"]) for asset in originals)
            if operation in {"hdr", "panorama"}:
                job = store.job(ui["job_id"])
                checks["one_owned_completed_actual_imaging_job"] = job["kind"] == "imaging" and job["state"] == "completed" and job["project_id"] == project["id"] and sum(j["kind"] == "imaging" for ident, j in store.jobs.items() if ident not in jobs_before) == 1
                asset = next(asset for asset in project["assets"] if asset["id"] == ui["asset_id"])
                receipt = job["result"]["receipt"]
                checks["admitted_display_and_float_master_have_immutable_receipt_hashes"] = asset["sha256"] == receipt["artifacts"]["display"]["sha256"] and asset["provenance"]["receipt_sha256"] == identity(directory / "imaging/outputs" / ui["job_id"] / "receipt.json")["sha256"]
                clicked = ui["clicked_downloads"]
                rows = ui.get("downloads", [])
                checks["every_actual_button_download_completed"] = len(rows) == len(clicked) == (4 if operation == "hdr" else 3)
                for request in clicked:
                    matches = [row for row in rows if row.get("url") == origin + request["url"]]
                    if len(matches) != 1:
                        raise ValueError("A photograph artifact did not download exactly once")
                    _, downloaded = _download_identity(matches[0], output, transport)
                    checks["download_" + request["key"] + "_matches_exact_owned_artifact"] = downloaded == identity(directory / "imaging/outputs" / ui["job_id"] / request["name"])
                metrics = runtime("inspect_pixels", root, directory, ui["job_id"], operation, maximum=3)
                result["independent_numeric_measurements"] = metrics
                checks["measured_geometry_matches_independent_camera_coordinates"] = metrics["geometric_error_max_pixels"] < 1.1
                if operation == "hdr":
                    checks["fitted_response_recovers_independent_capture_radiance"] = metrics["median_relative_radiance_error"] < .09 and metrics["response_p95_residual_stops"] < .3
                    checks["reference_motion_pixels_match_independent_moving_scene"] = metrics["motion_region_relative_error"] < .12 and ui["visible_motion_pixels"] == receipt["source_details"]["deghost"]["motion_pixels"]
                    checks["aligned_hdr_keeps_superwhite_and_transparent_uncovered_borders"] = metrics["linear_max"] > 10 and metrics["transparent_pixels"] > 2000
                else:
                    checks["stitched_linear_pixels_match_independent_world"] = metrics["median_linear_pixel_error"] < .006 and 638 <= metrics["shape"][1] <= 644
                    checks["overlap_gain_measured_from_half_exposure_source"] = max(abs(value - 2) for value in metrics["exposure_gains"][1]) < .03
                checks["undo_redo_saved_reopened_edit_uses_immutable_image"] = len(project["clips"]) == (1 if operation == "hdr" else 2) and project["clips"][-1]["asset_id"] == asset["id"] and project["clips"][-1]["duration"] == 12
                preview = directory / "previews" / Path(ui["frame_url"]).name
                checks["actual_renderer_created_displayed_frame"] = preview.is_file() and preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
                shutil.copyfile(preview, root / ("frame-" + operation + ".png"))
            elif operation == "deliver":
                rows = ui.get("downloads", [])
                checks["actual_movie_and_archive_downloads_completed"] = len(rows) == 2
                downloaded_paths = {}
                for key in ("movie", "archive"):
                    rows_for_url = [row for row in rows if row.get("url") == origin + ui[key + "_url"]]
                    if len(rows_for_url) != 1:
                        raise ValueError("The actual " + key + " download did not complete once")
                    path, actual = _download_identity(rows_for_url[0], output, transport)
                    expected = directory / "exports" / ui[key + "_name"]
                    checks[key + "_download_matches_completed_owned_bytes"] = actual == identity(expected)
                    downloaded_paths[key] = path
                metrics = runtime("inspect_movie", root, downloaded_paths["movie"], maximum=3)
                result["independent_movie_measurements"] = metrics
                checks["actual_lossless_sdr_movie_has_all_24_authored_16bit_frames"] = metrics["frames"] == 24 and metrics["codec"] == "ffv1" and metrics["pixel_format"] == "gbrap16le"
                checks["movie_first_last_16bit_pictures_match_actual_paused_export_graph"] = max(metrics["first_last_max_16bit_rgba_errors"]) <= 1
                restored = store.get(ui["restored_id"])
                fresh = store.project_dir(restored["id"])
                checks["restored_project_preserves_exact_edit_and_asset_references"] = restored["clips"] == project["clips"] and restored["assets"] == project["assets"] and restored["id"] != project["id"]
                masters = [asset for asset in project["assets"] if asset.get("provenance", {}).get("type") == "cinematicum-imaging"]
                preserved = True
                for asset in masters:
                    output_id = asset["provenance"]["output_id"]
                    recipe = asset["provenance"]["recipe"]
                    for name in imaging.expected_artifact_names(recipe):
                        relative = Path("imaging/outputs") / output_id / name
                        preserved &= identity(directory / relative) == identity(fresh / relative)
                checks["archive_restored_both_float_masters_receipts_and_motion_mask_exactly"] = len(masters) == 2 and preserved
            checks["actual_browser_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000
    except Exception as exc:
        result["error"] = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            result["process_error"] = str(exc.stderr)[-2000:]
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=.3)
        if store:
            store.shutdown()
            with store.lock:
                jobs = copy.deepcopy(list(store.jobs.values()))
            checks["owned_jobs_terminal_after_shutdown"] = all(job["state"] not in {"queued", "running"} for job in jobs)
            write_json(output / "owned-jobs.json", jobs)
        if root and fixture:
            checks["independent_original_photographs_and_truth_unchanged"] = all(identity(root / "photographs" / row["name"]) == row["identity"] for row in fixture["photographs"]) and {p.name: identity(p) for p in (root / "truth").iterdir()} == fixture["truth"]
            result["saved_project_identity"] = identity(root / "workspace/projects" / fixture["project_id"] / "project.json")
        result["source_after"] = source_inventory()
        checks["operative_and_acceptance_source_unchanged"] = result.get("source_before") == result["source_after"]
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["phase_within_18_second_foreground_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
    report = output / "ENGINE_TEST_still_photography_report.json"
    write_json(report, result)
    if result["passed"]:
        write_json(root / (operation + "-passed.json"), {"passed": True, "acceptance_id": fixture["acceptance_id"], "source_inventory": expected_sources,
                   "saved_project_identity": result["saved_project_identity"], "report_identity": identity(report)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operation", choices=PHASES, required=True)
    parser.add_argument("--fixture-workspace", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"passed": False, "reason": "The native entry point requires actual macOS WKWebView; use the separate browser driver on Linux."}))
        return 1
    result = run(args.binary, args.output, args.operation, args.fixture_workspace, read_json(args.source_manifest))
    print(json.dumps({"passed": result["passed"], "operation": args.operation, "checks": len(result["checks"]), "elapsed_seconds": result["elapsed_seconds"], "error": result.get("error")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

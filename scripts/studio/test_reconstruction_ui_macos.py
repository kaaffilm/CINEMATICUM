#!/usr/bin/env python3
"""Actual eight-photo COLMAP authoring in four owned foreground phases.

prepare creates independent ray/plane photographs in a new explicit fixture;
author imports them and edits/save/undoes/reopens the actual controls; solve
restarts the backend and runs the actual installed CPU COLMAP worker; apply
restarts it again, checks the explicit canvas guard, applies/undoes/reopens the
measured scene and downloads three actual artifacts. Each phase is bounded by
18 seconds. WKDownload uses an explicit evidence directory. Physical input,
NSSavePanel, the installed launcher, dense reconstruction and production-scale
quality are outside this acceptance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from install_macos import RUNTIME_FILES
import reconstruction
from scene import default_scene
from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result

HERE = Path(__file__).resolve().parent
STUDIO_SOURCE = Path(sys.modules[Store.__module__].__file__).resolve().parent
KIND = "cinematicum-owned-native-reconstruction-v1"
PHASES = ("prepare", "author", "solve", "apply")
ID = re.compile(r"[a-f0-9]{32}")

PREPARE = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from test_reconstruction import photographs
truth=photographs(Path(sys.argv[2]))
print(json.dumps(truth))
'''

GEOMETRY = r'''
import json,sys,sqlite3,zipfile,hashlib,io
from pathlib import Path
import numpy as np,pycolmap
from PIL import Image
output=Path(sys.argv[1]);truth=json.loads(Path(sys.argv[2]).read_text())
metadata=json.loads((output/'reconstruction.json').read_text())
names={row['name']:row['normalized_name'] for row in metadata['normalization']['photos']}
model=pycolmap.Reconstruction(output);ordered=[];expected=[];rotations=[]
for item in truth['images']:
    image=next(v for v in model.images.values() if v.name==names[item['name']])
    ordered.append(image.projection_center());expected.append(item['center']);rotations.append(image.cam_from_world().rotation.matrix())
a=np.array(ordered);b=np.array(expected);ac=a-a.mean(0);bc=b-b.mean(0)
u,s,vt=np.linalg.svd(bc.T@ac/len(a));d=np.eye(3);d[-1,-1]=np.sign(np.linalg.det(u@vt));rotation=u@d@vt
scale=np.sum(s*np.diag(d))/np.mean(np.sum(ac*ac,axis=1));translation=b.mean(0)-scale*rotation@a.mean(0)
aligned=scale*(a@rotation.T)+translation;camera_error=np.sqrt(np.mean(np.sum((aligned-b)**2,axis=1)))
angles=[]
for solved,item in zip(rotations,truth['images']):
    relative=(solved@rotation.T)@np.array(item['rotation']).T
    angles.append(float(np.degrees(np.arccos(np.clip((np.trace(relative)-1)/2,-1,1)))))
points=np.array([point.xyz for point in model.points3D.values()]);p=scale*(points@rotation.T)+translation;distances=[]
for x,y,z,w,h in truth['planes']:
    dx=np.maximum(np.abs(p[:,0]-x)-w/2,0);dy=np.maximum(np.abs(p[:,1]-y)-h/2,0)
    distances.append(np.sqrt(dx*dx+dy*dy+(p[:,2]-z)**2))
surface=np.min(np.array(distances),axis=0);errors=[]
for image in model.images.values():
    if image.camera.model_name!='PINHOLE':raise ValueError('Native fixture must retain its calibrated PINHOLE model')
    pose=image.cam_from_world();r=pose.rotation.matrix();t=pose.translation;fx,fy,cx,cy=image.camera.params
    for point in image.points2D:
        if not point.has_point3D():continue
        q=r@model.points3D[point.point3D_id].xyz+t
        if q[2]<=0:raise ValueError('A measured observation is behind its camera')
        x,y=q[:2]/q[2];errors.append(float(np.linalg.norm(np.array([fx*x+cx,fy*y+cy])-point.xy)))
with sqlite3.connect((output/'database.db').as_uri()+'?mode=ro&immutable=1',uri=True) as database:
    features=database.execute('SELECT SUM(rows) FROM keypoints').fetchone()[0]
    descriptors=database.execute('SELECT SUM(rows) FROM descriptors').fetchone()[0]
    verified=database.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows>0').fetchone()[0]
with zipfile.ZipFile(output/'undistorted-images.zip') as archive:
    manifest=json.loads(archive.read('manifest.json'));images_ok=len(manifest['cameras'])==8
    images_ok=images_ok and set(archive.namelist())=={'manifest.json',*(row['undistorted']['member'] for row in manifest['cameras'])}
    for row in manifest['cameras']:
        camera=row['undistorted'];data=archive.read(camera['member'])
        with Image.open(io.BytesIO(data)) as image:
            image.load();images_ok=images_ok and image.size==(camera['width'],camera['height']) and image.mode=='RGB'
        images_ok=images_ok and hashlib.sha256(data).hexdigest()==camera['sha256'] and len(data)==camera['bytes'] and camera['model']=='PINHOLE'
print(json.dumps({'registered':model.num_reg_images(),'points':model.num_points3D(),'observations':len(errors),
    'camera_rmse':float(camera_error),'camera_angle_max_degrees':max(angles),
    'surface_median_error':float(np.median(surface)),'surface_95_error':float(np.percentile(surface,95)),
    'reprojection_rms':float(np.sqrt(np.mean(np.square(errors)))),'alignment_scale':float(scale),
    'features':features,'descriptors':descriptors,'verified_pairs':verified,'undistorted_bundle_exact':images_ok}))
'''


def identity(path, maximum=32 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("Native acceptance requires a bounded regular file")
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def safe_directory(path, *, new=False):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("The explicit fixture/evidence path must not traverse a symlink")
    if new:
        if path.exists():
            raise ValueError("Preserve the previous native attempt and choose a new directory")
        path.mkdir(parents=True)
    elif not path.is_dir():
        raise ValueError("The explicitly prepared fixture directory is absent")
    return path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def read_json(path):
    identity(path)
    return json.loads(Path(path).read_text())


def source_inventory():
    names = set(RUNTIME_FILES) | {"install_macos.py", "test_reconstruction.py", "test_reconstruction_ui_macos.py",
                                "test_editing_ui_macos.py", "macos/ReconstructionSmoke.js", "macos/SmokeTest.swift"}
    for path in (STUDIO_SOURCE / "web").rglob("*"):
        if path.is_symlink():
            raise ValueError("Shipped web source must not contain symlinks")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.name != ".DS_Store":
            names.add(path.relative_to(STUDIO_SOURCE).as_posix())
    return {name: identity(STUDIO_SOURCE / name) for name in sorted(names)}


def _fixture(path):
    root = safe_directory(path)
    fixture = read_json(root / "native-fixture.json")
    if fixture.get("kind") != KIND or not ID.fullmatch(fixture.get("acceptance_id", "")):
        raise ValueError("This is not the explicitly prepared reconstruction fixture")
    if any(not ID.fullmatch(fixture.get(key, "")) for key in ("project_id", "sentinel_id")):
        raise ValueError("The fixture project identity is malformed")
    expected = [f"photo-{index:02d}.png" for index in range(8)]
    if [row.get("name") for row in fixture.get("photos", [])] != expected:
        raise ValueError("The prepared fixture does not identify exactly eight independent photos")
    if {path.name for path in (root / "photos").iterdir()} != set(expected):
        raise ValueError("The fixture photo namespace changed")
    if any(identity(root / "photos" / row["name"]) != row["identity"] for row in fixture["photos"]):
        raise ValueError("An original photograph changed")
    if identity(root / "truth.json") != fixture["truth_identity"]:
        raise ValueError("The independent ground truth changed")
    # Startup may settle interrupted work. Refuse it before opening the Store so
    # a new phase never rewrites an earlier failed/pending execution as success.
    for path in (root / "workspace/jobs").glob("*.json"):
        job = read_json(path)
        if not ID.fullmatch(path.stem) or job.get("id") != path.stem or job.get("project_id") not in {fixture["project_id"], fixture["sentinel_id"]}:
            raise ValueError("The explicit fixture contains an unexpected durable job")
        if job.get("state") not in {"completed", "failed", "cancelled"}:
            raise ValueError("An earlier phase has pending or malformed work; preserve it and prepare a new fixture")
    return root, fixture


def _assets_preserved(root, project, fixture):
    expected = {row["name"]: row["identity"] for row in fixture["photos"]}
    assets = project["assets"]
    return (len(assets) == 8 and len({asset["name"] for asset in assets}) == 8
            and all(asset["kind"] == "image" and (asset["width"], asset["height"]) == (640, 480)
                    and re.fullmatch(r"media/[a-f0-9]{32}\.png", asset["path"])
                    and identity(root / "workspace/projects" / project["id"] / asset["path"]) == expected.get(asset["name"])
                    and {"sha256": asset["sha256"], "size": asset["size"]} == expected.get(asset["name"])
                    for asset in assets))


def _artifacts(directory, receipt):
    rows = receipt.get("artifacts", [])
    names = [row["filename"] for row in rows]
    if len(names) != len(set(names)) or not set(names) <= reconstruction.ARTIFACT_NAMES - {"provenance.json"}:
        raise ValueError("The actual receipt contains unexpected or duplicate artifacts")
    actual = {path.name: identity(path) for path in directory.iterdir()}
    declared = {row["filename"]: {"sha256": row["sha256"], "size": row["bytes"]} for row in rows}
    declared["provenance.json"] = identity(directory / "provenance.json")
    if actual != declared:
        raise ValueError("The published sparse artifacts differ from their actual receipt")
    return actual


def run(binary, output, operation, fixture_workspace, expected_sources, *, transport="WKWebView"):
    began = time.monotonic()
    deadline = began + 18
    output = safe_directory(output, new=True)
    result = {"kind": KIND, "operation": operation, "browser": transport, "passed": False,
              "native_certified": operation != "prepare" and transport == "WKWebView" and sys.platform == "darwin",
              "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT", "checks": {},
              "scope": "Actual shipped photo importer, typed controls, CPU COLMAP solve, independent camera/structure math and undoable scene application. Downloads use an explicit evidence directory. Dense reconstruction, arbitrary footage, physical input, NSSavePanel and the installed launcher are not certified."}
    if transport != "WKWebView":
        result["scope"] += " This is Chromium transport validation only; no native acceptance is claimed."
    checks = result["checks"]
    store = server = thread = root = fixture = project = None
    final_fence = None

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The reconstruction phase exhausted its 18-second foreground budget")
        return min(maximum, remaining)

    try:
        if operation not in PHASES:
            raise ValueError("Unknown native reconstruction phase")
        before = source_inventory()
        result["source_before"] = before
        if before != expected_sources:
            raise ValueError("Current runtime, web or acceptance source differs from the explicit frozen inventory")
        checks["source_matches_explicit_frozen_inventory"] = True
        if operation == "prepare":
            root = safe_directory(fixture_workspace, new=True)
            python = reconstruction.find_python()
            if not python:
                raise RuntimeError("The actual managed COLMAP runtime is unavailable")
            prepared = subprocess.run([python, "-I", "-B", "-c", PREPARE, str(STUDIO_SOURCE), str(root / "photos")],
                                      capture_output=True, text=True, check=True, timeout=budget(12, 2), env=reconstruction._env())
            truth = json.loads(prepared.stdout)
            write_json(root / "truth.json", truth)
            store = Store(root / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST Reconstruction sentinel", "width": 640, "height": 360, "fps": 24})
            project = store.new_project({"name": "ENGINE TEST Native eight-photo reconstruction", "width": 640, "height": 360, "fps": 24})
            project["settings"]["scene"] = default_scene(640, 360)
            project = store.save(project["id"], project)
            fixture = {"kind": KIND, "acceptance_id": uuid.uuid4().hex,
                       "project_id": project["id"], "project_name": project["name"],
                       "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"],
                       "photos": [{"name": row["name"], "identity": identity(root / "photos" / row["name"])} for row in truth["images"]],
                       "truth_identity": identity(root / "truth.json")}
            write_json(root / "native-fixture.json", fixture)
            write_json(root / "initial-project.json", project)
            checks["eight_independent_calibrated_textured_plane_photographs"] = len(fixture["photos"]) == 8 and truth["camera_params"] == [650, 650, 320, 240]
            checks["fixture_starts_empty_with_deliberately_different_canvas"] = not project["assets"] and not project.get("reconstruction") and (project["width"], project["height"]) == (640, 360)
            checks["no_solver_features_poses_or_points_supplied"] = set(path.name for path in (root / "photos").iterdir()) == {row["name"] for row in fixture["photos"]}
        else:
            root, fixture = _fixture(fixture_workspace)
            phase_index = PHASES.index(operation)
            prior_phase = PHASES[phase_index - 1]
            prior_path = root / (prior_phase + "-passed.json")
            prior = read_json(prior_path)
            if prior.get("passed") is not True or prior.get("acceptance_id") != fixture["acceptance_id"] or prior.get("source_inventory") != before:
                raise ValueError("The preceding actual phase does not certify this exact fixture/source")
            if (root / (operation + "-passed.json")).exists():
                raise ValueError("This phase already passed; preserve it and use a new complete fixture for repetition")
            persisted_project = root / "workspace/projects" / fixture["project_id"] / "project.json"
            if identity(persisted_project) != prior["saved_project_identity"]:
                raise ValueError("The durable project changed after its preceding accepted phase")
            result["prior_phase_identity"] = identity(prior_path)
            result["helper_identity"] = identity(binary)
            store = Store(root / "workspace")
            project = store.get(fixture["project_id"])
            if project["name"] != fixture["project_name"] or store.get(fixture["sentinel_id"])["name"] != fixture["sentinel_name"]:
                raise ValueError("The exact fixture project/sentinel identity changed")
            initial = copy.deepcopy(project)
            with store.lock:
                jobs_before = {row["id"] for row in store.jobs.values()}
            config = {**fixture, "operation": operation}
            if operation == "apply":
                if not ID.fullmatch(prior.get("job_id", "")):
                    raise ValueError("The prior solve did not bind its actual job")
                config["job_id"] = prior["job_id"]
                directory = store.project_dir(project["id"]) / "reconstruction/outputs" / prior["job_id"]
                receipt = read_json(directory / "provenance.json")
                if _artifacts(directory, receipt) != prior["artifacts"]:
                    raise ValueError("The actual immutable solve artifacts changed before application")
            script = output / "ReconstructionSmoke.js"
            script.write_text((HERE / "macos/ReconstructionSmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps(config)))
            result["executed_javascript_identity"] = identity(script)
            downloads = output / "native_downloads"
            downloads.mkdir()

            class FixtureHandler(Handler):
                def do_GET(self):
                    match = re.fullmatch(r"/__engine_test__/photo/([0-7])", self.path)
                    if match:
                        try:
                            self.guard()
                            row = fixture["photos"][int(match[1])]
                            source = root / "photos" / row["name"]
                            if identity(source) != row["identity"]:
                                raise ValueError("The original independent photograph changed")
                            return self.file(source)
                        except Exception as exc:
                            return self.json(400, {"error": str(exc)})
                    return super().do_GET()

            server = Server(0, store)
            server.RequestHandlerClass = FixtureHandler
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            screenshot = output / "ENGINE_TEST_reconstruction_native.png"
            helper_timeout = budget(14.8, 2)
            completed = subprocess.run([str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot),
                                        "--script", str(script), "--download-dir", str(downloads), "--timeout", str(round(helper_timeout, 2))],
                                       capture_output=True, text=True, timeout=budget(helper_timeout + .3, 1.5))
            ui = read_helper_result(completed)
            result.update(ui=ui, helper_exit_code=completed.returncode)
            write_json(output / "ENGINE_TEST_browser_result.json", ui)
            if completed.stderr:
                result["helper_stderr_tail"] = completed.stderr[-1800:]
            checks["actual_shipped_controls_passed"] = completed.returncode == 0 and ui.get("passed") is True
            checks["no_browser_or_download_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
            required = ["selected_exact_owned_fixture_project"] + {
                "author": ["imported_eight_original_photographs_through_shipped_file_input", "saved_typed_eight_photo_calibration", "calibration_undo_redo_and_exact_project_reopen"],
                "solve": ["saved_calibration_survived_backend_restart", "actual_cpu_colmap_eight_view_solve_and_decoded_preview", "completion_did_not_silently_apply_the_scene"],
                "apply": ["saved_result_reopened_after_backend_restart", "unchecked_resolution_change_refused_without_mutation", "clicked_three_real_owned_artifact_downloads", "explicit_camera_canvas_application_one_undo_redo_and_reopen", "duplicate_marker_application_refused"],
            }[operation]
            checks.update({name: name in ui.get("steps", []) for name in required})
            if not checks["actual_shipped_controls_passed"]:
                raise RuntimeError(ui.get("error", "Native reconstruction controls failed"))
            project = store.get(fixture["project_id"])
            checks["admitted_photos_preserve_exact_original_bytes"] = _assets_preserved(root, project, fixture)
            with store.lock:
                new_jobs = [copy.deepcopy(row) for row in store.jobs.values() if row["id"] not in jobs_before and row["kind"] == "reconstruction"]
            if operation == "author":
                settings = reconstruction.validate_settings(project.get("reconstruction"))
                checks["exact_saved_calibrated_settings"] = settings["camera_model"] == "PINHOLE" and settings["camera_params"] == [650, 650, 320, 240] and settings["refine_intrinsics"] is False and settings["marker_limit"] == 150 and set(settings["asset_ids"]) == {asset["id"] for asset in project["assets"]}
                checks["authoring_did_not_run_solver_or_change_scene"] = not new_jobs and project["settings"]["scene"] == initial["settings"]["scene"] and not ui.get("downloads")
            elif operation == "solve":
                checks["one_owned_actual_completed_reconstruction_job"] = len(new_jobs) == 1 and new_jobs[0]["state"] == "completed" and new_jobs[0]["project_id"] == project["id"] and new_jobs[0]["id"] == ui.get("job_id")
                if not checks["one_owned_actual_completed_reconstruction_job"]:
                    raise ValueError("The phase did not own exactly one actual completed reconstruction job")
                job = new_jobs[0]
                directory = store.project_dir(project["id"]) / "reconstruction/outputs" / job["id"]
                receipt = read_json(directory / "provenance.json")
                result["artifacts"] = _artifacts(directory, receipt)
                result["job_id"] = job["id"]
                result["statistics"] = receipt["statistics"]
                checks["receipt_binds_current_worker_coordinator_and_camera_math"] = receipt["source_sha256"] == {name: before[name]["sha256"] for name in ("reconstruction.py", "reconstruction_worker.py", "camera_io.py")}
                checks["solver_used_exact_saved_calibration_and_eight_original_inputs"] = receipt["settings"] == project["reconstruction"] and len(receipt["inputs"]) == 8 and all(row["sha256"] == next(asset["sha256"] for asset in project["assets"] if asset["id"] == row["asset_id"]) for row in receipt["inputs"])
                checks["actual_feature_matching_bundle_adjustment_and_sparse_geometry"] = receipt["engine"]["name"] == "COLMAP" and receipt["engine"]["device"] == "CPU" and receipt["statistics"]["registered_images"] == 8 and receipt["statistics"]["points3D"] > 1000 and receipt["statistics"]["features"] > 10000 and receipt["statistics"]["verified_pairs"] > 10 and receipt["statistics"]["reprojection"]["rms_pixels"] < .5
                checks["no_silent_scene_or_canvas_application"] = project["settings"]["scene"] == initial["settings"]["scene"] and (project["width"], project["height"]) == (640, 360)
            else:
                checks["application_reused_exact_durable_solve_without_new_inference"] = not new_jobs
                actual_downloads = ui.get("downloads", [])
                requested = {row["name"]: row["url"] for row in ui.get("clicked_downloads", [])}
                expected_names = {"sparse.ply", "undistorted-images.zip", "provenance.json"}
                valid_downloads = len(actual_downloads) == 3 and set(requested) == expected_names
                seen = set()
                for download in actual_downloads:
                    name = download.get("suggested_filename", "")
                    target = Path(download.get("path", "")).absolute()
                    expected_name = bool(re.fullmatch(r"ENGINE_TEST_[A-Fa-f0-9-]{36}_" + re.escape(name), target.name)) if transport == "WKWebView" else target.name == name
                    valid_downloads = valid_downloads and name in expected_names and name not in seen and download.get("state") == "completed" and target.parent == downloads and expected_name and download.get("url") == origin + requested.get(name, "") and identity(target) == prior["artifacts"].get(name)
                    seen.add(name)
                checks["three_real_downloads_match_owned_urls_and_receipt_bytes"] = bool(valid_downloads and seen == expected_names)
                if not checks["three_real_downloads_match_owned_urls_and_receipt_bytes"]:
                    raise ValueError("An actual artifact download differs from its exact owned result")
                proposal = read_json(directory / "scene.json")
                camera = next(row for row in proposal["cameras"] if row["id"] == ui.get("selected_camera_id"))
                marker = "reconstruction_points_" + prior["job_id"][:16]
                scene = project["settings"]["scene"]
                checks["saved_camera_matches_actual_solved_reference_proposal"] = all(scene["camera"][key] == value for key, value in camera["camera"].items())
                checks["explicit_canvas_and_one_sparse_marker_saved"] = (project["width"], project["height"], scene["width"], scene["height"]) == (640, 480, 640, 480) and len([row for row in scene["objects"] if row["id"] == marker]) == 1
                checks["all_existing_authored_objects_preserved"] = [row for row in scene["objects"] if row["id"] != marker] == initial["settings"]["scene"]["objects"]
                inspected = subprocess.run([reconstruction.find_python(), "-I", "-B", "-c", GEOMETRY, str(directory), str(root / "truth.json")],
                                           capture_output=True, text=True, check=True, timeout=budget(2.5, .5), env=reconstruction._env())
                metrics = json.loads(inspected.stdout)
                result["independent_measurements"] = metrics
                checks["independent_serialized_model_camera_geometry"] = metrics["registered"] == 8 and metrics["camera_rmse"] < .005 and metrics["camera_angle_max_degrees"] < .3
                checks["independent_serialized_sparse_surface_geometry"] = metrics["points"] > 1000 and metrics["surface_median_error"] < .02 and metrics["surface_95_error"] < .06
                checks["independent_every_observation_reprojection"] = metrics["observations"] > 5000 and metrics["reprojection_rms"] < .5 and abs(metrics["reprojection_rms"] - receipt["statistics"]["reprojection"]["rms_pixels"]) < 1e-10
                checks["actual_sift_database_and_verified_pairs"] = metrics["features"] > 10000 and metrics["features"] == metrics["descriptors"] == receipt["statistics"]["features"] and metrics["verified_pairs"] > 10
                checks["actual_eight_image_undistortion_archive_decodes_exactly"] = metrics["undistorted_bundle_exact"] is True
                checks["immutable_solve_artifacts_preserved_after_application"] = _artifacts(directory, receipt) == prior["artifacts"]
                result["job_id"] = prior["job_id"]
                result["artifacts"] = prior["artifacts"]
            checks["actual_browser_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
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
            checks["all_owned_jobs_terminal_after_shutdown"] = all(row["state"] not in {"queued", "running"} for row in jobs)
            write_json(output / "ENGINE_TEST_owned_jobs.json", jobs)
        if root and fixture and project:
            persisted = root / "workspace/projects" / fixture["project_id"] / "project.json"
            result["saved_project_identity"] = identity(persisted)
            (output / "ENGINE_TEST_saved_project.json").write_bytes(persisted.read_bytes())
            checks["original_photos_and_independent_ground_truth_unchanged"] = all(identity(root / "photos" / row["name"]) == row["identity"] for row in fixture["photos"]) and identity(root / "truth.json") == fixture["truth_identity"]
            final_fence = {"passed": True, "acceptance_id": fixture["acceptance_id"], "operation": operation,
                           "saved_project_identity": result["saved_project_identity"], "source_inventory": result.get("source_before")}
            if result.get("job_id"):
                final_fence.update(job_id=result["job_id"], artifacts=result["artifacts"])
        result["source_after"] = source_inventory()
        checks["runtime_web_and_acceptance_source_unchanged"] = result.get("source_before") == result["source_after"]
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["phase_within_18_second_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(name for name, passed in checks.items() if not passed)
    report = output / "ENGINE_TEST_reconstruction_native_report.json"
    write_json(report, result)
    if result["passed"] and final_fence:
        final_fence["report_identity"] = identity(report)
        write_json(root / (operation + "-passed.json"), final_fence)
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
        print(json.dumps({"passed": False, "reason": "Actual macOS WKWebView is required; native execution is not simulated."}))
        return 1
    result = run(args.binary, args.output, args.operation, args.fixture_workspace, read_json(args.source_manifest))
    print(json.dumps({"passed": result["passed"], "operation": args.operation, "checks": len(result["checks"]),
                      "elapsed_seconds": result["elapsed_seconds"], "error": result.get("error"),
                      "report": str(args.output / "ENGINE_TEST_reconstruction_native_report.json")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

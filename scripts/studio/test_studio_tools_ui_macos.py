#!/usr/bin/env python3
"""Real WKWebView Studio tools acceptance; each phase is bounded to 18 seconds.

The deep phase drives shipped controls, imports a synthetic real multipart EXR,
edits/saves/undoes/reopens its graph, runs the actual worker and clicks a real
WKDownload. The helper's explicit evidence destination is not an NSSavePanel
test. No user project, production launcher or physical pointer input is claimed.

Learned acceptance uses an explicit new --fixture-workspace and five separate
foreground operations: learned-prepare, learned-sam-edit, learned-sam-render,
learned-tapir-edit, learned-tapir-render. The prepared still and moving/occluded
video are geometric test data. Each edit operation runs actual checkpoint-backed
inference through shipped controls and saves/undoes/reopens the application;
each render operation restarts the real backend and independently decodes the
downloaded master. All inference/render jobs settle before a phase returns.
"""
from __future__ import annotations

import argparse
from array import array
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from deep_compositing import deep_capabilities, find_imaging_python
from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result

HERE = Path(__file__).resolve().parent
STUDIO_SOURCE = Path(sys.modules[Store.__module__].__file__).resolve().parent
LEARNED_PHASES = ("learned-prepare", "learned-sam-edit", "learned-sam-render", "learned-tapir-edit", "learned-tapir-render")
LEARNED_FIXTURE_KIND = "cinematicum-owned-native-learned-fixture-v1"

LEARNED_FIXTURE_CODE = r'''
import json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from test_learned_tracking import synthetic_motion
root=Path(sys.argv[2]); ffmpeg=sys.argv[3]
project,frames,masks,centers=synthetic_motion(root/'geometric')
common=[ffmpeg,'-v','error','-nostdin','-f','rawvideo','-pix_fmt','rgb24','-s','256x160','-r','12','-i','pipe:0','-an','-threads','1']
subprocess.run(common+['-frames:v','1',str(root/'still.png')],input=frames[0].tobytes(),capture_output=True,check=True,timeout=4)
subprocess.run(common+['-frames:v','10','-c:v','libx264','-preset','ultrafast','-crf','8','-pix_fmt','yuv420p','-movflags','+faststart',str(root/'video.mp4')],input=frames.tobytes(),capture_output=True,check=True,timeout=4)
(root/'oracle-mask.bin').write_bytes(masks[0].astype('uint8').tobytes())
print(json.dumps({'width':256,'height':160,'fps':12,'video_frames':10,'still_frames':4,'centers':centers}))
'''

FIXTURE_CODE = r'''
import sys,numpy as np,OpenEXR as exr
parts=[]
for view,red in [('left',.25),('right',.125)]:
    channels={}
    for name,values in {'Z':[1.,3.],'ZBack':[1.,3.],'A':[.5,1.],'R':[red,0.],
                         'G':[0.,0.],'B':[0.,1.],'object.id':[4000000001,4000000002],
                         'velocity.X':[-3.5,8.]}.items():
        array=np.empty((16,16),dtype=object)
        for position in np.ndindex(array.shape):
            array[position]=np.array(values,dtype=np.uint32 if name=='object.id' else np.float32)
        channels[name]=array
    parts.append(exr.Part({'type':exr.deepscanline,'compression':exr.ZIPS_COMPRESSION,
                          'name':'ENGINE_TEST_'+view,'view':view},channels))
exr.File(parts).write(sys.argv[1])
'''

INSPECT_CODE = r'''
import json,sys,numpy as np,OpenEXR as exr
checks={}
with exr.File(sys.argv[1],separate_channels=True) as f:
    checks['download_contains_two_actual_deep_views']=len(f.parts)==2 and [p.header.get('view') for p in f.parts]==['left','right'] and all(p.header['type']==exr.deepscanline for p in f.parts)
    checks['all_sample_counts_and_depths_preserved']=all(all(np.array_equal(p.channels['Z'].pixels[pos],[1.,3.]) and np.array_equal(p.channels['ZBack'].pixels[pos],[1.,3.]) for pos in np.ndindex((16,16))) for p in f.parts)
    checks['large_uint_object_ids_preserved_exactly']=all(p.channels['object.id'].pixels[0,0].dtype==np.uint32 and all(np.array_equal(p.channels['object.id'].pixels[pos],np.array([4000000001,4000000002],dtype=np.uint32)) for pos in np.ndindex((16,16))) for p in f.parts)
    checks['actual_channel_gain_only_changed_selected_right_branch']=all(np.array_equal(p.channels['R'].pixels[pos],[.25,0.]) for p in f.parts for pos in np.ndindex((16,16)))
    checks['new_half_auxiliary_channel_only_in_edited_branch']='custom.scalar' not in f.parts[0].channels and f.parts[1].channels['custom.scalar'].pixels[0,0].dtype==np.float16 and all(np.array_equal(f.parts[1].channels['custom.scalar'].pixels[pos],[1.5,1.5]) for pos in np.ndindex((16,16)))
    checks['other_auxiliary_and_alpha_values_preserved']=all(np.array_equal(p.channels['velocity.X'].pixels[pos],[-3.5,8.]) and np.array_equal(p.channels['A'].pixels[pos],[.5,1.]) for p in f.parts for pos in np.ndindex((16,16)))
print(json.dumps(checks))
'''


def run(binary, output, operation="deep"):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    downloads = output / "native_downloads"
    downloads.mkdir(exist_ok=True)
    began, deadline = time.monotonic(), time.monotonic() + 18
    result = {"passed": False, "operation": operation, "browser": "WKWebView",
              "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT", "checks": {},
              "scope": "Shipped Studio tools controls and actual owned workers; real WKDownload to an explicit evidence directory. NSSavePanel, physical pointer input, installed launcher and production-scale performance are not certified."}
    checks = result["checks"]

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The Studio tools acceptance exceeded its 18-second execution budget")
        return min(maximum, remaining)

    with tempfile.TemporaryDirectory(prefix="cinematicum-STUDIO-TOOLS-WEBKIT-TEST-") as temporary:
        scratch = Path(temporary)
        store = server = thread = project = None
        try:
            if operation != "deep":
                raise ValueError("This native acceptance phase is not implemented; no result is simulated.")
            caps = deep_capabilities()
            if not caps["available"]:
                raise RuntimeError(caps.get("reason", "Actual deep EXR runtime is unavailable"))
            python = find_imaging_python()
            source = scratch / "ENGINE_TEST_depth_multiview.exr"
            subprocess.run([python, "-I", "-B", "-c", FIXTURE_CODE, str(source)], check=True,
                           capture_output=True, text=True, timeout=budget(2, 13))
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            store = Store(scratch / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST Studio tools sentinel", "width": 16, "height": 16, "fps": 12})
            project = store.new_project({"name": "ENGINE TEST — native deep EXR", "width": 16, "height": 16, "fps": 12})
            fixture = {"operation": operation, "project_id": project["id"], "project_name": project["name"],
                       "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"],
                       "source_name": source.name, "source_sha256": source_hash}
            script = scratch / "StudioToolsSmoke.js"
            script.write_text((HERE / "macos/StudioToolsSmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps(fixture)), encoding="utf-8")

            class FixtureHandler(Handler):
                def do_GET(self):
                    if self.path == "/__engine_test__/deep-source":
                        try:
                            self.guard()
                            return self.file(source)
                        except Exception as exc:
                            return self.json(400, {"error": str(exc)})
                    return super().do_GET()
            server = Server(0, store)
            server.RequestHandlerClass = FixtureHandler
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            screenshot = output / f"ENGINE_TEST_studio_{operation}_native.png"
            native_timeout = budget(13.5, 2.1)
            process = subprocess.run([str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot),
                                      "--script", str(script), "--download-dir", str(downloads),
                                      "--timeout", str(round(native_timeout, 2))],
                                     capture_output=True, text=True, timeout=budget(native_timeout + .8, 1.2))
            ui = read_helper_result(process)
            result.update(ui=ui, helper_exit_code=process.returncode)
            if process.stderr:
                result["helper_stderr_tail"] = process.stderr[-1600:]
            checks["actual_native_controls_passed"] = process.returncode == 0 and ui.get("passed") is True
            checks["no_browser_or_download_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
            for step in ("select_exact_owned_fixture_project", "real_deep_file_input_two_views_and_editable_channel_graph",
                         "graph_apply_save_undo_redo_and_exact_project_reopen", "actual_deep_worker_preview_receipt_and_media_admission",
                         "clicked_real_exr_wkdownload"):
                checks[step] = step in ui.get("steps", [])
            if not checks["actual_native_controls_passed"]:
                raise RuntimeError(ui.get("error", "Native Studio tools controls failed"))
            directory = store.project_dir(project["id"])
            saved = store.get(project["id"])
            graph = saved.get("deep_compositing", {})
            checks["saved_graph_retains_both_views_and_numeric_edit"] = len(graph.get("nodes", [])) == 3 and graph.get("outputs") == ["source1", "channels1"] and graph["nodes"][2].get("scale", {}).get("R") == {"multiply": 2, "add": 0}
            with store.lock:
                jobs = copy.deepcopy([j for j in store.jobs.values() if j.get("project_id") == project["id"] and j.get("kind") == "deep-compositing"])
            checks["exactly_one_completed_actual_deep_job"] = len(jobs) == 1 and jobs[0]["state"] == "completed"
            if not checks["exactly_one_completed_actual_deep_job"]:
                raise RuntimeError("Native controls did not complete exactly one real deep worker")
            job = jobs[0]
            artifacts = directory / "deep/outputs" / job["id"]
            receipt = json.loads((artifacts / "receipt.json").read_text())
            checks["frozen_saved_graph_matches_executed_receipt"] = receipt["recipe"] == graph
            exr_bytes = (artifacts / "composite.exr").read_bytes()
            checks["actual_exr_hash_and_bytes_match_receipt_and_native_fetch"] = hashlib.sha256(exr_bytes).hexdigest() == receipt["artifacts"]["exr"]["sha256"] and len(exr_bytes) == ui.get("exr_bytes")
            native_downloads = ui.get("downloads", [])
            checks["one_completed_real_wkdownload"] = len(native_downloads) == 1 and native_downloads[0].get("state") == "completed"
            if checks["one_completed_real_wkdownload"]:
                path = Path(native_downloads[0].get("path", "")).resolve()
                checks["native_download_owned_destination"] = path.parent == downloads and path.is_file()
                checks["native_download_exact_exr_bytes_and_url"] = checks["native_download_owned_destination"] and path.read_bytes() == exr_bytes and native_downloads[0].get("url") == origin + ui.get("exr_url", "")
            else:
                checks["native_download_exact_exr_bytes_and_url"] = False
            inspected = subprocess.run([python, "-I", "-B", "-c", INSPECT_CODE, str(artifacts / "composite.exr")],
                                       check=True, capture_output=True, text=True, timeout=budget(1.4, .35))
            independent = json.loads(inspected.stdout)
            checks.update(independent)
            asset = next(a for a in saved["assets"] if a["id"] == ui["asset_id"])
            checks["admitted_srgb_preview_hash_matches_receipt"] = asset["sha256"] == receipt["artifacts"]["preview"]["sha256"] and asset["provenance"]["display_encoding"] == "sRGB"
            checks["native_preview_matches_independent_channel_composite"] = len(ui.get("preview_pixel", [])) == 4 and all(abs(a - b) <= 2 for a, b in zip(ui["preview_pixel"], [137, 0, 188, 255]))
            checks["admitted_original_exr_bytes_preserved"] = (directory / "deep/sources" / f"{source_hash}.exr").read_bytes() == source.read_bytes()
            checks["actual_native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            for name in ("composite.exr", "preview.png", "receipt.json"):
                shutil.copy2(artifacts / name, output / ("ENGINE_TEST_deep_" + name))
            result["source_identity"] = {"sha256": source_hash, "size": source.stat().st_size}
            result["executed_recipe"] = receipt["recipe"]
            result["runtime_versions"] = receipt["versions"]
            if not all(checks.values()):
                result["error"] = "Failed checks: " + ", ".join(k for k, value in checks.items() if not value)
        except Exception as exc:
            result["error"] = str(exc)
            if isinstance(exc, subprocess.CalledProcessError):
                result["process_error"] = str(exc.stderr)[-1800:]
        finally:
            if store and project:
                (output / f"ENGINE_TEST_studio_{operation}_saved_project.json").write_text(json.dumps(store.get(project["id"]), indent=2), encoding="utf-8")
                with store.lock:
                    owned_jobs = [copy.deepcopy(j) for j in store.jobs.values() if j.get("project_id") == project["id"]]
                (output / f"ENGINE_TEST_studio_{operation}_jobs.json").write_text(json.dumps(owned_jobs, indent=2), encoding="utf-8")
            if server:
                server.shutdown(); server.server_close()
            if thread:
                thread.join(timeout=.3)
            if store:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["phase_within_18_second_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    (output / f"ENGINE_TEST_studio_{operation}_native_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _learned_identity(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("The owned learned fixture/evidence must be a bounded regular file")
    value = path.read_bytes()
    return {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}


def _learned_manifest(directory):
    directory = Path(directory).absolute()
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError("The native learned fixture must not traverse a symlink")
    path = directory / "native-fixture.json"
    _learned_identity(path)
    manifest = json.loads(path.read_text())
    if manifest.get("kind") != LEARNED_FIXTURE_KIND or not re.fullmatch(r"[a-f0-9]{32}", manifest.get("acceptance_id", "")):
        raise ValueError("This is not the explicitly prepared native learned fixture")
    for backend in ("sam2", "tapir"):
        entry = manifest["projects"][backend]
        if not re.fullmatch(r"[a-f0-9]{32}", entry.get("project_id", "")):
            raise ValueError("Malformed owned fixture project identity")
        if entry.get("source_file") != ("still.png" if backend == "sam2" else "video.mp4") or not re.fullmatch(r"media/[a-f0-9]{32}\.(png|mp4)", entry.get("asset_path", "")):
            raise ValueError("Malformed synthetic source path in the native fixture")
        if _learned_identity(directory / "sources" / entry["source_file"]) != entry["source_identity"]:
            raise ValueError("The original synthetic source changed")
    if _learned_identity(directory / "sources/oracle-mask.bin") != manifest["oracle_identity"]:
        raise ValueError("The independently generated geometric oracle changed")
    # Store startup settles interrupted jobs. Refuse to open a prior unfinished
    # acceptance workspace, so a retry cannot silently rewrite its evidence.
    for job in (directory / "workspace/jobs").glob("*.json"):
        _learned_identity(job)
        if json.loads(job.read_text()).get("state") in {"queued", "running"}:
            raise ValueError("A prior owned native phase still has unfinished work; preserve it and prepare a new fixture")
    return directory, manifest


def run_learned(binary, output, operation, fixture_workspace):
    """One bounded native phase; the shared fixture is explicitly owned, never a user workspace."""
    from learned_tracking import find_learned_python

    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=True)
    report = output / f"ENGINE_TEST_studio_{operation}_native_report.json"
    if report.exists():
        raise ValueError("Preserve the previous native report and use a fresh output directory")
    began, deadline = time.monotonic(), time.monotonic() + 18
    result = {"passed": False, "operation": operation, "browser": "WKWebView", "checks": {},
              "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT",
              "scope": "Real source bytes and checkpoint inference through shipped controls, source-bound undoable application and backend restart/reopen. Render phases use actual WKDownload into an explicit evidence directory. This does not certify physical input, NSSavePanel, installed launcher, MPS, production footage or production-scale performance."}
    checks = result["checks"]
    store = server = thread = None
    project = fixture = directory = fence = None

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The learned native phase exceeded its 18-second execution budget")
        return min(maximum, remaining)

    def source_preserved():
        entry = fixture["projects"][backend]
        admitted = store.project_dir(project["id"]) / entry["asset_path"]
        return (_learned_identity(admitted) == entry["source_identity"]
                and _learned_identity(directory / "sources" / entry["source_file"]) == entry["source_identity"])

    try:
        if operation == "learned-prepare":
            directory = Path(fixture_workspace).absolute()
            if directory.exists() or any(path.is_symlink() for path in directory.parents):
                raise ValueError("Prepare requires a new explicit fixture directory without symlink parents")
            directory.mkdir(parents=True)
            sources = directory / "sources"; sources.mkdir()
            python, ffmpeg = find_learned_python(), shutil.which("ffmpeg")
            if not python or not ffmpeg:
                raise ValueError("The real managed learned runtime and FFmpeg are required")
            created = subprocess.run([python, "-I", "-B", "-c", LEARNED_FIXTURE_CODE, str(STUDIO_SOURCE), str(sources), ffmpeg],
                                     check=True, capture_output=True, text=True, timeout=budget(13, 2))
            geometric = json.loads(created.stdout)
            store = Store(directory / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST learned sentinel", "width": 256, "height": 160, "fps": 12})
            fixture = {"kind": LEARNED_FIXTURE_KIND, "acceptance_id": uuid.uuid4().hex,
                       "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"], "projects": {},
                       "geometry": geometric, "oracle_identity": _learned_identity(sources / "oracle-mask.bin")}
            for backend, name, source_name, count in (("sam2", "SAM image", "still.png", 4), ("tapir", "TAPIR video", "video.mp4", 10)):
                project = store.new_project({"name": "ENGINE TEST native " + name, "width": 256, "height": 160, "fps": 12})
                original = sources / source_name
                staged = directory / ("upload-" + source_name); shutil.copyfile(original, staged)
                asset = store.admit(project["id"], staged, "ENGINE_TEST_" + source_name)
                project = store.get(project["id"])
                project["clips"] = [{"id": "picture", "asset_id": asset["id"], "track": 0, "start": 0, "in": 0, "duration": count}]
                project["settings"].update(image_precision="high16", transparent_background=True)
                project = store.save(project["id"], project)
                fixture["projects"][backend] = {"project_id": project["id"], "project_name": project["name"],
                    "asset_id": asset["id"], "asset_path": asset["path"], "source_file": source_name,
                    "source_identity": _learned_identity(original), "source_kind": asset["kind"], "frames": count}
                checks[backend + "_immutable_source_admitted_exactly"] = source_preserved()
                checks[backend + "_genuine_source_kind"] = asset["kind"] == ("image" if backend == "sam2" else "video")
            (directory / "native-fixture.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
            checks["independent_geometric_oracle_has_exact_dimensions"] = fixture["oracle_identity"]["size"] == 256 * 160
            checks["two_distinct_owned_projects_and_sentinel"] = len({entry["project_id"] for entry in fixture["projects"].values()} | {sentinel["id"]}) == 3
            result["fixture_identity"] = _learned_identity(directory / "native-fixture.json")
            result["fixture_geometry"] = geometric
        else:
            directory, fixture = _learned_manifest(fixture_workspace)
            backend = "sam2" if operation.startswith("learned-sam-") else "tapir"
            editing = operation.endswith("-edit")
            entry = fixture["projects"][backend]
            result["fixture_identity"] = _learned_identity(directory / "native-fixture.json")
            store = Store(directory / "workspace")
            project = store.get(entry["project_id"])
            if len(project["clips"]) != 1 or project["clips"][0]["id"] != "picture":
                raise ValueError("The prepared project is no longer the exact single-clip fixture")
            checks["immutable_source_preserved_before_phase"] = source_preserved()
            if editing and (project["clips"][0].get("learned_bindings") or project["clips"][0].get("learned_recipe")):
                raise ValueError("This fixture already contains learned edits; preserve it and prepare a fresh acceptance workspace")
            fence_path = directory / (backend + "-edit-passed.json")
            if not editing:
                _learned_identity(fence_path)
                fence = json.loads(fence_path.read_text())
                if fence.get("passed") is not True or fence.get("acceptance_id") != fixture["acceptance_id"] or fence.get("clip") != project["clips"][0]:
                    raise ValueError("Render requires the exact saved clip from its successful prior native edit phase")
                result["prior_native_edit_identity"] = _learned_identity(fence_path)
            with store.lock:
                before_ids = set(store.jobs)
            js_fixture = {"operation": operation, "backend": backend, "project_id": project["id"], "project_name": project["name"],
                          "sentinel_id": fixture["sentinel_id"], "sentinel_name": fixture["sentinel_name"],
                          "source_sha256": entry["source_identity"]["sha256"], "clip_id": "picture", "frames": entry["frames"],
                          "corrections": [{"frame": frame, "x": fixture["geometry"]["centers"][frame][0] / 256,
                                           "y": fixture["geometry"]["centers"][frame][1] / 160} for frame in (4, 5, 6)]}
            script = output / "StudioToolsSmoke.js"
            script.write_text((HERE / "macos/StudioToolsSmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps(js_fixture)), encoding="utf-8")
            downloads = output / "native_downloads"; downloads.mkdir(exist_ok=False)
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True); thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            screenshot = output / f"ENGINE_TEST_studio_{operation}_native.png"
            native_timeout = budget(14, 2.3)
            process = subprocess.run([str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot),
                                      "--script", str(script), "--download-dir", str(downloads), "--timeout", str(round(native_timeout, 2))],
                                     capture_output=True, text=True, timeout=budget(native_timeout + .7, 1.5))
            ui = read_helper_result(process); result.update(ui=ui, helper_exit_code=process.returncode)
            if process.stderr: result["helper_stderr_tail"] = process.stderr[-1600:]
            checks["actual_native_controls_passed"] = process.returncode == 0 and ui.get("passed") is True
            checks["no_browser_or_download_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
            required = ["select_exact_owned_fixture_project", "actual_source_frame_and_canvas_prompts", "undoable_recipe_saved", "actual_checkpoint_result_without_silent_application", "applied_edit_undo_redo_and_exact_reopen"] if editing else ["select_exact_owned_fixture_project", "saved_binding_reopened_after_backend_restart", "native_export_dialog_completed_actual_ffv1_master", "clicked_real_native_master_download"]
            if editing and backend == "tapir": required += ["learned_occlusion_requires_explicit_corrections", "point_corrections_stay_bound_to_selected_query"]
            for step in required: checks[step] = step in ui.get("steps", [])
            if not checks["actual_native_controls_passed"]:
                raise RuntimeError(ui.get("error", "Native learned controls failed"))
            saved = store.get(project["id"]); clip = saved["clips"][0]
            with store.lock:
                actual_jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
            new_jobs = [job for job in actual_jobs if job["id"] not in before_ids]
            relevant = [job for job in new_jobs if job["kind"] == ("learned-tracking" if editing else "render")]
            checks["exactly_one_completed_actual_phase_job"] = len(relevant) == 1 and relevant[0]["state"] == "completed"
            if not checks["exactly_one_completed_actual_phase_job"]:
                raise ValueError("The native phase did not complete exactly one actual owned analysis/render job")
            active = [job for job in actual_jobs if job["state"] in {"queued", "running"} and job["kind"] not in {"frame-preview", "tracking-frame", "audio-source"}]
            checks["no_unfinished_durable_work_at_phase_completion"] = not active
            job = relevant[0]
            analysis_id = job["id"] if editing else fence["job_id"]
            artifacts = store.project_dir(project["id"]) / "learned/outputs" / analysis_id
            receipt = json.loads((artifacts / "receipt.json").read_text())
            measurement = json.loads((artifacts / "result.json").read_text())
            lock = json.loads((STUDIO_SOURCE / "learned-runtime-lock.json").read_text())
            checks["actual_pinned_checkpoint_and_immutable_source_bound"] = (receipt["checkpoint_sha256"] == lock["models"][backend]["sha256"]
                and receipt["source"]["sha256"] == entry["source_identity"]["sha256"] and receipt["backend"] == backend
                and receipt["source_stream"]["kind"] == entry["source_kind"])
            checks["all_actual_learned_artifacts_match_receipt"] = bool(receipt["artifacts"]) and all(
                record["filename"] in {"result.json", "preview.png", "mask.mkv"}
                and _learned_identity(artifacts / record["filename"]) == {"sha256": record["sha256"], "size": record["size"]}
                for record in receipt["artifacts"])
            bindings = clip.get("learned_bindings", [])
            checks["one_saved_source_bound_application_without_staleness"] = len(bindings) == 1 and not bindings[0].get("invalidated") and clip.get("learned_recipe") == receipt["recipe"]
            if backend == "sam2":
                graph = clip.get("compositor", {})
                nodes = graph.get("nodes", [])
                checks["real_alpha_mask_node_and_explicit_still_hold"] = any(node.get("type") == "alpha_mask" for node in nodes) and bool(bindings) and bindings[0].get("target", {}).get("hold_still") is True
                masks = [asset for asset in saved["assets"] if asset.get("provenance", {}).get("output_id") == analysis_id]
                checks["actual_generated_mask_admitted_once_without_losing_owned_artifact"] = len(masks) == 1 and masks[0]["sha256"] == measurement["mask_sha256"] == _learned_identity(artifacts / "mask.mkv")["sha256"]
            else:
                tracks = measurement["measurement"]["tracks"]
                samples = next(track["track"]["samples"] for track in tracks if track["id"] == "point_1")
                checks["actual_tapir_occlusion_and_reidentification"] = [sample["visible"] for sample in samples] == [True] * 4 + [False] * 3 + [True] * 3
                errors = [math.hypot(sample["x"] * 256 - fixture["geometry"]["centers"][sample["frame"]][0], sample["y"] * 160 - 85) for sample in samples if sample["visible"]]
                result["max_visible_point_error_pixels"] = max(errors)
                checks["actual_visible_points_follow_independent_geometry"] = len(errors) == 7 and max(errors) < 2.5
                checks["saved_tracking_has_only_explicit_source_bound_corrections"] = clip.get("tracking", {}).get("source", {}).get("learned_corrections") == js_fixture["corrections"]
            if editing:
                checks["no_master_render_or_download_was_faked_in_edit_phase"] = not [row for row in new_jobs if row["kind"] == "render"] and not ui.get("downloads")
                if all(checks.values()):
                    fence = {"passed": True, "acceptance_id": fixture["acceptance_id"], "job_id": analysis_id, "clip": clip,
                             "receipt_identity": _learned_identity(artifacts / "receipt.json"), "operation": operation}
            else:
                checks["exact_prior_saved_application_survived_backend_restart_and_render"] = clip == fence["clip"] and _learned_identity(artifacts / "receipt.json") == fence["receipt_identity"]
                actual_downloads = ui.get("downloads", [])
                checks["exactly_one_completed_real_wkdownload"] = len(actual_downloads) == 1 and actual_downloads[0].get("state") == "completed"
                if not checks["exactly_one_completed_real_wkdownload"]:
                    raise ValueError("The actual master WKDownload did not complete")
                download = actual_downloads[0]
                downloaded = Path(download.get("path", "")).resolve()
                checks["real_download_owned_destination_url_and_exact_render_hash"] = (downloaded.parent == downloads.resolve() and downloaded.is_file()
                    and download.get("url") == origin + ui.get("download_href", "")
                    and _learned_identity(downloaded)["sha256"] == job["result"]["sha256"])
                if not checks["real_download_owned_destination_url_and_exact_render_hash"]:
                    raise ValueError("The downloaded master does not match the real owned render")
                if backend == "sam2":
                    raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(downloaded), "-vf", "alphaextract", "-threads", "1", "-pix_fmt", "gray16le", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True, timeout=budget(2, .3)).stdout
                    alpha = array("H"); alpha.frombytes(raw)
                    if sys.byteorder != "little": alpha.byteswap()
                    plane = 256 * 160
                    checks["decoded_real_master_has_four_full_precision_alpha_frames"] = len(alpha) == 4 * plane and set(alpha) == {0, 65535}
                    checks["held_image_mask_exact_across_all_four_master_frames"] = len(alpha) == 4 * plane and all(alpha[offset * plane:(offset + 1) * plane] == alpha[:plane] for offset in range(1, 4))
                    oracle = (directory / "sources/oracle-mask.bin").read_bytes()
                    intersection = sum(bool(value) and bool(expected) for value, expected in zip(alpha[:plane], oracle))
                    union = sum(bool(value) or bool(expected) for value, expected in zip(alpha[:plane], oracle))
                    result["independent_cutout_iou"] = intersection / union if union else 0
                    checks["actual_cutout_matches_independent_geometric_foreground"] = result["independent_cutout_iou"] > .95
                else:
                    raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(downloaded), "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True, timeout=budget(2, .3)).stdout
                    plane = 256 * 160 * 3
                    checks["real_stabilized_master_decodes_exactly_ten_frames"] = len(raw) == plane * 10
                    centers = []
                    for frame in (0, 1, 8, 9):
                        pixels = raw[frame * plane:(frame + 1) * plane]
                        indices = [index // 3 for index in range(0, len(pixels), 3) if pixels[index] > 100 and pixels[index] > 1.8 * pixels[index + 1] and pixels[index] > 1.8 * pixels[index + 2]]
                        if len(indices) < 1000: raise ValueError("The independently visible foreground disappeared from the stabilized master")
                        centers.append([sum(index % 256 for index in indices) / len(indices), sum(index // 256 for index in indices) / len(indices)])
                    result["independent_stabilized_centroids"] = centers
                    checks["measured_stabilization_holds_independent_foreground_location"] = max(math.hypot(point[0] - centers[0][0], point[1] - centers[0][1]) for point in centers) < 2.5
            checks["immutable_source_preserved_after_phase"] = source_preserved()
            checks["actual_native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            result["source_identity"] = entry["source_identity"]
            result["checkpoint_sha256"] = receipt["checkpoint_sha256"]
            result["learned_output_id"] = analysis_id
            for name in ("receipt.json", "result.json", "preview.png"):
                shutil.copy2(artifacts / name, output / ("ENGINE_TEST_learned_" + name))
    except Exception as exc:
        result["error"] = str(exc)
        if isinstance(exc, subprocess.CalledProcessError): result["process_error"] = str(exc.stderr)[-1800:]
    finally:
        if server:
            server.shutdown(); server.server_close()
        if thread: thread.join(timeout=.3)
        if store:
            store.shutdown()
            if project:
                saved_path = directory / "workspace/projects" / project["id"] / "project.json"
                _learned_identity(saved_path)
                (output / "ENGINE_TEST_saved_project.json").write_bytes(saved_path.read_bytes())
            with store.lock:
                owned_jobs = [copy.deepcopy(job) for job in store.jobs.values()]
            (output / "ENGINE_TEST_owned_jobs.json").write_text(json.dumps(owned_jobs, indent=2), encoding="utf-8")
            checks["all_phase_jobs_terminal_after_owned_shutdown"] = all(job["state"] not in {"queued", "running"} for job in owned_jobs)
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    checks["phase_within_18_second_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if result["passed"] and operation.endswith("-edit"):
        (directory / (backend + "-edit-passed.json")).write_text(json.dumps(fence, indent=2), encoding="utf-8")
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--operation", choices=["deep", *LEARNED_PHASES], default="deep")
    parser.add_argument("--fixture-workspace", type=Path, help="Explicit new owned directory for learned-prepare, reused by its four bounded native phases")
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Real macOS WKWebView is required; native acceptance is not simulated."}))
        return 0
    if not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and pass its executable.")
    if args.operation in LEARNED_PHASES and args.fixture_workspace is None:
        parser.error("Learned phases require their explicit --fixture-workspace.")
    result = (run_learned(args.binary, args.output, args.operation, args.fixture_workspace)
              if args.operation in LEARNED_PHASES else run(args.binary, args.output, args.operation))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

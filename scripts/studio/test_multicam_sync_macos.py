#!/usr/bin/env python3
"""Actual multicamera synchronization/edit/render acceptance in bounded phases.

Every phase owns and closes its server, browser and jobs in <=18 seconds.
The fixture consists of independently generated synthetic ENGINE TEST movies.
Chromium may exercise this same coordinator, but never certifies native macOS.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

from install_macos import RUNTIME_FILES
import multicam_sync as sync
from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result

HERE = Path(__file__).resolve().parent
STUDIO_SOURCE = Path(sys.modules[Store.__module__].__file__).resolve().parent
KIND = "cinematicum-owned-native-multicam-sync-v1"
PHASES = ("prepare", "author", "synchronize", "render")
ID = re.compile(r"[a-f0-9]{32}")

PREPARE = r'''
from pathlib import Path
import json,sys,subprocess,shutil,hashlib
import numpy as np
root=Path(sys.argv[1]);root.mkdir();(root/'media').mkdir();(root/'truth').mkdir()
rng=np.random.default_rng(866973);rate=48000;count=12*rate;margin=3*rate
world=rng.normal(0,.17,20*rate);kernel=np.hanning(31);kernel/=kernel.sum();world=np.convolve(world,kernel,'same')
reference=world[margin:margin+count].astype('<f4')
positive=(.75*np.convolve(world[margin+11819:margin+11819+count],[.1,.8,.1],'same')+.08+rng.normal(0,.0007,count)).astype('<f4')
negative=(-.85*world[margin-7517:margin-7517+count]-.05+rng.normal(0,.0006,count)).astype('<f4')
wrong=rng.normal(0,.1,(count,2)).astype('<f4')
for name,values in [('reference',reference),('multi',positive),('negative',negative)]:
    (root/'truth'/f'{name}.f32le').write_bytes(values.tobytes())
for name,streams,color in [('reference',[np.column_stack([reference]*2)],'red'),('multi',[wrong,np.column_stack([wrong[:,0],positive])],'blue'),('negative',[np.column_stack([negative]*2)],'green')]:
    argv=[shutil.which('ffmpeg'),'-v','error','-nostdin','-threads','1','-filter_threads','1','-f','lavfi','-i',f'color=c={color}:s=64x48:r=24:d=12']
    for i,values in enumerate(streams):
        p=root/'truth'/f'{name}-stream-{i}.f32le';p.write_bytes(np.asarray(values,dtype='<f4').tobytes());argv += ['-f','f32le','-ar','48000','-ac','2','-i',str(p)]
    argv += ['-map','0:v']
    for i in range(len(streams)):argv += ['-map',f'{i+1}:a']
    argv += ['-t','12','-c:v','ffv1','-c:a','pcm_f32le',str(root/'media'/f'ENGINE_TEST_{name}.mkv')]
    subprocess.run(argv,check=True,capture_output=True,timeout=3)
print(json.dumps({'offsets':{'reference':0,'multi':11819,'negative':-7517},'frames':278,'samples':556000,'cut_frame':120}))
'''

INSPECT = r'''
import json,sys,subprocess,shutil
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]);movie=Path(sys.argv[2]);count=556000;cut=120*2000
def ff(args):return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-threads','1','-filter_threads','1',*args],check=True,capture_output=True,timeout=3).stdout
reference=np.fromfile(root/'truth/reference.f32le',dtype='<f4');positive=np.fromfile(root/'truth/multi.f32le',dtype='<f4')
expected=np.concatenate([reference[11819:11819+cut],positive[cut:count]])
pcm=np.frombuffer(ff(['-i',str(movie),'-map','0:a:0','-ar','48000','-ac','2','-f','f32le','pipe:1']),dtype='<f4').reshape(-1,2)
pixels=np.frombuffer(ff(['-i',str(movie),'-map','0:v:0','-pix_fmt','rgb24','-f','rawvideo','pipe:1']),dtype=np.uint8).reshape(-1,48,64,3)
means=pixels.mean(axis=(1,2));r=means[:120];b=means[120:]
print(json.dumps({'sample_frames':len(pcm),'expected_sample_frames':len(expected),'frames':len(pixels),
  'max_pcm_error':float(np.max(np.abs(pcm-expected[:,None]))) if len(pcm)==len(expected) else None,
  'every_reference_frame_red':bool(len(r)==120 and (r[:,0]>220).all() and (r[:,2]<15).all()),
  'every_second_camera_frame_blue':bool(len(b)==158 and (b[:,2]>220).all() and (b[:,0]<15).all()),
  'boundary_frame_means':[means[119].tolist(),means[120].tolist()]}))
'''


def identity(path, maximum=40 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("Acceptance requires a bounded regular file")
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def safe_directory(path, *, new=False):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("The explicit fixture or evidence path traverses a symlink")
    if new:
        if path.exists():
            raise ValueError("Preserve the previous attempt and choose a new directory")
        path.mkdir(parents=True)
    elif not path.is_dir():
        raise ValueError("The explicit prepared fixture is absent")
    return path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def read_json(path):
    identity(path)
    return json.loads(Path(path).read_text())


def source_inventory():
    names = set(RUNTIME_FILES) | {"install_macos.py", "test_multicam_sync_macos.py", "test_multicam_sync_browser.cjs",
                                "test_editing_ui_macos.py", "macos/MulticamSyncSmoke.js", "macos/SmokeTest.swift"}
    for path in (STUDIO_SOURCE / "web").rglob("*"):
        if path.is_symlink():
            raise ValueError("Shipped web source must not contain symlinks")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.name != ".DS_Store":
            names.add(path.relative_to(STUDIO_SOURCE).as_posix())
    return {name: identity(STUDIO_SOURCE / name) for name in sorted(names)}


def _fixture(path):
    root = safe_directory(path)
    fixture = read_json(root / "native-fixture.json")
    if fixture.get("kind") != KIND or any(not ID.fullmatch(fixture.get(k, "")) for k in ("acceptance_id", "project_id", "sentinel_id")):
        raise ValueError("The fixture is not an explicitly prepared multicamera acceptance project")
    expected = ["ENGINE_TEST_reference.mkv", "ENGINE_TEST_multi.mkv", "ENGINE_TEST_negative.mkv"]
    if [row.get("name") for row in fixture.get("cameras", [])] != expected or {p.name for p in (root / "media").iterdir()} != set(expected):
        raise ValueError("The fixture camera namespace changed")
    if any(identity(root / "media" / row["name"]) != row["identity"] for row in fixture["cameras"]):
        raise ValueError("An original camera file changed")
    if {p.name: identity(p) for p in (root / "truth").iterdir()} != fixture["truth"]:
        raise ValueError("Independent sample ground truth changed")
    for path in (root / "workspace/jobs").glob("*.json"):
        job = read_json(path)
        if not ID.fullmatch(path.stem) or job.get("id") != path.stem or job.get("project_id") not in {fixture["project_id"], fixture["sentinel_id"]}:
            raise ValueError("The fixture contains an unexpected durable job")
        if job.get("state") not in {"completed", "failed", "cancelled"}:
            raise ValueError("The preceding attempt has pending work; preserve it and prepare a new fixture")
    return root, fixture


def _sources_preserved(root, project, fixture):
    expected = {row["name"]: row["identity"] for row in fixture["cameras"]}
    return len(project["assets"]) == 3 and all(
        asset["kind"] == "video" and (asset["width"], asset["height"]) == (64, 48)
        and re.fullmatch(r"media/[a-f0-9]{32}\.mkv", asset["path"])
        and identity(root / "workspace/projects" / project["id"] / asset["path"]) == expected.get(asset["name"])
        and asset["sha256"] == expected[asset["name"]]["sha256"] for asset in project["assets"])


def _download_identity(download, output, transport):
    name = download.get("suggested_filename", "")
    target = Path(download.get("path", "")).absolute()
    valid_name = bool(re.fullmatch(r"ENGINE_TEST_[A-Fa-f0-9-]{36}_" + re.escape(name), target.name)) if transport == "WKWebView" else target.name == name
    if not name or Path(name).name != name or target.parent != output / "native_downloads" or not valid_name or download.get("state") != "completed":
        raise ValueError("An actual download escaped its owned evidence destination")
    return target, identity(target)


def run(binary, output, operation, fixture_workspace, expected_sources, *, transport="WKWebView"):
    began = time.monotonic(); deadline = began + 18
    output = safe_directory(output, new=True)
    result = {"kind": KIND, "operation": operation, "browser": transport, "passed": False,
              "native_certified": operation != "prepare" and transport == "WKWebView" and sys.platform == "darwin",
              "fixture": "SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT", "checks": {},
              "scope": "Actual UI media admission, selected stream/channel sample measurement, atomic measured edit, undo/redo/save/reopen, camera cut, explicit playback mapping, ProRes/PCM export and exact owned downloads. No physical input, save chooser, installed launcher, production footage or broad session stability is certified."}
    checks = result["checks"]; store = server = thread = root = fixture = project = None; fence = None

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The multicamera phase exhausted its 18-second foreground budget")
        return min(maximum, remaining)

    try:
        if operation not in PHASES:
            raise ValueError("Unknown multicamera phase")
        before = source_inventory(); result["source_before"] = before
        if before != expected_sources:
            raise ValueError("Runtime, web or acceptance source differs from the frozen inventory")
        checks["source_matches_explicit_frozen_inventory"] = True
        if operation == "prepare":
            root = Path(fixture_workspace).absolute()
            if root.exists() or any(p.is_symlink() for p in (root, *root.parents)):
                raise ValueError("Prepare requires a new explicit fixture destination")
            root.parent.mkdir(parents=True, exist_ok=True)
            capabilities = sync.sync_capabilities()
            if not capabilities.get("available"):
                raise RuntimeError(capabilities.get("reason", "Actual NumPy correlation runtime is unavailable"))
            prepared = subprocess.run([capabilities["python"], "-I", "-B", "-c", PREPARE, str(root)],
                                      capture_output=True, text=True, check=True, timeout=budget(11, 2), env=sync._environment())
            truth = json.loads(prepared.stdout)
            store = Store(root / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST multicamera sentinel", "width": 64, "height": 48, "fps": 24})
            project = store.new_project({"name": "ENGINE TEST measured camera synchronization", "width": 64, "height": 48, "fps": 24})
            fixture = {"kind": KIND, "acceptance_id": uuid.uuid4().hex, "project_id": project["id"], "project_name": project["name"],
                       "sentinel_id": sentinel["id"], "sentinel_name": sentinel["name"], "expected": truth,
                       "cameras": [{"name": name, "identity": identity(root / "media" / name)} for name in
                                   ("ENGINE_TEST_reference.mkv", "ENGINE_TEST_multi.mkv", "ENGINE_TEST_negative.mkv")],
                       "truth": {p.name: identity(p) for p in (root / "truth").iterdir()}}
            write_json(root / "native-fixture.json", fixture)
            checks["three_independent_cameras_with_subframe_signed_offsets_and_wrong_default_stream"] = truth == {"offsets": {"reference": 0, "multi": 11819, "negative": -7517}, "frames": 278, "samples": 556000, "cut_frame": 120}
            checks["fresh_project_contains_no_media_edit_or_measurement"] = not project["assets"] and not project["clips"] and not project.get("multicam_groups")
        else:
            root, fixture = _fixture(fixture_workspace)
            prior_path = root / (PHASES[PHASES.index(operation) - 1] + "-passed.json")
            prior = read_json(prior_path)
            if prior.get("passed") is not True or prior.get("acceptance_id") != fixture["acceptance_id"] or prior.get("source_inventory") != before:
                raise ValueError("The prior actual phase does not certify this exact fixture/source")
            if (root / (operation + "-passed.json")).exists():
                raise ValueError("This phase already passed; preserve it and use a new complete fixture for repetition")
            persisted = root / "workspace/projects" / fixture["project_id"] / "project.json"
            if identity(persisted) != prior["saved_project_identity"]:
                raise ValueError("The saved project changed after its previous accepted phase")
            result["prior_phase_identity"] = identity(prior_path); result["helper_identity"] = identity(binary)
            store = Store(root / "workspace"); project = store.get(fixture["project_id"])
            if project["name"] != fixture["project_name"] or store.get(fixture["sentinel_id"])["name"] != fixture["sentinel_name"]:
                raise ValueError("The fixture project or sentinel identity changed")
            initial = copy.deepcopy(project)
            with store.lock:
                jobs_before = set(store.jobs)
            script = output / "MulticamSyncSmoke.js"
            script.write_text((HERE / "macos/MulticamSyncSmoke.js").read_text().replace("/* ENGINE_TEST_CONFIG */ {}", json.dumps({**fixture, "operation": operation})))
            result["executed_javascript_identity"] = identity(script)
            downloads = output / "native_downloads"; downloads.mkdir()

            class FixtureHandler(Handler):
                def do_GET(self):
                    match = re.fullmatch(r"/__engine_test__/camera/([0-2])", self.path)
                    if match:
                        try:
                            self.guard(); row = fixture["cameras"][int(match[1])]; camera = root / "media" / row["name"]
                            if identity(camera) != row["identity"]:
                                raise ValueError("The original fixture camera changed")
                            return self.file(camera)
                        except Exception as exc:
                            return self.json(400, {"error": str(exc)})
                    return super().do_GET()

            server = Server(0, store); server.RequestHandlerClass = FixtureHandler
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .025}, daemon=True); thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"; screenshot = output / "ENGINE_TEST_multicam_native.png"
            helper_timeout = budget(14.8, 2.5)
            argv = [str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot),
                    "--script", str(script), "--download-dir", str(downloads), "--timeout", str(round(helper_timeout, 2))]
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=budget(helper_timeout + .25, 2.2))
            except subprocess.TimeoutExpired:
                # This foreground invocation owns this process group. Contain
                # only these children; never signal an arbitrary existing app.
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=.4)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); stdout, stderr = process.communicate(timeout=.3)
                raise TimeoutError("The owned browser exceeded its foreground phase budget")
            completed = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
            ui = read_helper_result(completed); result.update(ui=ui, helper_exit_code=completed.returncode)
            write_json(output / "ENGINE_TEST_browser_result.json", ui)
            if completed.stderr:
                result["helper_stderr_tail"] = completed.stderr[-1600:]
            checks["actual_shipped_controls_passed"] = completed.returncode == 0 and ui.get("passed") is True
            checks["no_browser_or_download_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
            required = {
                "author": ["three_original_camera_files_imported_through_shipped_input", "import_did_not_silently_assemble_a_cut", "admitted_sources_saved_and_reopened"],
                "synchronize": ["selected_nondefault_stream_channel_and_signed_offsets_measured", "three_actual_waveforms_drawn_without_silent_edit", "source_sample_precision_and_default_playback_mix_preserved", "one_undo_redo_save_and_reopen_of_synchronized_edit", "three_real_measurement_downloads_requested"],
                "render": ["saved_measured_group_survived_backend_restart", "camera_switch_at_frame_120_preserved_sample_alignment", "analysis_did_not_change_mix_and_explicit_playback_mapping_saved", "actual_prores_pcm_render_and_download_requested"],
            }[operation]
            checks.update({name: name in ui.get("steps", []) for name in required})
            if not checks["actual_shipped_controls_passed"]:
                raise RuntimeError(ui.get("error", "Actual multicamera controls failed"))
            project = store.get(fixture["project_id"])
            checks["admitted_source_cameras_preserve_exact_original_bytes"] = _sources_preserved(root, project, fixture)
            with store.lock:
                jobs = [copy.deepcopy(j) for key, j in store.jobs.items() if key not in jobs_before]
            if operation == "author":
                checks["no_analysis_render_or_timeline_edit_on_import"] = not project["clips"] and not project.get("multicam_groups") and not any(j["kind"] in {"multicam-sync", "render"} for j in jobs) and not ui.get("downloads")
            elif operation == "synchronize":
                measured_jobs = [j for j in jobs if j["kind"] == "multicam-sync"]
                checks["exactly_one_owned_completed_measurement_job"] = len(measured_jobs) == 1 and measured_jobs[0]["state"] == "completed" and measured_jobs[0]["id"] == ui.get("job_id")
                if not checks["exactly_one_owned_completed_measurement_job"]:
                    raise ValueError("The phase did not own exactly one actual measurement job")
                job = measured_jobs[0]; measured = job["result"]; result["job_id"] = job["id"]
                directory = store.project_dir(project["id"]) / "multicam-sync/outputs" / job["id"]
                receipt = read_json(directory / "receipt.json")
                result["artifacts"] = {name: identity(directory / name) for name in sync.artifact_names(3)}
                checks["complete_artifact_inventory_matches_actual_receipt"] = {p.name for p in directory.iterdir()} == sync.artifact_names(3) and all(result["artifacts"][name] == value for name, value in receipt["artifacts"].items())
                checks["receipt_binds_exact_worker_and_coordinator_sources"] = receipt["implementation_sha256"] == {name: before[name]["sha256"] for name in ("multicam_sync.py", "multicam_sync_worker.py")}
                asset_names = {a["id"]: a["name"].removeprefix("ENGINE_TEST_").removesuffix(".mkv") for a in project["assets"]}
                checks["selected_samples_are_bit_identical_to_independent_ground_truth"] = all((directory / row["sample_file"]).read_bytes() == (root / "truth" / (asset_names[row["asset_id"]] + ".f32le")).read_bytes() for row in receipt["sources"])
                group = project["multicam_groups"][0]; ref = next(a for a in group["synchronization"]["angles"] if asset_names[a["asset_id"]] == "reference")
                checks["durable_group_keeps_subframe_reference_offset_and_common_window"] = ref["source_in_samples"] == 11819 and project["clips"][0]["in"] == 11819 / 2000 and project["clips"][0]["duration"] == 278 and group["synchronization"]["receipt_sha256"] == result["artifacts"]["receipt.json"]["sha256"]
                rows = ui.get("downloads", []); requested = {r["name"]: r["url"] for r in ui.get("clicked_downloads", [])}; names = {"analysis.json", "waveforms.json", "receipt.json"}
                valid = len(rows) == 3 and set(requested) == names; seen = set()
                for row in rows:
                    target, digest = _download_identity(row, output, transport); name = row["suggested_filename"]
                    valid = valid and name in names and name not in seen and row["url"] == origin + requested.get(name, "") and digest == result["artifacts"].get(name); seen.add(name)
                checks["three_actual_downloads_match_owned_receipt_bytes"] = bool(valid and seen == names)
            else:
                checks["measurement_artifacts_survive_backend_restart_and_camera_edit"] = all(identity(store.project_dir(project["id"]) / "multicam-sync/outputs" / prior["job_id"] / name) == digest for name, digest in prior["artifacts"].items())
                renders = [j for j in jobs if j["kind"] == "render"]
                checks["one_owned_actual_prores_pcm_render"] = len(renders) == 1 and renders[0]["state"] == "completed" and renders[0]["result"]["profile"] == "prores" and renders[0]["project_id"] == project["id"]
                if not checks["one_owned_actual_prores_pcm_render"]:
                    raise ValueError("The phase did not own one completed ProRes/PCM render")
                job = renders[0]; rows = ui.get("downloads", [])
                if len(rows) != 1:
                    raise ValueError("The actual rendered movie download did not complete exactly once")
                movie, digest = _download_identity(rows[0], output, transport)
                expected_movie = store.project_dir(project["id"]) / "exports" / job["result"]["filename"]
                checks["downloaded_movie_matches_exact_completed_job_bytes"] = digest == identity(expected_movie) and digest["sha256"] == job["result"]["sha256"] and rows[0]["url"] == origin + ui["download_href"] and rows[0]["suggested_filename"] == ui["download_name"] == job["result"]["filename"]
                capabilities = sync.sync_capabilities()
                inspected = subprocess.run([capabilities["python"], "-I", "-B", "-c", INSPECT, str(root), str(movie)],
                                           capture_output=True, text=True, check=True, timeout=budget(3, .5), env=sync._environment())
                metrics = json.loads(inspected.stdout); result["independent_media_measurements"] = metrics
                checks["all_278_decoded_frames_show_the_correct_camera_and_cut_boundary"] = metrics["frames"] == 278 and metrics["every_reference_frame_red"] and metrics["every_second_camera_frame_blue"]
                checks["all_556000_stereo_sample_frames_match_independent_source_trim_and_mapping"] = metrics["sample_frames"] == metrics["expected_sample_frames"] == 556000 and metrics["max_pcm_error"] < 1 / 32768 + 1e-6
                checks["render_did_not_change_saved_camera_edit"] = project["multicam_groups"] == initial["multicam_groups"] and len(project["clips"]) == 2 and project["clips"][1]["start"] == 120
                result.update(render_job_id=job["id"], movie_identity=digest, job_id=prior["job_id"], artifacts=prior["artifacts"])
            checks["actual_browser_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    except Exception as exc:
        result["error"] = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            result["process_error"] = str(exc.stderr)[-2000:]
    finally:
        if server:
            server.shutdown(); server.server_close()
        if thread:
            thread.join(timeout=.3)
        if store:
            store.shutdown()
            with store.lock:
                jobs = copy.deepcopy(list(store.jobs.values()))
            checks["all_owned_jobs_terminal_after_shutdown"] = all(j["state"] not in {"queued", "running"} for j in jobs)
            write_json(output / "ENGINE_TEST_owned_jobs.json", jobs)
        if root and fixture and project:
            persisted = root / "workspace/projects" / fixture["project_id"] / "project.json"
            result["saved_project_identity"] = identity(persisted); (output / "ENGINE_TEST_saved_project.json").write_bytes(persisted.read_bytes())
            checks["independent_original_media_and_sample_truth_unchanged"] = all(identity(root / "media" / row["name"]) == row["identity"] for row in fixture["cameras"]) and {p.name: identity(p) for p in (root / "truth").iterdir()} == fixture["truth"]
            fence = {"passed": True, "acceptance_id": fixture["acceptance_id"], "operation": operation, "saved_project_identity": result["saved_project_identity"], "source_inventory": result.get("source_before")}
            if result.get("job_id"):
                fence.update(job_id=result["job_id"], artifacts=result["artifacts"])
        result["source_after"] = source_inventory(); checks["runtime_web_and_acceptance_source_unchanged"] = result.get("source_before") == result["source_after"]
    result["elapsed_seconds"] = round(time.monotonic() - began, 3); checks["phase_within_18_second_bound"] = result["elapsed_seconds"] < 18
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    if not result["passed"] and "error" not in result:
        result["error"] = "Failed checks: " + ", ".join(k for k, v in checks.items() if not v)
    report = output / "ENGINE_TEST_multicam_native_report.json"; write_json(report, result)
    if result["passed"] and fence:
        fence["report_identity"] = identity(report); write_json(root / (operation + "-passed.json"), fence)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operation", choices=PHASES, required=True); parser.add_argument("--fixture-workspace", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"passed": False, "reason": "Actual macOS WKWebView is required; native acceptance is never simulated."})); return 1
    result = run(args.binary, args.output, args.operation, args.fixture_workspace, read_json(args.source_manifest))
    print(json.dumps({"passed": result["passed"], "operation": args.operation, "checks": len(result["checks"]), "elapsed_seconds": result["elapsed_seconds"], "error": result.get("error"), "report": str(args.output / "ENGINE_TEST_multicam_native_report.json")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

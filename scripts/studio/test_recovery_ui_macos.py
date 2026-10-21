#!/usr/bin/env python3
"""Two independently launched WKWebViews prove recovery across a restart.

Run checkpoint then recover with the same --output. Each command owns only its
ENGINE TEST workspace and starts/stops its own server and browser helper.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time

from server import Store, Server
from engine import probe_media


def run(binary, output, stage):
    output = Path(output).resolve();output.mkdir(parents=True, exist_ok=True)
    workspace = output / "ENGINE_TEST_recovery_workspace"
    if stage == "checkpoint" and workspace.exists():
        raise ValueError("Use a fresh ENGINE TEST output directory for the checkpoint stage.")
    if stage == "recover" and not workspace.is_dir():
        raise ValueError("Run the checkpoint stage first.")
    store = Store(workspace);httpd = None;worker = None
    report = {"passed": False, "stage": stage, "fixture": "Synthetic ENGINE TEST media, not a film"}
    started = time.monotonic()
    try:
        if stage == "checkpoint":
            p = store.new_project({"name": "ENGINE TEST recovery", "width": 160, "height": 90, "fps": 24})
            fixture = output / "ENGINE_TEST_recovery_source.mp4"
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "testsrc2=s=160x90:r=24:d=0.5", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(fixture)],
                           capture_output=True, check=True, timeout=3)
            store.admit(p["id"], fixture, "ENGINE TEST recovery source.mp4", {"fixture": "ENGINE TEST"})
            (output / "ENGINE_TEST_project_id.txt").write_text(p["id"])
        else:
            p = store.get((output / "ENGINE_TEST_project_id.txt").read_text())
        before = (store.project_dir(p["id"]) / "project.json").read_bytes()
        script = output / ("ENGINE_TEST_recovery_" + stage + ".js")
        script.write_text("const RECOVERY_TEST=" + json.dumps({"stage": stage}) + ";\n" +
                          Path(__file__).with_name("macos").joinpath("RecoverySmoke.js").read_text())
        httpd = Server(0, store)
        worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": .05}, daemon=True);worker.start()
        result = subprocess.run([str(Path(binary).resolve()), "--url", "http://127.0.0.1:" + str(httpd.server_port),
                                 "--output", str(output / ("ENGINE_TEST_recovery_" + stage + ".png")),
                                 "--script", str(script), "--timeout", "13"], capture_output=True, text=True, timeout=15)
        ui = next((json.loads(line) for line in reversed(result.stdout.splitlines()) if line.startswith("{") and '"passed"' in line), None)
        if ui is None:raise RuntimeError("Native helper returned no result: " + result.stderr[-1000:])
        report["ui"] = ui
        saved = store.get(p["id"]);listing = store.recovery(p["id"])
        checks = {"native_controls": result.returncode == 0 and ui.get("passed") is True}
        if stage == "checkpoint":
            checks["saved_project_bytes_unchanged"] = before == (store.project_dir(p["id"]) / "project.json").read_bytes()
            checks["one_complete_durable_draft"] = len(listing["drafts"]) == 1 and listing["drafts"][0]["clips"] == listing["drafts"][0]["titles"] == 1
            checks["saved_timeline_still_empty"] = not saved["clips"] and not saved["titles"]
        else:
            checks["recovered_objects_saved"] = len(saved["clips"]) == len(saved["titles"]) == 1 and saved["titles"][0]["text"] == "ENGINE TEST recovery title"
            checks["real_raster_title"] = bool(saved["titles"] and saved["titles"][0].get("asset_id"))
            jobs = [j for j in store.jobs.values() if j.get("kind") == "render" and j.get("state") == "completed"]
            checks["actual_movie_rendered"] = len(jobs) == 1
            if jobs:
                movie = store.project_dir(p["id"]) / "exports" / jobs[0]["result"]["filename"]
                metadata = probe_media(movie)
                checks["actual_movie_clock"] = metadata["frames"] == 12 and (metadata["width"], metadata["height"]) == (160, 90)
                report["media"] = metadata
        report.update(checks=checks, passed=all(checks.values()))
    except Exception as error:
        report["error"] = str(error)
    finally:
        if httpd:httpd.shutdown();httpd.server_close()
        if worker:worker.join()
        store.shutdown()
    report["elapsed_seconds"] = time.monotonic() - started
    (output / ("ENGINE_TEST_recovery_" + stage + "_result.json")).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report));return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser();parser.add_argument("--binary", required=True);parser.add_argument("--output", required=True);parser.add_argument("--stage", choices=("checkpoint", "recover"), required=True)
    args = parser.parse_args();raise SystemExit(run(args.binary, args.output, args.stage))

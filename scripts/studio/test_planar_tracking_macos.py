#!/usr/bin/env python3
"""Native measurement/apply/undo/save/reopen/render with retained diagnostics.

The isolated ENGINE TEST workspace is retained under the explicit evidence
output directory, including failed runs. No owner project or app is closed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from urllib.request import urlopen

from planar_tracking import planar_capabilities
from server import Server, Store
from test_editing_ui_macos import read_helper_result
from test_planar_tracking import FRAMES, HEIGHT, WIDTH, build_fixture, ffmpeg


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")


def run(binary, output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);began=time.monotonic()
    runtime=planar_capabilities()
    if not runtime.get("available"):
        result={"passed":False,"runtime":runtime,"error":"Native planar acceptance requires the real installed tracking runtime"}
        write_json(output/"result.json",result);print(json.dumps(result));return 1
    # Deliberately persistent and unique: another test or a failure cannot erase
    # the measured source, saved edit, job snapshots, helper logs or prior run.
    root=Path(tempfile.mkdtemp(prefix="ENGINE_TEST_planar-",dir=output))
    worker_root=root/"workers";worker_root.mkdir()
    prior_tempdir=tempfile.tempdir;tempfile.tempdir=str(worker_root)
    store=server=thread=None;ui={};receipt={};native_returncode=None;evidence_errors=[]
    checks={name:False for name in (
        "real_wk_workflow","background_stabilization_persisted","editable_image_pin_persisted",
        "no_stale_motion_released","undo_restored_source_range","actual_movie_frame_count",
        "pin_visible_in_both_captured_frames","pin_follows_stabilized_plane_in_actual_movie",
        "actual_worker_measurement_receipt","measurement_matches_admitted_bytes")}
    result={"passed":False,"checks":checks,"runtime":runtime,"receipt":receipt,"workspace":str(root),
            "fixture":"SYNTHETIC ENGINE TEST — NOT PRODUCTION MEDIA",
            "bounds_seconds":{"workflow":120,"export":60,"native_helper":130,"subprocess":140}}
    try:
        fixture=build_fixture(root);store=Store(root/"store")
        sentinel=store.new_project({"name":"ENGINE TEST sentinel","width":WIDTH,"height":HEIGHT,"fps":12})
        project=store.new_project({"name":"ENGINE TEST — native planar motion","width":WIDTH,"height":HEIGHT,"fps":12})
        for asset in fixture["assets"]:store.admit(project["id"],root/asset["path"],asset["name"])
        script=root/"planar-workflow.js"
        script.write_text("const PLANAR_TEST="+json.dumps({"project_id":project["id"],"sentinel_id":sentinel["id"]})+";\n"+
                          (Path(__file__).parent/"macos/PlanarTrackingSmoke.js").read_text(),encoding="utf-8")
        server=Server(0,store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        command=[str(Path(binary).resolve()),"--url",f"http://127.0.0.1:{server.server_port}",
                 "--output",str(output/"planar.png"),"--timeout","130","--script",str(script)]
        write_json(root/"native-command.json",command)
        try:
            process=subprocess.run(command,capture_output=True,text=True,timeout=140)
            native_returncode=process.returncode
            stdout,stderr=process.stdout,process.stderr
        except subprocess.TimeoutExpired as error:
            stdout=error.stdout or "";stderr=error.stderr or ""
            if isinstance(stdout,bytes):stdout=stdout.decode("utf-8",errors="replace")
            if isinstance(stderr,bytes):stderr=stderr.decode("utf-8",errors="replace")
            stderr+="\nNative helper exceeded the 140-second subprocess bound.\n"
            process=subprocess.CompletedProcess(command,-1,stdout,stderr);native_returncode=-1
        (root/"native.stdout.log").write_text(stdout,encoding="utf-8")
        (root/"native.stderr.log").write_text(stderr,encoding="utf-8")
        try:ui=read_helper_result(process)
        except RuntimeError as error:ui={"passed":False,"error":str(error)}
        saved=store.get(project["id"]);write_json(output/"project.json",saved)
        # An outer native deadline may preclude a script result. Persisted modes
        # still supply useful partial evidence; real_wk_workflow remains false.
        def saved_clip(key, mode):
            return next((clip for clip in saved["clips"] if clip["id"]==ui.get(key)),{}) if ui.get(key) else next(
                (clip for clip in saved["clips"] if clip.get("planar_motion",{}).get("mode")==mode),{})
        background=saved_clip("clip_id","stabilize");pin=saved_clip("pin_id","corner_pin")
        checks.update(real_wk_workflow=process.returncode==0 and ui.get("passed") is True,
                      background_stabilization_persisted=background.get("planar_motion",{}).get("mode")=="stabilize",
                      editable_image_pin_persisted=pin.get("planar_motion",{}).get("mode")=="corner_pin",
                      no_stale_motion_released=bool(background and pin) and all(not c.get("planar_motion",{}).get("invalidated") for c in saved["clips"]),
                      undo_restored_source_range=background.get("duration")==FRAMES and background.get("start")==0 and pin.get("start")==0)
        if ui.get("download_href"):
            with urlopen(f"http://127.0.0.1:{server.server_port}"+ui["download_href"],timeout=15) as response:movie=response.read()
            movie_path=output/"ENGINE_TEST_measured_planar.mov";movie_path.write_bytes(movie)
            raw=ffmpeg(["-i",str(movie_path),"-f","rawvideo","-pix_fmt","rgb24","-threads","1","pipe:1"])
            checks["actual_movie_frame_count"]=len(raw)==WIDTH*HEIGHT*3*FRAMES
            centers=[]
            for frame in (0,FRAMES-1):
                picture=raw[frame*WIDTH*HEIGHT*3:(frame+1)*WIDTH*HEIGHT*3]
                pixels=[(i//3%WIDTH,i//3//WIDTH) for i in range(0,len(picture),3)
                        if picture[i]>180 and picture[i+1]<65 and picture[i+2]>180]
                if pixels:centers.append([sum(x for x,_ in pixels)/len(pixels),sum(y for _,y in pixels)/len(pixels)])
            checks["pin_visible_in_both_captured_frames"]=len(centers)==2
            checks["pin_follows_stabilized_plane_in_actual_movie"]=len(centers)==2 and all(abs(a-b)<.8 for a,b in zip(centers[0],centers[1]))
            receipt.update(movie_sha256=hashlib.sha256(movie).hexdigest(),movie_bytes=len(movie),pin_centers=centers)
        if ui.get("measurements"):
            with urlopen(f"http://127.0.0.1:{server.server_port}"+ui["measurements"],timeout=10) as response:measured=response.read()
            track=json.loads(measured);(output/"measurement.json").write_bytes(measured)
            checks["actual_worker_measurement_receipt"]=track.get("backend")=="opencv-lk-ransac" and len(track.get("samples",[]))==FRAMES and all(s["visible"] for s in track["samples"])
            asset=next((a for a in saved["assets"] if a["id"]==background.get("asset_id")),{})
            checks["measurement_matches_admitted_bytes"]=track.get("source",{}).get("sha256")==asset.get("sha256") and bool(asset)
            receipt["measurement_sha256"]=hashlib.sha256(measured).hexdigest()
        result["passed"]=all(checks.values())
    except Exception as error:
        result["error"]=str(error)
        (root/"runner-error.log").write_text(traceback.format_exc(),encoding="utf-8")
    finally:
        if store is not None:
            with store.lock:write_json(root/"jobs-at-ui-end.json",copy.deepcopy(store.jobs))
        # Preserve any still-active worker graph/log files before owned shutdown
        # cleans its temporary directories. Completed job receipts remain in Store.
        try:shutil.copytree(worker_root,root/"workers-at-ui-end")
        except (OSError,shutil.Error) as error:evidence_errors.append("Active worker snapshot: "+str(error))
        if server is not None:server.shutdown();server.server_close()
        if thread is not None:thread.join(timeout=5)
        if store is not None:
            store.shutdown()
            with store.lock:write_json(root/"jobs-after-shutdown.json",copy.deepcopy(store.jobs))
        tempfile.tempdir=prior_tempdir
        result.update(ui=ui,native_returncode=native_returncode,evidence_errors=evidence_errors,
                      elapsed_seconds=round(time.monotonic()-began,3))
        write_json(output/"result.json",result)
    print(json.dumps(result));return 0 if result["passed"] else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--binary",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args();raise SystemExit(run(args.binary,args.output))

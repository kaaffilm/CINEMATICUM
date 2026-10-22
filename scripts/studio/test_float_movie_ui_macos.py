#!/usr/bin/env python3
"""Bounded prepare/author/render native coordinator for real Float32 media.

Each phase owns a foreground server and helper. A Chromium replay verifies this
coordinator without claiming native acceptance. WKWebView/WKDownload acceptance
requires the compiled existing macos/SmokeTest.swift helper on an actual Mac.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import zipfile

from float_movie import DEFAULTS, verify_master_package
from server import Server, Store
from test_editing_ui_macos import read_helper_result
from test_multicam_sync_macos import source_inventory as runtime_inventory
import test_float_movie as fixtures

HERE=Path(__file__).resolve().parent
SOURCE_FILES=("float_movie.py","float_movie_worker.py","engine.py","image_worker.py","imaging.py","timebase.py",
              "frame_preview.py","server.py","project_archive.py","web/app.js","web/index.html","web/viewer-tools.js",
              "web/float-movie-ui.js","macos/FloatMovieSmoke.js","test_float_movie_ui_macos.py",
              "test_float_movie.py","test_imaging.py","test_float_movie_browser.cjs")

def inventory():
    result={name:record["sha256"] for name,record in runtime_inventory().items()}
    result.update({name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCE_FILES})
    return dict(sorted(result.items()))

def write(path,value):path.write_text(json.dumps(value,indent=2)+"\n")

def run(binary,output,phase,fixture,transport="WKWebView"):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    fixture=Path(fixture).resolve();started=time.monotonic();before=inventory()
    result={"schema":"cinematicum-float32-ui-acceptance-v1","phase":phase,"passed":False,"engine_test_only":True,
            "transport":transport,"native_certified":False,"issuance_effect":"NONE","checks":{},"source_sha256":before,
            "scope":"Shipped controls and real downloaded EXR/audio bytes. Explicit evidence destination; physical input, NSSavePanel, installed launcher, HDR monitoring and calibrated display are not certified."}
    checks=result["checks"];store=server=thread=None;media=None
    try:
        if not fixtures.FLOAT_RUNTIME:raise RuntimeError("Use the actual isolated NumPy/OpenEXR/OCIO Imaging interpreter.")
        if phase=="prepare":
            fixture.mkdir(parents=True,exist_ok=False);store=Store(fixture/"workspace")
            sentinel=store.new_project({"name":"ENGINE TEST float reopen sentinel","fps":4,"width":32,"height":24})
            project=store.new_project({"name":"ENGINE TEST float native","fps":4,"width":32,"height":24})
            media=fixtures.FloatMovieTests();media.setUp();movie,_=media.movie();image=media.exr("native-float",(-4,4,8),.6)
            a=store.admit(project["id"],media.root/movie["path"],"ENGINE_TEST_movie.mkv")
            stage=store.project_dir(project["id"])/"ENGINE_TEST_upload.exr";shutil.copyfile(media.root/image["path"],stage)
            b=store.admit(project["id"],stage,"ENGINE_TEST_negative_superwhite.exr")
            project=store.get(project["id"]);project["settings"]={"image_precision":"float32","transparent_background":True,"float_color":copy.deepcopy(DEFAULTS)}
            project["clips"]=[{"id":"ENGINE_TEST_video","asset_id":a["id"],"start":0,"in":0,"duration":4,"track":0,"scale":.5,"float_input_space":"Linear Rec.709 (sRGB)"},
                              {"id":"ENGINE_TEST_exr","asset_id":b["id"],"start":0,"in":0,"duration":4,"track":1,"scale":.73,"rotation":27,"float_input_space":"ACEScg"}]
            saved=store.save(project["id"],project)
            binding={"project_id":project["id"],"sentinel_id":sentinel["id"],"sources":[{"asset_id":x["id"],"path":x["path"],"sha256":x["sha256"]} for x in (a,b)],"source_sha256":before,"engine_test_only":True}
            write(fixture/"binding.json",binding);checks["actual_source_media_admitted"]=len(saved["assets"])==2
            checks["saved_float_multitrack_fixture"]=len(saved["clips"])==2 and saved["settings"]["image_precision"]=="float32"
        else:
            binding=json.loads((fixture/"binding.json").read_text())
            if binding["source_sha256"]!=before:raise ValueError("Coordinator source changed after fixture preparation.")
            store=Store(fixture/"workspace");project=store.get(binding["project_id"])
            directory=store.project_dir(project["id"])
            for asset in binding["sources"]:
                if hashlib.sha256((directory/asset["path"]).read_bytes()).hexdigest()!=asset["sha256"]:raise ValueError("Fixture source changed.")
            script=output/"workflow.js";script.write_text("const FLOAT_TEST="+json.dumps({**binding,"phase":phase})+";\n"+(HERE/"macos/FloatMovieSmoke.js").read_text())
            downloads=output/"downloads";downloads.mkdir()
            server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.02},daemon=True);thread.start()
            origin=f"http://127.0.0.1:{server.server_port}"
            screenshot=output/"ENGINE_TEST_float_ui.png"
            process=subprocess.run([str(Path(binary).resolve()),"--url",origin+"/","--output",str(screenshot),"--script",str(script),"--download-dir",str(downloads),"--timeout","14"],capture_output=True,text=True,timeout=16)
            ui=read_helper_result(process);result["ui"]=ui;result["helper_exit_code"]=process.returncode
            if process.stderr:result["helper_stderr_tail"]=process.stderr[-1600:]
            checks["shipped_controls_completed"]=process.returncode==0 and ui.get("passed") is True
            checks["no_script_or_download_errors"]=not ui.get("page_errors") and not ui.get("download_errors")
            saved=store.get(project["id"]);write(output/"saved-project.json",saved)
            checks["persisted_float_color_and_alpha"]=saved["settings"]["image_precision"]=="float32" and saved["settings"]["transparent_background"] and saved["settings"]["float_color"]["output_space"]=="ACES2065-1"
            checks["explicit_source_color_persisted"]=[c["float_input_space"] for c in saved["clips"]]==["Linear Rec.709 (sRGB)","ACEScg"]
            if phase=="author":
                url=ui.get("processed_frame_url","");preview=[j for j in store.jobs.values() if j["kind"]=="frame-preview" and j["state"]=="completed" and j.get("result",{}).get("url")==url]
                checks["displayed_real_owned_preview"]=bool(preview)
                if preview:
                    png=directory/"previews"/Path(url).name;checks["preview_exact_bytes"]=hashlib.sha256(png.read_bytes()).hexdigest()==preview[-1]["result"]["sha256"]
                    shutil.copyfile(png,output/"processed-frame.png")
            else:
                completed=[j for j in store.jobs.values() if j["kind"]=="render" and j["state"]=="completed" and j.get("result",{}).get("profile")=="master32"]
                checks["one_actual_owned_master"]=len(completed)==1
                if completed:
                    receipt=completed[0]["result"];result["export_receipt"]=receipt;master=directory/"exports"/receipt["filename"]
                    manifest=verify_master_package(master,saved);checks["master_snapshot_and_all_hashes_valid"]=manifest["frames"]==4 and manifest["audio"]["samples"]==48000
                    checks["master_receipt_bytes"]=hashlib.sha256(master.read_bytes()).hexdigest()==receipt["sha256"]
                    files=ui.get("downloads",[]);checks["one_completed_download"]=len(files)==1 and files[0].get("state")=="completed"
                    if len(files)==1:
                        downloaded=Path(files[0].get("path","")).resolve();checks["download_owned_destination"]=downloaded.parent==downloads
                        checks["download_exact_master_bytes"]=downloaded.parent==downloads and downloaded.is_file() and downloaded.read_bytes()==master.read_bytes()
                        checks["download_exact_completed_url"]=files[0].get("url")==origin+receipt["url"]+"?download=1" and ui.get("download_filename")==receipt["filename"]
                    import numpy as np,OpenEXR
                    with zipfile.ZipFile(master) as archive:
                        image=output/"downloaded-frame.exr";image.write_bytes(archive.read("frames/frame-00000000.exr"))
                    with OpenEXR.File(str(image),separate_channels=True) as exr:
                        channels=exr.channels();rgba=np.stack([channels[c].pixels for c in "RGBA"],axis=-1)
                        checks["decoded_float32_channels"]=all(channels[c].pixels.dtype==np.dtype("float32") for c in "RGBA")
                        checks["negative_superwhite_and_fractional_alpha"]=bool(np.any(rgba[...,:3]<0) and np.any(rgba[...,:3]>1) and np.any((rgba[...,3]>0)&(rgba[...,3]<1)))
                    write(output/"master-manifest.json",manifest)
            checks["actual_ui_screenshot"]=screenshot.is_file() and screenshot.stat().st_size>1000
            checks["source_media_preserved"]=all(hashlib.sha256((directory/a["path"]).read_bytes()).hexdigest()==a["sha256"] for a in binding["sources"])
        checks["source_unchanged"]=before==inventory()
        if not all(checks.values()):result["error"]=result.get("ui",{}).get("error") or "Failed: "+", ".join(k for k,v in checks.items() if not v)
    except Exception as error:result["error"]=str(error)
    finally:
        if server:server.shutdown();server.server_close();thread.join(1)
        if store:store.shutdown()
        if media:media.tearDown()
    result["elapsed_seconds"]=round(time.monotonic()-started,3);result["passed"]=bool(checks) and all(checks.values()) and "error" not in result
    result["native_certified"]=result["passed"] and phase!="prepare" and transport=="WKWebView" and sys.platform=="darwin"
    write(output/"ENGINE_TEST_float_ui_report.json",result);return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--binary",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--fixture",type=Path,required=True);parser.add_argument("--phase",choices=("prepare","author","render"),required=True)
    args=parser.parse_args()
    if sys.platform!="darwin":print(json.dumps({"status":"skipped","reason":"Actual native acceptance requires macOS; no result is simulated."}));return 0
    result=run(args.binary,args.output,args.phase,args.fixture);print(json.dumps(result));return 0 if result["passed"] else 1

if __name__=="__main__":raise SystemExit(main())

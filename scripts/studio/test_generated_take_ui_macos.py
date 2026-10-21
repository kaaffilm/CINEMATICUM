#!/usr/bin/env python3
"""Play an actual completed generated take through the shipped native editor.

The original job/project is read only. A byte-identical media copy is admitted
into a disposable ENGINE TEST workspace. Native controls add it to the timeline,
play the source and save. No substitute media, exports or generation jobs are
created. Independent FFmpeg decoding, receipts and observed source requests
verify the picture that WKWebView actually displays.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from macos.verify_generated_take import content_hash, verify_take
from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result

HERE=Path(__file__).resolve().parent


class ObservedHandler(Handler):
    """Record actual response status, without replacing routing or media bytes."""
    def send_response(self,code,message=None):
        with self.server.observed_lock:
            self.server.observed.append({"method":self.command,"path":urlsplit(self.path).path,
                                         "status":code,"range":self.headers.get("Range","")})
        return super().send_response(code,message)


def run(binary,project_dir,job_json,evidence,job_snapshot=None):
    evidence=Path(evidence).resolve();evidence.mkdir(parents=True,exist_ok=True)
    began=time.monotonic();deadline=began+18
    result={"passed":False,"browser":"WKWebView","scope":"Actual generated source in an isolated ENGINE TEST project", "checks":{}}
    checks=result["checks"]
    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<=.1:raise TimeoutError("Actual-take native acceptance exceeded its bounded execution budget.")
        return min(maximum,remaining)
    with tempfile.TemporaryDirectory(prefix="cinematicum-actual-take-ENGINE-TEST-") as temporary:
        store=server=thread=None
        try:
            verified,context=verify_take(project_dir,job_json,job_snapshot,evidence/"decoded",timeout=budget(5))
            result["take_verification"]=verified
            checks["actual_take_receipts_and_every_decoded_frame_pass"]=verified["passed"]
            if not verified["passed"]:raise RuntimeError("Actual generation verification failed: "+verified.get("error","unknown"))
            scratch=Path(temporary);incoming=scratch/("ENGINE_TEST_actual_generated_take"+context["source"].suffix)
            # Store.admit moves its input. Only this new disposable copy may be
            # passed to it; the real generation's source path is never mutated.
            shutil.copy2(context["source"],incoming)
            checks["disposable_input_is_exact_original_take"]=content_hash(incoming)==context["source_sha256"]
            store=Store(scratch/"workspace")
            project=store.new_project({"name":"ENGINE TEST — actual generated take playback","fps":context["fps"],"width":context["width"],"height":context["height"]})
            asset=store.admit(project["id"],incoming,"ENGINE TEST actual generated take"+context["source"].suffix,copy.deepcopy(context["asset"]["provenance"]))
            server=Server(0,store);server.observed=[];server.observed_lock=threading.Lock();server.RequestHandlerClass=ObservedHandler
            thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True);thread.start()
            screenshot=evidence/"ENGINE_TEST_actual_take_webkit.png"
            native_timeout=budget(12.3,reserve=1)
            native=subprocess.run([str(Path(binary).resolve()),"--url",f"http://127.0.0.1:{server.server_port}/","--output",str(screenshot),
                "--timeout",str(round(native_timeout,2)),"--script",str(HERE/"macos"/"GeneratedTakeSmoke.js")],capture_output=True,text=True,timeout=budget(native_timeout+.6,reserve=.2))
            ui=read_helper_result(native);result["ui"]=ui;result["helper_exit_code"]=native.returncode
            if native.stderr.strip():result["helper_stderr_tail"]=native.stderr[-1400:]
            checks["shipped_native_add_play_save_controls_pass"]=native.returncode==0 and ui.get("passed") is True
            checks["no_uncaught_browser_errors"]=not ui.get("page_errors",[])
            checks["native_canvas_is_requested_size"]=ui.get("width")==context["width"] and ui.get("height")==context["height"]
            samples=ui.get("samples",[]);matches=[]
            for sample in samples:
                observed=sample.get("grid",[])
                if len(observed)!=288 or any(type(value)is not int or not 0<=value<=255 for value in observed):
                    raise ValueError("Native source picture returned an invalid sample grid.")
                errors=[sum(abs(a-b) for a,b in zip(observed,expected))/288 for expected in context["grids"]]
                closest=min(range(len(errors)),key=errors.__getitem__)
                matches.append({"timecode":sample["timecode"],"closest_decoded_frame":closest,"mean_absolute_rgb_error":round(errors[closest],4)})
            result["native_pixel_matches"]=matches
            # Hardware YUV-to-RGB rounding and transfer implementations need
            # not be byte-identical to FFmpeg. This bound is stated explicitly;
            # it is not used to assert frame-exact decoder/timeline latency.
            checks["native_images_match_independent_actual_source_decode"]=len(matches)>=3 and all(item["mean_absolute_rgb_error"]<8 for item in matches) and len({item["closest_decoded_frame"] for item in matches})>=3
            saved=store.get(project["id"]);clips=saved["clips"]
            checks["one_actual_take_added_by_ui_and_saved"]=len(clips)==1 and clips[0]["id"]==ui.get("clip_id") and clips[0]["asset_id"]==asset["id"]==ui.get("asset_id") and ui.get("project_id")==project["id"] and saved["revision"]>0
            checks["full_take_played_at_native_rate_without_extra_media"]=len(clips)==1 and clips[0]["start"]==0 and clips[0]["in"]==0 and clips[0]["duration"]==context["length"] and clips[0]["speed"]==1 and not clips[0]["reverse"] and len(saved["assets"])==1 and not saved["titles"]
            admitted=store.project_dir(project["id"])/asset["path"]
            checks["playback_asset_hash_and_generation_provenance_preserved"]=content_hash(admitted)==asset["sha256"]==context["source_sha256"] and asset["provenance"]==context["asset"]["provenance"]
            with server.observed_lock:requests=copy.deepcopy(server.observed)
            media_path=f"/api/projects/{project['id']}/media/{asset['id']}"
            source_requests=[item for item in requests if item["method"]=="GET" and item["path"]==media_path]
            result["observed_source_requests"]=source_requests
            checks["actual_admitted_source_served_to_native_decoder"]=bool(source_requests) and all(item["status"] in (200,206) for item in source_requests)
            with store.lock:jobs=copy.deepcopy(list(store.jobs.values()))
            result["fixture_job_kinds"]=[job["kind"] for job in jobs]
            checks["no_export_or_generation_substitute_created"]=not ui.get("render_video_src") and all(job["kind"]=="frame-preview" for job in jobs) and not list((store.project_dir(project["id"])/"exports").iterdir())
            checks["original_take_and_job_snapshot_remain_unchanged"]=content_hash(context["source"])==context["source_sha256"] and content_hash(context["snapshot_path"])==context["snapshot_sha256"]
            checks["native_screenshot_saved"]=screenshot.is_file() and screenshot.stat().st_size>1000
            (evidence/"ENGINE_TEST_saved_actual_take_project.json").write_text(json.dumps(saved,indent=2)+"\n")
            (evidence/"ENGINE_TEST_actual_take_ui.json").write_text(json.dumps(ui,indent=2)+"\n")
            if not all(checks.values()):result["error"]=ui.get("error") or "Failed checks: "+", ".join(name for name,value in checks.items() if not value)
        except Exception as error:result["error"]=str(error)
        finally:
            if server is not None:server.shutdown();server.server_close()
            if thread is not None:thread.join(timeout=.2)
            if store is not None:store.shutdown()
    result["elapsed_seconds"]=round(time.monotonic()-began,3);checks["bounded_run"]=result["elapsed_seconds"]<18.5
    result["passed"]=bool(checks) and all(checks.values()) and "error" not in result
    (evidence/"ENGINE_TEST_actual_take_report.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",type=Path);parser.add_argument("--project-dir",required=True,type=Path)
    parser.add_argument("--job-json",required=True,type=Path);parser.add_argument("--job-snapshot",type=Path)
    parser.add_argument("--output",required=True,type=Path);args=parser.parse_args()
    if sys.platform!="darwin":
        print(json.dumps({"status":"skipped","reason":"Actual WKWebView playback requires macOS; no UI result is simulated."}));return 0
    if not args.binary or not args.binary.is_file():parser.error("Pass the compiled macos/SmokeTest.swift executable with --binary.")
    result=run(args.binary,args.project_dir,args.job_json,args.output,args.job_snapshot)
    print(json.dumps(result,sort_keys=True));return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())

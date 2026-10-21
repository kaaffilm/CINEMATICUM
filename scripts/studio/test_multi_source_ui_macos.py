#!/usr/bin/env python3
"""Native two-source graph editing, shared undo, paused frame and movie proof.

Runs only in an isolated temporary workspace with two authored moving engine
fixtures. The existing SmokeTest.swift binary drives shipped DOM controls.
This never opens or edits the user's film project.
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
import tempfile
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from server import Server, Store
from test_editing_ui_macos import read_helper_result
from test_multi_source_compositor import WIDTH, HEIGHT, FPS, FRAMES, make_fixture, fixture_pixel


HERE=Path(__file__).resolve().parent
PNG_SIGNATURE=b"\x89PNG\r\n\x1a\n"


def run(binary,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();deadline=started+17.7
    result={"passed":False,"browser":"WKWebView","fixture":"SYNTHETIC ENGINE TEST — NOT FILM FOOTAGE","checks":{}}
    checks=result["checks"]

    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<.1:raise TimeoutError("Multi-source native acceptance exceeded its time budget.")
        return min(maximum,remaining)

    def decode(path):
        return subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-threads","1","-i",str(path),
                               "-map","0:v:0","-an","-threads","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],
                              check=True,capture_output=True,timeout=budget(3)).stdout

    with tempfile.TemporaryDirectory(prefix="cinematicum-multisource-webkit-TEST-") as temporary:
        scratch=Path(temporary);store=server=thread=None
        try:
            if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
                raise RuntimeError("FFmpeg and ffprobe are required for actual two-source media acceptance.")
            store=Store(scratch/"workspace")
            project=store.new_project({"name":"ENGINE TEST — independent media sources","fps":FPS,"width":WIDTH,"height":HEIGHT})
            admitted={};originals={}
            for kind in ("red","blue"):
                source=scratch/("ENGINE_TEST_"+kind+"_moving.mkv")
                make_fixture(source,kind)
                originals[kind]=hashlib.sha256(source.read_bytes()).hexdigest()
                admitted[kind]=store.admit(project["id"],source,source.name)
            fixture={kind+"_id":asset["id"] for kind,asset in admitted.items()}
            script=scratch/"MultiSourceSmoke.js"
            script.write_text("const MULTI_SOURCE_TEST="+json.dumps(fixture)+";\n"+(HERE/"macos"/"MultiSourceSmoke.js").read_text(),encoding="utf-8")
            server=Server(0,store)
            thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True);thread.start()
            screenshot=output/"ENGINE_TEST_multi_source_webkit.png"
            native_timeout=budget(12.8,2.3)
            process=subprocess.run([str(Path(binary).resolve()),"--url",f"http://127.0.0.1:{server.server_port}/",
                                    "--output",str(screenshot),"--timeout",str(round(native_timeout,2)),"--script",str(script)],
                                   capture_output=True,text=True,timeout=budget(native_timeout+.5))
            ui=read_helper_result(process);result["ui"]=ui;result["helper_exit_code"]=process.returncode
            checks["native_dom_acceptance_passed"]=process.returncode==0 and ui.get("passed") is True
            checks["no_browser_errors"]=not ui.get("page_errors",[])
            checks["bounded_native_runtime"]=ui.get("elapsed_ms",99999)<13000
            if process.stderr:result["helper_stderr_tail"]=process.stderr[-1200:]
            saved=store.get(project["id"]);directory=store.project_dir(project["id"])
            (output/"ENGINE_TEST_saved_project.json").write_text(json.dumps(saved,indent=2),encoding="utf-8")
            (output/"ENGINE_TEST_ui.json").write_text(json.dumps(ui,indent=2),encoding="utf-8")
            clips=sorted(saved.get("clips",[]),key=lambda item:item["start"])
            checks["two_timeline_windows"]=len(clips)==2
            if len(clips)==2:
                left,right=clips
                checks["independent_domain_preserved"]=left["start"]==0 and left["duration"]==8 and left["in"]==0 and right["start"]==11 and right["duration"]==13 and right["in"]==11 and right.get("animation_offset")==11 and all(c.get("animation_duration")==24 for c in clips)
                checks["split_copies_identical_graph"]=left.get("compositor")==right.get("compositor")
                graph=right.get("compositor",{});nodes={item["id"]:item for item in graph.get("nodes",[])}
                source=nodes.get(ui.get("source_id"),{});mask=nodes.get(ui.get("mask_id"),{});merge=nodes.get(ui.get("merge_id"),{})
                checks["typed_source_timing_saved_exactly"]=source.get("params")=={"asset_id":admitted["blue"]["id"],"source_in":4,"duration":8,"offset":6,"outside":"transparent"} and source.get("inputs")==[]
                primary=next((item for item in nodes.values() if item.get("type")=="source"),{})
                checks["two_distinct_media_branches_connected"]=len(nodes)==4 and mask.get("inputs")==[source.get("id")] and merge.get("inputs")==[primary.get("id"),mask.get("id")] and graph.get("output")==merge.get("id")
                checks["primary_media_unchanged"]=all(c["asset_id"]==admitted["red"]["id"] for c in clips)
            checks["no_unrequested_assets_or_titles"]=len(saved["assets"])==2 and not saved.get("titles")
            with store.lock:
                jobs=copy.deepcopy([job for job in store.jobs.values() if job["project_id"]==project["id"]])
            pictures={}
            for phase in ("before","after"):
                requested=ui.get(phase+"_frame",{})
                found=[job for job in jobs if job["kind"]=="frame-preview" and job["state"]=="completed" and job.get("result",{}).get("url")==requested.get("url")]
                checks[phase+"_is_actual_frame12_job"]=bool(found) and requested.get("frame")==12
                if found:
                    receipt=found[-1]["result"];picture=directory/"previews"/Path(urlsplit(receipt["url"]).path).name
                    checks[phase+"_preview_digest_verified"]=picture.read_bytes().startswith(PNG_SIGNATURE) and hashlib.sha256(picture.read_bytes()).hexdigest()==receipt.get("sha256") and receipt.get("pipeline")=="timeline-export-graph"
                    pictures[phase]=decode(picture);shutil.copy2(picture,output/("ENGINE_TEST_"+phase+"_frame12.png"))
            size=WIDTH*HEIGHT*3
            checks["trim_split_preserve_paused_pixels_exactly"]=set(pictures)=={"before","after"} and len(pictures["before"])==size and pictures["before"]==pictures["after"]
            completed=[job for job in jobs if job["kind"]=="render" and job["state"]=="completed"]
            checks["one_real_movie_export"]=len(completed)==1
            if completed:
                receipt=completed[0]["result"];movie=directory/"exports"/receipt["filename"]
                metadata=probe_media(movie);result["media"]=metadata
                checks["export_has_all_frames"]=metadata["width"]==WIDTH and metadata["height"]==HEIGHT and metadata["frames"]==FRAMES
                checks["webkit_plays_the_export"]=ui.get("video_src")==receipt["url"] and ui.get("video_time",0)>.06
                pixels=decode(movie);checks["all_movie_frames_decode"]=len(pixels)==FRAMES*size
                checks["trimmed_timeline_gap_is_black"]=len(pixels)==FRAMES*size and all(max(pixels[f*size:(f+1)*size])<=3 for f in (8,9,10))
                errors=[]
                for frame,x,y in ((0,16,25),(4,24,25),(6,113,17),(7,113,20),(12,125,31),(13,125,35),(14,125,31),(23,73,25)):
                    sample=frame-2 if 6<=frame<14 else None
                    expected=fixture_pixel("blue",sample,x,y)[:3] if x>=80 and sample is not None else fixture_pixel("red",frame,x,y)[:3]
                    at=frame*size+3*(y*WIDTH+x);actual=pixels[at:at+3]
                    errors.append(max((abs(a-b) for a,b in zip(actual,expected)),default=999))
                result["moving_source_pixel_errors"]=errors;checks["independent_source_motion_and_transparent_gaps"]=max(errors)<=10
                if "after" in pictures and len(pixels)==FRAMES*size:
                    error=sum(abs(a-b) for a,b in zip(pictures["after"],pixels[12*size:13*size]))/size
                    result["paused_vs_export_mean_rgb_error"]=round(error,6);checks["paused_frame_matches_export"]=error<4
                shutil.copy2(movie,output/"ENGINE_TEST_multi_source_export.mp4")
            checks["source_files_unchanged"]=all(asset["sha256"]==originals[kind] and hashlib.sha256((directory/asset["path"]).read_bytes()).hexdigest()==originals[kind] for kind,asset in admitted.items())
            checks["actual_native_screenshot"]=screenshot.is_file() and screenshot.stat().st_size>1000 and screenshot.read_bytes().startswith(PNG_SIGNATURE)
            result["jobs"]=[{"kind":job["kind"],"state":job["state"]} for job in jobs]
            if not all(checks.values()):result["error"]=ui.get("error") or "Failed checks: "+", ".join(name for name,passed in checks.items() if not passed)
        except Exception as error:
            result["error"]=str(error);checks["completed_without_fixture_error"]=False
            if isinstance(error,subprocess.CalledProcessError):result["process_error"]=(error.stderr or b"").decode(errors="replace")[-1600:]
        finally:
            if server is not None:server.shutdown();server.server_close()
            if thread is not None:thread.join(timeout=.2)
            if store is not None:store.shutdown()
    result["elapsed_seconds"]=round(time.monotonic()-started,3)
    checks["bounded_whole_run"]=result["elapsed_seconds"]<18.5
    result["passed"]=bool(checks) and all(checks.values()) and "error" not in result
    result["evidence_directory"]=str(output)
    (output/"ENGINE_TEST_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description="Actual WK two-source compositor, undo and rendered media acceptance")
    parser.add_argument("--binary",type=Path);parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if sys.platform!="darwin":
        print(json.dumps({"status":"skipped","reason":"Actual WKWebView acceptance requires macOS; no UI or media result is simulated."}));return 0
    if not args.binary or not args.binary.is_file():parser.error("Pass the compiled macos/SmokeTest.swift executable with --binary.")
    output=args.output or Path(tempfile.mkdtemp(prefix="cinematicum-multisource-ENGINE-TEST-evidence-"))
    result=run(args.binary,output);print(json.dumps(result,sort_keys=True));return 0 if result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())

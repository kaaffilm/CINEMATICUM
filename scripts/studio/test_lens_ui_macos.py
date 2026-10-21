#!/usr/bin/env python3
"""Native calibrated lens controls and independently verified movie pixels.

The isolated fixture includes hidden red in transparent pixels and moving
colored alpha ramps. It never opens or modifies a user's film project.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from frame_preview import preview_identity
import server as server_module
from scene import default_scene,validate_scene
from server import Server,Store
from test_editing_ui_macos import read_helper_result
from test_lens_compositor import BASE,WIDTH,HEIGHT,FPS,fixture,expected_pixel


HERE=Path(__file__).resolve().parent
FRAMES=12
PNG_SIGNATURE=b"\x89PNG\r\n\x1a\n"


def run(binary,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();deadline=started+17.7
    result={"passed":False,"browser":"WKWebView","fixture":"SYNTHETIC ENGINE TEST — NOT FILM FOOTAGE","checks":{}}
    checks=result["checks"]
    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<.1:raise TimeoutError("Lens native acceptance exceeded its time budget.")
        return min(maximum,remaining)
    def decode(path):
        return subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-threads","1","-i",str(path),
                               "-map","0:v:0","-an","-threads","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],
                              check=True,capture_output=True,timeout=budget(3)).stdout
    with tempfile.TemporaryDirectory(prefix="cinematicum-lens-webkit-TEST-") as temporary:
        scratch=Path(temporary);store=server=thread=None
        original_frame_renderer=server_module.render_frame
        frame_requests={}
        def recorded_frame_renderer(project,project_dir,frame,output_path,*args,**kwargs):
            # Observe the exact production call, without replacing its result
            # or taking a second snapshot from potentially newer UI state.
            frame_requests[Path(output_path).stem]={"project":copy.deepcopy(project),"frame":frame,
                                                   "identity":preview_identity(project,frame)}
            return original_frame_renderer(project,project_dir,frame,output_path,*args,**kwargs)
        server_module.render_frame=recorded_frame_renderer
        try:
            if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
                raise RuntimeError("FFmpeg and ffprobe are required for actual calibrated pixel acceptance.")
            store=Store(scratch/"workspace")
            project=store.new_project({"name":"ENGINE TEST — Calibrated lens pixels","fps":FPS,"width":WIDTH,"height":HEIGHT})
            spec=default_scene(WIDTH,HEIGHT);spec["frame_end"]=FRAMES
            spec["camera"].update(fov=48,focal_ratio=1.12,shift_x=.04,shift_y=.025)
            spec=validate_scene(spec);project["settings"]["scene"]=spec
            project["settings"]["engine_test_sentinel"]="preserved"
            project=store.save(project["id"],project)
            fy=.5/math.tan(math.radians(48)/2)
            params=dict(BASE,fx=fy*HEIGHT/WIDTH*1.12,fy=fy,cx=.54,cy=.475,direction="distort")
            source=scratch/"ENGINE_TEST_alpha_ramps.mkv"
            pixels=b"".join(bytes(fixture(frame,x,y)) for frame in range(FRAMES) for y in range(HEIGHT) for x in range(WIDTH))
            subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-threads","1",
                            "-f","rawvideo","-pixel_format","rgba","-video_size",f"{WIDTH}x{HEIGHT}",
                            "-framerate",str(FPS),"-i","pipe:0","-an","-c:v","ffv1","-pix_fmt","bgra","-threads","1",str(source)],
                           input=pixels,check=True,capture_output=True,timeout=budget(3))
            original=hashlib.sha256(source.read_bytes()).hexdigest()
            asset=store.admit(project["id"],source,source.name)
            script=scratch/"LensSmoke.js"
            script.write_text("const LENS_TEST="+json.dumps({"asset_id":asset["id"],"params":params})+";\n"+
                              (HERE/"macos"/"LensSmoke.js").read_text(),encoding="utf-8")
            server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True);thread.start()
            screenshot=output/"ENGINE_TEST_lens_webkit.png";native_timeout=budget(12.8,2.4)
            process=subprocess.run([str(Path(binary).resolve()),"--url",f"http://127.0.0.1:{server.server_port}/",
                                    "--output",str(screenshot),"--timeout",str(round(native_timeout,2)),"--script",str(script)],
                                   capture_output=True,text=True,timeout=budget(native_timeout+.5))
            ui=read_helper_result(process);result["ui"]=ui;result["helper_exit_code"]=process.returncode
            checks["native_controls_and_history_passed"]=process.returncode==0 and ui.get("passed") is True
            checks["no_browser_errors"]=not ui.get("page_errors",[])
            checks["bounded_native_runtime"]=ui.get("elapsed_ms",99999)<13000
            if process.stderr:result["helper_stderr_tail"]=process.stderr[-1200:]
            saved=store.get(project["id"]);directory=store.project_dir(project["id"])
            (output/"ENGINE_TEST_saved_project.json").write_text(json.dumps(saved,indent=2),encoding="utf-8")
            (output/"ENGINE_TEST_ui.json").write_text(json.dumps(ui,indent=2),encoding="utf-8")
            clips=saved.get("clips",[]);graph=clips[0].get("compositor",{}) if len(clips)==1 else {}
            node=next((item for item in graph.get("nodes",[]) if item.get("id")==ui.get("lens_id")),{})
            actual=node.get("params",{})
            checks["one_clip_with_connected_lens"]=len(clips)==1 and len(graph.get("nodes",[]))==2 and graph.get("output")==node.get("id") and node.get("type")=="lens_distortion" and len(node.get("inputs",[]))==1
            checks["calibration_saved_without_precision_loss"]=set(actual)==set(params) and all(actual.get(key)==value if isinstance(value,str) else math.isclose(actual.get(key,math.inf),value,abs_tol=1e-13,rel_tol=0) for key,value in params.items())
            checks["unsupported_calibration_animation_absent"]=not node.get("animation")
            checks["original_camera_and_settings_preserved"]=saved["settings"].get("scene")==spec and saved["settings"].get("engine_test_sentinel")=="preserved"
            checks["one_owned_source_no_unrequested_assets"]=len(saved["assets"])==1 and not saved.get("titles")
            with store.lock:jobs=copy.deepcopy([job for job in store.jobs.values() if job["project_id"]==project["id"]])
            (output/"ENGINE_TEST_frame_requests.json").write_text(json.dumps(frame_requests,indent=2),encoding="utf-8")
            pictures={};size=WIDTH*HEIGHT*3
            for direction in ("undistort","distort"):
                requested=ui.get(direction+"_frame",{})
                found=[job for job in jobs if job["kind"]=="frame-preview" and job["state"]=="completed" and job.get("result",{}).get("url")==requested.get("url")]
                checks[direction+"_is_actual_frame6_job"]=bool(found) and requested.get("frame")==6
                if found:
                    receipt=found[-1]["result"];picture=directory/"previews"/Path(urlsplit(receipt["url"]).path).name
                    request=frame_requests.get(picture.stem,{})
                    request_clips=request.get("project",{}).get("clips",[])
                    request_nodes=request_clips[0].get("compositor",{}).get("nodes",[]) if len(request_clips)==1 else []
                    request_lens=next((item for item in request_nodes if item.get("id")==ui.get("lens_id")),{})
                    expected_params=dict(params,direction=direction);request_params=request_lens.get("params",{})
                    checks[direction+"_snapshot_identity_is_actual_render_call"]=request.get("frame")==6 and request.get("identity")==picture.stem
                    checks[direction+"_snapshot_has_expected_calibration"]=set(request_params)==set(expected_params) and all(request_params.get(key)==value if isinstance(value,str) else math.isclose(request_params.get(key,math.inf),value,abs_tol=1e-13,rel_tol=0) for key,value in expected_params.items())
                    result[direction+"_snapshot_calibration"]=request_params
                    checks[direction+"_preview_receipt_verified"]=picture.read_bytes().startswith(PNG_SIGNATURE) and hashlib.sha256(picture.read_bytes()).hexdigest()==receipt.get("sha256") and receipt.get("pipeline")=="timeline-export-graph"
                    pictures[direction]=decode(picture);shutil.copy2(picture,output/("ENGINE_TEST_"+direction+"_frame6.png"))
                    errors=[]
                    for y in range(3,HEIGHT,7):
                        for x in range(3,WIDTH,9):
                            expected=expected_pixel(dict(params,direction=direction),6,x,y)[:3]
                            at=3*(y*WIDTH+x);rgb=pictures[direction][at:at+3]
                            errors.extend(abs(a-b) for a,b in zip(rgb,expected))
                    result[direction+"_oracle_mean_rgb_error"]=sum(errors)/len(errors)
                    result[direction+"_oracle_max_rgb_error"]=max(errors)
                    checks[direction+"_matches_independent_newton_and_alpha_oracle"]=len(pictures[direction])==size and sum(errors)/len(errors)<3 and max(errors)<8
            checks["two_operations_change_actual_pixels"]=set(pictures)=={"undistort","distort"} and pictures["undistort"]!=pictures["distort"]
            completed=[job for job in jobs if job["kind"]=="render" and job["state"]=="completed"]
            checks["one_real_movie_export"]=len(completed)==1
            if completed:
                receipt=completed[0]["result"];movie=directory/"exports"/receipt["filename"];metadata=probe_media(movie);result["media"]=metadata
                checks["movie_has_exact_frame_count"]=metadata["width"]==WIDTH and metadata["height"]==HEIGHT and metadata["frames"]==FRAMES
                checks["webkit_plays_the_export"]=ui.get("video_src")==receipt["url"] and ui.get("video_time",0)>.06
                pixels=decode(movie);checks["every_movie_frame_decodes"]=len(pixels)==FRAMES*size
                if "distort" in pictures and len(pixels)==FRAMES*size:
                    error=sum(abs(a-b) for a,b in zip(pictures["distort"],pixels[6*size:7*size]))/size
                    result["paused_export_mean_rgb_error"]=error;checks["paused_calibration_matches_export"]=error<4
                shutil.copy2(movie,output/"ENGINE_TEST_calibrated_export.mp4")
            checks["source_media_unchanged"]=asset["sha256"]==original and hashlib.sha256((directory/asset["path"]).read_bytes()).hexdigest()==original
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
            server_module.render_frame=original_frame_renderer
    result["elapsed_seconds"]=round(time.monotonic()-started,3)
    checks["bounded_whole_run"]=result["elapsed_seconds"]<18.5
    result["passed"]=bool(checks) and all(checks.values()) and "error" not in result
    (output/"ENGINE_TEST_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description="Actual WK calibrated lens controls, undo and independent rendered-pixel acceptance")
    parser.add_argument("--binary",type=Path);parser.add_argument("--output",type=Path);args=parser.parse_args()
    if sys.platform!="darwin":
        print(json.dumps({"status":"skipped","reason":"Actual WKWebView acceptance requires macOS; no UI or media result is simulated."}));return 0
    if not args.binary or not args.binary.is_file():parser.error("Pass the compiled macos/SmokeTest.swift executable with --binary.")
    output=args.output or Path(tempfile.mkdtemp(prefix="cinematicum-lens-ENGINE-TEST-evidence-"))
    result=run(args.binary,output);print(json.dumps(result,sort_keys=True));return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())

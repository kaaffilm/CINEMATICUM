#!/usr/bin/env python3
"""Bounded independent proof for the normal app's completed Metal scene job.

No CINEMATICUM runtime modules are imported. Reads the job/snapshot/source,
decodes the delivered MP4 through FFmpeg, and reopens .blend without rendering.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import time
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--project-dir", required=True, type=Path)
parser.add_argument("--job-json", required=True, type=Path)
parser.add_argument("--evidence", required=True, type=Path)
parser.add_argument("--blender", default="/Applications/Blender.app/Contents/MacOS/Blender")
args = parser.parse_args()
began = time.monotonic()
deadline = began + 17
evidence = args.evidence.resolve(); evidence.mkdir(parents=True, exist_ok=True)
checks = {}; report = {"passed": False, "fixture": "ENGINE TEST — Metal scene", "checks": checks}

def run(command, cap):
    remaining = min(cap, deadline - time.monotonic())
    if remaining <= .1: raise TimeoutError("Independent Metal verification exhausted its 17-second budget.")
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        output, error = process.communicate(timeout=remaining)
        if process.returncode: raise RuntimeError("Verification subprocess failed: " + error.decode(errors="replace")[-1800:] + output.decode(errors="replace")[-1800:])
        return output
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL); process.communicate(timeout=.5)

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def owned(base, relative):
    path = (base / relative).resolve(strict=True)
    if not path.is_relative_to(base): raise ValueError("Completed result path escapes its project.")
    return path

def write_png(path, rgb):
    def chunk(kind, data): return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    scanlines = b"".join(b"\0" + rgb[y*192*3:(y+1)*192*3] for y in range(128))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 192, 128, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))

try:
    project = args.project_dir.resolve(strict=True)
    body = json.loads(args.job_json.read_text()); job = body.get("job", body)
    assert job["state"] == "completed" and job["kind"] == "scene", "The actual scene job did not complete."
    result = job["result"]; asset = result["asset"]; provenance = asset["provenance"]
    movie = owned(project, asset["path"])
    source = owned(project, "exports/" + result["scene_filename"])
    manifest = json.loads(owned(project, "exports/" + job["id"] + ".json").read_text())
    snapshot = manifest["snapshot"]; receipt = provenance["render_device"]
    checks["committed_job_and_export_receipt_agree"] = manifest["result"] == result
    checks["actual_render_receipt_only_metal"] = (provenance["renderer"] == "Cycles METAL"
        and receipt["requested"] == receipt["actual"] == "METAL" and bool(receipt["devices"])
        and all(d["type"] == "METAL" and d["id"] for d in receipt["devices"]))
    checks["media_and_source_hashes_match"] = (sha(movie) == asset["sha256"] == provenance["output_sha256"]
        and sha(source) == result["scene_sha256"] == provenance["scene_sha256"])
    canonical = json.dumps(snapshot["scene"], sort_keys=True, separators=(",", ":")).encode()
    checks["exact_completed_recipe_identity"] = hashlib.sha256(canonical).hexdigest() == provenance["recipe_sha256"]
    ffprobe = shutil.which("ffprobe"); ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg: raise RuntimeError("FFmpeg and ffprobe must be available for actual decoded-media verification.")
    metadata = json.loads(run([ffprobe,"-v","error","-count_frames","-show_entries","stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames,duration","-of","json",str(movie)], 2.5))
    streams = metadata["streams"]; video = streams[0]
    checks["one_h264_frame_192x128_at_16fps"] = (len(streams) == 1 and video["codec_type"] == "video"
        and video["codec_name"] == "h264" and (video["width"],video["height"]) == (192,128)
        and int(video["nb_read_frames"]) == 1 and Fraction(video["avg_frame_rate"]) == 16)
    pixels = run([ffmpeg,"-v","error","-nostdin","-threads","1","-i",str(movie),"-map","0:v:0","-an","-frames:v","2","-threads","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"], 3)
    checks["exactly_one_frame_decodes"] = len(pixels) == 192*128*3
    assert checks["exactly_one_frame_decodes"], "Decoded media is not exactly the authored single frame."
    rgb = list(zip(pixels[0::3], pixels[1::3], pixels[2::3]))
    red = sum(r > 70 and r > g+20 and r > b+20 for r,g,b in rgb)
    corners = [rgb[y*192+x] for y in (0,1,126,127) for x in (0,1,190,191)]
    checks["visible_authored_red_object"] = red > 100
    checks["black_world_corners_preserved"] = max(max(pixel) for pixel in corners) < 16
    report["decoded"] = {"bytes":len(pixels),"rgb_sha256":hashlib.sha256(pixels).hexdigest(),"red_object_pixels":red,"corner_max":max(max(p) for p in corners)}
    write_png(evidence/"ENGINE_TEST_metal_decoded.png", pixels)
    expected = evidence/"ENGINE_TEST_metal_expected.json"
    expected.write_text(json.dumps({"scene":snapshot["scene"],"render_device":receipt},indent=2)+"\n")
    native_result = evidence/"ENGINE_TEST_metal_blend.json"
    output = run([args.blender,"--background","--factory-startup","--disable-autoexec",str(source),"--threads","2","--python-exit-code","1","--python",str(Path(__file__).with_name("verify_metal_blend.py")),"--",str(expected),str(native_result)], 11)
    (evidence/"ENGINE_TEST_metal_reopen.log").write_bytes(output)
    native = json.loads(native_result.read_text()); checks.update(native["checks"])
    report.update(metadata=metadata,render_device=receipt,source_sha256=result["scene_sha256"],blender=native)
    report["passed"] = bool(checks) and all(checks.values())
    if not report["passed"]: report["error"] = "Failed checks: " + ", ".join(k for k,v in checks.items() if not v)
except Exception as error:
    report["error"] = str(error)
report["elapsed_seconds"] = round(time.monotonic()-began,3)
(evidence/"ENGINE_TEST_metal_report.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,sort_keys=True))
raise SystemExit(0 if report["passed"] else 1)

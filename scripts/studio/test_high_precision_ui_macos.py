#!/usr/bin/env python3
"""Native 16-bit export controls, save/reopen, and real WKDownload acceptance.

The generic native helper's opt-in download directory receives the bytes through
WebKit. A destination panel is not simulated or claimed to have been tested.
Only an isolated synthetic numeric project and its evidence directory are used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from server import Server, Store
from test_editing_ui_macos import read_helper_result
from test_high_precision import WIDTH, HEIGHT, FPS, FRAMES, decode_rgba16, numeric_ramp, write_fixture

HERE = Path(__file__).resolve().parent


def run(binary, output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    downloads = output / "native_downloads"
    downloads.mkdir(exist_ok=True)
    began = time.monotonic()
    result = {"passed": False, "browser": "WKWebView", "fixture": "SYNTHETIC ENGINE TEST — NOT FILM FOOTAGE",
              "scope": "export-dialog controls and real WKDownload; NSSavePanel selection not tested", "checks": {}}
    checks = result["checks"]
    with tempfile.TemporaryDirectory(prefix="cinematicum-high16-WEBKIT-ENGINE-TEST-") as temporary:
        scratch = Path(temporary); store = server = thread = None
        try:
            fixture = write_fixture(scratch / "ENGINE_TEST_ONLY_16bit_ramp.mkv", numeric_ramp())
            source_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
            store = Store(scratch / "workspace")
            sentinel = store.new_project({"name": "ENGINE TEST reopen sentinel", "fps": FPS, "width": WIDTH, "height": HEIGHT})
            project = store.new_project({"name": "ENGINE TEST — native 16-bit SDR", "fps": FPS, "width": WIDTH, "height": HEIGHT})
            asset = store.admit(project["id"], fixture, fixture.name)
            fixture_identity = {"project_id": project["id"], "sentinel_id": sentinel["id"], "asset_id": asset["id"]}
            result["fixture_identity"] = fixture_identity
            script = scratch / "high16-workflow.js"
            script.write_text("const HIGH16_TEST=" + json.dumps(fixture_identity) + ";\n" +
                              (HERE / "macos" / "HighPrecisionSmoke.js").read_text(encoding="utf-8"), encoding="utf-8")
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True); thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            screenshot = output / "ENGINE_TEST_high16_native.png"
            native = subprocess.run([str(Path(binary).resolve()), "--url", origin + "/", "--output", str(screenshot),
                "--script", str(script), "--download-dir", str(downloads),
                "--timeout", "28"], check=False, capture_output=True, text=True, timeout=32)
            ui = read_helper_result(native)
            result["ui"] = ui; result["helper_exit_code"] = native.returncode
            if native.stderr: result["helper_stderr_tail"] = native.stderr[-1800:]
            checks["native_controls_history_save_reopen_and_download"] = native.returncode == 0 and ui.get("passed") is True
            checks["no_browser_errors"] = not ui.get("page_errors") and not ui.get("download_errors")
            saved, directory = store.get(project["id"]), store.project_dir(project["id"])
            (output / "ENGINE_TEST_high16_saved_project.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
            checks["saved_high16_transparent_recipe"] = saved.get("settings", {}).get("image_precision") == "high16" and saved["settings"].get("transparent_background") is True
            clips = saved.get("clips", [])
            checks["saved_nonidentity_transform"] = len(clips) == 1 and all(abs(clips[0].get(k, 999) - v) < 1e-9
                for k, v in {"scale": .73, "rotation": 27, "x": .07, "y": -.09}.items())
            with store.lock:
                jobs = copy.deepcopy([job for job in store.jobs.values() if job["project_id"] == project["id"]])
            completed = [j for j in jobs if j["kind"] == "render" and j["state"] == "completed"]
            checks["one_completed_native_master_job"] = len(completed) == 1
            if completed:
                receipt = completed[0]["result"]; result["export_receipt"] = receipt
                movie = directory / "exports" / receipt["filename"]
                payload = movie.read_bytes()
                checks["receipt_covers_actual_master"] = receipt.get("profile") == "master16" and hashlib.sha256(payload).hexdigest() == receipt.get("sha256")
                checks["native_link_binds_completed_master"] = ui.get("download_href") == receipt["url"] + "?download=1" and ui.get("download_filename") == receipt["filename"]
                native_files = ui.get("downloads", [])
                checks["exactly_one_real_wkdownload"] = len(native_files) == 1 and native_files[0].get("state") == "completed"
                if len(native_files) == 1:
                    path = Path(native_files[0].get("path", "")).resolve()
                    checks["download_confined_to_test_evidence"] = path.parent == downloads
                    if path.parent == downloads and path.is_file():
                        downloaded = path.read_bytes()
                        checks["native_download_exact_bytes"] = downloaded == payload and native_files[0].get("bytes") == len(payload)
                        checks["native_download_exact_export_url"] = native_files[0].get("url") == origin + ui.get("download_href", "")
                    else:
                        checks["native_download_exact_bytes"] = False
                with urllib.request.urlopen(origin + receipt["url"] + "?download=1", timeout=3) as response:
                    checks["download_route_attachment_headers_and_length"] = response.status == 200 and "attachment" in response.headers.get("Content-Disposition", "") and int(response.headers.get("Content-Length", -1)) == len(payload) and response.read(len(payload) + 1) == payload
                probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(movie)],
                    check=True, capture_output=True, text=True, timeout=6)
                streams = json.loads(probe.stdout)["streams"]
                video = next(s for s in streams if s["codec_type"] == "video")
                audio = next(s for s in streams if s["codec_type"] == "audio")
                checks["independent_ffv1_16bit_alpha_and_stereo_pcm_probe"] = video["codec_name"] == "ffv1" and video["pix_fmt"] == "gbrap16le" and video["width"] == WIDTH and video["height"] == HEIGHT and int(video["nb_read_frames"]) == FRAMES and audio["codec_name"] == "pcm_s16le" and audio["channels"] == 2 and int(audio["sample_rate"]) == 48000
                pictures = decode_rgba16(movie)
                checks["all_actual_master_pictures_decode"] = len(pictures) == WIDTH * HEIGHT * FRAMES
                checks["transformed_master_retains_more_than_eight_bit_color"] = len({p[0] for p in pictures if p[3] > 32768}) > 256
                checks["transparent_background_and_fractional_alpha_survive"] = any(p == (0, 0, 0, 0) for p in pictures) and any(0 < p[3] < 65535 and p[3] % 257 for p in pictures)
                requested = ui.get("processed_frame_url")
                frames = [j for j in jobs if j["kind"] == "frame-preview" and j["state"] == "completed" and j.get("result", {}).get("url") == requested]
                checks["native_viewer_displayed_actual_processed_frame"] = bool(frames)
                if frames:
                    receipt_frame = frames[-1]["result"]
                    png = directory / "previews" / Path(urlsplit(receipt_frame["url"]).path).name
                    frame_data = png.read_bytes()
                    checks["paused_png_is_rgba16_with_verified_digest"] = struct.unpack(">IIBBBBB", frame_data[16:29]) == (WIDTH, HEIGHT, 16, 6, 0, 0, 0) and hashlib.sha256(frame_data).hexdigest() == receipt_frame["sha256"]
                    checks["paused_16bit_samples_match_downloaded_master"] = decode_rgba16(png) == pictures[:WIDTH * HEIGHT]
                    shutil.copy2(png, output / "ENGINE_TEST_high16_processed_frame0.png")
            checks["source_media_identity_preserved"] = asset["sha256"] == source_hash and hashlib.sha256((directory / asset["path"]).read_bytes()).hexdigest() == source_hash
            checks["actual_native_screenshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            if not all(checks.values()): result["error"] = ui.get("error") or "Failed checks: " + ", ".join(k for k, ok in checks.items() if not ok)
        except Exception as error:
            result["error"] = str(error); checks["completed_without_fixture_error"] = False
            if isinstance(error, subprocess.CalledProcessError): result["process_error"] = str(error.stderr)[-1800:]
        finally:
            if server is not None: server.shutdown(); server.server_close()
            if thread is not None: thread.join(timeout=.5)
            if store is not None: store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    result["passed"] = bool(checks) and all(checks.values()) and "error" not in result
    (output / "ENGINE_TEST_high16_native_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual WKWebView/WKDownload acceptance requires macOS; no native result is simulated."})); return 0
    if not args.binary.is_file(): parser.error("Pass the compiled macos/SmokeTest.swift executable.")
    result = run(args.binary, args.output); print(json.dumps(result, sort_keys=True)); return 0 if result["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())

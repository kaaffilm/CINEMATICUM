#!/usr/bin/env python3
"""Real WK export/download/reimport/relink/undo acceptance in an isolated project.

The browser uses ordinary CINEMATICUM controls for all mutations. Download GETs
are read-only, and the returned OTIO bytes are loaded through a real FileList.
"""
from __future__ import annotations

import argparse
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

from server import Server, Store


def run(binary, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    screenshot = output / "ENGINE_TEST_interchange_webkit.png"
    result = {"passed": False, "browser": "WKWebView", "fixture": "ENGINE TEST cut interchange — not a film", "checks": {}}
    checks, started = result["checks"], time.monotonic()
    deadline = started + 17.5

    def budget(maximum, reserve=0):
        remaining = deadline - time.monotonic() - reserve
        if remaining <= .1:
            raise TimeoutError("The interchange acceptance exceeded its 18-second budget.")
        return min(maximum, remaining)

    with tempfile.TemporaryDirectory(prefix="cinematicum-interchange-webkit-TEST-") as temporary:
        work = Path(temporary)
        store = server = thread = project = None
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg or not shutil.which("ffprobe"):
                raise RuntimeError("This media-backed interchange acceptance requires FFmpeg and ffprobe.")
            source = work / "ENGINE_TEST_source.mp4"
            subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1", "-threads", "1",
                            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24000/1001", "-frames:v", "24", "-an",
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-threads", "1", str(source)],
                           check=True, capture_output=True, timeout=budget(4, 12))
            store = Store(work / "workspace")
            project = store.new_project({"name": "ENGINE TEST — Cut interchange", "frame_rate": {"numerator": 24000, "denominator": 1001}, "width": 160, "height": 90})
            asset = store.admit(project["id"], source, source.name)
            project = store.get(project["id"])
            project["clips"] = [{"id": "ENGINE_TEST_first", "asset_id": asset["id"], "track": 0, "start": 0, "in": .5, "duration": 6},
                                {"id": "ENGINE_TEST_second", "asset_id": asset["id"], "track": 0, "start": 9, "in": 6.5, "duration": 6}]
            project["tracks"] = [{"id": 0, "name": "ENGINE TEST picture"}]
            project = store.save(project["id"], project)
            server = Server(0, store)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            # Allow the helper's two-second snapshot fallback to finish before
            # killing it, while reserving cleanup time in the outer budget.
            native_timeout = budget(13.3, 3)
            process = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}",
                                      "--output", str(screenshot), "--script", str(Path(__file__).parent / "macos" / "InterchangeSmoke.js"),
                                      "--timeout", str(round(native_timeout, 2))], capture_output=True, text=True,
                                     timeout=budget(native_timeout + 2.2, .8))
            ui = None
            for line in reversed(process.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict) and "passed" in candidate:
                        ui = candidate
                        break
                except ValueError:
                    pass
            if ui is None:
                raise RuntimeError("WebKit did not return a result: " + (process.stderr or process.stdout)[-2500:])
            result["ui"], result["helper_exit_code"] = ui, process.returncode
            if process.stderr.strip():
                result["helper_stderr_tail"] = process.stderr[-1800:]
            checks["native_interchange_ui_passed"] = ui.get("passed") is True and process.returncode == 0
            for step in ("export_unsaved_edit_and_read_actual_download", "review_exact_roundtrip_with_real_content_hash",
                         "reject_original_json_duplicate_members_without_applying", "explicit_existing_asset_relink_and_warning_review",
                         "replace_timeline_once_and_undo_redo"):
                checks[step] = step in ui.get("steps", [])
            saved = store.get(project["id"])
            clips = sorted(saved["clips"], key=lambda clip: clip["start"])
            checks["cuts_gap_and_fractional_source_in_saved"] = (len(clips) == 2 and [(c["start"], c["duration"], c["in"]) for c in clips] == [(0, 6, 1.75), (9, 6, 6.5)])
            checks["real_existing_media_relinked"] = len(saved["assets"]) == 1 and all(c["asset_id"] == asset["id"] for c in clips)
            checks["rational_clock_preserved"] = saved["frame_rate"] == {"numerator": 24000, "denominator": 1001}
            checks["untranslated_external_effects_not_silently_applied"] = all(c["grade"]["exposure"] == 0 and not c.get("compositor") for c in clips)
            checks["video_only_external_tracks_do_not_duplicate_audio"] = all(c["volume"] == 0 for c in clips)
            checks["explicit_apply_saved_imported_identity"] = clips[0]["id"] == ui.get("imported_clip_id") and clips[0]["id"] != ui.get("original_clip_id")
            exports = list((store.project_dir(project["id"]) / "exports").glob("*.otio"))
            checks["one_actual_export_file"] = len(exports) == 1
            if exports:
                exported_path = exports[0]
                raw = exported_path.read_bytes()
                document = json.loads(raw)
                snapshot = document["metadata"]["cinematicum"]["project"]
                checks["downloaded_bytes_match_export_file"] = len(raw) == ui.get("download_bytes") and Path(urlsplit(ui.get("export_href", "")).path).name == exported_path.name
                checks["unsaved_authoring_snapshot_exported"] = snapshot["clips"][0]["grade"]["exposure"] == .5 and project["clips"][0]["grade"]["exposure"] == 0
                public = [child for track in document["tracks"]["children"] for child in track["children"]]
                gaps = [child for child in public if child["OTIO_SCHEMA"] == "Gap.1"]
                checks["public_otio_gap_is_three_frames"] = len(gaps) == 1 and gaps[0]["source_range"]["duration"]["value"] == 3
                references = [child["media_references"][child["active_media_reference_key"]] for child in public if child["OTIO_SCHEMA"] == "Clip.2"]
                media_path = store.project_dir(project["id"]) / asset["path"]
                identity = hashlib.sha256(media_path.read_bytes()).hexdigest()
                checks["media_reference_hashes_match_real_source"] = all(ref["metadata"]["cinematicum"]["sha256"] == identity and ref["target_url"] == asset["path"] for ref in references)
                shutil.copy2(exported_path, output / "ENGINE_TEST_exported_timeline.otio")
            checks["no_render_or_provider_job_started"] = not store.jobs
            checks["native_snapshot"] = screenshot.is_file() and screenshot.stat().st_size > 1000 and screenshot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            result["passed"] = all(checks.values())
            if not result["passed"]:
                result["error"] = ui.get("error") or "Failed checks: " + ", ".join(key for key, value in checks.items() if not value)
        except Exception as error:
            result["error"] = str(error)
        finally:
            if store and project:
                try:
                    (output / "ENGINE_TEST_interchange_saved_project.json").write_text(json.dumps(store.get(project["id"]), indent=2), encoding="utf-8")
                except Exception as error:
                    result["saved_evidence_error"] = str(error)
            if server:
                server.shutdown()
                server.server_close()
            if thread:
                thread.join(timeout=1)
            if store:
                store.shutdown()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["screenshot"] = str(screenshot) if screenshot.is_file() else None
    (output / "ENGINE_TEST_interchange_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        print(json.dumps({"status": "skipped", "reason": "Actual macOS WKWebView is required; no browser acceptance was claimed."}))
        return 0
    if not args.binary or not args.binary.is_file():
        parser.error("Compile macos/SmokeTest.swift and supply its executable with --binary.")
    output = args.output or Path(tempfile.mkdtemp(prefix="cinematicum-interchange-webkit-TEST-evidence-"))
    result = run(args.binary, output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

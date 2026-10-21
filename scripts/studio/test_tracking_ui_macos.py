#!/usr/bin/env python3
"""Actual WK point pick -> measured motion -> authored mask -> undo/retime/split."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from server import Store, Server
from test_editing_ui_macos import read_helper_result


def run(binary, output):
    from test_tracking import TrackingTests
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    TrackingTests.setUpClass()
    try:
        with tempfile.TemporaryDirectory(prefix="cinematicum-TRACK-WK-") as temporary:
            store = Store(temporary)
            project = store.new_project({"name": "ENGINE TEST measured tracking", "width": 128, "height": 96, "fps": 12})
            source = Path(temporary) / "ENGINE_TEST_moving.mkv"
            shutil.copy2(TrackingTests.root / "media/moving.mkv", source)
            store.admit(project["id"], source, source.name)
            server = Server(0, store); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                process = subprocess.run([str(Path(binary).resolve()), "--url", f"http://127.0.0.1:{server.server_port}", "--output", str(output / "tracking.png"), "--timeout", "14", "--script", str(Path(__file__).parent / "macos/TrackingSmoke.js")], capture_output=True, text=True, timeout=16)
                ui = read_helper_result(process)
                saved = store.get(project["id"]); clips = sorted(saved["clips"], key=lambda c:c["start"])
                checks = {"real_wk_controls": ui.get("passed") is True and process.returncode == 0,
                          "split_two_contiguous_clips": len(clips)==2 and [c["start"] for c in clips]==[0,6] and [c["duration"] for c in clips]==[6,6],
                          "preserved_domain": len(clips)==2 and [c["animation_offset"] for c in clips]==[0,6] and all(c["animation_duration"]==12 for c in clips),
                          "motion_and_mask_saved": len(clips)==2 and all(len(c.get("tracking",{}).get("keys",[]))==2 and len(c.get("compositor",{}).get("nodes",[]))==2 for c in clips)}
                if len(clips)==2:
                    checks["split_motion_curve_identical"] = clips[0]["tracking"]==clips[1]["tracking"]
                    checks["measured_dx_preserved"] = abs(clips[0]["tracking"]["keys"][-1]["x"]+22/128)<1e-7
                    masks = [next(n for n in c["compositor"]["nodes"] if n["type"]=="mask") for c in clips]
                    checks["mask_centers_measured_feature"] = all(abs(m["animation"]["x"][-1]["value"]-58/128)<1e-7 and abs(m["animation"]["y"][-1]["value"]-49/96)<1e-7 for m in masks)
                result={"passed":all(checks.values()),"checks":checks,"ui":ui,"elapsed_seconds":round(time.monotonic()-began,3),"fixture":"SYNTHETIC ENGINE TEST — NOT PRODUCTION MEDIA"}
                (output / "result.json").write_text(json.dumps(result,indent=2)+"\n")
                print(json.dumps(result));return 0 if result["passed"] else 1
            finally:
                server.shutdown();server.server_close();thread.join();store.shutdown()
    finally:
        TrackingTests.tearDownClass()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--binary",required=True);parser.add_argument("--output",required=True);args=parser.parse_args()
    raise SystemExit(run(args.binary,args.output))

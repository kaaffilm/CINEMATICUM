#!/usr/bin/env python3
"""Native modal/workflow/cancellation acceptance, explicitly without inference.

The setup worker is a labelled cancellation fixture. Project workflow writes,
Store job ownership, shipped DOM controls and WKWebView are actual code paths.
The real runtime's install/start/inference acceptance runs separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from managed_generation import default_workflow, load_lock
from server import Server, Store
from test_editing_ui_macos import read_helper_result

HERE = Path(__file__).resolve().parent


class CancellationFixture:
    default_workflow = staticmethod(default_workflow)

    def __init__(self):
        self.operation=None; self.event=None; self.installs=0; self.cancellations=0; self.shutdowns=0
        self.lock=load_lock()

    def status(self):
        total=sum(p["size"] for p in [self.lock["source"], *self.lock["packages"], *self.lock["models"]])
        return {"supported": True, "installed": False, "ready": False, "running": False,
                "runtime_id": "ENGINE-TEST-CANCELLATION-FIXTURE", "source_version": self.lock["source"]["version"],
                "operation": self.operation, "detail": "ENGINE TEST — cancellation fixture; no weights downloaded.",
                "reason": "", "progress": .25 if self.operation else 0, "downloaded_bytes": 0,
                "download_bytes": total, "first_install_required_bytes": total+6*1024**3,
                "free_disk_bytes": total+10*1024**3, "models": [], "model_execution_verified": False}

    def install(self, progress, event):
        self.installs+=1; self.operation="install"; self.event=event; progress(.25)
        try:
            if not event.wait(12): raise RuntimeError("Native cancellation fixture exceeded its bound.")
            self.cancellations+=1; raise RuntimeError("Cancelled labelled setup fixture; no model was installed.")
        finally: self.operation=None; self.event=None

    def shutdown(self):
        self.shutdowns+=1
        if self.event is not None: self.event.set()


def run(binary, evidence):
    evidence=Path(evidence).resolve(); evidence.mkdir(parents=True, exist_ok=True)
    began=time.monotonic(); result={"passed": False, "browser": "WKWebView", "fixture": "CANCELLATION TEST — NO MODEL EXECUTION", "checks": {}}
    checks=result["checks"]
    with tempfile.TemporaryDirectory(prefix="cinematicum-generation-ui-ENGINE-TEST-") as temporary:
        store=server=thread=None; fixture=CancellationFixture()
        try:
            store=Store(Path(temporary)/"workspace"); store.managed_generation=fixture
            project=store.new_project({"name": "ENGINE TEST — local generation controls", "width": 272, "height": 480, "fps": 8})
            server=Server(0,store); thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True); thread.start()
            screenshot=evidence/"ENGINE_TEST_generation_controls.png"
            native=subprocess.run([str(Path(binary).resolve()),"--url",f"http://127.0.0.1:{server.server_port}/","--output",str(screenshot),"--timeout","12.5","--script",str(HERE/"macos"/"GenerationSmoke.js")],capture_output=True,text=True,timeout=14)
            ui=read_helper_result(native); result["ui"]=ui; result["helper_exit_code"]=native.returncode
            checks["native_controls_passed"]=native.returncode==0 and ui.get("passed") is True
            checks["no_browser_errors"]=not ui.get("page_errors",[])
            checks["no_runtime_install_or_inference_claim"]=fixture.status()["installed"] is False and fixture.status()["model_execution_verified"] is False
            saved=store.get(project["id"]); workflow_path=store.project_dir(project["id"])/"workflow.json"
            workflow=json.loads(workflow_path.read_text()) if workflow_path.is_file() else {}
            expected={"width":272,"height":480,"length":9,"steps":4,"fps":8,"cfg":5}
            checks["actual_workflow_file_has_selected_options"]=workflow==default_workflow(expected)
            checks["project_persists_workflow_and_marker_bindings"]=saved.get("settings",{}).get("comfy_workflow_path")=="workflow.json" and saved.get("settings",{}).get("comfy_bindings")=={"negative":True,"seed":True}
            checks["one_setup_job_cancelled_through_store"]=fixture.installs==1 and fixture.cancellations==1
            with store.lock: jobs=[dict(job) for job in store.jobs.values() if job["project_id"]==project["id"]]
            checks["no_duplicate_or_generation_job"]=len(jobs)==1 and jobs[0]["kind"]=="generation-setup" and jobs[0]["state"]=="cancelled"
            checks["no_asset_admitted_by_setup"]=not saved["assets"] and not saved["clips"]
            checks["native_screenshot_written"]=screenshot.is_file() and screenshot.stat().st_size>1000
            (evidence/"ENGINE_TEST_saved_project.json").write_text(json.dumps(saved,indent=2),encoding="utf-8")
            (evidence/"ENGINE_TEST_workflow.json").write_text(json.dumps(workflow,indent=2),encoding="utf-8")
            if native.stderr: result["helper_stderr_tail"]=native.stderr[-1200:]
            if not all(checks.values()): result["error"]=ui.get("error") or "Failed checks: "+", ".join(k for k,v in checks.items() if not v)
        except Exception as error: result["error"]=str(error); checks["completed_without_fixture_error"]=False
        finally:
            if server is not None: server.shutdown(); server.server_close()
            if thread is not None: thread.join(timeout=.2)
            if store is not None: store.shutdown()
    result["elapsed_seconds"]=round(time.monotonic()-began,3); checks["bounded_run"]=result["elapsed_seconds"]<17
    result["passed"]=bool(checks) and all(checks.values()) and "error" not in result
    (evidence/"ENGINE_TEST_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description="Native local-generation settings and owned-job cancellation acceptance")
    parser.add_argument("--binary",type=Path); parser.add_argument("--output",type=Path); args=parser.parse_args()
    if sys.platform!="darwin":
        print(json.dumps({"status":"skipped","reason":"Actual WKWebView acceptance requires macOS; no UI result is simulated."})); return 0
    if not args.binary or not args.binary.is_file(): parser.error("Pass the compiled macos/SmokeTest.swift executable with --binary.")
    result=run(args.binary,args.output or Path(tempfile.mkdtemp(prefix="cinematicum-generation-ENGINE-TEST-evidence-")))
    print(json.dumps(result,sort_keys=True)); return 0 if result["passed"] else 1


if __name__=="__main__": raise SystemExit(main())

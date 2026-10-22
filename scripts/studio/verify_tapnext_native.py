"""Bounded actual macOS TAPNext editor acceptance; synthetic fixture only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from server import Store, Server

SOURCES = ("tapnext_runtime.py", "tapnext_worker.py", "tapnext-runtime-lock.json", "learned_tracking.py",
           "learned_tools.py", "web/learned-tracking-ui.js", "web/app.js", "web/index.html", "server.py")

AUTHOR = r'''
return await(async()=>{
 const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms)),steps=[];
 async function until(fn,message,ms=2500){const end=performance.now()+ms;while(performance.now()<end){if(fn())return;await sleep(20);}throw Error(message+'; '+($('#learned-tracking-dialog [data-status]')?.textContent||$('#toast')?.textContent||''));}
 function click(selector){const el=$(selector);if(!el||el.disabled)throw Error('Unavailable '+selector);el.scrollIntoView({block:'nearest',inline:'nearest'});const r=el.getBoundingClientRect();if(r.width<2||r.height<2||r.top<0||r.bottom>innerHeight+1)throw Error('Unreachable '+selector);el.click();}
 const clip=()=>state.project.clips.find(c=>c.id==='picture');
 try{
  await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST TAPNext'),'Fixture did not bootstrap');
  const item=$('.timeline-clip[data-clip="picture"]'),r=item.getBoundingClientRect();
  item.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:91,isPrimary:true,clientX:r.left+2,clientY:r.top+r.height/2}));
  window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,pointerId:91,isPrimary:true,clientX:r.left+2,clientY:r.top+r.height/2}));
  click('#authoring-tools');await until(()=>$('#authoring-tools-dialog')?.open,'Studio tools did not open');
  click('#learned-tracking-button');
  await until(()=>$('#learned-tracking-dialog [data-backend]')?.value==='tapnext'&&!$('#learned-tracking-dialog [data-run]').disabled,'Independent TAPNext did not become ready',5500);
  const canvas=$('#learned-tracking-dialog [data-canvas]'),bounds=canvas.getBoundingClientRect();
  canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:92,isPrimary:true,clientX:bounds.left+bounds.width*75/256,clientY:bounds.top+bounds.height*135/256}));
  const recipe=JSON.parse($('#learned-tracking-dialog [data-recipe]').value);
  if(recipe.backend!=='tapnext'||!recipe.points.some(p=>p.id==='point_1'))throw Error('Native canvas did not author the TAPNext point');
  click('#learned-tracking-dialog [data-save]');
  await until(()=>$('#learned-tracking-dialog [data-status]').textContent.startsWith('Prompt recipe saved'),'Native prompt save failed');steps.push('native_TAPNext_query_and_prompt_save');
  click('#learned-tracking-dialog [data-run]');
  await until(()=>!$('#learned-tracking-dialog [data-result]').hidden&&!$('#learned-tracking-dialog [data-apply-point]').disabled,'Actual TAPNext inference did not complete',10000);
  const point=$('#learned-tracking-dialog [data-point]');point.value='point_1';point.dispatchEvent(new Event('change',{bubbles:true}));
  click('#learned-tracking-dialog [data-apply-point]');
  await until(()=>$('#learned-tracking-dialog [data-status]').textContent.startsWith('Measured stabilization'),'Native point application failed');
  if(!clip().tracking||clip().learned_bindings?.[0]?.backend!=='tapnext')throw Error('The native edit lost its TAPNext binding');steps.push('native_actual_TAPNext_inference_and_apply');
  click('#learned-tracking-dialog [data-close]');await until(()=>!$('#learned-tracking-dialog').open,'Learned dialog did not close');
  click('#undo-button');if(clip().tracking)throw Error('Native Undo did not restore the previous motion');
  click('#redo-button');if(!clip().tracking||clip().learned_bindings?.[0]?.backend!=='tapnext')throw Error('Native Redo did not restore the measured motion');steps.push('native_undo_redo');
  click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Native project save failed');steps.push('native_save');
  return {passed:true,steps,backend:clip().learned_recipe.backend,query_count:clip().learned_recipe.points.length};
 }catch(error){return {passed:false,steps,error:error.message,toast:$('#toast')?.textContent};}
})();
'''

REOPEN = r'''
return await(async()=>{
 const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const end=performance.now()+4000;
 while(performance.now()<end&&!$('#viewer-project')?.textContent.includes('ENGINE TEST TAPNext'))await sleep(20);
 const clip=state.project.clips.find(c=>c.id==='picture');
 const checks={actual_native_reopen:Boolean(clip?.tracking),checkpoint_backend:clip?.learned_bindings?.[0]?.backend==='tapnext',recipe_restored:clip?.learned_recipe?.backend==='tapnext',binding_current:!clip?.learned_bindings?.[0]?.invalidated};
 return {passed:Object.values(checks).every(Boolean),checks};
})();
'''


def prepare(output):
    import numpy as np
    output.mkdir(parents=True, exist_ok=False)
    yy, xx = np.mgrid[:256, :256]
    background = np.stack([35+(xx//16)%2*8, 47+(yy//16)%2*8, 70+(xx//32+yy//32)%2*9], axis=-1).astype(np.uint8)
    texture = np.random.default_rng(72351).integers(0, 256, (52, 52, 3), dtype=np.uint8)
    texture[:, :, 0] = 160 + texture[:, :, 0]//3
    texture[:, :, 1:] //= 3
    frames = []
    for index in range(2):
        cx, cy = 75+14*index, 135
        image = background.copy()
        mask = (xx-cx)**2+(yy-cy)**2 <= 24**2
        region = image[cy-26:cy+26, cx-26:cx+26]
        local = mask[cy-26:cy+26, cx-26:cx+26]
        region[local] = texture[local]
        frames.append(image)
    source = output / "ENGINE_TEST_TAPNext_source.mkv"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "256x256",
                    "-r", "24", "-i", "pipe:0", "-an", "-c:v", "ffv1", "-level", "3", "-pix_fmt", "bgr0", "-threads", "1", str(source)],
                   input=np.stack(frames).tobytes(), check=True, timeout=5)
    store = Store(output / "workspace")
    try:
        project = store.new_project({"name": "ENGINE TEST TAPNext native", "width": 256, "height": 256, "fps": 24})
        asset = store.admit(project["id"], source, source.name, {"fixture": "SYNTHETIC ENGINE TEST"})
        project = store.get(project["id"])
        project["clips"] = [{"id": "picture", "asset_id": asset["id"], "start": 0, "in": 0, "duration": 2, "track": 0,
                             "learned_recipe": {"version": 1, "backend": "tapnext", "frame_start": 0, "frame_count": 2,
                                                "points": [{"id": "center", "frame": 0, "x": 75/256, "y": 135/256}]}}]
        store.save(project["id"], project)
        report = {"passed": True, "project_id": project["id"], "asset_id": asset["id"], "source_sha256": asset["sha256"],
                  "fixture": "SYNTHETIC ENGINE TEST; NOT PRODUCTION MEDIA"}
        (output / "fixture.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        store.shutdown()


def run(output, phase, binary, expected):
    if sys.platform != "darwin" or not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
        raise ValueError("Supply the exact hash-pinned macOS native helper")
    report_path = output / (phase + "-report.json")
    if report_path.exists():
        raise ValueError("Native evidence cannot overwrite a previous execution")
    source = Path(__file__).parent
    before = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in SOURCES}
    fixture = json.loads((output / "fixture.json").read_text())
    store = Store(output / "workspace")
    server = Server(0, store)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    started = time.monotonic()
    report = {"passed": False, "phase": phase, "source_sha256": before}
    try:
        script = output / (phase + ".js")
        script.write_text(AUTHOR if phase == "author" else REOPEN)
        screenshot = output / (phase + ".png")
        process = subprocess.run([str(binary), "--url", "http://127.0.0.1:" + str(server.server_port), "--script", str(script),
                                  "--output", str(screenshot), "--timeout", "17"], capture_output=True, text=True, timeout=18)
        ui = None
        for line in reversed(process.stdout.splitlines()):
            try:
                row = json.loads(line)
                if isinstance(row, dict) and "passed" in row:
                    ui = row
                    break
            except ValueError:
                pass
        project = store.get(fixture["project_id"])
        clip = project["clips"][0]
        binding = clip.get("learned_bindings", [{}])[0]
        checks = {"actual_native_controls": process.returncode == 0 and ui is not None and ui.get("passed") is True,
                  "native_screenshot": screenshot.is_file() and screenshot.stat().st_size > 1000,
                  "saved_actual_motion": bool(clip.get("tracking")), "saved_TAPNext_recipe": clip.get("learned_recipe", {}).get("backend") == "tapnext",
                  "saved_TAPNext_binding": binding.get("backend") == "tapnext" and not binding.get("invalidated"),
                  "original_media_preserved": hashlib.sha256(store.asset(project["id"], fixture["asset_id"])[1].read_bytes()).hexdigest() == fixture["source_sha256"],
                  "source_unchanged": before == {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in SOURCES},
                  "pinned_helper_unchanged": hashlib.sha256(binary.read_bytes()).hexdigest() == expected}
        report.update(ui=ui, checks=checks, passed=all(checks.values()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=.3)
        store.shutdown()
    report["elapsed_seconds"] = time.monotonic() - started
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("prepare", "author", "reopen"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--binary-sha256")
    args = parser.parse_args()
    result = prepare(args.output) if args.phase == "prepare" else run(args.output, args.phase, args.binary, args.binary_sha256)
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)

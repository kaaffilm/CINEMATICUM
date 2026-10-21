#!/usr/bin/env python3
"""Independently verify an actual completed managed Wan generation job.

This reads its immutable job snapshot, admitted bytes and provenance. It never
starts an engine, submits a prompt, rewrites a project, or substitutes test media.
No CINEMATICUM production module is imported by this verifier.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import time
import zlib

TOKENS = {"CINEMATICUM_POSITIVE_PROMPT": "positive", "CINEMATICUM_NEGATIVE_PROMPT": "negative"}
PATTERN = re.compile("|".join(TOKENS))
CORE_NODES = {"UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "EmptyHunyuanLatentVideo",
              "ModelSamplingSD3", "KSampler", "VAEDecodeTiled", "CreateVideo", "SaveVideo"}


def read_object(path, limit=4*1024*1024):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise ValueError("Acceptance metadata must be a bounded regular file: "+str(path))
    raw=path.read_bytes(); value=json.loads(raw)
    if not isinstance(value,dict): raise ValueError("Acceptance metadata must be an object.")
    return value,raw


def content_hash(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()


def one_node(workflow,kind):
    items=[(key,node) for key,node in workflow.items() if node.get("class_type")==kind]
    if len(items)!=1: raise ValueError("Expected exactly one "+kind+" in the submitted Wan graph.")
    return items[0]


def bind_snapshot(snapshot):
    counts={"positive":0,"negative":0,"seed":0}
    texts={"positive":snapshot["prompt"],"negative":snapshot["negative"]}
    def visit(value):
        if isinstance(value,list): return [visit(item) for item in value]
        if isinstance(value,dict): return {key:visit(item) for key,item in value.items()}
        if not isinstance(value,str): return value
        if value=="CINEMATICUM_SEED": counts["seed"]+=1; return snapshot["seed"]
        if "CINEMATICUM_SEED" in value: raise ValueError("Submitted seed marker was not a whole input value.")
        def replacement(match):
            kind=TOKENS[match.group()]; counts[kind]+=1; return texts[kind]
        return PATTERN.sub(replacement,value)
    # Only inputs are bound. Regex substitution does not reinterpret tokens
    # appearing inside the actual authored prompt or negative prompt.
    graph={key:{**node,"inputs":visit(node["inputs"])} for key,node in snapshot["workflow"].items()}
    digest=hashlib.sha256(json.dumps(graph,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return graph,counts,digest


def sample_grid(rgb,width,height,columns=12,rows=8):
    values=[]
    for row in range(rows):
        y=min(height-1,int((row+.5)*height/rows))
        for column in range(columns):
            x=min(width-1,int((column+.5)*width/columns)); offset=(y*width+x)*3
            values.extend(rgb[offset:offset+3])
    return values


def write_png(path,rgb,width,height):
    def chunk(kind,data): return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    lines=b"".join(b"\0"+rgb[y*width*3:(y+1)*width*3] for y in range(height))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))
                          +chunk(b"IDAT",zlib.compress(lines))+chunk(b"IEND",b""))


def verify_take(project_dir,job_json,job_snapshot=None,evidence=None,timeout=8):
    began=time.monotonic(); deadline=began+min(12,float(timeout))
    checks={}; report={"passed":False,"scope":"Actual completed Wan take; no generated or rendered substitute", "checks":checks}
    context={}
    if evidence is not None:
        evidence=Path(evidence).resolve(); evidence.mkdir(parents=True,exist_ok=True)
    def run(command,maximum):
        budget=min(maximum,deadline-time.monotonic())
        if budget<=.1: raise TimeoutError("Generated-take verification exceeded its deadline.")
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            stdout,stderr=process.communicate(timeout=budget)
            if process.returncode: raise RuntimeError(stderr.decode(errors="replace")[-1800:])
            return stdout
        finally:
            if process.poll() is None:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                process.communicate(timeout=.5)
    try:
        directory=Path(project_dir).resolve(strict=True)
        body,job_raw=read_object(job_json); job=body.get("job",body)
        if job.get("state")!="completed" or job.get("kind")!="generate": raise ValueError("Select an actual completed generation job.")
        if not re.fullmatch(r"[a-f0-9]{32}",job.get("id","")): raise ValueError("Invalid completed job ID.")
        if directory.name!=job["project_id"]: raise ValueError("The selected project directory does not own this job.")
        snapshot_path=Path(job_snapshot) if job_snapshot else directory.parent.parent/"jobs"/(job["id"]+".snapshot")
        snapshot,snapshot_raw=read_object(snapshot_path)
        if set(snapshot)!={"prompt","negative","seed","workflow"}: raise ValueError("The job did not preserve its generation request and workflow.")
        workflow=snapshot["workflow"]; graph,counts,bound_sha=bind_snapshot(snapshot)
        result=job["result"]; asset=result["asset"]; provenance=asset["provenance"]
        source=(directory/asset["path"]).resolve(strict=True)
        if not source.is_relative_to(directory/"media") or not source.is_file() or source.stat().st_size>128*1024*1024:
            raise ValueError("Expected a bounded admitted video inside this project's media folder.")
        source_sha=content_hash(source)
        document,_=read_object(directory/"project.json")
        stored=next((a for a in document["assets"] if a.get("id")==asset["id"]),None)
        checks["completed_asset_is_admitted_in_own_project"]=stored==asset and result["url"]=="/api/projects/%s/media/%s"%(job["project_id"],asset["id"])
        checks["admitted_bytes_match_both_hash_receipts"]=source_sha==asset["sha256"]==provenance["output_sha256"] and source.stat().st_size==asset["size"]
        checks["actual_comfy_prompt_identity_retained"]=provenance.get("backend")=="comfyui" and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,256}",provenance.get("prompt_id","")))
        checks["submitted_workflow_binding_hash_matches"]=bound_sha==provenance.get("workflow_sha256")
        checks["all_three_marker_bindings_and_seed_match"]=counts==provenance.get("marker_bindings")=={"positive":1,"negative":1,"seed":1} and provenance.get("seed_bound") is True and provenance.get("requested_seed")==snapshot["seed"]
        checks["submitted_graph_uses_only_core_wan_nodes"]=len(workflow)==11 and {n["class_type"] for n in workflow.values()}==CORE_NODES
        latent=one_node(workflow,"EmptyHunyuanLatentVideo")[1]["inputs"]
        video=one_node(workflow,"CreateVideo")[1]["inputs"]
        sampler=one_node(graph,"KSampler")[1]["inputs"]
        output_id,output=one_node(workflow,"SaveVideo")
        width,height,length,fps=latent["width"],latent["height"],latent["length"],video["fps"]
        if any(type(v)is not int for v in (width,height,length)) or not 1<=length<=81 or min(width,height)<16 or width*height*length*3>64*1024*1024:
            raise ValueError("The requested clip exceeds this bounded acceptance decoder's limits.")
        if isinstance(fps,bool) or not isinstance(fps,(float,int)) or not math.isfinite(fps) or not 1<=fps<=60:
            raise ValueError("The submitted video rate is invalid.")
        checks["expected_wan_models_and_output_node"]=one_node(workflow,"UNETLoader")[1]["inputs"]["unet_name"]=="wan2.1_t2v_1.3B_fp16.safetensors" and one_node(workflow,"CLIPLoader")[1]["inputs"]["clip_name"]=="umt5_xxl_fp8_e4m3fn_scaled.safetensors" and one_node(workflow,"VAELoader")[1]["inputs"]["vae_name"]=="wan_2.1_vae.safetensors" and provenance.get("output_node")==output_id and output["inputs"]["format"]=="mp4"
        current,current_raw=read_object(directory/"workflow.json")
        # A later take may legitimately use a different workflow. The immutable
        # job snapshot above is authoritative for this submitted generation.
        report["current_workflow_matches_this_submission"]=current==workflow
        report["current_workflow_sha256"]=hashlib.sha256(current_raw).hexdigest()
        ffmpeg,ffprobe=shutil.which("ffmpeg"),shutil.which("ffprobe")
        if not ffmpeg or not ffprobe: raise RuntimeError("FFmpeg and ffprobe are needed to verify every actual output frame.")
        metadata=json.loads(run([ffprobe,"-v","error","-count_frames","-show_frames","-show_entries",
            "stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames,duration:frame=media_type,best_effort_timestamp_time",
            "-of","json",str(source)],3))
        streams=metadata["streams"]; stream=streams[0]; frames=[f for f in metadata["frames"] if f.get("media_type")=="video"]
        checks["actual_codec_dimensions_and_frame_count"]=len(streams)==1 and stream.get("codec_type")=="video" and stream.get("codec_name")=="h264" and (stream.get("width"),stream.get("height"))==(width,height) and int(stream.get("nb_read_frames",0))==length and len(frames)==length
        checks["actual_rate_and_duration_match_workflow"]=abs(float(Fraction(stream["avg_frame_rate"]))-fps)<1e-6 and abs(float(stream["duration"])-length/fps)<=max(.000002,.001/fps)
        times=[float(frame["best_effort_timestamp_time"]) for frame in frames]
        checks["every_frame_has_expected_timestamp"]=len(times)==length and all(abs(moment-index/fps)<.000002 for index,moment in enumerate(times))
        pixels=run([ffmpeg,"-v","error","-nostdin","-threads","1","-i",str(source),"-map","0:v:0","-an","-frames:v",str(length+1),"-threads","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],4)
        stride=width*height*3
        checks["every_requested_frame_decodes"]=len(pixels)==length*stride
        if not checks["every_requested_frame_decodes"]: raise ValueError("Decoded byte count differs from the requested number of frames.")
        pictures=[pixels[index*stride:(index+1)*stride] for index in range(length)]
        grids=[sample_grid(picture,width,height) for picture in pictures]
        hashes=[hashlib.sha256(picture).hexdigest() for picture in pictures]
        stats=[]
        for index,(picture,grid) in enumerate(zip(pictures,grids)):
            luma=[(54*grid[i]+183*grid[i+1]+19*grid[i+2])/256 for i in range(0,len(grid),3)]
            mean=sum(luma)/len(luma); deviation=math.sqrt(sum((v-mean)**2 for v in luma)/len(luma))
            stats.append({"frame":index,"sha256":hashes[index],"min":min(picture),"max":max(picture),"mean_luma":round(mean,4),"luma_std":round(deviation,4),"luma_range":round(max(luma)-min(luma),4)})
        checks["all_decoded_frames_are_unique"]=len(set(hashes))==length
        checks["all_frames_contain_nonblank_picture"]=all(1<item["mean_luma"]<254 and item["luma_std"]>.5 and item["luma_range"]>3 for item in stats)
        checks["source_and_snapshot_remain_unchanged"]=content_hash(source)==source_sha and content_hash(snapshot_path)==hashlib.sha256(snapshot_raw).hexdigest()
        report.update(job_id=job["id"],project_id=job["project_id"],asset_id=asset["id"],source_sha256=source_sha,
            snapshot_sha256=hashlib.sha256(snapshot_raw).hexdigest(),job_document_sha256=hashlib.sha256(job_raw).hexdigest(),
            workflow_sha256=bound_sha,prompt_id=provenance["prompt_id"],requested_seed=snapshot["seed"],
            requested={"width":width,"height":height,"frames":length,"fps":fps,"duration":length/fps,"steps":sampler["steps"],"cfg":sampler["cfg"]},
            decoded_frames=stats,metadata=metadata)
        context={"source":source,"asset":asset,"width":width,"height":height,"length":length,"fps":fps,"grids":grids,
                 "source_sha256":source_sha,"snapshot_path":snapshot_path,"snapshot_sha256":report["snapshot_sha256"]}
        if evidence is not None:
            for index in sorted({0,length//2,length-1}): write_png(evidence/("ENGINE_TEST_generated_frame_%03d.png"%index),pictures[index],width,height)
        report["passed"]=bool(checks) and all(checks.values())
        if not report["passed"]: report["error"]="Failed checks: "+", ".join(name for name,value in checks.items() if not value)
    except Exception as error: report["error"]=str(error)
    report["elapsed_seconds"]=round(time.monotonic()-began,3)
    if evidence is not None: (evidence/"ENGINE_TEST_generated_take_report.json").write_text(json.dumps(report,indent=2)+"\n")
    return report,context


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir",required=True,type=Path); parser.add_argument("--job-json",required=True,type=Path)
    parser.add_argument("--job-snapshot",type=Path); parser.add_argument("--evidence",required=True,type=Path)
    args=parser.parse_args(); report,_=verify_take(args.project_dir,args.job_json,args.job_snapshot,args.evidence)
    print(json.dumps(report,sort_keys=True)); return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())

"""Owned preparation and identity checks for authored cubic-mask streams."""
from __future__ import annotations

import hashlib
from fractions import Fraction
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time


def prepare_roto_mask(node, width, height, scratch, *, frame_offset=0, frame_count=1,
                      animation_start=0, animation_duration=None, rate="24",
                      cancel_event=None, timeout=600):
    if __package__:
        from .compositor import validate_graph
        from .imaging import find_imaging_python
        from .lens_assets import _stop
    else:
        from compositor import validate_graph
        from imaging import find_imaging_python
        from lens_assets import _stop
    source = {"id":"source","type":"source","inputs":[],"params":{}}
    raw = dict(node); raw["id"]="roto";raw["inputs"]=["source"]
    normalized = validate_graph({"version":1,"nodes":[source,raw],"output":"roto"},width,height,
                                animation_start=animation_start,animation_duration=animation_duration)["nodes"][1]
    request = {"version":1,"node":normalized,"width":width,"height":height,
               "frame_offset":frame_offset,"frame_count":frame_count,"animation_start":animation_start,
               "animation_duration":animation_duration or 1296000,"rate":str(rate)}
    encoded = json.dumps(request, sort_keys=True, separators=(",",":"), allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Bezier mask preparation cancelled.")
    directory = Path(tempfile.mkdtemp(prefix="roto-"+digest[:12]+"-",dir=str(scratch)))
    executable = find_imaging_python() or sys.executable
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith(("PYTHON","OCIO")):
            environment.pop(key,None)
    environment.update(OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2")
    command = [executable,"-I",str(Path(__file__).with_name("roto.py")),"--render",str(directory)]
    with tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as outgoing, tempfile.TemporaryFile() as errors:
        incoming.write(encoded);incoming.seek(0)
        process = subprocess.Popen(command,stdin=incoming,stdout=outgoing,stderr=errors,start_new_session=True,env=environment)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Bezier mask preparation cancelled.")
                if time.monotonic()-started > timeout:
                    raise RuntimeError("Bezier mask preparation exceeded its time limit.")
                if cancel_event is not None: cancel_event.wait(.05)
                else: time.sleep(.05)
            errors.seek(0);detail=errors.read(8192).decode(errors="replace")
            if process.returncode:
                raise ValueError("Bezier mask preparation failed: "+detail[-2400:])
            outgoing.seek(0);response=outgoing.read(65537)
            if len(response)>65536:
                raise ValueError("Bezier mask receipt exceeds its size limit.")
        finally:
            _stop(process)
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Bezier mask preparation cancelled.")
    receipt=json.loads(response)
    static = not any(keys for name,keys in normalized.get("animation",{}).items() if name!="points") or frame_count==1
    name="mask.png" if static else "mask.nut"
    if (not isinstance(receipt,dict) or type(receipt.get("version")) is not int or receipt["version"]!=1
            or receipt.get("request_sha256")!=digest or receipt.get("width")!=width or receipt.get("height")!=height
            or receipt.get("frame_count")!=frame_count or receipt.get("frame_offset")!=frame_offset
            or receipt.get("rate")!=str(Fraction(rate))
            or receipt.get("backend")!="numpy-tiled-cubic" or receipt.get("file")!=name
            or receipt.get("static") is not static or receipt.get("bit_depth")!=16
            or receipt.get("sampling")!=2 or receipt.get("flatten_error_pixels")!=.125):
        raise ValueError("Bezier mask receipt does not match its authored path, range and precision.")
    path=directory/name
    if {p.name for p in directory.iterdir()}!={name} or path.is_symlink() or not path.is_file() or not 33<=path.stat().st_size<=4*1024**3:
        raise ValueError("Bezier worker produced unexpected files or exceeded its disk budget.")
    hasher=hashlib.sha256()
    with path.open("rb") as stream:
        header=stream.read(33);hasher.update(header)
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Bezier mask preparation cancelled.")
            hasher.update(chunk)
    if receipt.get("bytes")!=path.stat().st_size or receipt.get("sha256")!=hasher.hexdigest():
        raise ValueError("Bezier mask output does not match its content identity.")
    if static:
        if (header[:8]!=b"\x89PNG\r\n\x1a\n" or header[8:16]!=b"\x00\x00\x00\rIHDR"
                or struct.unpack(">IIBBBBB",header[16:29])!=(width,height,16,0,0,0,0)):
            raise ValueError("Bezier mask PNG has incorrect dimensions or precision.")
    elif not header.startswith(b"nut/multimedia container\x00"):
        raise ValueError("Animated Bezier mask has an unexpected container.")
    return {"path":path,"static":static,"receipt":receipt}

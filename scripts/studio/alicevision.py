"""Owned Meshroom/AliceVision dense photogrammetry, with actual engine outputs.

The MPL-2.0 upstream pipeline is pinned separately. Runtime configuration never
certifies reconstruction quality or GPU readiness: only a completed owned job
with validated source-bound outputs records an actual dense reconstruction.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import tempfile
import time
import zipfile
import zlib

GRAPH=Path(__file__).with_name("alicevision-photogrammetry-2025.1.mg")
GRAPH_SHA256="b9ca66655bb4fb6eacff1695c0502d17c71c29f00884fe4d2a522a4c9d7edde4"
UPSTREAM={"meshroom":"024b6f398c67bec4968a29a2c5744e49e2bab9b8",
          "alicevision":"928bac2689461ffb6f0174609f983a16bdbd2b30",
          "graph":"https://github.com/alicevision/AliceVision/blob/928bac2689461ffb6f0174609f983a16bdbd2b30/meshroom/photogrammetry.mg"}
ARTIFACT_NAMES=frozenset({"textured-mesh.zip","pipeline.mg","cameras.sfm","alicevision.json","provenance.json"})
MAX_CACHE_BYTES=8*1024*1024*1024
MAX_OUTPUT_BYTES=512*1024*1024
MAX_SECONDS=900
_ID=re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_NAME=re.compile(r"[A-Za-z0-9_.-]{1,160}\Z")


def _json(value):
    return (json.dumps(value,sort_keys=True,allow_nan=False,indent=2)+"\n").encode()


def _regular(path,limit):
    path=Path(path)
    if path.is_symlink():raise ValueError("Dense reconstruction cannot consume symbolic-link files.")
    with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)),"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:raise ValueError("Dense reconstruction file is empty, nonregular or oversized.")
        digest=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
        after=os.fstat(stream.fileno())
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError("Dense reconstruction file changed during verification.")
    return digest.hexdigest(),before.st_size


def _check(event,deadline):
    if event is not None and event.is_set():raise InterruptedError("Dense reconstruction cancelled.")
    if time.monotonic()>deadline:raise TimeoutError("Dense reconstruction exceeded its owned 15-minute execution budget.")


def validate_recipe(recipe,project):
    if not isinstance(recipe,dict) or set(recipe)!={"operation","settings"} or recipe.get("operation")!="meshroom_dense":
        raise ValueError("Expected the typed Meshroom dense reconstruction operation.")
    value=recipe["settings"]
    defaults={"version":1,"asset_ids":[],"downscale":4,"texture_side":2048,"require_all_images":True}
    if not isinstance(value,dict) or set(value)-set(defaults) or type(value.get("version")) is not int or value["version"]!=1:
        raise ValueError("Unsupported Meshroom settings.")
    result={**defaults,**copy.deepcopy(value)};ids=result["asset_ids"]
    if not isinstance(ids,list) or not 3<=len(ids)<=48 or any(not isinstance(v,str) or not _ID.fullmatch(v) for v in ids) or len(set(ids))!=len(ids):
        raise ValueError("Select 3–48 unique admitted photographs for dense reconstruction.")
    if type(result["downscale"]) is not int or result["downscale"] not in {2,4,8,16}:
        raise ValueError("Dense depth-map downscale must be 2, 4, 8 or 16.")
    if type(result["texture_side"]) is not int or result["texture_side"] not in {1024,2048}:
        raise ValueError("Dense texture atlases are bounded to 1024 or 2048 pixels.")
    if type(result["require_all_images"]) is not bool:raise ValueError("Image registration policy must be explicit.")
    total=0
    for ident in ids:
        matches=[a for a in project.get("assets",[]) if isinstance(a,dict) and a.get("id")==ident]
        if len(matches)!=1 or matches[0].get("kind")!="image":raise ValueError("Dense reconstruction inputs must be admitted still photographs.")
        asset=matches[0]
        if Path(asset.get("path","")).suffix.lower() not in {".png",".jpg",".jpeg"}:raise ValueError("Dense reconstruction accepts PNG or JPEG photographs.")
        width,height=asset.get("width"),asset.get("height")
        if any(type(v) is not int or not 32<=v<=8192 for v in (width,height)) or width*height>16*1024*1024:
            raise ValueError("Each dense input is bounded to 16 megapixels and an 8192-pixel edge.")
        total+=width*height
    if total>128*1024*1024:raise ValueError("Dense inputs exceed the 128-megapixel aggregate budget.")
    return {"operation":"meshroom_dense","settings":result}


def _runtime_paths():
    batch=os.environ.get("CINEMATICUM_MESHROOM_BATCH")
    if not batch:raise RuntimeError("No Meshroom runtime is configured; the existing CPU COLMAP runtime does not execute this dense graph.")
    batch=Path(batch).expanduser()
    compute=Path(os.environ.get("CINEMATICUM_MESHROOM_COMPUTE",str(batch.with_name("meshroom_compute")))).expanduser()
    for path in (batch,compute):
        if not path.is_absolute() or not path.is_file() or not os.access(path,os.X_OK):
            raise RuntimeError("Meshroom requires absolute executable batch and compute entrypoints.")
        _regular(path,512*1024*1024)
    return batch,compute


def _stop(process):
    # A launcher may exit while its process-group descendants are still live.
    # Custody follows the owned group, including after leader completion.
    try:
        os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    if process.poll() is None:
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    if process.poll() is None:process.wait(timeout=2)


def _environment(directory):
    # This is not a CPU/GPU memory guarantee. The owned process and scratch
    # budgets below remain enforced even when an upstream node chooses threads.
    temporary=Path(directory)/"engine-tmp";temporary.mkdir(mode=0o700,exist_ok=True)
    if temporary.is_symlink() or not temporary.is_dir():raise ValueError("Meshroom requires its private owned temporary directory.")
    env={key:value for key,value in os.environ.items() if not key.startswith(("PYTHON","MESHROOM_CACHE"))}
    env.update(TMPDIR=str(temporary),TMP=str(temporary),TEMP=str(temporary))
    return env


def _scratch_budget(directory):
    total=count=0
    for folder,dirs,files in os.walk(directory,followlinks=False):
        for name in [*dirs,*files]:
            path=Path(folder)/name
            if path.is_symlink():raise RuntimeError("Dense reconstruction produced a symbolic link in its owned scratch tree.")
        for name in files:
            try:record=(Path(folder)/name).stat()
            except FileNotFoundError:continue  # Upstream may atomically replace a live cache file.
            count+=1;total+=record.st_size
            if not stat.S_ISREG(record.st_mode) or count>20000 or total>MAX_CACHE_BYTES:
                raise RuntimeError("Dense reconstruction exceeded its 8-GiB/20,000-file scratch budget.")


def _execute(argv,directory,label,event,deadline,probe=False):
    _check(event,deadline)
    stdout=Path(directory)/(label+".stdout");stderr=Path(directory)/(label+".stderr")
    with stdout.open("wb") as out,stderr.open("wb") as err:
        process=subprocess.Popen([str(v) for v in argv],cwd=directory,stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,env=_environment(directory),start_new_session=True)
        try:
            checked=0.
            while process.poll() is None:
                _check(event,deadline)
                if stdout.stat().st_size+stderr.stat().st_size>(256*1024 if probe else 16*1024*1024):
                    raise RuntimeError("Meshroom exceeded its bounded diagnostic output.")
                if not probe and time.monotonic()-checked>.5:_scratch_budget(directory);checked=time.monotonic()
                event.wait(.1) if event is not None else time.sleep(.1)
            _check(event,deadline)
        finally:_stop(process)
    if stdout.stat().st_size+stderr.stat().st_size>(256*1024 if probe else 16*1024*1024):
        raise RuntimeError("Meshroom exceeded its bounded diagnostic output.")
    if process.returncode:raise RuntimeError("Meshroom failed: "+stderr.read_text(errors="replace")[-1800:])
    if not probe:_scratch_budget(directory)
    return stdout.read_text(errors="replace") if probe else None


def _commands(batch,compute,photos,published,cache,saved,settings):
    prepare=[batch,"--pipeline",GRAPH,"--input",photos,"--output",published,"--cache",cache,"--save",saved,
        "--paramOverrides",f"DepthMap_1.downscale={settings['downscale']}",f"Texturing_1.textureSide={settings['texture_side']}",
        "Texturing_1.outputMeshFileType=obj","Texturing_1.colorMapping.colorMappingFileType=png","--compute","no"]
    return prepare,[compute,saved,"--cache",cache,"--toNode","Publish_1"]


def capabilities():
    result={"available":False,"operations":[],"runtime_interface_verified":False,"actual_dense_acceptance":False,
            "graph_release":"2025.1.0","graph_sha256":GRAPH_SHA256,"reason":None,
            "limits":{"photos":48,"seconds":MAX_SECONDS,"scratch_bytes":MAX_CACHE_BYTES,"output_bytes":MAX_OUTPUT_BYTES},
            "scope":"Configured Meshroom graph execution through dense depth maps, meshing, filtering and UV texturing. A CLI probe does not certify GPU availability or reconstruction quality."}
    try:
        batch,compute=_runtime_paths()
        if _regular(GRAPH,65536)[0]!=GRAPH_SHA256:raise RuntimeError("The pinned upstream dense graph changed.")
        with tempfile.TemporaryDirectory(prefix="cinematicum-meshroom-probe-") as directory:
            first=_execute([batch,"--help"],directory,"batch-help",None,time.monotonic()+5,probe=True)
            second=_execute([compute,"--help"],directory,"compute-help",None,time.monotonic()+5,probe=True)
        if not all(flag in first for flag in ("--pipeline","--input","--save","--cache","--compute","--paramOverrides")) or not all(flag in second for flag in ("--cache","--toNode")):
            raise RuntimeError("The configured Meshroom CLI does not expose the required official graph interface.")
        result.update(available=True,operations=["meshroom_dense"],runtime_interface_verified=True,
            entrypoints={"batch_sha256":_regular(batch,512*1024*1024)[0],"compute_sha256":_regular(compute,512*1024*1024)[0]},
            reason="CLI interface verified; actual dense GPU execution and media acceptance remain unverified until an owned job completes.")
    except (OSError,ValueError,RuntimeError,TimeoutError,subprocess.TimeoutExpired) as exc:result["reason"]=str(exc)
    return result


def validate_graph(value,inputs,settings):
    if _regular(GRAPH,65536)[0]!=GRAPH_SHA256:raise ValueError("The pinned upstream graph changed.")
    template=json.loads(GRAPH.read_text())
    if not isinstance(value,dict) or not isinstance(value.get("graph"),dict):raise ValueError("Meshroom did not save a graph document.")
    graph=value["graph"]
    if set(graph)!=set(template["graph"]):raise ValueError("The configured graph must retain every pinned dense stage and no additional nodes.")
    versions=value.get("header",{}).get("nodesVersions",{})
    for name,node in template["graph"].items():
        actual=graph[name]
        if not isinstance(actual,dict) or actual.get("nodeType")!=node["nodeType"] or versions.get(node["nodeType"])!=template["header"]["nodesVersions"][node["nodeType"]]:
            raise ValueError("Meshroom node versions differ from the pinned 2025.1 graph contract.")
        actual_inputs=actual.get("inputs",{})
        if not isinstance(actual_inputs,dict):raise ValueError("A dense graph node has invalid inputs.")
        for key,link in node["inputs"].items():
            if actual_inputs.get(key)!=link:raise ValueError("The dense graph lost a required upstream stage connection.")
    viewpoints=graph["CameraInit_1"]["inputs"].get("viewpoints",[])
    if not isinstance(viewpoints,list) or sorted(v.get("path") for v in viewpoints if isinstance(v,dict))!=sorted(inputs):
        raise ValueError("The dense graph's photographs differ from its admitted source copies.")
    if graph["DepthMap_1"]["inputs"].get("downscale")!=settings["downscale"]:
        raise ValueError("The depth-map scale was not applied by Meshroom.")
    texturing=graph["Texturing_1"]["inputs"]
    if texturing.get("textureSide")!=settings["texture_side"] or texturing.get("outputMeshFileType")!="obj" or texturing.get("colorMapping",{}).get("colorMappingFileType")!="png":
        raise ValueError("The required bounded OBJ/PNG texture output was not configured.")
    return value


def _png(path,side):
    digest,size=_regular(path,64*1024*1024);data=Path(path).read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):raise ValueError("A referenced texture is not a PNG image.")
    offset=8;width=height=None;compressed=bytearray();ended=False
    while offset<len(data):
        if offset+12>len(data):raise ValueError("A texture PNG chunk is truncated.")
        length=struct.unpack(">I",data[offset:offset+4])[0];kind=data[offset+4:offset+8];end=offset+12+length
        if end>len(data) or length>64*1024*1024:raise ValueError("A texture PNG chunk exceeds its byte bound.")
        payload=data[offset+8:offset+8+length]
        if zlib.crc32(kind+payload)&0xffffffff!=struct.unpack(">I",data[end-4:end])[0]:raise ValueError("A texture PNG has an invalid chunk checksum.")
        if offset==8:
            if kind!=b"IHDR" or length!=13:raise ValueError("A texture PNG lacks its image header.")
            width,height,bits,color,compression,filtering,interlace=struct.unpack(">IIBBBBB",payload)
            if not 1<=width<=side or not 1<=height<=side or bits not in {8,16} or color not in {0,2,4,6} or compression or filtering or interlace:
                raise ValueError("A texture PNG exceeds its declared canvas/precision bound.")
            channels={0:1,2:3,4:2,6:4}[color];expected=height*(1+width*channels*(bits//8))
        elif kind==b"IHDR":raise ValueError("A texture PNG contains multiple image headers.")
        if kind==b"IDAT":compressed.extend(payload)
        if kind==b"IEND":
            if length or end!=len(data):raise ValueError("A texture PNG has data after its end marker.")
            ended=True;break
        offset=end
    if not ended or not compressed:raise ValueError("A texture PNG has no complete pixel stream.")
    try:
        decoder=zlib.decompressobj();pixels=decoder.decompress(compressed,expected+1)
    except zlib.error as exc:raise ValueError("A texture PNG has an invalid compressed pixel stream.") from exc
    if len(pixels)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("A texture PNG pixel stream is truncated or exceeds its decoded bound.")
    stride=expected//height
    if any(pixels[row*stride]>4 for row in range(height)):raise ValueError("A texture PNG uses an invalid scanline filter.")
    return {"filename":Path(path).name,"sha256":digest,"bytes":size,"width":width,"height":height}


def validate_surface(directory,texture_side):
    directory=Path(directory);mesh=directory/"texturedMesh.obj";material=directory/"texturedMesh.mtl"
    _regular(mesh,256*1024*1024);_regular(material,2*1024*1024)
    materials={};current=None
    with material.open(encoding="utf-8") as stream:
        for line in iter(lambda:stream.readline(65537),""):
            if len(line)>65536:raise ValueError("A material record exceeds its line bound.")
            fields=line.split()
            if not fields or fields[0].startswith("#"):continue
            if fields[0]=="newmtl":
                if len(fields)!=2 or not _NAME.fullmatch(fields[1]) or fields[1] in materials:raise ValueError("Invalid or duplicate textured material.")
                current=fields[1];materials[current]=None
            elif fields[0]=="map_Kd":
                if current is None or len(fields)!=2 or not _NAME.fullmatch(fields[1]) or not fields[1].lower().endswith(".png") or materials[current] is not None:
                    raise ValueError("Every texture must use one simple owned PNG path.")
                materials[current]=fields[1]
            elif fields[0].lower().startswith(("map_","bump","disp","decal","refl")):
                raise ValueError("Unsupported external material dependency.")
    counts={"vertices":0,"uv_coordinates":0,"normals":0,"faces":0};used=set();active=None;library=False
    with mesh.open(encoding="utf-8") as stream:
        for line in iter(lambda:stream.readline(65537),""):
            if len(line)>65536:raise ValueError("A mesh record exceeds its line bound.")
            fields=line.split()
            if not fields or fields[0].startswith("#"):continue
            kind=fields[0]
            if kind in {"v","vt","vn"}:
                try:values=[float(v) for v in fields[1:]]
                except ValueError as exc:raise ValueError("A mesh coordinate is not numeric.") from exc
                # AliceVision's Assimp OBJ export emits 3-component texture
                # coordinates, with zero Z. Ordinary 2-component UVs are valid.
                if (len(values) not in ({2,3} if kind=="vt" else {3}) or
                        any(not math.isfinite(v) or abs(v)>1e9 for v in values) or
                        kind=="vt" and len(values)==3 and abs(values[2])>1e-8):
                    raise ValueError("A mesh coordinate is invalid.")
                key={"v":"vertices","vt":"uv_coordinates","vn":"normals"}[kind];counts[key]+=1
                if counts[key]>4_000_000:raise ValueError("The mesh exceeds its geometry count bound.")
            elif kind=="mtllib":
                if fields!=["mtllib",material.name] or library:raise ValueError("The mesh references an unowned material library.")
                library=True
            elif kind=="usemtl":
                if len(fields)!=2 or fields[1] not in materials or materials[fields[1]] is None:raise ValueError("A face material lacks an owned diffuse texture.")
                active=fields[1]
            elif kind=="f":
                if not library or active is None or not 3<=len(fields)-1<=16:raise ValueError("The surface lacks textured bounded faces.")
                for field in fields[1:]:
                    pieces=field.split("/")
                    if len(pieces) not in {2,3} or not pieces[0] or not pieces[1]:raise ValueError("Every surface face needs actual UV indices.")
                    for token,key in zip(pieces,("vertices","uv_coordinates","normals")):
                        if token=="" and key=="normals":continue
                        try:index=int(token)
                        except ValueError as exc:raise ValueError("Invalid mesh index.") from exc
                        if index==0 or not -counts[key]<=index<=counts[key]:raise ValueError("A surface face references nonexistent geometry.")
                counts["faces"]+=1;used.add(active)
                if counts["faces"]>4_000_000:raise ValueError("The surface exceeds its face count bound.")
            elif kind not in {"o","g","s"}:raise ValueError("Unsupported executable or free-form OBJ directive.")
    if counts["vertices"]<3 or counts["uv_coordinates"]<3 or counts["faces"]<1:raise ValueError("Meshroom produced no usable textured surface.")
    textures=[_png(directory/name,texture_side) for name in sorted({materials[name] for name in used})]
    expected={mesh.name,material.name,*[t["filename"] for t in textures]}
    if {p.name for p in directory.iterdir()}!=expected:raise ValueError("The dense engine published an unexpected artifact inventory.")
    return {**counts,"materials":len(used),"textures":textures},sorted(expected)


def _registered(cache,inputs,require_all):
    candidates=list((Path(cache)/"StructureFromMotion").glob("*/cameras.sfm"))
    if len(candidates)!=1:raise ValueError("The dense graph did not preserve exactly one solved camera record.")
    path=candidates[0]
    if any(p.is_symlink() for p in (path,path.parent,path.parent.parent)):raise ValueError("The solved camera record escaped its owned cache.")
    _regular(path,2*1024*1024);value=json.loads(path.read_text())
    views=value.get("views",[]);poses=value.get("poses",[]);intrinsics=value.get("intrinsics",[])
    if any(not isinstance(items,list) or len(items)>48 for items in (views,poses,intrinsics)):raise ValueError("Invalid dense camera record.")
    names={record["filename"]:record["asset_id"] for record in inputs};pose_ids=set();intrinsic_ids=set()
    for record in poses:
        if not isinstance(record,dict):raise ValueError("Invalid measured dense camera pose.")
        ident=str(record.get("poseId"));transform=record.get("pose",{}).get("transform",{})
        try:
            rotation=[float(v) for v in transform.get("rotation",[])];center=[float(v) for v in transform.get("center",[])]
        except (ValueError,TypeError) as exc:raise ValueError("Dense camera transform is not numeric.") from exc
        if ident in pose_ids or len(rotation)!=9 or len(center)!=3 or any(not math.isfinite(v) or abs(v)>1e9 for v in rotation+center):
            raise ValueError("Dense camera transform is missing, duplicated or nonfinite.")
        for a in range(3):
            for b in range(3):
                if abs(sum(rotation[a*3+k]*rotation[b*3+k] for k in range(3))-(1 if a==b else 0))>2e-3:
                    raise ValueError("Dense camera rotation is not orthonormal.")
        a,b,c,d,e,f,g,h,i=rotation
        if abs(a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)-1)>2e-3:raise ValueError("Dense camera rotation has an invalid orientation.")
        pose_ids.add(ident)
    for record in intrinsics:
        if not isinstance(record,dict):raise ValueError("Invalid dense lens calibration record.")
        try:width=int(record.get("width",0));height=int(record.get("height",0));focal=float(record.get("focalLength",0))
        except (ValueError,TypeError) as exc:raise ValueError("Dense lens calibration is not numeric.") from exc
        ident=str(record.get("intrinsicId"))
        if ident in intrinsic_ids or not 1<=width<=8192 or not 1<=height<=8192 or not math.isfinite(focal) or focal<=0:
            raise ValueError("Dense lens calibration is missing, duplicated or invalid.")
        intrinsic_ids.add(ident)
    seen=set();registered=[]
    for view in views:
        if not isinstance(view,dict):raise ValueError("Invalid dense camera view.")
        name=Path(view.get("path","")).name
        if name not in names or name in seen:raise ValueError("Solved cameras do not belong to the selected photographs.")
        seen.add(name)
        pose=str(view.get("poseId","-1"))
        if pose not in {"-1","4294967295","18446744073709551615"} and pose in pose_ids:
            if str(view.get("intrinsicId")) not in intrinsic_ids:raise ValueError("A registered dense camera lacks its solved lens calibration.")
            registered.append(names[name])
    if len(registered)<3 or require_all and len(registered)!=len(inputs):
        raise ValueError("Dense reconstruction did not register the required source photographs; no missing poses were fabricated.")
    return path,{"input_images":len(inputs),"registered_images":len(registered),"unregistered_asset_ids":[r["asset_id"] for r in inputs if r["asset_id"] not in registered]}


def _bundle(directory,names,destination,event,deadline):
    entries=[];total=0
    with zipfile.ZipFile(destination,"w") as archive:
        for name in names:
            _check(event,deadline);digest,size=_regular(Path(directory)/name,256*1024*1024);total+=size
            if total>MAX_OUTPUT_BYTES:raise ValueError("The textured surface exceeds its 512-MiB publication budget.")
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=0o100644<<16
            info.compress_type=zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            with (Path(directory)/name).open("rb") as source,archive.open(info,"w") as output:
                for chunk in iter(lambda:source.read(1024*1024),b""):_check(event,deadline);output.write(chunk)
            entries.append({"filename":name,"sha256":digest,"bytes":size})
    return entries


def run(project,project_dir,recipe,output_dir,progress=None,cancel_event=None):
    # Import lazily to keep the optional adapter independent of COLMAP wheels.
    if __package__:from . import reconstruction as core
    else:import reconstruction as core
    recipe=validate_recipe(recipe,project);settings=recipe["settings"];deadline=time.monotonic()+MAX_SECONDS
    _check(cancel_event,deadline);batch,compute=_runtime_paths()
    identities={"batch_sha256":_regular(batch,512*1024*1024)[0],"compute_sha256":_regular(compute,512*1024*1024)[0]}
    if _regular(GRAPH,65536)[0]!=GRAPH_SHA256:raise RuntimeError("The pinned upstream dense graph changed.")
    root=Path(project_dir).absolute();output=Path(output_dir).absolute()
    try:relative=output.relative_to(root)
    except ValueError as exc:raise ValueError("Dense reconstruction output must remain inside its project.") from exc
    if len(relative.parts)!=3 or relative.parts[:2]!=("reconstruction","outputs") or not re.fullmatch(r"[a-f0-9]{32}",relative.name):raise ValueError("Dense reconstruction requires its exact owned output identity.")
    parent=core._owned(root,"reconstruction/outputs",directory=True,create=True)
    if os.path.lexists(output):raise ValueError("Existing dense output cannot be overwritten.")
    inputs=[];originals=[];total=0
    with tempfile.TemporaryDirectory(prefix=".meshroom-",dir=parent) as temporary:
        scratch=Path(temporary);photos=scratch/"images";photos.mkdir();published=scratch/"published";published.mkdir()
        generated=scratch/"result";generated.mkdir();cache=scratch/"cache";cache.mkdir();saved=scratch/"configured.mg"
        for index,ident in enumerate(settings["asset_ids"]):
            _check(cancel_event,deadline);asset=next(a for a in project["assets"] if a["id"]==ident);source=core._owned(root,asset["path"])
            digest,size=core._hash_file(source,core.MAX_IMAGE_BYTES);total+=size
            if total>core.MAX_INPUT_BYTES:raise ValueError("Dense sources exceed the 512-MiB input budget.")
            if (digest,size)!=(asset.get("sha256"),asset.get("size")):raise ValueError("A dense input changed since admission.")
            copied=photos/(f"{index:03d}_"+ident+source.suffix.lower());shutil.copyfile(source,copied)
            if _regular(copied,core.MAX_IMAGE_BYTES)!=(digest,size):raise ValueError("A photograph changed while staging dense reconstruction.")
            inputs.append({"asset_id":ident,"filename":copied.name,"sha256":digest,"bytes":size,"width":asset["width"],"height":asset["height"]})
            originals.append((source,digest,size))
        if progress:progress(.1)
        prepare,compute_argv=_commands(batch,compute,photos,published,cache,saved,settings)
        _execute(prepare,scratch,"initialize",cancel_event,deadline)
        _regular(saved,2*1024*1024);validate_graph(json.loads(saved.read_text()),[str(photos/r["filename"]) for r in inputs],settings)
        if progress:progress(.25)
        _execute(compute_argv,scratch,"compute",cancel_event,deadline)
        _check(cancel_event,deadline);statistics,names=validate_surface(published,settings["texture_side"])
        camera_record,camera_statistics=_registered(cache,inputs,settings["require_all_images"]);statistics.update(camera_statistics)
        if identities!={"batch_sha256":_regular(batch,512*1024*1024)[0],"compute_sha256":_regular(compute,512*1024*1024)[0]}:
            raise ValueError("A configured Meshroom entrypoint changed during execution.")
        if _regular(GRAPH,65536)[0]!=GRAPH_SHA256:raise ValueError("The pinned graph changed during dense reconstruction.")
        for source,digest,size in originals:
            if core._hash_file(source,core.MAX_IMAGE_BYTES)!=(digest,size):raise ValueError("An admitted photograph changed during dense reconstruction.")
        if progress:progress(.85)
        entries=_bundle(published,names,generated/"textured-mesh.zip",cancel_event,deadline)
        shutil.copyfile(saved,generated/"pipeline.mg");shutil.copyfile(camera_record,generated/"cameras.sfm")
        metadata={"type":"cinematicum-alicevision-dense","version":1,"statistics":statistics,"surface_members":entries,
            "graph_sha256":GRAPH_SHA256,"upstream":UPSTREAM,"runtime_entrypoints":identities,
            "coordinates":{"metric_scale":"unresolved","cameras":"AliceVision native extrinsics",
                "native_to_obj":[[1,0,0],[0,-1,0],[0,0,-1]],"note":"Upstream OBJ export flips native Y and Z; camera poses retain native coordinates."},
            "scope":"Actual official Meshroom graph invocation through SfM, depth-map estimation/filtering, meshing/filtering and UV texturing. OBJ axis conversion is explicit; metric scale remains unresolved. No editable scene or calibrated monitor acceptance is implied.",
            "replay":"Rebuild the pinned graph against these admitted source bytes. The saved executed graph retains its original job-local cache and source paths."}
        (generated/"alicevision.json").write_bytes(_json(metadata));artifacts=[];total=0
        for path in sorted(generated.iterdir()):
            digest,size=_regular(path,MAX_OUTPUT_BYTES);total+=size;artifacts.append({"filename":path.name,"sha256":digest,"bytes":size,"size":size})
        if total>MAX_OUTPUT_BYTES:raise ValueError("Dense output artifacts exceed their aggregate 512-MiB budget.")
        receipt={"type":"cinematicum-reconstruction","version":1,"operation":"meshroom_dense","settings":settings,"inputs":inputs,
            "engine":{"name":"Meshroom/AliceVision","graph_release":"2025.1.0","runtime_entrypoints":identities},
            "statistics":statistics,"scope":metadata["scope"],"upstream":UPSTREAM,"graph_sha256":GRAPH_SHA256,
            "proposal_error":"The actual textured mesh is available in textured-mesh.zip. Editable scene import is a separate operation.",
            "artifacts":artifacts,"source_sha256":{Path(__file__).name:_regular(__file__,1024*1024)[0]}}
        (generated/"provenance.json").write_bytes(_json(receipt));digest,size=_regular(generated/"provenance.json",2*1024*1024)
        if total+size>MAX_OUTPUT_BYTES:raise ValueError("Dense provenance exceeds the aggregate publication budget.")
        _check(cancel_event,deadline);os.rename(generated,output)
    if progress:progress(1)
    return {"output_id":relative.name,"settings":settings,"scene":None,"cameras":[],"proposal_error":receipt["proposal_error"],
        "statistics":statistics,"receipt":receipt,"provenance":{**receipt,"output_id":relative.name,"receipt_sha256":digest},
        "artifacts":[*artifacts,{"filename":"provenance.json","sha256":digest,"bytes":size,"size":size}]}

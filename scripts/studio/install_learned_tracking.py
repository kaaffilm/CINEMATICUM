#!/usr/bin/env python3
"""Install exact official SAM2.1 Tiny/TAPIR CPU code, dependencies and weights.

The stable runtime appears only after real checkpoint inference succeeds.
Existing unrelated files are never adopted or overwritten. Each --step runs
one foreground, resumable phase; downloads are cancellable fixed byte chunks.
No model code or weights are downloaded by inference itself. Native CPython
is an explicit external prerequisite. MPS/CUDA acceleration is not certified.
Native package verification retains its 12-second child deadline. An admitted
foreground CI caller can explicitly extend only that inventory deadline through
the Python API; installed RECORD, source and checkpoint checks remain identical.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import unquote, urlsplit
import urllib.request
import uuid

sys.dont_write_bytecode = True

LOCK = Path(__file__).with_name("learned-runtime-lock.json")
WORKER = Path(__file__).with_name("learned_tracking_worker.py")
VERSION = "torch28-v1"
VERSIONS_DIRECTORY = ".cinematicum-learned-runtimes"
RECEIPT = "cinematicum-learned-install.json"
PENDING = ".cinematicum-learned-pending.json"
CHUNK_BYTES = 4*1024*1024
MAX_DOWNLOAD = 256*1024*1024
BASE_PROBE = "import json,platform,sys;print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine()}))"
PIP_BOOTSTRAP = "import runpy,sys;archive=sys.argv.pop(1);sys.path.insert(0,archive);runpy.run_module('pip',run_name='__main__',alter_sys=True)"
PHASES = {"venv","ensurepip","download","install","sources","models","dependencies","verify","probe-sam2","probe-tapir","publish"}


def _target():
    if sys.platform == "darwin" and platform.machine() == "arm64":
        if int(platform.mac_ver()[0].split(".")[0]) < 11:
            raise ValueError("The pinned learned wheels require macOS11 or later")
        return "macos-arm64-py313", "3.13", "darwin", "arm64"
    if sys.platform == "linux" and platform.machine() == "x86_64":
        return "linux-x86_64-py312", "3.12", "linux", "x86_64"
    raise ValueError("Managed learned wheels support native macOS arm64 CPython3.13 and Linux x86_64 CPython3.12")


def default_destination():
    base=Path.home()/("Library/Application Support" if sys.platform=="darwin" else ".local/share")
    return base/"CINEMATICUM/LearnedTracking"/VERSION


def _json(value):
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()


def _read(path, maximum=4*1024*1024):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    with os.fdopen(fd,"rb") as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:
            raise ValueError("Learned installer records must be bounded regular files")
        data=stream.read(maximum+1)
        if len(data)!=info.st_size or len(data)>maximum:
            raise ValueError("Learned installer record changed while reading")
    return json.loads(data),data


def _hash(path, maximum=2*1024*1024*1024, cancel_event=None):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0));digest=hashlib.sha256()
    with os.fdopen(fd,"rb") as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=maximum:
            raise ValueError("Learned runtime files must be bounded regular files")
        while True:
            _cancel(cancel_event);block=stream.read(1024*1024)
            if not block:break
            digest.update(block)
        after=os.fstat(stream.fileno())
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError("Learned runtime bytes changed while verifying")
    return digest.hexdigest(),before.st_size


def load_lock(target=None):
    target=target or _target()[0]
    if target not in {"linux-x86_64-py312","macos-arm64-py313"}:
        raise ValueError("Unsupported learned runtime platform")
    all_locked,raw=_read(LOCK,256*1024)
    if (all_locked.get("schema")!="cinematicum-learned-runtime-lock" or all_locked.get("version")!=1
            or all_locked.get("runtime_version")!=VERSION):
        raise ValueError("Unsupported learned code/model lock")
    host=all_locked.get("platforms",{}).get(target,{})
    expected=("linux-x86_64","3.12") if target.startswith("linux") else ("macos-arm64","3.13")
    if (host.get("platform"),host.get("python"))!=expected:
        raise ValueError("Learned package lock does not match its host Python ABI")
    packages=host.get("packages",[])
    versions={name:record["version"] for name,record in all_locked.get("packages",{}).items()}
    if target.startswith("linux"):
        versions.update(torch="2.8.0+cpu",torchvision="0.23.0+cpu")
    if (len(packages)!=28 or len(versions)!=28 or {p.get("name"):p.get("version") for p in packages}!=versions
            or [p["name"] for p in packages[:3]]!=["pip","setuptools","wheel"]):
        raise ValueError("The learned lock must include every exact dependency and offline build tool")
    sources=all_locked.get("sources",[]);models=all_locked.get("models",{})
    if {s.get("package") for s in sources}!={"sam2","tapnet"} or len(sources)!=2 or set(models)!={"sam2","tapir"}:
        raise ValueError("Both official model sources and checkpoints are required")
    downloads=packages+sources+list(models.values());names=set()
    allowed_hosts={"files.pythonhosted.org","download.pytorch.org","download-r2.pytorch.org","codeload.github.com","huggingface.co"}
    for item in downloads:
        filename=item.get("filename","");url=urlsplit(item.get("url",""))
        if (not re.fullmatch(r"[A-Za-z0-9_.+-]+",filename) or filename in names or url.scheme!="https"
                or url.netloc not in allowed_hosts or url.query or url.fragment or url.username or url.password
                or not re.fullmatch(r"[a-f0-9]{64}",item.get("sha256",""))
                or type(item.get("size")) is not int or not 0<item["size"]<=MAX_DOWNLOAD):
            raise ValueError("A learned download lacks an immutable URL, filename, size or SHA-256 identity")
        names.add(filename)
        if item in packages:
            if (item.get("kind") not in {"wheel","sdist"}
                    or (item["kind"]=="sdist")!=(item["name"] in {"iopath","antlr4-python3-runtime"})
                    or unquote(url.path.rsplit("/",1)[-1])!=filename
                    or (item["kind"]=="wheel" and not filename.endswith(".whl"))
                    or (item["kind"]=="sdist" and not filename.endswith(".tar.gz"))):
                raise ValueError("Unsupported learned package transport")
        elif item in sources:
            if (url.netloc!="codeload.github.com" or not re.fullmatch(r"[a-f0-9]{40}",item.get("commit",""))
                    or not url.path.endswith("/"+item["commit"]) or item.get("license")!="Apache-2.0"):
                raise ValueError("Learned source must name its exact official commit and license")
            seen=set()
            for record in item.get("files",[]):
                name=record.get("path","")
                if (not isinstance(name,str) or not name or name.startswith("/") or any(x in {"",".",".."} for x in name.split("/"))
                        or not (name.startswith(item["package"]+"/") or name in {"README.md","LICENSE"}) or name in seen
                        or not re.fullmatch(r"[a-f0-9]{64}",record.get("sha256",""))
                        or type(record.get("size")) is not int or not 0<record["size"]<=8*1024*1024):
                    raise ValueError("Learned source extraction inventory is invalid")
                seen.add(name)
            if not seen:raise ValueError("Learned source inventory is empty")
        elif url.netloc!="huggingface.co" or "/resolve/" not in url.path or item.get("license")!="Apache-2.0":
            raise ValueError("Learned checkpoints must use their official immutable model revision")
    lock={"schema":all_locked["schema"],"version":1,"runtime_version":VERSION,"target":target,
          "platform":host["platform"],"python":host["python"],"packages":packages,"sources":sources,"models":models,
          "downloads":downloads,"device_policy":all_locked["device_policy"],
          "external_prerequisites":{"python":f"Native CPython{host['python']}; its standard library remains external"}}
    lock["external_runtime"]=dict(lock["external_prerequisites"])
    return lock,hashlib.sha256(raw).hexdigest()


def _cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError("Learned runtime installation cancelled; only its owned verified progress is resumable")


def _env():
    env={k:v for k,v in os.environ.items() if not k.startswith(("PYTHON","PIP_","CINEMATICUM_LEARNED_"))}
    env.update(PIP_CONFIG_FILE=os.devnull,PYTHONDONTWRITEBYTECODE="1",OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",
               VECLIB_MAXIMUM_THREADS="2",TOKENIZERS_PARALLELISM="false")
    return env


def _run(command, timeout=12, cancel_event=None):
    _cancel(cancel_event);process=None
    with tempfile.TemporaryFile() as log:
        try:
            process=subprocess.Popen([str(x) for x in command],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                     env=_env(),start_new_session=True)
            start=time.monotonic()
            while process.poll() is None:
                _cancel(cancel_event)
                if time.monotonic()-start>timeout:raise TimeoutError("Bounded learned installation phase exceeded its deadline; owned progress may be resumed")
                if log.tell()>4*1024*1024:raise RuntimeError("Learned installation produced excessive diagnostics")
                if cancel_event is not None:cancel_event.wait(.04)
                else:time.sleep(.04)
            log.seek(0);text=log.read(4*1024*1024).decode(errors="replace")
            if process.returncode:raise RuntimeError("Learned installation command failed: "+text[-2600:])
            return text
        finally:
            if process is not None and process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=2)
                except (ProcessLookupError,subprocess.TimeoutExpired):
                    if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)


def _require_python(report):
    _,version,system,machine=_target()
    if report.get("python",[])[:2]!=[int(x) for x in version.split(".")] or report.get("platform")!=system or report.get("machine")!=machine:
        raise ValueError(f"Choose native {machine} CPython{version} for the pinned learned wheels")


def choose_python(value=None):
    version=_target()[1]
    candidates=[Path(value).expanduser()] if value else [Path(sys.executable),Path(f"/opt/homebrew/bin/python{version}")]
    located=shutil.which(f"python{version}")
    if not value and located:candidates.append(Path(located))
    for candidate in candidates:
        if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate,os.X_OK):continue
        try:
            _require_python(json.loads(_run([candidate,"-I","-B","-c",BASE_PROBE],3)))
            return candidate
        except (OSError,ValueError,RuntimeError,TimeoutError):
            if value:raise
    raise ValueError(f"Native CPython{version} is required; choose its absolute path with --python")


def _destination(value=None):
    path=Path(value).expanduser() if value is not None else default_destination()
    if not path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("Learned destination must be an absolute named path without parent traversal")
    return path.parent.resolve()/path.name


@contextmanager
def _lock(parent):
    fd=os.open(parent/".cinematicum-learned-install.lock",os.O_CREAT|os.O_RDWR|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError("Learned installation lock is not a regular file")
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise ValueError("Another learned installation phase owns this destination") from exc
        yield
    finally:os.close(fd)


def _save(path,value,create=False):
    data=_json(value)
    if create:
        with path.open("xb") as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        return
    temporary=path.with_name(path.name+".tmp-"+uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()


def _owned_runtime(destination,state,digest,lock):
    name=state.get("runtime_name","")
    if (state.get("schema")!="cinematicum-learned-pending" or state.get("version")!=1
            or state.get("destination")!=str(destination) or state.get("lock_sha256")!=digest
            or not re.fullmatch(VERSION+r"-[a-f0-9]{32}",name) or state.get("phase") not in PHASES
            or type(state.get("index")) is not int or not 0<=state["index"]<=len(lock["downloads"])):
        raise ValueError("An unrelated or malformed pending learned installation will not be adopted")
    runtime=destination.parent/VERSIONS_DIRECTORY/name
    if runtime.is_symlink() or runtime.parent.is_symlink() or not runtime.is_dir():
        raise ValueError("The pending learned runtime is not an owned real directory")
    marker,_=_read(runtime/"owner.json")
    expected={k:state[k] for k in ("schema","version","destination","lock_sha256","runtime_name","base_python")}
    if marker!=expected:raise ValueError("Learned runtime owner marker differs from its pending journal")
    return runtime


def _verify_download(path,record,event=None):
    if path.is_symlink():raise ValueError("Learned downloads cannot be symbolic links")
    if _hash(path,MAX_DOWNLOAD,event)!=(record["sha256"],record["size"]):
        raise ValueError("Learned download differs from its exact pinned SHA-256 or byte count")


class _TrustedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        destination=urlsplit(newurl);original=urlsplit(request.full_url)
        # Hugging Face lists this CDN edge in its public host inventory:
        # https://huggingface.co/.well-known/meta.json (cdnDomains).
        # The pinned official model URL redirects here on the native Mac.
        allowed=(destination.hostname==original.hostname or
                 (original.hostname=="huggingface.co" and destination.hostname in {"cdn-lfs.huggingface.co","cdn-lfs-us-1.hf.co","cas-bridge.xethub.hf.co","us.aws.cdn.hf.co"}) or
                 (original.hostname in {"download.pytorch.org","download-r2.pytorch.org"} and destination.hostname in {"download.pytorch.org","download-r2.pytorch.org"}))
        if destination.scheme!="https" or destination.username or destination.password or not allowed:
            raise ValueError("Learned downloads cannot redirect outside the official pinned artifact CDN")
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def _download_chunk(directory,record,event=None,download_cache=None):
    path=directory/record["filename"];partial=path.with_name(path.name+".part")
    if os.path.lexists(path):_verify_download(path,record,event);return True
    if download_cache is not None:
        source=Path(download_cache)/record["filename"]
        if os.path.lexists(source):
            _verify_download(source,record,event)
            if os.path.lexists(partial):
                if partial.is_symlink() or not partial.is_file():raise ValueError("Invalid owned partial download")
                partial.unlink()
            with source.open("rb") as src,partial.open("xb") as dst:
                while True:
                    _cancel(event);block=src.read(1024*1024)
                    if not block:break
                    dst.write(block)
            _verify_download(partial,record,event);os.replace(partial,path);return True
    offset=0
    if os.path.lexists(partial):
        info=partial.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0<=info.st_size<=record["size"]:
            raise ValueError("Invalid partial learned download ownership or size")
        offset=info.st_size
    if offset==record["size"]:_verify_download(partial,record,event);os.replace(partial,path);return True
    end=min(record["size"],offset+CHUNK_BYTES)-1
    request=urllib.request.Request(record["url"],headers={"Range":f"bytes={offset}-{end}","Accept-Encoding":"identity"})
    opener=urllib.request.build_opener(_TrustedRedirects());_cancel(event);started=time.monotonic()
    with opener.open(request,timeout=4) as response:
        if response.status==206:
            if response.headers.get("Content-Range")!=f"bytes {offset}-{end}/{record['size']}" or response.headers.get("Content-Length")!=str(end-offset+1):
                raise ValueError("Learned artifact server did not honor its exact requested byte range")
            expected=end-offset+1;write_offset=offset
        elif response.status==200:
            # GitHub codeload streams complete immutable archives. A server
            # without range support restarts this owned partial, never appends
            # a full response to old bytes. The same total size/digest gate
            # applies, and elapsed time is still bounded for each foreground step.
            length=response.headers.get("Content-Length")
            if length is not None and length!=str(record["size"]):raise ValueError("Learned full response has a different byte count")
            expected=record["size"];write_offset=0
        else:raise ValueError("Unexpected learned artifact HTTP response")
        fd=os.open(partial,os.O_WRONLY|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"r+b") as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size!=offset:raise ValueError("Owned partial learned download changed")
            stream.seek(write_offset)
            if write_offset==0:stream.truncate(0)
            count=0
            while count<expected:
                _cancel(event)
                if time.monotonic()-started>8:break
                block=response.read(min(256*1024,expected-count))
                if not block:raise ValueError("Learned artifact response ended before its pinned size")
                stream.write(block);count+=len(block)
            stream.flush();os.fsync(stream.fileno())
    if partial.stat().st_size==record["size"]:
        _verify_download(partial,record,event);os.replace(partial,path);return True
    return False


def verify_pip_report(path,package,archive):
    report,_=_read(path);entries=report.get("install",[])
    if len(entries)!=1:raise ValueError("pip must install exactly one locked learned package")
    metadata=entries[0].get("metadata",{});download=entries[0].get("download_info",{})
    normalize=lambda name:re.sub(r"[-_.]+","-",name).lower()
    if (normalize(metadata.get("name",""))!=package["name"] or metadata.get("version")!=package["version"]
            or download.get("url")!=archive.as_uri()
            or download.get("archive_info",{}).get("hashes",{}).get("sha256")!=package["sha256"]):
        raise ValueError("pip installed different learned package bytes or metadata")


def _safe_directory(root,relative):
    current=root
    for part in PurePosixPath(relative).parts:
        current=current/part
        if current.is_symlink() or current.exists() and not current.is_dir():raise ValueError("Owned learned directory contains a link or unexpected file")
        current.mkdir(mode=0o700,exist_ok=True)
    return current


def extract_source(archive,source,runtime,python_version,event=None):
    """Read selected exact regular members, never tar.extract/executable setup."""
    _verify_download(archive,source,event)
    site=_safe_directory(runtime,f"lib/python{python_version}/site-packages")
    licenses=_safe_directory(runtime,"share/cinematicum-learned/licenses/"+source["package"])
    expected={record["path"]:record for record in source["files"]};seen=set()
    with tarfile.open(archive,"r:gz") as bundle:
        members=bundle.getmembers()
        if len(members)>20000 or sum(m.size for m in members if m.isfile())>512*1024*1024:
            raise ValueError("Learned upstream archive exceeds its extraction bound")
        for member in members:
            _cancel(event)
            parts=member.name.split("/")
            if len(parts)<2:continue
            relative="/".join(parts[1:]);record=expected.get(relative)
            if record is None:continue
            if relative in seen or not member.isfile() or member.size!=record["size"]:
                raise ValueError("A selected learned source member is repeated, linked or has changed size")
            seen.add(relative)
            stream=bundle.extractfile(member)
            if stream is None:raise ValueError("A selected learned source member is unreadable")
            with stream:data=stream.read(8*1024*1024+1)
            if (len(data),hashlib.sha256(data).hexdigest())!=(record["size"],record["sha256"]):
                raise ValueError("Learned source differs from its exact pinned upstream file")
            destination=site/relative if relative.startswith(source["package"]+"/") else licenses/relative
            _safe_directory(runtime,destination.parent.relative_to(runtime).as_posix())
            if os.path.lexists(destination):
                if destination.is_symlink() or _hash(destination,8*1024*1024,event)!=(record["sha256"],record["size"]):
                    raise ValueError("Resumable learned source destination contains different bytes")
            else:
                with destination.open("xb") as output:output.write(data)
    if seen!=set(expected):raise ValueError("The exact upstream archive omitted required learned source files")


def _package_check_budget(value):
    if type(value) is not int or not 1 <= value <= 60:
        raise ValueError("An explicit foreground learned package-check budget must be an integer from 1 to 60 seconds")
    return value


def probe_runtime(runtime,lock,digest,event=None,*,package_check_seconds=12):
    package_check_seconds=_package_check_budget(package_check_seconds)
    runtime=Path(runtime);config=runtime/"pyvenv.cfg"
    if config.is_symlink() or not config.is_file() or not re.search(r"(?mi)^include-system-site-packages\s*=\s*false\s*$",config.read_text()):
        raise ValueError("Learned runtime must be a real isolated virtual environment")
    expected={p["name"]:p["version"] for p in lock["packages"]}
    code="import importlib.metadata as m,json,platform,sys;names="+repr(list(expected))+";print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine(),'prefix':sys.prefix,'base_prefix':sys.base_prefix,'versions':{n:m.version(n) for n in names},'locations':{n:str(m.distribution(n).locate_file('')) for n in names}}))"
    report=json.loads(_run([runtime/"bin/python","-I","-B","-c",code],5,event));_require_python(report)
    if report["versions"]!=expected or Path(report["prefix"]).resolve()!=runtime.resolve() or report["prefix"]==report["base_prefix"]:
        raise ValueError("Installed learned package versions or interpreter isolation differ from their lock")
    for location in report["locations"].values():
        try:Path(location).resolve().relative_to(runtime.resolve())
        except ValueError as exc:raise ValueError("A learned package loaded from outside the owned runtime") from exc
    report["package_inventory"]=_verify_package_files(runtime,lock,event,timeout=package_check_seconds)
    capabilities=json.loads(_run([runtime/"bin/python","-I","-B",WORKER,"--capabilities"],12,event))
    if (capabilities.get("available") is not True or capabilities.get("lock_sha256")!=digest
            or capabilities.get("device")!="cpu" or set(capabilities.get("models",{}))!={"sam2","tapir"}):
        raise ValueError("Learned source/checkpoint integrity probe did not accept the exact runtime")
    for key,model in capabilities["models"].items():
        if (model.get("sha256"),model.get("bytes"))!=(lock["models"][key]["sha256"],lock["models"][key]["size"]):
            raise ValueError("Installed learned checkpoint is not the locked official model")
    report.update(capabilities=capabilities,worker_sha256=_hash(WORKER,1024*1024,event)[0],
                  installer_sha256=_hash(Path(__file__),1024*1024,event)[0])
    return report


def _verify_package_files(runtime,lock,event=None,*,timeout=12):
    """Verify installed RECORD hashes and refuse unrecorded importable files."""
    allowed=[record["path"] for source in lock["sources"] for record in source["files"]
             if record["path"].startswith(source["package"]+"/")]
    code=r'''
import base64,hashlib,importlib.metadata as metadata,json,os,pathlib,stat,sys,sysconfig
names,upstream=json.loads(sys.argv[1]);root=pathlib.Path(sys.prefix).resolve();site=pathlib.Path(sysconfig.get_paths()['purelib']).resolve()
known={site/name for name in upstream};fingerprints={};count=0
for name in names:
    distribution=metadata.distribution(name)
    if distribution.files is None:raise ValueError('A learned distribution has no installed file RECORD')
    for item in distribution.files:
        path=pathlib.Path(distribution.locate_file(item));resolved=path.resolve()
        if not resolved.is_relative_to(root) or path.is_symlink():raise ValueError('A learned package file escapes its owned runtime')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size>2*1024*1024*1024:raise ValueError('Invalid learned package file type/size')
            digest=hashlib.sha256()
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            after=os.fstat(stream.fileno())
        if (before.st_size,before.st_ino,before.st_mtime_ns)!=(after.st_size,after.st_ino,after.st_mtime_ns):raise ValueError('Learned package changed while checking its RECORD')
        if item.size is not None and before.st_size!=item.size:raise ValueError('Learned installed package size differs from its RECORD: '+str(item))
        if item.hash is not None:
            if item.hash.mode!='sha256' or base64.urlsafe_b64encode(digest.digest()).rstrip(b'=').decode()!=item.hash.value:raise ValueError('Learned package bytes differ from their installed RECORD: '+str(item))
        elif not str(item).endswith('.dist-info/RECORD'):raise ValueError('An installed learned package file lacks a content hash: '+str(item))
        known.add(resolved);fingerprints[str(resolved.relative_to(root))]=digest.hexdigest();count+=1
actual=set()
for path in site.rglob('*'):
    if path.is_symlink():raise ValueError('Learned site-packages contains an unexpected symbolic link')
    if path.is_file():actual.add(path.resolve())
extra=sorted(str(path.relative_to(site)) for path in actual-known)
missing=sorted(str(path.relative_to(site)) for path in known-actual if path.is_relative_to(site))
if extra or missing:raise ValueError('Learned package inventory differs: unexpected='+repr(extra[:8])+' missing='+repr(missing[:8]))
identity=hashlib.sha256(json.dumps(fingerprints,sort_keys=True,separators=(',',':')).encode()).hexdigest()
print(json.dumps({'distributions':len(names),'recorded_entries':count,'site_files':len(actual),'package_files_sha256':identity,'upstream_source_files':len(upstream)}))
'''
    payload=json.dumps([[package["name"] for package in lock["packages"]],allowed],separators=(",",":"))
    return json.loads(_run([Path(runtime)/"bin/python","-I","-B","-c",code,payload],_package_check_budget(timeout),event))


def _model_probe(runtime,backend,lock,digest,event=None):
    text=_run([runtime/"bin/python","-I","-B",WORKER,"--install-probe",backend],14,event)
    # CPU libraries can print diagnostics before the single JSON result.
    line=next((line for line in reversed(text.splitlines()) if line.startswith('{')),"")
    result=json.loads(line)
    required={"actual_checkpoint_mask","binary_full_depth_alpha"} if backend=="sam2" else {"actual_checkpoint_motion","actual_learned_visibility"}
    if (result.get("available") is not True or result.get("backend")!=backend or result.get("device")!="cpu"
            or result.get("lock_sha256")!=digest or result.get("checkpoint_sha256")!=lock["models"][backend]["sha256"]
            or set(result.get("checks",{}))!=required or not all(v is True for v in result["checks"].values())):
        raise ValueError("The installed model did not pass its actual checkpoint inference readiness gate")
    return result


def _inventory(runtime,event=None):
    result={};total=0
    for current,directories,files in os.walk(runtime,followlinks=False):
        for name in sorted(directories+files):
            _cancel(event);path=Path(current)/name;relative=path.relative_to(runtime).as_posix()
            if relative==RECEIPT:continue
            info=path.lstat()
            if stat.S_ISLNK(info.st_mode):result[relative]={"link":os.readlink(path)}
            elif stat.S_ISREG(info.st_mode):
                digest,size=_hash(path,cancel_event=event);total+=size;result[relative]={"sha256":digest,"bytes":size}
            elif not stat.S_ISDIR(info.st_mode):raise ValueError("Installed learned runtime contains an unsupported filesystem object")
            if total>8*1024*1024*1024 or len(result)>100000:raise ValueError("Installed learned runtime exceeds its inventory bound")
    return result


def _existing(destination,lock,digest,event=None,*,package_check_seconds=12):
    if not os.path.lexists(destination):return None
    if not destination.is_symlink():raise ValueError("An existing unmanaged learned destination will not be replaced or modified")
    relative=Path(os.readlink(destination))
    if relative.is_absolute() or len(relative.parts)!=2 or relative.parts[0]!=VERSIONS_DIRECTORY or not re.fullmatch(VERSION+r"-[a-f0-9]{32}",relative.name):
        raise ValueError("An unrelated learned runtime link will not be adopted")
    runtime=destination.parent/relative
    if runtime.is_symlink() or runtime.parent.is_symlink() or not runtime.is_dir():raise ValueError("The managed learned runtime link is invalid")
    receipt,_=_read(runtime/RECEIPT,32*1024*1024)
    if (receipt.get("schema")!="cinematicum-learned-install" or receipt.get("version")!=1
            or receipt.get("lock_sha256")!=digest or receipt.get("runtime_directory")!=str(runtime)
            or receipt.get("stable_destination")!=str(destination)):
        raise ValueError("Managed learned runtime lacks a matching pinned installation receipt")
    if _inventory(runtime,event)!=receipt.get("inventory"):raise ValueError("Installed learned runtime inventory changed after publication")
    verification=probe_runtime(runtime,lock,digest,event,package_check_seconds=package_check_seconds)
    for backend in ("sam2","tapir"):
        acceptance=receipt.get("model_acceptance",{}).get(backend,{})
        required={"actual_checkpoint_mask","binary_full_depth_alpha"} if backend=="sam2" else {"actual_checkpoint_motion","actual_learned_visibility"}
        if (set(acceptance.get("checks",{}))!=required or not all(value is True for value in acceptance["checks"].values())
                or acceptance.get("lock_sha256")!=digest or acceptance.get("checkpoint_sha256")!=lock["models"][backend]["sha256"]):
            raise ValueError("Learned publication lacks its actual checkpoint acceptance record")
    return {"status":"unchanged","runtime":str(destination),"python":str(destination/"bin/python"),"lock_sha256":digest,
            "verification":verification,"model_acceptance":receipt["model_acceptance"],
            "scope":"Current inventory and checkpoint hashes verified; recorded actual inference belongs to the installed immutable bytes"}


def info(destination=None):
    lock,digest=load_lock();destination=_destination(destination)
    return {"runtime":"learned","platform":lock["platform"],"python":lock["python"],"destination":str(destination),
            "lock_sha256":digest,"download_bytes":sum(p["size"] for p in lock["downloads"]),"packages":lock["packages"],
            "sources":lock["sources"],"models":lock["models"],"downloads":lock["downloads"],
            "external_prerequisites":lock["external_prerequisites"],"destination_exists":os.path.lexists(destination),
            "pending":(destination.parent/PENDING).is_file(),"bounded_step":True,
            "scope":"Official SAM2.1 Tiny and PyTorch TAPIR, CPU-only readiness; MPS/CUDA and arbitrary production footage remain separate acceptance"}


def step(destination=None,python=None,cancel_event=None,download_cache=None,*,package_check_seconds=12):
    package_check_seconds=_package_check_budget(package_check_seconds)
    _cancel(cancel_event);lock,digest=load_lock();destination=_destination(destination)
    if os.path.lexists(destination):return _existing(destination,lock,digest,cancel_event,package_check_seconds=package_check_seconds)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with _lock(destination.parent):
        if os.path.lexists(destination):return _existing(destination,lock,digest,cancel_event,package_check_seconds=package_check_seconds)
        journal=destination.parent/PENDING
        if not os.path.lexists(journal):
            base=choose_python(python);versions=destination.parent/VERSIONS_DIRECTORY
            if versions.is_symlink() or versions.exists() and not versions.is_dir():raise ValueError("An unrelated path occupies the learned versions directory")
            versions.mkdir(mode=0o700,exist_ok=True);name=VERSION+"-"+uuid.uuid4().hex;runtime=versions/name;runtime.mkdir(mode=0o700)
            state={"schema":"cinematicum-learned-pending","version":1,"destination":str(destination),"lock_sha256":digest,
                   "runtime_name":name,"base_python":str(base),"phase":"venv","index":0}
            _save(runtime/"owner.json",{k:state[k] for k in ("schema","version","destination","lock_sha256","runtime_name","base_python")},True)
            _save(journal,state,True)
            return {"status":"in_progress","phase":"venv","lock_sha256":digest,"download_bytes":sum(p["size"] for p in lock["downloads"])}
        state,_=_read(journal);runtime=_owned_runtime(destination,state,digest,lock);phase=state["phase"];base=Path(state["base_python"])
        if python is not None and Path(python).expanduser()!=base:raise ValueError("A resumable learned install cannot change its base interpreter")
        interpreter=runtime/"bin/python";cache=runtime/"download-cache"
        if phase=="venv":
            command=[base,"-I","-B","-m","venv","--without-pip"]
            if _target()[1]=="3.13":command.append("--without-scm-ignore-files")
            _run([*command,runtime],10,cancel_event)
            cache.mkdir(mode=0o700,exist_ok=True);state["phase"]="download"
        elif phase=="ensurepip":
            raise ValueError("This pending setup used an older bootstrap; preserve it and choose a fresh learned runtime destination")
        elif phase=="download":
            if cache.is_symlink() or not cache.is_dir():raise ValueError("The owned learned download cache is invalid")
            if state["index"]>=len(lock["downloads"]):raise ValueError("Invalid learned download cursor")
            if _download_chunk(cache,lock["downloads"][state["index"]],cancel_event,download_cache):
                state["index"]+=1
                if state["index"]==len(lock["downloads"]):state.update(phase="install",index=0)
        elif phase=="install":
            if state["index"]>=len(lock["packages"]):raise ValueError("Invalid learned package cursor")
            package=lock["packages"][state["index"]];archive=cache/package["filename"]
            _verify_download(archive,package,cancel_event)
            requirement=runtime/"package-requirement.txt";requirement.write_text(f"{package['name']} @ {archive.as_uri()} --hash=sha256:{package['sha256']}\n")
            report=runtime/("pip-"+package["name"]+".json")
            format_options=["--only-binary=:all:"] if package["kind"]=="wheel" else ["--no-build-isolation"]
            bootstrap=lock["packages"][0];bootstrap_wheel=cache/bootstrap["filename"]
            _verify_download(bootstrap_wheel,bootstrap,cancel_event)
            _run([interpreter,"-I","-B","-c",PIP_BOOTSTRAP,bootstrap_wheel,"--isolated","--disable-pip-version-check","--no-input","--no-cache-dir",
                  "install","--no-index","--no-deps",*format_options,"--require-hashes","--force-reinstall","--no-compile",
                  "--report",report,"-r",requirement],14,cancel_event)
            verify_pip_report(report,package,archive);state["index"]+=1
            if state["index"]==len(lock["packages"]):state.update(phase="sources",index=0)
        elif phase=="sources":
            if state["index"]>=len(lock["sources"]):raise ValueError("Invalid learned source cursor")
            source=lock["sources"][state["index"]]
            extract_source(cache/source["filename"],source,runtime,lock["python"],cancel_event)
            state["index"]+=1
            if state["index"]==len(lock["sources"]):state.update(phase="models",index=0)
        elif phase=="models":
            models=list(lock["models"].values())
            if state["index"]>=len(models):raise ValueError("Invalid learned checkpoint cursor")
            record=models[state["index"]];source=cache/record["filename"]
            directory=_safe_directory(runtime,"share/cinematicum-learned/models");target=directory/record["filename"]
            if os.path.lexists(target):_verify_download(target,record,cancel_event)
            else:
                _verify_download(source,record,cancel_event);_cancel(cancel_event)
                # Both paths belong to this same new runtime and filesystem.
                # Publish the already-verified bytes without a second 280MB
                # copy or a partly written checkpoint. link() refuses to
                # replace any unexpected destination; the journal can resume
                # safely after either metadata operation.
                os.link(source,target,follow_symlinks=False)
            if os.path.lexists(source):
                _verify_download(source,record,cancel_event)
                source.unlink()
            state["index"]+=1
            if state["index"]==len(models):state.update(phase="dependencies",index=0)
        elif phase=="dependencies":
            _run([interpreter,"-I","-B","-m","pip","--isolated","check"],10,cancel_event);state["phase"]="verify"
        elif phase=="verify":
            _save(runtime/"learned-verification.json",probe_runtime(runtime,lock,digest,cancel_event,package_check_seconds=package_check_seconds))
            inventory=_inventory(runtime,cancel_event)
            for name in ("readiness-inventory.json","acceptance-sam2.json","acceptance-tapir.json"):
                inventory.pop(name,None)
            _save(runtime/"readiness-inventory.json",inventory)
            state["phase"]="probe-sam2"
        elif phase in {"probe-sam2","probe-tapir"}:
            backend=phase.split("-",1)[1]
            _save(runtime/("acceptance-"+backend+".json"),_model_probe(runtime,backend,lock,digest,cancel_event))
            state["phase"]="probe-tapir" if backend=="sam2" else "publish"
        elif phase=="publish":
            before,_=_read(runtime/"learned-verification.json");current=probe_runtime(runtime,lock,digest,cancel_event,package_check_seconds=package_check_seconds)
            if current["versions"]!=before["versions"] or current["worker_sha256"]!=before["worker_sha256"]:
                state.update(phase="verify",index=0)
                _save(journal,state)
                raise ValueError("Learned runtime or acceptance source changed before publication; reverify")
            expected_inventory,_=_read(runtime/"readiness-inventory.json",32*1024*1024)
            current_inventory=_inventory(runtime,cancel_event)
            for name in ("readiness-inventory.json","acceptance-sam2.json","acceptance-tapir.json"):
                current_inventory.pop(name,None)
            if current_inventory!=expected_inventory:
                raise ValueError("Learned runtime bytes changed between integrity verification and actual model acceptance")
            acceptance={key:_read(runtime/("acceptance-"+key+".json"))[0] for key in ("sam2","tapir")}
            for key,record in acceptance.items():
                required={"actual_checkpoint_mask","binary_full_depth_alpha"} if key=="sam2" else {"actual_checkpoint_motion","actual_learned_visibility"}
                if (record.get("lock_sha256")!=digest or record.get("checkpoint_sha256")!=lock["models"][key]["sha256"]
                        or set(record.get("checks",{}))!=required or not all(v is True for v in record["checks"].values())):
                    raise ValueError("Learned publication requires both exact actual checkpoint gates")
            receipt={"schema":"cinematicum-learned-install","version":1,"runtime_directory":str(runtime),"stable_destination":str(destination),
                     "base_python":str(base),"lock_sha256":digest,"downloads":lock["downloads"],"verification":current,
                     "model_acceptance":acceptance,"inventory":_inventory(runtime,cancel_event)}
            _cancel(cancel_event);_save(runtime/RECEIPT,receipt)
            os.symlink(str(Path(VERSIONS_DIRECTORY)/runtime.name),destination,target_is_directory=True);journal.unlink()
            return {"status":"installed","runtime":str(destination),"python":str(destination/"bin/python"),"lock_sha256":digest,
                    "receipt":str(runtime/RECEIPT),"verification":current,"model_acceptance":acceptance}
        _save(journal,state)
        return {"status":"in_progress","phase":state["phase"],"index":state["index"],"lock_sha256":digest}


def install(destination=None,python=None,check_only=False,cancel_event=None,progress=None,download_cache=None,*,package_check_seconds=12):
    package_check_seconds=_package_check_budget(package_check_seconds)
    _cancel(cancel_event);lock,digest=load_lock();destination=_destination(destination)
    if check_only:
        result=_existing(destination,lock,digest,cancel_event,package_check_seconds=package_check_seconds)
        if result is None:raise ValueError("The managed learned runtime is not installed at "+str(destination))
        return result
    started=time.monotonic()
    while True:
        _cancel(cancel_event)
        if time.monotonic()-started>3600:raise TimeoutError("Learned installation exceeded its one-hour foreground budget; verified owned progress may be resumed")
        result=step(destination,python,cancel_event,download_cache,package_check_seconds=package_check_seconds)
        if progress is not None:progress(result)
        if result["status"]!="in_progress":return result


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python",type=Path);parser.add_argument("--destination",type=Path);parser.add_argument("--download-cache",type=Path)
    group=parser.add_mutually_exclusive_group();group.add_argument("--check",action="store_true");group.add_argument("--step",action="store_true");group.add_argument("--info",action="store_true")
    args=parser.parse_args()
    try:
        if args.info:result=info(args.destination)
        elif args.step:result=step(args.destination,args.python,download_cache=args.download_cache)
        else:result=install(args.destination,args.python,args.check,download_cache=args.download_cache)
        print(json.dumps(result,allow_nan=False,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,TimeoutError) as error:
        print(json.dumps({"status":"error","error":str(error)}),file=sys.stderr);return 1


if __name__=="__main__":raise SystemExit(main())

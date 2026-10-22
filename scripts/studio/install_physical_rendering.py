#!/usr/bin/env python3
"""Install the pinned Mitsuba/Dr.Jit CPU runtime without replacing existing data.

The ordinary installer is an owned, cancellable foreground operation. --step
performs one resumable phase or one bounded download chunk and then exits; it
never starts detached work. The stable destination is published only after
wheel hashes, package isolation, CPU LLVM and actual physical pixels/AD pass.
LLVM is an explicit external prerequisite, not installed or upgraded here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import urllib.request
import uuid

sys.dont_write_bytecode = True
import physical_rendering as physical

PINNED_PACKAGES = {"drjit": "1.5.0", "mitsuba": "3.9.1", "numpy": "2.5.4"}
VERSIONS_DIRECTORY = ".cinematicum-physical-runtimes"
RECEIPT = "cinematicum-physical-install.json"
PENDING = ".cinematicum-physical-pending.json"
CHUNK_BYTES = 4 * 1024 * 1024
BASE_PROBE = "import json,platform,sys;print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine()}))"


def _target():
    if sys.platform == "darwin" and platform.machine() == "arm64":
        if int(platform.mac_ver()[0].split(".")[0]) < 14:
            raise ValueError("The pinned physical wheels require macOS 14 or later.")
        return "macos-arm64", "3.13", "py313-v1", "macos-arm64-py313"
    if sys.platform == "linux" and platform.machine() == "x86_64":
        return "linux-x86_64", "3.12", "py312-v1", "linux-x86_64-py312"
    raise ValueError("Managed physical wheels support macOS arm64 CPython 3.13 and Linux x86_64 CPython 3.12.")


def default_destination():
    target, _, version, _ = _target()
    base = Path.home() / ("Library/Application Support" if target == "macos-arm64" else ".local/share")
    return base / "CINEMATICUM/Physical" / version


def _read(path, limit=4*1024*1024):
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Physical installer records must be regular files.")
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ValueError("Physical installer record exceeds its size limit.")
    return json.loads(data), data


def load_lock(target=None):
    target = target or _target()[3]
    if target not in {"macos-arm64-py313", "linux-x86_64-py312"}:
        raise ValueError("Unknown physical wheel platform.")
    lock, raw = _read(Path(__file__).with_name(f"physical-rendering-{target}.lock.json"))
    expected = ("macos-arm64", "3.13") if target.startswith("macos") else ("linux-x86_64", "3.12")
    if (lock.get("schema") != "cinematicum-physical-rendering-wheel-lock" or lock.get("version") != 1
            or (lock.get("platform"), lock.get("python")) != expected):
        raise ValueError("The physical wheel lock has an unsupported identity or platform.")
    packages = lock.get("packages", [])
    if len(packages) != len(PINNED_PACKAGES) or {p.get("name"): p.get("version") for p in packages} != PINNED_PACKAGES:
        raise ValueError("The physical lock must contain every exact direct and transitive wheel.")
    for package in packages:
        url = urlsplit(package.get("url", "")); filename = package.get("filename", "")
        if (not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", filename) or url.scheme != "https" or url.netloc != "files.pythonhosted.org"
                or url.query or url.fragment or not re.fullmatch(r"/packages/[a-f0-9/]+/"+re.escape(filename), url.path)
                or not re.fullmatch(r"[a-f0-9]{64}", package.get("sha256", ""))
                or type(package.get("size")) is not int or not 0 < package["size"] < 150*1024*1024):
            raise ValueError("A physical wheel has an invalid immutable identity, URL or size.")
    return lock, hashlib.sha256(raw).hexdigest()


def _cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError("Physical runtime installation cancelled; verified owned progress can be resumed.")


def _run(command, timeout=12, cancel_event=None, payload=None):
    _cancel(cancel_event)
    env = physical._env()
    for key in list(env):
        if key.startswith("PIP_"): del env[key]
    env.update(PIP_CONFIG_FILE=os.devnull, PYTHONDONTWRITEBYTECODE="1")
    process = None
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as input_file:
        if payload is not None: input_file.write(physical._json(payload)); input_file.seek(0)
        try:
            process = subprocess.Popen([str(x) for x in command], stdin=input_file if payload is not None else subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            started = time.monotonic()
            while process.poll() is None:
                _cancel(cancel_event)
                if time.monotonic()-started > timeout:
                    raise TimeoutError("The bounded physical installer phase timed out; its owned progress remains resumable.")
                if cancel_event is not None: cancel_event.wait(.04)
                else: time.sleep(.04)
            size = output.seek(0, os.SEEK_END); output.seek(max(0, size-2*1024*1024))
            result = output.read().decode("utf-8", errors="replace")
            if process.returncode:
                raise RuntimeError("Physical installation command failed: "+result[-2400:])
            return result
        finally:
            if process is not None: physical._terminate_owned(process)


def _require_python(report):
    target, version, _, _ = _target()
    system, machine = ("darwin", "arm64") if target == "macos-arm64" else ("linux", "x86_64")
    if report.get("python", [])[:2] != [int(x) for x in version.split(".")] or report.get("platform") != system or report.get("machine") != machine:
        raise ValueError(f"Choose a native {machine} CPython {version} interpreter for the locked wheels.")


def choose_python(value=None):
    version = _target()[1]
    candidates = [Path(value).expanduser()] if value else [Path(sys.executable), Path(f"/opt/homebrew/bin/python{version}")]
    located = shutil.which(f"python{version}")
    if not value and located: candidates.append(Path(located))
    for candidate in candidates:
        if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate, os.X_OK): continue
        try:
            _require_python(json.loads(_run([candidate, "-I", "-B", "-c", BASE_PROBE], 3)))
            return candidate
        except (OSError, ValueError, RuntimeError, TimeoutError):
            if value: raise
    raise ValueError(f"A native CPython {version} interpreter is required; use --python with its absolute path.")


def _destination(value):
    path = Path(value).expanduser() if value is not None else default_destination()
    if not path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("Physical destination must be an absolute named directory without parent traversal.")
    return path.parent.resolve()/path.name


@contextmanager
def _lock(parent):
    fd = os.open(parent/".cinematicum-physical-install.lock", os.O_CREAT|os.O_RDWR|getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError("The physical install lock is not a regular file.")
        try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc: raise ValueError("Another physical runtime installation phase is running.") from exc
        yield
    finally: os.close(fd)


def _save_state(path, state, create=False):
    data = physical._json(state)
    if create:
        with path.open("xb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        return
    temporary = path.with_name(path.name+".tmp-"+uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


def _runtime_from_state(destination, state, digest):
    name = state.get("runtime_name", "")
    if (state.get("schema") != "cinematicum-physical-pending" or state.get("version") != 1
            or state.get("destination") != str(destination) or state.get("wheel_lock_sha256") != digest
            or not re.fullmatch(_target()[2]+r"-[a-f0-9]{32}", name)
            or state.get("phase") not in {"venv", "ensurepip", "download", "install", "dependencies", "verify", "publish"}
            or type(state.get("package_index")) is not int or not 0 <= state["package_index"] <= len(PINNED_PACKAGES)):
        raise ValueError("Unrelated or malformed pending physical installation will not be adopted.")
    runtime = destination.parent/VERSIONS_DIRECTORY/name
    if runtime.is_symlink() or runtime.parent.is_symlink() or not runtime.is_dir():
        raise ValueError("The pending physical runtime is not an owned real directory.")
    marker, _ = _read(runtime/"owner.json")
    if marker != {k: state[k] for k in ("schema", "version", "destination", "wheel_lock_sha256", "runtime_name", "base_python")}:
        raise ValueError("The pending physical runtime ownership marker differs from its journal.")
    return runtime


def _verify_wheel(path, package):
    if path.is_symlink(): raise ValueError("Wheel caches cannot contain symbolic links.")
    if physical._hash_file(path, 150*1024*1024) != (package["sha256"], package["size"]):
        raise ValueError("The downloaded wheel differs from its exact pinned SHA-256 or byte count.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Physical wheel downloads do not follow redirects away from their pinned URL.")


def _download_chunk(directory, package, event=None, wheel_cache=None):
    path = directory/package["filename"]; partial = path.with_name(path.name+".part")
    if path.exists() or path.is_symlink(): _verify_wheel(path, package); return True
    if wheel_cache is not None:
        source = Path(wheel_cache)/package["filename"]
        if source.exists() or source.is_symlink():
            _verify_wheel(source, package); _cancel(event)
            with source.open("rb") as src, partial.open("xb") as dst: shutil.copyfileobj(src, dst, 1024*1024)
            _verify_wheel(partial, package); os.replace(partial, path); return True
    offset = 0
    if os.path.lexists(partial):
        info = partial.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= package["size"]:
            raise ValueError("Invalid partial wheel ownership or size.")
        offset = info.st_size
    if offset == package["size"]:
        _verify_wheel(partial, package); os.replace(partial, path); return True
    end = min(package["size"], offset+CHUNK_BYTES)-1
    request = urllib.request.Request(package["url"], headers={"Range":f"bytes={offset}-{end}","Accept-Encoding":"identity"})
    # Public HTTPS downloads honor the owner's network proxy configuration;
    # the immutable URL, certificate validation, byte count and hash still bind
    # the package. Loopback job APIs never travel through this downloader.
    opener = urllib.request.build_opener(_NoRedirect())
    _cancel(event); started = time.monotonic()
    with opener.open(request, timeout=4) as response:
        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{package['size']}":
            raise ValueError("The pinned wheel server did not honor the exact resumable byte range.")
        if response.headers.get("Content-Length") != str(end-offset+1):
            raise ValueError("Pinned wheel response length differs from the requested range.")
        flags = os.O_WRONLY|os.O_CREAT|getattr(os,"O_NOFOLLOW",0)
        fd = os.open(partial, flags, 0o600)
        with os.fdopen(fd,"r+b") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != offset: raise ValueError("Partial wheel changed during download.")
            stream.seek(offset); count = 0
            while count < end-offset+1:
                _cancel(event)
                if time.monotonic()-started > 7: break
                chunk = response.read(min(256*1024,end-offset+1-count))
                if not chunk: raise ValueError("The pinned wheel response ended before the requested byte range.")
                stream.write(chunk); count += len(chunk)
            stream.flush(); os.fsync(stream.fileno())
    if partial.stat().st_size == package["size"]:
        _verify_wheel(partial, package); os.replace(partial, path); return True
    return False


def verify_pip_report(path, package, wheel):
    report, _ = _read(path); entries = report.get("install", [])
    if len(entries) != 1: raise ValueError("pip did not install exactly one locked physical wheel.")
    metadata = entries[0].get("metadata", {}); download = entries[0].get("download_info", {})
    if (metadata.get("name", "").lower() != package["name"] or metadata.get("version") != package["version"]
            or download.get("url") != wheel.as_uri()
            or download.get("archive_info", {}).get("hashes", {}).get("sha256") != package["sha256"]):
        raise ValueError("pip installed different physical package bytes or metadata.")


def probe_runtime(directory, cancel_event=None):
    directory = Path(directory); config = directory/"pyvenv.cfg"
    if config.is_symlink() or not config.is_file() or not re.search(r"(?mi)^include-system-site-packages\s*=\s*false\s*$", config.read_text()):
        raise ValueError("Physical runtime must be a real isolated venv without system packages.")
    code = "import importlib.metadata as m,json,platform,sys;names="+repr(list(PINNED_PACKAGES))+";print(json.dumps({'python':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine(),'prefix':sys.prefix,'base_prefix':sys.base_prefix,'versions':{n:m.version(n) for n in names},'locations':{n:str(m.distribution(n).locate_file('')) for n in names}}))"
    python = directory/"bin/python"
    report = json.loads(_run([python,"-I","-B","-c",code],5,cancel_event)); _require_python(report)
    if report["versions"] != PINNED_PACKAGES or Path(report["prefix"]).resolve() != directory.resolve() or report["prefix"] == report["base_prefix"]:
        raise ValueError("Physical runtime interpreter, isolation or exact package versions differ.")
    for location in report["locations"].values():
        try: Path(location).resolve().relative_to(directory.resolve())
        except ValueError as exc: raise ValueError("A physical package loaded outside its isolated runtime.") from exc
    worker = Path(__file__).with_name("physical_rendering_worker.py")
    acceptance = json.loads(_run([python,"-I","-B",worker],10,cancel_event,{"command":"install_probe"}))
    checks = acceptance.get("checks", {})
    if (not acceptance.get("available") or set(checks) != {"actual_rgb_radiance","actual_reverse_mode_gradient","actual_spectral_integral","actual_polarized_stokes"}
            or not all(v is True for v in checks.values()) or acceptance.get("versions",{}).get("llvm",[0]) < [11,1]):
        raise ValueError("Physical runtime failed actual CPU LLVM/physical acceptance: "+str(acceptance.get("error",checks)))
    report["acceptance"] = acceptance
    llvm = physical._env().get("DRJIT_LIBLLVM_PATH")
    if llvm:
        resolved = Path(llvm).resolve(); digest,size = physical._hash_file(resolved)
        report["llvm_library"] = {"path":str(resolved),"sha256":digest,"bytes":size}
    else:
        report["llvm_library"] = {"path":None,"source":"System loader; actual version and evaluated CPU kernel verified."}
    report["worker_sha256"] = hashlib.sha256(worker.read_bytes()).hexdigest()
    return report


def _inventory(runtime):
    result = {}
    for current, directories, files in os.walk(runtime, followlinks=False):
        for name in directories+files:
            path = Path(current)/name; relative = path.relative_to(runtime).as_posix()
            if relative == RECEIPT: continue
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode): result[relative] = {"link":os.readlink(path)}
            elif stat.S_ISREG(info.st_mode):
                # Empty bootstrap/metadata files are legitimate in an actual venv.
                result[relative] = {"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":info.st_size}
            elif not stat.S_ISDIR(info.st_mode): raise ValueError("Physical runtime contains a nonregular filesystem object.")
    return result


def _existing(destination, digest, cancel_event=None, verify=True):
    if not os.path.lexists(destination): return None
    if not destination.is_symlink(): raise ValueError("An existing unmanaged physical destination will not be replaced or modified.")
    relative = Path(os.readlink(destination))
    if relative.is_absolute() or len(relative.parts)!=2 or relative.parts[0]!=VERSIONS_DIRECTORY or not re.fullmatch(_target()[2]+r"-[a-f0-9]{32}",relative.name):
        raise ValueError("An unrelated physical runtime symlink will not be changed.")
    runtime = destination.parent/relative
    if runtime.is_symlink() or runtime.parent.is_symlink() or not runtime.is_dir(): raise ValueError("The managed physical runtime link is invalid.")
    receipt, _ = _read(runtime/RECEIPT,16*1024*1024)
    if (receipt.get("schema")!="cinematicum-physical-install" or receipt.get("version")!=1
            or receipt.get("wheel_lock_sha256")!=digest or receipt.get("runtime_directory")!=str(runtime)
            or receipt.get("stable_destination")!=str(destination)):
        raise ValueError("The managed physical runtime lacks a matching pinned installation receipt.")
    result = {"status":"unchanged","runtime":str(destination),"python":str(destination/"bin/python"),"wheel_lock_sha256":digest}
    if verify:
        if _inventory(runtime)!=receipt.get("inventory"): raise ValueError("The installed physical runtime inventory changed after publication.")
        result["verification"] = probe_runtime(runtime,cancel_event)
        before=receipt.get("verification",{})
        if (result["verification"]["llvm_library"]!=before.get("llvm_library") or
                result["verification"]["acceptance"]["versions"].get("llvm")!=before.get("acceptance",{}).get("versions",{}).get("llvm")):
            raise ValueError("The external LLVM dependency changed after physical runtime publication.")
    return result


def info(destination=None):
    lock,digest=load_lock();destination=_destination(destination)
    return {"runtime":"physical","platform":lock["platform"],"python":lock["python"],"destination":str(destination),
            "wheel_lock_sha256":digest,"download_bytes":sum(p["size"] for p in lock["packages"]),"packages":lock["packages"],
            "external_prerequisites":lock["external_runtime"],"destination_exists":os.path.lexists(destination),
            "pending":(destination.parent/PENDING).is_file(),"bounded_step":True,
            "scope":"Pinned CPU Mitsuba/Dr.Jit; LLVM is required externally, PBRT executable is a separate optional engine."}


def step(destination=None, python=None, cancel_event=None, wheel_cache=None):
    """Perform one bounded foreground phase; callers may explicitly resume."""
    _cancel(cancel_event);lock,digest=load_lock();destination=_destination(destination)
    if os.path.lexists(destination): return _existing(destination,digest,cancel_event)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with _lock(destination.parent):
        if os.path.lexists(destination): return _existing(destination,digest,cancel_event)
        journal=destination.parent/PENDING
        if not os.path.lexists(journal):
            base=choose_python(python);versions=destination.parent/VERSIONS_DIRECTORY
            if versions.is_symlink() or os.path.lexists(versions) and not versions.is_dir(): raise ValueError("An unrelated path occupies the physical versions directory.")
            versions.mkdir(mode=0o700,exist_ok=True);name=_target()[2]+"-"+uuid.uuid4().hex;runtime=versions/name;runtime.mkdir(mode=0o700)
            state={"schema":"cinematicum-physical-pending","version":1,"destination":str(destination),"wheel_lock_sha256":digest,
                   "runtime_name":name,"base_python":str(base),"phase":"venv","package_index":0}
            _save_state(runtime/"owner.json",{k:state[k] for k in ("schema","version","destination","wheel_lock_sha256","runtime_name","base_python")},True)
            _save_state(journal,state,True)
            return {"status":"in_progress","phase":"venv","wheel_lock_sha256":digest,"download_bytes":sum(p["size"] for p in lock["packages"])}
        state,_=_read(journal);runtime=_runtime_from_state(destination,state,digest);phase=state["phase"]
        base=Path(state["base_python"])
        if python is not None and Path(python).expanduser()!=base: raise ValueError("A resumable install cannot switch its base interpreter.")
        interpreter=runtime/"bin/python";cache=runtime/"wheel-cache"
        if phase=="venv":
            command=[base,"-I","-B","-m","venv","--without-pip"]
            if _target()[1]=="3.13":command.append("--without-scm-ignore-files")
            _run([*command,runtime],10,cancel_event);state["phase"]="ensurepip"
        elif phase=="ensurepip":
            _run([interpreter,"-I","-B","-m","ensurepip","--default-pip"],12,cancel_event);state["phase"]="download"
            cache.mkdir(mode=0o700,exist_ok=True)
        elif phase=="download":
            if cache.is_symlink() or not cache.is_dir():raise ValueError("The owned wheel cache is invalid.")
            package=lock["packages"][state["package_index"]]
            if _download_chunk(cache,package,cancel_event,wheel_cache):
                state["package_index"]+=1
                if state["package_index"]==len(lock["packages"]):state.update(phase="install",package_index=0)
        elif phase=="install":
            package=lock["packages"][state["package_index"]];wheel=cache/package["filename"];_verify_wheel(wheel,package)
            requirements=runtime/"wheel-requirement.txt";requirements.write_text(f"{package['name']} @ {wheel.as_uri()} --hash=sha256:{package['sha256']}\n")
            report=runtime/("pip-"+package["name"]+".json")
            _run([interpreter,"-I","-B","-m","pip","--isolated","--disable-pip-version-check","--no-input","--no-cache-dir",
                  "install","--no-index","--no-deps","--only-binary=:all:","--require-hashes","--force-reinstall","--no-compile","--report",report,"-r",requirements],12,cancel_event)
            verify_pip_report(report,package,wheel);state["package_index"]+=1
            if state["package_index"]==len(lock["packages"]):state["phase"]="dependencies"
        elif phase=="dependencies":
            _run([interpreter,"-I","-B","-m","pip","--isolated","check"],10,cancel_event);state["phase"]="verify"
        elif phase=="verify":
            verification=probe_runtime(runtime,cancel_event);_save_state(runtime/"physical-acceptance.json",verification)
            state["phase"]="publish"
        elif phase=="publish":
            verification,_=_read(runtime/"physical-acceptance.json")
            # Re-evaluate the actual engine after any pause before publication.
            current=probe_runtime(runtime,cancel_event)
            if current["versions"]!=verification["versions"] or current["worker_sha256"]!=verification["worker_sha256"]:
                # Keep the verified installation resumable across a product
                # update. The next explicit step performs verification again;
                # this step publishes nothing under the stale acceptance.
                state["phase"]="verify";_save_state(journal,state)
                raise ValueError("The runtime or verification code changed before publication; resume setup to rerun verification.")
            receipt={"schema":"cinematicum-physical-install","version":1,"runtime_directory":str(runtime),"stable_destination":str(destination),
                     "base_python":str(base),"wheel_lock_sha256":digest,"wheels":lock["packages"],"verification":current,"inventory":_inventory(runtime)}
            _cancel(cancel_event);_save_state(runtime/RECEIPT,receipt)
            os.symlink(str(Path(VERSIONS_DIRECTORY)/runtime.name),destination,target_is_directory=True)
            journal.unlink()
            return {"status":"installed","runtime":str(destination),"python":str(destination/"bin/python"),"wheel_lock_sha256":digest,
                    "receipt":str(runtime/RECEIPT),"verification":current}
        _save_state(journal,state)
        return {"status":"in_progress","phase":state["phase"],"package_index":state["package_index"],"wheel_lock_sha256":digest}


def install(destination=None, python=None, check_only=False, cancel_event=None, progress=None, wheel_cache=None):
    lock,digest=load_lock();destination=_destination(destination)
    if check_only:
        existing=_existing(destination,digest,cancel_event)
        if existing is None:raise ValueError("The managed physical runtime is not installed at "+str(destination))
        return existing
    started=time.monotonic()
    while True:
        _cancel(cancel_event)
        if time.monotonic()-started>1800:raise TimeoutError("Physical installation exceeded its 30-minute foreground job budget; owned progress is resumable.")
        result=step(destination,python,cancel_event,wheel_cache)
        if progress is not None:progress(result)
        if result["status"]!="in_progress":return result


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python",type=Path);parser.add_argument("--destination",type=Path);parser.add_argument("--wheel-cache",type=Path)
    group=parser.add_mutually_exclusive_group();group.add_argument("--check",action="store_true");group.add_argument("--step",action="store_true");group.add_argument("--info",action="store_true")
    args=parser.parse_args()
    try:
        if args.info:result=info(args.destination)
        elif args.step:result=step(args.destination,args.python,wheel_cache=args.wheel_cache)
        else:result=install(args.destination,args.python,args.check,wheel_cache=args.wheel_cache)
        print(json.dumps(result,allow_nan=False,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,TimeoutError) as exc:
        print(json.dumps({"status":"error","error":str(exc)}),file=sys.stderr);return 1


if __name__=="__main__":raise SystemExit(main())

"""An app-owned, pinned headless Wan runtime, with cancellable setup.

This module installs only the shipped public-source/wheel/model lock. It never
opens another application, discovers an existing Comfy server, changes global
Python, or adopts a PID from disk. A live engine is a child of this Store and
dies with its owner. Model execution is still proved by the media adapter.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import runpy
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

LOCK_FILE = Path(__file__).with_name("generation-runtime-lock.json")
LOCK_SHA256 = "bed58809d01a894cf7717ba835aef8f73ff6325601a13b88872c53c66732da09"
SCHEMA = "cinematicum-managed-generation"
RUNTIME_ID = "wan21-v1"
MAX_SOURCE_BYTES = 256 * 1024 * 1024
FREE_SPACE_RESERVE = 6 * 1024 ** 3
DOWNLOAD_MAX_SECONDS = 6 * 60 * 60
SHA = re.compile(r"^[0-9a-f]{64}$")
MODEL_NAMES = {
    "diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors",
    "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae/wan_2.1_vae.safetensors",
}


def default_root():
    return Path.home() / "Library/Application Support/CINEMATICUM/Generation"


def _json(path, limit=2 * 1024 * 1024):
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Generation metadata must be a regular file.")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Generation metadata exceeds its size limit.")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Generation metadata must contain an object.")
    return value, data


def _atomic_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Generation metadata cannot replace a symbolic link.")
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with temporary.open("xb") as output:
            output.write(raw); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(raw).hexdigest()


def _cancel(event):
    if event is not None and event.is_set():
        raise RuntimeError("Managed generation operation cancelled.")


def _digest(path, event=None):
    result = hashlib.sha256()
    with os.fdopen(os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Generation content must be a regular file.")
        for block in iter(lambda: source.read(1024 * 1024), b""):
            _cancel(event); result.update(block)
        after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Generation content changed while being verified.")
    return result.hexdigest()


def _safe_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not (host in {"codeload.github.com", "github.com", "huggingface.co", "files.pythonhosted.org"}
                    or host.endswith(".huggingface.co") or host.endswith(".hf.co"))):
        raise ValueError("Generation downloads require a pinned official HTTPS host.")
    return url


class _OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def load_lock():
    value, data = _json(LOCK_FILE)
    if hashlib.sha256(data).hexdigest() != LOCK_SHA256:
        raise ValueError("The generation installation lock does not match this application build.")
    if (value.get("schema") != "cinematicum-generation-runtime-lock" or value.get("version") != 1
            or value.get("runtime_id") != RUNTIME_ID or value.get("platform") != "macos-arm64"
            or value.get("python") != "3.13" or value.get("minimum_macos") != "14.0"):
        raise ValueError("Unsupported managed generation installation lock.")
    if {entry.get("path") for entry in value.get("models", [])} != MODEL_NAMES or len(value.get("models", [])) != 3:
        raise ValueError("The generation model lock is incomplete.")
    packages = value.get("packages", [])
    if not isinstance(packages, list) or not 1 <= len(packages) <= 100 or len({p.get("name") for p in packages}) != len(packages):
        raise ValueError("The generation wheel lock is incomplete or ambiguous.")
    for entry in [value["source"], *value["models"], *packages]:
        _safe_url(entry.get("url", ""))
        if not SHA.fullmatch(entry.get("sha256", "")) or type(entry.get("size")) is not int or not 0 < entry["size"] <= 12 * 1024 ** 3:
            raise ValueError("The generation lock contains an invalid content identity.")
    for package in packages:
        if (not re.fullmatch(r"[a-z0-9-]+", package["name"]) or not re.fullmatch(r"[A-Za-z0-9_.+!-]+", package["version"])
                or Path(package["filename"]).name != package["filename"] or not package["filename"].endswith(".whl")
                or urllib.parse.urlsplit(package["url"]).hostname != "files.pythonhosted.org"):
            raise ValueError("The generation lock contains an invalid wheel.")
    return value


def default_workflow(options=None):
    """Core-node API graph, based on Comfy's official Wan1.3B recipe.

    Smaller authored dimensions and tiled VAE decoding reduce working memory.
    Euler uses the upstream sampler unchanged. The upstream UniPC scalar
    recurrence is unstable on MPS (Comfy-Org/ComfyUI issues 7027 and 16573);
    a completed prompt can otherwise produce almost-black frames. The saved
    workflow records this sampler choice for reproducibility.
    """
    if options is None: options = {}
    if not isinstance(options, dict) or set(options) - {"width", "height", "length", "steps", "cfg", "fps"}:
        raise ValueError("Managed shots accept width, height, length, steps, cfg and fps.")
    values = {"width": 480, "height": 272, "length": 17, "steps": 20, "cfg": 6.0, "fps": 16.0, **options}
    for name, low, high in (("width", 192, 832), ("height", 128, 480), ("length", 9, 81), ("steps", 4, 50)):
        if type(values[name]) is not int or not low <= values[name] <= high:
            raise ValueError("Managed shot %s must be an integer from %d to %d." % (name, low, high))
    if values["width"] % 16 or values["height"] % 16 or values["length"] % 4 != 1 or values["width"] * values["height"] > 832 * 480:
        raise ValueError("Wan dimensions use multiples of 16, length uses 4n+1 frames, and the canvas is limited to 480p.")
    for name, low, high in (("cfg", 1, 12), ("fps", 1, 60)):
        if isinstance(values[name], bool) or not isinstance(values[name], (int, float)) or not low <= values[name] <= high:
            raise ValueError("Managed shot %s is outside its supported range." % name)
    return {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.1_t2v_1.3B_fp16.safetensors", "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "cpu"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "CINEMATICUM_POSITIVE_PROMPT", "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "CINEMATICUM_NEGATIVE_PROMPT", "clip": ["38", 0]}},
        "40": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": values["width"], "height": values["height"], "length": values["length"], "batch_size": 1}},
        "48": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["37", 0], "shift": 8.0}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["48", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["40", 0],
            "seed": "CINEMATICUM_SEED", "steps": values["steps"], "cfg": values["cfg"], "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["39", 0], "tile_size": 256, "overlap": 64, "temporal_size": 16, "temporal_overlap": 4}},
        "49": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": values["fps"]}},
        "50": {"class_type": "SaveVideo", "inputs": {"video": ["49", 0], "filename_prefix": "CINEMATICUM/take", "format": "mp4",
            "format.codec": "h264", "format.codec.encoding": "re-encode", "format.codec.encoding.crf": 18.0}},
    }


def _clean_env():
    result = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "PIP_", "OCIO", "COMFY"))}
    result.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1", HF_HUB_DISABLE_TELEMETRY="1",
                  HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", DO_NOT_TRACK="1", OMP_NUM_THREADS="4",
                  PYTORCH_ENABLE_MPS_FALLBACK="1", PYTHONDONTWRITEBYTECODE="1")
    return result


def _stop(process):
    if process is None or process.poll() is not None: return
    try: os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError: return
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=3)


def _run(command, event=None, timeout=120, cwd=None):
    _cancel(event)
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(part) for part in command], stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, env=_clean_env(), cwd=cwd, start_new_session=True)
        began = time.monotonic()
        try:
            while process.poll() is None:
                _cancel(event)
                if time.monotonic() - began > timeout:
                    raise RuntimeError("Generation setup command exceeded its time limit.")
                if event is not None: event.wait(.1)
                else: time.sleep(.1)
            output.seek(0, os.SEEK_END); length = output.tell(); output.seek(max(0, length - 2 * 1024 * 1024))
            text = output.read().decode(errors="replace")
            if process.returncode:
                raise RuntimeError("Generation setup command failed: " + text[-4000:])
            _cancel(event)
            return text
        finally: _stop(process)


BASE_PROBE = "import sys,platform,json;print(json.dumps({'version':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine()}))"
RUNTIME_PROBE = r'''
import importlib.metadata as m,json,pathlib,platform,sys,torch,av,safetensors
expected=json.loads(sys.argv[1]);versions={name:m.version(name) for name in expected}
assert versions==expected, 'Installed package versions disagree with the lock'
assert torch.backends.mps.is_available(), 'PyTorch MPS is not available on this host'
sample=torch.tensor([1.,2.,3.],device='mps').square().to('cpu').tolist()
assert sample==[1.,4.,9.], 'MPS arithmetic failed'
assert av.codec.Codec('libx264','w').is_encoder, 'The video encoder is unavailable'
print(json.dumps({'version':list(sys.version_info[:3]),'platform':sys.platform,'machine':platform.machine(),
 'prefix':sys.prefix,'base_prefix':sys.base_prefix,'versions':versions,'torch':torch.__version__,
 'mps_arithmetic':True,'h264_encoder':True,'model_execution_verified':False}))
'''


def choose_python(explicit=None, event=None):
    candidates = [Path(explicit).expanduser()] if explicit else [
        Path.home() / "Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python",
        Path("/opt/homebrew/bin/python3.13"), Path(sys.executable)]
    for candidate in candidates:
        if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate, os.X_OK): continue
        try:
            report = json.loads(_run([candidate, "-I", "-B", "-c", BASE_PROBE], event, 15))
            if report.get("version", [])[:2] == [3, 13] and report.get("platform") == "darwin" and report.get("machine") == "arm64":
                return candidate
        except (RuntimeError, ValueError):
            _cancel(event)
            if explicit: raise
    raise ValueError("Managed generation needs Apple Silicon Python 3.13. The existing CINEMATICUM Imaging runtime or /opt/homebrew/bin/python3.13 can provide it.")


def host_support():
    version = platform.mac_ver()[0]
    supported = sys.platform == "darwin" and platform.machine() == "arm64" and version and int(version.split(".")[0]) >= 14
    return {"supported": bool(supported), "platform": sys.platform, "machine": platform.machine(), "macos": version,
            "reason": "" if supported else "This pinned local generation runtime requires Apple Silicon macOS 14 or newer."}


def _download(entry, destination, event=None, progress=None):
    """Resume a bounded owned partial; publish only after the complete hash."""
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink(): raise ValueError("Generation content cannot be a symbolic link.")
    expected, expected_size = entry["sha256"], entry["size"]
    if destination.exists():
        if not destination.is_file() or destination.stat().st_size != expected_size or _digest(destination, event) != expected:
            raise ValueError("Existing generation content has the wrong identity: " + destination.name)
        if progress: progress(expected_size)
        return
    part = destination.with_name(destination.name + "." + expected[:12] + ".part")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _OfficialRedirect())
    began = time.monotonic()
    for attempt in range(5):
        _cancel(event)
        if part.is_symlink() or part.exists() and not part.is_file(): raise ValueError("An unexpected generation partial occupies the download path.")
        offset = part.stat().st_size if part.exists() else 0
        if offset > expected_size: raise ValueError("Generation partial exceeds its declared size.")
        if offset == expected_size:
            if _digest(part, event) != expected:
                part.unlink(); raise ValueError("Generation download failed its pinned SHA-256 check: " + destination.name)
            _cancel(event); os.replace(part, destination)
            if progress: progress(expected_size)
            return
        headers = {"User-Agent": "CINEMATICUM-managed-generation/1", "Accept-Encoding": "identity"}
        if offset: headers["Range"] = "bytes=%d-" % offset
        try:
            request = urllib.request.Request(_safe_url(entry["url"]), headers=headers)
            with opener.open(request, timeout=8) as response:
                if response.status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not match or int(match[1]) != offset or int(match[3]) != expected_size or int(match[2]) != expected_size - 1:
                        raise ValueError("The model host returned an inconsistent resumed range.")
                elif response.status == 200:
                    offset = 0
                else: raise ValueError("The model host did not provide a complete download range.")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) != expected_size - offset:
                    raise ValueError("The model host's byte count differs from the pinned content.")
                flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | (os.O_APPEND if offset else os.O_TRUNC)
                with os.fdopen(os.open(str(part), flags, 0o600), "wb") as output:
                    if not stat.S_ISREG(os.fstat(output.fileno()).st_mode): raise ValueError("Download partial is not a regular file.")
                    if progress: progress(offset)
                    while True:
                        _cancel(event)
                        if time.monotonic() - began > DOWNLOAD_MAX_SECONDS:
                            raise RuntimeError("Generation download reached its six-hour limit; retry setup to resume its owned partial.")
                        # read1 returns available bytes instead of waiting for an
                        # entire MiB from a trickling HTTP peer before cancelling.
                        block = response.read1(1024 * 1024)
                        if not block: break
                        offset += len(block)
                        if offset > expected_size: raise ValueError("Generation download exceeded its pinned size.")
                        output.write(block)
                        if progress: progress(offset)
                    output.flush(); os.fsync(output.fileno())
                if offset != expected_size:
                    raise OSError("Generation download ended before the expected byte count.")
            if _digest(part, event) != expected:
                part.unlink(); raise ValueError("Generation download failed its pinned SHA-256 check: " + destination.name)
            _cancel(event); os.replace(part, destination)
            return
        except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
            _cancel(event)
            if attempt == 4: raise RuntimeError("Generation download interrupted; its owned partial can resume on retry: " + destination.name) from error
            if event is not None: event.wait(min(4, attempt + 1))
            else: time.sleep(min(4, attempt + 1))


def _remaining_download(entry, destination):
    """Count resumable bytes for disk checks; publication still requires SHA-256."""
    destination = Path(destination)
    if destination.is_symlink() or destination.exists() and not destination.is_file():
        raise ValueError("An unexpected file occupies the generation download path.")
    if destination.exists():
        if destination.stat().st_size != entry["size"]:
            raise ValueError("Existing generation content has the wrong byte count: " + destination.name)
        return 0
    part = destination.with_name(destination.name + "." + entry["sha256"][:12] + ".part")
    if part.is_symlink() or part.exists() and not part.is_file():
        raise ValueError("An unexpected generation partial occupies the download path.")
    size = part.stat().st_size if part.exists() else 0
    if size > entry["size"]: raise ValueError("Generation partial exceeds its declared size.")
    return entry["size"] - size


def extract_source(archive_path, destination, commit, event=None):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink(): raise ValueError("The source destination must be new.")
    prefix = "ComfyUI-" + commit + "/"; manifest = []
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_SOURCE_BYTES or len({e.filename for e in entries}) != len(entries):
            raise ValueError("ComfyUI source archive exceeds its bounded extraction contract.")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (not entry.filename.startswith(prefix) or ".." in path.parts or path.is_absolute() or "\\" in entry.filename
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.file_size > 64 * 1024 * 1024):
                raise ValueError("ComfyUI source archive contains an unsupported path or link.")
        destination.mkdir()
        for entry in entries:
            _cancel(event); relative = entry.filename[len(prefix):]
            if not relative: continue
            target = destination / relative
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(); size = 0
            with archive.open(entry) as source, target.open("xb") as output:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    _cancel(event); size += len(block); digest.update(block); output.write(block)
            if size != entry.file_size: raise ValueError("ComfyUI source archive has an inconsistent entry size.")
            manifest.append({"path": relative, "size": size, "sha256": digest.hexdigest()})
    if not (destination / "main.py").is_file() or not (destination / "LICENSE").is_file():
        raise ValueError("ComfyUI source archive is missing its engine or license.")
    return {"version": 1, "commit": commit, "files": sorted(manifest, key=lambda p: p["path"])}


class ManagedGeneration:
    default_workflow = staticmethod(default_workflow)

    def __init__(self, root=None):
        raw = Path(root).expanduser() if root is not None else default_root()
        if not raw.is_absolute() or ".." in raw.parts: raise ValueError("Generation storage requires an absolute owned path.")
        self.root = raw.parent.resolve() / raw.name
        self.lock = load_lock(); self._guard = threading.RLock(); self._operation_lock = threading.Lock()
        self._process = None; self._log = None; self._runtime_lock = None; self._job_event = None; self._closed = False
        self._url = None; self._ready = False; self._error = ""; self._operation = None; self._detail = ""; self._progress = 0.0
        self._downloaded = 0

    def _owned(self, relative, mkdir=False):
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts: raise ValueError("Invalid generation-owned path.")
        cursor = self.root
        for part in path.parts:
            cursor = cursor / part
            if cursor.is_symlink(): raise ValueError("Generation directories and content must not be symbolic links.")
        if mkdir: cursor.mkdir(parents=True, exist_ok=True)
        return cursor

    def _ensure_root(self):
        if self.root.is_symlink(): raise ValueError("The generation root cannot be a symbolic link.")
        if self.root.exists():
            if not self.root.is_dir(): raise ValueError("The generation root is occupied by an unrelated file.")
            marker = self.root / "owner.json"
            if not marker.exists():
                if any(self.root.iterdir()): raise ValueError("The generation directory has no CINEMATICUM owner receipt; it will not be changed.")
            else:
                owner, _ = _json(marker)
                if owner.get("schema") != SCHEMA or owner.get("version") != 1: raise ValueError("The generation directory belongs to another installation.")
                return
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.root / "owner.json", {"schema": SCHEMA, "version": 1, "identity": uuid.uuid4().hex})

    @contextmanager
    def _file_lock(self, name):
        path = self._owned(name)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError("Generation lock is not a regular file.")
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error: raise RuntimeError("Another CINEMATICUM generation operation owns this installation.") from error
            yield fd
        finally: os.close(fd)

    @contextmanager
    def _operation_context(self, name, event):
        if not self._operation_lock.acquire(blocking=False): raise RuntimeError("A managed generation operation is already running.")
        try:
            with self._guard:
                if self._closed: raise RuntimeError("The managed generation owner is closed.")
                self._operation = name; self._job_event = event; self._error = ""; self._progress = 0.0
            yield
        except Exception as error:
            with self._guard: self._error = str(error)
            raise
        finally:
            with self._guard: self._operation = None; self._job_event = None
            self._operation_lock.release()

    def _update(self, detail, value, progress=None, downloaded=None):
        with self._guard:
            self._detail = detail; self._progress = value
            if downloaded is not None: self._downloaded = downloaded
        if progress: progress(value)

    def _installation(self):
        if self.root.is_symlink() or not self.root.is_dir(): return None
        owner, _ = _json(self.root / "owner.json")
        if owner.get("schema") != SCHEMA or owner.get("version") != 1: raise ValueError("Generation owner receipt is invalid.")
        active_path = self._owned("active.json")
        if not active_path.is_file(): return None
        active, _ = _json(active_path)
        name = active.get("directory", "")
        if not re.fullmatch(r"versions/wan21-v1-[0-9a-f]{32}", name): raise ValueError("Generation active version is invalid.")
        version = self._owned(name)
        receipt, raw = _json(version / "install.json")
        if (hashlib.sha256(raw).hexdigest() != active.get("receipt_sha256") or receipt.get("schema") != SCHEMA
                or receipt.get("version") != 1 or receipt.get("lock_sha256") != LOCK_SHA256):
            raise ValueError("Generation installation receipt does not match this build.")
        if not (version / "python/bin/python").is_file() or not (version / "ComfyUI/main.py").is_file():
            raise ValueError("The managed generation runtime is incomplete.")
        for entry in self.lock["models"]:
            path = self._owned("models/" + entry["path"])
            if not path.is_file() or path.stat().st_size != entry["size"]:
                raise ValueError("Managed generation model is missing or incomplete: " + Path(entry["path"]).name)
        return version, receipt

    def status(self):
        support = host_support(); installed = False; reason = support["reason"]
        try: installed = self._installation() is not None
        except (ValueError, OSError) as error: reason = str(error)
        with self._guard:
            running = self._process is not None and self._process.poll() is None
            detail = self._detail
            if self._process is not None and not running:
                detail = "Local video engine exited. Start it again to generate another take."
                reason = "Owned engine exit status: %s." % self._process.returncode
            if not running: self._ready = False; self._url = None
            value = {"version": 1, "runtime_id": RUNTIME_ID, "supported": support["supported"], "installed": installed,
                "running": running, "ready": running and self._ready, "base_url": self._url if running else None,
                "root": str(self.root), "operation": self._operation, "detail": detail, "progress": self._progress,
                "reason": self._error or reason, "downloaded_bytes": self._downloaded,
                "model_bytes": sum(p["size"] for p in self.lock["models"]),
                "download_bytes": sum(p["size"] for p in [self.lock["source"], *self.lock["packages"], *self.lock["models"]]),
                "model_execution_verified": False, "source_version": self.lock["source"]["version"],
                "models": [{"name": Path(p["path"]).name, "bytes": p["size"], "sha256": p["sha256"]} for p in self.lock["models"]],
                "default_options": {"width": 480, "height": 272, "length": 17, "steps": 20, "cfg": 6, "fps": 16}}
        base = self.root
        while not base.exists() and base != base.parent: base = base.parent
        try: value["free_disk_bytes"] = shutil.disk_usage(base).free
        except OSError: value["free_disk_bytes"] = None
        value["first_install_required_bytes"] = value["download_bytes"] + FREE_SPACE_RESERVE
        return value

    def install(self, progress=None, event=None, python=None):
        with self._operation_context("install", event):
            if not host_support()["supported"]: raise ValueError(host_support()["reason"])
            _cancel(event); executable = choose_python(python, event); self._ensure_root()
            with self._file_lock("install.lock"):
                existing = self._installation()
                if existing:
                    self._verify(existing[0], existing[1], event, progress)
                    self._update("Pinned runtime and models verified.", 1, progress)
                    return self._finished_status()
                artifacts = [(self.lock["source"], self._owned("downloads/ComfyUI-" + self.lock["source"]["commit"] + ".zip"))]
                artifacts += [(p, self._owned("wheels/" + p["filename"])) for p in self.lock["packages"]]
                artifacts += [(p, self._owned("models/" + p["path"])) for p in self.lock["models"]]
                total = sum(p["size"] for p, _ in artifacts)
                remaining = sum(_remaining_download(p, path) for p, path in artifacts)
                if shutil.disk_usage(self.root).free < remaining + FREE_SPACE_RESERVE:
                    raise ValueError("Managed generation needs %.1f GB free for remaining downloads, its isolated environment and working space." % ((remaining + FREE_SPACE_RESERVE) / 1e9))
                completed = 0
                for entry, path in artifacts:
                    _cancel(event)
                    def update(size, prior=completed, filename=path.name):
                        self._update("Downloading and verifying " + filename, .02 + .80 * (prior + size) / total, progress, prior + size)
                    _download(entry, path, event, update); completed += entry["size"]
                self._owned("versions", mkdir=True)
                version = self._owned("versions/wan21-v1-" + uuid.uuid4().hex); version.mkdir()
                published = False
                try:
                    self._update("Extracting verified ComfyUI source.", .83, progress)
                    manifest = extract_source(artifacts[0][1], version / "ComfyUI", self.lock["source"]["commit"], event)
                    tree_sha = _atomic_json(version / "source-files.json", manifest)
                    self._update("Creating isolated Python 3.13 environment.", .85, progress)
                    _run([executable, "-I", "-B", "-m", "venv", "--without-scm-ignore-files", version / "python"], event, 120)
                    requirements = version / "wheel-requirements.txt"
                    requirements.write_text("".join("%s==%s --hash=sha256:%s\n" % (p["name"], p["version"], p["sha256"]) for p in self.lock["packages"]), encoding="utf-8")
                    interpreter = version / "python/bin/python"
                    self._update("Installing the 71 verified wheels into the owned environment.", .87, progress)
                    _run([interpreter, "-I", "-B", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--require-hashes",
                          "--only-binary=:all:", "--disable-pip-version-check", "--no-input", "--no-cache-dir", "--find-links", self._owned("wheels"),
                          "--report", version / "pip-report.json", "--requirement", requirements], event, 1200)
                    pip_report, _ = _json(version / "pip-report.json")
                    expected = {p["name"]: p for p in self.lock["packages"]}; seen = set()
                    for item in pip_report.get("install", []):
                        name = re.sub(r"[-_.]+", "-", item.get("metadata", {}).get("name", "").lower())
                        entry = expected.get(name); info = item.get("download_info", {})
                        if (not entry or name in seen or item.get("metadata", {}).get("version") != entry["version"]
                                or info.get("archive_info", {}).get("hashes", {}).get("sha256") != entry["sha256"]
                                or urllib.parse.unquote(urllib.parse.urlsplit(info.get("url", "")).path) != str(self._owned("wheels/" + entry["filename"]))):
                            raise ValueError("Installed wheel receipt differs from the pinned wheel identities.")
                        seen.add(name)
                    if seen != set(expected): raise ValueError("The isolated runtime did not install every pinned wheel.")
                    _run([interpreter, "-I", "-B", "-m", "pip", "--isolated", "check"], event, 60)
                    self._update("Checking MPS arithmetic and the H.264 encoder.", .95, progress)
                    probe = self._probe(version, event)
                    receipt = {"schema": SCHEMA, "version": 1, "lock_sha256": LOCK_SHA256, "source_manifest_sha256": tree_sha,
                        "source": self.lock["source"], "models": self.lock["models"], "probe": probe, "installed_at": time.time()}
                    receipt_sha = _atomic_json(version / "install.json", receipt)
                    _cancel(event)
                    _atomic_json(self.root / "active.json", {"version": 1, "directory": version.relative_to(self.root).as_posix(), "receipt_sha256": receipt_sha})
                    published = True
                finally:
                    if not published: shutil.rmtree(version)
                self._update("Pinned runtime and models installed. Start the local engine to check its workflow.", 1, progress)
                return self._finished_status()

    def _finished_status(self):
        value = self.status(); value["operation"] = None
        return value

    def _probe(self, version, event):
        versions = {p["name"]: p["version"] for p in self.lock["packages"]}
        text = _run([version / "python/bin/python", "-I", "-B", "-c", RUNTIME_PROBE, json.dumps(versions)], event, 90)
        report = json.loads(text.strip().splitlines()[-1])
        if (report.get("version", [])[:2] != [3, 13] or report.get("platform") != "darwin" or report.get("machine") != "arm64"
                or Path(report.get("prefix", "")).resolve() != (version / "python").resolve() or report.get("prefix") == report.get("base_prefix")
                or report.get("versions") != versions or report.get("mps_arithmetic") is not True or report.get("h264_encoder") is not True):
            raise ValueError("The generation interpreter failed its isolated runtime checks.")
        return report

    def _verify(self, version, receipt, event, progress=None):
        self._update("Verifying installed source and model identities.", .05, progress)
        manifest, raw = _json(version / "source-files.json")
        if hashlib.sha256(raw).hexdigest() != receipt.get("source_manifest_sha256"):
            raise ValueError("ComfyUI source manifest changed after installation.")
        root = version / "ComfyUI"
        if root.is_symlink(): raise ValueError("The installed source directory cannot be a symbolic link.")
        expected = {item["path"]: item for item in manifest.get("files", [])}
        found = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
        if found != set(expected): raise ValueError("ComfyUI source files changed after installation.")
        for relative, item in expected.items():
            _cancel(event); path = root / relative
            if path.stat().st_size != item["size"] or _digest(path, event) != item["sha256"]:
                raise ValueError("ComfyUI source identity changed: " + relative)
        for index, item in enumerate(self.lock["models"]):
            if _digest(self._owned("models/" + item["path"]), event) != item["sha256"]:
                raise ValueError("Generation model identity changed: " + Path(item["path"]).name)
            self._update("Verified " + Path(item["path"]).name, .1 + .4 * (index + 1) / 3, progress)
        self._probe(version, event)

    def start(self, progress=None, event=None):
        with self._operation_context("start", event):
            with self._guard:
                if self._process is not None and self._process.poll() is None and self._ready: return self._finished_status()
                stale = self._process is not None
            if stale: self.stop()
            installation = self._installation()
            if not installation: raise ValueError("Install the managed generation runtime before starting it.")
            version, receipt = installation; self._verify(version, receipt, event, progress)
            runtime_lock = self._file_lock("runtime.lock"); runtime_lock.__enter__()
            self._runtime_lock = runtime_lock
            try:
                for folder in ("state", "state/input", "state/output", "state/temp", "state/user", "logs"):
                    self._owned(folder, mkdir=True)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
                    reservation.bind(("127.0.0.1", 0)); port = reservation.getsockname()[1]
                base = self._owned("state"); source = version / "ComfyUI"
                args = [str(source / "main.py"), "--listen", "127.0.0.1", "--port", str(port), "--base-directory", str(base),
                        "--models-directory", str(self._owned("models")), "--output-directory", str(base / "output"),
                        "--input-directory", str(base / "input"), "--temp-directory", str(base / "temp"), "--user-directory", str(base / "user"),
                        "--disable-auto-launch", "--disable-all-custom-nodes", "--offline", "--disable-assets", "--cache-none",
                        "--lowvram", "--disable-dynamic-vram", "--reserve-vram", "4", "--disable-smart-memory",
                        "--disable-pinned-memory", "--fp16-unet", "--cpu-vae", "--fp32-vae"]
                self._log = self._owned("logs/engine-" + uuid.uuid4().hex + ".log").open("xb")
                command = [str(version / "python/bin/python"), "-I", "-B", str(Path(__file__).resolve()), "--owned-engine", str(os.getpid()), json.dumps(args)]
                self._update("Starting the owned local video engine.", .6, progress)
                self._process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=self._log, stderr=subprocess.STDOUT,
                    cwd=source, env=_clean_env(), start_new_session=True)
                url = "http://127.0.0.1:%d" % port; began = time.monotonic()
                if __package__:
                    from .adapters import _json_request
                    from .generation_readiness import workflow_readiness
                else:
                    from adapters import _json_request
                    from generation_readiness import workflow_readiness
                while time.monotonic() - began < 120:
                    _cancel(event)
                    if self._process.poll() is not None: raise RuntimeError("Owned ComfyUI exited during startup. " + self._log_tail())
                    try: stats = _json_request(url, "/system_stats", timeout=2)
                    except Exception:
                        if event is not None: event.wait(.2)
                        else: time.sleep(.2)
                        continue
                    if stats.get("system", {}).get("argv") != args:
                        raise RuntimeError("The selected loopback endpoint does not belong to this owned runtime.")
                    readiness = workflow_readiness(url, default_workflow())
                    _cancel(event)
                    if self._process.poll() is not None: raise RuntimeError("Owned ComfyUI stopped during workflow preflight.")
                    if not readiness.get("ready"): raise RuntimeError("Owned generation workflow is not ready: " + " ".join(readiness.get("errors", [])[:5]))
                    with self._guard: self._url = url; self._ready = True
                    self._update("Local video engine and Wan workflow are ready. Model execution is checked when a take finishes.", 1, progress)
                    value = self._finished_status(); value["workflow_readiness"] = readiness
                    return value
                raise RuntimeError("Owned ComfyUI did not become ready within two minutes. " + self._log_tail())
            except Exception:
                self.stop(); raise

    def _log_tail(self):
        if self._log is None: return ""
        self._log.flush()
        try:
            with Path(self._log.name).open("rb") as source:
                source.seek(0, os.SEEK_END); source.seek(max(0, source.tell() - 3000)); return source.read().decode(errors="replace")
        except OSError: return ""

    def stop(self):
        with self._guard:
            process = self._process; self._process = None; self._url = None; self._ready = False
            log = self._log; self._log = None; runtime_lock = self._runtime_lock; self._runtime_lock = None
        _stop(process)
        if log is not None: log.close()
        if runtime_lock is not None: runtime_lock.__exit__(None, None, None)
        if process is not None:
            with self._guard: self._detail = "Local video engine stopped."; self._progress = 0.0
        return self.status()

    def shutdown(self):
        with self._guard:
            self._closed = True
            if self._job_event is not None: self._job_event.set()
        self.stop()


def _owned_engine(parent_pid, arguments):
    """Same-process bootstrap; no shell, custom nodes or unrelated PID lookup."""
    if not isinstance(arguments, list) or not arguments or not all(isinstance(a, str) for a in arguments):
        raise ValueError("Invalid owned engine command.")
    source = Path(arguments[0]).resolve(strict=True)
    if source.name != "main.py" or source.parent.name != "ComfyUI" or os.getppid() != parent_pid or os.getpgrp() != os.getpid():
        raise ValueError("Managed engine must be launched by its live app owner into its own process group.")
    def watchdog():
        while os.getppid() == parent_pid: time.sleep(.5)
        os.killpg(os.getpgrp(), signal.SIGTERM)
        time.sleep(3)
        os.killpg(os.getpgrp(), signal.SIGKILL)
    threading.Thread(target=watchdog, daemon=True, name="cinematicum-owner-watch").start()
    sys.path.insert(0, str(source.parent)); sys.argv = arguments
    runpy.run_path(str(source), run_name="__main__")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--owned-engine":
        raise SystemExit("Use CINEMATICUM's managed generation controls.")
    _owned_engine(int(sys.argv[2]), json.loads(sys.argv[3]))

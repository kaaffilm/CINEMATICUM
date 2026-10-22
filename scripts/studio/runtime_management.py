"""Fixed managed optional runtimes; project requests never select executable code.

The authenticated server owns admission, durable job state and cancellation.
This registry accepts only a fixed runtime identity, an operation and the exact
lock digest shown by read-only discovery. Destinations and installers are code.
"""
from __future__ import annotations

import importlib
import inspect
import os
from pathlib import Path
import re
import threading

RUNTIMES = {
    "imaging": {"module":"install_imaging","label":"Color and imaging · OCIO / OpenEXR / RAW",
        "description":"Pinned color transforms, floating-point EXR and RAW decoding with real engine verification."},
    "tracking": {"module":"install_tracking","label":"Planar and optical-flow tracking · OpenCV",
        "description":"Pinned projective/affine measurement and optical flow with real numerical verification."},
    "optiland": {"module":"install_ray_optics","label":"Lens design · Optiland",
        "description":"Sequential optical prescriptions, glass catalogues, real rays, aberrations, PSF and MTF."},
    "physical": {"module":"install_physical_rendering","label":"Physical rendering · Mitsuba",
        "description":"CPU spectral radiance, Stokes polarization and differentiable material fitting. PBRT rendering needs its separate executable."},
    "learned": {"module":"install_learned_tracking","label":"Learned masks and points · SAM 2 / TAPIR",
        "description":"Pinned local checkpoints for image/video masks and learned point tracking; CPU is the default device."},
    "reconstruction": {"module":"install_reconstruction","label":"Photo reconstruction · COLMAP",
        "description":"CPU feature extraction, matching, structure from motion, bundle adjustment and image undistortion."},
}
_JOB_LOCK = threading.Lock()
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _entry(runtime_id):
    if not isinstance(runtime_id,str) or runtime_id not in RUNTIMES:
        raise ValueError("Choose a fixed runtime identity from Runtime setup.")
    return RUNTIMES[runtime_id]


def _installer(runtime_id):
    entry=_entry(runtime_id)
    try: return importlib.import_module(entry["module"])
    except ModuleNotFoundError as exc:
        if exc.name!=entry["module"]:raise
        raise ValueError("The managed installer for this runtime is not included in the current build.") from exc


def _downloads(lock):
    """List actual archives once; source-member manifests are not downloads."""
    downloads=[];seen=set();complete=True
    for category in ("packages","sources","models"):
        collection=lock.get(category,[])
        items=list(collection.values()) if isinstance(collection,dict) else collection
        if not isinstance(items,list):raise ValueError("Runtime lock has an invalid download collection.")
        for item in items:
            if (not isinstance(item,dict) or not isinstance(item.get("url"),str)
                    or not isinstance(item.get("sha256"),str) or not _SHA.fullmatch(item["sha256"])):
                raise ValueError("Runtime lock lacks an immutable download identity.")
            if item["url"] in seen:continue
            seen.add(item["url"])
            size=item.get("size",item.get("bytes"))
            if type(size) is not int or size<=0:complete=False;size=None
            downloads.append({"name":item.get("filename",item.get("name",item.get("id",item["url"].rsplit("/",1)[-1]))),
                              "version":item.get("version",item.get("commit")),"url":item["url"],"sha256":item["sha256"],"bytes":size})
    return downloads,complete and bool(downloads)


def describe(runtime_id):
    entry=_entry(runtime_id)
    result={"id":runtime_id,"label":entry["label"],"description":entry["description"],"installer_available":False,
            "can_install":False,"lock_sha256":None,"download_bytes":None,"download_bytes_complete":False,
            "destination_exists":False,"managed_state":"unavailable","downloads":[],"prerequisites":{},"reason":None}
    try:
        installer=_installer(runtime_id);lock,digest=installer.load_lock()
        if not isinstance(digest,str) or not _SHA.fullmatch(digest):raise ValueError("Installer returned an invalid wheel-lock identity.")
        destination=Path(installer.default_destination())
        if not destination.is_absolute():raise ValueError("The fixed runtime destination is invalid.")
        downloads,complete=_downloads(lock)
        extra=installer.info() if callable(getattr(installer,"info",None)) else {}
        if extra and extra.get("wheel_lock_sha256",extra.get("lock_sha256",digest))!=digest:
            raise ValueError("Runtime discovery and installer use different lock identities.")
        pending=bool(extra.get("pending",False));exists=os.path.lexists(destination)
        result.update(installer_available=True,can_install=complete,lock_sha256=digest,destination=str(destination),
            destination_exists=exists,managed_state="present_unverified" if exists else "pending" if pending else "not_installed",
            download_bytes=sum(d["bytes"] or 0 for d in downloads) if complete else None,download_bytes_complete=complete,
            downloads=downloads,platform=lock.get("platform"),python=lock.get("python"),
            prerequisites=lock.get("external_runtime",{}),bounded_step=callable(getattr(installer,"step",None)),
            reason=None if complete else "The current build does not provide complete pinned download byte counts for this platform.")
    except (OSError,ValueError,RuntimeError,ImportError) as exc:
        result["reason"]=str(exc)
    return result


def inventory():
    return {"version":1,"runtimes":[describe(ident) for ident in RUNTIMES],
            "ownership":"Installs use fixed private application-support destinations and preserve existing unmanaged files.",
            "verification":"A discovered path is unverified until its installer performs real engine checks.",
            "cancellation":"Jobs own their subprocesses. Physical setup retains owned, verified progress for an explicit resume."}


def validate_request(runtime_id,payload):
    _entry(runtime_id)
    if not isinstance(payload,dict) or set(payload)!={"operation","lock_sha256"}:
        raise ValueError("Runtime setup accepts only operation and the displayed lock_sha256; paths, URLs and commands are not accepted.")
    operation=payload["operation"];digest=payload["lock_sha256"]
    if not isinstance(operation,str) or operation not in {"install","check"}:
        raise ValueError("Runtime setup operation must be install or check.")
    if not isinstance(digest,str) or not _SHA.fullmatch(digest):raise ValueError("Runtime setup needs the exact displayed SHA-256 lock identity.")
    current=describe(runtime_id)
    if not current["installer_available"] or operation=="install" and not current["can_install"]:
        raise ValueError(current["reason"] or "This managed runtime is unavailable in the current build.")
    if digest!=current["lock_sha256"]:raise ValueError("The runtime lock changed. Refresh Runtime setup before starting the job.")
    return {"operation":operation,"lock_sha256":digest}


def run(runtime_id,payload,progress=None,cancel_event=None):
    request=validate_request(runtime_id,payload)
    if cancel_event is not None and cancel_event.is_set():raise InterruptedError("Runtime setup cancelled before work began.")
    if not _JOB_LOCK.acquire(blocking=False):raise ValueError("Another managed runtime setup job is running. Wait for it or cancel its owned job.")
    try:
        installer=_installer(runtime_id)
        # Repeat the digest check after obtaining the runtime setup lease.
        if installer.load_lock()[1]!=request["lock_sha256"]:raise ValueError("The pinned runtime lock changed before setup began.")
        if progress:progress(.02)
        kwargs={"check_only":request["operation"]=="check","cancel_event":cancel_event}
        if "progress" in inspect.signature(installer.install).parameters:
            def on_progress(value):
                phase=value.get("phase") if isinstance(value,dict) else None
                stages={"venv":.04,"ensurepip":.09,"download":.15,"install":.55,"dependencies":.72,"verify":.80,"publish":.92}
                if progress:progress(stages.get(phase,.97))
            kwargs["progress"]=on_progress
        result=installer.install(**kwargs)
        # A successful installer return is its publication commit. A late
        # cancel must not hide an already verified, published runtime.
        if not isinstance(result,dict) or result.get("status") not in {"installed","unchanged","verified"}:
            raise ValueError("The fixed installer did not finish a verified runtime installation.")
        if result.get("wheel_lock_sha256",result.get("lock_sha256"))!=request["lock_sha256"]:
            raise ValueError("The completed runtime receipt differs from its queued lock identity.")
        if progress:progress(1)
        return {"runtime_id":runtime_id,"operation":request["operation"],"lock_sha256":request["lock_sha256"],"result":result}
    finally:_JOB_LOCK.release()

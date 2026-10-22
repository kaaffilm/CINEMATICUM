#!/usr/bin/env python3
"""Provision a separate hash-pinned FCPXML schema validator for Linux CI.

No application/shared runtime is modified. The destination must be new. Both
the lxml wheel and Apple's original DTD documentation are verified before use;
the production XML importer remains stdlib-only and never calls this installer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verified(data, record):
    if len(data) != record["bytes"] or digest(data) != record["sha256"]:
        raise ValueError("Validation artifact differs from its exact byte count/SHA-256: " + record["filename"])
    return data


def local_bytes(path, maximum):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("Local validation artifacts require explicit regular paths without links/traversal")
    with path.open("rb") as stream:
        return stream.read(maximum + 1)


def artifact(record, local):
    if local is not None:
        return verified(local_bytes(local, record["bytes"]), record)
    request = urllib.request.Request(record["url"], headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return verified(response.read(record["bytes"] + 1), record)


def run(command, root, name, timeout=60):
    began = time.monotonic()
    result = subprocess.run([str(item) for item in command], capture_output=True,
                            timeout=timeout, text=True)
    (root / (name + ".stdout")).write_text(result.stdout)
    (root / (name + ".stderr")).write_text(result.stderr)
    (root / (name + ".json")).write_text(json.dumps({
        "command": [str(item) for item in command], "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - began, 3)}, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError("Independent validator setup failed at " + name + "; retained its complete output")
    return result.stdout


def provision(root, *, wheel=None, apple_document=None):
    if sys.platform != "linux" or platform.machine() != "x86_64" or sys.version_info[:2] != (3, 12):
        raise ValueError("This exact validation wheel requires native Linux x86_64 CPython 3.12")
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts or root.exists() or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Choose a fresh explicit validator root without symbolic links or parent traversal")
    root.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    report = {"schema": "cinematicum-independent-fcpxml-validator-bootstrap-v1",
              "passed": False, "scope": "Separate test-only XML validation runtime; application/shared runtimes unchanged."}
    try:
        lock_data = (HERE / "fcpxml-schema-validation-lock.json").read_bytes()
        lock = json.loads(lock_data)
        requirements_data = (HERE / "fcpxml-schema-validation-linux.requirements.txt").read_bytes()
        expected_requirement = "lxml==" + lock["lxml"]["version"] + " --hash=sha256:" + lock["lxml"]["sha256"] + "\n"
        if requirements_data.decode() != expected_requirement:
            raise ValueError("Independent validation requirement differs from the exact wheel lock")
        report["lock_sha256"] = digest(lock_data)
        report["bootstrap_sha256"] = digest(Path(__file__).read_bytes())
        downloads = root / "downloads"
        downloads.mkdir()
        wheel_data = artifact(lock["lxml"], wheel)
        wheel_path = downloads / lock["lxml"]["filename"]
        wheel_path.write_bytes(wheel_data)
        document_data = artifact(lock["apple_document"], apple_document)
        (root / lock["apple_document"]["filename"]).write_bytes(document_data)
        blocks = re.findall(r"```swift\n(.*?)\n```", document_data.decode("utf-8"), re.DOTALL)
        if len(blocks) != 1:
            raise ValueError("Exact Apple documentation no longer has one unambiguous DTD block")
        dtd_data = verified((blocks[0] + "\n").encode("utf-8"), lock["dtd"])
        dtd_path = root / lock["dtd"]["filename"]
        dtd_path.write_bytes(dtd_data)
        requirements = root / "requirements.txt"
        requirements.write_bytes(requirements_data)
        run([sys.executable, "-I", "-B", "-m", "venv", root / "runtime"], root, "create-venv")
        config = (root / "runtime/pyvenv.cfg").read_text()
        if "include-system-site-packages = false" not in config:
            raise ValueError("Independent validation requires a real isolated venv")
        python = root / "runtime/bin/python"
        run([python, "-I", "-B", "-m", "pip", "--isolated", "install", "--no-index",
             "--find-links", downloads, "--require-hashes", "--no-deps", "--only-binary=:all:",
             "--no-compile", "--report", root / "pip-report.json", "-r", requirements], root, "install-wheel")
        run([python, "-I", "-B", "-m", "pip", "check"], root, "pip-check", timeout=15)
        code = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
                "from validate_fcpxml_schema import runtime_identity;"
                "lock=json.load(open(sys.argv[2]));print(json.dumps(runtime_identity(lock)[1]))")
        probe = json.loads(run([python, "-I", "-B", "-c", code, HERE,
                               HERE / "fcpxml-schema-validation-lock.json"], root, "runtime-probe", timeout=15))
        if (wheel_path.read_bytes() != wheel_data or dtd_path.read_bytes() != dtd_data
                or (HERE / "fcpxml-schema-validation-lock.json").read_bytes() != lock_data):
            raise ValueError("Validation inputs changed during isolated setup")
        report.update({"passed": True, "python": str(python), "runtime": probe,
                       "wheel": lock["lxml"], "apple_document": lock["apple_document"],
                       "dtd": {**lock["dtd"], "path": str(dtd_path)},
                       "requirements_sha256": digest(requirements_data),
                       "pip_report_sha256": digest((root / "pip-report.json").read_bytes())})
    except Exception as error:
        report["error"] = str(error)
    report["elapsed_seconds"] = round(time.monotonic() - began, 3)
    (root / "bootstrap-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--wheel", type=Path, help="Optional exact local wheel; still hash-checked")
    parser.add_argument("--apple-document", type=Path, help="Optional exact local Apple Markdown; still hash-checked")
    args = parser.parse_args()
    report = provision(args.root, wheel=args.wheel, apple_document=args.apple_document)
    print(json.dumps({"passed": report["passed"], "root": str(args.root),
                      "report": str(args.root / "bootstrap-report.json"), "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only binding of an already verified installation to a final source commit.

The installation verifier is independent evidence tooling, never product code.
This reconciler imports it only after verifying its exact SHA-256. It performs
no installation, launch, project mutation, signing, or permission changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types


VERIFIER_SHA256 = "47de0993575e0646d7c507ebf387ea85db766b41d6c56fe597a7cb0b9047121e"


def verified_module(path):
    """Execute exactly the pinned bytes, without consulting/writing __pycache__."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Verifier path must be explicit and have no parent traversal")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open("/", directory_flags)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(descriptor)
            limit = 2 * 1024 * 1024
            if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
                raise ValueError("Independent verifier is not a bounded regular file")
            data = bytearray()
            while True:
                block = os.read(descriptor, min(1024 * 1024, limit - len(data) + 1))
                if not block:
                    break
                data.extend(block)
                if len(data) > limit:
                    raise ValueError("Independent verifier exceeded its read bound")
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if identity(before) != identity(os.fstat(descriptor)) or identity(before) != identity(current) or len(data) != before.st_size:
                raise ValueError("Independent verifier changed while its bytes were inspected")
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)
    verified = bytes(data)
    if hashlib.sha256(verified).hexdigest() != VERIFIER_SHA256:
        raise ValueError("Independent installation-verifier identity differs")
    audit = types.ModuleType("independent_installation_evidence")
    audit.__file__, audit.__package__ = str(path), ""
    exec(compile(verified, str(path), "exec"), audit.__dict__)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "verifier", "installation-evidence", "canonical-evidence", "output"):
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise ValueError("The installed Mac application must be inspected on macOS")
    if not re.fullmatch(r"[a-f0-9]{40}", args.expected_head):
        raise ValueError("Expected one exact Git commit SHA")
    verifier = args.verifier.absolute()
    audit = verified_module(verifier)
    source, output = audit.absolute(args.source), audit.absolute(args.output)
    install_record, installed = audit.read_json(args.installation_evidence.absolute())
    audit.require(installed.get("schema") == "cinematicum-installation-after-v1"
                  and installed.get("passed") is True
                  and len(installed.get("gates", [])) == 5
                  and all(gate.get("passed") is True for gate in installed["gates"]),
                  "Installation input is not a complete independent passing receipt")
    app = audit.absolute(Path(installed["paths"]["app"]))
    for protected in (source, app, Path(installed["paths"]["projects"]),
                      Path(installed["paths"]["original_checkout"])):
        audit.require(not output.is_relative_to(protected), "Evidence must stay outside protected paths")
    report = {"schema": "cinematicum-final-installed-source-reconciliation-v1", "passed": False,
              "created_at": datetime.now(timezone.utc).isoformat(), "checks": {},
              "scope": "Final published source, every installed runtime file, native-source mapping and unchanged complete bundle; read-only reconciliation, no replacement installation",
              "installation_evidence_sha256": install_record["sha256"],
              "reconciler_sha256": audit.read_file(Path(__file__).absolute())[0]["sha256"],
              "independent_verifier_sha256": VERIFIER_SHA256,
              "signing_or_notarization_certified": False}
    checks = report["checks"]
    try:
        current = audit.source_snapshot(source)
        audit.require(current["git_head"] == args.expected_head, "Source HEAD differs from the final published commit")
        for command in (["diff", "--exit-code", "--quiet", "HEAD", "--"],
                        ["diff", "--cached", "--exit-code", "--quiet", "HEAD", "--"]):
            audit.git_output(source, command)
        checks["exact_final_source_commit_and_clean_tracked_tree"] = True
        audit.require(current["code_identity_sha256"] == installed["source"]["code_identity_sha256"],
                      "A bundled runtime/native/installer file changed; reconciliation cannot replace new native acceptance or installation")
        checks["all_bundled_runtime_native_and_installer_sources_remain_identical"] = True
        runtime = audit.tree(app / "Contents/Resources/studio")
        audit.same_inventory(current["runtime_files"], runtime["files"], "Installed runtime differs from final source")
        checks["every_installed_runtime_byte_and_mode_matches_final_source"] = True
        manifest_record, manifest = audit.read_json(app / "Contents/Resources/source-manifest.json")
        expected_manifest = {"format": "cinematicum-installed-source-v1", "version": current["version"],
                             "runtime_files": {name: record["sha256"] for name, record in current["runtime_files"].items()},
                             "native_sources": {name: record["sha256"] for name, record in current["native_sources"].items()}}
        audit.require(manifest == expected_manifest, "Embedded installed-source mapping differs from final source")
        checks["embedded_source_mapping_matches_final_runtime_and_native_sources"] = True
        bundle = audit.bundle_snapshot(app)
        audit.same_inventory(installed["installed"]["bundle"]["files"], bundle["files"], "Installed bundle changed since installation acceptance")
        checks["complete_installed_bundle_is_unchanged"] = True
        canonical_record, canonical = audit.read_json(args.canonical_evidence.absolute())
        audit.require(canonical.get("schema") == "cinematicum-canonical-installed-launch-v1"
                      and canonical.get("passed") is True, "Canonical launch readiness has not passed")
        audit.same_inventory(canonical["bundle_after"]["files"], bundle["files"], "Installed bundle differs from actual canonical-launch acceptance")
        checks["same_bundle_passed_canonical_launch_engine_and_ordinary_quit"] = True
        backup = installed["receipt_and_backup"]["backup"]
        backup_record, _ = audit.read_file(Path(backup["path"]))
        audit.require(all(backup_record[key] == backup[key] for key in ("sha256", "size", "mode")),
                      "Verified original-bundle archive changed")
        checks["verified_original_bundle_archive_remains_identical"] = True
        owner = audit.owner_snapshot(Path(installed["paths"]["original_checkout"]))
        audit.require(owner == installed["original_checkout"], "Original checkout identities changed since installation acceptance")
        checks["original_checkout_makefile_head_and_status_preserved"] = True
        integrity = subprocess.run([sys.executable, "-I", str(source / "scripts/studio/source_integrity.py"), "--check"],
                                   cwd=source, capture_output=True, text=True, timeout=30)
        audit.require(integrity.returncode == 0, "Final source-integrity verification failed")
        report["source_integrity_result"] = json.loads(integrity.stdout)
        checks["final_source_integrity_manifest_passes"] = True
        report.update(source_commit=current["git_head"], version=current["version"],
                      source_code_identity_sha256=current["code_identity_sha256"],
                      source_integrity_sha256=current["source_integrity"]["sha256"],
                      runtime_file_count=runtime["file_count"], runtime_inventory_sha256=runtime["inventory_sha256"],
                      runtime_files={name: record["sha256"] for name, record in runtime["files"].items()},
                      native_sources={name: record["sha256"] for name, record in current["native_sources"].items()},
                      installed_source_manifest_sha256=manifest_record["sha256"],
                      bundle_file_count=bundle["file_count"], bundle_inventory_sha256=bundle["inventory_sha256"],
                      original_archive_sha256=backup_record["sha256"],
                      canonical_launch_evidence_sha256=canonical_record["sha256"])
    except Exception as error:
        report["error"] = str(error)
    report["passed"] = len(checks) == 9 and all(checks.values()) and "error" not in report
    audit.write_new_json(output, report)
    print(json.dumps({"passed": report["passed"], "checks": checks, "error": report.get("error"),
                      "report": str(output), "source_commit": report.get("source_commit")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)

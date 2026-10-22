#!/usr/bin/env python3
"""Independently validate actual FCPXML 1.10 files against Apple's pinned DTD.

This is an explicit acceptance gate, not a product parser or Final Cut Pro
interoperability claim. A separate lxml runtime is mandatory; missing tools,
changed DTD bytes, invalid input and external entities fail rather than skip.
The shipping FCPXML parser is never imported by this gate.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "fcpxml-schema-validation-lock.json"
MAX_XML_BYTES = 8 * 1024 * 1024


def read_regular(path, maximum):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Use explicit absolute input paths without parent traversal")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Schema inputs must not traverse symbolic links")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError("Expected a bounded regular schema/input file")
        parts = []
        total = 0
        while block := os.read(descriptor, min(1024 * 1024, maximum + 1 - total)):
            parts.append(block)
            total += len(block)
            if total > maximum:
                raise ValueError("Schema input grew beyond its byte limit")
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key) for key in fields):
            raise ValueError("Schema input changed while being read")
        return b"".join(parts)
    finally:
        os.close(descriptor)


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def runtime_identity(lock):
    from lxml import etree
    actual = {"lxml": version("lxml"), "lxml_version": list(etree.LXML_VERSION),
              "libxml2": list(etree.LIBXML_VERSION),
              "libxml2_compiled": list(etree.LIBXML_COMPILED_VERSION),
              "python": sys.version.split()[0],
              "module": str(Path(etree.__file__).resolve()),
              "module_identity": identity(Path(etree.__file__).read_bytes())}
    if (actual["lxml"] != lock["lxml"]["version"]
            or actual["lxml_version"][:3] != [6, 1, 1]
            or actual["libxml2"] != lock["lxml"]["libxml2"]
            or actual["libxml2_compiled"] != lock["lxml"]["libxml2"]):
        raise ValueError("Independent XML validator differs from pinned lxml/libxml2 versions")
    return etree, actual


def parse_document(etree, data):
    # Product exchange is UTF-8. Reject external/internal subsets before an XML
    # parser can consult any local file, network location or entity catalogue.
    data.decode("utf-8")
    if re.search(br"<!ENTITY\b", data, re.IGNORECASE):
        raise ValueError("Entity declarations are forbidden in acceptance inputs")
    declarations = re.findall(br"<!DOCTYPE[^>]*>", data, re.IGNORECASE | re.DOTALL)
    if len(declarations) > 1 or any(
            re.fullmatch(br"<!DOCTYPE\s+fcpxml\s*>", declaration) is None
            for declaration in declarations):
        raise ValueError("Only a bare FCPXML doctype is allowed; no external or internal subset")

    class DenyExternal(etree.Resolver):
        def resolve(self, url, public_id, context):
            raise ValueError("External XML resolution is forbidden")

    parser = etree.XMLParser(resolve_entities=False, load_dtd=False,
                             no_network=True, attribute_defaults=False,
                             dtd_validation=False, recover=False, huge_tree=False)
    parser.resolvers.add(DenyExternal())
    tree = etree.parse(io.BytesIO(data), parser)
    root = tree.getroot()
    if root.tag != "fcpxml" or root.get("version") != "1.10":
        raise ValueError("This exact Apple DTD gate certifies FCPXML 1.10 only")
    if tree.docinfo.system_url or tree.docinfo.public_id:
        raise ValueError("External XML identifiers are forbidden")
    count = 0
    pending = [(root, 0)]
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 100000 or depth > 64:
            raise ValueError("Acceptance XML exceeds its structure bounds")
        pending.extend((child, depth + 1) for child in node)
    return tree


def validate_bytes(etree, dtd, data):
    tree = parse_document(etree, data)
    valid = dtd.validate(tree)
    errors = [{"line": row.line, "column": row.column,
               "domain": row.domain_name, "type": row.type_name,
               "message": row.message} for row in list(dtd.error_log)[:32]]
    return valid, errors


def controls(etree, dtd):
    valid = b'<fcpxml version="1.10"><resources/><library/></fcpxml>'
    if not validate_bytes(etree, dtd, valid)[0]:
        raise ValueError("Pinned Apple DTD rejected the independent minimal positive control")
    invalid = b'<fcpxml version="1.10"><not-an-apple-element/></fcpxml>'
    if validate_bytes(etree, dtd, invalid)[0]:
        raise ValueError("Independent malformed-schema negative control unexpectedly passed")
    payloads = [
        b'<!DOCTYPE fcpxml SYSTEM "https://example.invalid/FCPXML.dtd">' + valid,
        b'<!DOCTYPE fcpxml [<!ENTITY secret SYSTEM "file:///unread-local-file">]>' + valid,
        valid.replace(b'1.10', b'1.9'),
    ]
    for payload in payloads:
        try:
            parse_document(etree, payload)
        except (ValueError, etree.XMLSyntaxError):
            continue
        raise ValueError("Forbidden external/entity/wrong-version input was not rejected")
    return {"actual_dtd_positive_control": True,
            "actual_dtd_negative_control": True,
            "external_dtd_refused": True,
            "external_entity_refused": True,
            "separate_1_9_dtd_claim_refused": True}


def run(dtd_path, hand_fixtures, exports):
    started = time.monotonic()
    report = {"schema": "cinematicum-independent-fcpxml-dtd-validation-v1",
              "passed": False, "dtd_version": "1.10", "files": [],
              "scope": "Actual local Apple 1.10 DTD grammar only; no Final Cut Pro application, source-time or rendered-media claim."}
    try:
        if not hand_fixtures or not exports or len(hand_fixtures) + len(exports) > 32:
            raise ValueError("Require at least one hand-authored fixture and one actual export, at most 32 files")
        paths = [("hand_fixture", Path(p)) for p in hand_fixtures] + [("actual_export", Path(p)) for p in exports]
        if len({str(p) for _, p in paths}) != len(paths):
            raise ValueError("Hand fixture and export inputs must be distinct explicit files")
        lock_data = LOCK_PATH.read_bytes()
        lock = json.loads(lock_data)
        report["lock_identity"] = identity(lock_data)
        dtd_data = read_regular(dtd_path, lock["dtd"]["bytes"])
        report["dtd_identity"] = identity(dtd_data)
        if report["dtd_identity"] != {key: lock["dtd"][key] for key in ("bytes", "sha256")}:
            raise ValueError("Apple DTD bytes differ from the pinned official extraction")
        etree, report["runtime_before"] = runtime_identity(lock)
        # The exact pinned DTD contains only its own local parameter entities.
        # No input-supplied DTD/catalog is loaded or used for validation.
        dtd = etree.DTD(io.BytesIO(dtd_data))
        report["checks"] = controls(etree, dtd)
        for role, path in paths:
            row = {"role": role, "path": str(path), "passed": False}
            try:
                data = read_regular(path, MAX_XML_BYTES)
                row.update(identity(data))
                row["passed"], row["errors"] = validate_bytes(etree, dtd, data)
                row["unchanged"] = identity(read_regular(path, MAX_XML_BYTES)) == identity(data)
                row["passed"] = row["passed"] and row["unchanged"]
            except Exception as error:
                row["error"] = str(error)
            report["files"].append(row)
        _, report["runtime_after"] = runtime_identity(lock)
        report["checks"]["runtime_unchanged"] = report["runtime_before"] == report["runtime_after"]
        report["checks"]["dtd_unchanged"] = read_regular(dtd_path, lock["dtd"]["bytes"]) == dtd_data
        report["checks"]["lock_unchanged"] = LOCK_PATH.read_bytes() == lock_data
        report["passed"] = all(report["checks"].values()) and all(row["passed"] for row in report["files"])
    except Exception as error:
        report["error"] = str(error)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtd", required=True, type=Path)
    parser.add_argument("--hand-fixture", required=True, action="append", type=Path)
    parser.add_argument("--export", required=True, action="append", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    output = args.report
    if not output.is_absolute() or output.exists() or any(p.is_symlink() for p in (output, *output.parents)):
        parser.error("Choose a fresh explicit report path without symbolic links")
    report = run(args.dtd, args.hand_fixture, args.export)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "files": len(report["files"]),
                      "report": str(output), "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

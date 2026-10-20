#!/usr/bin/env python3
"""Acquire official editor bundles and seal the exact bytes in a local lock.

Downloads are resumable so the owner can run bounded acquisition batches. No
program is executed. A resolved URL/version is kept until --refresh explicitly
requests new discovery. Published SHA-256 values are checked when provided;
otherwise the lock records that its hash was computed from HTTPS acquisition,
not independently published. Builds always verify the complete locked bytes.
"""
import argparse
import hashlib
import html.parser
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
IDS = {"shotcut", "kdenlive", "cinelerra", "natron", "friction", "glaxnimate", "blender"}
MAX_SIZE = 4 * 1024 ** 3


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    regular(path, missing=True)
    regular(tmp, missing=True)
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def emit(**value):
    print(json.dumps(value, sort_keys=True), flush=True)


def regular(path, missing=False):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Expected a regular file: " + str(path))
    if not missing and not path.is_file():
        raise ValueError("Required file is absent: " + str(path))


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only HTTPS artifact URLs without embedded credentials are accepted")
    if parsed.port not in (None, 443):
        raise ValueError("Unexpected artifact HTTPS port")
    return url


def request(url, headers=None, timeout=12):
    check_url(url)
    values = {"User-Agent": "CINEMATICUM-native-runtime/1", "Accept-Encoding": "identity"}
    values.update(headers or {})
    return urllib.request.build_opener(HTTPSRedirect()).open(
        urllib.request.Request(url, headers=values), timeout=timeout)


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def listing(url):
    with request(url) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Upstream directory listing exceeds limit")
    parser = Links()
    parser.feed(data.decode("utf-8", errors="replace"))
    return list(dict.fromkeys(urllib.parse.urljoin(url, x) for x in parser.links))


def version_key(value):
    return tuple(int(x) for x in re.findall(r"\d+", value))


def basename(url):
    return urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])


def resolve(entry):
    value = dict(entry)
    resolver = value.get("resolver")
    if not resolver:
        check_url(value["url"])
        return value
    if resolver == "kdenlive":
        directories = [x for x in listing(value["index"])
                       if re.fullmatch(r"\d+\.\d+", basename(x))]
        if not directories:
            raise ValueError("No stable Kdenlive release directory found")
        directory = max(directories, key=version_key)
        links = listing(directory.rstrip("/") + "/linux/")
        candidates = [x for x in links if re.fullmatch(
            r"kdenlive-\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?-x86_64\.AppImage", basename(x))]
    elif resolver == "blender":
        directories = [x for x in listing(value["index"])
                       if re.fullmatch(r"Blender\d+\.\d+", basename(x))]
        if not directories:
            raise ValueError("No Blender release directories found")
        candidates = []
        # A new directory can precede its stable release. Skip empty/beta-only ones.
        for directory in sorted(directories, key=version_key, reverse=True):
            candidates = [x for x in listing(directory.rstrip("/") + "/")
                          if re.fullmatch(r"blender-\d+\.\d+\.\d+-linux-x64\.tar\.xz", basename(x))]
            if candidates:
                break
    elif resolver == "cinelerra":
        candidates = [x for x in listing(value["index"])
                      if re.search(r"(?i)(cingg|cinelerra).*x86_64.*\.AppImage$", basename(x))
                      and not re.search(r"(?i)qt6|alpha|beta|debug", basename(x))]
    else:
        raise ValueError("Unknown upstream resolver")
    if not candidates:
        raise ValueError("No stable Linux amd64 artifact found for " + value["id"])
    value["url"] = max(candidates, key=lambda x: version_key(basename(x)))
    value["version"] = basename(value["url"])
    value["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    check_url(value["url"])
    return value


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(entry, directory, deadline):
    name = entry.get("filename") or basename(entry["url"])
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", name):
        raise ValueError("Unsafe artifact filename")
    target = directory / (entry["id"] + "--" + name)
    partial = target.with_name(target.name + ".part")
    regular(target, missing=True)
    regular(partial, missing=True)
    expected_size = entry.get("size")
    if not target.exists():
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": "bytes=%d-" % existing} if existing else {}
        try:
            response = request(entry["url"], headers,
                               timeout=min(5, max(0.2, deadline - time.monotonic())))
        except urllib.error.HTTPError as exc:
            full_range = exc.headers.get("Content-Range", "")
            if (exc.code == 416 and existing and (expected_size == existing or
                    (expected_size is None and full_range == "bytes */%d" % existing))):
                os.replace(str(partial), str(target))
                response = None
            else:
                raise
        if response is not None:
            with response:
                is_range = response.status == 206
                content_range = response.headers.get("Content-Range", "")
                if is_range and not content_range.startswith("bytes %d-" % existing):
                    raise ValueError("Invalid resume Content-Range")
                if not is_range:
                    existing = 0
                mode = "ab" if existing else "wb"
                total = existing
                with partial.open(mode) as sink:
                    while True:
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        sink.write(block)
                        total += len(block)
                        if total > MAX_SIZE or (expected_size and total > expected_size):
                            raise ValueError("Artifact exceeds size bound")
                        if time.monotonic() > deadline:
                            emit(engine=entry["id"], status="paused", bytes=total)
                            return None
                if expected_size and total != expected_size:
                    raise ValueError("Artifact size differs from upstream metadata")
                os.replace(str(partial), str(target))
    actual = sha256(target)
    with target.open("rb") as artifact:
        magic = artifact.read(20)
    if target.stat().st_size < 100 * 1024:
        raise ValueError("Artifact is unexpectedly small")
    if entry["kind"] == "appimage" and (magic[:4] != b"\x7fELF" or magic[18:20] != b"\x3e\x00"):
        raise ValueError("Artifact is not an amd64 ELF AppImage")
    if entry["kind"] == "tar" and magic[:6] != b"\xfd7zXZ\x00":
        raise ValueError("Artifact is not an XZ archive")
    expected = entry.get("sha256")
    if expected and actual != expected:
        raise ValueError("SHA-256 mismatch for " + entry["id"])
    if expected_size and target.stat().st_size != expected_size:
        raise ValueError("Artifact size mismatch for " + entry["id"])
    value = dict(entry)
    value.update({"archive": target.name, "sha256": actual, "size": target.stat().st_size,
                  "verification": entry.get("verification") or
                    ("published-sha256" if expected else "https-acquisition-sha256")})
    emit(engine=entry["id"], status="verified", bytes=value["size"], sha256=actual,
         verification=value["verification"])
    return value


def verify(directory, expected_ids=None):
    regular(directory / "engines.lock.json")
    lock = json.loads((directory / "engines.lock.json").read_text())
    if lock.get("schema") != 1 or lock.get("platform") != "linux/amd64":
        raise ValueError("Unsupported native bundle lock schema or platform")
    entries = lock.get("engines", [])
    seen = set()
    for item in entries:
        key = item.get("id")
        if key not in IDS or key in seen:
            raise ValueError("Unknown or duplicate engine in lock")
        seen.add(key)
        name = item.get("archive", "")
        if Path(name).name != name or not name:
            raise ValueError("Invalid archive path in lock")
        path = directory / name
        regular(path)
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
            raise ValueError("Missing SHA-256 in lock")
        if path.stat().st_size != item.get("size") or sha256(path) != item["sha256"]:
            raise ValueError("Locked artifact verification failed: " + key)
    if expected_ids and seen != set(expected_ids):
        raise ValueError("Incomplete locked editor set: " + ", ".join(sorted(seen)))
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "bundles")
    parser.add_argument("--only", choices=sorted(IDS), action="append")
    parser.add_argument("--max-seconds", type=float, default=900)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--resolve-only", action="store_true")
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    selected = set(args.only or IDS)
    if args.verify:
        lock = verify(directory, selected)
        emit(status="verified", engines=[x["id"] for x in lock["engines"]])
        return 0
    deadline = time.monotonic() + max(1, args.max_seconds)
    source = json.loads((HERE / "engines.json").read_text())
    resolved_path = directory / "resolved.json"
    regular(resolved_path, missing=True)
    resolved = {} if args.refresh or not resolved_path.exists() else json.loads(resolved_path.read_text())
    locked_path = directory / "engines.lock.json"
    regular(locked_path, missing=True)
    old = json.loads(locked_path.read_text()) if locked_path.exists() else {"schema": 1, "platform": "linux/amd64", "engines": []}
    locked = {x["id"]: x for x in old["engines"]}
    for entry in source["engines"]:
        key = entry["id"]
        if key not in selected:
            continue
        spec_sha = hashlib.sha256(json.dumps(entry, sort_keys=True).encode("utf-8")).hexdigest()
        if key not in resolved or resolved[key].get("spec_sha256") != spec_sha:
            resolved[key] = resolve(entry)
            resolved[key]["spec_sha256"] = spec_sha
            atomic_json(resolved_path, resolved)
        if args.resolve_only:
            emit(engine=key, status="resolved", url=resolved[key]["url"], version=resolved[key].get("version"))
            continue
        if time.monotonic() > deadline:
            return 75
        acquisition = dict(resolved[key])
        old_item = locked.get(key)
        if old_item and old_item.get("url") == acquisition.get("url"):
            # Never silently bless a changed cached artifact on a resumed run.
            acquisition.update({"sha256": old_item["sha256"], "size": old_item["size"],
                                "verification": old_item["verification"]})
        item = acquire(acquisition, directory, deadline)
        if item is None:
            return 75
        locked[key] = item
        atomic_json(locked_path, {"schema": 1, "platform": "linux/amd64",
                                 "engines": [locked[k] for k in sorted(locked)]})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, urllib.error.URLError) as exc:
        emit(status="error", error=str(exc))
        raise SystemExit(1)

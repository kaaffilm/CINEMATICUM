#!/usr/bin/env python3
"""Fetch one immutable, authenticated camera RAW fixture for actual tests only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

SOURCE = "https://raw.githubusercontent.com/letmaik/rawpy/a39c2e7a44911889c3360891012f862f904ba551/test/RAW_KODAK_DC50_%C3%A9.KDC"
ATTRIBUTION = "https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/README.txt"
SIZE = 92675
SHA256 = "37e290dbd0053f00e508d02a6b3a2a990432dad1eb74c40a52ca899f0f225ecc"


def verified_bytes(data):
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("The camera RAW fixture does not match its pinned original byte length and SHA-256")
    return data


def fetch_fixture(output):
    output = Path(output).absolute()
    if output.is_symlink() or output.exists() and not output.is_file():
        raise ValueError("The fixture destination must be a regular file, not a link or directory")
    reused = output.exists()
    if reused:
        with output.open("rb") as existing:
            verified_bytes(existing.read(SIZE + 1))
    else:
        with urllib.request.urlopen(SOURCE, timeout=30) as response:
            data = verified_bytes(response.read(SIZE + 1))
        output.parent.mkdir(parents=True, exist_ok=True)
        # Never replace an existing caller-owned file, including a racing write.
        created = False
        try:
            with output.open("xb") as target:
                created = True
                target.write(data)
        except BaseException:
            if created:
                output.unlink(missing_ok=True)
            raise
    return {"path": str(output), "bytes": SIZE, "sha256": SHA256, "source": SOURCE,
            "attribution": ATTRIBUTION, "license": "CC BY-NC-SA 4.0", "reused_verified_file": reused,
            "scope": "Authentic Kodak DC50 camera sample from rawsamples.ch, temporary test input only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(fetch_fixture(args.output), indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print("RAW fixture fetch failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

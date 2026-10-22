#!/usr/bin/env python3
"""Bounded actual Mac acceptance of reverse, retimed and nested live PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from test_audio_routing_macos import run_sequence

HERE = Path(__file__).resolve().parent
PATHS = ("web/pcm-playback.js", "web/audio-routing.js", "web/sequence-playback.js",
         "web/editing.js", "web/app.js", "test_audio_routing_macos.py",
         "macos/AudioRoutingSmoke.js", "macos/AudioProbeWorklet.js")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", choices=("reverse", "reverse_retimed", "nested_reverse"), required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Actual macOS WKWebView is required; no native certificate is issued elsewhere.")
    if not args.binary.is_absolute() or args.binary.is_symlink() or digest(args.binary) != args.binary_sha256:
        parser.error("The explicit native helper does not match its expected physical hash.")
    if not args.output.is_absolute() or args.output.exists():
        parser.error("A new absolute output directory is required.")
    before = {name: digest(HERE / name) for name in PATHS}
    began = time.monotonic()
    report = run_sequence(args.binary, args.output, args.scenario, repetitions=2)
    after = {name: digest(HERE / name) for name in PATHS}
    gates = report.setdefault("checks", {})
    gates["runtime_and_acceptance_source_unchanged"] = before == after
    gates["pinned_native_helper_unchanged"] = digest(args.binary) == args.binary_sha256
    gates["within_18_second_foreground_bound"] = time.monotonic() - began < 18
    report["passed"] = report["passed"] and all(gates.values())
    summary = {key: report.get(key) for key in ("passed", "scenario", "checks", "elapsed_seconds", "error")}
    summary.update(native_certified=True, source_sha256=before,
                   helper_sha256=args.binary_sha256, fixture="SYNTHETIC ENGINE TEST; NOT PRODUCTION MEDIA")
    (args.output / "source-bound-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

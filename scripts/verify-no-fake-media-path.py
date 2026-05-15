#!/usr/bin/env python3
from pathlib import Path
import json
import os
import sys

ROOT = Path.cwd()

def fail(reason):
    print("NO_FAKE_MEDIA_PATH=false")
    print(f"REASON={reason}")
    raise SystemExit(1)

# Production bin must not contain the ffmpeg test-pattern generator.
bad_bin = ROOT / "bin/cinematicum-proof-video-generator"
if bad_bin.exists():
    text = bad_bin.read_text(errors="ignore")
    if "testsrc2" in text or "proof-video-generator" in str(bad_bin):
        fail("test_pattern_generator_present_in_production_bin")

# Runtime generator must not be the proof/test-pattern generator.
cmd = os.environ.get("CINEMATICUM_VIDEO_GENERATOR", "")
if "cinematicum-proof-video-generator" in cmd or "testsrc2" in cmd:
    fail("runtime_generator_is_test_pattern_or_proof_generator")

record_path = ROOT / "records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json"
if record_path.exists():
    record = json.loads(record_path.read_text())

    failed_hashes = {
        "1822a3c1f7a1718fbd38e6ecabb74f9f0abff6369553051569cdd4178971f5a8",
    }

    if record.get("media_sha256") in failed_hashes:
        fail("record_points_to_known_failed_flat_or_card_sequence")

    if record.get("substance_gate_status") == "FAILED_FLAT_OR_CARD_SEQUENCE":
        fail("record_still_declares_failed_flat_or_card_sequence")

    if record.get("issued") is True and record.get("media_substance_passed") is not True:
        fail("issued_true_without_media_substance_pass")

timeline_path = ROOT / "CASES/CASE_001_THE_LAST_RENDER/FILM/TIMELINE_MANIFEST.json"
if timeline_path.exists() and record_path.exists():
    record = json.loads(record_path.read_text())
    issuance_claimed = any(record.get(k) is True for k in (
        "media_present",
        "motion_picture_media_issuance_ready",
        "motion_picture_media_issued",
        "motion_picture_issued",
        "admissible_motion_picture_issued",
        "issued",
    ))
    if issuance_claimed:
        timeline = json.loads(timeline_path.read_text())
        hashes = [item.get("sha256") for item in timeline.get("items", []) if item.get("sha256")]
        duplicates = sorted({h for h in hashes if hashes.count(h) > 1})
        if duplicates:
            fail("timeline_reuses_take_hashes_not_unique_cinematic_takes")

print("NO_FAKE_MEDIA_PATH=true")

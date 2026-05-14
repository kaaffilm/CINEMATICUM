# CINEMATICUM — Public Status

Current active state:

    CASE_001_THE_LAST_RENDER = ISSUED_ADMISSIBLE_MOTION_PICTURE

Protocol film issuance state:

    CINEMATICUM is issued as a public replayable hash-bound protocol-film perimeter.
    protocol_issued=true
    unqualified_issued=false
    issuance_type=PROTOCOL_FILM
    protocol_perimeter_issued=true
    protocol_film_issued=true
    issued_object=PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER

Motion-picture media issuance state:

    motion_picture_media_issued=true
    motion_picture_issued=true
    admissible_motion_picture_issued=true
    final_master_media_issued=true
    motion_picture_media_issuance_ready=true
    media_present=true
    generation_present=false
    engine_present=false
    model_present=false
    model_weight_payload_present=false
    private_access_required=true
    network_required_after_clone=false

Release candidate state:

    release_candidate_ready=true
    motion_picture_issued=true
    admissible_motion_picture_media_issued=true
    media_present=true

Terminal motion-picture media issuance state:

    admissible_motion_picture_media_issued=true
    admissibility_verdict_present=true
    terminal_closure_present=true
    media_payload_present=false
    raw_media_stored_in_git=false

Verification required:

    bash scripts/verify-all.sh
    bash scripts/verify-outsider-clone-replay.sh
    python3 -m cinematicum_studio.cli issuance-check CASE_001_THE_LAST_RENDER

Registry freshness required:

    bash scripts/verify-object-registry-fresh.sh
    python3 scripts/regenerate-object-registry.py --check

## Boundary

This status page reports protocol-film perimeter issuance and hash-bound external motion-picture media issuance.

Protocol-film perimeter issuance does not by itself issue motion-picture media.

Motion-picture media issuance is admitted only by the hash-bound external media admission record.

Bare `issued` is reserved for motion-picture media issuance and is now true only at the hash-bound media boundary.

CINEMATICUM does not claim raw media, footage, audio, stills, model weights, render workflows, or media payloads inside git.

The current truth owners remain:

- `CINEMATICUM_PROTOCOL_ISSUANCE.json`
- `CINEMATICUM_CURRENT_STATE_INDEX.json`
- `CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json`
- `MOTION_PICTURE_ISSUANCE_ACT.json`
- `records/motion_picture_issuance/MOTION_PICTURE_MEDIA_ADMISSION_RECORD.json`

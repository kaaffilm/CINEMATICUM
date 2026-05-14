# CINEMATICUM — Public Status

Current active state:

    CASE_001_THE_LAST_RENDER = RELEASE_CANDIDATE_READY

Protocol film issuance state:

    CINEMATICUM is issued as a public replayable hash-bound protocol-film perimeter.
    protocol_issued=true
    unqualified_issued=false
    issuance_type=PROTOCOL_FILM
    protocol_perimeter_issued=true
    protocol_film_issued=true
    issued_object=PUBLIC_REPLAYABLE_HASH_BOUND_PROTOCOL_PERIMETER

Motion-picture media issuance state:

    motion_picture_media_issued=false
    motion_picture_issued=false
    admissible_motion_picture_issued=false
    final_master_media_issued=false
    motion_picture_media_issuance_ready=false
    media_present=false
    generation_present=false
    engine_present=false
    model_present=false
    model_weight_payload_present=false
    private_access_required=false
    network_required_after_clone=false

Release candidate state:

    release_candidate_ready=true
    motion_picture_issued=false
    admissible_motion_picture_media_issued=false
    media_present=false

Terminal motion-picture media issuance state:

    admissible_motion_picture_media_issued=false
    admissibility_verdict_present=false
    terminal_closure_present=false
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

This status page reports protocol-film perimeter issuance and release-candidate readiness.

Protocol-film perimeter issuance does not issue motion-picture media.

Motion-picture media issuance remains false until an explicit hash-bound external media admission boundary exists.

Bare `issued` is reserved for motion-picture media issuance and remains false at release-candidate readiness.

CINEMATICUM does not claim raw media, footage, audio, stills, model weights, render workflows, or media payloads inside git.

The current truth owners remain:

- `CINEMATICUM_PROTOCOL_ISSUANCE.json`
- `CINEMATICUM_CURRENT_STATE_INDEX.json`
- `CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json`
- `CINEMATICUM_REPOSITORY_STATUS_SEAL.json`

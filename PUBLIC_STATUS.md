# CINEMATICUM — Public Status

Current active state:

    CASE_001_THE_LAST_RENDER = RELEASE_CANDIDATE_READY

Release candidate state:

    release_candidate_ready=true

Still false:
    issued=false
    media_present=false
    generation_present=false
    engine_present=false
    model_present=false
    outsider_replay_passed=false
    admissibility_verdict_present=false
    terminal_closure_present=false

Verification required:

    bash scripts/verify-all.sh

Registry freshness required:

    bash scripts/verify-object-registry-fresh.sh

## Boundary

This status page does not issue a film.

This status page reports release-candidate-ready state; it does not issue a film.

This status page does not admit footage, audio, stills, model weights, render workflows, or media.

This status page does not execute replay.

This status page does not produce an admissibility verdict.

The current truth owners remain:

- `CINEMATICUM_CURRENT_STATE_INDEX.json`
- `CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json`

# CINEMATICUM — State Transition Gate

This file defines whether CINEMATICUM may advance from the current state.

## Current active state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Gate status

    may_advance_now=false
    next_candidate_state=RELEASE_CANDIDATE_READY
    next_candidate_state_unblocked=false
    final_issuance_state_unblocked=false

## Blocked targets

    RELEASE_CANDIDATE_READY
    ISSUED_ADMISSIBLE_MOTION_PICTURE

## Binding rule

No state transition is valid unless:

1. the transition gate declares the target state unblocked;
2. the required authority objects exist;
3. the active current-state owners are updated in the same governed change;
4. `bash scripts/verify-all.sh` passes.

## Still false

    release_candidate_ready=false
    issued=false
    media_present=false
    generation_present=false
    engine_present=false
    model_present=false
    outsider_replay_passed=false
    admissibility_verdict_present=false
    terminal_closure_present=false

## Negative boundary

This transition gate does not issue a film.

This transition gate does not admit media.

This transition gate does not execute replay.

This transition gate does not produce an admissibility verdict.

This transition gate does not create terminal closure.

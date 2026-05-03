# CINEMATICUM — Required Authority Objects

This file lists the authority objects required before CINEMATICUM may advance beyond the current state.

## Current active state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Gate status

    may_advance_now=false
    release_candidate_ready_unblocked=false
    issuance_unblocked=false
    required_authority_objects_missing=true
    schemas_do_not_satisfy_authority_objects=true

## Required before release-candidate-ready

All are currently missing as authority objects:

    DIRECTOR_ACCEPTANCE_OBJECT
    FINAL_CUT_TIMELINE_LOCK_OBJECT
    SOUND_MIX_LOCK_OBJECT
    COLOR_GRADE_LOCK_OBJECT
    MEDIA_HASH_MANIFEST_OBJECT
    RELEASE_MANIFEST_OBJECT
    OUTSIDER_REPLAY_BUNDLE_OBJECT
    REPLAY_EXECUTION_REPORT_OBJECT
    ADMISSIBILITY_VERDICT_OBJECT
    TERMINAL_CLOSURE_CANDIDATE_OBJECT

## Required before issuance

All are currently missing as authority objects:

    MOTION_PICTURE_ISSUANCE_ACT_OBJECT
    OUTSIDER_REPLAY_PASS_OBJECT
    ADMISSIBILITY_VERDICT_OBJECT
    TERMINAL_CLOSURE_OBJECT
    MEDIA_ADMISSION_OBJECT

## Binding rule

A schema does not satisfy an authority object.

A README entry does not satisfy an authority object.

A public status page does not satisfy an authority object.

An object registry row does not satisfy an authority object.

A checklist row does not satisfy an authority object.

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

This checklist does not issue a film.

This checklist does not admit media.

This checklist does not execute replay.

This checklist does not produce an admissibility verdict.

This checklist does not create terminal closure.

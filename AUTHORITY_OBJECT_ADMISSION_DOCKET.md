# CINEMATICUM — Authority Object Admission Docket

This docket prevents silent authority-object appearance.

It does not admit authority.

## Current state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Request directory

    authority_object_admission_requests/

The directory is reserved. It currently contains no request JSON.

## Authority object directory

    authority_objects/

The directory remains reserved. It currently contains no authority-object JSON.

## Rule

Before any authority object can appear, a public request must exist.

A request must declare:

    object_type
    schema_version
    case_id
    target_authority_object
    source_template
    requesting_actor
    request_timestamp_utc
    authority_basis
    evidence_references
    requested_state_effect
    requested_admission_status

## Current docket status

    admission_requests_present=false
    admission_request_count=0
    accepted_admission_requests_present=false
    accepted_admission_request_count=0
    pending_admission_requests_present=false
    pending_admission_request_count=0
    instantiated_authority_objects_present=false
    authority_satisfied=false
    required_authority_objects_missing=true
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false
    terminal_closure_present=false

## Boundary

The admission docket is not an authority object.

The admission docket does not accept a request.

The admission docket does not instantiate authority.

The admission docket does not satisfy required authority.

The admission docket does not admit media.

The admission docket does not execute replay.

The admission docket does not create an admissibility verdict.

The admission docket does not advance current state.

The admission docket does not issue a film.

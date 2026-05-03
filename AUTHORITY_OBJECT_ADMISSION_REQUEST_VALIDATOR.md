# CINEMATICUM — Authority Object Admission Request Validator

This validator scans the authority-object admission request directory.

It validates request shape.

It does not create requests.

It does not accept requests.

It does not reject requests.

It does not admit authority objects.

It does not instantiate authority objects.

It does not advance state.

## Current state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Directory scanned

    authority_object_admission_requests/

## Pattern scanned

    AUTHORITY_OBJECT_ADMISSION_REQUEST_*.json

## Current result

    zero_requests_valid=true
    admission_requests_present=false
    admission_request_count=0
    valid_admission_request_count=0
    invalid_admission_request_count=0
    accepted_admission_requests_present=false
    rejected_admission_requests_present=false
    pending_admission_requests_present=false
    instantiated_authority_objects_present=false
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

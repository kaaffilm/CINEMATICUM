# CINEMATICUM — Authority Object Admission Request Schema

This document defines the request shape for future authority-object admission.

The schema does not admit any authority object.

The schema does not instantiate any authority object.

The schema does not satisfy authority.

The schema does not advance state.

## Current state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Request directory

    authority_object_admission_requests/

## Request file pattern

    AUTHORITY_OBJECT_ADMISSION_REQUEST_*.json

## Required request fields

    object_type
    schema_version
    request_id
    case_id
    requested_authority_object_type
    requested_authority_template
    requester_assertion
    evidence_references
    media_payload_present
    model_weight_payload_present
    private_access_required
    requested_admission_status
    authority_satisfied_by_request
    may_advance_state_by_request

## Required fixed values

    object_type=CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST
    case_id=CASE_001_THE_LAST_RENDER
    media_payload_present=false
    model_weight_payload_present=false
    private_access_required=false
    requested_admission_status=PENDING
    authority_satisfied_by_request=false
    may_advance_state_by_request=false

## Still false

    admission_requests_present=false
    accepted_admission_requests_present=false
    rejected_admission_requests_present=false
    pending_admission_requests_present=false
    instantiated_authority_objects_present=false
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

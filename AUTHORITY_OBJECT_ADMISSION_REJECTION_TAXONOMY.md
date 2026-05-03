# CINEMATICUM — Authority Object Admission Rejection Taxonomy

This object freezes canonical rejection reason codes for authority-object admission requests.

It prevents validator drift.

## Current result

    canonical_rejection_reason_count=9
    required_corpus_reason_count=5
    covered_rejection_reason_count=5
    uncovered_rejection_reason_count=4
    taxonomy_complete_for_current_validator=true
    corpus_complete_for_required_reasons=true
    fixtures_are_live_requests=false
    admission_request_count=0
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

## Canonical fatal reason codes

    missing_case_id
    wrong_case_id
    wrong_current_state
    unknown_authority_object_type
    authority_satisfied_by_request_true
    may_advance_state_by_request_true
    media_payload_present_true
    model_weight_payload_present_true
    private_access_required_true

## Covered by current rejection corpus

    missing_case_id
    wrong_current_state
    authority_satisfied_by_request_true
    media_payload_present_true
    private_access_required_true

## Not live authority

The taxonomy does not create requests.
The taxonomy does not accept requests.
The taxonomy does not instantiate authority objects.
The taxonomy does not advance state.

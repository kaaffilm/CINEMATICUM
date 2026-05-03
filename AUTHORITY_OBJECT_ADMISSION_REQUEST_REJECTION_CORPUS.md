# CINEMATICUM — Authority Object Admission Request Rejection Corpus

This corpus contains rejected fixtures only.

The fixtures are not live admission requests.

They are outside:

    authority_object_admission_requests/

They exist under:

    fixtures/authority_object_admission_requests/rejected/

## Current result

    rejection_fixture_count=5
    fixtures_are_live_requests=false
    admission_requests_present=false
    admission_request_count=0
    valid_admission_request_count=0
    invalid_admission_request_count=0
    accepted_admission_requests_present=false
    rejected_fixtures_are_admission_requests=false
    instantiated_authority_objects_present=false
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

## Rejection reasons

    missing_case_id
    wrong_current_state
    authority_satisfied_by_request_true
    media_payload_present_true
    private_access_required_true

The corpus hardens the validator without advancing the film.

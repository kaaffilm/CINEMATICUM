# CINEMATICUM — Authority Object Admission Decision Ledger

PR27 adds the public decision ledger for authority-object admission outcomes.

The ledger separates:

    request -> validation -> decision -> authority object instantiation

No authority object may become admissible by request existence alone.

## Current result

    decision_record_count=0
    accepted_decision_count=0
    rejected_decision_count=0
    pending_decision_count=0
    orphan_decision_count=0
    invalid_decision_count=0
    live_admission_request_count=0
    all_live_requests_have_decisions=true
    all_accepted_decisions_have_valid_requests=true
    all_rejected_decisions_have_canonical_reasons=true
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

## Rule

A future accepted decision must point to a valid live admission request.

A future rejected decision must point to a canonical rejection reason.

The ledger itself does not instantiate authority.

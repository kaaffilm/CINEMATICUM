# CINEMATICUM — Authority Object Instantiation Gate

This gate defines the boundary between an inert template and an actual authority object.

It does not instantiate authority.

## Current state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Authority object directory

    authority_objects/

The directory is reserved. It currently contains no authority-object JSON.

## Template directory

    templates/authority_objects/

Templates are not authority objects.

## Promotion requirements

A future authority object must:

    copy a template outside templates/authority_objects
    set template_only=false
    provide authority_actor
    provide authority_timestamp_utc
    provide authority_basis
    provide explicit_acceptance_or_rejection
    provide object_hashes_or_references
    provide signature_or_public_accountable_record
    pass its dedicated verifier
    pass scripts/verify-all.sh

## Still false

    instantiated_authority_objects_present=false
    authority_satisfied=false
    required_authority_objects_missing=true
    templates_do_not_satisfy_authority_objects=true
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false
    terminal_closure_present=false

## Boundary

The instantiation gate is not an authority object.

The instantiation gate does not satisfy required authority.

The instantiation gate does not admit media.

The instantiation gate does not execute replay.

The instantiation gate does not create an admissibility verdict.

The instantiation gate does not advance current state.

The instantiation gate does not issue a film.

# CINEMATICUM — Master Verification Manifest Closure

This layer closes the verification control plane.

## Current active state

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## Closure rule

Every required script and unittest named by:

    CINEMATICUM_MASTER_VERIFICATION_MANIFEST.json

must exist.

Every required script except:

    scripts/verify-all.sh

must be invoked by:

    scripts/verify-all.sh

The `scripts/verify-all.sh` script must exist and be executable, but must not self-invoke.

The `scripts/regenerate-object-registry.py` script must exist and be executable, but is not invoked by `verify-all.sh` because it is a registry utility, not a verifier.

Every required CI workflow named by the manifest must exist either by workflow file stem or by workflow `name:`.

## Verify

    bash scripts/verify-master-verification-manifest-closure.sh
    bash scripts/verify-all.sh

## Closure assertions

    manifest_present=true
    verify_all_present=true
    all_required_scripts_exist=true
    all_required_scripts_executable=true
    all_required_scripts_in_verify_all=true
    all_required_unittests_exist=true
    all_required_unittests_in_verify_all=true
    all_required_ci_workflows_exist=true
    object_registry_fresh_required=true
    verify_all_required=true
    verify_all_self_reference_exempt=true
    verify_all_membership_exempt_scripts_declared=true
    registry_generator_exempt_from_verify_all_membership=true

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

This closure guard does not issue a film.

This closure guard does not admit media.

This closure guard does not advance state.

This closure guard does not replace the current-state owners.

This closure guard does not replace the object registry.

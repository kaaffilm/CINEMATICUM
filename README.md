# CINEMATICUM

**CINEMATICUM issues admissible motion pictures.**

CINEMATICUM is a sovereign cinematic jurisdiction for issuing admissible motion pictures: finished audience-facing films whose director authority, final cut, timeline, release artifacts, and proof chain can survive independent public replay.

CINEMATICUM is not an AI video generator, prompt pipeline, model showcase, software demo, render farm, or festival gimmick.

A generated video is an output.
A studio film is a production.
A CINEMATICUM film is an issued motion-picture object.

## Case 001

`CASE_001_THE_LAST_RENDER`

**THE LAST RENDER** is the first case submitted to CINEMATICUM law.

Core thesis:

> A film is not alive because it is generated. A film is alive because someone chose what must remain.

## PR1 boundary

PR1 creates jurisdiction only.

No engines.
No models.
No generation.
No media.

## Verify

```bash
bash scripts/verify-cinematic-jurisdiction.sh
python3 -m unittest tests/test_cinematic_jurisdiction.py
````

Expected:

```text
CINEMATICUM CINEMATIC JURISDICTION: PASS
```


## PR2 — Issuance docket control plane

PR2 promotes CINEMATICUM from jurisdiction birth into issuance-docket control.

This does not issue a film.

This does not add engines, models, generation, media, render workflows, release artifacts, or finished footage.

PR2 adds the admissible film object anatomy, department authority ledger, case docket, case evidence ledger, directorial order, forbidden image doctrine, CI workflow, verifier, and tests.

The governing boundary remains:

    CINEMATICUM issues admissible motion pictures.
    No engines. No models. No generation. No media.

### PR2 verification

    bash scripts/verify-cinematic-jurisdiction.sh
    python3 -m unittest tests/test_cinematic_jurisdiction.py
    bash scripts/verify-cinematic-issuance-docket.sh
    python3 -m unittest tests/test_cinematic_issuance_docket.py

## PR3 — Release-candidate object law

PR3 adds release-candidate law and replay/manifest schemas.

This does not create a release candidate.

This does not issue a film.

This does not add footage, audio, render workflows, model outputs, release artifacts, or media.

PR3 defines how a future release candidate must bind director acceptance, locked picture, final-cut timeline, release manifest, hash manifest, and outsider replay.

### PR3 verification

    bash scripts/verify-release-candidate-law.sh
    python3 -m unittest tests/test_release_candidate_law.py

## PR4 — Authority acceptance object law

PR4 adds director acceptance, final-cut timeline lock, sound mix lock, color grade lock, and terminal-closure candidate schemas.

This does not make the case release-candidate-ready.

This does not issue a film.

This does not add footage, audio, stills, render workflows, model outputs, release artifacts, or media.

PR4 defines which authority acceptance objects must exist before a future release candidate may be asserted.

### PR4 verification

    bash scripts/verify-authority-acceptance-law.sh
    python3 -m unittest tests/test_authority_acceptance_law.py

## PR5 — Outsider replay bundle law

PR5 adds outsider replay bundle, replay execution report, admissibility verdict, and public replay index schemas.

This does not create a replay bundle.

This does not execute replay.

This does not produce an admissibility verdict.

This does not make the case release-candidate-ready.

This does not issue a film.

PR5 defines the evidence package an outsider must later be able to replay without private narration.

### PR5 verification

    bash scripts/verify-outsider-replay-bundle-law.sh
    python3 -m unittest tests/test_outsider_replay_bundle_law.py

## PR6 — Current-state index

PR6 adds the current-state index and case-level active current-state pointer.

This prevents staged layer-status records from being mistaken for competing current truth.

Current active state for `CASE_001_THE_LAST_RENDER`:

    OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false

### PR6 verification

    bash scripts/verify-current-state-index.sh
    python3 -m unittest tests/test_current_state_index.py

## PR7 — Master progression verifier

PR7 adds the governed progression matrix and master verification battery.

Use one command:

    bash scripts/verify-all.sh

Current active state:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false

PR7 prevents future layers from confusing schema with object, replay requirements with replay pass, verdict schema with verdict, or jurisdiction with issued film.

## PR8 — Object registry

PR8 adds the machine-readable object registry and surface-class catalog.

Use:

    bash scripts/verify-object-registry.sh
    bash scripts/verify-all.sh

The registry does not issue a film, does not admit media, does not execute replay, and does not override current state.

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR9 — Object registry regeneration guard

PR9 adds a freshness guard for `CINEMATICUM_OBJECT_REGISTRY.json`.

Regenerate:

    python3 scripts/regenerate-object-registry.py --write

Check:

    bash scripts/verify-object-registry-fresh.sh
    bash scripts/verify-all.sh

The guard fails when JSON objects change without registry regeneration.

## PR10 — Repository status seal

PR10 adds the public repository status seal.

Read:

    PUBLIC_STATUS.md
    CINEMATICUM_REPOSITORY_STATUS_SEAL.json

Verify:

    bash scripts/verify-repository-status-seal.sh
    bash scripts/verify-all.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false

The status seal summarizes current object state but does not outrank `CINEMATICUM_CURRENT_STATE_INDEX.json` or `CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json`.

## PR11 — Public inspection dossier

PR11 adds the outsider inspection entrypoint.

Read:

    PUBLIC_INSPECTION.md
    PUBLIC_INSPECTION_DOSSIER.json

Verify:

    bash scripts/verify-public-inspection-dossier.sh
    bash scripts/verify-all.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false

The dossier requires no private access and does not outrank the current-state owners.

## PR12 — Public inspection negative proof

PR12 proves that public inspection surfaces are not issuance, media admission, replay pass, admissibility verdict, or terminal closure.

Read:

    PUBLIC_NEGATIVE_PROOF.md
    PUBLIC_INSPECTION_NEGATIVE_PROOF.json

Verify:

    bash scripts/verify-public-inspection-negative-proof.sh
    bash scripts/verify-all.sh

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false
    admissibility_verdict_present=false
    terminal_closure_present=false

## PR13 — Authority precedence lattice

PR13 adds the authority precedence lattice.

Read:

    AUTHORITY_PRECEDENCE.md
    CINEMATICUM_AUTHORITY_PRECEDENCE_LATTICE.json

Verify:

    bash scripts/verify-authority-precedence-lattice.sh
    bash scripts/verify-all.sh

Binding rule:

    active current-state objects outrank README prose, schemas, registry projections, status seals, public inspection surfaces, negative proofs, and layer-status records.

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR14 — State transition gate

PR14 adds the state transition gate.

Read:

    STATE_TRANSITION_GATE.md
    CINEMATICUM_STATE_TRANSITION_GATE.json

Verify:

    bash scripts/verify-state-transition-gate.sh
    bash scripts/verify-all.sh

Current gate status:

    may_advance_now=false
    next_candidate_state=RELEASE_CANDIDATE_READY
    next_candidate_state_unblocked=false
    final_issuance_state_unblocked=false

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR15 — Required authority object checklist

PR15 adds the required authority object checklist.

Read:

    REQUIRED_AUTHORITY_OBJECTS.md
    CINEMATICUM_REQUIRED_AUTHORITY_OBJECT_CHECKLIST.json

Verify:

    bash scripts/verify-required-authority-objects.sh
    bash scripts/verify-all.sh

Current gate status:

    may_advance_now=false
    required_authority_objects_missing=true
    schemas_do_not_satisfy_authority_objects=true

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR16 — Transition attempt rejection ledger

PR16 adds the transition attempt rejection ledger.

Read:

    TRANSITION_ATTEMPT_REJECTION_LEDGER.md
    CINEMATICUM_TRANSITION_ATTEMPT_REJECTION_LEDGER.json

Verify:

    bash scripts/verify-transition-attempt-rejection-ledger.sh
    bash scripts/verify-all.sh

Current ledger status:

    transition_attempts_recorded=0
    valid_transition_attempt_present=false
    may_advance_now=false
    required_authority_objects_missing=true

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR17 — Public perimeter sentinel

PR17 adds the public perimeter sentinel.

Read:

    PUBLIC_PERIMETER_SENTINEL.md
    CINEMATICUM_PUBLIC_PERIMETER_SENTINEL.json

Verify:

    bash scripts/verify-public-perimeter-sentinel.sh
    bash scripts/verify-all.sh

Current sentinel status:

    private_access_required=false
    media_or_model_payload_present=false
    forbidden_private_file_present=false
    valid_transition_attempt_present=false
    may_advance_now=false
    required_authority_objects_missing=true

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR18 — Master verification manifest closure

PR18 adds the master verification manifest closure guard.

Read:

    MASTER_VERIFICATION_MANIFEST_CLOSURE.md
    CINEMATICUM_MASTER_VERIFICATION_MANIFEST_CLOSURE.json

Verify:

    bash scripts/verify-master-verification-manifest-closure.sh
    bash scripts/verify-all.sh

Closure status:

    all_required_scripts_exist=true
    all_required_scripts_executable=true
    all_required_scripts_in_verify_all=true
    all_required_unittests_exist=true
    all_required_unittests_in_verify_all=true
    all_required_ci_workflows_exist=true

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

## PR19 — Outsider clone replay

PR19 adds the clone-time outsider replay harness.

Fresh public checkout:

    git clone https://github.com/kaaffilm/CINEMATICUM.git
    cd CINEMATICUM
    bash scripts/verify-all.sh

Local harness:

    bash scripts/verify-outsider-clone-replay.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false
    valid_transition_attempt_present=false
    may_advance_now=false
    terminal_closure_present=false

The clone replay harness proves public reproducibility of the repository perimeter. It does not issue a film, admit media, execute film replay, or create terminal closure.

## PR20 — Authority object template kit

PR20 adds inert templates for future required authority objects.

Verify:

    bash scripts/verify-authority-object-template-kit.sh
    bash scripts/verify-all.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    template_only=true
    authority_satisfied=false
    templates_do_not_satisfy_authority_objects=true
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false

The template kit creates a forward path, not authority.

## PR21 — Authority object instantiation gate

PR21 defines the boundary between inert templates and actual authority objects.

Verify:

    bash scripts/verify-authority-object-instantiation-gate.sh
    bash scripts/verify-all.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    instantiated_authority_objects_present=false
    authority_satisfied=false
    required_authority_objects_missing=true
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false

The gate defines promotion requirements. It does not instantiate authority.

## PR22 — Authority object admission docket

PR22 prevents silent authority-object appearance.

Verify:

    bash scripts/verify-authority-object-admission-docket.sh
    bash scripts/verify-all.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    admission_requests_present=false
    admission_request_count=0
    accepted_admission_requests_present=false
    instantiated_authority_objects_present=false
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

The docket requires a public request before any future authority object can be instantiated.

## PR23 — Authority object admission request schema

PR23 defines the only admissible shape for future authority-object admission requests.

Verify:

    bash scripts/verify-authority-object-admission-request-schema.sh
    bash scripts/verify-all.sh

Current active state remains:

    CASE_001_THE_LAST_RENDER = OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    admission_requests_present=false
    admission_request_count=0
    accepted_admission_requests_present=false
    rejected_admission_requests_present=false
    pending_admission_requests_present=false
    instantiated_authority_objects_present=false
    authority_satisfied=false
    may_advance_now=false
    release_candidate_ready=false
    issued=false
    media_present=false

The schema does not admit an authority object and does not advance state.

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

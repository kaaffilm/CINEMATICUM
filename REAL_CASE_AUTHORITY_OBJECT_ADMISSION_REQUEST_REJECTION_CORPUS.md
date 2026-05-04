# REAL CASE AUTHORITY OBJECT ADMISSION REQUEST REJECTION CORPUS

This object adds the fixture-only rejection corpus for malformed real-case authority-object admission requests.

It proves that known-invalid request shapes are rejected without creating live requests, accepting requests, rejecting live requests, instantiating authority objects, satisfying authority, advancing state, admitting media, creating a release candidate, reopening the current snapshot, or creating a new snapshot.

## Scope

```text
REAL_CASE_AUTHORITY_OBJECTS_ONLY
````

## Current state

```text
OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED
```

## Corpus

The corpus contains five non-live fixtures:

1. missing required slot id
2. unknown authority object slot
3. media payload attempt
4. state advancement attempt
5. current snapshot mutation attempt

## Non-capability

This object is not a decision ledger.
It is not an enforcement gate.
It is not an authority-object instantiation.
It is not a release candidate.
It is not issuance.

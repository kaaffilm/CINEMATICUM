# CASE_001_THE_LAST_RENDER — Locked Picture Boundary

A locked picture is not an issued film.

A locked picture is a future admissibility object that states which sequence of shots, cuts, timings, and silences has been accepted as picture-locked under director authority.

PR3 does not create a locked picture.

PR3 defines the boundary that a future locked-picture object must satisfy before `CASE_001_THE_LAST_RENDER` can become a release candidate.

## Required future locked-picture fields

- case id
- locked picture id
- director authority id
- timeline id
- cut list digest
- shot-function map digest
- silence map digest
- accepted duration
- lock timestamp
- successor or supersession rule

## Forbidden in PR3

- footage
- audio
- rendered clips
- model outputs
- prompt chains
- release files
- final media

# CINEMATICUM

Strict realistic production stack for **THE LAST RENDER**.

This repository does not accept toy procedural media as a final film.

## Real final-picture input

Place realistic MP4 shots here:

```text
source/films/THE_LAST_RENDER/shots/
````

Each file must match:

```text
production/THE_LAST_RENDER/shots/shotlist.json
```

## Commands

```bash
make check
make source-qc
make render
make open
```

## External video backend

```bash
VIDEO_GEN_COMMAND='your_real_video_backend_command' make render
```

The backend receives:

```text
SHOT_ID
PROMPT_FILE
OUT_MP4
DURATION
WIDTH
HEIGHT
FPS
```

and must write a real MP4 to `OUT_MP4`.

No procedural fallback. No fake media. No proof-only issuance.

<!-- CINEMATICUM_PRODUCT_BOUNDARY_V1_START -->
## CINEMATICUM v1.0 Product Boundary

CINEMATICUM is now operable as a local product surface.

```bash
node bin/cinematicum.cjs verify
node bin/cinematicum.cjs proof
node bin/cinematicum.cjs artifact
node bin/cinematicum.cjs studio
node bin/cinematicum.cjs export
```

Boundary:

- no external API
- no external media
- no network runtime dependency
- no manual media selection
- no candidate selection
- no truth claim
- no admissibility claim
- no external reality claim

The product boundary proves command availability, local studio surface, release-bundle export, director-engine linkage, compiler-generated film linkage, and issued GODCUT artifact integrity.
<!-- CINEMATICUM_PRODUCT_BOUNDARY_V1_END -->

<!-- CINEMATICUM_INSTALLABLE_PRODUCT_BOUNDARY_V11_START -->
## CINEMATICUM v1.1 Installable Product Boundary

CINEMATICUM now has an installable package boundary.

The package must prove, from a clean temporary install, that these commands work without cloning the working tree manually:

```bash
cinematicum proof
cinematicum artifact
cinematicum studio
cinematicum verify
cinematicum export
```

The installable boundary preserves:

- no external API
- no external media
- no network runtime dependency
- no manual media selection
- no candidate selection
- no truth claim
- no admissibility claim
- no external reality claim

The release package is a product transport. It does not convert the film into truth, admissibility, or external reality.
<!-- CINEMATICUM_INSTALLABLE_PRODUCT_BOUNDARY_V11_END -->

<!-- CINEMATICUM_OUTSIDER_REPRODUCIBLE_RELEASE_V12_START -->

## CINEMATICUM v1.2 — Outsider Reproducible Release Boundary

CINEMATICUM v1.2 seals the public release surface.

The v1.2 boundary proves that an outsider can verify the issued GODCUT film artifact from a deterministic release bundle without trusting the author's working tree.

Verified boundary:

- deterministic release bundle
- deterministic outsider replay manifest
- release asset hash ledger
- replay from extracted bundle
- single JSON command surface
- gitless runtime verification
- no external API
- no external media
- no network runtime dependency
- no manual media selection
- no candidate selection
- truth/admissibility/external reality not claimed

Canonical issued artifact:

```text
CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4
sha256: f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192
```

Verification:

```bash
node scripts/verify-outsider-reproducible-release.mjs
```

<!-- CINEMATICUM_OUTSIDER_REPRODUCIBLE_RELEASE_V12_END -->

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

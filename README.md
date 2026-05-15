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

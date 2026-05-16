# CINEMATICUM real video backend contract

`make source-shots` does not synthesize fake film. It calls a real backend wrapper through `VIDEO_GEN_COMMAND`.

Required command form:

```bash
VIDEO_GEN_COMMAND=./scripts/backends/your-real-backend.sh make source-shots
````

For each shot, CINEMATICUM sets:

* `CINEMATICUM_FILM`
* `CINEMATICUM_SHOT_ID`
* `CINEMATICUM_PROMPT_JSON`
* `CINEMATICUM_OUTPUT_MP4`

The backend wrapper must create the MP4 at:

```bash
$CINEMATICUM_OUTPUT_MP4
```

The output must be real video material, not a still-card slideshow, not test bars, not fractal filler, not placeholder animation.

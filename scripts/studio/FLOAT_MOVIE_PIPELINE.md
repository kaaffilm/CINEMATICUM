# Scene-linear Float32 movie candidate

This isolated next-release candidate adds real scene-linear movie processing to
Studio. It is separate from the frozen 0.10 release and has its own source and
acceptance record. The existing Standard 8-bit SDR and High 16-bit SDR paths
continue to use their original processing and output profiles.

## Author and export

1. Install the existing isolated **Imaging** runtime. It must supply NumPy,
   OpenColorIO and OpenEXR; FFmpeg and ffprobe must also be available. The server
   remains standard-library-only and launches the imaging worker with `-I -B`.
2. Open **Export**, choose **Scene-linear Float32 · OCIO / ACES**, and choose
   working space, EXR output space, default source interpretation and SDR display
   view. These are ordinary editable project settings with Undo, Redo and Save.
3. Select the actual color interpretation for each picture source. EXR and
   PQ/HLG clips require an explicit per-clip space. Adding an EXR in Float32 mode
   keeps its original float data on the timeline. The UI uses its declared OCIO
   source metadata when present and otherwise chooses ACEScg as an editable
   default; that default is an interpretation, not measured color detection.
   Ordinary source media use the chosen project default unless overridden.
4. Use clip placement, opacity animation, exposure, raster titles and the
   stereo mixer. The Color inspector exposes scene-linear exposure and the
   project's OCIO controls. Paused frames use the actual float renderer and
   selected display view. Playback renders an SDR review movie first.
5. Choose **Float32 EXR movie master · ZIP** for preserved scene-linear values
   and alpha. H.264 and ProRes are display-transformed SDR derivatives. The ZIP
   is downloaded as a master package and is never sent to a browser video decoder.

The pinned config is `studio-config-v5.0.0_aces-v2.1_ocio-v2.6`. Working and EXR
output spaces are ACEScg, ACES2065-1 or Linear Rec.709 (sRGB). Input spaces come
from the actual installed config; data spaces and unknown names are rejected.
The display is `sRGB - Display`; the default view is
`ACES 2.0 - SDR 100 nits (Rec.709)`. Available non-Raw views are read from OCIO.

## Pixel processing

EXR HALF/FLOAT RGB(A) inputs are read directly through OpenEXR. Floating-point
movie formats supported by FFmpeg decode to planar float32; ordinary integer
video sources decode to 16-bit RGBA before conversion to float32. Media retain
their inspected source stream and exact selected source range.

Each clip's actual OCIO input processor converts straight RGB to the selected
scene-linear working space. Exposure multiplies that light by `2 ** stops`.
RGB is associated with alpha before bilinear scale/rotation/translation and
source-over compositing. Transparent pixels do not contribute hidden RGB.
Unassociation preserves every positive alpha, including very small fractions.
The compositor neither clamps negative RGB nor clamps superwhite RGB to one.
Nonfinite values, absolute RGB above `1e20`, and source alpha outside `[0,1]`
are rejected. Alpha roundoff alone is bounded at the composite boundary.

Clip x/y/scale/rotation/opacity curves preserve the existing interpolation modes
and trimmed animation domain. Muted/soloed picture tracks, overlapping layers,
constant-speed retime/reverse, gaps and rasterized title fades use the actual
timeline clock. The existing audio graph supplies source stream/channel mapping,
clip/track gain, keyframed gain, fades, pan, retime/reverse and the stereo limiter.
When the multicamera engine is present, its authoritative source-audio plan
retains fixed-camera sound across picture cuts, including a silent picture
camera. All angles bound by a camera audio lock join the source hash inventory.
A missing required audio-plan implementation is an explicit failure.

The master output processor transforms unassociated working RGB into the chosen
linear output space and reassociates it. Every written EXR is reopened and all
four stored FLOAT32 channels must exactly equal the intended float32 pixels.
For display only, transparency is composited against black in scene-linear
light, then the selected OCIO display/view transform runs once. Display PNG is
16-bit RGBA; its alpha is opaque. H.264 is 8-bit 4:2:0 and ProRes is 10-bit 4:2:2,
both with Rec.709 primaries/matrix and the sRGB display transfer tag. Display
encoding clips to its representable range; the EXR master retains float RGB.

## `master32` package

| Member | Actual format and binding |
| --- | --- |
| `frames/frame-00000000.exr` onward | One ZIP-compressed flat RGB+A OpenEXR per project frame; every channel is FLOAT32, with premultiplied alpha and explicit OCIO space/frame/rate metadata. |
| `mix.wav` | 48 kHz, two-channel IEEE float32 PCM, with the exact rational timeline sample count. |
| `display.png` | Opaque 16-bit RGBA SDR display derivative of frame zero. |
| `config.ocio` | The exact serialized OCIO configuration used for this render. |
| `manifest.json` | Canonical normalized project snapshot and SHA-256, exact rational rate/frame count, complete source hashes/sizes, config/processor/runtime/code identities, and every artifact's SHA-256/size. |

The outer ZIP uses stored members, supports ZIP64, and has an exact inventory.
Manifest verification rejects altered members, incomplete frame sequences,
undeclared files, duplicate names, unexpected compression, inconsistent recipe
or source identities and changed audio/frame clocks. Package verification on
archive restore checks retained bytes without executing the config or loading
the optional imaging runtime; creation independently read-checks the EXR pixels.

Portable project archives include completed owned Float32 packages and their
preserved export snapshots/receipts. Historical master sources remain bound
even when a later edit stops using them. Restore verifies dependency closure
and the inner master package; a relocated project can render the same source
pixels again. No package or receipt changes film issuance or grants approval.

## Ownership and limits

Rendering uses the normal owned Studio render job, cancellation token, durable
status and local download route. Sources are SHA-256 checked before and after
the worker and again before publishing the completed output. Files are read
without following source symlinks and checked for mutation during hashing.
Temporary processing, EXRs and partial packages stay in one private output
directory. Cancellation terminates that invocation's process group, removes
staging, and preserves imported sources and previous completed outputs. Only a
fully verified result atomically replaces its output destination.

| Bound | Limit |
| --- | --- |
| Canvas | 8,388,608 pixels |
| Source picture | 16,777,216 pixels |
| Export | 1–14,400 project frames |
| Source file | 16 GiB |
| Completed master | 32 GiB |
| Reverse picture buffer | 512 MiB |
| Still cache | 128 MiB |
| Transform tile | 64 output rows |
| Owned export / paused frame | 1,800 seconds / 45 seconds |

V1 refuses live nested sequences, compositor/plugin graphs, point/planar/learned
tracking bindings, SDR blur/sharpen/vignette/chroma-key effects, SDR contrast,
saturation/temperature and the old per-clip SDR color pipeline. It refuses
unsupported EXR layouts and arbitrary external OCIO configs. Flatten a supported
sequence deliberately or use an appropriate existing processing mode; a failed
float render does not silently substitute an 8-bit graph.

This is a bounded scene-linear movie pipeline. It does not implement HDR
mastering, reference HDR scopes, calibrated/high-bit-depth display output,
RAW movie decoding, arbitrary scene-linear plugin graphs, production-scale
throughput or a real-time float GPU playback cache. Native installation and
actual Mac acceptance are separate from Linux/Chromium verification.

## Verification entry points

Run `test_float_movie.py` and `test_float_movie_http.py` using the real isolated
Imaging interpreter and set `CINEMATICUM_IMAGING_PYTHON` to that interpreter.
The tests use explicitly labelled ENGINE TEST images and tones, actual FFmpeg,
OpenEXR and OCIO, independent numeric pixel/mix oracles and negative cases.

`test_float_movie_browser.cjs --python ABS --browser ABS --evidence NEW_ABS`
checks the shipped controls, Undo/Redo, Save/reload, paused image, actual owned
master job and real browser download. It blocks external browser requests.

`test_float_movie_ui_macos.py --binary SMOKE_HELPER --fixture FIXTURE --output
NEW_PHASE_EVIDENCE --phase prepare|author|render` runs three bounded foreground
phases using the existing `macos/SmokeTest.swift` helper. Each helper is limited
to 14 seconds; the coordinator binds prepared source identities between phases.
Actual WKWebView/WKDownload evidence requires macOS. A Chromium adapter can
exercise the coordinator without making a native acceptance claim.

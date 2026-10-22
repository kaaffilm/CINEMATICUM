# CINEMATICUM Studio 0.10: implemented scope

This document describes source implementation. [Verification](VERIFICATION_0_10.md)
records executed acceptance, and [remaining work](UNFINISHED_0_10.md) retains
unimplemented requirements. The previous 0.9.1 audio, planar tracking and high16
SDR implementations remain part of the application.

## Scientific authoring

Open **Studio tools** to use the project-owned tools. Each operation saves typed
data in the CINEMATICUM project, submits an owned job to an isolated engine,
verifies the published artifacts, and keeps an editable result history.

| Tool | Actual implementation | Current bounds |
| --- | --- | --- |
| Deep compositing | OpenEXR deep samples, multipart/multiview sources, arbitrary-channel operators, depth-aware merging and flattening, actual EXR and preview output | 48 nodes, 128 source records, 16 parts, 64 channels; explicit pixel/sample budgets. Separate from the timeline RGBA graph. |
| Learned masks | Checkpoint-backed SAM 2.1 image/video propagation, one prompted object, editable corrections, source-bound mask output and undoable application | 32 frames, 512-pixel analysis edge, binary alpha; no automatic instance discovery. |
| Learned points | Checkpoint-backed TAPIR trajectories with learned visibility/uncertainty, source-time bindings and manual corrections | 16 points, 32 frames, 512-pixel analysis edge. TAPNext is a separate unimplemented engine. |
| Lens design | Optiland optical prescriptions, packaged glass dispersion, real rays, paraxial measures, spots/fans, Seidel sums, FFT PSF/MTF and bounded least-squares optimization | Centered sequential refractive systems; 32 surfaces, nine fields/wavelengths, eight optimization variables. No manufacturing tolerance or non-sequential transport. |
| Physical rendering | Actual Mitsuba CPU RGB, spectral and polarized still rendering; bounded material inverse optimization; strict PBRT-v4 scene import/export and executable rendering | Still images and the supported typed scene/material contract. Does not implement a scene-linear movie pipeline. |
| Photo reconstruction | Actual CPU COLMAP SIFT extraction/matching, incremental structure from motion, Ceres bundle adjustment and official image undistortion | 48 photographs, 128 aggregate megapixels, bounded execution; editable camera/point proposals. Dense reconstruction, meshing/texturing and AliceVision remain open. |

Scientific results contain engine, recipe, source and artifact identities. The
application rejects missing engines, unavailable checkpoints, invalid documents
and stale dependencies instead of manufacturing successful output. Separate
native and numeric acceptance is required for each claimed workflow.

## Scene processing and collaboration

The [scene graph](SCENE_PROCESSING_V1.md) implements scene paths and sets, typed
contexts, deterministic asset variations, transforms/material/attribute edits,
pruning and camera selection. Local processing uses actual Cycles. Paired TLS
workers can execute fixed operations with immutable task/result identities,
bounded scheduling, cancellation and authenticated artifact retrieval. This is
a CINEMATICUM document format; it does not interpret Gaffer or Python plugins.

Opt-in collaboration uses a paired TLS service, durable SQLite shared state,
authenticated SHA-addressed media, revision-aware three-way edits, explicit
conflicts and reconnect/presence handling. Pairing credentials stay outside
project documents. It does not establish production-scale operation or a
general multi-tenant hosted service.

## Multicamera synchronization

The existing angle-cut editor now accepts measured synchronization from actual
selected source audio streams/channels. The worker checks silence, ambiguous
correlation and separated-window consistency, then proposes a constant sample
offset. Applying the proposal changes the multicamera group through one
undoable edit. See [multicamera synchronization](MULTICAM_SYNC.md).

The analysis covers 2–16 videos, up to 120 seconds from each selected source and
up to 60 seconds of lag. It does not correct clock drift or add simultaneous
angle monitoring or audio-lock mode.

## Runtime setup and release identity

Runtime setup manages isolated imaging, tracking, learned, optical,
reconstruction and physical worker dependencies with pinned input identities.
Heavy scientific packages are not imported into the editor server. FFmpeg,
Blender, Python and the required native system libraries remain explicit
prerequisites where not supplied by a managed runtime.

The recovered source targets **0.10.0 / build 11**. Source publication, a passing
whole-build freeze, package installation and actual installed launch are
separate records. The capability ledger retains `parity_complete: false`.

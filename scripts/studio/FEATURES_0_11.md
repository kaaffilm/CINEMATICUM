# CINEMATICUM Studio 0.11: implemented scope

Studio 0.11 retains the scientific, scene, collaboration and editing systems
documented in [0.10](FEATURES_0_10.md), then adds the following workflows.
Implementation, [verification](VERIFICATION_0_11.md), installation and
[remaining requirements](UNFINISHED_0_11.md) have separate records.

## Simultaneous cameras and fixed sound

The [multicamera monitor](MULTICAM_MONITOR.md) shows 2–16 camera pictures on
one timeline clock and permits an undoable picture cut while original source
PCM continues playing. A group may lock sound to a fixed camera, original
stream and channel pair independently of the visible picture. Gain, pan,
fades, keyframes, rational sample clocks, save/reopen, archives and rendered
nested or reversed sequences retain that source choice. Missing or altered
camera identities and invalid source ranges fail explicitly.

This remains constant-offset synchronization. It does not add clock-drift
correction, live reverse sound, speed ramps, optical flow or general conform.

## Scene-linear Float32 movies

The [Float32 movie pipeline](FLOAT_MOVIE_PIPELINE.md) performs real OCIO/ACES
input, working-space, linear output and SDR display transforms. Floating-point
premultiplied transforms and source-over preserve negative RGB, superwhite
values and fractional alpha through supported multitrack edits. Source color
interpretation, exposure, output space and display view are editable and
participate in Undo, Redo, Save and reopen.

The Float32 master is an actual RGBA FLOAT32 EXR sequence, exact-clock stereo
float PCM, OCIO configuration, project/source identities and artifact hashes
in one verified ZIP. H.264 and ProRes remain SDR display derivatives. Owned
jobs, cancellation, downloads and portable archives retain their existing
contracts. Locked multicamera sound is supported, including a silent picture
camera; every camera in its binding is checked before export.

Float32 V1 explicitly refuses unsupported live nested compositions, plugin
graphs, tracking bindings and SDR-only effects. HDR mastering, calibrated
monitoring, RAW movies and production-scale throughput remain open.

## Interchange with editable compositions

[OTIO interchange](OTIO_INTERCHANGE.md) now carries real constant-speed and
reverse operators, ordered same-track overlap lanes, trimmed/nested Track and
Stack compositions, and linear SMPTE dissolves with real source handles.
Dissolves mix associated-alpha picture and complementary source PCM; nested
audio retains the absolute sample grid at fractional frame rates. Public
interchange and checked private authoring data support review, one undo,
save/reopen, download and portable archive restoration.

Missing handles, overlapping/non-linear transitions, unsupported time effects
and plugin schemas are refused explicitly. General AAF/XML/native formats and
unrestricted third-party-editor fidelity remain open. Float32 continues to
refuse unsupported live nested/operator processing.

## Measured HDR photographs and panoramas

[Still photography](STILL_PHOTOGRAPHY.md) adds measured translation or planar
perspective alignment to 2–16 exposure brackets, real inverse-response fitting,
and a visible/downloadable reference-based motion mask. A separate 2–8-image
panorama workflow measures connected planar overlaps, optionally matches
exposure, and feathers the scene-linear pixels. Original inputs, scene-linear
FLOAT32 EXR, the 16-bit display image, geometry/response receipts and motion
mask remain available through archive restoration.

The workflows require the documented capture assumptions and pixel bounds.
Reference motion replacement retains clipped or blurred reference detail.
Spherical projection, parallax repair, moving-subject seam reconstruction and
RAW movie processing remain open. Still-image HDR output does not establish
HDR movie monitoring or mastering.

## Native lifecycle

The installed 0.10 acceptance exposed a startup quit defect. The 0.11 candidate
now waits for document/bootstrap readiness before the existing save and
active-job decision. Its native acceptance exercises the actual production class,
ordinary termination, dirty-save and explicit Keep Working / Cancel Jobs and
Quit decisions. The failed 0.10 attempt remains in the historical record.

The candidate targets **0.11.0 / build 12**. The capability ledger retains
`parity_complete: false` until the whole requested scope is implemented and
accepted; a passing local build alone does not change that scope.

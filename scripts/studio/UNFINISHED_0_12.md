# CINEMATICUM 0.12: remaining work

Reviewed 22 October 2026. [Implemented scope](FEATURES_0_12.md),
[verification](VERIFICATION_0_12.md) and the [capability ledger](capabilities.json)
distinguish source implementation from acceptance and release. This register
continues the 0.11 register while retaining uncompleted requirements.

## Remaining release work

Core `c9869e86b9421b7fdc083d249b1616114320f0d5` passed all **895 tests**, zero
failures/errors/skips, with unchanged source and managed runtimes. Four actual
retime phases passed 58 outer checks. The 0.12.0/build 13 replacement passed
five independent installation gates for 112 runtime/web files and the 117-file
bundle, preserving the prior app and existing projects. Canonical installed
launch passed 16/16 in 7.028 seconds. These completed gates are recorded in
[Verification 0.12](VERIFICATION_0_12.md).

All eight selected installed-runtime endpoint phases passed 14/14 each, with
5/5 preparation and 6/6 final preservation. Their exact reports are collected
and source-bound. The documentation/history merge has its own integrity manifest
and explicit reconciliation to unchanged accepted runtime/test sources.
Exact-head CI/publication remains the final release gate. The original
893-test freeze and failed first native archive attempt remain historical
records. No completed bounded gate changes `parity_complete: false`.

## Major systems with missing implementation

| System | Remaining work |
| --- | --- |
| AliceVision / Meshroom | Actual integrated image-to-dense-surface/texturing workflow and graph. The new CPU COLMAP sparse solver does not implement AliceVision. |
| TAPNext | Actual learned inference and editing integration where required independently of the implemented TAPIR engine. |
| CameraCtrl | Actual camera-conditioned generation with measured pose/intrinsic/ray conditioning. |
| DiffusionLight | Actual checkpoint inference and generated HDR lighting environments. |
| Commercial services | Authenticated working Runway, Krea, OpenArt, Magnific, Artlist, Firefly, Flow, Luma, Kling, Pika, FLORA and Weave operations and actual permitted output acceptance. No account or paid-job success is implied. |
| Signed distribution | Developer ID signing, notarization and a complete managed/bundled runtime distribution. A local development bundle does not close this requirement. |
| Production playback cache | A general decoded-frame/GPU cache and sustained real-media performance acceptance. Encoded proxies are already implemented. |

Deep/multiview EXR, SAM 2.1, TAPIR, optical design, physical still rendering,
typed scene processing, paired collaboration and waveform multicamera
synchronization are implemented bounded systems. They must not be described
as wholly absent. Their remaining breadth, usability and production-scale
validation remain requirements.

## Professional workflows

| Area | Remaining implementation and acceptance |
| --- | --- |
| Editing | Pitch-preserving variable-speed sound, broader curve duration/resolution, negative/zero-speed ramps, live timewarped nesting, slip/slide/roll of nonlinear maps, clock-drift correction and general offline/online conform. Studio 0.12 implements positive 0.25–4x ramps and actual DIS optical flow within a 240-frame, Standard8, 1280-edge bound, with rendered playback and exact-grid varispeed sound. Bounded native acceptance passed; broader real-shot quality and production scale remain unaccepted. |
| Interchange | General AAF/XML/native formats, arbitrary OTIO schemas/plugins, non-linear or overlapping transitions, speed ramps, freeze frames and unrestricted composition depth. Constant retime/reverse, same-track overlap lanes, trimmed/nested Track/Stack compositions and linear SMPTE dissolves are implemented; the earlier 0.11 native compositions workflow passed under its recorded source, while unrestricted third-party-editor fidelity remains unaccepted. |
| Compositing | Nested/plugin graphs, roto hierarchy/paint, broader 3D/particle composition and production cache scheduling. The timeline RGBA graph remains limited to 32 nodes and eight additional media sources; deep still processing has its own limits. |
| Tracking | Longer/multi-object learned workflows, broader production recovery, automatic lens/rolling-shutter estimation and real-shot coverage. Existing learned visibility and corrections do not establish universal re-identification. |
| Color and HDR movies | HDR mastering, calibrated monitoring, RAW movies, arbitrary external OCIO configurations and general scene-linear nested/plugin/tracking composition. The retained 0.11 implementation provides bounded real OCIO/ACES Float32 movie processing and EXR/PCM masters; high16 remains SDR and Float32 previews are SDR display derivatives. |
| Motion graphics | Full vector document/layer model, gradients/operators, general SVG/Lottie, text animators, expressions and reusable compositions. |
| 3D authoring | Edge tools, sculpting, texture painting, shader graphs, camera/light parenting, constraints, rigs, shape keys, geometry nodes and simulation. |
| Reconstruction | Dense reconstruction, meshing/texturing, broader camera models and production image-set robustness. |
| Audio | Buses/sends/returns, plugin hosting, recording/restoration/loudness workflows, surround/general output layouts, live reverse audio and pitch-preserving variable-speed ramps. The implemented ramp filter changes pitch with speed and preserves the selected stereo source clock. |
| RAW/HDR stills | RAW movies, spherical/cylindrical panorama projection, parallax and moving-subject seam repair, recovery of clipped/blurred reference detail, and broader capture/production robustness. Measured bracket alignment, relative inverse-response fitting, reference motion replacement and planar panoramas are implemented within documented capture/pixel bounds. |
| Lens correction | Lensfun profiles, fisheye/anamorphic/rational models, chromatic/vignette correction and automatic calibration. |
| Automation | General scripting/expressions/plugins and resumable interrupted rendering beyond typed owned jobs and status recovery. |
| Delivery | Broadcast/cinema/HDR profiles, target-specific QC and calibrated output monitoring. |
| Reliability and scale | Sustained sessions/generation, wider codecs/devices/shot quality, large projects, concurrent throughput and remote collaboration/farm operation. |

## THE LAST RENDER and issuance

Studio acceptance does not finish the audience film. Production still needs its
actual 18 source shots and selected takes, accepted picture, sound and grade,
final delivery and provenance, director/script/shot locks, independent outsider
replay and authoritative terminal closure. Existing compiler-cut records remain
distinct from accepted-film issuance. No status string, synthetic engine test,
or successful media decode substitutes for director acceptance.

Production remains local with no paid APIs or cloud rendering. Media/model
weights stay outside Git. The authority binding and reciprocal production
acknowledgement already exist. The derived authority reconciliation and real
final-film acceptance/independent replay implementation are published in
[CINEMATICUM/CINEMATICUM draft PR #7](https://github.com/CINEMATICUM/CINEMATICUM/pull/7)
at `03ff6d312341291b0c52cfa828f630e903133520` (16/16 local checks and passing exact-head [CI run 39756314260](https://github.com/CINEMATICUM/CINEMATICUM/actions/runs/39756314260)).
The current case remains
open until the complete final-film evidence and actual approvals exist.

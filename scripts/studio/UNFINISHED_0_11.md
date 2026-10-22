# CINEMATICUM 0.11: remaining work

Reviewed 22 October 2026. [Implemented scope](FEATURES_0_11.md),
[verification](VERIFICATION_0_11.md) and the [capability ledger](capabilities.json)
distinguish source implementation from acceptance and release. This register
continues the 0.10 register while retaining uncompleted requirements.

## Candidate release

Core `530ba240` passed the complete 874-test suite with actual optional
engines and zero failures, errors or skips. All 19 native phases passed:
15 native executions plus four fixture preparations, reporting 235 outer
checks and binding 138 unique production/helper source identities. The
startup-quit correction passed all three native regression phases. Replacement
installation passed all five independent source/bundle/backup/project/checkout
gates for 0.11.0/build 12. Canonical installed launch passed its separate
16/16-check gate in 8.408 seconds, including first ordinary termination and
preservation of all 113 bundle files.

All seven selected default-runtime readiness gates passed: deep 17/17 and
six separate phases of 14/14. Preparation passed 5/5; the final 6/6 preservation
gate confirmed the complete bundle and protected workspace remained unchanged.
The documentation/ledger manifest is reconciled to the accepted runtime/test
source with an explicit six-file documentation-only delta. The remaining 0.11
release work is exact-head CI and publication. Results retain their exact source
and receipt identities. The first 0.10 ordinary installed quit, the first 0.11
full-suite fixture failure, initial aggregate installer timeout, and aggregate
ray-optics deadline remain preserved as historical failed or incomplete attempts.
The ray-optics deadline occurred after actual ordinary quit and before the
large preservation rehash; its later phased acceptance is separate evidence.

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
| Editing | Variable speed ramps, optical-flow retiming, clock-drift correction and general offline/online conform. Simultaneous monitoring and fixed source-audio locking passed the bounded 0.11 native and complete-suite gates; broader production acceptance remains separate. |
| Interchange | General AAF/XML/native formats, arbitrary OTIO schemas/plugins, non-linear or overlapping transitions, speed ramps, freeze frames and unrestricted composition depth. Constant retime/reverse, same-track overlap lanes, trimmed/nested Track/Stack compositions and linear SMPTE dissolves passed bounded 0.11 native and complete-suite gates; unrestricted third-party fidelity remains unaccepted. |
| Compositing | Nested/plugin graphs, roto hierarchy/paint, broader 3D/particle composition and production cache scheduling. The timeline RGBA graph remains limited to 32 nodes and eight additional media sources; deep still processing has its own limits. |
| Tracking | Longer/multi-object learned workflows, broader production recovery, automatic lens/rolling-shutter estimation and real-shot coverage. Existing learned visibility and corrections do not establish universal re-identification. |
| Color and HDR movies | HDR mastering, calibrated monitoring, RAW movies, arbitrary external OCIO configurations and general scene-linear nested/plugin/tracking composition. The 0.11 candidate implements bounded real OCIO/ACES Float32 movie processing and EXR/PCM masters; high16 remains SDR and Float32 previews are SDR display derivatives. |
| Motion graphics | Full vector document/layer model, gradients/operators, general SVG/Lottie, text animators, expressions and reusable compositions. |
| 3D authoring | Edge tools, sculpting, texture painting, shader graphs, camera/light parenting, constraints, rigs, shape keys, geometry nodes and simulation. |
| Reconstruction | Dense reconstruction, meshing/texturing, broader camera models and production image-set robustness. |
| Audio | Buses/sends/returns, plugin hosting, recording/restoration/loudness workflows, surround/general output layouts and live reverse audio. |
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

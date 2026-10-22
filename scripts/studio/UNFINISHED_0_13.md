# CINEMATICUM 0.13: remaining work

This register describes the accepted 0.13 feature/core scope and preserves
the requirements remaining after the published 0.12 release. See the
[implemented scope](FEATURES_0_13.md), [verification record](VERIFICATION_0_13.md)
and [capability ledger](capabilities.json). `parity_complete` remains false.

## Release completion

Lensfun radial profiles, four fisheye projections and bounded FCPXML
interchange passed the actual integrated Mac author/render workflows and their
independent media/schema checks. All 925 complete-suite tests passed against
one frozen core with no failures/errors/skips and unchanged source/runtimes.
Six actual Mac phases passed 150 outer checks (four native executions and two
fixture preparations); the exact Mac XML input/export also passed the separate
pinned Apple 1.10 DTD gate. Those gates are complete.

Actual replacement installation passed 5/5 for the complete 119-file bundle
and 114 runtime/web files, preserving the prior 0.12 bundle and all 59 existing
project files (2,858,334,501 bytes). Canonical launch passed 16/16; all eight
selected installed runtime endpoints passed 14/14 with 5/5 preparation and
6/6 final preservation. Those installation/readiness gates are complete.

This evidence publication reconciles the six documentation/ledger changes to
unchanged accepted product/test/native/CI files. Exact-head CI is a
post-publication gate: [PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162)
and its current run/artifact record the actual published-head result. This
source record does not predict its own later CI outcome. Full professional
parity and accepted-film requirements below remain unfinished.

The published 0.12 release already passed its 895-test complete run, actual
native retiming, installation, launch, selected runtime readiness and final
10/10 installed-source reconciliation. Those completed local/native gates do
not need to be repeated merely to describe the new candidate. Exact-head
Studio CI for its published source passed all 895 tests and seven separate
browser gates, with the entire declared source and manifest identity verified.

## Major systems with missing implementation

| System | Remaining work |
| --- | --- |
| AliceVision / Meshroom | Integrated image-to-dense-surface/texturing workflow and graph; the existing CPU COLMAP sparse solver is a separate bounded reconstruction workflow. |
| CameraCtrl | Actual camera-conditioned generation with measured pose/intrinsic/ray conditioning. |
| DiffusionLight | Actual checkpoint inference and generated HDR lighting environments. |
| Commercial services | Authenticated working Runway, Krea, OpenArt, Magnific, Artlist, Firefly, Flow, Luma, Kling, Pika, FLORA and Weave operations, with permitted output acceptance. |
| Signed distribution | Developer ID signing, notarization and a complete managed/bundled runtime distribution. |
| Production playback cache | General GPU caching and sustained real-media performance acceptance. A bounded 96 MiB decoded-picture cache supports repeated paused/scrub/reverse requests; native/production throughput remains open. |

The Runtime setup catalogue now includes the existing pinned imaging and
OpenCV tracking installers and a separate official TAPNext overlay through
authenticated, lock-bound owned jobs.
Imaging cancellation also preserves its unpublished-runtime boundary. This
closes those management integrations; the complete runtime distribution and
signing requirements above remain open.

Bounded deep/multiview EXR, SAM 2.1, TAPIR, independent TAPNext, Optiland optical prescriptions,
Mitsuba/PBRT still rendering, typed scene processing, paired collaboration,
waveform camera synchronization, simultaneous camera monitoring, locked
source audio and positive variable-speed retiming are implemented systems.
Their broader production requirements remain open; they are not wholly absent.

## Professional workflows

| Area | Remaining implementation and acceptance |
| --- | --- |
| Editing | Broader curve duration/resolution; negative/zero-speed ramps; live timewarped nesting; slip/slide/roll of nonlinear maps; clock-drift correction; general offline/online conform; arbitrary-footage flow quality. Existing ramps are positive 0.25–4x, at most 240 frames, Standard8 and at most a 1280-pixel edge, with rendered playback and varispeed sound. |
| Interchange | AAF, native editor libraries and general XML formats; external Final Cut Pro acceptance; FCPXML transitions/titles/multicam/effects, custom routing and unrestricted sampling; arbitrary OTIO schemas/plugins, non-linear or overlapping transitions, speed ramps, freeze frames and unrestricted composition depth. The new bounded standalone FCPXML 1.9/1.10 import and 1.10 export supports exact cut/gap/connected-lane/compound clocks and measured constant picture grids; only the 1.10 grammar is independently DTD-validated. Existing OTIO constant retime/reverse, same-track lanes, trimmed/nested Track/Stack compositions and linear SMPTE dissolves remain supported within their separate bounds. |
| Compositing | Nested/plugin graphs, roto hierarchy/paint, broader 3D/particle composition and production cache scheduling. The RGBA graph remains bounded to 32 nodes and eight additional media sources. |
| Tracking | Longer/multi-object learned workflows, production recovery, automatic lens/rolling-shutter estimation and broader real-shot coverage. |
| Color and HDR movies | HDR mastering, calibrated monitoring, RAW movies, arbitrary external OCIO configurations and general scene-linear nested/plugin/tracking composition. High16 remains SDR; Float32 previews are SDR display derivatives. |
| Motion graphics | Full vector document/layer model, gradients/operators, general SVG/Lottie, text animators, expressions and reusable compositions. |
| 3D authoring | Edge tools, sculpting, texture painting, shader graphs, camera/light parenting, constraints, rigs, shape keys, geometry nodes and simulation. |
| Reconstruction | Dense reconstruction, meshing/texturing, broader camera models and production image-set robustness. |
| Audio | Buses/sends/returns, plugin hosting, recording/restoration/loudness workflows, surround/general output layouts and production sound acceptance. Bounded rendered pitch-preserving positive ramps are implemented. Live source-PCM reverse, constant-speed reverse and nested reverse are implemented; broader sustained production audio acceptance remains open. |
| RAW/HDR stills | RAW movies, spherical/cylindrical panorama projection, parallax and moving-subject seam repair, recovery of clipped/blurred reference detail and broader capture robustness. |
| Lens correction | Automatic calibration and EXIF/profile matching; focal interpolation; database updating; ACM/TCA/vignetting/crop records; non-rectilinear Lensfun profiles; anamorphic/rational models; animated parameters; arbitrary panorama projection and greater-than-180-degree reconstruction. Actual measured radial Lensfun samples and four explicit fisheye models are now implemented within their documented capture/pixel bounds; production lens accuracy and maximum-size performance still need acceptance. |
| Optical design and physical rendering | Non-sequential optical transport, tolerancing and production lens validation; general spectral differentiable movies and unrestricted PBRT/scene/material transport. The separately implemented Optiland and Mitsuba/PBRT workflows retain their stated limits. |
| Automation | General scripting/expressions/plugins and resumable interrupted rendering beyond typed owned jobs and status recovery. |
| Delivery | Broadcast/cinema/HDR profiles, target-specific QC and calibrated monitoring. |
| Reliability and scale | Sustained sessions/generation, wider codecs/devices/shot quality, large projects, concurrent throughput and remote collaboration/farm operation. |

## THE LAST RENDER and issuance

Studio engine acceptance does not finish the audience film. Production still
needs its actual 18 source shots and selected takes, accepted picture, sound
and grade, final delivery/provenance, director/script/shot locks, independent
outsider replay and authoritative terminal closure. The retained
[0.12 issuance register](UNFINISHED_0_12.md#the-last-render-and-issuance)
documents the separately published authority/replay implementation and its
scope. Synthetic engine tests, status strings and successful media decoding
do not substitute for actual final-film evidence and director approval.

Current incremental source/evidence limits are recorded in [the candidate acceptance note](INCREMENTAL_ACCEPTANCE_2026_10_22.md). Earlier installed/native receipts do not certify the changed source.

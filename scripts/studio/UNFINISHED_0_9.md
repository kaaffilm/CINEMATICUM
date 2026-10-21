# CINEMATICUM 0.9.1 candidate — remaining work

Reviewed 21 October 2026. This register distinguishes missing implementations, bounded features, current acceptance and release alignment. The filename is retained for existing links. [Verification 0.9.1](VERIFICATION_0_9_1.md) records the current candidate; [verification 0.9](VERIFICATION_0_9.md) preserves earlier execution without transferring its results to newer source.

**CINEMATICUM remains incomplete against the requested application and system scope.** Selected-source audio playback, measured affine/projective tracking and high16 SDR movie processing are implemented in the current source. They do not complete the absent systems below. The machine-readable [capability ledger](capabilities.json) retains `parity_complete: false`.

| Ledger state | Entries | Meaning |
| --- | ---: | --- |
| `implemented` | 1 | Implementation within the stated contract. |
| `implemented_bounded` | 46 | Implementation with explicit data, operation or resource limits; includes the accepted normal 17-frame Wan workflow. |
| `partial` | 12 | A portion exists while major behaviors remain absent. |
| `missing` | 13 | No implemented execution path for the named system: the 11 major systems plus general decoded-picture caching and signed distribution. |
| **Total** | **72** | Capability groups of different sizes, not a completion percentage. |

## 1. Acceptance and release gates at this evidence freeze

| Gate | Current evidence | Work still required |
| --- | --- | --- |
| Live audio | Final-native-01 routing 11/11 and overlap, nested and retimed playback 12/12 each, with zero underruns. Routing captured two phases; each sequence scenario ran three repetitions. | Wider codecs/devices/long sessions remain unverified. Reverse live audio requires rendered playback. Installed-source reconciliation now passed 9/9. |
| High16 SDR movies | Final-extended-01 passed 21/21; production download-04 passed 22/22 independent checks for actual default Save and public NSSavePanel Cancel action, exact master bytes, decode/alpha and cleanup. | Physical Cancel-button/Escape input, arbitrary chooser navigation, renamed/existing destinations are outside acceptance. HDR/scene-linear movies, calibrated display and production scale remain open. Failed attempt03 remains historical. |
| Planar tracking | After the worker-launch fix, bundle-fixed-planar passed 10/10 in 10.282 seconds through seven native stages and actual measurement/render. Both pin centers remain (80.5, 64.0), movie 268,926 bytes. | Broader shots, re-identification, lens/rolling-shutter estimation and sustained/concurrent throughput remain open. Corrected canonical launch and final source reconciliation have passed. |
| Normal local generation | Two real 480 × 272, 17-frame, 20-step Euler takes passed 14/14 media and 14/14 native playback each. One 33-frame case passed 11/11 inference-harness, 14/14 media and 14/14 playback checks. | Broader duration coverage, sustained operation and production quality remain unverified. Earlier termination, nearly-black output and first 13/14 playback remain historical failures. |
| Whole-build regression | Current worker-corrected source passed 544 tests with zero failures, errors, skips or expected failures; report elapsed 169.194 seconds, wrapper 169.301. All 189 operative files stayed unchanged, actual optional workers and genuine RAW ran. | Corrected runtime is published at `81827cf`; all 23 exact-head workflows passed; later documentation/live PR-head checks remain separate. Historical base `4530c54` passed 23 workflows, 543 Studio tests and 209 manifest checks; that result does not certify the new runtime fix. |
| Production ordinary quit | Quit-05 passed 21/21 independent and 10/10 native checks in 67.203 seconds. Real Keep Working completed a 48-frame high16 master; later cancellation stopped a second real render and preserved the first output and saved edits. | This tests unchanged production methods and actual alerts with isolated startup; it is separate from installed-app UI and does not explain the historical generation termination. |
| Installed application | Install-03 passed all five gates in 16.515 seconds; full private receipt now collected/hash-verified. Canonical launch-02 passed 16/16 in 5.361 seconds; final published-source reconciliation passed 9/9 against `81827cf`, including all 62 runtime and 67 bundle files. Original and later prior-bundle archives and protected workspace are preserved. | Signed/notarized self-contained distribution and production-scale validation remain unfinished. These launch/integrity passes do not certify every editing workflow or establish current THE LAST RENDER completion/issuance. |
| Repository/release records | Corrected runtime published as `81827cf92d159b9619d51000da61ea3c8a6b6ce7`; original failure reports and newly passed release receipts are retained. | Retain the 23/23 exact-head CI result separately from the live PR head, then publish this status/evidence update and manifest with their own identities. No full-system completion is implied. |

The canonical app's first actual launch exposed a real preservation defect:
isolated `-I` Python workers ignored inherited bytecode settings and created
three cached modules inside the bundle (67 files became 70). Five worker launch
sites across imaging, planar, lens and roto modules now explicitly pass `-B`.
The retained failing subprocess regression, corrected 8/8 focused checks,
544-test freeze and new native planar/quit gates cover that correction.
Install-03 installed it; canonical launch-02 subsequently passed 16/16 with the
whole bundle unchanged, and final source reconciliation passed 9/9.

Earlier MIDIA grant/context interruptions and the 64-session limit delayed
execution and receipt collection. Current-session access is restored; actual
receipt collection, canonical-launch verification, native Save/public-action
Cancel and final reconciliation are passed. Historical uncollected/failed
records remain unchanged to preserve what was known at each freeze.

## 2. Major systems still absent

These are source-implementation gaps. A model name, installed external program, source review, solved-data importer or generic job adapter does not count as an implementation of the requested system.

| Missing system | What remains absent | Boundary of current code |
| --- | --- | --- |
| Deep compositing | Deep-image samples/operators, multiview compositing and an arbitrary-channel EXR graph. | The [compositor](compositor.py) uses bounded RGBA nodes; the [still worker](image_worker.py) has separate single-part RGB/RGBA EXR operations. |
| Meshroom / AliceVision reconstruction | Integrated feature extraction/matching, SfM/bundle adjustment, dense reconstruction, surface/texturing and reconstruction graph. | [Camera import](camera_io.py) reads already-solved pinhole cameras; it does not solve images. |
| SAM 2 | Actual checkpoint-backed image/video segmentation, correction/object memory and propagation. | [Roto](roto.py) and [tracking](tracking.py) author geometric masks or measure classical motion. |
| TAPIR / TAPNext | Learned point inference, checkpoint/recurrent state, occlusion/re-identification and editable correction workflow. | [Point](tracking.py) and [planar](planar_tracking.py) tracking use classical measurement. |
| CameraCtrl | Camera-conditioned model execution and faithful pose/intrinsic/ray conditioning. | [Scene cameras](scene.py) and [managed Wan generation](managed_generation.py) are separate; text-to-video does not consume CameraCtrl conditioning. |
| Commercial AI services | Authenticated, working integrations for Runway, Krea, OpenArt, Magnific, Artlist, Firefly, Flow, Luma, Kling, Pika, FLORA and Weave. | [Generic API workflows](adapters.py) and local Wan do not establish those services' accounts, models or product workflows. |
| Optiland / ray-optics | Optical prescriptions, glass catalogues, real-ray/paraxial tracing, optimization, aberration, PSF and MTF tools. | [Camera optics](camera_io.py) and [Brown distortion](lens_assets.py) provide bounded geometric operations. |
| Mitsuba / pbrt | Spectral/polarized/differentiable transport, inverse optimization and pbrt scene/backend execution. | [Scene rendering](scene.py) drives bounded actual Cycles work. |
| Gaffer-style scene processing | General scene paths/sets/contexts, lazy processing, asset variants and distributed dispatch. | [Object hierarchy](scene_hierarchy.py) and owned jobs retain a narrower authored scene. |
| DiffusionLight | Actual model inference and generated probes/HDR environment maps. | The boundary is documented in [AI/motion research](research/ai-motion.md); no checkpoint worker executes it. |
| Real-time collaboration | Shared project state/database, concurrent editing, conflict handling, presence/permissions and multi-client recovery. | [Local storage/job ownership](server.py) and undo remain local application mechanisms. |

Each system needs an editable CINEMATICUM representation, usable controls, actual execution, persistence/undo, cancellation/recovery where applicable, and independent output acceptance. The current source does not supply those missing parts.

## 3. Existing systems that remain incomplete

| Area | Implemented scope | Remaining work |
| --- | --- | --- |
| Professional editing | Rational time, multitrack trim/split/ripple/slip/slide/roll, constant forward/reverse speed, shared-format sequences, manual multicam, captions/proxies. | Variable speed ramps, optical-flow retiming, automatic multicamera synchronization, simultaneous angle monitor, audio-lock mode and general offline/online conform. |
| Project interchange | Bounded OTIO cuts/gaps and nested Stack/Track ranges with identity-checked private roundtrip metadata. | General AAF/XML/native formats; transitions, retime/reverse export, same-track overlaps, trimmed Tracks/top-level Stacks and disabled nested items. |
| Compositing | One primary source plus eight additional media sources within 32 nodes; defined masks/effects/merges and animated Bézier paths. | Nested/general plugin graphs, broad 3D/particle composition, roto hierarchy/paint and production cache scheduling. |
| Tracking | Classical point measurement; actual affine/projective planes up to 240 frames/640-pixel analysis edge; bounded stabilization/pinning. | Automatic re-identification, lens/rolling-shutter estimation, broad correction/long-shot workflow and production-scale acceptance. |
| Color/HDR movies | Display-referred SDR grades/LUTs and opt-in 16-bit integer RGBA movie processing; separate float OCIO/RAW/EXR still and Cycles master paths. | Whole-timeline OCIO/ACES, scene-linear floating-point movie composition, HDR mastering and calibrated output monitoring. |
| Motion graphics | Cubic roto/path editing, bounded monotone animation tangents and one closed SVG path exchange. | General vector document/layers, gradients/operators, SVG/Lottie interchange, text animators, expressions and reusable compositions. |
| 3D authoring | Bounded vertex/face/UV editing, object hierarchy, eight modifiers, camera/light/material controls and actual Cycles. | Edge tools, sculpt/texture painting, shader graphs, camera/light parenting, constraints, rigs/shape keys, geometry nodes and simulation. |
| COLMAP | Selected solved PINHOLE/SIMPLE_PINHOLE camera import. | Feature extraction/matching, structure from motion, bundle adjustment, dense reconstruction and broader camera models. |
| Audio production | Selected-stream/channel stereo mix, gains/pan/fades, forward live source PCM and rendered reverse audio. | Buses/sends/returns, plugin hosting, surround/general layouts, recording/restoration/loudness and full session workflows. |
| RAW/HDR still workflows | Actual rawpy/LibRaw development, known-response merge of 2–16 aligned stills and float EXR. | RAW movies, bracket alignment, deghosting, response-curve fitting and panorama stitching. |
| Lens correction | Static bounded five-term Brown warp with explicit calibration. | Lensfun profiles, broad fisheye/anamorphic/rational models, chromatic/vignette correction and automatic calibration. |
| Automation | Typed operations, owned jobs, snapshots, receipts and polling recovery. | General scripting, expressions, plugin hosting, wider automation and resumable interrupted renders. |
| Delivery | H.264, ProRes and a high16 FFV1/alpha master; separate retained float EXR masters. | Complete broadcast/cinema/HDR profiles, target-specific QC and calibrated monitoring. |
| Performance/distribution | Encoded preview proxies, bounded processed-frame jobs, source PCM caching, verified local app replacement and optional managed runtimes. | General decoded-frame/GPU playback cache, production-scale validation and signed/notarized distribution with all required runtimes bundled or fully managed. |

The limits above are part of the persisted/rendered contract. Examples include 64 shared-format sequences, eight nested levels, 4,096 stored clips and 1,024 expanded instances; manual multicamera groups of 2–16 videos; 2–32 Bézier anchors and 64 path keys; and a 2,073,600-pixel planar/lens warp bound. The [capability audit](CAPABILITY_AUDIT.md) and [ledger](capabilities.json) retain the detailed per-feature limits and source evidence.

## 4. Boundaries of the new implementations

### Selected-source sample playback

[Audio source preparation](audio_source.py) decodes the chosen original stream/channels to verified 48 kHz stereo float PCM. The [scheduler](web/pcm-playback.js) schedules source samples with live mix changes, including simultaneous clips and nested instances. Forward retimes use pitch-preserving source-tempo derivatives. It does not play a pre-rendered timeline mix to simulate interactivity.

Buffering is bounded to a three-second horizon and 128 MiB in memory; the disk derivative cache is bounded to 16 GiB and each standard WAV to its 32-bit size limit. Current native captures establish their tested cases, not every codec, hardware device, long session or output layout. The former browser-decoder silence is retained in historical verification; it must not be presented as a fresh failure of the new scheduler without a matching reproduction.

### Planar measurement and edit dependencies

The [worker](planar_worker.py) executes actual feature flow and RANSAC affine/projective fitting. Source hashes and source-time/rate/clip bindings accompany measurements. Applying stabilization or an image pin changes actual rendered pixels; pinning accounts for the background's existing stabilization.

A pure timeline translation moves a dependent pin once. Incompatible source/timing edits, a deleted driver, independent pin movement, invalid track ordering or changed background transform mark derived motion stale. Clips, imported media, authored keys and the original measurements remain intact. The inspector/Track dialog expose the stale state; stale stabilization is bypassed and stale pins are transparent in preview. [Export preflight](planar_tracking.py) refuses stale motion until the user remeasures or explicitly clears it. Save/reopen and undo retain these states. This preserves authored work without silently issuing a misleading final composite.

Native-07 completed measurement, application, undo, timing edits, save/reopen and processed-frame review, then exceeded its 12-second ProRes wait while Wan inference was active. Native-08 passed after generation stopped. The earlier timeout is retained as history, not converted into a pass. The harness now keeps its isolated source/store, measurements, native logs, job snapshots and active worker files on failure, and uses a bounded 60-second export wait within a 120-second control sequence. These bounded tests do not establish production concurrency.

### High16 SDR movies

The movie graph has an explicit 16-bit unsigned normalized RGBA path, alpha-aware transforms/source-over and 16-bit paused PNG output. The `master16` profile writes lossless FFV1 level-3 `gbrap16le` with alpha and PCM audio. The high16 canvas limit is 8,388,608 pixels and the transformed working-image limit is 16,777,216 pixels; narrower graph limits remain applicable. Sources: [engine](engine.py), [compositor](compositor.py), [frame preview](frame_preview.py), [numeric acceptance](test_high_precision.py).

This remains clamped SDR. A 16-bit container does not prove that all processing preserved precision; decoded numeric/alpha checks are required. Conversely, the old statement that every movie path reduces to 8-bit is no longer accurate. Separate OCIO/RAW/EXR stills and Cycles float masters do not complete a scene-linear/HDR movie pipeline.

### Managed local generation

The managed engine supplies one pinned core Wan 1.3B workflow with custom nodes disabled. The earlier reduced genuine take remains a real inference proof. An earlier normal take was cancelled during ordinary app termination; a later completed UniPC take was nearly black and rejected. Two subsequent serial Euler takes passed independent media acceptance at the normal settings, with 17 distinct decoded frames each. The verifier reads actual sample timestamps/durations and MP4 media/edit-list clocks: it accepts only their measured clock quantization and still rejects missing frames, shortened samples and unrelated timing errors. No accepted source file was altered to obtain this result.

The first native playback attempt exposed final-frame loss when adding a rounded-duration source to the timeline. The nearest-frame correction and exact-timing verifier passed 18 focused Node/real-media checks, and both final native playbacks subsequently passed 14/14 with all 17 timeline frames. The normal 17-frame workflow is accepted within those settings. The harness binds both the exact intended project and current job ID so a different fixture or earlier job cannot satisfy a fresh run. Its explicit `--frames 33` option uses the real length input after checking normal defaults, retains 480 × 272, 20 steps, 16 fps and CFG 6, and grants a bounded 2,400 seconds per take. Actual 33-frame inference and native playback passed; generation elapsed 928.394 seconds. Final-extended-01 passed high16, generation33, generation33-playback and source-after in 937.624 seconds. Retained raw reports passed 11/11 inference-harness, 14/14 media and 14/14 playback checks; native playback took 4.208 seconds. All 33 source frames decoded, were distinct/nonblank, and retained their original hash/provenance. Sources: [managed engine](managed_generation.py), [native inference harness](test_generation_inference_macos.py), [output verifier](macos/verify_generated_take.py), [real MP4 timing regression](test_generated_take_timing.py).

## 5. Frozen-source verification and release alignment

The earlier **515 tests in 153.974 seconds with zero failures/skips** belong to the earlier frozen source recorded in [verification 0.9](VERIFICATION_0_9.md). Earlier 3D, editorial, roto, media, Metal, RAW, OTIO and reduced-Wan results retain their value at their actual scope. New code and new harnesses require their own executions.

The current worker-corrected frozen Linux run passed **544 tests with zero
failures, errors, skips or expected failures**. Report elapsed time was 169.194
seconds; wrapper elapsed was 169.301 seconds. Actual pinned NumPy, OpenCV, OCIO,
rawpy/LibRaw, OpenEXR and official OpenTimelineIO ran, including genuine Kodak
RAW. All 189 operative files stayed unchanged; the 48 unchanged JavaScript
files retain their successful syntax checks. The
[current report](verification/0.9.1/bundle-fixed-full-actual-runtime-report.json),
[operative inventory](verification/0.9.1/bundle-fixed-frozen-operative-source.json)
and [identity check](verification/0.9.1/bundle-fixed-frozen-operative-check.json)
retain exact evidence. Report SHA-256 is
`50f5531cbbd015abb7dc238c91e91ecc685d0cda48014deac31f70e416264541`;
inventory SHA-256 is
`30b514a409c8a0d86a047780b004942f6c65defbaf3ccb7e0da72f92085f7f3d`.
The earlier 543-test reports remain attached to their previous snapshots.

Historical base `4530c54` passed 23 workflows, 543 Studio tests and 209
manifest files. The corrected 544-test runtime is now published as
`81827cf92d159b9619d51000da61ea3c8a6b6ce7`; all 23 exact-head workflows passed. Later documentation-commit CI remains
separate from live [PR #162 checks](https://github.com/kaaffilm/CINEMATICUM/pull/162/checks).
Native audio/high16, normal and bounded 33-frame generation/playback, planar,
production quit and scoped chooser Save/Cancel passed. The full install-03
receipt is collected, canonical launch passed 16/16 and final reconciliation
passed 9/9. Remaining release-record work is to retain those exact identities,
preserve the passed exact-head CI record and publish the status/evidence update with an updated
manifest. All missing systems, broader professional workflows and signed
self-contained distribution remain open; this Studio work does not establish current THE LAST RENDER completion/issuance.

The original production checkout and the isolated development worktree have distinct state. Preserve the owner's modified files and existing projects; do not overwrite them merely to align a version. The separate issuance/compiler authority is also distinct from the Studio editor. Installing Studio does not generate missing production source takes or certify a finished film. The installer preserves external project storage and the optional runtimes, but it does not make external FFmpeg/Blender prerequisites self-contained or signed. The current signing-identity inspection found one Apple Development identity and no Developer ID Application identity; it does not establish a signed/notarized distribution. No named-provider credential was exported in the inspected MIDIA environment, which does not establish whether credentials exist in another keychain or account.

At 2026-10-21 22:41 UTC, a [read-only owner-output inventory](verification/0.9.1/case001-owner-output-inventory.json) found the exact owner-checkout `source/films/THE_LAST_RENDER/shots`, `dist/films/THE_LAST_RENDER` and `production/THE_LAST_RENDER/qc` directories present but each containing zero regular files and zero bytes. This establishes no current source-shot, delivery or QC files in those three directories; it does not audit other locations or contradict retained historical compiler/replay releases. Current THE LAST RENDER completion and issuance are not established by this Studio work.

## 6. Hardware and scope of evidence

Current native `sysctl`/`sw_vers` reports identify Apple M3, 17,179,869,184 bytes of memory (16 GiB), and macOS 26.5.2 build 25F84. Actual tracking probing reports OpenCV 4.11.0 and NumPy 2.3.5. Runtime availability is distinct from a passed authoring workflow. MPS generation and bounded Metal rendering on this machine do not certify CUDA/OptiX/HIP/oneAPI execution, arbitrary checkpoints, long takes or production throughput. Those need suitable hardware and corresponding real-output evidence.

The audit covers focused investigation of 33 reference systems. It is not an exhaustive line-by-line review of entire upstream codebases or proprietary source. The 72 ledger groups do not map every upstream subfeature. Full completion requires the absent systems, remaining professional workflows and their actual acceptance, not a documentation status change. `parity_complete` remains `false`.

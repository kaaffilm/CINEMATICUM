# CINEMATICUM 0.9.1 candidate — remaining work

Reviewed 21 October 2026. This register distinguishes missing implementations, bounded features, current acceptance and release alignment. The filename is retained for existing links. [Verification 0.9.1](VERIFICATION_0_9_1.md) records the current candidate; [verification 0.9](VERIFICATION_0_9.md) preserves earlier execution without transferring its results to newer source.

**CINEMATICUM remains incomplete against the requested application and system scope.** Selected-source audio playback, measured affine/projective tracking and high16 SDR movie processing are implemented in the current source. They do not complete the absent systems below. The machine-readable [capability ledger](capabilities.json) retains `parity_complete: false`.

| Ledger state | Entries | Meaning |
| --- | ---: | --- |
| `implemented` | 1 | Implementation within the stated contract. |
| `implemented_bounded` | 45 | Implementation with explicit data, operation or resource limits; acceptance is recorded separately. |
| `partial` | 12 | A portion exists while major behaviors remain absent. |
| `missing` | 13 | No implemented execution path for the named system: the 11 major systems plus general decoded-picture caching and signed distribution. |
| `adapter_implemented_validation_pending` | 1 | Two genuine normal takes pass independent media checks; corrected native playback, longer takes and sustained operation require further acceptance. |
| **Total** | **72** | Capability groups of different sizes, not a completion percentage. |

## 1. Current acceptance and release gates

| Gate | Current evidence | Work still required |
| --- | --- | --- |
| Live audio | Native-03 passed routing (11 checks) and overlap, nested sequence and retimed playback (12 checks each), with zero underruns. Routing used selected-source and gain/pan/restart phases; each sequence scenario ran three repetitions. The new path schedules source PCM rather than relying on the former container decoder. | Bind these reports to the frozen source and verified installed runtime. Wider media/device coverage and production-scale playback remain unverified. Reverse live sound still requires rendered playback. |
| High16 SDR movies | Native-03 passed 21/21 checks on three transformed 64 × 32 frames at 12 fps, saved precision, export controls and an actual 63,252-byte WKDownload. The FFV1 `gbrap16le`/alpha master includes 48 kHz stereo PCM. Numeric regression distinguishes 1,024 source values and checks fractional alpha/transforms. | Bind the reports to frozen/installed source. The NSSavePanel chooser, calibrated display and production scale remain unverified. HDR/scene-linear movie work remains separate. |
| Planar tracking | Native-08 passed 10/10 checks in 9.463 seconds: real OpenCV measurement on 12/12 visible frames, native apply/undo/redo, timing invalidation/remap, save/reopen, processed paused frame and actual ProRes export. First/last pin centroids both measured (80.5, 64.0); output was 268,926 bytes. | Bind the accepted files/reports to the frozen regression and installed runtime. Wider shots, re-identification, lens/rolling-shutter estimation and sustained/concurrent throughput remain open. |
| Normal local generation | Two actual serial Euler takes at 480 × 272, 17 frames, 20 steps, 16 fps and CFG 6 passed 14/14 independent media/provenance checks each; all 17 frames were distinct and nonblank. The second take passed 14/14 native playback checks. The first passed 13/14: old timeline insertion floored its rounded container duration and lost the last frame. | Rerun actual native playback after the nearest-frame correction, which has focused Node/real-media verification. Mac synchronization was denied after MIDIA-AI's upgrade invalidated the execution grant. The prepared 33-frame acceptance has not run; longer takes, sustained operation and production quality remain open. |
| Whole-build regression | The current isolated Linux strict run passed 543 tests in 169.490 seconds with zero failures, errors, skips or expected failures, actual pinned optional workers and genuine Kodak RAW input. All 189 frozen operative files stayed unchanged; 48 JavaScript syntax checks also passed. | Local full regression is passed. GitHub CI remains pending; native Mac UI and replacement installation retain separate gates. The earlier 515-test result remains historical. |
| Installed application | The installer now builds version 0.9.1, preserves prior bundles/projects and embeds a copied-runtime/native-source hash manifest. An earlier 0.9 app installation is historical evidence. | Actual replacement is blocked by the expired MIDIA-AI execution grant. After access is restored, install the accepted source, preserve the prior bundle and projects, independently compare every installed runtime file with the frozen source, and record native launch/runtime availability. |
| Repository/release records | The capability ledger and this register describe the new source. Manifest generation/verification, current verification documentation and draft-PR alignment are release work in progress. | Finalize the source-integrity manifest without invented hashes, retain gate receipts, update draft PR #162 to the actual source/release scope, and record publication/CI status separately from installation. |

An ordinary application quit now checks for active durable jobs and requires an explicit choice before cancelling them. New-job admission closes atomically, and the server records the exit reason and affected jobs. These changes improve preservation and diagnosis; they do not retrospectively establish who or what initiated the earlier generation termination. Sources: [native lifecycle](macos/StudioApp.swift), [server](server.py), [shutdown regression](test_shutdown.py).

The current native-work blocker is an actual connector authorization change: MIDIA-AI upgraded from 0.7.2 to 0.8.0 and returned `COMMANDER_AUTHORITY_EXPIRED_OR_CHANGED` on the next synchronization attempt. A successor runtime context exists, but it does not carry a command-execution grant. The denied sync did not install the last local correction. This blocks the corrected Mac playback rerun, the planned 33-frame take and replacement installation; it does not prevent local regression, source review or repository verification. Those unexecuted native actions remain pending rather than being inferred from source or local tests.

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

One native playback passed and the other exposed final-frame loss when adding a rounded-duration source to the timeline. The local nearest-frame correction and the exact-timing verifier passed 18 focused Node/real-media checks; corrected Mac playback remains blocked, so normal-workflow acceptance is still incomplete. The native harness binds the current job ID so an earlier completed job cannot satisfy a fresh run. Its new explicit `--frames 33` option uses the real length input after checking the normal 17-frame defaults, retains 480 × 272, 20 steps, 16 fps and CFG 6, and grants a bounded 2,400 seconds per take. This longer case has not executed. Sources: [managed engine](managed_generation.py), [native inference harness](test_generation_inference_macos.py), [output verifier](macos/verify_generated_take.py), [real MP4 timing regression](test_generated_take_timing.py).

## 5. Frozen-source verification and release alignment

The earlier **515 tests in 153.974 seconds with zero failures/skips** belong to the earlier frozen source recorded in [verification 0.9](VERIFICATION_0_9.md). Earlier 3D, editorial, roto, media, Metal, RAW, OTIO and reduced-Wan results retain their value at their actual scope. New code and new harnesses require their own executions.

The current local isolated Linux run passed **543 tests in 169.490 seconds**, with zero failures, errors, skips or expected failures. Report elapsed time was 169.725 seconds. Actual pinned NumPy, OpenCV, OCIO, rawpy/LibRaw, OpenEXR and official OpenTimelineIO dependencies executed, including the genuine Kodak RAW input. The 189 operative code/test files were unchanged across the run; all 48 JavaScript syntax checks passed separately. See the [full report](verification/0.9.1/full-actual-runtime-report.json), [frozen operative inventory](verification/0.9.1/frozen-operative-source.json) and [unchanged-source check](verification/0.9.1/frozen-operative-check.json). Report SHA-256 is `d436f9f736d0c4ba5d41bf5762de9e9039efccd99afc18e5577b2311eee821a8`; inventory SHA-256 is `5db8cdeef9c316c5809e8c219815c3e7454f448fe08c7a972c80a3662f976653`.

This closes local full regression, not native macOS acceptance or installation. GitHub CI remains pending. Final Mac synchronization, corrected playback, longer inference and replacement installation remain blocked by the connector authority change. Release alignment must:

1. Freeze the complete reviewed runtime, tests, native sources, dependency locks and documentation. Include all new files, not only files already listed in the old integrity manifest.
2. Generate a deterministic inventory from actual bytes, rejecting missing/extra runtime files and unsafe paths. Exclude the manifest from its own digest inventory and document any verification-record exclusion to avoid self-reference. Keep source identity and evidence identity separately reviewable.
3. Retain the passed full-suite receipt and finish the remaining native workflows against the corresponding frozen content. Record every skip/failure explicitly. A changed runtime or test after a gate requires affected verification and a new source identity.
4. Build/install that source while preserving existing project data and an independently verified prior-bundle archive. Compare the installed runtime inventory and native-source manifest against the accepted snapshot, then record actual app launch/runtime availability.
5. Update [verification 0.9.1](VERIFICATION_0_9_1.md), the capability/release records and [draft PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162) with the actual commit and results. Publication, CI, local installation and signing are separate states.

The original production checkout and the isolated development worktree have distinct state. Preserve the owner's modified files and existing projects; do not overwrite them merely to align a version. The separate issuance/compiler authority is also distinct from the Studio editor. Installing Studio does not generate missing production source takes or certify a finished film. The installer preserves external project storage and the optional runtimes, but it does not make external FFmpeg/Blender prerequisites self-contained or signed. The current signing-identity inspection found one Apple Development identity and no Developer ID Application identity; it does not establish a signed/notarized distribution. No named-provider credential was exported in the inspected MIDIA environment, which does not establish whether credentials exist in another keychain or account.

## 6. Hardware and scope of evidence

Current native `sysctl`/`sw_vers` reports identify Apple M3, 17,179,869,184 bytes of memory (16 GiB), and macOS 26.5.2 build 25F84. Actual tracking probing reports OpenCV 4.11.0 and NumPy 2.3.5. Runtime availability is distinct from a passed authoring workflow. MPS generation and bounded Metal rendering on this machine do not certify CUDA/OptiX/HIP/oneAPI execution, arbitrary checkpoints, long takes or production throughput. Those need suitable hardware and corresponding real-output evidence.

The audit covers focused investigation of 33 reference systems. It is not an exhaustive line-by-line review of entire upstream codebases or proprietary source. The 72 ledger groups do not map every upstream subfeature. Full completion requires the absent systems, remaining professional workflows and their actual acceptance, not a documentation status change. `parity_complete` remains `false`.

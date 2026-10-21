# CINEMATICUM 0.9 — what remains unfinished

Audit date: 21 October 2026. This report describes the current repository and the recorded native acceptance results. It distinguishes implemented tools with limits, absent systems, outstanding verification and release alignment. It does not modify project media, the authority repository or an existing production checkout.

**CINEMATICUM is not feature-complete against the combined applications in the requested comparison.** It has a working integrated editor and substantial native authoring/rendering functionality. Those working tools do not supply every system in Blender, Premiere, Resolve, Fusion, Nuke, After Effects, the other editors, the scientific libraries or the listed AI products.

The current [capability ledger](capabilities.json) explicitly records `parity_complete: false`. Its 67 entries have these states:

| Recorded state | Entries | Meaning in this audit |
| --- | ---: | --- |
| `implemented` | 1 | Implemented within its stated contract. |
| `implemented_bounded` | 41 | Working functionality with explicit data, operation or resource limits. |
| `partial` | 12 | A useful portion exists; major systems or behaviors remain absent. |
| `missing` | 12 | The named system has no implemented execution path. |
| `adapter_implemented_validation_pending` | 1 | Actual reduced generation and playback passed; normal-default quality and sustained operation remain unverified. |
| **Total** | **67** | These are capability groups, not equally sized features. |

No completion percentage follows from those counts. A bounded UV operation, an audio subsystem and an entire reconstruction pipeline have different scopes. Execution wording was reconciled during this audit; the conservative capability states remain unchanged.

## 1. Confirmed absent systems

These are implementation gaps, not hidden controls or tests that merely need to be rerun. Evidence links point to the implemented contracts and the corresponding capability assessment.

| Domain | Systems still absent | Repository evidence |
| --- | --- | --- |
| Editing and conform | Variable-speed ramps; optical-flow retiming; automatic multicamera waveform/timecode synchronization; multicamera audio-lock and multiangle monitoring; general offline/online conform; broad native project, XML, AAF and EDL interchange. | [Editorial operations](editorial.py), [OTIO interchange](interchange.py), [nested interchange](sequence_interchange.py), [editorial comparison](research/editorial.md). |
| Audio | A full bus/send/return/submix architecture; general surround/immersive output layouts; audio plugin hosting; full recording, restoration, loudness and DAW/session workflows. | [Timeline/audio renderer](engine.py), [live source routing](web/audio-routing.js), [capability ledger](capabilities.json). |
| Compositing and VFX | General nested node compositions; roto-layer hierarchy and paint/clone systems; deep/multiview/arbitrary-channel compositing; general 3D/particle compositing; general planar/affine/projective and optical-flow tracking; broad node/plugin compatibility and production cache scheduling. | [Compositor](compositor.py), [roto rendering](roto.py), [tracking](tracking.py), [compositing comparison](research/compositing-motion.md). |
| Motion graphics | A complete vector document/layer model, gradients and shape operators; general procedural/path effects; Lottie/general SVG interchange; text animators, expressions, layer parenting and general motion-design 3D. | [Compositor controls](web/compositor-ui.js), [compositor contracts](compositor.py), [capability ledger](capabilities.json). |
| Color and image pipeline | Floating-point scene-linear processing throughout the movie graph; whole-timeline OCIO/ACES configuration; HDR mastering/delivery and calibrated HDR monitoring; RAW video; general image-sequence/arbitrary-channel editing; the full colour-science spectral/colorimetry/appearance library. | [Movie renderer](engine.py), [compositor](compositor.py), [color stages](color_pipeline.py), [still imaging](imaging.py), [color comparison](research/color-science.md). |
| 3D authoring | Edge tools, sculpting and texture painting; a material/shader node graph; camera/light parenting and constraints; armatures, skinning and shape keys; geometry nodes and simulation systems; broad editable scene interchange. | [Scene schema and renderer](scene.py), [modeling operations](scene_modeling.py), [mesh import](spatial_import.py), [spatial comparison](research/spatial.md). |
| Physical rendering | Mitsuba spectral/polarized/differentiable rendering and inverse optimization; a pbrt scene/backend implementation, compound-lens transport and general participating-medium authoring; Gaffer-style lazy scene/path/set/context processing, variants and distributed dispatch. | [Scene renderer](scene.py), [physical-rendering comparison](research/physical-rendering.md), [capability ledger](capabilities.json). |
| Camera and optics | An interactive vanishing-line/photo calibration solver; automatic camera/lens calibration; broad distorted/fisheye/rational/anamorphic camera models; Lensfun profile lookup/conversion and chromatic/vignetting correction; rolling-shutter estimation; Optiland/ray-optics optical assemblies, glass catalogs, optimization and aberration/PSF/MTF analysis. | [Camera import/math](camera_io.py), [lens graph contract](compositor.py), [camera/optics comparison](research/camera-optics.md). |
| Reconstruction | Source-image feature extraction/matching, registration, structure from motion, bundle adjustment, dense depth/fusion, surface reconstruction and texturing; actual AliceVision/Meshroom worker/graph execution. | [Solved-camera import](camera_io.py), [capability ledger](capabilities.json), [spatial comparison](research/spatial.md). |
| Neural tools | SAM 2 segmentation/correction/object memory; TAPIR/TAPNext inference and learned occlusion/re-identification; CameraCtrl inference and general faithful camera conditioning; DiffusionLight inference and HDR environment generation. | [Classical tracking](tracking.py), [managed generation](managed_generation.py), [AI/motion comparison](research/ai-motion.md), [capability ledger](capabilities.json). |
| Commercial AI products | Authenticated native integrations and the corresponding product workflows for Runway, Krea, OpenArt, Magnific, Artlist, Firefly, Flow, Luma, Kling, Pika, FLORA and Weave. Generic ComfyUI execution does not establish these products' features, accounts, credits or proprietary models. | [Generation adapter](adapters.py), [managed generation](managed_generation.py), [capability ledger](capabilities.json). |
| Plugins and scripting | OFX/OpenFX, VST/Audio Unit and general third-party node/renderer hosting; an unrestricted expressions or scripting system. | [Defined compositor nodes](compositor.py), [typed server actions](server.py), [capability ledger](capabilities.json). |
| Production scale | A sustained decoded/GPU realtime media cache; shared collaborative project databases; distributed rendering; continuation of an interrupted render from its last completed work; broad broadcast/cinema delivery systems. | [Frame preview](frame_preview.py), [job lifecycle](server.py), [delivery profiles](engine.py), [capability audit](CAPABILITY_AUDIT.md). |

The remaining work is not limited to installing these third-party programs or opening their windows. Each missing authoring system needs a CINEMATICUM data model, usable controls, execution, persistence, undo/recovery and independent output verification.

## 2. Working implementations that remain bounded or partial

The following functionality is real. Its limits explain why it cannot be counted as complete parity with a larger application.

### Editing, sequences, media and interchange

The editor implements rational timing; multitrack picture/sound; trim, split, ripple, slip, slide and roll; constant-speed forward/reverse; editable nested sequences; manual multicamera cuts; plain captions; preview proxies and exact-original relink.

The sequence library is bounded to 64 sequences with a shared frame rate/canvas, nesting depth eight, 4,096 stored authored clips and 1,024 expanded clips, text plates or sequence instances. Multicamera cutting uses an explicitly chosen common event and camera-follow audio. It is not automatic synchronization or a multiangle monitor. Plain SRT/WebVTT is supported; styled/timed markup, regions and general broadcast caption behavior are not. Sources: [editorial.py](editorial.py), [editorial controls](web/editorial-ui.js), [engine.py](engine.py).

Proxies preserve the original as the source for export. Relink verifies the exact original size and SHA-256; it is not alternate-take or heuristic path conform. Proxy creation has its own format, resolution and frame-count bounds. Sources: [media_management.py](media_management.py), [media controls](web/media-management-ui.js).

OTIO supports a defined cuts/gaps/Stack/Track subset with nested source ranges and a shared clock. Retimed/reversed export, transitions, same-track overlaps, trimmed Tracks/top-level Stacks and disabled nested items are rejected. CINEMATICUM metadata preserves effects, captions and mixer state only when content identities and public structure agree; those properties do not become portable generic OTIO effects. Sources: [interchange.py](interchange.py), [sequence_interchange.py](sequence_interchange.py).

### Live playback and exact image review

Live source playback draws pose, opacity and a limited basic grade/blur approximation. It does not evaluate the complete compositor, LUT, lens and roto graph in realtime. Exact graph review uses the rendered authoring frame or encoded preview. Sources: [sequence-playback.js](web/sequence-playback.js), [frame_preview.py](frame_preview.py).

The exact authoring-frame worker uses a 45-second timeout and a bounded still cache. This is a useful review path, not a production decoded/GPU playback cache. Sustained large-project performance remains separate from correctness on bounded test fixtures. Sources: [frame_preview.py](frame_preview.py), [server.py](server.py).

### Audio

Decoded waveforms, source stream/channel selection, track/clip gain, balance, fades, constant-speed retiming and stereo export exist. Any valid selected input channel pair can map to output L/R. Output remains stereo, and interactive reverse sound remains muted. Sources: [waveform.py](waveform.py), [engine.py](engine.py), [audio-routing.js](web/audio-routing.js).

The new native routing identifies container audio tracks and mutes unsupported routes instead of silently substituting an unidentified stream. Some actual source-selection runs passed, but a fresh second-stream run reproduced silence despite the correct track identity and an active graph. This is a confirmed intermittent native playback defect; successful isolated runs do not establish reliable routing. The defect and final mixer/lifecycle acceptance are tracked below.

### Compositor, motion and tracking

The image graph supports a primary source plus eight additional owned media sources, at most 32 nodes and a defined set of blend/effect operations. Optional alpha-effect masks exist only on the supported grade, curves, blur, sharpen, key and lens nodes. Curves, sharpen amount and lens calibration are not general animated properties. Source: [compositor.py](compositor.py).

Editable cubic Bézier masks have 2–32 anchors, independent incoming/outgoing handles, per-point feather and up to 64 fixed-topology path keys. Rendering produces measured 16-bit mask coverage, but that does not make the complete movie graph 16-bit or floating point. Timing tangents are bounded monotone cubic interpolation, not arbitrary overshooting curves. SVG exchange supports one closed path from a defined command subset, not a general SVG document. Sources: [roto.py](roto.py), [roto_assets.py](roto_assets.py), [compositor-ui.js](web/compositor-ui.js).

Measured tracking is classical translation tracking with explicit frame/coordinate/visibility bounds. Translation stabilization and a mask following that track are implemented; they are not semantic segmentation, planar solving or neural tracking. Source: [tracking.py](tracking.py).

### Color, RAW, EXR and HDR stills

Declared input transforms and combined 1D-shaper/3D LUT stages are implemented. The final movie/compositor graph still reduces images to 8-bit `rgba`/`rgb24`. A 10-bit ProRes output profile does not restore precision lost earlier. Sources: [color_pipeline.py](color_pipeline.py), [compositor.py](compositor.py), [engine.py](engine.py).

Separate still-imaging paths implement builtin-config CPU OCIO transforms, RAW development through rawpy/LibRaw, floating-point EXR and a known-response merge of 2–16 aligned exposure-timed stills. They are not movie-wide OCIO, RAW video, unrestricted EXR/deep/multipart channels or automatic HDR alignment/deghosting. The genuine camera RAW integration now passed using an actual Kodak DC50 fixture; that specific proof does not establish broad camera-vendor or RAW-video parity. Sources: [imaging.py](imaging.py), [image_worker.py](image_worker.py), [imaging tests](test_imaging.py).

### 3D, UVs, materials and camera

Native scene controls implement primitives/imported polygon meshes, object parenting, pose keys, physical camera/light/material settings, editable cages, UV tools and real headless Cycles output with a retained `.blend`. The authored scene is bounded to 96 objects, 16 lights, 7,200 frames and declared geometry/render budgets. Source: [scene.py](scene.py).

The modifier stack has eight supported types: Mirror, Bevel, Subdivision, Solidify, Array, Decimate, Smooth and Simple Deform. Vertex movement preserves UV corners; topology-changing operations explicitly clear imported UV data where it cannot be preserved correctly. Object parents keep local transforms; camera/light parenting, constraints and automatic keep-world parenting are not included. Sources: [scene_modeling.py](scene_modeling.py), [modeling_blender.py](modeling_blender.py), [scene_hierarchy.py](scene_hierarchy.py).

UV authoring includes projection, actual smart unwrap, selected-face seam separation, point transforms and connected-island grid packing. Grid packing does not optimize texel density or general packing. Imported OBJ UVs/material values are retained, but image textures and a general shader graph are not authored by this path. Rendering an existing `.blend` does not convert every Blender system into editable native CINEMATICUM data. Sources: [scene_modeling.py](scene_modeling.py), [spatial_import.py](spatial_import.py), [3D controls](web/scene-editor.js).

fSpy and selected COLMAP files supply already solved cameras. COLMAP import explicitly accepts distortion-free `PINHOLE`/`SIMPLE_PINHOLE`, not general reconstruction or distorted camera models. Brown footage warping is a static five-coefficient operation with a contraction bound, at most two lens nodes and a 2,073,600-pixel canvas limit. It is not Lensfun profile conversion or an optics-design solver. Sources: [camera_io.py](camera_io.py), [compositor.py](compositor.py), [lens_assets.py](lens_assets.py).

### Generation, automation and production

The managed generation runtime has now executed actual Wan text-to-video inference. Its pinned setup is for Apple Silicon macOS 14 or newer and Python 3.13. Managed controls are bounded to the declared 480p canvas, 9–81 frames and 4–50 steps. The owned engine disables custom nodes. External configured API workflows remain a separate adapter path; neither route establishes the feature set of every listed AI product. Sources: [managed_generation.py](managed_generation.py), [generation-runtime-lock.json](generation-runtime-lock.json), [adapters.py](adapters.py).

Automation uses typed operations, owned jobs, snapshots and receipts. Bulk editorial actions are explicitly grade, volume, sequence and trim. Queued/running jobs recovered after process termination become interrupted and require a new render; resumable model downloads do not imply resumable movie rendering. Source: [server.py](server.py).

The shot-plan workflow binds actual selected source media and assembles a reviewed cut. Missing media prevents assembly. It does not create all missing shots or certify a finished film. The read-only check of the originally requested production checkout found **18 planned shots, zero files/media in its source-shot directory and zero files/media in its film-output directory**. Completion of that production handoff requires all 18 selected source takes, an actual assembled cut, sound work and media/film QC. This finding is specific to those production folders; it does not claim that no media exists elsewhere or that the separate authority/compiler artifact is missing. Source: [production.py](production.py).

Project archives retain owned authoring/media dependencies with a 64 GiB/10,000-file bound; external engines, plugins and model weights are prerequisites, not embedded archive contents. Source: [project_archive.py](project_archive.py).

## 3. Verification: established results and open gates

Implementation, an available harness and a passing actual execution are different evidence levels. Synthetic fixtures are clearly identified as verification inputs and are not production footage.

### Established results

| Verified operation | Actual recorded result | Limit of the result |
| --- | --- | --- |
| Native 3D backend and controls | 19 backend checks and eight native control stages passed. | Covers the tested hierarchy, modeling, UV and device behaviors, not unrestricted Blender parity. |
| Native editorial, roto and media controls | Four editorial stages, 26 roto checks and four media-management stages passed. | Covers the stated test contracts; manual multicam and the other bounds still apply. |
| Proxy/export identity | Independently decoded exports retained 12 picture frames and 24,000 stereo sample frames byte-for-byte when preview proxy settings changed. | This establishes the tested original-source export path, not arbitrary conform. |
| Metal rendering | A normal application render completed in 82.430497 seconds; independent verification passed 18/18 checks in 6.694 seconds, including decoded picture and reopened retained source. | Actual Metal output is proven for the tested machine/job. Other GPU backends require their own hardware executions. The earlier 15.522-second timeout is historical. |
| Managed runtime installation/startup | Verified source, 71 wheels and three weights installed; actual MPS startup, encoder and required graph nodes passed. | Installation/startup alone is not output or quality acceptance. |
| Reduced real Wan inference and output | 192 × 128, nine frames, four steps: completed in 44.410 seconds and admitted a nine-frame, 16 fps H.264 asset. Independent decoding passed 14/14 checks; actual native Add → Play → Save/pixel/timeline acceptance passed 14/14 checks in 1.393 seconds. | The reduced take's inference, decoded media and native playback are proven. Normal-default quality and sustained operation remain separate open gates. |
| Genuine RAW and official OTIO integrations | RAW development: one test in 1.534 seconds, OK. Official OTIO reader/writer: one test in 0.463 seconds, OK. Both executed with zero skips. | Real Kodak DC50 development and the supported OTIO exchange were exercised; broader vendor/format semantics remain outside their scope. |
| Full Python suite on frozen current source | **515 tests in 153.974 seconds, OK; zero failures and zero skips.** | Includes the genuine RAW and official OTIO gates. Separate native acceptance remains open; this result does not override the reproduced native audio failure. |
| Candidate installation | A genuine 0.9 candidate was installed and normally launched; 53 files matched that candidate's expected runtime contents and four existing project JSON identities were preserved. | Current source has subsequently changed. Final alignment is still open. |

Detailed reproducible evidence and entrypoints are in [VERIFICATION_0_9.md](VERIFICATION_0_9.md), [Metal output verification](macos/verify_metal_result.py), [retained-source verification](macos/verify_metal_blend.py) and [generated-take verification](macos/verify_generated_take.py).

### Native audio — intermittent defect confirmed; resolution pending

Actual WAV, first MOV and a second MOV source-selection run passed. The successful second-stream run measured 32,768 contiguous samples, the expected selected tones/channel swap and zero steady-state seeks.

A fresh run of the current source then failed the second-stream baseline: **32,768 raw and output samples were zero**, despite correct enabled-track identity, a ready graph, advancing playback, no steady-state seeks and a passing independent audio calibration. Therefore source selection is **intermittently functional and not yet reliable**. This is a recurrent native defect, not merely an unrun gain/pan test.

Gain/pan plus restart/lifecycle acceptance also remains open. A subsequent exact-position activation seek completed its native seek event but still yielded zero PCM; that unproven change was removed. No speculative activation workaround remains in the frozen source. Correct saved metadata and correct exported audio do not close these live playback gates. Evidence: [native audio harness](test_audio_routing_macos.py), [live routing](web/audio-routing.js), [sequence playback](web/sequence-playback.js).

### Generated take — reduced output passed; normal-default operation pending

The reduced real take has completed both independent output and native playback acceptance: **14/14 decoded-media checks and 14/14 native Add → Play → Save/pixel/saved-timeline checks passed**. All nine actual frames matched their corresponding independently decoded frames; mean absolute pixel error was approximately 0.233–0.306, below the declared threshold of 8. The verified asset is nine-frame, 16 fps H.264 at 192 × 128. No export or substitute generation replaced the tested take. This closes the reduced-take gate; the verifier's fixture self-tests are not being counted as actual model output.

The normal-default 480 × 272, 17-frame, 20-step run was cancelled by normal application shutdown after about 21 seconds. The cause of that quit remains unresolved. It is not evidence of a model error and does not establish a completed default run. Normal-default quality, longer runs and sustained-session reliability remain unverified. Evidence: [managed generation](managed_generation.py), [actual-output verifier](macos/verify_generated_take.py), [verification record](VERIFICATION_0_9.md).

### Other open verification

- After resolving the native audio defect, rerun the affected regression and source/mixer/lifecycle gates against the matching installed bundle. The current frozen-source full suite has passed; it does not certify a future fix.
- Verify CUDA, OptiX, HIP and oneAPI on corresponding actual hardware before claiming those device executions. Device enumeration/selection code is not a substitute for output.
- Establish sustained large-project/media performance and longer generation/render sessions; the bounded fixture checks do not establish professional scale or every delivery target.

The two optional skips in the historical 509-test run are documented in [VERIFICATION_0_9.md](VERIFICATION_0_9.md). Both passed separately and again in the current 515-test full run, which had zero skips. No skipped or unavailable execution is counted as passed.

## 4. Release and source alignment remain unfinished

The following are concrete integration tasks, separate from the missing feature systems:

1. **Align current source with the installed bundle.** The fresh audit found 50 of 53 runtime files matching current source. `web/app.js`, `web/audio-routing.js` and `web/sequence-playback.js` differ. Rebuild/install the final source, verify its contents and rerun the relevant native gates before calling the current fixes shipped.
2. **Reconcile the intended original production checkout.** It still lacks the Studio server/runtime and contains the owner's modified Makefile. Preserve that Makefile and the existing main branch while integrating the reviewed 0.9 work. The isolated worktree and installed candidate do not, by themselves, update that checkout. The separate authority repository is not expected to contain the editor.
3. **Complete source publication and CI.** The remote draft still contains 0.8. The current 0.9 source is unpublished and has no 0.9 CI result. `source-integrity.json` still identifies 0.8.0; its explicit source manifest must be regenerated for a reviewed 0.9 publication. Publication, current-source CI and installation are distinct states.
4. **Complete distribution packaging.** The native shell locates an external Python runtime; FFmpeg, Blender and optional imaging/model runtimes remain prerequisites. The installer explicitly reports no signing performed. A self-contained, signed/notarized distribution and its verification are unfinished.
5. **Retain project preservation and rollback guarantees.** The candidate preserved the existing project JSON identities and archived the previous bundle. The final installation must preserve those guarantees as well; it must not overwrite owner changes merely to align versions.

Sources: [native app lifecycle](macos/StudioApp.swift), [installer](install_macos.py), [verification record](VERIFICATION_0_9.md). The app intentionally saves edits and stops its owned jobs on quit; unexplained termination during the default generation run still needs its own diagnosis.

## 5. Documentation reconciled during this audit

The source documentation initially contradicted newer execution evidence. The following corrections have now been made in the current source. They do not publish a release, fix the native audio defect or establish any of the missing capabilities.

| Document | Earlier stale or incomplete statement | Correction made |
| --- | --- | --- |
| [Root README](../../README.md), [Studio README](README.md), [capability audit](CAPABILITY_AUDIT.md), [ledger](capabilities.json) | Metal picture output is still described as unverified after a short timeout. | Record the completed normal app render and independent 18/18 acceptance. Preserve the old timeout only as history. |
| [Root README](../../README.md), [Studio README](README.md), [capability audit](CAPABILITY_AUDIT.md), [ledger](capabilities.json) | Managed generation is described only as an adapter/pending runtime, or without the actual successful inference. | Record completed installation, startup, reduced real Wan inference and independent actual-output/native playback acceptance; keep default-run quality/reliability open. Add the managed implementation to ledger evidence. |
| [Studio README](README.md), [capability audit](CAPABILITY_AUDIT.md), [ledger](capabilities.json) | Source playback may use its default audio stream. | Describe explicit container-track selection and fail-muted unsupported routes; incorporate the final native mixer/lifecycle outcome when available. |
| [Verification 0.9](VERIFICATION_0_9.md) | The normal-default generation run is described as underway. | Record cancellation by normal app shutdown, unresolved quit cause and absent completed default-run acceptance. |
| [Verification 0.9](VERIFICATION_0_9.md) | Audio-pending language predates the successful source-selection runs and the subsequent reproduced second-stream silence. | Record both outcomes: some baselines passed, but current second-stream playback remains intermittent and requires a defect fix plus repeated source/mixer/lifecycle acceptance. |
| [Verification 0.9](VERIFICATION_0_9.md) | Reduced-take decoding/native playback is described as pending. | Record the independent 14/14 media and 14/14 native actual-output passes, while retaining the normal-default/sustained-operation gap. |
| [Capability audit](CAPABILITY_AUDIT.md) | No installed 0.9 application is asserted. | Reconcile this with the actual candidate installation while preserving the current-source mismatch and unpublished-release distinction. |
| [Root README](../../README.md) | Legacy v1.0/v1.1 compiler boundaries state no external media/network/manual selection alongside the current Studio product. | Clearly identify those sections as historical/separate compiler contracts so they do not misdescribe current media import and managed model setup. |

The verification report limits its installation statement to the recorded candidate and distinguishes source, installation and publication. Reconcile these records with any later executed results before a release; do not treat this documentation cleanup as an implementation pass.

## 6. Limit of the claimed exhaustive comparison

The [capability audit](CAPABILITY_AUDIT.md) records focused investigation of 33 reference systems. The research files identify inspected source, APIs and retrieval limits. Proprietary applications were assessed through public contracts and documentation; their entire internal source was not reverse engineered.

There is not yet an exhaustive, version-pinned, app-by-app feature inventory mapping every requested upstream feature to a CINEMATICUM control, persisted representation, execution path and acceptance test. The 67 ledger entries are broad capability groups. They cannot establish that every subfeature in every referenced application has been inspected or accounted for.

Accordingly, this document gives the concrete major gaps supported by the repository and current execution evidence. It does not claim an exact count of every remaining upstream feature, complete source equivalence, complete production readiness or complete parity. `parity_complete` must remain `false` until those missing systems and the corresponding acceptance criteria are actually satisfied.

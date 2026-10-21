# CINEMATICUM 0.5 — engineering comparison and implementation audit

**Status: a substantive upgrade to CINEMATICUM's own editor; full parity with the listed applications remains unimplemented.** This audit records inspected source/interfaces, concrete changes, reproducible acceptance and unresolved requirements. It does not assign a misleading completion percentage or present an installed external program as an implemented CINEMATICUM feature.

The user requirement is one audiovisual authoring application with one project, timeline, media inventory, undo history and output pipeline. CINEMATICUM's controls author the data. FFmpeg and Blender are headless processing engines; no third-party editor interface is opened or embedded. A backend integration counts only for the operations actually exposed, preserved and executed.

## Research scope and evidence

The source review follows data through project storage, timing, animation, graph evaluation, geometry, model inputs and job outputs. It is a focused source-level investigation of the listed subsystems, not a line-by-line audit of entire upstream repositories. Public proprietary interfaces were inspected; proprietary application source was not available. Cinelerra's accessible GitHub source is a dated historical mirror and is explicitly separated from its current manual.

| Reference system | Evidence and significant comparison | Implemented related capability in CINEMATICUM 0.5 | Material gaps |
| --- | --- | --- | --- |
| Shotcut | MLT annotations, resource traversal and numerator/denominator metadata | Shared media/timeline model, track controls, real FFmpeg export, rational clock | Full MLT project/filter compatibility, broad transitions, proxy conform and hardware pipeline |
| Kdenlive | Project/sequence tractors, profile clock, UI/render synchronization | Persistent own timeline, retime/reverse, clip/track state, exact cut/audio boundaries | Multiple/nested sequences, multicam, full trim modes, proxies, subtitles and plugin catalogue |
| Cinelerra-GG | Current project/EDL manual; historical XML object/session/track/nested-EDL reader | Multitrack audio/picture, motion, mix state and bounded cut exchange | Native XML project support, nested EDLs, advanced audio/plugin systems, broader capture/delivery |
| Premiere | Public FrameRate/TickTime and interchange contracts | Exact rational clock, source/timeline separation, cut OTIO import/export with explicit losses | Premiere project/XML/AAF translation, multicam, collaboration, advanced conform and editing |
| DaVinci Resolve | Public Edit workflow, timeline curves and multicam | Editable cuts, frame-based animation, SDR scopes/grades and encoded output | Resolve color management, ACES/HDR, RAW controls, Fairlight, multicam, collaborative database |
| After Effects | Public property/keyframe/mask semantics | Independent property channels, animated masks, clip transforms and raster titles | Expressions, text animators, precomps, parenting, effect ecosystem, motion-design 3D |
| Fusion | Public image graph, mask ports, spline and modifier behavior | Source branches, ordered merges, animated alpha, grade/key/blur/mask nodes | Multi-source shot graph, general masks/modifiers, custom tangents, 3D/particle graph, production caching |
| Nuke | Public Roto/AnimCTransform API | Independent animated mask/transform channels and preserved trim domains | Deep/multiview/arbitrary channels, advanced roto/paint, 3D/camera pipeline, node/plugin ecosystem |
| Natron | Pinned Curve and Bezier source | Time-dependent parameter evaluation, polygon geometry/transform channels | Bezier feather points/hierarchy, roto paint, OFX host, full multi-input graph and cache scheduler |
| Friction | Pinned vector/path/animation source and public docs | Animated bounded polygon paths, easing and own editing gestures | Full vector scene graph, editable Bezier handles, procedural/path effects and vector exports |
| Glaxnimate | Pinned document/animation source and public model docs | Independent shape-point animation with stable topology | Full vector drawing, gradients, shape operators, Lottie/SVG interchange and motion design |
| Blender | Pinned OBJ parser/mesh/material construction; installed headless engine | Own primitive/mesh viewport, transforms, materials, object/camera/light animation, actual Cycles output and retained `.blend` | Vertex/edge/face editing, UV authoring/textures, rigs, sculpting, modifiers, simulations and general scene interchange |
| COLMAP | Pinned model reader and incremental reconstruction pipeline | Source/camera conventions documented; imported mesh can be used after reconstruction elsewhere | No SfM, bundle adjustment, dense reconstruction or solved-camera import executed here |
| AliceVision | Pinned sparse/depth/meshing programs | Reconstruction stages and hardware/build boundaries mapped | No AliceVision worker, image matching, depth fusion, meshing or texturing pipeline |
| Meshroom | Pinned graph/node execution and plugin architecture | Owned jobs and shared scene asset admission | No Meshroom graph compatibility or full photogrammetry workflow |
| SAM 2 | Video predictor initialization/prompt-correction source | Explicit distinction between geometric masks and segmentation | No neural segmentation model, object memory, corrections propagation or temporal mask clip |
| TAPIR | Official model/coordinate documentation | Validated source-space point-track interchange and actual classical measurement | No TAPIR inference/checkpoint integration, learned occlusion/re-identification |
| TAPNext | Recurrent forward/prediction-head source | Explicit frame/coordinate/visibility contract | No TAPNext inference state, checkpoint execution or learned tracker adapter |
| ComfyUI | Prompt/node/model/history/cancellation source and official API | Imported API graphs, chosen input binding, installed-node/model preflight, one-ID job tracking, output probe/admission and scoped cancellation | Configured service/models absent on the checked Mac; no actual model-generation proof or paid-provider integration |
| CameraCtrl | Camera-matrix/ray construction and pose injection source | Matrix/intrinsic/convention requirements documented | No CameraCtrl inference or faithful general camera-condition export |

Detailed source files, hashes, APIs and reasoning are in [editorial](research/editorial.md), [compositing and motion](research/compositing-motion.md), [spatial systems](research/spatial.md), and [AI and measured motion](research/ai-motion.md). Those documents distinguish immutable commits from individual Git blob hashes and describe retrieval limitations. The machine-readable [capability ledger](capabilities.json) uses the same conservative states.

## Concrete changes in this build

### 1. Exact time and audio boundaries

`timebase.py` stores a reduced integer ratio and derives the convenience FPS number. The renderer carries the ratio through source conform, timestamp units, canvas generation, encoding and Blender image sequences. Timeline positions are integer frames; source in-points may be fractional project frames. All 48 kHz audio placements use absolute sample boundaries, so successive 29.97/59.94 cuts do not accumulate independently rounded sample errors.

This exposed and fixed two export defects: a redundant output picture limit truncated the limiter's audio tail, and MOV's previous movie timescale rounded audio edit duration too coarsely. Tests examine packet timestamps, decoded pictures and PCM, including reverse, fractional trims, held/eased gain and many cuts. The UI labels fractional-rate timecode NDF; drop-frame display has not been implemented.

Decoded split comparisons also exposed timestamp truncation changing half-frame selection after a fractional source split. A bounded frame-aligned conform clock and explicit retimed timestamp rounding preserve the selected pictures across cuts. Permanent regression coverage compares every decoded frame in 48 combinations of container timestamps, rate, speed and direction, each split at three positions. The paused-frame cache version changes with this correction.

### 2. Animated image processing and shape geometry

Compositor nodes now store separate animation channels. Grade, blur, chroma tolerance/blend, merge opacity and mask placement/feather/geometry evaluate at the clip's preserved animation-domain frame. A property edit cannot silently key unrelated channels. Polygon path keys preserve topology; completed point gestures use one undo checkpoint. Parameters, paused PNGs and movie export evaluate the same saved data.

The graph remains one source per clip, with 32 nodes and bounded animation/working-image budgets. It does not acquire deep compositing, arbitrary channels, a general multi-source shot graph or a plugin host merely by exposing node controls. Static-only controls remain clearly static.

Extending a clip enlarges the editable animation domain to include the new visible interval without inserting keys or moving existing trajectories. Audio fade endpoints retain their independent original domain.

### 3. Measured tracking that changes the actual output

The user chooses a feature in an actual conformed source frame. FFmpeg correlation measures the chosen patch across the requested range. Result receipts include source identity, exact rate, source-time mapping, positions, visibility and confidence. Missing matches remain gaps. There is no synthetic trajectory or model-name substitution.

Applying stabilization creates an additive source-relative motion channel. Existing position, scale, rotation, opacity and sound remain authored separately. Tracking curves have no invented frame-zero anchor. A tracked ellipse receives its own mask channels and provenance. Source slips/reverse invalidate derived motion; trims/splits retain the curve domain; speed changes rescale keys. Independent output measurements verify stabilization. Affine/planar/optical-flow tracking and semantic segmentation remain missing.

### 4. Geometry that survives viewport, render and scene replay

The OBJ/MTL path parses selected text into bounded indexed meshes, triangulates concave simple faces, preserves UV/normal corners, partitions materials, and records actual source hashes. It never follows embedded filesystem references. The editor displays and ray-selects the actual geometry and appends an import as one undoable scene edit.

Headless Blender receives those same vertices/triangles/corner attributes and the authored transforms/materials/keys. The saved `.blend` can be reopened and inspected independently. Unsupported textures/transparency are reported. Mesh import is not topology editing, UV authoring, rigging or reconstruction.

### 5. Interchange with explicit fidelity and an undoable application step

The bounded OTIO exporter writes picture/audio tracks, gaps, cuts and actual media references. Companion audio tracks avoid ambiguous embedded-sound behavior. The importer resolves already-imported media using verified SHA-256 or explicit selections; it never follows arbitrary document URLs. The preview shows the candidate edit and warnings before one undoable replacement. It does not autosave.

Private authoring metadata can reconstruct an unchanged CINEMATICUM roundtrip. A digest of the public edit detects external changes; private effects are not allowed to override edited public timing. This is change detection, not authentication. Unsupported transitions, timewarps, nesting, overlaps and unrepresentable final gaps reject explicitly. Official OpenTimelineIO reader/writer tests and decoded picture/PCM tests check the supported subset. General AAF/XML/native-project conversion remains missing.

### 6. Job cancellation with a verified meaning

ComfyUI cancellation addresses only the actual accepted prompt ID. Where the new atomic job-cancel route is absent, the fallback deletes only that queued ID. It never sends a global interrupt. A successful dispatch and a confirmed terminal cancellation are reported separately. A legacy running prompt can continue remotely after local waiting stops; the job receipt states that outcome. This protocol upgrade is tested against HTTP fixtures, and is not claimed as a successful neural-generation run.

## Remaining work, ordered by required data model

| Required level | Missing implementation | Evidence needed before it can be called complete |
| --- | --- | --- |
| Editing/conform | Sequences, nesting, multicam/sync, source channel maps, rolling/slip/slide, proxies and relink | Roundtrips across sequence boundaries, source/timecode identity, proxy/original frame equivalence and editorial operation acceptance |
| Image pipeline | Scene-linear float processing, OCIO/ACES transforms, HDR, RAW, image sequences and EXR channels | Known color reference transforms, linear/alpha checks, high-dynamic-range values and export/monitoring validation |
| Compositing/VFX | Multi-source shot graph, Bezier roto/paint, planar/affine tracks, lens models, deep and arbitrary channels | Independent pixel/matte fixtures, coordinate and premultiplication checks, cache invalidation and bounded actual renders |
| Motion design | Vector document model, curves/tangents, text shaping/animators, parenting, expressions, reusable compositions | Editable data roundtrips, shape topology invariants, deterministic animation and actual vector/raster export |
| 3D | Mesh topology tools, UV/texture/material graphs, hierarchy/constraints, armatures, modifiers and simulation | Saved scene replay, topology/material/animation checks, simulation cache identity and actual rendered output |
| Reconstruction | Feature extraction/matching, camera models/poses, bundle adjustment, depth, surface and texture pipeline | Real multi-view input, registration/reprojection metrics, recovered geometry and pose-coordinate verification |
| Neural tools | SAM/TAPIR/TAPNext workers, checkpoint/config identity, correction state, memory budgeting and CameraCtrl conditioning | Actual model output on declared hardware, correct visibility/mask/camera conversions, reproducible identity and cancellation |
| Audio/delivery | Bus routing, channel layouts, plugin hosting, loudness, restoration, captions and broader delivery profiles | Decoded channel/sample/loudness checks, session roundtrips and target-profile acceptance |
| Production scale | Realtime decoded/GPU cache, background rendering, shared projects, crash recovery beyond current atomic saves, deployment packaging | Large real-media benchmarks, concurrent edit/conflict tests, interrupted-job recovery and signed distribution verification |

These are engineering requirements, not hidden buttons or implied installed capabilities. The previous provider list—Runway, Krea, OpenArt, Magnific, Artlist, Firefly, Flow, Luma, Kling, Pika, FLORA and Weave—also remains an external-product comparison requirement. This build adds no authenticated provider SDK, account, credits or licensed proprietary model. Generic ComfyUI execution cannot honestly stand in for them.

## Verification boundaries

The Python suite checks decoded media and real local HTTP behavior. Native WK acceptance runs operate shipped controls in disposable projects, then inspect saved data and exported media independently. Blender replay opens the actual retained `.blend`; it is stronger evidence than inspecting a generated Python recipe alone. Synthetic fixtures are clearly named ENGINE TEST, never inserted into the user's film or authority objects.

The checked Mac has FFmpeg and Blender, but the configured ComfyUI endpoint was unavailable. Native app updates preserve existing projects and the previous application bundle. Source publication stays on the existing draft PR; the owner checkout, source footage, current case and issuance records are not rewritten by these upgrades. Exact verification results are recorded separately after execution; a test file's presence alone is not a passing result.

# CINEMATICUM 0.7 — engineering comparison and implementation audit

**Status: a substantive upgrade to CINEMATICUM's own editor; full parity with the listed applications remains unimplemented.** This audit records inspected source/interfaces, concrete changes, reproducible acceptance and unresolved requirements. It does not assign a misleading completion percentage or present an installed external program as an implemented CINEMATICUM feature.

The user requirement is one audiovisual authoring application with one project, timeline, media inventory, undo history and output pipeline. CINEMATICUM's controls author the data. FFmpeg and Blender are headless processing engines; no third-party editor interface is opened or embedded. A backend integration counts only for the operations actually exposed, preserved and executed.

## Research scope and evidence

The comparison now covers 33 distinct reference systems from the technical list. The source review follows data through project storage, timing, animation, graph evaluation, geometry, model inputs and job outputs. It is a focused source-level investigation of the listed subsystems, not a line-by-line audit of entire upstream repositories. Public proprietary interfaces were inspected; proprietary application source was not available. Cinelerra's accessible GitHub source is a dated historical mirror and is explicitly separated from its current manual.

| Reference system | Evidence and significant comparison | Implemented related capability in CINEMATICUM 0.7 | Material gaps |
| --- | --- | --- | --- |
| Shotcut | MLT annotations, resource traversal and numerator/denominator metadata | Shared media/timeline model, track controls, real FFmpeg export, rational clock | Full MLT project/filter compatibility, broad transitions, proxy conform and hardware pipeline |
| Kdenlive | Project/sequence tractors, profile clock, UI/render synchronization | Own timeline, retime/reverse, slip/slide/outgoing-cut roll, track state and exact cut/audio boundaries | Multiple/nested sequences, multicam, broader contextual trimming, proxies, subtitles and plugin catalogue |
| Cinelerra-GG | Current project/EDL manual; historical XML object/session/track/nested-EDL reader | Multitrack audio/picture, motion, mix state and bounded cut exchange | Native XML project support, nested EDLs, advanced audio/plugin systems, broader capture/delivery |
| Premiere | Public FrameRate/TickTime and interchange contracts | Exact rational clock, source/timeline separation, cut OTIO import/export with explicit losses | Premiere project/XML/AAF translation, multicam, collaboration, advanced conform and editing |
| DaVinci Resolve | Public Edit workflow, timeline curves and multicam | Own trim modes, SDR scopes/grades, actual OCIO still views, RAW still development and encoded movies | Whole-timeline color management, HDR mastering, RAW video, Fairlight, multicam and collaborative database |
| After Effects | Public property/keyframe/mask semantics | Independent property channels, animated masks, clip transforms and raster titles | Expressions, text animators, precomps, parenting, effect ecosystem, motion-design 3D |
| Fusion | Public image graph, mask ports, spline and modifier behavior | Up to eight additional project-media sources, ordered merges, animated alpha, grade/key/blur/mask and calibrated lens nodes | General masks/modifiers, custom tangents, nested compositions, 3D/particle graph and production caching |
| Nuke | Public Roto/AnimCTransform API | Independent animated mask/transform channels and preserved trim domains | Deep/multiview/arbitrary channels, advanced roto/paint, 3D/camera pipeline, node/plugin ecosystem |
| Natron | Pinned Curve and Bezier source | Independent animated parameters, polygon channels and bounded multi-source image graphs | Bezier feather points/hierarchy, roto paint, OFX hosting and general graph/cache scheduling |
| Friction | Pinned vector/path/animation source and public docs | Animated bounded polygon paths, easing and own editing gestures | Full vector scene graph, editable Bezier handles, procedural/path effects and vector exports |
| Glaxnimate | Pinned document/animation source and public model docs | Independent shape-point animation with stable topology | Full vector drawing, gradients, shape operators, Lottie/SVG interchange and motion design |
| Blender | Pinned OBJ parser/mesh/material construction; installed headless engine | Own vertex/face selection and topology edits, actual live Mirror/Bevel/Subdivision, physical scene controls, Cycles and retained editable `.blend` | Edge tools, UV/textures, shader graphs, hierarchy/constraints, rigs, sculpting, geometry nodes, simulations and broader scene interchange |
| COLMAP | Pinned model readers, pinhole/radial/OpenCV models and pose conventions | Data-only selected text-model camera import; roll, principal offsets and unequal focal lengths preserved | No feature extraction, SfM, bundle adjustment or dense reconstruction; camera import still rejects distorted COLMAP models |
| AliceVision | Pinned sparse/depth/meshing programs | Reconstruction stages and hardware/build boundaries mapped | No AliceVision worker, image matching, depth fusion, meshing or texturing pipeline |
| Meshroom | Pinned graph/node execution and plugin architecture | Owned jobs and shared scene asset admission | No Meshroom graph compatibility or full photogrammetry workflow |
| SAM 2 | Video predictor initialization/prompt-correction source | Explicit distinction between geometric masks and segmentation | No neural segmentation model, object memory, corrections propagation or temporal mask clip |
| TAPIR | Official model/coordinate documentation | Validated source-space point-track interchange and actual classical measurement | No TAPIR inference/checkpoint integration, learned occlusion/re-identification |
| TAPNext | Recurrent forward/prediction-head source | Explicit frame/coordinate/visibility contract | No TAPNext inference state, checkpoint execution or learned tracker adapter |
| ComfyUI | Prompt/node/model/history/cancellation source and official API | Imported API graphs, chosen input binding, installed-node/model preflight, one-ID job tracking, output probe/admission and scoped cancellation | Configured service/models absent on the checked Mac; no actual model-generation proof or paid-provider integration |
| CameraCtrl | Camera-matrix/ray construction and pose injection source | Matrix/intrinsic/convention requirements documented | No CameraCtrl inference or faithful general camera-condition export |
| Mitsuba 3 | Pinned sensor/integrator/BSDF architecture | Physical camera and material controls drive real Cycles rendering | No Mitsuba backend, spectral/polarized transport, differentiable rendering or inverse optimizer |
| pbrt-v4 | Pinned camera/integrator/material source and public book | Lens/sensor/aperture and actual path-control settings | No pbrt scene parser/backend, spectral transport, realistic compound lens or participating-medium authoring |
| Gaffer | Pinned node/plug/context, scene path/set and dispatch architecture | One saved project and owned render jobs | No lazy scene graph, procedural path/set processing, asset variants or distributed dispatch |
| Optiland | Pinned optical prescription, ray tracing, analysis and optimization code | Explicit sensor, focal length, aperture and focus controls | No lens-design model, glass catalogue, optical optimization, aberration/PSF/MTF tools |
| ray-optics | Pinned sequential/paraxial model and real-ray tracing source | Camera geometric parameters and validated projection math | No editable optical assembly, paraxial/aberration analysis or ray-fan/spot tools |
| OpenCV | Pinned calibration, projection and distortion implementation | Source-model reprojection checks and actual bounded five-term Brown footage warp with independent inverse/map tests | No general OpenCV worker, automatic calibration solve, fisheye/rational models or optical-flow/vision suite |
| fSpy | Pinned v1 binary container and camera transform/intrinsic serialization | Own file picker imports actual fSpy v1/JSON solved cameras into the own 3D scene | No interactive vanishing-line solver or photograph calibration UI |
| Lensfun | Pinned lens database/model/correction pipeline | Explicit Brown calibration drives an actual static image remap in the compositor | No Lensfun profile lookup/conversion, TCA/vignetting correction or broad lens-model support |
| colour-science | Pinned transfer functions, primaries/matrices and adaptation code | Explicit float transfer/gamut conversion and Bradford white adaptation | No full spectral/colorimetry/appearance library or colour runtime integration |
| OpenColorIO | Pinned config/processor/transform and Cube format behavior | Actual builtin-config OCIO CPU source/scene-linear/display-view still processing, plus owned Cube LUTs in the movie graph | No external config/context editing, movie-wide OCIO graph, GPU shader cache, HDR output or calibrated monitoring |
| LibRaw | Pinned decode/process pipeline | Preserved original camera RAW, actual rawpy/LibRaw unpack/demosaic, white balance/highlight controls and float master | No RAW movie timeline, unrestricted decoder options or complete camera-vendor rendering parity |
| colour-hdri | Pinned radiometric calibration/merge/exposure processing | Known-response radiance merge of 2–16 explicitly timed aligned stills, with float EXR master | No response-curve fitting, alignment/deghosting, panorama/probe construction or colour-hdri runtime |
| DiffusionLight | Pinned diffusion/probe/exposure workflow | Model/input/output boundaries documented | No actual weights, inference, synthesized probes or HDR environment generation |

Detailed source files, hashes, APIs and reasoning are in [editorial](research/editorial.md), [compositing and motion](research/compositing-motion.md), [spatial systems](research/spatial.md), and [AI and measured motion](research/ai-motion.md). New investigations are recorded in [camera and optics](research/camera-optics.md), [color science](research/color-science.md), and [physical rendering](research/physical-rendering.md), plus [editable topology and live modifiers](research/mesh-modeling.md). Those documents distinguish immutable commits from individual Git blob hashes and describe retrieval limitations. The machine-readable [capability ledger](capabilities.json) uses the same conservative states.

## Concrete changes in this build

### 1. Exact time and audio boundaries

`timebase.py` stores a reduced integer ratio and derives the convenience FPS number. The renderer carries the ratio through source conform, timestamp units, canvas generation, encoding and Blender image sequences. Timeline positions are integer frames; source in-points may be fractional project frames. All 48 kHz audio placements use absolute sample boundaries, so successive 29.97/59.94 cuts do not accumulate independently rounded sample errors.

This exposed and fixed two export defects: a redundant output picture limit truncated the limiter's audio tail, and MOV's previous movie timescale rounded audio edit duration too coarsely. Tests examine packet timestamps, decoded pictures and PCM, including reverse, fractional trims, held/eased gain and many cuts. The UI labels fractional-rate timecode NDF; drop-frame display has not been implemented.

Decoded split comparisons also exposed timestamp truncation changing half-frame selection after a fractional source split. A bounded frame-aligned conform clock and explicit retimed timestamp rounding preserve the selected pictures across cuts. Permanent regression coverage compares every decoded frame in 48 combinations of container timestamps, rate, speed and direction, each split at three positions. The paused-frame cache version changes with this correction.

### 2. Animated image processing and shape geometry

Compositor nodes now store separate animation channels. Grade, blur, chroma tolerance/blend, merge opacity and mask placement/feather/geometry evaluate at the clip's preserved animation-domain frame. A property edit cannot silently key unrelated channels. Polygon path keys preserve topology; completed point gestures use one undo checkpoint. Parameters, paused PNGs and movie export evaluate the same saved data.

The graph now contains one primary clip source and up to eight independent project-media nodes within its 32-node limit. Each additional source references an owned asset ID and specifies its source in-point, duration, signed animation-domain offset and transparent/hold policy. Actual pictures feed the saved connections and ordered merges; source audio is not implicitly mixed. Trims/splits preserve the animation domain. The same graph feeds paused-frame PNGs and movie export. Node counts, animation keys and working pixels remain bounded; nested compositions, deep/multiview/arbitrary channels and a plugin host remain absent.

A calibrated lens node adds actual static Brown undistort/redistort processing with explicit normalized intrinsics and five distortion coefficients. Compatible base camera intrinsics can be copied from the scene. A whole-canvas contraction bound of `q ≤ 0.45` rejects folding/strong models; two lens nodes and 2,073,600 nonidentity canvas pixels are the current limits. An owned, cancellable worker generates six verified 16-bit sampling maps. Bilinear RGBA remapping preserves premultiplied edges and uses transparent out-of-frame samples. Identity is an exact bypass. Lensfun profile conversion, fisheye/anamorphic/rational models, auto-calibration and animated coefficients remain missing.

Extending a clip enlarges the editable animation domain to include the new visible interval without inserting keys or moving existing trajectories. Audio fade endpoints retain their independent original domain.

### 3. Measured tracking that changes the actual output

The user chooses a feature in an actual conformed source frame. FFmpeg correlation measures the chosen patch across the requested range. Result receipts include source identity, exact rate, source-time mapping, positions, visibility and confidence. Missing matches remain gaps. There is no synthetic trajectory or model-name substitution.

Applying stabilization creates an additive source-relative motion channel. Existing position, scale, rotation, opacity and sound remain authored separately. Tracking curves have no invented frame-zero anchor. A tracked ellipse receives its own mask channels and provenance. Source slips/reverse invalidate derived motion; trims/splits retain the curve domain; speed changes rescale keys. Independent output measurements verify stabilization. Affine/planar/optical-flow tracking and semantic segmentation remain missing.

### 4. Geometry that survives viewport, render and scene replay

The OBJ/MTL path parses selected text into bounded indexed meshes, triangulates concave simple faces, preserves UV/normal corners, partitions materials, and records actual source hashes. It never follows embedded filesystem references. The editor displays and ray-selects the actual geometry and appends an import as one undoable scene edit.

The 0.7 authoring model adds ordered control polygons, a canonical authored-geometry hash, separate original-source provenance, a live modifier recipe and the actual evaluated mesh. Own vertex/face modes support selection, exact local coordinates and move handles. Face extrude creates walls/cap; subdivision shares edge midpoints with neighboring faces; deletion removes only selected faces and unused vertices. One accepted worker candidate enters shared undo once. Geometry edits currently clear imported UV corners with an explicit message.

Mirror, Bevel and Subdivision (Catmull–Clark/Simple) are real Blender modifiers, with ordered enable/parameter/reorder/remove/refresh/apply controls. The shaded viewport displays their actual evaluated result. The retained `.blend` preserves the base cage and live stack; the render reevaluates and checks actual engine version, vertices, topology, normals and UVs against the stored evaluation before producing pictures. Applying a stack reevaluates before baking, and undo restores the cage and modifiers. Bounds include 10,000 cage vertices/faces, 512 selected elements, four modifiers and a shared 5 MiB geometry budget. Each Blender evaluation is an owned 45-second worker.

`test_scene_modeling_blender.py` independently reopens the source, checks live settings and geometry, measures real enabled/disabled render differences, and requires a freshly rehashed forged preview to fail. The corresponding native control harness is separate; its presence is not a completed acceptance run. Edge modeling, UV authoring, rigs, sculpting, hierarchy, deformation, geometry nodes, simulation and reconstruction remain unimplemented.

### 5. Interchange with explicit fidelity and an undoable application step

The bounded OTIO exporter writes picture/audio tracks, gaps, cuts and actual media references. Companion audio tracks avoid ambiguous embedded-sound behavior. The importer resolves already-imported media using verified SHA-256 or explicit selections; it never follows arbitrary document URLs. The preview shows the candidate edit and warnings before one undoable replacement. It does not autosave.

Private authoring metadata can reconstruct an unchanged CINEMATICUM roundtrip. A digest of the public edit detects external changes; private effects are not allowed to override edited public timing. This is change detection, not authentication. Unsupported transitions, timewarps, nesting, overlaps and unrepresentable final gaps reject explicitly. Official OpenTimelineIO reader/writer tests and decoded picture/PCM tests check the supported subset. General AAF/XML/native-project conversion remains missing.

### 6. Job ownership, recovery and cancellation

ComfyUI cancellation addresses only the actual accepted prompt ID. Where the new atomic job-cancel route is absent, the fallback deletes only that queued ID. It never sends a global interrupt. A successful dispatch and a confirmed terminal cancellation are reported separately. A legacy running prompt can continue remotely after local waiting stops; the job receipt states that outcome. This protocol is tested against HTTP fixtures and is not claimed as a successful neural-generation run.

Shared job polling now captures an owner object and rechecks it after each response so an earlier poll cannot overwrite a newer job. Repeated communication failures preserve Retry status and Cancel for the original job. Modeling requests are read-only candidate evaluations: revision and object identity guard the one undoable application, and a cancelled, failed or stale candidate leaves authored geometry unchanged. Status recovery does not later apply an abandoned candidate. `test_job_polling.py` covers ownership and connection-recovery behavior.

### 7. Calibrated camera interchange

The fSpy reader validates its real binary header and JSON camera records. COLMAP import reads the explicitly selected camera/image text pair, verifies camera IDs/quaternions and preserves pinhole intrinsics. Both map into the own camera model with explicit world-axis conversion and translation scale. Roll, image principal point and `fx/fy` survive; incompatible aspect ratio, unsupported distortion and invalid geometry reject before application. Camera selection is reviewed and applied once through project undo; prior camera animation is explicitly replaced.

The scene viewport and retained Blender camera use the same projection contract. Acceptance compares source equations to WebGL projected points and independently reopens the retained `.blend` to check actual Blender projection. This imports a solved camera; it does not perform COLMAP reconstruction or fSpy vanishing-line solving. The camera reader still rejects unsupported distorted COLMAP camera models. The new separate calibrated-lens compositor node processes footage using explicitly supplied Brown calibration; it does not turn import into a calibration or reconstruction solve.

### 8. Physical camera, material and transport controls

The saved scene now carries sensor height, authoritative vertical FOV, derived focal length, roll/shifts/focal ratio, focus distance/f-stop and aperture shape. Pose channels preserve the lens parameters at each integer frame; incompatible redundant lens values reject. Cycles receives the actual DOF/aperture settings, Principled transmission/IOR/emission and bounded bounce/denoising/seed parameters. Emission color is converted from authored display RGB to scene-linear values.

The own viewport supplies editable geometry and approximate material feedback. Native acceptance checks actual retained camera/material/integrator properties and compares rendered sharp/defocused pixels. This does not implement Mitsuba differentiation, pbrt spectral transport, optical prescription optimization or Gaffer's general scene graph.

### 9. A real input color stage and owned LUTs

A float RGBA stage decodes declared source transfer, applies primary conversion and Bradford white adaptation, then encodes Rec.709. Supported inputs are Rec.709/sRGB/linear/LogC3 EI800 with Rec.709/Rec.2020/ACEScg/ARRI Wide Gamut 3 primaries. A strict Cube reader supports independent per-channel domains, 1D and 3D tables, and the selected interpolation. The project stores canonical UTF-8 tables by actual SHA-256, with missing/tampered tables rejected at validation.

Investigation exposed FFmpeg Cube-domain handling that was insufficient for nonzero minima. The compiler explicitly normalizes each channel and feeds a unit-domain table. Tests exercise nonzero/unequal domains, all tetrahedral regions, alpha, transfer reference values and literal filter paths. Integration tests decode the actual current-frame PNG and exported movie and verify that the stage feeds the compositor. The UI imports real files, applies through one undo entry, saves and reloads.

Float values survive this input stage; the movie compositor and delivery remain SDR. Its ACEScg primary conversion is distinct from the actual OCIO display-view transforms now available in the separate still-image worker.

The optional worker executes real builtin-config OpenColorIO source-to-scene-linear and display/view transforms. RAW development uses rawpy/LibRaw on preserved SHA-addressed camera originals, exposing demosaic, white balance, highlights and half-size controls. HDR merging combines 2–16 aligned static-scene stills with explicit shutter times and a known response. It does not fit a response curve, align frames or remove ghosts.

Each successful operation retains a float32 ZIP RGBA `linear.exr`, a separately encoded 16-bit sRGB `display.png` and a receipt binding the recipe, actual source/config/runtime identity and output hashes. Negative and above-one linear values survive the EXR; the display image is admitted to the normal media inventory. Single-part RGB/RGBA EXR inputs require an explicit space when metadata does not establish it. RAW sources are bounded to 512 MiB and 67,108,864 sensor pixels, output to 33,554,432 pixels, and jobs to five minutes. Deep/multipart/arbitrary-channel EXR, RAW movie editing, full float/OCIO movie compositing, external OCIO configs and HDR mastering remain missing.

The core server remains standard-library-only. NumPy 2.3.5, OpenColorIO 2.6.0, rawpy 0.27.1 and OpenEXR 3.4.15 run under the separate managed interpreter at `~/Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python`; application bundle replacement does not move that runtime. `test_imaging.py` requires the actual worker and a real camera file for RAW execution. The native OCIO/RAW/HDR control harness has independent operation stages; run results are recorded separately.

### 10. One installed native app

The old installer retained sibling `.app` backups, so macOS discovered several CINEMATICUM entries. The new installer builds the app/icon first, independently verifies all archived file bytes and modes, then replaces the canonical bundle with a rollback path. Recognized old backup/rejected bundles become ZIP archives under a non-indexed folder. It preserves unrelated applications and symlinks. Archive verification, rollback failure handling and recovery are tested; existing project files are kept outside installation.

### 11. Editorial trim modes that preserve the source clock

The own Trim dialog previews and applies source slip, touching-shot slide and outgoing-cut roll in integer timeline frames. The operation planner accounts for speed, reverse, source handles, locked tracks and one-frame minimum neighboring shots. Slide retains the selected source and fixed sequence endpoints; roll changes one outgoing boundary; slip keeps placement and authored animation while changing source content. Slip clears derived source tracking in the same undo entry. Missing/ambiguous adjacency rejects explicitly. Each accepted operation applies once through shared history; a zero offset is a no-op.

`test_trim_edits.py` checks independent editorial invariants and decoded frame selection. `test_trim_ui_macos.py` uses the actual controls on three touching eight-frame clips, verifies one undo/redo, saves and exports, then independently reads frame-ID patches and moving-marker positions from all 24 rendered frames. Source-handle and locked-track rejection have separate native coverage. The native harness is not itself a passing execution report.

## Remaining work, ordered by required data model

| Required level | Missing implementation | Evidence needed before it can be called complete |
| --- | --- | --- |
| Editing/conform | Sequences, nesting, multicam/sync, source channel maps, richer contextual trimming, proxies and relink | Roundtrips across sequence boundaries, source/timecode identity, proxy/original frame equivalence and editorial operation acceptance |
| Image pipeline | Extend float/OCIO processing through the movie compositor, HDR mastering, RAW video, image sequences, arbitrary EXR channels and calibrated monitoring | Known color reference transforms throughout the timeline, linear/alpha checks, HDR export and monitoring validation |
| Compositing/VFX | Nested compositions, Bezier roto/paint, planar/affine tracks, broad lens models/profile conversion, deep and arbitrary channels | Independent pixel/matte fixtures, coordinate and premultiplication checks, cache invalidation and bounded actual renders |
| Motion design | Vector document model, curves/tangents, text shaping/animators, parenting, expressions, reusable compositions | Editable data roundtrips, shape topology invariants, deterministic animation and actual vector/raster export |
| 3D | Edge/sculpt tools, UV/texture/material graphs, hierarchy/constraints, armatures, deformation/geometry nodes and simulation | Saved scene replay, topology/material/animation checks, simulation cache identity and actual rendered output |
| Reconstruction | Feature extraction/matching, camera models/poses, bundle adjustment, depth, surface and texture pipeline | Real multi-view input, registration/reprojection metrics, recovered geometry and pose-coordinate verification |
| Neural tools | SAM/TAPIR/TAPNext workers, checkpoint/config identity, correction state, memory budgeting and CameraCtrl conditioning | Actual model output on declared hardware, correct visibility/mask/camera conversions, reproducible identity and cancellation |
| Audio/delivery | Bus routing, channel layouts, plugin hosting, loudness, restoration, captions and broader delivery profiles | Decoded channel/sample/loudness checks, session roundtrips and target-profile acceptance |
| Production scale | Realtime decoded/GPU cache, background rendering, shared projects, crash recovery beyond current atomic saves, deployment packaging | Large real-media benchmarks, concurrent edit/conflict tests, interrupted-job recovery and signed distribution verification |

These are engineering requirements, not hidden buttons or implied installed capabilities. The previous provider list—Runway, Krea, OpenArt, Magnific, Artlist, Firefly, Flow, Luma, Kling, Pika, FLORA and Weave—also remains an external-product comparison requirement. This build adds no authenticated provider SDK, account, credits or licensed proprietary model. Generic ComfyUI execution cannot honestly stand in for them.

## Verification boundaries

The Python suite checks decoded media and real local HTTP behavior. Native WK acceptance runs operate shipped controls in disposable projects, then inspect saved data and exported media independently. Blender replay opens the actual retained `.blend`; it is stronger evidence than inspecting a generated Python recipe alone. Synthetic fixtures are clearly named ENGINE TEST, never inserted into the user's film or authority objects.

The checked Mac has FFmpeg and Blender, but the configured ComfyUI endpoint was unavailable. Native app updates preserve existing projects and archive previous own application bundles with file-hash and permission verification. Source publication stays on the existing draft PR; the owner checkout, source footage, current case and issuance records are not rewritten by these upgrades. Exact verification results are recorded separately after execution; a test file's presence alone is not a passing result. Consult the versioned verification report for the actual native stage results and tested environment.

# CINEMATICUM Studio 0.13

A working local audiovisual editor. Media are imported into an owned project,
edited on a frame-based timeline, previewed, and exported through real render
engines. Timeline, compositor, mixer and 3D authoring are CINEMATICUM controls
sharing one saved project and undo history. FFmpeg and Blender run as headless
processing engines; no external editor interface is embedded or launched.
No missing shot is replaced with filler. Exporting media has no film
issuance effect.

## Current build

Studio **0.13.0 / build 14** adds measured Lensfun radial profiles, four fisheye
projections and bounded public Final Cut Pro XML interchange. In a compositor
lens node, select **Lensfun profile** or **Fisheye**, import/select the measured
profile when needed, and apply the calibration through normal undo history.
Selected numeric data and original XML identity remain in the saved project.
[Lens workflows](LENS_WORKFLOWS.md) describes capture geometry and model limits.

In **Interchange**, select **Final Cut Pro XML (.fcpxml)**, choose a standalone
1.9/1.10 document, explicitly map its resources to owned media, review and apply
one undoable timeline replacement. Export writes public 1.10 XML for the
admitted cut/gap/connected-lane/compound edits. Nonzero clocks and trimmed
sequences survive save/reopen and portable archives. Unsupported operators
refuse before applying or exporting. [FCPXML](FCPXML_INTERCHANGE.md) defines the
measured picture grids and the external-editor limitations.

Accepted core `cdd15816` passed all **925 complete-suite tests**, with no
failures/errors/skips and unchanged source and all five managed runtimes.
The actual Mac lens and FCPXML phases passed **150 outer checks** across four
native author/render executions and two fixture preparations. The FCPXML movie
matched every one of 40 numbered pictures and all 64,064 stereo sample frames
with zero PCM error. The exact Mac input/export also passed the separate pinned
Apple 1.10 DTD gate. Actual replacement installation passed 5/5 for all 114
runtime/web and 119 bundle files, preserving prior 0.12 and 59 existing project
files (2,858,334,501 bytes). Canonical launch passed 16/16; all eight installed
runtime phases passed 14/14, with 6/6 final preservation. The exact publication
and post-publication CI outcome are recorded in
[PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162). See [Features 0.13](FEATURES_0_13.md),
[Verification 0.13](VERIFICATION_0_13.md) and [remaining work](UNFINISHED_0_13.md).

Published 0.12 `dcea8619` is the preserved previous release. It passed 895
complete-suite tests, 58 reported native retime checks, 5 installation checks,
16 canonical launch checks and eight selected installed-runtime phases of 14
checks each. Final installed-source reconciliation passed 10/10, and its actual
published source passed all 895 CI tests and seven separate browser gates with
complete source identity verified. The retained [0.12 record](VERIFICATION_0_12.md)
keeps those results attached to their actual source. Current 0.13 evidence is
recorded separately.

The existing positive variable-speed curves and actual dense optical flow,
simultaneous cameras and fixed-camera sound, Float32 OCIO/ACES movies, editable
OTIO compositions, measured HDR photographs and planar panoramas remain
available, alongside the scientific, learned, scene and collaboration tools.
Open **Multicam**, **Interchange**, **Develop images**, **Export** or **Studio
tools** for those workflows. [Retiming](RETIME.md) defines the existing speed,
pitch and quality bounds.

## Previous upgrade

The 0.9.1 candidate adds source-sample live audio, measured affine/projective
planar tracking and image corner pinning, and 16-bit UNORM SDR processing with
a lossless FFV1 RGB+alpha master. It also guards native quit while media jobs
are active and includes the tracking modules and runtime installers in the
application bundle. These additions have separate native acceptance gates;
their results and the exact tested source are recorded in
[Verification 0.9.1](VERIFICATION_0_9_1.md).

The 0.9 source adds live nested sequences, manual multicamera editing, captions,
source-channel mapping, drop-frame display, verified preview proxies and
exact-original relinking. Compositing adds cubic Bézier roto with point feather,
bounded SVG boundary import/export and combined 1D-shaper/3D Cube LUTs. 3D adds
object hierarchy, editable UVs and real smart unwrap, five additional modifier
types, and validated Cycles compute-device selection.

These operations use CINEMATICUM's own controls and shared project history.
Existing recovery/version history, portable archives, production shot assembly,
scene-linear EXR masters, calibrated cameras, physical materials, exact clocks,
measured tracking and OCIO/RAW/bracket still processing remain available.
Read the [source comparison and capability audit](CAPABILITY_AUDIT.md),
[capability ledger](capabilities.json), and
[current unfinished-work register](UNFINISHED_0_13.md) for implemented bounds and
remaining professional gaps. [Verification 0.9](VERIFICATION_0_9.md) is historical
evidence for the earlier candidate. Its 515-test result does not certify newer
source. The current verification record identifies current-source acceptance,
installation, and publication independently.

Runtime setup includes fixed, pinned imaging and OpenCV tracking installers
alongside Optiland, Mitsuba, SAM 2/TAPIR, independent TAPNext and COLMAP setup.
Install and Verify use project-owned jobs and the displayed lock identity.
Imaging setup supports cancellation of its owned commands and refuses to
publish a newly built runtime after cancellation. Existing installations and
unrelated files are preserved. This does not bundle FFmpeg, Blender or every
runtime, or establish Developer ID signing and notarization.

**TAPNext** is a separate checkpoint-backed point tracker in Learned masks and
points. Runtime setup installs its exact official source, Einops overlay and
BootsTAPNext checkpoint beside the existing learned Torch environment; it does
not replace the TAPIR package or weights. Choose TAPNext, load an actual clip
frame, author point queries, run inference and apply stabilization with explicit
corrections. Recipes, source/checkpoint bindings and ordinary Undo/Redo survive
save/reopen and export. The CPU workflow is bounded to 16 points, 32 conformed
frames and a 512-pixel analysis edge, with model input resized to 256 × 256.
Before-query and outside-source samples are invisible. Synthetic readiness and
editing checks do not establish production long-shot or occlusion recovery.

## Source-sample audio and 16-bit masters

Live audio comes from bounded PCM sample ranges decoded from the selected
original stream. Channel mapping and constant-speed tempo conversion are
included in the source receipt; the native scheduler applies the clip/track
gain and pan on a shared playback clock. Overlapping clips and live nested
sequences retain independent source clocks. A late range stops at the last
scheduled sample and buffers again instead of shifting late audio against an
advancing picture clock. Reverse playback schedules original stereo sample
frames in reverse order, including constant-speed and nested sequence edits.
Picture proxy refreshes retain the original-source audio transport. This
stereo mixer does not add buses, audio plugins or surround output.

In **Export**, choose **High 16-bit SDR** under Movie processing. This setting
also enables the processed 16-bit paused image. Select **Transparent background
for the master** when an alpha channel is required, then export
**16-bit lossless master · MKV**. The actual movie uses FFV1 planar 16-bit RGB
plus straight alpha and PCM audio. The native download link transfers the
completed master; Render preview provides browser playback. H.264 and ProRes
deliveries use their own output bit depths and flatten transparency against
black. Processing mode and transparency are saved project settings with undo.

Identity samples preserve all 1,024 distinct codes in the numeric acceptance
fixture. Filtering, association/unassociation and bounded grades can round,
clip or ring. Lanczos edge overshoot and the scaler's fractional-alpha rounding
are recorded in the precision tests; 16-bit storage does not promise 16-bit
numerical accuracy after every transform. The path is bounded to 8,388,608
canvas pixels and 16,777,216 transformed working pixels. This mode remains
UNORM SDR. The integrated [Float32 movie pipeline](FLOAT_MOVIE_PIPELINE.md)
provides scene-linear OCIO/ACES processing for supported timeline operations, real
FLOAT32 EXR sequence masters with PCM audio, and display-transformed SDR previews.
Its settings, source interpretations, export/download and archive bindings share
the normal project workflow. HDR mastering and calibrated monitoring remain open.

## Recover edits and move projects

Unsaved changes are checkpointed after 750 ms of inactivity, or within three
seconds during continuous editing. This protects the current edit without
changing the committed project. The header reports recovery status separately
from Save. **History** lists recoverable drafts and up to 20 previous saved
versions. Recovery is explicit, creates one undo entry, and still requires Save
to commit. The current media inventory is retained when recovering an older
edit. Drafts from different editor instances remain separate; an older response
cannot acknowledge or overwrite a newer checkpoint. Checkpoints are not a
promise of zero loss between the last successful request and a process crash.

**Archive** saves a dirty edit and creates a downloadable `.cinematicum.zip`
package containing the editable project, admitted media, project LUTs, saved
workflow, original RAW inputs, referenced imaging masters/recipes, and authored
scene sources and EXR packages. Copying and hashing use bounded streams, and
the archive is limited to 64 GiB and 10,000 members. ZIP64 members are stored
without additional compression; already-compressed media retain their exact
bytes. Restore verifies paths, member types, sizes, hashes and dependency
closure before publishing a new project identity. **Open restored project**
opens that separate project when validation succeeds. Cancelled/failed uploads
are removed; external engines, plugins and model weights are prerequisites,
and opaque imported `.blend` files may still need externally linked resources.
Restoring a package never executes its workflow or opens Blender automatically.

## Assemble a production shot plan

Open **Production** from the timeline toolbar and select a shot-list JSON.
The repository's `production/THE_LAST_RENDER/shots/shotlist.json` format is
supported. Review the ordered requirements, choose actual imported video for
each shot, set a source In frame, and preview that source range. Matching is
checked against source identity and available duration; choosing a differently
named take requires explicit acknowledgement. A plan can be saved while media
are missing. The app reports each missing or short source and keeps assembly
blocked until all required shots are valid.

**Assemble cut** creates one undoable candidate at the plan's exact rational
frame rate. Incompatible canvas/rate replacement requires an explicit choice;
locked timeline tracks reject replacement. Times off the frame grid are
rejected instead of rounded. The saved plan and selected take ranges remain
editable with the project. **Export shot requirements** downloads a persistent
JSON attachment; it does not include media. Use Archive to move the complete
editable project. No plan, render, archive or restore changes film issuance.

## Open it

Requirements: Python 3.9+, FFmpeg with FFprobe, and either the native macOS app
or a current browser. H.264 export needs FFmpeg's `libx264` encoder; ProRes
needs `prores_ks`. Blender and ComfyUI are optional engines. The core editor and
server use Python's standard library and require no npm packages. The optional
imaging worker runs in a separate managed Python environment with NumPy,
OpenColorIO, rawpy/LibRaw and OpenEXR. Run these commands from the repository root.

```bash
make studio
```

The editor binds only to `127.0.0.1`, normally on port 8765. A different port or
project directory can be selected explicitly:

```bash
python3 scripts/studio/server.py --port 8766 --workspace /path/to/projects --open
```

### Native macOS application

Build using the installed Xcode command-line tools, then open the app:

```bash
make studio-install-macos
open "$HOME/Applications/CINEMATICUM Studio.app"
```

The installer produces `~/Applications/CINEMATICUM Studio.app` for the Mac's
architecture. It builds but does not launch the app. To build elsewhere:

```bash
python3 scripts/studio/install_macos.py --build-only \
  --output "$PWD/dist/macos/CINEMATICUM Studio.app"
```

The app starts its own Python service on an available loopback port and opens
the editor in a native WKWebView, with native import and export dialogs.
Closing the window saves pending timeline edits and asks before cancelling active
owned media jobs. The app still requires installed Python, FFmpeg, and any
optional engines; the installer does not bundle them or create a signed,
notarized distribution.

Install-03 passed in 16.515 seconds; its full private receipt is now collected
and hash-verified. It verified the frozen 189-file source, 62 runtime files,
67 bundle files and all 57 protected workspace files. Both the original 59-file
app archive and later 70-file archive are preserved. Canonical launch-02 passed
16/16 in 5.361 seconds, and final source reconciliation passed 9/9 against
published `81827cf92d159b9619d51000da61ea3c8a6b6ce7`.

Production quit passed 21/21 independent and 10/10 native checks. The production
chooser separately passed 22/22 independent checks for actual Save and public
NSSavePanel Cancel action, exact downloaded bytes and cleanup. This scoped test
does not certify physical Cancel-button/Escape input, arbitrary chooser
navigation, renamed destinations or existing-file replacement. Current-session
access is restored; historical failures remain in
[the verification record](VERIFICATION_0_9_1.md).

Quit Studio before rebuilding. Replacement is allowed only for a bundle with
Studio's own identifier. The installer creates and reads back a ZIP archive,
checking every file's bytes and permissions before replacing the old app.
Archives live in `~/Applications/.CINEMATICUM-Backups.noindex`; recognized old
`.backup-*.app` and `.rejected-*.app` bundles are consolidated there so only one
application appears in the launcher. Unrelated bundles and symlinks are preserved.
The native app now has its own icon. Projects default to `~/Movies/CINEMATICUM`; application
updates do not replace that folder. On Linux the default is
`$XDG_DATA_HOME/cinematicum`, or `~/.local/share/cinematicum` when unset.

### Optional imaging runtime

On Apple Silicon, install the pinned Python 3.13 imaging environment separately:

```bash
python3 scripts/studio/install_imaging.py --python /opt/homebrew/bin/python3.13
```

The managed interpreter lives at
`~/Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python` and
survives replacement of the application bundle. Its pinned packages are
NumPy 2.3.5, OpenColorIO 2.6.0, rawpy 0.27.1 and OpenEXR 3.4.15. The core app
checks the worker before offering image development. An explicitly configured
`CINEMATICUM_IMAGING_PYTHON` can select a compatible isolated interpreter on
another installation. The app installer does not silently install these
packages. Ordinary timeline editing and exports do not require this environment.

## Work with real media

1. Import video, audio, still images, or a Blender scene using the file picker or
   by dropping files into the media bin. Imports are copied and content-hashed.
2. Double-click a video, image, or audio asset to add it to the timeline. Drag to
   change its start or layer; use the clip edges or Inspector for exact trims.
3. Add picture and audio tracks with **＋ Video** and **＋ Audio**, up to 16 of
   each. Higher picture layers composite above lower layers. Track mute, solo,
   lock and gain are shared with the Audio mixer. Gaps render black; audio gaps
   render silence. Solo is evaluated separately for picture and audio tracks.
4. Use Color for input transforms, white balance, LUTs, exposure, contrast,
   saturation, and temperature. Composite
   provides an editable node graph as well as clip transforms and effects.
   Add titles with position, size, color, duration, and fades.
5. Editor playback is interactive. When paused in Color or Composite, the
   current frame is rendered by the same graph as export, including unsaved
   effects. Color scopes measure that rendered display RGB image: histogram,
   luma waveform and vectorscope. Render preview plays actual encoded output.
6. Save the project, or export H.264 MP4 or ProRes MOV. Export snapshots retain
   the exact project revision and output SHA-256; editing later does not alter a
   running render.

### Timing, animation and sound

New projects support 24, 25, 30, 48, 50 and 60 fps, plus exact 24000/1001,
30000/1001 and 60000/1001 rates. The API accepts reduced rational rates from
1 to 60 fps. `frame_rate` is authoritative; numeric `fps` is derived for UI
arithmetic. Render timestamps and 48 kHz audio placement use the rational clock
and absolute sample boundaries. **Sequences → Timecode display** selects NDF or
DF. Drop-frame labels are supported for exact 30000/1001 and 60000/1001 projects;
other rates reject DF. This changes labels, not frame rate, picture content or
audio timing. NDF remains the default.

The clip inspector exposes 0.25×–4× speed, reverse of the selected source range,
clip gain, stereo balance and audio fades. Source in points may be fractional
project frames; timeline starts and durations remain integer frames. Speed
changes preserve the selected source range to frame precision. Trim handles
and split account for speed and reverse. Ripple delete closes a gap on the
selected track. Track locking prevents direct clip editing.

Select a clip and click **Trim** for source slip, shot slide or outgoing-cut roll.
Offsets are integer timeline frames; the preview reports the actual permitted
offset before application. A slip changes the selected source range while its
timeline position, length and authored animation stay fixed. A slide moves the
selected shot and trims its touching neighbors, retaining the shot's source and
the sequence endpoints. A roll moves the selected clip's outgoing cut and
adjusts the next touching clip. Speed, reverse, available source handles and a
one-frame minimum for neighboring clips bound each operation. These tools reject
ambiguous/missing adjacency and locked tracks. One application is one shared
undo entry. Slipping source content clears derived stabilization and tracked-mask
motion in that same edit; ordinary authored channels remain.

Source audio waveforms come from decoded 48 kHz stereo PCM with real minimum,
maximum and RMS samples, cached by source identity. The Audio workspace has
track names, gain, mute, solo and lock. Export processes pitch-preserving tempo,
reversed audio, sample-based fades, stereo balance and animated volume. Live
reverse, constant-speed reverse and nested reverse use the selected original
stream and channel mapping. Native fixture acceptance measures actual WebAudio
PCM against independent decoding, repeated starts, source-clock direction and
underruns. These synthetic fixtures do not establish sustained production-media
performance or complete audio-production facilities.

Clip position, scale, rotation, opacity and volume can be keyframed, with linear,
hold, ease-in, ease-out and smooth ease-in/out interpolation. Each property uses
its own keys and the base property value at frame zero. Keyframe chips expose
playhead navigation, outgoing interpolation and deletion. Trims and splits preserve the complete animation and fade envelopes, including
hidden keys outside the trimmed range. Editing a fade resets its envelope to
the current clip range. Constant retiming rescales animation and fade times to integer
output frames.

Space plays/pauses, S splits the selected clip at the playhead, Delete removes
the selection, and Cmd/Ctrl-Z and Cmd/Ctrl-S undo and save. Titles use actual
transparent PNG plates generated from the editor canvas, so the Mac does not
need FFmpeg's optional `drawtext` filter.

## Sequences, cameras, captions and source audio

**Sequences** opens the shared sequence library. Name an edit and choose **New
empty** or **Duplicate active**. **Open** switches the active edit without losing
the previous sequence. **Nest at playhead** places another sequence on picture
track V1 with its sound; changes to that child remain live in the parent. Nested
clips retain ordinary trims, retiming, transforms and mixing through the render
path. Save commits the complete library. Referenced sequences cannot be deleted,
and circular dependencies are rejected.

All sequences share the project's canvas size, exact frame rate and media
inventory. Limits are 64 sequences, eight nesting levels, 256 clips and 128 text
plates per sequence, 4,096 stored clips across the project, and 1,024 expanded
clip/text/sequence instances for each rendered dependency tree. These limits
apply to repeated instances as well as distinct sources. Use **Render preview**
for the complete processed nested picture and sound.

**Multicam** creates a group from 2–16 distinct imported videos. Enter the source
offset containing the same event in each angle, measured in project-rate frames,
then choose **Create cut at playhead**. The available cut ends with the shortest
remaining angle. Select its timeline clip, put the playhead at the cut, and choose an angle button. The new
segment preserves synchronization and either follows that camera's audio or
retains the group's explicitly locked sound camera, stream and channel pair;
authored gain, balance and fade envelopes remain. [Measured source-audio
synchronization](MULTICAM_SYNC.md) estimates constant offsets, and the
[simultaneous monitor](MULTICAM_MONITOR.md) shares the timeline's source-PCM
clock. Timecode synchronization and clock-drift correction remain unsupported.
Live angle switching must precede retiming, tracking or node compositing of
that multicamera clip. A project holds up to 64 groups.

**Captions** imports plain UTF-8 SRT or WebVTT, adds a cue at the playhead, and
edits start/end frames and text. **Apply caption edit** applies the complete cue
edit once through undo. **Burn captions into picture** generates actual text
plates; **Export SRT** or **Export WebVTT** downloads the sidecar. Imports round
absolute cue endpoints once to the project clock. Up to 4,096 cues are retained;
burn-in shares the 128-title limit with other titles. Styled/timed markup, WebVTT
positioning, STYLE and REGION blocks are rejected. Import files are limited to
2 MiB and cue text to 4,000 characters.

Select a timeline clip and open **Source audio** to choose one of its actual
audio streams and the zero-based source channels feeding stereo left and right.
Selecting one channel twice creates dual mono. **Apply channel mapping** changes
the rendered mix; **Reset to source default** removes that override. Timeline
waveforms honor the stream/channel mapping. Native source playback is undergoing
acceptance: a second MOV stream intermittently returns silence, including the
latest fresh test. Use rendered playback to inspect the exported mapping while
that defect remains open. This supplies explicit two-channel routing; general
surround output and a bus/plugin workstation remain unimplemented.

## Preview proxies and original-media repair

Open **Media & proxies**, choose a video and a **Preview long edge** of 640, 960,
1,280 or 1,920, then **Create proxy**. Proxies do not upscale a source. Each
H.264/AAC derivative is checked against the original decoded picture count and
relative timestamps before admission; source and proxy hashes bind its receipt.
The timestamp tolerance is two microseconds, with a 1,300,000-frame analysis
bound. **Cancel proxy job** stops the owned process and removes its partial
output.

Enable **Use available preview proxies** and Save to retain the preview choice.
Verified proxies drive interactive source decoding, while export and processing
continue to resolve original media. Proxies are lower-resolution lossy viewing
copies and do not promise identical pixels to their originals. They do not
supply a decoded GPU playback cache or arbitrary offline/online conform.

**Relink exact original…** restores a missing or damaged imported asset only when
the selected file matches its recorded SHA-256 and size. The asset identity and
existing edits remain intact. Different bytes are rejected; import a new take as
a new asset. A damaged existing original is retained in the project's repair
backup before replacement. **Refresh** rereads original/proxy availability.
Native acceptance verifies actual proxy decoder URLs, wrong-file rejection,
exact restoration and identical decoded original-based exports before and after
these operations.

## Input color and LUTs

Select a picture clip, open **Color**, then **Input transform, white balance & LUT**.
Choose the source transfer function (Rec.709, sRGB, linear, or LogC3 EI800), source
primaries (Rec.709, Rec.2020, ACEScg, or ARRI Wide Gamut 3), and source/target white
chromaticities. Bradford adaptation and RGB/XYZ matrices run in a float RGBA stage.
The stage encodes Rec.709 before the clip compositor and creative grading.

Import a selected `.cube` file to keep it with the project. The importer accepts
a three-channel 1D table (up to 65,536 rows), a 3D table (up to 65³), or a combined
1D shaper followed by a 3D table. Single tables support finite per-channel
domains. Combined tables use separate `LUT_1D_INPUT_RANGE` and
`LUT_3D_INPUT_RANGE` directives; ambiguous shared `DOMAIN_MIN/MAX` declarations
are rejected. The shaper uses linear interpolation, then the 3D stage uses the
selected nearest, trilinear or tetrahedral mode. Independent 1D tables also
support nearest interpolation. Files are limited to 24 MiB. Tables are
canonicalized and addressed by SHA-256; missing or changed bytes stop validation. The selected LUT runs after
the input conversion, before the compositor. Apply creates one undo entry and
does not autosave. LUT storage persists independently of undo.

Paused frames and export share this processing. Interactive source playback
remains approximate; use **Render preview** to judge moving processed footage.
This is an explicit input-to-SDR stage, not a complete OCIO/ACES display pipeline.
The downstream compositor/delivery remains SDR. RAW still development and OCIO
views are separate Develop operations; RAW-movie editing, HDR mastering,
whole-timeline OCIO management and automatic camera color-space detection remain
unimplemented.

## Calibrated cameras and physical rendering

In **3D**, use **Import camera…** for an fSpy v1 project/export or selected COLMAP
`cameras.txt` and `images.txt`. Review the solved camera, explicit world up axis
and translation scale, then apply it as one undoable camera replacement. Previous
camera animation is replaced; objects and lights remain. No path or photograph
named in an imported document is opened. Camera import keeps orientation/roll,
principal-point offsets and `fx/fy`; source and project aspect ratios must agree.
COLMAP import supports PINHOLE and SIMPLE_PINHOLE only. Distorted camera models
reject with an explicit error. Camera import does not undistort footage; the
separate Calibrated lens node applies supplied Brown calibration to image pixels.
The import does not run a reconstruction or calibration solve.

The camera inspector exposes sensor height and focal length, with vertical FOV
as the authoritative saved projection. Lens edits derive FOV; contradictory API
values reject. Depth of field exposes focus distance, f-stop and aperture shape.
Camera roll, shifts, focus distance and f-stop can be animated. The calibrated
focal ratio is static for the shot because Blender's output pixel aspect cannot
be keyed; attempts to animate it are rejected before rendering.
Materials expose transmission, index of refraction and emission alongside base
color, roughness and metallic. The scene's ray settings control actual Cycles
bounce limits, denoising and seed. The saved `.blend` retains those settings.

The own WebGL viewport matches camera geometry and offers approximate material
feedback. Use the actual Cycles render for depth of field, refraction and light
transport. Spectral/differentiable rendering, lens-prescription optimization and
full shader graphs and unrestricted geometry authoring remain separate
engineering requirements.

## Node compositing

Select a picture clip and open **Composite**. Add and connect grade, blur,
sharpen, chroma-key, RGB curves, rectangle/ellipse/polygon/Bézier mask, and merge nodes. Connections,
parameters, node positions, and the chosen output are saved with the clip.
The **Masked correction** action creates an editable branch: the original
picture is merged with a graded, masked version of itself. Masks support
feathering, rotation and inversion; polygon points are draggable. RGB curves
have draggable and numeric points for the master and individual channels,
using monotone cubic interpolation. Merge supports normal, multiply, screen,
add and difference, with source-over alpha and ordered background/foreground
inputs. Each completed curve or polygon gesture creates one undo entry; Escape
cancels it.

The graph processes the clip's trimmed source before ordinary clip transforms,
grading, effects, and placement on the timeline. Add **Project media** nodes to
bring other imported videos or stills into the same composition. Each node has
its own source in-point, duration, signed start offset and transparent/hold
behavior outside that range. These values use project-rate frames in the clip's
preserved animation domain, so trims and splits retain the source relationship.
Each source is fitted into the graph canvas with transparent margins. Different
nodes may reference the same asset with different ranges. Connections and ordered
Merge inputs combine their actual pictures; a media node can also be the graph
output. Their audio remains on the timeline. Clip retiming affects the primary
clip source, while additional media nodes retain their explicit ranges.
The paused current-frame renderer evaluates the connected output automatically.
During interactive playback, use Render preview to review the complete node
processing in the encoded movie.

Grade, blur, chroma similarity/blend, merge opacity and mask placement/shape
parameters have independent keyframe channels. Use the diamond beside a property
to key it at the playhead. Once keyed, editing that property writes its own key;
other channels keep their existing timing. Keys support linear, hold, ease-in,
ease-out, ease-in/out and **Cubic · custom tangents**, with frame navigation and
deletion. Cubic incoming/outgoing progress slopes are bounded to 0–3 for monotone
interpolation; arbitrary overshooting time curves are not supported. Polygon path
animation preserves vertex count/order; each completed vertex drag is one undo
entry. Topology changes are disabled while the path is animated. Sharpen amount,
curve control points and chroma color remain static in this release.

Graphs allow up to 32 nodes, exactly one primary clip-source node, and up to eight
additional project-media nodes, with no missing connections or cycles.
A resource limit bounds canvas pixels multiplied by active graph nodes to
268,435,456. Scalar animation has up to 128 keys per channel, polygon paths up to
64; a graph has at most 1,024 keys and 8,192 animated coordinate values.
Disconnected nodes remain editable but are not rendered.

### Cubic Bézier roto and point feather

Add a **Shape mask** node, then choose **Bezier roto** in its shape selector.
Drag an anchor or its incoming/outgoing handle; Shift-drag a handle mirrors the
opposite handle. Numeric anchor/handle fields, **Smooth handles**, **Corner**,
**Split next segment** and **Remove anchor** edit the retained cubic path.
**Point feather scale** multiplies the global **Inward feather** at each anchor.
The path diamond keys anchors, handles and feather together. All path keys keep
consistent anchor count and order; splitting/removing an anchor updates every
key. Splitting uses exact De Casteljau subdivision of the cubic. A completed
gesture creates one undo entry; Escape cancels a drag.

Paths contain 2–32 anchors and at most 64 path keys. The graph's shared 1,024-key
and 8,192-value budgets still apply. NumPy in the optional imaging runtime
rasterizes actual 16-bit coverage with 2×2 sampling and adaptive cubic flattening
at a 0.125-pixel tolerance. Paused frames and export use the same prepared matte;
animated masks retain the clip's trim/split frame domain. Worker output is
content-verified and bounded to 4 GiB; preparation is cancellable. Longer or
larger shots can exceed the processing bound.

**Import SVG · replace** accepts one supported closed path and replaces that
shape and its animation in one undoable edit. **Export SVG boundary** writes its
cubic boundary; CINEMATICUM metadata also retains transforms and point feather.
An ordinary SVG reader sees the boundary, not CINEMATICUM's feather matte.
SVG imports are limited to 256 KiB and one closed M/L/H/V/C/S/Q/T/Z path;
arcs, groups, SVG transforms and external resources are unsupported. This bounded
exchange does not supply a general SVG/Lottie document, roto-layer hierarchy or
paint system.

Grade, curves, blur, sharpen, chroma-key and calibrated-lens nodes expose an
optional **Effect mask · alpha** input. Connect the alpha output of a mask branch
and optionally invert it to restrict that effect. Validation includes mask edges
when checking graph cycles; rendered interpolation retains associated color and
alpha. **Save graph** and **Import graph** exchange bounded graph JSON using the
current project's media IDs; they do not package or remap external media.

### Calibrated footage lens processing

Add a **Calibrated lens** node to undistort captured footage or reproduce a known
distortion. It accepts the five-term Brown model (`k1`, `k2`, `k3`, `p1`, `p2`)
and normalized focal lengths/principal point (`fx`, `fy`, `cx`, `cy`). Compatible
base intrinsics can be copied from the authored 3D camera; the distortion
coefficients must still be supplied explicitly. Calibration is static.

Both paused-frame rendering and export evaluate actual bilinear RGBA remapping.
Out-of-image samples become transparent. A conservative whole-image Jacobian
bound rejects folding or excessively strong models before preparing maps. A
graph accepts two lens nodes and nonidentity lens processing up to 2,073,600
pixels, such as 1920 × 1080. A zero-coefficient lens passes the image through
without resampling, including larger canvases. Map preparation is an owned,
cancellable worker with a 90-second limit; the optional imaging runtime
accelerates the same calculation.

Studio 0.13 adds four explicit fisheye projections and import of
actual Lensfun XML radial calibrations. In the node inspector, choose
equidistant, equisolid, stereographic or orthographic, or select **Read Lensfun
XML**, review the exact measured focal sample and capture crop factor, then
choose **Apply selected calibration**. Profile data is embedded in the graph;
the XML file is not needed to reopen or render the saved project. The existing
Brown controls and project format remain compatible. See
[Lens workflows](LENS_WORKFLOWS.md) for coordinate conventions, tested evidence
and the actual integrated native/media acceptance. Automatic profile matching, focal
interpolation, rational/anamorphic models, chromatic/vignette correction,
automatic calibration and animated lens parameters remain unimplemented.

## Develop still images

Open **Develop images** to use the actual optional imaging worker. **OCIO color
transform** evaluates a selected builtin configuration, explicit source color
space, exposure and display view through OpenColorIO. The default builtin
configuration includes ACES transforms; output previews are bounded to its
`sRGB - Display` path. External arbitrary configs and file transforms are not
accepted.

**Develop camera RAW** preserves the original sensor file under its SHA-256
identity and uses rawpy/LibRaw for unpacking and development. Controls include
AHD/LINEAR/VNG/PPG/DCB demosaic, as-shot/daylight/automatic/custom white balance,
highlight clipping/blending/reconstruction and half-size output. The selected
algorithm must be supported by the actual file and runtime. LibRaw produces
linear 16-bit RGB; subsequent color transforms and the retained master use float
precision.

**Merge exposure brackets** combines 2–16 photographs using explicit shutter
times, fixed aperture/ISO/white balance, and a known sRGB/Rec.709/linear response
or measured inverse RGB response. Choose already aligned, measured translation
or planar perspective, then optionally retain the reference photograph inside
measured motion regions. The motion mask can be viewed and downloaded; clipped,
blurred or noisy reference detail remains. Measured response needs three
distinct shutter times spanning at least two stops.

**Stitch planar panorama** measures connected overlaps between 2–8 static,
textured photographs, optionally matches their exposure, and feathers linear
pixels. Uncovered regions remain transparent. Spherical/cylindrical projection,
parallax repair and moving-subject seams remain unsupported. Both enhanced
workflows require the installed Tracking runtime in addition to Imaging.
[STILL_PHOTOGRAPHY.md](STILL_PHOTOGRAPHY.md) records capture and pixel limits.

Every successful job retains `linear.exr`, `display.png` and `receipt.json`;
reference motion replacement also preserves its hashed `motion.png` mask.
The ZIP-compressed float32 RGBA EXR preserves negative and above-one scene
values with explicit alpha semantics. The separate 16-bit sRGB display PNG is
admitted into the normal media bin for editing. The receipt binds the actual
sources, recipe, config/runtime versions and output hashes. The original sensor
file and completed outputs are immutable; changing development settings creates
a new result.

Imported EXR stills require a single RGB/RGBA part and an explicit source color
space when its metadata is insufficient. Develop their display result for the
SDR timeline, or select the separate Float32 movie mode for direct scene-linear
RGB(A) EXR clips. Deep/multipart/arbitrary-channel movie graphs, HDR mastering
and a RAW timeline are not provided by the still-image path.

Limits are 512 MiB per RAW source, 128 RAW sources per project, 67,108,864 sensor
pixels before unpacking, 33,554,432 output pixels and 16,384 pixels per image
dimension. Imaging jobs have a five-minute limit and stop their own worker on
cancellation.

## Track motion and apply it

Select a picture video clip and click **Track motion** in the Inspector. Load
its actual starting frame, click a distinctive textured feature, choose a range
up to 480 clip frames, then **Measure motion**. The visible path contains measured
matches, with explicit gaps for missing detections. Radius is measured in the
analysis image; its maximum edge is 384 pixels. Template matching can lose or
misidentify repeated textures, scale changes, rotation and occlusion.

**Stabilize clip** adds an independent displacement channel relative to the
reference point. Manual transforms and sound automation are preserved. It holds
the first/last displacement outside the tracked range and does not auto-crop
exposed borders. **Remove stabilization** removes only that channel. **Create
tracked mask** adds a new animated ellipse to the compositor; this follows a
point and does not identify an object. Each application is one undoable edit.

The tracker rejects a low-contrast/ambiguous seed, missing samples during
application, or a trajectory requiring over 128 keys at half-source-pixel
simplification precision. That precision bounds simplification, not the accuracy
of template matching. Download the actual measurement JSON or import compatible
point tracks; source hash, frame rate, source range, speed, reverse and clip
identity must match. Trims/splits preserve applied motion, and retiming rescales
its keys along with compositor and pose animation. Changing source-in or reverse
clears derived stabilization and tracked-mask motion in the same undoable edit;
ordinary authored mask animation is preserved. Track the changed content again.
The point mode is a classical FFmpeg correlation tracker. It does not perform
neural segmentation, learned point tracking, camera solving or automatic
re-identification after occlusion.

### Planar measurement, stabilization and corner pin

In the same motion dialog, choose an affine or projective plane model and set
four corners on the decoded seed frame. The optional tracking runtime uses
OpenCV feature motion and RANSAC to measure the plane across the requested
frames. It is bounded to 240 clip frames and a 640-pixel analysis edge. The
receipt retains source identity, timing, model, feature/inlier measurements and
per-frame homographies; installation alone does not certify a track.

Apply stabilization to the measured clip or choose an admitted image to create
an editable corner-pinned overlay. The overlay follows the measured plane,
including the background's existing point or planar stabilization. Apply,
remove and undo use normal project history. Measurement data, keys and source
media remain part of the saved project.

Changing a measured source range, retime, transform or parent stabilization
marks dependent planar motion stale. The application preserves the authored
overlay and measurements, shows the reason, and blocks final export until the
motion is remeasured or explicitly removed. Undo can restore a matching binding.
A pure timeline move remaps the dependent pin when the source clocks still
match. This avoids silently applying a measured homography to different source
content. Source files are rehashed again before rendering.

## Exchange timelines and compositions

Click **Interchange** in the timeline toolbar. Export creates an actual `.otio`
JSON file containing picture/audio tracks, cuts, gaps, nested compositions,
constant retime/reverse, ordered overlap lanes and linear SMPTE dissolves with
rational timing. Media is referenced, not embedded. Embedded video audio is represented
on companion audio tracks. Color, masks, tracking, titles, mixer state and other
CINEMATICUM authoring data remain private namespaced metadata; other editors
receive source media with public timing and transition operators. Warnings
identify authoring properties that do not travel as public effects.

Import a `.otio` file, explicitly map its references to existing imported media
when no verified content hash matches, then **Review timeline**. The preview
reports the candidate's tracks, clips, rate and warnings. **Replace timeline**
applies it with one undo checkpoint; saving remains separate. The importer never
opens external paths/URLs from a document. A changed source edit invalidates
stale private metadata. Bounded nested `Stack`/`Track` exchange preserves trimmed
Tracks and the top-level Stack, companion picture/audio roles, disabled items,
composition padding, and explicit/trailing or all-gap durations. Public-only
imports create editable sequences; existing
destination sequences remain. An unchanged CINEMATICUM roundtrip also restores
all active/inactive sequence authoring only after byte-identity and regenerated
public-timing/structure checks.

Constant `LinearTimeWarp` uses output duration and the lower bound of the consumed
source window. Signed speeds from 0.25× to 4× are supported; a negative scalar
reverses that conformed window. Check the receiving editor's time-effect
convention. Same-track overlaps become ordered parallel lanes, preserving the
picture stack and additive source audio. `SMPTE_Dissolve` becomes an editable
sequence operator with measured source handles, premultiplied RGBA mixing and
complementary audio fades. It survives undo, save, reopen and project archives.

Nested exchange uses the shared rational project clock and existing sequence
bounds. Unsupported transition types, overlapping transitions, missing media
handles, freeze frames, speed ramps, multiple timewarps and general plugin
schemas are rejected explicitly. Effects, captions and mixer gains remain
private metadata rather than portable OTIO effects. AAF, Premiere XML and Resolve
project translation are unsupported. The request/document size limit is 8 MiB.
See [OTIO_INTERCHANGE.md](OTIO_INTERCHANGE.md) for precise conventions, limits,
independent media checks and bounded native acceptance commands.


## Create and render 3D scenes

Open **3D** to author a scene inside Studio. Add cubes, spheres, planes, and
cylinders; edit object transforms and materials; position lights and the
render camera; and set pose keyframes. Direct move/rotate/scale handles support
axis constraints, snapping, keyboard nudges and Escape cancellation. The
offline WebGL viewport supports orbit, pan, zoom, object selection, duplication,
camera framing, and animation playback. Its dope sheet has draggable object,
camera and light keys with interpolation controls. Camera position/target/FOV
and light position/target/power/size can all be animated.
Scene recipes are stored in the same project and participate in undo and save.

**Render scene** builds the authored scene in Blender using Cycles, renders
actual frames, and admits the encoded movie into the media bin. CPU remains the
default. **Light paths & sampling → Compute device** selects CPU, Metal, CUDA,
OptiX, HIP or oneAPI. The executing Blender instance enumerates devices and
requires the chosen backend; unavailable GPUs fail explicitly without a silent
CPU fallback. Recipe and receipt retain requested/actual device information.
After an earlier short harness timed out, a normal owned Metal job completed
in 82.430497 seconds. Independent verification passed 18 checks in 6.694 seconds,
covering decoded pixels, the retained `.blend`, the actual Metal device receipt
and absence of CPU fallback. The tested scene was one 192 × 128 frame with four
samples and no denoising; this does not establish large-scene throughput or
other GPU backends. Device preferences are machine/session specific even when
the retained `.blend` stores the GPU flag and recipe.
The completed job also offers the editable `.blend` source. Add the movie to
the timeline to edit and composite it with footage, sound, and titles.
Enable **Linear EXR** in the scene output controls to retain float32 RGBA beauty
frames. Optional passes are depth, normal, motion vectors, diffuse color and
emission. The job's **Linear EXR + passes** attachment contains the requested
inclusive frame range, scene recipe, exact rational clock, channel inventory
and per-file hashes. A transparent world preserves premultiplied alpha in EXR;
the H.264 movie is an opaque display derivative. The output is linear Rec.709
and uses lossless ZIP compression. These masters do not make the SDR timeline
an HDR compositing or mastering pipeline.
WebGL lighting is an interactive approximation; Blender produces the rendered
materials, shadows, and lighting. Supported authored scenes contain up to
96 objects, 16 lights, 128 pose keys per object, and 7,200 frames.
Transforms use Z-up coordinates and XYZ Euler rotation. Linear, hold, quadratic
ease-in/out and cubic smooth ease-in/out have matching viewport and render
evaluation. Saved Blender actions retain these curves; camera lens conversion
is baked at integer render frames.
New cameras use transported aiming to prevent an abrupt roll at a world-axis
pole. Older scenes retain their saved world-up framing until changed explicitly.
Camera/target and aimed-light paths are checked over the complete eased interval,
including subframes; undefined coincident aiming is rejected before rendering.

### Object hierarchy

Select an object and use **Parent · local transform** to choose another object
or **World · no parent**. The outliner displays the hierarchy. Position, rotation,
scale and pose keys are local to the parent; changing the parent preserves local
values and changes the inherited world pose. Parent animation, rotation and
nonuniform scale compose through the actual affine matrix in the viewport and
retained Blender scene. World-space move handles/nudges convert back to the
child's local coordinates.

Cycles, missing parents and hierarchies deeper than 24 levels are rejected.
Reparent or remove children before deleting their parent. Camera/light parenting,
constraints, armatures and automatic world-pose-preserving reparenting are not
implemented. Previously unparented scenes retain their existing transform behavior.

### Import real mesh geometry

**Import OBJ** in the 3D workspace accepts one selected OBJ plus up to eight MTL
files. Choose Y-up or Z-up and an explicit scale. The parser preserves indexed
triangle geometry, negative-index references, UV corners, custom/smoothed
normals, groups and solid material assignment; concave simple polygons are
triangulated. Material partitions become separately editable objects.

The viewport displays and ray-selects the actual mesh, and the same geometry
is constructed in the headless Blender render and retained `.blend`. Move,
rotate, scale, duplicate, material controls and animation use the shared scene
history. Importing all mesh parts creates one undo entry. Source bytes and
canonical geometry are hashed for provenance.

Limits: 5 MiB OBJ, 1 MiB total selected MTL, 50,000 source vertices, 100,000
triangles, 96 material parts and 5 MiB canonical geometry per scene. Unsupported
texture maps/transparency are reported; referenced files are never opened.
UVs are preserved, but texture image/material graph authoring is not implemented.
Invalid, degenerate, self-intersecting or nonplanar faces are rejected.

### Edit mesh topology and live modifiers

Select a primitive or imported mesh and enter **Edit mesh**. Conversion creates
an editable control cage while retaining the object's identity, transforms,
material and animation. Vertex and face modes support canvas selection,
Shift-click selection, exact element indices, local coordinate editing and move
handles. A drag previews the cage and commits one evaluated operation on release;
Escape cancels the gesture. Face extrusion creates a cap and side walls;
subdivision shares edge midpoints with neighboring faces; deletion removes
selected faces and unused vertices. Delete/Backspace in Edit mesh acts on face
selection instead of removing the object.

The ordered modifier stack exposes **Mirror**, **Bevel**, **Subdivision**
(Catmull–Clark or Simple), **Solidify**, **Array**, **Decimate**, **Smooth** and
**Simple Deform** (Twist, Bend, Taper or Stretch). Add, adjust, reorder, enable, remove or apply modifiers
inside CINEMATICUM. The installed Blender engine evaluates the actual geometry
before a candidate enters shared undo history. The shaded viewport displays that
evaluated mesh; the retained `.blend` contains the original cage and live
modifiers. Rendering reevaluates the cage and verifies engine version, geometry,
normals and UVs against the saved evaluation. Refresh recomputes an evaluation
after an intentional engine update. Applying the stack reevaluates before baking;
undo restores both the cage and stack.

Edited geometry receives a new canonical hash. Original import identity stays
separate in provenance and source files are unchanged. Vertex-position changes
retain UV corners and seams; topology-changing extrusion, subdivision and
deletion clear them and require reprojection. Selections are bounded to 512
elements; cages to 10,000 vertices, 10,000 faces and 60,000 corners; stacks to
eight modifiers and subdivision to three levels. Array count is 1–64; complexity
admission includes Array/Solidify expansion. Cages and evaluations together share
a 5 MiB scene geometry budget. Evaluation uses one owned Blender worker at a
time, with a 45-second limit per evaluation. Edge tools, sculpting, rigs, shape
keys, geometry nodes and simulation remain missing.

### Edit UV coordinates

After **Edit mesh**, the **UV coordinates** controls project the whole cage or
selected faces using Box atlas, planar XY/XZ/YZ or individual-face mapping.
**Smart unwrap** executes Blender's real smart projection on the whole cage. **Separate selected
faces** creates independent UV links at the selection boundary. **Pack islands**
places connected islands in separate grid cells with margin while preserving
each island's aspect ratio; it does not optimize arbitrary packing or equalize
texel density.

Click or Shift-click UV points, drag them, or select an exact UV index. **UVs of
selected faces** and **Select all UVs** support bounded selections of up to 512
points. Edit the U/V center, **Rotate 90°**, **Mirror U**, or scale the selection
by 0.5×/2×. Arrow keys move 0.01 UV units, or 0.1 with Shift. Escape cancels a
pointer drag. Accepted operations pass through the same evaluated modeling job
and shared undo as mesh edits. Seams and quad/n-gon UV corners survive the actual
Blender cage and retained source. Texture painting, texture-image assignment
and a material shader graph remain separate missing authoring systems.

### Existing Blender scenes

Import an existing `.blend` file, select it in the 3D panel, and choose an
inclusive Blender frame range. The existing camera, scene, lighting, materials,
and animation are rendered to PNG frames and then encoded into an MP4 that is
admitted to the media bin. Add the finished take to the same editing timeline.

The adapter disables scene Python auto-execution and executes its own settings
script. Before rendering, it mutes compositor File Output nodes across every
scene and nested node group, and redirects their supported output paths to the
job's temporary directory. The main composite remains active. This controls
those secondary outputs; it is not an operating-system sandbox for untrusted
Blender files. Render cancellation stops only the child process group owned by
that job.

Imported `.blend` scenes are rendered as supplied; their complete scene data is
not converted into CINEMATICUM's bounded authoring model. The mesh tools above
operate the scene authored in CINEMATICUM. Rigging, sculpting and simulation
interfaces remain unimplemented.
Pack external resources in the source `.blend` before importing it: only the
selected scene file is copied, not a directory of linked assets.

## Local AI video generation

### Managed engine inside Studio

Open **Generate → Local generation setup**, choose **Install local engine**, then
**Start engine**. Choose shot settings and click **Use these settings in this
project**. Back in Generate, enter the prompt, negative prompt and seed, then
choose **Generate media**. The completed actual video enters the same media bin
and can be added to the timeline. Setup and startup are owned, cancellable app
jobs; closing their dialog leaves the job running and reopening it restores
its controls. Native quit first saves edits and checks active jobs. **Keep
Working** leaves those jobs running; **Cancel Jobs and Quit** explicitly cancels
them and stops the owned engine. A shutdown receipt distinguishes that choice
from a signal or an unexpected interruption.

The managed runtime is pinned ComfyUI 0.42.1 with 71 dependency wheels and three
Wan 1.3B model files. A real installation verified all 10,634,173,896 downloaded
bytes, then started the owned MPS process and passed an 11-node core workflow
preflight. Files live below `~/Library/Application Support/CINEMATICUM/Generation`,
separate from the application bundle and any prior ComfyUI installation.
[The runtime lock](generation-runtime-lock.json) records source, model and
dependency identities. Setup requires Apple Silicon, macOS 14+ and a compatible
Python 3.13; it checks free space before downloading and preserves resumable
partials. The core managed workflow uses no custom nodes or paid/API services.

The default shot settings are 480 × 272, 17 frames, 20 sampling steps, guidance 6
and 16 fps, using the upstream Euler sampler and simple schedule. The sampler
choice is saved in the submitted workflow. The earlier UniPC preset produced a
completed but nearly-black normal-size take on the measured M3 Mac; independent
picture checks rejected it. Existing authored workflows are preserved. Apply
**Use these settings in this project** to write the current managed preset.
Custom dimensions use multiples of 16 within 192–832 × 128–480;
length is 9–81 frames in steps of four, and sampling steps are 4–50. These are
accepted parameter bounds, not a performance or quality guarantee on every Mac.

Actual execution is verified for **192 × 128, nine frames at 16 fps, four steps,
seed 42**, completed in **44.410 seconds**. Independent media verification and
native playback each passed **14/14 checks**; their combined acceptance took
1.393 seconds. All nine decoded source frames matched the native canvas, real
byte-range requests served the admitted movie, and Add/Play/Save preserved its
provenance. The test used a copy in an isolated ENGINE TEST project, with no
export or generated-media substitute and no change to the original snapshot.
This verifies the small take's execution and editing path, not production
quality or feature parity with the requested AI products.

Two subsequent normal 480 × 272, 17-frame, 20-step Euler takes completed through
native Generate controls. Both passed 14/14 independent media/provenance/timing
checks. The earlier native playback exposed a final-frame insertion defect;
nearest project-frame quantization now preserves the complete source through
Add-to-timeline and trim edits. Both final native playback runs passed **14/14**,
including all 17 timeline frames, saved provenance and unchanged original media.
The normal workflow is accepted within these settings. The earlier 13/14 result
remains retained. One real 33-frame case also passed inference and native
playback; its generation harness took 928.394 seconds. This establishes one
longer bounded case: 11/11 inference-harness checks, 14/14 independent media
checks and 14/14 native playback checks, with unaltered raw reports retained.

The earlier normal-preset attempt was cancelled when the application terminated
through AppKit; its historical cause remains unknown. The current native
inference acceptance runs repeated actual takes through Generate controls and
independently checks every decoded frame, source hash, request, workflow and
durable job identity. [Verification 0.9.1](VERIFICATION_0_9_1.md) records the
executed results, including rejected attempts. Longer takes, production quality
and sustained production operation require broader acceptance beyond the one
passed 33-frame case.

### Separately configured workflows

Start your existing ComfyUI installation, then use **Check engines** in Studio.
The endpoint defaults to `http://127.0.0.1:8188`. Configure a different endpoint
when starting the server with `COMFYUI_URL` or `--comfy-url`; jobs cannot choose
their own server. An engine check confirms connectivity. **Validate workflow**
additionally checks required nodes, model names, inputs, links, and output
nodes against the running ComfyUI server. Generation repeats this preflight
before submitting a job. Passing preflight does not prove sufficient memory
or successful video execution. The local adapter rejects paid/API nodes.
For the native app, quit Studio first,
then launch its executable with an environment override:

```bash
COMFYUI_URL=http://127.0.0.1:8189 \
  "$HOME/Applications/CINEMATICUM Studio.app/Contents/MacOS/CINEMATICUMStudio"
```

In **Generate**, import a **ComfyUI API-format export**, not a UI graph with
`nodes` and `links`. The **Connect your prompt** dialog shows node IDs, node
names, input names, and existing values. Select the exact positive text input;
optionally select a separate negative text input and an integer seed input.
Leaving either optional selection empty preserves its original workflow value.

Studio writes the following markers into those selected inputs. You can also
prepare these bindings directly in the API JSON; an already marked workflow
imports without the mapping dialog. Only marked inputs change during a run:

| Desired binding | Value in the chosen node input |
|---|---|
| Positive prompt, required | `CINEMATICUM_POSITIVE_PROMPT` |
| Negative prompt, optional | `CINEMATICUM_NEGATIVE_PROMPT` |
| Integer seed, optional | `CINEMATICUM_SEED` as the entire input value |

Text markers may appear within fixed text; the seed marker must occupy the
entire value and becomes a JSON integer. Studio preserves unmarked negative
text and other inputs. The workflow must save a video output (MP4, WebM, or
MOV); image-only outputs are rejected. Models, custom nodes, VRAM, and storage
are supplied by the configured ComfyUI installation. The
checked-in legacy `production/THE_LAST_RENDER/workflows/comfyui-api.json` is a
UI graph and is deliberately rejected instead of reported as ready.

Accepted jobs are submitted once, tracked by their actual prompt ID, downloaded
from the configured server, inspected by FFprobe, and admitted as media. No
success is inferred from a queue receipt. Cancellation targets only the accepted
prompt ID through the server's per-job endpoint. On older servers that return
404 or 405, Studio requests removal of that exact queued prompt; an already
running job may continue. The receipt distinguishes a cancellation request from
confirmed remote cancellation. Studio never calls the global interrupt endpoint.
Waiting is bounded to 30 minutes and each video download to 2 GiB.

Commercial model providers are **not connected in this build**. Runway, Krea,
OpenArt, Magnific, Artlist, Firefly, Google's video models, Luma, Kling, Pika,
FLORA, and Figma Weave need separately implemented and verified adapters with
the account access their published contracts require. No credits are consumed
by installing or testing Studio.

## Automation

The editor has concrete bulk actions: monochrome grading, muting clip audio,
and arranging a track without gaps. The underlying local API supports atomic
typed recipes with `grade`, `volume`, `sequence`, and absolute source-in/output-duration
`trim` actions. Locked tracks reject automation atomically; volume recipes also
update animated volume keys. Source-changing trim recipes reject clips with
measured stabilization or tracked masks until that derived motion is removed.
It has no
shell, `eval`, arbitrary code execution, or claim of a natural-language agent.

Jobs retain their submitted identity during polling. After repeated connection
failures, **Retry status** resumes the same owned job and **Cancel** remains
available. A response from an earlier polling owner cannot overwrite a newer
job's status. Mesh evaluation returns a candidate; project revision and object
identity are checked before one undoable application. Failed, cancelled or stale
evaluations do not change authored geometry. Retrying status does not silently
apply an abandoned modeling result to a changed scene.

A saved project can be rendered from a script without opening the editor:

```bash
python3 scripts/studio/server.py --workspace /path/to/projects \
  --render PROJECT_ID --profile prores
```

The HTTP API's bootstrap response provides a process-local token. Mutating
requests require that token in `X-Cinematicum-Token`; the service rejects
foreign browser origins and invalid Host headers. Supported routes:

| Route | Purpose |
|---|---|
| `GET /api/bootstrap` | Current project, token, engine capabilities, job state |
| `GET/POST /api/projects` | List or create projects |
| `GET/PUT /api/projects/{id}` | Open or save with revision conflict checking |
| `POST /api/projects/{id}/import?name=...` | Stream a media file into this project |
| `GET /api/projects/{id}/media/{asset_id}` | Play imported media; byte ranges supported |
| `GET /api/projects/{id}/media-inventory` | Inspect original and verified proxy inventory |
| `POST /api/projects/{id}/media-proxy` | Queue a frame-clock-verified preview derivative |
| `GET /api/projects/{id}/media-proxy/{asset_id}?long_edge=...` | Play a verified proxy; byte ranges supported |
| `POST /api/projects/{id}/media-relink?asset_id=...` | Restore selected bytes matching the exact original identity |
| `POST /api/projects/{id}/editorial` | Return an unsaved sequence/caption/multicam/audio/timecode edit or caption export |
| `POST /api/projects/{id}/render` | Snapshot and queue preview/H.264/ProRes export |
| `POST /api/projects/{id}/frame-preview` | Render one unsaved timeline frame through the export graph |
| `GET /api/projects/{id}/previews/{hash}.png` | Read a cached actual rendered frame |
| `GET /api/projects/{id}/waveform/{asset_id}?bins=512` | Decode source min/max/RMS waveform data |
| `POST /api/projects/{id}/workflow` | Validate and save API workflow JSON |
| `GET /api/generation-runtime` | Inspect the owned managed runtime without installing or starting it |
| `POST /api/projects/{id}/generation-setup` | Queue verified managed runtime/model installation |
| `POST /api/projects/{id}/generation-start` | Queue owned engine startup and core-workflow preflight |
| `POST /api/projects/{id}/generation-stop` | Stop only the engine owned by this Studio session |
| `POST /api/projects/{id}/generation-workflow` | Save the selected managed shot settings as the project's API workflow |
| `GET /api/projects/{id}/generation-readiness` | Inspect workflow and installed node/model compatibility |
| `POST /api/projects/{id}/generate` | Queue configured ComfyUI generation |
| `POST /api/projects/{id}/scene` | Render an authored scene and preserve editable Blender source |
| `POST /api/projects/{id}/blender` | Render an imported scene |
| `POST /api/projects/{id}/scene/import-obj` | Parse supplied OBJ/MTL into canonical mesh parts without saving |
| `POST /api/projects/{id}/scene/import-camera` | Parse a selected fSpy/COLMAP solved camera without saving |
| `POST /api/projects/{id}/scene/model-mesh` | Queue an owned topology/modifier evaluation and return a candidate |
| `GET /api/imaging-capabilities` | Inspect the optional installed imaging runtime |
| `GET /api/projects/{id}/imaging-catalog` | List actual builtin OCIO config spaces and display views |
| `GET /api/projects/{id}/imaging-sources` | List preserved original RAW sources |
| `POST /api/projects/{id}/imaging-raw-import?name=...` | Preserve and inspect a selected original RAW file |
| `POST /api/projects/{id}/imaging-render` | Queue actual OCIO/RAW/HDR/panorama processing and admit its display image |
| `GET /api/projects/{id}/imaging/outputs/{job}/{filename}` | Download the float master, display image or receipt |
| `POST /api/projects/{id}/tracking-frame` | Decode the actual conformed seed image |
| `POST /api/projects/{id}/tracking` | Measure point motion and retain its JSON receipt |
| `POST /api/projects/{id}/tracking-validate` | Validate imported point samples against the current source |
| `POST /api/projects/{id}/tracking-motion` | Plan independent stabilization without saving |
| `GET /api/projects/{id}/analysis/{job}.png` or `.json` | Read measured analysis output |
| `POST /api/projects/{id}/interchange-export` | Write bounded OTIO cuts, retimes, overlap lanes and editable nested/dissolve compositions |
| `POST /api/projects/{id}/interchange-import` | Return an unsaved validated timeline candidate |
| `POST /api/projects/{id}/automate` | Apply an atomic editing recipe |
| `POST /api/projects/{id}/checkpoint` | Preserve a revision-bound unsaved editor draft |
| `GET/POST /api/projects/{id}/recovery` | List, explicitly recover or discard a draft/version |
| `POST /api/projects/{id}/production-review` | Validate ordered shot requirements and selected sources |
| `POST /api/projects/{id}/production-plan` | Return an unsaved project candidate retaining the plan |
| `POST /api/projects/{id}/production-conform` | Return an unsaved exact-frame cut candidate |
| `POST /api/projects/{id}/production-export` | Write a persistent shot-requirements JSON attachment |
| `POST /api/projects/{id}/archive-export` | Queue a verified portable project archive |
| `POST /api/projects/{id}/archive-restore` | Stream a selected archive and restore a separate project |
| `GET /api/jobs/{id}` | Read progress, errors, and verified output |
| `POST /api/jobs/{id}/cancel` | Cancel the owned local job |

## Editable speed ramps and optical flow

The inspector's **Speed ramp & optical flow** controls author 2–32 linear speed
keys at 0.25×–4× across up to 240 output frames. The original media, rational
source origin and complete curve survive splits, edge trims, undo, saved
projects and archives. Actual bidirectional DIS flow supplies intermediate
pictures, while the selected original stream/channel pair follows a 64-tap
anti-aliased varispeed clock. Gain, pan and output-time fades apply afterward.
Pitch follows speed. Play renders the actual ramp sequence before playback;
the constant-speed live source mixer retains its previous behavior.

This is Standard8 opaque SDR processing, bounded to a 1280-pixel source edge,
921,600 source pixels and at most 16 authored/expanded ramp instances. The
worker refuses High16/Float32 processing, alpha/PQ/HLG sources and unsupported
time/tracking bindings. Slip/slide/roll involving ramps and nonlinear OTIO interchange remain
unsupported. [RETIME.md](RETIME.md) documents the exact map, complete bounds,
quality limits and actual source-bound acceptance.

## Current boundaries

The project stores integer timeline frames with exclusive clip ends and an exact
rational frame rate from 1 to 60. The timeline rendering workspace is SDR; PQ/HLG material is
refused until an explicit conversion is available. Practical limits are 512
assets, 256 clips and 128 titles per sequence, six hours per sequence, and a
maximum canvas area of 33.5 million pixels. The sequence library has the separate
nesting, expanded-instance and total-clip bounds documented above. Timeline controls expose up to 16 video and 16 audio tracks.
Authoring stills have a 45-second processing limit and a 64-image cache. They
are evaluated from the timeline start, so long timelines may need an encoded
preview. Scope values are display-referred SDR RGB, not reference HDR scopes.

The optional still-image worker provides actual OCIO/ACES transforms and float
EXR masters; authored Cycles scenes can also export float EXR sequences and
passes. The separate [Float32 movie candidate](FLOAT_MOVIE_PIPELINE.md) extends
OCIO scene-linear processing across its documented bounded movie operations.
This implementation still lacks HDR finishing, RAW-movie editing,
pitch-preserving variable-speed sound, general automatic tracking
re-identification, roto hierarchy/paint, unrestricted mesh/rig and texture editing,
plugin hosting, general AAF/XML/native-project interchange, a full audio
workstation and a production-scale decoded GPU playback cache. Actual SAM 2.1
segmentation, TAPIR/TAPNext point tracking, paired collaborative editing and measured
multicamera synchronization have the explicit limits in the capability ledger.
Nested OTIO exchange includes the documented retime, overlap and linear-dissolve
operators; arbitrary time/transition plugins remain unsupported. Source
formats that a browser cannot decode can still render through FFmpeg; use an
encoded preview to review them. ProRes is an export format and may require an
external player on some browsers.

The app does not copy or embed the complete interfaces or codebases of the
referenced commercial products, Kdenlive, Natron, Cinelerra-GG, Friction,
Glaxnimate, or Shotcut. One saved project and an actual processing path are
implemented; full feature parity is not claimed.

## Verification

```bash
make studio-test
node --check scripts/studio/web/app.js
node --check scripts/studio/web/editing.js
node --check scripts/studio/web/viewer-tools.js
node --check scripts/studio/web/compositor-ui.js
node --check scripts/studio/web/scene-editor.js
node --check scripts/studio/web/tracking-ui.js
node --check scripts/studio/web/interchange-ui.js
node --check scripts/studio/web/imaging-ui.js
node --check scripts/studio/web/editorial-ui.js
node --check scripts/studio/web/media-management-ui.js
node --check scripts/studio/web/sequence-playback.js
make qc-stack
```

Tests decode exported frames and audio to check timing, gaps, grading,
transparency, chroma key, motion, title fades, audio gain, and ProRes output.
Rational-clock tests inspect every encoded packet timestamp, decoded frame and
48 kHz cut boundary, including reverse and fractional source trims. OTIO tests
include an independent official reader/writer (test-only dependency) and decoded
picture/PCM roundtrips. Tracking tests measure actual motion and re-measure a
stabilized render. Mesh tests inspect real geometry and reopen its Blender source.
Node tests decode branching, output rewiring, animated/rotated/polygon masks, feathering,
master/RGB curves, blend modes, merge alpha, and filtered edges. Timeline tests
measure rendered frames and decoded PCM for retime, reverse, source boundaries,
rotation, easing, fades, stereo balance, track state and waveform statistics.
Scene tests compare JavaScript, Python and Blender animation evaluation. Native
WKWebView acceptance scripts exercise the actual controls and save/export paths;
`test_scene_motion_blender.py` also reopens and evaluates the retained .blend.
`test_multi_source_compositor.py` decodes independent source ranges, hold/gaps,
trim/split domains and source audio isolation. `test_lens_compositor.py` checks
calibration math and actual remapped pixels against an independent inverse.
`test_trim_edits.py` verifies slip/slide/roll timing and source frames;
`test_trim_ui_macos.py` drives real native edits, one-step undo/redo and exports
whose decoded frame identifiers and moving markers are checked independently.
`test_scene_modeling_blender.py` reopens the retained base cage/live stack,
compares evaluated geometry and rendered pixels, and rejects a forged viewport
cache. `test_imaging.py` executes the optional real runtime; its RAW acceptance
requires an actual camera fixture. Native imaging acceptance separates OCIO,
RAW and bracket operations. Test availability is not a passing run: execution
results are recorded separately in versioned verification reports; harness
coverage alone is not a claim that a native run passed.
Adapter tests cover protocol failures, explicit prompt binding, cancellation,
and compositor file-output controls. API tests cover output admission, upload,
save/reopen, revision conflicts, byte-range playback, actual export, and
path/origin/token boundaries. Synthetic
test pictures, tones, and test scenes are test fixtures only, never a film.

The 0.9 acceptance record includes 19 native 3D backend checks, eight native
scene-control stages, four editorial-control stages, 26 roto checks and four
media/proxy-control stages. The media stages independently decode every exported
fixture frame and stereo PCM sample before/after proxy use and exact relinking.
The earlier short Metal harness timed out; the later normal app render completed
in 82.430497 seconds and passed 18 independent checks. Managed setup/start and
the small actual Wan take described above are verified, including 14 independent
media and 14 native playback checks. These are historical 0.9 results; the
current source-sample audio, planar, high16 and normal-generation gates are
recorded separately for 0.9.1.

The earlier 515-test and 543-test runs remain historical source receipts.
After the isolated-worker bytecode fix, the current frozen Linux run passed
**544 tests with zero failures, errors, skips or expected failures**. Its report
elapsed time is 169.194 seconds; wrapper elapsed is 169.301 seconds. All 189
operative files stayed unchanged, actual optional workers and genuine RAW ran,
and the 48 unchanged JavaScript files retain their successful syntax checks.
Historical `4530c54` Studio CI passed 543 tests and 209 manifest files. The
current runtime is published at `81827cf92d159b9619d51000da61ea3c8a6b6ce7`;
its 23 exact-head workflows all passed, while later documentation CI and live [PR #162 checks](https://github.com/kaaffilm/CINEMATICUM/pull/162/checks)
remain separate evidence. Bounded 33-frame inference/playback, production quit,
corrected planar, collected installation verification, canonical launch and
source reconciliation passed. Production chooser Save/public-action Cancel
passed at the stated scope. These passes do not complete the missing systems,
professional workflows or signed distribution. Current THE LAST RENDER film
completion/issuance is not established by this Studio work.
See [Verification 0.9.1](VERIFICATION_0_9_1.md) for current source and native
receipt identities, and
[the unfinished-work register](UNFINISHED_0_9.md) for remaining implementation
and external-access requirements.

Studio writes projects and exports into its own workspace. It does not alter
the pinned GODCUT, the existing film verification commands, or
`CINEMATICUM/CINEMATICUM` issuance records. The production repository's accepted
authority acknowledgement remains in effect.

# CINEMATICUM Studio 0.8

A working local audiovisual editor. Media are imported into an owned project,
edited on a frame-based timeline, previewed, and exported through real render
engines. Timeline, compositor, mixer and 3D authoring are CINEMATICUM controls
sharing one saved project and undo history. FFmpeg and Blender run as headless
processing engines; no external editor interface is embedded or launched.
No missing shot is replaced with filler. Exporting media has no film
issuance effect.

## This upgrade

Studio 0.8 adds recoverable unsaved edits, previous saved versions, portable
project archives, and an integrated production shot-plan workflow. Authored 3D
scenes can retain scene-linear float32 RGBA EXR sequences and depth, normal,
motion-vector, diffuse-color and emission passes alongside their review movie
and editable Blender source. Continuous camera aiming and deformed mesh UV
seams are preserved. OTIO self-roundtrips identify and rebind nested compositor
and title media by bytes; still-image admission and imaging agree on all eight
EXIF orientations. Generation preflight checks installed socket types and
reachable video output, and deleted clips release their playback resources.

These operations use CINEMATICUM's own controls and project data. The release
retains calibrated fSpy/COLMAP camera import, physical camera/material controls,
Cycles rendering, exact rational clocks, animated compositing, measured point
tracking, OBJ/MTL import, Cube LUTs and bounded OpenTimelineIO interchange.
Read the [source comparison and capability audit](CAPABILITY_AUDIT.md) for the
reference-system comparison, and [the capability ledger](capabilities.json) for
the current implemented scope and remaining professional gaps. Execution
evidence for this upgrade is recorded in [verification 0.8](VERIFICATION_0_8.md).

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
Closing the window saves pending timeline edits and waits for its owned local
render jobs to stop. The app still requires installed Python, FFmpeg, and any
optional engines; the installer does not bundle them or create a signed,
notarized distribution.

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
and absolute sample boundaries. NTSC-family timecode is displayed as nominal
**non-drop-frame** timecode, explicitly labeled NDF; it is not wall-clock time.

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
reversed audio, sample-based fades, stereo balance and animated volume. Reverse
audio and multichannel downmix should be reviewed with rendered playback.

Clip position, scale, rotation, opacity and volume can be keyframed, with linear,
hold, ease-in, ease-out and smooth ease-in/out interpolation. Each property uses
its own keys and the base property value at frame zero. Keyframe chips expose
playhead navigation, outgoing interpolation and deletion. Trims and splits preserve the complete animation and fade envelopes, including
hidden keys outside the trimmed range. Editing a fade resets its envelope to
the current clip range. Retiming rescales animation and fade times to integer
output frames.

Space plays/pauses, S splits the selected clip at the playhead, Delete removes
the selection, and Cmd/Ctrl-Z and Cmd/Ctrl-S undo and save. Titles use actual
transparent PNG plates generated from the editor canvas, so the Mac does not
need FFmpeg's optional `drawtext` filter.

## Input color and LUTs

Select a picture clip, open **Color**, then **Input transform, white balance & LUT**.
Choose the source transfer function (Rec.709, sRGB, linear, or LogC3 EI800), source
primaries (Rec.709, Rec.2020, ACEScg, or ARRI Wide Gamut 3), and source/target white
chromaticities. Bradford adaptation and RGB/XYZ matrices run in a float RGBA stage.
The stage encodes Rec.709 before the clip compositor and creative grading.

Import a selected `.cube` file to keep it with the project. The importer accepts
one three-channel 1D table (up to 65,536 rows) or one 3D table (up to 65³), with
finite per-channel input domains. Nearest/linear 1D and nearest/trilinear/
tetrahedral 3D interpolation are available. Tables are canonicalized and addressed
by SHA-256; missing or changed bytes stop validation. The selected LUT runs after
the input conversion, before the compositor. Apply creates one undo entry and
does not autosave. LUT storage persists independently of undo.

Paused frames and export share this processing. Interactive source playback
remains approximate; use **Render preview** to judge moving processed footage.
This is an explicit input-to-SDR stage, not a complete OCIO/ACES display pipeline.
The downstream compositor/delivery remains SDR; RAW development, HDR mastering,
general OCIO configs, combined shaper+3D Cube files and automatic camera
color-space detection are not implemented.

## Calibrated cameras and physical rendering

In **3D**, use **Import camera…** for an fSpy v1 project/export or selected COLMAP
`cameras.txt` and `images.txt`. Review the solved camera, explicit world up axis
and translation scale, then apply it as one undoable camera replacement. Previous
camera animation is replaced; objects and lights remain. No path or photograph
named in an imported document is opened. Camera import keeps orientation/roll,
principal-point offsets and `fx/fy`; source and project aspect ratios must agree.
COLMAP import supports PINHOLE and SIMPLE_PINHOLE only. Distorted camera models
reject with an explicit error; numerical Brown-model utilities are not a footage
undistortion feature. The import does not run a reconstruction or calibration solve.

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
sharpen, chroma-key, RGB curves, rectangle/ellipse/polygon mask, and merge nodes. Connections,
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
ease-out and ease-in/out, with frame navigation and deletion. Polygon path
animation preserves vertex count/order; each completed vertex drag is one undo
entry. Topology changes are disabled while the path is animated. Sharpen amount,
curve control points and chroma color remain static in this release.

Graphs allow up to 32 nodes, exactly one primary clip-source node, and up to eight
additional project-media nodes, with no missing connections or cycles.
A resource limit bounds canvas pixels multiplied by active graph nodes to
268,435,456. Scalar animation has up to 128 keys per channel, polygon paths up to
64; a graph has at most 1,024 keys and 8,192 animated coordinate values.
Disconnected nodes remain editable but are not rendered.

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
accelerates the same calculation. Lensfun profile lookup, fisheye/rational/
anamorphic models, automatic calibration and animated lens parameters remain
unimplemented.

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

**Merge exposure brackets** combines 2–16 already aligned photographs of a static
scene using explicit shutter times and a declared sRGB, Rec.709 or linear
response. Captures must share aperture and ISO. This is radiance merging for a
known response; image alignment, ghost removal and response-curve estimation
remain unimplemented.

Every successful job retains `linear.exr`, `display.png` and `receipt.json`.
The ZIP-compressed float32 RGBA EXR preserves negative and above-one scene
values with explicit alpha semantics. The separate 16-bit sRGB display PNG is
admitted into the normal media bin for editing. The receipt binds the actual
sources, recipe, config/runtime versions and output hashes. The original sensor
file and completed outputs are immutable; changing development settings creates
a new result.

Imported EXR stills require a single RGB/RGBA part and an explicit source color
space when its metadata is insufficient. Develop them before adding their
display result to the SDR timeline. Deep/multipart/arbitrary-channel EXR,
floating-point movie compositing, HDR mastering and a RAW timeline are not
provided by this still-image path.

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
This is a classical FFmpeg
correlation tracker, not SAM 2, TAPIR/TAPNext, planar tracking or a camera solver.

## Exchange cut timelines

Click **Interchange** in the timeline toolbar. Export creates an actual `.otio`
JSON file containing picture/audio tracks, cuts, gaps, references and rational
timing. Media is referenced, not embedded. Embedded video audio is represented
on companion audio tracks. Color, masks, tracking, titles, mixer state and other
CINEMATICUM authoring data remain private namespaced metadata; other editors
receive unprocessed cuts. Warnings identify these differences.

Import a `.otio` file, explicitly map its references to existing imported media
when no verified content hash matches, then **Review timeline**. The preview
reports the candidate's tracks, clips, rate and warnings. **Replace timeline**
applies it with one undo checkpoint; saving remains separate. The importer never
opens external paths/URLs from a document. A changed source edit invalidates
stale private metadata. Nested stacks, transitions, timewarps, reverse, same-track
overlaps and unsupported final gaps are rejected instead of silently flattened.
AAF, Premiere XML, Resolve projects and general OTIO plugin schemas are not
supported. The request/document size limit is 8 MiB.


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

**Render scene** builds the authored scene in Blender using Cycles CPU,
renders actual frames, and admits the encoded movie into the media bin.
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

The ordered modifier stack exposes **Mirror**, **Bevel** and **Subdivision**
(Catmull–Clark or Simple). Add, adjust, reorder, enable, remove or apply modifiers
inside CINEMATICUM. The installed Blender engine evaluates the actual geometry
before a candidate enters shared undo history. The shaded viewport displays that
evaluated mesh; the retained `.blend` contains the original cage and live
modifiers. Rendering reevaluates the cage and verifies engine version, geometry,
normals and UVs against the saved evaluation. Refresh recomputes an evaluation
after an intentional engine update. Applying the stack reevaluates before baking;
undo restores both the cage and stack.

Edited geometry receives a new canonical hash. Original import identity stays
separate in provenance and source files are unchanged. Geometry edits regenerate
normals and currently clear imported UV corners with an explicit message.
Selections are bounded to 512 elements; cages to 10,000 vertices, 10,000 faces
and 60,000 corners; stacks to four modifiers and subdivision to three levels.
Cages and evaluations together share a 5 MiB scene geometry budget. Evaluation
uses one owned Blender worker at a time, with a 45-second limit per evaluation.
Parenting, edge tools, sculpting, UV authoring, rigs, shape keys, geometry nodes
and simulation remain missing.

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
| `POST /api/projects/{id}/render` | Snapshot and queue preview/H.264/ProRes export |
| `POST /api/projects/{id}/frame-preview` | Render one unsaved timeline frame through the export graph |
| `GET /api/projects/{id}/previews/{hash}.png` | Read a cached actual rendered frame |
| `GET /api/projects/{id}/waveform/{asset_id}?bins=512` | Decode source min/max/RMS waveform data |
| `POST /api/projects/{id}/workflow` | Validate and save API workflow JSON |
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
| `POST /api/projects/{id}/imaging-render` | Queue actual OCIO/RAW/bracket processing and admit its display image |
| `GET /api/projects/{id}/imaging/outputs/{job}/{filename}` | Download the float master, display image or receipt |
| `POST /api/projects/{id}/tracking-frame` | Decode the actual conformed seed image |
| `POST /api/projects/{id}/tracking` | Measure point motion and retain its JSON receipt |
| `POST /api/projects/{id}/tracking-validate` | Validate imported point samples against the current source |
| `POST /api/projects/{id}/tracking-motion` | Plan independent stabilization without saving |
| `GET /api/projects/{id}/analysis/{job}.png` or `.json` | Read measured analysis output |
| `POST /api/projects/{id}/interchange-export` | Write a bounded OTIO cut document |
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

## Current boundaries

The project stores integer timeline frames with exclusive clip ends and an exact
rational frame rate from 1 to 60. The timeline rendering workspace is SDR; PQ/HLG material is
refused until an explicit conversion is available. Practical limits are 512
assets, 256 clips, 128 titles, six hours, and a maximum canvas area of
33.5 million pixels. Timeline controls expose up to 16 video and 16 audio tracks.
Authoring stills have a 45-second processing limit and a 64-image cache. They
are evaluated from the timeline start, so long timelines may need an encoded
preview. Scope values are display-referred SDR RGB, not reference HDR scopes.

The optional still-image worker provides actual OCIO/ACES transforms and float
EXR masters; authored Cycles scenes can also export float EXR sequences and
passes. Those features do not extend float processing across the movie
timeline. This implementation still lacks HDR finishing, multicam,
optical-flow retiming, planar/affine tracking, neural segmentation, Bezier roto
with feather points, unrestricted mesh/UV/rig editing, plugin-host
compatibility, general AAF/XML/nested OTIO interchange, a full audio workstation, collaborative
editing, or a production-grade realtime playback cache. Source
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

Studio writes projects and exports into its own workspace. It does not alter
the pinned GODCUT, the existing film verification commands, or
`CINEMATICUM/CINEMATICUM` issuance records. The production repository's accepted
authority acknowledgement remains in effect.

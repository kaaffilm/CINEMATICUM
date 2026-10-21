# CINEMATICUM Studio 0.4

A working local audiovisual editor. Media are imported into an owned project,
edited on a frame-based timeline, previewed, and exported through real render
engines. Timeline, compositor, mixer and 3D authoring are CINEMATICUM controls
sharing one saved project and undo history. FFmpeg and Blender run as headless
processing engines; no external editor interface is embedded or launched.
No missing shot is replaced with filler. Exporting media has no film
issuance effect.

## Open it

Requirements: Python 3.9+, FFmpeg with FFprobe, and either the native macOS app
or a current browser. H.264 export needs FFmpeg's `libx264` encoder; ProRes
needs `prores_ks`. Blender and ComfyUI are optional engines. There are no pip or
npm runtime dependencies. Run these commands from the repository root.

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
Studio's own identifier, and the previous bundle is retained beside the new
one as a backup. Projects default to `~/Movies/CINEMATICUM`; application
updates do not replace that folder. On Linux the default is
`$XDG_DATA_HOME/cinematicum`, or `~/.local/share/cinematicum` when unset.

## Work with real media

1. Import video, audio, still images, or a Blender scene using the file picker or
   by dropping files into the media bin. Imports are copied and content-hashed.
2. Double-click a video, image, or audio asset to add it to the timeline. Drag to
   change its start or layer; use the clip edges or Inspector for exact trims.
3. Add picture and audio tracks with **＋ Video** and **＋ Audio**, up to 16 of
   each. Higher picture layers composite above lower layers. Track mute, solo,
   lock and gain are shared with the Audio mixer. Gaps render black; audio gaps
   render silence. Solo is evaluated separately for picture and audio tracks.
4. Use Color for exposure, contrast, saturation, and temperature. Composite
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

The clip inspector exposes 0.25×–4× speed, reverse of the selected source range,
clip gain, stereo balance and audio fades. Source in points may be fractional
project frames; timeline starts and durations remain integer frames. Speed
changes preserve the selected source range to frame precision. Trim handles
and split account for speed and reverse. Ripple delete closes a gap on the
selected track. Track locking prevents direct clip editing.

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

The graph processes that clip's trimmed source before ordinary clip
transforms, grading, effects, and placement on the timeline. Higher timeline
layers combine different footage sources. The graph currently branches and
recombines one clip; it is not a separate multi-source shot composition.
The paused current-frame renderer evaluates the connected output automatically.
During interactive playback, use Render preview to review the complete node
processing in the encoded movie.

Graphs allow up to 32 nodes, one source, and no missing connections or cycles.
A resource limit bounds canvas pixels multiplied by active graph nodes to
268,435,456. Disconnected nodes remain editable but are not rendered.

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
WebGL lighting is an interactive approximation; Blender produces the rendered
materials, shadows, and lighting. Supported authored scenes contain up to
96 primitive objects, 16 lights, 128 pose keys per object, and 7,200 frames.
Transforms use Z-up coordinates and XYZ Euler rotation. Linear, hold, quadratic
ease-in/out and cubic smooth ease-in/out have matching viewport and render
evaluation. Saved Blender actions retain these curves; camera lens conversion
is baked at integer render frames.

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

The primitive scene editor does not include Blender's mesh editing, rigging,
sculpting, or simulation interface.
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
success is inferred from a queue receipt. Local cancellation stops waiting;
the shared ComfyUI job may continue. Studio does not call ComfyUI's global
interrupt endpoint and therefore does not stop somebody else's job.
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
update animated volume keys. It has no
shell, `eval`, arbitrary code execution, or claim of a natural-language agent.

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
| `POST /api/projects/{id}/automate` | Apply an atomic editing recipe |
| `GET /api/jobs/{id}` | Read progress, errors, and verified output |
| `POST /api/jobs/{id}/cancel` | Cancel the owned local job |

## Current boundaries

The project stores integer timeline frames with exclusive clip ends and an integer
frame rate from 1 to 60. The rendering workspace is SDR; PQ/HLG material is
refused until an explicit conversion is available. Practical limits are 512
assets, 256 clips, 128 titles, six hours, and a maximum canvas area of
33.5 million pixels. Timeline controls expose up to 16 video and 16 audio tracks.
Authoring stills have a 45-second processing limit and a 64-image cache. They
are evaluated from the timeline start, so long timelines may need an encoded
preview. Scope values are display-referred SDR RGB, not reference HDR scopes.

This implementation does not yet provide ACES/OCIO color management,
HDR finishing, fractional project rates, multicam, optical-flow retiming,
tracking/roto, arbitrary mesh editing, plugin-host compatibility,
AAF/XML/OTIO project interchange, a full audio workstation, collaborative
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
make qc-stack
```

Tests decode exported frames and audio to check timing, gaps, grading,
transparency, chroma key, motion, title fades, audio gain, and ProRes output.
Node tests decode branching, output rewiring, rotated/polygon masks, feathering,
master/RGB curves, blend modes, merge alpha, and filtered edges. Timeline tests
measure rendered frames and decoded PCM for retime, reverse, source boundaries,
rotation, easing, fades, stereo balance, track state and waveform statistics.
Scene tests compare JavaScript, Python and Blender animation evaluation. Native
WKWebView acceptance scripts exercise the actual controls and save/export paths;
`test_scene_motion_blender.py` also reopens and evaluates the retained .blend.
Adapter tests cover protocol failures, explicit prompt binding, cancellation,
and compositor file-output controls. API tests cover output admission, upload,
save/reopen, revision conflicts, byte-range playback, actual export, and
path/origin/token boundaries. Synthetic
test pictures, tones, and test scenes are test fixtures only, never a film.

Studio writes projects and exports into its own workspace. It does not alter
the pinned GODCUT, the existing film verification commands, or
`CINEMATICUM/CINEMATICUM` issuance records. The production repository's accepted
authority acknowledgement remains in effect.

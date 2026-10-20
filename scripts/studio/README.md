# CINEMATICUM Studio

## Complete native editor workspaces

Studio 0.3 adds embedded workspaces for the actual Linux applications: Kdenlive,
Shotcut, Cinelerra-GG, Natron, Friction, Glaxnimate, and Blender. Their own editing
interfaces, native project files, plugins bundled by upstream, and render engines
run in an app-owned Docker Desktop container. Xpra streams the desktop and audio
into the CINEMATICUM window. The **Assembly** button returns to Studio's existing
local timeline. These are separately maintained native document models; this
integration does not translate all seven into one lossless timeline format.

Start Docker Desktop, open Studio, and choose **Install editors** once. The
installer downloads the exact packages in `full_runtime/engines.json`, checks
published hashes where available, records a SHA-256 acquisition lock for every
archive, verifies that lock again before extraction, and builds the local image.
Source changes reuse the verified package cache. No privileged container or
Docker socket mount is used. The image and native projects stay on this Mac.

Each project's native documents live in `nativeprojects/PROJECT_ID` inside the
Studio workspace; the editors see that folder as `/projects/PROJECT_ID`.
Imported Studio media is available read-only at `/media`. Save completed media
in `/projects/PROJECT_ID/exports`, then choose **Import exports** to copy and
validate the results into the Assembly media bin. Native documents remain
editable in their originating editor. Saving from the Studio header forwards
the native editor's Save command when its workspace is active.

Closing the Studio window disconnects the viewer and preserves native editor
processes, including unsaved documents, for reopening. Save and close projects
inside their editors before stopping Docker Desktop. Studio does not silently
terminate these documents or another application's containers.

On Apple Silicon this deployment runs Linux x86-64 applications with software
Mesa graphics and CPU rendering. It does not provide Metal/CUDA passthrough,
native capture hardware integration, a reference-quality HDR monitor stream,
or a claim of identical performance to native Mac builds. Friction's selected
upstream release is a release candidate. The commercial AI providers remain
unconnected; their names are not reported as installed engines.

A working local audiovisual editor. Media are imported into an owned project,
edited on a frame-based timeline, previewed, and exported through real render
engines. No missing shot is replaced with filler. Exporting media has no film
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
3. Put picture layers on V1–V4 and audio on A1–A2. Higher picture layers composite
   above lower layers. Gaps render black, and audio gaps render silence.
4. Use Color for exposure, contrast, saturation, and temperature. Composite
   provides an editable node graph as well as clip transforms and effects.
   Add titles with position, size, color, duration, and fades.
5. Source preview is interactive and approximate. Render preview evaluates the
   complete FFmpeg composition and plays the actual encoded output.
6. Save the project, or export H.264 MP4 or ProRes MOV. Export snapshots retain
   the exact project revision and output SHA-256; editing later does not alter a
   running render.

Space plays/pauses, S splits the selected clip at the playhead, Delete removes
the selection, and Cmd/Ctrl-Z and Cmd/Ctrl-S undo and save. Titles use actual
transparent PNG plates generated from the editor canvas, so the Mac does not
need FFmpeg's optional `drawtext` filter.

## Node compositing

Select a picture clip and open **Composite**. Add and connect grade, blur,
sharpen, chroma-key, rectangle/ellipse mask, and merge nodes. Connections,
parameters, node positions, and the chosen output are saved with the clip.
The **Masked correction** action creates an editable branch: the original
picture is merged with a graded, masked version of itself. Masks support
feathering and inversion; merge inputs are ordered background, foreground.

The graph processes that clip's trimmed source before ordinary clip
transforms, grading, effects, and placement on the timeline. Higher timeline
layers combine different footage sources. The graph currently branches and
recombines one clip; it is not a separate multi-source shot composition.
Render preview evaluates the connected output and plays the resulting file.
The interactive source viewer does not evaluate graph nodes.

Graphs allow up to 32 nodes, one source, and no missing connections or cycles.
A resource limit bounds canvas pixels multiplied by active graph nodes to
268,435,456. Disconnected nodes remain editable but are not rendered.

## Create and render 3D scenes

Open **3D** to author a scene inside Studio. Add cubes, spheres, planes, and
cylinders; edit object transforms and materials; position lights and the
render camera; and set pose keyframes. The offline WebGL viewport supports
orbit, pan, zoom, object selection, camera framing, and animation playback.
Scene recipes are stored in the same project and participate in undo and save.

**Render scene** builds the authored scene in Blender using Cycles CPU,
renders actual frames, and admits the encoded movie into the media bin.
The completed job also offers the editable `.blend` source. Add the movie to
the timeline to edit and composite it with footage, sound, and titles.
WebGL lighting is an interactive approximation; Blender produces the rendered
materials, shadows, and lighting. Supported authored scenes contain up to
96 primitive objects, 16 lights, 128 pose keys per object, and 7,200 frames.
Transforms use Z-up coordinates and linear XYZ Euler interpolation.

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
typed recipes with `grade`, `volume`, `sequence`, and `trim` actions. It has no
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
| `POST /api/projects/{id}/workflow` | Validate and save API workflow JSON |
| `GET /api/projects/{id}/generation-readiness` | Inspect workflow and installed node/model compatibility |
| `POST /api/projects/{id}/generate` | Queue configured ComfyUI generation |
| `POST /api/projects/{id}/scene` | Render an authored scene and preserve editable Blender source |
| `POST /api/projects/{id}/blender` | Render an imported scene |
| `POST /api/projects/{id}/automate` | Apply an atomic editing recipe |
| `GET /api/jobs/{id}` | Read progress, errors, and verified output |
| `POST /api/jobs/{id}/cancel` | Cancel the owned local job |

## Current boundaries

The project stores integer frames with exclusive clip ends and an integer
frame rate from 1 to 60. The rendering workspace is SDR; PQ/HLG material is
refused until an explicit conversion is available. Practical limits are 512
assets, 256 clips, 128 titles, six hours, and a maximum canvas area of
33.5 million pixels. Timeline controls show four video and two audio tracks.

This first implementation does not yet provide ACES/OCIO color management,
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
node --check scripts/studio/web/compositor-ui.js
node --check scripts/studio/web/scene-editor.js
make qc-stack
```

Tests decode exported frames and audio to check timing, gaps, grading,
transparency, chroma key, motion, title fades, audio gain, and ProRes output.
Node tests decode branching, output rewiring, masks, feathering, merge alpha,
and filtered edges. Scene tests validate recipes and generated Blender source.
Adapter tests cover protocol failures, explicit prompt binding, cancellation,
and compositor file-output controls. API tests cover output admission, upload,
save/reopen, revision conflicts, byte-range playback, actual export, and
path/origin/token boundaries. Synthetic
test pictures, tones, and test scenes are test fixtures only, never a film.

Studio writes projects and exports into its own workspace. It does not alter
the pinned GODCUT, the existing film verification commands, or
`CINEMATICUM/CINEMATICUM` issuance records. The production repository's accepted
authority acknowledgement remains in effect.

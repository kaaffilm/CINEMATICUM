# CINEMATICUM Studio

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
4. Use Color for exposure, contrast, saturation, and temperature. Composite adds
   position, scale, rotation, opacity, keyframes, blur, sharpening, vignette, and
   chroma key. Add titles with position, size, color, duration, and fades.
5. Source preview is interactive and approximate. Render preview evaluates the
   complete FFmpeg composition and plays the actual encoded output.
6. Save the project, or export H.264 MP4 or ProRes MOV. Export snapshots retain
   the exact project revision and output SHA-256; editing later does not alter a
   running render.

Space plays/pauses, S splits the selected clip at the playhead, Delete removes
the selection, and Cmd/Ctrl-Z and Cmd/Ctrl-S undo and save. Titles use actual
transparent PNG plates generated from the editor canvas, so the Mac does not
need FFmpeg's optional `drawtext` filter.

## Blender

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

This is a scene-rendering integration; Studio does not yet include Blender's
interactive modeling, rigging, sculpting, or simulation interface.
Pack external resources in the source `.blend` before importing it: only the
selected scene file is copied, not a directory of linked assets.

## Local AI video generation

Start your existing ComfyUI installation, then use **Check engines** in Studio.
The endpoint defaults to `http://127.0.0.1:8188`. Configure a different endpoint
when starting the server with `COMFYUI_URL` or `--comfy-url`; jobs cannot choose
their own server. An engine check confirms connectivity, not that the required
models or video workflow are installed. For the native app, quit Studio first,
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
| `POST /api/projects/{id}/generate` | Queue configured ComfyUI generation |
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
tracking/roto, a node compositor, a full 3D editor, plugin-host compatibility,
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
make qc-stack
```

Tests decode exported frames and audio to check timing, gaps, grading,
transparency, chroma key, motion, title fades, audio gain, and ProRes output.
Adapter tests cover protocol failures, explicit prompt binding, cancellation,
and compositor file-output controls. API tests cover output admission, upload,
save/reopen, revision conflicts, byte-range playback, actual export, and
path/origin/token boundaries. Synthetic
test pictures, tones, and test scenes are test fixtures only, never a film.

Studio writes projects and exports into its own workspace. It does not alter
the pinned GODCUT, the existing film verification commands, or
`CINEMATICUM/CINEMATICUM` issuance records. The production repository's accepted
authority acknowledgement remains in effect.

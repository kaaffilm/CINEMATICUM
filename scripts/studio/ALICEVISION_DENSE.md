# Meshroom dense reconstruction adapter

`meshroom_dense` is a separate typed operation on the existing project-owned
reconstruction job route. It executes the complete official photogrammetry
graph: camera initialization, feature extraction/matching, SfM, dense depth-map
estimation/filtering, meshing/filtering, UV texturing and publication. It does
not replace the separately accepted CPU COLMAP sparse solver.

The upstream pipeline is copied without changes from AliceVision 3.3.0 commit
`928bac2689461ffb6f0174609f983a16bdbd2b30`,
`meshroom/photogrammetry.mg`, SHA-256
`b9ca66655bb4fb6eacff1695c0502d17c71c29f00884fe4d2a522a4c9d7edde4`.
It targets Meshroom 2025.1.0 commit
`024b6f398c67bec4968a29a2c5744e49e2bab9b8`.
The copied graph remains under MPL-2.0; its license is preserved in
`alicevision-graph-LICENSE.md`.

The configured absolute `CINEMATICUM_MESHROOM_BATCH` entrypoint and its sibling
`meshroom_compute` (or explicit `CINEMATICUM_MESHROOM_COMPUTE`) run in owned
temporary directories, including upstream CameraInit temporary files. `--help` checks the required CLI interface. Entry-point
hashes are bound before/after execution; this does not certify every library or
binary in an external distribution. Meshroom has no `--version` flag in the
pinned release. The saved graph's node versions, required links, complete
photograph inventory and fixed output parameters are checked before computing
the Publish node and all its dependencies.

The initialization call uses `--compute no`; upstream camera initialization
still executes during that call. The actual computation is
`meshroom_compute <configured.mg> --cache <owned-cache> --toNode Publish_1`.
The adapter requests 4× depth-map downscaling and 2048-pixel PNG texture atlases
by default; its typed recipe supports downscale 2/4/8/16 and atlas side
1024/2048. PNG must be requested explicitly because upstream's 2025.1 default
is EXR. Photographs remain unchanged and must match their admitted hashes and
sizes before and after execution.

Bounds are 3–48 photos, 16 megapixels per photo, 128 megapixels/512 MiB input,
15 minutes, 8 GiB/20,000 files of scratch and 512 MiB published artifacts.
Cancellation and bounds terminate the owned process group, including upstream
children. These are application execution/output bounds, not a claim that the
external engine's GPU or per-process memory is confined by an OS sandbox.

Acceptance validates nonempty finite mesh geometry, actual UV indices, owned
material/texture dependencies, PNG checksums and bounded decoded pixel streams,
and source-bound solved camera records with finite orthonormal poses and valid
lens calibration. Outputs are `textured-mesh.zip`, `pipeline.mg`, `cameras.sfm`,
`alicevision.json` and `provenance.json`. The OBJ export flips native Y and Z (diag[1, -1, -1]); the saved camera poses
retain AliceVision native coordinates. That conversion is explicit in metadata.
Metric scale remains unresolved; editable scene conversion is a separate operation.
The saved execution graph retains job-local paths. Replaying it requires
rebuilding the pinned graph against the recorded admitted photograph bytes.

The included tests cover typed recipes, graph wiring, source/output contracts,
surface/texture/camera validation, scratch limits and cancellation. Parser
fixtures are explicitly labelled ENGINE TEST data. They are not reconstructed
photographs or engine acceptance. Actual sustained reconstruction and capture
quality remain unaccepted until a compatible real runtime and real image set
complete the workflow. The pinned stable CUDA 12 binaries target Linux/Windows;
an Apple Silicon Mac does not acquire dense GPU support from this adapter.
Newer unreleased SYCL/Metal work requires its own source pin and acceptance.

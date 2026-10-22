# Spatial authoring and reconstruction: source review

Reviewed 2026-10-21. This review examines public, official source and documentation. It distinguishes code that was inspected from capabilities implemented in CINEMATICUM and from acceptance checks that still require the real engine. The inspected revisions are fixed below; a website's current documentation can describe a different revision.

## Reproducible source baseline

| System | Inspected branch and commit | Source landmarks |
| --- | --- | --- |
| Blender | `main` · [`fbe82a46101643c5cf8d7ab331d6a47566008fa7`](https://github.com/blender/blender/tree/fbe82a46101643c5cf8d7ab331d6a47566008fa7) | `source/blender/io/wavefront_obj/importer/obj_import_file_reader.cc`, `obj_import_mesh.cc`, `obj_import_mtl.cc` |
| COLMAP | `main` · [`880654712f8f8e2196ec15b035b386b2b55f4502`](https://github.com/colmap/colmap/tree/880654712f8f8e2196ec15b035b386b2b55f4502) | `doc/format.rst`, `src/colmap/scene/reconstruction_io_text.cc`, `src/colmap/controllers/incremental_pipeline.cc` |
| AliceVision | `develop` · [`7aea32b71fe0726bfb75c4bbcb2105f55d897759`](https://github.com/alicevision/AliceVision/tree/7aea32b71fe0726bfb75c4bbcb2105f55d897759) | `src/software/pipeline/main_incrementalSfM.cpp`, `main_depthMapEstimation.cpp`, `main_meshing.cpp` |
| Meshroom | `develop` · [`65b5f6cdad2aa57d8a383549e166826b3f3b8670`](https://github.com/alicevision/Meshroom/tree/65b5f6cdad2aa57d8a383549e166826b3f3b8670) | `README.md`, `INSTALL_PLUGINS.md`, `meshroom/core/graph.py`, `meshroom/core/desc/node.py` |

Repository metadata, branch object hashes and the listed source files were retrieved through the GitHub connector. Documentation was checked separately. No repository was forked, changed or published in this review.

## What these systems actually do

Blender is a general scene-authoring and rendering system. Its OBJ importer turns interchange geometry into editable mesh data, objects and materials. COLMAP estimates camera geometry and sparse structure from image observations and can continue into dense reconstruction. AliceVision provides photogrammetry algorithms and pipeline executables. Meshroom supplies graph execution, dependency tracking, caching and user interaction around node plugins. Treating their names as interchangeable features would obscure the actual work required. [Blender OBJ documentation](https://docs.blender.org/manual/en/4.1/files/import_export/obj.html), [COLMAP CLI](https://colmap.github.io/cli.html), [AliceVision](https://alicevision.org/), [Meshroom README at the inspected revision](https://github.com/alicevision/Meshroom/blob/65b5f6cdad2aa57d8a383549e166826b3f3b8670/README.md).

| Concern | Evidence in upstream source | Consequence for CINEMATICUM |
| --- | --- | --- |
| Geometry interchange | Blender separates face-corner vertex, normal and texture-coordinate indices; negative indices are resolved against arrays available at the face. | The project must store indexed geometry and corner attributes, rather than a label saying that a model was imported. |
| Native scene data | `MeshFromGeometry::create_mesh` constructs vertices, faces, edges, UVs and normals; `create_mesh_object` applies object/material conventions. | Imported geometry must reach both the authoring viewport and the saved Blender scene with the same topology and transform. |
| Material dependencies | Blender's MTL loader searches several filesystem locations for referenced images. | CINEMATICUM's web upload must only consume explicitly supplied data. It must never turn an untrusted `mtllib` or texture name into a filesystem read. |
| Structure from motion | COLMAP's incremental pipeline loads a database, selects/initializes image pairs, registers images and refines a reconstruction. | Importing already solved points and camera poses does not implement feature matching, pose estimation, triangulation or bundle adjustment. |
| Dense geometry | AliceVision fuses observations/depth data and constructs a mesh through graph processing and postprocessing. | A point cloud is not equivalent to a reconstructed surface, texture atlas or completed asset. |
| Job execution | Meshroom nodes build commands, run owned processes with logs, report return codes and cache outputs. | A job is complete only when the real worker output is validated and admitted to the shared project. |

### Blender: the important interchange boundary

In [`obj_import_file_reader.cc`](https://github.com/blender/blender/blob/fbe82a46101643c5cf8d7ab331d6a47566008fa7/source/blender/io/wavefront_obj/importer/obj_import_file_reader.cc), `parse_vertex_index` handles relative negative indices and validates array bounds. Position, normal and UV readers remain separate. Object and group handling creates geometry partitions. These distinctions matter: flattening OBJ's `v/vt/vn` corner tuples into one vertex index would lose UV seams and split normals.

[`obj_import_mesh.cc`](https://github.com/blender/blender/blob/fbe82a46101643c5cf8d7ab331d6a47566008fa7/source/blender/io/wavefront_obj/importer/obj_import_mesh.cc) validates mesh construction and repairs some invalid faces. CINEMATICUM chooses explicit rejection for ambiguous, degenerate, nonplanar or self-intersecting faces instead of inventing repaired topology. Concave simple polygons need a real triangulation algorithm; a triangle fan can fill regions outside the polygon. The independent parser uses bounded ear clipping and preserves the original winding and corner associations.

[`obj_import_mtl.cc`](https://github.com/blender/blender/blob/fbe82a46101643c5cf8d7ab331d6a47566008fa7/source/blender/io/wavefront_obj/importer/obj_import_mtl.cc) includes `load_texture_image` and material-to-node socket mapping. CINEMATICUM initially supports solid diffuse color, roughness and metalness. It reports texture-map references and preserves UV data, but does not claim to import those images. One OBJ group with multiple materials becomes separate editable mesh parts, because CINEMATICUM's current material control belongs to one object. This retains authored material assignment without silently reducing all parts to one color.

The generated Blender script creates data with [`Mesh.from_pydata`](https://docs.blender.org/api/current/bpy.types.Mesh.html), sets per-corner UVs/custom normals and then applies the existing scene transforms, materials and keyframes. It does not ask an external application's UI to import anything. The saved `.blend` contains the actual geometry, a copy of the scene recipe and geometry/source hashes. The WebGL preview consumes the same canonical geometry. Its lighting remains an approximation; the saved headless Cycles render is the render artifact.

OBJ alone does not carry the full Blender scene model. It is not a replacement for rigs, modifiers, constraints, simulations, cameras, light rigs or hierarchical animation. These limitations are documented in the [official OBJ manual](https://docs.blender.org/manual/en/4.1/files/import_export/obj.html). Support for mesh interchange therefore closes one concrete gap, rather than establishing Blender feature parity.

### COLMAP: solved geometry has precise conventions

The [official output format](https://colmap.github.io/format.html) and pinned [`reconstruction_io_text.cc`](https://github.com/colmap/colmap/blob/880654712f8f8e2196ec15b035b386b2b55f4502/src/colmap/scene/reconstruction_io_text.cc) define several facts that an importer must preserve:

- IDs are identifiers and need not be contiguous array offsets.
- Image poses use a Hamilton quaternion and translation for a world-to-camera transform. Camera center is `-RᵀT`.
- Camera coordinates are X right, Y down and Z forward. CINEMATICUM uses a Z-up world and a target-based camera; a conversion must state its basis explicitly.
- `images.txt` uses two records per image. The second can be empty; the name at the end of the first record can contain whitespace.
- Sparse models have distinct cameras, registered images, 3D points and observation tracks. New models may also include rigs and frames, while legacy files remain supported.
- Intrinsic models are not interchangeable. A vertical FOV and centered principal point cannot exactly represent arbitrary lens distortion, off-center intrinsics or every COLMAP camera model.

[`IncrementalPipeline::Run`, `Reconstruct` and `InitializeReconstruction`](https://github.com/colmap/colmap/blob/880654712f8f8e2196ec15b035b386b2b55f4502/src/colmap/controllers/incremental_pipeline.cc) show why loading a text model is not reconstruction. The solver consumes matches and camera/image data, initializes a viable pair and performs iterative registration/refinement. A future CINEMATICUM reconstruction worker must expose actual stage progress, preserve the input/output association and inspect reprojection/registration results. A fabricated point cloud, a sample asset or a success flag after launching a process would not satisfy that requirement.

The [current CLI documentation](https://colmap.github.io/cli.html) gives separate feature extraction, matching, mapping, undistortion, stereo and fusion stages. It also documents CPU settings for feature extraction/matching and cooperative cancellation. Hardware availability must be checked for the selected stage and built binary; it should not be inferred from the presence of a product name.

### AliceVision: sparse, dense and meshing stages are separate

[`main_incrementalSfM.cpp`](https://github.com/alicevision/AliceVision/blob/7aea32b71fe0726bfb75c4bbcb2105f55d897759/src/software/pipeline/main_incrementalSfM.cpp) configures feature/match inputs, tracks and bundle adjustment. The [StructureFromMotion manual](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/StructureFromMotion.html) describes initial-pair selection, incremental camera registration, triangulation and refinement. These are computation stages, not UI widgets.

[`main_meshing.cpp`](https://github.com/alicevision/AliceVision/blob/7aea32b71fe0726bfb75c4bbcb2105f55d897759/src/software/pipeline/main_meshing.cpp) constructs dense SfM observations, runs graph filling/binarization and meshing, postprocesses the result and writes a real mesh file. The [Meshing manual](https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/nodes/Meshing.html) discusses depth fusion, spatial partitioning, Delaunay tetrahedralization and graph-cut extraction. Skipping dense data for a draft has different output quality and is not equivalent to completed photogrammetry.

The inspected [`main_depthMapEstimation.cpp`](https://github.com/alicevision/AliceVision/blob/7aea32b71fe0726bfb75c4bbcb2105f55d897759/src/software/pipeline/main_depthMapEstimation.cpp) includes both CUDA and SYCL compile-time paths. Older documentation that describes a CUDA-only depth pipeline should not be applied to this revision without qualification. This does not establish a working macOS/SYCL build; that would require a verified engine, driver and actual acceptance run. CINEMATICUM must report the engine it actually executed.

### Meshroom: lessons from a graph runtime

At the inspected revision, Meshroom's [README](https://github.com/alicevision/Meshroom/blob/65b5f6cdad2aa57d8a383549e166826b3f3b8670/README.md) describes a plugin-driven graph framework. [`INSTALL_PLUGINS.md`](https://github.com/alicevision/Meshroom/blob/65b5f6cdad2aa57d8a383549e166826b3f3b8670/INSTALL_PLUGINS.md) describes plugin node/template locations and `MESHROOM_PLUGINS_PATH`. Assuming an old monolithic `meshroom/nodes/aliceVision` directory would misidentify the current architecture.

[`GraphModification`](https://github.com/alicevision/Meshroom/blob/65b5f6cdad2aa57d8a383549e166826b3f3b8670/meshroom/core/graph.py) groups graph changes before updating dependencies. [`CommandLineNode`, `processChunk` and `executeChunkCommandLine`](https://github.com/alicevision/Meshroom/blob/65b5f6cdad2aa57d8a383549e166826b3f3b8670/meshroom/core/desc/node.py) separate declarative attributes from owned command execution, working directories, logs, cleanup and completion state. CINEMATICUM already has owned render jobs; geometry import must use its existing project history, not create a second document or a second application's state.

## Implementation scope and remaining gaps

The concrete upgrade is a data-only OBJ importer feeding one project recipe and the existing own-interface 3D authoring tools. The import endpoint parses supplied UTF-8 OBJ/MTL text and returns canonical objects; the scene editor appends them in one undoable checkpoint. Transforms, solid materials, camera/light animation and object keys remain shared with primitives. Original bytes are hashed before axis/scale conversion. The parser applies numeric, topology, file-size, object-count and aggregate-geometry limits before saving or launching an engine. Filesystem references in uploaded text are never followed.

The unit tests must inspect topology, concave polygon area, winding, negative indices, UV seams, smoothing/custom normals, material partitions, provenance, bounds and malformed input. Renderer-boundary tests must inspect the generated data. A separate real Blender replay test must reopen the saved scene and check actual vertices/triangles/UVs/normals/materials, animation and decoded rendered frames. A fixture or generated Python script alone is not render proof.

### Implemented admission limits and verification

The importer is implemented in `spatial_import.py`, integrated into `scene.py` and the own-interface `web/scene-editor.js`. The server route parses supplied data; the browser performs the one history checkpoint. OBJ input is capped at 5 MiB, up to eight selected MTL files at 1 MiB combined, 50,000 source vertices, 100,000 triangles and 96 object/material parts. Faces are limited to 64 corners and input lines to 16,384 characters. Converted coordinates must fit within ±1,000 scene units. Across a scene, imported mesh data must fit within 5 MiB and the aggregate vertex/triangle limits; duplication is checked too. These are explicit current implementation limits, not upstream limits.

Unsupported geometry directives, invalid indices, nonfinite coordinates, zero normals, invalid polygons and directory/URL material-library references fail admission. MTL images are never opened. Solid material color, roughness and metalness are retained; opacity and unsupported material attributes produce visible warnings. Linear diffuse color is represented through the scene's existing 8-bit sRGB color control, so this is not a lossless general material interchange. UVs and normals retain independent corner indices. The saved mesh carries a canonical geometry digest plus original UTF-8 source and selected MTL digests.

| Acceptance | Source command | Status at this implementation checkpoint |
| --- | --- | --- |
| Parser, mesh schema, geometry budget, source hashes, numeric/path rejection, viewport geometry and transformed ray intersections; existing scene/motion regressions | From `scripts/studio`: `python3 -m unittest test_spatial_import test_scene -v` | 29 tests passed in the Linux development workspace. Process-fixture tests are labeled as boundary tests. |
| Browser/Python syntax | `node --check scripts/studio/web/scene-editor.js`; `node --check scripts/studio/macos/MeshImportSmoke.js`; Python `py_compile` on the spatial files | Passed. |
| Native own-interface mesh import | `python3 scripts/studio/test_mesh_import_ui_macos.py --binary <compiled SmokeTest.swift> --output <evidence>` | Harness supplied; actual macOS run required. It uses a real FileList, validates one-step undo/redo, reads real WebGL pixels and independently inspects the saved project. |
| Saved Blender mesh and real encoded output | `python3 scripts/studio/test_spatial_blender.py --output <evidence>` | Harness supplied; actual Blender run required. It renders three frames at 24000/1001, decodes them, reopens `.blend` data and checks topology, corner UVs/normals, materials, hashes and animated transforms. |

The standalone scene renderer now uses the shared rational timebase: nominal Blender FPS plus `fps_base`, and the exact numerator/denominator for FFmpeg image-sequence encoding. Scene-motion interpolation remains shared between authoring, rendered frames and the saved `.blend` animation. The previous owner-specific Blender action-slot fix is preserved so camera lens baking cannot overwrite another owner's easing curves.

Remaining gaps include textures and general material graphs, editable vertex/edge/face topology, armatures and skinning, arbitrary modifiers, subdivision authoring, simulations, robust scene interchange beyond this subset, camera-distortion models and a tested SfM/MVS solver pipeline. Importing already solved COLMAP data, if subsequently added, must be labeled as such and never presented as reconstructing images. Broader feature parity requires these systems to be designed, implemented and accepted separately.

## Source reuse boundary

The inspected Blender importer files carry `GPL-2.0-or-later` SPDX notices; the inspected COLMAP reconstruction reader carries `BSD-3-Clause`; the inspected AliceVision pipeline sources carry MPL 2.0 notices, and Meshroom references MPL v2. This report records the notices present in inspected files, not a repository-wide legal conclusion. The CINEMATICUM parser is independently written against the interchange conventions and uses the installed Blender engine through its data API. No upstream source implementation is pasted into the app, and no capability is attributed to a bundled engine that was not actually available and exercised.

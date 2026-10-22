# Mesh topology and live modifier evaluation

This increment adds editable control geometry to CINEMATICUM's own 3D workspace.
The application owns selection, coordinate controls, extrusion, subdivision,
deletion, the modifier stack and undo. The installed Blender engine evaluates
the exact Mirror, Bevel and Subdivision result that the application's shaded
viewport displays. The retained Blender source contains the base cage and live
modifiers, and must reproduce the saved viewport geometry before rendering.

This is a bounded modeling system, not parity with Blender's full modeling,
sculpting, geometry nodes, rigging, UV editing or simulation systems.

## Primary source inspection

Reviewed Blender source at commit
[`1f7f1f75140c2832ec922210f29dfffbfaee3b73`](https://github.com/blender/blender/tree/1f7f1f75140c2832ec922210f29dfffbfaee3b73).
The source pin identifies the implementation reviewed. Each real evaluation
separately records the installed binary's `bpy.app.version_string`.

| Source | Contract that matters here | Implementation decision |
|---|---|---|
| [`MOD_mirror.cc`](https://github.com/blender/blender/blob/1f7f1f75140c2832ec922210f29dfffbfaee3b73/source/blender/modifiers/intern/MOD_mirror.cc) | Axis operations run in order; merging acts on the evaluated mesh; bisect and flip have independent axis properties. | Expose a local axis, origin bisect, opposite-side choice and bounded merge distance. Build a genuine Mirror modifier and evaluate its geometry. |
| [`MOD_bevel.cc`](https://github.com/blender/blender/blob/1f7f1f75140c2832ec922210f29dfffbfaee3b73/source/blender/modifiers/intern/MOD_bevel.cc) | Bevel uses a mesh topology operator with width interpretation, segments and angle limits. Its result depends on adjacency. | Use the actual engine's edge bevel with offset width, angle limit and overlap clamping. A shader highlight or duplicated edge would not implement this behavior. |
| [`MOD_subsurf.cc`](https://github.com/blender/blender/blob/1f7f1f75140c2832ec922210f29dfffbfaee3b73/source/blender/modifiers/intern/MOD_subsurf.cc) | Viewport and render may request different subdivision levels; tessellation is evaluated from control topology. | Set both levels identically, expose Catmull–Clark and Simple, retain polygon control faces, and compare actual evaluated triangles. |
| [Blender Mirror manual](https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/mirror.html) | Mirroring is defined in local object axes around its origin. | UI calls the axis local; there is no implied arbitrary mirror-object support. |
| [Blender Subdivision Surface manual](https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/subdivision_surface.html) | Subdivision increases surface topology and can smooth the shape. | UI distinguishes a topology edit from a nondestructive subdivision modifier. |

Source inspection informed the public API contract; Blender's implementation
files were not copied into CINEMATICUM. The native helper calls the installed
engine through its normal Python mesh/modifier interfaces.

## Authored data and provenance

Legacy primitives and imported triangle meshes remain valid. Entering Edit mesh
converts a primitive into a canonical indexed control cage, or gives an imported
mesh an editable cage without changing the caller's source object. The object
retains its ID, transform, material and pose keys.

The optional `modeling` record contains:

- `version: 1`.
- `faces`: ordered control polygons referencing `mesh.vertices`.
- `origin`: the original primitive type, or the original canonical geometry
  digest and explicitly supplied OBJ source record.
- `modifiers`: an ordered, bounded list of supported modifier specifications.
- `evaluation`: a key binding the base geometry digest, control faces and
  normalized modifier stack; the actual Blender version; and the canonical
  evaluated mesh.

`mesh` remains the canonical control geometry. Its triangle representation is
deterministically ear-clipped in the dominant-plane projection, permitting
nonplanar subdivision control faces while rejecting crossed polygon edges.
The shaded viewport uses the engine's evaluated geometry, including its actual
triangulation and corner normals. Picking control faces uses the control cage.

An edited import does not continue to claim that its current geometry is the
original source file. Source name, source bytes digest, material source digests,
import axis, scale and original mesh digest move into `modeling.origin`.
Geometry operations regenerate the authored canonical digest. They never write
to or reopen an OBJ/MTL source path. Topology edits rebuild normals and clear
imported UV corners, with an explicit message in the editor.

## Actual editing behavior

Vertex and face modes use the real viewport projection and ray intersections.
Click selects an element; Shift-click adds or removes it. The inspector supports
an exact element index and local coordinates. Move handles convert their world
translation into the object's local coordinates, including rotation and
nonuniform scale. A gesture sends one operation when released; Escape cancels
the cage preview. The returned evaluated candidate enters shared project history
as one undo operation.

Face extrusion creates a displaced cap and side walls. Deleting faces removes
only those polygons and compacts unused positions. Face subdivision reuses edge
midpoints and inserts them into neighbouring faces, avoiding disconnected
T-junctions. Triangles split into four triangles; quads split into four quads;
larger polygons split around a center. This topology operation preserves the
surface positions. Smoothing belongs to the separate subdivision modifier.

The modifier inspector supports addition, parameter changes, ordering, enable,
removal, refresh and application. Changes are evaluated before committing.
Applying the stack first reevaluates the original cage, then creates a new
editable cage from that actual result. A stored preview alone is insufficient
evidence to bake geometry. Undo restores the original cage and full stack.

## Runtime and replay guarantees

`model_mesh({object, operation}, cancel_event=None)` produces a candidate without
saving the project. The server runs it as an owned cancellable job. The editor
checks the project revision and original object identity before applying its
result. A changed project, cancellation or failed geometry evaluation leaves the
authored scene unchanged.

The worker accepts data only. It uses an owned temporary directory, a fixed
generated script, the installed Blender executable, a 45-second evaluation
timeout, two engine threads and one simultaneous modeling evaluator. It starts
with factory settings and disabled file auto-execution. No supplied paths,
scripts, expressions, geometry-node programs or external asset references are
executed.

The retained render builds the cage and actual modifier stack again. It checks
the installed Blender version, evaluated triangle/index arrays, vertex
coordinates, corner normals and UVs against the saved viewport mesh. Geometry
differences fail before output rendering. The retained `.blend` contains both
live modifiers and the entire CINEMATICUM recipe, not only a flattened picture.

## Bounds

| Resource | Bound |
|---|---|
| Editable cage | 10,000 vertices, 10,000 faces, 60,000 face corners |
| Control polygon | 3–64 distinct positions |
| Interactive selection | 512 elements |
| Modifier stack | Four ordered modifiers |
| Mirror | One local axis per modifier; merge 0.000001–0.1 m |
| Bevel | Width 0.0001–2 local m; 1–6 segments; angle 0–180° |
| Subdivision | 1–3 matching viewport/render levels |
| Evaluated mesh | Existing 50,000-vertex and 100,000-triangle mesh limits |
| Entire scene geometry | Cages plus evaluations: 100,000 vertices, 200,000 triangles, 5 MiB |

A conservative preflight growth estimate rejects excessive stacks before engine
launch. Exact evaluated counts and canonical byte limits are checked afterward.

## Acceptance and remaining gaps

`test_scene_modeling.py` independently checks closed-surface edge incidence,
signed volume, extrusion depth, connected subdivision, source separation,
canonical digest changes, malformed operations, stale evaluation binding,
growth limits, cancellation and ownership of evaluation workers. It does not
stand in for a native rendering proof.

`test_scene_modeling_blender.py` has sequential `convert`, `edit`, `topology`,
`modifiers`, `render`, `replay` and `forged` stages for environments with short
command budgets. It operates the actual engine and reopens the retained source
in a separate Blender process. The independent inspection compares every base
vertex/face and evaluated vertex/triangle, inspects live modifier parameters,
renders the stack enabled and disabled, and measures the changed pixels. It
also modifies a cached preview and gives it a fresh canonical digest; the real
render must still reject that forged geometry.

`test_mesh_modeling_ui_macos.py` and `MeshModelingSmoke.js` exercise actual native
controls and server jobs, coordinate-based canvas picking, shared undo/redo,
saved canonical geometry, modifier enable/order/apply, and visible controls.
Each stage persists an isolated synthetic test project for the next short run.

Native tests require the installed engine and WKWebView. A Linux skip is not a
pass and is not evidence of a native render. Test artifacts are synthetic engine
fixtures, not authored film footage.

Remaining work includes edge selection and edge modeling tools, unrestricted
mesh sizes, sculpting, UV editing, vertex groups and bevel weights, subdivision
creases, shape keys/deformation animation, geometry nodes, parenting, armatures,
constraints, rigging and simulation. Those systems are not inferred from the
presence of these controls.

# Compositing and motion: source review and implemented design

Review date: 21 October 2026. Scope: Natron, Nuke, Fusion, After Effects,
Glaxnimate and Friction. This is a source/documentation comparison, not a claim
that CINEMATICUM contains their complete implementations.

## Evidence and reproducibility

The three open-source repositories were inspected at the following immutable
commits, using their public GitHub trees and the source files linked below.
No upstream application code is copied into CINEMATICUM by this change.

| Project | Inspected revision | Evidence type |
|---|---|---|
| Natron | [`3763d805d7d277d10af10025ae41af677682b3e6`](https://github.com/NatronGitHub/Natron/commit/3763d805d7d277d10af10025ae41af677682b3e6) | Public C++ source and official 2.5 documentation; the documentation is older than this source revision. |
| Friction | [`cfc7481d09f3791457747752c268a779ac55258f`](https://github.com/friction2d/friction/commit/cfc7481d09f3791457747752c268a779ac55258f) | Public C++ source and official current web documentation. |
| Glaxnimate | [`ef01e17a883abcd3a12381d87f79ba1de4e0a845`](https://github.com/KDE/glaxnimate/commit/ef01e17a883abcd3a12381d87f79ba1de4e0a845) | KDE's public source mirror and official model documentation. |
| Nuke | Public 17.1 Python API and Roto node reference | Public interface documentation only. Nuke's private implementation was not available or inspected. |
| Fusion | Current Blackmagic Design Fusion product/operation documentation | Public interface documentation only. Fusion's private implementation was not available or inspected. |
| After Effects | Current Adobe animation and mask documentation | Public interface documentation only. After Effects' private implementation was not available or inspected. |

The distinctions matter: reading a Python API does not reveal the proprietary
renderer, and a documentation feature list does not establish performance or
file compatibility in another application.

## Capability comparison beyond the immediate animation change

These rows separate implemented CINEMATICUM behavior from larger upstream
capability families. They are not an exhaustive per-menu parity inventory.

| Capability family | Primary upstream evidence | CINEMATICUM compositor status |
|---|---|---|
| Image graph and reusable tools | [Natron](https://natrongithub.github.io/) documents grouped node snippets/PyPlugs; [Nuke](https://www.foundry.com/products/nuke-family/nuke) documents Gizmos, Toolsets and LiveGroups. | A saved bounded DAG with branches, reconnectable ports and one selected output; one clip-source stream. No reusable macro/group system or arbitrary separate media inputs. |
| Host plug-ins | Natron's [official overview](https://natrongithub.github.io/) documents OpenFX hosting; Nuke's [overview](https://www.foundry.com/products/nuke-family/nuke) identifies C++ SDK and BlinkScript interfaces. | Finite built-in render-backed node types. No OpenFX/NDK plug-in ABI, binary plug-in loader or arbitrary shader execution. |
| Color and image representation | Nuke's [overview](https://www.foundry.com/products/nuke-family/nuke) documents multi-channel/deep images, OpenEXR, OCIO and ACES; Adobe documents [OCIO/ACES project management](https://helpx.adobe.com/after-effects/desktop/adjust-colors/opencolorio-and-aces-color-management/opencolorio-aces-color-management.html). | SDR RGBA image graph and RGB/master tone curves with alpha preserved. No scene-linear floating-point project color pipeline, arbitrary EXR channels or deep samples. An exposure slider does not establish ACES/HDR equivalence. |
| Roto geometry | [Natron](https://natrongithub.github.io/) documents layered roto/per-vertex feather; [Nuke Roto](https://learn.foundry.com/nuke/17.1/content/reference_guide/draw_nodes/roto.html) documents Bezier/B-spline shape editing. | Ellipse, rectangle and polygon mattes; animated transform, feather and stable-topology polygon points. No Bezier handles, separate feather vertices, roto paint strokes or multiple-shape hierarchy inside one mask. |
| Temporal authoring | The Nuke animated-transform API, Adobe interpolation docs and inspected Natron/Friction/Glaxnimate source expose richer key/curve models. | Independent scalar/path channels, five easing choices, key navigation, key-time edits, shared undo/redo and preserved trim/split time domains. No custom temporal tangents, looping expressions, constraints or modifier network. |
| Vector deliverables | Glaxnimate's [format manual](https://docs.glaxnimate.org/en/formats.html) documents Lottie/TGS, SVG/SMIL, frame images, GIF/WebP and bitmap tracing; that manual identifies itself as 0.5.4 and explicitly notes Lottie feature limits. | Polygon data remains editable in the native project and renders to the movie. No Lottie/TGS/SVG animation export or vector-format compatibility is claimed. |
| Raster/path effect extensibility | Friction's [effects](https://friction.graphics/documentation/effects.html) and [shader definition](https://friction.graphics/documentation/shaders.html) docs describe animated raster/path effects and typed UI properties backed by GLSL fragments. | Known grade/blur/chroma/alpha parameters compile to FFmpeg; editable RGB tone curves remain static. No Friction shader loader, vector path-effect stack or user-defined GLSL. |
| 3D and motion systems | Blackmagic's [Fusion documentation](https://www.blackmagicdesign.com/products/davinciresolve/fusion) describes compositing geometry, cameras, lights, masks, modifiers and expressions. | This per-clip compositor is 2D. CINEMATICUM's separate owned scene model is evaluated in its own scene workstream; this graph does not become a Fusion-equivalent 3D graph by rendering a scene movie. |
| Tracking and automation | Natron's [roto API](https://natron.readthedocs.io/en/rb-2.5/devel/roto.html) exposes track relationships; Nuke's [overview](https://www.foundry.com/products/nuke-family/nuke) exposes Python/pipeline interfaces. | Bounded saved animation data can receive tracker-generated x/y curves. This is distinct from persistent arbitrary parameter links, planar/camera solves and a general script host. The tracker implementation and evidence belong to the tracking workstream. |

The clearest remaining architectural gaps are separate media inputs and
effect-mask ports, a scene-linear image/color model, Bezier/feather-point roto,
and reusable graph components. Those require new data and rendering contracts;
adding names to the node menu would not implement them.

## What the sources actually show

### Natron: curves are first-class data, and roto has separate geometry and properties

[`Engine/Curve.cpp`, `Curve::getValueAt`](https://github.com/NatronGitHub/Natron/blob/3763d805d7d277d10af10025ae41af677682b3e6/Engine/Curve.cpp)
locates neighboring keys, supplies value/derivative/interpolation information
to the interpolation evaluator and optionally clamps the result. This is a
parameter model with explicit temporal semantics, rather than UI-only values.
[`Engine/Bezier.cpp`](https://github.com/NatronGitHub/Natron/blob/3763d805d7d277d10af10025ae41af677682b3e6/Engine/Bezier.cpp)
contains time-dependent point evaluation, shape transforms, feather geometry,
and keyframe interpolation applied to control/feather points.

The official [roto scripting documentation](https://natron.readthedocs.io/en/rb-2.5/devel/roto.html)
separates curves from their layer hierarchy and exposes geometry, keyframes,
opacity, feathering and point-to-track relationships. CINEMATICUM's current
per-clip graph does not have that hierarchy or Natron's Bezier/feather-point
model. Its polygon mask is a bounded straight-edge shape.

**Concrete lesson:** a saved parameter must evaluate identically in the
inspector, paused frame and export. Mask shape deformation and mask transforms
need separate channels so moving a shape does not rewrite all its vertices.

### Nuke: independent transform channels and explicit roto operations

The public [`AnimCTransform` API](https://learn.foundry.com/nuke/developers/17.1/pythondevguide/_autosummary/nuke.rotopaint.AnimCTransform.html)
provides individual curves and key operations for translation, rotation,
scale, pivot and skew. Its documented evaluator accepts time. The
[`Roto` node reference](https://learn.foundry.com/nuke/17.1/content/reference_guide/draw_nodes/roto.html)
documents Bezier/B-spline editing, per-shape controls, background and optional
mask inputs, and the distinction between shape and transform animation.

CINEMATICUM currently has one source image per graph and a much smaller node
vocabulary. It does not implement Nuke's multi-view/deep data model,
arbitrary channels, full roto hierarchy or Nuke script compatibility.

**Concrete lesson:** keying X must not insert keys in Y, feather, opacity or
other parameters. Dedicated curves avoid the timing side effects of a single
combined keyframe object.

### Fusion: image graphs, animated properties, and purpose-built mask inputs

Blackmagic's [Fusion documentation](https://www.blackmagicdesign.com/products/davinciresolve/fusion)
describes image merge inputs, dedicated effect mask connections, animated
inspector properties, spline/keyframe editors, expressions/modifiers, 3D
nodes, and animated Bezier/B-spline masks. Its spline editor includes custom
tangents and time operations; its mask tools include per-point feathering.

CINEMATICUM's current merge graph operates on branches of one clip source.
Mask nodes multiply alpha on a branch; they are not a general mask-input port
on every effect. CINEMATICUM does not yet implement Fusion's modifier network,
custom animation tangents, particles, deep compositing or full 3D node graph.

**Concrete lesson:** expose only render-backed animatable properties, and
preserve coverage when changing merge opacity. Scalar opacity is not a color
blend operation and must be applied to foreground alpha.

### After Effects: time interpolation and path geometry are separate decisions

Adobe's [keyframe interpolation documentation](https://helpx.adobe.com/after-effects/desktop/animate-in-after-effects/animation-keyframes/keyframe-interpolation.html)
distinguishes temporal interpolation from spatial interpolation and documents
linear, hold and Bezier families. The [mask/path documentation](https://helpx.adobe.com/after-effects/desktop/animate-in-after-effects/animate-shape-paths-and-masks/animating-shape-paths-masks.html)
describes path keyframes, vertex correspondence, geometry transforms and mask
tracking. In particular, rotating vertices between shape keys is different
from rotating a transform: point interpolation follows its own trajectories.

CINEMATICUM does not provide After Effects' shape operators, expressions,
per-character text animators, motion-graphics templates, Roto Brush, or
After Effects project compatibility.

**Concrete lesson:** the first implementation uses explicit vertex ordering
and equal point counts throughout an animated polygon. It rejects a topology
change instead of silently connecting unrelated vertices. Rotation remains a
separate parameter with its own trajectory.

### Glaxnimate: a shared serializable model plus coordinated editing commands

The official [model-object documentation](https://glaxnimate.org/contributing/code/model_objects/)
explains the relationship between document objects and serialized JSON and how
animatable property metadata participates in the UI. Format-specific import
and export bindings remain separate work; shared state alone is not format
parity.

In [`animatable_path.cpp`](https://github.com/KDE/glaxnimate/blob/ef01e17a883abcd3a12381d87f79ba1de4e0a845/src/core/glaxnimate/model/animation/animatable_path.cpp),
`AnimatedPropertyBezier::split_segment` and `remove_points` update keyframes
under an undo macro. [`animation_commands.cpp`](https://github.com/KDE/glaxnimate/blob/ef01e17a883abcd3a12381d87f79ba1de4e0a845/src/core/glaxnimate/command/animation_commands.cpp)
contains undoable key and multi-property editing commands.
[`keyframe_transition.cpp`](https://github.com/KDE/glaxnimate/blob/ef01e17a883abcd3a12381d87f79ba1de4e0a845/src/core/glaxnimate/model/animation/keyframe_transition.cpp)
represents hold, linear, ease, overshoot and custom transition behavior through
transition state and Bezier handles.

CINEMATICUM does not have Glaxnimate's full vector object hierarchy,
Bezier-handle editing, Lottie/SVG animation export or format-specific property
conversion. Its current RGB color curves are tone mappings, not temporal
animation curves; these must not be confused in the UI.

**Concrete lesson:** each completed vertex drag should be one shared-project
undo action. Adding/removing points across existing keys requires a deliberate
topology operation. This change preserves topology by restricting such edits
while the polygon path is animated.

### Friction: bounded scalar evaluation and a separate animated path model

[`QrealAnimator::calculateBaseValueAtRelFrame`](https://github.com/friction2d/friction/blob/cfc7481d09f3791457747752c268a779ac55258f/src/core/Animators/qrealanimator.cpp)
finds adjacent keys, solves the time component of the cubic, evaluates its
value component, clamps the result and holds the nearest endpoint outside the
key interval. [`SmartPathAnimator`](https://github.com/friction2d/friction/blob/cfc7481d09f3791457747752c268a779ac55258f/src/core/Animators/SmartPath/smartpathanimator.cpp)
stores path state separately, evaluates paths at relative frames and applies
geometry transforms across saved path values.

The [animation techniques](https://friction.graphics/documentation/animation_techniques.html)
and [expressions](https://friction.graphics/documentation/expressions.html)
documentation describes additional motion workflows. CINEMATICUM does not
implement Friction's expression language, shader effects or complete
vector/raster scene model.

**Concrete lesson:** retain explicit bounds and a documented time domain.
Use a small finite easing vocabulary now; arbitrary executable expressions are
not needed to implement usable motion and would introduce a different trust
and resource boundary.

## CINEMATICUM change derived from this review

The compositing/motion work adds an optional `animation` map to each existing
version-1 node. Each supported numeric parameter has independent key times.
Polygon `points` is a shape channel whose keyed arrays preserve vertex count
and order. Static v0.4 graphs remain valid.

```json
{
  "id": "subject_mask",
  "type": "mask",
  "inputs": ["source"],
  "params": {"shape": "ellipse", "x": 0.25, "y": 0.5},
  "animation": {
    "x": [
      {"frame": 0, "value": 0.25, "interpolation": "linear"},
      {"frame": 24, "value": 0.75, "interpolation": "ease_in_out"}
    ]
  }
}
```

`interpolation` belongs to the segment leaving its key. The supported methods
are linear, constant, ease-in, ease-out and ease-in-out. Values hold outside
the keyed interval. The unkeyed parameter value supplies the frame-zero
anchor unless an explicit frame-zero key replaces it.

Animation time is `decoded_clip_frame + clip.animation_offset`. The valid
stored domain is `clip.animation_start` through `clip.animation_duration - 1`;
negative start values are supported. A trim or split changes the clip's
animation offset and keeps the original node curves. No interpolated boundary
key is inserted, so a curved trajectory survives an edit unchanged.

The implementation uses the same compiled graph for paused frame preview and
export. Per-frame command updates are emitted only for known filter options;
mask geometry and merge alpha are evaluated from generated bounded
expressions. User text cannot become a filter expression or command. FFmpeg's
[sendcmd reference](https://ffmpeg.org/ffmpeg-filters.html#sendcmd_002c-asendcmd)
documents expression commands; actual decoded-frame checks also guard the
runtime counter convention and first-frame behavior.

## Implementation and acceptance

`compositor.py` now validates and compiles these channels:

| Node | Animated properties |
|---|---|
| Grade | Exposure, contrast, saturation, temperature |
| Gaussian blur | Sigma, applied to both image axes |
| Chroma key | Similarity and blend |
| Mask | X/Y center, width, height, rotation, inward feather and polygon points |
| Merge | Foreground opacity, including normal/multiply/screen/add/difference |

Sharpen amount and RGB/master tone-curve shapes remain static. The current
unsharp filter does not expose an equivalent runtime amount command; this
change does not display an animation button for an unsupported channel.

`web/compositor-ui.js` adds parameter key buttons, independent-channel
selection, key navigation/time editing, outgoing interpolation and a
make-static action. Editing an already animated scalar inserts/updates its key
at the playhead. Dragging a keyed polygon vertex creates one shared-project
undo action. Add/remove/reset topology controls are disabled while path
animation exists. A path may still become concave or self-intersect; the
renderer uses the existing even-odd fill rule.

The public UI bridge takes `frame`, `animationStart` and `animationDuration`
in `setContext`. `setFrame(frame)` refreshes evaluated inspector values without
mutating the graph. `onSeek(domainFrame)` requests an animation-domain frame;
the host maps it back to timeline time with
`clip.start + domainFrame - clip.animation_offset`.

Validation limits are 32 graph nodes, 128 keys per scalar channel, 64 polygon
keys, 24 vertices per polygon, 1024 total keys and 8192 keyed scalar/coordinate
values. Every value/frame is finite and bounded. Duplicate channel times,
unknown properties/easing, altered polygon topology and executable input
strings are rejected. Generated animation conditions form a balanced tree;
the maximum scalar-key test renders the last key through real FFmpeg.

The decoded-media suite in `test_compositor.py` checks existing static graphs
and new moving/deforming/rotating/feathered masks, independent grade/blur/chroma
channels, animated alpha in every blend mode, first-frame and held-key
boundaries, negative animation time and byte-identical replay after a trim
offset. It compares dynamic output with separately evaluated static graphs.
It also compares the shipped JavaScript inspector evaluator with Python on
scalar and polygon data. Run from `scripts/studio`:

```sh
python3 -m unittest test_compositor -v
```

`macos/CompositorAnimationSmoke.js` and
`test_compositor_animation_ui_macos.py` add a real WKWebView acceptance path:
author keys through shipped controls, drag a polygon, undo/redo, seek, split,
trim the leading edge, compare retained rendered PNG pixels, save, export and
play the actual movie. Python independently checks saved curves/domain data,
the preview receipts and decoded movie frame. The Linux environment explicitly
skips this native test; a skipped run is not Mac acceptance evidence. Invoke
the previously compiled `macos/SmokeTest.swift` helper with:

```sh
python3 test_compositor_animation_ui_macos.py --binary /absolute/path/to/cinematicum-smoke --output /absolute/path/to/ENGINE_TEST_evidence
```

This work does not establish complete equivalence with any of the six products
above. Test counts and the actual native acceptance result are reported in the
delivery evidence; they are not inferred from source inspection.

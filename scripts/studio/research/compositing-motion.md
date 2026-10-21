# CINEMATICUM: independent media sources in the compositor

Research and implementation: 2026-10-21. This increment extends CINEMATICUM's existing typed image graph. It adds real project-media inputs, source-range timing, and explicit transparent/hold behavior to the same renderer used by paused frames and movie export. It does not launch another editor or claim feature parity with Natron, Nuke, Fusion, or After Effects.

## Primary sources inspected

| Upstream source | Exact inspected revision | Relevant behavior |
| --- | --- | --- |
| [Natron OpenFX GenericReader.cpp](https://github.com/NatronGitHub/openfx-io/blob/9fb5ee936bad741f6dda66d87df50599873b2e5d/IOSupport/GenericReader.cpp) | Commit `9fb5ee936bad741f6dda66d87df50599873b2e5d`; file blob `0092560d33125c9da4e6bc52a6733a5be71f5438` | `getSequenceTime()` subtracts the reader time offset before checking the selected source domain. The before/after branches distinguish nearest-endpoint hold, loop/bounce, black, and error. |
| [FFmpeg vf_tpad.c](https://github.com/FFmpeg/FFmpeg/blob/58892c922e348b3010803d2dcaac74f79565633e/libavfilter/vf_tpad.c) | Commit `58892c922e348b3010803d2dcaac74f79565633e`; file blob `a1c9aecd3582222af2a6205595a1e6d564b2afd7` | Finite integer prefix/suffix frame counts; solid-color or cloned first/last-frame padding; explicit RGBA color; frame-rate-derived padded timestamps. |
| [FFmpeg trim.c](https://github.com/FFmpeg/FFmpeg/blob/58892c922e348b3010803d2dcaac74f79565633e/libavfilter/trim.c) | Same commit; file blob `1077ff3d1acfc8082ae9c01ef2058b142d27edbc` | Start frame is inclusive; end frame is exclusive. Frame-count selection is separate from timestamp selection. |
| [Natron Read-node documentation](https://natron.readthedocs.io/en/rb-2.5/guide/thenodes-image-read.html) | Official rb-2.5 documentation, accessed 2026-10-21 | Selected first/last range, time offset, hold/transparent-black behavior, image interpretation, and limitations of implicit frame-rate interpretation. |
| [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html#tpad) | Official documentation, accessed 2026-10-21 | Supported `trim`, `tpad`, `setpts`, and framesync controls. |

The source commits are pinned revisions inspected for these mechanisms, not a claim that they are the latest complete application release. No upstream implementation was copied into CINEMATICUM. The implementation uses the installed FFmpeg executable through the project's existing renderer and its existing process safeguards.

## Previous gap and implemented behavior

Previously, every branch originated from one selected timeline clip. Masks, color corrections, keys, and merge operations could combine processed versions of that clip, but a graph could not read a second project movie. This prevented normal foreground/background compositing inside the graph.

The new `media_source` node has no image inputs and reads an existing project asset by its ID. Each such node has its own source range and placement. Multiple nodes may reference the same asset with different source in-points. Up to eight additional media sources are supported within the existing 32-node graph limit. The original `source` node remains compatible and still represents the selected timeline clip. It may be disconnected when an additional media source is the desired graph output.

The UI includes a project asset selector, source in-point, selected duration, start in the preserved animation domain, outside-range policy, current sampled source frame, and thumbnail. Adding a media source leaves the current output connected until the user connects a branch, adds a merge, or explicitly selects another output. Every committed edit uses the existing shared history. Sources contribute picture only; timeline audio remains an independent edit.

## Canonical data and timing

Graphs remain `version: 1`. A media node is represented as:

```json
{
  "id": "foreground",
  "type": "media_source",
  "inputs": [],
  "params": {
    "asset_id": "owned_project_asset_id",
    "source_in": 4,
    "duration": 8,
    "offset": 6,
    "outside": "transparent"
  }
}
```

All source timing values are integer **project frames**, after the source is conformed to the project's rational frame rate. They are not source-native frame numbers or seconds. CINEMATICUM intentionally uses its established project-rate pipeline rather than copying Natron's frame-rate-agnostic interpretation.

For local output frame `n`, the independent animation coordinate is `F = clip.animation_offset + n`. The source is active on the half-open interval `[offset, offset + duration)`. The active source index is `source_in + F - offset`. With `outside: transparent`, other frames have zero alpha. With `outside: hold`, the index is clamped to `[source_in, source_in + duration - 1]`. Hold therefore freezes the selected range's endpoints, not the complete asset's first and last frames.

For the example above, animation frames 6–13 read conformed source frames 4–11. Frames 0–5 and 14 onward are transparent. Changing the policy to hold produces source frame 4 before animation frame 6 and source frame 11 after animation frame 13.

Trimming or splitting the owning timeline clip changes its visible animation window. It does not rewrite source-node offsets or in-points, and it does not resample existing node parameter curves. Clip speed/reverse affects the original clip source; additional sources retain their explicitly authored source range. This distinction is shown in the inspector.

Still images require source in-point zero and can fill any supported selected duration. Video ranges are checked against probed duration at project rate, with the same half-frame metadata tolerance already used by timeline clips.

## Integration boundary and rendering

`validate_graph()` normalizes a bounded, typed graph. `media_sources(graph, active_only=True)` returns detached canonical source requests in graph order. `validate_media_sources(graph, assets, fps)` validates **all** references, including disconnected nodes, against the project's probed asset map.

The engine owns asset resolution, file access, stream selection, source decoding, rate conforming, image fitting, transparent geometric margins, and project ownership checks. Each reachable media node is supplied as a distinct, zero-origin, square-pixel, straight-RGBA stream at the same dimensions and frame rate as the primary graph input. This separation ensures that node data cannot become a filename, URL, command, or free-form filter expression.

`compile_graph()` accepts `external_labels={node_id: internal_label}` and `frame_count=clip.duration`. It requires exactly the reachable nodes, validates distinct internal labels, and compiles selected-source trim, finite prefix/suffix padding, the requested animation window, and timestamp resets. All branch outputs therefore have the requested frame count. If the primary clip source is disconnected, its prepared stream is consumed with a null sink. The existing typed merge and alpha logic then process the branches.

The paused viewer and movie export use the same engine graph. The compositor adds no alternate browser approximation of a multi-source render. Its inspector's pure sampled-frame display is independently tested against the Python evaluator and decoded frames.

## Validation and evidence

`test_multi_source_compositor.py` includes:

- Strict field types, finite and integer frame bounds, allowed outside policies, identifier restrictions, the eight-source cap, and disconnected-cycle validation.
- Missing, audio, scene, unsupported HDR and linear-EXR source rejection, including disconnected references; still-image and video-range checks.
- Exact internal input-label ownership, reachable-only compilation, and independently timed instances of the same asset.
- Actual FFV1 moving-source fixtures with separate authored red horizontal motion and blue vertical motion. Decoded pixel checks establish that both source images contribute at their independently selected times.
- Exact transparent gaps and held endpoint checks; output count and alpha checks when the source range is wholly before or after the clip window; external-only graph output with unused primary input.
- Negative source offsets and negative animation windows; integer source boundaries after 24000/1001 rate conforming.
- Pixel-identical split/trim windows while merge opacity uses its existing independent animated curve.
- Full engine export and paused-frame comparison, a deliberately empty trimmed timeline gap, all-frame decoding, and a later timeline clip that catches accidental FFmpeg input-index shifts. Independent sine-wave audio and raster-title checks also verify that additional picture inputs do not redirect timeline sound or title media.

The native acceptance pair `macos/MultiSourceSmoke.js` and `test_multi_source_ui_macos.py` creates an isolated two-source project and authors the graph through shipped WKWebView controls. It checks source addition and policy undo/redo, rejects an overlong range, builds a masked merge, reads an actual paused PNG, splits and trims, checks the retained paused frame again, saves, exports, and plays the rendered movie. Python independently checks saved source timing, image hashes, source immutability, decoded pixels, timeline gaps, and paused/export consistency. It reports actual evidence rather than substituting synthetic UI success when macOS is unavailable.

Local standalone validation and decoded-media checks passed on FFmpeg 6.1.1. Native UI and final integrated installation acceptance are separate gates run by the owning root workflow; this file does not claim those gates passed before their report exists.

## Remaining limits

This increment implements finite additional video/still sources and explicit hold/transparent timing. Separate before/after policies, looping/bouncing, media-source retime curves, sequence-pattern discovery, frame-missing substitution, per-source color-management controls, multiview/multilayer EXR reads, channel routing, deep compositing, optical-flow retiming, caching/proxy controls, and a production float image pipeline remain outside this implementation. The existing graph uses the current SDR RGBA renderer; unsupported HDR sources are rejected instead of silently interpreted as SDR. The report is a bounded source study and implementation record, not a full reverse engineering or parity claim for the referenced products.

## Calibrated lens pixels: source study and implemented scope

The camera import increment already transferred pinhole intrinsics and poses
into CINEMATICUM's own scene. It did not correct distorted image pixels. The
new **Calibrated lens** node closes that specific gap: it can undistort captured
footage or reproduce a calibrated distortion in a connected image branch.

| Source inspected | Pinned revision / blob | Mechanism inspected |
| --- | --- | --- |
| [OpenCV undistort.dispatch.cpp](https://github.com/opencv/opencv/blob/1e71c2b43a57fad2d863a0c9b3537bbf610164d7/modules/calib3d/src/undistort.dispatch.cpp) | Commit `1e71c2b43a57fad2d863a0c9b3537bbf610164d7`; blob `2a53c254d5f74264ffdde6f5dda6c681c121c1ab` | Intrinsic normalization, radial/tangential distortion, inverse iteration and its error checks. The inspected OpenCV code also handles coefficients and tilted-sensor models that this bounded node does not implement. |
| [OpenCV calibration documentation](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html) | Official 4.13.0 documentation, accessed 2026-10-21 | Pixel focal lengths and principal point, resolution scaling, radial/tangential coefficient conventions, and the need for a bijective distortion map. |
| [FFmpeg vf_remap.c](https://github.com/FFmpeg/FFmpeg/blob/58892c922e348b3010803d2dcaac74f79565633e/libavfilter/vf_remap.c) | Commit `58892c922e348b3010803d2dcaac74f79565633e`; blob `de83bb467166d1c0e24d2287cd3dacb84f86e4e5` | Integer-coordinate 16-bit maps, out-of-bounds fill, and supported high-depth alpha formats. A single remap does not provide the fractional sampling required here. |
| [FFmpeg vf_maskedmerge.c](https://github.com/FFmpeg/FFmpeg/blob/58892c922e348b3010803d2dcaac74f79565633e/libavfilter/vf_maskedmerge.c) | Same commit; blob `299c05c1ba4b52f8bd2bd9fb1952f81717fa9bb9` | Per-plane weighted mixing, including supported 16-bit RGBA planes. This enables fractional interpolation after selecting the four source corners. |
| [FFmpeg vf_geq.c](https://github.com/FFmpeg/FFmpeg/blob/58892c922e348b3010803d2dcaac74f79565633e/libavfilter/vf_geq.c) | Same commit; blob `fc3dd6740ef6a4618c4195b5672995f48da1c8a2` | Pixel lookup, bilinear boundaries and expression evaluation. An initial per-frame expression implementation was rejected after measured cost proved unsuitable for video. |

### Calibration and image conventions

The node accepts `direction`, `fx`, `fy`, `cx`, `cy`, `k1`, `k2`, `k3`, `p1`
and `p2`. Focal lengths and principal point are normalized by their respective
image axes, so pixel FX is `fx × image_width` and pixel FY is
`fy × image_height`. Pixel centers have integer coordinates starting at zero;
image Y points down. The graph canvas is the primary fitted image, before
ordinary clip placement transforms. There is no implicit lens profile lookup.

With ideal normalized camera coordinates x and y and `r² = x² + y²`, the
forward map is:

```text
radial = 1 + k1*r² + k2*r⁴ + k3*r⁶
xd = x*radial + 2*p1*x*y + p2*(r² + 2*x²)
yd = y*radial + p1*(r² + 2*y²) + 2*p2*x*y
```

For undistortion, each output ideal pixel samples the corresponding distorted
input using that forward map. For reproducing distortion, each distorted
output pixel samples the ideal input through the inverse map. Samples outside
the image have zero coverage. The node does not crop, zoom, or change the
principal point to conceal missing image coverage.

The **Copy base scene camera intrinsics** control copies a compatible existing
scene camera's vertical FOV, principal-point shifts, and focal ratio into these
four normalized image intrinsics. Its aspect must match the graph image. It
uses the base camera, not an arbitrarily selected animated pose. Authored
distortion coefficients remain explicit. The supported fSpy/COLMAP pinhole
imports do not establish a distortion calibration, so no undocumented
coefficient conversion is inferred from them.

### A full-domain inverse bound

The implementation uses a conservative analytic certificate over the complete
normalized image rectangle. Let R be the largest radius at its four corners:

```text
q = 3*abs(k1)*R² + 5*abs(k2)*R⁴ + 7*abs(k3)*R⁶
    + 8*R*(abs(p1) + abs(p2))
```

This bounds the spectral norm of the forward map Jacobian minus identity.
Requiring `q <= 0.45` ensures strong monotonicity and a contraction for the
projected inverse iteration on the image rectangle. The bound is checked
before rendering, including disconnected lens nodes. It is an intentionally
conservative supported subset: a calibration rejected by this node may still
be physically meaningful, but it needs a different solver or model.

Iteration count is derived from that bound and a normalized coordinate
tolerance, with a fixed maximum of 48 iterations. Every inverse sample is
checked against the forward residual. A converged projected point on the
boundary whose residual is nonzero represents an output ray outside the
mapped source. It becomes transparent. A residual failure in the interior
raises an error; it is not silently replaced with an uncalibrated pixel.

### Static map generation and real bilinear pixels

The expensive coordinate calculation runs once for each unique calibration
and graph size in a render. The engine invokes the shipped numeric worker in
a cancellable subprocess, sends at most 16 KiB of bounded JSON, and provides
an owned, empty temporary output directory. The graph contains no filenames,
arbitrary expressions, or commands. Standard Python works without external
modules. An installed isolated imaging runtime optionally accelerates the
same algorithm with NumPy over 32-row strips; NumPy is not imported by the
Studio server.

The worker emits exactly six 16-bit PNGs: floor/ceiling X and Y coordinate
maps, plus horizontal and vertical fractional weight maps. Coordinates are
not rounded to a nearest pixel. The two fractions are rounded to units of
1/65535, so each coordinate's fractional quantization error is at most
0.5/65535 pixel. The engine checks the request digest, fixed filenames, PNG
dimensions/depth, byte counts and SHA-256 digests before accepting these maps.

Each PNG is decoded once and its frame is repeated for the clip's exact
duration. Four remaps sample the source corners in premultiplied 16-bit RGBA.
Two horizontal weighted merges and one vertical weighted merge interpolate
all four channels identically. The result is unpremultiplied before returning
to the existing SDR graph. This avoids hidden color bleeding from transparent
pixels and retains fractional pixel motion. The final graph still uses its
existing SDR output precision; intermediate 16-bit sampling does not turn it
into a scene-linear float compositor.

Nonzero processing is bounded to two calibrated lens nodes and 2,073,600
pixels per graph canvas (1920 × 1080). Larger images can use an identity lens
node because identity is emitted as an exact no-op. Calibration is static;
unsupported animated lens coefficients are rejected instead of generating
maps at every frame.

### Measured costs and acceptance

These are local engineering measurements from the workspace, not a realtime
promise for the user's Mac. They use the same five-term inverse calibration
as the independent tests and NumPy 2.3.5 when indicated:

| Operation | Image | Measured elapsed |
| --- | --- | ---: |
| Production forward map preparation, NumPy | 1920 × 1080 | 0.72 s |
| Production inverse map preparation, NumPy | 1920 × 1080 | 1.06 s |
| Production inverse map preparation, standard Python | 640 × 360 | 2.14 s |
| Production inverse map preparation, standard Python | 1920 × 1080 | 16.69 s |
| Four-remap/three-merge prototype, 24 inverse-warp frames, one FFmpeg graph thread | 1920 × 1080 | 3.83 s |

The engine's worker timeout is 90 seconds and cancellation is propagated
during preparation. Full-resolution previews may wait for map preparation;
the UI therefore does not claim realtime calibrated processing.

`test_lens_compositor.py` passes 13 tests, including more than 1,200
independent forward/Newton inverse point comparisons; every map sample in
two small images against a separate Newton solver; exact NumPy/standard
Python map equality; strict JSON, bounds, exclusive output files and PNG
receipts; and a worker run with Python site packages disabled. Actual FFmpeg
pixel tests cover both directions, premultiplied alpha, hidden transparent
red next to green edges, exact identity, and pixel-identical trimmed windows
with upstream mask animation. The shipped JavaScript validator is executed
to check matching bounds and absence of unsupported animation channels.

An integrated engine test renders a split/trimmed graph containing additional
media and a lens, verifies single preparation of shared calibration maps,
exact retained paused PNGs, every exported frame, the deliberately empty
timeline gap, both independent media contributions, and paused/export
consistency. The earlier 45 compositor and multi-source tests also pass.

`macos/LensSmoke.js` and `test_lens_ui_macos.py` form a separate native gate:
they operate shipped controls, check camera-intrinsic copying, invalid-fold
rejection, visible inspector controls, single undo/redo, reset behavior,
both actual paused-frame operations, exact saved calibration, export and
playback. Python independently compares both PNGs with its Newton/alpha
oracle and checks the movie, source hashes and paused/export parity. Native
success is only established by its resulting report; preparation and syntax
checks are not counted as a native pass.

This implementation does not provide automatic checkerboard calibration,
Lensfun profile conversion, fisheye/rational/thin-prism/anamorphic models,
rolling-shutter correction, animated calibration, optical element design,
spectral lens transport, full distortion-map interchange, or parity with
OpenCV/Lensfun/Nuke. It adds a real, tested calibrated image operation inside
CINEMATICUM's own graph and editor.

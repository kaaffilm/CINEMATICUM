# CINEMATICUM Studio 0.13: lens workflows and interchange

Studio 0.13 starts from published 0.12 source
`dcea86196f81d6476a0f60538429b984b24c1129` and retains its accepted
[retiming and production workflows](FEATURES_0_12.md). Frozen core `cdd15816`
passed all **925 tests** with zero failures/errors/skips and unchanged source
and managed engines. Six actual Mac phases passed **150 outer checks**, with
four native UI executions and two fixture preparations. Actual replacement
installation passed 5/5 for 114 runtime/web and 119 bundle files; canonical
launch passed 16/16 and all eight installed runtime phases passed 14/14.
Final preservation passed 6/6. Exact publication and its subsequent CI outcome
are recorded through [PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162).
The [verification record](VERIFICATION_0_13.md) preserves the integrated
identities alongside original isolated evidence. Full professional parity
remains unfinished.

## Measured Lensfun radial profiles

The compositor lens node can import actual Lensfun version 1/2 XML and select
an explicit measured focal sample. Supported radial equations are `poly3`,
`poly5` and `ptlens`. The parser retains the source-byte SHA-256 and embeds a
typed calibration record in the editable project. Saved projects and portable
archives therefore retain their selected calibration without depending on a
subsequently changed database file.

The warp accounts for the documented calibration/capture crop, aspect and
optical-center conventions. It numerically inverts admitted radial mappings
within a bounded monotone domain. The interface exposes the selected profile,
capture geometry and direction, and applies the edit through the ordinary
undo history. Existing Brown calibration remains available.

This workflow requires an explicit profile and exact measured focal sample.
Automatic EXIF matching, camera lookup, interpolation between focal samples,
database updating, TCA and vignetting are separate remaining requirements.
The application does not silently download or install a Lensfun database.

## Four explicit fisheye projections

The lens node also supports equidistant, equisolid, stereographic and
orthographic fisheye mappings to or from a rectilinear image. The renderer
uses the selected projection's actual ray equations. Unsupported rays and
samples outside the input image become transparent. The admitted domain is
the front hemisphere; arbitrary panorama projections and reconstruction
beyond 180 degrees remain outside this workflow.

Paused pictures and movie exports execute the same compositor. The implemented
scope includes Standard8 and high16 SDR. The existing Float32 movie path
continues to reject compositor graphs explicitly; adding a lens node does not
silently flatten that limitation.

## Bounds and evidence

| Area | Implemented bound |
| --- | --- |
| Lens nodes | At most two per compositor graph |
| Active image | At most 2,073,600 pixels |
| XML | At most 512 KiB, 512 lenses and 2,048 calibration samples |
| Lensfun models | Exact measured `poly3`, `poly5` and `ptlens` radial samples |
| Radial inversion | Conservative derivative-deviation bound of 0.8 |
| Capture | Complete uncropped image, square pixels, no letterboxing |
| Fisheye domain | Front hemisphere with transparent invalid/outside samples |

The original feature source passed 25 focused tests and actual Chromium
authoring/export acceptance. Independent physical-millimetre/Newton and 3D-ray
oracles checked the rendered pixels, including high16 values and alpha.
The shared coordinator first passed through Chromium in three bounded phases
with 10/41/24 outer checks; that original result retains `native_certified: false`.
It subsequently passed the same 10/41/24 checks on the exact integrated Mac
core: one fixture preparation and two actual native UI executions, including
all eight delivered movie pictures and a clearly labelled native ProRes
decoder probe. The complete 925-test core gate also passed. These shared lens
checks are not counted again for each supported projection/profile.

[LENS_WORKFLOWS.md](LENS_WORKFLOWS.md) describes the mathematical conventions,
supported profile fields and acceptance limits.
[LENS_NATIVE_ACCEPTANCE.md](LENS_NATIVE_ACCEPTANCE.md) supplies the bounded
native commands and distinguishes the shipped H.264 player from the separate
ProRes native decoder probe.

## Public Final Cut Pro XML interchange

**Interchange → Format → Final Cut Pro XML (.fcpxml)** imports a standalone
1.9/1.10 document and exports standalone 1.10 XML. The review maps each resource
to media already owned by the destination project, checks the actual source
identity and clocks, and proposes one undoable timeline replacement. No source
URL is followed. Current edits can be exported without discarding unsaved work.
The original source/timecode origins, nested edits and owned media survive
save/reopen and portable archive relocation.

The supported mapping includes exact rational frame positions, nonzero source
and sequence origins, gaps, connected picture/audio lanes, trimmed shared
compound sequences and simple clip containers. Static fit, uniform scale,
position, central-anchor rotation, normal opacity and clip level retain their
editable native values. Connections become independent native lanes; magnetic
follow relationships and receiving-editor DSP are separate concerns.

Picture retiming is deliberately restricted to measured compatible grids:
ordinary 1×, explicit floor-repeat 0.25×/0.5× with integral consumed frames,
and 2× only after the actual source passes a bounded decoded timestamp proof.
Source and project picture rates must match. Reverse XML maps, arbitrary speed
curves, mixed rates, frame blending and optical flow refuse explicitly. These
restrictions do not change native or OTIO retiming.

The XML boundary admits progressive square-pixel SDR Rec.709 and stereo 48 kHz
output. It is limited to 8 MiB, 30,000 elements, 1,024 resources, 512 assets and
six-hour timelines. Each sequence admits 256 clips and 16 picture/audio lanes;
the existing 64-sequence/eight-level/1,024-expanded-instance limits still apply.
Transitions, titles, multicamera clips, effects, custom channel/pan/fade routing,
track mix operations and unsupported spatial/color/timing operators fail before
application or export.

The isolated implementation passed 19 focused tests. Independent real-media
oracles checked every one of 40 numbered pictures and all 64,064 stereo sample
frames, including a relocated archive. The shared native coordinator passed
74 outer checks and 20 UI checks in Chromium. Actual Mac acceptance then
passed 11/30/34 outer checks across preparation/author/render (75 total, with
21 nested UI assertions), including the extra actual advancing ProRes decoder
probe. Every numbered picture and stereo sample frame again matched the
independent expected output. The exact Mac hand input and completed XML
download passed the independently provisioned Apple 1.10 DTD validator on
Linux. This proves the admitted XML grammar and Studio behavior; it does not
certify interchange inside Final Cut Pro, physical chooser/speaker interaction,
unrestricted XML, AAF or native Final Cut libraries.

[FCPXML_INTERCHANGE.md](FCPXML_INTERCHANGE.md) defines the supported operators,
retime admission and explicit refusals. [FCPXML_SCHEMA_VALIDATION.md](FCPXML_SCHEMA_VALIDATION.md)
records the pinned, separate schema validator. The accepted 1.9 shared subset
has no separate 1.9 DTD certification.

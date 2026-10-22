# Final Cut Pro XML timeline interchange

CINEMATICUM imports a bounded, public FCPXML timeline and exports standalone
FCPXML 1.10. The importer accepts the documented shared subset of standalone
1.9 and 1.10 documents. This workflow does not implement AAF, Final Cut Pro's
native library format, or a complete exchange of every Final Cut Pro edit.

## Use the shipped controls

1. Open the destination project and import the media that the timeline uses.
2. Choose **Interchange → Format → Final Cut Pro XML (.fcpxml)**, then **Import
   FCPXML**. Select a standalone UTF-8 `.fcpxml` or `.xml` file, up to 8 MiB.
3. For each XML resource, choose an existing project asset. Automatic matching
   works only when the XML includes CINEMATICUM's recorded SHA-256 and exactly
   one imported asset has those bytes. Filenames and external paths are not
   fuzzy-matched. An explicit relink to different content is disclosed and
   still must pass media type, dimensions, clock and source-window checks.
4. Choose **Review imported timeline**. Read the supported-edit and connection
   warnings, then choose **Replace timeline**. Inspection and review do not
   save or modify the project. Applying is one undoable change; Undo restores
   the previous edit, and Redo reapplies the candidate.
5. Save normally. The previous active sequence and existing sequence library
   remain available. The imported active timeline and its actual compound
   sequences become editable native sequences. A differently formatted XML
   must be imported into an empty project so existing sequence clocks are not
   changed.
6. To exchange the current edit, choose **Export FCPXML → Prepare FCPXML file**
   and use the resulting download. Unsaved current edits are included. Media
   remains in the project and must be relinked in the receiving editor.

The format selector defaults to OpenTimelineIO when the dialog is opened.
Existing OTIO import/export remains a separate workflow with its own supported
operators and limitations. A format change clears a previously inspected file
or prepared download; an asynchronously returned result cannot apply to a
changed project or stale dialog operation.

## Supported mapping

| Public XML | Native result and restrictions |
| --- | --- |
| One project and sequence | Exact rational project rate, explicit progressive square-pixel SDR Rec.709 format, stereo 48 kHz output. Frame starts/durations must be integral project frames. |
| `asset`, original `media-rep` | Links only to media already owned by the destination project. Actual picture dimensions, frame rate and active mono/stereo audio stream information must agree with the declaration. No original URL is opened. |
| Asset/source `start`, sequence `tcStart` | Nonzero source and sequence origins are subtracted in rational seconds before mapping native positions. Retained origins survive save/reopen, repeated imports, native sequence-library storage and project archive relocation. |
| Primary spine and gaps | Cut positions, empty intervals and explicit sequence out points are retained. Same-spine overlap is refused. |
| Connected video/audio and secondary spines | Exact timeline positions and picture stack order become independently editable native lanes. Connections are not native magnetic-follow editing relationships. |
| `media/sequence` and `ref-clip` | Shared compound resources remain real nested sequences. Trims use the exact compound source clock. Nested formats must match the project clock and canvas. |
| Simple generic `clip` container | Exactly one contained primary item or spine becomes a real nested sequence. Its own selected source window is preserved. |
| Separate `video` and `audio`, or `srcEnable` | Picture and source sound selection is explicit. J/L splits must be represented as separate picture/audio elements. One mono/stereo stream is supported; custom channels, audio-role routing and multiple active streams are refused. |
| `adjust-conform` | Fit only. Other spatial conform modes must be rendered or converted explicitly. |
| `adjust-transform` | Static position, uniform scale, central anchor and rotation. Nonidentity transforms require equal source/sequence dimensions. Apple's position units use a percentage of original frame height; its positive rotation is counterclockwise. The native conversion accounts for the different canvas-normalized coordinates and rotation sign. |
| `adjust-blend`, `adjust-volume` | Normal source-over opacity and static clip dB level become native opacity/gain. Keyframed parameters and other blend modes are refused. |

A sequence may contain at most 256 native clips, 16 picture lanes and 16 audio
lanes. The existing project limits still apply: 64 sequences, 4,096 authored
clips, eight levels of nesting and 1,024 expanded render instances. Timelines
are bounded to six hours. The parser separately limits the upload to 8 MiB,
30,000 XML elements, depth 40, 1,024 resources and 512 assets. Canvas dimensions
must be even, from 16 to 8,192 pixels on each edge and within the native total
pixel bound.

### Picture retime admission

The native renderer's FFmpeg frame-rate stage rounds input timestamps. That is
not a general implementation of evaluating an arbitrary Final Cut Pro source
time curve with nearest-neighbor sampling. The importer and exporter therefore
admit only independently measured compatible grids:

| Picture speed | Required source-clock and sampling conditions |
| --- | --- |
| 1× | Matching source/project frame rate and integral source-frame in point. |
| 0.5× or 0.25× | Explicit `floor` sampling, matching rates, integral source in, and an integral number of consumed source frames. Native repeated pictures then match the independent floor oracle. |
| 2× | Matching rates and integral source in, plus an actual decoded presentation-timestamp proof for the selected source extent. All decoded PTS must agree with best-effort timestamps and form consecutive exact project-frame ticks from source zero. The proof is bounded to the first 4,096 source frames and an eight-second foreground decode budget. Real reordered H.264 B frames are covered by the regression. |

Native compound sequences have a constructed project-frame clock. Direct 2×
media must pass the source proof; quantized Matroska clocks, variable/ambiguous
presentation timestamps and unproved longer windows are rejected. The proof
binds to the actual owned file identity and invalidates its cache if the file
changes. It inspects decoded presentation order, not packet decode order.

Other positive picture speeds, fractional picture source in points, mixed
source/project rates, frame blending, optical flow and reverse XML maps are
refused. Negative-map endpoint sample parity needs an external Final Cut Pro
numbered-frame export/render oracle; a self-roundtrip is not that evidence.
Native reverse and the existing OTIO reverse workflow are unchanged.

An audio-only element may express an exact positive 0.25–4× constant interval
through the native pitch-preserving tempo operation. This does not certify
identical DSP in a receiving application. Smooth/ramped/frozen maps and
`preservesPitch="0"` are rejected. When both `conform-rate` and `timeMap` exist,
their sampling declarations must agree. Anchored descendants on any retimed
parent are rejected instead of approximating their timing relationships.

## Source identity, saving and archives

The XML's resource IDs, document SHA-256, original source-clock origins, opaque
media-reference labels and actual linked-media SHA-256 values are retained as
provenance in the native project. Source paths remain project-owned paths.
No hidden native snapshot is embedded in the exported XML to override public
edits on reimport. Source media files are neither rewritten nor normalized by
this interchange.

The normal portable-project archive contains the native edits, nested sequence
library, retained clocks and owned media. The focused archive regression
restores to a different project directory and verifies the independently
expected decoded frames and every PCM sample. Source XML text itself is not
silently installed as a project dependency; retain the selected document if its
original annotations are needed.

Notes, descriptive metadata, role labels, track names/locks and library
keywords are not native authoring or mixer relationships in this workflow.
The import review states that distinction. External paths, bookmarks, proxy
representations and library/import-location directives are descriptive data,
never instructions to fetch or open a file.

## Explicit limits

Unsupported live edits produce an error before a candidate is applied or a
file is exported. These include transitions/dissolves, titles/captions,
multicamera/synchronized clips, effects and color graphs, keyframes, learned or
planar tracking, custom audio routing/pan/fades, track mute/solo/gain,
unsupported timing curves, noncentral anchors, nonuniform scaling, HDR or
scene-linear project output, interlacing, non-square pixels, 360/stereo formats,
and same-track native overlaps. Render an intended effect or stem explicitly
before exchanging it, or use the appropriate native/OTIO workflow.

The exported clip levels do not encode CINEMATICUM's final stereo limiter or
its tempo/filter implementation. The independent low-level PCM fixture stays
below that limiter's threshold. It establishes exact Studio media behavior for
that fixture, not sample-identical receiving-editor DSP for arbitrary mixes.
The receiving application's resampling, color management, compositing and
output codecs can also differ. The XML expresses the supported edit parameters;
no full visual/audio application-parity claim is made.

The XML parser accepts the normal name-only `<!DOCTYPE fcpxml>` declaration,
but refuses external/internal DTD references, entity declarations, executable
processing instructions, namespaces and unsupported edit elements. It never
loads a schema or follows a media URL. Media labels with path traversal,
backslashes, unsupported schemes or control characters are rejected. Actual
XML schema validation is a separate, offline acceptance gate.

## Verification and primary references

The hand-authored fixture in `test_fcpxml.py` uses exact 30000/1001 timing,
nonzero source and sequence origins, connected picture/audio, a trimmed shared
compound and a proved 2× segment. Its independent oracle enumerates all 40 source
frame counters and source channels and all 64,064 stereo PCM sample frames.
Further actual-media tests cover decoded B-frame timestamps, refusal of
quantized source clocks, repeated-picture grids, partial-tail refusal,
translation/scale/opacity/rotation, static audio level, explicit unsupported
edits, preserved prior sequences and portable archive relocation.

The external validator uses the official Apple FCPXML 1.10 DTD, SHA-256
`6044527401b6cc92a9d86383437794d8de801c1904b6d08409ce81720fd23f33`, extracted
from Apple's published DTD document. It validates the independently authored
input and an actual public export with pinned lxml, separately from the stdlib
production parser. Passing this DTD is not acceptance inside Final Cut Pro.
No installed Final Cut Pro application is available for that external gate.
The 1.9 import declaration describes the shared admitted subset; it is not a
separate claim of validation against an Apple 1.9 DTD.

Primary specifications:

- [Apple FCPXML DTD](https://developer.apple.com/documentation/professional-video-applications/document-type-definition)
- [Timing attributes](https://developer.apple.com/documentation/professional-video-applications/timing-attributes)
- [Timeline attributes](https://developer.apple.com/documentation/professional-video-applications/timeline-attributes)
- [timeMap](https://developer.apple.com/documentation/professional-video-applications/timemap)
- [Frame sampling](https://developer.apple.com/documentation/professional-video-applications/frame-sampling)
- [Rate conform](https://developer.apple.com/documentation/professional-video-applications/conform-rate)
- [Transform coordinates](https://developer.apple.com/documentation/professional-video-applications/adjust-transform)
- [Describing Final Cut Pro items](https://developer.apple.com/documentation/professional-video-applications/describing-final-cut-pro-items-in-fcpxml)

# Editorial systems: source evidence, clocks, interchange and trim modes

Research date: 2026-10-21. Scope: Shotcut, Kdenlive, Cinelerra-GG, Premiere and DaVinci Resolve. Public documentation was read through web retrieval; the Shotcut, Kdenlive, MLT and OpenTimelineIO source landmarks below were retrieved through the connected GitHub plugin. Proprietary application source was not available or inspected. This is a focused engineering comparison, not a claim to have reproduced those products.

## What the upstream systems actually store and expose

| System | Evidence inspected | Consequence for CINEMATICUM |
| --- | --- | --- |
| Shotcut | Application-specific metadata supplements the MLT editing/render graph. Source code reads frame-rate numerator and denominator independently. | A list of FFmpeg filters does not reproduce an editable Shotcut project; the authoring model and exact media clock also matter. |
| Kdenlive | Its project format extends MLT XML, supports separate sequences, and distinguishes project/UI metadata from rendering data. Profile interfaces retain numerator/denominator. | Use one authoritative project model, preserve nested domain identities, and keep rational rates through headless rendering. |
| Cinelerra-GG | Project XML preserves format settings; media is played according to the project format. Its rich XML project and interchange CMX3600 EDL are different representations. | Make conform rules explicit, and describe interchange losses instead of claiming universal project compatibility. |
| Premiere | Public UXP APIs expose FrameRate and TickTime; public EDL documentation describes a bounded interchange workflow. | Keep time precision separate from the displayed label, and make the source-time/timeline-time conversion explicit. |
| DaVinci Resolve | Public Edit documentation describes trim/sync tools, independent timeline curves, multicam and multiple timelines. | An editable timeline requires more than transport buttons. Track relationships, parameter animation and conform behavior must be represented in saved data. |

### Shotcut: MLT rendering is only part of the editable document

Inspected revision: `2b943b01b5b5ed0754a94b5f26ba0581b17d4035` (retrieved default branch).

- [`src/models/resourcemodel.cpp`](https://github.com/mltframework/shotcut/blob/2b943b01b5b5ed0754a94b5f26ba0581b17d4035/src/models/resourcemodel.cpp): `ResourceModel`/`ProducerFinder` walk producers, playlists and tractors, retaining track/clip locations. Media inspection obtains `meta.media.frame_rate_num` and `meta.media.frame_rate_den` before deriving a display value.
- [`src/widgets/mltclipproducerwidget.cpp`](https://github.com/mltframework/shotcut/blob/2b943b01b5b5ed0754a94b5f26ba0581b17d4035/src/widgets/mltclipproducerwidget.cpp): the media-properties UI derives FPS from the two metadata fields; displaying a decimal is not evidence of a decimal-only clock.
- [Official MLT XML annotations](https://www.shotcut.org/notes/mltxml-annotations/): Shotcut adds editable timeline, filter identity, transition, proxy and other application metadata to the rendering representation. These annotations distinguish user-facing objects from internal services.

The implementation lesson is to preserve source identity, editorial intent and UI state alongside an executable rendering graph. Merely opening an MLT service or reproducing the arrangement of its panels does not implement these semantics.

### Kdenlive and MLT: exact clock plus a shared renderable graph

Inspected Kdenlive revision: `60c117f7acdc8f309eef3ba24773af2d2e3a48fc`.

- [`src/profiles/profileinfo.hpp`](https://github.com/KDE/kdenlive/blob/60c117f7acdc8f309eef3ba24773af2d2e3a48fc/src/profiles/profileinfo.hpp): the profile interface exposes integer `frame_rate_num()` and `frame_rate_den()` separately from derived `fps()`.
- [`dev-docs/fileformat.md`](https://github.com/KDE/kdenlive/blob/60c117f7acdc8f309eef3ba24773af2d2e3a48fc/dev-docs/fileformat.md): `.kdenlive` extends MLT XML. Its format history describes the removal of duplicated UI/render representations that caused synchronization problems. Current sequence organization uses sequence tractors and a bin containing clips/sequences; track playlists and transitions are structural data. Most media remains referenced externally.
- [Official project settings](https://docs.kdenlive.org/en/project_and_asset_management/project_settings.html) and [general settings](https://docs.kdenlive.org/en/project_and_asset_management/project_settings/general_settings.html) distinguish the project profile and media/proxy handling.

MLT revision `62356dc1ddd663c507c471e255e79ca1aa250961`, [`src/framework/mlt_profile.h`](https://github.com/mltframework/mlt/blob/62356dc1ddd663c507c471e255e79ca1aa250961/src/framework/mlt_profile.h): `mlt_profile_s` stores integer rate numerator/denominator, image dimensions, sample/display aspect ratios, progressive state and colorspace. `mlt_profile_fps` exposes a derived floating-point value. This directly supports the distinction between a stored rational clock and a convenient numeric FPS value.

### Cinelerra-GG: project settings and exchange limitations

Additional source check: the project's [GitHub mirror at commit `2f5f5847bfeea491f69f5314dcbccaf6de4b22e4`](https://github.com/cinelerra-gg/cinelerra-gg/tree/2f5f5847bfeea491f69f5314dcbccaf6de4b22e4) is dated **2019-05-18**. It is not treated as the current 2026 implementation. Its [`cinelerra-5.1/cinelerra/edl.C`](https://github.com/cinelerra-gg/cinelerra-gg/blob/2f5f5847bfeea491f69f5314dcbccaf6de4b22e4/cinelerra-5.1/cinelerra/edl.C), blob `cc2e84fb3c7b128ab5ecb5716f0c8bb310979fd5`, was inspected directly. `create_objects` separates tracks, assets, global/session state, local session and labels. The XML reader has distinct handling for assets, mixers, tracks, clip EDLs, nested EDLs and viewer EDLs, with selective load flags. This confirms that native project loading is not equivalent to a flat cut-list import. Current documentation supplies the current product comparison; historical source supplies this narrower architectural observation. The current official source browser is [git.cinelerra-gg.org](https://git.cinelerra-gg.org/); its XHTML entry point was not readable by the web retrieval tool during this review.


The [official manual index](https://download.cinelerra-gg.org/view.php?file=CinelerraGG_Manual/cin-index.html) identifies the manual as dated 31 August 2026. [Project and Media Attributes](https://download.cinelerra-gg.org/view.php?file=CinelerraGG_Manual/Project_Media_Attributes.html) describes project-controlled playback, audio resampling and XML-persisted format attributes. This establishes public behavior; it does not establish the exact internal numeric type of its clock.

[Export to EDL](https://download.cinelerra-gg.org/view.php?file=CinelerraGG_Manual/Export_EDL.html) distinguishes Cinelerra's own XML EDL from CMX3600 interchange. The latter has a 999-event limit and a restricted editorial vocabulary; its documented export handles one video or one audio track per file, with imperfect cross-application reconstruction possible. It therefore provides no basis for saying that a CMX file transfers a complete composition, effect stack or audio session.

The source host linked by the [official homepage](https://www.cinelerra-gg.org/en) is [git.cinelerra-gg.org](https://git.cinelerra-gg.org/). The retrieval reader refused its XHTML content type. The historical GitHub mirror examined above is the only Cinelerra source revision asserted here; it is not the current host revision.

### Premiere: time coordinates and interchange are distinct concepts

Public UXP documentation, introduced with API version 25.6, exposes [`FrameRate`](https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/framerate) with a ticks-per-frame property and a derived FPS value. [`TickTime`](https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/ticktime) can be constructed from frame count plus FrameRate or from tick strings; it exposes explicit frame-alignment operations. These are documented extension interfaces, not access to Premiere's proprietary implementation.

[Timecode display format](https://helpx.adobe.com/premiere/desktop/organize-media/apply-labeling/change-timecode-display-format.html) includes audio-sample/millisecond displays and drop/non-drop frame choices. [EDL export](https://helpx.adobe.com/premiere/desktop/render-and-export/export-files/export-a-project-as-an-edl-file.html) recommends simple sequences, correct source timecode and selected tracks; merged audio/video relationships do not survive as merged objects. The practical implication is that display labels, exact sample/frame coordinates and interchange fidelity must be treated separately.

### DaVinci Resolve: shared editing semantics across specialist work

The [official Edit page](https://www.blackmagicdesign.com/products/davinciresolve/edit) documents context-sensitive/dynamic trimming, track targeting and sync controls, stacked/tabbed timelines, parameter curves, multicam synchronization and adjustment clips. Those behaviors require persistent relationships between clips and tracks. CINEMATICUM's existing track mute/solo and scalar easing are meaningful foundations, but they are not equivalent to this whole editing system. Its current project model has no nested sequence, multicam-angle or adjustment-layer representation.

The full Resolve reference PDF exceeded this retrieval tool's size limit; its detailed conform rules and internal implementation were not audited. No proprietary Resolve source or undocumented algorithm is claimed.

## Concrete implementation: exact rational clocks

The previous CINEMATICUM engine accepted only integer project FPS. `timebase.py` now stores the canonical reduced ratio in `frame_rate = {numerator, denominator}` and keeps `fps` as a derived compatibility value. Contradictory fields reject explicitly. Legacy integer projects continue to work. Labels 23.976, 29.97 and 59.94 normalize to 24000/1001, 30000/1001 and 60000/1001 respectively. The tested project range remains 1–60 FPS.

`engine.py` sends the exact ratio to source conform, image-sequence input, the canvas clock and output encoding. PTS placement uses the inverse rational time base. Duration bounds and audio sample indices use `Fraction` arithmetic. Adjacent clip lengths use the difference between rounded absolute boundaries, preventing repeated per-clip sample-rounding drift. Picture curves sample integer frame positions; audio curves retain continuous sample coordinates and the original animation/fade domain.

This work also fixed a real export-tail defect: a redundant output frame limit could stop muxing before the audio limiter flushed 239 samples. The graph already bounds the picture count; retaining only that bound lets audio flush. A 48 kHz MOV movie timescale prevents AAC edit-list durations from being rounded to milliseconds. Actual output rate, frame count, dimensions and audio duration are checked before publishing the file. Blender adapters receive the same rational clock through `fps`/`fps_base` and exact image-sequence encoding.

Acceptance is in `test_timebase.py`: H.264 and ProRes packet PTS are checked against exact fractions for all three broadcast rates; decoded PCM length is checked; forward/reverse cuts with fractional sample boundaries preserve pictures and sample envelopes; a retimed rational trim and exact PNG preview are checked. Six-hour arithmetic and 100,001 consecutive one-frame sample spans are checked without accumulating rounded frame durations. Existing decoded timeline, animation, waveform, preview and Blender adapter regressions also pass.

## Implemented bounded OTIO exchange

OpenTimelineIO source revision `f8a2f36df61ce88eb6b73a57df393a87d3e3e42e` was inspected through the GitHub plugin: [file-format specification](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/f8a2f36df61ce88eb6b73a57df393a87d3e3e42e/docs/tutorials/otio-file-format-specification.md), [generated serialized fields](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/f8a2f36df61ce88eb6b73a57df393a87d3e3e42e/docs/tutorials/otio-serialized-schema-only-fields.md), [Clip implementation](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/f8a2f36df61ce88eb6b73a57df393a87d3e3e42e/src/opentimelineio/clip.cpp) and [multiple-track fixture](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/f8a2f36df61ce88eb6b73a57df393a87d3e3e42e/tests/sample_data/multiple_track.otio). The public schema uses per-object versions, numeric RationalTime values/rates, namespaced metadata, and active media references in Clip.2. Its documentation recommends the official library for general reading/writing. CINEMATICUM implements only a bounded subset and independently verifies its output with that library.

`interchange.py` now exports Timeline.1 → Stack.1 → Track.1 → Clip.2/Gap.1, with ExternalReference.1, TimeRange.1 and RationalTime.1. Video source audio receives companion Audio-track cuts, rather than depending on another application's handling of embedded audio. The canonical integer rate ratio is stored in namespaced metadata alongside the numeric OTIO rate. A private authoring snapshot preserves CINEMATICUM effects, mixer settings and titles for an unchanged self-roundtrip. A digest of the public editorial structure detects external changes so stale private effects cannot silently replace newly edited cuts; the digest is not an authenticity or security mechanism.

Imports resolve references only to already-imported local assets using actual SHA-256 or an explicit target-reference-to-asset mapping. OTIO paths and URLs are never opened. Unsupported transitions, timewarps, nested or trimmed compositions, same-track overlaps on export, nonintegral cut durations and unrepresentable trailing gaps refuse explicitly. Unknown effects/markers and cross-editor compositing limitations produce review warnings. An import returns an unsaved candidate and cannot overwrite project files.

`test_interchange.py` verifies the wire format with the official [OpenTimelineIO 0.18.1 package](https://pypi.org/project/OpenTimelineIO/0.18.1/), source-timecode/sample-clock conversion, explicit relinking boundaries, stale-metadata rejection and identical decoded picture/PCM after a full self-roundtrip. The package is a scratch test dependency; production does not install a plugin discovery system or require a compiled Python extension. This is cut-timeline OTIO interoperability, not full AAF, multicam, nested-sequence or effect translation.

## Implemented slip, slide and outgoing-cut roll

The 0.7 increment adds actual operations to `web/editing.js` and a shared-history
Trim dialog in `web/app.js`. The dialog previews the permitted integer-frame
offset before applying it. The operation planner returns replacement clip data;
the UI applies that candidate in one existing project-history transaction.

| Operation | What changes | Preserved relationships |
|---|---|---|
| Slip source | The selected clip's source in-point advances along its playback direction, accounting for speed and reverse. | Timeline start, duration and authored animation remain fixed. Derived stabilization/tracked-mask measurements are cleared because they no longer describe the selected content. |
| Slide shot | The selected clip moves; the touching previous and next clips are trimmed to accommodate it. | Selected source range, duration and animation remain fixed; the sequence's outer endpoints remain fixed. Neighbor animation and fade domains retain their original coordinates. |
| Roll outgoing cut | The selected clip's end and the next touching clip's start move together. | The outer endpoints and continuous source relationship are retained; both clips preserve their animation/fade domains. |

Available media handles and a one-frame minimum clip duration bound the accepted
offset. Missing or ambiguous adjacency, locked tracks and unsupported source
relationships reject before editing. Zero offset creates no history. This
implements the declared touching-clip operations; it does not add multicam,
nested sequences or a general sync-group trim system.

`test_trim_edits.py` checks timing invariants, fractional source clocks,
speed/reverse, handle limits, locked-track rejection and actual decoded exported
frames. `test_trim_ui_macos.py` and `macos/TrimSmoke.js` independently seed three
touching eight-frame clips at source in-points 8/24/40 and 24 fps. Native stages
exercise slip +3, slide +2 and roll −2 through DOM controls, verify exactly one
undo/redo, save and export. An independent oracle reads binary frame-index
patches and a moving rectangle from every output frame; its expected sequence
does not call the trim implementation. A separate stage checks both source
handle limits, zero no-op and locked-track behavior. Native execution reports,
rather than the presence of these harnesses, establish pass/fail.

## Remaining editorial boundaries

- CINEMATICUM still needs a distinct nested-sequence/multicam model, sync-group and source-channel mapping, broader contextual trimming and a managed offline/proxy conform workflow. The bounded slip/slide/outgoing-cut roll operations above do not supply those systems.
- Movie timeline rendering remains SDR Rec.709. The separate OCIO/RAW/HDR still-image worker preserves float EXR masters but does not add a whole-timeline scene-linear/HDR pipeline, field-based processing or calibrated external monitoring.
- Source-rate conform is nearest-frame selection. Tempo processing is FFmpeg `atempo`; there is no claim of optical-flow retiming or proprietary speech/music processing parity.
- Interchange must declare what it can carry. CMX3600, AAF, OTIO and application-native projects have different semantics. None should be presented as a complete conversion without a tested feature mapping and explicit losses.
- Publicly documented product behavior and inspected open-source structures guide independent implementation. No upstream application is embedded or launched by these changes.

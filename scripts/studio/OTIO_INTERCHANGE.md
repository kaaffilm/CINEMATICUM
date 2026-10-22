# OTIO composition interchange

Studio imports and exports ordinary OpenTimelineIO JSON through **Interchange**.
The importer does not execute OTIO adapters, plugins or target URLs. References
must resolve to already admitted media by an explicit mapping or verified
SHA-256. Review is read-only, Apply creates one undo checkpoint, and Save remains
a separate action. No extra Python package is needed by the application for
this JSON path; upstream OpenTimelineIO is required by its compatibility tests.

## Public operators

| OTIO structure | Studio behavior |
| --- | --- |
| Video/Audio Track, Clip, Gap | Ordered cuts, rational source time, explicit/trailing/all-gap duration. Video imports are picture-only; explicit Audio tracks carry sound. |
| Constant `LinearTimeWarp.1` | One signed scalar with magnitude 0.25–4. The source-range duration is the output duration. The source start is the lower bound of the consumed window; negative scalar reverses the selected, conformed window. |
| `SMPTE_Dissolve` | The transition adds no timeline duration. Its in/out offsets select real adjacent source handles. Picture mixes associated RGBA linearly; source audio uses complementary linear sample envelopes. |
| Same-track overlapping native clips | Export creates ordered parallel Track lanes inside a Stack. Native list/painter order and additive audio are preserved, even when painter order differs from source start order. |
| Nested Stack/Track | Import creates editable sequences, preserving shared-clock timing, source trims, constant time effects, disabled state, explicit duration and picture/audio roles. |
| Trimmed Track, trimmed root Stack | The trimmed range becomes the active edit. Composition ranges outside their contents produce explicit transparent/silent padding. Missing external media handles are rejected. |

The reverse-window convention is explicit because OTIO is an interchange data
model, not a media renderer. A receiving application must implement the same
time-effect convention to reproduce the same pictures. Studio renders its
selected/conformed window in reverse order, and reverses source PCM before its
existing pitch-preserving tempo filter. This is constant speed retiming, not
optical flow, a variable speed ramp or a new time-stretch algorithm.

At output transition frame `f` of `N`, the incoming weight is `f/N`. Alpha is
weighted with the same factors as associated color, then unassociated for stored
RGBA. This correctly handles translucent sources and fades through transparent
gaps. Audio evaluates the linear envelope at every 48 kHz sample. Normal-speed
nested sequences share the parent's absolute sample grid, including at
30000/1001 and 60000/1001; independently rounded local durations cannot introduce
a one-sample padded tail at a nested cut.

An imported dissolve is a native sequence carrying a versioned `otio_dissolve`
operator and two editable operand sequences. The operator enforces its two
full-canvas inputs and complementary envelopes. Edit source content inside the
operand sequences; incompatible edits to the operator structure are refused.
Public export regenerates an actual `Transition.1`, not an opacity annotation.
The ordinary 8-bit and 16-bit SDR graph, processed-frame renderer and sequence
preview implement this operator. This does not add support to a separate float
movie backend that explicitly rejects live nested sequences.

## Private authoring round trips

Public export carries source references and timing operators. Grades, transforms,
tracking, masks, titles, arbitrary mixer automation and other authoring remain
namespaced CINEMATICUM metadata; the export dialog warns about these limits.
An unchanged document restores complete active/inactive sequence authoring only
after all referenced media identities match, project normalization passes, and
regenerated public timing/media structure agrees. Public edits invalidate stale
private state. External public imports preserve existing destination sequences.

Saving, reopening and project archive export/restore retain the operator and
its editable nested dependencies. Archive restoration creates a new project
identity and keeps original source bytes unchanged. Object-key ordering in a
canonical JSON archive is not authoring state; array/painter order is preserved.

## Explicit bounds and refusals

- Native limits remain 64 sequences, eight nested sequence levels, 256 clips per
  sequence, 4,096 authored clips and 1,024 expanded instances. Each sequence has
  at most 16 picture tracks and 16 audio tracks. A same-track overlap export has
  at most 16 ordered lanes. These limits are validated after conversion.
- Input traversal allows 32 composition levels, 4,096 item/transition events,
  512 items per input Track and 48 children per input Stack. Existing strict JSON
  document/depth limits, including 8 MiB, still apply. OTIO Track/Stack wrappers
  do not automatically count as native sequence levels: only true identity
  wrappers are collapsed.
- Placement, output durations and transition offsets must map to integer
  project frames. Fractional media source-in points are preserved. A padded
  composition trim whose visible boundary cannot map to output frames is
  refused. The existing six-hour timeline bound applies.
- Only `SMPTE_Dissolve` is accepted. Wipes and plugin transitions, adjacent or
  overlapping transitions, missing source handles and offsets beyond adjacent
  item durations are refused. An explicit zero-duration Gap can represent an
  end fade; a bare transition without both adjacent items is refused.
- Only one explicit `LinearTimeWarp.1` per item is accepted. FreezeFrame,
  zero/nonfinite/out-of-range scalars, variable or unknown time effects and
  multiple stacked timewarps are refused. Unsupported ordinary non-time effects
  and markers produce warnings instead of a false portable-effect claim.
- External references must be admitted media. Image sequences, generator media,
  unknown schemas and general adapter/plugin execution are unsupported. This
  work does not implement AAF, Premiere XML or native Resolve project exchange.

## Verification

`test_otio_compositions.py` uses real FFV1 frames, wide binary source-frame
counters, independent deterministic stereo PCM and translucent PNGs. Actual
upstream OTIO parses/re-serializes the documents and expands transition handles.
Tests compare every decoded frame/sample for reverse, overlap, nested trims and
public/private round trips, verify associated alpha independently, and verify
the fractional-rate dissolve against a separately computed 22,422-sample oracle.
Existing interchange, editorial, audio, sequence and installer tests remain
required. No mock rendering constitutes acceptance.

The real-control browser gate uses the same four foreground phases as native:

```sh
NODE_PATH=/absolute/playwright-1.51.1/node_modules node test_otio_compositions_browser.cjs \
  --python /absolute/verification/bin/python \
  --browser /absolute/chrome-for-testing/chrome-linux64/chrome \
  --evidence /absolute/new-otio-evidence
```

Dependencies are Python with NumPy and upstream OpenTimelineIO 0.18.0 or 0.18.1,
FFmpeg/ffprobe on PATH, Playwright 1.51.1 and an explicitly supplied H.264-capable
Chrome for Testing. Every report records the observed upstream version and
browser executable SHA-256. Browser success does not certify macOS.

For native acceptance, compile the existing `macos/SmokeTest.swift` on the Mac
and freeze the exact local runtime/web/helper inventory:

```sh
swiftc macos/SmokeTest.swift -o /absolute/owned/NativeSmoke
python3 -B -c 'from test_otio_compositions_macos import source_inventory,write_json; from pathlib import Path; write_json(Path("/absolute/owned/otio-source.json"),source_inventory())'
```

Run each command as one foreground operation, in order:

```sh
python3 -B test_otio_compositions_macos.py --binary /absolute/owned/NativeSmoke --operation prepare --output /absolute/owned/prepare --fixture-workspace /absolute/new-fixture --source-manifest /absolute/owned/otio-source.json
python3 -B test_otio_compositions_macos.py --binary /absolute/owned/NativeSmoke --operation author --output /absolute/owned/author --fixture-workspace /absolute/new-fixture --source-manifest /absolute/owned/otio-source.json
python3 -B test_otio_compositions_macos.py --binary /absolute/owned/NativeSmoke --operation render --output /absolute/owned/render --fixture-workspace /absolute/new-fixture --source-manifest /absolute/owned/otio-source.json
python3 -B test_otio_compositions_macos.py --binary /absolute/owned/NativeSmoke --operation archive --output /absolute/owned/archive --fixture-workspace /absolute/new-fixture --source-manifest /absolute/owned/otio-source.json
```

Each coordinator phase is limited to 18 seconds and its UI helper to 14 seconds.
It owns and joins the server, helper process group and jobs; a timeout records a
failure and kills the owned process group. Repetition requires a new fixture,
and source changes during a phase invalidate its result. Author uses actual
FileList input, relink controls, Review, Apply, Undo/Redo, Save, reopen and a real
OTIO attachment. Render verifies the actual processed transition frame and
downloaded ProRes pixels/PCM. Archive uploads the real exported ZIP, opens its
new project and independently verifies its downloaded movie. All content is
synthetic ENGINE TEST material. Native certification requires measured Mac
results against the final integrated source and is not inferred from Linux.

## Upstream semantics

- [OTIO 0.18.1 timeline structure](https://opentimelineio.readthedocs.io/en/v0.18.1/tutorials/otio-timeline-structure.html)
- [OTIO serialized schema](https://opentimelineio.readthedocs.io/en/latest/tutorials/otio-serialized-schema.html)
- The installed upstream `opentimelineio.algorithms.track_with_expanded_transitions`
  provides the independently checked transition-handle expansion.

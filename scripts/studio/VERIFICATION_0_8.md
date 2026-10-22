# CINEMATICUM Studio 0.8 verification

Verified 2026-10-21. All rendered acceptance material described here is
**synthetic engine-test footage**. These results establish the specified
operations; they do not establish a completed film, full professional parity,
or a successful neural-generation run.

## Release result

| Gate | Executed result |
| --- | --- |
| Full Python regression suite | 425 tests: 423 passed, 2 skipped; 135.743 seconds |
| JavaScript syntax | All 31 web/native acceptance scripts passed |
| Native recovery, two separate application/server runs | Checkpoint 4/4 checks; restart/recover/undo/redo/save/render 5/5 |
| Native production workflow | 29/29 checks, including actual ProRes picture and stereo audio |
| Native archive workflow | 28/28 checks; every decoded RGB frame and PCM sample identical after restore |
| Native 3D output controls | 10/10 checks, including actual EXR and retained-source attachments |
| Native camera, source animation and mesh integrity | 9/9 checks with a real saved/reopened Blender scene |
| Independent native EXR pixel acceptance | 18/18 numerical/file-identity checks |
| Native recovery, resource lifetime, generation schema and archive HTTP contracts | 34 tests passed |
| Native EXIF orientation | 6 tests passed, including all eight pixel permutations |
| Native nested-media OTIO | 19 passed, 1 optional independent-reader check skipped |
| Native application | arm64 launcher and icon compiled; version 0.8.0/build 8 installed; all 39 bundled runtime files verified |

Check counts in native harnesses are assertions within those workflows, not
additional Python `unittest` cases. The full regression suite used Python
3.12.14, FFmpeg 6.1.1 and Node 24.19.0 on Linux, with the existing isolated
imaging runtime. Native validation used WKWebView, FFmpeg 8.1.1 and Blender
5.2.2 LTS. The opened application service identified itself as
`CINEMATICUM/0.8.0 Python/3.14.3`.

The two full-suite skips were explicit: no genuine camera RAW fixture was
provided to `CINEMATICUM_RAW_TEST_FILE`, and the optional official OpenTimelineIO
reader was not installed in this execution environment. The CI workflow installs
the official reader. Neither skip is counted as a pass; this release does not
claim a newly verified genuine-camera RAW development operation.

## What the tests establish

### Recovery and playback ownership

The native checkpoint phase authored a clip and an unsaved title after 40
add/delete cycles. The committed project bytes remained unchanged. A separate
server and native web-view process recovered that draft explicitly, exercised
Undo and Redo, saved the actual raster title, and exported/decoded 12 H.264
frames. API regressions cover revision conflicts, out-of-order acknowledgements,
two editor identities, damaged files, bounded saved-version retention, failed
atomic saves, and a failed save followed by new media admission.

The resource-lifetime test evaluates the shipped media-management functions.
Deleted and rebound media release listeners and audio nodes; inactive resources
remain bounded to 12 and 24 simultaneously active layers are retained. This is
an ownership regression, not a claim of measured long-session memory limits.

### Production plan to actual edit

The native test imports two synthetic moving-picture sources with distinct
tones, selects a shot plan, confirms missing-source refusal, saves/reopens an
unresolved plan, binds real takes, previews source handles, downloads the
persistent JSON attachment, and assembles one undoable cut. Empty/fractional
In values stay invalid. Valid shot identifiers `__proto__` and `constructor`
survive the entire workflow without prototype-map collisions.

The resulting ProRes contains exactly four red then four blue frames, with the
expected 8-frame, 24 fps duration and 48 kHz stereo PCM. The saved selected-take
bindings and downloaded requirements are independently checked. No generation
job, filler shot, original source overwrite or issuance transition occurs.

### Portable project preservation

The native test creates a real edit and raster title, renders ProRes, downloads
the generated archive, selects those exact bytes for upload through the shipped
Archive controls, restores a new identity, explicitly opens it, and exports
again. Every decoded frame and PCM sample matches. Original project/inventory
bytes remain unchanged; source/title identities, LUT and workflow are retained.

Backend tests also remove the original source location before replay, preserve
and rerender actual OCIO EXR/display results, stream a 257 MiB source fixture,
retain RAW/scene/master dependencies, and reject missing closure members,
tampering, unsafe paths/types, duplicate/colliding names, compressed-member
resource attacks and an archive whose ZIP overhead exceeds the 64 GiB bound.
The HTTP tests verify interrupted/full-queue uploads and immediate queued
cancellation cleanup while an earlier worker is still running. Restart cleanup
only removes reserved regular upload files; unrelated paths and symlinks remain.

### Scene-linear masters and useful passes

One middle frame of a three-frame moving emission plane is rendered by real
Cycles. The retained source keeps the complete authored animation. An
independent OpenEXR decoder checks float32 storage, all actual channels,
dimensions, the exact 24000/1001 clock and hashes. Results include:

| Quantity | Measured result |
| --- | --- |
| Scene-linear red maximum | 4.0, retained above display white |
| Alpha range | 0 to 1 |
| Maximum premultiplied error against `red = 4 × alpha` | 0 |
| Matte diffuse red | 0.2158605158, matching independently decoded sRGB `#808080` with IOR 1 |
| Horizontal temporal vector magnitudes | 2.627665 px in each neighboring-frame component |
| Vertical temporal motion | 0 |
| Normal X minimum | approximately −0.5 |
| Surface depth range | approximately 2.662 to 3.323 m |

The native UI also authors transparency/output/pass controls, exercises undo,
requests a subset range, saves the recipe, and obtains actual movie, `.blend`
and EXR archive responses. Camera verification reopens the saved source and
samples a pole-crossing path without a roll jump. Undefined complete aim paths
are rejected before Blender starts. Deformed vertices retain both UV islands
and the full source playback range.

Native testing exposed Blender 5 media-type enum ordering and current EXR pass
names. Runtime handling now supports those actual APIs while retaining the
older API branch. Older Blender versions were not executed by this native gate.
The diffuse fixture explicitly removes the dielectric specular partition with
IOR 1; the numerical tolerance was not widened to conceal a mismatch.

### Media identity, orientation and generation contracts

Nested OTIO tests identify title plates and every retained compositor source by
content hash, relocate to new asset IDs/paths, and compare decoded picture/PCM.
A coincident old ID cannot substitute unrelated bytes. Private restoration
rejects incomplete/incorrect dependency identities.

Orientation tests use asymmetrical real image pixels, including mirror cases,
and compare admission dimensions and rgba64 decoding for all eight EXIF values.
FFmpeg 8's display-matrix metadata is handled when textual EXIF tags are absent.
Actual OCIO/HDR image tests agree with manually oriented inputs.

Generation preflight tests use declared backend schemas to verify socket types,
output indices, numeric bounds, dynamic inputs, video savers and a reachable
positive prompt. They establish preflight behavior, not installed model weights
or generated media quality. No paid-provider or neural-model parity is claimed.

## Reproduction

Run the regression suite with an actual isolated imaging interpreter:

```bash
CINEMATICUM_IMAGING_PYTHON=/path/to/imaging/python \
  python3 -m unittest discover -s scripts/studio -p 'test_*.py' -v
```

Native acceptance entrypoints are `test_recovery_ui_macos.py` (checkpoint and
recover stages), `test_production_ui_macos.py`,
`test_project_archive_ui_macos.py`, `test_scene_masters_ui_macos.py`,
`test_camera_integrity_blender.py` and `test_scene_masters_blender.py`.
Use the compiled `macos/SmokeTest.swift` helper for the UI scripts and fresh,
isolated output folders. The EXR numerical script requires the imaging Python
with NumPy and OpenEXR. These commands operate on synthetic test projects.

## Boundaries retained

The movie timeline remains SDR and the live preview is not a calibrated HDR
finishing monitor. Float still and 3D masters do not imply a float movie
compositor. Complete multicam/nested editing, advanced retiming, deep/Bezier
compositing, neural masks/tracking, reconstruction solving, unrestricted
modeling/rigging/simulation, spectral/differentiable rendering, plugin hosting,
collaborative editing and paid model integrations remain outside the implemented
scope. Archives do not embed external engines/model weights or guarantee the
external dependencies of an opaque imported `.blend`.

The native package still requires the installed Python/media/optional engines
and is not signed or notarized. The capability ledger remains
`parity_complete: false`. Test outputs are not production footage and have no
film issuance effect.

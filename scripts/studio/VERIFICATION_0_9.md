# CINEMATICUM Studio 0.9 verification

Evidence recorded for the 0.9 source on 2026-10-21. The complete Python regression
run and installation of a 0.9 candidate have finished. This remains a provisional
verification record because the explicitly pending native gates below are open
and the final candidate has not been published.

All rendered acceptance material described here is **synthetic ENGINE_TEST
footage** in isolated test projects. These checks establish the specified
operations. They do not establish a completed film, full professional feature
parity or production-quality neural output. The completed reduced generation
run, its completed output acceptance and candidate installation are recorded
separately from final publication.

## Recorded execution results

| Gate | Executed result | Scope of the evidence |
| --- | --- | --- |
| Native Blender hierarchy | 6/6 checks passed | Real CPU frame, saved/reopened source, three-level parenting, local animation and affine transforms at subframes |
| Native Blender UVs and modifiers | 9/9 checks passed | Actual UV loops and smart unwrap, five additional live modifier types, evaluated geometry and source replay |
| Native Blender compute-device configuration | 4/4 checks passed | CPU contract, actual Metal enumeration, selected device identity and saved/reopened GPU configuration |
| Native 3D authoring controls | All eight stages passed | Hierarchy, cage conversion, UV projection/move/unwrap, Array creation/offset and saved Metal selection |
| Native editorial controls | All four stages passed | Sequences, captions, exported source-audio mapping and manual multicamera cuts; the latest nested-sequence stage was rerun successfully |
| Native cubic roto/compositor controls | 26/26 checks passed | Real authoring, history, saved cubic geometry, effect masks, rendered frames and movie pixels |
| Native media/proxy controls | All four stages passed | Baseline, cancellation, actual preview proxy, exact-original relink and original-based exports |
| Native local-generation controls | 10/10 checks passed, using an explicitly labelled cancellation fixture | Real UI, project workflow persistence and Store cancellation; no runtime installation, model weights or inference |
| Integration metadata and generation ownership regressions | Passed in focused runs and the recorded full suite | Metadata retention, job/endpoint ownership and prior-workflow preservation |
| Native Metal picture render | **Completed normal app job in 82.430497 seconds; independent verification passed 18/18 checks in 6.694 seconds** | Actual decoded GPU-rendered picture, matching job/recipe/hash receipts and reopened source; the earlier 15.522-second bounded test timeout is resolved by this separate completed operation |
| Native live-audio PCM gate | **Unresolved; intermittent second-stream silence reproduced** | An earlier 32,768-sample second-stream/channel-swap comparison passed, but the latest fresh native run returned zero raw/output PCM despite correct selected-track metadata and a passing calibration; final gain/pan/restart acceptance is also open |
| Complete Python regression suite on frozen current source | **515 tests in 153.974 seconds; `OK`, zero failures and zero skips** | Includes the real optional imaging runtime, genuine camera RAW fixture and official OTIO reader; separate native acceptance gates are not implied by this aggregate |
| Native 0.9 candidate installation | Passed | 53 runtime file identities verified by SHA-256, four existing project JSON identities preserved, prior bundle archived and normal launch verified |
| Actual managed runtime installation/startup | Passed | 10,634,173,896 verified bytes: 71 wheels, three model-weight files and pinned ComfyUI 0.42.1 source; owned startup confirms MPS, the encoder and 11 required nodes |
| Actual managed neural generation | **First reduced run completed; independent output 14/14 and native playback 14/14 checks passed** | A 192 × 128, nine-frame, four-step Wan job with seed 42 completed in 44.410 seconds; every frame decoded and all nine native canvas pictures matched the actual source; default-preset and production-quality acceptance remain open |
| Genuine camera RAW integration | **Passed: one test in 1.534 seconds, no skip** | A real Kodak DC50 upstream fixture was developed through rawpy/LibRaw; independent float-pixel, white-balance, source-preservation and tamper checks passed |
| Official OpenTimelineIO integration | **Passed: one test in 0.463 seconds, no skip** | The official 0.18.1 reader/writer accepted the actual bounded exchange and retained the tested clock, gaps, cuts and CINEMATICUM roundtrip |

The first three Blender rows contain 19 backend checks in total. Native stage
counts and individual assertion counts are different units; they are not added
to the Python `unittest` total. A checked-in harness is not evidence that it ran.
The reported native scene work used Apple Silicon, macOS 26.5.2, WKWebView and
Blender 5.2.2 LTS. An earlier full run recorded 509 tests in 150.533 seconds with
two skips. The final frozen-source run supersedes it with 515 tests, zero skips
and actual execution of both optional integrations. Native WKWebView/Blender
command-line acceptance is recorded separately; the 515-test pass does not
override the reproduced native audio failure. The local and native worktrees
match on all 53 runtime files; the installed candidate differs in three files.

## What the passed native gates establish

### Hierarchy, UVs and actual Blender geometry

`test_scene_authoring_blender.py` executes the real engine and independently
reopens the retained `.blend`. The hierarchy stage preserves the authored recipe
and real parent links across three levels, compares composed matrices at five
subframe positions, and produces an actual CPU-rendered frame. The comparisons
include inherited nonuniform scale and shear, rather than only comparing local
translation values.

The modeling stage inspects the actual Blender quad-loop UV coordinates, reopens
the saved source and verifies that the mapping survives. It executes smart
unwrap and separately checks actual geometry changes from Array, Solidify,
Decimate, Smooth and Simple Deform. These checks establish engine execution and
retained modifier data; they do not imply every combination of the eight
supported modifier types has been exhaustively tested.

`test_scene_authoring_ui_macos.py` passed the following stages through
CINEMATICUM's own native controls:

| Stage | Operation checked |
| --- | --- |
| `hierarchy` | Parent selection and retention of local material/animation data |
| `convert` | Conversion to an editable quad control cage |
| `project` | Box UV projection and complete saved face-corner mapping |
| `uvmove` | Actual pointer movement of selected UVs while preserving seams |
| `unwrap` | Real smart unwrap with a changed, finite mapping |
| `array` | A live Array modifier and actual repeated geometry |
| `arrayoffset` | An edited modifier offset and updated evaluated geometry |
| `gpu` | Explicit Metal selection saved without changing scene geometry |

The separate device stage enumerates actual available Metal devices and checks
the saved/reopened GPU flag and selection recipe. The early `device-render`
attempt timed out at 15.522 seconds; enumeration alone did not close the picture
gate. A later job using the normal application render path completed in
82.430497 seconds and supplied actual output. The bounded attempt remains a
recorded timeout, while the separate completed operation resolves the Metal
picture acceptance gate.

`macos/verify_metal_result.py` independently verified that completed job without
importing CINEMATICUM runtime modules. Its **18 checks passed in 6.694 seconds**.
The delivered movie contains exactly one H.264 frame at 192 × 128 and 16 fps.
The decoded RGB picture contains 3,338 red-object pixels and black corner pixels
whose maximum channel value is zero. The verification reconciles the completed
job, export receipt, exact scene recipe, movie hash and retained source hash.

`macos/verify_metal_blend.py` reopens the retained `.blend`, checks Cycles GPU
mode and the saved Metal request/receipt, and compares the authored geometry,
resolution, frame count and recipe. A fresh hardware enumeration matches the
recorded Metal device identities with CPU and other device types disabled.
Device preferences are process state, so this enumeration is reported separately
from the fields saved in the `.blend`. The verifier does not rerender the frame
or save user preferences.

| Verified artifact | SHA-256 |
| --- | --- |
| Decoded RGB picture | `a5e06e5552c1779c5d4d1b7ce545f092a8a6e2db36db0374e5bec13216fd7926` |
| Retained `.blend` | `f885a33a58e44bcf9e2e7a14c637771cdf129bd56429840531dac047bbf371ae` |

### Editorial state, nested pictures, captions and rendered sound

`test_editorial_ui_macos.py` passed `sequences`, `captions`, `audio` and
`multicam`. These are real control/save/export stages with independently decoded
synthetic output. The sequence stage was refreshed after the nested-playback
changes and passed again.

The sequence fixture saves a live nested dependency and independently checks
the red/blue source cut in its rendered picture. The multicamera fixture creates
a manually synchronized group and cuts at frame six; its 24 decoded frames
contain the expected camera change. This establishes manual source-frame sync
and cutting, not automatic waveform/timecode synchronization or simultaneous
angle monitoring.

The caption stage retains multiline Unicode text, a real raster burn-in asset
and an actual SRT sidecar. The audio stage selects the second source audio
stream, swaps its channels, saves that mapping and measures the corresponding
channel values in the decoded movie output.

**That exported-audio result does not establish live browser audio routing.**
The separate `test_audio_routing_macos.py` gate remains unresolved. Earlier late,
contiguous 8,192-frame AudioWorklet observations found zero MOV PCM and incomplete
WAV energy despite a passing independent oscillator calibration. Subsequent
fixes produced passing WAV/first-stream observations and a 32,768-sample selected
second-MOV-stream comparison with the expected swapped channel amplitudes/RMS
and zero steady-state seeks. Gain/pan/restart then exposed a media-element
lifecycle problem. After that fix, a fresh native run again returned zero PCM
from both the selected source tap and the output, despite the correct selected
track, running source clock, unit element volume and a passing independent
oscillator calibration. This is an intermittent native routing defect; the
earlier success does not establish reliable source selection. Final gain/pan
and restart acceptance remain open. Correct saved identity and export audio
do not satisfy these live gates.

Source regressions also cover nested picture/continuous-audio clock separation,
fractional source in-points, constant retiming, reverse and source-channel
metadata. These regressions are included in the recorded full suite. Bounded nested
OTIO exchange and the exact limitations of the sequence model are documented in
the [Studio guide](README.md) and [capability audit](CAPABILITY_AUDIT.md).

### Cubic geometry, feather and effect masks in actual output

`test_roto_ui_macos.py` passed 26 checks using the own compositor interface. The
saved graph retains cubic anchors and incoming/outgoing handles, per-point
feather, custom cubic timing tangents and distinct source/effect-mask branches.
The test exercises actual history and save behavior before requesting processed
frames and a movie.

Independent decoding checks that exact cubic subdivision preserves the picture,
the effect changes its authored region, and cubic feather coverage agrees with
an independent point oracle. It decodes every fixture movie frame, verifies
actual animation changes and compares the corresponding delivered picture with
the paused graph frame. The native web view plays the returned movie; original
source bytes remain unchanged.

Combined 1D-shaper/3D Cube processing, graph JSON and bounded SVG exchange also
have source regression coverage in the recorded full suite.
These operations do not extend float processing through the whole movie graph;
delivery remains SDR.

### Proxy decoding, exact relink and original-based exports

`test_media_management_ui_macos.py` passed the ordered `baseline`, `cancel`,
`proxy` and `relink` stages in one isolated fixture workspace.

The fixture contains an actual 800 × 450, 60-frame, 24 fps source with sound. The
proxy stage creates a real 640 × 360 derivative, verifies source/proxy content
identities and independently compares all 60 decoded frame timestamps. It
observes the actual browser decoder URL and picture dimensions changing when
preview proxies are enabled, then saves that preference.

The cancellation stage operates a real proxy job and confirms terminal
cancellation, no admitted proxy and cleanup of its owned working files. The
relink stage removes only its own fixture original, selects wrong bytes through
the browser file path and verifies rejection, then selects the exact original
bytes and verifies restoration. Existing project and asset-inventory identities
survive both attempts. The restored original decodes, and the verified proxy
remains available.

Baseline, post-proxy and post-relink stages each export actual ProRes from the
original media. Independent decoding compares **all 12 RGB pictures and 24,000
stereo PCM sample frames**—24,000 samples per channel. The decoded RGB and PCM
bytes are identical across those exports. This is decoded-content equivalence;
it does not claim that lossy proxy pixels or separately encoded movie-container
bytes are identical to the originals.

### Managed-generation controls and ownership

`test_generation_ui_macos.py` passed ten checks through native controls. Its
runtime worker is explicitly labelled **CANCELLATION TEST — NO MODEL EXECUTION**.
The UI selects shot options, persists the actual workflow and prompt/seed
bindings, starts one Store setup job, cancels it and confirms the terminal state.
It admits no asset and submits no generation job. The fixture reports neither
an installed engine nor verified model execution.

Focused regression and source review found and corrected these concrete
ownership/preservation defects before installation:

- A dead owned engine retained its runtime lock and prevented restart. Restart
  now releases stale owned process/log/lock state; dead-engine status reports
  the exit instead of retaining a ready message.
- A buffered model-download read could hide cancellation behind a slow stream.
  Reads now return available chunks, check cancellation between them and retain
  resumable partials when the artifact deadline is reached.
- An interrupted workflow-history copy could leave a partial hash-named backup.
  Backup publication is atomic, existing archive identity is checked and failed
  publication preserves the current workflow.
- A dead managed child's ephemeral endpoint could be reused accidentally.
  Generation checks the current managed child before preflight and queued
  submission. Runtime stop and endpoint reset share the admission lock.

The cached official ComfyUI source archive was independently checked against the
lock's SHA-256 and size. Inspection of that exact source confirmed the selected
startup flags, model search directories, Wan node contracts, dynamic video-save
inputs and per-job cancellation route. Hash/source inspection and fixture
coverage establish those contracts separately from actual runtime execution.

The normal app-owned installer subsequently completed and verified
**10,634,173,896 bytes**, covering 71 pinned wheels, three model-weight files and
the ComfyUI 0.42.1 source archive. The owned engine started successfully; runtime
checks confirmed MPS availability, the encoder and all 11 required graph nodes.
These are actual installation/startup results, separate from the cancellation
fixture above.

A first real Wan inference job requested **192 × 128, nine frames, four steps
and seed 42**. It completed in **44.410 seconds** and admitted a nine-frame H.264
asset. `macos/verify_generated_take.py` independently passed all **14 checks**:
the immutable job workflow, prompt/negative/seed bindings, recorded hashes,
model/output-node identities, actual H.264 metadata, all nine decoded frames,
exact 16 fps timestamps and preserved source/snapshot. The source is 0.5625
seconds long. Unique, nonblank decoded pictures establish valid media, not
production quality or creative suitability.

`test_generated_take_ui_macos.py` then passed all **14 native checks** in
**1.393 seconds**, using a byte-identical copy of that actual generated take in
an isolated project. Actual Add → Play → Save controls preserved the media and
timeline; the native decoder received successful source requests. All nine
observed canvas pictures matched the corresponding independently decoded source
frames, with mean absolute RGB error from **0.2326 to 0.3056** code values
(the declared tolerance is less than 8). No export or generation substitute
was created. This checks actual picture playback, not frame-exact presentation
latency or production-quality neural output.

A further run using the normal defaults—**480 × 272, 17 frames and 20 steps**—was
cancelled after approximately 21 seconds during normal application termination.
The AppKit record shows the ordinary termination path; why termination was
requested remains unresolved. This is not a demonstrated model-execution
failure. The default preset, maximum settings, visual quality and sustained
generation behavior remain unverified.

### Candidate installation and existing project preservation

A 0.9 candidate was installed and launched through the normal application path.
Verification matched 53 bundled runtime files to their expected SHA-256 values.
The four existing project JSON files retained their prior content identities,
and the previous application bundle was archived before replacement.

This establishes the recorded candidate installation. It does not publish the
source or close feature gates, and changes made after this installation require
their own bundle-content verification before a final release claim.

A subsequent comparison found **50 of 53 current runtime files matching** the
installed candidate. `web/app.js`, `web/audio-routing.js` and
`web/sequence-playback.js` differ because the live-audio changes are newer. The
remote draft PR still contains the 0.8 source; there is no published 0.9 CI
result. The originally requested production checkout remains on its existing
main revision without Studio source and has an owner-modified Makefile. That
checkout must be reconciled without replacing the owner's edits or silently
merging the draft work.

## Pending acceptance

The following results remain open in this draft:

1. **Live audio:** resolve intermittent second-stream silence and complete
   independent sustained source/channel/gain/pan/restart comparisons. Correct
   saved metadata, an earlier passing observation and correct movie exports do
   not close this gate.
2. **Managed generation defaults and quality:** complete the normal-default
   run and evaluate realistic quality, settings and sustained execution. The
   reduced actual inference, independent decode and native playback are now
   complete; they do not establish these broader claims.
3. **Final release validation:** the current frozen-source full suite passed
   515 tests with no skips. A subsequent audio fix still requires its own
   regression/native acceptance, a matching installed bundle and verification
   of that installation. Reconcile the intended source checkout and
   publish/verify the draft branch. No final publication or signing/notarization
   is claimed.

## Previously skipped integrations now executed

The real RAW integration used rawpy's Kodak DC50 test fixture at upstream commit
`a39c2e7a44911889c3360891012f862f904ba551`. Its 92,675 bytes match Git blob
`32354628d6653b83db905417e25e77b037337c94` and SHA-256
`37e290dbd0053f00e508d02a6b3a2a990432dad1eb74c40a52ca899f0f225ecc`.
The [upstream fixture](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/RAW_KODAK_DC50_%C3%A9.KDC)
and [attribution](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/README.txt)
identify the real camera sample. The binary is a separate test input and is not
included in the repository or used as production footage.

`test_genuine_camera_raw_development_and_white_balance` passed against actual
rawpy 0.27.1 / LibRaw 0.22.1. It exercised preserved original bytes, AHD half-size
development, nontrivial output, a float EXR pixel compared with independent
rawpy/OCIO processing, changed white balance and rejection of source tampering.
The sensor data decodes as 512 × 768 with three colors. This closes the specific
genuine-RAW fixture gate; it does not establish every camera vendor, all decoder
settings or RAW-video editing.

`test_official_otio_reader_and_writer_preserve_the_exchange` passed with official
OpenTimelineIO 0.18.1 in an isolated package target. The 842,762-byte CPython 3.12
Linux wheel matches published SHA-256
`8f0924f818b496cf771612d489082bdb83f42b6bd97ed06589dd2e2c086742c9`.
The test verifies schema interpretation, rational timing, gaps, source/audio
cuts and the bounded authoring roundtrip. It does not extend the supported
OTIO subset or implement AAF/XML/native-project interchange.

## Reproduction entrypoints

Run the complete suite with the actual optional imaging interpreter when it is
available:

```bash
CINEMATICUM_IMAGING_PYTHON=/path/to/imaging/python \
CINEMATICUM_RAW_TEST_FILE=/path/to/verified-camera-raw \
PYTHONPATH=/path/to/official-otio-package-target \
  python3 -m unittest discover -s scripts/studio -p 'test_*.py' -v
```

Native scripts require macOS and the compiled `macos/SmokeTest.swift` helper;
Blender scripts require the actual engine. Use fresh isolated output folders.
The media stages share their own folder and must run in their stated order.
The scene-control stages likewise follow their harness's stage order. Skipping
an unavailable runtime is not a passing execution.

| Entrypoint | Relevant operation |
| --- | --- |
| `test_scene_authoring_blender.py` | `hierarchy`, `modeling`, `device`, and the separate `device-render` gate |
| `macos/verify_metal_result.py` / `macos/verify_metal_blend.py` | Independent decoded-picture and reopened-source acceptance of a completed normal Metal render job |
| `test_scene_authoring_ui_macos.py` | Eight own-control stages listed above |
| `test_editorial_ui_macos.py` | `sequences`, `captions`, `audio`, `multicam` |
| `test_roto_ui_macos.py` | Cubic path/effect-mask authoring and decoded output |
| `test_media_management_ui_macos.py` | `baseline`, `cancel`, `proxy`, `relink` |
| `test_generation_ui_macos.py` | Explicit setup-cancellation fixture and workflow persistence |
| `macos/verify_generated_take.py` / `test_generated_take_ui_macos.py` | Independent actual Wan output and native Add/Play/Save/picture acceptance |
| `test_audio_routing_macos.py` | Separate live browser PCM measurement; currently unresolved |
| `test_managed_generation.py` / `test_generation_store.py` | Install contracts, owned jobs/endpoints, cancellation and data preservation |

Detailed feature bounds remain in [capabilities.json](capabilities.json).
`parity_complete` remains `false`: accepted bounded operations do not imply
unrestricted modeling/rigging/simulation, a float/HDR movie pipeline, advanced
roto/paint, learned tracking/segmentation, reconstruction solving, plugin hosting,
collaboration or commercial-provider integration. Test fixtures never become
production footage and have no film issuance effect.

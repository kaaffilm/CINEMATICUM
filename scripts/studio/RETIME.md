# Editable speed ramps and optical-flow retiming

Studio 0.12 integrates this workflow into the exact 0.11 core
`530ba2400571a8b67efa2d9ab28997f65920c006`. It implements actual source-media
processing and ordinary authoring controls. [Current verification](VERIFICATION_0_12.md)
keeps the original isolated receipts separate from the integrated source freeze.
Native acceptance and installation remain separate gates; Chromium results
cannot certify WKWebView or an installed application.

## Authoring and retained edits

Select an admitted original video/audio timeline clip and open **Speed ramp &
optical flow** in its inspector. Set an output duration, choose nearest source
frames or optical flow, and enter speed keys. The first key is at output frame
zero, and the last key is at the output duration. Add/delete interior keys and
edit their output frames and speeds. The graph and source-range summary update
from the same analytic source clock used by the renderer. Apply is one unsaved,
undoable edit; Save retains the complete recipe with the original asset.

Source speed changes linearly between keys. A constant curve is supported,
including optical-flow slow motion. The existing constant-speed/reverse
controls and forward live PCM transport retain their previous processing. A
ramp clip must first be at forward 1×; a second time warp is rejected.

Splitting a ramp retains its keys and changes the right clip's source in and
curve offset. Edge trims select a window of that same curve. A trimmed head may
extend back into its retained domain if the timeline/source permits it; a tail
may extend only to the original curve end. Reopening a split interval in the
dialog presents equivalent local keys. Applying those local keys preserves its
source map. Authored transform/gain keys and fade envelopes remain in their
original output-time domains. Removing the ramp returns to forward 1× and caps
the duration to available original media. Slip, slide and roll involving a ramp
are explicitly unavailable; use its edges or the curve dialog.

The paused processed frame and exports use the actual retime worker and movie
graph. Pressing Play on a sequence containing a ramp first renders its preview;
the completed H.264 preview supplies picture and sound. Press Play again to
play/pause that rendered movie. Ramp source PCM is excluded from the live
constant-speed mixer, preventing a second, incorrectly timed sound voice.
Edits invalidate the rendered snapshot in the normal way.

Save/reopen and portable project archives retain the recipe and original media.
Temporary FFV1/float-PCM derivatives do not become replacement project assets.
OTIO export explicitly refuses projects containing these nonlinear time maps;
render and reimport an exchange copy when the destination requires an ordinary
linear media reference. This does not add AAF/XML/native-project interchange.

## Source and sample clocks

The stored representation is explicit and versioned:

```json
{
  "version": 1,
  "method": "optical_flow",
  "audio": "varispeed",
  "offset": 0,
  "source_origin": {"numerator": "4", "denominator": "1"},
  "keys": [{"frame": 0, "speed": 0.5}, {"frame": 12, "speed": 1.5}]
}
```

For a speed segment beginning at frame `a`, ending at `b`, and with endpoint
speeds `v0`, `v1`, its integrated source displacement over `u` output frames is
`v0*u + (v1-v0)*u*u/(2*(b-a))`. The application evaluates JSON decimal numbers
with rational arithmetic. The source origin is an exact nonnegative rational
frame coordinate stored as bounded integer strings. It stays unchanged through
split and trim, so a fractional visible `clip.in` never becomes a rounded new
source anchor. If `F` is the whole integrated curve, a clip with source origin
`q`, retained curve offset `d`, and local output time `t` reads source frame
`q + F(d+t)`. The displayed source in is `q+F(d)`. Nearest mode chooses
`floor(source + 0.5)` with exact rational arithmetic before passing the selected
real frame index to the worker. Reapplying unchanged local dialog keys retains
the original curve, origin and hidden handles; changing keys reanchors the new
curve at the exact current source position.

Original video is conformed to the exact project frame rate using FFmpeg's
nearest CFR timestamp policy before selecting the required real frames. The
trimmed raw input resets its PTS origin; otherwise FFmpeg would duplicate the
first trimmed picture to fill its leading timestamp. A fractional flow position
requires both real source frames. A missing final handle is rejected.

Let `R` be the exact project fps, `S=48000`, `O` the inherited sequence audio
origin, `A` clip start and `D` its output duration. The worker emits exactly
`round((O+A+D)*S/R) - round((O+A)*S/R)` stereo sample frames. Its phase is
`phi=round((O+A)*S/R) - (O+A)*S/R`. Output sample `n` evaluates the source map at
`t=(n+phi)*R/S`, then converts that source-frame coordinate to original sample
space with `S/R`. Tiny sample-grid phases beyond a curve endpoint continue its
endpoint speed. They are not clamped to frame zero.

The worker first decodes the selected original stream and selected channel pair
as 48 kHz float stereo. It uses a 64-tap Blackman-windowed sinc with cutoff
`0.95/max(1, instantaneousSpeed)` and float64 accumulation. It computes bounded
4096-sample blocks, then emits float32 PCM. Gain, pan, fades, track mixing and
volume animation apply afterward in the existing timeline graph. The temporary
clip clears only its already-applied stream/channel selection and resets its
source in/speed; it retains the authored mix controls. This preserves the
absolute sample grid through splits and forward normal-speed nested trims.

Varispeed deliberately changes pitch with speed. The optional Preserve pitch
mode uses stereo-linked 2048-sample/256-hop phase-vocoder windows at the
analytic variable source clock. A curve-wide synthesis lattice retains exact
samples across fractional-origin splits/trims. Finite windows can soften
transients; review rendered speech and music. This is bounded processing,
with no production-quality guarantee for arbitrary material.
Mute emits the exact same number of zero samples. Constant retimes continue to
use the existing pitch-preserving source-tempo path.

## Actual optical flow and quality limits

The pinned OpenCV worker computes **bidirectional DIS dense optical flow** with
the medium preset and finest scale zero. It estimates at a maximum 640-pixel
analysis edge, scales vectors back to source dimensions and performs four
inverse-warp iterations for each intermediate time. Forward/backward consistency
and image bounds determine usable contributions. Occluded/unreliable pixels
fall back to the nearest real source picture. A large residual across most of
the image marks a cut and uses nearest source frames. The render receipt records
real flow-pair counts, interpolated frames, cut fallback frames, low-confidence
fractions, exact source positions, versions and source identity.

This is classical motion estimation. Occlusion, disocclusion, motion blur,
flashes, small moving structures, fast motion and repeated textures can produce
artifacts or trigger nearest-picture fallback. Review the actual rendered movie.
The engine does not claim learned motion inference or production-scale quality.

Supported bounds:

| Area | Current bound |
|---|---|
| Clock | Existing exact project rates from 1–60 fps |
| Curve | 2–32 strictly ordered integer-frame keys; 0.25×–4× forward speed |
| Output/domain | 1–240 output frames; retained curve domain at most 240 frames |
| Picture source | Original opaque SDR video, both dimensions at least 16; edge at most 1280; at most 921,600 pixels |
| Raw picture window | At most 512 MiB for the conservative source/output estimate |
| Analysis | At most 640-pixel edge; output remains the actual source dimensions |
| Project complexity | At most 16 authored ramp clips; at most 16 expanded ramp instances per sequence |
| Precision | Standard 8-bit SDR processing; no high16/Float32, PQ/HLG or alpha-source retiming |
| Sound | Selected original stream and two output channels, 48 kHz; anti-aliased varispeed or exact mute |
| Nesting | Normal-speed forward nested instances, including source trims; retimed/reversed ancestors refuse |
| Processing | Each owned retime derivative has a 120-second processing deadline; cancellation stops its owned process group |

The feature refuses multicamera-bound clips, measured tracking/stabilization,
learned-analysis bindings, tracked-mask sources and dependent measured corner
pins. A ramp cannot be authored directly on a nested sequence instance. Render
an explicit new source first when a workflow needs an unsupported combination.

## Runtime and verification

The worker requires actual **NumPy 2.3.5** and **opencv-python-headless
4.11.0.86**. It checks distribution versions and executes a dense-flow
translation probe before advertising availability. It selects an explicit
`CINEMATICUM_TRACKING_PYTHON` or the existing managed Tracking interpreter. It
does not install packages or modify shared runtimes. FFmpeg and FFprobe must be
on PATH. Original media SHA-256 identities are verified before and after work.

`test_retime.py` creates actual FFV1/PCM fixtures and uses independent translated
texture and literal quadratic/continuous-tone oracles. It checks every source
picture and sample, fractional-rate phase/split continuity, alias suppression,
muted/audio-only processing, selected stream/channel routing, gain/pan/fades,
paused/export agreement, normal-speed nested trims, saved/archive restoration,
changed-source refusal and cancellation. Runtime-dependent cases clearly skip
when the actual runtime is unavailable; those skips are not acceptance.

```sh
CINEMATICUM_TRACKING_PYTHON=/absolute/pinned/python \
  /absolute/pinned/python -m unittest -v test_retime
```

Run from `scripts/studio`. The shared ordinary-control acceptance has separate
`prepare`, `author`, `playback`, and `archive` phases. Each coordinator phase has
an 18-second foreground budget and its native/browser helper at most 14 seconds.
Every phase starts and joins its own loopback server, helper and jobs. It keeps
failure evidence; repetition uses a new fixture. No process is detached to evade
the deadline. Playback records real decoded picture clocks and nonzero stereo
audio. Exports/downloads are decoded and compared against independently authored
original-pixel and sample truth. Archive restoration renders from the restored
originals with a new project identity.

Chromium command from the repository root:

```sh
NODE_PATH=/absolute/playwright-1.51.1/node_modules \
CINEMATICUM_TRACKING_PYTHON=/absolute/pinned/python \
node scripts/studio/test_retime_browser.cjs \
  --python /absolute/pinned/python \
  --browser /absolute/chrome-for-testing-134.0.6998.35/chrome-linux64/chrome \
  --evidence /absolute/new-owned-evidence
```

For native acceptance, compile the repository's existing `macos/SmokeTest.swift`
helper, freeze `test_retime_macos.source_inventory()` to a JSON file, then run
each phase through the pinned NumPy/OpenCV interpreter:

```sh
swiftc scripts/studio/macos/SmokeTest.swift -o /absolute/owned/NativeSmoke
CINEMATICUM_TRACKING_PYTHON=/absolute/pinned/python \
  /absolute/pinned/python scripts/studio/test_retime_macos.py \
  --binary /absolute/owned/NativeSmoke \
  --operation prepare \
  --output /absolute/new-owned-evidence/prepare \
  --fixture-workspace /absolute/new-owned-evidence/fixture \
  --expected-sources /absolute/new-owned-evidence/source-inventory.json
```

Repeat with `author`, `playback`, and `archive`, each with its own new output
directory and the same frozen inventory/fixture. The source inventory includes
all shipped runtime and web files and the relevant acceptance helper sources.
The coordinator rechecks it before and after every phase. The release owner
must run the complete integrated suite and native gates before installation.

### Measured isolated candidate acceptance — 22 October 2026

The original pre-integration candidate passed all 19 `test_retime` cases with zero skips,
failures or errors in 16.195 seconds. Eleven recorded production/test source
identities were unchanged across that run. A further 19 focused existing
editing/live-audio checks and 10 existing actual-media regression cases passed.
The latter exercised constant retime and pitch, reverse picture/sound, fades,
the paused export graph, nested constant retimes, fixed-camera nested/reversed
sound, and actual slip/slide/roll pictures. These are affected-area gates, not a
whole-build certification.

The shared ordinary-control script passed 58 Chromium checks: prepare in
0.760 seconds, author in 2.291 seconds, playback in 9.611 seconds and archive in
5.437 seconds. The observed browser was Chrome for Testing 134.0.6998.35 with
Playwright 1.51.1 and a real H.264 decoder. Its executable identity and the
complete runtime/web/acceptance inventory were unchanged before and after.

| Independent measurement | Result |
|---|---|
| Six optical-flow midpoint interiors | Exact translated pixels, RMSE 0; nearest RMSE 18.4–18.9 and ordinary blend RMSE 11.1–11.4 |
| Fractional 30000/1001 clock | All 19,219 stereo sample frames checked; maximum analytic error below 6.27e-7 |
| Split PCM continuity | 6,407 + 12,812 sample frames exactly equal the unsplit output |
| 4× anti-aliasing fixture | Rejected 14 kHz source band reduced by 97.61 dB; retained 300 Hz tone became 1,200 Hz |
| Actual browser preview | 13 decoded video frames and 16,384 captured stereo sample frames; nonzero sound with the selected channel routing |
| Both downloaded ProRes movies | 15 pictures and 30,000 stereo sample frames each; maximum analytic PCM error 0.505 of a 16-bit LSB, maximum interior picture MAE 3.09 |
| Portable project restoration | A new project identity retained editable curves and original media; restored decoded pictures and samples matched the original export |

The source fixtures are synthetic ENGINE TEST material. Successful displacement
and audio measurements do not certify arbitrary-footage optical-flow quality,
long-running performance or native playback. WKWebView acceptance, the complete
integrated regression, installation and distribution remain separate gates.
The handoff retains full source hashes, logs, original media and independent
pixel/sample truth, including the earlier failed decode-timestamp experiment.

Primary implementation references:

- [OpenCV DIS optical flow](https://docs.opencv.org/4.x/de/d4f/classcv_1_1DISOpticalFlow.html)
- [OpenCV geometric image transformations and remapping](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html)
- [FFmpeg fps, trim, setpts and audio filters](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg audio resampling](https://ffmpeg.org/ffmpeg-resampler.html)

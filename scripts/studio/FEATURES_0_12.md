# CINEMATICUM Studio 0.12: editable retiming

Studio 0.12 starts from the exact integrated 0.11 core
`530ba2400571a8b67efa2d9ab28997f65920c006`, retaining its
[implemented workflows](FEATURES_0_11.md). This candidate adds editable variable
speed and actual optical-flow source processing. Its
[verification](VERIFICATION_0_12.md), native acceptance and installation are
separate gates. [Remaining requirements](UNFINISHED_0_12.md) still apply.

## Authoring and source-time mapping

Select an admitted original video or audio clip and open **Speed ramp & optical
flow** in the inspector. Author an output duration and 2–32 speed keys, choose
nearest pictures or optical flow, and choose varispeed sound or mute. The graph
shows the linear speed segments and their integrated source range. Apply is one
undoable edit; save/reopen and portable archives retain the original media and
complete recipe.

The source map integrates the speed curve analytically. Python rational
arithmetic and browser BigInt arithmetic retain an exact source origin and
nearest-frame tie decisions. Splits and edge trims select windows of the same
curve, preserving hidden handles and independent output-time animation/fades.
Reapplying unchanged local keys preserves the full original map. Changed keys
start from the exact retained source coordinate.

## Actual picture and sound processing

The pinned OpenCV worker measures bidirectional DIS dense optical flow and
inverse-warps the real source pictures. Confidence, image bounds and cut checks
use nearest real pictures where interpolation is unreliable. Reports retain
actual flow-pair/interpolation counts, fallbacks, versions and source hashes.
This is measured classical motion estimation; arbitrary-footage quality is not
certified by the synthetic acceptance fixtures.

The selected original stream/channel pair is decoded as 48 kHz float stereo.
A 64-tap anti-aliased varispeed filter evaluates the nonlinear source clock on
the absolute sample grid, including fractional frame rates and forward nested
source trims. Existing gain, pan, fades, track mixing and volume animation apply
after source retiming. Pitch follows speed; pitch-preserving ramps remain open.

Paused images, rendered playback and export use this actual source-time path.
Play renders the ramp sequence into an H.264 preview before playback. The
existing constant-speed live PCM mixer excludes ramp voices and retains its
previous transport. Intermediate FFV1/float-PCM files remain temporary; the
project and archive continue to reference their admitted originals.

## Supported bounds

| Area | Implemented bound |
|---|---|
| Speed curve | Positive 0.25×–4×; 2–32 ordered integer-frame keys |
| Curve/output duration | At most 240 frames |
| Picture processing | Standard8 opaque SDR; source dimensions at least 16, edge at most 1280, at most 921,600 source pixels |
| Flow analysis | At most 640-pixel edge, output at source dimensions |
| Processing | 512 MiB conservative raw-picture window; 120-second owned derivative deadline |
| Project expansion | At most 16 authored/expanded ramp instances per sequence |
| Nesting | Forward normal-speed nested instances, including source trims |
| Sound | Selected source stream/channel pair, exact-grid 48 kHz stereo varispeed or mute |

High16/Float32 processing, alpha/PQ/HLG source retiming, timewarped/reversed
ancestors, directly ramped sequence instances and measured tracking/multicamera
bindings refuse explicitly. Dependent corner pins cannot silently retain a
changed background clock. Slip/slide/roll involving ramps and nonlinear OTIO
export also refuse. Changed original bytes are rejected before and after work.

[RETIME.md](RETIME.md) documents the source equation, audio phase, ordinary
controls, runtime pins and numerical acceptance. The candidate targets
**0.12.0 / build 13** and retains `parity_complete: false`.

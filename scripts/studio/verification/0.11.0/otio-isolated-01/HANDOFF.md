# OTIO composition interchange — integration handoff

Base: `a031a04e19007f7bac252c1f5b0f8d66db15371a`. Isolated source baseline:
`acb51ed56580c82acb606f37458e3e1ca0f8491e`. All existing changed files are checked
against the exact upstream base Git blob. The patch has 16 explicit source/doc
files; task fixtures, temporary directories and previous candidate work are
excluded. See `source-manifest.json` for full base/candidate SHA-256 identities
and `verification.json` for measured checks. No external refs were changed.

## Implemented

Real OTIO constant retime/reverse, same-track overlap lanes, trimmed/nested
Track and Stack compositions, and SMPTE linear dissolves. Dissolves preserve
associated-alpha picture semantics and complementary source-PCM sample fades,
including the absolute nested 48 kHz grid at fractional frame rates. Public
export writes actual OTIO timewarp/transition operators. Import creates editable
native sequence dependencies. Exact private restoration checks every referenced
source and regenerated public structure. UI supports read-only review, one undo,
save/reopen, downloaded public/private OTIO and lossless project archive restore.

## Integration points

- Merge the new `otio_compositions.py` and dispatch additions in `interchange.py`.
- `editorial.py` adds optional `otio_dissolve` snapshot/switch handling and strict
  operator validation. Keep the multicamera audio-lock implementation during
  the merge; this patch was intentionally based on the unchanged a031 source.
- `engine.py` adds `_dissolve_picture`, the two picture composition branches,
  transparent operator background, and `_graph(..., _audio_origin=0)`. Preserve
  the merged multicamera `resolve_audio` plan; source-origin timing applies to
  the effective audio plan. The child absolute origin propagates only through
  normal-speed forward nested instances; retimed/reversed instances retain
  their source clock before existing tempo operations.
- `web/sequence-playback.js` adds associated Canvas weighted addition for the
  two operator inputs. Keep the multicamera changes in that same module.
- `install_macos.py` adds `otio_compositions.py` to bundled runtime files. Keep
  any other new runtime modules already integrated by sibling patches.
- `capabilities.json` changes only `editor.otio`; merge that entry with other
  capability updates. Status remains `partial` because arbitrary OTIO plugins,
  unsupported operators, AAF/XML/native-project exchange remain absent.
- This patch does not change the separate float renderer. Preserve its explicit
  nested/operator refusal. Never flatten `otio_dissolve` into plain source-over.

## Measured acceptance

86 distinct affected tests passed on Python 3.12 / NumPy 2.3.5 / OpenTimelineIO
0.18.1. The first 86-test invocation passed 85 and encountered one sandbox-only
EPERM at local socket construction. That exact existing HTTP test then passed
in the authorized host context in 1.209 seconds with source unchanged. The
original failure and rerun logs are retained, not rewritten as one suite pass.

The actual browser gate passed 63/63 checks across prepare/author/render/archive
in 2.739, 3.381, 4.242 and 5.085 seconds. Both direct and restored-archive ProRes
movies contain all 28 independently expected source frames and all 56,000
stereo PCM sample frames with zero LSB error. Dissolve RGB maximum error is 4
through the actual encoder. The unit media gate additionally verifies true
premultiplied-alpha 16-bit output and every sample of a 22,422-sample fractional
rate transition. Source hashes were stable throughout the accepted browser run.

`otio-actual-processed-dissolve.png` is the actual processed-frame viewer at the
50% dissolve, inspected visually. Native macOS is not yet certified. The
coordinator uses 18-second foreground phases, a 14-second UI helper, no detached
work, source/fixture inventories, actual completed downloads and independent
frame/PCM decode. Exact native commands and bounds are in the new
`scripts/studio/OTIO_INTERCHANGE.md`.

Browser executable:
`/workspace/scratch/091f394ee5df/cinematicum-runtimes/chrome-for-testing-134.0.6998.35/chrome-linux64/chrome`
Observed version: `Google Chrome for Testing 134.0.6998.35`.
Executable SHA-256:
`f661a8c124888f491966c29581f33c1953c86c15d77048bc91452b66743d5f3a`.
Playwright 1.51.1. Preserved ZIP and runtime-inventory.json are in the adjacent
`chrome-for-testing-134.0.6998.35` directory. ZIP SHA-256:
`7c11f4cb9620df17582509184106cef56a06b7ac37bc08c12d84a6fb367abc41`.

## Remaining release gates

Apply and resolve overlap with sibling candidates, run the combined-source
regression and actual native phases, then install/verify the combined bundle.
No broad production-scale, third-party editor fidelity or native certification
is inferred from these isolated candidate results. Output-duration/lower-window
reverse conventions and explicit unsupported bounds are documented in-product.

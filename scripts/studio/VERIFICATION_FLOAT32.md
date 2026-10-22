# Scene-linear Float32 candidate verification

This record covers the isolated next-release Float32 implementation, tested
with real local media engines on Linux. It does not certify the frozen 0.10
release, a later merged source, an installed Mac application, HDR monitoring,
calibrated display or production footage. All source pictures and tones are
explicitly labelled ENGINE TEST fixtures. Film issuance remains `NONE`.

## Frozen evidence

The exact 20-file implementation patch applies to
`a031a04e19007f7bac252c1f5b0f8d66db15371a` and has SHA-256
`8ef500068be903d417c4c8d4f13964ac92b6230393df8d97a16d9632fe669f8e`.
Its per-file base/output inventory is
`cinematicum-float-review-manifest.json`, SHA-256
`9e6137cf72182c175267d814dc1bbf3e24157a0763878c86b54d87649b193d6e`.
The operative source stayed unchanged throughout the final test run.
The machine-readable [acceptance summary](verification/float32/acceptance-summary.json)
binds every retained record and screenshot by SHA-256 and size.

| Gate | Actual result |
| --- | --- |
| One frozen affected-source regression | **95/95**, zero failures, errors or skips; 74.107 seconds. Includes 20 Float32 media/pixel cases, two owned HTTP cases and 73 high16/engine/frame/color/archive regressions. |
| Shipped browser workflow | **22/22** in 10.945 seconds, Chromium. Actual controls, per-source interpretations, Undo/Redo, Save/reload, OCIO paused frame, owned render and download. |
| Native coordinator, prepare | **3/3** independent checks in 1.316 seconds; no native UI invoked. |
| Native coordinator, author | **9/9** independent plus **8/8** UI checks in 5.009 seconds, replayed through Chromium. |
| Native coordinator, render | **16/16** independent plus **5/5** UI checks in 5.134 seconds, replayed through Chromium. |
| Changed JavaScript syntax | **4/4** parsed successfully. |
| Actual Mac / installed build | Pending; `native_certified: false`, `installed: false`. |

The actual runtime was Python 3.12.14, NumPy 2.3.5, OpenEXR 3.4.15,
OpenColorIO 2.6.0 and FFmpeg 6.1.1. Runtime versions and code identities are in
[the frozen report](verification/float32/frozen-tests.json); every test name
and result is retained in [the log](verification/float32/frozen-tests.log).

## What was measured

Numeric tests decoded actual FLOAT32 EXRs and compared pixels against independent
source-over, linear exposure, tiny-alpha, transformed-edge and OCIO expectations.
They preserved negative values, values above one and fractional alpha, including
positive alpha of `1e-9`. Real FFV1 video and EXR layers changed across all four
timeline frames. Audio was independently decoded; the normal four-frame/4-fps
case contained exactly 48,000 stereo samples, and a two-frame 30000/1001 case
contained exactly 3,203 samples. Reverse picture ordering, track gain/mute and
actual raster-title fades were exercised.

The source/recipe/config binding tests rejected changed sources, altered package
members, unknown OCIO names/views, unsupported effects and missing runtime.
Cancellation preserved previous completed output, removed private staging and
left admitted sources unchanged. A portable archive was actually restored to a
different project root and rerendered to identical retained EXR frame bytes.

HTTP tests used the real server, token protection, normal owned job queue,
durable completed status and binary attachment route. Save/reopen retained the
Float32 recipe; a forged client media inventory could not replace owned assets.
A cancelled queued master published neither a ZIP nor an export receipt.

The browser downloaded a real **471,004-byte** master ZIP with SHA-256
`2cbd4a24c42fdcd3c45101963cb10634bda3d696a38e53a443eaee5ce80d521d`.
The retained [ENGINE TEST master](verification/float32/browser/ENGINE_TEST_float32_master.zip)
contains four FLOAT32 RGBA EXRs in ACES2065-1, a 48 kHz stereo float PCM WAV,
display PNG, exact OCIO config and complete manifest. Its actual bytes matched
the completed owned job receipt and every package member was verified.

The browser-visible JSON and exact preserved server snapshot were checked
separately: JavaScript serializes integral numbers without Python's `.0`, so
the byte hash binds the preserved normalized server snapshot while the browser
comparison checks the same structured values. This does not weaken package or
source integrity checks. Earlier fixture-only failures involved EXR upload
staging, adding the second picture track, and that numeric JSON test oracle;
the final accepted workflow completed all gates without browser script errors
or external browser requests.

## Review images and native replay

- [Export and OCIO controls](verification/float32/browser/float-export-controls.png)
- [Actual paused display derivative](verification/float32/browser/float-paused-preview.png)
- [Completed browser master download](verification/float32/browser/float-master-download.png)
- [Coordinator rendering and download](verification/float32/ui-coordinator/render/ENGINE_TEST_float_ui.png)

The prepare/author/render coordinator accepts the existing compiled
`macos/SmokeTest.swift` helper and runs each phase in an owned foreground scope.
Its helper limit is 14 seconds and subprocess limit 16 seconds. The author phase
checks Undo/Redo, a separate sentinel project, Save/reopen and the real paused
image. The render phase checks the exact download, every master member, actual
FLOAT32 channel types and negative/superwhite/fractional-alpha pixels. Chromium
replay proves the coordinator's workflow; actual WKWebView/WKDownload acceptance
must be collected independently on a Mac. Neither transport certifies physical
input, a native Save dialog, the installed launcher or calibrated output.

The [processing document](FLOAT_MOVIE_PIPELINE.md) defines the exact settings,
profile metadata, pixel operations, job ownership and limits. The main limits
are 8,388,608 canvas pixels, 16,777,216 source pixels, 14,400 frames, 16 GiB source
files and a 32 GiB package. Live nested/graph/tracking operations are explicitly
unsupported. Native acceptance, a new combined whole-build freeze, CI,
installation and installed launch remain separate release gates.

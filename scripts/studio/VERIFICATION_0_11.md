# CINEMATICUM Studio 0.11 verification

Recorded 22 October 2026. The integration candidate starts from published
`a031a04e19007f7bac252c1f5b0f8d66db15371a`. The [0.10 record](VERIFICATION_0_10.md)
contains the actual 812-test local/CI freezes, verified replacement installation
and the failed first installed-quit acceptance. Those results do not certify
this newer source.

## Completed feature and integration gates

| Gate | Actual result | Scope |
| --- | --- | --- |
| Multicamera affected regression | 62/62 | Isolated candidate; includes 15 independently decoded original-picture/audio cases. |
| Multicamera browser on integrated source | 58/58 in 13.324 s | Four actual prepare/author/play/render phases, simultaneous pictures, one continuous source PCM voice across a live camera cut, save/reopen and real download. |
| Float32 frozen affected regression | 95/95 in 74.107 s | Isolated candidate; real OCIO/OpenEXR/FFmpeg, HTTP jobs, archives and affected existing features; no failures/errors/skips. |
| Float32 browser on integrated source | 22/22 in 11.166 s | Actual controls, undo/redo, save/reopen, OCIO paused frame, master job, downloaded ZIP and independent EXR/audio/config/source validation. |
| Combined Float32 and fixed-camera sound | 2/2 in 2.957 s | A silent picture retains locked original sound; mutation of an otherwise unused bound camera blocks export and preserves the preceding master. |
| OTIO affected regression | 86 distinct tests | Isolated candidate: 85 passed in the original 86-test run; the single loopback-socket sandbox denial passed in its exact authorized host rerun. Both records are retained. |
| OTIO browser | 63/63 | Actual import/review/undo/save/reopen, processed dissolve, downloaded movie and archive restoration. Original and restored exports each preserve all 28 expected source frames and 56,000 stereo sample frames with zero PCM LSB error. |
| Startup quit browser | 39/39 original; 32/32 recurring CI mode | Reproduced both prior startup races; corrected mode verifies real authenticated bootstrap, dirty saves, revision-conflict refusal and real FFmpeg job cancellation. The recurring mode explicitly does not request old-source reproduction. |
| Native startup helper compilation | Passed on arm64 macOS | Exact production class body is retained. First helper compilation exposed a Swift numeric-literal typo; the corrected helper compiled successfully. This is compilation evidence, not native workflow acceptance. |
| HDR/panorama numeric and affected regression | 13/13 new tests; 27 distinct affected tests | Measured geometry, nonlinear response, motion masks, linear radiance, connected panoramas, cancellation and exact archive replay. The affected count includes 26 explicit initial OK records plus a separately captured legacy archive pass. |
| HDR/panorama browser | 70/70 in 39.586 s | Five bounded phases cover actual source import, processing controls, edits, downloads and archive restoration. The 24-frame FFV1 gbrap16le movie has zero error against every first/last paused-frame RGBA sample. |

These rows have different source inventories and overlapping affected suites;
their counts are not summed into a whole-build result. Browser acceptance is
separate from actual WKWebView/WKDownload or canonical installed-app acceptance.
Reports, screenshots and collection hashes are retained under
`verification/0.11.0/integrated-browser-01/`, with the isolated Float32 record
in [VERIFICATION_FLOAT32.md](VERIFICATION_FLOAT32.md).

The first integrated Float32 browser attempt failed because Playwright's
function wait used evaluation forbidden by the product CSP in the verified
Chrome for Testing build. Ordinary DOM selector waits replaced that harness
operation; the application's CSP was unchanged. Both attempts are retained.
Chrome for Testing 134.0.6998.35 provides the actual H.264 decoder needed for
simultaneous camera acceptance; its official archive and executable identities
are verified by the updated bootstrap.

## Release gates

The combined frozen full suite, native feature phases, startup-quit regression,
exact-head CI, replacement installation, installed runtime-file reconciliation
and canonical installed launch are still pending for this candidate. The final
release record must identify the source actually used by each gate. Existing
projects and the previous application must remain preserved.

No record here certifies signed/notarized distribution, full professional
feature parity, calibrated HDR output, production-scale quality or an accepted
audience film. [Remaining work](UNFINISHED_0_11.md) retains those requirements.

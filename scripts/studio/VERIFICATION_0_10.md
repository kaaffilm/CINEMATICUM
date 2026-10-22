# CINEMATICUM Studio 0.10 verification

Recorded 22 October 2026. This is the recovered 0.10 candidate, with release
gates tracked independently. The prior 544-test 0.9.1 report remains historical.
An earlier 808-test report was not recovered and does not certify this source.

## Source preservation

Checkpoint `04d44cd2eb6c1935e331719a0b5feecf8e30dc02` preserves 278 retained source
files without modifying the retained development workspace. The complete
[recovery inventory](RECOVERY_SOURCE_0_10.json) binds 5,261,470 source bytes.
Inventory SHA-256:
`05fc40beb5a48fe5a236ef04370031b9f14328fe297d81874ddefc941d0cb3b2`.
Recovery is not a new test pass or an installation receipt.

## Native acceptance collected in this continuation

All following operations executed on the owner's Mac against explicitly frozen
runtime/web/helper inventories. The native helper was freshly compiled from
`macos/SmokeTest.swift`. Synthetic ENGINE TEST projects were isolated from
existing projects. Every phase terminated its owned work in the foreground.

| Workflow | Checks | Seconds | Measured scope |
| --- | ---: | ---: | --- |
| Optics authoring | 14/14 | 7.912 | Actual controls, optical prescription edit, undo/redo, save and exact reopen; no analysis job during authoring. |
| Optics analysis/download | 27/27 | 13.650 | Actual Optiland worker, authored glass/rays/PSF/MTF, independent lens equation and FFT comparison, byte-identical WKDownload. |
| Reconstruction preparation | 8/8 | 1.796 | Eight independent calibrated textured-plane images, no supplied solver poses/features, empty fixture and frozen source. This phase itself is not UI acceptance. |
| Reconstruction authoring | 15/15 | 3.374 | Actual photograph import, settings, undo/redo and save/reopen through WKWebView. |
| Reconstruction solve | 18/18 | 8.591 | Actual CPU COLMAP solve, source-bound result and independent calibrated geometry checks. |
| Reconstruction application | 26/26 | 5.613 | Undoable camera/point scene application, persistence, actual preview and three artifact downloads. |
| Physical authoring/render | 25/25 | 3.280 | Actual material/light edits, save/undo/reopen, CPU Mitsuba float EXR, independent radiometry, admitted sRGB preview and WKDownload. |
| Multicamera preparation | 7/7 | 0.507 | Three independent source streams, nondefault stream/channel mappings and known sample offsets; this phase itself is not UI acceptance. |
| Multicamera authoring | 13/13 | 2.042 | Actual import and selected stream/channel edits, undo/redo and exact save/reopen. |
| Multicamera synchronization | 20/20 | 2.209 | Actual measured offsets, source binding, undoable apply, save/reopen and angle cut. |
| Multicamera render/download | 19/19 | 1.847 | Actual ProRes/PCM export, all 278 picture frames and 556,000 stereo sample frames independently compared; exact owned downloads. |

These 11 phases passed 192 checks in total, including fixture preparation.
An independent Chromium run also passed all 59 multicamera checks; its raw
records are in `verification/0.10.0/multicam-browser-01/`. The native rendered
audio maximum sample error was `1.52587890625e-05`; the source measurement
recovered the expected +11,819 and −7,517 sample offsets.

Raw records and inventories are retained in
`verification/0.10.0/recovered-native-01/`. Collected files are compared by SHA-256
with their exact native bytes. These tests use an explicit evidence download
directory; they do not claim physical input, arbitrary NSSavePanel behavior,
installed-launch acceptance, dense reconstruction or production-scale quality.

The earlier optics authoring helper allowed seven seconds for cold engine
readiness. Its replacement allows ten seconds while retaining the same
13.5-second JavaScript and 18-second complete-phase deadlines and all original
checks. Optiland still imports and executes its actual installed engine. The
initial isolated direct-file harness invocation lacked the sibling-module
import path and exited before testing; explicit source-path invocation fixed
that launch error. Historical failed attempts are not relabeled as passes.

## Frozen full regression and CI

The exact published source `a031a04e19007f7bac252c1f5b0f8d66db15371a`
passed **812 tests** locally with zero failures, errors, skips or expected
failures. Source and all managed runtime inventories remained unchanged. The
complete gate took 834.087 seconds; its report SHA-256 is
`697b5977e365161b5843dc396cf854597c81f338fe5b6970856d8a22745571f6`.
The report and log are in `verification/0.10.0/whole-build-current-02/`.

Exact-head [CI run 39757512895](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39757512895)
also passed all 812 tests with no skips, unchanged source and runtimes, actual
optional engines and the multicamera browser gate. The CI verifier took
535.482 seconds. The independently downloaded artifact matches GitHub's
SHA-256 `60f0ad36f7c916a7a083ec6b6f9a6e5079f2fb3114d34d3551b3b7037901766a`;
its report SHA-256 is `de45703e8864615b92990da282c4e5e9931984af029093bcc475afa6145fe7e3`.
The retained metadata is `verification/0.10.0/ci-current-01/ci-summary.json`.

The initial local preflight failed before test discovery when the workspace
synchronizer introduced temporary files inside a managed runtime. The strict
inventory guard refused that candidate. Clean isolated runtimes outside the
synchronized workspace passed full before/after verification. The initial
failed record remains in `whole-build-preflight-01`; it is not counted as a pass.

## Installation and the remaining launch defect

The actual 0.10.0/build 11 application was built and installed from unchanged
a031 source in 7.910 seconds. All **100 copied runtime files** match their
source bytes and modes. Independent source, installed bundle, installer/backup,
existing projects and original checkout gates all passed. The prior 67-file
bundle is recoverable from its verified backup. All 59 existing project files,
**2,858,334,503 bytes**, were preserved. Public hashes and counts are in
`verification/0.10.0/installed-current-01/installation-summary.json`; raw
independent receipts remain on the Mac. This is an unsigned development bundle.

The canonical installed launch verified LaunchServices identity, the real
bundled server, default workspace, editor HTTP bytes and a native window.
However, the first ordinary quit request did not finish within its 15-second
deadline. A second ordinary cleanup quit succeeded; no force termination was
used, and all protected project and bundle bytes remained unchanged. **That
launch run remains failed.** The startup-quit correction and its regression
acceptance belong to the next candidate. No full professional-system parity or
accepted film issuance follows from these records.

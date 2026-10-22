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

## Open release gates

The current combined frozen full suite, exact-head CI, verified replacement
installation and actual
installed launch/source reconciliation must complete before this candidate is
accepted. Current capability/source records identify these gates explicitly.
No report here asserts full professional-system parity or completed film
issuance. [Remaining work](UNFINISHED_0_10.md) defines those separate obligations.

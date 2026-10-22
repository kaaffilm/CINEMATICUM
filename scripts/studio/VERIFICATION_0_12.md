# CINEMATICUM Studio 0.12 verification

Recorded 22 October 2026. Studio **0.12.0 / build 13** adds editable speed
ramps, actual DIS optical-flow picture processing and exact-grid varispeed
audio to the integrated 0.11 core. The accepted core passed the complete suite,
bounded native retime acceptance, replacement installation and canonical
installed launch. All eight selected installed-runtime phases passed, followed
by complete preservation. The documentation/history merge is reconciled to the
unchanged accepted runtime/test source; exact-head CI/publication remains pending.

## Accepted core and source identity

| Identity | Value |
| --- | --- |
| Accepted core | `c9869e86b9421b7fdc083d249b1616114320f0d5` |
| Parent | `530ba2400571a8b67efa2d9ab28997f65920c006` |
| Accepted tree | `941da9dbc805788a89c610ee688cc17de08fccc4` |
| Core source manifest SHA-256 | `31125bf9cef0a920bc0a5e45b2f132fdfbf4d3a5640d55cb01af372266d736d3` |
| Complete core source inventory SHA-256 | `cf8691d3b1d3a646ea6a73bdafe9829830b94c5592eb771c313aa449a70725b7` |
| Declared source | 343 files, plus the manifest in the complete runner digest |

Exact commit metadata and raw Git commit content are retained in
[core-acceptance-01](verification/0.12.0/core-acceptance-01/core-commit.json).
Its [source freeze](verification/0.12.0/core-acceptance-01/source-freeze.json)
records every declared file. These identities remain attached to the original
tests and installation. A documentation-only follow-up must retain its own
manifest and explicit reconciliation to the tested core.

## Complete regression and immutable runtimes

| Gate | Actual result | Source-bound record |
| --- | --- | --- |
| First integrated freeze | **893/893**, zero failures/errors/skips; 926.689 s total, 769.560 s unittest | [First report](verification/0.12.0/whole-build-current-01/report.json), [log](verification/0.12.0/whole-build-current-01/verification.log), [summary](verification/0.12.0/whole-build-current-01/summary.json) |
| Corrected accepted core | **895/895**, zero failures/errors/skips; 893.861 s total, 752.114 s unittest | [Final report](verification/0.12.0/whole-build-current-02/report.json), [log](verification/0.12.0/whole-build-current-02/verification.log), [summary](verification/0.12.0/whole-build-current-02/summary.json) |
| Download completion and source integrity | **6/6**, including six actual browser subcases; 14.233 s | [Targeted report](verification/0.12.0/download-completion-01/report.json) |

Both complete runners exited zero. They accepted no expected failures,
unexpected successes or skips. Source hashes and all five managed runtime
inventories and installation receipts were unchanged before and after each
run. The engines were actual Optiland, physical rendering, learned inference,
COLMAP reconstruction and Blender/Cycles installations. The genuine Kodak
RAW fixture was present; no missing-RAW exception was used. The base environment
used Python 3.12.14, NumPy 2.3.5 and OpenTimelineIO **0.18.1**. Each report records
the complete base and managed engine identities.

Corrected report SHA-256:
`c039f6629882521608427279d27b71dac0db8e9e8eb2e63c326c2be50df07d40`.
First report SHA-256:
`a48eb7cb57d1fa3c4327a822c472278ad362220fd9bad3869f579f1952bb7f6e`.
The first source inventory was
`8edd16decf0dfa4cd2891bc39f1e04b776e8294354f7d108e00f2cbe4134f4f2`;
its pass remains historical evidence before the download-completion correction.

## Preserved failure and exact download completion

The first actual Mac archive phase failed with
`Exactly one actual movie download is required`. The UI had completed all
three control steps and requested the restored movie, but Swift exited after
the completed ZIP before WebKit registered the movie callback. The coordinator
correctly refused incomplete evidence. The failed phase and its original
source inventory remain under
[native-retime-01-failed](verification/0.12.0/native-retime-01-failed/archive/ENGINE_TEST_retime_report.json).

The corrected helper requires an explicit expected-download count and waits
through late registration within its existing deadline. Retime author,
playback and archive require exactly **0/1/2** completed files. The same
contract covers the concrete multi-download OTIO and still-photography helpers.
Existing path, owned-job, byte/hash and independent media checks remain intact.
All **114 compared production runtime, web and application source paths** are
byte-identical to the first successful whole-build freeze. Only acceptance
helpers, a real regression test, CI step order and the manifest changed.

Two new unittest methods exercise six real Chromium subcases across three
browser adapters. A second attachment requested after JavaScript returns must
still complete; a missing second attachment must fail within the helper's
three-second deadline. Four existing integrity tests also passed. The first
targeted attempt could not create a loopback socket before any browser launched.
Its unchanged failed record is retained under
[download-completion-00-blocked](verification/0.12.0/download-completion-00-blocked/interpretation.json).
The accepted host-context run used the same source and assertions.

## Actual browser and native retime workflows

| Phase | Checks | Actual Chromium | Actual Mac coordinator |
| --- | ---: | ---: | ---: |
| Fixture preparation | 6 | 1.269 s | 2.003 s |
| Author, edit history and reopen | 14 | 4.151 s | 6.073 s |
| Rendered playback and movie download | 19 | 9.802 s | 12.118 s |
| Archive restore, render and both downloads | 19 | 6.084 s | 6.735 s |
| Total reported outer checks | **58** | **Passed** | **Passed** |

There are **three actual native UI executions and one fixture preparation**;
fixture generation alone is not native certification. Outer checks include
repeated source and cleanup guards and are not 58 distinct feature tests.
Every Mac phase remained inside its 18-second foreground budget, with at most
14 seconds assigned to the helper. Owned jobs, server and helper processes
were joined; repeated runs require a fresh complete fixture.

Chromium records are under
[browser-retime-02](verification/0.12.0/browser-retime-02/phase-summary.json).
They use Chrome for Testing **134.0.6998.35** and Playwright **1.51.1**, and retain
`native_certified: false`. The unchanged browser executable SHA-256 is
`f661a8c124888f491966c29581f33c1953c86c15d77048bc91452b66743d5f3a`.
The [full source binding](verification/0.12.0/browser-retime-02/full-source-binding.json)
matches the accepted core before and after. Playback decoded 13 pictures
and captured 17,408 stereo sample frames.

The release owner executed the native workflow in actual WKWebView. The
[native consistency review](verification/0.12.0/core-acceptance-01/native-consistency-review.json)
verifies all 37 transferred JSON files and matches every operative
runtime/web/helper source to the accepted core. Corrected phase records are
under [native-retime-02](verification/0.12.0/native-retime-02/archive/ENGINE_TEST_retime_report.json).
The fresh compiled helper is 206,920 bytes, SHA-256
`c6b70d236c056a6ed3eaa08ef44aaa1672ecce904f8004095b69ac2a60f3bee7`;
its Swift source is
`f6b3ee4295bcefe003c2220a7ed42a3dc4208a95ce6842936b8a901048aef6cd`.
The [native build receipt](verification/0.12.0/native-build/smoke-build-02.json)
records the 13.874-second fresh compilation.

Every exported ProRes movie contains **15 picture frames and 30,000 stereo
sample frames**, all compared to independent truth. Maximum analytic PCM error
is **0.5040506312921025 of a 16-bit LSB**. Maximum interior picture MAE is
**3.0890299479166665** in Chromium's FFmpeg environment and **2.107421875** on
the Mac. Black and silent lead intervals are exact. Both restored and original
movies passed independently, and the native ZIP and MOV downloads completed
and matched their actual owned outputs.

## Installation and canonical launch

The actual **0.12.0 / build 13** replacement passed all **five independent
installation gates**. It reconciled **112 runtime/web files** and the complete
**117-file application bundle**, preserved the previous 0.11 bundle, and
preserved **59 existing project files / 2,858,334,503 bytes**.

| Installed identity | SHA-256 |
| --- | --- |
| Native application executable | `ca2a5bf65d934b87b0dfafc55392b648bda650c1c7ce76491cc5b21e20a84b39` |
| Complete bundle inventory | `0815da5bec19eb5c214496000e3a9ca07bdc8781fdebb3730a7e0fa79b5ea2c2` |
| Independent after-installation receipt | `1da36c98eeabdd91fa79a1492f5c6956c689450643e0087fd9d9641498480ef8` |

Canonical installed launch passed **16/16 in 7.028 seconds**, including the
first ordinary native termination, owned server exit, workspace ownership
release and a fresh no-active-jobs shutdown receipt. All 117 bundle files and
protected project/cache files remained unchanged; force termination and
production-code injection were not used. The public
[installation summary](verification/0.12.0/installed-current-01/installation-summary.json)
and [canonical launch report](verification/0.12.0/installed-current-01/launch/installed-launch-report.json)
retain their source/native/bundle identities. The prior 113-file 0.11 bundle
is preserved in its verified backup archive. The installation summary SHA-256
is `8d95706b7e01ed003a272dee828fa04f8f9fa61608f4427b2c56a75f16dbfdac`.

The [Mac source binding](verification/0.12.0/core-acceptance-01/mac-frozen-source-binding.json)
compares all **344 core files including the manifest** against the exact 895-test
report. Every one of the 112 installed runtime/web payloads also matches the
local accepted core. The 88 transferred installation/readiness/source JSON
files were verified against the release owner's exact transfer manifest.

## Installed runtime readiness and final publication

All eight required installed default-runtime endpoint phases passed:

| Endpoint | Checks | Time | Source-bound receipt |
| --- | ---: | ---: | --- |
| deep | 14/14 | 3.613 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/deep/tool-report.json) |
| ray-optics | 14/14 | 14.404 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/ray-optics/tool-report.json) |
| physical-rendering | 14/14 | 3.985 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/physical-rendering/tool-report.json) |
| learned | 14/14 | 5.817 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/learned/tool-report.json) |
| reconstruction | 14/14 | 3.287 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/reconstruction/tool-report.json) |
| scene-processing | 14/14 | 2.772 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/scene-processing/tool-report.json) |
| multicam-sync | 14/14 | 2.648 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/multicam-sync/tool-report.json) |
| retime | 14/14 | 3.503 s | [Report](verification/0.12.0/installed-current-01/readiness-phased/retime/tool-report.json) |

Separate preparation passed **5/5 in 3.709 seconds**. Final preservation passed
**6/6 in 2.674 seconds**: all 117 installed bundle files and all 57 protected
workspace files / 2,858,334,304 bytes were preserved; no files changed or went
missing, no unexpected additions appeared, and no app, active job or workspace
owner remained. These protected-workspace counts differ from the installation
project baseline because the readiness guard defines its own scope and excludes
operational metadata. The [final report](verification/0.12.0/installed-current-01/readiness-phased/verify/readiness-verification-report.json)
SHA-256 is `8dd544c219ff5c43ad32e81c2fb334de48b42b98b3a49747c20cb8df33a6e2f5`.

The actual installed retime endpoint returned OpenCV-headless **4.11.0.86** and
NumPy **2.3.5**, the supported DIS method and limits, and a measured median
translation error of **0.0000033207866181328427 pixels**. This small synthetic
probe establishes actual installed engine execution within its stated bounds;
it does not establish arbitrary-shot interpolation quality.

The coordinator ran one owned foreground phase at a time. Each report binds the
same accepted core/tree/manifest, native executable, installation receipt,
controller and coordinator, with actual ordinary termination and no force quit.
Readiness is separate from full installed-app editing/export acceptance. The
[recorded command sources](verification/0.12.0/tools/recorded-phased-commands.json)
retain the ten actual historical bounded invocations, including the failed
optimized controller build and the successful unoptimized build. No failed
build receipt was removed or reclassified.

Text-only public evidence includes both complete suite reports/logs,
source/commit identities, browser and native reports, preserved failures and
independent acceptance tools. Synthetic raw pictures, sample arrays, movies,
screenshots, archives and model weights are excluded from Git. Private
installation inventories are represented by source-bound public summaries.
Original fixtures and the complete local handoff remain retained separately.

Historical 0.11 publication commit
`4095e184de322ba6b9d1bfb2f7ed3bf65ecdf7e8` preserves the earlier 874-test core,
19 native phases, verified installation/launch and selected installed-runtime
readiness. Its records and three historical release documents are retained in
this documentation merge. Current 0.12 README/ledger claims use the new core;
historical results retain their original source identity.

The [documentation/source reconciliation](verification/0.12.0/documentation-release-01/source-reconciliation.json)
records exactly **nine changed declared documentation/ledger paths**, **334
unchanged declared source files** and **112 unchanged installed runtime/web
payloads**. The existing generator produces the separate final manifest; all
production, tests, native helpers and CI workflow bytes remain identical to
accepted core `c9869e86`. Historical 0.11 records retain their original bytes.
Final exact-head CI/publication remains pending. No source test, native fixture or installed
readiness result certifies signed/notarized distribution, arbitrary-footage
optical-flow quality, sustained production performance or full professional
parity. The [unfinished-work register](UNFINISHED_0_12.md) retains those limits.

## Historical pre-integration acceptance

The original retime candidate's source manifest and receipts are retained under
`verification/0.12.0/isolated-retime-01/`. These results belong to that exact
isolated source, before the final 0.11 integration and 0.12 version changes.

| Gate | Actual result |
|---|---|
| New clock and actual-media tests | 19/19, zero failures/errors/skips, 16.195 s |
| Existing editing/live-PCM affected checks | 19/19, zero failures/errors/skips, 1.990 s |
| Existing constant-retime/reverse/nested/multicam/trim media checks | 10/10, zero failures/errors/skips, 18.317 s |
| Actual Chromium workflow | 58/58: prepare 0.760 s, author 2.291 s, playback 9.611 s, archive 5.437 s |

The numerical checks decode actual source and delivered media. Six measured
flow midpoints matched independently translated interior pixels exactly.
Fractional-rate split PCM was sample-for-sample identical to the unsplit output.
The browser captured 13 decoded pictures and 16,384 stereo sample frames. Both
downloaded ProRes movies had 15 pictures and 30,000 stereo sample frames, with
maximum analytic PCM error 0.5041 of a 16-bit LSB and maximum interior picture
MAE 3.0891. Archive restoration retained editable curves and original media.

All 121 operative browser/helper source identities remained unchanged. The
original failed source-PTS experiment is preserved separately; resetting PTS
after source-frame trimming fixed the observed picture duplication. Exact
rational source anchors also prevent a reopened split curve from changing a
half-frame nearest-picture decision.


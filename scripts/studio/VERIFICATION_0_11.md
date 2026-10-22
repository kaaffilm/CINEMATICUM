# CINEMATICUM Studio 0.11 verification

Recorded 22 October 2026. Accepted core
`530ba2400571a8b67efa2d9ab28997f65920c006` starts from published
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

## Accepted frozen core

The complete discoverable Python/Node/media suite passed **874/874 tests** with
zero failures, errors, skips, expected failures or unexpected successes.
Unittest execution took **807.404 seconds**; the complete gate took **961.413
seconds** and exited zero. Actual pinned imaging, tracking, optics, physical
rendering, learned inference, reconstruction, Blender and PBRT runtimes were
present. The genuine Kodak RAW fixture ran without a missing-fixture exception.
All five managed runtime inventories were unchanged before and after the run.

| Identity | Recorded value |
| --- | --- |
| Accepted core commit | `530ba2400571a8b67efa2d9ab28997f65920c006` |
| Git tree | `4836005d8a9aed6790e596c23fa5e8b58d9d8ede` |
| Declared source files | 330, unchanged throughout the complete run |
| Source-integrity manifest SHA256 | `141b53f435f68d325a73e2f0d930fc4acd7054b364b3336aada9f4439bd43d66` |
| Runner inventory SHA256, before and after | `a4c94c9c4c0aafc2ab99cc74f35b7870daeae71ba353922bc75b413c01c68873` |
| Complete report SHA256 | `d46c3a8de453269d18dcf0cb5981d2b3d83f3ceb5b4309fbf1ca5d5266a49d4c` |
| Complete log SHA256 | `d8fbdd4a80e53021965c4afcfc659a504070ecf67bb1b7ebab716ff19f4d4efa` |

The [full report](verification/0.11.0/whole-build-current-02/report.json),
[log](verification/0.11.0/whole-build-current-02/verification.log) and
[collection summary](verification/0.11.0/whole-build-current-02/summary.json)
retain exact package, runtime-receipt and binary identities. Collection also
matched all 330 declared source blobs plus the manifest against this exact Git
commit and the current files: **331/331 matches**.

The [first complete run](verification/0.11.0/whole-build-current-01-failed/summary.json)
remains failed and preserved: 874 tests ran, with one stale JavaScript VM fixture
omitting the normal `project.settings` object. Adding only `settings:{}` to that
fixture retained every audio-clock/gap/preparation-cancellation assertion.
Production code did not change. The same original test passed in the second
complete run; the first result was not relabeled or combined with a selective
rerun to obtain the 874-test pass.

## Native feature acceptance

All **19 phases passed**, comprising **15 native executions and four fixture
preparations**. They report **235 outer checks**. Those checks include repeated
source-identity and cleanup assertions and are not 235 distinct feature tests.
The source-binding record contains **1,917 hash comparisons across 138 unique
production/helper source files**, all matching the accepted freeze.

| Native workflow | Phases | Native executions | Fixture preparations | Reported outer checks |
| --- | ---: | ---: | ---: | ---: |
| Startup quit and active-job protection | 3 | 3 | 0 | 16 |
| Simultaneous cameras and fixed sound | 4 | 3 | 1 | 58 |
| Float32 controls and downloaded master | 3 | 2 | 1 | 28 |
| OTIO composition editing/render/archive | 4 | 3 | 1 | 63 |
| HDR photography/panorama/delivery | 5 | 4 | 1 | 70 |
| Total | 19 | 15 | 4 | 235 |

The [native source-binding receipt](verification/0.11.0/native-current-01/source-binding.json)
has SHA256 `c722fafcdc53735d3d9ac753413ad8694abaf6e418ab2eca88d822d42c69fe54`
and identifies every phase report. Its whole-build status was captured before
run 02 completed; the later full-suite receipt above supplies that separate
result. The raw receipt remains unchanged. Native feature harnesses use actual
WKWebView/owned workers and explicit evidence download destinations. They do not
certify physical input, arbitrary NSSavePanel navigation, the canonical installed
launcher, production quality or HDR monitoring.

## Replacement installation

The accepted core was installed as **0.11.0 / build 12** and all **five independent
gates passed**: frozen source, installed bundle, installer receipt and prior-app
backup, existing projects, and original checkout. The installation reconciles
**108 runtime/web files** and the complete **113-file bundle**, preserves all
**105 files** of the previous 0.10 application in its verified ZIP, and preserves
**59 existing project files / 2,858,334,502 bytes**.

The first aggregate installer call exceeded its 18-second foreground limit;
the canonical 0.10 app remained intact and its incomplete staging was retained.
A fresh build then executed the unchanged accepted installer commands/functions
in bounded foreground phases: main compilation 7.818 s, icon compilation 2.091 s,
icon drawing 0.106 s, ICNS packaging 0.095 s, `install_staged` 0.230 s and
registration 0.081 s. Each successful phase recorded actual exit-zero evidence.
The old bundle and complete staged source/runtime identities were revalidated
before the original protected replacement transaction. No production source
was changed to split these phases.

| Installed identity | Recorded value |
| --- | --- |
| Native executable SHA256 | `8f19b8920ebdd8cfacf7c3330ed60043fe33a22c6aed494d377ee64e080427ad` |
| Independent after-receipt SHA256 | `7ecf56cdb747a0ded253a35acfa601a1cd64d60d247e206f4101db31dafabbc3` |
| Installer receipt SHA256 | `dec23b7bddf9e7a5c407beffc608bb29b415042ae59da316dcd49e08d715d693` |
| Public installation summary SHA256 | `435083d8abed2cb8134a169aa51addbddc113872a89ef48ca249da8740c1a93b` |
| Accepted source code identity | `56d854dec688dbf25857cc154c6cfe819d934af147483da6a1d3967447a99345` |
| Preserved prior bundle | `CINEMATICUM Studio-20261022T112837Z-e044b7b2.zip` in the sibling `.CINEMATICUM-Backups.noindex` directory |

The public [installation summary](verification/0.11.0/installed-current-01/installation-summary.json)
records the source, backup and preservation identities without relabeling a
build or replacement check as installed-launch acceptance. No Developer ID
signing or notarization was performed. External runtimes remain prerequisites.

## Canonical installed launch

The actual LaunchServices gate passed **16/16 checks in 8.408 seconds** using
the accepted installed bundle. It verified the actual bundled server, default
workspace, runtime flags, live editor bytes and native window. The first
ordinary `NSRunningApplication.terminate` completed; the server exited, the
workspace lock was released, and a fresh shutdown receipt recorded no active
jobs. All 113 bundle files and the protected existing project/cache files
remained unchanged. No force quit, permission changes or injected application
code was used.

The [installed-launch report](verification/0.11.0/installed-current-01/launch/installed-launch-report.json)
has SHA256 `d0549b8ad8a9d09209f08ba9a2bbc103ed31821946c845baf55850f61828515d`.
It is separate from the feature harnesses and the selected default-runtime
readiness gates below. The earlier failed 0.10 ordinary installed quit remains
a failed historical result.

## Installed default-runtime readiness

All seven selected runtimes passed through the actual installed default engine
configuration. Each actual launch/readiness/ordinary-quit gate checks the owned
LaunchServices instance, bundled server, required bootstrap flags, live editor
bytes, runtime capability response and fresh shutdown/ownership release.

| Selected runtime | Passed checks | Gate time |
| --- | ---: | ---: |
| Deep compositing | 17/17 | 9.627 s |
| ray-optics | 14/14 | 17.630 s |
| physical-rendering | 14/14 | 4.682 s |
| learned | 14/14 | 7.302 s |
| reconstruction | 14/14 | 5.767 s |
| scene-processing | 14/14 | 3.320 s |
| multicam-sync | 14/14 | 4.150 s |

The [deep gate](verification/0.11.0/installed-current-01/tools/deep/installed-launch-report.json)
retains its separate 17/17 receipt. The subsequent six tool phases report
**84/84 checks**, with one **5/5 preparation in 5.095 s** and one **6/6 final
preservation verification in 4.346 s**. These repeated lifecycle and identity
checks are not additional distinct feature tests. Physical-rendering readiness
includes actual PBRT availability; learned readiness requires both SAM 2 and
TAPIR checkpoint entries. These capability GETs certify installed readiness,
not a new production-quality inference/render benchmark.

The [final preservation report](verification/0.11.0/installed-current-01/readiness-phased/verify/readiness-verification-report.json)
has SHA256 `9e78972299a6294b7d71da7339de5000a80a16e5238b3228b2db7a9b0e2e0317`.
It binds all six tool receipts to core `530ba240`, its original source manifest,
the actual installation evidence, coordinator, independent controller and native
executable. All six owned instances and bundled servers had exited; no active
durable jobs or workspace owner remained. The complete **113-file bundle** and
all **57 protected workspace files / 2,858,334,304 bytes** were unchanged, with
zero missing, changed, unexpected or newly added derivative files. The readiness
comparison excludes only the two documented operational lock/shutdown metadata
files; the installation gate above separately checked its complete 59-file
snapshot. Before and after protected-workspace inventory SHA256 is
`f3e2a94dd77fa0c4e8299121803952b91c613d13c69f7eb4b0267fb4087b860b`.

The original aggregate ray-optics call reached its foreground deadline after
actual ordinary quit but before finishing the large preservation rehash. Its
incomplete attempt and subsequent exact preservation reconciliation remain in
`installed-current-01/failed-aggregate-ray-optics/`. The successful coordinator
uses unchanged accepted launch/controller functions, one private full baseline,
one actual tool per call, and one final full preservation comparison. The 52
public phased receipts are retained byte-for-byte; the private full baseline
stays on the owner's Mac. No force termination or injected product code was used.

## Remaining release gates and documentation provenance

| Gate | Current status |
| --- | --- |
| Complete frozen local regression | Passed for accepted core `530ba240`, 874/874 |
| Native feature and startup regression | Passed, 19 phases as scoped above |
| Replacement installation and preservation | Passed, five independent gates |
| Canonical installed launch/ordinary quit | Passed, 16/16 in 8.408 s, including first ordinary termination |
| Selected default-runtime readiness | Passed: deep 17/17; six phases 84/84; preparation 5/5; final preservation 6/6 |
| Exact-head GitHub CI and PR publication | Pending for the final published 0.11 head; older 0.10/0.9 checks are historical |
| Final documentation/ledger source manifest | Reconciled: six documentation/ledger files changed; all other 324 declared files and all 108 runtime/web payloads unchanged |

The 874-test run covers the original **330-file** frozen inventory, including
documentation and the capability ledger. The documentation follow-up changes
exactly `README.md`, `scripts/studio/README.md`,
`scripts/studio/FEATURES_0_11.md`, `scripts/studio/VERIFICATION_0_11.md`,
`scripts/studio/UNFINISHED_0_11.md` and `scripts/studio/capabilities.json`,
plus the regenerated source manifest. All
other **324 declared source files**, including every production module, web
asset, test, native source and CI workflow, remain byte-identical to `530ba240`.
All **108 installed runtime/web payloads** retain their accepted source bytes.
The [documentation reconciliation](verification/0.11.0/documentation-release-01/source-reconciliation.json)
records exact before/after identities and the new manifest hash. Verification
receipts and helper sources are explicitly excluded from source-manifest scope.
The final published commit and exact-head CI must still be recorded separately.
The original full-suite report and its manifest hash remain unchanged; no test
execution is attributed to the later documentation bytes.

No record here certifies signed/notarized distribution, full professional
feature parity, calibrated HDR output, production-scale quality or an accepted
audience film. [Remaining work](UNFINISHED_0_11.md) retains those requirements.

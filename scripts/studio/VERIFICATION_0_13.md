# CINEMATICUM Studio 0.13 verification

This is the current integration record, not a completed release certificate.
The isolated candidate starts from published 0.12 commit
`dcea86196f81d6476a0f60538429b984b24c1129`, tree
`bcc211cff651a3773ae09823758e3add0d8e2e96`. Its accepted core and historical
release receipts remain immutable. New feature tests are attached to their
actual source and do not inherit the earlier complete-suite result.

## Historical accepted release

The [0.12 verification record](VERIFICATION_0_12.md) retains the actual
895-test complete run, 58 reported native retime checks, five installation
checks, 16 canonical launch checks and eight selected installed-runtime phases
of 14 checks each. Its final preservation passed six checks. Publication
`dcea8619` is now the head of draft PR #162, and the
[final installed-source reconciliation](verification/0.12.0/publication-complete-01/published-installed-reconciliation.json)
passed 10/10 for all 112 runtime files and the full 117-file bundle. The
actual Studio CI run 39780897825 subsequently passed 895/895 tests and seven
separate browser gates. The complete declared source and manifest identity
match `dcea8619`, as recorded in the retained historical source-binding report.

## Lens feature source and original acceptance

The exact feature patch SHA-256 is
`adb9c225c4562bd142e1f5722eb88c96918908fa64aa8807437d51253322cbb7`.
Its authoritative before-source tree is the accepted 0.12 core tree
`941da9dbc805788a89c610ee688cc17de08fccc4`. All ten modular source/test/document
paths applied with their exact after-hashes. README and the four related lens
capability records were merged while retaining current 0.12 history. The
[original path manifest](verification/0.13.0/lens-isolated-01/source-handoff/changed-paths.json)
and [replay receipt](verification/0.13.0/lens-isolated-01/source-handoff/patch-replay.json)
retain the complete isolated identities.

| Original isolated gate | Actual result | Scope |
| --- | --- | --- |
| Focused lens tests | 25/25, no failures/errors/skips, 15.173 s | Fourteen existing Brown tests and eleven new tests; 4,680 independent geometric comparisons, scalar/NumPy parity, actual RGBA/UNORM16 media and schema validation |
| Browser controls and delivery | 30/30 coordinator and 13/13 UI, 15.380 s | Actual four-projection authoring, pinned XML import, apply/undo/redo/save/reopen, eight-frame H.264 delivery/download/playback |
| High16 media | Passed inside focused tests | FFV1 and 16-bit PNG; more than 512 distinct red values, independent premultiplied RGBA error at most five UNORM16 units, paused/master equality |

The focused result is retained in
[focused-tests-04.log](verification/0.13.0/lens-isolated-01/focused-tests-04.log).
The final original browser result is
[browser-03/browser-report.json](verification/0.13.0/lens-isolated-01/browser-03/browser-report.json).
Its sampled independent mean RGB error was at most 0.411 and maximum error at
most 1.787 eight-bit code values. Every movie frame matched the separately
encoded lossless/codec control. The valid-control browser run preceded the
final malformed-`model:null` correction; the complete focused suite certifies
that correction, and the later phased browser gate uses the corrected source.

Original fixture/driver failures and their unchanged reports remain preserved.
The [independent review](verification/0.13.0/lens-isolated-01/independent-review.json)
records the schema correction. No previous failed receipt is relabelled as a
pass. Raw synthetic PNG/movie files remain outside Git, with their exact
identities in the [public evidence selection](verification/0.13.0/lens-isolated-01/public-evidence-selection.json).

## Shared native coordinator exercised in Chromium

The separate acceptance-only patch SHA-256 is
`5e2f4da1b519c382f88f502bd1b0027b91641e72d0106e15ec5fffa0bf04e0d9`.
It adds four files without changing the feature implementation. Its exact
[path hashes](verification/0.13.0/lens-native-harness-01/source-handoff/changed-paths.json)
and [tested source inventory](verification/0.13.0/lens-native-harness-01/source-handoff/tested-source-inventory.json)
are retained separately from the later integrated source.

| Phase | Outer checks | Seconds | Native certification |
| --- | ---: | ---: | --- |
| Prepare | 10/10 | 0.444 | No; fixture preparation |
| Author | 41/41 | 6.933 | No; actual Chromium |
| Render | 24/24 | 4.241 | No; actual Chromium |

The [portable result](verification/0.13.0/lens-native-harness-01/portable-02/browser-report.json)
passed in 12.628 seconds overall. Each coordinator phase remained below its
18-second foreground budget. The script uses the actual file-input change
handler, compositor controls, undo/redo, save/reopen and H.264 player, then
checks the completed download and all eight decoded movie frames. It does not
claim physical open/save-panel interaction. The result explicitly retains
`native_certified: false`.

A separate [ProRes backend check](verification/0.13.0/lens-native-harness-01/prores-backend-01/report.json)
passed 4/4 in 3.342 seconds. This validates the actual encoded control and all
eight frames, not the macOS decoder. Native ProRes playback is a clearly
identified test-owned video-element probe of the actual exported download;
the editor exposes ProRes as delivery rather than ordinary preview transport.

The first portable render correctly failed because the coordinator required
a new callback for a legitimately cached paused picture. The corrected helper
binds saved, previously verified project/frame snapshots by hash, requires the
current completed cached receipt and matching PNG hash, and still compares
the pixels to independent truth. The application cache and numerical
assertions were preserved. Both attempts remain under
[lens-native-harness-01](verification/0.13.0/lens-native-harness-01/public-evidence-selection.json).

## Pinned independent fixture and CI

The test-only Olympus XML is the unmodified Lensfun source at commit
`9e6deafe100a7c6f7ce019624bb8c4da20bf7c29`, path
`data/db/slr-olympus.xml`: **116,602 bytes**, SHA-256
`f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615`.
Its exact [source and license record](verification/0.13.0/lens-isolated-01/upstream-notices/source.json)
and CC BY-SA 3.0 notice are retained. CI downloads and hash-checks it into an
independent temporary test-fixture directory, outside application runtimes.
It explicitly invokes `test_lens_models_native_browser.cjs`; the main-function
phase harness is not silently counted as unittest discovery.

## FCPXML implementation and independent acceptance

The seven-path feature patch is 138,630 bytes, SHA-256
`7828902ad6e197197f17287e30c9772e7ae36428a2b36fcb265c44d1248e2865`.
The actual isolated feature and fixture hashes are retained in the
[feature manifest](verification/0.13.0/fcpxml-isolated-01/feature-manifest.json).
The importer/exporter, UI, fixture and documentation applied byte-for-byte.
The shared server retains both FCPXML dispatch and Lensfun import; the installer
contains both runtime modules exactly once. The only additional product changes
are the intended 0.13.0/build 14 version constants.

The [focused receipt](verification/0.13.0/fcpxml-isolated-01/focused-receipt.json)
records **19/19 tests**, no failures/errors/skips, in 7.761 seconds. Actual-media
oracles cover NTSC clocks, nonzero origins, connected lanes, trimmed compounds,
decoded reordered H.264 timestamps, admitted repeats, quantized-clock and
partial-tail refusals, static transform/opacity/dB, repeated import and real
portable archive relocation. Earlier timing counterexamples and failed test
attempts remain under the original isolated evidence.

The four-file acceptance-only patch is 49,644 bytes, SHA-256
`1104325dd9a178c5ad7f812fb177b7bf655831975df743a4e20d1356f4aceb02`.
Its final shared-coordinator Chromium run has the following actual results:

| Phase | Outer checks | UI checks | Seconds |
| --- | ---: | ---: | ---: |
| Prepare | 11/11 | Not applicable | 3.061 |
| Author | 30/30 | 16/16 | 4.026 |
| Render | 33/33 | 4/4 | 5.898 |

The [final result](verification/0.13.0/fcpxml-native-harness-01/source-handoff/final-results.json)
binds all 74 outer and 20 UI checks to the actual isolated source. Both UI
phases completed their actual download with no browser/download errors.
Every one of 40 numbered output pictures had the expected original frame
identity, and all 64,064 stereo sample frames matched independent PCM truth
with zero LSB error. The maximum source-color error was three eight-bit code
values. Its processed preview pixel, request snapshot and completed PNG bytes
were also checked. `native_certified` and `native_prores_playback_certified`
remain false; native WKWebView/ProRes execution is a separate integrated gate.

All six original portability attempts and the independent review remain in
the [retained text evidence](verification/0.13.0/fcpxml-native-harness-01/public-evidence-selection.json).
The source-path preflight failure, sandbox localhost denial, stale saved-label
assertion and ordinary export-save revision assertion are preserved. The last
two corrections changed acceptance assertions only; they did not change the
product's editing/save/download behavior. The passing preceding-source run is
retained separately from the final source-bound run. The raw media archive
remains outside Git with its complete file/hash inventory.

## Independent official Apple DTD gate

The schema gate uses its own hash-pinned lxml 6.1.1 environment (actual libxml2
2.14.6), separate from the app and shared verification runtimes. The official
Apple source document is pinned to SHA-256
`b4ed24c7dfbb84fb81bdb6880029f007b7784459256b9b489397d7264dc5735a`;
its extracted 1.10 DTD is pinned to
`6044527401b6cc92a9d86383437794d8de801c1904b6d08409ce81720fd23f33`.
Actual bootstrap, wheel installation, runtime probes and the original
hand-authored/public-export validation remain under
[fcpxml-schema-isolated-01](verification/0.13.0/fcpxml-schema-isolated-01/schema-acceptance-02.json).

The [final portability schema report](verification/0.13.0/fcpxml-schema-isolated-01/final-portable-06/schema-report.json)
independently validates the actual prepared input (2,793 bytes,
`c0654f0e5582479eb307e04baeafd926aa350319f6db8b494a8a7a1df7317769`)
and completed downloaded export (4,595 bytes,
`3bd3fd5f06bc01323708d8948aa4e7c50fceac4b98ca2f539f7f53a2c99f60d6`).
The validator disables external network/entity resolution and requires real
positive/invalid-grammar/security controls plus unchanged inputs/runtime/DTD.
The accepted 1.9 shared import subset has no separate 1.9 DTD certificate.
No Final Cut Pro host execution or unrestricted visual/DSP parity is claimed.

CI provisions this validator outside the application runtime, explicitly runs
`test_fcpxml_native_browser.cjs`, then validates that run's actual prepared XML
and completed download. The checkout explicitly selects the PR head SHA or
`github.sha` for other events. CI source verification therefore binds the
candidate head directly rather than a generated PR merge commit.

## Short integrated checks

The combined 0.13 product passed **72/72** targeted tests, zero failures, errors
or skips, in **30.353 seconds**. The
[actual report](verification/0.13.0/integration-01/targeted-tests/report.json)
includes FCPXML, existing Brown/new lens behavior, legacy OTIO interchange and
the installer. All nine observed product/UI source hashes stayed unchanged.
An independent read-only patch-composition review passed **21/21 checks** and
found no discrepancy in either route, runtime entry or shared UI bridge; its
[receipt](verification/0.13.0/integration-01/shared-source-review.json)
retains both patch identities and the precise version-only differences.
These short gates do not replace the complete frozen suite or native phases.

Both shared native coordinators were then exercised once against the integrated
0.13 runtime/UI bytes with the existing pinned Chrome executable:

| Integrated Chromium gate | Outer phase checks | Total seconds | Result |
| --- | --- | ---: | --- |
| Lens authoring and delivery | 10/41/24 | 17.827 | Passed |
| FCPXML authoring and delivery | 11/30/33 | 12.895 | Passed |

The [lens report](verification/0.13.0/integration-01/lens-browser-integrated-01/browser-report.json)
and [FCPXML report](verification/0.13.0/integration-01/fcpxml-browser-integrated-01/browser-report.json)
retain exact source inventories, actual downloaded media checks and the
unchanged browser SHA-256. Each phase stayed within its 18-second budget.
All reports retain `native_certified: false`. The exact integrated FCPXML input
and completed export separately passed the
[pinned independent Apple DTD gate](verification/0.13.0/integration-01/fcpxml-schema-report.json).
Public evidence keeps the original text and hashes; synthetic media/screenshots
are retained outside Git in inventoried raw-evidence archives.

## Integrated release gates still pending

The provisional 0.13 source is prepared for native acceptance before the
complete frozen suite. The complete integrated suite,
actual macOS lens and interchange acceptance, replacement installation,
canonical launch, installed-runtime readiness and exact-head publication/CI
remain pending. Independent installation/readiness tools are prepared for
0.13.0/build 14. Their tracked readiness template deliberately keeps its
core/tree/manifest/native pins unset and fails closed. After the accepted core
and actual native app exist, a separate copy outside the source checkout will
be bound to those exact identities and recorded with its own SHA-256. The
installation/readiness invocation uses that external copy without changing
the clean accepted core. A subsequent evidence-only release commit can retain
the exact tool and reconcile the unchanged product files. Their production
observation and preservation methods are unchanged.

Current SmokeTest Swift source matches its retained successful compilation
receipt; the release owner must check the actual binary identity before reuse.
The installed controller hardcodes the accepted bundle version/build, so only
those two constants change for 0.13.0/build 14. Its actual bounded `-Onone`
[controller compilation](verification/0.13.0/native-build/controller-build-01.json)
passed in 1.555 seconds with source SHA-256
`242ce3defae2a0d6f3466fb5a937776106081178cdbd40b16f55108a2fcf77e8`
and binary SHA-256
`514babe113c42ae6f666b29ab0b934d878cbc50cf7d9053086fea60a72877101`.
Its observation/ownership/termination methods are unchanged. Compiling the
independent controller does not certify a new installed application launch.

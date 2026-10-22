# CINEMATICUM Studio 0.13 verification

Studio 0.13.0/build 14 has completed its frozen local, actual native and
installed application acceptance. This record preserves those bounded outcomes
and their exact sources; the final published-head CI outcome is recorded
separately in PR #162 and its actual run/artifact.
The accepted core starts from published 0.12 commit
`dcea86196f81d6476a0f60538429b984b24c1129`, tree
`bcc211cff651a3773ae09823758e3add0d8e2e96`. Its accepted core and historical
release receipts remain immutable. New feature tests are attached to their
actual source and do not inherit the earlier complete-suite result.

## Historical accepted release

The [0.12 verification record](VERIFICATION_0_12.md) retains the actual
895-test complete run, 58 reported native retime checks, five installation
checks, 16 canonical launch checks and eight selected installed-runtime phases
of 14 checks each. Its final preservation passed six checks. Publication
`dcea8619` was accepted through draft PR #162, and the
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

## Actual source-bound macOS acceptance

The corrected frozen core is `cdd15816c228fe4133fbb3ce6d90978333d699e6`,
tree `a62ce29a8af68b38d14820c45fc42e1266762e34`. Its 367-file declared
manifest has SHA-256
`21034979d805cdf680c255720f6311319f3fc22c2b405dbd43294a5485d09f8d`;
the complete source fingerprint, including the manifest identity, is
`a40f5ead75fc240128030d4c438a8395751fc52f26f2446ceff48de9bcb97fd9`.
The [source freeze](verification/0.13.0/core-acceptance-01/source-freeze.json)
and [exact commit record](verification/0.13.0/core-acceptance-01/core-commit.json)
retain the original accepted identities.

All six actual Mac phases passed without a retry or native failure:

| Workflow | Prepare | Native author | Native render |
| --- | ---: | ---: | ---: |
| Lensfun/fisheye | 10/10, 0.225 s | 41/41, 6.800 s | 24/24, 3.944 s |
| FCPXML | 11/11, 0.689 s | 30/30, 1.844 s | 34/34, 3.649 s |

These are **150 outer checks**, with **36 nested UI assertions**, across four
actual native executions and two fixture preparations. Preparation remains
`native_certified: false`. Every foreground phase finished within 18 seconds.
The 17.151-second sum is the sum of separate phase durations.
The original [lens author](verification/0.13.0/native-current-01/lens-native-01/author/ENGINE_TEST_lens_models_report.json),
[lens render](verification/0.13.0/native-current-01/lens-native-01/render/ENGINE_TEST_lens_models_report.json),
[FCPXML author](verification/0.13.0/native-current-01/fcpxml-native-01/author/ENGINE_TEST_fcpxml_report.json)
and [FCPXML render](verification/0.13.0/native-current-01/fcpxml-native-01/render/ENGINE_TEST_fcpxml_report.json)
reports retain the actual UI outcomes, source snapshots and completed downloads.

Lens delivery checked every one of eight 160×90/12 fps ProRes pictures against
a separate codec control. FCPXML checked every source-frame identity in its
40-picture NTSC output and all 64,064 stereo sample frames against independent
truth, with **zero LSB PCM error**. Maximum source-color error was three
eight-bit code values. The native phases also observed advancing playback of
the actual exported ProRes downloads. Those checks are explicitly identified
test-owned decoder probes; the application uses ProRes as delivery. Muted
playback is not physical speaker monitoring. Physical open/save-panel
interaction and external Final Cut Pro execution remain unclaimed.

The independent [evidence consistency review](verification/0.13.0/core-acceptance-01/native-consistency-review.json)
verified all 95 original text records, 48 bound phase artifacts, 50 retained
raw-media identities and the exact 127/126-entry source inventories. Synthetic
movies/images remain outside Git; the original media inventory is preserved.
The observed SmokeTest binary is 206,920 bytes, SHA-256
`c6b70d236c056a6ed3eaa08ef44aaa1672ecce904f8004095b69ac2a60f3bee7`,
bound to source SHA-256
`f6b3ee4295bcefe003c2220a7ed42a3dc4208a95ce6842936b8a901048aef6cd`.

The exact Mac-generated hand input and completed XML download separately
passed the pinned Apple 1.10 DTD through the existing isolated Linux
lxml 6.1.1/libxml2 2.14.6 validator. This is validation of actual native
artifacts, not a claim that lxml ran on the Mac or that Final Cut Pro accepted
the document. The [actual schema receipt](verification/0.13.0/core-acceptance-01/native-fcpxml-schema-01.json)
passed eight validator/control/preservation checks in 0.045 seconds, with both
documents unchanged. Input SHA-256 is
`c0654f0e5582479eb307e04baeafd926aa350319f6db8b494a8a7a1df7317769`;
actual exported SHA-256 is
`6bb84d9c4ffbed26e51b43b879ba9d080736881807b892c6c85103787caf7a45`.
No separate 1.9 DTD certification is asserted.

## Complete frozen regression

The one complete run against core `cdd15816` **passed all 925 tests** with
process exit 0, zero failures, errors, expected failures, unexpected successes
or allowed/unexpected skips. The unittest body took **928.953 seconds**; the
complete runner, including strict source/runtime preflight and final inventory
checks, took **1,106.158 seconds**. There was no corrective rerun.

The [original full report](verification/0.13.0/whole-build-current-01/report.json)
is 142,197 bytes, SHA-256
`85a2d15cb8f08c839e9ff4f6416173779c4989ca7551b99b3c84edc86d559745`.
The [original log](verification/0.13.0/whole-build-current-01/verification.log)
is 304,416 bytes, SHA-256
`99d9714c6f25b50c69233d05cecc22505999348b9806284164556ef64b5cc6c8`.
The [compact summary](verification/0.13.0/whole-build-current-01/summary.json)
and [actual launcher invocation](verification/0.13.0/whole-build-current-01/invocation.json)
retain the interpreter, command, full measured counts and identities.

Every one of the 367 declared source files and the manifest matched the frozen
source before and after execution. The five managed engines—Optiland,
Mitsuba/Dr.Jit, learned SAM/TAPIR, COLMAP and Blender—retained their exact
installation receipts and complete runtime inventories. The base interpreter
was Python 3.12.14 with NumPy 2.3.5, OpenTimelineIO 0.18.1, OpenEXR 3.4.15,
OpenColorIO 2.6.0, OpenCV 4.11.0.86 and rawpy 0.27.1; the genuine Kodak RAW
fixture was present. Managed workers retain their own separately recorded
package versions. The complete runner did not permit a missing RAW skip.

This is the actual discoverable Python/Node/media suite. The standalone
phased browser/native drivers retain their separate reports and counts;
their assertions are not added to the 925 unittest result. The frozen core
remained tracked-clean throughout the run and its final read-only collection.

## Actual replacement installation and canonical launch

The 925-test report was transferred unchanged and independently bound to the
actual Mac core before promotion: the [Mac source binding](verification/0.13.0/installed-current-01/frozen-full-suite/mac-source-binding.json)
compared all **367 declared files plus the manifest**, required the accepted
core/tree and clean tracked source, and matched the original report SHA-256.

Fresh phased native compilation and icon generation completed before the
unchanged installer promoted the staged bundle. The original [build and promotion
receipts](verification/0.13.0/installed-current-01/phased-build/staged-validation-01.json)
retain the real compile, source and staging identities. The installed native
executable is **226,400 bytes**, SHA-256
`ca2a5bf65d934b87b0dfafc55392b648bda650c1c7ce76491cc5b21e20a84b39`.
Its actual bytes match the preceding unchanged Swift build; this release still
retains the fresh compilation receipt.

The independent [installation summary](verification/0.13.0/installed-current-01/installation-summary.json)
passed **5/5** source/installed/receipt-and-backup/projects/original-checkout
gates. It verified version **0.13.0**, build **14**, all **114 runtime/web files**
and the complete **119-file bundle**. Bundle inventory SHA-256 is
`ce983bba3a03ce13b965d779b26b04ed8cbc40bb111d9f43999a9e11ee583672`.
The embedded runtime/native source manifest is 11,183 bytes, SHA-256
`ca3a8e842a57faa7d093d4aaf63b94c72e54152014c01d3797e7fa5c528ef6cb`;
it is distinct from the repository's declared source manifest.

The previous 0.12 bundle was preserved as
`CINEMATICUM Studio-20261022T141133Z-ba798a07.zip`, 1,197,667 bytes,
SHA-256 `00aa6adb67759da5b1ad14b19391108ada5f9cf791d706094ff9c066da637c1d`.
All **117 previous bundle files** matched their accepted inventory. The fresh
0.13 before/after installation comparison preserved **59 existing project
files / 2,858,334,501 bytes**. The owner checkout check preserved its Makefile
bytes/mode, HEAD and Git-status snapshot; it did not inspect every owner file.
The complete private before/after evidence stays on the owner Mac; the public
summary omits private project names and contents. Its SHA-256 is
`c096f0aa20fca94bd5e1e2c352e062b423f90c50961a87dd092c52de5873ddc5`;
the independent after receipt SHA-256 is
`1c73ce565024cd2b1e693ce6e405d44cce6c216b822bf038761e76f2556817dd`.

Canonical [installed launch](verification/0.13.0/installed-current-01/launch/installed-launch-report.json)
passed **16/16 in 6.972 seconds**. The actual LaunchServices launch used the
installed native executable, bundled server and default project workspace.
It verified the live editor and native window, then completed the first
ordinary `NSRunningApplication.terminate`, server exit and workspace ownership
release. No force termination or production-code injection was used. The full
bundle and pre-existing project/cache files stayed unchanged. This launch
receipt has SHA-256
`c32618ede19c254250d41e7e93a327cf03c6b03f25592c0998b6d4fb99056e14`.

## Installed runtime readiness and preservation

The separate installed-readiness preparation passed **5/5 in 10.163 seconds**.
Eight distinct actual default-runtime endpoints then passed through owned
canonical launches and ordinary quits:

| Installed capability | Checks | Seconds |
| --- | ---: | ---: |
| Deep compositing | 14/14 | 6.174 |
| Ray optics | 14/14 | 13.285 |
| Physical rendering | 14/14 | 3.641 |
| Learned tracking | 14/14 | 5.373 |
| Reconstruction | 14/14 | 7.902 |
| Scene processing | 14/14 | 1.934 |
| Multicamera synchronization | 14/14 | 2.523 |
| Retiming | 14/14 | 2.255 |

The original per-tool reports and ownership events are retained under
[installed-current-01/readiness-phased](verification/0.13.0/installed-current-01/readiness-phased/prepare-report.json).
These are actual installed capability/readiness checks, not additional
production-quality inference, render, editing or output acceptance. The
complete frozen suite and separate native feature phases provide their own
processing/interaction evidence.

Final [preservation](verification/0.13.0/installed-current-01/readiness-phased/verify/readiness-verification-report.json)
passed **6/6 in 2.186 seconds**. All 119 bundle files and **57 protected
workspace files / 2,858,334,304 bytes** were unchanged, with zero missing,
changed, unexpected added or derivative-added files. The launch/readiness
comparison excludes only the explicitly disclosed operational workspace lock
and last-exit metadata; its 57-file count is distinct from the 59-file complete
installation snapshot. No owned application, active job or workspace owner
remained. The final receipt SHA-256 is
`56a15e8249f9e8b22ab04170e89671a4f576cc304570ae1c9194382b6155ccdd`.

The [installed evidence consistency record](verification/0.13.0/core-acceptance-01/installed-consistency-review.json)
verifies all **99 original public text files**, their source/build bindings,
actual checks and preserved bytes. This is a read-only receipt comparison,
not another native execution. The exact original [transfer manifest](verification/0.13.0/installed-current-01/transfer.json)
is retained with those files.

## External acceptance-tool binding

The core's reviewed readiness template remains fail-closed with its four
core/tree/manifest/native identity constants unset. The actual Mac run used a
separately copied and hashed external helper, binding **only those four
constants**. All remaining helper/controller bytes match the frozen template.
The [binding receipt](verification/0.13.0/installed-current-01/installed-acceptance-tool-binding.json)
records template SHA-256
`4a9e19cd07837a5e2376aa0a407416f83dda6af16babeccf066cf0ebba20b0d7`
and actual bound helper SHA-256
`a9c6feadfe85b263dd3010f8cd1815e753450048bc12c48b6788891fd9f65391`.
The exact bound tool copy is retained under `installed-current-01/bound-tools`;
the original core was not edited to run installation acceptance.

The [actual external Mac guard execution](verification/0.13.0/installed-current-01/installed-acceptance-guard-01.json)
passed **6/6** with an explicit `CINEMATICUM_ACCEPTED_SOURCE` path. The earlier
unpublished provisional handoff's path-inference defect and its six-test Linux
correction remain under `integration-01/external-guards`; no native or full
suite ran on that superseded provisional source. Those guard tests are
separate from the 925-test discoverable suite and from native application
acceptance.

The installed-controller version/build constants are 0.13.0/14. Its actual
bounded `-Onone` [compilation](verification/0.13.0/native-build/controller-build-01.json)
passed in 1.555 seconds, with source SHA-256
`242ce3defae2a0d6f3466fb5a937776106081178cdbd40b16f55108a2fcf77e8`
and binary SHA-256
`514babe113c42ae6f666b29ab0b934d878cbc50cf7d9053086fea60a72877101`.
The original observation, ownership and ordinary-termination methods remain
unchanged; build and installed execution are retained as separate proofs.

## Documentation-only publication and external CI

This release follow-up changes six current documentation/ledger files and
regenerates the declared source manifest. The [source reconciliation](verification/0.13.0/documentation-release-01/source-reconciliation.json)
compares the final declared source to accepted core `cdd15816`: **361 other
declared files, all 114 installed runtime/web payloads, and every product,
test, native and CI byte remain unchanged**. All original reports keep the
actual core and manifest identities from their execution. No old receipt is
rewritten to impersonate this evidence commit.

Exact final-head CI is a **post-publication gate**. Its actual outcome belongs
to [draft PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162), the matching
[workflow/checks](https://github.com/kaaffilm/CINEMATICUM/pull/162/checks) and
collected run artifact. The workflow checks the explicit PR head, or
`github.sha` for push/dispatch, and retains the complete suite, separate
browser gates and independent XML grammar validation. The release owner
records the resulting exact-source run/artifact in the PR after collection;
this source commit does not predict its own external result or require a
new source commit solely to attach it. Historical accepted 0.12 CI remains
immutable in this repository.

Full professional parity remains false. The retained [signing-prerequisite
observation](verification/0.13.0/installed-current-01/distribution-signing-prerequisite.json)
found one valid code-signing identity overall and no usable Developer ID
Application identity. No identity/private-key material was exported;
notarization account access was not inspected. This is a specific distribution
prerequisite, not a claim that all owner accounts or credentials are absent.
Python, FFmpeg, Blender and optional workers remain external prerequisites;
this is not a signed/notarized complete distribution. The
[remaining-work register](UNFINISHED_0_13.md) retains the broader implementation,
production-quality, monitoring and accepted-film requirements.

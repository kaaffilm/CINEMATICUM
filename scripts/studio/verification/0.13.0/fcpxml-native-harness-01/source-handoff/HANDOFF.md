# FCPXML acceptance helper and independent review handoff

The acceptance-only extension is complete and frozen. The final portable run
passed all 74 coordinator checks, all 16 author UI checks and all four portable
render UI checks against the final FCPXML source and fixture. Actual native
WKWebView execution remains a separate required gate owned by root.

## Integration

Apply `fcpxml-native-acceptance.patch` from the repository root after the separate
FCPXML feature patch. This patch adds exactly four files and changes no production
code, runtime, release history or capability record:

- `scripts/studio/test_fcpxml_macos.py`
- `scripts/studio/test_fcpxml_native_browser.cjs`
- `scripts/studio/macos/FcpxmlSmoke.js`
- `scripts/studio/FCPXML_NATIVE_ACCEPTANCE.md`

Patch SHA-256:
`1104325dd9a178c5ad7f812fb177b7bf655831975df743a4e20d1356f4aceb02`.
The patch is 49,644 bytes. `changed-paths.json` contains every new file's exact
SHA-256 and size. `patch-replay.json` records a successful clean replay and
byte-for-byte verification of all four files. The isolated feature base was
`c9869e86b9421b7fdc083d249b1616114320f0d5`; the intended integrated 0.13 base is
the published 0.12 commit `dcea86196f81d6476a0f60538429b984b24c1129`.

The feature source and fixture are supplied separately by verification_runtime.
The final tested feature identities are:

| Path under scripts/studio | SHA-256 |
| --- | --- |
| fcpxml.py | d2eb27d14243d6d51e3d19325d09101fe9a67209231e79d92a101bfbe8b14064 |
| test_fcpxml.py | 2c633fb6d7b438ac5bd9108b6d36a715a81caf5b928c75adf23451052cd6591a |
| server.py | 06a2ffa157f339d64a93f4ed923bf6af3764e33697d808ddef0b7bc40c56595e |
| install_macos.py | 8291966a06594387db5fbf0aa6106abebd4593ea6296a15d1b9fb1587c5b862c |
| web/interchange-ui.js | e0b74c54728de48e136e1d0c40608da63785847a1fdf5c93acbd377da2df3923 |
| web/index.html | 2707509f6e8c17250e2fea625cd23fefdac9f4be693d1e9153481d0711c2c2c0 |

`tested-source-inventory.json` binds all 125 runtime, web and helper dependencies
used by the isolated final run. Regenerate the expected inventory from the final
integrated candidate before its native run. This isolated inventory does not
certify later lens integration, release documents or installed-bundle parity.

## Final actual acceptance

Final raw evidence directory:
`/workspace/scratch/091f394ee5df/cinematicum-fcpxml-native-driver-06`.

| Phase | Coordinator checks | UI checks | Elapsed |
| --- | ---: | ---: | ---: |
| Prepare | 11/11 | Not applicable | 3.061 s |
| Author | 30/30 | 16/16 | 4.026 s |
| Render | 33/33 | 4/4 | 5.898 s |

The same 18-second coordinators, 14-second helper ceiling and 13-second browser
script deadline will be used on the Mac. Every phase preserved its original
media, immutable truth, sentinel project and complete source inventory. Both UI
phases had one completed download, zero browser errors and zero download errors.

The hand-authored XML exercises nonzero asset and sequence origins, connected
overlays, independently trimmed audio with gain, a real trimmed compound sequence
and a source-clock-proven constant forward time map. It is authored independently
of the exporter. The imported native cut is compared directly with that XML's
known semantics and actual original media, before any exported XML is reimported.

The actual completed ProRes movie contains all 40 expected source frame
identities, including every overlap, compound and double-speed boundary. All
64,064 stereo sample frames match their original PCM windows exactly: maximum
sample error is zero LSB. The maximum color-channel error is 3 on the 8-bit
independent source-color check. The processed preview pixel at frame 6 is exactly
`[0, 0, 102, 255]`, with its request snapshot, completed job and downloaded PNG
bytes bound in the receipt. A normal movie export performs one save; only the
expected revision increment and update timestamp change.

The existing Chrome executable was unchanged before and after the run:
`f661a8c124888f491966c29581f33c1953c86c15d77048bc91452b66743d5f3a`.
Every portable report explicitly sets `native_certified` to false. The wrapper
also sets `native_prores_playback_certified` to false.

## Exact DTD artifacts

Use the real acceptance artifacts below for the separate pinned Apple DTD
validator. Their bytes are copied from the actual fixture and completed download,
and equality is enforced by acceptance checks.

| Artifact relative to final evidence directory | Bytes | SHA-256 |
| --- | ---: | --- |
| prepare/ENGINE_TEST_input.fcpxml | 2,793 | c0654f0e5582479eb307e04baeafd926aa350319f6db8b494a8a7a1df7317769 |
| author/ENGINE_TEST_exported.fcpxml | 4,595 | 3bd3fd5f06bc01323708d8948aa4e7c50fceac4b98ca2f539f7f53a2c99f60d6 |

No extra XML or media download is required for this helper. It generates the
owned fixture with the feature's `test_fcpxml.py` and installed FFmpeg. The XML's
file and HTTPS labels are deliberately inaccessible references; only explicitly
admitted owned assets can be used. The fixture has actual asset hashes.

## Execution

Full Mac commands and requirements are in the added
`scripts/studio/FCPXML_NATIVE_ACCEPTANCE.md`. Use the existing native smoke helper
with download completion support; no new Swift binary is supplied here. Prepare,
author and render must run sequentially against one fresh owned fixture. The
helper executable is separately hashed at preparation and checked thereafter.
Use explicit `/private/tmp/...` paths on the Mac to avoid the `/tmp` symlink.

The exact final portable command, from the isolated acceptance repository root,
was:

```sh
NODE_PATH=/workspace/scratch/091f394ee5df/cinematicum-runtimes/browser-driver/node_modules \
node scripts/studio/test_fcpxml_native_browser.cjs \
  --python /workspace/scratch/091f394ee5df/cinematicum-runtimes/verification/bin/python \
  --browser /workspace/scratch/091f394ee5df/cinematicum-runtimes/chrome-for-testing-134.0.6998.35/chrome-linux64/chrome \
  --evidence /workspace/scratch/091f394ee5df/cinematicum-fcpxml-native-driver-06
```

A repeat must use a new evidence directory. The current managed sandbox denied
localhost binding; the bounded final command was run with the approved sandbox
override. This did not change application behavior or waive a verification gate.

## Retained failures and counterexamples

`evidence-files.json` inventories all 265 retained files and their hashes, totaling
24,357,144 bytes. `retained-evidence.tar.gz` contains those exact files, including
all six attempts and the independent review. Its SHA-256 is
`b4515e080254ad90119807e64b6b6baaa2cbaa58f4b6667edd68035f3053ba5b`.
`text-evidence` retains 186 text artifacts for repository inclusion without
embedding the raw media. The raw media remains available in the archive and
original evidence directories; the manifest binds both.

The earlier attempts remain visible:

- 01: preflight found that the old temporary Chrome path no longer existed.
- 02: fixture preparation passed, then sandbox localhost binding was denied.
- 03: actual authoring and download succeeded; the helper incorrectly expected
  a saved-status label that changes to `LOCAL PROJECT` on reopen.
- 04: authoring and all movie/frame/PCM checks succeeded; the helper incorrectly
  treated the normal export-save revision and timestamp update as a content edit.
- 05: all 74 checks passed against the preceding feature source. It is retained
  but superseded by 06 after the feature's provenance fix and actual fixture hash.
- 06: all 74 checks passed against the final feature and fixture hashes above.

The corrections for 03 and 04 were confined to acceptance assertions. They did
not change product behavior or bypass the file, review, apply, undo, save, export
or download controls.

## Independent correctness review

`independent-review.json` contains the complete review and primary Apple links.
The review identified and resolved six concrete timing or validation risks:
unproven negative-map first-frame semantics; mismatched conform/map sampling;
general positive nearest sampling that differs from the native filter; double
speed on rounded container timestamps; fractional slow-map source tails; and
ignored nested content inside notes. Production fixes belong to the feature
owner and are bound to the final source hash above.

Actual source-counter counterexamples are preserved. The resulting picture scope
is explicitly bounded to the proven source grids; unsupported cases fail with
errors. Double-speed admission checks decoded presentation timestamps and
best-effort timestamps, with a bounded prefix and immutable file identity; it
does not rely on packet decode order. The feature owner separately tested a
reordered H.264 source. Repeated import now preserves valid existing sequence
timecode-origin records, with a focused regression.

No additional blocker was found in the reviewed origin math, connected and
nested offsets, owned-media relinking, XML limits, unsupported-property rejection
or public export structure. This statement applies to the reviewed supported
scope, not arbitrary FCPXML documents.

## Explicit remaining gates and limits

Root must run the actual three Mac phases on the final integrated candidate,
including WKWebView ProRes decode and an advancing movie clock. The helper uses a
separately labeled test-owned video element for that native decoder check.
It does not claim a new product ProRes transport or physical speaker output.

File/DataTransfer injection exercises the real shipped onchange handler; neither
physical open nor save panels are asserted. Installed-bundle integrity,
canonical launch, whole-suite verification and release publication remain the
integrator's independent gates.

No Final Cut Pro host is installed, so external-editor import and render parity
are unverified. Apple DTD validity and public self-reimport do not replace that
gate. Negative/reverse FCPXML maps, arbitrary speed ramps, general fractional or
mixed-rate picture grids and media outside the bounded proof remain unsupported.
The native final audio limiter and another editor's retiming DSP are not encoded
by static public dB values; this fixture is below the native limiter threshold.
No AAF, legacy FCP7 XML or general native-project exchange claim is made.

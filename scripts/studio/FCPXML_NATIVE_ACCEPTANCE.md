# Native FCPXML acceptance

This is a bounded acceptance of CINEMATICUM's shipped FCPXML workflow. The
actual import starts from a hand-authored public XML document. Source media,
timeline source-frame counters and the original stereo PCM windows are generated
independently of the FCPXML exporter. A private exporter/importer round trip is
not used as the oracle for the original imported edit.

## Required environment

Use the final candidate's Python runtime with NumPy and its normal FFmpeg and
FFprobe. Use the already-built `macos/SmokeTest.swift` helper that supports an
owned download directory and `expected_download_count`. This workflow does not
install software, fetch models, open source URLs or access any existing project.

The new source files are `test_fcpxml_macos.py`,
`test_fcpxml_native_browser.cjs` and `macos/FcpxmlSmoke.js`. The independent
fixture lives in the production feature's focused test, `test_fcpxml.py`.
`source_inventory()` binds all shipped runtime/web files, the installer inventory,
the Swift helper source and every imported acceptance helper to exact SHA-256 and
size values. The native helper executable is separately bound at preparation and
must remain unchanged in every phase. Regenerate the expected inventory after
the final integrated source freeze; a prior isolated candidate's inventory does
not certify a later release.

## Three owned foreground phases

Every coordinator invocation has an 18-second foreground budget. Its browser
helper is limited to at most 14 seconds; the JavaScript has its own 13-second
deadline. The coordinator closes its own server and joins its owned jobs before
reporting. Do not reuse a completed phase or erase a failed attempt. Prepare a
fresh fixture and fresh output directories for a repeated acceptance.

1. **Prepare** makes two real numbered video sources with stereo PCM and a
   hand-authored FCPXML timeline at exactly `30000/1001` fps. It writes immutable
   picture-counter and PCM truth, admits the original media, preserves a separate
   sentinel project and saves an initial eight-frame cut. It does not preapply an
   FCPXML import.
2. **Author** selects FCPXML in the actual interchange dialog, supplies the exact
   fixture bytes through the shipped file input's `change` handler, explicitly
   relinks the two resources and reviews without modifying the edit. It applies
   one undoable change, performs one undo and one redo, saves, switches projects
   and reopens. It exports and actually downloads public FCPXML, then reviews the
   exact downloaded bytes using their content hashes without applying them.
3. **Render** reopens the saved imported edit, displays an exact processed frame,
   exports ProRes through the ordinary export dialog and actually downloads it.
   The native run decodes and plays that exact export through a separately
   labeled test-owned video element. The coordinator decodes every video frame
   and stereo PCM sample and compares them with the independent original-media
   oracle. It also checks the completed export receipt and download hashes. A normal movie export saves once: only the revision and update timestamp may change; the complete remaining project must remain identical.

The timeline has 40 frames, nonzero source and sequence timecode origins,
connected overlays, independent audio levels, a real trimmed compound sequence
and a forward constant time map. The accepted speed and sampling mode are taken
from the independently authored, source-bound fixture; unsupported retime grids
must remain explicit errors in the production importer/exporter. The older
native engine counterexamples are retained separately in review evidence.

## Mac commands

From the final candidate's `scripts/studio`, use absolute, non-symlink paths.
On macOS prefer an explicit `/private/tmp/...` directory over the `/tmp` symlink.
Create only the acceptance parent directory in advance; `fixture`, `prepare`,
`author` and `render` must not yet exist.

```sh
python -B -c 'from test_fcpxml_macos import source_inventory,write_json; write_json("/absolute/acceptance/source-inventory.json",source_inventory())'

python -B test_fcpxml_macos.py \
  --binary /absolute/existing-native-helper \
  --operation prepare \
  --fixture-workspace /absolute/acceptance/fixture \
  --output /absolute/acceptance/prepare \
  --expected-sources /absolute/acceptance/source-inventory.json

python -B test_fcpxml_macos.py \
  --binary /absolute/existing-native-helper \
  --operation author \
  --fixture-workspace /absolute/acceptance/fixture \
  --output /absolute/acceptance/author \
  --expected-sources /absolute/acceptance/source-inventory.json

python -B test_fcpxml_macos.py \
  --binary /absolute/existing-native-helper \
  --operation render \
  --fixture-workspace /absolute/acceptance/fixture \
  --output /absolute/acceptance/render \
  --expected-sources /absolute/acceptance/source-inventory.json
```

The exact hand-authored input is retained at `prepare/ENGINE_TEST_input.fcpxml`.
The actual completed interchange download is also retained at
`author/ENGINE_TEST_exported.fcpxml`; its copied bytes must match the real
download and owned export. These deterministic paths can be validated against
the pinned Apple DTD without substituting a new fixture.

Each phase writes `ENGINE_TEST_fcpxml_report.json`, its exact source inventory,
saved project, executed JavaScript identity and an artifact inventory. UI phases
also retain the actual browser result, screenshots, owned job records and
downloaded files. Successful phases write a receipt inside the fixture binding
the preceding saved project and report. Later phases reject changed helper,
source, media, ground truth or saved-project bytes.

## Portable browser check

Use an explicitly supplied existing Chromium binary and the installed Playwright
driver. No download is performed. The evidence directory must be new.

```sh
NODE_PATH=/absolute/browser-driver/node_modules \
node test_fcpxml_native_browser.cjs \
  --python /absolute/verification-python \
  --browser /absolute/chrome \
  --evidence /absolute/new-browser-evidence
```

This runs the same three phase coordinators and the same shipped UI script.
It checks actual ProRes export/download bytes and independently decodes their
picture and PCM through FFmpeg. It explicitly excludes WKWebView and native
ProRes video-element playback. Every report sets `native_certified` to `false`;
the browser wrapper additionally records
`native_prores_playback_certified: false`. Portable success never substitutes for
the native Mac phases.

## Scope of a passing result

The fixture `File` and `DataTransfer` exercise the actual shipped file-input
handler. They do not assert a physical open panel. The helper's explicit owned
download destination does not assert a physical save panel. No changes are made
to product code to admit the fixture or bypass the normal review/apply controls.

The ProRes video element belongs to the acceptance script. CINEMATICUM offers
ProRes as a download; the test does not claim a new product ProRes transport.
Muted playback proves actual native decode and an advancing movie clock. The
independent PCM decode proves the sample stream, without claiming physical
speaker output or audible monitoring.

The coordinator serves the frozen checkout. Installed-bundle file parity,
canonical application launch, production footage, long-session behavior and an
external Final Cut Pro import/render remain separate gates. Apple DTD validation
and successful public XML reimport do not certify an external editor.

# Separate lens native-acceptance handoff

The feature handoff remains byte-for-byte frozen. This additional patch contains
only four new acceptance/documentation files and applies after the feature patch.
It does not edit production code, source version, installed runtimes or the0.12
release. Clean replay applied all four paths and verified every final byte hash.

## Exact artifacts

- `lens-native-acceptance.patch`, SHA-256
  `5e2f4da1b519c382f88f502bd1b0027b91641e72d0106e15ec5fffa0bf04e0d9`.
- `changed-paths.json`: exact SHA-256 and sizes for all four new source files.
- `tested-source-inventory.json`: exact runtime/web/helper-source inventory used
  by the successful portable phase run. Regenerate the expected inventory on
  the final integrated0.13 freeze; this older candidate inventory must not be
  falsely reused to certify a changed0.13 source.
- `native-harness-evidence.tar.gz` and `evidence-files.json`:89 retained evidence
  artifacts, including the failed attempt, actual movie download, source-bound
  snapshots, PNGs, codec controls and exact executed JavaScript.
- `lensfun-pinned-test-fixture.tar.gz`: unmodified pinned Olympus XML, its source
  record, unmodified upstreamCC-BY-SA3.0 license and attribution. Test-only;
  do not include in RUNTIME_FILES or silently install a database.
- `artifact-hashes.json`: exact archive and manifest hashes.

The native helper binary is passed explicitly and hashed during prepare; author
and render refuse a different binary. Use the already built SmokeTest.swift
helper with expected_download_count support, as directed by root. The coordinator
also inventories the current SmokeTest.swift source. It does not infer a compiler
provenance relationship; root owns the independently verified helper binary.

## Collected verification

The identical native phase script and coordinator passed through the existing
explicit Chromium adapter, with **native_certified:false** throughout:

| Phase | Checks | Seconds |
|---|---:|---:|
| Prepare |10/10|0.444|
| Author |41/41|6.933|
| Render |24/24|4.241|

Each phase was below18seconds and the whole portable run took12.628seconds.
The browser binary hash was unchanged. Author exercised the actual file onchange,
all four fisheye pictures, exact upstream profile apply/undo/redo/save/reopen and
independent decoded-alpha pixels. Render used the shipped H.264 export/player,
completed the actual download, checked all source/export/download hashes and
matched all eight decoded movie frames to the separate lossless+codec control.

A separate actual ProRes backend check passed4/4 in3.342seconds: eight decoded
frames, exact independently encoded picture-control equality, unchanged source
bytes and export receipt equality. This proves the ProRes control calculation;
it does not prove the macOS native decoder. Actual nativeMac run is still pending.

The first portable run's prepare/author passed, but render's coordinator required
a fresh render callback even when the application correctly reused a cached PNG.
The failure is retained. The corrected coordinator preserves a hash-bound map of
previously verified render snapshots across phases, requires its unchanged
identity and a current completed cached receipt/PNG hash, and then compares the
independent pixels. Product caching was not removed or changed.

## Required fixture and CI

Exact XML path in the shared workspace:
`/workspace/scratch/091f394ee5df/lensfun-reference/slr-olympus.xml`.
Official pinned URL:
https://raw.githubusercontent.com/lensfun/lensfun/9e6deafe100a7c6f7ce019624bb8c4da20bf7c29/data/db/slr-olympus.xml
Size116,602bytes; SHA-256
`f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615`.

The source patch adds no package/runtime installation. CI must supply the existing
verification Python, FFmpeg/FFprobe, Node/Playwright and H.264-capable browser, and
provision this exact XML outside the application bundle. Hash-check it before use.
The new portable command, run from scripts/studio, is:

```sh
NODE_PATH=/absolute/browser-driver/node_modules node test_lens_models_native_browser.cjs --python /absolute/verification-python --browser /absolute/chrome --profile /absolute/slr-olympus.xml --evidence /absolute/new-phase-evidence
```

## Mac execution after final source freeze

Full instructions and explicit scope are in `scripts/studio/LENS_NATIVE_ACCEPTANCE.md`.
From scripts/studio, create one parent evidence directory, record the expected
source inventory after all0.13 integration changes, then invoke each phase
separately. Use physical absolute paths (for example /private/tmp on Mac), not a
symlinked ancestor. Fixture and per-phase output paths must not already exist.

```sh
python -B -c 'from test_lens_models_macos import source_inventory,write_json; write_json("/absolute/acceptance/source-inventory.json",source_inventory())'
python -B test_lens_models_macos.py --binary /absolute/native-helper --operation prepare --profile /absolute/slr-olympus.xml --delivery prores --fixture-workspace /absolute/acceptance/fixture --output /absolute/acceptance/prepare --expected-sources /absolute/acceptance/source-inventory.json
python -B test_lens_models_macos.py --binary /absolute/native-helper --operation author --delivery prores --fixture-workspace /absolute/acceptance/fixture --output /absolute/acceptance/author --expected-sources /absolute/acceptance/source-inventory.json
python -B test_lens_models_macos.py --binary /absolute/native-helper --operation render --delivery prores --fixture-workspace /absolute/acceptance/fixture --output /absolute/acceptance/render --expected-sources /absolute/acceptance/source-inventory.json
```

Default native delivery is ProRes. Its download is initiated through the shipped
export/download controls. Because the editor offers ProRes as a download rather
than preview transport, playback is clearly labeled as a separate test-owned
native video-element decode/clock probe of that exact export. No product ProRes
transport claim is made. If native H.264 works, --delivery h264 for all three
phases exercises the ordinary editor player instead. Delivery cannot change
mid-fixture.

The XML uses a test-owned File/DataTransfer delivered to the real file-input
change handler. No physical open-panel assertion is made. Download uses the
existing helper's explicit owned test directory; no physical save-panel assertion
is made. Installed-app/runtime identity and launcher, production lens-footage
accuracy, full-suite freeze and release publication remain separate root gates.

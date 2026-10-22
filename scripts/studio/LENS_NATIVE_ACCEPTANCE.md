# Phased Lensfun/fisheye native acceptance

`test_lens_models_macos.py` runs three separately bounded operations: `prepare`,
`author`, and `render`. Each phase owns and closes its server, helper process and
jobs, requires a new evidence directory, and must finish within 18 seconds. A UI
phase gives the existing `macos/SmokeTest.swift` binary at most 14 seconds. It
requires the helper with explicit `expected_download_count` completion support;
the helper is recorded by its actual binary SHA-256 and cannot change between
phases.

This is acceptance code. It does not modify a production runtime, install an
engine or access a user's project. Actual macOS WKWebView execution is required
for `native_certified`; Chromium reports that field as false.

## What each phase proves

| Phase | Actual operations and independent checks |
|---|---|
| `prepare` | Creates fresh owned project and sentinel, independently generated eight-frame lossless RGBA media, exact upstream XML and source truth; decodes the fixture and verifies every source byte against the independent input. No preauthored compositor graph is created. |
| `author` | Adds the clip from the bin, adds the lens node, selects all four fisheye models and collects real paused PNGs; reads the exact XML through a File/DataTransfer and the shipped file-input onchange; selects/applies the 7mm PTLens calibration; performs one undo and redo, saves, switches projects and reopens. Python verifies saved data, original media, six actual pictures against the independent physical-mm/ray and alpha oracle, and exact before/after-save pixels. |
| `render` | Reopens the persisted graph, verifies a real paused picture, uses the actual export control and download link, waits for the exact completed download, verifies source/export/download hashes, decodes every movie frame, and checks playback. A separate lossless-picture and delivery-codec control checks all exported frames. |

The profile file is a **test-owned `File`** passed through the real input event.
The physical macOS file-open panel is not asserted. Downloads use the native
helper's explicit owned test directory; the physical save panel is not asserted.

The default native delivery is **ProRes**. The shipped editor exposes ProRes as
a download and does not switch its transport to that movie. The harness checks
the exact ProRes export with a separate, explicitly labeled test-owned native
video element. This establishes native decoding/clock advancement of the actual
delivered movie; it does not claim a new product ProRes transport. For a native
runtime with working H.264, `--delivery h264` instead exercises the shipped editor
player after the ordinary H.264 export. The delivery choice is fixed at prepare
and must remain the same across all phases.

Each phase records exact runtime/web/acceptance source identities, the actual
helper binary, executed JavaScript, saved project and every retained evidence
artifact. A later phase refuses changed source, helper, delivery, original media,
ground truth or prior saved project. Cached paused images are accepted only when
the preceding passed phase retained the exact render snapshot under a verified
hash and the current cache receipt and PNG hash agree. The cache is not removed,
disabled or replaced for the test. Repeated or failed attempts remain available;
a new complete fixture is required if an attempted edit changed the saved state.

## Exact external fixture

Supply the unmodified Lensfun XML from:

```
https://raw.githubusercontent.com/lensfun/lensfun/9e6deafe100a7c6f7ce019624bb8c4da20bf7c29/data/db/slr-olympus.xml
```

Required SHA-256:

```
f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615
```

The file is 116,602 bytes. It contains 106 supported exact radial calibration
samples. The selected record is Olympus Zuiko Digital ED 7–14mm f/4.0 at 7mm,
crop 2, 4:3 calibration aspect, PTLens `[-0.013136, 0.015797, 0.0]`. The rendered
signal is synthetic ENGINE TEST media, not a physical-lens accuracy claim.

The database is licensed by the Lensfun project and its contributors under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Retain attribution
and the upstream license with any fixture or derived evidence distribution:

```
https://raw.githubusercontent.com/lensfun/lensfun/9e6deafe100a7c6f7ce019624bb8c4da20bf7c29/data/COPYING.CC_BY-SA_3.0
```

License SHA-256:
`3f941b3b89cf7b8370ceb83cc76d2120d471b58735d8ca60238a751a48d7f72f`.
The helper source does not bundle the database or download it at runtime.

## macOS execution

Use the existing verification Python, installed FFmpeg/FFprobe and actual native
helper. All paths below are explicit placeholders. Use a real path without a
symlinked ancestor, such as `/private/tmp/...` rather than macOS's `/tmp` alias.
The fixture and phase output paths must not already exist. Do not use a user's
film/project directory for these test destinations.

From `scripts/studio`, record the exact source inventory **after integration and
the final source freeze**:

```sh
python -B -c 'from test_lens_models_macos import source_inventory,write_json; write_json("/absolute/acceptance/source-inventory.json",source_inventory())'
```

Prepare:

```sh
python -B test_lens_models_macos.py \
  --binary /absolute/native-helper \
  --operation prepare \
  --profile /absolute/slr-olympus.xml \
  --delivery prores \
  --fixture-workspace /absolute/acceptance/fixture \
  --output /absolute/acceptance/prepare \
  --expected-sources /absolute/acceptance/source-inventory.json
```

Then run `author` and `render` in separate foreground invocations, preserving
the same fixture, helper, source inventory and delivery:

```sh
python -B test_lens_models_macos.py \
  --binary /absolute/native-helper \
  --operation author \
  --delivery prores \
  --fixture-workspace /absolute/acceptance/fixture \
  --output /absolute/acceptance/author \
  --expected-sources /absolute/acceptance/source-inventory.json

python -B test_lens_models_macos.py \
  --binary /absolute/native-helper \
  --operation render \
  --delivery prores \
  --fixture-workspace /absolute/acceptance/fixture \
  --output /absolute/acceptance/render \
  --expected-sources /absolute/acceptance/source-inventory.json
```

Reports are `ENGINE_TEST_lens_models_report.json` in each output. Read both
`passed` and `native_certified`; verify every check, the source/helper identities,
prior-phase linkage, completed download count and artifact inventory. Native
prepare intentionally has `native_certified: false` because it does not open a
native browser. Actual UI phases can claim native certification only on macOS.

The complete installed-app/runtime identity, launcher, final frozen full suite
and release publication remain separate gates. This coordinator serves the
current source checkout; it does not infer installed-app parity from its own
native UI pass.

## Chromium/CI check of the same phase script

`test_lens_models_native_browser.cjs` reuses the existing explicit Chromium helper
in `test_retime_browser.cjs`. It supplies the exact same native script and Python
coordinator, with H.264 delivery, and never claims macOS certification. The
browser must have an actual H.264 decoder; retain the already provisioned Chrome
for Testing/Playwright runtime and its pinned installation workflow.

```sh
NODE_PATH=/absolute/browser-driver/node_modules \
node test_lens_models_native_browser.cjs \
  --python /absolute/verification-python \
  --browser /absolute/chrome \
  --profile /absolute/slr-olympus.xml \
  --evidence /absolute/new-lens-phase-evidence
```

CI must provision the exact XML outside the application bundle and verify its
SHA-256 before this command. It needs FFmpeg/FFprobe, the established verification
Python/runtime, Node, Playwright and the existing H.264-capable browser. No
additional shared engine/runtime installation is required. The driver saves a
source inventory and phase summary, preserves the complete owned fixture and
phase artifacts, and checks the browser binary hash before/after.

Keep phase reports and raw media in the evidence store. If retaining only text
reports in Git, include hashes and byte sizes of the actual PNG/movie artifacts
and preserve the original raw evidence outside the tracked source tree. Never
replace a failed native run with a Chromium success.

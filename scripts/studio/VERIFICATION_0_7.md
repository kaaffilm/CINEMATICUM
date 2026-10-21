# CINEMATICUM Studio 0.7.0 — executed verification

Recorded on 2026-10-21. **The native ARM64 application was built, installed and opened successfully.** All 21 planned native workflow stages passed. The results below record executed checks on the identified source. They do not establish complete parity with the 33 reference systems in the [capability audit](CAPABILITY_AUDIT.md).

## Source identity and verification

| Item | Recorded checkpoint |
| --- | --- |
| Runtime under test | [`b1fd392d9434614f5a6e4d7f79bf5b2aa44af6b3`](https://github.com/kaaffilm/CINEMATICUM/commit/b1fd392d9434614f5a6e4d7f79bf5b2aa44af6b3) |
| Publication | Existing [draft PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162) |
| Source manifest | `source-integrity.json`: 111 entries; SHA-256 `16d4f0dcf2ee8de52519b82f7ce35f580960d6d247e713680f14c4793b72d6fe` |
| Studio verification | [Run 39582070296](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39582070296): passed on the runtime commit above |
| Additional workflows | Eleven other workflows reported green at this checkpoint |
| Public auditor | [Run 39582070266](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39582070266): passed on b1fd392; all 13 workflows succeeded |
| Calibrated lens | 29 native checks passed; independent numerical pixels, exact lossless-frame identity, exact complete-sequence codec control |
| Canonical 0.7 application | Installed and opened: version 0.7.0 / build 7; 32 bundled runtime files verified; both existing projects preserved |

All 111 manifest entries and the manifest itself were verified during pinned transfer to the isolated Mac worktree. All 32 installed runtime files matched tested source bytes, and seven affected assets served by the running app matched those files. This subsequent report is intentionally outside the runtime manifest. Source publication remains on draft PR #162; main was not merged.

## Executed environments

Native acceptance used the user's **Apple M3 Mac with 16 GiB memory**, FFmpeg **8.1.1**, and actual headless **Blender 5.2.2 LTS**. Interface tests used the shipped editor in the native WKWebView helper and disposable ENGINE TEST projects.

The separate imaging runtime used **Python 3.13.13**, **NumPy 2.3.5**, **OpenColorIO 2.6.0**, **rawpy 0.27.1 / LibRaw 0.22.1**, and **OpenEXR 3.4.15**. Its builtin studio configuration was `studio-config-v5.0.0_aces-v2.1_ocio-v2.6`.

The GitHub Studio workflow used Ubuntu, Python 3.11, FFmpeg, OpenTimelineIO 0.18.1 and the four pinned imaging dependencies. It completed **329 tests in 76.784 seconds: 328 passed and one optional genuine-RAW fixture test skipped**, followed by JavaScript syntax checks. The fixture skip is explicit; the separate native RAW workflow below executed actual camera data.

## Native authoring and rendered-output acceptance

| Workflow | Executed behavior and independent evidence | Result |
| --- | --- | --- |
| Slip source | Shipped trim controls, one undo/redo, saved edit and actual movie export; independent binary source-frame patches and moving-marker positions | Passed: all 24/24 exported frame IDs correct; maximum marker error 0 pixels |
| Slide shot | Same acceptance through the slide operation, including neighboring cuts and preserved outer endpoints | Passed: 24/24 correct frame IDs; 0-pixel marker error |
| Roll outgoing cut | Same acceptance through the outgoing-cut roll operation | Passed: 24/24 correct frame IDs; 0-pixel marker error |
| Trim guards | Actual source-handle limits, zero-offset no-op and locked-track controls | 7 checks passed |
| Independent compositor media | Native source controls and history, range rejection, masked merge, actual paused frame, split/trim preservation, saved graph, decoded export and native playback | 24 checks passed |
| Mesh authoring | Convert, vertex move, face extrusion, subdivision, deletion, Mirror, Bevel, Subdivision Surface, stack reorder, disable, enable and apply through native controls and actual geometry jobs | All 12 native stages passed |
| Mesh backend replay | Actual engine evaluation, editable cage/live modifiers, retained Blender source, independent reopened geometry, rendered pixels and invalid-evaluation rejection | 16 checks passed using Blender 5.2.2 LTS |
| OCIO development | Actual source/input/view/exposure controls, admitted output, PNG/EXR/receipt downloads, saved clip, independent sRGB→Rec.709 expectation, paused-frame/export comparison | 18 checks passed |
| HDR bracket merge | Explicit bracket selection and shutter times, actual radiance result above one, retained float output and normal preview/export | 19 checks passed |
| Genuine camera RAW | Actual native FileList, preserved sensor original, executed demosaic/WB/highlight/half-size settings, output downloads and media admission, saved clip and real preview/export | 18 checks passed |
| Calibrated lens | Actual intrinsics and coefficients, undo/redo, independent distortion/inverse and alpha pixels, exact lossless frame, exact independently encoded sequence, saved graph and native playback | 29 checks passed in 3.424 seconds |

These small, controlled media and geometry fixtures verify the stated operations. They are not a production-scale performance or arbitrary-input compatibility benchmark. Synthetic fixtures are identified as ENGINE TEST. The genuine RAW fixture is separately identified in the imaging evidence; no test media are presented as a finished film.

### Calibrated lens and delivery identity

The final native workflow executed both distortion directions using unequal focal scales, a shifted principal point, radial coefficients through k3 and tangential coefficients p1/p2. The source contains moving color/alpha ramps and hidden color in transparent pixels. The independent oracle uses a separate Newton inverse and premultiplied bilinear evaluation.

| Direction | Mean RGB error in 8-bit code values | Maximum RGB error |
| --- | --- | --- |
| Undistort | 0.3480602560 | 1.5692477930 |
| Distort | 0.3681470044 | 1.7273950479 |

A native failure first exposed FFmpeg 8 alpha-mode negotiation: the old weight images could be premultiplied twice. Weight PNGs now store white RGB and the fraction in alpha, then explicitly premultiply once. Both numeric weights and alpha metadata agree across filter inputs. The pure independent pixel test passed on the Mac after this correction with its unchanged 2.2-level maximum-error threshold. Paused-frame cache pipeline version advanced to 10.

The original flat PNG-versus-H.264 threshold was separately invalid for this high-frequency moving fixture. Even an isolated encode of the identical paused pixels exceeded it. A complete lossless RGB sequence establishes the correct control for temporal coding:

- The actual paused frame 6 is byte-identical to frame 6 of the complete lossless movie graph. Both RGB SHA-256 values are `15b18c1c26cee4fc2a484abb119d393656bdf39e0bf88bf8727576702746f00b`.
- A separate H.264 encode of that entire RGB sequence produces decoded pixels byte-identical to the actual exported movie across all 12 frames. Both decoded-sequence SHA-256 values are `fac20887f724bbbcd556b760a5e124ea6f9e9054fbf033fb6aaa33a11adcf6c1`.
- The paused-to-delivery mean RGB difference remains recorded as **5.1129398148**. The same difference occurs in the control; exported-versus-control difference is **0**. No numerical lens threshold was relaxed.

Actual frame-render snapshots bind the requested calibration, project, frame and cache identity. The retained report includes both movies, PNGs, hashes and native playback. The added portable regression also passes in CI. Nonidentity calibrated processing remains bounded to two lens nodes and 2,073,600 canvas pixels; identity processing does not require resampling.

### Imaging precision and the corrected preview bottleneck

The optional worker executes real OCIO source-to-linear and display/view processors, rawpy/LibRaw camera development, and known-response bracket reconstruction. Each successful job retains `linear.exr`, `display.png` and `receipt.json`, binding source identities, recipe, configuration and actual runtime versions. Float EXR tests preserve negative values, highlights above one and premultiplied alpha. The current movie compositor and delivery remain SDR.

The camera fixture is Nikon D3S `iss030e122639.NEF`, 10,656,312 bytes, SHA-256 `5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`; its immutable upstream source and separate fixture boundaries are recorded in [color-science research](research/color-science.md).

Native RAW acceptance exposed slow per-pixel transfer evaluation on the full-resolution developed display image. A bounded UNORM16 lookup now handles only admitted imaging sRGB PNGs with unchanged Rec.709/D65 primaries/white and no creative LUT. Exhaustive measured tests cover all 65,536 values independently in every RGB channel: maximum transfer error is half one 16-bit code, and alpha is exact. General float, gamut, log, adaptation and creative-LUT paths retain their float implementation.

The local FFmpeg 6.1.1 benchmark of the same 2142×1422 RAW-derived PNG through a 160×90 timeline frame improved from **7.802 seconds to 0.605 seconds**. Maximum final RGB difference was 1/255; mean difference was 0.0048/255. These timings are local measurements. The subsequent native RAW acceptance passed without relaxing its independent pixel oracle or 2200 ms preview wait. The color suite contains 24 passing tests, including the exhaustive lookup and float-preservation regressions.

## Optional imaging installer acceptance

A **fresh isolated imaging installation passed in 4.376 seconds** on the Mac. It installed the four exact Apple Silicon CPython 3.13 wheels from a verified local wheel cache and the checked lock, verified installed package identities, constructed and executed the actual OCIO CPU display processor, loaded LibRaw, and round-tripped a float EXR containing negative and above-one values.

The installer builds a venv at its permanent versioned path and publishes the stable link only after verification. The default stable interpreter is:

```text
~/Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python
```

`install_imaging.py --check` verifies an existing healthy environment without replacing it. The installer tests additionally cover failed-build cleanup, unrelated-path preservation, idempotence and a destination created during installation. The successful fresh-install proof used the separate evidence destination listed below. The fresh-install timing excludes the earlier wheel downloads. The canonical app subsequently discovered the stable imaging runtime automatically and reported all three operations available.

## Evidence locations and reproducibility

Native evidence is retained beneath this pinned execution workspace on the Mac:

```text
/Users/midiakiasat/.midia-ai/gateway-live/workspaces/auto-731aef864221792e4f581ef074d1b92c
```

| Relative evidence directory | Producer and selector |
| --- | --- |
| `.studio-test/v7-trim-ui-proof` | `test_trim_ui_macos.py --stage slip`, `slide`, `roll` |
| `.studio-test/v7-trim-ui-proof-final` | `test_trim_ui_macos.py --stage guards` |
| `.studio-test/v7-multi-source-ui-proof` | `test_multi_source_ui_macos.py` |
| `.studio-test/v7-modeling-ui-proof` | `test_mesh_modeling_ui_macos.py`, all 12 ordered stages |
| `.studio-test/v7-modeling-engine-proof` | `test_scene_modeling_blender.py`, ordered backend stages |
| `.studio-test/v7-imaging-ui-proof` | `test_imaging_ui_macos.py --operation ocio`, `hdr_merge`, `raw`; RAW requires the real fixture |
| `.studio-test/v7-installer-proof/runtime` | Fresh `install_imaging.py` destination |
| `.studio-test/v7-lens-ui-proof-complete` | Final `test_lens_ui_macos.py`: all 29 checks passed |
| `.studio-test/v7-install-proof` | Fresh project/checkout baseline, verified installation and running-app checks |

Native UI commands require the compiled `macos/SmokeTest.swift` helper supplied with `--binary`, and their own evidence path supplied with `--output`. Stage order is defined in each harness. Reports retain actual saved project state and the relevant decoded media, receipts, screenshots or reopened-engine results; a harness file's presence is not execution evidence.

The pinned runtime root is [`scripts/studio` at b1fd392](https://github.com/kaaffilm/CINEMATICUM/tree/b1fd392d9434614f5a6e4d7f79bf5b2aa44af6b3/scripts/studio). Its [`research` directory](https://github.com/kaaffilm/CINEMATICUM/tree/b1fd392d9434614f5a6e4d7f79bf5b2aa44af6b3/scripts/studio/research) contains eight subsystem investigations with upstream commit/file identities. Those source pins identify inspected implementations; installed engine versions are recorded independently. Public proprietary interfaces were examined, and no complete proprietary codebase or entire upstream application was reverse engineered.

## Installed application and preservation

The native ARM64 build completed in **8.352 seconds**, without compiler warnings. The installed bundle is **0.7.0 / build 7**, targets `arm64-apple-macos12.0`, and includes a 283,603-byte native icon.

```text
/Users/midiakiasat/Applications/CINEMATICUM Studio.app
```

The preceding canonical bundle was archived with byte and permission verification before replacement. There is one canonical CINEMATICUM `.app` in the user's Applications directory and seven verified recovery ZIPs in `.CINEMATICUM-Backups.noindex`.

After the app opened, its own child service reported **`CINEMATICUM/0.7.0 Python/3.14.3`**. The running service independently reported FFmpeg, Blender, H.264, ProRes, the node compositor, point tracking, input color processing, camera import, mesh authoring and the optional imaging runtime available. Imaging reported Python 3.13.13 and the exact versions listed above, with no missing dependencies and OCIO, RAW and HDR-merge operations enabled.

All **32 installed runtime files** matched the pinned source. Seven JavaScript/HTML assets fetched from the running app matched their installed bytes. Both pre-existing projects remained present; all **four project/inventory JSON files were byte-identical** before installation and after launch. The owner checkout stayed at `5003627c56413ce1aff1df324668fc11792ea58a`, with the same two working-status entries and identical status fingerprint. No owner checkout reset, film source replacement or issuance-record edit was performed.

The actual modeling implementation and Blender replay harness were byte-identical between the earlier 16 backend checks and the final source; all 12 updated mesh UI stages were separately executed. Native mesh and imaging screenshots were visually reviewed. All fixture work used isolated test projects rather than the two production projects.

The app is left running. Local Python, FFmpeg and Blender remain dependencies; this is an unsigned, unnotarized application build, not a self-contained distribution.

## Other defects corrected and public verification

- Source duration now uses valid integer `duration_ts × time_base` metadata before rounded decimal duration. A genuine 80-frame, 24 fps fixture previously exposed a lost final trim handle; its +48-frame slip now delivers source frames 72–79 exactly.
- Rejected lens edits restore the inspector's committed value and preserve valid undo/redo state.
- Job polling retains request ownership. A superseded response cannot replace a newer job; interrupted jobs and retry/cancel state recover visibly.
- The RAW display transfer bottleneck and the FFmpeg alpha issue are documented above, including measured numerical limits.
- The public auditor's anonymous GitHub metadata lookup failed with HTTP 403, including one retry. The runner now uses the same pinned public release asset URLs directly. Canonical/raw SHA checks, artifact identity and all five replay assertions remain intact. The exact historical 403 cause was not recoverable from its old error handler.

The repaired auditor passed the full unchanged verifier on [commit 4a3d9dd](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39581458028): `valid=true`, no errors, five replay commands, all public assets hash-verified, and extracted artifact SHA `f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192`. That run took approximately 182.283 seconds. The earlier Mac check was stopped at its bounded 15-second budget and is not counted as a pass. The final source checkpoint [b1fd392 also passed the complete auditor](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39582070266) in approximately 181.679 seconds, without a retry. All 13 workflows were successful on this final source. Runner SHA-256 is `4a3d73c1e8a2fd7f8c08f8e00625628d5db745a2c0ef93f910077bfad04e672e`; receipt SHA-256 is `5dd43d9b490c0ee994d5b1870b7bb8e29e1e52fafb6d734219c19d840b6b096a`.

## Remaining capability boundaries

This upgrade implements bounded editorial trim modes, independently timed compositor sources, editable mesh topology/live modifiers and actual OCIO/RAW/HDR still processing within CINEMATICUM's own authoring controls. The [capability ledger](capabilities.json) and [audit](CAPABILITY_AUDIT.md) retain the unresolved systems.

Major remaining work includes nested sequences and multicam; a float/color-managed movie compositor, HDR mastering and calibrated monitoring; deep/arbitrary-channel compositing and advanced roto/paint; full vector motion design; UV/material graphs, rigs and simulation; SfM/MVS reconstruction; optical prescription, spectral and differentiable rendering; neural segmentation/tracking/camera conditioning; advanced audio and production-scale caching/collaboration. No paid provider integration or successful neural inference is claimed by this verification report.

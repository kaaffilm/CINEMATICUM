# CINEMATICUM Studio 0.6.0 — executed verification

Recorded on 2026-10-21. **The native ARM64 application was built, installed and opened successfully.** This report records executed source, media, native-interface and installation checks. It does not certify complete parity with the 33 systems in the [capability audit](CAPABILITY_AUDIT.md).

## Source identity

- Final runtime source: [`41008a3d7ba9be4b60a45d7fc50fa45e6395b71c`](https://github.com/kaaffilm/CINEMATICUM/commit/41008a3d7ba9be4b60a45d7fc50fa45e6395b71c).
- Initial 0.6 implementation: [`d6f1ba6ec1e57b372e2ff76448fb2554293a6e33`](https://github.com/kaaffilm/CINEMATICUM/commit/d6f1ba6ec1e57b372e2ff76448fb2554293a6e33).
- `source-integrity.json` SHA-256: `0b7faae1774a10398e5be579a0a1e7194da6ddbb8df1b5b40a8d4f67e0d067a0`.
- All 83 manifest entries and the manifest itself were verified during pinned transfer. All **26 installed runtime files** were independently compared byte-for-byte with their tested source.
- This report is a subsequent documentation checkpoint and is intentionally outside that runtime manifest.

All source publication remains on [draft PR #162](https://github.com/kaaffilm/CINEMATICUM/pull/162). Main was not merged. The owner checkout HEAD remains `5003627c56413ce1aff1df324668fc11792ea58a`; its working changes were not reset.

## Automated verification

The final [Studio media verification workflow](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39569672837) passed on the final runtime commit: **238 tests in 75.872 seconds**, followed by successful JavaScript syntax checks. Coverage includes actual decoded video/PCM, real local HTTP, rational timing and split equivalence, independent OpenTimelineIO read/write, project validation, LUT pixels and transport regressions.

On the Mac, **71 targeted tests passed under Python 3.9.6**, including camera import, scene validation, color processing and all five installer/archive tests. FFmpeg was 8.1.1. The installed app subsequently started its own Python 3.14.3 service successfully.

Tests use explicitly named synthetic ENGINE TEST fixtures. The test media were never inserted into either existing production project, a film case or issuance records. Fixture speed and tiny image dimensions are not production performance benchmarks.

## Native interface acceptance

The actual shipped interface was loaded in a compiled WKWebView helper, with disposable project storage. The final camera, color and physical-authoring workflows ran at both the Mac's actual normal content size, **1440 × 815**, and the application's minimum content size, **1000 × 700**.

| Workflow | Actual operations and independent checks | Result |
| --- | --- | --- |
| Color pipeline | Native FileList import; malformed Cube rejection; project-owned SHA-256 table; nonzero per-channel domains; actual rendered PNG pixels; single undo/redo; preset binding and saved interpolation | 17 checks passed at each size; 1.853 s normal / 1.674 s minimum |
| Camera import | Binary fSpy and COLMAP text FileLists; duplicate-member rejection; read-only review; selection of pose 93; single undo/redo; camera-key replacement; exact saved calibration/provenance; unrelated geometry, lighting and settings preserved | 12 checks passed at each size; 1.581 s normal / 0.726 s minimum |
| Physical authoring | Material presets and emission; sensor/focal controls; focus/f-stop/aperture; calibrated framing; animated focus/roll; ray limits; undo/redo and independent saved-project inspection | 10 checks passed at each size; 0.940 s normal / 0.684 s minimum |
| Existing editing/export | Fractional trim, reverse/retime, track/mixer state, animation, curve/polygon gestures, decoded waveform, three scopes, exact paused frame, actual H.264 export and native playback | 30 checks passed; 2.967 s |

The color and camera tests also check actual viewport bounds and `elementFromPoint` hits for their action buttons. Scrolling the body leaves the footer in place; closed dialogs leave no visible layout rectangle. These checks caught a real issue that DOM-only clicks had missed.

The physical workflow verifies the toolbar, Samples, Render button and inspector fields through actual bounds and hit tests before interaction. At 1000 × 700:

- The 3D viewport measures **590 × 219 pixels**.
- The inspector has **122 pixels** of independently scrollable height.
- The render footer ends at y=530; the film timeline begins at y=553.
- Camera selection reveals its inspector heading, lower calibration controls remain reachable, and normal field edits preserve inspector scroll.
- Horizontal toolbar scrolling makes all tools reachable while retaining the render action.

These are measured layout results, not only CSS assertions. Native screenshots were also visually inspected. The final interface fixes changed no camera projection, color or rendering backend code.

To reproduce minimum-size acceptance after compiling `macos/SmokeTest.swift`, set `CINEMATICUM_SMOKE_WIDTH=1000` and `CINEMATICUM_SMOKE_HEIGHT=700`, then run each UI acceptance command with that helper:

```bash
CINEMATICUM_SMOKE_WIDTH=1000 CINEMATICUM_SMOKE_HEIGHT=700 \
  python3 scripts/studio/test_color_pipeline_ui_macos.py \
  --binary /path/to/cinematicum-webkit-smoke --output /path/to/new-color-evidence

CINEMATICUM_SMOKE_WIDTH=1000 CINEMATICUM_SMOKE_HEIGHT=700 \
  python3 scripts/studio/test_camera_import_ui_macos.py \
  --binary /path/to/cinematicum-webkit-smoke --output /path/to/new-camera-evidence

CINEMATICUM_SMOKE_WIDTH=1000 CINEMATICUM_SMOKE_HEIGHT=700 \
  python3 scripts/studio/test_physical_scene_ui_macos.py \
  --binary /path/to/cinematicum-webkit-smoke --output /path/to/new-physical-evidence
```

The viewport environment variables are accepted only by the standalone test helper. The production app is not given test globals or a test automation endpoint.

## Rendered camera and physical evidence

These checks executed the installed **Blender 5.2.2 LTS** in headless mode, rendered real output and reopened the retained `.blend` in a separate process. Inspecting a generated recipe alone was not accepted as proof.

### Imported camera projection

Three source-model fixtures compare independent source equations with Blender's `world_to_camera_view` on reopened cameras:

| Source case | Image size | Maximum projection error |
| --- | --- | --- |
| fSpy landscape | 192 × 128 | 0.000025635 pixels |
| fSpy portrait | 128 × 192 | 0.000037079 pixels |
| COLMAP shifted principal point and unequal focal lengths | 192 × 128 | 0.000009156 pixels |

All three passed the unchanged 0.002-pixel acceptance tolerance. Each case also verified token rejection for unauthorized mutation and that importing a candidate alone did not change the project. The small dimensions and exact fixtures verify coordinate handling; they are not a calibration-accuracy claim for arbitrary photographs.

### Physical material, focus and light paths

The physical rendering workflow passed **11 checks** in 2.499 seconds:

- Actual Principled transmission, IOR and scene-linear emission in the reopened scene.
- Actual sensor/lens/focus/aperture settings at two animated frames.
- Actual Cycles bounce limits, seed and denoising state.
- Two real encoded movie frames, retained recipe and independently reopened Blender source.
- Roll, principal shifts and unequal focal scales agreeing with the projection contract; maximum error **0.000024150 pixels**.
- Separate sharp and defocused PNG renders. **6,623 pixels** exceeded a 0.05 change in their mean-RGB value; the mean absolute difference in these normalized per-pixel averages was **0.171907**. The fixture's edge-energy measure fell from **0.171769** to **0.115095**.

The existing scene-animation replay passed **8 checks**, including nine decoded movie frames and five independently evaluated camera, light and object poses. Imported-mesh replay passed **14 checks**, including three actual frames at 24000/1001 and preserved vertices, topology, corner UVs, normals, materials, source hashes and animation.

The relevant backend files are unchanged between those executions and the final runtime checkpoint. Later changes corrected only acceptance tolerances and native layout/visibility.

## Color and editing pixel evidence

The native color fixture's decoded input center was RGB **[160, 80, 100]**. After the imported nonzero-domain Cube, the actual renderer PNG was **[64, 104, 149]**, agreeing with independent domain evaluation. The same result passed at both window sizes. Source transform, LUT and compositor ordering are also covered by the full suite.

The existing editing acceptance produced **eight distinct decoded video frames** and **32,000 stereo PCM samples**. The paused PNG and delivered frame had mean RGB absolute error **1.11769** in 8-bit values after H.264 encoding. Native WKWebView played that exported file. These results support the tested pipeline, not every unimplemented format or effect.

## Defects corrected during this upgrade

1. fSpy's image-extent convention needed different handling for portrait frames. Source projection and independent Blender replay now agree in both orientations.
2. Blender marks render pixel aspect as non-animatable. Imported unequal focal scales remain explicit static calibration; unsupported ratio animation rejects rather than producing a misleading retained scene.
3. FFmpeg's Cube handling was insufficient for nonzero input minima. The color compiler normalizes every channel's domain explicitly before evaluating a unit-domain render table.
4. A camera UI harness compared rounded inspector text at full stored precision. Display tolerances now reflect the two/four decimal places; exact saved-data checks and the independent projection threshold remain unchanged.
5. One portable camera test used exact equality across Python's math implementations. A one-ULP difference on Python 3.9 was corrected with a tight numerical assertion, without changing runtime math.
6. Color/camera actions and the 3D render footer could lie beyond clipped layout areas. Fixed action rows, scrollable content, responsive scene allocation and native hit tests now cover the minimum supported size.
7. Sibling backup `.app` bundles produced multiple installed application entries. The installer now verifies recoverable ZIP archives before replacement or retirement, preserving both file bytes and permissions. Failure-path tests retain the previous app even when install and rollback renames both fail.

## Installed application and preservation

The native build completed for **arm64-apple-macos12.0**, without compiler warnings. Installed version is **0.6.0 / build 6**, with a generated 283,603-byte native icon.

Canonical application:

```text
~/Applications/CINEMATICUM Studio.app
```

Installation archived the preceding canonical app and five recognized backup/rejected app bundles. There are **six verified ZIP archives**, no archive warnings and **one remaining CINEMATICUM .app bundle** in the Applications directory. The archives are retained in `~/Applications/.CINEMATICUM-Backups.noindex`.

After opening the installed app:

- Its own child service reported `CINEMATICUM/0.6.0 Python/3.14.3` on a loopback port.
- All **26 installed runtime files** matched tested source bytes.
- Four newly affected assets served by the running app matched source bytes.
- FFmpeg, Blender, H.264/ProRes, the node compositor, point tracking, input color processing and camera import were available.
- Both pre-existing projects remained present. All four project/inventory JSON files were byte-identical before installation and after launch.
- No authority objects, source shots or film issuance records were edited.

The app is left running. Local FFmpeg/Blender/Python remain required; this is not a signed or notarized self-contained distribution.

## Remaining capability boundaries

The [33-system audit](CAPABILITY_AUDIT.md), seven source-investigation documents and [machine-readable capability ledger](capabilities.json) distinguish source evidence, implemented operations and missing systems. They are focused subsystem investigations; proprietary source and entire upstream codebases were not reverse engineered.

Full parity remains incomplete. Major missing areas include multicam/nested editorial workflows; full OCIO/ACES display processing, HDR and RAW; multi-source/deep compositing and advanced roto/paint; a complete vector/motion-design system; mesh topology, rigs and simulation; SfM/MVS reconstruction; optical prescription/aberration tools; spectral or differentiable rendering; neural segmentation/tracking/camera conditioning; advanced audio and production-scale caching/collaboration.

The configured ComfyUI endpoint refused the connection during the final running-app check. No successful neural inference, model download or paid-provider execution is claimed. The earlier commercial-provider list is still an integration requirement, not an implemented feature catalogue.


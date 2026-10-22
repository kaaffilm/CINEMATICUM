# Lensfun and fisheye workflows — isolated next candidate

This change adds actual Lensfun-format radial correction and four explicit
fisheye projections to the existing calibrated-lens node. It is an isolated
candidate based on the frozen 0.12 source tree. It is not installed, included in
the completed 0.12 acceptance, or certified by that build's full-suite result.
The runtime version and frozen release integrity manifest are intentionally
unchanged until integration and release verification.

## Editor workflow

1. Select a picture clip, open **Composite**, and add **Calibrated lens**.
2. For a measured Brown calibration, retain **Brown calibration** and the
   existing `fx`, `fy`, `cx`, `cy`, `k1`, `k2`, `k3`, `p1`, `p2` controls.
   **Copy base scene camera intrinsics** and coefficient reset retain their
   previous behavior.
3. For an explicitly known fisheye projection, choose **Equidistant**,
   **Equisolid**, **Stereographic** or **Orthographic** and enter its normalized
   focal lengths and optical center. Choose **Correct to rectilinear** or
   **Reproduce source lens**. The same intrinsics define the source and target
   images; this is not an automatic focal-length estimator.
4. For a Lensfun calibration, choose **Read Lensfun XML**, select the actual
   local XML file, select an exact measured focal sample, review the capture
   crop factor, then select **Apply selected calibration**. The import itself
   only produces a reviewable list; application is a single undoable graph edit.
5. Save the project. Its typed graph contains the selected numeric calibration,
   source-file SHA-256, maker/model and exact focal length. Reopening and
   rendering do not depend on the original XML path, a network connection or a
   separately installed Lensfun database.

Use a complete, uncropped capture with square pixels and no letterboxing at the
lens node's input. Graph scaling/cropping performed before correction can change
the meaning of the calibration. Capture crop is a physical sensor convention;
changing it solely to bypass a bound is not a valid substitute for a matching
capture. The application does not invent missing physical calibration data.

## Supported calibration and coordinate conventions

Lensfun XML versions 1 and 2 are accepted. Supported radial records are `poly3`
(`k1`), `poly5` (`k1`, `k2`) and `ptlens` (`a`, `b`, `c`) on rectilinear lens
profiles. Calibration-specific crop/aspect values take precedence over the
lens defaults. Optical-center offsets follow Lensfun's half-short-edge units.
The importer selects an exact measured sample: it does not interpolate a zoom
lens or infer capture metadata.

Lensfun coefficients are not Brown coefficients. The implementation follows
Lensfun's focal-preserving polynomial normalization before evaluating radius:
for poly3, `d = 1 - k1` and the quadratic radial coefficient is `k1 / d^3`;
for PTLens, `d = 1 - a - b - c`, with linear, quadratic and cubic radial
coefficients `c / d^2`, `b / d^3`, `a / d^4`. Poly5 retains its quadratic and
quartic coefficients. This avoids treating Lensfun's older Hugin-normalized
polynomial as an unadjusted camera model.

For graph width `W` and height `H`, the calibration-coordinate scale is:

```
scale = 2 * calibration_crop * sqrt(calibration_aspect^2 + 1)
        / (capture_crop * sqrt(W^2 + H^2))
center_x_pixels = ((W - 1) + min(W - 1, H - 1) * center_x_offset) / 2
center_y_pixels = ((H - 1) + min(W - 1, H - 1) * center_y_offset) / 2
```

The image diagonal is therefore preserved when applying calibration to a
different aspect at the same sensor crop. These conventions were checked
against the upstream Lensfun modifier constructor and polynomial rescaling
implementation, not inferred from the XML field names alone.

For a unit focal length and ray angle `theta`, the supported fisheye radii are
`theta`, `2*sin(theta/2)`, `2*tan(theta/2)` and `sin(theta)` respectively.
Correction maps each rectilinear output ray into its fisheye source coordinate.
Reproduction uses the inverse projection to sample a rectilinear source.
Behind-plane or out-of-image samples become transparent. The orthographic
inverse is explicitly restricted to the front hemisphere, where it is unique.

Primary references:

- [Lensfun correction and projection definitions](https://lensfun.github.io/manual/latest/corrections.html)
- [Lensfun lens/calibration XML conventions](https://lensfun.github.io/manual/latest/el_lens.html)
- [Lensfun distortion model reference](https://lensfun.github.io/manual/latest/group__Lens.html)
- [Upstream modifier implementation](https://github.com/lensfun/lensfun/blob/master/libs/lensfun/modifier.cpp)
- [Upstream coordinate and polynomial implementation](https://github.com/lensfun/lensfun/blob/master/libs/lensfun/mod-coord.cpp)

## Validation and execution bounds

The existing Brown schema and its whole-image contraction bound of 0.45 remain
unchanged. Active Lensfun and fisheye models use the same two-node and
2,073,600-pixel graph bounds. Zero-coefficient Brown and Lensfun models are exact
identity operations and do not resample a larger canvas.

Lensfun inverse evaluation requires a conservative whole-image radial derivative
deviation of at most 0.8. Thus its radial derivative stays at least 0.2 over the
certified interval, and a bounded bisection has a unique admissible root. This
can refuse a usable lens profile more conservatively than Lensfun itself.
Capture crop must be at least the calibration crop; larger-field extrapolation
is rejected. A sample that exceeds the bound is refused explicitly at apply or
validation time.

XML is limited to 512 KiB, 16,000 elements, 512 lenses and 2,048 radial samples.
Only the conventional `lensfun-database.dtd` declaration is recognized and
removed. Internal subsets, entities and alternative external DTD references
are rejected; no DTD or remote resource is read. The guarded JSON import route
uses the existing localhost token, origin and host validation. The project
stores typed data, never a filesystem path, URL or executable expression.

The isolated map worker loads the owned `lens_geometry.py` sibling by its exact
file location when executed with `python -I`; it does not add the current
directory or arbitrary environment module paths. `install_macos.py` includes
this new runtime file for a future rebuilt application.

## Evidence and reproducibility

Evidence lives under `verification/0.13.0/lens-isolated-01/`. That directory name
is an evidence grouping for this next candidate, not a published version.

`test_lens_geometry.py` uses an independent physical-sensor-millimeter radial
oracle, a Newton inverse rather than the production bisection, and independently
constructed 3D rays for the fisheye comparison. It checks actual decoded movie
pixels, alpha, exact numeric map planes, import authorization, saved/reopened
typed profiles, browser/backend validation parity and unchanged Brown behavior.
Synthetic coefficients are labeled ENGINE TEST rather than physical lens
calibration. The original Brown test module is also run without weakening its
assertions.

The final combined gate passed **25/25 tests**, with no failures, errors or
skips, in 15.173 seconds (`focused-tests-04.log`). This includes actual 16-bit
FFV1 masters and 16-bit paused PNGs for PTLens and equisolid in both directions.
Each output retained more than 512 distinct red-channel values; every decoded
pixel matched the independent associated-color/alpha oracle within five
UNORM16 code values, and each paused image exactly matched its master frame.
Source media bytes were unchanged.

The actual browser workflow used the pinned upstream Olympus Lensfun file:

- Repository: [lensfun/lensfun](https://github.com/lensfun/lensfun)
- Commit: `9e6deafe100a7c6f7ce019624bb8c4da20bf7c29`
- Path: `data/db/slr-olympus.xml`
- Size: 116,602 bytes
- SHA-256: `f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615`
- [Exact fixture URL](https://raw.githubusercontent.com/lensfun/lensfun/9e6deafe100a7c6f7ce019624bb8c4da20bf7c29/data/db/slr-olympus.xml)

The parser returned 106 exact calibrations. At their own calibration crop, 103
passed the conservative derivative certificate and three were explicitly
refused. The applied sample was Olympus Zuiko Digital ED 7–14mm f/4.0 at 7mm,
crop 2, 4:3 calibration aspect, PTLens coefficients
`[-0.013136, 0.015797, 0.0]`. This is a real upstream measurement; the rendered
image is a synthetic numerical test signal, not a claimed photograph from that
physical lens. Upstream attribution and the database license accompany the
derived evidence in `upstream-notices/` below the evidence directory. No full
database is bundled into the application.

`browser-03/browser-report.json` records 30/30 coordinator checks and 13/13
actual UI checks in 15.38 seconds. Chromium selected all four fisheye models,
read the exact profile through the file input, selected/applied the sample,
performed undo/redo, saved, reloaded, exported eight H.264 frames and played the
actual export. Each paused picture matched the independent ray/alpha oracle;
the largest mean RGB error was 0.411 code values and the largest sampled error
was 1.787. Reopening preserved every decoded pixel. The exported movie matched
the separate lossless-frame/codec control across every frame.

Earlier failures are retained. The first HTTP fixture used an unsupported PPM
extension; it was replaced with a genuine PNG fixture. The first combined
regression revealed that isolated `python -I` could not import the new sibling;
the owned-file import fix restored the original worker tests. Browser attempt
01 encountered the shipped CSP's correct rejection of Playwright's
`waitForFunction` eval; the driver now polls by direct evaluation without
changing the CSP. Attempt 02 incorrectly required a preview URL to remain the
same across a save: the existing identity deliberately includes revision and
updated time. The replacement assertion proves full project equality except
those two save metadata fields and exact decoded pixel equality. The independent
review found an explicit `model:null` browser/backend validation mismatch;
the frontend now defaults only an absent model, and the parity regression
includes that malformed graph.

Run the focused tests from `scripts/studio` using the established verification
runtime and installed FFmpeg/FFprobe:

```sh
python -B -m unittest test_lens_geometry test_lens_compositor -v
```

For actual browser acceptance, provision the browser and Playwright explicitly,
set `NODE_PATH` to that existing driver, and pass absolute paths:

```sh
python -B test_lens_models_browser.py \
  --browser /absolute/path/to/chrome \
  --profile /absolute/path/to/slr-olympus.xml \
  --evidence /absolute/path/to/new-evidence-directory
```

The runner verifies the exact upstream profile hash, blocks browser requests
outside its owned loopback origin, uses a fresh temporary project, and retains
actual reports, screenshots, pixels and decoded media. It does not mock the
editor, install runtimes or claim native macOS acceptance.

## Remaining limits and release gates

- Exact measured radial samples only. No automatic EXIF/camera matching, focal
  interpolation, bundled database updater, ACM model, TCA, vignetting, crop
  records or Lensfun profiles requiring a projection change.
- Fisheye projections use static common intrinsics, front-hemisphere geometry
  and the current image extent. They do not implement spherical panoramas,
  arbitrary input/output projections, anamorphic/rational optics, automatic
  calibration, dynamic lens breathing or chromatic calibration.
- The current Float32 movie pipeline rejects compositor graphs. These lens
  nodes are available in the Standard 8-bit and 16-bit SDR pipelines; this
  change does not add lens graph support to scene-linear Float32 movies.
- Native WKWebView file-picker acceptance, native installed runtime verification,
  the complete suite on the final integrated source and release/documentation
  reconciliation remain required. Chromium evidence cannot certify these gates.
- Real production lens footage, lens-specific optical accuracy, maximum-size
  performance and calibrated output monitoring are not established by these
  small synthetic picture tests.

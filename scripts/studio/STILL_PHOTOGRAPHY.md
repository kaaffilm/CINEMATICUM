# HDR still photographs and planar panoramas

**Develop images** processes actual imported photographs through the existing
Imaging and Tracking runtimes. The still workflows measure bracket alignment,
fit a camera response when requested, replace detected moving regions with a
chosen reference exposure, and stitch connected views into a planar panorama.
Every completed job creates new media and preserves its original source files.

## Merge an exposure bracket

1. Import the photographs into the project's media bin, then open **Develop
   images** and choose **Merge exposure brackets**.
2. Select 2–16 bracket images and enter each shutter duration in **seconds**.
   For example, enter `0.008` for 1/125 second. Shutter times are explicit inputs;
   this workflow does not infer them from EXIF. At least two different times
   are required.
3. Choose **Capture response**: **Known sRGB**, **Known Rec.709**, **Known
   linear**, or **Measure camera response from brackets**. Choose the transfer
   actually used to encode the source pixels. Measured response requires at
   least three distinct shutter durations spanning a ratio of four or more
   (two stops).
4. Choose a selected **Reference photograph**, or leave **Automatic · middle
   shutter time**. The reference establishes the alignment coordinate system
   and supplies replacement pixels for moving regions.
5. Set **Align photographs** to **Already aligned**, **Measure translation**,
   or **Measure planar perspective**. Translation measures image displacement;
   planar perspective measures a projective homography from shared texture.
6. For moving subjects, choose **Keep reference in motion mask**. Set **Motion
   threshold · stops** between 0.1 and 4; the default is 0.5. Lower thresholds
   mark more radiance disagreements. **Merge every exposure** leaves this
   replacement disabled.
7. Choose the installed **OCIO configuration**, **Display**, **View**, and
   **Exposure · stops**, then press **Merge and develop**. Review the processed
   picture, response residual, and reported motion/clipping counts. **View
   motion mask** displays the actual mask; white pixels use only the reference.

Use captures made with the same aperture, ISO, white balance, focus, and color
primaries. The supported primaries are Rec.709/sRGB. Inputs must be finite,
opaque still images with normalized capture values between zero and one.
Camera RAW import/development is a separate operation; the bracket inputs are
the selected media-bin images. HDR captures must have equal dimensions.

Measured response uses an actual Debevec fit followed by monotone projection.
The receipt retains a 256-level inverse response for each RGB channel, the
sample count, fitting residuals, and the projection adjustment. Each channel is
normalized at code value 128: the result is relative radiance, not absolute
radiometric or white-balance calibration. A poor fit is refused. Saturated
detail absent from every usable exposure cannot be recovered.

Alignment requires a textured common background and at least 50% common
reference coverage. Missing aligned borders remain transparent. A homography
does not correct depth-dependent parallax, rolling shutter, or lens distortion.
Reference replacement preserves the selected exposure's noise, blur, and
clipped highlights; it does not reconstruct occluded objects. The receipt
counts motion pixels whose reference exposure is clipped.

## Stitch a planar panorama

1. Import 2–8 overlapping photographs, open **Develop images**, and choose
   **Stitch planar panorama**.
2. Select every photograph to include. Choose the **Reference photograph**,
   or leave **Automatic · first selected photograph**.
3. Choose **Capture transfer**: **sRGB**, **Rec.709**, or **Linear**. Keep focus
   and white balance fixed across the capture.
4. Enable **Match exposure in measured overlaps** when appropriate. This
   measures a separate gain for each RGB channel from usable overlapping
   linear pixels. Insufficient overlap or a gain outside 0.25–4 is refused.
5. Choose the OCIO display settings and press **Stitch and develop**.

The solver connects all selected views through measured feature matches and
planar homographies. A disconnected or ambiguous view causes failure; the job
does not silently drop it. Output covers the union of the warped images, uses
scene-linear feathering in overlaps, and leaves uncovered pixels transparent.
The receipt retains source-to-reference and source-to-canvas transforms,
inliers, residuals, overlap counts, and exposure gains.

Use a static scene with distinctive, connected overlap. This is a planar
workflow: cylindrical/spherical projection, strong-parallax correction,
automatic lens estimation, and moving-subject seam repair are outside its
scope.

## Results, editing, and preservation

| Artifact | Stored behavior |
| --- | --- |
| **Float EXR** (`linear.exr`) | 32-bit scene-linear RGBA in the receipt's OCIO working space, with premultiplied alpha and the chosen exposure adjustment. Finite values below zero and above one remain representable. |
| **Display PNG** (`display.png`) | 16-bit sRGB RGBA with straight alpha, rendered through the selected OCIO display/view and clipped to the display range. This is the new media-bin asset. |
| **Processing receipt** (`receipt.json`) | Normalized recipe, original source identities, runtime/configuration identities, measured geometry/response/motion statistics, and output byte hashes. |
| **Motion mask PNG** (`motion.png`) | Present only when reference-based ghost removal is selected. White marks reference replacement, black marks ordinary merging, and alpha records valid common coverage. The receipt binds its hash and size. |

Processing does not insert or replace timeline clips. Add the developed image
through the ordinary media-bin controls, then use normal edit undo/redo and
Save. Reopening preserves the authored clip and immutable asset references.
The dialog offers downloads of the completed artifacts and a toggle between
the developed picture and motion mask.

Adding the developed media-bin asset uses the display PNG. Its accompanying
EXR is not automatically substituted into a movie graph. Movie processing and
delivery follow the project's explicitly selected pipeline; these still
operations do not themselves certify HDR movie mastering or calibrated output
monitoring. The lossless movie acceptance below selects the existing **High
16-bit SDR** path.

Jobs own their staging files and processing children. **Cancel processing**
stops the job; a failed or cancelled job does not publish a completed output or
replace originals. A changed source identity is refused. A project archive
preserves the selected original media, normalized recipes, float masters,
display copies, receipts, and any motion masks. Restore verifies their bytes
and creates a new project; it does not overwrite the source project.

## Processing limits and installed runtimes

| Limit | Bound |
| --- | ---: |
| HDR bracket count | 2–16 |
| Panorama image count | 2–8 |
| Enhanced source dimensions | At least 32 pixels on each edge |
| Enhanced pixels per source | 8,388,608 |
| Total enhanced input pixels | 25,165,824 |
| Output pixels | 33,554,432 |
| Output edge | 16,384 pixels |
| Feature-analysis edge | 1,536 pixels |
| Explicit shutter duration | 0.000001–3,600 seconds |
| Geometry child timeout | 240 seconds |
| Owned image-job timeout | 300 seconds |

The enhanced-input bounds apply when alignment, measured response, reference
ghost removal, or panorama processing is requested. Existing already-aligned
HDR merging with a known response and no ghost removal retains its established
processing path. Geometry is measured at the analysis resolution; the source
pixels and final warps use the decoded image resolution.

On macOS the existing managed interpreters are:

```text
~/Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python
~/Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python
```

Imaging supplies NumPy, OCIO, and OpenEXR. Tracking supplies NumPy and OpenCV.
The standard application process does not import these optional numeric
libraries. The image job passes hashed float snapshots to its owned geometry
child, verifies the returned bytes, and uses the same cancellation process
group. These workflows do not install packages or download models.

## Native acceptance: five bounded phases

Run acceptance on macOS from the exact source root being verified. Use a new
evidence directory for each attempt. The commands below use the existing
managed runtimes and build the independent WKWebView helper from that source.
Run setup and compilation separately from the five phase invocations.

```sh
export CINEMATICUM_IMAGING_PYTHON="$HOME/Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python"
export CINEMATICUM_TRACKING_PYTHON="$HOME/Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python"
CINEMATICUM_STILL_SOURCE="$PWD"
CINEMATICUM_STILL_EVIDENCE="$CINEMATICUM_STILL_SOURCE/dist/verification/still-photography-01"
mkdir -p "$CINEMATICUM_STILL_SOURCE/dist/verification"
mkdir "$CINEMATICUM_STILL_EVIDENCE"
CINEMATICUM_STILL_BINARY="$CINEMATICUM_STILL_EVIDENCE/StillPhotographySmoke"
swiftc "$CINEMATICUM_STILL_SOURCE/scripts/studio/macos/SmokeTest.swift" \
  -framework Cocoa -framework WebKit -o "$CINEMATICUM_STILL_BINARY"
shasum -a 256 "$CINEMATICUM_STILL_BINARY" > "$CINEMATICUM_STILL_EVIDENCE/helper.sha256"
```

Freeze the operative and acceptance-source inventory after integration:

```sh
"$CINEMATICUM_IMAGING_PYTHON" -I -B - \
  "$CINEMATICUM_STILL_SOURCE/scripts/studio" \
  "$CINEMATICUM_STILL_EVIDENCE/source-inventory.json" <<'PY'
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from test_still_photography_ui import source_inventory
Path(sys.argv[2]).write_text(json.dumps(source_inventory(), indent=2, sort_keys=True) + "\n")
PY
```

Execute each following command as a separate foreground operation, in order.
Every phase has an 18-second work bound and records a fresh report. The next
phase requires the preceding successful report, exact saved-project identity,
original fixture identities, and unchanged frozen source.

```sh
"$CINEMATICUM_IMAGING_PYTHON" -B "$CINEMATICUM_STILL_SOURCE/scripts/studio/test_still_photography_ui.py" \
  --binary "$CINEMATICUM_STILL_BINARY" --operation prepare \
  --output "$CINEMATICUM_STILL_EVIDENCE/prepare" \
  --fixture-workspace "$CINEMATICUM_STILL_EVIDENCE/fixture" \
  --source-manifest "$CINEMATICUM_STILL_EVIDENCE/source-inventory.json"
```

```sh
"$CINEMATICUM_IMAGING_PYTHON" -B "$CINEMATICUM_STILL_SOURCE/scripts/studio/test_still_photography_ui.py" \
  --binary "$CINEMATICUM_STILL_BINARY" --operation import \
  --output "$CINEMATICUM_STILL_EVIDENCE/import" \
  --fixture-workspace "$CINEMATICUM_STILL_EVIDENCE/fixture" \
  --source-manifest "$CINEMATICUM_STILL_EVIDENCE/source-inventory.json"
```

```sh
"$CINEMATICUM_IMAGING_PYTHON" -B "$CINEMATICUM_STILL_SOURCE/scripts/studio/test_still_photography_ui.py" \
  --binary "$CINEMATICUM_STILL_BINARY" --operation hdr \
  --output "$CINEMATICUM_STILL_EVIDENCE/hdr" \
  --fixture-workspace "$CINEMATICUM_STILL_EVIDENCE/fixture" \
  --source-manifest "$CINEMATICUM_STILL_EVIDENCE/source-inventory.json"
```

```sh
"$CINEMATICUM_IMAGING_PYTHON" -B "$CINEMATICUM_STILL_SOURCE/scripts/studio/test_still_photography_ui.py" \
  --binary "$CINEMATICUM_STILL_BINARY" --operation panorama \
  --output "$CINEMATICUM_STILL_EVIDENCE/panorama" \
  --fixture-workspace "$CINEMATICUM_STILL_EVIDENCE/fixture" \
  --source-manifest "$CINEMATICUM_STILL_EVIDENCE/source-inventory.json"
```

```sh
"$CINEMATICUM_IMAGING_PYTHON" -B "$CINEMATICUM_STILL_SOURCE/scripts/studio/test_still_photography_ui.py" \
  --binary "$CINEMATICUM_STILL_BINARY" --operation deliver \
  --output "$CINEMATICUM_STILL_EVIDENCE/deliver" \
  --fixture-workspace "$CINEMATICUM_STILL_EVIDENCE/fixture" \
  --source-manifest "$CINEMATICUM_STILL_EVIDENCE/source-inventory.json"
```

The phases prepare independent synthetic ENGINE TEST photographs; import six
actual PNG files through the shipped controls; execute alignment, measured
response, and motion replacement; stitch a panorama with measured exposure
matching; and export/download a 24-frame FFV1 16-bit SDR master and a project
archive. They exercise normal add/undo/redo/save/reopen controls, compare
geometry and radiance against independently generated truth, compare decoded
movie pictures with the actual paused export graph, and verify archive-restored
masters and masks byte for byte.

`ENGINE_TEST_still_photography_report.json` in every phase directory contains
the actual result, source identities, and checks. Preserve unsuccessful
attempts, and begin a new attempt after a source/helper change. The ordinary
native CLI refuses non-macOS execution. The separate
`test_still_photography_browser.cjs` driver runs the same controls in a real
browser and marks that evidence `native_certified: false`.

These acceptance helpers do not certify physical mouse/keyboard input, the
production Save panel, the installed application launcher, arbitrary capture
sets, or sustained production-scale operation. A native result exists only
after the corresponding WKWebView phases actually pass against frozen source.

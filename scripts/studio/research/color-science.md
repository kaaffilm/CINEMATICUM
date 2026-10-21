# Color science, LUTs, RAW and HDR source inspection

Inspected 2026-10-21 for CINEMATICUM Studio v0.6. This audit records actual implementation files at immutable Git commits. The implementation added here is an input colour transform and project-owned creative LUT pipeline. RAW development, HDR mastering, a full OCIO processor and generated environment lighting remain separate, unimplemented capabilities.

## Pinned primary source evidence

Repository heads observed through GitHub, followed by file reads at those exact commits:

| Repository | Observed commit | Relevant implementation evidence |
| --- | --- | --- |
| colour-science/colour | `e82dd140c02d66a174072281e667d595ac5b6951` | Cube ordering/domain parsing, Bradford adaptation, RGB primary matrices and transfer functions |
| AcademySoftwareFoundation/OpenColorIO | `22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd` | Iridas Cube parser/operation building, Baker validation and Python bindings |
| LibRaw/LibRaw | `2caab57e269cc7fce17c3189e4d4d7e3e5861875` | Raw-to-image conversion, full development sequence and output packing |
| colour-science/colour-hdri | `213e07f2da7c509361c22f57c97008e0e4529f2e` | Radiometric image-stack merge and response-curve estimation |
| DiffusionLight/DiffusionLight | `7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc` | Model loading/inpainting, mirror-ball projection and exposure combination |
| FFmpeg/FFmpeg | `713d9fa4b794d6df513ae742d3180732a54e0b66` | Actual `geq`, `lut1d` and `lut3d` execution semantics |

These are source revisions, not claims that those versions are installed on the user's computer. CINEMATICUM executes the installed FFmpeg. Its filter behaviour is separately tested against known pixel values.

| Source file at inspected commit | Git blob SHA |
| --- | --- |
| [colour: Iridas Cube reader/writer](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/io/luts/iridas_cube.py) | `43f48ebabb7ca01990f9a6546240465e7de968ca` |
| [colour: Von Kries/Bradford matrix construction](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/adaptation/vonkries.py) | `3d5f50e1c71f215e915acaf838cc2ee711ea00e3` |
| [colour: CAT coefficient datasets](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/adaptation/datasets/cat.py) | `31f79235bb74a410b4a5b036a71047dd0b412fc6` |
| [colour: sRGB transfer](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/srgb.py) | `b9cfc8bd2899211477e2bf545f0686010418a829` |
| [colour: BT.601 transfer used by BT.709](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/itur_bt_601.py) | `637e48623d705955a7851626cf5c11568338f15f` |
| [colour: BT.709 transfer delegation](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/itur_bt_709.py) | `2764db10c8ebf0ec543bf8b94ef804e3e363ba40` |
| [colour: ARRI transfer functions and EI tables](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/arri.py) | `21004f41cbf060130f8a8744b785db7f9300c594` |
| [colour: ARRI gamut definitions](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/datasets/arri.py) | `b63f3bd6b925ca507f226c7f432ddfa7df0d2ead` |
| [colour: ACES/AP1 primaries and white](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/datasets/aces.py) | `b41fc9f4e07104c44de20a5b605317bf7f211834` |
| [OCIO: Iridas Cube format](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/OpenColorIO/fileformats/FileFormatIridasCube.cpp) | `b6da8d7e81bfd30ce77a53fbf8417e7fb203ad07` |
| [OCIO: Baker validation/dispatch](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/OpenColorIO/Baker.cpp) | `e92a4f3d31688d8769da8595f7b0cbc5940ebf32` |
| [OCIO: Python Baker bindings](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/bindings/python/PyBaker.cpp) | `f3c2439415e42f5e198dfca7fea7e04028868293` |
| [OCIO: Python Baker acceptance tests](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/tests/python/BakerTest.py) | `aa48327869897013c3a10981c0f5d30804e7988b` |
| [LibRaw: development sequence](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/src/postprocessing/dcraw_process.cpp) | `80271935fd8331c9b4ead87a675cb89681b338a7` |
| [LibRaw: processed output memory packing](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/src/postprocessing/mem_image.cpp) | `95d582ac684a8f73741b7d425660e2f90e8b31e2` |
| [LibRaw: raw2image and CFA-aware cropping](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/src/preprocessing/raw2image.cpp) | `899aad385441678cca71b2b294fd47ee18964ccf` |
| [colour-hdri: image stack to HDRI](https://github.com/colour-science/colour-hdri/blob/213e07f2da7c509361c22f57c97008e0e4529f2e/colour_hdri/generation/hdri.py) | `c25cc84208ab9ef5febfe2f3010c210893fb3cf1` |
| [colour-hdri: Debevec response estimation](https://github.com/colour-science/colour-hdri/blob/213e07f2da7c509361c22f57c97008e0e4529f2e/colour_hdri/calibration/debevec1997.py) | `58f19f0b65c3579242c5df9f85b7d5d677154699` |
| [DiffusionLight: inpainting orchestration](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/inpaint.py) | `6b6fe9eda92ed90b790cdb8904dfa03b1eff8b74` |
| [DiffusionLight: SD/SDXL model loading](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/relighting/inpainter.py) | `0eddd323ec8fe5afea076906837b880ce234aaf2` |
| [DiffusionLight: ball to environment projection](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/ball2envmap.py) | `6d54dff03d4552ec9539c7d5320b61c43293a68d` |
| [DiffusionLight: exposure to HDR](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/exposure2hdr.py) | `00072017ce0305e80e703a5ca7204e18db9398a0` |
| [FFmpeg: float GEQ formats and sampling](https://github.com/FFmpeg/FFmpeg/blob/713d9fa4b794d6df513ae742d3180732a54e0b66/libavfilter/vf_geq.c) | `fc3dd6740ef6a4618c4195b5672995f48da1c8a2` |
| [FFmpeg: Cube parsing and 1D/3D interpolation](https://github.com/FFmpeg/FFmpeg/blob/713d9fa4b794d6df513ae742d3180732a54e0b66/libavfilter/vf_lut3d.c) | `2c78507b7e45449a2213f05c712f1913c600ceb0` |

## What the source review established

### LUT coordinates must be preserved explicitly

Colour's Cube reader reconstructs 3D data with the red index changing fastest. Its domain is a pair of three-component bounds. OCIO builds domain normalization into its operation sequence. A LUT is therefore a sampled function over a declared input domain, not a list of RGB triples that can be evaluated without the bounds. Both readers distinguish 1D channel tables from 3D tables; the Resolve combined-shaper variant has additional semantics. See the [Colour reader](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/io/luts/iridas_cube.py) and [OCIO format implementation](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/OpenColorIO/fileformats/FileFormatIridasCube.cpp).

The inspected FFmpeg Cube parser reads minimum and maximum values but sets a clipped reciprocal extent as its scale. The float processing path multiplies input channels by that scale; it does not subtract each Cube minimum. Passing an arbitrary-domain Cube directly to `lut3d` would change its meaning. CINEMATICUM therefore writes a unit-domain render copy and applies `clip((channel - minimum) / (maximum - minimum), 0, 1)` in float GEQ before the LUT. The pixel tests exercise unequal ranges, nonzero minima and out-of-range input. This fixes a specific source-derived integration hazard. See [FFmpeg `parse_cube` and float interpolation paths](https://github.com/FFmpeg/FFmpeg/blob/713d9fa4b794d6df513ae742d3180732a54e0b66/libavfilter/vf_lut3d.c).

### White balance belongs between transfer decoding and encoding

The Von Kries implementation computes a cone-domain diagonal scale between source and target whites, then returns the matrix product through the inverse CAT basis. CINEMATICUM independently implements the Bradford form:

`M_XYZ = inverse(B) × diag((B × white_target)/(B × white_source)) × B`.

It derives RGB→XYZ matrices from the selected primaries and nominal white, then composes `inverse(M_709) × M_XYZ × M_input`. This matrix acts on linear RGB. An encoded RGB channel offset is not the same operation. Numerical tests compare a published D65→D50 matrix and verify that the source white maps to the target white. See [adaptation implementation](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/adaptation/vonkries.py) and [CAT data](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/adaptation/datasets/cat.py).

The implemented transfer choices are identity linear, the piecewise sRGB function, BT.709 OETF/inverse OETF, and ARRI LogC3 **SUP 3.x, EI 800, linear scene exposure factor**. The LogC3 constants and breakpoint are specific to that camera mode. Its UI preset binds LogC3 to ARRI Wide Gamut 3; changing only the curve would not convert camera primaries. LogC4, other EI tables, S-Log, V-Log, PQ, HLG and BT.1886 display EOTF are not silently treated as these functions. See [ARRI transfer table](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/arri.py), [ARRI primaries](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/datasets/arri.py), [sRGB](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/srgb.py) and [BT.709 delegation](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/colour/models/rgb/transfer_functions/itur_bt_709.py).

### An OCIO Baker is a configured processor, not an ACES checkbox

The inspected Baker validates a configuration, source and destination spaces (or display/view), output format, cube/shaper sizes and optional looks. The Python tests set a real configuration before baking and inspect the resulting LUT text. A useful adapter would need an installed `PyOpenColorIO`, an immutable supported configuration, explicit source/display/view selection and tested baking-domain/precision rules. Merely accepting a `.cube` or converting AP1 primaries does not execute that machinery. No OCIO runtime is assumed or loaded by this release. See [Baker validation](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/OpenColorIO/Baker.cpp), [Python bindings](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/bindings/python/PyBaker.cpp) and [Baker tests](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/tests/python/BakerTest.py).

### RAW development needs sensor data, metadata and a development sequence

`raw2image_ex` checks unpacking order and available sensor buffers, handles CFA-aware crop alignment and may subtract black. `dcraw_process` follows with color scaling, interpolation/demosaicing, highlight handling and RGB conversion. Memory output has its own bit-depth and gamma/brightness packing. A photo file being decoded by FFmpeg does not establish that this raw sequence ran. This release neither invokes LibRaw nor adds RAW extensions to the admitted media types. A future adapter must preserve original sensor media and development parameters, report the actual LibRaw version, and validate linear output against known RAW fixtures. See [raw conversion](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/src/preprocessing/raw2image.cpp), [development](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/src/postprocessing/dcraw_process.cpp) and [output packing](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/src/postprocessing/mem_image.cpp).

### HDR radiance reconstruction and generated lighting are distinct operations

`colour-hdri` merges an exposure stack using exposure-derived normalization and per-pixel weights; a nonlinear source can supply camera response functions. The response estimator solves a constrained least-squares system with smoothing, then exponentiates the recovered log response. This needs exposure metadata, comparable images and controlled response assumptions. The new color pipeline implements none of that merge or calibration. See [HDRI merge](https://github.com/colour-science/colour-hdri/blob/213e07f2da7c509361c22f57c97008e0e4529f2e/colour_hdri/generation/hdri.py) and [response estimation](https://github.com/colour-science/colour-hdri/blob/213e07f2da7c509361c22f57c97008e0e4529f2e/colour_hdri/calibration/debevec1997.py).

DiffusionLight instead loads SD/SDXL pipelines, optional ControlNet and LoRA, creates mirror-ball appearances at several exposure conditions, projects the ball into a latitude/longitude environment map, then combines exposure-normalized luminance into HDR output. Its projected illumination is inferred by a model. Its source code is not a substitute for installed weights, executable dependencies or measured illumination truth. No model inference, checkpoint download or external provider call was performed here. See [inpainting](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/inpaint.py), [model loading](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/relighting/inpainter.py), [projection](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/ball2envmap.py) and [exposure merge](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/exposure2hdr.py).

## Implemented CINEMATICUM contract

`color_pipeline.py` owns the following executable behaviour:

- Strict `.cube` parsing: exactly one 1D three-channel table or one 3D table; 1D sizes 2–65,536; 3D sizes 2–65; exact row count; finite bounded numbers; strictly increasing per-channel domains; optional unique quoted title; comments and whitespace normalization. Combined shaper files and unknown directives fail explicitly. The text limit is 24 MiB, and a project holds at most 128 imported LUTs.
- Canonical storage: a deterministic text serialization is SHA-256 addressed at `color/luts/<digest>.cube`. Imports are published atomically without overwriting an existing identity. Directory/file symlinks, missing content, altered bytes and noncanonical files are rejected. Saved clip JSON contains the digest and interpolation only, never an arbitrary LUT pathname.
- 1D nearest/linear interpolation and 3D nearest/trilinear/tetrahedral interpolation. The independent Python evaluator tests all six tetrahedral simplex orderings. Domain endpoints clamp; LUT output values remain float and can be negative or above one inside the color stage.
- An explicit input transform from linear, sRGB, Rec.709 or the specified LogC3 mode; primaries from Rec.709, Rec.2020, ACEScg/AP1 or ARRI Wide Gamut 3; Bradford white adaptation; output encoded to Rec.709 before the creative LUT.
- Actual FFmpeg filters on `gbrapf32le`; RGB equations explicitly copy alpha. The transform precedes the clip's node compositor and existing creative grade in the shared render graph. Paused preview and movie export use that graph.
- An in-app Color pipeline editor with camera/input presets, source/target CIE xy controls, project LUT selection, import errors, domain/identity review, interpolation choice, bypass, reset and one-change undo/redo through the parent editor.

The selected input interpretation is explicit user data, not guessed from a filename. The output remains the current SDR compositor and delivery pipeline. Negative/superwhite intermediate preservation does not make the rest of the compositor float HDR. ACEScg input conversion is a matrix/transfer conversion, without an ACES rendering or display transform; out-of-output-gamut values and highlights may clip downstream. There is no camera-specific highlight compression, gamut mapping, monitor calibration, ICC display management or RAW development in this addition.

### Integration API

```python
descriptor = import_cube(text, project_dir)
descriptors = list_luts(project_dir)
pipeline = validate_pipeline(clip.get("color_pipeline"), project_dir)
filters = compile_pipeline(pipeline, project_dir, render_temp_dir, prefix="c0")
```

```json
{
  "version": 1,
  "enabled": true,
  "input_transfer": "logc3_ei800",
  "input_primaries": "arri_wide_gamut3",
  "source_white": [0.3127, 0.329],
  "target_white": [0.3127, 0.329],
  "lut": null
}
```

`GET /api/projects/:id/color-luts` lists server-owned descriptors. `POST /api/projects/:id/color-lut-import` takes `{ "text": "..." }` and returns `{ "lut": descriptor }`; the server applies a route-specific body bound. Importing a file does not apply a clip edit. Applying the selected pipeline goes through the existing undoable project mutation. Preview invalidation uses the changed project state.

## Acceptance and runtime requirements

Run `python3 -m unittest discover -s scripts/studio -p test_color_pipeline.py -v`. The 22 targeted tests cover malformed Cube rejection, canonical identity, channel/row ordering, all six simplex regions, published adaptation and transfer reference points, content tampering, missing references, symlink rejection, and independently measured FFmpeg float pixels. Float tests include alpha, nonzero unequal domains, negative/superwhite values, actual AWG3/LogC3 and ACEScg neutral conversions, and filter paths containing FFmpeg metacharacters. These tests passed in the development workspace. They use generated test pixels only.

The separate `test_color_pipeline_ui_macos.py` runs `macos/ColorPipelineSmoke.js` in the actual WKWebView helper. It uses the shipped file input and controls, saves the clip, checks undo/redo and independently decodes the actual preview PNGs. It requires a real Mac and explicitly skips elsewhere. Its run result is recorded by the root acceptance pass; source presence alone is not a native acceptance claim.

Required runtime capabilities are Python 3.9+, FFmpeg/ffprobe, float planar GBR(A), `geq`, `lut1d`, `lut3d`, and the existing renderer's codecs. No NumPy, Colour, OpenColorIO, LibRaw, Torch or DiffusionLight package is required for this implemented path. Missing renderer support must surface an actual render error rather than an unchanged-image success.

## Licensing boundary

No upstream implementation files or model weights are vendored by this addition. CINEMATICUM's parser, interpolation reference, matrix algebra, filter compiler and UI are original implementations of the documented formats and mathematical definitions. The inspected [Colour license](https://github.com/colour-science/colour/blob/e82dd140c02d66a174072281e667d595ac5b6951/LICENSE), [Colour HDRI license](https://github.com/colour-science/colour-hdri/blob/213e07f2da7c509361c22f57c97008e0e4529f2e/LICENSE) and [OCIO license](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/LICENSE) are BSD-style three-clause notices. [LibRaw's copyright notice](https://github.com/LibRaw/LibRaw/blob/2caab57e269cc7fce17c3189e4d4d7e3e5861875/COPYRIGHT) describes LGPL 2.1 or CDDL 1.0 licensing with component notices. [DiffusionLight's repository code license](https://github.com/DiffusionLight/DiffusionLight/blob/7130ec43739d6c9fe1e70cf5f0389b8f72f5ddbc/LICENSE) is MIT; that code notice does not establish the terms of every separately downloaded model checkpoint. Future distribution of those runtimes or code must retain the applicable notices and satisfy the selected dependency licenses.

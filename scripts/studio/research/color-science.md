# Color science, LUTs, RAW and HDR source inspection

Inspected 2026-10-21. This audit records actual implementation files at immutable Git commits. The v0.6 work added the dependency-free input transform and project-owned creative LUT pipeline documented below. The continuation adds an isolated, executable imaging worker for builtin OCIO display transforms, real LibRaw RAW development, aligned exposure-bracket reconstruction and float OpenEXR preservation. Its implementation, pinned dependencies, acceptance evidence and remaining boundaries are documented in **Imaging worker continuation** at the end. References below to the v0.6 release's missing OCIO/RAW/HDR capabilities describe that historical release, not the continuation.

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

## Imaging worker continuation

The optional worker is executable through `imaging.py` and `image_worker.py`; the normal editor and `color_pipeline.py` still import no third-party Python packages. The installed environment is selected explicitly by `CINEMATICUM_IMAGING_PYTHON`, or the packaged Mac location `~/Library/Application Support/CINEMATICUM/Imaging/py313-v1/bin/python`. There is no silent fallback to arbitrary system packages. Capability discovery imports the actual modules under that interpreter and reports the versions and available operations. A missing dependency disables the affected workflow with an explicit error.

### Additional primary source inspection

| Source at immutable commit | Git blob SHA | What was inspected |
| --- | --- | --- |
| [rawpy dependency/build declaration](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/pyproject.toml) | `d817e5c9f2ecacfe09248894cebbfade695b8daf` | Supported Python versions, NumPy dependency and extension packaging |
| [rawpy LibRaw bindings](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/rawpy/_rawpy.pyx) | `391983c4b14f8aad5693f9da9253786e292fb096` | `open_buffer`, header sizes before `unpack`, automatic-unpack properties, demosaic support and exact `Params`→LibRaw assignments |
| [rawpy genuine camera fixture tests](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/test_basic.py) | `9cf865dd24843082d10785dc1963234625696267` | Nikon D3S fixture dimensions, 16-bit linear development, sensor buffers and channel metadata |
| [rawpy sample-file provenance](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/README.txt) | `5297c6712d9f18ccb85813bb8e5ff0aebe39d3a0` | Identifies the separately licensed rawsamples.ch test photos; those were not bundled |
| [OCIO builtin registry](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/OpenColorIO/builtinconfigs/BuiltinConfigRegistry.cpp) | `61825a065301757018cfda380b962b9304749466` | Named embedded configuration contents and current CG/studio registry identifiers |
| [OCIO builtin registry tests](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/tests/python/BuiltinConfigRegistryTest.py) | `fddf1bdd47cd37466178e2424674ccad4e57b087` | The actual Python iterator contract including recommendation/default fields |
| [OCIO float CPU bindings](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/bindings/python/PyCPUProcessor.cpp) | `e5786ba244fcc3dfdbfe9f51eeca9ceb3e716790` | Packed NumPy buffer handling and in-place CPU processor execution |
| [OCIO CPU numerical tests](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/tests/python/CPUProcessorTest.py) | `128281cfe9d6dfa96d99a9d36a1081fb651afc56` | Float32 RGB/RGBA arrays and negative/superwhite numeric ranges |
| [OpenEXR 3.4.15 Python implementation](https://github.com/AcademySoftwareFoundation/openexr/blob/e71cdd5d30a146dcb56c5e4c576d9e9d3c45f4fb/src/wrappers/python/PyOpenEXR.cpp) | `2e9d1106f41272b38c6db6ce533cdb160796134a` | Channel grouping, array strides, explicit float channel slices, part/window and deep-data distinction |
| [OpenEXR RGB/RGBA tests](https://github.com/AcademySoftwareFoundation/openexr/blob/e71cdd5d30a146dcb56c5e4c576d9e9d3c45f4fb/src/wrappers/python/tests/test_rgba.py) | `a36b2ee2650e014deea2799a55336ae1985c8108` | Exact float array round-trip, grouped/separate channels and ambiguous channel collision rejection |
| [OpenEXR supported Python File API](https://github.com/AcademySoftwareFoundation/openexr/blob/e71cdd5d30a146dcb56c5e4c576d9e9d3c45f4fb/website/python.rst) | `3f454f8e8bc712e5f3e08f2c3574b2abbbbb727e` | Header-only inspection and supported metadata/array types |
| [OpenEXR license](https://github.com/AcademySoftwareFoundation/openexr/blob/e71cdd5d30a146dcb56c5e4c576d9e9d3c45f4fb/LICENSE.md) | `b2a016ed195d6493eaa8db7251dc83fba466d223` | BSD three-clause redistribution notice |

The runtime requirements are pinned to `numpy==2.3.5`, `opencolorio==2.6.0`, `rawpy==0.27.1` and `OpenEXR==3.4.15`. Official release metadata is available at [NumPy](https://pypi.org/project/numpy/2.3.5/), [OpenColorIO](https://pypi.org/project/opencolorio/2.6.0/), [rawpy](https://pypi.org/project/rawpy/0.27.1/) and [OpenEXR](https://pypi.org/project/OpenEXR/3.4.15/). The development acceptance used an isolated Python 3.12.14 environment with these exact versions and LibRaw 0.22.1. The Mac runtime installation independently reported Python 3.13.13 and the same four package/LibRaw versions. Native UI acceptance is a separate run and is not inferred from successful package imports.

### Repeatable optional runtime installation

On Apple Silicon macOS with an existing native CPython 3.13 interpreter:

```sh
python3 scripts/studio/install_imaging.py --python /opt/homebrew/bin/python3.13
python3 scripts/studio/install_imaging.py --check
```

The default stable runtime is `~/Library/Application Support/CINEMATICUM/Imaging/py313-v1`. The helper does not install Python itself or change global Python packages. `imaging-macos-arm64-py313.lock.json` records the four exact CPython 3.13/macOS 11+ arm64 wheel URLs, sizes and SHA-256 hashes obtained from official PyPI release JSON. pip receives direct `files.pythonhosted.org` URLs with `--require-hashes --only-binary=:all: --no-deps --no-index`; the helper verifies pip's installed-version/download-hash report and then imports all four actual modules. Its health check constructs the real default builtin OCIO configuration, executes its actual CPU display transform, opens the LibRaw binding, and round-trips a float EXR containing −0.25 and 4 without clipping. The installed version and module location must belong to the expected isolated environment.

A fresh environment is built at its permanent private version path. After successful verification, the stable path is created as a relative symlink in one no-overwrite operation. The environment itself is never moved: [Python's venv documentation](https://docs.python.org/3.13/library/venv.html#how-venvs-work) explains that installed script shebangs retain absolute interpreter paths. An installation receipt records those permanent paths, exact wheel identities and numerical health results. An existing healthy directory, including the independently installed Mac runtime, is checked and returned unchanged; its original wheel hashes are not retroactively asserted. Existing unrelated files, unrelated links, unhealthy environments and destinations created during installation are preserved. Failed new installations remove only their unpublished environment. `--destination` can explicitly choose a separate absolute path; `--check` never installs anything.

Eight installer tests passed in the development workspace. They cover publication at the verified permanent path, idempotence, failed installation cleanup, a concurrently created destination, preservation of unrelated/failed-existing paths, exact wheel-report rejection and the actual numerical dependency probe. Fresh Apple Silicon wheel installation requires its own Mac execution; the Linux tests do not claim to install macOS binaries. The [pip documentation](https://pip.pypa.io/en/stable/cli/pip_install/) describes the direct archive URL, no-index, no-dependency, hash-checking and installation-report interfaces used by the helper.

### Executed operations and stored artifacts

**OCIO still-image development.** The worker enumerates the installed `BuiltinConfigRegistry` and accepts only exact registry names. `Config.CreateFromBuiltinConfig` constructs the configuration; no external `.ocio` file, environment substitution, URL or LUT search path is accepted. The selected input space is converted through a real float CPU processor into the configuration's `scene_linear` role. Exposure multiplies that linear image by `2**stops`. A real `DisplayViewTransform` then produces the selected sRGB display view. The default studio configuration is `studio-config-v5.0.0_aces-v2.1_ocio-v2.6`, observed in the actual runtime; its catalogue includes camera log spaces such as ARRI LogC4, Apple Log, S-Log3 and V-Log. Available names always come from the selected configuration, not a hard-coded claim that every model/camera is supported.

The current display delivery is explicitly `sRGB - Display`; its actual ACES, un-tone-mapped and colorimetric views are selectable. The data-only `Raw` view is excluded because it is not an sRGB display encoding. Imported EXR `ocioColorSpace` metadata may select a matching input space only after header inspection and catalogue membership checks. An EXR with absent/unknown metadata requires an explicit input choice. No ACEScg assumption is silently attached to an arbitrary EXR.

**Camera RAW development.** Original bytes are SHA-256 addressed under `imaging/sources/<sha>.raw`, with a source descriptor containing real CFA, black/white level, dimensions, orientation and white-balance metadata. The worker opens the preserved sensor data with rawpy/LibRaw, checks sensor dimensions before unpacking, and executes demosaicing, as-shot/daylight/automatic/custom sensor white balance, highlight clip/blend/reconstruction, and optional half-size processing. The output is LibRaw 16-bit linear Rec.709-primary RGB using `gamma=(1,1)` and `no_auto_bright=True`; this is promoted to float for the actual OCIO processing. The receipt states the 16-bit development boundary. Neither the container's float type nor highlight reconstruction claims to recover sensor detail already lost at capture or to make LibRaw's packed output an unclipped sensor-float image. Unsupported demosaic algorithms and missing as-shot white balance fail explicitly.

**HDR bracket reconstruction.** Two to sixteen distinct admitted images use explicit exposure seconds and a selected sRGB/Rec.709/linear capture response. For each channel, the worker computes a weighted mean of linear signal divided by shutter time. The triangular confidence weight excludes encoded samples at or below 0.002 and at or above 0.998. Processing is sequential across inputs, with equal-dimension and opaque-image validation. Channels with no usable exposure retain the closest available capture sample as a documented floor/lower bound; the receipt counts unrecovered pixels, all-dark channels and all-saturated channels. The method assumes a registered static scene, unchanged aperture/ISO and the selected known response. It does not claim alignment, optical flow, deghosting, automatic exposure extraction or fitted camera-response calibration. This implements a real bounded radiance operation informed by the inspected [colour-hdri merge](https://github.com/colour-science/colour-hdri/blob/213e07f2da7c509361c22f57c97008e0e4529f2e/colour_hdri/generation/hdri.py), independently of that package's implementation.

Every successful job atomically publishes exactly three files beneath `imaging/outputs/<job_id>/`:

- `linear.exr`: float32 scene-linear RGBA with conventional premultiplied alpha, selected OCIO space/config metadata and ACEScg chromaticities when applicable. Negative and above-one RGB values survive. Display clipping does not affect this master.
- `display.png`: 16-bit straight-alpha RGBA, tagged sRGB, containing the executed display/view transform. This is copied into normal admitted media for editing, actual paused preview and normal movie export.
- `receipt.json`: exact normalized recipe, immutable source identities, executed versions, configuration serialization SHA/cache ID, display processor cache ID, source-specific details, statistics and hashes of the two image artifacts. The admitted asset records the receipt hash and float-master hash.

A newly added timeline clip with trusted `cinematicum-imaging`/version 1/`display_encoding: sRGB` provenance receives an explicit sRGB-input/Rec.709-primaries color pipeline. A compositor `media_source` for the same admitted display image receives the equivalent input normalization. These stages decode the already rendered sRGB display signal and encode the editor's existing Rec.709 OETF output; they do not run another OCIO view or scene tone map. The Develop viewer continues to show its actual sRGB PNG. This is the renderer's explicit encoding convention, not a claim of calibrated BT.1886/gamma-2.4 monitoring or HDR mastering. Existing unmarked media retains its original behavior.

The worker never accepts arbitrary output locations. Uploads and source assets must be inside the owning project, every path component is checked for symlinks, file reads use `O_NOFOLLOW` where available, and source hashes are checked again against private job snapshots. Recipes reject unknown properties. Outputs are bounded to 33.5 million pixels; sensor headers to 67 million pixels; RAW originals to 512 MiB and 128 sources per project. Processes have a five-minute job limit, propagate cancellation to their owned process group, and publish no result directory after cancellation. The server's normal authorization and job admission mechanisms remain responsible for HTTP requests.

### Two measured precision failures that changed the implementation

The development machine's FFmpeg 6.1.1 could encode a float EXR but its EXR decode path returned clipped values. Merely checking the file extension, encoder name or float output pixel format would have missed the lost negative/highlight data. The worker therefore uses the supported `OpenEXR.File` API for actual EXR input/output. It reads headers before allocating pixels, accepts a single flat RGB(A) part with full-resolution channels and matching zero-origin data/display windows, and rejects deep, multipart, subsampled or cropped-window inputs rather than silently discarding their semantics. The [official API documentation](https://openexr.com/en/latest/python.html) distinguishes these cases and the header-only path.

The same FFmpeg installation's packed 16-bit RGB→planar float path also introduced differing channel rounding into a neutral PNG. For an encoded signal of 0.5371023117, the nominal RGB float decode returned approximately `[0.5370870, 0.5371329, 0.5370718]`; direct packed `rgba64le` preserved all three channels at the same original integer value. Integer still inputs now decode to packed 16-bit RGBA and are explicitly divided by 65535 in NumPy. This removed a measured HDR reconstruction error rather than relaxing the numerical test. Existing float sources are handled as float, and EXR bypasses FFmpeg decoding entirely.

### Acceptance evidence

`test_imaging.py` has 17 acceptance tests. With `CINEMATICUM_IMAGING_PYTHON` pointing to the isolated runtime and `CINEMATICUM_RAW_TEST_FILE` pointing to the real camera fixture, the original 16 passed together in the development workspace; the additional integrated timeline/compositor transfer test passed in a focused invocation. They verify:

- Actual builtin registry/processor execution and rejection of external config paths/URLs; PNG pixels compared with an independently constructed OCIO display processor; a changed view changes the display image while retaining the same float master.
- A direct float EXR round-trip with negative values, highlights above one, partial alpha and embedded chromaticities. The independently supplied premultiplied sample `[-0.25, 0.09, 2, 0.5]`, after +1 stop, reads back as `[-0.5, 0.18, 4, 0.5]`; unassociated working values range from −1 to 8.
- Recovery of independently generated scene radiance `(0.12, 2, 10)` from quantized, clipped sRGB exposures, with absolute channel error below 0.002; explicit unrecovered-highlight counts; dimension/alpha mismatch rejection.
- Genuine camera development compared against a separate rawpy/OCIO reference, and a custom sensor white-balance change producing a different display image.
- An actual developed uniform PNG rendered as both a direct timeline clip and an independent compositor media source. Independently computed inverse-sRGB/Rec.709 expected pixels agree within 4/255; the two engine paths agree within 2/255. Removing the specific imaging provenance leaves an unmarked source unconverted and changes measured pixels, proving that the normalization is scoped to the generated display assets.
- Immutable source/output hashes, tampered/missing/symlink input rejection, duplicate-content bracket rejection, invalid RAW rejection, strict numeric/schema validation, and running-job cancellation with no published artifacts.

The real camera fixture is rawpy's [Nikon D3S `iss030e122639.NEF`](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/iss030e122639.NEF): Git blob `e03d193927a604de40fd0fd7a71e33fde878a0e1`, 10,656,312 bytes, SHA-256 `5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`. The upstream test identifies the camera and expected sensor/output dimensions. It was downloaded only to the separate acceptance-fixture directory, not vendored into CINEMATICUM or presented as user production footage. Fixture access is opt-in through the environment variable; ordinary tests never download media. Any redistribution of source imagery must preserve its separately applicable provenance and rights rather than assuming the rawpy code license covers photos.

`test_imaging_ui_macos.py` runs `macos/ImagingSmoke.js` inside the actual native WKWebView helper. OCIO, HDR and RAW are separate invocations with an 18-second budget. The harness uses the shipped Develop button, actual controls and native FileList, verifies visible/hit-testable controls, downloads the actual PNG/EXR/receipt, places the developed asset into the timeline, saves it, decodes the normal paused frame and compares a normal two-frame movie export. It also checks the saved sRGB input pipeline and independently evaluates the piecewise sRGB inverse/Rec.709 OETF against actual flat-fixture preview pixels. RAW requires a real fixture passed with `--raw-file`; the test-only guarded loopback route supplies those bytes to the native file input. Native results are emitted as explicit evidence reports. They must be run on the Mac before a native-pass claim; the Linux harness reports a skip.

### Remaining boundaries

This continuation provides real OCIO still-image processing, real bounded camera RAW development, radiance reconstruction and float EXR masters. The main movie compositor/delivery remains SDR. There is no claim of float-throughout timeline compositing, PQ/HLG mastering, HDR monitor output, arbitrary external OCIO config packaging, multilayer/deep EXR compositing, DNG/RAW sensor editing in the timeline, automatic bracket alignment/deghosting, fitted camera-response recovery, or DiffusionLight inference. These are separate implementation and validation tasks, not hidden enabled capabilities.

The runtime is installed as isolated pinned third-party wheels; upstream source implementation is not copied into CINEMATICUM. Wheel licenses and dependencies must accompany any redistributed runtime. rawpy's MIT wrapper notice does not replace LibRaw's own license, and OpenEXR's BSD notice is retained by the installed distribution. No neural model checkpoint or paid generation call is part of these operations.

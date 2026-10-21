# Camera calibration and optics: source audit and implemented boundary

Audit date: 2026-10-21. This is a source and file-format audit of fSpy, COLMAP,
OpenCV and Lensfun, followed by an independent implementation of camera-data
import. It is not a claim that CINEMATICUM contains these entire applications.
The implementation neither starts their interfaces nor executes imported code.

## Pinned upstream evidence

The GitHub connector returned the commit and blob identities below. The original
`stuffmatic/fSpy` URL now redirects to the upstream `perarnia/fSpy` repository;
the canonical destination was verified before reading its source.

| System | Commit examined | Files examined and Git blob identities |
| --- | --- | --- |
| [fSpy](https://github.com/perarnia/fSpy/tree/702189ec5acbbd2c8ba492db0e52ecb5fc908f5c) | `702189ec5acbbd2c8ba492db0e52ecb5fc908f5c` | `project_file_format.md` → `d1f379b039b952d71942eb1be526015b4cb682bc`; `src/gui/io/project-file.ts` → `6551c916b8726add73cf03534b82c8ff362bc676`; `src/gui/solver/solver-result.ts` → `fa353f93ca826a2f253999fde69f621df2cfa25e`; `src/gui/solver/solver.ts` → `9abc756c3dfb2ff48e7e6a673b069c6f15763821` |
| fSpy projection and coordinates | Same commit | `src/gui/solver/math-util.ts` → `c9ed40244c8aed36c5a778f85003ab7608509b07`; `coordinates-util.ts` → `10f1d88b85cf3235e03b851efc599f9418be9147`; `transform.ts` → `44b8efa75aab256edce74e158db694b88674b1e8` |
| [Official fSpy Blender importer](https://github.com/perarnia/fSpy-Blender/tree/eec40b085d45cc623fd379998d85b88de679d4b8) | `eec40b085d45cc623fd379998d85b88de679d4b8` | `fspy_blender/fspy.py` → `2fd5ad22d3346434a149aa9e9439df69f21d2977`; `fspy_blender/addon.py` → `dc3ac3758478f8791367479ebbe7a0b3c8dced4d`; `test_data/json_export.json` → `ab7f61c6cbcd6fb8b4a56481e138fd0b4613242b`; `test_data/shifted_portrait.fspy` → `e27380a1d007476e071b72ac05ee4c9ee75c14cc` |
| [COLMAP](https://github.com/colmap/colmap/tree/ceffea58c6e635078ca2e0858ea5ee57870e062e) | `ceffea58c6e635078ca2e0858ea5ee57870e062e` | `src/colmap/scene/reconstruction_io_text.cc` → `f55d3a9e09040d47d985bf9e58da90ae7dc2b6aa`; `src/colmap/sensor/models/pinhole.h` → `385289f5d4bdb4119839aa10c9989a5e413532f0`; `radial.h` → `e42e82ef179ea1c4dfa55258eff9f1ca0b4cda9c`; `opencv.h` → `cd07c3e0591a995d062c607118965a5ab21913d9` |
| [OpenCV](https://github.com/opencv/opencv/tree/1e71c2b43a57fad2d863a0c9b3537bbf610164d7) | `1e71c2b43a57fad2d863a0c9b3537bbf610164d7` | `modules/calib3d/src/calibration_base.cpp` → `1583d3de36b3c27b24741a1ff1534c48c713436c`; `modules/calib3d/src/undistort.dispatch.cpp` → `2a53c254d5f74264ffdde6f5dda6c681c121c1ab` |
| [Lensfun](https://github.com/lensfun/lensfun/tree/b98997f7f1c020d0fac3136c2abbf06126385971) | `b98997f7f1c020d0fac3136c2abbf06126385971` | `libs/lensfun/modifier.cpp` → `03f01302560e139c6a5f8d298b1201ad27f9d74a`; `libs/lensfun/mod-coord.cpp` → `7350303b70c9b8004f35d2cbabc2f0e760bfd8c2` |

Primary public references additionally checked:

- [COLMAP output format](https://colmap.github.io/format.html), including identifiers,
  Hamilton poses, and the two-line image records.
- [OpenCV calibration and 3D reconstruction](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html),
  including the pinhole matrix and radial/tangential model.
- [Lensfun manual](https://lensfun.github.io/manual/latest/), including correction
  types and coordinate-mapping behavior.

## Findings that change the implementation

### fSpy is a solved camera container, not a scene or model

The v1 container is a 16-byte header followed by a UTF-8 state document and an
opaque image blob. The header supplies the `fspy` magic, little-endian version,
JSON byte length and image byte length. The state may contain null camera
parameters after an unsuccessful solve. The implementation checks the entire
container length and rejects an unsolved camera before returning a candidate.
The embedded image is neither decoded nor added to the media bin.

The serialized `cameraTransform.rows` matrix is camera-to-world. Its columns
represent local right, up and backward; translation is in the fourth column.
The inverse view transform, when supplied, must agree. Scale, shear,
reflections, non-affine rows and inconsistent inverse matrices are rejected.

The projection code, not the field names, determines the lens conversion.
fSpy's image-plane coordinate system has its longest half-extent equal to one
and its Y axis pointing upward. Its projection uses the parameter named
`horizontalFieldOfView` for both normalized axes. Consequently, with
`L=max(W,H)` and `s=cot(horizontalFieldOfView/2)`, the corresponding square-pixel
intrinsics are `fx=fy=s*L/2`, `cx=W/2+principalPoint.x*L/2`, and
`cy=H/2-principalPoint.y*L/2`. This is an inference from the read projection and
coordinate conversion functions, checked using independent projected points.

For portrait images, blindly copying the stored `verticalFieldOfView` would
change framing. The inspected upstream portrait fixture contains a 1728×2592
image and a normalized field of about 1.16259 radians; its separately stored
vertical field is about 1.55622 radians. CINEMATICUM derives the actual vertical
field from the projection's focal length and image height. The mathematical
tests cover portrait, landscape and square images, including shifted principal
points and camera roll. Upstream fixture bytes were inspected for the format
audit; they are not vendored or used as CINEMATICUM production assets.

Reference distance units are not automatically converted. If a reference axis
was not set, the translation scale is arbitrary. The user selects the conversion
to scene units and sees that limitation in the import review.

### COLMAP poses need an explicit change of camera convention

`images.txt` supplies a Hamilton quaternion in `(qw,qx,qy,qz)` order and a
world-to-camera translation. The camera center is `-Rᵀt`. COLMAP camera axes are
right, down and forward, whereas the scene camera is right, up and backward.
The importer converts the camera axes and preserves the reconstruction's world
axes unless the user explicitly chooses the Y-up conversion.

The text reader preserves noncontiguous IDs and names containing spaces. It
consumes the observation line after every pose, including an empty line. It
validates those observations but does not import point clouds or resolve image
paths. A registered image pose is selected by the user; file order is not
treated as an animation clock. The two legacy-compatible camera/image text
files are used; rig graphs, frame grouping and binary model files are outside
this importer.

`SIMPLE_PINHOLE` accepts `f,cx,cy`; `PINHOLE` accepts `fx,fy,cx,cy`. Unequal focal
lengths and off-center principal points are preserved. Radial, OpenCV, fisheye,
skew and every other camera model are rejected, including a non-pinhole model
whose distortion coefficients happen to be zero. The user must supply a
supported undistorted model. No coefficient is silently discarded.

### OpenCV and Lensfun coefficients are not interchangeable

OpenCV's source separates a pinhole transform from radial, tangential,
rational, thin-prism and tilted-sensor terms. Its inverse is iterative. The
independent CINEMATICUM numerical helper currently implements only five-term
Brown-Conrady mapping, with coefficient order `[k1,k2,p1,p2,k3]` and normalized
right/down camera coordinates. The inverse uses an analytic Jacobian with
damped Newton steps. A result must reproject within `1e-10` normalized units;
singular/folded local mappings and non-convergence are errors. This helper is
not wired as a video filter, is not a calibration estimator, and does not make
distorted cameras admissible to the scene.

Lensfun additionally owns a lens database, focal-length/crop interpolation,
vignetting, transverse chromatic aberration, multiple projection models and
perspective correction. Its normalization distinguishes focal-length units,
Hugin units and corner-based vignetting units. Its poly3 and PTLens conversion
rescales coefficients to preserve focal length. Its image correction API
produces source lookup coordinates; applying the forward distortion mapping to
an output grid is part of inverse image sampling. Treating Lensfun's `k1` as an
OpenCV `k1` without converting calibration geometry would therefore be wrong.
No Lensfun profile is currently accepted, and no database coverage is claimed.

## Canonical contract and own interface

`camera_io.import_camera(payload, width, height)` returns reviewable candidates
and does not mutate a project or access the filesystem. Each candidate contains
`id`, `name`, source dimensions, `camera`, and source provenance. Binary and JSON
fSpy inputs retain a SHA-256 of the exact supplied bytes. COLMAP candidates
retain both exact text hashes, camera/image IDs, intrinsics, scale and up-axis.

| Canonical camera field | Meaning |
| --- | --- |
| `position` | Camera center in the scene's Z-up world |
| `target` | A point one scene unit along the forward direction |
| `fov` | Vertical field of view, degrees |
| `roll` | Degrees about local positive Z, the backward optical axis |
| `shift_x` | `cx/W−0.5` |
| `shift_y` | `0.5−cy/H` |
| `focal_ratio` | `fx/fy` |
| `keyframes` | Empty for a selected still-camera pose |

The existing camera projection, inspector and Blender compiler consume these
fields. The own `camera-io-ui.js` dialog reads actual selected files, submits
original JSON text or binary bytes, lets the user choose a registered pose,
discloses replacement of camera animation, and applies a single undoable
replacement through the owning app bridge. It guards project identity and
revision before and after asynchronous reads, backend requests and applying.
It does not launch fSpy, COLMAP, OpenCV or Lensfun.

Source and project image aspect must agree within relative `1e-6`; uniform
resizing is supported. The importer does not guess cropping, letterboxing,
anamorphic de-squeezing, source gravity or scene scale. A Y-up selection maps
`[x,y,z]` to `[x,−z,y]` and is a proper rotation, not a reflection. Apply the same
axis and scale choices to imported geometry.

Admission limits: binary fSpy 5 MiB; camera JSON 1 MiB; each COLMAP text 3 MiB;
128 cameras/registered poses; 100,000 observations. JSON duplicate keys,
non-finite values and excessive nesting are errors. Source labels are never
opened as paths. Scene positions/targets must remain within ±1000; imported
vertical field is 10–100 degrees, focal ratio 0.25–4, and normalized principal
shifts ±2. Bounds reject an import; they never clamp its calibration silently.

## Verification and remaining work

`python3 -m unittest -v test_camera_io` passed 25 tests in this development
workspace. The suite independently reprojects 3D points through source fSpy
matrices and Rodrigues-generated COLMAP poses. It executes the actual UI file
transport in Node and then the Python parser, and executes the actual scene
editor's JavaScript view-projection matrix. It also covers source hashes,
portrait images, nonzero roll, shifted/unequal intrinsics, Y-up scaling, empty
observation lines, duplicate JSON, binary truncation, unsupported models and
Brown inverse residuals. These mathematical and transport tests do not stand
in for native render or UI proof.

`verify_camera_native.py --output NEW_DIRECTORY --case CASE` is the separate
native acceptance harness. Each case imports through actual HTTP in an isolated
workspace, verifies application-token enforcement and read-only review, renders
a real one-frame test movie, then reopens the saved `.blend` and compares
Blender-projected pixels against independent source expectations. Cases are
`fspy_landscape`, `fspy_portrait`, and `colmap_shifted_anisotropic`.

`test_camera_import_ui_macos.py --binary SMOKE_HELPER --output DIRECTORY` runs
the actual shipped modal and FileList flow in WKWebView, including failed import,
fSpy apply/undo/redo, COLMAP pose selection, replacement of keys, saving and
preservation of unrelated scene settings. Its report and screenshot are the
native UI evidence; merely having the harness is not a passing result.

Still absent: fSpy's interactive vanishing-line solver; feature extraction,
matching, bundle adjustment and reconstruction; calibrated plate/background
compositing; distortion-aware scene projection/rendering; dense point clouds;
rig/timing import; lens profiles and image remapping; optical element tracing,
chromatic dispersion and lens-design optimization. Those remain distinct
engineering work rather than renamed controls.

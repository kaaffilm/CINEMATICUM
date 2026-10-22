# Physical scene authoring: source study and implemented boundary

Review date: 2026-10-21. This review inspected selected implementation files at
the exact revisions below. It is a source-level comparison of camera, material,
light transport and scene-data contracts, not a claim to have reproduced all of
these projects. The changes run in CINEMATICUM's own scene editor and existing
headless Blender/Cycles renderer. Mitsuba, PBRT, Gaffer, Optiland and ray-optics
are not installed engines or hidden launchers in this release. No upstream
implementation was copied into the application.

## Reproducible source evidence

| Project / pinned commit | Inspected implementation | Git blob SHA | Contract observed |
|---|---|---|---|
| Mitsuba 3 `aa01500f57770a4ef0b067693cae08b3e8a2ac73` | [src/sensors/thinlens.cpp](https://github.com/mitsuba-renderer/mitsuba3/blob/aa01500f57770a4ef0b067693cae08b3e8a2ac73/src/sensors/thinlens.cpp) | `c1e4cbd21f23702674bfea4494ec001ccf3953e7` | Explicit FOV axis, focus plane, aperture sampling, camera transform and principal-point offsets. |
| Same Mitsuba revision | [src/bsdfs/principled.cpp](https://github.com/mitsuba-renderer/mitsuba3/blob/aa01500f57770a4ef0b067693cae08b3e8a2ac73/src/bsdfs/principled.cpp) | `41dbb8bd9acd922be7c12deaa0d62db794ca5d3b` | Separate reflective/transmissive lobes, IOR, roughness and metallic inputs; mutually exclusive redundant optical controls. |
| Same Mitsuba revision | [src/integrators/path.cpp](https://github.com/mitsuba-renderer/mitsuba3/blob/aa01500f57770a4ef0b067693cae08b3e8a2ac73/src/integrators/path.cpp) | `459e2d05893cf8694ab56c1652f3319fbb117104` | Path state, BSDF/emitter PDFs, throughput, direct-emission accumulation and MIS weighting. |
| PBRT v4 `b4ce9687e6c695f5582997c61b0c66cf064bdb4a` | [src/pbrt/cameras.cpp](https://github.com/mmp/pbrt-v4/blob/b4ce9687e6c695f5582997c61b0c66cf064bdb4a/src/pbrt/cameras.cpp) | `6b8fb3c92b39c1b5a7200a3514defe9d80e1b347` | Perspective thin-lens rays, focal plane and lens radius; a separate realistic camera with optical interfaces, film size, aperture stops and thick-lens focusing. |
| Gaffer `5fa96838ea3adc2e7c1672169ed5ae89e357f3e6` | [src/GafferScene/Camera.cpp](https://github.com/GafferHQ/gaffer/blob/5fa96838ea3adc2e7c1672169ed5ae89e357f3e6/src/GafferScene/Camera.cpp) | `0f93cf7dbfeb57bded94c6bc2dd668898489185b` | Camera plugs for aperture, focal length, FOV, f-stop, focus distance, offsets and render overrides. |
| Same Gaffer revision | [include/GafferScene/ScenePlug.h](https://github.com/GafferHQ/gaffer/blob/5fa96838ea3adc2e7c1672169ed5ae89e357f3e6/include/GafferScene/ScenePlug.h) | `1bd16a112c4a9a5fa96652a9a8ed521a3396fd0e` | Separate location bounds, transforms, attributes, objects and children; global options/sets; path-context evaluation. |
| Same Gaffer revision | [src/Gaffer/Context.cpp](https://github.com/GafferHQ/gaffer/blob/5fa96838ea3adc2e7c1672169ed5ae89e357f3e6/src/Gaffer/Context.cpp) | `4f29249d17fc97ccc21a0c70bee5b4e516029985` | Typed context values with equality, copying and hashes. |
| Optiland `eda2917a794eb1e200557d865e475e02a4d7534a` | [optiland/optic/optic.py](https://github.com/optiland/optiland/blob/eda2917a794eb1e200557d865e475e02a4d7534a/optiland/optic/optic.py) | `88c36e2c6635c2169ae3526455246fc508d2fd11` | Optical system owns surface, field and wavelength groups, paraxial/aberration models, ray tracer, solves and pickups. |
| Same Optiland revision | [optiland/raytrace/real_ray_tracer.py](https://github.com/optiland/optiland/blob/eda2917a794eb1e200557d865e475e02a4d7534a/optiland/raytrace/real_ray_tracer.py) | `6c449fe347b59112ec64fe8eb91ec55337183f24` | Pupil/field sampling and explicit wavelength; ray aiming; traversal through actual optical surfaces; optional polarization handling. |
| ray-optics `e25bc579116d31ed97fa1632f871e2801e8e956e` | [src/rayoptics/seq/sequential.py](https://github.com/mjhoptics/ray-optics/blob/e25bc579116d31ed97fa1632f871e2801e8e956e/src/rayoptics/seq/sequential.py) | `ad659e0884b153bc3884b86eaca1ebeba3101487` | Explicit interfaces and gaps, stop surface, transforms, wavelength-index arrays and sequence persistence. |
| Same ray-optics revision | [src/rayoptics/raytr/raytrace.py](https://github.com/mjhoptics/ray-optics/blob/e25bc579116d31ed97fa1632f871e2801e8e956e/src/rayoptics/raytr/raytrace.py) | `cd65c677e37afab9c20c595953319c3568641b57` | Refraction/reflection and sequential intersection/optical-action evaluation. |
| Blender `1f7f1f75140c2832ec922210f29dfffbfaee3b73` | [source/blender/makesrna/intern/rna_camera.cc](https://github.com/blender/blender/blob/1f7f1f75140c2832ec922210f29dfffbfaee3b73/source/blender/makesrna/intern/rna_camera.cc) | `e597338258fbcd97b02a851211344f6deec42e39` | Actual runtime property bounds: focal length minimum 1 mm, aperture rotation ±π, circular or polygonal aperture, sensor dimensions and focus distance. |
| Same Blender revision | [source/blender/makesrna/intern/rna_scene.cc](https://github.com/blender/blender/blob/1f7f1f75140c2832ec922210f29dfffbfaee3b73/source/blender/makesrna/intern/rna_scene.cc) | `1b135ccbd260b716d92ca97b90208beddebcf2ca` | Output pixel-aspect properties explicitly clear the animatable flag. The calibrated focal ratio must remain static for retained-source replay. |

The Blender source pin is the API contract reviewed; native acceptance records
the installed Blender version separately. A repository head is never presented
as the installed binary version.

## Findings that changed CINEMATICUM

### A lens needs a physical scale and an unambiguous projection

The previous scene recipe had only vertical FOV, position and target. Its saved
Blender camera always used a 24 mm vertical sensor, with no authored DOF. The
source review separates the projection from aperture sampling. Mitsuba's thin
lens projects a raster sample to a focal plane, samples an aperture point, then
aims the ray at that focal-plane position. PBRT's perspective camera follows the
same thin-lens distinction. CINEMATICUM therefore now authors sensor height,
focal length, focus distance, f-stop and aperture geometry while preserving the
existing vertical-FOV animation contract.

The authoritative saved projection is still `camera.fov` in vertical degrees:

```text
focal_length_mm = sensor_height_mm / (2 * tan(vertical_fov / 2))
```

The UI's editable focal-length field converts to this FOV. Changing sensor
height retains framing and changes physical lens/aperture scale. A JSON import
may provide `focal_length_mm`; validation derives FOV when absent, accepts a
matching supplied FOV, and rejects contradictory values. Normalization removes
the redundant focal-length alias. Both values cannot drift independently.
Every authored camera key is checked against Blender's 1 mm focal-length
minimum. Unsupported combinations fail before a render is launched.

The sensor's active vertical gate defaults to 24 mm, preserving existing v0.5
framing. One scene unit is one metre. Focus distance is the optical-axis
distance to the focus plane. A “Focus at look-at point” action writes the
current camera-to-target distance, including an animation key when appropriate.
F-stop controls DOF; it does not silently apply a photographic exposure change.
ISO, shutter exposure and lens transmission measurements remain outside this
camera model.

### Camera calibration must survive both the viewport and the saved scene

The common calibrated camera contract uses:

| Field | Meaning | Accepted range |
|---|---|---|
| `fov` | Vertical field in degrees | 10–100 |
| `sensor_height_mm` | Active sensor height, static | 1–100 mm, with derived focal length ≥1 mm |
| `roll` | Rotation about camera local +Z/backward axis | −3600…3600° |
| `shift_x` | `cx / width − 0.5` | −2…2 |
| `shift_y` | `0.5 − cy / height` | −2…2 |
| `focal_ratio` | Calibrated pixel focal ratio `fx / fy`, static | 0.1–10 |
| `focus_distance` | Camera-to-focus-plane distance | 0.01–10000 m |
| `f_stop` | Thin-lens f-number | 0.1–128 |
| `dof_enabled` | Actual path-traced depth of field | Boolean |
| `aperture_blades` | Zero is circular; otherwise polygonal | 0 or 3–16 |
| `aperture_rotation` | Polygon rotation | −180…180° |
| `aperture_ratio` | Aperture shape ratio | 0.1–10 |

Position, target, FOV, roll, shifts, focus distance and f-stop share
the existing complete-pose keys and outgoing easing. Sensor height, aperture
shape, focal ratio and the DOF switch are static scene settings. Attempts to
place `focal_ratio` in animation keys are rejected explicitly. The UI uses the same
projection for rendering the viewport, camera guides and pointer picking.

For output `W×H`, `fy = H / (2 tan(fov/2))`, `fx = fy * focal_ratio`,
`cx = W(0.5 + shift_x)` and `cy = H(0.5 − shift_y)`. The camera basis uses Z-up,
falling back to Y-up near a vertical optical axis, followed by local-axis roll.
This convention is shared with the separate calibrated-camera importer.

Blender receives vertical sensor fit. Its horizontal shift is
`−shift_x * (W/H) / focal_ratio`; its vertical shift is `−shift_y`. Render pixel
aspect represents `fx/fy` during camera ray generation. The generated movie
explicitly uses square-pixel display aspect: calibration has already been
applied to the sampled image, so it must not stretch the movie again.
The source inspection caught Blender's non-animatable pixel-aspect restriction;
the application enforces it instead of storing unplayable ratio animation.

Camera quaternion, lens, projection and focus are baked at integer frames in
the retained `.blend`. Translation keeps the authored eased curves. The camera
aim marker remains an independently animated object; the camera no longer has
a constraint that would discard authored roll. Reopening the source reproduces
rendered frame poses without executing CINEMATICUM's generated Python again.
This guarantees frame replay, not an untested continuous/subframe camera solver.

### Material properties must reach actual shading

The former material exposed base colour, metallic and roughness. The new own
inspector adds transmission, IOR, emission colour and emission strength, plus
editable solid, metal, glass and emitter presets. A preset is one project undo
operation. These values reach Blender's Principled BSDF inputs, including the
Blender 3/4+ input-name compatibility mapping. Colour swatches are converted from
sRGB to scene-linear RGB before assigning material and light inputs.

Transmission/roughness/metallic are bounded to 0–1, IOR to 1–4, and emission
strength to 0–1000. Unknown shader programs, expressions, texture paths and
arbitrary node code are rejected. Glass uses the authored geometry's actual
thickness. The WebGL display is a solid shading approximation with emission and
Fresnel response; refraction, depth of field and indirect illumination are
evaluated in the rendered scene. The UI says this explicitly.

Mitsuba's inspected Principled implementation has additional lobes and a
differentiable parameter system. Its source review informed the separation of
IOR, transmission and emissive response, not a claim to reproduce its BSDF or
rendering engine. CINEMATICUM does not yet expose arbitrary shader graphs,
spectral dispersion, textured emission, volume absorption or material animation.

### Path controls must affect light transport

The scene now retains a `render` object containing total, diffuse, glossy,
transmission and transparent bounce limits, denoising and the sampling seed.
The own “Light paths & sampling” inspector writes these properties into the
project, and the renderer assigns them to `scene.cycles`. Limits are integers
0–64; the seed is 0–2147483647. Samples remain 4–256 through the existing render
bar. Per-ray limits are also constrained by the renderer's total path depth.

These controls expose actual Cycles behavior. The reviewed Mitsuba integrator
tracks throughput and emission/BSDF sampling probabilities, demonstrating why a
render setting must reach the light-transport engine. CINEMATICUM has not
implemented a second MIS integrator, spectral engine, differentiable integrator
or GPU scheduling system by adding these controls.

## Explicit comparison and remaining boundaries

| Reference system | Implemented CINEMATICUM result | Remaining work |
|---|---|---|
| Mitsuba thin-lens and Principled contracts | Physical camera/DOF, calibrated projection, bounded glass/emission inputs and path limits in own UI; real Cycles output | Mitsuba execution/import/export, spectral/polarized rendering, differentiation, full BSDF/integrator library |
| PBRT perspective/realistic cameras | Physical sensor/FOV/focus/aperture with frame replay | Multi-element lens prescription, spherical-interface tracing, exit-pupil sampling, measured aperture maps, thick-lens focus, realistic aberrations |
| Gaffer camera and scene dataflow | Saved structured scene, separate camera/material/render settings, undoable authoring and owned render jobs | Gaffer's path-context scene evaluation, plug graph, expression/caching model, sets/collections, procedural scene assembly and renderer dispatch |
| Optiland optical system and real-ray tracer | Explicit physical camera units and lens controls in the film scene | Surface prescription editor, glass/wavelength catalogues, actual optical optimization, pupil aiming, polarization, spot/MTF/wavefront/aberration analysis |
| ray-optics sequential model and ray tracer | Camera settings with stable serialization and actual render behavior | Interfaces/gaps/stop surfaces, sequential ray tracing, wavelength-dependent materials, optical analysis and lens-design document interchange |

PBRT's realistic camera and the two optical-design systems model a sequence of
physical optical surfaces. A thin-lens f-stop control is not that system. The
next optical-design implementation requires an actual surface prescription,
ray-intersection/refraction evaluator and numerical comparison against known
lens cases. That work remains explicit rather than being advertised as a
disabled “optics engine” menu item.

## Acceptance and evidence

`python3 -m unittest test_scene -v` covers legacy normalization, single-authority
physical lens conversion, conflicting values, bounds, independent JSON
roundtrips and shared Python/JavaScript camera interpolation. Syntax validation
also compiles the generated Blender script and the UI module. These unit checks
are not used as proof that Blender rendered the physical effects.

Two separate native acceptance workflows exercise the implementation:

1. `test_physical_scene_ui_macos.py --binary <compiled SmokeTest> --output <dir>`
   runs `macos/PhysicalSceneSmoke.js` in actual WKWebView. It edits the own
   material/lens/DOF/path controls, checks undo/redo, authors focus/roll keys,
   saves the project and independently checks the stored recipe. It captures a
   native screenshot. It does not claim a rendered film.
2. `test_physical_scene_blender.py --output <dir>` renders an authored two-frame
   scene, reopens its retained `.blend` in another Blender process, inspects
   actual camera/material/path values and tests projected world points against
   an independent pinhole formula. The second process also renders the same
   emissive-bar geometry with DOF on/off, reads saved PNG pixels, measures image
   differences and tests loss of high-frequency detail. The `.blend`, movie,
   comparison PNGs and numerical report are retained as labelled ENGINE TEST
   evidence.

The earlier `test_scene_motion_blender.py` replay sampler now includes the
expanded camera channels. Its position/lens/light easing checks remain intact.
Native execution results belong in the release verification evidence; a skipped
test is explicitly reported as skipped and is never counted as rendering proof.

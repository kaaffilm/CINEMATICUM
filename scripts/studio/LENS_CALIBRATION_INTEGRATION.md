# Lens calibration application integration

Studio tools → Measure lens calibration submits `calibrate_checkerboard` through
the authenticated project-owned queue. Opening the dialog saves pending edits
first. The result retains the input photograph identities and scientific
artifacts in Saved results. All six artifacts are included in project archives
and remain readable after restoration without importing a transient job
database. The optional Tracking runtime is still required to perform new work;
opening or restoring a project does not run that runtime.

This app bridge is **export-only**. It deliberately supplies no
`applyLensProfile` callback, so the dialog's Apply button remains hidden and no
timeline clip, project revision or undo history is changed by a measurement.
Matching image dimensions alone does not prove that a selected clip shares the
calibration photographs' physical camera, fixed focus/zoom, sensor crop or pixel
orientation. The normalized Brown proposal in provenance is available for
explicit review and downstream use. A future direct-apply bridge must bind the
selected clip and source geometry, verify the current project revision, and
commit one validated undoable edit; this integration makes no such claim.

The application process imports no OpenCV/NumPy. The installer includes
`lens_calibration.py` and `lens_calibration_worker.py`; it copies and hashes the
web control with the other web assets. Development `test-deps` and
`test-runtime` directories are not distributable dependencies.

`test_lens_calibration_integration.py` exercises the actual loopback HTTP
routes, authentication, queue validation/cancellation, saved-artifact hashes,
and project archive round-trip. Its inert transport inventory never represents
a successful lens inference. `test_lens_calibration_smoke.py` separately runs
real SB corner detection and numerical fit/covariance tests in the selected
isolated interpreter. Each smoke case can run independently with
`--engine-case detector` or `--engine-case covariance`. These generated ENGINE
TESTS establish engine behavior within their bounds; physical-camera capture
acceptance and rolling-shutter timing estimation remain open.

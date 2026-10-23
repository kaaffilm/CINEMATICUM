# Measured checkerboard lens calibration

The `calibrate_checkerboard` operation detects actual target corners in admitted
opaque eight-bit PNG/JPEG photographs and fits the fixed-optics Brown model.
The main application imports no NumPy/OpenCV; the existing isolated Tracking
runtime executes the detector, pose solver and calibration. Inputs must retain
their admitted bytes and uniform stored pixel dimensions. EXIF orientation is
not applied: calibration and observations use the stored pixel raster.

The capture contract is 12–40 views, a rigid flat checkerboard with known inner
corner rows/columns and physically measured square pitch, fixed zoom/focus,
at most 2048 pixels per edge/four megapixels per photograph and 128 megapixels
in aggregate. Image count alone does not establish identifiability. The fit
checks target coverage, pose diversity, reprojection error and local intrinsic
information after eliminating each board pose. Parallel target poses and
rank-deficient/ill-conditioned data are refused. Photographs with no complete
detected board are rejected explicitly; omission requires an explicit recipe
choice and every input remains accounted for.

The worker uses OpenCV's subpixel chessboard SB detector. Calibration points
are contiguous float32 arrays. Intrinsics/distortion are float64. Two radial
terms fix k3 to zero; three terms estimate k3 as well. Distortion order is
`[k1, k2, p1, p2, k3]`. The result preserves the training fit and evaluates
independent held-out images using pose estimation with those fixed intrinsics;
there is no later all-view refit that erases the holdout distinction.

OpenCV's extended calibration API returns marginal standard deviations, not a
full covariance matrix. The worker separately constructs the shared-intrinsic
information matrix from `projectPoints` Jacobians after eliminating per-view
pose nuisance parameters. Normalized parameter scales are used for rank and
conditioning diagnostics, then covariance is restored to pixel/coefficient
units. Covariance is conditional on the fixed target, constant lens, local
linearization and stated independent pixel-noise assumptions. It does not
include target printing/flatness error, square-pitch uncertainty, optical drift
or an independently measured physical accuracy guarantee. Fixed parameters are
labelled fixed rather than assigned a claim of perfect certainty.

The application independently reprojects every published corner using the
reported physical target, camera matrix, Brown coefficients and board pose. It
checks the reported RMS, proper rotations, input/holdout inventory, covariance
order/symmetry/positive definiteness and declared information rank/condition.
All scientific outputs and their source inputs are hashed before immutable
publication. The owned worker supports cancellation and a 15-minute deadline;
published output is bounded to 128 MiB.

The result includes `calibration.json`, `observations.json`, `opencv.yml`, actual
detected-corner previews and source-bound provenance. A compositor proposal
normalizes fx/cx by image width and fy/cy by image height. Both OpenCV and the
existing Brown sampler use zero-based integer pixel centers, so this conversion
adds no half-pixel shift. Applying the proposal requires matching optics,
aspect ratio and pixel orientation; only uniform resolution scaling preserves
the normalization. Existing compositor coefficient, invertibility and raster
bounds remain enforced. A measured scientific calibration is retained even if
the editing compositor cannot represent that lens safely.

Static target views do not estimate rolling-shutter timing in this workflow.
A timing estimator would require its own motion/scene model, native sensor-row
mapping and identifiable timing parameters. For example, under
`t = t_frame + delay + (raw_row - reference_row) * seconds_per_row`, zero motion
provides no timing information; unconstrained image velocity can confound its
product with row time. This does not claim that all target-free rolling-shutter
self-calibration is impossible. No such trajectory/scene estimator is
implemented or accepted here.

Primary API references:

- https://github.com/opencv/opencv/blob/4.12.0/modules/calib3d/include/opencv2/calib3d.hpp
- https://github.com/opencv/opencv/blob/4.12.0/modules/calib3d/src/calibration.cpp
- https://github.com/opencv/opencv/blob/4.12.0/modules/calib3d/src/chessboard.cpp
- https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr98-71.pdf
- https://www.cv-foundation.org/openaccess/content_cvpr_2013/papers/Oth_Rolling_Shutter_Camera_2013_CVPR_paper.pdf

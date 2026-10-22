"""Measured HDR photograph alignment/response/deghosting and planar stitching.

OpenCV 4.11 APIs: https://docs.opencv.org/4.11.0/d6/df5/group__photo__hdr.html
and https://docs.opencv.org/4.11.0/d1/de0/tutorial_py_feature_homography.html
This is a bounded static-camera/planar workflow, not optical-flow reconstruction
or a spherical panorama solver. Receipts retain the measured geometry, response
table, coverage, residuals and every reference-frame fallback.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from imaging import MAX_PIXELS, _hash_file, _json_bytes, _owned, validate_imaging_recipe
from still_photography import ANALYSIS_EDGE, MAX_IMAGE_PIXELS, MAX_STACK_PIXELS


def modules():
    try:
        import numpy as np
        import cv2 as cv
    except ImportError as exc:
        raise ValueError("Photograph geometry requires NumPy and OpenCV in the isolated tracking runtime.") from exc
    cv.setNumThreads(2)
    cv.setRNGSeed(0)
    return np, cv


def transfer(rgb, name, np):
    if name == "linear":
        return rgb
    if name == "srgb":
        return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    if name == "rec709":
        return np.where(rgb < .081, rgb / 4.5, ((rgb + .099) / 1.099) ** (1 / .45))
    raise ValueError("Choose a known transfer or fit the bracket response.")


def photograph(rgba, np):
    if (rgba.ndim != 3 or rgba.shape[2] != 4 or not np.isfinite(rgba).all()
            or np.any(rgba[..., 3] < .99999)):
        raise ValueError("Enhanced photographs must contain finite opaque RGBA pixels.")
    if float(rgba[..., :3].min()) < -.00001 or float(rgba[..., :3].max()) > 1.00001:
        raise ValueError("Photograph captures must be normalized between zero and one.")
    if min(rgba.shape[:2]) < 32 or rgba.shape[0] * rgba.shape[1] > MAX_IMAGE_PIXELS:
        raise ValueError("Enhanced photograph inputs need at least 32 pixels per dimension and at most 8.4 million pixels.")
    return np.clip(rgba[..., :3], 0, 1)


def features(rgb, np, cv):
    height, width = rgb.shape[:2]
    scale = min(1., ANALYSIS_EDGE / max(width, height))
    small = cv.resize(rgb, (round(width * scale), round(height * scale)), interpolation=cv.INTER_AREA) if scale < 1 else rgb
    gray = cv.cvtColor(np.rint(small * 255).astype(np.uint8), cv.COLOR_RGB2GRAY)
    # A global monotone remapping reduces dependence on bracket exposure while
    # preserving feature geometry. It is never used for output image pixels.
    gray = cv.equalizeHist(gray)
    detector = cv.SIFT_create(nfeatures=6000, contrastThreshold=.015, edgeThreshold=12)
    keys, descriptors = detector.detectAndCompute(gray, None)
    if descriptors is None or len(keys) < 12:
        raise ValueError("A photograph has too little distinct texture for measured alignment.")
    return keys, descriptors, scale


def corners(shape, np):
    height, width = shape[:2]
    return np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float64)


def project(points, matrix, np):
    h = np.column_stack((points, np.ones(len(points)))) @ matrix.T
    if not np.isfinite(h).all() or np.any(np.abs(h[:, 2]) < 1e-6) or np.any(h[:, 2] * h[0, 2] <= 0):
        raise ValueError("Measured photograph geometry crosses the projective horizon.")
    return h[:, :2] / h[:, 2:3]


def checked_geometry(matrix, source_shape, np, cv):
    if matrix is None or matrix.shape != (3, 3) or not np.isfinite(matrix).all() or abs(matrix[2, 2]) < 1e-9:
        raise ValueError("Photograph alignment did not measure a finite homography.")
    matrix = matrix / matrix[2, 2]
    warped = project(corners(source_shape, np), matrix, np)
    if not cv.isContourConvex(warped.astype(np.float32)):
        raise ValueError("Measured photograph geometry folds the input image.")
    area = abs(cv.contourArea(warped.astype(np.float32)))
    height, width = source_shape[:2]
    if not .2 <= area / ((width - 1) * (height - 1)) <= 5:
        raise ValueError("Photograph geometry exceeds the supported planar scale range.")
    return matrix


def measure(source, target, source_features, target_features, model, np, cv):
    sk, sd, ss = source_features
    tk, td, ts = target_features
    matches = cv.BFMatcher(cv.NORM_L2).knnMatch(sd, td, k=2)
    good = sorted((a for pair in matches if len(pair) == 2 for a, b in [pair] if a.distance < .72 * b.distance),
                  key=lambda match: (match.distance, match.queryIdx, match.trainIdx))
    # Repeated patterns must not count multiple source observations as the
    # same independently measured target feature.
    unique, used = [], set()
    for match in good:
        if match.trainIdx not in used:
            used.add(match.trainIdx)
            unique.append(match)
    if len(unique) < 12:
        raise ValueError("Photographs do not have twelve distinct feature matches in their overlap.")
    a = np.array([sk[m.queryIdx].pt for m in unique], np.float64) / ss
    b = np.array([tk[m.trainIdx].pt for m in unique], np.float64) / ts
    threshold = 2.5 / min(ss, ts)
    if model == "translation":
        delta = b - a
        shift = np.median(delta, axis=0)
        inliers = np.linalg.norm(delta - shift, axis=1) <= threshold
        if np.count_nonzero(inliers) < 10:
            raise ValueError("The photographs do not share one supported translation.")
        shift = np.median(delta[inliers], axis=0)
        matrix = np.array([[1, 0, shift[0]], [0, 1, shift[1]], [0, 0, 1]], np.float64)
    else:
        matrix, selected = cv.findHomography(a, b, cv.RANSAC, threshold, maxIters=5000, confidence=.999)
        if selected is None:
            raise ValueError("The photographs do not share a measurable projective plane.")
        inliers = selected.ravel().astype(bool)
    matrix = checked_geometry(matrix, source.shape, np, cv)
    error = np.linalg.norm(project(a, matrix, np) - b, axis=1)
    inliers &= error <= threshold
    count = int(np.count_nonzero(inliers))
    if count < 10 or count / len(unique) < .35:
        raise ValueError("Photograph alignment has too few geometrically consistent matches.")
    coverage = []
    for points, shape in ((a[inliers], source.shape), (b[inliers], target.shape)):
        area = cv.contourArea(cv.convexHull(points.astype(np.float32)))
        coverage.append(float(area / (shape[0] * shape[1])))
    if min(coverage) < .025 or float(np.median(error[inliers])) > 1.5 / min(ss, ts):
        raise ValueError("Photograph matches are too concentrated or inaccurate for reliable geometry.")
    return matrix, {"matches": len(unique), "inliers": count, "inlier_fraction": count / len(unique),
                    "median_error_pixels": float(np.median(error[inliers])),
                    "max_inlier_error_pixels": float(np.max(error[inliers])),
                    "feature_hull_fraction": coverage, "analysis_scales": [ss, ts]}


def align_brackets(images, recipe, np, cv):
    ids = [b["asset_id"] for b in recipe["brackets"]]
    reference = ids.index(recipe["reference_asset_id"])
    shape = images[reference].shape
    if any(image.shape != shape for image in images):
        raise ValueError("HDR brackets must have identical image dimensions.")
    height, width = shape[:2]
    aligned, valid, records = [], [], []
    model = recipe["alignment"]
    target_features = features(images[reference], np, cv) if model != "none" else None
    for index, source in enumerate(images):
        details, matrix = {}, np.eye(3, dtype=np.float64)
        if model != "none" and index != reference:
            matrix, details = measure(source, images[reference], features(source, np, cv), target_features, model, np, cv)
        moved = cv.warpPerspective(source, matrix, (width, height), flags=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT)
        mask = cv.warpPerspective(np.ones((height, width), np.float32), matrix, (width, height),
                                  flags=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT) > .99999
        if np.count_nonzero(mask) < width * height * .5:
            raise ValueError("A bracket has less than fifty percent overlap with its reference photograph.")
        aligned.append(moved)
        valid.append(mask)
        records.append({"asset_id": ids[index], "source_to_reference": matrix.tolist(),
                        "valid_pixels": int(np.count_nonzero(mask)), **details})
    common = np.logical_and.reduce(valid)
    if np.count_nonzero(common) < width * height * .5:
        raise ValueError("Bracket alignment leaves less than fifty percent shared image coverage.")
    return aligned, common, reference, records


def isotonic(values, np):
    # Equal-weight pool-adjacent-violators projects a measured noisy inverse
    # response onto the physical nondecreasing constraint; it fits no gamma.
    levels, counts = [], []
    for value in values:
        levels.append(float(value))
        counts.append(1)
        while len(levels) > 1 and levels[-2] > levels[-1]:
            count = counts[-2] + counts[-1]
            merged = (levels[-2] * counts[-2] + levels[-1] * counts[-1]) / count
            levels[-2:] = [merged]
            counts[-2:] = [count]
    return np.repeat(np.asarray(levels), counts)


def calibrate(images, times, mask, reference, np, cv):
    locations = np.flatnonzero(mask)
    if locations.size < 256:
        raise ValueError("Measured camera response needs at least 256 shared static pixels.")
    # Select actual paired source samples across the reference brightness range.
    # Arrange them as a grid solely because CalibrateDebevec samples image grids.
    brightness = np.mean(images[reference], axis=-1).ravel()[locations]
    ordered = locations[np.argsort(brightness, kind="stable")]
    selected = ordered[np.linspace(0, len(ordered) - 1, 256).astype(np.int64)]
    samples = [np.rint(image.reshape(-1, 3)[selected] * 255).astype(np.uint8).reshape(16, 16, 3) for image in images]
    for channel in range(3):
        codes = np.concatenate([sample[..., channel].ravel() for sample in samples])
        if len(np.unique(codes[(codes > 5) & (codes < 250)])) < 24:
            raise ValueError("Camera response fitting needs a wider range of unsaturated RGB capture levels.")
    measured = cv.createCalibrateDebevec(samples=256, lambda_=20., random=False).process(
        samples, times=np.asarray(times, np.float32)).reshape(256, 3)
    if not np.isfinite(measured).all() or np.min(measured) <= 0 or np.max(measured) > 1e12:
        raise ValueError("The measured camera response is nonfinite or ill-conditioned.")
    log_response = np.log(measured.astype(np.float64))
    projected = np.stack([isotonic(log_response[:, channel], np) for channel in range(3)], axis=-1)
    projection_delta = float(np.max(np.abs(projected - log_response)))
    projected -= projected[128]
    response = np.exp(projected).astype(np.float32)
    exposures = []
    for sample, exposure in zip(samples, times):
        encoded = sample.reshape(-1, 3)
        exposures.append(np.stack([np.log(response[encoded[:, channel], channel]) for channel in range(3)], axis=-1) - math.log(exposure))
    logs = np.stack(exposures)
    weights = np.stack([np.minimum(sample.reshape(-1, 3), 255 - sample.reshape(-1, 3)).astype(np.float64) for sample in samples])
    weights[weights <= 5] = 0
    denominator = np.sum(weights, axis=0)
    mean = np.sum(weights * logs, axis=0) / np.maximum(denominator, 1e-9)
    residual = np.abs(logs - mean) / math.log(2)
    errors = residual[(weights > 0) & (denominator[None] > 0)]
    metrics = {"method": "OpenCV CalibrateDebevec; monotone log-response projection",
               "sample_count": 256, "sample_positions_sha256": __import__("hashlib").sha256(selected.astype("<i8").tobytes()).hexdigest(),
               "calibration_precision": "256 encoded levels per RGB channel; interpolated onto original float capture values",
               "normalization": "inverse_response[128] = 1 independently in R, G and B; absolute radiometry and white balance are not calibrated",
               "lambda": 20., "monotone_projection_max_log_change": projection_delta,
               "median_residual_stops": float(np.median(errors)), "p95_residual_stops": float(np.quantile(errors, .95)),
               "inverse_response_rgb": response.tolist()}
    return response, metrics


def response_pixels(image, response, np):
    codes = np.arange(256, dtype=np.float32) / 255
    return np.stack([np.interp(image[..., channel], codes, response[:, channel]) for channel in range(3)], axis=-1).astype(np.float32)


def motion_mask(images, radiances, reference, common, threshold, np, cv):
    ref, reference_light = images[reference], radiances[reference]
    motion = np.zeros(common.shape, bool)
    ref_valid = (ref > .02) & (ref < .98)
    for index, (image, light) in enumerate(zip(images, radiances)):
        if index == reference:
            continue
        reliable = ref_valid & (image > .02) & (image < .98)
        stops = np.abs(np.log2(np.maximum(light, 1e-9) / np.maximum(reference_light, 1e-9)))
        # The encoded noise floor is represented by a relative stop threshold;
        # clipped samples are not evidence of motion.
        motion |= np.any(reliable & (stops > threshold), axis=-1) & common
    binary = cv.morphologyEx(motion.astype(np.uint8), cv.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    binary = cv.dilate(binary, np.ones((5, 5), np.uint8))
    return (binary > 0) & common


def hdr(images, recipe, np, cv):
    images, common, reference, alignment = align_brackets(images, recipe, np, cv)
    times = [entry["exposure_time"] for entry in recipe["brackets"]]
    fitted = recipe["input_transfer"] == "measured"
    response, calibration = None, None
    if fitted:
        # A static capture is monotone with shutter duration before the response
        # is known. Large ordering reversals cannot be calibration samples.
        candidates = common.copy()
        order = sorted(range(len(times)), key=lambda i: times[i])
        for left, right in zip(order, order[1:]):
            candidates &= np.all(images[left] <= images[right] + 2 / 255, axis=-1)
        response, calibration = calibrate(images, times, candidates, reference, np, cv)
        provisional = [response_pixels(image, response, np) / exposure for image, exposure in zip(images, times)]
        outliers = motion_mask(images, provisional, reference, common, recipe["ghost_threshold_stops"], np, cv)
        refined = candidates & ~outliers
        if np.count_nonzero(refined) < 256:
            raise ValueError("Motion leaves too few static pixels to measure the camera response.")
        if np.any(candidates & outliers):
            response, calibration = calibrate(images, times, refined, reference, np, cv)
        calibration["static_candidate_pixels"] = int(np.count_nonzero(refined))
        if calibration["p95_residual_stops"] > .75:
            raise ValueError("Measured camera response does not explain the supplied exposure times within 0.75 stops.")
    radiances = [(response_pixels(image, response, np) if fitted else transfer(image, recipe["input_transfer"], np)) / exposure
                 for image, exposure in zip(images, times)]
    motion = motion_mask(images, radiances, reference, common, recipe["ghost_threshold_stops"], np, cv) if recipe["deghost"] == "reference" else np.zeros(common.shape, bool)
    numerator = np.zeros_like(images[0], dtype=np.float32)
    denominator = np.zeros_like(numerator)
    fallback = radiances[reference].copy()
    score = np.abs(images[reference] - .5)
    all_dark = np.ones(numerator.shape, bool)
    all_bright = np.ones(numerator.shape, bool)
    for image, light in zip(images, radiances):
        dark, bright = image <= .002, image >= .998
        weight = np.minimum(image, 1 - image)
        weight[dark | bright] = 0
        numerator += weight * light
        denominator += weight
        better = np.abs(image - .5) < score
        np.copyto(fallback, light, where=better)
        np.minimum(score, np.abs(image - .5), out=score)
        all_dark &= dark
        all_bright &= bright
    unresolved = denominator <= 1e-12
    np.divide(numerator, denominator, out=numerator, where=~unresolved)
    np.copyto(numerator, fallback, where=unresolved)
    numerator[motion] = radiances[reference][motion]
    numerator[~common] = 0
    clipped_reference = motion & np.any((images[reference] <= .002) | (images[reference] >= .998), axis=-1)
    details = {"alignment": {"model": recipe["alignment"], "reference_asset_id": recipe["reference_asset_id"], "measurements": alignment,
                              "coverage": "shared valid reference-image pixels; uncovered borders remain transparent",
                              "shared_pixels": int(np.count_nonzero(common))},
               "deghost": {"mode": recipe["deghost"], "threshold_stops": recipe["ghost_threshold_stops"],
                           "motion_pixels": int(np.count_nonzero(motion)), "clipped_reference_motion_pixels": int(np.count_nonzero(clipped_reference)),
                           "method": "radiance disagreement against the selected reference; 3px closing and 2px expansion",
                           "fallback": "all RGB channels in measured motion use only the reference exposure; its noise and clipped detail are retained",
                           "motion_mask": "motion.png" if recipe["deghost"] == "reference" else None},
               "response": calibration if fitted else {"method": "known transfer", "transfer": recipe["input_transfer"]},
               "unrecovered_channels": int(np.count_nonzero(unresolved & common[..., None])),
               "unrecovered_pixels": int(np.count_nonzero(np.any(unresolved, axis=-1) & common)),
               "all_dark_channels": int(np.count_nonzero(all_dark & common[..., None])),
               "all_saturated_channels": int(np.count_nonzero(all_bright & common[..., None])),
               "radiance_units": "relative response-normalized RGB per second" if fitted else "relative linear Rec.709 signal per second",
               "assumptions": ["fixed aperture, ISO and white balance", "Rec.709/sRGB capture primaries", "static planar background",
                               "reference-only motion does not reconstruct occluded, clipped or blurred detail"]}
    return np.dstack((numerator, common.astype(np.float32))), details, motion


def panorama(images, recipe, np, cv):
    ids = recipe["images"]
    reference = ids.index(recipe["reference_asset_id"])
    descriptors = [features(image, np, cv) for image in images]
    transforms = {reference: np.eye(3, dtype=np.float64)}
    details = {reference: {"asset_id": ids[reference], "matched_to": None}}
    failed = set()
    while len(transforms) < len(images):
        candidates = []
        for index in range(len(images)):
            if index in transforms:
                continue
            for target in transforms:
                if (index, target) in failed:
                    continue
                try:
                    relative, metrics = measure(images[index], images[target], descriptors[index], descriptors[target], "homography", np, cv)
                    combined = checked_geometry(transforms[target] @ relative, images[index].shape, np, cv)
                    candidates.append((metrics["inliers"], -metrics["median_error_pixels"], index, target, combined, metrics))
                except ValueError:
                    failed.add((index, target))
        if not candidates:
            raise ValueError("The panorama photographs do not form one connected, textured planar overlap. No images were silently discarded.")
        _, _, index, target, combined, metrics = max(candidates, key=lambda value: value[:2])
        transforms[index] = combined
        details[index] = {"asset_id": ids[index], "matched_to": ids[target], **metrics}
    all_corners = np.concatenate([project(corners(image.shape, np), transforms[index], np) for index, image in enumerate(images)])
    low, high = np.floor(all_corners.min(axis=0)), np.ceil(all_corners.max(axis=0))
    width, height = (high - low + 1).astype(np.int64).tolist()
    if width < 1 or height < 1 or max(width, height) > 16384 or width * height > MAX_PIXELS:
        raise ValueError("The measured panorama canvas exceeds 16,384 pixels per edge or 33.5 million pixels.")
    offset = np.array([[1, 0, -low[0]], [0, 1, -low[1]], [0, 0, 1]], np.float64)
    numerator = np.zeros((height, width, 3), np.float32)
    denominator = np.zeros((height, width), np.float32)
    coverage_count = np.zeros((height, width), np.uint8)
    for index in transforms:
        image = images[index]
        matrix = offset @ transforms[index]
        light = transfer(image, recipe["input_transfer"], np)
        moved = cv.warpPerspective(light, matrix, (width, height), flags=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT)
        mask = cv.warpPerspective(np.ones(image.shape[:2], np.float32), matrix, (width, height),
                                  flags=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT) > .99999
        overlap = mask & (denominator > 0)
        if index != reference and np.count_nonzero(overlap) < min(np.count_nonzero(mask), np.count_nonzero(denominator)) * .08:
            raise ValueError("The measured panorama overlap is too small to stitch reliably.")
        gain = np.ones(3, np.float32)
        if recipe["exposure_compensation"] and index != reference:
            existing = numerator / np.maximum(denominator[..., None], 1e-9)
            for channel in range(3):
                reliable = overlap & (moved[..., channel] > .01) & (moved[..., channel] < .9) & (existing[..., channel] > .01) & (existing[..., channel] < .9)
                if np.count_nonzero(reliable) < 128:
                    raise ValueError("Panorama exposure matching needs 128 unsaturated overlapping samples per channel.")
                gain[channel] = np.median(existing[..., channel][reliable] / moved[..., channel][reliable])
            if np.any((gain < .25) | (gain > 4)):
                raise ValueError("Panorama exposure differences exceed the supported two-stop gain range.")
        moved *= gain
        # Pad so a completely filled image still has a finite edge distance.
        weight = cv.distanceTransform(np.pad(mask.astype(np.uint8), 1), cv.DIST_L2, cv.DIST_MASK_PRECISE)[1:-1, 1:-1]
        weight = np.minimum(weight, 64)
        numerator += moved * weight[..., None]
        denominator += weight
        coverage_count += mask.astype(np.uint8)
        details[index].update(source_to_reference=transforms[index].tolist(), source_to_canvas=matrix.tolist(),
                              source_width=image.shape[1], source_height=image.shape[0], exposure_gain_rgb=gain.tolist(),
                              covered_pixels=int(np.count_nonzero(mask)))
    valid = denominator > 0
    rgb = numerator / np.maximum(denominator[..., None], 1e-9)
    result = {"projection": "planar homographies in selected reference coordinates", "reference_asset_id": ids[reference],
              "measurements": [details[index] for index in range(len(images))], "canvas_origin_in_reference": low.tolist(),
              "blend": "linear-light distance feather, capped at 64 pixels", "exposure_compensation": recipe["exposure_compensation"],
              "covered_pixels": int(np.count_nonzero(valid)), "overlap_pixels": int(np.count_nonzero(coverage_count > 1)),
              "uncovered_pixels": int(np.count_nonzero(~valid)), "input_transfer": recipe["input_transfer"],
              "assumptions": ["static scene with planar overlap or camera rotation approximated by homographies", "fixed focus and white balance",
                              "no spherical/cylindrical projection, lens estimation, parallax repair or moving-subject seam removal"]}
    return np.dstack((rgb, valid.astype(np.float32))), result, None


def probe(np, cv):
    rng = np.random.default_rng(20261022)
    rgb = cv.GaussianBlur(rng.uniform(.05, .95, (160, 192, 3)).astype(np.float32), (3, 3), 0)
    shifted = np.zeros_like(rgb)
    shifted[4:, 7:] = rgb[:-4, :-7]
    matrix, _ = measure(shifted, rgb, features(shifted, np, cv), features(rgb, np, cv), "translation", np, cv)
    grid = np.linspace(.02, 1.5, 16 * 16, dtype=np.float32).reshape(16, 16, 1)
    images = [np.rint(np.minimum(1, grid * time) ** (1 / 2.2) * 255).astype(np.uint8).repeat(3, axis=2) for time in (.25, .5, 1.)]
    response = cv.createCalibrateDebevec(samples=64, lambda_=20., random=False).process(images, times=np.array([.25, .5, 1.], np.float32))
    good = bool(np.max(np.abs(matrix[:2, 2] - [-7, -4])) < .25 and response.shape == (256, 1, 3)
                and np.isfinite(response).all() and np.all(response > 0) and response[200, 0, 0] > response[80, 0, 0])
    return {"available": good, "actual_operations_verified": good, "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "opencv": cv.__version__},
            "alignment_models": ["translation", "homography"], "deghost_modes": ["reference"],
            "response_fit": "Debevec 256-level inverse RGB response", "panorama_projection": "planar"}


def render(request, np, cv):
    recipe = validate_imaging_recipe(request.get("recipe"))
    root = Path(request["workspace"])
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir() or not root.name.startswith(".building-")
            or tuple(root.parts[-3:-1]) != ("imaging", "outputs")):
        raise ValueError("Photograph geometry requires a private owned imaging directory.")
    inputs = request.get("inputs")
    count = len(recipe["images"]) if recipe["operation"] == "panorama" else len(recipe["brackets"])
    if not isinstance(inputs, list) or len(inputs) != count:
        raise ValueError("Photograph inputs do not match the authored recipe.")
    images, total = [], 0
    for index, descriptor in enumerate(inputs):
        width, height = descriptor.get("width"), descriptor.get("height")
        if type(width) is not int or type(height) is not int or min(width, height) < 32 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError("A photograph snapshot has an unsupported shape.")
        total += width * height
        if total > MAX_STACK_PIXELS:
            raise ValueError("The photograph stack exceeds its total pixel bound.")
        filename = "photo-source-%02d.f32le" % index
        if descriptor.get("filename") != filename:
            raise ValueError("Photograph snapshots must use their owned sequence identities.")
        path = _owned(root, filename)
        digest, size = _hash_file(path, MAX_IMAGE_PIXELS * 16)
        if size != width * height * 16 or digest != descriptor.get("sha256") or size != descriptor.get("size"):
            raise ValueError("A photograph snapshot changed before measurement.")
        rgba = np.frombuffer(path.read_bytes(), dtype="<f4").reshape(height, width, 4)
        images.append(photograph(rgba, np))
    pixels, details, motion = (hdr if recipe["operation"] == "hdr_merge" else panorama)(images, recipe, np, cv)
    if not np.isfinite(pixels).all() or np.max(np.abs(pixels[..., :3])) > 1e20:
        raise ValueError("Photograph processing produced unbounded float pixels.")
    def save(filename, data):
        path = root / filename
        with path.open("xb") as output:
            output.write(data)
        digest, size = _hash_file(path)
        return {"filename": filename, "sha256": digest, "size": size}
    result = {"width": pixels.shape[1], "height": pixels.shape[0], "details": details,
              "pixels": save("photo-result.f32le", pixels.astype("<f4").tobytes())}
    details["runtime"] = {"python": sys.version.split()[0], "numpy": np.__version__, "opencv": cv.__version__}
    if recipe["operation"] == "hdr_merge" and recipe["deghost"] == "reference":
        result["motion"] = save("photo-motion.u8", (motion.astype(np.uint8) * 255).tobytes())
    return result


def main():
    try:
        np, cv = modules()
        if sys.argv[1:] == ["--capabilities"]:
            result = probe(np, cv)
        elif len(sys.argv) == 1:
            payload = sys.stdin.buffer.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise ValueError("The photograph request exceeds its byte bound.")
            request = json.loads(payload)
            if not isinstance(request, dict) or set(request) != {"workspace", "recipe", "inputs"}:
                raise ValueError("Invalid photograph worker request.")
            result = render(request, np, cv)
        else:
            raise ValueError("Unsupported photograph worker command.")
        sys.stdout.buffer.write(_json_bytes(result))
        return 0
    except Exception as exc:
        sys.stdout.buffer.write(_json_bytes({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

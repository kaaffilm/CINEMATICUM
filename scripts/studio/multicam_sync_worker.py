#!/usr/bin/env python3
"""Bounded, actual sample correlation for admitted multicamera audio windows.

The controller owns decoded little-endian 48 kHz mono samples. This isolated
worker never opens source media, network locations, or project documents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

import numpy as np

VERSION = 1
ALGORITHM = "fft-normalized-48k-v1"
RATE = 48000
DECIMATION = 6
COARSE_RATE = RATE // DECIMATION
MAX_WINDOW = 120 * RATE
MIN_OVERLAP = 4 * RATE
MAX_LAG = 60 * RATE
MAX_START = 21600 * RATE
MAX_JSON = 12 * 1024 * 1024
MIN_AC_RMS = 2e-5
MIN_CORRELATION = .60
MIN_LOCAL_CORRELATION = .55
MIN_PEAK_MARGIN = .08
MAX_COMPETITOR_RATIO = .90
MAX_OFFSET_SPREAD = 24
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
HASH = re.compile(r"^[a-f0-9]{64}$")


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer between {low} and {high}.")
    return value


def _pcm(path, count, digest):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != count * 4:
        raise ValueError("Synchronization samples have an invalid owned file or byte count.")
    with path.open("rb") as stream:
        raw = stream.read(MAX_WINDOW * 4 + 1)
    if len(raw) != count * 4 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Synchronization sample bytes changed after decode.")
    result = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    if result.size != count or not np.isfinite(result).all():
        raise ValueError("Synchronization audio contains incomplete or non-finite samples.")
    if np.max(np.abs(result), initial=0) > 64:
        raise ValueError("Synchronization sample amplitude exceeds the supported finite range.")
    return result


def normalized_correlations(x, y, minimum, maximum, min_overlap):
    """Pearson correlation at each lag: x[n + lag] corresponds to y[n].

    FFT convolution computes the uncentered products; separate overlap prefix
    sums supply each lag's actual means and variances. Short overlaps and
    constant audio never acquire a score through zero padding.
    """
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    n, m = len(x), len(y)
    if not n or not m or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Correlation requires finite nonempty one-dimensional samples.")
    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("Correlation accepts one selected mono channel per source.")
    minimum, maximum = max(-m + 1, int(minimum)), min(n - 1, int(maximum))
    if minimum > maximum:
        return np.empty(0, dtype=np.int64), np.empty(0), np.empty(0, dtype=np.int64)
    length = n + m - 1
    fft_length = 1 << (length - 1).bit_length()
    if fft_length > 2 ** 21:
        raise ValueError("The normalized correlation exceeds its FFT memory bound.")
    # Global centering also avoids cancellation when a recorder adds DC.
    x = x - x.mean(); y = y - y.mean()
    products = np.fft.irfft(np.fft.rfft(x, fft_length) * np.fft.rfft(y[::-1], fft_length), fft_length)
    lags = np.arange(minimum, maximum + 1, dtype=np.int64)
    x0, y0 = np.maximum(lags, 0), np.maximum(-lags, 0)
    counts = np.minimum(n - x0, m - y0)
    sx = np.concatenate(([0.], np.cumsum(x))); sy = np.concatenate(([0.], np.cumsum(y)))
    qx = np.concatenate(([0.], np.cumsum(x * x))); qy = np.concatenate(([0.], np.cumsum(y * y)))
    sum_x, sum_y = sx[x0 + counts] - sx[x0], sy[y0 + counts] - sy[y0]
    var_x = np.maximum(0, qx[x0 + counts] - qx[x0] - sum_x * sum_x / counts)
    var_y = np.maximum(0, qy[y0 + counts] - qy[y0] - sum_y * sum_y / counts)
    valid = (counts >= min_overlap) & (var_x / counts >= MIN_AC_RMS ** 2) & (var_y / counts >= MIN_AC_RMS ** 2)
    result = np.zeros(len(lags), dtype=np.float64)
    result[valid] = (products[lags[valid] + m - 1] - sum_x[valid] * sum_y[valid] / counts[valid]) / np.sqrt(var_x[valid] * var_y[valid])
    np.clip(result, -1, 1, out=result)
    return lags, result, counts


def _coarse(samples):
    # Symmetric, unity-DC Hann-windowed sinc low-pass; all sources share the
    # same zero-phase sample grid before integer decimation to 8 kHz.
    coordinate = np.arange(-60, 61, dtype=np.float64)
    kernel = 2 * (3000 / RATE) * np.sinc(2 * (3000 / RATE) * coordinate) * np.hanning(len(coordinate))
    kernel /= kernel.sum()
    centered = samples - samples.mean()
    return np.convolve(centered, kernel, mode="same")[::DECIMATION]


def _score(x, y, lag):
    x0, y0 = max(lag, 0), max(-lag, 0)
    count = min(len(x) - x0, len(y) - y0)
    if count < MIN_OVERLAP:
        return 0.
    a = x[x0:x0 + count]; b = y[y0:y0 + count]
    a = a - a.mean(); b = b - b.mean()
    aa, bb = float(np.dot(a, a)), float(np.dot(b, b))
    if min(aa, bb) / count < MIN_AC_RMS ** 2:
        return 0.
    return float(np.clip(np.dot(a, b) / math.sqrt(aa * bb), -1, 1))


def waveform(samples, start):
    count = min(1024, max(1, math.ceil(len(samples) / 256)))
    edges = np.linspace(0, len(samples), count + 1, dtype=np.int64)
    blocks = []
    for begin, end in zip(edges, edges[1:]):
        value = samples[begin:end]
        blocks.append({"start_sample": start + int(begin), "samples": int(end - begin),
                       "min": float(value.min()), "max": float(value.max()),
                       "rms": float(np.sqrt(np.mean(value * value)))})
    return {"start_sample": start, "samples": len(samples), "rate": RATE, "blocks": blocks,
            "mean": float(samples.mean()), "ac_rms": float(np.std(samples)),
            "peak": float(np.max(np.abs(samples)))}


def estimate_pair(reference, target, max_lag, min_overlap=MIN_OVERLAP):
    """Return an evidenced offset or an explicit refusal, never a guessed cut."""
    if min(len(reference), len(target)) < min_overlap:
        return {"accepted": False, "reason": "insufficient_overlap", "message": "The decoded windows do not contain the required common sound duration."}
    if min(float(np.std(reference)), float(np.std(target))) < MIN_AC_RMS:
        return {"accepted": False, "reason": "silent_or_constant", "message": "A selected channel is silent, constant, or below the supported signal floor."}
    x, y = _coarse(reference), _coarse(target)
    bound = max_lag // DECIMATION
    lags, correlations, counts = normalized_correlations(x, y, -bound, bound, math.ceil(min_overlap / DECIMATION))
    if not len(lags):
        return {"accepted": False, "reason": "insufficient_overlap", "message": "There is no admissible sample overlap."}
    magnitude = np.abs(correlations); best = int(np.argmax(magnitude))
    lag, score = int(lags[best]), float(magnitude[best])
    separated = np.abs(lags - lag) > round(.025 * COARSE_RATE)
    competitor = float(magnitude[separated].max(initial=0))
    # Retain measured local maxima, including the best rejected alternatives.
    maxima = np.flatnonzero((magnitude >= np.roll(magnitude, 1)) & (magnitude >= np.roll(magnitude, -1)))
    ranked = sorted(maxima.tolist(), key=lambda i: (-magnitude[i], abs(int(lags[i])), int(lags[i])))[:12]
    peaks = [{"lag_samples": int(lags[i]) * DECIMATION, "correlation": float(correlations[i]),
              "overlap_samples": int(counts[i]) * DECIMATION} for i in ranked]
    result = {"accepted": False, "coarse_lag_samples": lag * DECIMATION,
              "coarse_correlation": float(correlations[best]), "second_peak_magnitude": competitor,
              "peak_margin": score - competitor, "candidate_peaks": peaks}
    if score < MIN_CORRELATION:
        return {**result, "reason": "weak_correlation", "message": "The selected channels do not share a sufficiently strong measured waveform."}
    if competitor >= score * MAX_COMPETITOR_RATIO or score - competitor < MIN_PEAK_MARGIN:
        return {**result, "reason": "ambiguous_offset", "message": "Repeated or periodic sound produces competing offsets; choose a distinct sound window or align manually."}
    if abs(lag) >= bound - 1:
        return {**result, "reason": "search_boundary", "message": "The best offset reaches the search boundary; widen the permitted search or choose corresponding windows."}
    estimates = [(value, _score(reference, target, value))
                 for value in range(max(-max_lag, lag * DECIMATION - 2 * DECIMATION),
                                    min(max_lag, lag * DECIMATION + 2 * DECIMATION) + 1)]
    fine, fine_score = max(estimates, key=lambda item: (abs(item[1]), -abs(item[0])))
    result.update(lag_samples=fine, correlation=fine_score, polarity=1 if fine_score >= 0 else -1)
    if abs(fine_score) < MIN_LOCAL_CORRELATION:
        return {**result, "reason": "weak_full_resolution_match", "message": "The coarse match did not survive verification against full-rate samples."}
    x0, y0 = max(fine, 0), max(-fine, 0)
    overlap = min(len(reference) - x0, len(target) - y0)
    length = min(2 * RATE, overlap // 3)
    radius = RATE // 100  # Independently search ten milliseconds around each match.
    checks = []
    for position in np.linspace(0, overlap - length, 3, dtype=np.int64):
        begin_x = x0 + int(position); begin_y = max(0, y0 + int(position) - radius)
        end_y = min(len(target), y0 + int(position) + length + radius)
        a, b = reference[begin_x:begin_x + length], target[begin_y:end_y]
        local_lags, local_scores, _ = normalized_correlations(a, b, -2 * radius, 0, length)
        if not len(local_lags) or float(np.abs(local_scores).max(initial=0)) < MIN_LOCAL_CORRELATION:
            return {**result, "reason": "insufficient_independent_evidence", "message": "Separated sound windows do not independently verify this offset.", "window_checks": checks}
        index = int(np.argmax(np.abs(local_scores)))
        local_offset = begin_x - begin_y + int(local_lags[index])
        checks.append({"reference_center_sample": begin_x + length // 2, "samples": length,
                       "lag_samples": local_offset, "correlation": float(local_scores[index])})
    spread = max(item["lag_samples"] for item in checks) - min(item["lag_samples"] for item in checks)
    positions = np.asarray([item["reference_center_sample"] for item in checks], dtype=np.float64)
    offsets = np.asarray([item["lag_samples"] for item in checks], dtype=np.float64)
    positions -= positions.mean()
    drift_ppm = float(np.dot(positions, offsets - offsets.mean()) / np.dot(positions, positions) * 1e6) if np.dot(positions, positions) else 0.
    result.update(window_checks=checks, offset_spread_samples=spread, measured_drift_ppm=drift_ppm,
                  overlap_samples=overlap)
    if spread > MAX_OFFSET_SPREAD or any(abs(item["lag_samples"] - fine) > MAX_OFFSET_SPREAD for item in checks):
        return {**result, "reason": "inconsistent_clock_or_offset", "message": "Separated windows disagree about the offset; this tool does not conceal recorder clock drift or discontinuities."}
    if any((1 if item["correlation"] >= 0 else -1) != result["polarity"] for item in checks):
        return {**result, "reason": "inconsistent_polarity", "message": "Separated sound windows disagree about waveform polarity."}
    return {**result, "accepted": True, "reason": "measured", "message": "A unique constant sample offset passed independent window checks."}


def analyze(request, directory, progress=None):
    directory = Path(directory).resolve(strict=True)
    if not isinstance(request, dict) or set(request) != {"version", "reference_asset_id", "sources", "max_lag_samples", "min_overlap_samples"} or type(request["version"]) is not int or request["version"] != VERSION:
        raise ValueError("Unsupported synchronization worker request.")
    sources = request["sources"]
    if not isinstance(sources, list) or not 2 <= len(sources) <= 16:
        raise ValueError("Choose 2–16 distinct synchronization sources.")
    lag = _integer(request["max_lag_samples"], "Search range", RATE // 10, MAX_LAG)
    overlap = _integer(request["min_overlap_samples"], "Minimum overlap", MIN_OVERLAP, MAX_WINDOW)
    ids = set(); records = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != {"asset_id", "filename", "start_sample", "samples", "sha256"}:
            raise ValueError("Invalid decoded synchronization source binding.")
        if not ID.fullmatch(str(source["asset_id"])) or source["asset_id"] in ids:
            raise ValueError("Synchronization source identities must be distinct.")
        if source["filename"] != f"samples_{index:02d}.f32le" or not HASH.fullmatch(str(source["sha256"])):
            raise ValueError("Synchronization samples must use their owned file identity.")
        _integer(source["start_sample"], "Window first sample", 0, MAX_START)
        _integer(source["samples"], "Decoded samples", 1, MAX_WINDOW)
        ids.add(source["asset_id"]); records.append(source)
    reference_id = request["reference_asset_id"]
    if reference_id not in ids:
        raise ValueError("Choose a reference from the selected camera sources.")
    anchor = next(source for source in records if source["asset_id"] == reference_id)
    reference = _pcm(directory / anchor["filename"], anchor["samples"], anchor["sha256"])
    measured, waves = [], []
    for index, source in enumerate(records):
        samples = reference if source is anchor else _pcm(directory / source["filename"], source["samples"], source["sha256"])
        waves.append({"asset_id": source["asset_id"], "sample_sha256": source["sha256"], **waveform(samples, source["start_sample"])})
        if source is anchor:
            accepted = len(reference) >= overlap and float(np.std(reference)) >= MIN_AC_RMS
            pair = {"accepted": accepted, "reason": "reference" if accepted else "silent_or_short_reference",
                    "lag_samples": 0, "correlation": 1. if accepted else 0., "polarity": 1}
        else:
            pair = estimate_pair(reference, samples, lag, overlap)
        if pair["accepted"]:
            pair["offset_samples"] = anchor["start_sample"] - source["start_sample"] + pair["lag_samples"]
        measured.append({"asset_id": source["asset_id"], **pair})
        if progress:
            progress((index + 1) / len(records))
    accepted = all(item["accepted"] for item in measured)
    common = None
    if accepted:
        offsets = {item["asset_id"]: item["offset_samples"] for item in measured}
        begin = max(source["start_sample"] + offsets[source["asset_id"]] for source in records)
        end = min(source["start_sample"] + source["samples"] + offsets[source["asset_id"]] for source in records)
        if end - begin < overlap:
            accepted = False
        else:
            common = {"reference_start_sample": begin, "samples": end - begin,
                      "source_starts": {source["asset_id"]: begin - offsets[source["asset_id"]] for source in records}}
    report = {"version": VERSION, "algorithm": ALGORITHM, "rate": RATE, "accepted": accepted,
              "reason": "measured" if accepted else "rejected_pair" if not all(item["accepted"] for item in measured) else "no_common_overlap",
              "reference_asset_id": reference_id, "angles": measured, "common_overlap": common,
              "criteria": {"minimum_ac_rms": MIN_AC_RMS, "minimum_correlation": MIN_CORRELATION,
                           "minimum_local_correlation": MIN_LOCAL_CORRELATION, "minimum_peak_margin": MIN_PEAK_MARGIN,
                           "maximum_competitor_ratio": MAX_COMPETITOR_RATIO, "maximum_offset_spread_samples": MAX_OFFSET_SPREAD,
                           "max_lag_samples": lag, "min_overlap_samples": overlap},
              "runtime": {"engine": "NumPy FFT and full-rate normalized sample correlation", "numpy": np.__version__,
                          "python": sys.version.split()[0], "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    return report, {"version": VERSION, "rate": RATE, "channels": 1, "sources": waves}


def capabilities():
    # This tiny actual calculation proves the executable's FFT convention and
    # normalization before the application offers an analysis job.
    rng = np.random.default_rng(85432)
    reference = rng.uniform(-.25, .25, 512)
    target = 1.4 * reference[37:437] + .1
    lags, values, _ = normalized_correlations(reference, target, -80, 80, 250)
    index = int(np.argmax(values))
    if int(lags[index]) != 37 or abs(float(values[index]) - 1) > 1e-10:
        raise ValueError("The isolated NumPy runtime failed its actual correlation probe.")
    return {"available": True, "version": VERSION, "algorithm": ALGORITHM, "numpy": np.__version__,
            "runtime_operations_verified": True, "max_sources": 16, "max_window_samples": MAX_WINDOW,
            "max_lag_samples": MAX_LAG, "min_overlap_samples": MIN_OVERLAP, "rate": RATE}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--directory")
    args = parser.parse_args()
    if args.capabilities:
        print(json.dumps(capabilities(), allow_nan=False)); return
    if not args.request or not args.directory:
        parser.error("Provide an owned decoded-sample directory and request file.")
    path = Path(args.request)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError("Invalid bounded synchronization request file.")
    request = json.loads(path.read_bytes())
    def progress(value):
        print(json.dumps({"progress": value}), flush=True)
    report, waves = analyze(request, args.directory, progress)
    for name, value in (("analysis.json", report), ("waveforms.json", waves)):
        with (Path(args.directory) / name).open("x") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

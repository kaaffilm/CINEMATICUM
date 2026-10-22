"""Data-only Lensfun calibrations and explicit front-hemisphere projections.

The Lensfun XML importer does not execute XML, load DTDs, open profile paths,
download a database, guess a camera, or interpolate missing focal lengths.
The selected calibration travels inside the editable project. The radial
equations and focal-preserving normalization follow Lensfun's documented
poly3/poly5/PTLens models, including its d**(n+1) coefficient adjustment.
Pixel interpolation remains the compositor's existing alpha-aware sampler.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 512 * 1024
MAX_CALIBRATIONS = 2048
PROJECTIONS = ("equidistant", "equisolid", "stereographic", "orthographic")
PROFILE_KEYS = {"version", "maker", "lens", "source_sha256", "focal_mm", "calibration_crop",
                "calibration_aspect", "image_crop", "center_x", "center_y", "distortion", "coefficients"}
COEFFICIENTS = {"poly3": ("k1",), "poly5": ("k1", "k2"), "ptlens": ("a", "b", "c")}
DEFAULTS = {"direction": "undistort", "fx": 1., "fy": 1., "cx": .5, "cy": .5,
            "k1": 0., "k2": 0., "k3": 0., "p1": 0., "p2": 0.}


def finite(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Lens {name} must be a finite number between {low} and {high}.")
    return float(value)


def _text(value, name, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"Lens {name} must contain 1–{maximum} printable characters.")
    return value


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS or type(profile.get("version")) is not int or profile["version"] != 1:
        raise ValueError("Lensfun calibration requires the supported version 1 profile fields.")
    clean = {"version": 1, "maker": _text(profile["maker"], "maker", 160),
             "lens": _text(profile["lens"], "model", 256)}
    digest = profile["source_sha256"]
    if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
        raise ValueError("Lensfun source requires its original XML SHA-256 identity.")
    clean["source_sha256"] = digest
    for name, low, high in (("focal_mm", .1, 2000), ("calibration_crop", .1, 100),
                            ("calibration_aspect", 1, 4), ("image_crop", .1, 100),
                            ("center_x", -.5, .5), ("center_y", -.5, .5)):
        clean[name] = finite(profile[name], name, low, high)
    if clean["image_crop"] + 1e-10 < clean["calibration_crop"]:
        raise ValueError("Use an image crop factor at least as large as this calibration; extrapolation beyond its sensor is unsupported.")
    model = profile["distortion"]
    if not isinstance(model, str) or model not in COEFFICIENTS:
        raise ValueError("Lensfun supports poly3, poly5 and PTLens radial distortion calibrations.")
    values = profile["coefficients"]
    if not isinstance(values, list) or len(values) != len(COEFFICIENTS[model]):
        raise ValueError("Lensfun coefficient count differs from its distortion model.")
    clean["distortion"] = model
    clean["coefficients"] = [finite(v, "coefficient", -1, 1) for v in values]
    profile_domain(clean)
    return clean


def radial_coefficients(profile):
    """Return coefficients of r * (1 + c1*r + ... + c4*r**4).

    r is in the calibration sensor's half-short-edge units. Unlike a raw
    Hugin polynomial, Lensfun preserves the paraxial focal length: poly3 and
    PTLens need the d power adjustment before applying their coefficients.
    """
    model, values = profile["distortion"], profile["coefficients"]
    if model == "poly5":
        return (0., values[0], 0., values[1])
    d = 1 - (values[0] if model == "poly3" else sum(values))
    if d < .1:
        raise ValueError("Lensfun's focal-preserving scale must remain positive and at least 0.1.")
    if model == "poly3":
        return (0., values[0] / d**3, 0., 0.)
    a, b, c = values
    return (c / d**2, b / d**3, a / d**4, 0.)


def profile_domain(profile):
    # Half the image diagonal in calibration units, enlarged conservatively
    # for any accepted center shift. This bound covers every image aspect,
    # orientation and resolution; it does not certify only sampled points.
    radius = (profile["calibration_crop"] / profile["image_crop"] *
              math.hypot(profile["calibration_aspect"], 1) *
              (1 + abs(profile["center_x"]) + abs(profile["center_y"])))
    coefficients = radial_coefficients(profile)
    q = sum((i + 2) * abs(c) * radius**(i + 1) for i, c in enumerate(coefficients))
    if not math.isfinite(q) or q > .8 + 1e-12:
        raise ValueError("Lensfun calibration exceeds the conservative full-image radial invertibility bound (0.8). Use a smaller captured field or another calibration.")
    return {"q": q, "radius": radius, "iterations": 56, "coefficients": coefficients}


def validate_advanced(params, clean):
    model = params.get("model", "brown")
    if not isinstance(model, str) or model not in {"brown", "fisheye", "lensfun"}:
        raise ValueError("Choose Brown, an explicit fisheye projection, or a Lensfun calibration.")
    if model == "brown":
        if "projection" in params or "profile" in params:
            raise ValueError("Brown calibration cannot also contain a fisheye projection or Lensfun profile.")
        return clean
    if any(clean[name] for name in ("k1", "k2", "k3", "p1", "p2")):
        raise ValueError("Apply Brown coefficients in a separate lens node; they cannot silently modify another lens model.")
    clean["model"] = model
    if model == "fisheye":
        projection = params.get("projection")
        if not isinstance(projection, str) or projection not in PROJECTIONS or "profile" in params:
            raise ValueError("Fisheye requires equidistant, equisolid, stereographic or orthographic projection and no Lensfun profile.")
        clean["projection"] = projection
    else:
        if "projection" in params or any(clean[k] != DEFAULTS[k] for k in ("fx", "fy", "cx", "cy")):
            raise ValueError("Lensfun uses its recorded sensor crop and optical center; manual Brown intrinsics must stay at their defaults.")
        clean["profile"] = validate_profile(params.get("profile"))
    return clean


def active(params):
    if params.get("model") == "fisheye":
        return True
    if params.get("model") == "lensfun":
        return any(params["profile"]["coefficients"])
    return any(params.get(name, 0) for name in ("k1", "k2", "k3", "p1", "p2"))


def _xml_number(value, name, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Lensfun {name} is missing or is not numeric.") from None
    return finite(number, name, low, high)


def _aspect(value):
    if isinstance(value, str) and ":" in value:
        pieces = value.split(":")
        if len(pieces) != 2:
            raise ValueError("Lensfun aspect ratio must be numeric or a:b.")
        value = _xml_number(pieces[0], "aspect numerator", .1, 100) / _xml_number(pieces[1], "aspect denominator", .1, 100)
    return _xml_number(value, "aspect ratio", 1, 4)


def parse_lensfun_xml(text):
    """Read actual Lensfun version 1/2 XML without filesystem/network access.

    Exact measured focal samples are offered. Other focal lengths, ACM,
    automatic matching, TCA, vignetting and sensor crops are never guessed.
    The conventional external DTD declaration is recognized then removed;
    arbitrary declarations, entities and internal subsets are rejected.
    """
    if not isinstance(text, str) or not 1 <= len(text.encode("utf-8")) <= MAX_XML_BYTES:
        raise ValueError("Choose a Lensfun XML file of at most 512 KiB.")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cleaned = re.sub(r'<!DOCTYPE\s+lensdatabase\s+SYSTEM\s+[\"\']lensfun-database\.dtd[\"\']\s*>', '', text)
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', cleaned, re.I):
        raise ValueError("Lensfun XML cannot contain entities, internal subsets or external DTD references.")
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as error:
        raise ValueError("The selected Lensfun XML is malformed.") from error
    if root.tag != "lensdatabase" or root.attrib not in ({"version": "1"}, {"version": "2"}):
        raise ValueError("Choose a Lensfun lensdatabase version 1 or 2 XML file.")
    if sum(1 for _ in root.iter()) > 16000 or len(root.findall("lens")) > 512:
        raise ValueError("Lensfun XML exceeds its element or lens limit.")
    entries, skipped = [], []
    def primary(element, tag, default=None):
        nodes = [n for n in element.findall(tag) if not n.attrib.get("lang")]
        if len(nodes) > 1:
            raise ValueError(f"Lensfun {tag} is ambiguous.")
        return nodes[0].text.strip() if nodes and nodes[0].text else default
    for lens in root.findall("lens"):
        maker = _text(primary(lens, "maker", "Unknown maker"), "maker", 160)
        name = _text(primary(lens, "model", "Unnamed lens"), "model", 256)
        kind = primary(lens, "type", "rectilinear")
        if kind != "rectilinear":
            skipped.append(f"{maker} {name}: {kind} profile; use the explicit fisheye model for projection conversion.")
            continue
        crop = primary(lens, "cropfactor")
        aspect = primary(lens, "aspect-ratio", "1.5")
        centers = lens.findall("center")
        if len(centers) > 1:
            raise ValueError("Lensfun optical center is ambiguous.")
        center = centers[0].attrib if centers else {}
        if set(center) - {"x", "y"}:
            raise ValueError("Lensfun optical center contains unsupported attributes.")
        for calibration in lens.findall("calibration"):
            if set(calibration.attrib) - {"cropfactor", "aspect-ratio"}:
                raise ValueError("Lensfun calibration contains unsupported geometry attributes.")
            ccrop = _xml_number(calibration.get("cropfactor", crop), "calibration crop factor", .1, 100)
            caspect = _aspect(calibration.get("aspect-ratio", aspect))
            for row in calibration.findall("distortion"):
                model = row.get("model")
                if model not in COEFFICIENTS:
                    skipped.append(f"{maker} {name}: unsupported distortion model {model}.")
                    continue
                if set(row.attrib) - {"model", "focal", "real-focal", *COEFFICIENTS[model]}:
                    raise ValueError("Lensfun distortion sample contains unsupported attributes.")
                profile = {"version": 1, "maker": maker, "lens": name, "source_sha256": digest,
                    "focal_mm": _xml_number(row.get("focal"), "focal length", .1, 2000),
                    "calibration_crop": ccrop, "calibration_aspect": caspect, "image_crop": ccrop,
                    "center_x": _xml_number(center.get("x", "0"), "center X", -.5, .5),
                    "center_y": _xml_number(center.get("y", "0"), "center Y", -.5, .5),
                    "distortion": model, "coefficients": [_xml_number(row.get(k, "0"), k, -1, 1) for k in COEFFICIENTS[model]]}
                # A sample may be usable at a larger crop even when the full
                # calibration sensor exceeds our conservative inverse bound.
                radial_coefficients(profile)
                ident = hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
                entries.append({"id": ident, "label": f"{maker} {name} · {profile['focal_mm']:g} mm · crop {ccrop:g} · {model}", "profile": profile})
                if len(entries) > MAX_CALIBRATIONS:
                    raise ValueError("Lensfun XML exceeds 2048 distortion samples.")
    unique = {entry["id"]: entry for entry in entries}
    if not unique:
        raise ValueError("This file contains no supported rectilinear poly3, poly5 or PTLens distortion samples.")
    return {"source_sha256": digest, "calibrations": list(unique.values()),
            "warnings": ["Choose the exact measured focal length and the capture sensor crop factor. Automatic matching and focal interpolation are not applied.",
                         "Radial distortion only: TCA, vignetting, crop records and projection changes in Lensfun profiles are not applied.",
                         "The incoming graph image must represent the complete uncropped capture, without letterboxing or a changed pixel aspect."] + skipped[:32]}


def _profile_scale(profile, width, height):
    scale = 2 * profile["calibration_crop"] * math.hypot(profile["calibration_aspect"], 1) / (profile["image_crop"] * math.hypot(width, height))
    small = min(width - 1, height - 1)
    return scale, ((width - 1) + small * profile["center_x"]) / 2, ((height - 1) + small * profile["center_y"]) / 2


def _radius_forward(radius, coefficients):
    c1, c2, c3, c4 = coefficients
    return radius * (1 + radius * (c1 + radius * (c2 + radius * (c3 + radius * c4))))


def sampler(params, width, height):
    """Scalar backward mapping independent of the vector implementation."""
    model = params["model"]
    if model == "lensfun":
        profile = params["profile"]; domain = profile_domain(profile)
        scale, cx, cy = _profile_scale(profile, width, height)
    def sample(x, y):
        if model == "lensfun":
            a, b = (x - cx) * scale, (y - cy) * scale
            radius = math.hypot(a, b)
            if params["direction"] == "undistort":
                mapped = _radius_forward(radius, domain["coefficients"])
            else:
                low, high = 0., domain["radius"]
                if radius > _radius_forward(high, domain["coefficients"]) + 1e-10:
                    return None
                for _ in range(domain["iterations"]):
                    middle = (low + high) / 2
                    if _radius_forward(middle, domain["coefficients"]) < radius: low = middle
                    else: high = middle
                mapped = (low + high) / 2
            factor = mapped / radius if radius else 1.
            u, v = a * factor / scale + cx, b * factor / scale + cy
        else:
            a = (x / width - params["cx"]) / params["fx"]
            b = (y / height - params["cy"]) / params["fy"]
            radius, projection = math.hypot(a, b), params["projection"]
            if params["direction"] == "undistort":
                theta = math.atan(radius)
                mapped = {"equidistant": lambda: theta, "equisolid": lambda: 2 * math.sin(theta / 2),
                          "stereographic": lambda: 2 * math.tan(theta / 2), "orthographic": lambda: math.sin(theta)}[projection]()
            else:
                limit = {"equidistant": math.pi / 2, "equisolid": math.sqrt(2), "stereographic": 2., "orthographic": 1.}[projection]
                if radius >= limit: return None
                theta = {"equidistant": lambda: radius, "equisolid": lambda: 2 * math.asin(radius / 2),
                         "stereographic": lambda: 2 * math.atan(radius / 2), "orthographic": lambda: math.asin(radius)}[projection]()
                mapped = math.tan(theta)
            factor = mapped / radius if radius else 1.
            u, v = (a * factor * params["fx"] + params["cx"]) * width, (b * factor * params["fy"] + params["cy"]) * height
        if not (-1e-7 <= u <= width - 1 + 1e-7 and -1e-7 <= v <= height - 1 + 1e-7): return None
        return max(0., min(u, width - 1)), max(0., min(v, height - 1))
    return sample


def coordinates_numpy(params, xs, ys, width, height, np):
    """Bounded Float64 strips; no image-sized auxiliary allocation."""
    x, y = np.broadcast_arrays(xs, ys)
    valid = np.ones(x.shape, dtype=bool)
    if params["model"] == "lensfun":
        profile = params["profile"]; domain = profile_domain(profile)
        scale, cx, cy = _profile_scale(profile, width, height)
        a, b = (x - cx) * scale, (y - cy) * scale
        radius = np.hypot(a, b)
        if params["direction"] == "undistort":
            mapped = _radius_forward(radius, domain["coefficients"])
        else:
            low, high = np.zeros_like(radius), np.full_like(radius, domain["radius"])
            valid &= radius <= _radius_forward(domain["radius"], domain["coefficients"]) + 1e-10
            for _ in range(domain["iterations"]):
                middle = (low + high) / 2
                lower = _radius_forward(middle, domain["coefficients"]) < radius
                low, high = np.where(lower, middle, low), np.where(lower, high, middle)
            mapped = (low + high) / 2
        factor = np.divide(mapped, radius, out=np.ones_like(radius), where=radius != 0)
        u, v = a * factor / scale + cx, b * factor / scale + cy
    else:
        a, b = (x / width - params["cx"]) / params["fx"], (y / height - params["cy"]) / params["fy"]
        radius, projection = np.hypot(a, b), params["projection"]
        if params["direction"] == "undistort":
            theta = np.arctan(radius)
            mapped = {"equidistant": lambda: theta, "equisolid": lambda: 2 * np.sin(theta / 2),
                      "stereographic": lambda: 2 * np.tan(theta / 2), "orthographic": lambda: np.sin(theta)}[projection]()
        else:
            limit = {"equidistant": math.pi / 2, "equisolid": math.sqrt(2), "stereographic": 2., "orthographic": 1.}[projection]
            valid &= radius < limit
            bounded = np.minimum(radius, limit - 1e-12)
            theta = {"equidistant": lambda: bounded, "equisolid": lambda: 2 * np.arcsin(bounded / 2),
                     "stereographic": lambda: 2 * np.arctan(bounded / 2), "orthographic": lambda: np.arcsin(bounded)}[projection]()
            mapped = np.tan(theta)
        factor = np.divide(mapped, radius, out=np.ones_like(radius), where=radius != 0)
        u, v = (a * factor * params["fx"] + params["cx"]) * width, (b * factor * params["fy"] + params["cy"]) * height
    valid &= np.isfinite(u) & np.isfinite(v) & (u >= -1e-7) & (u <= width - 1 + 1e-7) & (v >= -1e-7) & (v <= height - 1 + 1e-7)
    return np.clip(u, 0, width - 1), np.clip(v, 0, height - 1), valid

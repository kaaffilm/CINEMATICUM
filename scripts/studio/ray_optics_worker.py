"""Private JSON worker for real Optiland CPU analysis; never an in-process plugin.

Invoked with -I -B by ray_optics.py. No user code, filenames, external material
catalogues, or pickled optical states are accepted. Numerical arrays come from
Optiland ray tracing and scalar diffraction, not illustrative substitutes.
"""
from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ray_optics import (ARTIFACT_NAMES, MAX_FIELDS, MAX_SURFACES, MAX_WAVELENGTHS,
                        RUNTIME_REQUIREMENTS, default_prescription, validate_ray_optics_recipe,
                        validate_optical_prescription)


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _hash(path):
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _runtime():
    packages = {name: importlib.metadata.version(name) for name in
                ("optiland", "numpy", "scipy", "matplotlib", "numba", "pandas", "PyYAML", "vtk")}
    for name, expected in RUNTIME_REQUIREMENTS.items():
        if packages[name] != expected:
            raise ValueError(f"Optics runtime requires {name}=={expected}; found {packages[name]}.")
    import matplotlib
    matplotlib.use("Agg", force=True)
    import optiland.backend as backend
    backend.set_backend("numpy")
    from optiland import optic, materials  # actually import the optical engine
    from optiland.mtf import FFTMTF
    from optiland.optimization.optimizer.scipy import LeastSquares
    return {"engine": "Optiland", "backend": "numpy-cpu", "packages": packages,
            "python": platform.python_version(), "platform": platform.platform(), "license": "MIT",
            "upstream": "https://github.com/optiland/optiland", "worker_sha256": _hash(__file__)["sha256"],
            "controller_sha256": _hash(Path(__file__).with_name("ray_optics.py"))["sha256"]}


def _doctor(runtime):
    from optiland.materials import MaterialCatalog
    return {"available": True, "operations": ["analyze", "optimize"], "runtime": runtime,
            "limits": {"surfaces": MAX_SURFACES, "fields": MAX_FIELDS, "wavelengths": MAX_WAVELENGTHS,
                       "pupil_samples": 128, "fft_grid": 512, "optimization_variables": 8, "max_evaluations": 200},
            "catalogs": MaterialCatalog.available(), "default_prescription": default_prescription(),
            "scope": "Centered sequential refractive optics; spherical/conic/even-asphere surfaces, built-in glass catalogues, real rays, geometric spots and ray fans, third-order Seidel sums, scalar FFT PSF/MTF at the primary wavelength, bounded local least-squares optimization. No manufacturing tolerance, non-sequential, polarization, or stray-light certification."}


def _catalog(query, limit):
    from optiland.materials import MaterialCatalog
    catalogs = MaterialCatalog.available()
    matches = []
    for catalog in catalogs:
        for name in MaterialCatalog(catalog).list():
            if query.casefold() in (catalog + ":" + name).casefold():
                matches.append({"catalog": catalog, "name": name})
    return {"available": True, "catalogs": catalogs, "query": query, "materials": matches[:limit],
            "total_matches": len(matches), "truncated": len(matches) > limit,
            "source": "Optiland packaged refractiveindex.info manufacturer-glass database",
            "database_license": "CC0-1.0 (refractiveindex.info database)", "match_policy": "exact"}


def _finite(value, label):
    import numpy as np
    data = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(data)):
        raise ValueError(f"{label} has non-finite values: this prescription does not produce a valid sampled optical result.")
    return data


def _scalar(value, label):
    return float(_finite(value, label).reshape(-1)[0])


def _build(prescription):
    import numpy as np
    from optiland import optic
    from optiland.materials import IdealMaterial, Material, MaterialCatalog, MatchPolicy
    lens = optic.Optic()
    lens.name = prescription["name"]
    lens.surfaces.add(index=0, radius=np.inf,
                      thickness=np.inf if prescription["object_distance"] is None else prescription["object_distance"])
    catalog_names = MaterialCatalog.available()
    catalog_glasses = {}
    materials = []
    for index, surface in enumerate(prescription["surfaces"], 1):
        spec = surface["material"]
        if spec["type"] == "air":
            material = IdealMaterial(1.0)
        elif spec["type"] == "constant":
            material = IdealMaterial(spec["index"])
        else:
            catalog = spec["catalog"]
            if catalog not in catalog_names:
                raise ValueError(f"Unknown packaged glass catalogue: {catalog}.")
            if catalog not in catalog_glasses:
                catalog_glasses[catalog] = set(MaterialCatalog(catalog).list())
            if spec["name"] not in catalog_glasses[catalog]:
                raise ValueError(f"Glass {catalog}:{spec['name']} does not match an exact packaged material.")
            material = Material(spec["name"], catalog=catalog, match_policy=MatchPolicy.STRICT, bounds="raise")
        refractive = []
        for wave in prescription["wavelengths"]:
            n = _scalar(material.n(wave["value"]), "Refractive index")
            if n < 1 or n > 4:
                raise ValueError("This visible/near-IR refractive workflow requires index values between 1 and 4.")
            refractive.append({"wavelength_um": wave["value"], "n": n})
        entry = {"surface": surface["id"], "material": spec, "refractive_indices": refractive}
        if spec["type"] == "catalog":
            entry["catalog_file"] = {"name": Path(material.filename).name, **_hash(material.filename)}
        materials.append(entry)
        arguments = {"radius": np.inf if surface["radius"] is None else surface["radius"],
                     "thickness": surface["thickness"], "conic": surface["conic"],
                     "material": material, "is_stop": surface["stop"]}
        if surface["coefficients"]:
            arguments.update(surface_type="even_asphere", coefficients=surface["coefficients"])
        lens.surfaces.add(index=index, **arguments)
    lens.surfaces.add(index=len(prescription["surfaces"]) + 1)
    lens.set_aperture("EPD", prescription["aperture"]["value"])
    lens.fields.set_type("angle")
    for field in prescription["fields"]:
        lens.fields.add(x=field["x"], y=field["y"], weight=field["weight"])
    for wave in prescription["wavelengths"]:
        lens.wavelengths.add(wave["value"], is_primary=wave["primary"], weight=wave["weight"])
    # Explicit authoring plane; no hidden image solve or autofocus occurs.
    return lens, materials


def _optimize(lens, recipe, progress):
    from optiland.optimization import OptimizationProblem
    from optiland.optimization.optimizer.scipy import LeastSquares
    model, settings = copy.deepcopy(recipe["prescription"]), recipe["optimization"]
    indices = {s["id"]: i for i, s in enumerate(model["surfaces"], 1)}
    problem = OptimizationProblem(batching=False)
    for variable in settings["variables"]:
        problem.add_variable(lens, variable["parameter"], surface_number=indices[variable["surface"]],
                             min_val=variable["min"], max_val=variable["max"])
    fields = lens.fields.get_field_coords()
    for index, coord in enumerate(fields):
        for wave in model["wavelengths"]:
            problem.add_operand("rms_spot_size", target=0.,
                                weight=math.sqrt(model["fields"][index]["weight"] * wave["weight"]),
                                input_data={"optic": lens, "surface_number": len(model["surfaces"]) + 1,
                                            "Hx": coord[0], "Hy": coord[1], "num_rays": recipe["analysis"]["rings"],
                                            "wavelength": wave["value"], "nan_policy": "raise"})
    if settings["target_efl"] is not None:
        problem.add_operand("f2", target=settings["target_efl"], weight=settings["efl_weight"], input_data={"optic": lens})
    before = _scalar(problem.rss(), "Initial optical merit")
    progress(.12, "Optimizing real traced rays within surface bounds")
    result = LeastSquares(problem).optimize(maxiter=settings["max_evaluations"], disp=False, plot=False,
                                            tol=1e-8, method_choice="trf")
    # Use the actual optimizer's final state, then independently retrace below.
    after = _scalar(problem.rss(), "Final optical merit")
    if after > before + max(1e-10, before * 1e-6):
        raise ValueError("Optimization increased the measured merit; no proposed prescription was published.")
    for spec, variable in zip(settings["variables"], problem.variables):
        value = _scalar(variable.variable.get_value(), "Optimized surface value")
        if value < spec["min"] - 1e-8 or value > spec["max"] + 1e-8:
            raise ValueError("Optimizer escaped a prescribed physical bound.")
        model["surfaces"][indices[spec["surface"]] - 1][spec["parameter"]] = value
    model = validate_optical_prescription(model)
    return model, {"algorithm": "Optiland LeastSquares / SciPy trust-region reflective", "merit": "root sum of squared weighted centroid RMS-spot residuals and optional EFL residual",
                   "before": before, "after": after, "converged": bool(result.success),
                   "status": int(result.status), "message": str(result.message), "function_evaluations": int(result.nfev),
                   "variables": settings["variables"], "applied_to_project": False}


def _tagged_native(value):
    """JSON-portable Optic.to_dict state; restore tagged floats before from_dict.

    Native Optiland uses infinity for the object plane and flat surfaces. JSON
    has no infinity value; an explicit tagged wrapper preserves it losslessly.
    This is never accepted as an executable/importable project recipe.
    """
    import numpy as np
    if isinstance(value, dict):
        # Catalogue/name fully identifies a Material for Optic.from_dict.
        # Upstream also serializes its installation-specific YAML filename;
        # omit that redundant absolute path so the state is portable.
        return {str(k): _tagged_native(v) for k, v in value.items()
                if not (k == "filename" and value.get("catalog") and value.get("name"))}
    if isinstance(value, (list, tuple)):
        return [_tagged_native(v) for v in value]
    if isinstance(value, np.ndarray):
        return _tagged_native(value.tolist())
    if isinstance(value, np.generic):
        return _tagged_native(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            raise ValueError("The native optical state contains NaN.")
        return {"__optiland_float__": "inf" if value > 0 else "-inf"}
    return value


def _analyze(lens, model, settings, directory, progress):
    import numpy as np
    import matplotlib.pyplot as plt
    from optiland.analysis import RayFan, SpotDiagram
    from optiland.mtf import FFTMTF
    from optiland.psf import FFTPSF
    fields = lens.fields.get_field_coords()
    waves = [w["value"] for w in model["wavelengths"]]
    primary = next(w["value"] for w in model["wavelengths"] if w["primary"])
    efl = _scalar(lens.paraxial.f2(), "Effective focal length")
    if efl <= 0:
        raise ValueError("Scalar image-space PSF analysis currently requires a positive-focus refractive system.")
    analysis = {"version": 1, "units": {"length": "mm", "wavelength": "um", "field": "degree", "mtf_frequency": "cycles/mm"},
                "paraxial": {"effective_focal_length_mm": efl, "f_number": _scalar(lens.paraxial.FNO(), "F-number"),
                             "back_focus_offset_from_image_mm": _scalar(lens.paraxial.F2(), "Back focus offset"),
                             "image_gap_mm": model["surfaces"][-1]["thickness"]},
                "fields": model["fields"], "wavelengths": model["wavelengths"], "sampling": settings,
                "spots": [], "fans": [], "diffraction": [],
                "scope": "Spot samples and real ray fans cover every authored field/wavelength. Scalar FFT PSF and incoherent MTF use the primary wavelength and the authored image plane; there is no hidden refocus, polarization or stray-light simulation."}
    progress(.3, "Tracing real pupil rays at all fields and wavelengths")
    spot = SpotDiagram(lens, fields="all", wavelengths="all", num_rings=settings["rings"], reference="centroid")
    spots_rms = _finite(spot.rms_spot_radius(), "RMS spots")
    fig, axes = plt.subplots(1, len(fields), figsize=(max(4, len(fields) * 3), 3.5), squeeze=False)
    with (directory / "rays.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["field_index", "wavelength_um", "ray_index", "surface_index", "x_mm", "y_mm", "z_mm", "relative_intensity"])
        for f_index, coord in enumerate(fields):
            ax = axes[0, f_index]
            for w_index, wave in enumerate(waves):
                data = spot.data[f_index][w_index]
                x, y, intensity = (_finite(v, "Spot samples") for v in (data.x, data.y, data.intensity))
                if not np.all(intensity > 0):
                    raise ValueError("Some sampled rays were blocked; this bounded workflow refuses an apparently complete spot/MTF result.")
                analysis["spots"].append({"field_index": f_index, "wavelength_um": wave, "ray_count": int(x.size),
                                           "rms_radius_mm": float(spots_rms[f_index, w_index]),
                                           "centroid_mm": [float(x.mean()), float(y.mean())],
                                           "x_mm": x.tolist(), "y_mm": y.tolist(), "relative_intensity": intensity.tolist()})
                ax.scatter((x - x.mean()) * 1000, (y - y.mean()) * 1000, s=4, label=f"{wave:g} µm")
                lens.trace(coord[0], coord[1], wave, num_rays=settings["rings"], distribution="hexapolar")
                # Infinite object-plane coordinates are intentionally excluded.
                sx, sy, sz, si = [_finite(np.asarray(a)[1:], "Real traced ray intersections")
                                   for a in (lens.surfaces.x, lens.surfaces.y, lens.surfaces.z, lens.surfaces.intensity)]
                for surface in range(sx.shape[0]):
                    for ray in range(sx.shape[1]):
                        writer.writerow([f_index, wave, ray, surface + 1, sx[surface, ray], sy[surface, ray], sz[surface, ray], si[surface, ray]])
            ax.set(title=f"Field {f_index + 1} · centroid", xlabel="x (µm)", ylabel="y (µm)", aspect="equal")
            ax.grid(alpha=.25)
        axes[0, 0].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(directory / "spot.svg")
        plt.close(fig)
    fan = RayFan(lens, fields="all", wavelengths="all", num_points=settings["fan_samples"])
    for f_index, field in enumerate(fan.fields):
        for wavelength in fan.wavelengths:
            entry = fan.data[str(field.coord)][str(wavelength.value)]
            for axis in ("x", "y"):
                displacement = _finite(entry[axis], "Ray fan")
                intensity = _finite(entry["intensity_" + axis], "Ray-fan intensity")
                if not (intensity > 0).all():
                    raise ValueError("A sampled fan ray was blocked; no complete aberration result was published.")
                analysis["fans"].append({"pupil_axis": axis, "field_index": f_index,
                                          "wavelength_um": float(wavelength.value),
                                          "normalized_pupil": _finite(fan.data["P" + axis], "Fan pupil").tolist(),
                                          "displacement_mm": displacement.tolist(), "relative_intensity": intensity.tolist()})
    analysis["third_order_seidel_sums"] = dict(zip(("spherical", "coma", "astigmatism", "field_curvature", "distortion"),
                                                   _finite(lens.aberrations.seidels(), "Third-order Seidel sums").tolist()))
    analysis["third_order_seidel_convention"] = "Optiland third_order Seidel wavefront coefficients in lens units (mm); paraxial third-order approximation, not a full-field error budget."
    progress(.55, "Computing actual scalar FFT diffraction and modulation transfer")
    mtf = FFTMTF(lens, fields=fields, wavelength=primary, num_rays=settings["pupil_samples"], grid_size=settings["fft_grid"])
    psfs = []
    fig, axes = plt.subplots(1, len(fields), figsize=(max(4, len(fields) * 3), 3.5), squeeze=False)
    for f_index, coord in enumerate(fields):
        # Retain the engine PSF and physical units, with energy-normalized data
        # in NPZ for reuse. Preview contrast is explicitly logarithmic.
        psf = FFTPSF(lens, coord, primary, num_rays=settings["pupil_samples"], grid_size=settings["fft_grid"])
        values = _finite(psf.psf, "Scalar FFT PSF")
        total = float(values.sum())
        if total <= 0 or values.min() < 0:
            raise ValueError("Scalar diffraction returned no physical point-spread energy.")
        psfs.append(values / total)
        extents = [_scalar(v, "PSF physical extent") for v in psf._get_psf_units(values)]
        tangential, sagittal = [_finite(v, "MTF") for v in mtf.mtf[f_index]]
        if not np.isclose(tangential[0], 1) or not np.isclose(sagittal[0], 1):
            raise ValueError("The MTF did not normalize to unity at zero spatial frequency.")
        analysis["diffraction"].append({"field_index": f_index, "wavelength_um": primary,
                                         "strehl_ratio": _scalar(psf.strehl_ratio(), "Strehl ratio"),
                                         "psf_extent_um": extents, "psf_shape": list(values.shape),
                                         "psf_energy_normalized_sum": float(psfs[-1].sum()),
                                         "frequency_tangential_cycles_per_mm": _finite(mtf.freq_tang[f_index], "Tangential frequency").tolist(),
                                         "frequency_sagittal_cycles_per_mm": _finite(mtf.freq_sag[f_index], "Sagittal frequency").tolist(),
                                         "tangential_mtf": tangential.tolist(), "sagittal_mtf": sagittal.tolist()})
        ax = axes[0, f_index]
        ax.imshow(np.log10(np.maximum(values / values.max(), 1e-6)), origin="lower", cmap="magma", vmin=-6, vmax=0,
                  extent=[-extents[0] / 2, extents[0] / 2, -extents[1] / 2, extents[1] / 2])
        ax.set(title=f"Field {f_index + 1} · log10 intensity", xlabel="x (µm)", ylabel="y (µm)")
    fig.tight_layout()
    fig.savefig(directory / "psf.png", dpi=130)
    plt.close(fig)
    np.savez_compressed(directory / "psf.npz", psf_energy_normalized=np.stack(psfs), wavelength_um=np.array(primary),
                        field_angles_degrees=np.array([[f["x"], f["y"]] for f in model["fields"]]),
                        extent_um=np.array([d["psf_extent_um"] for d in analysis["diffraction"]]))
    with (directory / "mtf.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["field_index", "wavelength_um", "tangential_cycles_per_mm", "tangential_mtf", "sagittal_cycles_per_mm", "sagittal_mtf"])
        for item in analysis["diffraction"]:
            for values in zip(item["frequency_tangential_cycles_per_mm"], item["tangential_mtf"], item["frequency_sagittal_cycles_per_mm"], item["sagittal_mtf"]):
                writer.writerow([item["field_index"], primary, *values])
    fig, ax = mtf.view(add_reference=True)
    fig.tight_layout()
    fig.savefig(directory / "mtf.svg")
    plt.close(fig)
    fig, ax = lens.draw(fields="all", wavelengths="primary", num_rays=7, show=False, figsize=(10, 4), title=model["name"])
    fig.tight_layout()
    fig.savefig(directory / "layout.svg")
    plt.close(fig)
    return analysis


def _run(request, runtime):
    recipe = validate_ray_optics_recipe(request["recipe"])
    if hashlib.sha256(_json(recipe)).hexdigest() != request["recipe_sha256"]:
        raise ValueError("Optical recipe identity changed before execution.")
    scratch = Path(request["scratch"])
    if not scratch.is_absolute() or scratch.is_symlink() or not scratch.is_dir():
        raise ValueError("Worker scratch directory must be an existing owned directory.")
    directory = scratch / "result"
    directory.mkdir()
    started = time.monotonic()
    def progress(fraction, message):
        staging = scratch / "progress.tmp"
        staging.write_bytes(_json({"fraction": fraction, "message": message}))
        os.replace(staging, scratch / "progress.json")
    progress(.05, "Resolving exact packaged glass dispersion models")
    lens, materials = _build(recipe["prescription"])
    model, optimization = recipe["prescription"], None
    if recipe["operation"] == "optimize":
        model, optimization = _optimize(lens, recipe, progress)
        lens, materials = _build(model)  # reconstruct from the serializable proposed authoring state
    analysis = _analyze(lens, model, recipe["analysis"], directory, progress)
    analysis["materials"] = materials
    analysis["optimization"] = optimization
    progress(.88, "Binding numerical artifacts to prescription and source provenance")
    (directory / "prescription.json").write_bytes(_json(model))
    (directory / "analysis.json").write_bytes(_json(analysis))
    native = {"format": "cinematicum-optiland-state", "version": 1, "engine_version": RUNTIME_REQUIREMENTS["optiland"],
              "nonfinite_encoding": "{\"__optiland_float__\":\"inf\"} or \"-inf\"; restore to float before Optic.from_dict",
              "optic": _tagged_native(lens.to_dict())}
    (directory / "optiland.json").write_bytes(_json(native))
    inventory = {name: _hash(directory / name) for name in sorted(ARTIFACT_NAMES - {"receipt.json"})}
    receipt = {"version": 1, "kind": "optiland-sequential-optics", "output_id": request["output_id"],
               "recipe_sha256": request["recipe_sha256"], "project_sha256": request["project_sha256"],
               "recipe": recipe, "result_prescription_sha256": inventory["prescription.json"]["sha256"],
               "runtime": runtime, "artifacts": inventory, "elapsed_seconds": round(time.monotonic() - started, 6),
               "limitations": _doctor(runtime)["scope"]}
    (directory / "receipt.json").write_bytes(_json(receipt))
    progress(1, "Optical analysis complete; proposed prescription awaits explicit apply")
    return {"complete": True, "output_id": request["output_id"]}


def main():
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Optical worker input is too large.")
        request = json.loads(raw)
        with contextlib.redirect_stdout(sys.stderr):
            runtime = _runtime()
            if request.get("command") == "doctor":
                response = _doctor(runtime)
            elif request.get("command") == "catalog":
                response = _catalog(request["query"], request["limit"])
            elif request.get("command") == "run":
                response = _run(request, runtime)
            else:
                raise ValueError("Unsupported optical worker command.")
        sys.stdout.buffer.write(_json(response))
        return 0
    except Exception as exc:
        sys.stdout.buffer.write(_json({"error": f"{type(exc).__name__}: {exc}"[:2000]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

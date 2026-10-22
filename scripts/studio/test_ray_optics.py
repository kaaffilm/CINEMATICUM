"""Actual Optiland physics, numerical artifacts and owned-job boundaries.

Requires the pinned isolated runtime via CINEMATICUM_OPTICS_PYTHON (or managed
Optics install). A missing runtime fails this acceptance module; no fake worker
or successful skipped optional test is substituted for optical calculations.
"""
import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import ray_optics as optics


class OpticalPrescriptionTests(unittest.TestCase):
    def test_default_prescription_roundtrips_without_mutating_input(self):
        source = optics.default_prescription()
        original = copy.deepcopy(source)
        normal = optics.validate_optical_prescription(source)
        self.assertEqual(normal, original)
        normal["surfaces"][0]["radius"] = 60
        self.assertEqual(source, original)

    def test_rejects_unbounded_invalid_or_ambiguous_physics_inputs(self):
        cases = []
        for change in ({"version": True}, {"units": "inch"}, {"object_distance": -1}, {"script": "print(1)"},
                       {"aperture": {"type": "EPD", "value": True}}, {"fields": []},
                       {"wavelengths": [{"value": .55, "primary": False}]}):
            cases.append({**optics.default_prescription(), **change})
        for key, value in (("radius", 0), ("radius", float("nan")), ("thickness", -1),
                           ("id", "../../outside"), ("material", {"type": "catalog", "catalog": "../../x", "name": "N-BK7"}),
                           ("coefficients", [float("inf")]), ("stop", False)):
            model = optics.default_prescription(); model["surfaces"][0][key] = value; cases.append(model)
        model = optics.default_prescription(); model["surfaces"][-1]["material"] = {"type": "constant", "index": 1.5}; cases.append(model)
        for model in cases:
            with self.subTest(model=model), self.assertRaises(ValueError):
                optics.validate_optical_prescription(model)

    def test_bounded_optimization_cannot_cross_singular_radii_or_unknown_fields(self):
        base = {"version": 1, "operation": "optimize", "prescription": optics.default_prescription(),
                "optimization": {"variables": [{"surface": "s2", "parameter": "thickness", "min": 40, "max": 55}]}}
        self.assertEqual(optics.validate_ray_optics_recipe(base)["optimization"]["max_evaluations"], 60)
        for variables in ([], [{"surface": "s1", "parameter": "radius", "min": -60, "max": 60}],
                          [{"surface": "s2", "parameter": "thickness", "min": 50, "max": 60}],
                          [{"surface": "s2", "parameter": "__class__", "min": 1, "max": 2}],
                          base["optimization"]["variables"] * 2):
            with self.subTest(variables=variables), self.assertRaises(ValueError):
                optics.validate_ray_optics_recipe({**base, "optimization": {"variables": variables}})
        for analysis in ({"fft_grid": 100}, {"pupil_samples": 128, "fft_grid": 128}, {"rings": 2.5}, {"shader": "code"}):
            with self.subTest(analysis=analysis), self.assertRaises(ValueError):
                optics.validate_ray_optics_recipe({**base, "analysis": analysis})

    def test_missing_runtime_is_an_explicit_unavailable_capability(self):
        result = optics.ray_optics_capabilities("/no-such-optics-runtime/python")
        self.assertFalse(result["available"])
        self.assertEqual(result["operations"], [])
        self.assertIn("not installed", result["reason"])
        self.assertEqual(result["default_prescription"], optics.default_prescription())

    def test_editor_import_does_not_import_optional_scientific_packages(self):
        script = "import sys;sys.path.insert(0,sys.argv[1]);import ray_optics;assert not any(x in sys.modules for x in ('numpy','scipy','optiland'));print('stdlib-only')"
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(Path(__file__).parent)],
                                check=True, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.stdout.strip(), "stdlib-only")

    def test_managed_wheel_locks_pin_complete_platform_dependency_closures(self):
        import install_ray_optics as installer
        for target in ("macos-arm64-py313", "linux-x86_64-py312"):
            lock, digest = installer.load_lock(target)
            self.assertEqual(len(lock["packages"]), 26)
            self.assertRegex(digest, r"^[a-f0-9]{64}$")
            self.assertEqual({p["name"]: p["version"] for p in lock["packages"]}, installer.PINNED_PACKAGES)
            for package in lock["packages"]:
                self.assertTrue(package["url"].startswith("https://files.pythonhosted.org/packages/"))
                self.assertRegex(package["sha256"], r"^[a-f0-9]{64}$")
            # This is an installer report-contract test, not substituted optical
            # execution: actual installed packages/physics run in the class below.
            report = {"install": [{"metadata": {"name": p["name"], "version": p["version"]},
                                    "download_info": {"url": p["url"], "archive_info": {"hashes": {"sha256": p["sha256"]}}}}
                                   for p in lock["packages"]]}
            with tempfile.TemporaryDirectory(prefix="cinematicum-optics-lock-TEST-") as directory:
                path = Path(directory) / "pip-report.json"; path.write_text(json.dumps(report)); installer.verify_pip_report(path, lock)
                report["install"][0]["download_info"]["archive_info"]["hashes"]["sha256"] = "0" * 64
                path.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, "different version, URL or hash"):
                    installer.verify_pip_report(path, lock)

    def test_installer_preserves_unrelated_existing_directory_and_link(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-preserve-TEST-") as directory:
            root = Path(directory); destination = root / "existing"; destination.mkdir()
            sentinel = destination / "owned-by-user.txt"; sentinel.write_text("keep this")
            with self.assertRaisesRegex(ValueError, "unmanaged optics destination"):
                installer.install(destination, check_only=True)
            link = root / "unrelated-link"; link.symlink_to(destination, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unrelated optics symlink"):
                installer.install(link, check_only=True)
            self.assertEqual(sentinel.read_text(), "keep this")
            self.assertFalse((root / installer.VERSIONS_DIRECTORY).exists())


class OpticsInstallerTests(unittest.TestCase):
    """Installer isolation, cancellation and durable byte-identity boundaries."""
    def test_explicit_foreground_budget_is_bounded_before_any_setup(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-budget-TEST-") as temporary:
            destination = Path(temporary) / "new" / "runtime"
            for budget in (None, False, 0, -1, 61, 1.5, float("inf"), "60"):
                for operation in (installer.step, installer.install):
                    with self.subTest(budget=budget, operation=operation.__name__), self.assertRaisesRegex(ValueError, "phase budget"):
                        operation(destination, phase_budget_seconds=budget)
            self.assertFalse(destination.parent.exists())
            self.assertEqual(installer.info(destination)["phase_budget_seconds"], 14)

    def test_longer_foreground_check_still_rejects_bytes_changed_by_probe(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-budget-drift-TEST-") as temporary:
            root = Path(temporary); destination = root / "runtime"
            name = installer._target()[2] + "-" + "1" * 32
            runtime = root / installer.VERSIONS_DIRECTORY / name
            runtime.mkdir(parents=True)
            data = runtime / "identity-boundary-fixture.txt"
            data.write_text("before probe")
            receipt = {"schema": "cinematicum-optics-install", "version": 2,
                "wheel_lock_sha256": installer.load_lock()[1], "runtime_directory": str(runtime),
                "stable_destination": str(destination), "base_python": sys.executable,
                "base_python_identity": installer._base_identity(sys.executable),
                "inventory": installer._inventory(runtime)}
            installer._save_state(runtime / installer.RECEIPT, receipt)
            destination.symlink_to(Path(installer.VERSIONS_DIRECTORY) / name, target_is_directory=True)
            def change_bytes(_runtime, event):
                self.assertFalse(event.is_set())
                data.write_text("changed during probe")
                return {"scope": "test control flow only; no optical acceptance asserted"}
            with patch.object(installer, "probe_runtime", side_effect=change_bytes):
                with self.assertRaisesRegex(ValueError, "changed during actual numerical verification"):
                    installer.install(destination, check_only=True, phase_budget_seconds=60)
            self.assertEqual(json.loads((runtime / installer.RECEIPT).read_text()), receipt)

    def test_info_and_isolated_cli_do_not_create_runtime_or_import_engine(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-info-TEST-") as temporary:
            destination = Path(temporary) / "new" / "runtime"
            details = installer.info(destination)
            self.assertTrue(details["bounded_step"])
            self.assertEqual(details["phase_budget_seconds"], 14)
            self.assertEqual(len(details["packages"]), 26)
            self.assertFalse(destination.parent.exists())
            result = subprocess.run([sys.executable, "-I", "-B", installer.__file__, "--info", "--destination", str(destination)],
                                    capture_output=True, text=True, check=True, timeout=10)
            self.assertEqual(json.loads(result.stdout), details)
            self.assertFalse(destination.parent.exists())
            code = "import sys;sys.path.insert(0,sys.argv[1]);import install_ray_optics;print([n for n in ('numpy','optiland','scipy') if n in sys.modules])"
            result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(Path(installer.__file__).parent)],
                                    capture_output=True, text=True, check=True, timeout=10)
            self.assertEqual(result.stdout.strip(), "[]")

    def test_cancelled_setup_creates_no_runtime_parent_or_pending_record(self):
        import install_ray_optics as installer
        event = threading.Event(); event.set()
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-cancel-TEST-") as temporary:
            destination = Path(temporary) / "new" / "runtime"
            with self.assertRaises(InterruptedError):
                installer.step(destination, cancel_event=event)
            self.assertFalse(destination.parent.exists())

    def test_native_venv_phase_resumes_exact_owned_journal_and_refuses_other_destination(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-resume-TEST-") as temporary:
            root = Path(temporary); destination = root / "runtime"
            first = installer.step(destination, python=sys.executable)
            self.assertEqual(first["phase"], "venv")
            state = json.loads((root / installer.PENDING).read_text())
            runtime = root / installer.VERSIONS_DIRECTORY / state["runtime_name"]
            marker = (runtime / "owner.json").read_bytes()
            second = installer.step(destination, python=sys.executable)
            self.assertEqual(second["phase"], "ensurepip")
            self.assertTrue((runtime / "pyvenv.cfg").is_file())
            self.assertFalse(destination.exists())
            self.assertEqual((runtime / "owner.json").read_bytes(), marker)
            with self.assertRaisesRegex(ValueError, "pending optics installation"):
                installer.step(root / "different-runtime")
            self.assertEqual(json.loads((root / installer.PENDING).read_text())["runtime_name"], state["runtime_name"])

    def test_drifted_verification_is_invalidated_before_publication(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-drift-TEST-") as temporary:
            root = Path(temporary); destination = root / "runtime"
            installer.step(destination, python=sys.executable)
            journal = root / installer.PENDING; state = json.loads(journal.read_text())
            runtime = root / installer.VERSIONS_DIRECTORY / state["runtime_name"]
            # A stale acceptance record cannot substitute for another run of
            # actual physics. Full installed physics is checked separately.
            state["phase"] = "inventory"; installer._save_state(journal, state)
            sources = installer._source_identity(); sources["ray_optics_worker.py"] = "0" * 64
            installer._save_state(runtime / "optics-acceptance.json", {"verification_sources": sources})
            with self.assertRaisesRegex(ValueError, "source changed"):
                installer.step(destination)
            self.assertEqual(json.loads(journal.read_text())["phase"], "verify")
            self.assertFalse(os.path.lexists(destination))
            self.assertFalse((runtime / installer.RECEIPT).exists())

    def test_chunk_resume_requires_exact_bytes_and_preserves_bad_partial_for_diagnosis(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-bytes-TEST-") as temporary:
            root = Path(temporary); cache = root / "cache"; cache.mkdir(); owned = root / "owned"; owned.mkdir()
            # Byte-transport fixture, not a substitute Optiland package/runtime.
            data = b"bounded wheel transport\0" * 400000
            package = {"filename": "transport_fixture-1-py3-none-any.whl", "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
            source = cache / package["filename"]; source.write_bytes(data)
            partial = owned / (source.name + ".part")
            self.assertFalse(installer._download_chunk(owned, package, wheel_cache=cache))
            self.assertEqual(partial.stat().st_size, installer.CHUNK_BYTES)
            self.assertFalse(installer._download_chunk(owned, package, wheel_cache=cache))
            self.assertEqual(partial.stat().st_size, 2 * installer.CHUNK_BYTES)
            self.assertTrue(installer._download_chunk(owned, package, wheel_cache=cache))
            self.assertEqual((owned / source.name).read_bytes(), data)
            self.assertFalse(partial.exists())
            bad = root / "bad"; bad.mkdir(); bad_partial = bad / partial.name
            bad_partial.write_bytes(b"!" * installer.CHUNK_BYTES)
            self.assertFalse(installer._download_chunk(bad, package, wheel_cache=cache))
            with self.assertRaisesRegex(ValueError, "exact pinned SHA-256"):
                installer._download_chunk(bad, package, wheel_cache=cache)
            self.assertTrue(bad_partial.is_file())
            self.assertFalse((bad / source.name).exists())
            self.assertEqual(source.read_bytes(), data)

    def test_wheel_links_and_foreign_pending_ownership_are_never_adopted(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-links-TEST-") as temporary:
            root = Path(temporary); source = root / "original"; source.write_bytes(b"original")
            cache = root / "cache"; cache.mkdir(); owned = root / "owned"; owned.mkdir()
            package = {"filename": "linked-1-py3-none-any.whl", "size": 8, "sha256": hashlib.sha256(b"original").hexdigest()}
            (cache / package["filename"]).symlink_to(source)
            with self.assertRaises(OSError):
                installer._download_chunk(owned, package, wheel_cache=cache)
            destination = root / "runtime"; installer.step(destination, python=sys.executable)
            state = json.loads((root / installer.PENDING).read_text())
            marker = root / installer.VERSIONS_DIRECTORY / state["runtime_name"] / "owner.json"
            original = marker.read_bytes(); marker.write_text("{}")
            with self.assertRaisesRegex(ValueError, "ownership marker"):
                installer.step(destination)
            self.assertFalse(os.path.lexists(destination))
            self.assertEqual(marker.read_text(), "{}")
            self.assertNotEqual(original, marker.read_bytes())
            self.assertEqual(source.read_bytes(), b"original")

    def test_complete_inventory_detects_added_empty_files_links_bytes_and_modes(self):
        import install_ray_optics as installer
        with tempfile.TemporaryDirectory(prefix="cinematicum-optics-inventory-TEST-") as temporary:
            root = Path(temporary); (root / "directory").mkdir()
            file = root / "directory" / "module.py"; file.write_bytes(b"value=1\n")
            (root / "empty").write_bytes(b""); (root / "link").symlink_to("directory/module.py")
            before = installer._inventory(root)
            self.assertEqual(set(before), {"directory", "directory/module.py", "empty", "link"})
            self.assertEqual(before["empty"]["bytes"], 0)
            self.assertEqual(before["link"]["link"], "directory/module.py")
            file.chmod(0o700)
            self.assertNotEqual(installer._inventory(root), before)
            file.chmod(before["directory/module.py"]["mode"])
            file.write_bytes(b"value=2\n")
            self.assertNotEqual(installer._inventory(root), before)
            file.write_bytes(b"value=1\n"); (root / "additional").write_bytes(b"")
            self.assertNotEqual(installer._inventory(root), before)


class ActualOptilandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = optics.find_ray_optics_python()
        if not cls.python:
            raise RuntimeError("Actual ray-optics acceptance requires CINEMATICUM_OPTICS_PYTHON or the managed Optics runtime; no skipped or fake inference is accepted.")
        cls.capability = optics.ray_optics_capabilities(cls.python)
        if not cls.capability["available"]:
            raise RuntimeError(cls.capability.get("reason", "Optiland is unavailable"))
        cls.temp = tempfile.TemporaryDirectory(prefix="cinematicum-OPTICS-TEST-")
        cls.root = Path(cls.temp.name)
        cls.project = {"id": "actual-optics", "name": "Actual optical physics acceptance", "assets": [], "clips": []}
        cls.recipe = {"version": 1, "operation": "analyze", "prescription": optics.default_prescription()}
        cls.baseline = optics.run_ray_optics(cls.project, cls.root, cls.recipe, cls.root / "optics/outputs/baseline", python=cls.python)
        if list((cls.root / "optics/outputs").glob(".baseline-building-*")):
            raise AssertionError("The completed baseline retained its owned scratch directory")
        cls.addClassCleanup(cls.temp.cleanup)

    def runtime(self, code, *args):
        # Independent upstream restoration calls may JIT Numba kernels too.
        # Keep their caches in owned test scratch, just as the product worker
        # does, rather than adding bytecode beside the installed packages.
        with tempfile.TemporaryDirectory(prefix="upstream-cache-", dir=self.root) as cache:
            result = subprocess.run([self.python, "-I", "-B", "-c", code, *map(str, args)], check=True,
                                    capture_output=True, text=True, timeout=35, env=optics._environment(cache))
        return json.loads(result.stdout)

    def run_model(self, name, model, **changes):
        result = optics.run_ray_optics(self.project, self.root,
                                      {"version": 1, "operation": "analyze", "prescription": model, **changes},
                                      self.root / "optics/outputs" / name, python=self.python)
        self.assertFalse(list((self.root / "optics/outputs").glob(f".{name}-building-*")), "A completed job retained its owned scratch")
        return result

    def test_actual_runtime_and_exact_glass_catalogue(self):
        self.assertEqual(self.capability["runtime"]["packages"]["optiland"], "0.6.3")
        catalog = optics.ray_optics_catalog("N-BK7", python=self.python)
        self.assertIn({"catalog": "schott", "name": "N-BK7"}, catalog["materials"])
        self.assertIn("ohara", catalog["catalogs"])
        self.assertEqual(catalog["match_policy"], "exact")
        material = self.baseline["analysis"]["materials"][0]
        self.assertAlmostEqual(material["refractive_indices"][1]["n"], 1.51680003, places=7)
        self.assertGreater(material["refractive_indices"][0]["n"], material["refractive_indices"][2]["n"])
        self.assertRegex(material["catalog_file"]["sha256"], "^[0-9a-f]{64}$")

    def test_actual_runtime_has_every_pinned_transitive_distribution(self):
        import install_ray_optics as installer
        names = list(installer.PINNED_PACKAGES)
        report = self.runtime("import importlib.metadata as m,json,sys;names=json.loads(sys.argv[1]);print(json.dumps({n:m.version(n) for n in names}))", json.dumps(names))
        self.assertEqual(report, installer.PINNED_PACKAGES)

    def test_actual_cold_plot_cache_uses_only_pinned_bundled_fonts(self):
        inherited = {"MPLCONFIGDIR": str(self.root / "inherited-font-cache"),
                     "MPL_IGNORE_SYSTEM_FONTS": "", "MPLBACKEND": "invalid-inherited-backend"}
        previous = {key: os.environ.get(key) for key in inherited}
        try:
            os.environ.update(inherited)
            report = self.runtime("""import json,sys
from pathlib import Path
calls=[]
def audit(event,args):
 if event=='subprocess.Popen': calls.append(Path(args[0]).name)
sys.addaudithook(audit)
import matplotlib as mpl
from matplotlib import font_manager as fm
data=Path(mpl.get_data_path()).resolve()
fonts=fm.fontManager.ttflist+fm.fontManager.afmlist
print(json.dumps({'font_count':len(fonts),
 'only_bundled':all(Path(font.fname).resolve().is_relative_to(data) for font in fonts),
 'system_fonts':fm.findSystemFonts(),
 'default_font':Path(fm.findfont('DejaVu Sans')).resolve().relative_to(data).as_posix(),
 'private_cache':Path(mpl.get_cachedir()).resolve().is_relative_to(Path(sys.argv[1]).resolve()),
 'backend':mpl.get_backend(),'processes':calls}))""", self.root)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertGreater(report["font_count"], 0)
        self.assertTrue(report["only_bundled"])
        self.assertTrue(report["private_cache"])
        self.assertEqual(report["system_fonts"], [])
        self.assertEqual(report["default_font"], "fonts/ttf/DejaVuSans.ttf")
        self.assertEqual(report["backend"].lower(), "agg")
        self.assertFalse(set(report["processes"]) & {"system_profiler", "fc-list", "fc-match"})
        self.assertFalse(Path(inherited["MPLCONFIGDIR"]).exists())

    def test_installer_runs_real_catalogue_ray_and_diffraction_gates_with_source_binding(self):
        import install_ray_optics as installer
        report = installer.probe_runtime(Path(self.python).parent.parent)
        self.assertEqual(report["versions"], installer.PINNED_PACKAGES)
        self.assertEqual(set(report["checks"]), {"catalog_dispersion", "thick_lens_focal_length", "real_ray_spot",
                                                "diffraction_strehl", "mtf_normalization", "complete_artifacts"})
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["verification_sources"], installer._source_identity())

    def test_effective_focal_length_matches_independent_thick_lens_equation(self):
        n = self.baseline["analysis"]["materials"][0]["refractive_indices"][1]["n"]
        # Lensmaker equation in air, R1=+50, R2=-50, center thickness=5 mm.
        power = (n - 1) * (1 / 50 - 1 / -50 + (n - 1) * 5 / (n * 50 * -50))
        self.assertAlmostEqual(self.baseline["analysis"]["paraxial"]["effective_focal_length_mm"], 1 / power, places=9)
        self.assertAlmostEqual(self.baseline["analysis"]["paraxial"]["f_number"], 1 / power / 10, places=9)
        self.assertLess(abs(self.baseline["analysis"]["paraxial"]["back_focus_offset_from_image_mm"]), 1e-8)

    def test_actual_rays_are_refracted_and_chromatic_spots_change(self):
        path = self.root / self.baseline["artifacts"]["rays.csv"]["path"]
        with path.open() as file:
            rows = list(csv.DictReader(file))
        self.assertGreater(len(rows), 1000)
        marginal = [r for r in rows if r["field_index"] == "0" and r["wavelength_um"] == "0.5875618"]
        first = [abs(float(r["y_mm"])) for r in marginal if r["surface_index"] == "1"]
        last = [abs(float(r["y_mm"])) for r in marginal if r["surface_index"] == "3"]
        self.assertGreater(max(first), 4.9)
        self.assertLess(max(last), max(first) / 10)
        spots = self.baseline["analysis"]["spots"]
        self.assertEqual(len(spots), 9)
        self.assertGreater(len({round(s["rms_radius_mm"], 9) for s in spots}), 6)
        self.assertEqual(len(self.baseline["analysis"]["fans"]), 18)
        self.assertNotEqual(self.baseline["analysis"]["third_order_seidel_sums"]["spherical"], 0)

    def test_psf_is_real_nonnegative_energy_and_mtf_matches_independent_fft(self):
        path = self.root / self.baseline["artifacts"]["psf.npz"]["path"]
        data = self.runtime("""import numpy as n,json,sys
a=n.load(sys.argv[1],allow_pickle=False);p=a['psf_energy_normalized'];out=[]
for image in p:
 o=n.abs(n.fft.fftshift(n.fft.fft2(image)));c=o.shape[0]//2
 out.append({'sum':float(image.sum()),'min':float(image.min()),'tangential':(o[c:,c]/o[c,c]).tolist(),'sagittal':(o[c,c:]/o[c,c]).tolist()})
print(json.dumps(out))""", path)
        for actual, result in zip(data, self.baseline["analysis"]["diffraction"]):
            self.assertAlmostEqual(actual["sum"], 1, places=12)
            self.assertGreaterEqual(actual["min"], 0)
            self.assertAlmostEqual(result["tangential_mtf"][0], 1, places=12)
            for key in ("tangential", "sagittal"):
                for value, expected in zip(result[key + "_mtf"], actual[key]):
                    self.assertAlmostEqual(value, expected, places=10)
            self.assertTrue(all(b > a for a, b in zip(result["frequency_tangential_cycles_per_mm"], result["frequency_tangential_cycles_per_mm"][1:])))

    def test_real_small_aperture_approaches_diffraction_limited_strehl(self):
        model = optics.default_prescription(); model["aperture"]["value"] = 1
        model["fields"] = [model["fields"][0]]; model["wavelengths"] = [model["wavelengths"][1]]
        result = self.run_model("small-aperture", model)
        self.assertGreater(result["analysis"]["diffraction"][0]["strehl_ratio"], .98)
        self.assertLess(result["analysis"]["spots"][0]["rms_radius_mm"], .0001)

    def test_actual_optimization_improves_defocused_lens_and_requires_explicit_apply(self):
        model = optics.default_prescription(); model["aperture"]["value"] = 5
        model["fields"] = [model["fields"][0]]; model["wavelengths"] = [model["wavelengths"][1]]
        model["surfaces"][-1]["thickness"] = 44
        before_project, before_model = copy.deepcopy(self.project), copy.deepcopy(model)
        result = self.run_model("optimized", model, operation="optimize", optimization={
            "variables": [{"surface": "s2", "parameter": "thickness", "min": 40, "max": 55}],
            "max_evaluations": 50, "target_efl": 49.2129957616})
        measured = result["analysis"]["optimization"]
        self.assertTrue(measured["converged"])
        self.assertLess(measured["after"], measured["before"] / 30)
        self.assertGreater(result["analysis"]["diffraction"][0]["strehl_ratio"], .8)
        self.assertTrue(47 < result["prescription"]["surfaces"][-1]["thickness"] < 48)
        self.assertEqual(self.project, before_project); self.assertEqual(model, before_model)
        self.assertFalse(measured["applied_to_project"])

    def test_native_state_restores_into_real_upstream_optic_and_has_no_install_paths(self):
        path = self.root / self.baseline["artifacts"]["optiland.json"]["path"]
        self.assertNotIn(str(Path(self.python).parent.parent), path.read_text())
        restored = self.runtime("""import json,sys
from optiland import optic
def restore(v):
 if isinstance(v,dict):
  if set(v)=={'__optiland_float__'}:return float(v['__optiland_float__'])
  return {k:restore(x) for k,x in v.items()}
 if isinstance(v,list):return [restore(x) for x in v]
 return v
l=optic.Optic.from_dict(restore(json.load(open(sys.argv[1]))['optic']))
r=l.trace(0,0,l.primary_wavelength,4)
print(json.dumps({'efl':float(l.paraxial.f2()),'y':r.y.tolist()}))""", path)
        self.assertAlmostEqual(restored["efl"], self.baseline["analysis"]["paraxial"]["effective_focal_length_mm"], places=9)
        self.assertGreater(len(restored["y"]), 30)

    def test_even_asphere_and_conic_are_actual_surface_geometry(self):
        model = optics.default_prescription(); model["fields"] = [model["fields"][0]]
        model["surfaces"][0]["conic"] = -.5; model["surfaces"][0]["coefficients"] = [-1e-6]
        result = self.run_model("asphere", model)
        self.assertEqual(result["prescription"]["surfaces"][0]["coefficients"], [-1e-6])
        old = next(s["rms_radius_mm"] for s in self.baseline["analysis"]["spots"] if s["field_index"] == 0 and s["wavelength_um"] == .5875618)
        new = next(s["rms_radius_mm"] for s in result["analysis"]["spots"] if s["wavelength_um"] == .5875618)
        self.assertGreater(abs(old - new), .00001)

    def test_invalid_glass_fails_real_resolution_without_publishing(self):
        model = optics.default_prescription(); model["surfaces"][0]["material"]["name"] = "N-BK7-unavailable"
        with self.assertRaisesRegex(ValueError, "exact packaged material"):
            self.run_model("invalid-glass", model)
        self.assertFalse((self.root / "optics/outputs/invalid-glass").exists())
        self.assertFalse(list((self.root / "optics/outputs").glob(".invalid-glass-building-*")))

    def test_artifact_receipts_bind_every_file_recipe_project_and_source(self):
        self.assertEqual(set(self.baseline["artifacts"]), optics.ARTIFACT_NAMES)
        receipt = self.baseline["receipt"]
        self.assertEqual(receipt["recipe_sha256"], hashlib.sha256(optics._json_bytes(optics.validate_ray_optics_recipe(self.recipe))).hexdigest())
        self.assertEqual(receipt["project_sha256"], hashlib.sha256(optics._json_bytes(self.project)).hexdigest())
        for name, artifact in self.baseline["artifacts"].items():
            path = self.root / artifact["path"]
            self.assertEqual(path.stat().st_size, artifact["size"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])
            if name != "receipt.json": self.assertEqual(receipt["artifacts"][name], {k: artifact[k] for k in ("size", "sha256")})
        self.assertEqual(receipt["runtime"]["worker_sha256"], hashlib.sha256(Path(optics.__file__).with_name("ray_optics_worker.py").read_bytes()).hexdigest())

    def test_cancellation_terminates_owned_worker_without_partial_publication(self):
        event = threading.Event(); timer = threading.Timer(.3, event.set); timer.start()
        try:
            with self.assertRaises(InterruptedError):
                optics.run_ray_optics(self.project, self.root, self.recipe, self.root / "optics/outputs/cancelled", cancel_event=event, python=self.python)
        finally:
            timer.cancel()
        self.assertFalse((self.root / "optics/outputs/cancelled").exists())
        self.assertFalse(list((self.root / "optics/outputs").glob(".cancelled-building-*")))

    def test_outputs_cannot_escape_overwrite_or_follow_symlinks(self):
        with self.assertRaises(ValueError):
            optics.run_ray_optics(self.project, self.root, self.recipe, self.root.parent / "unowned-optics-output", python=self.python)
        with self.assertRaisesRegex(ValueError, "already exists"):
            optics.run_ray_optics(self.project, self.root, self.recipe, self.root / "optics/outputs/baseline", python=self.python)
        target = self.root / "optics/outputs/linked"; target.symlink_to(self.root / "optics/outputs/baseline", target_is_directory=True)
        with self.assertRaises(ValueError):
            optics.run_ray_optics(self.project, self.root, self.recipe, target, python=self.python)
        self.assertEqual(optics._command(self.python)[1:3], ["-I", "-B"])


if __name__ == "__main__":
    unittest.main()

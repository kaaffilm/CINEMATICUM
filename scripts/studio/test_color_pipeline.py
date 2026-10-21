"""Measured float-pixel acceptance tests; all pixels are synthetic test signals."""
import copy
import array
import hashlib
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from color_pipeline import (CubeLUT, WHITEPOINTS, chromatic_adaptation_matrix,
                            compile_pipeline, decode_transfer, encode_transfer,
                            import_cube, input_matrix, list_luts, load_lut,
                            parse_cube, rgb_to_xyz_matrix, sample_lut,
                            transform_rgb, validate_pipeline, xy_to_xyz)


def identity_cube(dimension=3, low=(0, 0, 0), high=(1, 1, 1)):
    values = [(0, 0, 0), (1, 1, 1)] if dimension == 1 else [(r, g, b) for b in (0, 1) for g in (0, 1) for r in (0, 1)]
    return CubeLUT(dimension, 2, tuple(low), tuple(high), tuple(values), "COLOR TEST identity")


def pipeline(**changes):
    p = {"version": 1, "enabled": True, "input_transfer": "rec709", "input_primaries": "rec709",
         "source_white": list(WHITEPOINTS["D65"]), "target_white": list(WHITEPOINTS["D65"]), "lut": None}
    p.update(changes)
    return p


class CubeTests(unittest.TestCase):
    def test_canonicalization_is_stable_across_number_and_comment_spellings(self):
        first = parse_cube('\ufeff# comment\nTITLE "Look #1"\nLUT_1D_SIZE 2\n-0 0e0 .0 #black\n1.0 1e0 +1\n')
        second = parse_cube('TITLE "Look #1"\nLUT_1D_SIZE 2\n0 0 0\n1 1 1')
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.text(), parse_cube(first.text()).text())
        self.assertEqual(first.sha256, hashlib.sha256(first.text().encode()).hexdigest())

    def test_rejects_ambiguous_malformed_or_executable_content(self):
        cases = ["", "0 0 0", "LUT_3D_SIZE 1", "LUT_3D_SIZE 66", "LUT_1D_SIZE 65537",
                 "LUT_1D_SIZE 2.0\n0 0 0\n1 1 1", "LUT_1D_SIZE 2\n0 0 0\nNaN 1 1",
                 "LUT_1D_SIZE 2\n0 0 0\ninf 1 1", "LUT_1D_SIZE 2\n0 0 0\n1e999 1 1",
                 "LUT_1D_SIZE 2\n0 0 0\n1 1 1 1", "LUT_1D_SIZE 2\n0 0 0\n1 1 1\n1 1 1",
                 "LUT_1D_SIZE 2\n0 0 0", "LUT_1D_SIZE 2\nLUT_3D_SIZE 2\n0 0 0\n1 1 1",
                 "LUT_1D_SIZE 2\nDOMAIN_MIN 1 0 0\nDOMAIN_MAX 1 1 1\n0 0 0\n1 1 1",
                 "LUT_1D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MIN 0 0 0\n0 0 0\n1 1 1",
                 "LUT_1D_SIZE 2\n0 0 0\nDOMAIN_MAX 1 1 1\n1 1 1",
                 "LUT_1D_SIZE 2\nLUT_3D_INPUT_RANGE 0 1\n0 0 0\n1 1 1",
                 "LUT_1D_SIZE 2\nLUT_1D_INPUT_RANGE 0 1\nDOMAIN_MIN 0 0 0\n0 0 0\n1 1 1",
                 "LUT_1D_SIZE 2\nLUT_1D_INPUT_RANGE 1 1\n0 0 0\n1 1 1",
                 'TITLE "ok"\nTITLE "no"\nLUT_1D_SIZE 2\n0 0 0\n1 1 1',
                 'TITLE "unterminated\nLUT_1D_SIZE 2\n0 0 0\n1 1 1',
                 "INCLUDE /etc/passwd", "LUT_1D_SIZE 2\n0 0 0\n$(echo) 1 1",
                 "LUT_1D_SIZE 2\n0 0 0\n1 1 1\x00"]
        for value in cases:
            with self.subTest(value=value[:60]), self.assertRaises(ValueError):
                parse_cube(value)

    def test_single_stage_input_range_survives_canonical_roundtrip(self):
        # INPUT_RANGE binds to its named table. A valid single-stage range is
        # supported alongside the original per-channel DOMAIN convention.
        for dimension in (1, 3):
            rows = "\n".join(" ".join(map(str, row)) for row in identity_cube(dimension).values)
            lut = parse_cube(f"LUT_{dimension}D_SIZE 2\nLUT_{dimension}D_INPUT_RANGE -1 3\n" + rows)
            with self.subTest(dimension=dimension):
                self.assertEqual(lut.domain_min, (-1, -1, -1))
                self.assertEqual(lut.domain_max, (3, 3, 3))
                self.assertEqual(sample_lut(lut, (0, 1, 2)), (.25, .5, .75))
                self.assertEqual(sample_lut(lut, (-2, 1, 4)), (0, .5, 1))
                restored = parse_cube(lut.text())
                self.assertEqual(restored, lut)
                self.assertEqual(restored.sha256, lut.sha256)

    def test_red_changes_fastest_and_channels_are_independent(self):
        lut = parse_cube(identity_cube().text())
        for rgb in ((0.2, 0.6, 0.9), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
            for mode in ("trilinear", "tetrahedral"):
                result = sample_lut(lut, rgb, mode)
                for actual, expected in zip(result, rgb):
                    self.assertAlmostEqual(actual, expected, places=12)

    def test_nonzero_per_channel_domains_and_endpoint_clamping(self):
        for dimension in (1, 3):
            lut = identity_cube(dimension, (-1, 2, 10), (1, 4, 14))
            self.assertEqual(sample_lut(lut, (-2, 3, 20)), (0.0, 0.5, 1.0))
            self.assertEqual(sample_lut(lut, (0, 2.5, 11)), (0.5, 0.25, 0.25))

    def test_tetrahedral_differs_from_trilinear_in_all_six_simplexes(self):
        # Only the all-high corner is one: trilinear is r*g*b and the
        # containing tetrahedron gives min(r,g,b), independently known.
        lut = CubeLUT(3, 2, (0, 0, 0), (1, 1, 1), tuple([(0, 0, 0)] * 7 + [(1, 1, 1)]))
        import itertools
        for rgb in itertools.permutations((0.2, 0.5, 0.8)):
            self.assertAlmostEqual(sample_lut(lut, rgb, "trilinear")[0], 0.08)
            self.assertAlmostEqual(sample_lut(lut, rgb, "tetrahedral")[0], 0.2)
        self.assertEqual(sample_lut(lut, (0.5, 0.5, 0.5), "tetrahedral"), (0.5, 0.5, 0.5))

    def test_1d_interpolation_and_nearest_half_tie(self):
        lut = CubeLUT(1, 3, (0, 0, 0), (1, 1, 1), ((0, 0, 0), (0.25, 0.5, 0.75), (1, 1, 1)))
        self.assertEqual(sample_lut(lut, (0.25, 0.25, 0.25)), (0.125, 0.25, 0.375))
        self.assertEqual(sample_lut(lut, (0.25, 0.25, 0.25), "nearest"), (0.25, 0.5, 0.75))
        with self.assertRaises(ValueError):
            sample_lut(lut, (0, 0, 0), "tetrahedral")

    def test_out_of_range_lut_outputs_remain_float(self):
        lut = parse_cube("LUT_1D_SIZE 2\n-1 2 3\n4 5 6")
        self.assertEqual(sample_lut(lut, (0.5, 0.5, 0.5)), (1.5, 3.5, 4.5))


class ColorMathTests(unittest.TestCase):
    def test_known_transfer_points_and_camera_middle_gray(self):
        self.assertAlmostEqual(decode_transfer(0.5, "srgb"), 0.21404114048223255, places=12)
        self.assertAlmostEqual(encode_transfer(0.18, "rec709"), 0.4090077288641504, places=12)
        self.assertAlmostEqual(encode_transfer(0.18, "logc3_ei800"), 0.39100683203408376, places=12)
        self.assertAlmostEqual(decode_transfer(0.092809, "logc3_ei800"), 0.0, places=12)
        for transfer in ("linear", "srgb", "rec709", "logc3_ei800"):
            for value in (-0.001, 0, 0.003, 0.01, 0.05, 0.18, 0.8, 1.5):
                self.assertAlmostEqual(decode_transfer(encode_transfer(value, transfer), transfer), value, places=7)

    def test_bradford_matches_published_d65_d50_matrix(self):
        matrix = chromatic_adaptation_matrix(WHITEPOINTS["D65"], WHITEPOINTS["D50"])
        expected = ((1.0479297, 0.0229468, -0.0501922), (0.0296278, 0.9904344, -0.0170738),
                    (-0.0092430, 0.0150551, 0.7518742))
        for row, values in zip(matrix, expected):
            for actual, reference in zip(row, values):
                self.assertAlmostEqual(actual, reference, delta=4e-7)
        source, target = xy_to_xyz(WHITEPOINTS["D65"]), xy_to_xyz(WHITEPOINTS["D50"])
        for row, reference in zip(matrix, target):
            self.assertAlmostEqual(sum(v * w for v, w in zip(row, source)), reference, places=10)

    def test_derived_rec709_matrix_and_wide_gamut_neutral(self):
        actual = rgb_to_xyz_matrix("rec709")
        expected = ((0.4123907993, 0.3575843394, 0.1804807884),
                    (0.2126390059, 0.7151686788, 0.0721923154),
                    (0.0193308187, 0.1191947798, 0.9505321522))
        for row, reference in zip(actual, expected):
            for value, want in zip(row, reference):
                self.assertAlmostEqual(value, want, places=9)
        p = validate_pipeline({"version": 1, "input_transfer": "linear", "input_primaries": "acescg"})
        output = transform_rgb((0.18, 0.18, 0.18), p)
        for value in output:
            self.assertAlmostEqual(value, 0.4090077288641504, places=10)

    def test_invalid_pipeline_and_whitepoints_fail_closed(self):
        for changes in ({"input_transfer": "pq"}, {"input_transfer": []}, {"input_primaries": "anything"},
                        {"enabled": 1}, {"version": True}, {"source_white": [0, 0]},
                        {"source_white": [0.9, 0.9]}, {"source_white": [float("nan"), 0.3]},
                        {"raw": True}, {"lut": {"sha256": "../file", "interpolation": "linear"}},
                        {"lut": {"sha256": "0" * 64, "interpolation": "linear", "path": "/tmp/a"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_pipeline(pipeline(**changes))


class ProjectLUTTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cinematicum-COLOR-TEST-")
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_import_roundtrip_and_deduplication(self):
        first = import_cube(identity_cube().text(), self.root)
        self.assertEqual(first, import_cube(identity_cube().text(), self.root))
        self.assertEqual([first], list_luts(self.root))
        self.assertEqual(first, load_lut(self.root, first["sha256"]).descriptor())
        self.assertEqual(len(list((self.root / "color" / "luts").iterdir())), 1)

    def test_missing_tampered_and_noncanonical_luts_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            load_lut(self.root, "0" * 64)
        descriptor = import_cube(identity_cube().text(), self.root)
        path = self.root / "color" / "luts" / (descriptor["sha256"] + ".cube")
        path.write_text(path.read_text() + "# tampered\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            load_lut(self.root, descriptor["sha256"])
        with self.assertRaises(ValueError):
            import_cube(identity_cube().text(), self.root)

    def test_directory_and_file_symlinks_are_rejected(self):
        external = self.root / "outside"
        external.mkdir()
        (self.root / "color").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            import_cube(identity_cube().text(), self.root)
        (self.root / "color").unlink()
        descriptor = import_cube(identity_cube().text(), self.root)
        path = self.root / "color" / "luts" / (descriptor["sha256"] + ".cube")
        original = path.read_text()
        path.unlink()
        (external / "lut.cube").write_text(original)
        path.symlink_to(external / "lut.cube")
        with self.assertRaisesRegex(ValueError, "symbolic"):
            load_lut(self.root, descriptor["sha256"])

    def test_project_reference_validates_dimension_and_rejects_paths(self):
        descriptor = import_cube(identity_cube(1).text(), self.root)
        p = pipeline(lut={"sha256": descriptor["sha256"], "interpolation": "tetrahedral"})
        with self.assertRaisesRegex(ValueError, "dimension"):
            validate_pipeline(p, self.root)
        p["lut"]["interpolation"] = "linear"
        self.assertEqual(validate_pipeline(p, self.root), p)
        self.assertEqual(compile_pipeline(None, self.root, self.root), [])
        self.assertEqual(compile_pipeline(pipeline(), self.root, self.root), [])
        self.assertEqual(compile_pipeline(pipeline(enabled=False), self.root, self.root), [])


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class FloatRenderTests(unittest.TestCase):
    setUp = ProjectLUTTests.setUp
    tearDown = ProjectLUTTests.tearDown
    def render(self, pixels, p, temp_dir=None):
        # Arrange a 2 x N planar float frame. The fourth plane is independent
        # alpha, which must be unchanged by every colour operation.
        self.assertEqual(len(pixels) % 2, 0)
        planes = [pixel[c] for c in (1, 2, 0, 3) for pixel in pixels]
        filters = compile_pipeline(p, self.root, temp_dir or self.root)
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
                                 "-f", "rawvideo", "-pix_fmt", "gbrapf32le", "-s", "2x%d" % (len(pixels) // 2),
                                 "-i", "pipe:0", "-vf", ",".join(filters) or "null", "-frames:v", "1",
                                 "-f", "rawvideo", "-pix_fmt", "gbrapf32le", "-threads", "1", "pipe:1"],
                                input=struct.pack("<%df" % len(planes), *planes), capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        samples = struct.unpack("<%df" % len(planes), result.stdout)
        count = len(pixels)
        return [tuple(samples[plane * count + i] for plane in (2, 0, 1, 3)) for i in range(count)]

    def assert_pixels(self, result, expected, tolerance=5e-6):
        for actual, wanted in zip(result, expected):
            for a, b in zip(actual, wanted):
                self.assertAlmostEqual(a, b, delta=tolerance)

    def test_actual_render_preserves_nonzero_domains_and_alpha(self):
        for dimension in (1, 3):
            lut = identity_cube(dimension, (0.25, -0.5, 0.1), (0.75, 1.5, 0.6))
            descriptor = import_cube(lut.text(), self.root)
            p = pipeline(lut={"sha256": descriptor["sha256"], "interpolation": "linear" if dimension == 1 else "tetrahedral"})
            pixels = [(0.5, 0.5, 0.35, 0.4), (0.0, 2.0, -1.0, 0.75)]
            self.assert_pixels(self.render(pixels, p), [(0.5, 0.5, 0.5, 0.4), (0, 1, 0, 0.75)])

    def test_actual_tetrahedral_and_trilinear_match_known_simplex_results(self):
        lut = CubeLUT(3, 2, (0, 0, 0), (1, 1, 1), tuple([(0, 0, 0)] * 7 + [(1, 1, 1)]))
        descriptor = import_cube(lut.text(), self.root)
        for mode, expected in (("tetrahedral", 0.2), ("trilinear", 0.08), ("nearest", 0)):
            p = pipeline(lut={"sha256": descriptor["sha256"], "interpolation": mode})
            pixels = [(0.2, 0.5, 0.8, 0.3), (0.8, 0.2, 0.5, 0.6)]
            self.assert_pixels(self.render(pixels, p), [(expected, expected, expected, 0.3), (expected, expected, expected, 0.6)])

    def test_actual_linear_and_srgb_conversion_use_known_rec709_values(self):
        self.assert_pixels(self.render([(0.18, 0.18, 0.18, 0.25), (0.01, 0.01, 0.01, 1)], pipeline(input_transfer="linear")),
                           [(0.4090077289, 0.4090077289, 0.4090077289, 0.25), (0.045, 0.045, 0.045, 1)])
        # Independently calculated IEC sRGB inverse then BT.709 OETF at .5.
        want = 1.099 * 0.21404114048223255 ** 0.45 - 0.099
        self.assert_pixels(self.render([(0.5, 0.5, 0.5, 0.8), (0, 0, 0, 1)], pipeline(input_transfer="srgb")),
                           [(want, want, want, 0.8), (0, 0, 0, 1)])

    def test_integer_display_fast_path_measures_every_16bit_level_and_exact_alpha(self):
        # Every channel independently covers all 65,536 input codes. The
        # permutation prevents a component-order bug from passing as gray.
        import sys
        pixels = array.array("H")
        for code in range(65536):
            pixels.extend((code, (31 * code) % 65536, 65535 - code, code))
        if sys.byteorder != "little":
            pixels.byteswap()
        filters = compile_pipeline(pipeline(input_transfer="srgb"), self.root, self.root, input_unorm16=True)
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
                                 "-f", "rawvideo", "-pix_fmt", "rgba64le", "-s", "256x256", "-i", "pipe:0",
                                 "-vf", ",".join(filters), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba64le",
                                 "-threads", "1", "pipe:1"], input=pixels.tobytes(), capture_output=True, check=True, timeout=10)
        measured = array.array("H")
        measured.frombytes(result.stdout)
        if sys.byteorder != "little":
            measured.byteswap()
        self.assertEqual(len(measured), 4 * 65536)
        # Independent piecewise IEC sRGB inverse and BT.709 OETF; no production
        # color evaluator or filter-expression generator supplies this oracle.
        reference = []
        for code in range(65536):
            encoded = code / 65535
            linear = encoded / 12.92 if encoded <= .04045 else ((encoded + .055) / 1.055) ** 2.4
            reference.append(65535 * (4.5 * linear if linear < .018 else 1.099 * linear ** .45 - .099))
        largest_error = 0
        for code in range(65536):
            self.assertEqual(measured[code * 4 + 3], code)
            for channel, source in enumerate((code, (31 * code) % 65536, 65535 - code)):
                largest_error = max(largest_error, abs(measured[code * 4 + channel] - reference[source]))
        self.assertLessEqual(largest_error, .50000001, "Lookup error exceeds half one UNORM16 code")

    def test_integer_fast_path_never_replaces_general_float_or_creative_transforms(self):
        srgb = pipeline(input_transfer="srgb")
        self.assertEqual(compile_pipeline(srgb, self.root, self.root)[0], "format=gbrapf32le")
        descriptor = import_cube("LUT_1D_SIZE 2\n-1 2 3\n4 5 6", self.root)
        for changes in ({"input_transfer": "linear"}, {"input_transfer": "logc3_ei800"},
                        {"input_primaries": "acescg"}, {"source_white": list(WHITEPOINTS["D50"])},
                        {"target_white": list(WHITEPOINTS["D50"])},
                        {"lut": {"sha256": descriptor["sha256"], "interpolation": "linear"}}):
            with self.subTest(changes=changes):
                self.assertEqual(compile_pipeline({**srgb, **changes}, self.root, self.root, input_unorm16=True)[0],
                                 "format=gbrapf32le")
        # The default sRGB float route still preserves out-of-integer-range data.
        values = [(-.1, .5, 1.5, .25), (1.5, -.1, .5, .75)]
        rendered = self.render(values, srgb)
        self.assertLess(rendered[0][0], 0)
        self.assertGreater(rendered[0][2], 1)
        self.assert_pixels(rendered, [transform_rgb(p[:3], srgb) + (p[3],) for p in values])

    def test_actual_awg_logc3_middle_gray_and_acescg_white(self):
        p = pipeline(input_transfer="logc3_ei800", input_primaries="arri_wide_gamut3")
        value = 0.39100683203408376
        self.assert_pixels(self.render([(value, value, value, 0.8), (0.092809, 0.092809, 0.092809, 1)], p),
                           [(0.4090077289, 0.4090077289, 0.4090077289, 0.8), (0, 0, 0, 1)])
        p = validate_pipeline({"version": 1, "input_transfer": "linear", "input_primaries": "acescg"})
        self.assert_pixels(self.render([(0.18, 0.18, 0.18, 0.3), (1, 1, 1, 1)], p),
                           [(0.4090077289, 0.4090077289, 0.4090077289, 0.3), (1, 1, 1, 1)])

    def test_actual_adaptation_and_gamut_matrix_match_independent_cpu(self):
        p = pipeline(input_transfer="srgb", input_primaries="rec2020", source_white=list(WHITEPOINTS["D50"]))
        pixels = [(0.7, 0.3, 0.1, 0.41), (0.2, 0.65, 0.4, 0.83)]
        expected = [transform_rgb(rgb[:3], p) + (rgb[3],) for rgb in pixels]
        self.assert_pixels(self.render(pixels, p), expected)

    def test_actual_lut_float_output_does_not_clip_negative_or_superwhite(self):
        lut = parse_cube("LUT_1D_SIZE 2\n-1 2 3\n4 5 6")
        descriptor = import_cube(lut.text(), self.root)
        p = pipeline(lut={"sha256": descriptor["sha256"], "interpolation": "linear"})
        self.assert_pixels(self.render([(0.5, 0.5, 0.5, 0.3), (1, 1, 1, 0.8)], p),
                           [(1.5, 3.5, 4.5, 0.3), (4, 5, 6, 0.8)])

    def test_filter_file_paths_with_ffmpeg_metacharacters_are_literal(self):
        destination = self.root / "colour O'Brien : [x],semi;slash\\"
        destination.mkdir()
        descriptor = import_cube(identity_cube().text(), self.root)
        p = pipeline(lut={"sha256": descriptor["sha256"], "interpolation": "tetrahedral"})
        pixels = [(0.2, 0.3, 0.4, 0.5), (0.6, 0.7, 0.8, 0.9)]
        self.assert_pixels(self.render(pixels, p, destination), pixels)


if __name__ == "__main__":
    unittest.main()

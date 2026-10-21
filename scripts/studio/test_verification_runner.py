"""Exercise the release runner's protection against apparently green skips."""
import io
import unittest

from run_verification import RAW_REASON, RAW_TEST, run_suite


class VerificationRunnerTests(unittest.TestCase):
    def fixture(self, ident, reason):
        class Fixture(unittest.TestCase):
            def runTest(self):
                self.skipTest(reason)

            def id(self):
                return ident
        return Fixture()

    def test_missing_runtime_skip_fails_even_when_raw_is_declared_optional(self):
        for optional in (False, True):
            result = run_suite(unittest.TestSuite([self.fixture("test_planar_tracking.PlanarInferenceTests.test_measure",
                "Actual OpenCV planar runtime unavailable")]), allow_missing_raw=optional, stream=io.StringIO())
            self.assertFalse(result.wasSuccessful())
            self.assertEqual(len(result.unexpected_skips), 1)
            self.assertEqual(result.allowed_skips, [])

    def test_class_setup_skip_is_not_hidden_by_zero_executed_tests(self):
        class MissingRuntime(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest("Unavailable engine")

            def test_inference(self):
                self.fail("Missing engine cannot reach inference")
        result = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(MissingRuntime), stream=io.StringIO())
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.testsRun, 0)
        self.assertEqual(len(result.unexpected_skips), 1)
        with self.assertRaisesRegex(ValueError, "no tests"):
            run_suite(unittest.TestSuite(), stream=io.StringIO())

    def test_only_exact_explicit_raw_exception_is_accepted(self):
        for ident, reason, optional, allowed in (
            (RAW_TEST, RAW_REASON, False, False), (RAW_TEST, RAW_REASON, True, True),
            (RAW_TEST, "Broken RAW engine", True, False), (RAW_TEST + "_other", RAW_REASON, True, False)):
            with self.subTest(ident=ident, reason=reason, optional=optional):
                result = run_suite(unittest.TestSuite([self.fixture(ident, reason)]),
                                   allow_missing_raw=optional, stream=io.StringIO())
                self.assertEqual(result.wasSuccessful(), allowed)


if __name__ == "__main__":
    unittest.main()

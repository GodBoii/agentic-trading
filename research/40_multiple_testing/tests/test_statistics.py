import importlib
import unittest

stats = importlib.import_module("research.40_multiple_testing.statistics")


class StatisticalDiagnosticTests(unittest.TestCase):
    def test_two_positive_days_cannot_establish_small_tail(self):
        self.assertEqual(stats.sign_flip_tail([10, 20]), .25)

    def test_zero_activity_is_not_a_discovery(self):
        self.assertEqual(stats.sign_flip_tail([0, 0]), 1)

    def test_negative_result_has_large_positive_tail(self):
        self.assertEqual(stats.sign_flip_tail([-10, -20]), 1)

    def test_known_bh_reference_case(self):
        expected = [.02, .04, .04, .008]
        for actual, target in zip(stats.benjamini_hochberg([.01, .04, .03, .002]), expected):
            self.assertAlmostEqual(actual, target)

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            stats.sign_flip_tail([float("nan")])
        with self.assertRaises(ValueError):
            stats.benjamini_hochberg([1.1])


if __name__ == "__main__":
    unittest.main()

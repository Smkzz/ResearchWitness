"""Exact arithmetic boundary tests for source-grounded percentage review."""
from __future__ import annotations

import unittest

from tools.percentage_math import (
    compatible_integer_denominator_range,
    compatible_integer_numerator_range,
    independently_rounded_components,
)


class PercentageMathTests(unittest.TestCase):
    def test_fixed_denominator_feasible_numerator_range(self):
        result = compatible_integer_numerator_range(20, "5.00", 2)
        self.assertTrue(result["integer_numerator_feasible"])
        self.assertEqual(result["minimum_compatible_numerator"], 1)
        self.assertEqual(result["maximum_compatible_numerator"], 1)

    def test_fixed_denominator_can_make_a_displayed_percentage_impossible(self):
        result = compatible_integer_numerator_range(3, "33.34", 2)
        self.assertFalse(result["integer_numerator_feasible"])
        self.assertIsNone(result["minimum_compatible_numerator"])
        self.assertIsNone(result["maximum_compatible_numerator"])

    def test_fixed_count_can_have_one_compatible_denominator(self):
        result = compatible_integer_denominator_range(2, "25.0", 1)
        self.assertTrue(result["integer_denominator_feasible"])
        self.assertEqual(result["minimum_compatible_denominator"], 8)
        self.assertEqual(result["maximum_compatible_denominator"], 8)

    def test_half_up_lower_boundary_is_inclusive_and_upper_is_exclusive(self):
        # 1/8 is exactly 12.5%; it rounds up to 13 at zero places.
        self.assertTrue(compatible_integer_numerator_range(8, "13", 0)["integer_numerator_feasible"])
        # The same tie cannot round down to 12 under half-up.
        self.assertFalse(compatible_integer_numerator_range(8, "12", 0)["integer_numerator_feasible"])

    def test_component_rounding_is_independent(self):
        result = independently_rounded_components([1, 1, 1], 3, 2)
        self.assertEqual(result["component_rounded_percentages"], ["33.33", "33.33", "33.33"])
        self.assertEqual(result["independently_rounded_percentages_sum"], "99.99")
        self.assertEqual(result["rounded_percentage_of_component_count_sum"], "100.00")
        self.assertTrue(result["component_counts_sum_equals_denominator"])

    def test_component_helper_does_not_assume_partition(self):
        result = independently_rounded_components([1, 1], 3, 2)
        self.assertFalse(result["component_counts_sum_equals_denominator"])

    def test_invalid_precision_scope_and_counts_are_rejected(self):
        for args in (
            (0, "1.00", 2),
            (3, "33.340", 2),
            (3, "1e2", 0),
            (3, "NaN", 0),
            (3, "101", 0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                compatible_integer_numerator_range(*args)
        for counts in ([], [True], [-1], [1.0]):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                independently_rounded_components(counts, 10, 2)


if __name__ == "__main__":
    unittest.main()

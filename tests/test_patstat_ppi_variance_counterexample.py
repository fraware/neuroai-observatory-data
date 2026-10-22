"""Exact finite-population tests for omitted second-stage variance."""
from __future__ import annotations

import math
import unittest

from scripts.patstat_ppi_variance_counterexample import demonstrate_omitted_variance


class PatstatSecondStageVarianceTests(unittest.TestCase):
    def test_corrected_estimator_has_nonzero_second_stage_variance(self) -> None:
        r = demonstrate_omitted_variance()
        self.assertEqual(r["population_n"], 20)
        self.assertEqual(r["first_stage_census_n"], 20)
        self.assertEqual(r["fully_enumerated_second_stage_sample_count"], 4845)
        self.assertEqual(r["true_reference_total"], 10)
        self.assertAlmostEqual(r["mean_corrected_estimate"], 10)
        self.assertEqual(r["variance_from_cheap_only_formula"], 0)
        self.assertAlmostEqual(r["variance_of_corrected_estimate_exact"], 400 / 19)
        self.assertAlmostEqual(r["variance_from_independent_srswor_formula"], 400 / 19)
        self.assertAlmostEqual(
            r["coverage_of_zero_width_interval_at_true_total"],
            math.comb(10, 2) ** 2 / math.comb(20, 4),
        )
        self.assertLess(r["coverage_of_zero_width_interval_at_true_total"], 0.5)
        self.assertEqual(r["status"], "FINITE_POPULATION_MATHEMATICAL_DEMONSTRATION_ONLY")

    def test_exact_variance_formula_at_multiple_sample_sizes(self) -> None:
        for n, k, m in [(12, 3, 2), (12, 6, 3), (15, 10, 4), (8, 1, 5)]:
            with self.subTest(n=n, k=k, m=m):
                r = demonstrate_omitted_variance(n, k, m)
                self.assertAlmostEqual(r["mean_corrected_estimate"], k)
                self.assertGreater(r["variance_of_corrected_estimate_exact"], 0)
                self.assertAlmostEqual(
                    r["variance_of_corrected_estimate_exact"],
                    r["variance_from_independent_srswor_formula"],
                )

    def test_invalid_synthetic_parameters_fail_closed(self) -> None:
        for n, k, m in [
            (1, 1, 1), (20, 0, 4), (20, 20, 4),
            (20, 10, 0), (20, 10, 20), (25, 10, 4),
        ]:
            with self.subTest(n=n, k=k, m=m):
                with self.assertRaisesRegex(ValueError, "bounds"):
                    demonstrate_omitted_variance(n, k, m)


if __name__ == "__main__":
    unittest.main()

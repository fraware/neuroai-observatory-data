"""Exhaustive independent reference checks for prospective two-phase SRS."""
from __future__ import annotations

import itertools
import unittest

from scripts.patstat_prospective_two_phase_srs import estimate_design


F = (0, 1, 0, 0, 1, 0)
Y = (1, 1, 0, 1, 0, 0)
POOL = (1, 1, 0, 1, 0, 1)


def _one(s: tuple[int, ...], r: tuple[int, ...], pool: tuple[int, ...] = POOL):
    return estimate_design(
        [
            {
                "N": 6,
                "phase1": [
                    {"id": str(i), "cheap": F[i], "pool": pool[i]} for i in s
                ],
                "phase2": [{"id": str(i), "reference": Y[i]} for i in r],
            }
        ]
    )


class ProspectiveTwoPhaseReferenceTests(unittest.TestCase):
    def test_all_90_nested_sampling_outcomes_and_covariance(self) -> None:
        observed = []
        for first in itertools.combinations(range(6), 4):
            for second in itertools.combinations(first, 2):
                observed.append(_one(first, second))
        self.assertEqual(len(observed), 90)
        fields = (
            "estimated_population_relevant_total",
            "estimated_retrieved_relevant_total",
            "estimated_total_variance",
            "estimated_retrieved_total_variance",
            "estimated_total_retrieved_covariance",
        )
        averages = {
            field: sum(row[field] for row in observed) / len(observed)
            for field in fields
        }
        self.assertAlmostEqual(averages[fields[0]], 3.0)
        self.assertAlmostEqual(averages[fields[1]], 3.0)
        y_var = sum((row[fields[0]] - 3.0) ** 2 for row in observed) / len(observed)
        z_var = sum((row[fields[1]] - 3.0) ** 2 for row in observed) / len(observed)
        yz_cov = sum(
            (row[fields[0]] - 3.0) * (row[fields[1]] - 3.0)
            for row in observed
        ) / len(observed)
        self.assertAlmostEqual(y_var, 6.0)
        self.assertAlmostEqual(z_var, 3.3)
        self.assertAlmostEqual(yz_cov, 3.9)
        self.assertAlmostEqual(averages[fields[2]], y_var)
        self.assertAlmostEqual(averages[fields[3]], z_var)
        self.assertAlmostEqual(averages[fields[4]], yz_cov)

    def test_all_in_pool_yields_exact_unit_ratio_and_zero_delta_variance(self) -> None:
        result = _one((0, 1, 2, 3), (0, 1), (1,) * 6)
        self.assertAlmostEqual(result["estimated_retrieval_ratio"], 1.0)
        self.assertAlmostEqual(result["estimated_retrieval_ratio_delta_variance"], 0.0)
        self.assertAlmostEqual(
            result["estimated_total_variance"],
            result["estimated_retrieved_total_variance"],
        )
        self.assertAlmostEqual(
            result["estimated_total_retrieved_covariance"],
            result["estimated_total_variance"],
        )

    def test_independent_strata_add_totals_and_covariances(self) -> None:
        item = {
            "N": 6,
            "phase1": [{"id": str(i), "cheap": F[i], "pool": POOL[i]} for i in (0, 1, 2, 3)],
            "phase2": [{"id": str(i), "reference": Y[i]} for i in (0, 1)],
        }
        single = estimate_design([item])
        double = estimate_design([item, item])
        for name in (
            "estimated_population_relevant_total",
            "estimated_retrieved_relevant_total",
            "estimated_total_variance",
            "estimated_retrieved_total_variance",
            "estimated_total_retrieved_covariance",
        ):
            self.assertAlmostEqual(double[name], 2 * single[name])
        self.assertAlmostEqual(
            double["estimated_retrieval_ratio"],
            single["estimated_retrieval_ratio"],
        )
        self.assertAlmostEqual(
            double["estimated_retrieval_ratio_delta_variance"],
            single["estimated_retrieval_ratio_delta_variance"] / 2,
        )

    def test_invalid_nested_design_fails_closed(self) -> None:
        first = [
            {"id": str(i), "cheap": F[i], "pool": POOL[i]} for i in (0, 1, 2, 3)
        ]
        second = [{"id": str(i), "reference": Y[i]} for i in (0, 1)]
        cases = [
            ({"N": 3, "phase1": first, "phase2": second}, "Nested SRSWOR"),
            ({"N": 6, "phase1": first, "phase2": second[:1]}, "Nested SRSWOR"),
            ({"N": 6, "phase1": [first[0], first[0], *first[2:]], "phase2": second}, "distinct"),
            ({"N": 6, "phase1": first, "phase2": [second[0], second[0]]}, "unique subset"),
            ({"N": 6, "phase1": first, "phase2": [second[0], {"id": "5", "reference": 1}]}, "unique subset"),
            ({"N": 6, "phase1": [{**first[0], "cheap": 2}, *first[1:]], "phase2": second}, "binary"),
            ({"N": 6, "phase1": first, "phase2": [{**second[0], "reference": 2}, second[1]]}, "binary"),
        ]
        with self.assertRaisesRegex(ValueError, "At least one"):
            estimate_design([])
        for record, error in cases:
            with self.subTest(error=error, record=record):
                with self.assertRaisesRegex(ValueError, error):
                    estimate_design([record])


if __name__ == "__main__":
    unittest.main()

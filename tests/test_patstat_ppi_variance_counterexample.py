"""Exact finite-population tests for second-stage variance omission."""
from __future__ import annotations

import math

import pytest

from scripts.patstat_ppi_variance_counterexample import demonstrate_omitted_variance


def test_enumerated_corrected_estimator_has_nonzero_second_stage_variance() -> None:
    r = demonstrate_omitted_variance()
    assert r["population_n"] == 20
    assert r["first_stage_census_n"] == 20
    assert r["fully_enumerated_second_stage_sample_count"] == 4845
    assert r["true_reference_total"] == 10
    assert r["mean_corrected_estimate"] == pytest.approx(10)
    assert r["variance_from_cheap_only_formula"] == 0
    assert r["variance_of_corrected_estimate_exact"] == pytest.approx(400 / 19)
    assert r["variance_from_independent_srswor_formula"] == pytest.approx(400 / 19)
    assert r["coverage_of_zero_width_interval_at_true_total"] == pytest.approx(
        math.comb(10, 2) ** 2 / math.comb(20, 4)
    )
    assert r["coverage_of_zero_width_interval_at_true_total"] < 0.5
    assert r["status"] == "FINITE_POPULATION_MATHEMATICAL_DEMONSTRATION_ONLY"


@pytest.mark.parametrize(
    ("n", "k", "m"),
    [(12, 3, 2), (12, 6, 3), (15, 10, 4), (8, 1, 5)],
)
def test_second_stage_sampling_variance_matches_design_formula(
    n: int, k: int, m: int
) -> None:
    r = demonstrate_omitted_variance(n, k, m)
    assert r["mean_corrected_estimate"] == pytest.approx(k)
    assert r["variance_of_corrected_estimate_exact"] > 0
    assert r["variance_of_corrected_estimate_exact"] == pytest.approx(
        r["variance_from_independent_srswor_formula"]
    )


@pytest.mark.parametrize(
    ("n", "k", "m"),
    [(1, 1, 1), (20, 0, 4), (20, 20, 4), (20, 10, 0), (20, 10, 20), (25, 10, 4)],
)
def test_invalid_synthetic_parameters_fail_closed(n: int, k: int, m: int) -> None:
    with pytest.raises(ValueError, match="bounds"):
        demonstrate_omitted_variance(n, k, m)

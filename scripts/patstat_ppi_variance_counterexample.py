"""Finite-population counterexample for omitted second-stage PPI variance.

This is a *synthetic mathematical diagnostic*, NOT a PATSTAT estimator or
human-labeled benchmark. The historical reproduce.py adds a second-stage
correction to its point estimate, while its displayed variance is calculated
from first-stage cheap-label variability only.

A first-stage census of a stratum with constant cheap label has cheap-only
variance zero, even though an independently sampled correction has positive
design variance. Exhaustively enumerate all equal-probability second-stage
samples to make that distinction unambiguous.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from typing import Any


def demonstrate_omitted_variance(
    population_n: int = 20,
    reference_positive_n: int = 10,
    reread_sample_n: int = 4,
) -> dict[str, Any]:
    """Exact SRSWOR repeated-sampling results with constant first-stage labels.

    The synthetic y vector has reference_positive_n ones followed by zeros.
    All cheap/model labels f_i are zero, so their census mean and variance
    are exactly zero. The post-stratified residual correction is simply the
    randomly selected sample mean of y, since the only f-cell is zero.
    """
    n = population_n
    k = reference_positive_n
    m = reread_sample_n
    if not (2 <= n <= 24 and 0 < k < n and 1 <= m < n):
        raise ValueError("Synthetic finite-population parameter bounds violated")
    y = (1,) * k + (0,) * (n - k)
    true_total = k
    all_estimates: list[float] = []
    for ids in itertools.combinations(range(n), m):
        corrected_total = n * sum(y[i] for i in ids) / m
        all_estimates.append(corrected_total)
    sample_space = math.comb(n, m)
    if len(all_estimates) != sample_space:
        raise AssertionError("Not all SRSWOR samples enumerated")
    expected_estimate = math.fsum(all_estimates) / sample_space
    actual_variance = math.fsum((a - true_total) ** 2 for a in all_estimates) / sample_space

    # Exact design variance of N * ybar from SRSWOR with population
    # variance denominator N-1. This independently checks enumeration.
    p = k / n
    finite_pop_s2 = (n / (n - 1)) * p * (1 - p)
    design_variance = n * n * (1 - m / n) * finite_pop_s2 / m
    if not math.isclose(expected_estimate, true_total, rel_tol=0, abs_tol=1e-12):
        raise AssertionError("Synthetic correction is not design unbiased")
    if not math.isclose(actual_variance, design_variance, rel_tol=1e-12):
        raise AssertionError("Enumeration does not reproduce SRSWOR design variance")

    # First-stage census with all f_i=0 gives zero for historical
    # N^2*(1-n/N)*mean_f*(1-mean_f)/n: both factors vanish.
    cheap_only_variance = 0.0
    zero_width_coverage = sum(
        estimate == true_total for estimate in all_estimates
    ) / sample_space
    return {
        "artifact_type": "PATSTAT_PPI_SECOND_STAGE_VARIANCE_SYNTHETIC_COUNTEREXAMPLE_v0.1",
        "status": "FINITE_POPULATION_MATHEMATICAL_DEMONSTRATION_ONLY",
        "population_n": n,
        "reference_positive_n": k,
        "first_stage_census_n": n,
        "constant_first_stage_model_label": 0,
        "second_stage_srs_without_replacement_n": m,
        "fully_enumerated_second_stage_sample_count": sample_space,
        "true_reference_total": true_total,
        "mean_corrected_estimate": expected_estimate,
        "variance_of_corrected_estimate_exact": actual_variance,
        "variance_from_independent_srswor_formula": design_variance,
        "variance_from_cheap_only_formula": cheap_only_variance,
        "coverage_of_zero_width_interval_at_true_total": zero_width_coverage,
        "conclusion": (
            "Adding a second-stage random residual correction contributes "
            "sampling variance even when first-stage model labels are "
            "constant and their first-stage census variance is zero. "
            "The historical cheap-only variance expression does not "
            "generally measure the displayed corrected estimator variance."
        ),
        "nonclaims": [
            "No inference about actual historical second-stage inclusion probabilities",
            "No PATSTAT population or retrieval-coverage confidence interval",
            "No proof of actual Baseline A estimator bias",
            "No human reference labels, licensing decision or scientific gate approval",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=str)
    args = parser.parse_args(argv)
    rendered = json.dumps(demonstrate_omitted_variance(), indent=2, sort_keys=True) + "\n"
    if args.output:
        from pathlib import Path

        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

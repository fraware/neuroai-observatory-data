"""Prospective, explicitly assumed stratified nested two-phase SRS reference.

This is a mathematical REFERENCE IMPLEMENTATION for a newly designed study,
not a reconstruction of PATSTAT Baseline A. Inputs represent observed binary
cheap labels and pool flags on phase-1 SRSWOR units, and independent binary
reference labels on a phase-2 SRSWOR subsample of those units.

In every stratum h:
  T_y = N_h * (mean_s(f) + mean_r(y-f))
  T_z = N_h * (mean_s(f*pool) + mean_r((y-f)*pool))
  V_ab = N_h^2 * ((1-n_h/N_h) * S_ab,y,r/n_h
                  + (1-m_h/n_h) * S_ab,e,r/m_h)

The within-sample covariance terms use unbiased denominator m_h-1.
These covariance expressions are unbiased under the *specified* nested
SRSWOR design; they are not applicable to unknown or unequal-probability
historical second-stage selection. Ratio variance is first-order delta,
not an exact guaranteed-coverage interval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _cov(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Reference covariance needs two paired values")
    mx, my = sum(x) / len(x), sum(y) / len(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (len(x) - 1)


def estimate_design(strata: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate two totals, their full phase-1/phase-2 covariance and a ratio."""
    if not isinstance(strata, list) or not strata:
        raise ValueError("At least one probability-sample stratum required")
    total_y = total_pool = 0.0
    var_y = var_pool = cov_yp = 0.0
    summaries: list[dict[str, Any]] = []
    for h, stratum in enumerate(strata):
        N = stratum["N"]
        first = stratum["phase1"]
        second = stratum["phase2"]
        if not isinstance(N, int) or isinstance(N, bool):
            raise ValueError("Population N must be an integer")
        n, m = len(first), len(second)
        if not (N >= n >= m >= 2):
            raise ValueError("Nested SRSWOR counts must satisfy N >= n >= m >= 2")
        ids: dict[str, tuple[int, int]] = {}
        for row in first:
            uid, f, p = row["id"], row["cheap"], row["pool"]
            if not isinstance(uid, str) or not uid or uid in ids:
                raise ValueError("Phase-1 IDs must be distinct nonempty strings")
            if type(f) is not int or type(p) is not int or f not in (0, 1) or p not in (0, 1):
                raise ValueError("Observed phase-1 cheap and pool values must be binary")
            ids[uid] = f, p
        s_ids = set()
        y_values: list[float] = []
        z_values: list[float] = []
        e_values: list[float] = []
        ez_values: list[float] = []
        for row in second:
            uid, y = row["id"], row["reference"]
            if uid not in ids or uid in s_ids:
                raise ValueError("Phase-2 IDs must be unique subset of phase 1")
            if type(y) is not int or y not in (0, 1):
                raise ValueError("Observed phase-2 reference label must be binary")
            s_ids.add(uid)
            f, p = ids[uid]
            y_values.append(float(y))
            z_values.append(float(y * p))
            e_values.append(float(y - f))
            ez_values.append(float((y - f) * p))
        n_f = sum(f for f, _ in ids.values())
        n_fp = sum(f * p for f, p in ids.values())
        estimate_y = N * (n_f / n + sum(e_values) / m)
        estimate_pool = N * (n_fp / n + sum(ez_values) / m)
        factor_1 = N**2 * (1 - n / N) / n
        factor_2 = N**2 * (1 - m / n) / m
        vy = factor_1 * _cov(y_values, y_values) + factor_2 * _cov(e_values, e_values)
        vz = factor_1 * _cov(z_values, z_values) + factor_2 * _cov(ez_values, ez_values)
        cyz = factor_1 * _cov(y_values, z_values) + factor_2 * _cov(e_values, ez_values)
        total_y += estimate_y
        total_pool += estimate_pool
        var_y += vy
        var_pool += vz
        cov_yp += cyz
        summaries.append(
            {
                "stratum_index": h,
                "population_N": N,
                "phase1_n": n,
                "phase2_m": m,
                "phase1_inclusion_probability": n / N,
                "conditional_phase2_inclusion_probability": m / n,
                "estimated_total": estimate_y,
                "estimated_retrieved_total": estimate_pool,
                "estimated_total_variance": vy,
                "estimated_retrieved_variance": vz,
                "estimated_total_retrieved_covariance": cyz,
            }
        )
    ratio = None
    ratio_variance = None
    if total_y > 0:
        ratio = total_pool / total_y
        raw_var = (var_pool + ratio * ratio * var_y - 2 * ratio * cov_yp) / total_y**2
        if raw_var < -1e-10:
            raise ValueError("Invalid negative delta-ratio variance")
        ratio_variance = max(raw_var, 0.0)
    return {
        "design": "STRATIFIED_NESTED_SRSWOR_PHASE1_AND_PHASE2",
        "authority": "PROSPECTIVE_SYNTHETIC_OR_DECLARED_PROBABILITY_DESIGN_ONLY",
        "estimated_population_relevant_total": total_y,
        "estimated_retrieved_relevant_total": total_pool,
        "estimated_total_variance": var_y,
        "estimated_retrieved_total_variance": var_pool,
        "estimated_total_retrieved_covariance": cov_yp,
        "estimated_retrieval_ratio": ratio,
        "estimated_retrieval_ratio_delta_variance": ratio_variance,
        "strata": summaries,
        "limitations": [
            "Exact nested SRSWOR selection in each phase must be independently demonstrated",
            "The second-stage reference labels must be fit for scientific purpose",
            "Ratio delta variance is approximate; denominator near zero is unstable",
            "No historical PATSTAT selection probabilities or second-stage variance recovered",
            "No human-gold status, licensing decision, or G2/G5 publication authorization",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    report = estimate_design(data["strata"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

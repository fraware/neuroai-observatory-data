#!/usr/bin/env python3
"""Independent, fail-closed audit of the public PATSTAT Baseline A extract.

This script checks only claims that are mechanically reconstructible from the public
CSV files. It deliberately does not certify the historical sampling design, the full
prediction-powered estimator, interval validity, human label truth, PATSTAT rights,
G2/G5 passage, or publication authority.

Usage:
    python scripts/audit_patstat_baseline_a.py
    python scripts/audit_patstat_baseline_a.py --format pretty
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACT = ROOT / "patent-evidence-extract"

STANDARD_VERDICTS = {
    "NOT_NOML",
    "NOT_ML",
    "BOR_NOML",
    "BOR_ML",
    "REL_NOML",
    "REL_ML",
}

EXPECTED_HEADERS = {
    "strata.csv": ["stratum", "score_lo", "score_hi", "N_families", "n_judged"],
    "judged_sample.csv": ["docdb_family_id", "stratum", "score", "neuro", "ml", "verdict"],
    "gold_labels.csv": ["docdb_family_id", "stratum", "gold_neuro", "cheap_neuro"],
    "pool_frame.csv": [
        "docdb_family_id",
        "earliest_year",
        "office",
        "bloc",
        "family_size",
        "similarity",
        "ai_score",
        "found_by_query",
        "band",
        "era",
        "g06n",
        "cluster",
        "neuro",
        "ml",
    ],
    "clusters.csv": ["cluster", "n_families", "top_terms"],
}

SOURCE_BLOBS = {
    "strata.csv": "b5eff1e15d7ccf17a8a1c51388a03ae5a3dc8a00",
    "judged_sample.csv": "e10a5af342cf472dac2a8a3e19e16099bc85708d",
    "gold_labels.csv": "bc4e1c7cd1b32080d144f1b94828f58b67ac5492",
    "pool_frame.csv": "6691dcbf2c77437abf72d0d83494e3154f077b62",
    "clusters.csv": "929265475ad76aa4739c579446faab82e87defa0",
    "reproduce.py": "702d130e0c3cc553ddde03a590dd1a6b34d897dd",
    "ANALYSIS.md": "4e6ceb36fbfe287eeb78ef0d8ac004725ce7b427",
    "README.md": "940ea76931be46cd7ba9d969f0d766ccd13816e1",
}

SOURCE_MAIN_COMMIT = "825f8702cda66dd6b9740f563d2e8fb3e7144f5f"


class AuditError(RuntimeError):
    """Raised when the public extract violates a mechanical audit invariant."""


@dataclass(frozen=True)
class Estimate:
    total: float
    first_stage_sd_only: float | None = None


def git_blob_sha(path: Path) -> str:
    """Return the Git blob SHA-1 for a local file."""
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _read_csv(path: Path, expected_header: Sequence[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(expected_header):
            raise AuditError(
                f"{path.name}: header mismatch; expected={list(expected_header)!r}, "
                f"actual={reader.fieldnames!r}"
            )
        return list(reader)


def _unique_ids(rows: Iterable[Mapping[str, str]], field: str, label: str) -> set[str]:
    values = [row[field] for row in rows]
    unique = set(values)
    if len(unique) != len(values):
        raise AuditError(f"{label}: duplicate {field} values detected")
    return unique


def _rel(value: str, *, borderline_relevant: bool = False) -> float:
    if value == "2":
        return 1.0
    if borderline_relevant and value == "1":
        return 1.0
    return 0.0


def _cohen_kappa(
    rows: Sequence[Mapping[str, str]],
    prediction_field: str,
    outcome_field: str,
    labels: Sequence[str],
) -> tuple[float, dict[str, dict[str, int]]]:
    confusion = {
        pred: {outcome: 0 for outcome in labels}
        for pred in labels
    }
    for row in rows:
        pred = row[prediction_field]
        outcome = row[outcome_field]
        if pred not in confusion or outcome not in confusion[pred]:
            raise AuditError(
                f"unexpected label in kappa calculation: pred={pred!r}, outcome={outcome!r}"
            )
        confusion[pred][outcome] += 1

    n = len(rows)
    observed = sum(confusion[label][label] for label in labels) / n
    expected = 0.0
    for label in labels:
        row_share = sum(confusion[label].values()) / n
        col_share = sum(confusion[pred][label] for pred in labels) / n
        expected += row_share * col_share
    if math.isclose(expected, 1.0):
        raise AuditError("kappa expected agreement is 1; statistic undefined")
    return (observed - expected) / (1.0 - expected), confusion


def _binary_metrics(gold: Sequence[Mapping[str, str]]) -> dict[str, float | int]:
    tp = fp = fn = tn = 0
    for row in gold:
        pred = row["cheap_neuro"] == "2"
        outcome = row["gold_neuro"] == "2"
        if pred and outcome:
            tp += 1
        elif pred:
            fp += 1
        elif outcome:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)

    binary_rows = [
        {
            "pred": "1" if row["cheap_neuro"] == "2" else "0",
            "out": "1" if row["gold_neuro"] == "2" else "0",
        }
        for row in gold
    ]
    kappa, _ = _cohen_kappa(binary_rows, "pred", "out", ["0", "1"])
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "cohen_kappa_binary": kappa,
    }


def _estimate(
    judged: Sequence[Mapping[str, str]],
    gold_by_id: Mapping[str, Mapping[str, str]],
    population_by_stratum: Mapping[str, int],
    *,
    members: set[str] | None,
    borderline_relevant: bool = False,
    correction_cells: str = "public_masked_binary",
) -> Estimate:
    """Reconstruct a point estimate under an explicitly named correction-cell rule.

    public_masked_binary reproduces reproduce.py exactly. The alternative modes are
    sensitivity calculations only; they are not substitutes for the unavailable
    historical second-stage selection design or pilot/ppi.py implementation.
    """
    if correction_cells not in {
        "public_masked_binary",
        "original_binary",
        "original_three_class",
    }:
        raise ValueError(f"unsupported correction_cells={correction_cells!r}")

    valid = [row for row in judged if row["neuro"] != ""]
    by_stratum: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in valid:
        by_stratum[row["stratum"]].append(row)

    total = 0.0
    first_stage_var = 0.0

    for stratum, rows in by_stratum.items():
        n = len(rows)
        N_h = population_by_stratum[stratum]

        def keep(row: Mapping[str, str]) -> float:
            return 1.0 if members is None or row["docdb_family_id"] in members else 0.0

        masked_f = [
            _rel(row["neuro"], borderline_relevant=borderline_relevant) * keep(row)
            for row in rows
        ]
        mean_f = sum(masked_f) / n

        if correction_cells == "public_masked_binary":
            keys: Sequence[str | float] = (0.0, 1.0)

            def in_cell(index: int, key: str | float) -> bool:
                return masked_f[index] == key

        elif correction_cells == "original_binary":
            keys = (0.0, 1.0)

            def in_cell(index: int, key: str | float) -> bool:
                return (
                    _rel(
                        rows[index]["neuro"],
                        borderline_relevant=borderline_relevant,
                    )
                    == key
                )

        else:
            keys = ("0", "1", "2")

            def in_cell(index: int, key: str | float) -> bool:
                return rows[index]["neuro"] == key

        rectifier = 0.0
        for key in keys:
            cell_indexes = [i for i in range(n) if in_cell(i, key)]
            if not cell_indexes:
                continue
            correction_values: list[float] = []
            for i in cell_indexes:
                row = rows[i]
                gold = gold_by_id.get(row["docdb_family_id"])
                if gold is None:
                    continue
                correction_values.append(
                    (
                        _rel(
                            gold["gold_neuro"],
                            borderline_relevant=borderline_relevant,
                        )
                        - _rel(
                            row["neuro"],
                            borderline_relevant=borderline_relevant,
                        )
                    )
                    * keep(row)
                )
            if correction_values:
                rectifier += (
                    len(cell_indexes)
                    / n
                    * (sum(correction_values) / len(correction_values))
                )

        total += N_h * (mean_f + rectifier)

        if correction_cells == "public_masked_binary":
            fpc = 1.0 - n / N_h if N_h > n else 0.0
            first_stage_var += N_h**2 * fpc * mean_f * (1.0 - mean_f) / n

    return Estimate(
        total=total,
        first_stage_sd_only=(
            math.sqrt(first_stage_var)
            if correction_cells == "public_masked_binary"
            else None
        ),
    )


def _cheap_only_total(
    judged: Sequence[Mapping[str, str]],
    population_by_stratum: Mapping[str, int],
) -> float:
    by_stratum: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in judged:
        if row["neuro"] != "":
            by_stratum[row["stratum"]].append(row)
    return sum(
        population_by_stratum[stratum]
        * sum(_rel(row["neuro"]) for row in rows)
        / len(rows)
        for stratum, rows in by_stratum.items()
    )


def _stage2_allocation(
    judged: Sequence[Mapping[str, str]],
    gold: Sequence[Mapping[str, str]],
) -> list[dict[str, float | int | str]]:
    n1: Counter[tuple[str, str]] = Counter(
        (row["stratum"], row["neuro"])
        for row in judged
        if row["neuro"] != ""
    )
    n2: Counter[tuple[str, str]] = Counter(
        (row["stratum"], row["cheap_neuro"]) for row in gold
    )
    output: list[dict[str, float | int | str]] = []
    for stratum, label in sorted(n1, key=lambda key: (int(key[0]), int(key[1]))):
        first = n1[(stratum, label)]
        second = n2[(stratum, label)]
        output.append(
            {
                "stratum": stratum,
                "cheap_label": label,
                "first_stage_count": first,
                "second_stage_count": second,
                "observed_second_stage_fraction": second / first,
            }
        )
    return output


def _low_score_zero_event_bound(
    strata: Sequence[Mapping[str, str]],
    *,
    alpha: float = 0.05,
) -> dict[str, object]:
    """Exploratory zero-event bound under independent binomial-SRS assumptions.

    This is deliberately labelled as a sensitivity calculation. It does not establish
    the historical sampling design and does not turn stronger-model labels into truth.
    """
    per_stratum: list[dict[str, float | int | str]] = []
    total_upper = 0.0
    for row in strata:
        if int(row["stratum"]) > 3:
            continue
        n = int(row["n_judged"])
        N_h = int(row["N_families"])
        p_upper = 1.0 - alpha ** (1.0 / n)
        count_upper = N_h * p_upper
        total_upper += count_upper
        per_stratum.append(
            {
                "stratum": row["stratum"],
                "N_families": N_h,
                "n_judged": n,
                "one_sided_95_binomial_zero_event_p_upper": p_upper,
                "implied_count_upper": count_upper,
            }
        )
    return {
        "assumption": (
            "independent simple-random sampling within each stratum and zero true "
            "events in the observed sample; historical design validity and label truth "
            "are not established"
        ),
        "per_stratum": per_stratum,
        "sum_of_stratum_upper_counts": total_upper,
    }


def _cluster_audit(pool: Sequence[Mapping[str, str]]) -> dict[str, object]:
    blank = sum(row["cluster"] == "" for row in pool)
    nonblank_rows = [row for row in pool if row["cluster"] != ""]
    valid_0_20 = sum(
        row["cluster"].isdigit() and 0 <= int(row["cluster"]) <= 20
        for row in nonblank_rows
    )
    same_id = sum(
        row["cluster"] == row["docdb_family_id"] for row in nonblank_rows
    )

    offset_matches: dict[str, int] = {}
    for offset in range(5):
        matches = 0
        for index, row in enumerate(pool):
            if row["cluster"] == "":
                continue
            target = index + offset
            if target < len(pool) and row["cluster"] == pool[target]["docdb_family_id"]:
                matches += 1
        offset_matches[str(offset)] = matches

    by_band: dict[str, dict[str, int]] = {}
    for band in sorted({row["band"] for row in pool}):
        indices = [i for i, row in enumerate(pool) if row["band"] == band]
        nonblank = [i for i in indices if pool[i]["cluster"] != ""]
        band_record = {
            "nonblank_cluster_rows": len(nonblank),
            "offset_0_matches": 0,
            "offset_1_matches": 0,
            "offset_2_matches": 0,
            "offset_3_matches": 0,
            "offset_4_matches": 0,
        }
        for offset in range(5):
            band_record[f"offset_{offset}_matches"] = sum(
                i + offset < len(pool)
                and pool[i]["cluster"] == pool[i + offset]["docdb_family_id"]
                for i in nonblank
            )
        by_band[band] = band_record

    nonblank_indices = [
        i for i, row in enumerate(pool) if row["cluster"] != ""
    ]
    contiguous_prefix = (
        nonblank_indices == list(range(len(nonblank_indices)))
        if nonblank_indices
        else True
    )

    return {
        "row_count": len(pool),
        "blank_cluster_rows": blank,
        "nonblank_cluster_rows": len(nonblank_rows),
        "unique_cluster_values_including_blank": len(
            {row["cluster"] for row in pool}
        ),
        "values_in_declared_cluster_id_range_0_20": valid_0_20,
        "cluster_equals_same_row_docdb_family_id": same_id,
        "nonblank_values_form_contiguous_file_prefix": contiguous_prefix,
        "offset_matches_to_docdb_family_id": offset_matches,
        "by_band": by_band,
        "estimator_consumes_cluster_field": False,
    }


def build_audit(extract: Path) -> dict[str, object]:
    """Build the exact public-extract audit record."""
    missing = [name for name in SOURCE_BLOBS if not (extract / name).is_file()]
    if missing:
        raise AuditError(f"missing source files: {missing}")

    actual_blobs = {
        name: git_blob_sha(extract / name)
        for name in SOURCE_BLOBS
    }
    mismatched = {
        name: {"expected": SOURCE_BLOBS[name], "actual": actual}
        for name, actual in actual_blobs.items()
        if actual != SOURCE_BLOBS[name]
    }
    if mismatched:
        raise AuditError(
            "source blob binding mismatch: "
            + json.dumps(mismatched, sort_keys=True)
        )

    strata = _read_csv(extract / "strata.csv", EXPECTED_HEADERS["strata.csv"])
    judged = _read_csv(
        extract / "judged_sample.csv", EXPECTED_HEADERS["judged_sample.csv"]
    )
    gold = _read_csv(
        extract / "gold_labels.csv", EXPECTED_HEADERS["gold_labels.csv"]
    )
    pool = _read_csv(
        extract / "pool_frame.csv", EXPECTED_HEADERS["pool_frame.csv"]
    )
    clusters = _read_csv(
        extract / "clusters.csv", EXPECTED_HEADERS["clusters.csv"]
    )

    judged_ids = _unique_ids(judged, "docdb_family_id", "judged_sample.csv")
    gold_ids = _unique_ids(gold, "docdb_family_id", "gold_labels.csv")
    pool_ids = _unique_ids(pool, "docdb_family_id", "pool_frame.csv")
    if not gold_ids.issubset(judged_ids):
        raise AuditError("gold_labels.csv contains ids absent from judged_sample.csv")

    judged_by_id = {row["docdb_family_id"]: row for row in judged}
    cheap_mismatches = [
        row["docdb_family_id"]
        for row in gold
        if judged_by_id[row["docdb_family_id"]]["neuro"] != row["cheap_neuro"]
    ]
    if cheap_mismatches:
        raise AuditError(
            "gold_labels cheap_neuro does not round-trip to judged_sample for "
            f"{cheap_mismatches[:10]}"
        )

    population_by_stratum = {
        row["stratum"]: int(row["N_families"]) for row in strata
    }
    gold_by_id = {row["docdb_family_id"]: row for row in gold}

    per_stratum: list[dict[str, object]] = []
    for design in strata:
        h = design["stratum"]
        rows = [row for row in judged if row["stratum"] == h]
        valid = [row for row in rows if row["neuro"] != ""]
        label_counts = Counter(row["neuro"] for row in valid)
        per_stratum.append(
            {
                "stratum": h,
                "N_families": int(design["N_families"]),
                "planned_n_judged": int(design["n_judged"]),
                "exported_rows": len(rows),
                "valid_neuro_rows": len(valid),
                "missing_neuro_rows": len(rows) - len(valid),
                "label_0": label_counts["0"],
                "label_1_borderline": label_counts["1"],
                "label_2_relevant": label_counts["2"],
            }
        )

    missing_label_rows = [
        {
            "docdb_family_id": row["docdb_family_id"],
            "stratum": row["stratum"],
            "score": row["score"],
            "verdict": row["verdict"],
        }
        for row in judged
        if row["neuro"] == "" or row["ml"] == ""
    ]
    nonstandard_rows = [
        {
            "docdb_family_id": row["docdb_family_id"],
            "stratum": row["stratum"],
            "score": row["score"],
            "neuro": row["neuro"],
            "ml": row["ml"],
            "verdict": row["verdict"],
        }
        for row in judged
        if row["verdict"] not in STANDARD_VERDICTS
    ]

    kappa_three, confusion_three = _cohen_kappa(
        gold, "cheap_neuro", "gold_neuro", ["0", "1", "2"]
    )
    binary = _binary_metrics(gold)

    corpus_public = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=None,
        correction_cells="public_masked_binary",
    )
    pool_public = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=pool_ids,
        correction_cells="public_masked_binary",
    )
    cheap_only = _cheap_only_total(judged, population_by_stratum)

    borderline_corpus = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=None,
        borderline_relevant=True,
        correction_cells="public_masked_binary",
    )
    borderline_pool = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=pool_ids,
        borderline_relevant=True,
        correction_cells="public_masked_binary",
    )

    original_three_corpus = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=None,
        correction_cells="original_three_class",
    )
    original_three_pool = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=pool_ids,
        correction_cells="original_three_class",
    )
    original_binary_pool = _estimate(
        judged,
        gold_by_id,
        population_by_stratum,
        members=pool_ids,
        correction_cells="original_binary",
    )

    sd = corpus_public.first_stage_sd_only
    if sd is None:
        raise AuditError("public estimator did not return first-stage SD")
    first_stage_wald = [
        corpus_public.total - 1.96 * sd,
        corpus_public.total + 1.96 * sd,
    ]

    return {
        "schema_version": "0.1",
        "audit_scope": "PUBLIC_EXTRACT_MECHANICAL_AUDIT_ONLY",
        "source_binding": {
            "source_main_commit": SOURCE_MAIN_COMMIT,
            "git_blobs": actual_blobs,
        },
        "row_integrity": {
            "strata_rows": len(strata),
            "judged_rows": len(judged),
            "gold_rows": len(gold),
            "pool_rows": len(pool),
            "cluster_summary_rows": len(clusters),
            "judged_unique_ids": len(judged_ids),
            "gold_unique_ids": len(gold_ids),
            "pool_unique_ids": len(pool_ids),
            "gold_ids_all_present_in_judged": True,
            "gold_cheap_labels_match_judged": True,
            "per_stratum": per_stratum,
        },
        "verdict_integrity": {
            "standard_verdict_tokens": sorted(STANDARD_VERDICTS),
            "rows_with_missing_neuro_or_ml": len(missing_label_rows),
            "missing_label_rows": missing_label_rows,
            "rows_with_nonstandard_raw_verdict": len(nonstandard_rows),
            "nonstandard_raw_verdict_rows": nonstandard_rows,
            "analysis_statement_four_rows_carried_missing_supported_by_export": False,
        },
        "reread_agreement": {
            "three_class_confusion_prediction_by_outcome": confusion_three,
            "cohen_kappa_three_class": kappa_three,
            "binary_label2_vs_rest": binary,
            "analysis_kappa_0_469_reproduced_as_three_class": math.isclose(
                kappa_three, 0.469, abs_tol=0.0005
            ),
        },
        "point_estimate_reproduction": {
            "cheap_only_corpus": cheap_only,
            "public_script_corpus": corpus_public.total,
            "public_script_pool": pool_public.total,
            "public_script_recall": pool_public.total / corpus_public.total,
            "public_script_missed": corpus_public.total - pool_public.total,
        },
        "uncertainty_audit": {
            "public_script_first_stage_sd_only": sd,
            "public_script_first_stage_only_wald95": first_stage_wald,
            "readme_reported_interval": [40256, 57854],
            "analysis_reported_interval": [41512, 58192],
            "readme_interval_reproduced_by_visible_variance": False,
            "analysis_interval_reproduced_by_visible_variance": False,
            "full_interval_validated": False,
            "recall_ratio_uncertainty_validated": False,
        },
        "second_stage_allocation": {
            "observed_allocation_by_original_stratum_and_cheap_label": _stage2_allocation(
                judged, gold
            ),
            "exact_selection_probabilities_reconstructible_from_public_extract": False,
            "design_unbiasedness_validated": False,
            "note": (
                "Observed reread fractions differ materially across original cheap-label "
                "cells. The public reproducer collapses labels 0 and 1 into a binary cell, "
                "and for pool estimation post-stratifies after applying the pool mask. "
                "Without the historical selection design and pilot/ppi.py, the claimed "
                "design-unbiasedness is not independently established."
            ),
        },
        "sensitivity_only_not_validated_estimands": {
            "borderline_as_relevant_under_public_algorithm": {
                "corpus": borderline_corpus.total,
                "pool": borderline_pool.total,
                "recall": borderline_pool.total / borderline_corpus.total,
            },
            "preserve_original_three_class_correction_cells": {
                "corpus": original_three_corpus.total,
                "pool": original_three_pool.total,
                "recall": original_three_pool.total / original_three_corpus.total,
            },
            "preserve_original_binary_cell_before_pool_mask": {
                "pool": original_binary_pool.total,
                "recall_using_public_corpus": original_binary_pool.total / corpus_public.total,
            },
            "interpretation": (
                "These calculations expose sensitivity to boundary and correction-cell "
                "semantics. They do not identify the historically correct estimator."
            ),
        },
        "low_score_zero_event_sensitivity": _low_score_zero_event_bound(strata),
        "pool_cluster_field_audit": _cluster_audit(pool),
        "scientific_disposition": {
            "state": "PARTIAL_INDEPENDENT_AUDIT_BLOCKED_ON_MISSING_PROVENANCE",
            "public_point_estimates_mechanically_reproduced": True,
            "historical_estimator_fully_reconstructed": False,
            "design_unbiasedness_established": False,
            "reported_intervals_validated": False,
            "retrieval_recall_uncertainty_validated": False,
            "human_reference_standard_established": False,
            "global_population_generalization_established": False,
            "rights_clearance_established": False,
        },
        "authority": {
            "g0_passed": False,
            "g2_passed": False,
            "g5_passed": False,
            "canonical_scientific_finding": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extract",
        type=Path,
        default=DEFAULT_EXTRACT,
        help="Path to the bound patent-evidence-extract directory.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "pretty"),
        default="json",
        help="Output compact JSON or indented JSON.",
    )
    args = parser.parse_args()

    try:
        audit = build_audit(args.extract)
    except (OSError, UnicodeDecodeError, csv.Error, AuditError, ValueError) as exc:
        print(f"INVALID: {exc}")
        return 1

    if args.format == "pretty":
        print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(
            json.dumps(
                audit,
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

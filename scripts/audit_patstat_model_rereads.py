"""Read-only, model-to-model PATSTAT Baseline A reread diagnostics.

This audit reads the *historical* nine-stratum frame and 333 stronger-model
rereads. It checks field integrity, reports the observed correction-cell
occupancy, and computes descriptive agreement. Neither classifier is human
ground truth. It does not reconstruct first-/second-phase inclusion
probabilities, certify population estimates or confidence intervals, or
modify the historical Baseline A files.

Usage:
    python -m scripts.audit_patstat_model_rereads \
        --data-dir patent-evidence-extract \
        --output /tmp/patstat-reread-diagnostics.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path("patent-evidence-extract")
LABELS = ("0", "1", "2")
EXPECTED_STRATA = tuple(str(i) for i in range(9))


class RereadAuditError(ValueError):
    """Raised for malformed, missing or inconsistent historical source data."""


def _load_csv(path: Path, required: set[str]) -> tuple[list[dict[str, str]], str]:
    """Read unmodified source bytes and reject invalid CSV schemas."""
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(text.splitlines())
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RereadAuditError(f"{path.name}: missing required columns")
        rows = list(reader)
    except UnicodeError as exc:
        raise RereadAuditError(f"{path.name}: invalid UTF-8") from exc
    for index, row in enumerate(rows, start=2):
        if None in row or any(v is None for v in row.values()):
            raise RereadAuditError(f"{path.name}: malformed row {index}")
    return rows, hashlib.sha256(payload).hexdigest()


def _kappa(confusion: dict[str, dict[str, int]], labels: tuple[str, ...]) -> float | None:
    """Return descriptive unweighted Cohen kappa, or None for degeneracy."""
    n = sum(confusion[r][c] for r in labels for c in labels)
    if n == 0:
        return None
    observed = sum(confusion[c][c] for c in labels) / n
    expected = sum(
        sum(confusion[label][col] for col in labels)
        * sum(confusion[row][label] for row in labels)
        for label in labels
    ) / (n * n)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def build_diagnostic(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """Reproduce descriptive reread statistics with a fail-closed CSV audit."""
    strata, strata_digest = _load_csv(
        data_dir / "strata.csv", {"stratum", "N_families", "n_judged"}
    )
    second, reread_digest = _load_csv(
        data_dir / "gold_labels.csv",
        {"docdb_family_id", "stratum", "gold_neuro", "cheap_neuro"},
    )
    populations: dict[str, int] = {}
    sample_sizes: dict[str, int] = {}
    for row in strata:
        stratum = row["stratum"]
        if stratum in populations or stratum not in EXPECTED_STRATA:
            raise RereadAuditError("Duplicate or unknown stratum")
        try:
            population = int(row["N_families"])
            sampled = int(row["n_judged"])
        except ValueError as exc:
            raise RereadAuditError("Invalid stratum population/sample count") from exc
        if not (0 < sampled <= population):
            raise RereadAuditError("Invalid within-stratum sampling bounds")
        populations[stratum] = population
        sample_sizes[stratum] = sampled
    if set(populations) != set(EXPECTED_STRATA):
        raise RereadAuditError("Historical nine-stratum design incomplete")

    observed = Counter()
    strong_label_counts = Counter()
    first_label_counts = Counter()
    confusion = {r: {c: 0 for c in LABELS} for r in LABELS}
    seen: set[str] = set()
    by_stratum = Counter()
    for row in second:
        identifier = row["docdb_family_id"]
        stratum = row["stratum"]
        strong = row["gold_neuro"]
        first = row["cheap_neuro"]
        if (
            not identifier.isdecimal()
            or identifier in seen
            or stratum not in populations
            or strong not in LABELS
            or first not in LABELS
        ):
            raise RereadAuditError("Malformed, duplicate or out-of-frame model reread")
        seen.add(identifier)
        observed[(stratum, first)] += 1
        by_stratum[stratum] += 1
        confusion[strong][first] += 1
        strong_label_counts[strong] += 1
        first_label_counts[first] += 1
    for stratum in EXPECTED_STRATA:
        if by_stratum[stratum] > sample_sizes[stratum]:
            raise RereadAuditError("More rereads than sampled families in a stratum")

    n = len(second)
    # Rows index the stronger model, columns the original 26B model.
    tp = confusion["2"]["2"]
    fp = confusion["0"]["2"] + confusion["1"]["2"]
    fn = confusion["2"]["0"] + confusion["2"]["1"]
    tn = n - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    binary_raw = {
        "0": {"0": tn, "1": fp},
        "1": {"0": fn, "1": tp},
    }
    # A symmetric display, with 1 indicating the first-model positive;
    # here rows are stronger-model status, columns first-model status.
    binary_kappa = _kappa(binary_raw, ("0", "1"))
    original_cells = [
        {"stratum": stratum, "first_model_label": label, "reread_count": observed[(stratum, label)]}
        for stratum in EXPECTED_STRATA
        for label in LABELS
    ]
    return {
        "artifact_type": "PATSTAT_BASELINE_A_MODEL_REREAD_DIAGNOSTIC_v0.1",
        "status": "DESCRIPTIVE_MODEL_COMPARISON_ONLY",
        "source_files_sha256": {
            "strata.csv": strata_digest,
            "gold_labels.csv": reread_digest,
        },
        "strata_count": len(populations),
        "english_abstract_frame_families": sum(populations.values()),
        "historical_first_model_sample_n_from_strata": sum(sample_sizes.values()),
        "stronger_model_reread_count": n,
        "first_model_labels": dict(sorted(first_label_counts.items())),
        "stronger_model_labels": dict(sorted(strong_label_counts.items())),
        "reread_count_by_stratum": dict(sorted(by_stratum.items())),
        "observed_stratum_by_first_label_cells": original_cells,
        "zero_observed_reread_cells": [
            {"stratum": cell["stratum"], "first_model_label": cell["first_model_label"]}
            for cell in original_cells if cell["reread_count"] == 0
        ],
        "stronger_model_rows_by_first_model_columns": confusion,
        "binary_stronger_model_as_reference_only": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall,
            "cohen_kappa": binary_kappa,
        },
        "three_class_cohen_kappa": _kappa(confusion, LABELS),
        "not_established": [
            "Human reference labels or D3 validation",
            "Historical second-stage selection probabilities or within-cell sampling design",
            "A design-unbiased correction or justified post-stratified estimator",
            "Complete first-/second-phase variance and ratio uncertainty",
            "Population precision or recall from the selected 333 rereads",
            "Rights clearance or public release authority",
        ],
        "interpretation": (
            "Zero observed reread cells describe these 333 selected records; "
            "they do not establish an empty population cell. The historical "
            "reproduce.py estimator omits a correction when its selected "
            "reread cell is empty. The actual population cell sizes, "
            "selection probabilities, and uncertainty remain to be audited."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Compute a read-only JSON diagnostic without altering source data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = json.dumps(build_diagnostic(args.data_dir), sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

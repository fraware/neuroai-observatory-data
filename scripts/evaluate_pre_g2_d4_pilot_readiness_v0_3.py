from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import evaluate_pre_g2_d4_pilot_readiness_v0_2 as predecessor

BENCHMARK_ID = predecessor.BENCHMARK_ID
PROTOCOL_ID = predecessor.PROTOCOL_ID
COMMITMENT_SCHEME = predecessor.COMMITMENT_SCHEME
READY_STATE = predecessor.READY_STATE
NOT_READY_STATE = predecessor.NOT_READY_STATE
REQUIRED_STRATA = predecessor.REQUIRED_STRATA
DISPOSITIONS = predecessor.DISPOSITIONS
READINESS_POLICY_ID = "PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-18_v0.3"

EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {*predecessor.EXPECTED_TOP_LEVEL_KEYS, "primary_secondary_confusion_matrix"}
)


class D4PilotReadinessV03Error(predecessor.D4PilotReadinessError):
    """Raised when the D4 v0.3 readiness evidence violates the successor contract."""


# Preserve the predecessor module interface for composed-execution callers.
D4PilotReadinessError = D4PilotReadinessV03Error


def _validate_confusion_matrix(value: Any) -> dict[str, dict[str, int]]:
    matrix = predecessor._require_mapping(value, "primary_secondary_confusion_matrix")
    predecessor._require_exact_keys(
        matrix,
        set(DISPOSITIONS),
        "primary_secondary_confusion_matrix",
    )
    normalized: dict[str, dict[str, int]] = {}
    total = 0
    for primary in DISPOSITIONS:
        row = predecessor._require_mapping(
            matrix[primary],
            f"primary_secondary_confusion_matrix.{primary}",
        )
        predecessor._require_exact_keys(
            row,
            set(DISPOSITIONS),
            f"primary_secondary_confusion_matrix.{primary}",
        )
        normalized[primary] = {}
        for secondary in DISPOSITIONS:
            count = predecessor._require_int(
                row[secondary],
                f"primary_secondary_confusion_matrix.{primary}.{secondary}",
                maximum=60,
            )
            normalized[primary][secondary] = count
            total += count
    if total != 60:
        raise D4PilotReadinessV03Error(
            "primary_secondary_confusion_matrix must account for exactly 60 double-labeled items"
        )
    return normalized


def evaluate_pilot_readiness(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate D4 readiness and bind the governance-mandated full 4x4 matrix.

    The predecessor v0.2 quantitative controls remain unchanged. This successor
    adds only evidence completeness and consistency checks required by the human
    governance disposition in issue #242: the complete PRIMARY x SECONDARY
    four-way matrix must be present, account for all 60 items, and agree with
    the reported exact-agreement count.
    """

    predecessor._require_exact_keys(
        report,
        set(EXPECTED_TOP_LEVEL_KEYS),
        "report",
    )
    matrix = _validate_confusion_matrix(report["primary_secondary_confusion_matrix"])

    predecessor_report = dict(report)
    predecessor_report.pop("primary_secondary_confusion_matrix")
    try:
        result = predecessor.evaluate_pilot_readiness(predecessor_report)
    except predecessor.D4PilotReadinessError as exc:
        raise D4PilotReadinessV03Error(str(exc)) from exc

    diagonal = sum(matrix[label][label] for label in DISPOSITIONS)
    agreement = report["primary_secondary_exact_agreement_count"]
    if diagonal != agreement:
        raise D4PilotReadinessV03Error(
            "primary_secondary_exact_agreement_count must equal the confusion-matrix diagonal"
        )

    include_exclude_reversals = (
        matrix["INCLUDE"]["EXCLUDE"] + matrix["EXCLUDE"]["INCLUDE"]
    )
    borderline_or_abstain_disagreements = sum(
        matrix[primary][secondary]
        for primary in DISPOSITIONS
        for secondary in DISPOSITIONS
        if primary != secondary
        and (
            primary in {"BORDERLINE", "ABSTAIN"}
            or secondary in {"BORDERLINE", "ABSTAIN"}
        )
    )

    return {
        **result,
        "readiness_policy_id": READINESS_POLICY_ID,
        "primary_secondary_confusion_matrix": matrix,
        "include_exclude_reversal_count": include_exclude_reversals,
        "borderline_or_abstain_disagreement_count": borderline_or_abstain_disagreements,
        "full_confusion_matrix_required_for_human_calibration": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate PRE-G2 D4 pilot readiness under the v0.3 "
            "confusion-matrix evidence successor"
        )
    )
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise D4PilotReadinessV03Error("report root must be an object")
        result = evaluate_pilot_readiness(payload)
    except (OSError, json.JSONDecodeError, predecessor.D4PilotReadinessError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0 if result["quantitative_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PATENT_V0_1"
PROTOCOL_ID = "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1"
COMMITMENT_SCHEME = "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1"
READY_STATE = "READY_FOR_HUMAN_CALIBRATION_DISPOSITION"
NOT_READY_STATE = "NOT_READY_NEW_DISJOINT_ROUND_REQUIRED"

PILOT_N = 60
MAX_UNRESOLVED = 6
MIN_BOUNDARY_COUNT = 10
MIN_STRATUM_COUNT = 10

REQUIRED_STRATA = (
    "GRAY_CAPABILITY",
    "MISSING_OR_SHORT_ABSTRACT",
    "MULTI_JURISDICTION",
    "MULTI_YEAR",
    "MULTILINGUAL",
    "SEMANTICALLY_DECEPTIVE_NEGATIVE",
)
DISPOSITIONS = ("ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "benchmark_id",
    "protocol_id",
    "pilot_round_id",
    "state",
    "total_items",
    "double_labeled_items",
    "primary_secondary_exact_agreement_count",
    "primary_secondary_confusion_matrix",
    "adjudicated_disagreement_count",
    "unresolved_disagreement_count",
    "resolved_disposition_counts",
    "required_stratum_counts",
    "per_stratum_disagreement_counts",
    "semantic_validation_failure_count",
    "reviewer_reference_collision_count",
    "evidence_binding_failure_count",
    "blinding_exception_count",
    "blinding_exception_with_rationale_count",
    "pilot_items_held_out_eligible_count",
    "pilot_membership_commitment",
    "pilot_membership_commitment_scheme",
    "reviewer_training_record_sha256",
    "exposure_register_sha256",
    "prior_exposure_disjointness_audit_sha256",
    "authority",
}
EXPECTED_AUTHORITY_KEYS = {
    "reviewer_competence_established",
    "benchmark_adequacy_established",
    "g2_passed",
    "canonical_s2_authority",
    "publication_authority",
    "population_generalization_authority",
    "assessment_effect",
}


class D3ChallengePilotReadinessError(ValueError):
    """Raised when a D3 challenge pilot aggregate is invalid."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D3ChallengePilotReadinessError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D3ChallengePilotReadinessError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_int(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise D3ChallengePilotReadinessError(f"{field} must be an integer")
    if value < minimum:
        raise D3ChallengePilotReadinessError(f"{field} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise D3ChallengePilotReadinessError(f"{field} must be <= {maximum}")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D3ChallengePilotReadinessError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return value


def _require_count_map(
    value: Any,
    keys: tuple[str, ...],
    field: str,
) -> dict[str, int]:
    mapping = _require_mapping(value, field)
    _require_exact_keys(mapping, set(keys), field)
    return {
        key: _require_int(mapping[key], f"{field}.{key}", maximum=PILOT_N)
        for key in keys
    }


def _validate_confusion_matrix(value: Any) -> dict[str, dict[str, int]]:
    matrix = _require_mapping(value, "primary_secondary_confusion_matrix")
    _require_exact_keys(matrix, set(DISPOSITIONS), "primary_secondary_confusion_matrix")
    normalized: dict[str, dict[str, int]] = {}
    total = 0
    for primary in DISPOSITIONS:
        row = _require_mapping(
            matrix[primary],
            f"primary_secondary_confusion_matrix.{primary}",
        )
        _require_exact_keys(
            row,
            set(DISPOSITIONS),
            f"primary_secondary_confusion_matrix.{primary}",
        )
        normalized[primary] = {}
        for secondary in DISPOSITIONS:
            count = _require_int(
                row[secondary],
                f"primary_secondary_confusion_matrix.{primary}.{secondary}",
                maximum=PILOT_N,
            )
            normalized[primary][secondary] = count
            total += count
    if total != PILOT_N:
        raise D3ChallengePilotReadinessError(
            "primary_secondary_confusion_matrix must account for all 60 items"
        )
    return normalized


def _validate_authority(value: Any) -> None:
    authority = _require_mapping(value, "authority")
    _require_exact_keys(authority, EXPECTED_AUTHORITY_KEYS, "authority")
    for field in (
        "reviewer_competence_established",
        "benchmark_adequacy_established",
        "g2_passed",
        "canonical_s2_authority",
        "publication_authority",
        "population_generalization_authority",
    ):
        if authority[field] is not False:
            raise D3ChallengePilotReadinessError(
                f"authority.{field} must remain false"
            )
    if authority["assessment_effect"] != "NONE":
        raise D3ChallengePilotReadinessError(
            "authority.assessment_effect must remain NONE"
        )


def evaluate_pilot_readiness(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the fixed D3 challenge calibration gate without conferring authority.

    Raw reviewer agreement is deliberately reported but is not an automated pass/fail
    threshold because the challenge pilot intentionally enriches ambiguous and
    borderline cases. A passing result only makes the round eligible for separate
    human calibration review.
    """

    _require_exact_keys(report, EXPECTED_TOP_LEVEL_KEYS, "report")
    if report["schema_version"] != "0.1":
        raise D3ChallengePilotReadinessError("schema_version must be 0.1")
    if report["benchmark_id"] != BENCHMARK_ID:
        raise D3ChallengePilotReadinessError(
            f"benchmark_id must be {BENCHMARK_ID}"
        )
    if report["protocol_id"] != PROTOCOL_ID:
        raise D3ChallengePilotReadinessError(
            f"protocol_id must be {PROTOCOL_ID}"
        )
    if not isinstance(report["pilot_round_id"], str) or not report[
        "pilot_round_id"
    ].strip():
        raise D3ChallengePilotReadinessError(
            "pilot_round_id must be a non-empty string"
        )
    if report["state"] != "COMPLETE_ROUND_NO_EXTENSION":
        raise D3ChallengePilotReadinessError(
            "state must be COMPLETE_ROUND_NO_EXTENSION"
        )
    if report["pilot_membership_commitment_scheme"] != COMMITMENT_SCHEME:
        raise D3ChallengePilotReadinessError(
            f"pilot_membership_commitment_scheme must be {COMMITMENT_SCHEME}"
        )

    total = _require_int(report["total_items"], "total_items", maximum=PILOT_N)
    double_labeled = _require_int(
        report["double_labeled_items"],
        "double_labeled_items",
        maximum=PILOT_N,
    )
    agreement = _require_int(
        report["primary_secondary_exact_agreement_count"],
        "primary_secondary_exact_agreement_count",
        maximum=PILOT_N,
    )
    matrix = _validate_confusion_matrix(
        report["primary_secondary_confusion_matrix"]
    )
    diagonal = sum(matrix[label][label] for label in DISPOSITIONS)
    if agreement != diagonal:
        raise D3ChallengePilotReadinessError(
            "primary_secondary_exact_agreement_count must equal the confusion-matrix diagonal"
        )

    adjudicated = _require_int(
        report["adjudicated_disagreement_count"],
        "adjudicated_disagreement_count",
        maximum=PILOT_N,
    )
    unresolved = _require_int(
        report["unresolved_disagreement_count"],
        "unresolved_disagreement_count",
        maximum=PILOT_N,
    )
    if total != PILOT_N or double_labeled != PILOT_N:
        raise D3ChallengePilotReadinessError(
            "pilot round must contain exactly 60 items and all 60 must be double labeled"
        )
    if agreement + adjudicated + unresolved != PILOT_N:
        raise D3ChallengePilotReadinessError(
            "agreement + adjudicated disagreement + unresolved disagreement must account for all 60 items"
        )

    dispositions = _require_count_map(
        report["resolved_disposition_counts"],
        DISPOSITIONS,
        "resolved_disposition_counts",
    )
    if sum(dispositions.values()) != agreement + adjudicated:
        raise D3ChallengePilotReadinessError(
            "resolved disposition counts must equal agreement + adjudicated disagreement counts"
        )

    stratum_counts = _require_count_map(
        report["required_stratum_counts"],
        REQUIRED_STRATA,
        "required_stratum_counts",
    )
    stratum_disagreements = _require_count_map(
        report["per_stratum_disagreement_counts"],
        REQUIRED_STRATA,
        "per_stratum_disagreement_counts",
    )
    for stratum in REQUIRED_STRATA:
        if stratum_disagreements[stratum] > stratum_counts[stratum]:
            raise D3ChallengePilotReadinessError(
                f"per_stratum_disagreement_counts.{stratum} cannot exceed required_stratum_counts.{stratum}"
            )

    semantic_failures = _require_int(
        report["semantic_validation_failure_count"],
        "semantic_validation_failure_count",
    )
    reviewer_collisions = _require_int(
        report["reviewer_reference_collision_count"],
        "reviewer_reference_collision_count",
    )
    evidence_failures = _require_int(
        report["evidence_binding_failure_count"],
        "evidence_binding_failure_count",
    )
    blinding_exceptions = _require_int(
        report["blinding_exception_count"],
        "blinding_exception_count",
        maximum=PILOT_N,
    )
    blinding_with_rationale = _require_int(
        report["blinding_exception_with_rationale_count"],
        "blinding_exception_with_rationale_count",
        maximum=PILOT_N,
    )
    pilot_held_out_eligible = _require_int(
        report["pilot_items_held_out_eligible_count"],
        "pilot_items_held_out_eligible_count",
        maximum=PILOT_N,
    )

    _require_sha256(
        report["pilot_membership_commitment"],
        "pilot_membership_commitment",
    )
    _require_sha256(
        report["reviewer_training_record_sha256"],
        "reviewer_training_record_sha256",
    )
    _require_sha256(
        report["exposure_register_sha256"],
        "exposure_register_sha256",
    )
    _require_sha256(
        report["prior_exposure_disjointness_audit_sha256"],
        "prior_exposure_disjointness_audit_sha256",
    )
    _validate_authority(report["authority"])

    violations: list[str] = []
    if unresolved > MAX_UNRESOLVED:
        violations.append("UNRESOLVED_DISAGREEMENT_ABOVE_6_OF_60")
    for disposition in ("INCLUDE", "EXCLUDE", "BORDERLINE"):
        if dispositions[disposition] < MIN_BOUNDARY_COUNT:
            violations.append(f"RESOLVED_{disposition}_BELOW_10")
    for stratum in REQUIRED_STRATA:
        if stratum_counts[stratum] < MIN_STRATUM_COUNT:
            violations.append(f"STRATUM_{stratum}_BELOW_10")
    if semantic_failures != 0:
        violations.append("SEMANTIC_VALIDATION_FAILURE_COUNT_NONZERO")
    if reviewer_collisions != 0:
        violations.append("REVIEWER_REFERENCE_COLLISION_COUNT_NONZERO")
    if evidence_failures != 0:
        violations.append("EVIDENCE_BINDING_FAILURE_COUNT_NONZERO")
    if blinding_with_rationale != blinding_exceptions:
        violations.append("BLINDING_EXCEPTION_RATIONALE_ACCOUNTING_MISMATCH")
    if pilot_held_out_eligible != 0:
        violations.append("PILOT_ITEM_HELD_OUT_ELIGIBILITY_NONZERO")

    quantitative_gate_passed = not violations
    return {
        "pilot_round_id": report["pilot_round_id"],
        "state": (
            READY_STATE
            if quantitative_gate_passed
            else NOT_READY_STATE
        ),
        "quantitative_gate_passed": quantitative_gate_passed,
        "agreement_count": agreement,
        "agreement_rate_descriptive_only": agreement / PILOT_N,
        "agreement_is_automated_gate": False,
        "unresolved_disagreement_count": unresolved,
        "unresolved_disagreement_rate_descriptive_only": unresolved / PILOT_N,
        "resolved_disposition_counts": dispositions,
        "required_stratum_counts": stratum_counts,
        "violations": violations,
        "human_calibration_disposition_required": True,
        "population_generalizable": False,
        "authority": {
            "reviewer_competence_established": False,
            "benchmark_adequacy_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "population_generalization_authority": False,
            "assessment_effect": "NONE",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the PRE-G2 D3 challenge 60-family pilot readiness gate"
    )
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise D3ChallengePilotReadinessError("report root must be an object")
        result = evaluate_pilot_readiness(payload)
    except (OSError, json.JSONDecodeError, D3ChallengePilotReadinessError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0 if result["quantitative_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

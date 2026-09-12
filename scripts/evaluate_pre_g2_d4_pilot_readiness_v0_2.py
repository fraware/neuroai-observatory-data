from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PRODUCT_V0_1"
PROTOCOL_ID = "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1"\nREADINESS_POLICY_ID = "PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-12_v0.2"
COMMITMENT_SCHEME = "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1"
READY_STATE = "READY_FOR_HUMAN_CALIBRATION_DISPOSITION"
NOT_READY_STATE = "NOT_READY_NEW_DISJOINT_ROUND_REQUIRED"

REQUIRED_STRATA = (
    "AMBIGUOUS_BIOSIGNAL",
    "CLINICAL",
    "CONSUMER",
    "ENTERTAINMENT_XR",
    "MULTI_JURISDICTION",
    "MULTILINGUAL",
    "NONTRADITIONAL_FORM_FACTOR",
    "RESEARCH",
    "WELLNESS",
    "WORKPLACE",
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
    "pilot_disjointness_proof_sha256",
    "authority",
}
EXPECTED_AUTHORITY_KEYS = {
    "reviewer_competence_established",
    "benchmark_adequacy_established",
    "g2_passed",
    "canonical_s2_authority",
    "publication_authority",
    "assessment_effect",
}


class D4PilotReadinessError(ValueError):
    """Raised when a pilot aggregate is structurally or semantically invalid."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D4PilotReadinessError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D4PilotReadinessError(f"{field} keys mismatch; missing={missing}, extra={extra}")


def _require_int(value: Any, field: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise D4PilotReadinessError(f"{field} must be an integer")
    if value < minimum:
        raise D4PilotReadinessError(f"{field} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise D4PilotReadinessError(f"{field} must be <= {maximum}")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D4PilotReadinessError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _require_count_map(value: Any, keys: tuple[str, ...], field: str) -> dict[str, int]:
    mapping = _require_mapping(value, field)
    _require_exact_keys(mapping, set(keys), field)
    return {key: _require_int(mapping[key], f"{field}.{key}", maximum=60) for key in keys}


def _validate_authority(value: Any) -> None:
    authority = _require_mapping(value, "authority")
    _require_exact_keys(authority, EXPECTED_AUTHORITY_KEYS, "authority")
    for field in (
        "reviewer_competence_established",
        "benchmark_adequacy_established",
        "g2_passed",
        "canonical_s2_authority",
        "publication_authority",
    ):
        if authority[field] is not False:
            raise D4PilotReadinessError(f"authority.{field} must remain false")
    if authority["assessment_effect"] != "NONE":
        raise D4PilotReadinessError("authority.assessment_effect must remain NONE")


def evaluate_pilot_readiness(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the fixed 60-item quantitative pilot gate without conferring authority.

    A passing result means only that the aggregate is ready for a separate human
    calibration disposition. It does not establish reviewer competence, source
    truth, benchmark adequacy, G2, publication authority, or S2 authority.
    """

    _require_exact_keys(report, EXPECTED_TOP_LEVEL_KEYS, "report")
    if report["schema_version"] != "0.1":
        raise D4PilotReadinessError("schema_version must be 0.1")
    if report["benchmark_id"] != BENCHMARK_ID:
        raise D4PilotReadinessError(f"benchmark_id must be {BENCHMARK_ID}")
    if report["protocol_id"] != PROTOCOL_ID:
        raise D4PilotReadinessError(f"protocol_id must be {PROTOCOL_ID}")
    if not isinstance(report["pilot_round_id"], str) or not report["pilot_round_id"].strip():
        raise D4PilotReadinessError("pilot_round_id must be a non-empty string")
    if report["state"] != "COMPLETE_ROUND_NO_EXTENSION":
        raise D4PilotReadinessError("state must be COMPLETE_ROUND_NO_EXTENSION")
    if report["pilot_membership_commitment_scheme"] != COMMITMENT_SCHEME:
        raise D4PilotReadinessError(f"pilot_membership_commitment_scheme must be {COMMITMENT_SCHEME}")

    total = _require_int(report["total_items"], "total_items", maximum=60)
    double_labeled = _require_int(report["double_labeled_items"], "double_labeled_items", maximum=60)
    agreement = _require_int(
        report["primary_secondary_exact_agreement_count"],
        "primary_secondary_exact_agreement_count",
        maximum=60,
    )
    adjudicated = _require_int(
        report["adjudicated_disagreement_count"],
        "adjudicated_disagreement_count",
        maximum=60,
    )
    unresolved = _require_int(
        report["unresolved_disagreement_count"],
        "unresolved_disagreement_count",
        maximum=60,
    )

    if total != 60 or double_labeled != 60:
        raise D4PilotReadinessError("pilot round must contain exactly 60 items and all 60 must be double labeled")
    if agreement + adjudicated + unresolved != 60:
        raise D4PilotReadinessError(
            "agreement + adjudicated disagreement + unresolved disagreement must account for all 60 items"
        )

    dispositions = _require_count_map(report["resolved_disposition_counts"], DISPOSITIONS, "resolved_disposition_counts")
    resolved_count = sum(dispositions.values())
    if resolved_count != agreement + adjudicated:
        raise D4PilotReadinessError(
            "resolved disposition counts must equal agreement + adjudicated disagreement counts"
        )

    stratum_counts = _require_count_map(report["required_stratum_counts"], REQUIRED_STRATA, "required_stratum_counts")
    stratum_disagreements = _require_count_map(
        report["per_stratum_disagreement_counts"], REQUIRED_STRATA, "per_stratum_disagreement_counts"
    )
    for stratum in REQUIRED_STRATA:
        if stratum_disagreements[stratum] > stratum_counts[stratum]:
            raise D4PilotReadinessError(
                f"per_stratum_disagreement_counts.{stratum} cannot exceed required_stratum_counts.{stratum}"
            )

    semantic_failures = _require_int(report["semantic_validation_failure_count"], "semantic_validation_failure_count")
    reviewer_collisions = _require_int(
        report["reviewer_reference_collision_count"], "reviewer_reference_collision_count"
    )
    evidence_failures = _require_int(report["evidence_binding_failure_count"], "evidence_binding_failure_count")
    blinding_exceptions = _require_int(report["blinding_exception_count"], "blinding_exception_count", maximum=60)
    blinding_with_rationale = _require_int(
        report["blinding_exception_with_rationale_count"],
        "blinding_exception_with_rationale_count",
        maximum=60,
    )
    pilot_held_out_eligible = _require_int(
        report["pilot_items_held_out_eligible_count"], "pilot_items_held_out_eligible_count", maximum=60
    )

    _require_sha256(report["pilot_membership_commitment"], "pilot_membership_commitment")
    _require_sha256(report["reviewer_training_record_sha256"], "reviewer_training_record_sha256")
    _require_sha256(report["exposure_register_sha256"], "exposure_register_sha256")
    _require_sha256(report["pilot_disjointness_proof_sha256"], "pilot_disjointness_proof_sha256")
    _validate_authority(report["authority"])

    violations: list[str] = []
    if agreement < 48:
        violations.append("PRIMARY_SECONDARY_EXACT_AGREEMENT_BELOW_48_OF_60")
    if unresolved > 3:
        violations.append("UNRESOLVED_DISAGREEMENT_ABOVE_3_OF_60")
    for disposition in ("INCLUDE", "EXCLUDE", "BORDERLINE"):
        if dispositions[disposition] < 10:
            violations.append(f"RESOLVED_{disposition}_BELOW_10")
    for stratum in REQUIRED_STRATA:
        if stratum_counts[stratum] < 6:
            violations.append(f"STRATUM_{stratum}_BELOW_6")
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
        "state": READY_STATE if quantitative_gate_passed else NOT_READY_STATE,
        "quantitative_gate_passed": quantitative_gate_passed,
        "agreement_count": agreement,
        "agreement_rate": agreement / 60,
        "unresolved_disagreement_count": unresolved,
        "unresolved_disagreement_rate": unresolved / 60,
        "resolved_disposition_counts": dispositions,
        "required_stratum_counts": stratum_counts,
        "violations": violations,
        "human_calibration_disposition_required": True,
        "authority": {
            "reviewer_competence_established": False,
            "benchmark_adequacy_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the PRE-G2 D4 60-item pilot readiness gate under the approved v0.2 agreement policy")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise D4PilotReadinessError("report root must be an object")
        result = evaluate_pilot_readiness(payload)
    except (OSError, json.JSONDecodeError, D4PilotReadinessError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0 if result["quantitative_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

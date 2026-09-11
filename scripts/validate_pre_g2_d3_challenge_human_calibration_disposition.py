from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PATENT_V0_1"
PROTOCOL_ID = "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1"
APPROVAL_SCOPE = "FINAL_CHALLENGE_CANDIDATE_POOL_SELECTION_ONLY"
GOVERNANCE_ROLE = "D3_HUMAN_CALIBRATION_AUTHORITY"
READY_STATE = "READY_FOR_HUMAN_CALIBRATION_DISPOSITION"
DECISIONS = {"APPROVE", "REVISE", "REJECT"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_KEYS = {
    "schema_version",
    "disposition_id",
    "benchmark_id",
    "protocol_id",
    "pilot_round_id",
    "pilot_membership_commitment",
    "pilot_manifest_sha256",
    "pilot_readiness_aggregate_sha256",
    "pilot_readiness_result_sha256",
    "reviewer_training_record_sha256",
    "exposure_register_sha256",
    "prior_exposure_disjointness_audit_sha256",
    "quantitative_gate_passed",
    "decision",
    "approval_scope",
    "governance_ref",
    "governance_role",
    "rationale",
    "decided_at",
    "authority",
}
AUTHORITY_KEYS = {
    "reviewer_competence_established",
    "benchmark_adequacy_established",
    "g0_passed",
    "g2_passed",
    "g5_passed",
    "rights_clearance",
    "population_generalization_authority",
    "canonical_s2_authority",
    "publication_authority",
    "phase4_online_first_default_authorized",
    "assessment_effect",
}


class D3CalibrationDispositionError(ValueError):
    """Raised when a human calibration disposition is invalid or misbound."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise D3CalibrationDispositionError(
            "calibration material must be finite JSON-compatible data"
        ) from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def calibration_disposition_sha256(disposition: dict[str, Any]) -> str:
    return canonical_sha256(disposition)


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D3CalibrationDispositionError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D3CalibrationDispositionError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D3CalibrationDispositionError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D3CalibrationDispositionError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return value


def _require_aware_timestamp(value: Any, field: str) -> datetime:
    text = _require_string(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise D3CalibrationDispositionError(
            f"{field} must be an ISO-8601 date-time"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise D3CalibrationDispositionError(
            f"{field} must include an explicit timezone"
        )
    return parsed


def _validate_authority(value: Any) -> None:
    authority = _require_mapping(value, "authority")
    _require_exact_keys(authority, AUTHORITY_KEYS, "authority")
    for field in (
        "reviewer_competence_established",
        "benchmark_adequacy_established",
        "g0_passed",
        "g2_passed",
        "g5_passed",
        "rights_clearance",
        "population_generalization_authority",
        "canonical_s2_authority",
        "publication_authority",
        "phase4_online_first_default_authorized",
    ):
        if authority[field] is not False:
            raise D3CalibrationDispositionError(
                f"authority.{field} must remain false"
            )
    if authority["assessment_effect"] != "NONE":
        raise D3CalibrationDispositionError(
            "authority.assessment_effect must remain NONE"
        )


def validate_calibration_disposition(
    disposition: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    readiness_aggregate: dict[str, Any],
    readiness_result: dict[str, Any],
) -> None:
    """Validate one human disposition against exact derived pilot evidence.

    This validates identity, digest and authority boundaries. It does not establish
    that the human governance reference is competent or that the rationale is
    scientifically correct.
    """

    _require_exact_keys(disposition, EXPECTED_KEYS, "calibration_disposition")
    if disposition["schema_version"] != "0.1":
        raise D3CalibrationDispositionError("schema_version must be 0.1")
    _require_string(disposition["disposition_id"], "disposition_id")
    if disposition["benchmark_id"] != BENCHMARK_ID:
        raise D3CalibrationDispositionError(
            f"benchmark_id must be {BENCHMARK_ID}"
        )
    if disposition["protocol_id"] != PROTOCOL_ID:
        raise D3CalibrationDispositionError(
            f"protocol_id must be {PROTOCOL_ID}"
        )
    if disposition["approval_scope"] != APPROVAL_SCOPE:
        raise D3CalibrationDispositionError(
            f"approval_scope must be {APPROVAL_SCOPE}"
        )
    if disposition["governance_role"] != GOVERNANCE_ROLE:
        raise D3CalibrationDispositionError(
            f"governance_role must be {GOVERNANCE_ROLE}"
        )
    _require_string(disposition["governance_ref"], "governance_ref")
    _require_string(disposition["rationale"], "rationale")
    _require_aware_timestamp(disposition["decided_at"], "decided_at")
    if disposition["decision"] not in DECISIONS:
        raise D3CalibrationDispositionError("decision is unsupported")
    if disposition["quantitative_gate_passed"] is not True:
        raise D3CalibrationDispositionError(
            "quantitative_gate_passed must be true"
        )
    _validate_authority(disposition["authority"])

    if pilot_manifest.get("benchmark_id") != BENCHMARK_ID:
        raise D3CalibrationDispositionError(
            "pilot manifest benchmark_id mismatch"
        )
    if pilot_manifest.get("protocol_id") != PROTOCOL_ID:
        raise D3CalibrationDispositionError(
            "pilot manifest protocol_id mismatch"
        )
    pilot_round_id = _require_string(
        pilot_manifest.get("pilot_round_id"),
        "pilot_manifest.pilot_round_id",
    )
    pilot_membership = _require_sha256(
        pilot_manifest.get("pilot_membership_commitment"),
        "pilot_manifest.pilot_membership_commitment",
    )
    for field in (
        "reviewer_training_record_sha256",
        "exposure_register_sha256",
        "prior_exposure_disjointness_audit_sha256",
    ):
        _require_sha256(
            pilot_manifest.get(field),
            f"pilot_manifest.{field}",
        )

    if disposition["pilot_round_id"] != pilot_round_id:
        raise D3CalibrationDispositionError(
            "disposition pilot_round_id does not bind the supplied pilot manifest"
        )
    if disposition["pilot_membership_commitment"] != pilot_membership:
        raise D3CalibrationDispositionError(
            "disposition pilot membership commitment mismatch"
        )
    for field in (
        "reviewer_training_record_sha256",
        "exposure_register_sha256",
        "prior_exposure_disjointness_audit_sha256",
    ):
        if disposition[field] != pilot_manifest[field]:
            raise D3CalibrationDispositionError(
                f"disposition {field} does not bind the supplied pilot manifest"
            )

    expected_digests = {
        "pilot_manifest_sha256": canonical_sha256(pilot_manifest),
        "pilot_readiness_aggregate_sha256": canonical_sha256(
            readiness_aggregate
        ),
        "pilot_readiness_result_sha256": canonical_sha256(readiness_result),
    }
    for field, expected in expected_digests.items():
        _require_sha256(disposition[field], field)
        if disposition[field] != expected:
            raise D3CalibrationDispositionError(
                f"{field} does not bind the exact supplied pilot/readiness evidence"
            )

    if readiness_aggregate.get("benchmark_id") != BENCHMARK_ID:
        raise D3CalibrationDispositionError(
            "readiness aggregate benchmark_id mismatch"
        )
    if readiness_aggregate.get("protocol_id") != PROTOCOL_ID:
        raise D3CalibrationDispositionError(
            "readiness aggregate protocol_id mismatch"
        )
    if readiness_aggregate.get("pilot_round_id") != pilot_round_id:
        raise D3CalibrationDispositionError(
            "readiness aggregate pilot_round_id mismatch"
        )
    if readiness_aggregate.get("pilot_membership_commitment") != pilot_membership:
        raise D3CalibrationDispositionError(
            "readiness aggregate pilot membership mismatch"
        )

    if readiness_result.get("pilot_round_id") != pilot_round_id:
        raise D3CalibrationDispositionError(
            "readiness result pilot_round_id mismatch"
        )
    if readiness_result.get("state") != READY_STATE:
        raise D3CalibrationDispositionError(
            "readiness result is not ready for human calibration disposition"
        )
    if readiness_result.get("quantitative_gate_passed") is not True:
        raise D3CalibrationDispositionError(
            "readiness result quantitative gate did not pass"
        )
    if readiness_result.get("human_calibration_disposition_required") is not True:
        raise D3CalibrationDispositionError(
            "readiness result must preserve the human calibration requirement"
        )
    if readiness_result.get("population_generalizable") is not False:
        raise D3CalibrationDispositionError(
            "readiness result cannot claim population generalizability"
        )


def require_approved_calibration_disposition(
    disposition: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    readiness_aggregate: dict[str, Any],
    readiness_result: dict[str, Any],
) -> str:
    validate_calibration_disposition(
        disposition,
        pilot_manifest=pilot_manifest,
        readiness_aggregate=readiness_aggregate,
        readiness_result=readiness_result,
    )
    if disposition["decision"] != "APPROVE":
        raise D3CalibrationDispositionError(
            "human calibration disposition does not approve final challenge candidate-pool selection"
        )
    return calibration_disposition_sha256(disposition)


def _load_object(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise D3CalibrationDispositionError(f"{field} root must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one PRE-G2 D3 human calibration disposition against exact pilot/readiness evidence"
    )
    parser.add_argument("disposition", type=Path)
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("readiness_aggregate", type=Path)
    parser.add_argument("readiness_result", type=Path)
    parser.add_argument(
        "--require-approve",
        action="store_true",
        help="Fail unless the structurally valid human disposition is APPROVE.",
    )
    args = parser.parse_args()
    try:
        disposition = _load_object(args.disposition, "disposition")
        manifest = _load_object(args.pilot_manifest, "pilot_manifest")
        aggregate = _load_object(
            args.readiness_aggregate,
            "readiness_aggregate",
        )
        result = _load_object(args.readiness_result, "readiness_result")
        validate_calibration_disposition(
            disposition,
            pilot_manifest=manifest,
            readiness_aggregate=aggregate,
            readiness_result=result,
        )
        if args.require_approve and disposition["decision"] != "APPROVE":
            raise D3CalibrationDispositionError(
                "approval is required for this execution path"
            )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D3CalibrationDispositionError,
    ):
        print(
            "INVALID: controlled D3 human calibration disposition validation failed"
        )
        return 1
    print(
        "VALID: D3 human calibration disposition is exactly bound; broader authority remains unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PRODUCT_V0_1"
SAMPLING_PROTOCOL_ID = "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1"
PILOT_EXECUTION_PROTOCOL_ID = "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1"
APPROVAL_SCOPE = "FINAL_D4_CHALLENGE_SELECTION_ONLY"
GOVERNANCE_ROLE = "D4_HUMAN_CALIBRATION_AUTHORITY"
ENVELOPE_STATE = "CONTROLLED_COMPOSITION_BINDING_RECORDED"
READY_STATE = "READY_FOR_HUMAN_CALIBRATION_DISPOSITION"
DECISIONS = {"APPROVE", "REVISE", "REJECT"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

DISPOSITION_KEYS = {
    "schema_version",
    "disposition_id",
    "benchmark_id",
    "sampling_protocol_id",
    "pilot_execution_protocol_id",
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
DISPOSITION_AUTHORITY_KEYS = {
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
ENVELOPE_KEYS = {
    "schema_version",
    "envelope_id",
    "benchmark_id",
    "sampling_protocol_id",
    "pilot_execution_protocol_id",
    "scope",
    "state",
    "pilot_round_id",
    "pilot_membership_commitment",
    "human_calibration_disposition_sha256",
    "candidate_pool_id",
    "candidate_pool_commitment",
    "identity_namespace_attestation_sha256",
    "bound_at",
    "control_ref",
    "authority",
}
ENVELOPE_AUTHORITY_KEYS = {
    "human_identity_established",
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


class D4CalibrationAuthorizationError(ValueError):
    """Raised when D4 calibration/selection authorization material is invalid."""


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
        raise D4CalibrationAuthorizationError(
            "authorization material must be finite JSON-compatible data"
        ) from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D4CalibrationAuthorizationError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D4CalibrationAuthorizationError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D4CalibrationAuthorizationError(
            f"{field} must be a non-empty string"
        )
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D4CalibrationAuthorizationError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _require_aware_timestamp(value: Any, field: str) -> datetime:
    text = _require_string(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise D4CalibrationAuthorizationError(
            f"{field} must be an ISO-8601 date-time"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise D4CalibrationAuthorizationError(
            f"{field} must include an explicit timezone"
        )
    return parsed


def _validate_disposition_authority(value: Any) -> None:
    authority = _require_mapping(value, "disposition.authority")
    _require_exact_keys(
        authority,
        DISPOSITION_AUTHORITY_KEYS,
        "disposition.authority",
    )
    for field in DISPOSITION_AUTHORITY_KEYS - {"assessment_effect"}:
        if authority[field] is not False:
            raise D4CalibrationAuthorizationError(
                f"disposition.authority.{field} must remain false"
            )
    if authority["assessment_effect"] != "NONE":
        raise D4CalibrationAuthorizationError(
            "disposition.authority.assessment_effect must remain NONE"
        )


def _validate_envelope_authority(value: Any) -> None:
    authority = _require_mapping(value, "authorization_envelope.authority")
    _require_exact_keys(
        authority,
        ENVELOPE_AUTHORITY_KEYS,
        "authorization_envelope.authority",
    )
    for field in ENVELOPE_AUTHORITY_KEYS - {"assessment_effect"}:
        if authority[field] is not False:
            raise D4CalibrationAuthorizationError(
                f"authorization_envelope.authority.{field} must remain false"
            )
    if authority["assessment_effect"] != "NONE":
        raise D4CalibrationAuthorizationError(
            "authorization_envelope.authority.assessment_effect must remain NONE"
        )


def validate_human_calibration_disposition(
    disposition: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    readiness_aggregate: dict[str, Any],
    readiness_result: dict[str, Any],
) -> None:
    """Bind one human calibration disposition to exact derived pilot evidence.

    This establishes only declared local object consistency. It does not establish
    reviewer competence, governance identity, scientific truth, benchmark adequacy
    or any broader programme authority.
    """

    _require_exact_keys(disposition, DISPOSITION_KEYS, "disposition")
    if disposition["schema_version"] != "0.1":
        raise D4CalibrationAuthorizationError(
            "disposition.schema_version must be 0.1"
        )
    _require_string(disposition["disposition_id"], "disposition.disposition_id")
    if disposition["benchmark_id"] != BENCHMARK_ID:
        raise D4CalibrationAuthorizationError(
            f"disposition.benchmark_id must be {BENCHMARK_ID}"
        )
    if disposition["sampling_protocol_id"] != SAMPLING_PROTOCOL_ID:
        raise D4CalibrationAuthorizationError(
            f"disposition.sampling_protocol_id must be {SAMPLING_PROTOCOL_ID}"
        )
    if disposition["pilot_execution_protocol_id"] != PILOT_EXECUTION_PROTOCOL_ID:
        raise D4CalibrationAuthorizationError(
            "disposition.pilot_execution_protocol_id mismatch"
        )
    if disposition["approval_scope"] != APPROVAL_SCOPE:
        raise D4CalibrationAuthorizationError(
            f"disposition.approval_scope must be {APPROVAL_SCOPE}"
        )
    if disposition["governance_role"] != GOVERNANCE_ROLE:
        raise D4CalibrationAuthorizationError(
            f"disposition.governance_role must be {GOVERNANCE_ROLE}"
        )
    _require_string(disposition["governance_ref"], "disposition.governance_ref")
    _require_string(disposition["rationale"], "disposition.rationale")
    _require_aware_timestamp(disposition["decided_at"], "disposition.decided_at")
    if disposition["decision"] not in DECISIONS:
        raise D4CalibrationAuthorizationError(
            "disposition.decision is unsupported"
        )
    if disposition["quantitative_gate_passed"] is not True:
        raise D4CalibrationAuthorizationError(
            "disposition.quantitative_gate_passed must be true"
        )
    _validate_disposition_authority(disposition["authority"])

    if pilot_manifest.get("benchmark_id") != BENCHMARK_ID:
        raise D4CalibrationAuthorizationError(
            "pilot manifest benchmark_id mismatch"
        )
    if pilot_manifest.get("sampling_protocol_id") != SAMPLING_PROTOCOL_ID:
        raise D4CalibrationAuthorizationError(
            "pilot manifest sampling_protocol_id mismatch"
        )
    if (
        pilot_manifest.get("execution_protocol_id")
        != PILOT_EXECUTION_PROTOCOL_ID
    ):
        raise D4CalibrationAuthorizationError(
            "pilot manifest execution_protocol_id mismatch"
        )

    pilot_round_id = _require_string(
        pilot_manifest.get("pilot_round_id"),
        "pilot_manifest.pilot_round_id",
    )
    pilot_membership = _require_sha256(
        pilot_manifest.get("pilot_membership_commitment"),
        "pilot_manifest.pilot_membership_commitment",
    )
    if disposition["pilot_round_id"] != pilot_round_id:
        raise D4CalibrationAuthorizationError(
            "disposition pilot_round_id does not bind supplied manifest"
        )
    if disposition["pilot_membership_commitment"] != pilot_membership:
        raise D4CalibrationAuthorizationError(
            "disposition pilot membership commitment mismatch"
        )

    manifest_digest_fields = (
        "reviewer_training_record_sha256",
        "exposure_register_sha256",
        "prior_exposure_disjointness_audit_sha256",
    )
    for field in manifest_digest_fields:
        value = _require_sha256(
            pilot_manifest.get(field),
            f"pilot_manifest.{field}",
        )
        if disposition[field] != value:
            raise D4CalibrationAuthorizationError(
                f"disposition.{field} does not bind supplied manifest"
            )

    expected_digests = {
        "pilot_manifest_sha256": canonical_sha256(pilot_manifest),
        "pilot_readiness_aggregate_sha256": canonical_sha256(
            readiness_aggregate
        ),
        "pilot_readiness_result_sha256": canonical_sha256(
            readiness_result
        ),
    }
    for field, expected in expected_digests.items():
        _require_sha256(disposition[field], f"disposition.{field}")
        if disposition[field] != expected:
            raise D4CalibrationAuthorizationError(
                f"disposition.{field} does not bind exact supplied evidence"
            )

    if readiness_aggregate.get("benchmark_id") != BENCHMARK_ID:
        raise D4CalibrationAuthorizationError(
            "readiness aggregate benchmark_id mismatch"
        )
    if readiness_aggregate.get("protocol_id") != SAMPLING_PROTOCOL_ID:
        raise D4CalibrationAuthorizationError(
            "readiness aggregate protocol_id mismatch"
        )
    if readiness_aggregate.get("pilot_round_id") != pilot_round_id:
        raise D4CalibrationAuthorizationError(
            "readiness aggregate pilot_round_id mismatch"
        )
    if (
        readiness_aggregate.get("pilot_membership_commitment")
        != pilot_membership
    ):
        raise D4CalibrationAuthorizationError(
            "readiness aggregate pilot membership mismatch"
        )

    if readiness_result.get("pilot_round_id") != pilot_round_id:
        raise D4CalibrationAuthorizationError(
            "readiness result pilot_round_id mismatch"
        )
    if readiness_result.get("state") != READY_STATE:
        raise D4CalibrationAuthorizationError(
            "readiness result is not ready for human calibration disposition"
        )
    if readiness_result.get("quantitative_gate_passed") is not True:
        raise D4CalibrationAuthorizationError(
            "readiness result quantitative gate did not pass"
        )
    if (
        readiness_result.get("human_calibration_disposition_required")
        is not True
    ):
        raise D4CalibrationAuthorizationError(
            "readiness result must preserve human calibration requirement"
        )


def require_approved_human_calibration_disposition(
    disposition: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    readiness_aggregate: dict[str, Any],
    readiness_result: dict[str, Any],
) -> str:
    validate_human_calibration_disposition(
        disposition,
        pilot_manifest=pilot_manifest,
        readiness_aggregate=readiness_aggregate,
        readiness_result=readiness_result,
    )
    if disposition["decision"] != "APPROVE":
        raise D4CalibrationAuthorizationError(
            "human calibration disposition does not approve final D4 challenge selection"
        )
    return canonical_sha256(disposition)


def validate_selection_authorization_envelope(
    envelope: dict[str, Any],
    *,
    approved_disposition_sha256: str,
    pilot_manifest: dict[str, Any],
    candidate_pool: dict[str, Any],
    identity_namespace_attestation: dict[str, Any],
) -> str:
    """Validate the append-only composition binding for final D4 selection."""

    _require_exact_keys(envelope, ENVELOPE_KEYS, "authorization_envelope")
    if envelope["schema_version"] != "0.1":
        raise D4CalibrationAuthorizationError(
            "authorization_envelope.schema_version must be 0.1"
        )
    _require_string(envelope["envelope_id"], "authorization_envelope.envelope_id")
    if envelope["benchmark_id"] != BENCHMARK_ID:
        raise D4CalibrationAuthorizationError(
            f"authorization_envelope.benchmark_id must be {BENCHMARK_ID}"
        )
    if envelope["sampling_protocol_id"] != SAMPLING_PROTOCOL_ID:
        raise D4CalibrationAuthorizationError(
            "authorization_envelope.sampling_protocol_id mismatch"
        )
    if (
        envelope["pilot_execution_protocol_id"]
        != PILOT_EXECUTION_PROTOCOL_ID
    ):
        raise D4CalibrationAuthorizationError(
            "authorization_envelope.pilot_execution_protocol_id mismatch"
        )
    if envelope["scope"] != APPROVAL_SCOPE:
        raise D4CalibrationAuthorizationError(
            f"authorization_envelope.scope must be {APPROVAL_SCOPE}"
        )
    if envelope["state"] != ENVELOPE_STATE:
        raise D4CalibrationAuthorizationError(
            f"authorization_envelope.state must be {ENVELOPE_STATE}"
        )
    _require_aware_timestamp(
        envelope["bound_at"],
        "authorization_envelope.bound_at",
    )
    _require_string(
        envelope["control_ref"],
        "authorization_envelope.control_ref",
    )
    _validate_envelope_authority(envelope["authority"])

    _require_sha256(
        approved_disposition_sha256,
        "approved_disposition_sha256",
    )
    if (
        envelope["human_calibration_disposition_sha256"]
        != approved_disposition_sha256
    ):
        raise D4CalibrationAuthorizationError(
            "authorization envelope does not bind exact approved disposition"
        )

    pilot_round_id = _require_string(
        pilot_manifest.get("pilot_round_id"),
        "pilot_manifest.pilot_round_id",
    )
    pilot_membership = _require_sha256(
        pilot_manifest.get("pilot_membership_commitment"),
        "pilot_manifest.pilot_membership_commitment",
    )
    if envelope["pilot_round_id"] != pilot_round_id:
        raise D4CalibrationAuthorizationError(
            "authorization envelope pilot_round_id mismatch"
        )
    if envelope["pilot_membership_commitment"] != pilot_membership:
        raise D4CalibrationAuthorizationError(
            "authorization envelope pilot membership mismatch"
        )

    candidate_pool_id = _require_string(
        candidate_pool.get("candidate_pool_id"),
        "candidate_pool.candidate_pool_id",
    )
    candidate_pool_commitment = _require_sha256(
        candidate_pool.get("candidate_pool_commitment"),
        "candidate_pool.candidate_pool_commitment",
    )
    if envelope["candidate_pool_id"] != candidate_pool_id:
        raise D4CalibrationAuthorizationError(
            "authorization envelope candidate_pool_id mismatch"
        )
    if envelope["candidate_pool_commitment"] != candidate_pool_commitment:
        raise D4CalibrationAuthorizationError(
            "authorization envelope candidate_pool_commitment mismatch"
        )

    attestation_sha256 = canonical_sha256(identity_namespace_attestation)
    if (
        envelope["identity_namespace_attestation_sha256"]
        != attestation_sha256
    ):
        raise D4CalibrationAuthorizationError(
            "authorization envelope identity namespace attestation digest mismatch"
        )
    return canonical_sha256(envelope)


def _load_object(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise D4CalibrationAuthorizationError(
            f"{field} root must be an object"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PRE-G2 D4 human calibration and final-selection authorization bindings"
    )
    parser.add_argument("disposition", type=Path)
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("readiness_aggregate", type=Path)
    parser.add_argument("readiness_result", type=Path)
    parser.add_argument("--authorization-envelope", type=Path)
    parser.add_argument("--candidate-pool", type=Path)
    parser.add_argument("--identity-namespace-attestation", type=Path)
    parser.add_argument("--require-approve", action="store_true")
    args = parser.parse_args()

    try:
        disposition = _load_object(args.disposition, "disposition")
        manifest = _load_object(args.pilot_manifest, "pilot_manifest")
        aggregate = _load_object(
            args.readiness_aggregate,
            "readiness_aggregate",
        )
        result = _load_object(args.readiness_result, "readiness_result")
        validate_human_calibration_disposition(
            disposition,
            pilot_manifest=manifest,
            readiness_aggregate=aggregate,
            readiness_result=result,
        )
        disposition_sha = canonical_sha256(disposition)
        if args.require_approve and disposition["decision"] != "APPROVE":
            raise D4CalibrationAuthorizationError(
                "approval is required for this execution path"
            )

        envelope_args = (
            args.authorization_envelope,
            args.candidate_pool,
            args.identity_namespace_attestation,
        )
        if any(value is not None for value in envelope_args):
            if any(value is None for value in envelope_args):
                raise D4CalibrationAuthorizationError(
                    "authorization-envelope validation requires envelope, candidate pool and namespace attestation together"
                )
            envelope = _load_object(
                args.authorization_envelope,
                "authorization_envelope",
            )
            pool = _load_object(args.candidate_pool, "candidate_pool")
            attestation = _load_object(
                args.identity_namespace_attestation,
                "identity_namespace_attestation",
            )
            validate_selection_authorization_envelope(
                envelope,
                approved_disposition_sha256=disposition_sha,
                pilot_manifest=manifest,
                candidate_pool=pool,
                identity_namespace_attestation=attestation,
            )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D4CalibrationAuthorizationError,
    ):
        print(
            "INVALID: controlled D4 calibration/selection authorization validation failed"
        )
        return 1

    print(
        "VALID: exact D4 calibration/selection bindings verified; broader authority remains unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

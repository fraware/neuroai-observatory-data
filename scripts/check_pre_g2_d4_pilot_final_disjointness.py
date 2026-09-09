from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    BENCHMARK_ID,
    EXECUTION_PROTOCOL_ID,
    D4PilotExecutionError,
    load_validated_pilot_packets,
)
from scripts.select_pre_g2_d4_held_out import D4SelectionError, _validate_pool

NAMESPACE_ID = "D4_CONTROLLED_ITEM_ID_V1"
ATTESTATION_STATE = "HUMAN_CONTROLLED_NAMESPACE_BINDING_RECORDED"
AUDIT_DOMAIN = "PRE_G2_D4_PILOT_FINAL_DISJOINTNESS_AUDIT_V1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ATTESTATION_KEYS = {
    "schema_version",
    "namespace_id",
    "state",
    "pilot_round_id",
    "pilot_membership_commitment",
    "candidate_pool_id",
    "candidate_pool_commitment",
    "human_identity_resolution_provenance_sha256",
    "authority",
}
ATTESTATION_AUTHORITY_KEYS = {
    "identity_resolution_truth_established",
    "g2_passed",
    "canonical_s2_authority",
    "publication_authority",
    "assessment_effect",
}


class D4DisjointnessError(ValueError):
    """Raised when the controlled pilot/final-pool disjointness audit is invalid."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_domain(domain: str, value: Any) -> str:
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\0")
    h.update(_canonical_bytes(value))
    return h.hexdigest()


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D4DisjointnessError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D4DisjointnessError(f"{field} keys mismatch; missing={missing}, extra={extra}")


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D4DisjointnessError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _validate_attestation(
    attestation: dict[str, Any],
    manifest: dict[str, Any],
    candidate_pool: dict[str, Any],
) -> None:
    _require_exact_keys(attestation, ATTESTATION_KEYS, "identity_namespace_attestation")
    if attestation["schema_version"] != "0.1":
        raise D4DisjointnessError("identity namespace attestation schema_version must be 0.1")
    if attestation["namespace_id"] != NAMESPACE_ID:
        raise D4DisjointnessError(f"identity namespace attestation namespace_id must be {NAMESPACE_ID}")
    if attestation["state"] != ATTESTATION_STATE:
        raise D4DisjointnessError(f"identity namespace attestation state must be {ATTESTATION_STATE}")
    if attestation["pilot_round_id"] != manifest.get("pilot_round_id"):
        raise D4DisjointnessError("identity namespace attestation pilot_round_id does not match pilot manifest")
    if attestation["pilot_membership_commitment"] != manifest.get("pilot_membership_commitment"):
        raise D4DisjointnessError(
            "identity namespace attestation pilot membership commitment does not match pilot manifest"
        )
    if attestation["candidate_pool_id"] != candidate_pool.get("candidate_pool_id"):
        raise D4DisjointnessError("identity namespace attestation candidate_pool_id does not match candidate pool")
    if attestation["candidate_pool_commitment"] != candidate_pool.get("candidate_pool_commitment"):
        raise D4DisjointnessError(
            "identity namespace attestation candidate-pool commitment does not match candidate pool"
        )
    _require_sha256(
        attestation["human_identity_resolution_provenance_sha256"],
        "identity_namespace_attestation.human_identity_resolution_provenance_sha256",
    )

    authority = _require_mapping(attestation["authority"], "identity_namespace_attestation.authority")
    _require_exact_keys(authority, ATTESTATION_AUTHORITY_KEYS, "identity_namespace_attestation.authority")
    for field in (
        "identity_resolution_truth_established",
        "g2_passed",
        "canonical_s2_authority",
        "publication_authority",
    ):
        if authority[field] is not False:
            raise D4DisjointnessError(f"identity_namespace_attestation.authority.{field} must remain false")
    if authority["assessment_effect"] != "NONE":
        raise D4DisjointnessError("identity_namespace_attestation.authority.assessment_effect must remain NONE")


def compute_disjointness_audit(
    manifest: dict[str, Any],
    packet_root: Path,
    pilot_commitment_key: bytes,
    candidate_pool: dict[str, Any],
    candidate_pool_commitment_key: bytes,
    identity_namespace_attestation: dict[str, Any],
    identity_namespace_attestation_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare exact controlled IDs under an explicit shared-namespace attestation.

    This establishes exact string-ID overlap for the validated controlled inputs.
    It does not establish that human entity/alias resolution underlying the shared
    identifier namespace is scientifically or factually correct.
    """

    _require_sha256(identity_namespace_attestation_sha256, "identity_namespace_attestation_sha256")
    try:
        _, pilot_item_ids = load_validated_pilot_packets(manifest, packet_root, pilot_commitment_key)
    except D4PilotExecutionError as exc:
        raise D4DisjointnessError(f"pilot execution validation failed: {exc}") from exc

    try:
        validated_candidates = _validate_pool(candidate_pool, candidate_pool_commitment_key)
    except D4SelectionError as exc:
        raise D4DisjointnessError(f"candidate-pool validation failed: {exc}") from exc

    _validate_attestation(identity_namespace_attestation, manifest, candidate_pool)

    pilot_ids = set(pilot_item_ids)
    candidate_ids = {candidate["candidate_id"] for candidate in validated_candidates}
    overlap_ids = sorted(pilot_ids.intersection(candidate_ids))

    controlled_audit = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "execution_protocol_id": EXECUTION_PROTOCOL_ID,
        "comparison_semantics": "SHARED_CONTROLLED_ITEM_ID_NAMESPACE_EXACT_EQUALITY",
        "namespace_id": NAMESPACE_ID,
        "identity_namespace_attestation_sha256": identity_namespace_attestation_sha256,
        "human_identity_resolution_provenance_sha256": identity_namespace_attestation[
            "human_identity_resolution_provenance_sha256"
        ],
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest["pilot_membership_commitment"],
        "candidate_pool_id": candidate_pool["candidate_pool_id"],
        "candidate_pool_commitment": candidate_pool["candidate_pool_commitment"],
        "pilot_item_count": len(pilot_ids),
        "candidate_pool_count": len(candidate_ids),
        "overlap_count": len(overlap_ids),
        "overlap_item_ids": overlap_ids,
        "pilot_membership_hmac_verified": True,
        "candidate_pool_hmac_verified": True,
        "identity_namespace_binding_verified": True,
        "identity_resolution_truth_established": False,
        "custody": "S3_CONTROLLED",
        "authority": {
            "final_selection_authorized": False,
            "benchmark_adequacy_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }
    audit_sha256 = _sha256_domain(AUDIT_DOMAIN, controlled_audit)
    public_summary = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "execution_protocol_id": EXECUTION_PROTOCOL_ID,
        "comparison_semantics": "SHARED_CONTROLLED_ITEM_ID_NAMESPACE_EXACT_EQUALITY",
        "namespace_id": NAMESPACE_ID,
        "identity_namespace_attestation_sha256": identity_namespace_attestation_sha256,
        "pilot_membership_commitment": manifest["pilot_membership_commitment"],
        "candidate_pool_commitment": candidate_pool["candidate_pool_commitment"],
        "pilot_item_count": len(pilot_ids),
        "candidate_pool_count": len(candidate_ids),
        "overlap_count": len(overlap_ids),
        "overlap_zero": len(overlap_ids) == 0,
        "controlled_audit_sha256": audit_sha256,
        "identity_namespace_binding_verified": True,
        "identity_resolution_truth_established": False,
        "public_zero_knowledge_proof": False,
        "independently_verifiable_without_s3_inputs": False,
        "authority": controlled_audit["authority"],
    }
    return controlled_audit, public_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check PRE-G2 D4 pilot/final candidate-pool disjointness under a controlled shared ID namespace"
    )
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("candidate_pool", type=Path)
    parser.add_argument("identity_namespace_attestation", type=Path)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--pilot-commitment-key-file", type=Path, required=True)
    parser.add_argument("--candidate-pool-commitment-key-file", type=Path, required=True)
    parser.add_argument(
        "--controlled-output",
        type=Path,
        default=None,
        help="Optional explicit S3 path for the controlled audit containing any overlapping IDs.",
    )
    args = parser.parse_args()

    try:
        manifest = json.loads(args.pilot_manifest.read_text(encoding="utf-8"))
        candidate_pool = json.loads(args.candidate_pool.read_text(encoding="utf-8"))
        attestation_raw = args.identity_namespace_attestation.read_bytes()
        attestation = json.loads(attestation_raw.decode("utf-8"))
        if not isinstance(manifest, dict) or not isinstance(candidate_pool, dict) or not isinstance(attestation, dict):
            raise D4DisjointnessError("manifest, candidate pool, and identity namespace attestation must be objects")
        pilot_key = args.pilot_commitment_key_file.read_bytes()
        candidate_key = args.candidate_pool_commitment_key_file.read_bytes()
        if not pilot_key or not candidate_key:
            raise D4DisjointnessError("commitment key files must not be empty")
        attestation_sha256 = hashlib.sha256(attestation_raw).hexdigest()
        controlled_audit, public_summary = compute_disjointness_audit(
            manifest,
            args.packet_root,
            pilot_key,
            candidate_pool,
            candidate_key,
            attestation,
            attestation_sha256,
        )
        if args.controlled_output is not None:
            args.controlled_output.write_text(
                json.dumps(controlled_audit, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, D4DisjointnessError) as exc:
        print(f"INVALID: {exc}")
        return 1

    if not public_summary["overlap_zero"]:
        print(
            "INVALID: pilot/final candidate overlap detected; "
            f"count={public_summary['overlap_count']}; "
            f"controlled_audit_sha256={public_summary['controlled_audit_sha256']}"
        )
        return 2

    print(json.dumps(public_summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

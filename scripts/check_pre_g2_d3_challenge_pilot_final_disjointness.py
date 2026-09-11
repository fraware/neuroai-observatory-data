from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.build_pre_g2_d3_challenge_pilot_readiness import (
    BENCHMARK_ID,
    D3ChallengePilotExecutionError,
    PROTOCOL_ID,
    load_validated_pilot_packets,
)
from scripts.select_pre_g2_d3_challenge_held_out import (
    D3ChallengeSelectionError,
    _validate_pool,
)

NAMESPACE_ID = "D3_DOCDB_SIMPLE_PATENT_FAMILY_ID_V1"
ATTESTATION_STATE = "HUMAN_CONTROLLED_NAMESPACE_BINDING_RECORDED"
AUDIT_DOMAIN = "PRE_G2_D3_CHALLENGE_PILOT_FINAL_DISJOINTNESS_AUDIT_V1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ATTESTATION_KEYS = {
    "schema_version",
    "namespace_id",
    "state",
    "pilot_round_id",
    "pilot_membership_commitment",
    "candidate_pool_id",
    "candidate_pool_commitment",
    "human_family_resolution_provenance_sha256",
    "authority",
}
ATTESTATION_AUTHORITY_KEYS = {
    "family_resolution_truth_established",
    "g2_passed",
    "canonical_s2_authority",
    "publication_authority",
    "assessment_effect",
}


class D3ChallengeDisjointnessError(ValueError):
    """Raised when a controlled D3 pilot/final-pool audit is invalid."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise D3ChallengeDisjointnessError(
            "controlled disjointness material must be finite JSON-compatible data"
        ) from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_domain(domain: str, value: Any) -> str:
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\0")
    h.update(_canonical_bytes(value))
    return h.hexdigest()


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D3ChallengeDisjointnessError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D3ChallengeDisjointnessError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D3ChallengeDisjointnessError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _validate_attestation(
    attestation: dict[str, Any],
    manifest: dict[str, Any],
    candidate_pool: dict[str, Any],
    supplied_sha256: str,
) -> str:
    _require_sha256(
        supplied_sha256,
        "identity_namespace_attestation_sha256",
    )
    actual_sha256 = _canonical_sha256(attestation)
    if actual_sha256 != supplied_sha256:
        raise D3ChallengeDisjointnessError(
            "identity namespace attestation digest does not bind the supplied canonical content"
        )
    _require_exact_keys(
        attestation,
        ATTESTATION_KEYS,
        "identity_namespace_attestation",
    )
    if attestation["schema_version"] != "0.1":
        raise D3ChallengeDisjointnessError(
            "identity namespace attestation schema_version must be 0.1"
        )
    if attestation["namespace_id"] != NAMESPACE_ID:
        raise D3ChallengeDisjointnessError(
            f"identity namespace attestation namespace_id must be {NAMESPACE_ID}"
        )
    if attestation["state"] != ATTESTATION_STATE:
        raise D3ChallengeDisjointnessError(
            f"identity namespace attestation state must be {ATTESTATION_STATE}"
        )
    if attestation["pilot_round_id"] != manifest.get("pilot_round_id"):
        raise D3ChallengeDisjointnessError(
            "identity namespace attestation pilot_round_id does not match pilot manifest"
        )
    if attestation["pilot_membership_commitment"] != manifest.get(
        "pilot_membership_commitment"
    ):
        raise D3ChallengeDisjointnessError(
            "identity namespace attestation pilot membership commitment mismatch"
        )
    if attestation["candidate_pool_id"] != candidate_pool.get(
        "candidate_pool_id"
    ):
        raise D3ChallengeDisjointnessError(
            "identity namespace attestation candidate_pool_id mismatch"
        )
    if attestation["candidate_pool_commitment"] != candidate_pool.get(
        "candidate_pool_commitment"
    ):
        raise D3ChallengeDisjointnessError(
            "identity namespace attestation candidate-pool commitment mismatch"
        )
    _require_sha256(
        attestation["human_family_resolution_provenance_sha256"],
        "identity_namespace_attestation.human_family_resolution_provenance_sha256",
    )

    authority = _require_mapping(
        attestation["authority"],
        "identity_namespace_attestation.authority",
    )
    _require_exact_keys(
        authority,
        ATTESTATION_AUTHORITY_KEYS,
        "identity_namespace_attestation.authority",
    )
    for field in (
        "family_resolution_truth_established",
        "g2_passed",
        "canonical_s2_authority",
        "publication_authority",
    ):
        if authority[field] is not False:
            raise D3ChallengeDisjointnessError(
                f"identity_namespace_attestation.authority.{field} must remain false"
            )
    if authority["assessment_effect"] != "NONE":
        raise D3ChallengeDisjointnessError(
            "identity_namespace_attestation.authority.assessment_effect must remain NONE"
        )
    return actual_sha256


def compute_disjointness_audit(
    manifest: dict[str, Any],
    packet_root: Path,
    pilot_commitment_key: bytes,
    candidate_pool: dict[str, Any],
    candidate_pool_commitment_key: bytes,
    identity_namespace_attestation: dict[str, Any],
    identity_namespace_attestation_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        _, pilot_refs = load_validated_pilot_packets(
            manifest,
            packet_root,
            pilot_commitment_key,
        )
    except D3ChallengePilotExecutionError:
        raise D3ChallengeDisjointnessError(
            "pilot execution validation failed under the merged controlled contract"
        ) from None
    try:
        candidates = _validate_pool(
            candidate_pool,
            candidate_pool_commitment_key,
        )
    except D3ChallengeSelectionError:
        raise D3ChallengeDisjointnessError(
            "candidate-pool validation failed under the merged controlled contract"
        ) from None

    attestation_sha = _validate_attestation(
        identity_namespace_attestation,
        manifest,
        candidate_pool,
        identity_namespace_attestation_sha256,
    )
    pilot_set = set(pilot_refs)
    candidate_set = {
        candidate["candidate_id"]
        for candidate in candidates
    }
    overlap = sorted(pilot_set.intersection(candidate_set))

    authority = {
        "final_selection_authorized": False,
        "benchmark_adequacy_established": False,
        "g2_passed": False,
        "canonical_s2_authority": False,
        "publication_authority": False,
        "population_generalization_authority": False,
        "assessment_effect": "NONE",
    }
    controlled = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "comparison_semantics": "SHARED_CONTROLLED_DOCDB_FAMILY_NAMESPACE_EXACT_EQUALITY",
        "namespace_id": NAMESPACE_ID,
        "identity_namespace_attestation_sha256": attestation_sha,
        "human_family_resolution_provenance_sha256": identity_namespace_attestation[
            "human_family_resolution_provenance_sha256"
        ],
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "candidate_pool_id": candidate_pool[
            "candidate_pool_id"
        ],
        "candidate_pool_commitment": candidate_pool[
            "candidate_pool_commitment"
        ],
        "pilot_item_count": len(pilot_set),
        "candidate_pool_count": len(candidate_set),
        "overlap_count": len(overlap),
        "overlap_family_refs": overlap,
        "pilot_membership_hmac_verified": True,
        "candidate_pool_hmac_verified": True,
        "identity_namespace_binding_verified": True,
        "family_resolution_truth_established": False,
        "custody": "S3_CONTROLLED",
        "authority": authority,
    }
    controlled_sha = _sha256_domain(
        AUDIT_DOMAIN,
        controlled,
    )
    summary = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "comparison_semantics": "SHARED_CONTROLLED_DOCDB_FAMILY_NAMESPACE_EXACT_EQUALITY",
        "namespace_id": NAMESPACE_ID,
        "identity_namespace_attestation_sha256": attestation_sha,
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "candidate_pool_commitment": candidate_pool[
            "candidate_pool_commitment"
        ],
        "pilot_item_count": len(pilot_set),
        "candidate_pool_count": len(candidate_set),
        "overlap_count": len(overlap),
        "overlap_zero": len(overlap) == 0,
        "controlled_audit_sha256": controlled_sha,
        "identity_namespace_binding_verified": True,
        "family_resolution_truth_established": False,
        "public_zero_knowledge_proof": False,
        "independently_verifiable_without_s3_inputs": False,
        "authority": authority,
    }
    return controlled, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check PRE-G2 D3 challenge pilot/final candidate-pool disjointness"
    )
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("candidate_pool", type=Path)
    parser.add_argument(
        "identity_namespace_attestation",
        type=Path,
    )
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument(
        "--pilot-commitment-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-pool-commitment-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--controlled-output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    try:
        manifest = json.loads(
            args.pilot_manifest.read_text(encoding="utf-8")
        )
        pool = json.loads(
            args.candidate_pool.read_text(encoding="utf-8")
        )
        attestation = json.loads(
            args.identity_namespace_attestation.read_text(
                encoding="utf-8"
            )
        )
        if (
            not isinstance(manifest, dict)
            or not isinstance(pool, dict)
            or not isinstance(attestation, dict)
        ):
            raise D3ChallengeDisjointnessError(
                "manifest, candidate pool and attestation must be objects"
            )
        pilot_key = args.pilot_commitment_key_file.read_bytes()
        pool_key = args.candidate_pool_commitment_key_file.read_bytes()
        if not pilot_key or not pool_key:
            raise D3ChallengeDisjointnessError(
                "commitment key files must not be empty"
            )
        attestation_sha = _canonical_sha256(attestation)
        controlled, summary = compute_disjointness_audit(
            manifest,
            args.packet_root,
            pilot_key,
            pool,
            pool_key,
            attestation,
            attestation_sha,
        )
        if args.controlled_output is not None:
            args.controlled_output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            args.controlled_output.write_text(
                json.dumps(
                    controlled,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D3ChallengeDisjointnessError,
    ):
        print(
            "INVALID: controlled D3 pilot/final disjointness validation failed"
        )
        return 1

    if not summary["overlap_zero"]:
        print(
            "INVALID: controlled D3 pilot/final overlap detected; "
            f"count={summary['overlap_count']}; "
            f"controlled_audit_sha256={summary['controlled_audit_sha256']}"
        )
        return 2
    print(
        json.dumps(
            summary,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

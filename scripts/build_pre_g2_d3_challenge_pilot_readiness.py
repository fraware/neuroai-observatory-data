from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.evaluate_pre_g2_d3_challenge_pilot_readiness import (
    BENCHMARK_ID,
    COMMITMENT_SCHEME,
    DISPOSITIONS,
    PROTOCOL_ID,
    REQUIRED_STRATA,
    evaluate_pilot_readiness,
)
from scripts.validate_pre_g2_d3_patent_review_packet_semantics import (
    D3PatentReviewPacketSemanticError,
    validate_packet_semantics,
)

PILOT_N = 60
PILOT_MEMBERSHIP_DOMAIN = "PRE_G2_D3_CHALLENGE_PILOT_MEMBERSHIP_COMMITMENT_V1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_CONTROLLED_FAILURE = (
    "INVALID: controlled D3 challenge pilot execution failed under the S3 containment boundary"
)
PUBLIC_INTERNAL_FAILURE = (
    "INVALID: internal D3 challenge pilot execution failure contained under the S3 boundary"
)

MANIFEST_KEYS = {
    "schema_version",
    "benchmark_id",
    "protocol_id",
    "pilot_round_id",
    "state",
    "pilot_membership_commitment",
    "pilot_membership_commitment_scheme",
    "reviewer_training_record_sha256",
    "exposure_register_sha256",
    "prior_exposure_disjointness_audit_sha256",
    "packet_manifest",
}
PACKET_ENTRY_KEYS = {"controlled_packet_ref", "packet_sha256"}


class D3ChallengePilotExecutionError(ValueError):
    """Raised when a controlled pilot cannot safely produce a readiness aggregate."""


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
        raise D3ChallengePilotExecutionError(
            "controlled pilot material must be finite JSON-compatible data"
        ) from exc


def _hmac_domain(key: bytes, domain: str, value: Any) -> str:
    if not isinstance(key, bytes) or not key:
        raise D3ChallengePilotExecutionError(
            "pilot membership commitment key must be non-empty bytes"
        )
    payload = domain.encode("utf-8") + b"\0" + _canonical_bytes(value)
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def pilot_membership_commitment(family_refs: list[str], key: bytes) -> str:
    normalized = sorted(family_refs)
    if len(normalized) != PILOT_N or len(set(normalized)) != PILOT_N:
        raise D3ChallengePilotExecutionError(
            "pilot membership must contain exactly 60 unique controlled family references"
        )
    return _hmac_domain(
        key,
        PILOT_MEMBERSHIP_DOMAIN,
        normalized,
    )


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D3ChallengePilotExecutionError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D3ChallengePilotExecutionError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D3ChallengePilotExecutionError(
            f"{field} must be a non-empty string"
        )
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D3ChallengePilotExecutionError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _safe_packet_path(packet_root: Path, controlled_ref: str) -> Path:
    relative = Path(controlled_ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise D3ChallengePilotExecutionError(
            "controlled packet references must be relative and traversal-free"
        )
    root = packet_root.expanduser().resolve(strict=False)
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise D3ChallengePilotExecutionError(
            "controlled packet reference escapes packet_root"
        ) from exc
    return candidate


def _load_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    _require_exact_keys(manifest, MANIFEST_KEYS, "pilot_manifest")
    if manifest["schema_version"] != "0.1":
        raise D3ChallengePilotExecutionError("schema_version must be 0.1")
    if manifest["benchmark_id"] != BENCHMARK_ID:
        raise D3ChallengePilotExecutionError(
            f"benchmark_id must be {BENCHMARK_ID}"
        )
    if manifest["protocol_id"] != PROTOCOL_ID:
        raise D3ChallengePilotExecutionError(
            f"protocol_id must be {PROTOCOL_ID}"
        )
    _require_string(manifest["pilot_round_id"], "pilot_round_id")
    if manifest["state"] != "COMPLETE_ROUND_NO_EXTENSION":
        raise D3ChallengePilotExecutionError(
            "pilot state must be COMPLETE_ROUND_NO_EXTENSION"
        )
    if manifest["pilot_membership_commitment_scheme"] != COMMITMENT_SCHEME:
        raise D3ChallengePilotExecutionError(
            f"pilot_membership_commitment_scheme must be {COMMITMENT_SCHEME}"
        )
    _require_sha256(
        manifest["pilot_membership_commitment"],
        "pilot_membership_commitment",
    )
    for field in (
        "reviewer_training_record_sha256",
        "exposure_register_sha256",
        "prior_exposure_disjointness_audit_sha256",
    ):
        _require_sha256(manifest[field], field)

    raw_entries = manifest["packet_manifest"]
    if not isinstance(raw_entries, list) or len(raw_entries) != PILOT_N:
        raise D3ChallengePilotExecutionError(
            "packet_manifest must contain exactly 60 entries"
        )
    entries: list[dict[str, str]] = []
    seen_refs: set[str] = set()
    for index, raw in enumerate(raw_entries):
        entry = _require_mapping(raw, f"packet_manifest[{index}]")
        _require_exact_keys(
            entry,
            PACKET_ENTRY_KEYS,
            f"packet_manifest[{index}]",
        )
        ref = _require_string(
            entry["controlled_packet_ref"],
            f"packet_manifest[{index}].controlled_packet_ref",
        )
        if ref in seen_refs:
            raise D3ChallengePilotExecutionError(
                "controlled packet references must be unique"
            )
        seen_refs.add(ref)
        digest = _require_sha256(
            entry["packet_sha256"],
            f"packet_manifest[{index}].packet_sha256",
        )
        entries.append(
            {
                "controlled_packet_ref": ref,
                "packet_sha256": digest,
            }
        )
    return entries


def load_validated_pilot_packets(
    manifest: dict[str, Any],
    packet_root: Path,
    commitment_key: bytes,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries = _load_manifest(manifest)
    packets: list[dict[str, Any]] = []
    family_refs: list[str] = []
    seen_family_refs: set[str] = set()

    for entry in entries:
        path = _safe_packet_path(
            packet_root,
            entry["controlled_packet_ref"],
        )
        raw_bytes = path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        if not hmac.compare_digest(
            digest,
            entry["packet_sha256"],
        ):
            raise D3ChallengePilotExecutionError(
                "controlled review-packet digest mismatch"
            )
        try:
            packet = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise D3ChallengePilotExecutionError(
                "controlled review packet is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(packet, dict):
            raise D3ChallengePilotExecutionError(
                "controlled review packet root must be an object"
            )
        try:
            validate_packet_semantics(packet)
        except D3PatentReviewPacketSemanticError as exc:
            raise D3ChallengePilotExecutionError(
                "controlled review packet failed merged D3 semantic validation"
            ) from exc
        if packet["candidate_role"] != "PILOT_DEVELOPMENT":
            raise D3ChallengePilotExecutionError(
                "all pilot packets must have candidate_role=PILOT_DEVELOPMENT"
            )
        if packet["review_design"]["double_label_required"] is not True:
            raise D3ChallengePilotExecutionError(
                "all pilot packets must be independently double labeled"
            )
        if packet["exposure_control"]["held_out_eligible"] is not False:
            raise D3ChallengePilotExecutionError(
                "pilot packets cannot remain held-out eligible"
            )

        family_ref = _require_string(
            packet["exact_patent_binding"]["controlled_family_ref"],
            "exact_patent_binding.controlled_family_ref",
        )
        if family_ref in seen_family_refs:
            raise D3ChallengePilotExecutionError(
                "pilot controlled family references must be unique"
            )
        seen_family_refs.add(family_ref)
        family_refs.append(family_ref)
        packets.append(packet)

    recomputed = pilot_membership_commitment(
        family_refs,
        commitment_key,
    )
    if not hmac.compare_digest(
        recomputed,
        manifest["pilot_membership_commitment"],
    ):
        raise D3ChallengePilotExecutionError(
            "pilot membership commitment does not bind the exact validated 60-family membership"
        )
    return packets, family_refs


def derive_readiness_aggregate(
    manifest: dict[str, Any],
    packet_root: Path,
    commitment_key: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    packets, _ = load_validated_pilot_packets(
        manifest,
        packet_root,
        commitment_key,
    )

    agreement = 0
    adjudicated = 0
    unresolved = 0
    resolved_dispositions: Counter[str] = Counter()
    stratum_counts: Counter[str] = Counter()
    stratum_disagreements: Counter[str] = Counter()
    matrix: dict[str, Counter[str]] = {
        disposition: Counter()
        for disposition in DISPOSITIONS
    }
    blinding_exceptions = 0
    blinding_with_rationale = 0

    for packet in packets:
        by_role = {
            record["adjudicator_role"]: record
            for record in packet["reviewer_records"]
        }
        primary = by_role["PRIMARY_REVIEWER"]["decision"]
        secondary = by_role["SECONDARY_REVIEWER"]["decision"]
        matrix[primary][secondary] += 1
        disagreement = primary != secondary
        if not disagreement:
            agreement += 1
        state = packet["adjudication"]["state"]
        if state == "ADJUDICATED":
            adjudicated += 1
        elif state == "DISAGREE_UNADJUDICATED":
            unresolved += 1

        final = packet["adjudication"]["final_disposition"]
        if final is not None:
            resolved_dispositions[final] += 1

        item_strata = [
            annotation["stratum"]
            for annotation in packet["construct_annotations"]
        ]
        stratum_counts.update(item_strata)
        if disagreement:
            stratum_disagreements.update(item_strata)

        if (
            packet["review_design"]["model_output_blinding_state"]
            == "BLINDING_NOT_PRACTICABLE_RECORDED"
        ):
            blinding_exceptions += 1
            if packet["review_design"]["blinding_exception_rationale"]:
                blinding_with_rationale += 1

    aggregate = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "pilot_round_id": manifest["pilot_round_id"],
        "state": manifest["state"],
        "total_items": PILOT_N,
        "double_labeled_items": PILOT_N,
        "primary_secondary_exact_agreement_count": agreement,
        "primary_secondary_confusion_matrix": {
            primary: {
                secondary: matrix[primary][secondary]
                for secondary in DISPOSITIONS
            }
            for primary in DISPOSITIONS
        },
        "adjudicated_disagreement_count": adjudicated,
        "unresolved_disagreement_count": unresolved,
        "resolved_disposition_counts": {
            disposition: resolved_dispositions[disposition]
            for disposition in DISPOSITIONS
        },
        "required_stratum_counts": {
            stratum: stratum_counts[stratum]
            for stratum in REQUIRED_STRATA
        },
        "per_stratum_disagreement_counts": {
            stratum: stratum_disagreements[stratum]
            for stratum in REQUIRED_STRATA
        },
        "semantic_validation_failure_count": 0,
        "reviewer_reference_collision_count": 0,
        "evidence_binding_failure_count": 0,
        "blinding_exception_count": blinding_exceptions,
        "blinding_exception_with_rationale_count": blinding_with_rationale,
        "pilot_items_held_out_eligible_count": 0,
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "pilot_membership_commitment_scheme": manifest[
            "pilot_membership_commitment_scheme"
        ],
        "reviewer_training_record_sha256": manifest[
            "reviewer_training_record_sha256"
        ],
        "exposure_register_sha256": manifest[
            "exposure_register_sha256"
        ],
        "prior_exposure_disjointness_audit_sha256": manifest[
            "prior_exposure_disjointness_audit_sha256"
        ],
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
    result = evaluate_pilot_readiness(aggregate)
    return aggregate, result


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def _normalized(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def run_builder(
    manifest_path: Path,
    packet_root: Path,
    key_path: Path,
    *,
    controlled_aggregate_output: Path | None = None,
    controlled_error_output: Path | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    inputs = {
        _normalized(manifest_path),
        _normalized(key_path),
    }
    outputs = [
        _normalized(path)
        for path in (
            controlled_aggregate_output,
            controlled_error_output,
        )
        if path is not None
    ]
    if any(path in inputs for path in outputs) or len(outputs) != len(
        set(outputs)
    ):
        return 1, None, PUBLIC_CONTROLLED_FAILURE

    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if not isinstance(manifest, dict):
            raise D3ChallengePilotExecutionError(
                "pilot manifest root must be an object"
            )
        key = key_path.read_bytes()
        if not key:
            raise D3ChallengePilotExecutionError(
                "pilot commitment key file must not be empty"
            )
        aggregate, result = derive_readiness_aggregate(
            manifest,
            packet_root,
            key,
        )
        if controlled_aggregate_output is not None:
            _atomic_write_json(
                controlled_aggregate_output,
                aggregate,
            )
        return (
            0 if result["quantitative_gate_passed"] else 2,
            result,
            "",
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D3ChallengePilotExecutionError,
    ) as exc:
        if controlled_error_output is not None:
            try:
                _atomic_write_json(
                    controlled_error_output,
                    {
                        "schema_version": "0.1",
                        "protocol_id": PROTOCOL_ID,
                        "failure_class": "CONTROLLED_INPUT_OR_PILOT_EXECUTION_FAILURE",
                        "exception_type": type(exc).__name__,
                        "controlled_detail": str(exc),
                        "custody": "S3_CONTROLLED",
                        "public_output_authority": False,
                    },
                )
            except OSError:
                pass
        return 1, None, PUBLIC_CONTROLLED_FAILURE
    except Exception as exc:
        if controlled_error_output is not None:
            try:
                _atomic_write_json(
                    controlled_error_output,
                    {
                        "schema_version": "0.1",
                        "protocol_id": PROTOCOL_ID,
                        "failure_class": "UNEXPECTED_INTERNAL_FAILURE",
                        "exception_type": type(exc).__name__,
                        "controlled_detail": str(exc),
                        "custody": "S3_CONTROLLED",
                        "public_output_authority": False,
                    },
                )
            except OSError:
                pass
        return 70, None, PUBLIC_INTERNAL_FAILURE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive the PRE-G2 D3 challenge pilot readiness aggregate from controlled packets"
    )
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument(
        "--pilot-commitment-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--controlled-aggregate-output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--controlled-error-output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    status, result, public_message = run_builder(
        args.pilot_manifest,
        args.packet_root,
        args.pilot_commitment_key_file,
        controlled_aggregate_output=args.controlled_aggregate_output,
        controlled_error_output=args.controlled_error_output,
    )
    if result is None:
        print(public_message)
        return status
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())

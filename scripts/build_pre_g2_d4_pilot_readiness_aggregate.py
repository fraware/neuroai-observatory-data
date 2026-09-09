from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.evaluate_pre_g2_d4_pilot_readiness import (
    COMMITMENT_SCHEME,
    REQUIRED_STRATA,
    evaluate_pilot_readiness,
)
from scripts.validate_pre_g2_d4_review_packet_semantics import (
    D4ReviewPacketSemanticError,
    validate_packet_semantics,
)

BENCHMARK_ID = "PRE_G2_PRODUCT_V0_1"
SAMPLING_PROTOCOL_ID = "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1"
EXECUTION_PROTOCOL_ID = "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1"
PILOT_MEMBERSHIP_DOMAIN = "PRE_G2_D4_PILOT_MEMBERSHIP_COMMITMENT_V1"
PILOT_SIZE = 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_KEYS = {
    "schema_version",
    "benchmark_id",
    "sampling_protocol_id",
    "execution_protocol_id",
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
PACKET_TOP_KEYS = {
    "schema_version",
    "benchmark_id",
    "benchmark_kind",
    "item_id",
    "candidate_role",
    "exact_object_binding",
    "evidence_packet",
    "construct_strata",
    "review_design",
    "reviewer_records",
    "adjudication",
    "exposure_control",
    "rights_containment",
}
EXACT_OBJECT_KEYS = {
    "object_name",
    "organization_identity",
    "object_type",
    "version_status",
    "version_or_release",
    "observed_at",
    "jurisdiction_context",
    "language_context",
    "identity_resolution_state",
    "identity_basis_refs",
}
EVIDENCE_PACKET_KEYS = {
    "evidence_refs",
    "observation_cutoff",
    "identity_evidence_present",
    "stronger_claims_require_independent_support",
}
EVIDENCE_REF_KEYS = {
    "evidence_id",
    "source_class",
    "observed_at",
    "content_sha256",
    "claim_scopes",
    "source_identity_ref",
    "source_language",
    "review_language",
    "translation_status",
    "translation_provenance_ref",
}
REVIEW_DESIGN_KEYS = {
    "double_label_required",
    "model_output_blinding_state",
    "blinding_exception_rationale",
}
REVIEWER_RECORD_KEYS = {
    "reviewer_ref",
    "evidence_packet_sha256",
    "decision",
    "rationale",
    "adjudicator_role",
    "timestamp",
    "exact_object_binding",
}
ADJUDICATION_KEYS = {"state", "final_disposition", "final_rationale"}
EXPOSURE_KEYS = {"exposure_status", "exposure_register_ref", "held_out_eligible"}
RIGHTS_KEYS = {"custody", "redistribution_authority_claimed"}
FORBIDDEN_MODEL_KEYS = {
    "prediction",
    "probability_positive",
    "probability_include",
    "model_prediction",
    "model_predictions",
    "model_score",
    "model_scores",
    "prompt",
    "prompts",
    "threshold",
    "thresholds",
    "final_model_error",
    "final_model_errors",
    "historical_machine_label",
    "historical_machine_labels",
    "machine_label",
    "machine_labels",
}


class D4PilotExecutionError(ValueError):
    """Raised when controlled pilot execution cannot safely produce an aggregate."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _hmac_domain(key: bytes, domain: str, value: Any) -> str:
    if not isinstance(key, bytes) or not key:
        raise D4PilotExecutionError("pilot membership commitment key must be non-empty bytes")
    payload = domain.encode("utf-8") + b"\0" + _canonical_bytes(value)
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D4PilotExecutionError(f"{field} must be an object")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D4PilotExecutionError(f"{field} keys mismatch; missing={missing}, extra={extra}")


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D4PilotExecutionError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise D4PilotExecutionError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _reject_forbidden_model_fields(value: Any, field: str = "packet") -> None:
    if isinstance(value, dict):
        forbidden = sorted(set(value).intersection(FORBIDDEN_MODEL_KEYS))
        if forbidden:
            raise D4PilotExecutionError(f"{field} contains forbidden model-development fields: {forbidden}")
        for key, child in value.items():
            _reject_forbidden_model_fields(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_model_fields(child, f"{field}[{index}]")


def _validate_object_binding_shape(value: Any, field: str) -> None:
    mapping = _require_mapping(value, field)
    _require_exact_keys(mapping, EXACT_OBJECT_KEYS, field)


def _validate_packet_shape(packet: dict[str, Any]) -> None:
    """Enforce the exact public packet shape before semantic aggregation.

    This is deliberately narrower than a general JSON-Schema engine. It locks the
    exact object keys used by the merged public schema, rejects model-development
    fields recursively, and then delegates cross-field semantics to the merged
    validator.
    """

    _require_exact_keys(packet, PACKET_TOP_KEYS, "packet")
    _reject_forbidden_model_fields(packet)
    _validate_object_binding_shape(packet.get("exact_object_binding"), "packet.exact_object_binding")

    evidence_packet = _require_mapping(packet.get("evidence_packet"), "packet.evidence_packet")
    _require_exact_keys(evidence_packet, EVIDENCE_PACKET_KEYS, "packet.evidence_packet")
    evidence_refs = evidence_packet.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise D4PilotExecutionError("packet.evidence_packet.evidence_refs must be a non-empty array")
    for index, raw_ref in enumerate(evidence_refs):
        ref = _require_mapping(raw_ref, f"packet.evidence_packet.evidence_refs[{index}]")
        _require_exact_keys(ref, EVIDENCE_REF_KEYS, f"packet.evidence_packet.evidence_refs[{index}]")

    strata = packet.get("construct_strata")
    if not isinstance(strata, list) or not strata:
        raise D4PilotExecutionError("packet.construct_strata must be a non-empty array")
    if any(not isinstance(value, str) for value in strata):
        raise D4PilotExecutionError("packet.construct_strata values must be strings")
    if len(strata) != len(set(strata)):
        raise D4PilotExecutionError("packet.construct_strata values must be unique")
    unknown_strata = sorted(set(strata) - set(REQUIRED_STRATA))
    if unknown_strata:
        raise D4PilotExecutionError(f"packet.construct_strata contains unsupported values: {unknown_strata}")

    review_design = _require_mapping(packet.get("review_design"), "packet.review_design")
    _require_exact_keys(review_design, REVIEW_DESIGN_KEYS, "packet.review_design")

    reviewer_records = packet.get("reviewer_records")
    if not isinstance(reviewer_records, list) or not reviewer_records:
        raise D4PilotExecutionError("packet.reviewer_records must be a non-empty array")
    for index, raw_record in enumerate(reviewer_records):
        record = _require_mapping(raw_record, f"packet.reviewer_records[{index}]")
        _require_exact_keys(record, REVIEWER_RECORD_KEYS, f"packet.reviewer_records[{index}]")
        _validate_object_binding_shape(
            record.get("exact_object_binding"),
            f"packet.reviewer_records[{index}].exact_object_binding",
        )

    adjudication = _require_mapping(packet.get("adjudication"), "packet.adjudication")
    _require_exact_keys(adjudication, ADJUDICATION_KEYS, "packet.adjudication")
    exposure = _require_mapping(packet.get("exposure_control"), "packet.exposure_control")
    _require_exact_keys(exposure, EXPOSURE_KEYS, "packet.exposure_control")
    rights = _require_mapping(packet.get("rights_containment"), "packet.rights_containment")
    _require_exact_keys(rights, RIGHTS_KEYS, "packet.rights_containment")


def pilot_membership_commitment(pilot_round_id: str, item_ids: list[str], key: bytes) -> str:
    if len(item_ids) != PILOT_SIZE or len(set(item_ids)) != PILOT_SIZE:
        raise D4PilotExecutionError("pilot membership must contain exactly 60 unique item IDs")
    preimage = {
        "benchmark_id": BENCHMARK_ID,
        "sampling_protocol_id": SAMPLING_PROTOCOL_ID,
        "execution_protocol_id": EXECUTION_PROTOCOL_ID,
        "pilot_round_id": pilot_round_id,
        "item_ids": sorted(item_ids),
    }
    return _hmac_domain(key, PILOT_MEMBERSHIP_DOMAIN, preimage)


def _safe_packet_path(packet_root: Path, controlled_ref: str) -> Path:
    ref = Path(controlled_ref)
    if ref.is_absolute() or ".." in ref.parts:
        raise D4PilotExecutionError("controlled_packet_ref must be a safe relative path")
    root = packet_root.resolve()
    try:
        resolved = (root / ref).resolve(strict=True)
    except OSError as exc:
        raise D4PilotExecutionError("controlled packet is missing or unreadable") from exc
    if not resolved.is_relative_to(root):
        raise D4PilotExecutionError("controlled_packet_ref escapes packet root")
    if not resolved.is_file():
        raise D4PilotExecutionError("controlled_packet_ref must resolve to a regular file")
    return resolved


def _validate_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    _require_exact_keys(manifest, MANIFEST_KEYS, "manifest")
    if manifest["schema_version"] != "0.1":
        raise D4PilotExecutionError("manifest.schema_version must be 0.1")
    if manifest["benchmark_id"] != BENCHMARK_ID:
        raise D4PilotExecutionError(f"manifest.benchmark_id must be {BENCHMARK_ID}")
    if manifest["sampling_protocol_id"] != SAMPLING_PROTOCOL_ID:
        raise D4PilotExecutionError(f"manifest.sampling_protocol_id must be {SAMPLING_PROTOCOL_ID}")
    if manifest["execution_protocol_id"] != EXECUTION_PROTOCOL_ID:
        raise D4PilotExecutionError(f"manifest.execution_protocol_id must be {EXECUTION_PROTOCOL_ID}")
    _require_nonempty_string(manifest["pilot_round_id"], "manifest.pilot_round_id")
    if manifest["state"] != "COMPLETE_ROUND_NO_EXTENSION":
        raise D4PilotExecutionError("manifest.state must be COMPLETE_ROUND_NO_EXTENSION")
    if manifest["pilot_membership_commitment_scheme"] != COMMITMENT_SCHEME:
        raise D4PilotExecutionError(f"manifest.pilot_membership_commitment_scheme must be {COMMITMENT_SCHEME}")
    _require_sha256(manifest["pilot_membership_commitment"], "manifest.pilot_membership_commitment")
    _require_sha256(manifest["reviewer_training_record_sha256"], "manifest.reviewer_training_record_sha256")
    _require_sha256(manifest["exposure_register_sha256"], "manifest.exposure_register_sha256")
    _require_sha256(
        manifest["prior_exposure_disjointness_audit_sha256"],
        "manifest.prior_exposure_disjointness_audit_sha256",
    )

    entries = manifest["packet_manifest"]
    if not isinstance(entries, list) or len(entries) != PILOT_SIZE:
        raise D4PilotExecutionError("manifest.packet_manifest must contain exactly 60 entries")
    normalized: list[dict[str, str]] = []
    seen_refs: set[str] = set()
    for index, raw_entry in enumerate(entries):
        entry = _require_mapping(raw_entry, f"manifest.packet_manifest[{index}]")
        _require_exact_keys(entry, PACKET_ENTRY_KEYS, f"manifest.packet_manifest[{index}]")
        controlled_ref = _require_nonempty_string(
            entry["controlled_packet_ref"], f"manifest.packet_manifest[{index}].controlled_packet_ref"
        )
        if controlled_ref in seen_refs:
            raise D4PilotExecutionError("manifest.packet_manifest controlled_packet_ref values must be unique")
        seen_refs.add(controlled_ref)
        normalized.append(
            {
                "controlled_packet_ref": controlled_ref,
                "packet_sha256": _require_sha256(
                    entry["packet_sha256"], f"manifest.packet_manifest[{index}].packet_sha256"
                ),
            }
        )
    return normalized


def load_validated_pilot_packets(
    manifest: dict[str, Any],
    packet_root: Path,
    commitment_key: bytes,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries = _validate_manifest(manifest)
    packets: list[dict[str, Any]] = []
    item_ids: list[str] = []
    seen_items: set[str] = set()

    for entry in entries:
        path = _safe_packet_path(packet_root, entry["controlled_packet_ref"])
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise D4PilotExecutionError("controlled packet could not be read") from exc
        actual_digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual_digest, entry["packet_sha256"]):
            raise D4PilotExecutionError("controlled packet SHA-256 does not match manifest")
        try:
            packet = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise D4PilotExecutionError("controlled packet must be valid UTF-8 JSON") from exc
        if not isinstance(packet, dict):
            raise D4PilotExecutionError("controlled packet root must be an object")
        _validate_packet_shape(packet)
        try:
            validate_packet_semantics(packet)
        except D4ReviewPacketSemanticError as exc:
            raise D4PilotExecutionError(f"controlled packet failed merged D4 semantic validation: {exc}") from exc

        if packet.get("candidate_role") != "PILOT_DEVELOPMENT":
            raise D4PilotExecutionError("every controlled pilot packet must have candidate_role=PILOT_DEVELOPMENT")
        review_design = _require_mapping(packet.get("review_design"), "packet.review_design")
        if review_design.get("double_label_required") is not True:
            raise D4PilotExecutionError("every controlled pilot packet must require independent double labeling")
        exposure = _require_mapping(packet.get("exposure_control"), "packet.exposure_control")
        if exposure.get("held_out_eligible") is not False:
            raise D4PilotExecutionError("pilot item cannot be held-out eligible")

        item_id = _require_nonempty_string(packet.get("item_id"), "packet.item_id")
        if item_id in seen_items:
            raise D4PilotExecutionError("pilot review packets must contain 60 unique item IDs")
        seen_items.add(item_id)
        item_ids.append(item_id)
        packets.append(packet)

    if len(packets) != PILOT_SIZE or len(item_ids) != PILOT_SIZE:
        raise D4PilotExecutionError("validated pilot execution must contain exactly 60 packets/items")

    expected_commitment = pilot_membership_commitment(manifest["pilot_round_id"], item_ids, commitment_key)
    if not hmac.compare_digest(expected_commitment, manifest["pilot_membership_commitment"]):
        raise D4PilotExecutionError("pilot membership commitment does not match exact validated 60-item membership")
    return packets, item_ids


def build_pilot_readiness_aggregate(
    manifest: dict[str, Any],
    packet_root: Path,
    commitment_key: bytes,
) -> dict[str, Any]:
    packets, _ = load_validated_pilot_packets(manifest, packet_root, commitment_key)

    state_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter({key: 0 for key in ("ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE")})
    stratum_counts: Counter[str] = Counter({stratum: 0 for stratum in REQUIRED_STRATA})
    stratum_disagreements: Counter[str] = Counter({stratum: 0 for stratum in REQUIRED_STRATA})
    blinding_exception_count = 0

    for packet in packets:
        adjudication = packet["adjudication"]
        state = adjudication["state"]
        state_counts[state] += 1
        if state in {"AGREE", "ADJUDICATED"}:
            final_disposition = adjudication["final_disposition"]
            if final_disposition not in disposition_counts:
                raise D4PilotExecutionError("resolved packet final disposition is outside approved D1 domain")
            disposition_counts[final_disposition] += 1

        is_disagreement = state in {"ADJUDICATED", "DISAGREE_UNADJUDICATED"}
        for stratum in packet["construct_strata"]:
            stratum_counts[stratum] += 1
            if is_disagreement:
                stratum_disagreements[stratum] += 1

        if packet["review_design"]["model_output_blinding_state"] == "BLINDING_NOT_PRACTICABLE_RECORDED":
            blinding_exception_count += 1

    aggregate = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": SAMPLING_PROTOCOL_ID,
        "pilot_round_id": manifest["pilot_round_id"],
        "state": "COMPLETE_ROUND_NO_EXTENSION",
        "total_items": PILOT_SIZE,
        "double_labeled_items": PILOT_SIZE,
        "primary_secondary_exact_agreement_count": state_counts["AGREE"],
        "adjudicated_disagreement_count": state_counts["ADJUDICATED"],
        "unresolved_disagreement_count": state_counts["DISAGREE_UNADJUDICATED"],
        "resolved_disposition_counts": {
            "ABSTAIN": disposition_counts["ABSTAIN"],
            "BORDERLINE": disposition_counts["BORDERLINE"],
            "EXCLUDE": disposition_counts["EXCLUDE"],
            "INCLUDE": disposition_counts["INCLUDE"],
        },
        "required_stratum_counts": {stratum: stratum_counts[stratum] for stratum in REQUIRED_STRATA},
        "per_stratum_disagreement_counts": {
            stratum: stratum_disagreements[stratum] for stratum in REQUIRED_STRATA
        },
        "semantic_validation_failure_count": 0,
        "reviewer_reference_collision_count": 0,
        "evidence_binding_failure_count": 0,
        "blinding_exception_count": blinding_exception_count,
        "blinding_exception_with_rationale_count": blinding_exception_count,
        "pilot_items_held_out_eligible_count": 0,
        "pilot_membership_commitment": manifest["pilot_membership_commitment"],
        "pilot_membership_commitment_scheme": COMMITMENT_SCHEME,
        "reviewer_training_record_sha256": manifest["reviewer_training_record_sha256"],
        "exposure_register_sha256": manifest["exposure_register_sha256"],
        "pilot_disjointness_proof_sha256": manifest["prior_exposure_disjointness_audit_sha256"],
        "authority": {
            "reviewer_competence_established": False,
            "benchmark_adequacy_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }

    # Reuse the merged readiness evaluator as an invariant checker. A scientifically
    # valid but threshold-failing pilot remains a valid aggregate; the evaluator's
    # quantitative result is intentionally not promoted into authority here.
    evaluate_pilot_readiness(aggregate)
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive an aggregate PRE-G2 D4 pilot readiness report from exact S3 review packets"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--commitment-key-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise D4PilotExecutionError("manifest root must be an object")
        commitment_key = args.commitment_key_file.read_bytes()
        if not commitment_key:
            raise D4PilotExecutionError("commitment key file must not be empty")
        aggregate = build_pilot_readiness_aggregate(manifest, args.packet_root, commitment_key)
    except (OSError, json.JSONDecodeError, D4PilotExecutionError, ValueError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(json.dumps(aggregate, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

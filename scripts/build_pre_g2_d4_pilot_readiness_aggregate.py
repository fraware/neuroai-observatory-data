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

OBJECT_TYPES = {
    "PRODUCT",
    "SYSTEM",
    "SERVICE",
    "PLATFORM",
    "SOFTWARE",
    "DEVICE",
    "NONTRADITIONAL_FORM_FACTOR",
}
SOURCE_CLASSES = {
    "FIRST_PARTY",
    "REGULATOR",
    "SCIENTIFIC_PUBLICATION",
    "INSTITUTIONAL_PARTNER",
    "DISTRIBUTOR_OR_RETAILER",
    "MEDIA_OR_ANALYST",
    "OTHER",
}
CLAIM_SCOPES = {
    "EXISTENCE_IDENTITY",
    "CAPABILITY_DESCRIPTION",
    "CONTEXT_OF_USE",
    "REGULATORY_STATUS",
    "EFFECTIVENESS",
    "DEPLOYMENT",
    "COMMERCIALIZATION",
}
D1_DISPOSITIONS = {"ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE"}
REVIEWER_ROLES = {"PRIMARY_REVIEWER", "SECONDARY_REVIEWER", "FINAL_ADJUDICATOR"}
ADJUDICATION_STATES = {"ADJUDICATED", "AGREE", "DISAGREE_UNADJUDICATED"}
EXPOSURE_STATES = {
    "NO_KNOWN_EXPOSURE_REVIEWED",
    "EXPOSED_EXCLUDE_FROM_HELD_OUT",
    "UNKNOWN_REVIEW_REQUIRED",
}

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
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise D4PilotExecutionError("controlled pilot material must be finite JSON-compatible data") from exc


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


def _require_unique_strings(value: Any, field: str, *, min_length: int = 1) -> list[str]:
    if not isinstance(value, list) or not value:
        raise D4PilotExecutionError(f"{field} must be a non-empty array")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _require_nonempty_string(item, f"{field}[{index}]")
        if len(text) < min_length:
            raise D4PilotExecutionError(f"{field}[{index}] is shorter than the public schema permits")
        result.append(text)
    if len(result) != len(set(result)):
        raise D4PilotExecutionError(f"{field} values must be unique")
    return result


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
    binding = _require_mapping(value, field)
    _require_exact_keys(binding, EXACT_OBJECT_KEYS, field)
    _require_nonempty_string(binding["object_name"], f"{field}.object_name")
    _require_nonempty_string(binding["organization_identity"], f"{field}.organization_identity")
    if binding["object_type"] not in OBJECT_TYPES:
        raise D4PilotExecutionError(f"{field}.object_type is outside the public schema enum")
    if binding["version_status"] not in {"KNOWN", "NOT_STATED"}:
        raise D4PilotExecutionError(f"{field}.version_status is outside the public schema enum")
    if binding["version_status"] == "KNOWN":
        _require_nonempty_string(binding["version_or_release"], f"{field}.version_or_release")
    elif binding["version_or_release"] is not None:
        raise D4PilotExecutionError(f"{field}.version_or_release must be null when version_status=NOT_STATED")
    _require_nonempty_string(binding["observed_at"], f"{field}.observed_at")
    _require_unique_strings(binding["jurisdiction_context"], f"{field}.jurisdiction_context")
    _require_unique_strings(binding["language_context"], f"{field}.language_context", min_length=2)
    if binding["identity_resolution_state"] not in {"RESOLVED", "AMBIGUOUS"}:
        raise D4PilotExecutionError(f"{field}.identity_resolution_state is outside the public schema enum")
    _require_unique_strings(binding["identity_basis_refs"], f"{field}.identity_basis_refs")


def _validate_packet_shape(packet: dict[str, Any]) -> None:
    """Enforce the merged public review-packet structure before semantic aggregation."""

    _require_exact_keys(packet, PACKET_TOP_KEYS, "packet")
    _reject_forbidden_model_fields(packet)
    if packet["schema_version"] != "0.1" or packet["benchmark_id"] != BENCHMARK_ID:
        raise D4PilotExecutionError("packet version/benchmark binding is invalid")
    if packet["benchmark_kind"] != "PRODUCT":
        raise D4PilotExecutionError("packet.benchmark_kind must be PRODUCT")
    _require_nonempty_string(packet["item_id"], "packet.item_id")
    if packet["candidate_role"] not in {"PILOT_DEVELOPMENT", "HELD_OUT_CANDIDATE"}:
        raise D4PilotExecutionError("packet.candidate_role is outside the public schema enum")

    _validate_object_binding_shape(packet["exact_object_binding"], "packet.exact_object_binding")

    evidence_packet = _require_mapping(packet["evidence_packet"], "packet.evidence_packet")
    _require_exact_keys(evidence_packet, EVIDENCE_PACKET_KEYS, "packet.evidence_packet")
    evidence_refs = evidence_packet["evidence_refs"]
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise D4PilotExecutionError("packet.evidence_packet.evidence_refs must be a non-empty array")
    for index, raw_ref in enumerate(evidence_refs):
        field = f"packet.evidence_packet.evidence_refs[{index}]"
        ref = _require_mapping(raw_ref, field)
        _require_exact_keys(ref, EVIDENCE_REF_KEYS, field)
        _require_nonempty_string(ref["evidence_id"], f"{field}.evidence_id")
        if ref["source_class"] not in SOURCE_CLASSES:
            raise D4PilotExecutionError(f"{field}.source_class is outside the public schema enum")
        _require_nonempty_string(ref["observed_at"], f"{field}.observed_at")
        _require_sha256(ref["content_sha256"], f"{field}.content_sha256")
        claim_scopes = _require_unique_strings(ref["claim_scopes"], f"{field}.claim_scopes")
        if not set(claim_scopes).issubset(CLAIM_SCOPES):
            raise D4PilotExecutionError(f"{field}.claim_scopes contains an unsupported value")
        _require_nonempty_string(ref["source_identity_ref"], f"{field}.source_identity_ref")
        if len(_require_nonempty_string(ref["source_language"], f"{field}.source_language")) < 2:
            raise D4PilotExecutionError(f"{field}.source_language is shorter than the public schema permits")
        if len(_require_nonempty_string(ref["review_language"], f"{field}.review_language")) < 2:
            raise D4PilotExecutionError(f"{field}.review_language is shorter than the public schema permits")
        if ref["translation_status"] not in {"SOURCE_LANGUAGE_REVIEWED", "TRANSLATED_FOR_REVIEW"}:
            raise D4PilotExecutionError(f"{field}.translation_status is outside the public schema enum")
        if ref["translation_provenance_ref"] is not None:
            _require_nonempty_string(ref["translation_provenance_ref"], f"{field}.translation_provenance_ref")
    _require_nonempty_string(evidence_packet["observation_cutoff"], "packet.evidence_packet.observation_cutoff")
    if not isinstance(evidence_packet["identity_evidence_present"], bool):
        raise D4PilotExecutionError("packet.evidence_packet.identity_evidence_present must be boolean")
    if evidence_packet["stronger_claims_require_independent_support"] is not True:
        raise D4PilotExecutionError("packet stronger-claim boundary must remain enabled")

    strata = _require_unique_strings(packet["construct_strata"], "packet.construct_strata")
    unknown_strata = sorted(set(strata) - set(REQUIRED_STRATA))
    if unknown_strata:
        raise D4PilotExecutionError(f"packet.construct_strata contains unsupported values: {unknown_strata}")

    review_design = _require_mapping(packet["review_design"], "packet.review_design")
    _require_exact_keys(review_design, REVIEW_DESIGN_KEYS, "packet.review_design")
    if not isinstance(review_design["double_label_required"], bool):
        raise D4PilotExecutionError("packet.review_design.double_label_required must be boolean")
    if review_design["model_output_blinding_state"] not in {
        "BLINDED_TO_MODEL_OUTPUT",
        "BLINDING_NOT_PRACTICABLE_RECORDED",
    }:
        raise D4PilotExecutionError("packet review blinding state is outside the public schema enum")
    if review_design["blinding_exception_rationale"] is not None:
        _require_nonempty_string(
            review_design["blinding_exception_rationale"],
            "packet.review_design.blinding_exception_rationale",
        )

    reviewer_records = packet["reviewer_records"]
    if not isinstance(reviewer_records, list) or not 1 <= len(reviewer_records) <= 3:
        raise D4PilotExecutionError("packet.reviewer_records must contain between one and three records")
    for index, raw_record in enumerate(reviewer_records):
        field = f"packet.reviewer_records[{index}]"
        record = _require_mapping(raw_record, field)
        _require_exact_keys(record, REVIEWER_RECORD_KEYS, field)
        _require_nonempty_string(record["reviewer_ref"], f"{field}.reviewer_ref")
        _require_sha256(record["evidence_packet_sha256"], f"{field}.evidence_packet_sha256")
        if record["decision"] not in D1_DISPOSITIONS:
            raise D4PilotExecutionError(f"{field}.decision is outside the D1 disposition domain")
        _require_nonempty_string(record["rationale"], f"{field}.rationale")
        if record["adjudicator_role"] not in REVIEWER_ROLES:
            raise D4PilotExecutionError(f"{field}.adjudicator_role is outside the public schema enum")
        _require_nonempty_string(record["timestamp"], f"{field}.timestamp")
        _validate_object_binding_shape(record["exact_object_binding"], f"{field}.exact_object_binding")

    adjudication = _require_mapping(packet["adjudication"], "packet.adjudication")
    _require_exact_keys(adjudication, ADJUDICATION_KEYS, "packet.adjudication")
    if adjudication["state"] not in ADJUDICATION_STATES:
        raise D4PilotExecutionError("packet.adjudication.state is outside the public schema enum")
    if adjudication["final_disposition"] is not None and adjudication["final_disposition"] not in D1_DISPOSITIONS:
        raise D4PilotExecutionError("packet.adjudication.final_disposition is outside the D1 domain")
    if adjudication["final_rationale"] is not None:
        _require_nonempty_string(adjudication["final_rationale"], "packet.adjudication.final_rationale")

    exposure = _require_mapping(packet["exposure_control"], "packet.exposure_control")
    _require_exact_keys(exposure, EXPOSURE_KEYS, "packet.exposure_control")
    if exposure["exposure_status"] not in EXPOSURE_STATES:
        raise D4PilotExecutionError("packet.exposure_control.exposure_status is outside the public schema enum")
    _require_nonempty_string(exposure["exposure_register_ref"], "packet.exposure_control.exposure_register_ref")
    if not isinstance(exposure["held_out_eligible"], bool):
        raise D4PilotExecutionError("packet.exposure_control.held_out_eligible must be boolean")

    rights = _require_mapping(packet["rights_containment"], "packet.rights_containment")
    _require_exact_keys(rights, RIGHTS_KEYS, "packet.rights_containment")
    if rights["custody"] != "S3_CONTROLLED" or rights["redistribution_authority_claimed"] is not False:
        raise D4PilotExecutionError("packet rights containment must remain S3-controlled and non-authorizing")


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
        except D4ReviewPacketSemanticError:
            # The merged semantic validator may include controlled evidence refs in
            # detailed diagnostics. Do not propagate those identifiers to stdout.
            raise D4PilotExecutionError("controlled packet failed merged D4 semantic validation") from None

        if packet["candidate_role"] != "PILOT_DEVELOPMENT":
            raise D4PilotExecutionError("every controlled pilot packet must have candidate_role=PILOT_DEVELOPMENT")
        if packet["review_design"]["double_label_required"] is not True:
            raise D4PilotExecutionError("every controlled pilot packet must require independent double labeling")
        if packet["exposure_control"]["held_out_eligible"] is not False:
            raise D4PilotExecutionError("pilot item cannot be held-out eligible")

        item_id = _require_nonempty_string(packet["item_id"], "packet.item_id")
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
        state = packet["adjudication"]["state"]
        state_counts[state] += 1
        if state in {"AGREE", "ADJUDICATED"}:
            final_disposition = packet["adjudication"]["final_disposition"]
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

    # Reuse the merged readiness evaluator as an invariant checker. A structurally
    # valid but threshold-failing pilot remains a valid aggregate; the quantitative
    # result is intentionally not promoted into authority here.
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

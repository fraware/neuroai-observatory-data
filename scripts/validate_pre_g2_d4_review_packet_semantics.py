from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

D1_DISPOSITIONS = frozenset({"ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE"})
REVIEWER_ROLES = frozenset({"PRIMARY_REVIEWER", "SECONDARY_REVIEWER", "FINAL_ADJUDICATOR"})
UNRESOLVED_STATE = "DISAGREE_UNADJUDICATED"


class D4ReviewPacketSemanticError(ValueError):
    """Raised when cross-field D4 review semantics fail closed."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D4ReviewPacketSemanticError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise D4ReviewPacketSemanticError(f"{field} must be an array")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D4ReviewPacketSemanticError(f"{field} must be a non-empty string")
    return value


def _parse_aware_timestamp(value: Any, field: str) -> datetime:
    text = _require_string(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise D4ReviewPacketSemanticError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise D4ReviewPacketSemanticError(f"{field} must include a timezone offset")
    return parsed


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def validate_packet_semantics(packet: dict[str, Any]) -> None:
    """Validate cross-field semantics that the public JSON Schema cannot express.

    This validator does not establish source truth, reviewer competence, benchmark
    adequacy, rights, or G2. It assumes structural schema validation is performed
    separately and adds fail-closed identity/review/adjudication/exposure checks.
    """

    if packet.get("schema_version") != "0.1":
        raise D4ReviewPacketSemanticError("schema_version must be 0.1")
    if packet.get("benchmark_id") != "PRE_G2_PRODUCT_V0_1" or packet.get("benchmark_kind") != "PRODUCT":
        raise D4ReviewPacketSemanticError("packet must bind PRE_G2_PRODUCT_V0_1 / PRODUCT")

    candidate_role = packet.get("candidate_role")
    if candidate_role not in {"PILOT_DEVELOPMENT", "HELD_OUT_CANDIDATE"}:
        raise D4ReviewPacketSemanticError("candidate_role is unsupported")

    object_binding = _require_mapping(packet.get("exact_object_binding"), "exact_object_binding")
    object_binding_canonical = _canonical(object_binding)
    identity_state = object_binding.get("identity_resolution_state")
    if identity_state not in {"RESOLVED", "AMBIGUOUS"}:
        raise D4ReviewPacketSemanticError("identity_resolution_state is unsupported")
    object_observed_at = _parse_aware_timestamp(object_binding.get("observed_at"), "exact_object_binding.observed_at")
    raw_identity_basis_refs = _require_list(object_binding.get("identity_basis_refs"), "exact_object_binding.identity_basis_refs")
    if not raw_identity_basis_refs:
        raise D4ReviewPacketSemanticError("identity_basis_refs must not be empty")
    identity_basis_refs = [
        _require_string(value, f"exact_object_binding.identity_basis_refs[{index}]")
        for index, value in enumerate(raw_identity_basis_refs)
    ]
    if len(identity_basis_refs) != len(set(identity_basis_refs)):
        raise D4ReviewPacketSemanticError("identity_basis_refs must be unique")

    evidence_packet = _require_mapping(packet.get("evidence_packet"), "evidence_packet")
    cutoff = _parse_aware_timestamp(evidence_packet.get("observation_cutoff"), "evidence_packet.observation_cutoff")
    if object_observed_at > cutoff:
        raise D4ReviewPacketSemanticError("exact object observation cannot be later than the evidence cutoff")
    if evidence_packet.get("identity_evidence_present") is not True:
        raise D4ReviewPacketSemanticError("identity_evidence_present must be true before human reference review")
    if evidence_packet.get("stronger_claims_require_independent_support") is not True:
        raise D4ReviewPacketSemanticError("stronger-claim evidence boundary must remain enabled")

    evidence_refs = _require_list(evidence_packet.get("evidence_refs"), "evidence_packet.evidence_refs")
    if not evidence_refs:
        raise D4ReviewPacketSemanticError("evidence_packet.evidence_refs must not be empty")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_ref in enumerate(evidence_refs):
        ref = _require_mapping(raw_ref, f"evidence_packet.evidence_refs[{index}]")
        evidence_id = _require_string(ref.get("evidence_id"), f"evidence_packet.evidence_refs[{index}].evidence_id")
        if evidence_id in evidence_by_id:
            raise D4ReviewPacketSemanticError("evidence_id values must be unique within a packet")
        evidence_by_id[evidence_id] = ref
        observed = _parse_aware_timestamp(
            ref.get("observed_at"), f"evidence_packet.evidence_refs[{index}].observed_at"
        )
        if observed > cutoff:
            raise D4ReviewPacketSemanticError("evidence observation cannot be later than the packet cutoff")

    missing_identity_refs = [ref for ref in identity_basis_refs if ref not in evidence_by_id]
    if missing_identity_refs:
        raise D4ReviewPacketSemanticError(
            f"identity_basis_refs must resolve to evidence in the same packet: {sorted(missing_identity_refs)}"
        )
    if not any(
        "EXISTENCE_IDENTITY" in _require_list(evidence_by_id[ref].get("claim_scopes"), f"evidence {ref}.claim_scopes")
        for ref in identity_basis_refs
    ):
        raise D4ReviewPacketSemanticError(
            "at least one identity_basis_ref must explicitly support EXISTENCE_IDENTITY"
        )

    review_design = _require_mapping(packet.get("review_design"), "review_design")
    double_label_required = review_design.get("double_label_required")
    if not isinstance(double_label_required, bool):
        raise D4ReviewPacketSemanticError("review_design.double_label_required must be boolean")
    if candidate_role == "HELD_OUT_CANDIDATE" and double_label_required is not True:
        raise D4ReviewPacketSemanticError("all held-out D4 candidates require independent double labeling")
    blinding_state = review_design.get("model_output_blinding_state")
    exception_rationale = review_design.get("blinding_exception_rationale")
    if blinding_state == "BLINDED_TO_MODEL_OUTPUT":
        if exception_rationale is not None:
            raise D4ReviewPacketSemanticError("blinded review cannot carry a blinding-exception rationale")
    elif blinding_state == "BLINDING_NOT_PRACTICABLE_RECORDED":
        _require_string(exception_rationale, "review_design.blinding_exception_rationale")
    else:
        raise D4ReviewPacketSemanticError("model_output_blinding_state is unsupported")

    reviewer_records = _require_list(packet.get("reviewer_records"), "reviewer_records")
    if not reviewer_records:
        raise D4ReviewPacketSemanticError("at least one reviewer record is required")
    by_role: dict[str, dict[str, Any]] = {}
    reviewer_refs: set[str] = set()
    reviewed_at_by_role: dict[str, datetime] = {}
    for index, raw_record in enumerate(reviewer_records):
        record = _require_mapping(raw_record, f"reviewer_records[{index}]")
        reviewer_ref = _require_string(record.get("reviewer_ref"), f"reviewer_records[{index}].reviewer_ref")
        if reviewer_ref in reviewer_refs:
            raise D4ReviewPacketSemanticError("reviewer_ref values must be distinct across reviewer roles")
        reviewer_refs.add(reviewer_ref)
        role = record.get("adjudicator_role")
        if role not in REVIEWER_ROLES:
            raise D4ReviewPacketSemanticError("reviewer adjudicator_role is unsupported")
        assert isinstance(role, str)
        if role in by_role:
            raise D4ReviewPacketSemanticError(f"duplicate reviewer role: {role}")
        by_role[role] = record
        if record.get("decision") not in D1_DISPOSITIONS:
            raise D4ReviewPacketSemanticError("review decision is outside the approved D1 disposition domain")
        _require_string(record.get("rationale"), f"reviewer_records[{index}].rationale")
        reviewer_binding = _require_mapping(
            record.get("exact_object_binding"), f"reviewer_records[{index}].exact_object_binding"
        )
        if _canonical(reviewer_binding) != object_binding_canonical:
            raise D4ReviewPacketSemanticError("every reviewer record must bind the exact same object as the packet")
        reviewed_at = _parse_aware_timestamp(record.get("timestamp"), f"reviewer_records[{index}].timestamp")
        if reviewed_at < cutoff:
            raise D4ReviewPacketSemanticError("review timestamp cannot precede the frozen evidence cutoff")
        reviewed_at_by_role[role] = reviewed_at

    primary = by_role.get("PRIMARY_REVIEWER")
    secondary = by_role.get("SECONDARY_REVIEWER")
    final_adjudicator = by_role.get("FINAL_ADJUDICATOR")
    if primary is None:
        raise D4ReviewPacketSemanticError("PRIMARY_REVIEWER is required")
    if double_label_required and secondary is None:
        raise D4ReviewPacketSemanticError("SECONDARY_REVIEWER is required for double-labeled items")
    if not double_label_required and secondary is not None:
        raise D4ReviewPacketSemanticError("secondary review requires double_label_required=true")

    adjudication = _require_mapping(packet.get("adjudication"), "adjudication")
    state = adjudication.get("state")
    final_disposition = adjudication.get("final_disposition")
    final_rationale = adjudication.get("final_rationale")

    if state == "AGREE":
        if secondary is None:
            raise D4ReviewPacketSemanticError("AGREE requires primary and secondary reviews")
        if primary.get("decision") != secondary.get("decision"):
            raise D4ReviewPacketSemanticError("AGREE requires matching primary and secondary dispositions")
        if final_adjudicator is not None:
            raise D4ReviewPacketSemanticError("AGREE must not include an unnecessary FINAL_ADJUDICATOR")
        if final_disposition != primary.get("decision"):
            raise D4ReviewPacketSemanticError("AGREE final_disposition must equal the agreed reviewer disposition")
        _require_string(final_rationale, "adjudication.final_rationale")
    elif state == "ADJUDICATED":
        if secondary is None:
            raise D4ReviewPacketSemanticError("ADJUDICATED requires primary and secondary reviews")
        if primary.get("decision") == secondary.get("decision"):
            raise D4ReviewPacketSemanticError("ADJUDICATED requires a real primary/secondary disagreement")
        if final_adjudicator is None:
            raise D4ReviewPacketSemanticError("ADJUDICATED requires a FINAL_ADJUDICATOR record")
        if final_disposition not in D1_DISPOSITIONS:
            raise D4ReviewPacketSemanticError("adjudicated final_disposition is outside the D1 domain")
        if final_adjudicator.get("decision") != final_disposition:
            raise D4ReviewPacketSemanticError("FINAL_ADJUDICATOR decision must equal final_disposition")
        adjudicator_time = reviewed_at_by_role["FINAL_ADJUDICATOR"]
        if adjudicator_time < max(
            reviewed_at_by_role["PRIMARY_REVIEWER"], reviewed_at_by_role["SECONDARY_REVIEWER"]
        ):
            raise D4ReviewPacketSemanticError("FINAL_ADJUDICATOR timestamp cannot precede primary/secondary review")
        _require_string(final_rationale, "adjudication.final_rationale")
    elif state == UNRESOLVED_STATE:
        if secondary is None:
            raise D4ReviewPacketSemanticError("unresolved disagreement requires primary and secondary reviews")
        if primary.get("decision") == secondary.get("decision"):
            raise D4ReviewPacketSemanticError("unresolved disagreement requires differing reviewer dispositions")
        if final_adjudicator is not None:
            raise D4ReviewPacketSemanticError("unresolved disagreement must not include FINAL_ADJUDICATOR")
        if final_disposition is not None or final_rationale is not None:
            raise D4ReviewPacketSemanticError("unresolved disagreement must retain null final disposition/rationale")
    else:
        raise D4ReviewPacketSemanticError("adjudication.state is unsupported")

    exposure = _require_mapping(packet.get("exposure_control"), "exposure_control")
    exposure_status = exposure.get("exposure_status")
    held_out_eligible = exposure.get("held_out_eligible")
    if not isinstance(held_out_eligible, bool):
        raise D4ReviewPacketSemanticError("exposure_control.held_out_eligible must be boolean")
    _require_string(exposure.get("exposure_register_ref"), "exposure_control.exposure_register_ref")
    if candidate_role == "PILOT_DEVELOPMENT" and held_out_eligible:
        raise D4ReviewPacketSemanticError("pilot/development material cannot be held-out eligible")
    if identity_state != "RESOLVED" and held_out_eligible:
        raise D4ReviewPacketSemanticError("ambiguous object identity cannot be held-out eligible")
    if exposure_status != "NO_KNOWN_EXPOSURE_REVIEWED" and held_out_eligible:
        raise D4ReviewPacketSemanticError("held-out eligibility requires completed no-known-exposure review")
    if state == UNRESOLVED_STATE and held_out_eligible:
        raise D4ReviewPacketSemanticError("unresolved disagreement cannot be held-out eligible")

    rights = _require_mapping(packet.get("rights_containment"), "rights_containment")
    if rights.get("custody") != "S3_CONTROLLED":
        raise D4ReviewPacketSemanticError("review packet custody must remain S3_CONTROLLED")
    if rights.get("redistribution_authority_claimed") is not False:
        raise D4ReviewPacketSemanticError("review packet cannot claim redistribution authority")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PRE-G2 D4 review-packet cross-field semantics")
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
        if not isinstance(packet, dict):
            raise D4ReviewPacketSemanticError("packet root must be an object")
        validate_packet_semantics(packet)
    except (OSError, json.JSONDecodeError, D4ReviewPacketSemanticError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print("VALID: PRE-G2 D4 cross-field semantics satisfied; no authority is conferred")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

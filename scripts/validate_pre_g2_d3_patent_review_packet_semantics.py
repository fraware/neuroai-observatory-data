from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PATENT_V0_1"
EVIDENCE_ROLE = "CHALLENGE_CONSTRUCT_COVERAGE"
D1_DISPOSITIONS = {"INCLUDE", "EXCLUDE", "BORDERLINE", "ABSTAIN"}
ADJUDICATION_STATES = {"AGREE", "ADJUDICATED", "DISAGREE_UNADJUDICATED"}
UNRESOLVED_STATE = "DISAGREE_UNADJUDICATED"
REVIEWER_ROLES = {"PRIMARY_REVIEWER", "SECONDARY_REVIEWER", "FINAL_ADJUDICATOR"}
REQUIRED_STRATA = {
    "GRAY_CAPABILITY",
    "MISSING_OR_SHORT_ABSTRACT",
    "MULTI_JURISDICTION",
    "MULTI_YEAR",
    "MULTILINGUAL",
    "SEMANTICALLY_DECEPTIVE_NEGATIVE",
}
CLAIM_SCOPES = {
    "CAPABILITY_CONTEXT",
    "FAMILY_IDENTITY",
    "JURISDICTION",
    "NEGATIVE_CONTROL_CONTEXT",
    "PATENT_TEXT",
    "PUBLICATION_IDENTITY",
    "TEMPORAL",
}
SOURCE_CLASSES = {
    "EPO_OPS_BIBLIOGRAPHIC",
    "PATENT_OFFICE_PUBLIC",
    "PATSTAT_CONTROLLED",
    "RIGHTS_APPROVED_OTHER",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_MODEL_KEYS = {
    "prediction",
    "predictions",
    "model_prediction",
    "model_predictions",
    "probability_positive",
    "probability_include",
    "model_score",
    "model_scores",
    "historical_machine_label",
    "historical_machine_labels",
    "cheap_neuro",
    "gold_neuro",
    "verdict",
    "prompt",
    "prompts",
    "threshold",
    "thresholds",
    "final_model_error",
    "final_model_errors",
}

TOP_LEVEL_KEYS = {
    "schema_version",
    "benchmark_id",
    "benchmark_kind",
    "evidence_role",
    "candidate_role",
    "exact_patent_binding",
    "evidence_packet",
    "construct_annotations",
    "review_design",
    "reviewer_records",
    "adjudication",
    "exposure_control",
    "sampling_provenance",
    "rights_containment",
    "authority",
}
PATENT_BINDING_KEYS = {
    "controlled_family_ref",
    "unit_of_observation",
    "family_identity_state",
    "publication_identity_refs",
    "family_years",
    "jurisdictions",
    "source_languages",
    "text_availability",
    "observed_at",
    "identity_basis_refs",
}
EVIDENCE_PACKET_KEYS = {
    "evidence_refs",
    "observation_cutoff",
    "historical_machine_labels_included",
    "population_weights_included",
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
    "custody",
    "rights_state",
}
CONSTRUCT_ANNOTATION_KEYS = {"stratum", "human_confirmed", "rationale", "evidence_refs"}
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
    "exact_patent_binding",
}
ADJUDICATION_KEYS = {"state", "final_disposition", "final_rationale"}
EXPOSURE_KEYS = {"exposure_status", "exposure_register_ref", "held_out_eligible"}
SAMPLING_PROVENANCE_KEYS = {
    "baseline_a_used_for_candidate_discovery",
    "historical_machine_labels_visible_to_reviewers",
    "query_pool_provenance",
    "population_weight",
    "inclusion_probability",
}
RIGHTS_KEYS = {
    "packet_custody",
    "patstat_rights_issue",
    "patstat_rights_clearance",
    "redistribution_authority_claimed",
}
AUTHORITY_KEYS = {
    "g2_passed",
    "benchmark_adequacy_established",
    "population_generalization_authority",
    "canonical_s2_authority",
    "publication_authority",
    "assessment_effect",
}


class D3PatentReviewPacketSemanticError(ValueError):
    """Raised when a D3 challenge review packet violates controlled semantics."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D3PatentReviewPacketSemanticError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise D3PatentReviewPacketSemanticError(f"{field} must be an array")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D3PatentReviewPacketSemanticError(f"{field} must be a non-empty string")
    return value


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D3PatentReviewPacketSemanticError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_unique_strings(value: Any, field: str) -> list[str]:
    values = _require_list(value, field)
    if not values:
        raise D3PatentReviewPacketSemanticError(f"{field} must be non-empty")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise D3PatentReviewPacketSemanticError(f"{field} must contain non-empty strings")
    rendered = [str(item) for item in values]
    if len(rendered) != len(set(rendered)):
        raise D3PatentReviewPacketSemanticError(f"{field} values must be unique")
    return rendered


def _parse_aware_timestamp(value: Any, field: str) -> datetime:
    text = _require_string(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise D3PatentReviewPacketSemanticError(f"{field} must be ISO-8601 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise D3PatentReviewPacketSemanticError(f"{field} must include an explicit timezone")
    return parsed


def _reject_forbidden_model_fields(value: Any, field: str = "packet") -> None:
    if isinstance(value, dict):
        forbidden = sorted(set(value).intersection(FORBIDDEN_MODEL_KEYS))
        if forbidden:
            raise D3PatentReviewPacketSemanticError(
                f"{field} contains forbidden model-development fields: {forbidden}"
            )
        for key, child in value.items():
            _reject_forbidden_model_fields(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_model_fields(child, f"{field}[{index}]")


def _validate_patent_binding(binding: dict[str, Any], field: str) -> dict[str, Any]:
    _require_exact_keys(binding, PATENT_BINDING_KEYS, field)
    _require_string(binding.get("controlled_family_ref"), f"{field}.controlled_family_ref")
    if binding.get("unit_of_observation") != "DOCDB_SIMPLE_PATENT_FAMILY":
        raise D3PatentReviewPacketSemanticError(
            f"{field}.unit_of_observation must be DOCDB_SIMPLE_PATENT_FAMILY"
        )
    if binding.get("family_identity_state") not in {"RESOLVED", "AMBIGUOUS_REVIEW_REQUIRED"}:
        raise D3PatentReviewPacketSemanticError(f"{field}.family_identity_state is unsupported")

    publication_refs = _require_unique_strings(
        binding.get("publication_identity_refs"),
        f"{field}.publication_identity_refs",
    )
    years = _require_list(binding.get("family_years"), f"{field}.family_years")
    if not years or any(not isinstance(year, int) or isinstance(year, bool) for year in years):
        raise D3PatentReviewPacketSemanticError(f"{field}.family_years must contain integers")
    if any(year < 1800 or year > 2200 for year in years):
        raise D3PatentReviewPacketSemanticError(f"{field}.family_years contains an invalid year")
    if len(years) != len(set(years)):
        raise D3PatentReviewPacketSemanticError(f"{field}.family_years values must be unique")

    jurisdictions = _require_unique_strings(binding.get("jurisdictions"), f"{field}.jurisdictions")
    languages = _require_unique_strings(binding.get("source_languages"), f"{field}.source_languages")
    if binding.get("text_availability") not in {
        "ENGLISH_ABSTRACT",
        "NON_ENGLISH_ABSTRACT_ONLY",
        "SHORT_ABSTRACT",
        "MISSING_ABSTRACT",
        "TITLE_ONLY",
    }:
        raise D3PatentReviewPacketSemanticError(f"{field}.text_availability is unsupported")
    observed_at = _parse_aware_timestamp(binding.get("observed_at"), f"{field}.observed_at")
    identity_refs = _require_unique_strings(
        binding.get("identity_basis_refs"), f"{field}.identity_basis_refs"
    )
    return {
        "publication_refs": publication_refs,
        "years": years,
        "jurisdictions": jurisdictions,
        "languages": languages,
        "observed_at": observed_at,
        "identity_refs": identity_refs,
    }


def validate_packet_semantics(packet: dict[str, Any]) -> None:
    _require_exact_keys(packet, TOP_LEVEL_KEYS, "packet")
    _reject_forbidden_model_fields(packet)

    if packet.get("schema_version") != "0.1":
        raise D3PatentReviewPacketSemanticError("schema_version must be 0.1")
    if packet.get("benchmark_id") != BENCHMARK_ID:
        raise D3PatentReviewPacketSemanticError(f"benchmark_id must be {BENCHMARK_ID}")
    if packet.get("benchmark_kind") != "PATENT":
        raise D3PatentReviewPacketSemanticError("benchmark_kind must be PATENT")
    if packet.get("evidence_role") != EVIDENCE_ROLE:
        raise D3PatentReviewPacketSemanticError(f"evidence_role must be {EVIDENCE_ROLE}")

    candidate_role = packet.get("candidate_role")
    if candidate_role not in {"PILOT_DEVELOPMENT", "HELD_OUT_CANDIDATE"}:
        raise D3PatentReviewPacketSemanticError("candidate_role is unsupported")

    binding = _require_mapping(packet.get("exact_patent_binding"), "exact_patent_binding")
    binding_facts = _validate_patent_binding(binding, "exact_patent_binding")
    binding_canonical = _canonical(binding)

    evidence_packet = _require_mapping(packet.get("evidence_packet"), "evidence_packet")
    _require_exact_keys(evidence_packet, EVIDENCE_PACKET_KEYS, "evidence_packet")
    if evidence_packet.get("historical_machine_labels_included") is not False:
        raise D3PatentReviewPacketSemanticError(
            "historical machine labels must not be included in the review evidence packet"
        )
    if evidence_packet.get("population_weights_included") is not False:
        raise D3PatentReviewPacketSemanticError(
            "challenge review evidence must not include population weights"
        )
    cutoff = _parse_aware_timestamp(
        evidence_packet.get("observation_cutoff"), "evidence_packet.observation_cutoff"
    )
    if binding_facts["observed_at"] > cutoff:
        raise D3PatentReviewPacketSemanticError(
            "exact_patent_binding.observed_at cannot be later than the frozen evidence cutoff"
        )

    evidence_refs = _require_list(evidence_packet.get("evidence_refs"), "evidence_packet.evidence_refs")
    if not evidence_refs:
        raise D3PatentReviewPacketSemanticError("evidence_packet.evidence_refs must be non-empty")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    non_english_or_translated = False
    for index, raw_ref in enumerate(evidence_refs):
        ref = _require_mapping(raw_ref, f"evidence_packet.evidence_refs[{index}]")
        _require_exact_keys(ref, EVIDENCE_REF_KEYS, f"evidence_packet.evidence_refs[{index}]")
        evidence_id = _require_string(
            ref.get("evidence_id"), f"evidence_packet.evidence_refs[{index}].evidence_id"
        )
        if evidence_id in evidence_by_id:
            raise D3PatentReviewPacketSemanticError("evidence_id values must be unique")
        evidence_by_id[evidence_id] = ref
        source_class = ref.get("source_class")
        if source_class not in SOURCE_CLASSES:
            raise D3PatentReviewPacketSemanticError("source_class is unsupported")
        observed = _parse_aware_timestamp(
            ref.get("observed_at"), f"evidence_packet.evidence_refs[{index}].observed_at"
        )
        if observed > cutoff:
            raise D3PatentReviewPacketSemanticError(
                "evidence observation cannot be later than the frozen evidence cutoff"
            )
        digest = ref.get("content_sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise D3PatentReviewPacketSemanticError("evidence content_sha256 is invalid")
        scopes = _require_unique_strings(
            ref.get("claim_scopes"), f"evidence_packet.evidence_refs[{index}].claim_scopes"
        )
        if not set(scopes).issubset(CLAIM_SCOPES):
            raise D3PatentReviewPacketSemanticError("evidence claim_scopes contain unsupported values")
        _require_string(
            ref.get("source_identity_ref"),
            f"evidence_packet.evidence_refs[{index}].source_identity_ref",
        )
        source_language = _require_string(
            ref.get("source_language"), f"evidence_packet.evidence_refs[{index}].source_language"
        )
        review_language = _require_string(
            ref.get("review_language"), f"evidence_packet.evidence_refs[{index}].review_language"
        )
        translation_status = ref.get("translation_status")
        translation_ref = ref.get("translation_provenance_ref")
        if translation_status == "SOURCE_LANGUAGE_REVIEWED":
            if source_language != review_language:
                raise D3PatentReviewPacketSemanticError(
                    "SOURCE_LANGUAGE_REVIEWED requires matching source/review languages"
                )
            if translation_ref is not None:
                raise D3PatentReviewPacketSemanticError(
                    "SOURCE_LANGUAGE_REVIEWED must not carry translation provenance"
                )
        elif translation_status == "TRANSLATED_FOR_REVIEW":
            if source_language == review_language:
                raise D3PatentReviewPacketSemanticError(
                    "TRANSLATED_FOR_REVIEW requires distinct source/review languages"
                )
            _require_string(
                translation_ref,
                f"evidence_packet.evidence_refs[{index}].translation_provenance_ref",
            )
        else:
            raise D3PatentReviewPacketSemanticError("translation_status is unsupported")
        if source_language.lower() != "en" or translation_status == "TRANSLATED_FOR_REVIEW":
            non_english_or_translated = True

        custody = ref.get("custody")
        rights_state = ref.get("rights_state")
        if source_class == "PATSTAT_CONTROLLED":
            if custody != "S3_CONTROLLED" or rights_state != "S3_LICENSED_RIGHTS_UNRESOLVED":
                raise D3PatentReviewPacketSemanticError(
                    "PATSTAT_CONTROLLED evidence must remain S3_CONTROLLED and rights-unresolved"
                )
        elif custody not in {"PUBLIC_REPRODUCIBLE", "S3_CONTROLLED"}:
            raise D3PatentReviewPacketSemanticError("evidence custody is unsupported")
        if rights_state not in {
            "PUBLIC_SOURCE_TERMS_APPLY",
            "S3_LICENSED_RIGHTS_UNRESOLVED",
            "S3_CONTROLLED_OTHER",
        }:
            raise D3PatentReviewPacketSemanticError("evidence rights_state is unsupported")

    missing_identity_refs = [
        ref for ref in binding_facts["identity_refs"] if ref not in evidence_by_id
    ]
    if missing_identity_refs:
        raise D3PatentReviewPacketSemanticError(
            "identity_basis_refs must resolve to evidence in the same packet"
        )
    for identity_ref in binding_facts["identity_refs"]:
        scopes = set(evidence_by_id[identity_ref]["claim_scopes"])
        if not scopes.intersection({"FAMILY_IDENTITY", "PUBLICATION_IDENTITY"}):
            raise D3PatentReviewPacketSemanticError(
                "every identity_basis_ref must support FAMILY_IDENTITY or PUBLICATION_IDENTITY"
            )

    publication_ref_set = set(binding_facts["publication_refs"])
    unresolved_publication_refs = publication_ref_set - set(evidence_by_id)
    if unresolved_publication_refs:
        raise D3PatentReviewPacketSemanticError(
            "publication_identity_refs must resolve to evidence in the same packet"
        )
    for publication_ref in publication_ref_set:
        if "PUBLICATION_IDENTITY" not in evidence_by_id[publication_ref]["claim_scopes"]:
            raise D3PatentReviewPacketSemanticError(
                "publication_identity_refs must explicitly support PUBLICATION_IDENTITY"
            )

    annotations = _require_list(packet.get("construct_annotations"), "construct_annotations")
    if not annotations:
        raise D3PatentReviewPacketSemanticError("construct_annotations must be non-empty")
    annotation_by_stratum: dict[str, dict[str, Any]] = {}
    for index, raw_annotation in enumerate(annotations):
        annotation = _require_mapping(raw_annotation, f"construct_annotations[{index}]")
        _require_exact_keys(
            annotation,
            CONSTRUCT_ANNOTATION_KEYS,
            f"construct_annotations[{index}]",
        )
        stratum = annotation.get("stratum")
        if stratum not in REQUIRED_STRATA:
            raise D3PatentReviewPacketSemanticError("construct annotation stratum is unsupported")
        assert isinstance(stratum, str)
        if stratum in annotation_by_stratum:
            raise D3PatentReviewPacketSemanticError("construct stratum annotations must be unique")
        annotation_by_stratum[stratum] = annotation
        if annotation.get("human_confirmed") is not True:
            raise D3PatentReviewPacketSemanticError(
                "construct annotations must be human-confirmed"
            )
        _require_string(annotation.get("rationale"), f"construct_annotations[{index}].rationale")
        annotation_refs = _require_unique_strings(
            annotation.get("evidence_refs"),
            f"construct_annotations[{index}].evidence_refs",
        )
        if any(ref not in evidence_by_id for ref in annotation_refs):
            raise D3PatentReviewPacketSemanticError(
                "construct annotation evidence_refs must resolve inside the same packet"
            )

    strata = set(annotation_by_stratum)
    if "MULTI_YEAR" in strata and len(binding_facts["years"]) < 2:
        raise D3PatentReviewPacketSemanticError(
            "MULTI_YEAR requires at least two distinct family years"
        )
    if "MULTI_JURISDICTION" in strata and len(binding_facts["jurisdictions"]) < 2:
        raise D3PatentReviewPacketSemanticError(
            "MULTI_JURISDICTION requires at least two jurisdictions"
        )
    if "MULTILINGUAL" in strata and not non_english_or_translated:
        raise D3PatentReviewPacketSemanticError(
            "MULTILINGUAL requires non-English or translated review evidence"
        )
    if (
        "MISSING_OR_SHORT_ABSTRACT" in strata
        and binding.get("text_availability") not in {"MISSING_ABSTRACT", "SHORT_ABSTRACT"}
    ):
        raise D3PatentReviewPacketSemanticError(
            "MISSING_OR_SHORT_ABSTRACT requires MISSING_ABSTRACT or SHORT_ABSTRACT"
        )

    sampling = _require_mapping(packet.get("sampling_provenance"), "sampling_provenance")
    _require_exact_keys(sampling, SAMPLING_PROVENANCE_KEYS, "sampling_provenance")
    if not isinstance(sampling.get("baseline_a_used_for_candidate_discovery"), bool):
        raise D3PatentReviewPacketSemanticError(
            "baseline_a_used_for_candidate_discovery must be boolean"
        )
    if sampling.get("historical_machine_labels_visible_to_reviewers") is not False:
        raise D3PatentReviewPacketSemanticError(
            "historical machine labels must remain hidden from reviewers"
        )
    if sampling.get("query_pool_provenance") not in {
        "IN_QUERY_POOL",
        "OUTSIDE_QUERY_POOL",
        "UNKNOWN",
        "NOT_APPLICABLE",
    }:
        raise D3PatentReviewPacketSemanticError("query_pool_provenance is unsupported")
    if sampling.get("population_weight") is not None or sampling.get("inclusion_probability") is not None:
        raise D3PatentReviewPacketSemanticError(
            "challenge packets must not carry population weights or inclusion probabilities"
        )

    review_design = _require_mapping(packet.get("review_design"), "review_design")
    _require_exact_keys(review_design, REVIEW_DESIGN_KEYS, "review_design")
    double_label_required = review_design.get("double_label_required")
    if not isinstance(double_label_required, bool):
        raise D3PatentReviewPacketSemanticError("double_label_required must be boolean")
    if candidate_role == "HELD_OUT_CANDIDATE" and double_label_required is not True:
        raise D3PatentReviewPacketSemanticError(
            "held-out D3 challenge candidates require independent double review"
        )
    blinding_state = review_design.get("model_output_blinding_state")
    exception_rationale = review_design.get("blinding_exception_rationale")
    if blinding_state == "BLINDED_TO_MODEL_OUTPUT":
        if exception_rationale is not None:
            raise D3PatentReviewPacketSemanticError(
                "blinded review cannot carry a blinding-exception rationale"
            )
    elif blinding_state == "BLINDING_NOT_PRACTICABLE_RECORDED":
        _require_string(exception_rationale, "review_design.blinding_exception_rationale")
    else:
        raise D3PatentReviewPacketSemanticError("model_output_blinding_state is unsupported")

    evidence_packet_sha256 = _canonical_sha256(evidence_packet)
    reviewer_records = _require_list(packet.get("reviewer_records"), "reviewer_records")
    if not reviewer_records:
        raise D3PatentReviewPacketSemanticError("at least one reviewer record is required")
    by_role: dict[str, dict[str, Any]] = {}
    reviewer_refs: set[str] = set()
    reviewed_at_by_role: dict[str, datetime] = {}
    for index, raw_record in enumerate(reviewer_records):
        record = _require_mapping(raw_record, f"reviewer_records[{index}]")
        _require_exact_keys(record, REVIEWER_RECORD_KEYS, f"reviewer_records[{index}]")
        reviewer_ref = _require_string(
            record.get("reviewer_ref"), f"reviewer_records[{index}].reviewer_ref"
        )
        if reviewer_ref in reviewer_refs:
            raise D3PatentReviewPacketSemanticError(
                "reviewer_ref values must be distinct across reviewer roles"
            )
        reviewer_refs.add(reviewer_ref)
        bound_digest = record.get("evidence_packet_sha256")
        if bound_digest != evidence_packet_sha256:
            raise D3PatentReviewPacketSemanticError(
                "every reviewer record must bind the exact canonical evidence_packet SHA-256"
            )
        role = record.get("adjudicator_role")
        if role not in REVIEWER_ROLES:
            raise D3PatentReviewPacketSemanticError("reviewer adjudicator_role is unsupported")
        assert isinstance(role, str)
        if role in by_role:
            raise D3PatentReviewPacketSemanticError("reviewer roles must be unique")
        by_role[role] = record
        if record.get("decision") not in D1_DISPOSITIONS:
            raise D3PatentReviewPacketSemanticError(
                "review decision is outside the approved D1 disposition domain"
            )
        _require_string(record.get("rationale"), f"reviewer_records[{index}].rationale")
        reviewer_binding = _require_mapping(
            record.get("exact_patent_binding"),
            f"reviewer_records[{index}].exact_patent_binding",
        )
        _validate_patent_binding(
            reviewer_binding,
            f"reviewer_records[{index}].exact_patent_binding",
        )
        if _canonical(reviewer_binding) != binding_canonical:
            raise D3PatentReviewPacketSemanticError(
                "every reviewer record must bind the exact same patent family as the packet"
            )
        reviewed_at = _parse_aware_timestamp(
            record.get("timestamp"), f"reviewer_records[{index}].timestamp"
        )
        if reviewed_at < cutoff:
            raise D3PatentReviewPacketSemanticError(
                "review timestamp cannot precede the frozen evidence cutoff"
            )
        reviewed_at_by_role[role] = reviewed_at

    primary = by_role.get("PRIMARY_REVIEWER")
    secondary = by_role.get("SECONDARY_REVIEWER")
    final_adjudicator = by_role.get("FINAL_ADJUDICATOR")
    if primary is None:
        raise D3PatentReviewPacketSemanticError("PRIMARY_REVIEWER is required")
    if double_label_required and secondary is None:
        raise D3PatentReviewPacketSemanticError(
            "SECONDARY_REVIEWER is required for double-labeled items"
        )
    if not double_label_required and secondary is not None:
        raise D3PatentReviewPacketSemanticError(
            "secondary review requires double_label_required=true"
        )

    adjudication = _require_mapping(packet.get("adjudication"), "adjudication")
    _require_exact_keys(adjudication, ADJUDICATION_KEYS, "adjudication")
    state = adjudication.get("state")
    if state not in ADJUDICATION_STATES:
        raise D3PatentReviewPacketSemanticError("adjudication.state is unsupported")
    final_disposition = adjudication.get("final_disposition")
    final_rationale = adjudication.get("final_rationale")

    if state == "AGREE":
        if secondary is None:
            raise D3PatentReviewPacketSemanticError("AGREE requires primary and secondary reviews")
        if primary.get("decision") != secondary.get("decision"):
            raise D3PatentReviewPacketSemanticError(
                "AGREE requires matching primary and secondary dispositions"
            )
        if final_adjudicator is not None:
            raise D3PatentReviewPacketSemanticError(
                "AGREE must not include a FINAL_ADJUDICATOR"
            )
        if final_disposition != primary.get("decision"):
            raise D3PatentReviewPacketSemanticError(
                "AGREE final_disposition must equal the agreed disposition"
            )
        _require_string(final_rationale, "adjudication.final_rationale")
    elif state == "ADJUDICATED":
        if secondary is None:
            raise D3PatentReviewPacketSemanticError(
                "ADJUDICATED requires primary and secondary reviews"
            )
        if primary.get("decision") == secondary.get("decision"):
            raise D3PatentReviewPacketSemanticError(
                "ADJUDICATED requires a real primary/secondary disagreement"
            )
        if final_adjudicator is None:
            raise D3PatentReviewPacketSemanticError(
                "ADJUDICATED requires a FINAL_ADJUDICATOR"
            )
        if final_disposition not in D1_DISPOSITIONS:
            raise D3PatentReviewPacketSemanticError(
                "adjudicated final_disposition is outside the D1 domain"
            )
        if final_adjudicator.get("decision") != final_disposition:
            raise D3PatentReviewPacketSemanticError(
                "FINAL_ADJUDICATOR decision must equal final_disposition"
            )
        rationale = _require_string(final_rationale, "adjudication.final_rationale")
        if final_adjudicator.get("rationale") != rationale:
            raise D3PatentReviewPacketSemanticError(
                "FINAL_ADJUDICATOR rationale must equal final_rationale"
            )
        adjudicator_time = reviewed_at_by_role["FINAL_ADJUDICATOR"]
        if adjudicator_time <= max(
            reviewed_at_by_role["PRIMARY_REVIEWER"],
            reviewed_at_by_role["SECONDARY_REVIEWER"],
        ):
            raise D3PatentReviewPacketSemanticError(
                "FINAL_ADJUDICATOR timestamp must be later than primary/secondary review"
            )
    else:
        if secondary is None:
            raise D3PatentReviewPacketSemanticError(
                "unresolved disagreement requires primary and secondary reviews"
            )
        if primary.get("decision") == secondary.get("decision"):
            raise D3PatentReviewPacketSemanticError(
                "unresolved disagreement requires differing reviewer dispositions"
            )
        if final_adjudicator is not None:
            raise D3PatentReviewPacketSemanticError(
                "unresolved disagreement must not include FINAL_ADJUDICATOR"
            )
        if final_disposition is not None or final_rationale is not None:
            raise D3PatentReviewPacketSemanticError(
                "unresolved disagreement must retain null final disposition/rationale"
            )

    exposure = _require_mapping(packet.get("exposure_control"), "exposure_control")
    _require_exact_keys(exposure, EXPOSURE_KEYS, "exposure_control")
    exposure_status = exposure.get("exposure_status")
    if exposure_status not in {
        "NO_KNOWN_EXPOSURE_REVIEWED",
        "EXPOSED_EXCLUDE_FROM_HELD_OUT",
        "UNKNOWN_REVIEW_REQUIRED",
    }:
        raise D3PatentReviewPacketSemanticError("exposure_status is unsupported")
    _require_string(exposure.get("exposure_register_ref"), "exposure_control.exposure_register_ref")
    held_out_eligible = exposure.get("held_out_eligible")
    if not isinstance(held_out_eligible, bool):
        raise D3PatentReviewPacketSemanticError("held_out_eligible must be boolean")
    if candidate_role == "PILOT_DEVELOPMENT" and held_out_eligible:
        raise D3PatentReviewPacketSemanticError(
            "pilot/development material cannot be held-out eligible"
        )
    if binding.get("family_identity_state") != "RESOLVED" and held_out_eligible:
        raise D3PatentReviewPacketSemanticError(
            "ambiguous patent-family identity cannot be held-out eligible"
        )
    if exposure_status != "NO_KNOWN_EXPOSURE_REVIEWED" and held_out_eligible:
        raise D3PatentReviewPacketSemanticError(
            "held-out eligibility requires completed no-known-exposure review"
        )
    if state == UNRESOLVED_STATE and held_out_eligible:
        raise D3PatentReviewPacketSemanticError(
            "unresolved disagreement cannot be held-out eligible"
        )

    rights = _require_mapping(packet.get("rights_containment"), "rights_containment")
    _require_exact_keys(rights, RIGHTS_KEYS, "rights_containment")
    if rights.get("packet_custody") != "S3_CONTROLLED":
        raise D3PatentReviewPacketSemanticError("review packet custody must remain S3_CONTROLLED")
    if rights.get("patstat_rights_issue") != 210:
        raise D3PatentReviewPacketSemanticError("patstat_rights_issue must remain bound to #210")
    if rights.get("patstat_rights_clearance") is not False:
        raise D3PatentReviewPacketSemanticError("review packet cannot claim PATSTAT rights clearance")
    if rights.get("redistribution_authority_claimed") is not False:
        raise D3PatentReviewPacketSemanticError("review packet cannot claim redistribution authority")

    authority = _require_mapping(packet.get("authority"), "authority")
    _require_exact_keys(authority, AUTHORITY_KEYS, "authority")
    for key in (
        "g2_passed",
        "benchmark_adequacy_established",
        "population_generalization_authority",
        "canonical_s2_authority",
        "publication_authority",
    ):
        if authority.get(key) is not False:
            raise D3PatentReviewPacketSemanticError(f"authority.{key} must remain false")
    if authority.get("assessment_effect") != "NONE":
        raise D3PatentReviewPacketSemanticError("authority.assessment_effect must remain NONE")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PRE-G2 D3 patent challenge review-packet semantics"
    )
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
        if not isinstance(packet, dict):
            raise D3PatentReviewPacketSemanticError("packet root must be an object")
        validate_packet_semantics(packet)
    except (OSError, json.JSONDecodeError, D3PatentReviewPacketSemanticError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print("VALID: PRE-G2 D3 patent challenge semantics satisfied; no authority is conferred")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

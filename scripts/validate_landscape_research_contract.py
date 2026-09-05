#!/usr/bin/env python3
"""Deterministic offline validation for LANDSCAPE_RESEARCH_CONTRACT_v0.1."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "landscape-research-contract-v0.1.schema.json"

EXPECTED_PRIMARY_QUESTIONS = (
    "RQ-01","RQ-02","RQ-03","RQ-04","RQ-05","RQ-06","RQ-07",
)
EXPECTED_SECONDARY_QUESTIONS = (
    "SQ-01","SQ-02","SQ-03","SQ-04","SQ-05","SQ-06",
)
EXPECTED_DELIVERABLES = tuple(f"D{i}" for i in range(19))
EXPECTED_CLAIMS = {
    "CLAIM_ENTITY_EXISTENCE",
    "CLAIM_CAPABILITY_OR_CONTEXT",
    "CLAIM_ACTOR_ROLE",
    "CLAIM_COMMERCIALIZATION_OR_DEPLOYMENT",
    "CLAIM_NEUROAI_BOUNDARY_MEMBERSHIP",
    "CLAIM_CONCENTRATION",
    "CLAIM_PRODUCT_PATENT_RELATION",
    "CLAIM_GOVERNANCE_RELEVANCE",
    "CLAIM_ASSESSMENT_TRIGGER",
    "CLAIM_EVALUATION_READINESS",
}
EXPECTED_EVIDENCE_RULES = {
    "ATTRIBUTABLE_PUBLIC_SOURCE",
    "TRACEABLE_LICENSED_SOURCE",
    "MULTI_SIGNAL_ATTRIBUTABLE_EVIDENCE",
    "EXPERT_REVIEW_REQUIRED",
    "VALIDATED_ANALYTICAL_DENOMINATOR",
    "PATENT_PRODUCT_TIERED_EVIDENCE",
    "MECHANISM_BOUNDED_GOVERNANCE_MAPPING",
    "EXACT_SYSTEM_TRIGGER_EVIDENCE",
    "DOCUMENTED_EVALUATION_PROTOCOL",
}
EXPECTED_DISPOSITIONS = ["INCLUDE","EXCLUDE","BORDERLINE","ABSTAIN"]
EXPECTED_UNIT_CHAIN = [
    "SOURCE","OBSERVATION","CANDIDATE_OR_EXTRACTION",
    "ASSERTION_OR_RELATIONSHIP_OR_EVENT",
]
EXPECTED_STRUCTURED = [
    "PATENT_DATABASE","PUBLICATION_INDEX","CLINICAL_TRIAL_REGISTRY",
    "GRANT_DATABASE","REGULATORY_DATABASE",
]
EXPECTED_OPEN_WORLD = [
    "COMPANY_PRODUCT_PAGE","NEWS","CONFERENCE_MATERIAL",
    "COMMERCIAL_DISCOVERY_DATABASE","EXPERT_NOMINATION","PUBLIC_WEB_MEDIA",
    "MULTILINGUAL_WEB_DISCOVERY","SNOWBALL_CO_MENTION",
]
EXPECTED_GRAY = {
    "GRAY_ATTENTION_VIGILANCE",
    "GRAY_COGNITIVE_AFFECTIVE_STATE",
    "GRAY_ADAPTIVE_INTERFACES",
    "GRAY_COGNITIVE_ENHANCEMENT_TRAINING",
    "GRAY_BEHAVIORAL_PERSONALIZATION",
    "GRAY_NONTRADITIONAL_FORM_FACTOR",
}
EXPECTED_TRACKS = [
    "TRACK_PATENTS","TRACK_COMPANIES_PRODUCTS","TRACK_GRAY_THIRD",
    "TRACK_MULTILINGUAL_REGIONAL",
]
EXPECTED_LINK_TIERS = ["L1","L2","L3","L4"]
EXPECTED_GOVERNANCE_CHAIN = [
    "OBSERVED_PRODUCT_OR_SYSTEM","CAPABILITY","DEPLOYMENT_CONTEXT",
    "MECHANISM","GOVERNANCE_CONCERN","POLICY_INSTRUMENT_OR_RECOMMENDATION",
]
EXPECTED_GATES = ["G2","G3","G4","G5"]


class ValidationError(ValueError):
    """Raised when the research contract violates a fail-closed invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_repo_path(root: Path, raw_path: str) -> Path:
    logical = PurePosixPath(raw_path)
    _require(not logical.is_absolute(), f"unsafe repository-relative path: {raw_path}")
    _require(logical.parts and ".." not in logical.parts, f"unsafe repository-relative path: {raw_path}")
    _require(logical.as_posix() == raw_path, f"non-canonical repository-relative path: {raw_path}")
    target = root.joinpath(*logical.parts)
    _require(
        target.resolve(strict=False).is_relative_to(root.resolve()),
        f"path escapes repository root: {raw_path}",
    )
    return target


def _resolve_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    _require(ref.startswith("#/"), f"unsupported schema ref: {ref}")
    node: Any = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        _require(isinstance(node, dict) and part in node, f"unresolvable schema ref: {ref}")
        node = node[part]
    _require(isinstance(node, dict), f"schema ref must resolve to object: {ref}")
    return node


def _matches_json_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ValidationError(f"unsupported schema type: {type_name}")


def _validate_schema_subset(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> None:
    if "$ref" in schema:
        _validate_schema_subset(value, _resolve_ref(root_schema, schema["$ref"]), root_schema, path)
        return
    if "const" in schema:
        _require(value == schema["const"], f"schema const violation at {path}")
    if "enum" in schema:
        _require(value in schema["enum"], f"schema enum violation at {path}: {value!r}")
    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        _require(any(_matches_json_type(value, kind) for kind in allowed), f"schema type violation at {path}")

    if isinstance(value, str):
        if "minLength" in schema:
            _require(len(value) >= schema["minLength"], f"schema minLength violation at {path}")
        if "pattern" in schema:
            _require(re.search(schema["pattern"], value) is not None, f"schema pattern violation at {path}: {value!r}")

    if isinstance(value, list):
        if "minItems" in schema:
            _require(len(value) >= schema["minItems"], f"schema minItems violation at {path}")
        if "maxItems" in schema:
            _require(len(value) <= schema["maxItems"], f"schema maxItems violation at {path}")
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            _require(len(serialized) == len(set(serialized)), f"schema uniqueItems violation at {path}")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema_subset(item, schema["items"], root_schema, f"{path}[{index}]")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            _require(key in value, f"schema required property missing at {path}.{key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            _require(not extras, f"schema additional properties at {path}: {sorted(extras)}")
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema_subset(value[key], child_schema, root_schema, f"{path}.{key}")


def _ids(rows: Any, key: str, label: str) -> list[str]:
    _require(isinstance(rows, list), f"{label} must be a list")
    values = [row.get(key) if isinstance(row, dict) else None for row in rows]
    _require(all(isinstance(v, str) and v for v in values), f"{label} contains a missing {key}")
    _require(len(values) == len(set(values)), f"{label} {key} values must be unique")
    return values


def validate_document(
    doc: dict[str, Any],
    schema: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> None:
    _require(doc.get("artifact_id") == "LANDSCAPE_RESEARCH_CONTRACT_v0.1", "unexpected artifact_id")
    _require(doc.get("version") == "0.1", "unexpected version")
    _require(doc.get("status") == "PRE_G1_DRAFT", "D1 must remain PRE_G1_DRAFT")
    _require(doc.get("issue") == 181, "D1 must remain bound to issue 181")
    _require(
        isinstance(doc.get("created_against_observatory_main_sha"), str)
        and re.fullmatch(r"[0-9a-f]{40}", doc["created_against_observatory_main_sha"]) is not None,
        "created_against_observatory_main_sha must be a lowercase 40-hex SHA",
    )

    governance = doc.get("governance") or {}
    for key in ("g1_approved","canonical_authority","publication_authority","mutation_authority"):
        _require(governance.get(key) is False, f"governance field {key} must remain false")
    _require(governance.get("requires_human_governance_disposition") is True, "human G1 disposition must remain required")
    _require(governance.get("approval_outcomes_allowed") == ["APPROVE","WITHHOLD","DEFER"], "approval outcomes drifted")
    _require(governance.get("exact_artifact_binding_required_for_g1") is True, "G1 exact-artifact binding must remain required")
    _require(governance.get("governance_disposition_id") is None, "unapproved D1 must not name a governance disposition id")
    _require(governance.get("governance_disposition_path") is None, "unapproved D1 must not name a governance disposition path")

    scope = doc.get("scope") or {}
    _require(scope.get("open_world_completeness_claim") is False, "D1 cannot claim open-world completeness")
    required_non_goals = {
        "Authorize G0 or G1","Authorize publication","Mutate canonical S2 records",
        "Use model consensus as ground truth","Change v4.2 requirement meanings",
        "Expose protected S3 material",
    }
    _require(required_non_goals.issubset(set(scope.get("non_goals") or [])), "required non-goals missing")
    saturation = str(scope.get("protocol_bounded_saturation_semantics") or "")
    _require("never establishes global completeness" in saturation, "saturation semantics must prohibit global completeness")

    qids = _ids(doc.get("questions"), "question_id", "questions")
    _require(tuple(qids) == EXPECTED_PRIMARY_QUESTIONS, "primary questions must contain the seven controlling IDs in order")
    for row in doc["questions"]:
        _require(row.get("tier") == "PRIMARY", f"{row.get('question_id')}: controlling question must remain PRIMARY")
    sqids = _ids(doc.get("secondary_questions"), "question_id", "secondary_questions")
    _require(tuple(sqids) == EXPECTED_SECONDARY_QUESTIONS, "secondary questions must contain the six controlled IDs in order")
    for row in doc["secondary_questions"]:
        _require(row.get("tier") == "SECONDARY", f"{row.get('question_id')}: tier must remain SECONDARY")
        _require(row.get("parent_question_id") in EXPECTED_PRIMARY_QUESTIONS, f"{row.get('question_id')}: unknown parent question")

    deliverables = doc.get("deliverables")
    dids = _ids(deliverables, "deliverable_id", "deliverables")
    _require(tuple(dids) == EXPECTED_DELIVERABLES, "deliverables must map D0 through D18 in order")
    for row in deliverables:
        bindings = row.get("question_bindings") or []
        _require(bindings and set(bindings).issubset(set(EXPECTED_PRIMARY_QUESTIONS)), f"{row.get('deliverable_id')}: invalid question binding")
    d1 = next(row for row in deliverables if row["deliverable_id"] == "D1")
    _require(set(d1["question_bindings"]) == set(EXPECTED_PRIMARY_QUESTIONS), "D1 must bind all seven controlling questions")
    d2 = next(row for row in deliverables if row["deliverable_id"] == "D2")
    _require(d2["question_bindings"] == ["RQ-01","RQ-04","RQ-06","RQ-07"], "D2 substantive question binding drifted")
    d18 = next(row for row in deliverables if row["deliverable_id"] == "D18")
    _require(d18["question_bindings"] == ["RQ-07"], "D18 must bind the exact-system assessment-trigger question")

    evidence_rules = doc.get("evidence_rules") or {}
    _require(set(evidence_rules) == EXPECTED_EVIDENCE_RULES, "evidence rule set mismatch")
    claims = doc.get("claim_classes")
    claim_ids = _ids(claims, "claim_class_id", "claim_classes")
    _require(set(claim_ids) == EXPECTED_CLAIMS, "claim class set mismatch")
    for row in claims:
        _require(set(row.get("question_bindings") or []).issubset(set(EXPECTED_PRIMARY_QUESTIONS)), f"{row.get('claim_class_id')}: unknown question binding")
        _require(set(row.get("allowed_evidence_rules") or []).issubset(EXPECTED_EVIDENCE_RULES), f"{row.get('claim_class_id')}: unknown evidence rule")
        _require(row.get("prohibited_inferences"), f"{row.get('claim_class_id')}: prohibited inferences required")
    product_patent = next(row for row in claims if row["claim_class_id"] == "CLAIM_PRODUCT_PATENT_RELATION")
    _require("Ownership certainty from shared names alone" in product_patent["prohibited_inferences"], "name-only product-patent inference must remain prohibited")

    semantics = doc.get("classification_semantics") or {}
    _require(semantics.get("allowed_dispositions") == EXPECTED_DISPOSITIONS, "classification dispositions drifted")
    for key in (
        "abstention_required_when_evidence_insufficient","borderline_requires_recorded_rationale",
        "proxy_only_cannot_establish_inclusion","inclusion_requires_attributable_evidence",
        "open_world_unknowns_must_remain_explicit",
    ):
        _require(semantics.get(key) is True, f"classification invariant {key} must remain true")
    gray = semantics.get("gray_third") or {}
    _require(gray.get("retrieval_only") is True, "gray third must remain retrieval-only")
    _require(gray.get("canonical_population_class") is False, "gray third must not become a canonical population class")
    gray_ids = {row.get("id") for row in gray.get("search_families") or []}
    _require(gray_ids == EXPECTED_GRAY, "gray-third family set drifted")

    tracks = doc.get("discovery_tracks")
    track_ids = _ids(tracks, "track_id", "discovery_tracks")
    _require(track_ids == EXPECTED_TRACKS, "discovery track set/order drifted")
    track_types = {row["track_id"]: row.get("universe_type") for row in tracks}
    _require(track_types["TRACK_PATENTS"] == "STRUCTURED_DENOMINATED", "patent track must remain structured denominated")
    _require(track_types["TRACK_COMPANIES_PRODUCTS"] == "OPEN_WORLD_PROTOCOL", "company/product track must remain open-world protocol")
    _require(track_types["TRACK_GRAY_THIRD"] == "OPEN_WORLD_PROTOCOL", "gray-third track must remain open-world protocol")

    sources = doc.get("source_classes") or {}
    _require(sources.get("structured_denominated") == EXPECTED_STRUCTURED, "structured denominated source set drifted")
    _require(sources.get("open_world_channels") == EXPECTED_OPEN_WORLD, "open-world channel set drifted")
    _require("COMPANY_PRODUCT_PAGE" not in sources.get("structured_denominated", []), "company/product pages cannot be treated as a structured denominator")
    _require(sources.get("structured_denominator_must_be_explicit") is True, "structured denominator must remain explicit")
    _require(sources.get("open_world_protocol_must_report_stopping_and_marginal_yield") is True, "open-world stopping/yield reporting must remain required")
    _require(sources.get("source_class_does_not_determine_claim_truth") is True, "source class cannot become truth authority")

    _require(doc.get("unit_chain") == EXPECTED_UNIT_CHAIN, "unit chain drifted")
    units = doc.get("units_of_analysis") or {}
    _require(units.get("entity_types") == ["ORGANIZATION","PRODUCT","SYSTEM","PATENT"], "unit/entity type set drifted")
    for key in ("organization_product_distinct","organization_patent_distinct","product_patent_relation_is_separate"):
        _require(units.get(key) is True, f"unit invariant {key} must remain true")

    identity = doc.get("identity_contract") or {}
    for key in (
        "exact_identifiers_preferred","unresolved_literals_preserved","fuzzy_name_match_cannot_merge",
        "parent_subsidiary_distinct_unless_evidenced","acquisition_and_ownership_time_scoped",
        "patent_publication_and_family_distinct","product_family_and_exact_product_distinct",
        "multilingual_aliases_do_not_change_canonical_identity",
    ):
        _require(identity.get(key) is True, f"identity invariant {key} must remain true")

    linkage = doc.get("patent_product_linkage") or {}
    tiers = linkage.get("tiers") or []
    _require([row.get("tier") for row in tiers] == EXPECTED_LINK_TIERS, "L1-L4 tier set/order drifted")
    l4 = next(row for row in tiers if row.get("tier") == "L4")
    _require("never an established" in l4.get("permitted_use",""), "L4 must remain candidate/discovery only")
    for key in ("l4_excluded_from_established_link_counts","l3_quantitative_use_requires_validated_error_study","l1_l2_report_claims_require_human_review","unresolved_links_remain_unresolved"):
        _require(linkage.get(key) is True, f"patent-product invariant {key} must remain true")

    models = doc.get("model_assistance") or {}
    _require(models.get("model_consensus_is_truth") is False, "model consensus cannot become truth")
    _require(models.get("provider_model_and_version_provenance_required") is True, "model provenance must remain required")
    _require(models.get("human_disposition_required_at_governed_boundaries") is True, "human disposition must remain required")
    role_ids = _ids(models.get("roles"), "role", "model roles")
    _require(len(role_ids) == 6, "six model-assistance roles are required")

    review = doc.get("human_review") or {}
    for key in (
        "g1_requires_attributable_human_disposition_over_exact_d1_d2_identity",
        "benchmark_labels_are_human_adjudicated",
        "difficult_gray_and_ambiguous_cases_prioritized_for_expert_review",
        "l1_l2_report_links_require_human_review",
        "l3_links_require_statistically_informative_sample_review",
        "genuine_disagreement_may_remain_unresolved",
    ):
        _require(review.get(key) is True, f"human-review invariant {key} must remain true")
    _require(review.get("required_disposition_fields") == ["decision","rationale","adjudicator_role","timestamp","exact_object_binding"], "human disposition fields drifted")

    mapping = doc.get("governance_mapping") or {}
    _require(mapping.get("chain") == EXPECTED_GOVERNANCE_CHAIN, "governance mapping chain drifted")
    _require(mapping.get("concerns_and_mechanisms_human_defined_before_model_assistance") is True, "governance concerns/mechanisms must remain human-defined before model assistance")
    _require(mapping.get("predicted_company_behavior_allowed") is False, "predicted company behavior must remain prohibited")
    _require(mapping.get("detailed_harmful_use_instructions_are_research_objective") is False, "detailed harmful-use instructions must not become a research objective")
    _require(mapping.get("expert_review_required") is True, "governance mapping review must remain required")

    evaluation = doc.get("evaluation_requirements") or {}
    _require(evaluation.get("quality_before_cost") is True, "quality must remain prior to cost optimization")
    _require(evaluation.get("production_filter_before_held_out_evaluation") is False, "production filtering before held-out evaluation must remain false")
    _require(evaluation.get("thresholds_predeclared_from_research_requirements") is True, "threshold predeclaration must remain required")
    gates = evaluation.get("gate_acceptance") or []
    _require([row.get("gate") for row in gates] == EXPECTED_GATES, "G2-G5 acceptance logic drifted")
    held = evaluation.get("held_out_controls") or {}
    for key in ("human_labels_required","frozen_split_required","hashes_recorded","benchmark_provenance_recorded","tuning_and_test_workflows_separated"):
        _require(held.get(key) is True, f"held-out control {key} must remain true")
    _require(held.get("test_membership_accessible_to_tuning") is False, "held-out test membership must remain inaccessible to tuning")

    containment = doc.get("containment") or {}
    for key in ("s3_private_labels_allowed_in_public_s2","held_out_membership_allowed_in_public_s2","licensed_or_protected_raw_capture_allowed_in_public_s2","private_review_packets_allowed_in_public_s2"):
        _require(containment.get(key) is False, f"containment field {key} must remain false")
    for key in ("licensed_data_requires_purpose_limitation","data_minimization_required","redistribution_rights_checked_before_publication","public_claims_require_permitted_evidence_or_bounded_derived_assertion"):
        _require(containment.get(key) is True, f"containment control {key} must remain true")
    _require(containment.get("candidate_authorization_publication_boundary") == "candidate != authorization != publication", "candidate/authorization/publication boundary drifted")

    change = doc.get("stopping_change_control") or {}
    _require(change.get("global_completeness_from_saturation_allowed") is False, "saturation cannot imply global completeness")
    for key in ("term_or_boundary_change_requires_recorded_rationale","semantic_change_requires_versioned_successor","expert_disposition_does_not_apply_automatically","thresholds_may_not_be_reverse_engineered_to_current_model_performance","historical_control_artifacts_are_not_rewritten"):
        _require(change.get(key) is True, f"change-control invariant {key} must remain true")

    trigger = doc.get("assessment_trigger") or {}
    for key in ("trigger_is_recommendation_only","exact_system_or_configuration_required","sufficient_evidence_required","v4_2_requirement_meanings_unchanged","reopening_requires_separate_attributable_decision"):
        _require(trigger.get(key) is True, f"assessment-trigger invariant {key} must remain true")
    _require(trigger.get("trigger_has_assessment_effect") is False, "landscape trigger must have no assessment effect")

    integrity = doc.get("integrity") or {}
    schema_path = safe_repo_path(root, str(integrity.get("schema_path") or ""))
    validator_path = safe_repo_path(root, str(integrity.get("validator_entrypoint") or ""))
    doc_paths = integrity.get("documentation_paths")
    _require(isinstance(doc_paths, list) and doc_paths, "documentation_paths must be non-empty")
    for raw in doc_paths:
        safe_repo_path(root, raw)
    _require(schema_path == root / "schemas" / "landscape-research-contract-v0.1.schema.json", "schema path binding mismatch")
    _require(validator_path == root / "scripts" / "validate_landscape_research_contract.py", "validator path binding mismatch")
    observed_schema_sha = sha256_bytes(canonical_json_bytes(_load_json(schema_path)))
    _require(integrity.get("schema_sha256") == observed_schema_sha, "schema_sha256 binding mismatch")

    if schema is not None:
        _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema must use JSON Schema 2020-12")
        _require(schema.get("type") == "object", "schema root must be object")
        _require(schema.get("additionalProperties") is False, "schema root must fail closed")
        _validate_schema_subset(doc, schema, schema)
        _require(set(schema.get("required", [])) == set(doc.keys()), "schema required top-level keys must exactly match document keys")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    try:
        artifact = _load_json(args.artifact)
        schema = _load_json(args.schema)
        validate_document(artifact, schema, ROOT)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: LANDSCAPE_RESEARCH_CONTRACT_v0.1 is a fail-closed PRE_G1_DRAFT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

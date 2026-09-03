#!/usr/bin/env python3
"""Deterministic offline semantic validation for D2 CAPABILITY_CONTEXT_TAXONOMY_v0.1.

This script intentionally performs no network access and cannot approve G1 or mutate
canonical Observatory state. It validates only local draft structure and programme
invariants that are important enough to fail closed before human governance review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "capability-context-taxonomy-v0.1.schema.json"

EXPECTED_AXES = (
    "sensing_modality",
    "inferred_state",
    "intervention_output_capability",
    "product_form_factor",
    "deployment_context",
    "regulatory_scientific_claim_state",
)
REQUIRED_SENTINELS = {
    "sensing_modality": {"SENSE_UNKNOWN", "SENSE_OTHER_REVIEW_REQUIRED"},
    "inferred_state": {"STATE_UNKNOWN", "STATE_OTHER_REVIEW_REQUIRED"},
    "intervention_output_capability": {"OUTPUT_UNKNOWN", "OUTPUT_OTHER_REVIEW_REQUIRED"},
    "product_form_factor": {"FORM_UNKNOWN", "FORM_OTHER_REVIEW_REQUIRED"},
    "deployment_context": {"CONTEXT_UNKNOWN", "CONTEXT_OTHER_REVIEW_REQUIRED"},
    "regulatory_scientific_claim_state": {"CLAIM_UNKNOWN", "CLAIM_OTHER_REVIEW_REQUIRED"},
}
EXPECTED_GRAY_FAMILIES = {
    "GRAY_ATTENTION_VIGILANCE",
    "GRAY_COGNITIVE_AFFECTIVE_STATE",
    "GRAY_ADAPTIVE_INTERFACES",
    "GRAY_COGNITIVE_ENHANCEMENT_TRAINING",
    "GRAY_BEHAVIORAL_PERSONALIZATION",
    "GRAY_NONTRADITIONAL_FORM_FACTOR",
}
EXPECTED_CHAIN = [
    "OBSERVED_PRODUCT_OR_SYSTEM",
    "CAPABILITY",
    "DEPLOYMENT_CONTEXT",
    "MECHANISM",
    "GOVERNANCE_CONCERN",
    "POLICY_INSTRUMENT_OR_RECOMMENDATION",
]
EXPECTED_BOUNDED_LANGUAGE = (
    "could implicate concern {concern} under conditions {conditions} through mechanism {mechanism}"
)


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_document(doc: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    _require(doc.get("artifact_id") == "CAPABILITY_CONTEXT_TAXONOMY_v0.1", "unexpected artifact_id")
    _require(doc.get("version") == "0.1", "unexpected taxonomy version")
    _require(doc.get("status") == "PRE_G1_DRAFT", "D2 must remain PRE_G1_DRAFT")

    gov = doc.get("governance", {})
    _require(gov.get("g1_approved") is False, "technical D2 artifact must not approve G1")
    _require(gov.get("canonical_authority") is False, "D2 draft must not carry canonical authority")
    _require(gov.get("publication_authority") is False, "D2 draft must not carry publication authority")
    _require(gov.get("assessment_effect") == "NONE", "D2 draft must not alter assessment state")
    _require(gov.get("requires_human_governance_disposition") is True, "human G1 disposition must remain required")

    policy = doc.get("classification_policy", {})
    for key in (
        "abstention_required_when_evidence_insufficient",
        "unknown_states_must_be_available",
        "other_review_required_states_must_be_available",
        "taxonomy_classification_is_not_inclusion",
        "physiological_proxy_only_cannot_establish_neuroai",
    ):
        _require(policy.get(key) is True, f"classification policy invariant {key} must be true")

    axes = doc.get("axes")
    _require(isinstance(axes, dict), "axes must be an object")
    _require(tuple(axes.keys()) == EXPECTED_AXES, "axes must be present in the controlled order with no extras")

    all_ids: set[str] = set()
    for axis in EXPECTED_AXES:
        terms = axes.get(axis)
        _require(isinstance(terms, list) and terms, f"axis {axis} must contain terms")
        axis_ids: set[str] = set()
        for term in terms:
            _require(isinstance(term, dict), f"axis {axis} term must be an object")
            term_id = term.get("id")
            _require(isinstance(term_id, str) and term_id, f"axis {axis} term missing id")
            _require(term_id not in axis_ids, f"duplicate term id within {axis}: {term_id}")
            _require(term_id not in all_ids, f"duplicate term id across taxonomy: {term_id}")
            axis_ids.add(term_id)
            all_ids.add(term_id)
            _require(isinstance(term.get("label"), str) and term["label"].strip(), f"{term_id} missing label")
            _require(isinstance(term.get("definition"), str) and term["definition"].strip(), f"{term_id} missing definition")
            _require(isinstance(term.get("aliases"), list), f"{term_id} aliases must be a list")
            for alias in term["aliases"]:
                _require(set(alias) == {"language", "text"}, f"{term_id} alias must contain only language/text")
                _require(isinstance(alias["language"], str) and alias["language"], f"{term_id} alias missing language")
                _require(isinstance(alias["text"], str) and alias["text"].strip(), f"{term_id} alias missing text")
        _require(REQUIRED_SENTINELS[axis].issubset(axis_ids), f"axis {axis} missing UNKNOWN/OTHER_REVIEW_REQUIRED sentinels")

    for term in axes["sensing_modality"]:
        if term.get("proxy_only") is True:
            _require(term.get("neural_directness") == "PHYSIOLOGICAL_PROXY", f"proxy-only sensing term {term['id']} must be PHYSIOLOGICAL_PROXY")
            _require(term.get("default_inclusion_evidence_role") == "SUPPORTING_ONLY", f"proxy-only sensing term {term['id']} cannot be primary inclusion evidence")
        if term.get("neural_directness") == "PHYSIOLOGICAL_PROXY":
            _require(term.get("proxy_only") is True, f"physiological proxy {term['id']} must be marked proxy_only")

    gray = doc.get("gray_third", {})
    _require(gray.get("retrieval_only") is True, "gray-third must remain retrieval/boundary-testing only")
    _require(gray.get("canonical_population_class") is False, "gray-third must not be declared a canonical population class")
    gray_ids = {item.get("id") for item in gray.get("search_families", [])}
    _require(gray_ids == EXPECTED_GRAY_FAMILIES, "gray-third search families must match the six blueprint families exactly")

    mapping = doc.get("mapping_scaffold", {})
    _require(mapping.get("status") == "PRE_D12_SCAFFOLD_ONLY", "mapping scaffold must not claim D12 completion")
    _require(mapping.get("chain") == EXPECTED_CHAIN, "mapping chain must preserve capability/context/mechanism/concern separation")
    _require(mapping.get("bounded_language_template") == EXPECTED_BOUNDED_LANGUAGE, "bounded policy language template changed")
    _require(mapping.get("predicted_harm_allowed") is False, "predicted-harm assertions must remain prohibited")
    _require(mapping.get("review_required") is True, "mapping review must remain required")

    multilingual = doc.get("multilingual_policy", {})
    for key in (
        "controlled_ids_language_independent",
        "english_label_is_reference_label_not_identity",
        "translated_terms_are_aliases_only",
        "preserve_original_language_source_metadata",
        "translation_review_required_for_query_pack_promotion",
    ):
        _require(multilingual.get(key) is True, f"multilingual invariant {key} must be true")

    change = doc.get("change_control", {})
    for key in (
        "term_addition_requires_recorded_rationale",
        "term_deletion_or_semantic_change_requires_version_bump",
        "expert_dispositions_may_propose_changes_but_do_not_apply_automatically",
        "g1_approval_requires_exact_d1_d2_identity_binding",
        "technical_validation_cannot_set_g1_approved",
        "future_d12_crosswalk_must_reference_exact_taxonomy_version",
    ):
        _require(change.get(key) is True, f"change-control invariant {key} must be true")

    if schema is not None:
        _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema must use JSON Schema 2020-12")
        _require(schema.get("type") == "object", "schema root must be an object")
        _require(schema.get("additionalProperties") is False, "schema root must fail closed on unknown properties")
        required = set(schema.get("required", []))
        _require(required == set(doc.keys()), "schema required top-level keys must exactly match artifact top-level keys")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()

    try:
        doc = _load_json(args.artifact)
        schema = _load_json(args.schema)
        validate_document(doc, schema)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS: CAPABILITY_CONTEXT_TAXONOMY_v0.1 is structurally coherent and remains PRE_G1_DRAFT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Deterministic offline semantic validation for D2 CAPABILITY_CONTEXT_TAXONOMY_v0.1.

This script intentionally performs no network access and cannot approve G1 or mutate
canonical Observatory state. It validates only local draft structure and programme
invariants that are important enough to fail closed before human governance review.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "capability-context-taxonomy-v0.1.schema.json"
DEFAULT_D1_ARTIFACT = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
DEFAULT_D1_SCHEMA = ROOT / "schemas" / "landscape-research-contract-v0.1.schema.json"
DEFAULT_D1_VALIDATOR = ROOT / "scripts" / "validate_landscape_research_contract.py"

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


def _load_python_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    _require(spec is not None and spec.loader is not None, f"unable to import module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_d1_contract_identity() -> dict[str, Any]:
    validator = _load_python_module(DEFAULT_D1_VALIDATOR, "d1_validator")
    artifact = _load_json(DEFAULT_D1_ARTIFACT)
    schema = _load_json(DEFAULT_D1_SCHEMA)
    validator.validate_document(artifact, schema, ROOT)

    deliverables = artifact.get("deliverables") or []
    d2_row = next(
        (
            row for row in deliverables
            if isinstance(row, dict) and row.get("deliverable_id") == "D2"
        ),
        None,
    )
    _require(d2_row is not None, "D1 must declare the D2 deliverable binding")
    return {
        "artifact_id": artifact.get("artifact_id"),
        "version": artifact.get("version"),
        "created_against_observatory_main_sha": artifact.get(
            "created_against_observatory_main_sha"
        ),
        "artifact_path": "curation/LANDSCAPE_RESEARCH_CONTRACT_v0.1.json",
        "validator_entrypoint": "scripts/validate_landscape_research_contract.py",
        "canonical_json_sha256": validator.sha256_bytes(
            validator.canonical_json_bytes(artifact)
        ),
        "d2_question_bindings": d2_row.get("question_bindings"),
    }


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
    """Validate the exact JSON-Schema subset used by this D2 contract, offline.

    Supported keywords are deliberately explicit. Any new unsupported keyword that
    affects instance validation must be added here before the workflow can claim
    the bundled schema is enforced.
    """
    if "$ref" in schema:
        _validate_schema_subset(value, _resolve_ref(root_schema, schema["$ref"]), root_schema, path)
        return

    if "const" in schema:
        _require(value == schema["const"], f"schema const violation at {path}")
    if "enum" in schema:
        _require(value in schema["enum"], f"schema enum violation at {path}: {value!r}")

    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        _require(
            any(_matches_json_type(value, type_name) for type_name in allowed),
            f"schema type violation at {path}: expected {allowed}",
        )

    if isinstance(value, str):
        if "minLength" in schema:
            _require(len(value) >= schema["minLength"], f"schema minLength violation at {path}")
        if "pattern" in schema:
            import re

            _require(
                re.search(schema["pattern"], value) is not None,
                f"schema pattern violation at {path}: {value!r}",
            )

    if isinstance(value, list):
        if "minItems" in schema:
            _require(len(value) >= schema["minItems"], f"schema minItems violation at {path}")
        if "maxItems" in schema:
            _require(len(value) <= schema["maxItems"], f"schema maxItems violation at {path}")
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            _require(
                len(serialized) == len(set(serialized)),
                f"schema uniqueItems violation at {path}",
            )
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema_subset(item, schema["items"], root_schema, f"{path}[{index}]")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            _require(key in value, f"schema required property missing at {path}.{key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            _require(not extras, f"schema additional properties at {path}: {sorted(extras)}")
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema_subset(value[key], child_schema, root_schema, f"{path}.{key}")


def validate_document(doc: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    _require(
        doc.get("artifact_id") == "CAPABILITY_CONTEXT_TAXONOMY_v0.1",
        "unexpected artifact_id",
    )
    _require(doc.get("version") == "0.1", "unexpected taxonomy version")
    _require(doc.get("status") == "PRE_G1_DRAFT", "D2 must remain PRE_G1_DRAFT")
    d1_binding = doc.get("d1_contract_binding", {})
    _require(isinstance(d1_binding, dict), "d1_contract_binding must be an object")
    expected_d1 = _load_d1_contract_identity()
    for key in (
        "artifact_id",
        "version",
        "created_against_observatory_main_sha",
        "artifact_path",
        "validator_entrypoint",
        "canonical_json_sha256",
        "d2_question_bindings",
    ):
        _require(
            d1_binding.get(key) == expected_d1.get(key),
            f"D1 binding mismatch for {key}",
        )
    _require(
        doc.get("created_against_observatory_main_sha")
        == expected_d1["created_against_observatory_main_sha"],
        "D2 must be created against the same observatory main SHA as D1",
    )

    gov = doc.get("governance", {})
    _require(gov.get("g1_approved") is False, "technical D2 artifact must not approve G1")
    _require(gov.get("canonical_authority") is False, "D2 draft must not carry canonical authority")
    _require(gov.get("publication_authority") is False, "D2 draft must not carry publication authority")
    _require(gov.get("assessment_effect") == "NONE", "D2 draft must not alter assessment state")
    _require(
        gov.get("requires_human_governance_disposition") is True,
        "human G1 disposition must remain required",
    )

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
    _require(
        tuple(axes.keys()) == EXPECTED_AXES,
        "axes must be present in the controlled order with no extras",
    )

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
            _require(
                isinstance(term.get("label"), str) and term["label"].strip(),
                f"{term_id} missing label",
            )
            _require(
                isinstance(term.get("definition"), str) and term["definition"].strip(),
                f"{term_id} missing definition",
            )
            _require(isinstance(term.get("aliases"), list), f"{term_id} aliases must be a list")
            for alias in term["aliases"]:
                _require(
                    set(alias) == {"language", "text"},
                    f"{term_id} alias must contain only language/text",
                )
                _require(
                    isinstance(alias["language"], str) and alias["language"],
                    f"{term_id} alias missing language",
                )
                _require(
                    isinstance(alias["text"], str) and alias["text"].strip(),
                    f"{term_id} alias missing text",
                )
        _require(
            REQUIRED_SENTINELS[axis].issubset(axis_ids),
            f"axis {axis} missing UNKNOWN/OTHER_REVIEW_REQUIRED sentinels",
        )

    for term in axes["sensing_modality"]:
        if term.get("proxy_only") is True:
            _require(
                term.get("neural_directness") == "PHYSIOLOGICAL_PROXY",
                f"proxy-only sensing term {term['id']} must be PHYSIOLOGICAL_PROXY",
            )
            _require(
                term.get("default_inclusion_evidence_role") == "SUPPORTING_ONLY",
                f"proxy-only sensing term {term['id']} cannot be primary inclusion evidence",
            )
        if term.get("neural_directness") == "PHYSIOLOGICAL_PROXY":
            _require(
                term.get("proxy_only") is True,
                f"physiological proxy {term['id']} must be marked proxy_only",
            )

    gray = doc.get("gray_third", {})
    _require(
        gray.get("retrieval_only") is True,
        "gray-third must remain retrieval/boundary-testing only",
    )
    _require(
        gray.get("canonical_population_class") is False,
        "gray-third must not be declared a canonical population class",
    )
    gray_ids = {item.get("id") for item in gray.get("search_families", [])}
    _require(
        gray_ids == EXPECTED_GRAY_FAMILIES,
        "gray-third search families must match the six blueprint families exactly",
    )

    mapping = doc.get("mapping_scaffold", {})
    _require(
        mapping.get("status") == "PRE_D12_SCAFFOLD_ONLY",
        "mapping scaffold must not claim D12 completion",
    )
    _require(
        mapping.get("chain") == EXPECTED_CHAIN,
        "mapping chain must preserve capability/context/mechanism/concern separation",
    )
    _require(
        mapping.get("bounded_language_template") == EXPECTED_BOUNDED_LANGUAGE,
        "bounded policy language template changed",
    )
    _require(
        mapping.get("predicted_harm_allowed") is False,
        "predicted-harm assertions must remain prohibited",
    )
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

    # Validate the exact JSON-Schema subset used by this artifact without
    # third-party dependencies or network access.
    if schema is not None:
        _require(
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            "schema must use JSON Schema 2020-12",
        )
        _require(schema.get("type") == "object", "schema root must be an object")
        _require(
            schema.get("additionalProperties") is False,
            "schema root must fail closed on unknown properties",
        )
        _validate_schema_subset(doc, schema, schema)
        required = set(schema.get("required", []))
        _require(
            required == set(doc.keys()),
            "schema required top-level keys must exactly match artifact top-level keys",
        )


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

    print(
        "PASS: CAPABILITY_CONTEXT_TAXONOMY_v0.1 is structurally coherent "
        "and remains PRE_G1_DRAFT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

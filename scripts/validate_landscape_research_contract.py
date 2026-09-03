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
DEFAULT_ARTIFACT = (
    ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
)
DEFAULT_SCHEMA = (
    ROOT / "schemas" / "landscape-research-contract-v0.1.schema.json"
)
EXPECTED_QUESTIONS = (
    "RQ-01",
    "RQ-02",
    "RQ-03",
    "RQ-04",
    "RQ-05",
    "RQ-06",
    "RQ-07",
)
EXPECTED_DELIVERABLES = {"D1", "D2"}
EXPECTED_CLAIMS = {
    "CLAIM_ENTITY_EXISTENCE",
    "CLAIM_NEUROAI_BOUNDARY_MEMBERSHIP",
    "CLAIM_PRODUCT_PATENT_RELATION",
    "CLAIM_EVALUATION_READINESS",
}
EXPECTED_EVIDENCE_RULES = {
    "ATTRIBUTABLE_PUBLIC_SOURCE",
    "TRACEABLE_LICENSED_SOURCE",
    "MULTI_SIGNAL_ATTRIBUTABLE_EVIDENCE",
    "EXPERT_REVIEW_REQUIRED",
    "EXACT_PRODUCT_REFERENCE_IN_PATENT",
    "EXACT_PATENT_REFERENCE_IN_PRODUCT_MATERIAL",
    "TRIANGULATED_ATTRIBUTABLE_RELATION",
    "DOCUMENTED_EVALUATION_PROTOCOL",
}
EXPECTED_DISPOSITIONS = ("INCLUDE", "EXCLUDE", "BORDERLINE", "ABSTAIN")
EXPECTED_BOUNDED_STRUCTURED = (
    "PATENT_DATABASE",
    "REGULATORY_DATABASE",
    "CLINICAL_TRIAL_REGISTRY",
    "PUBLICATION_INDEX",
    "GRANT_DATABASE",
    "COMPANY_PRODUCT_PAGE",
)
EXPECTED_OPEN_WORLD = (
    "NEWS",
    "CONFERENCE_MATERIAL",
    "THIRD_PARTY_MARKET_REPORT",
    "MULTILINGUAL_WEB_DISCOVERY",
)
EXPECTED_UNIT_CHAIN = (
    "SOURCE",
    "OBSERVATION",
    "CANDIDATE_OR_EXTRACTION",
    "ASSERTION_OR_RELATIONSHIP_OR_EVENT",
)
EXPECTED_EVALUATION_DIMENSIONS = (
    "PRECISION",
    "RECALL",
    "CALIBRATION",
    "UNCERTAINTY_OR_ABSTENTION",
    "SUBGROUP_ANALYSIS",
    "MULTILINGUAL_OR_GRAY_STRATA",
)


class ValidationError(ValueError):
    """Raised when the contract violates a fail-closed invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_repo_path(root: Path, raw_path: str) -> Path:
    logical = PurePosixPath(raw_path)
    _require(
        not logical.is_absolute(),
        f"unsafe repository-relative path: {raw_path}",
    )
    _require(
        logical.parts and ".." not in logical.parts,
        f"unsafe repository-relative path: {raw_path}",
    )
    _require(
        logical.as_posix() == raw_path,
        f"non-canonical repository-relative path: {raw_path}",
    )
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
        _require(
            isinstance(node, dict) and part in node,
            f"unresolvable schema ref: {ref}",
        )
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
        _require(
            any(_matches_json_type(value, kind) for kind in allowed),
            f"schema type violation at {path}",
        )

    if isinstance(value, str):
        if "minLength" in schema:
            _require(
                len(value) >= schema["minLength"],
                f"schema minLength violation at {path}",
            )
        if "pattern" in schema:
            _require(
                re.search(schema["pattern"], value) is not None,
                f"schema pattern violation at {path}: {value!r}",
            )

    if isinstance(value, list):
        if "minItems" in schema:
            _require(
                len(value) >= schema["minItems"],
                f"schema minItems violation at {path}",
            )
        if "maxItems" in schema:
            _require(
                len(value) <= schema["maxItems"],
                f"schema maxItems violation at {path}",
            )
        if schema.get("uniqueItems") is True:
            serialized = [
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in value
            ]
            _require(
                len(serialized) == len(set(serialized)),
                f"schema uniqueItems violation at {path}",
            )
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema_subset(
                    item,
                    schema["items"],
                    root_schema,
                    f"{path}[{index}]",
                )

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            _require(
                key in value,
                f"schema required property missing at {path}.{key}",
            )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            _require(
                not extras,
                f"schema additional properties at {path}: {sorted(extras)}",
            )
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema_subset(
                    value[key],
                    child_schema,
                    root_schema,
                    f"{path}.{key}",
                )


def validate_document(
    doc: dict[str, Any],
    schema: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> None:
    _require(
        doc.get("artifact_id") == "LANDSCAPE_RESEARCH_CONTRACT_v0.1",
        "unexpected artifact_id",
    )
    _require(doc.get("version") == "0.1", "unexpected version")
    _require(doc.get("status") == "PRE_G1_DRAFT", "D1 must remain PRE_G1_DRAFT")
    _require(doc.get("issue") == 181, "D1 must remain bound to issue 181")

    governance = doc.get("governance", {})
    for key in (
        "g1_approved",
        "canonical_authority",
        "publication_authority",
        "mutation_authority",
    ):
        _require(
            governance.get(key) is False,
            f"governance field {key} must remain false",
        )
    _require(
        governance.get("requires_human_governance_disposition") is True,
        "requires_human_governance_disposition must remain true",
    )
    _require(
        governance.get("approval_outcomes_allowed")
        == ["APPROVE", "WITHHOLD", "DEFER"],
        "human disposition outcomes must remain APPROVE/WITHHOLD/DEFER",
    )
    _require(
        governance.get("exact_artifact_binding_required_for_g1") is True,
        "G1 must require exact artifact binding",
    )
    if governance.get("g1_approved") is False:
        _require(
            governance.get("governance_disposition_id") is None,
            "g1_approved=false must not name a disposition id",
        )
        _require(
            governance.get("governance_disposition_path") is None,
            "g1_approved=false must not name a disposition path",
        )

    scope = doc.get("scope", {})
    _require(
        scope.get("open_world_completeness_claim") is False,
        "D1 cannot claim open-world completeness",
    )
    non_goals = scope.get("non_goals") or []
    _require(
        "Authorize G0 or G1" in non_goals,
        "non-goals must explicitly prohibit G0/G1 authorization",
    )
    _require(
        "Expose protected S3 material" in non_goals,
        "non-goals must explicitly prohibit S3 exposure",
    )

    questions = doc.get("questions")
    _require(isinstance(questions, list), "questions must be a list")
    question_ids = [row.get("question_id") for row in questions]
    _require(
        tuple(question_ids) == EXPECTED_QUESTIONS,
        "questions must contain the seven controlled IDs in order",
    )
    _require(len(set(question_ids)) == len(question_ids), "question IDs must be unique")
    tiers = {
        row["question_id"]: row.get("tier")
        for row in questions
        if isinstance(row, dict) and "question_id" in row
    }
    _require(
        sum(tier == "PRIMARY" for tier in tiers.values()) == 3,
        "exactly three questions must be PRIMARY",
    )
    _require(
        sum(tier == "SECONDARY" for tier in tiers.values()) == 4,
        "exactly four questions must be SECONDARY",
    )

    deliverables = doc.get("deliverables")
    _require(
        isinstance(deliverables, list) and deliverables,
        "deliverables must be a non-empty list",
    )
    deliverable_ids = [row.get("deliverable_id") for row in deliverables]
    _require(
        set(deliverable_ids) == EXPECTED_DELIVERABLES,
        "deliverables must contain exactly D1 and D2",
    )
    for row in deliverables:
        bindings = row.get("question_bindings")
        _require(
            isinstance(bindings, list) and bindings,
            f"{row.get('deliverable_id')}: question_bindings required",
        )
        _require(
            set(bindings).issubset(set(EXPECTED_QUESTIONS)),
            f"{row.get('deliverable_id')}: unknown question binding",
        )
    d1 = next(row for row in deliverables if row.get("deliverable_id") == "D1")
    _require(
        set(d1["question_bindings"]) == set(EXPECTED_QUESTIONS),
        "D1 must bind all seven research questions",
    )
    d2 = next(row for row in deliverables if row.get("deliverable_id") == "D2")
    _require(
        "RQ-02" in d2["question_bindings"]
        and "RQ-04" in d2["question_bindings"],
        "D2 binding drift detected",
    )

    evidence_rules = doc.get("evidence_rules")
    _require(
        isinstance(evidence_rules, dict),
        "evidence_rules must be an object",
    )
    _require(
        set(evidence_rules) == EXPECTED_EVIDENCE_RULES,
        "evidence_rules field set mismatch",
    )

    claim_classes = doc.get("claim_classes")
    _require(
        isinstance(claim_classes, list) and claim_classes,
        "claim_classes must be a non-empty list",
    )
    claim_ids = [row.get("claim_class_id") for row in claim_classes]
    _require(set(claim_ids) == EXPECTED_CLAIMS, "claim class set mismatch")
    for row in claim_classes:
        allowed = row.get("allowed_evidence_rules") or []
        _require(
            set(allowed).issubset(EXPECTED_EVIDENCE_RULES),
            f"{row.get('claim_class_id')}: unknown evidence rule",
        )
        _require(
            isinstance(row.get("maximum_interpretation"), str)
            and row["maximum_interpretation"].strip(),
            "maximum_interpretation required",
        )
        prohibited = row.get("prohibited_inferences") or []
        _require(
            isinstance(prohibited, list) and prohibited,
            f"{row.get('claim_class_id')}: prohibited_inferences required",
        )
        if row.get("claim_class_id") == "CLAIM_PRODUCT_PATENT_RELATION":
            _require(
                "Ownership certainty from shared names alone" in prohibited,
                "product-patent relation must prohibit name-only ownership inference",
            )

    semantics = doc.get("classification_semantics", {})
    _require(
        semantics.get("allowed_dispositions") == list(EXPECTED_DISPOSITIONS),
        "classification disposition set changed",
    )
    for key in (
        "abstention_required_when_evidence_insufficient",
        "borderline_requires_recorded_rationale",
        "proxy_only_cannot_establish_inclusion",
        "inclusion_requires_attributable_evidence",
        "open_world_unknowns_must_remain_explicit",
    ):
        _require(semantics.get(key) is True, f"classification invariant {key} must be true")

    source_classes = doc.get("source_classes", {})
    _require(
        source_classes.get("bounded_structured")
        == list(EXPECTED_BOUNDED_STRUCTURED),
        "bounded structured source classes drifted",
    )
    _require(
        source_classes.get("open_world_discovery")
        == list(EXPECTED_OPEN_WORLD),
        "open-world discovery source classes drifted",
    )
    _require(
        source_classes.get("bounded_structured_required_for_canonical_claims") is True,
        "bounded structured source classes must be required for canonical claims",
    )
    _require(
        source_classes.get("open_world_discovery_can_trigger_review_only") is True,
        "open-world discovery must remain review-only",
    )

    _require(
        doc.get("unit_chain") == list(EXPECTED_UNIT_CHAIN),
        "unit_chain must remain source->observation->candidate/"
        "extraction->assertion/relationship/event",
    )

    identity = doc.get("identity_contract", {})
    for key in (
        "organization_identity_distinct_from_product_identity",
        "product_identity_distinct_from_patent_identity",
        "product_patent_relation_requires_separate_evidence",
        "name_similarity_is_never_sufficient_for_merge",
        "multilingual_aliases_do_not_change_canonical_identity",
    ):
        _require(identity.get(key) is True, f"identity invariant {key} must be true")

    evaluation = doc.get("evaluation_requirements", {})
    _require(
        evaluation.get("required_dimensions") == list(EXPECTED_EVALUATION_DIMENSIONS),
        "evaluation required dimensions changed",
    )
    minimums = evaluation.get("minimum_design_requirements", {})
    for key in (
        "precision_required",
        "recall_required",
        "calibration_required",
        "uncertainty_or_abstention_required",
        "subgroup_analysis_required",
        "multilingual_or_gray_strata_required",
    ):
        _require(minimums.get(key) is True, f"evaluation invariant {key} must be true")
    _require(
        evaluation.get("scale_up_without_documented_evaluation") is False,
        "scale-up without documented evaluation must remain false",
    )

    containment = doc.get("containment", {})
    for key in (
        "s3_private_labels_allowed_in_public_s2",
        "held_out_membership_allowed_in_public_s2",
        "licensed_or_protected_raw_capture_allowed_in_public_s2",
        "private_review_packets_allowed_in_public_s2",
    ):
        _require(containment.get(key) is False, f"containment field {key} must remain false")
    _require(
        containment.get("candidate_authorization_publication_boundary") == "candidate != authorization != publication",
        "candidate/authorization/publication boundary changed",
    )

    integrity = doc.get("integrity", {})
    schema_path = safe_repo_path(root, str(integrity.get("schema_path") or ""))
    validator_path = safe_repo_path(root, str(integrity.get("validator_entrypoint") or ""))
    doc_paths = integrity.get("documentation_paths")
    _require(
        isinstance(doc_paths, list) and doc_paths,
        "documentation_paths must be a non-empty list",
    )
    for raw_path in doc_paths:
        safe_repo_path(root, raw_path)
    _require(
        validator_path
        == DEFAULT_ARTIFACT.parents[1]
        / "scripts"
        / "validate_landscape_research_contract.py",
        "validator entrypoint binding mismatch",
    )
    _require(schema_path == DEFAULT_SCHEMA, "schema path binding mismatch")
    observed_schema_sha = sha256_bytes(schema_path.read_bytes())
    _require(
        integrity.get("schema_sha256") == observed_schema_sha,
        "schema_sha256 binding mismatch",
    )

    if schema is not None:
        _require(
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            "schema must use JSON Schema 2020-12",
        )
        _require(schema.get("type") == "object", "schema root must be object")
        _require(
            schema.get("additionalProperties") is False,
            "schema root must fail closed",
        )
        _validate_schema_subset(doc, schema, schema)
        _require(
            set(schema.get("required", [])) == set(doc.keys()),
            "schema required top-level keys must exactly match document keys",
        )


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
    print(
        "PASS: LANDSCAPE_RESEARCH_CONTRACT_v0.1 remains a fail-closed "
        "PRE_G1_DRAFT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

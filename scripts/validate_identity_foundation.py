from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "schemas" / "vnext"
NAMESPACES = ROOT / "identity" / "namespaces-v0.1.json"
FIXTURE = ROOT / "fixtures" / "vnext" / "identity-bundle.synthetic.json"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


NS_VALIDATOR = Draft202012Validator(_load_schema("identifier-namespace.schema.json"), format_checker=FormatChecker())
XID_VALIDATOR = Draft202012Validator(_load_schema("external-identifier.schema.json"), format_checker=FormatChecker())
CANDIDATE_VALIDATOR = Draft202012Validator(_load_schema("entity-resolution-candidate.schema.json"), format_checker=FormatChecker())
DECISION_VALIDATOR = Draft202012Validator(_load_schema("entity-resolution-decision.schema.json"), format_checker=FormatChecker())


def _structural(validator: Draft202012Validator, obj: dict, label: str) -> None:
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        error = errors[0]
        path = ".".join(map(str, error.path)) or "<root>"
        raise ValueError(f"{label}:{path}: {error.message}")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_namespace_registry(registry: dict | None = None) -> dict[str, dict]:
    if registry is None:
        registry = json.loads(NAMESPACES.read_text())
    if registry.get("status") != "CONTROLLED_VOCABULARY_NOT_IDENTITY_AUTHORITY":
        raise ValueError("namespace registry authority boundary is invalid")
    by_id: dict[str, dict] = {}
    for row in registry.get("records", []):
        _structural(NS_VALIDATOR, row, row.get("namespace_id", "IDENTIFIER_NAMESPACE"))
        namespace_id = row["namespace_id"]
        if namespace_id in by_id:
            raise ValueError(f"duplicate namespace_id: {namespace_id}")
        try:
            re.compile(row["pattern"])
        except re.error as exc:
            raise ValueError(f"invalid namespace regex: {namespace_id}") from exc
        by_id[namespace_id] = row
    if not by_id:
        raise ValueError("namespace registry is empty")
    return by_id


def normalize_value(observed_value: str, namespace: dict) -> str:
    rule = namespace["normalization"]
    value = observed_value.strip() if rule["trim"] else observed_value
    for prefix in rule["strip_prefixes"]:
        if value[: len(prefix)].casefold() == prefix.casefold():
            value = value[len(prefix):]
            break
    if rule["case"] == "LOWER":
        value = value.lower()
    elif rule["case"] == "UPPER":
        value = value.upper()
    return value


def validate_external_identifier(record: dict, *, namespaces: dict[str, dict], entity_types: dict[str, str], source_observation_ids: set[str]) -> bool:
    _structural(XID_VALIDATOR, record, record.get("identifier_record_id", "EXTERNAL_IDENTIFIER"))
    namespace = namespaces.get(record["namespace_id"])
    if namespace is None:
        raise ValueError(f"unknown namespace: {record['namespace_id']}")
    if record["entity_id"] not in entity_types:
        raise ValueError(f"dangling entity reference: {record['entity_id']}")
    entity_type = entity_types[record["entity_id"]]
    if entity_type not in namespace["allowed_entity_types"]:
        raise ValueError(f"namespace {record['namespace_id']} is not allowed for entity type {entity_type}")
    if record["source_observation_id"] not in source_observation_ids:
        raise ValueError(f"dangling source observation: {record['source_observation_id']}")
    expected = normalize_value(record["observed_value"], namespace)
    if record["normalized_value"] != expected:
        raise ValueError(f"normalization mismatch for {record['identifier_record_id']}")
    if re.fullmatch(namespace["pattern"], record["normalized_value"]) is None:
        raise ValueError(f"malformed normalized identifier for namespace {record['namespace_id']}")
    if "accepted_at" in record and _parse_time(record["accepted_at"]) < _parse_time(record["observed_at"]):
        raise ValueError("accepted_at precedes observed_at")
    if record["resolution_state"] == "SUPERSEDED":
        if _parse_time(record["superseded_at"]) < _parse_time(record["accepted_at"]):
            raise ValueError("superseded_at precedes accepted_at")
        if record["successor_record_id"] == record["identifier_record_id"]:
            raise ValueError("identifier cannot supersede itself")
    return True


def validate_bundle(bundle: dict, namespace_registry: dict | None = None) -> bool:
    if bundle.get("synthetic") is not True:
        raise ValueError("identity foundation fixture must be explicitly synthetic")
    entity_types = bundle.get("entity_types", {})
    source_observation_ids = set(bundle.get("source_observation_ids", []))
    if len(source_observation_ids) != len(bundle.get("source_observation_ids", [])):
        raise ValueError("duplicate source observation id")

    namespaces = load_namespace_registry(namespace_registry)

    identifiers = bundle.get("external_identifiers", [])
    identifier_by_id: dict[str, dict] = {}
    accepted_keys: dict[tuple[str, str], str] = {}
    for record in identifiers:
        validate_external_identifier(record, namespaces=namespaces, entity_types=entity_types, source_observation_ids=source_observation_ids)
        record_id = record["identifier_record_id"]
        if record_id in identifier_by_id:
            raise ValueError(f"duplicate identifier_record_id: {record_id}")
        identifier_by_id[record_id] = record
        if record["resolution_state"] == "ACCEPTED":
            key = (record["namespace_id"], record["normalized_value"])
            previous_entity = accepted_keys.get(key)
            if previous_entity is not None and previous_entity != record["entity_id"]:
                raise ValueError(f"accepted identifier collision: {key[0]}:{key[1]}")
            accepted_keys[key] = record["entity_id"]

    for record in identifiers:
        if record["resolution_state"] == "SUPERSEDED":
            successor = identifier_by_id.get(record["successor_record_id"])
            if successor is None:
                raise ValueError("identifier successor_record_id is dangling")
            if successor["entity_id"] != record["entity_id"] or successor["namespace_id"] != record["namespace_id"]:
                raise ValueError("identifier successor changes entity or namespace")

    known_evidence = source_observation_ids | set(identifier_by_id)
    candidates = bundle.get("resolution_candidates", [])
    candidate_by_id: dict[str, dict] = {}
    for candidate in candidates:
        _structural(CANDIDATE_VALIDATOR, candidate, candidate.get("candidate_id", "ENTITY_RESOLUTION_CANDIDATE"))
        candidate_id = candidate["candidate_id"]
        if candidate_id in candidate_by_id:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        if candidate["left_entity_id"] == candidate["right_entity_id"]:
            raise ValueError("entity resolution candidate cannot self-match")
        for entity_id in (candidate["left_entity_id"], candidate["right_entity_id"]):
            if entity_id not in entity_types:
                raise ValueError(f"dangling entity reference: {entity_id}")
        if entity_types[candidate["left_entity_id"]] != entity_types[candidate["right_entity_id"]]:
            raise ValueError("entity resolution candidate crosses entity types")
        for signal in candidate["signals"]:
            for reference in signal["evidence_references"]:
                if reference not in known_evidence:
                    raise ValueError(f"dangling candidate evidence reference: {reference}")
        candidate_by_id[candidate_id] = candidate

    decisions = bundle.get("resolution_decisions", [])
    decision_ids: set[str] = set()
    decided_candidates: set[str] = set()
    expected_effect = {"SAME_ENTITY": "MERGE_SUCCESSOR_REQUIRED", "KEEP_DISTINCT": "NO_MERGE", "INSUFFICIENT_EVIDENCE": "NO_CANONICAL_EFFECT"}
    for decision in decisions:
        _structural(DECISION_VALIDATOR, decision, decision.get("decision_id", "ENTITY_RESOLUTION_DECISION"))
        decision_id = decision["decision_id"]
        if decision_id in decision_ids:
            raise ValueError(f"duplicate decision_id: {decision_id}")
        decision_ids.add(decision_id)
        candidate = candidate_by_id.get(decision["candidate_id"])
        if candidate is None:
            raise ValueError(f"dangling candidate reference: {decision['candidate_id']}")
        if decision["candidate_id"] in decided_candidates:
            raise ValueError(f"contradictory or duplicate final decision for candidate: {decision['candidate_id']}")
        decided_candidates.add(decision["candidate_id"])
        if decision["left_entity_id"] != candidate["left_entity_id"] or decision["right_entity_id"] != candidate["right_entity_id"]:
            raise ValueError("decision entity pair does not match candidate")
        if decision["canonical_effect"] != expected_effect[decision["disposition"]]:
            raise ValueError("decision canonical_effect is inconsistent with disposition")
        if candidate["candidate_state"] != "ADJUDICATED":
            raise ValueError("decision requires candidate_state ADJUDICATED")
        if _parse_time(decision["decided_at"]) < _parse_time(candidate["created_at"]):
            raise ValueError("decision predates candidate")
        for reference in decision["evidence_references"]:
            if reference not in known_evidence:
                raise ValueError(f"dangling decision evidence reference: {reference}")

    for candidate in candidates:
        if candidate["candidate_state"] == "ADJUDICATED" and candidate["candidate_id"] not in decided_candidates:
            raise ValueError("adjudicated candidate lacks decision")
        if candidate["candidate_state"] == "OPEN" and candidate["candidate_id"] in decided_candidates:
            raise ValueError("open candidate cannot have final decision")

    return True


def main() -> None:
    bundle = json.loads(FIXTURE.read_text())
    validate_bundle(bundle)
    print("PASS identity foundation: " f"{len(load_namespace_registry())} namespaces, " f"{len(bundle['external_identifiers'])} identifiers, " f"{len(bundle['resolution_candidates'])} candidates, " f"{len(bundle['resolution_decisions'])} decisions")


if __name__ == "__main__":
    main()

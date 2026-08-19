from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]
SCHEMA_DIR = ROOT / "schemas" / "vnext"
VOCABULARY = ROOT / "ontology" / "vocabulary-v0.1.json"
PREDICATES = ROOT / "ontology" / "predicates-v0.1.json"

SCHEMA_BY_KIND = {
    "ENTITY": "entity.schema.json",
    "ASSERTION": "assertion.schema.json",
    "RELATIONSHIP": "relationship.schema.json",
    "EVENT": "event.schema.json",
    "SOURCE_OBSERVATION": "source-observation.schema.json",
}

ID_FIELD_BY_KIND = {
    "ENTITY": "entity_id",
    "ASSERTION": "assertion_id",
    "RELATIONSHIP": "relationship_id",
    "EVENT": "event_id",
    "SOURCE_OBSERVATION": "source_observation_id",
}

COLLECTION_BY_KIND = {
    "ENTITY": "entities",
    "ASSERTION": "assertions",
    "RELATIONSHIP": "relationships",
    "EVENT": "events",
    "SOURCE_OBSERVATION": "source_observations",
}


class ContractError(ValueError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_temporal(value: str) -> datetime:
    if "T" not in value:
        d = date.fromisoformat(value)
        return datetime.combine(d, time.min, tzinfo=timezone.utc)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ContractError(f"datetime lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _record_id(record: dict[str, Any]) -> str:
    kind = record["record_kind"]
    return record[ID_FIELD_BY_KIND[kind]]


def _validate_temporal(record: dict[str, Any]) -> None:
    rid = _record_id(record)
    valid = record.get("valid_time")
    if valid:
        start = valid.get("valid_from")
        end = valid.get("valid_to")
        if start and end and _parse_temporal(start) > _parse_temporal(end):
            raise ContractError(f"{rid}: valid_from is after valid_to")

    recorded = record.get("recorded_at")
    accepted = record.get("accepted_at")
    superseded = record.get("superseded_at")
    if recorded and accepted and _parse_temporal(recorded) > _parse_temporal(accepted):
        raise ContractError(f"{rid}: recorded_at is after accepted_at")
    if accepted and superseded and _parse_temporal(accepted) >= _parse_temporal(superseded):
        raise ContractError(f"{rid}: superseded_at must be after accepted_at")


def _validate_value_type(assertion: dict[str, Any]) -> None:
    if "value" not in assertion:
        return
    value_type = assertion["value_type"]
    value = assertion["value"]
    ok = {
        "STRING": isinstance(value, str),
        "NUMBER": isinstance(value, (int, float)) and not isinstance(value, bool),
        "INTEGER": isinstance(value, int) and not isinstance(value, bool),
        "BOOLEAN": isinstance(value, bool),
        "DATE": isinstance(value, str),
        "DATETIME": isinstance(value, str),
        "URI": isinstance(value, str),
        "IDENTIFIER": isinstance(value, str),
    }[value_type]
    if not ok:
        raise ContractError(
            f"{assertion['assertion_id']}: value is incompatible with value_type {value_type}"
        )
    if value_type in {"DATE", "DATETIME"}:
        _parse_temporal(value)


def validate_bundle(bundle_path: Path) -> dict[str, int]:
    vocabulary = load_json(VOCABULARY)
    predicate_registry = load_json(PREDICATES)
    predicates = {row["id"]: row for row in predicate_registry["predicates"]}

    validators: dict[str, Draft202012Validator] = {}
    for kind, filename in SCHEMA_BY_KIND.items():
        schema = load_json(SCHEMA_DIR / filename)
        Draft202012Validator.check_schema(schema)
        validators[kind] = Draft202012Validator(schema, format_checker=FormatChecker())

    bundle = load_json(bundle_path)
    records: list[dict[str, Any]] = []
    for kind, collection in COLLECTION_BY_KIND.items():
        for record in bundle.get(collection, []):
            if record.get("record_kind") != kind:
                raise ContractError(
                    f"{collection}: expected record_kind {kind}, got {record.get('record_kind')}"
                )
            validators[kind].validate(record)
            records.append(record)

    ids: dict[str, dict[str, Any]] = {}
    for record in records:
        rid = _record_id(record)
        if rid in ids:
            raise ContractError(f"duplicate record id: {rid}")
        ids[rid] = record
        _validate_temporal(record)

    entities = {
        row["entity_id"]: row
        for row in bundle.get("entities", [])
    }
    source_ids = {
        row["source_observation_id"]
        for row in bundle.get("source_observations", [])
    }
    assertion_ids = {
        row["assertion_id"]
        for row in bundle.get("assertions", [])
    }

    for record in records:
        if record["record_kind"] in {"ENTITY", "ASSERTION", "RELATIONSHIP", "EVENT"}:
            for source_id in record.get("source_observation_ids", []):
                if source_id not in source_ids:
                    raise ContractError(
                        f"{_record_id(record)}: dangling source observation {source_id}"
                    )
        successor = record.get("successor_record_id")
        if successor and successor not in ids:
            raise ContractError(
                f"{_record_id(record)}: dangling successor record {successor}"
            )

    for assertion in bundle.get("assertions", []):
        subject = entities.get(assertion["subject_id"])
        if subject is None:
            raise ContractError(
                f"{assertion['assertion_id']}: dangling subject {assertion['subject_id']}"
            )
        predicate = predicates.get(assertion["predicate"])
        if predicate is None:
            raise ContractError(
                f"{assertion['assertion_id']}: unknown predicate {assertion['predicate']}"
            )
        if subject["entity_type"] not in predicate["subject_types"]:
            raise ContractError(
                f"{assertion['assertion_id']}: subject type {subject['entity_type']} is invalid for {assertion['predicate']}"
            )
        if "object_id" in assertion:
            if predicate["object_mode"] != "ENTITY":
                raise ContractError(
                    f"{assertion['assertion_id']}: predicate {assertion['predicate']} does not accept entity objects"
                )
            obj = entities.get(assertion["object_id"])
            if obj is None:
                raise ContractError(
                    f"{assertion['assertion_id']}: dangling object {assertion['object_id']}"
                )
            if obj["entity_type"] not in predicate["object_types"]:
                raise ContractError(
                    f"{assertion['assertion_id']}: object type {obj['entity_type']} is invalid for {assertion['predicate']}"
                )
        else:
            if predicate["object_mode"] != "VALUE":
                raise ContractError(
                    f"{assertion['assertion_id']}: predicate {assertion['predicate']} requires an entity object"
                )
            if assertion["value_type"] not in predicate["value_types"]:
                raise ContractError(
                    f"{assertion['assertion_id']}: value_type {assertion['value_type']} is invalid for {assertion['predicate']}"
                )
            _validate_value_type(assertion)

    for relationship in bundle.get("relationships", []):
        subject = entities.get(relationship["subject_id"])
        obj = entities.get(relationship["object_id"])
        if subject is None:
            raise ContractError(
                f"{relationship['relationship_id']}: dangling subject {relationship['subject_id']}"
            )
        if obj is None:
            raise ContractError(
                f"{relationship['relationship_id']}: dangling object {relationship['object_id']}"
            )
        predicate = predicates.get(relationship["predicate"])
        if predicate is None:
            raise ContractError(
                f"{relationship['relationship_id']}: unknown predicate {relationship['predicate']}"
            )
        if predicate["object_mode"] != "ENTITY":
            raise ContractError(
                f"{relationship['relationship_id']}: predicate {relationship['predicate']} is not a relationship predicate"
            )
        if subject["entity_type"] not in predicate["subject_types"]:
            raise ContractError(
                f"{relationship['relationship_id']}: invalid subject type for {relationship['predicate']}"
            )
        if obj["entity_type"] not in predicate["object_types"]:
            raise ContractError(
                f"{relationship['relationship_id']}: invalid object type for {relationship['predicate']}"
            )
        for assertion_id in relationship.get("assertion_ids", []):
            if assertion_id not in assertion_ids:
                raise ContractError(
                    f"{relationship['relationship_id']}: dangling assertion {assertion_id}"
                )

    for event in bundle.get("events", []):
        for participant in event["participants"]:
            if participant["entity_id"] not in entities:
                raise ContractError(
                    f"{event['event_id']}: dangling participant {participant['entity_id']}"
                )

    expected = {
        "entity_types": set(vocabulary["entity_types"]),
        "event_types": set(vocabulary["event_types"]),
        "evidence_states": set(vocabulary["evidence_states"]),
        "rights_classes": set(vocabulary["rights_classes"]),
        "resolution_states": set(vocabulary["resolution_states"]),
    }
    schema_checks = {
        "entity_types": set(load_json(SCHEMA_DIR / "entity.schema.json")["properties"]["entity_type"]["enum"]),
        "event_types": set(load_json(SCHEMA_DIR / "event.schema.json")["properties"]["event_type"]["enum"]),
        "evidence_states": set(load_json(SCHEMA_DIR / "assertion.schema.json")["properties"]["evidence_state"]["enum"]),
        "rights_classes": set(load_json(SCHEMA_DIR / "source-observation.schema.json")["properties"]["rights_class"]["enum"]),
        "resolution_states": set(load_json(SCHEMA_DIR / "entity.schema.json")["properties"]["resolution_state"]["enum"]),
    }
    if expected != schema_checks:
        raise ContractError("schema enums drift from the controlled vocabulary")

    return {name: len(bundle.get(collection, [])) for name, collection in COLLECTION_BY_KIND.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "bundle",
        nargs="?",
        type=Path,
        default=ROOT / "fixtures" / "vnext" / "core-bundle.json",
    )
    args = parser.parse_args()
    counts = validate_bundle(args.bundle)
    print(json.dumps({"status": "PASS", "counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

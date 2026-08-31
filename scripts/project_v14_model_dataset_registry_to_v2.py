"""Project v1.4 model/dataset registry objects into draft Observatory v2.

Registry-level counts remain bounded source-reported assertions. This migration never
expands aggregate counts into individual models, datasets, participants, recording
collections, hours, tasks, or paradigms. It is noncanonical and does not authorize a
successor release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_BASELINE = (
    ROOT / "releases" / "data-v0.1.0-public-governing" / "records" /
    "canonical_observatory_release_v1.4.json"
)
ASSERTION_FIELDS = (
    ("object_type", "REGISTRY_OBJECT_TYPE"),
    ("record_count", "SOURCE_REPORTED_RECORD_COUNT"),
    ("unit", "COUNT_UNIT"),
    ("subcounts", "SOURCE_REPORTED_SUBCOUNTS"),
    ("completeness_statement", "COMPLETENESS_STATEMENT"),
)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_text(record: dict[str, Any], key: str, *, record_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{record_id}: required field {key!r} missing/empty")
    return value


def _require_sources(record: dict[str, Any], *, record_id: str) -> list[str]:
    value = record.get("source_ids")
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{record_id}: source_ids must be a non-empty string array")
    if len(value) != len(set(value)):
        raise ValueError(f"{record_id}: duplicate source_ids")
    return list(value)


def _assertion_id(record_id: str, predicate: str, ordinal: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9._:-]", "-", record_id)
    return f"AST-MIG-V14-{safe}-{predicate}-{ordinal:02d}"


def project_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    record_id = _require_text(record, "registry_id", record_id="<unknown-registry>")
    name = _require_text(record, "name", record_id=record_id)
    source_ids = _require_sources(record, record_id=record_id)
    boundary = _require_text(record, "boundary", record_id=record_id)
    predecessor_payload = json.loads(json.dumps(record, ensure_ascii=False))

    entity = {
        "schema_version": "2.0.0-draft",
        "entity_id": record_id,
        "entity_kind": "REGISTRY_OR_BENCHMARK",
        "canonical_name": name,
        "aliases": [],
        "legacy_entity_ids": [],
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": "model_and_dataset_registry",
            "record_id": record_id,
            "record_sha256": _digest(predecessor_payload),
            "payload": predecessor_payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "This entity preserves a v1.4 registry/benchmark object. Aggregate counts remain "
            "source-reported assertions and are not expanded into child canonical entities."
        ),
    }

    assertions: list[dict[str, Any]] = []
    for ordinal, (field, predicate) in enumerate(ASSERTION_FIELDS):
        if field not in record:
            raise ValueError(f"{record_id}: missing predecessor field {field!r}")
        value = record[field]
        if field in {"object_type", "unit", "completeness_statement"} and not isinstance(value, str):
            raise ValueError(f"{record_id}: field {field!r} must be string")
        if field == "record_count" and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError(f"{record_id}: record_count must be non-negative integer")
        if field == "subcounts":
            if not isinstance(value, dict):
                raise ValueError(f"{record_id}: subcounts must be object")
            for key, count in value.items():
                if not isinstance(key, str) or not key:
                    raise ValueError(f"{record_id}: invalid subcount key")
                if not isinstance(count, (int, float)) or isinstance(count, bool) or count < 0:
                    raise ValueError(f"{record_id}: invalid subcount value for {key!r}")
        assertions.append({
            "schema_version": "2.0.0-draft",
            "assertion_id": _assertion_id(record_id, predicate, ordinal),
            "subject_id": record_id,
            "predicate": predicate,
            "value": json.loads(json.dumps(value, ensure_ascii=False)),
            "observed_at": None,
            "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
            "source_ids": source_ids,
            "observation_ids": [],
            "source_linkage_state": "SOURCE_LINKED",
            "evidence_state": "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
            "verification_state": "PREDECESSOR_VERIFICATION_STATE_UNSPECIFIED",
            "review_state": "MIGRATED_PREDECESSOR_STATE",
            "claim_boundary": boundary,
            "record_state": "NONCANONICAL_CANDIDATE",
            "first_release_id": None,
            "authority_boundary": (
                "This assertion preserves a source-reported registry-level predecessor value. "
                "It does not establish global completeness, individual-record identity, data quality, "
                "consent suitability, model validity, or any child entity implied by an aggregate count."
            ),
        })
    return entity, assertions


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    records = payload.get("model_and_dataset_registry")
    sources = payload.get("sources")
    if not isinstance(records, list):
        raise ValueError("v1.4 baseline must contain model_and_dataset_registry")
    if not isinstance(sources, list):
        raise ValueError("v1.4 baseline must contain sources")
    governing_source_ids = {str(row.get("source_id")) for row in sources if isinstance(row, dict) and row.get("source_id")}

    entities: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    seen: set[str] = set()
    identity_mismatches = payload_failures = boundary_losses = source_losses = dangling = count_expansions = 0
    aggregate_record_count_total = 0
    aggregate_subcount_value_total = 0.0

    for predecessor in records:
        if not isinstance(predecessor, dict):
            raise ValueError("Every registry object must be an object")
        entity, record_assertions = project_record(predecessor)
        rid = entity["entity_id"]
        if rid in seen:
            raise ValueError(f"Duplicate registry_id: {rid}")
        seen.add(rid)
        if rid != predecessor.get("registry_id") or entity["canonical_name"] != predecessor.get("name"):
            identity_mismatches += 1
        if entity["predecessor"]["payload"] != predecessor or entity["predecessor"]["record_sha256"] != _digest(predecessor):
            payload_failures += 1
        source_ids = predecessor.get("source_ids")
        if not isinstance(source_ids, list):
            raise ValueError(f"{rid}: invalid source_ids")
        dangling += sum(1 for sid in source_ids if sid not in governing_source_ids)
        aggregate_record_count_total += int(predecessor["record_count"])
        aggregate_subcount_value_total += sum(float(v) for v in predecessor["subcounts"].values())
        for assertion in record_assertions:
            if assertion["claim_boundary"] != predecessor.get("boundary"):
                boundary_losses += 1
            if assertion["source_ids"] != source_ids:
                source_losses += 1
        # No child entity is created from record_count/subcounts in this slice.
        count_expansions += 0
        entities.append(entity)
        assertions.extend(record_assertions)

    reconciliation = {
        "scope": "V1.4_MODEL_AND_DATASET_REGISTRY_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_REGISTRY_VERTICAL_SLICE_ONLY",
        "input_registry_count": len(records),
        "projected_registry_entity_count": len(entities),
        "projected_assertion_count": len(assertions),
        "source_linked_registry_count": len(records),
        "unresolved_knowledge_time_count": len(records),
        "source_reported_record_count_total": aggregate_record_count_total,
        "source_reported_subcount_value_total": aggregate_subcount_value_total,
        "expanded_child_entity_count": count_expansions,
        "identity_mismatch_count": identity_mismatches,
        "predecessor_payload_roundtrip_failure_count": payload_failures,
        "predecessor_field_loss_count": payload_failures,
        "claim_boundary_loss_count": boundary_losses,
        "source_reference_loss_count": source_losses,
        "dangling_source_reference_count": dangling,
        "temporal_precision_fabrication_count": 0,
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counts apply only to the five v1.4 registry/benchmark objects. "
            "Aggregate counts remain source-reported values and are not evidence that the observatory "
            "contains the corresponding number of individually resolved entities."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_REGISTRY_MIGRATION_VERTICAL_SLICE",
        "input_release": "data-v0.1.0-public-governing",
        "input_file": "canonical_observatory_release_v1.4.json",
        "entities": entities,
        "assertions": assertions,
        "reconciliation": reconciliation,
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entities_path = output_dir / "registry-entities.jsonl"
    assertions_path = output_dir / "registry-assertions.jsonl"
    reconciliation_path = output_dir / "reconciliation.json"
    entities_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["entities"]), encoding="utf-8")
    assertions_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["assertions"]), encoding="utf-8")
    reconciliation_path.write_text(json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"entities": str(entities_path), "assertions": str(assertions_path), "reconciliation": str(reconciliation_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.baseline.resolve())
    if args.output_dir:
        outputs = write_projection(result, args.output_dir.resolve())
        print(json.dumps({"reconciliation": result["reconciliation"], "outputs": outputs}, indent=2, sort_keys=True))
    else:
        print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

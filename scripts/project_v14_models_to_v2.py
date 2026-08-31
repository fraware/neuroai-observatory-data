"""Project v1.4 representative model records into draft Observatory v2 entities/assertions.

This stacked, noncanonical migration slice preserves all predecessor model payloads and
source references. `source_system_id` is retained as a bounded predecessor reference
assertion only; this slice does not claim that a system entity/crosswalk has already
been resolved. It does not authorize a v2 successor.
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
    ROOT
    / "releases"
    / "data-v0.1.0-public-governing"
    / "records"
    / "canonical_observatory_release_v1.4.json"
)

ASSERTION_FIELDS = (
    ("source_system_id", "SOURCE_SYSTEM_REFERENCE"),
    ("developer", "DEVELOPER_REPRESENTATION"),
    ("modality", "MODALITY"),
    ("model_category", "MODEL_CATEGORY"),
    ("publication_state", "PUBLICATION_STATE"),
    ("version", "VERSION_LABEL"),
    ("benchmark_scope", "BENCHMARK_SCOPE"),
    ("checkpoint_state", "CHECKPOINT_STATE"),
    ("license_state", "LICENSE_STATE"),
    ("dataset_lineage_state", "DATASET_LINEAGE_STATE"),
    ("assurance_assessment_available", "ASSURANCE_ASSESSMENT_AVAILABLE"),
    ("verification_state", "VERIFICATION_STATE"),
)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _temporal_value(raw: str) -> dict[str, str]:
    if re.fullmatch(r"\d{4}", raw):
        precision = "YEAR"
    elif re.fullmatch(r"\d{4}-\d{2}", raw):
        precision = "MONTH"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        precision = "DATE"
    elif "T" in raw:
        precision = "TIMESTAMP"
    else:
        precision = "UNRESOLVED"
    return {"value": raw, "precision": precision}


def _require_text(record: dict[str, Any], key: str, *, model_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{model_id}: required predecessor field {key!r} is missing/empty")
    return value


def _require_sources(record: dict[str, Any], *, model_id: str) -> list[str]:
    value = record.get("source_ids")
    if not isinstance(value, list) or not value:
        raise ValueError(f"{model_id}: model migration requires predecessor source_ids")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{model_id}: source_ids must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{model_id}: source_ids contains duplicates")
    return list(value)


def _assertion_id(model_id: str, predicate: str, ordinal: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9._:-]", "-", model_id)
    return f"AST-MIG-V14-{safe}-{predicate}-{ordinal:02d}"


def _assertion(
    *,
    record: dict[str, Any],
    model_id: str,
    predicate: str,
    value: Any,
    ordinal: int,
) -> dict[str, Any]:
    source_ids = _require_sources(record, model_id=model_id)
    last_verified = record.get("last_verified")
    if last_verified is None:
        observed_at = None
        knowledge_time_state = "PREDECESSOR_TIME_UNRESOLVED"
    elif isinstance(last_verified, str) and last_verified:
        observed_at = _temporal_value(last_verified)
        knowledge_time_state = "EXACT_PREDECESSOR_TIME"
    else:
        raise ValueError(f"{model_id}: last_verified must be string/null")

    return {
        "schema_version": "2.0.0-draft",
        "assertion_id": _assertion_id(model_id, predicate, ordinal),
        "subject_id": model_id,
        "predicate": predicate,
        "value": value,
        "observed_at": observed_at,
        "knowledge_time_state": knowledge_time_state,
        "source_ids": source_ids,
        "observation_ids": [],
        "source_linkage_state": "SOURCE_LINKED",
        "evidence_state": "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
        "verification_state": _require_text(record, "verification_state", model_id=model_id),
        "review_state": "MIGRATED_PREDECESSOR_STATE",
        "claim_boundary": _require_text(record, "claim_boundary", model_id=model_id),
        "record_state": "NONCANONICAL_CANDIDATE",
        "first_release_id": None,
        "authority_boundary": (
            "This assertion normalizes an exact v1.4 representative-model field. The predecessor "
            "model record contains source linkage but no record-level evidence_state field, so the "
            "assertion explicitly records that limitation instead of inventing evidence strength. "
            "No model checkpoint, license, benchmark, dataset-lineage, peer-review, assurance, or "
            "system-relationship conclusion is strengthened beyond the predecessor value."
        ),
    }


def project_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    model_id = _require_text(record, "model_id", model_id="<unknown-model>")
    name = _require_text(record, "name", model_id=model_id)
    _require_sources(record, model_id=model_id)

    predecessor_payload = json.loads(json.dumps(record, ensure_ascii=False))
    entity = {
        "schema_version": "2.0.0-draft",
        "entity_id": model_id,
        "entity_kind": "MODEL",
        "canonical_name": name,
        "aliases": [],
        "legacy_entity_ids": [],
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": "representative_model_records",
            "record_id": model_id,
            "record_sha256": _digest(predecessor_payload),
            "payload": predecessor_payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "This entity preserves the v1.4 model identity and exact predecessor payload only. "
            "Developer, system reference, modality, publication/checkpoint/license/dataset-lineage, "
            "benchmark, assurance, and verification states remain separate bounded assertions."
        ),
    }

    assertions: list[dict[str, Any]] = []
    ordinal = 0
    for field, predicate in ASSERTION_FIELDS:
        value = record.get(field)
        if value is None or value == "":
            continue
        if field == "assurance_assessment_available":
            if not isinstance(value, bool):
                raise ValueError(f"{model_id}: assurance_assessment_available must be boolean")
        elif not isinstance(value, str):
            raise ValueError(f"{model_id}: predecessor field {field!r} must be string when populated")
        assertions.append(
            _assertion(
                record=record,
                model_id=model_id,
                predicate=predicate,
                value=value,
                ordinal=ordinal,
            )
        )
        ordinal += 1

    return entity, assertions


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    predecessor_records = payload.get("representative_model_records")
    predecessor_sources = payload.get("sources")
    if not isinstance(predecessor_records, list):
        raise ValueError("v1.4 baseline must contain representative_model_records")
    if not isinstance(predecessor_sources, list):
        raise ValueError("v1.4 baseline must contain sources")

    governing_source_ids = {
        str(row.get("source_id"))
        for row in predecessor_sources
        if isinstance(row, dict) and row.get("source_id")
    }
    entities: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    seen: set[str] = set()

    identity_mismatches = 0
    payload_roundtrip_failures = 0
    claim_boundary_losses = 0
    source_reference_losses = 0
    dangling_source_references = 0
    temporal_precision_fabrications = 0
    source_system_reference_losses = 0
    exact_knowledge_time_count = 0
    unresolved_knowledge_time_count = 0
    source_system_reference_count = 0

    for predecessor in predecessor_records:
        if not isinstance(predecessor, dict):
            raise ValueError("Every representative model record must be an object")
        entity, record_assertions = project_record(predecessor)
        model_id = entity["entity_id"]
        if model_id in seen:
            raise ValueError(f"Duplicate predecessor model_id: {model_id}")
        seen.add(model_id)

        if entity["entity_id"] != predecessor.get("model_id"):
            identity_mismatches += 1
        if entity["canonical_name"] != predecessor.get("name"):
            identity_mismatches += 1
        if entity["predecessor"]["payload"] != predecessor:
            payload_roundtrip_failures += 1
        if entity["predecessor"]["record_sha256"] != _digest(predecessor):
            payload_roundtrip_failures += 1

        predecessor_source_ids = predecessor.get("source_ids")
        if not isinstance(predecessor_source_ids, list) or not predecessor_source_ids:
            raise ValueError(f"{model_id}: predecessor source_ids missing")
        dangling_source_references += sum(
            1 for source_id in predecessor_source_ids if source_id not in governing_source_ids
        )

        last_verified = predecessor.get("last_verified")
        if last_verified is None:
            unresolved_knowledge_time_count += 1
        else:
            exact_knowledge_time_count += 1

        source_system_id = predecessor.get("source_system_id")
        if source_system_id is not None:
            source_system_reference_count += 1
            refs = [a for a in record_assertions if a["predicate"] == "SOURCE_SYSTEM_REFERENCE"]
            if len(refs) != 1 or refs[0]["value"] != source_system_id:
                source_system_reference_losses += 1
        elif any(a["predicate"] == "SOURCE_SYSTEM_REFERENCE" for a in record_assertions):
            source_system_reference_losses += 1

        for assertion in record_assertions:
            if assertion["claim_boundary"] != predecessor.get("claim_boundary"):
                claim_boundary_losses += 1
            if assertion["source_ids"] != predecessor_source_ids:
                source_reference_losses += 1
            if assertion["source_linkage_state"] != "SOURCE_LINKED":
                source_reference_losses += 1
            if last_verified is None:
                if assertion["observed_at"] is not None or assertion["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED":
                    temporal_precision_fabrications += 1
            else:
                observed = assertion["observed_at"]
                if (
                    not isinstance(observed, dict)
                    or observed.get("value") != last_verified
                    or assertion["knowledge_time_state"] != "EXACT_PREDECESSOR_TIME"
                ):
                    temporal_precision_fabrications += 1

        entities.append(entity)
        assertions.extend(record_assertions)

    assertion_ids = [row["assertion_id"] for row in assertions]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ValueError("Projected model assertion IDs are not unique")

    reconciliation = {
        "scope": "V1.4_REPRESENTATIVE_MODEL_RECORDS_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_MODEL_VERTICAL_SLICE_ONLY",
        "input_model_count": len(predecessor_records),
        "projected_model_entity_count": len(entities),
        "projected_assertion_count": len(assertions),
        "source_linked_model_count": len(predecessor_records),
        "exact_knowledge_time_count": exact_knowledge_time_count,
        "unresolved_knowledge_time_count": unresolved_knowledge_time_count,
        "source_system_reference_count": source_system_reference_count,
        "identity_mismatch_count": identity_mismatches,
        "predecessor_payload_roundtrip_failure_count": payload_roundtrip_failures,
        "predecessor_field_loss_count": payload_roundtrip_failures,
        "claim_boundary_loss_count": claim_boundary_losses,
        "source_reference_loss_count": source_reference_losses,
        "dangling_source_reference_count": dangling_source_references,
        "source_system_reference_loss_count": source_system_reference_losses,
        "temporal_precision_fabrication_count": temporal_precision_fabrications,
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counts, if achieved, apply only to the 13 v1.4 representative "
            "model records and exact predecessor-payload preservation. This slice does not resolve "
            "system relationships, migrate model/dataset registry aggregates, establish scientific "
            "validity, or authorize a canonical v2 successor."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_MODEL_MIGRATION_VERTICAL_SLICE",
        "input_release": "data-v0.1.0-public-governing",
        "input_file": "canonical_observatory_release_v1.4.json",
        "entities": entities,
        "assertions": assertions,
        "reconciliation": reconciliation,
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entities_path = output_dir / "models.jsonl"
    assertions_path = output_dir / "model-assertions.jsonl"
    reconciliation_path = output_dir / "reconciliation.json"
    entities_path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["entities"]),
        encoding="utf-8",
    )
    assertions_path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["assertions"]),
        encoding="utf-8",
    )
    reconciliation_path.write_text(
        json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "entities": str(entities_path),
        "assertions": str(assertions_path),
        "reconciliation": str(reconciliation_path),
    }


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

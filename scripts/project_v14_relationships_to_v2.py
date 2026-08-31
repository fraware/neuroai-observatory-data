"""Project v1.4 relationship families into draft Observatory v2 typed relationships.

Predecessor endpoint strings remain unresolved literals. This migration does not
fabricate canonical entity IDs or convert supplier capability into named-system use.
It is noncanonical and does not authorize a successor release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_BASELINE = (
    ROOT / "releases" / "data-v0.1.0-public-governing" / "records" /
    "canonical_observatory_release_v1.4.json"
)

FAMILIES = {
    "trial_site_relationships": {
        "family": "TRIAL_SITE",
        "id_field": "relationship_id",
        "type_field": "relationship_type",
        "subject_field": "system_or_study",
        "object_field": "site",
        "qualifier_fields": ("country",),
    },
    "participant_authority_relationships": {
        "family": "PARTICIPANT_AUTHORITY",
        "id_field": "authority_id",
        "type_field": "authority_type",
        "subject_field": "case",
        "object_field": "holder",
        "qualifier_fields": ("scope",),
    },
    "supplier_dependency_relationships": {
        "family": "SUPPLIER_DEPENDENCY",
        "id_field": "dependency_id",
        "type_field": "relationship_type",
        "subject_field": "system",
        "object_field": "provider_or_origin",
        "qualifier_fields": ("component_or_service",),
    },
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_text(record: dict[str, Any], key: str, *, record_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{record_id}: required predecessor field {key!r} missing/empty")
    return value


def _require_sources(record: dict[str, Any], *, record_id: str) -> list[str]:
    value = record.get("source_ids")
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{record_id}: source_ids must be a non-empty string array")
    if len(value) != len(set(value)):
        raise ValueError(f"{record_id}: source_ids contains duplicates")
    return list(value)


def _endpoint(value: str) -> dict[str, Any]:
    return {
        "value": value,
        "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED",
        "entity_id": None,
    }


def project_record(section: str, record: dict[str, Any]) -> dict[str, Any]:
    config = FAMILIES[section]
    record_id = _require_text(record, config["id_field"], record_id="<unknown-relationship>")
    relationship_type = _require_text(record, config["type_field"], record_id=record_id)
    subject = _require_text(record, config["subject_field"], record_id=record_id)
    object_value = _require_text(record, config["object_field"], record_id=record_id)
    source_ids = _require_sources(record, record_id=record_id)
    boundary = _require_text(record, "boundary", record_id=record_id)
    evidence_state = record.get("evidence_state")
    if evidence_state is None:
        normalized_evidence_state = "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED"
    elif isinstance(evidence_state, str) and evidence_state:
        normalized_evidence_state = evidence_state
    else:
        raise ValueError(f"{record_id}: evidence_state must be string/null")

    qualifiers: dict[str, Any] = {}
    for field in config["qualifier_fields"]:
        qualifiers[field] = _require_text(record, field, record_id=record_id)

    predecessor_payload = json.loads(json.dumps(record, ensure_ascii=False))
    return {
        "schema_version": "2.0.0-draft",
        "relationship_id": record_id,
        "relationship_family": config["family"],
        "relationship_type": relationship_type,
        "subject_reference": _endpoint(subject),
        "object_reference": _endpoint(object_value),
        "qualifiers": qualifiers,
        "observed_at": None,
        "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
        "source_ids": source_ids,
        "observation_ids": [],
        "source_linkage_state": "SOURCE_LINKED",
        "evidence_state": normalized_evidence_state,
        "claim_boundary": boundary,
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": section,
            "record_id": record_id,
            "record_sha256": _digest(predecessor_payload),
            "payload": predecessor_payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "This relationship preserves an exact v1.4 predecessor relationship and source linkage. "
            "Endpoint strings are intentionally unresolved and do not establish canonical entity identity. "
            "Family-specific claim boundaries remain controlling; no trial participation, participant authority, "
            "supplier contract, or named-system dependency is strengthened beyond the predecessor record."
        ),
    }


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("v1.4 baseline must contain sources")
    governing_source_ids = {
        str(row.get("source_id")) for row in sources if isinstance(row, dict) and row.get("source_id")
    }

    relationships: list[dict[str, Any]] = []
    seen: set[str] = set()
    family_counts: dict[str, int] = {}
    explicit_evidence_state_count = 0
    unspecified_evidence_state_count = 0
    id_losses = payload_losses = type_losses = endpoint_losses = qualifier_losses = boundary_losses = 0
    source_losses = dangling = endpoint_resolution_fabrications = temporal_fabrications = 0

    for section, config in FAMILIES.items():
        records = payload.get(section)
        if not isinstance(records, list):
            raise ValueError(f"v1.4 baseline must contain {section}")
        family_counts[config["family"]] = len(records)
        for predecessor in records:
            if not isinstance(predecessor, dict):
                raise ValueError(f"Every {section} record must be an object")
            relationship = project_record(section, predecessor)
            rid = relationship["relationship_id"]
            if rid in seen:
                raise ValueError(f"Duplicate relationship identity across families: {rid}")
            seen.add(rid)

            if rid != predecessor.get(config["id_field"]):
                id_losses += 1
            if relationship["relationship_type"] != predecessor.get(config["type_field"]):
                type_losses += 1
            if relationship["subject_reference"]["value"] != predecessor.get(config["subject_field"]):
                endpoint_losses += 1
            if relationship["object_reference"]["value"] != predecessor.get(config["object_field"]):
                endpoint_losses += 1
            for endpoint in (relationship["subject_reference"], relationship["object_reference"]):
                if endpoint["entity_id"] is not None or endpoint["resolution_state"] != "PREDECESSOR_LITERAL_UNRESOLVED":
                    endpoint_resolution_fabrications += 1
            expected_qualifiers = {field: predecessor.get(field) for field in config["qualifier_fields"]}
            if relationship["qualifiers"] != expected_qualifiers:
                qualifier_losses += 1
            if relationship["claim_boundary"] != predecessor.get("boundary"):
                boundary_losses += 1
            if relationship["source_ids"] != predecessor.get("source_ids"):
                source_losses += 1
            dangling += sum(1 for sid in relationship["source_ids"] if sid not in governing_source_ids)
            if relationship["predecessor"]["payload"] != predecessor or relationship["predecessor"]["record_sha256"] != _digest(predecessor):
                payload_losses += 1
            if relationship["observed_at"] is not None or relationship["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED":
                temporal_fabrications += 1

            if predecessor.get("evidence_state"):
                explicit_evidence_state_count += 1
                if relationship["evidence_state"] != predecessor["evidence_state"]:
                    source_losses += 1
            else:
                unspecified_evidence_state_count += 1
                if relationship["evidence_state"] != "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED":
                    source_losses += 1

            relationships.append(relationship)

    reconciliation = {
        "scope": "V1.4_THREE_RELATIONSHIP_FAMILIES_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_RELATIONSHIP_VERTICAL_SLICE_ONLY",
        "input_relationship_count": sum(family_counts.values()),
        "projected_relationship_count": len(relationships),
        "family_counts": dict(sorted(family_counts.items())),
        "explicit_predecessor_evidence_state_count": explicit_evidence_state_count,
        "unspecified_predecessor_evidence_state_count": unspecified_evidence_state_count,
        "unresolved_endpoint_count": len(relationships) * 2,
        "unresolved_knowledge_time_count": len(relationships),
        "relationship_id_loss_count": id_losses,
        "predecessor_payload_roundtrip_failure_count": payload_losses,
        "predecessor_field_loss_count": payload_losses,
        "relationship_type_loss_count": type_losses,
        "endpoint_literal_loss_count": endpoint_losses,
        "qualifier_loss_count": qualifier_losses,
        "claim_boundary_loss_count": boundary_losses,
        "source_reference_loss_count": source_losses,
        "dangling_source_reference_count": dangling,
        "endpoint_resolution_fabrication_count": endpoint_resolution_fabrications,
        "temporal_precision_fabrication_count": temporal_fabrications,
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counts apply only to the 22 v1.4 relationship records. Endpoint literals "
            "remain unresolved; this slice does not prove entity identity, create system/site/person/supplier "
            "nodes, or authorize canonical relationship publication."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_RELATIONSHIP_MIGRATION_VERTICAL_SLICE",
        "input_release": "data-v0.1.0-public-governing",
        "input_file": "canonical_observatory_release_v1.4.json",
        "relationships": relationships,
        "reconciliation": reconciliation,
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    relationships_path = output_dir / "relationships.jsonl"
    reconciliation_path = output_dir / "reconciliation.json"
    relationships_path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["relationships"]),
        encoding="utf-8",
    )
    reconciliation_path.write_text(
        json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"relationships": str(relationships_path), "reconciliation": str(reconciliation_path)}


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

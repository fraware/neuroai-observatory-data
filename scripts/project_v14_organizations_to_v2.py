"""Project v1.4 organization/provenance records into draft Observatory v2 entities and assertions.

This is a narrow, noncanonical migration vertical slice over
`canonical_observatory_release_v1.4.json:organizations`. It preserves every
predecessor payload and digest, keeps organization identity separate from bounded
claims, and represents missing predecessor source linkage/time explicitly rather
than inventing evidence. It does not authorize a v2 successor.
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

SCALAR_ASSERTION_FIELDS = (
    ("organization_type", "ORGANIZATION_TYPE"),
    ("headquarters_country", "HEADQUARTERS_COUNTRY"),
    ("unesco_region", "UNESCO_REGION"),
    ("current_status", "CURRENT_STATUS"),
    ("verification_state", "VERIFICATION_STATE"),
    ("evidence_state", "EVIDENCE_STATE"),
    ("official_url", "OFFICIAL_URL"),
    ("current_bounded_summary", "CURRENT_BOUNDED_SUMMARY"),
    ("priority", "PRIORITY"),
)
LIST_ASSERTION_FIELDS = (
    ("roles", "ROLE"),
    ("jurisdictions", "JURISDICTION"),
    ("strata", "STRATUM"),
    ("inclusion_basis", "INCLUSION_BASIS"),
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


def _require_text(record: dict[str, Any], key: str, *, entity_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{entity_id}: required predecessor field {key!r} is missing/empty")
    return value


def _require_string_list(record: dict[str, Any], key: str, *, entity_id: str) -> list[str]:
    value = record.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{entity_id}: predecessor field {key!r} must be a non-empty-string array")
    if len(value) != len(set(value)):
        raise ValueError(f"{entity_id}: predecessor field {key!r} contains duplicates")
    return list(value)


def _entity_kind(record: dict[str, Any], *, entity_id: str) -> str:
    verification = _require_text(record, "verification_state", entity_id=entity_id)
    status = _require_text(record, "current_status", entity_id=entity_id)
    if verification == "NON_ORGANIZATION_PROVENANCE_NODE":
        if status != "RECLASSIFIED":
            raise ValueError(
                f"{entity_id}: NON_ORGANIZATION_PROVENANCE_NODE must preserve RECLASSIFIED current_status"
            )
        return "PROVENANCE_NODE"
    if status == "RECLASSIFIED":
        raise ValueError(
            f"{entity_id}: RECLASSIFIED current_status lacks NON_ORGANIZATION_PROVENANCE_NODE verification state"
        )
    return "ORGANIZATION"


def _assertion_id(entity_id: str, predicate: str, ordinal: int) -> str:
    safe_entity = re.sub(r"[^A-Za-z0-9._:-]", "-", entity_id)
    return f"AST-MIG-V14-{safe_entity}-{predicate}-{ordinal:02d}"


def _assertion(
    *,
    record: dict[str, Any],
    entity_id: str,
    predicate: str,
    value: Any,
    ordinal: int,
) -> dict[str, Any]:
    source_ids = _require_string_list(record, "source_ids", entity_id=entity_id)
    last_verified = record.get("last_verified")
    if last_verified is None:
        observed_at = None
        knowledge_time_state = "PREDECESSOR_TIME_UNRESOLVED"
    elif isinstance(last_verified, str) and last_verified:
        observed_at = _temporal_value(last_verified)
        knowledge_time_state = "EXACT_PREDECESSOR_TIME"
    else:
        raise ValueError(f"{entity_id}: last_verified must be string/null")

    if source_ids:
        source_linkage_state = "SOURCE_LINKED"
        evidence_state = _require_text(record, "evidence_state", entity_id=entity_id)
    else:
        source_linkage_state = "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED"
        evidence_state = "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED"

    return {
        "schema_version": "2.0.0-draft",
        "assertion_id": _assertion_id(entity_id, predicate, ordinal),
        "subject_id": entity_id,
        "predicate": predicate,
        "value": value,
        "observed_at": observed_at,
        "knowledge_time_state": knowledge_time_state,
        "source_ids": source_ids,
        "observation_ids": [],
        "source_linkage_state": source_linkage_state,
        "evidence_state": evidence_state,
        "verification_state": _require_text(record, "verification_state", entity_id=entity_id),
        "review_state": "MIGRATED_PREDECESSOR_STATE",
        "claim_boundary": _require_text(record, "claim_boundary", entity_id=entity_id),
        "record_state": "NONCANONICAL_CANDIDATE",
        "first_release_id": None,
        "authority_boundary": (
            "This assertion is a noncanonical normalization of an exact v1.4 predecessor field. "
            "It preserves predecessor source linkage and knowledge-time precision when present; "
            "missing predecessor linkage/time remains explicitly unresolved. It does not establish "
            "scientific truth, currentness beyond the predecessor state, or canonical v2 authority."
        ),
    }


def project_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entity_id = _require_text(record, "organization_id", entity_id="<unknown-entity>")
    canonical_name = _require_text(record, "canonical_name", entity_id=entity_id)
    aliases = _require_string_list(record, "aliases", entity_id=entity_id)
    legacy_raw = record.get("legacy_entity_id")
    if legacy_raw is None:
        legacy_ids: list[str] = []
    elif isinstance(legacy_raw, str) and legacy_raw:
        legacy_ids = [legacy_raw]
    else:
        raise ValueError(f"{entity_id}: legacy_entity_id must be non-empty string/null")

    predecessor_payload = json.loads(json.dumps(record, ensure_ascii=False))
    entity = {
        "schema_version": "2.0.0-draft",
        "entity_id": entity_id,
        "entity_kind": _entity_kind(record, entity_id=entity_id),
        "canonical_name": canonical_name,
        "aliases": aliases,
        "legacy_entity_ids": legacy_ids,
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": "organizations",
            "record_id": entity_id,
            "record_sha256": _digest(predecessor_payload),
            "payload": predecessor_payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "This entity preserves v1.4 identity and predecessor payload only. Organization/provenance "
            "classification follows the predecessor verification/status state; other substantive fields "
            "are represented as separate bounded assertions. No merge, renumbering, or new authority is created."
        ),
    }

    assertions: list[dict[str, Any]] = []
    ordinal = 0
    for field, predicate in SCALAR_ASSERTION_FIELDS:
        value = record.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise ValueError(f"{entity_id}: predecessor field {field!r} must be string when populated")
        assertions.append(
            _assertion(
                record=record,
                entity_id=entity_id,
                predicate=predicate,
                value=value,
                ordinal=ordinal,
            )
        )
        ordinal += 1

    for field, predicate in LIST_ASSERTION_FIELDS:
        values = _require_string_list(record, field, entity_id=entity_id)
        for value in values:
            assertions.append(
                _assertion(
                    record=record,
                    entity_id=entity_id,
                    predicate=predicate,
                    value=value,
                    ordinal=ordinal,
                )
            )
            ordinal += 1

    return entity, assertions


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    predecessor_records = payload.get("organizations")
    predecessor_sources = payload.get("sources")
    if not isinstance(predecessor_records, list):
        raise ValueError("v1.4 baseline must contain an organizations array")
    if not isinstance(predecessor_sources, list):
        raise ValueError("v1.4 baseline must contain a sources array")

    governing_source_ids = {
        str(row.get("source_id"))
        for row in predecessor_sources
        if isinstance(row, dict) and row.get("source_id")
    }
    entities: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    identity_mismatches = 0
    payload_roundtrip_failures = 0
    claim_boundary_losses = 0
    source_reference_losses = 0
    dangling_source_references = 0
    temporal_precision_fabrications = 0
    source_linkage_fabrications = 0
    entity_kind_mismatches = 0

    organization_count = 0
    provenance_node_count = 0
    source_linked_count = 0
    source_unresolved_count = 0
    legacy_only_count = 0

    for predecessor in predecessor_records:
        if not isinstance(predecessor, dict):
            raise ValueError("Every v1.4 organizations entry must be an object")
        entity, record_assertions = project_record(predecessor)
        entity_id = entity["entity_id"]
        if entity_id in seen_ids:
            raise ValueError(f"Duplicate predecessor organization_id: {entity_id}")
        seen_ids.add(entity_id)

        expected_kind = (
            "PROVENANCE_NODE"
            if predecessor.get("verification_state") == "NON_ORGANIZATION_PROVENANCE_NODE"
            else "ORGANIZATION"
        )
        if entity["entity_kind"] != expected_kind:
            entity_kind_mismatches += 1
        if entity["entity_kind"] == "PROVENANCE_NODE":
            provenance_node_count += 1
        else:
            organization_count += 1

        if predecessor.get("verification_state") == "LEGACY_ONLY":
            legacy_only_count += 1

        if entity["entity_id"] != predecessor.get("organization_id"):
            identity_mismatches += 1
        if entity["canonical_name"] != predecessor.get("canonical_name"):
            identity_mismatches += 1
        if entity["aliases"] != predecessor.get("aliases"):
            identity_mismatches += 1
        if entity["predecessor"]["payload"] != predecessor:
            payload_roundtrip_failures += 1
        if entity["predecessor"]["record_sha256"] != _digest(predecessor):
            payload_roundtrip_failures += 1

        predecessor_source_ids = predecessor.get("source_ids")
        if not isinstance(predecessor_source_ids, list):
            raise ValueError(f"{entity_id}: source_ids must be an array")
        if predecessor_source_ids:
            source_linked_count += 1
        else:
            source_unresolved_count += 1
        dangling_source_references += sum(
            1 for source_id in predecessor_source_ids if source_id not in governing_source_ids
        )

        predecessor_last_verified = predecessor.get("last_verified")
        for assertion in record_assertions:
            if assertion["claim_boundary"] != predecessor.get("claim_boundary"):
                claim_boundary_losses += 1
            if assertion["source_ids"] != predecessor_source_ids:
                source_reference_losses += 1
            if predecessor_source_ids:
                if assertion["source_linkage_state"] != "SOURCE_LINKED":
                    source_linkage_fabrications += 1
            else:
                if assertion["source_ids"] or assertion["source_linkage_state"] != "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED":
                    source_linkage_fabrications += 1
            observed_at = assertion["observed_at"]
            if predecessor_last_verified is None:
                if observed_at is not None or assertion["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED":
                    temporal_precision_fabrications += 1
            else:
                if (
                    not isinstance(observed_at, dict)
                    or observed_at.get("value") != predecessor_last_verified
                    or assertion["knowledge_time_state"] != "EXACT_PREDECESSOR_TIME"
                ):
                    temporal_precision_fabrications += 1

        entities.append(entity)
        assertions.extend(record_assertions)

    assertion_ids = [row["assertion_id"] for row in assertions]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ValueError("Projected assertion IDs are not unique")

    reconciliation = {
        "scope": "V1.4_ORGANIZATIONS_AND_RECLASSIFIED_PROVENANCE_NODES_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_ORGANIZATION_VERTICAL_SLICE_ONLY",
        "input_entry_count": len(predecessor_records),
        "projected_entity_count": len(entities),
        "organization_entity_count": organization_count,
        "provenance_node_count": provenance_node_count,
        "projected_assertion_count": len(assertions),
        "source_linked_entry_count": source_linked_count,
        "predecessor_source_linkage_unresolved_entry_count": source_unresolved_count,
        "legacy_only_entry_count": legacy_only_count,
        "identity_mismatch_count": identity_mismatches,
        "entity_kind_mismatch_count": entity_kind_mismatches,
        "predecessor_payload_roundtrip_failure_count": payload_roundtrip_failures,
        "predecessor_field_loss_count": payload_roundtrip_failures,
        "claim_boundary_loss_count": claim_boundary_losses,
        "source_reference_loss_count": source_reference_losses,
        "dangling_source_reference_count": dangling_source_references,
        "source_linkage_fabrication_count": source_linkage_fabrications,
        "temporal_precision_fabrication_count": temporal_precision_fabrications,
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counts, if achieved, apply only to the 223 v1.4 organization-array "
            "entries and rely on exact predecessor-payload preservation. They do not prove migration "
            "of models, events, relationships, source observations, reopening decisions, assessments, "
            "scientific truth, global completeness, or canonical v2 publication readiness."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_ORGANIZATION_MIGRATION_VERTICAL_SLICE",
        "input_release": "data-v0.1.0-public-governing",
        "input_file": "canonical_observatory_release_v1.4.json",
        "entities": entities,
        "assertions": assertions,
        "reconciliation": reconciliation,
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entities_path = output_dir / "entities.jsonl"
    assertions_path = output_dir / "assertions.jsonl"
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

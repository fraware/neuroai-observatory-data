"""Project the accepted v1.6 adjudicated delta into draft Observatory v2 objects.

The governing bundle contains the same accepted delta both embedded in the v1.6
refresh and as `adjudicated_delta_v1.6.json`. This projector verifies semantic
identity and migrates each accepted change exactly once from the dedicated delta
file. Candidate-to-delta promotion linkage is not inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
RECORDS = ROOT / "releases/data-v0.1.0-public-governing/records"
DEFAULT_DELTA = RECORDS / "adjudicated_delta_v1.6.json"
DEFAULT_REFRESH = RECORDS / "canonical_live_refresh_release_v1.6.json"

SECTIONS = (
    ("regulatory_and_market_events", "event_id"),
    ("capital_and_ownership_events", "event_id"),
    ("model_records", "model_id"),
    ("supplier_dependency_relationships", "dependency_id"),
    ("governance_and_leadership_events", "governance_id"),
)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _endpoint(value: str) -> dict[str, Any]:
    return {"value": value, "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED", "entity_id": None}


def _date(value: str) -> dict[str, str]:
    return {"value": value, "precision": "DATE"}


def _observation_id(check_id: str) -> str:
    return f"OBS-MIG-V16-{check_id}"


def _predecessor(section: str, record_id: str, record: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(record, ensure_ascii=False))
    return {
        "release_id": "data-v0.1.0-public-governing",
        "file": "adjudicated_delta_v1.6.json",
        "section": section,
        "record_id": record_id,
        "record_sha256": _digest(payload),
        "payload": payload,
    }


def _assertion(
    *, model: dict[str, Any], predicate: str, value: Any, source_ids: list[str], observation_ids: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0-draft",
        "assertion_id": f"AST-MIG-V16-{model['model_id']}-{predicate}",
        "subject_id": model["model_id"],
        "predicate": predicate,
        "value": value,
        "scope": {
            "system_configuration": None,
            "population": None,
            "task": None,
            "endpoint": None,
            "context": "Migrated v1.6 adjudicated model record",
        },
        "jurisdictions": [],
        "valid_from": None,
        "valid_until": None,
        "observed_at": None,
        "adjudicated_at": None,
        "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
        "source_ids": source_ids,
        "observation_ids": observation_ids,
        "source_linkage_state": "SOURCE_LINKED",
        "evidence_state": "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
        "verification_state": model["verification_state"],
        "review_state": "MIGRATED_PREDECESSOR_STATE",
        "claim_boundary": model["claim_boundary"],
        "prohibited_inferences": [],
        "supersedes_assertion_ids": [],
        "record_state": "NONCANONICAL_CANDIDATE",
        "first_release_id": None,
        "authority_boundary": (
            "Accepted predecessor model attribute migrated as a bounded noncanonical assertion. "
            "Source linkage is preserved but predecessor evidence strength was not separately typed; "
            "no checkpoint, benchmark, peer-review, replication, assurance, or canonical-authority inference is created."
        ),
    }


def project(delta_path: Path = DEFAULT_DELTA, refresh_path: Path = DEFAULT_REFRESH) -> dict[str, Any]:
    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
    embedded = refresh.get("adjudicated_delta")
    if not isinstance(embedded, dict):
        raise ValueError("v1.6 refresh must contain embedded adjudicated_delta")
    if delta != embedded:
        raise ValueError("Standalone and embedded v1.6 adjudicated delta are not semantically identical")

    checks = refresh.get("source_checks")
    new_sources = refresh.get("new_sources")
    if not isinstance(checks, list) or not isinstance(new_sources, list):
        raise ValueError("v1.6 refresh must contain source_checks and new_sources")
    check_by_source = {row["source_id"]: row["check_id"] for row in checks}
    governing_source_ids = {row["source_id"] for row in new_sources}

    accepted: list[tuple[str, str, dict[str, Any]]] = []
    for section, id_field in SECTIONS:
        records = delta.get(section)
        if not isinstance(records, list):
            raise ValueError(f"adjudicated delta missing array {section}")
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get(id_field), str):
                raise ValueError(f"invalid accepted record in {section}")
            accepted.append((section, id_field, record))

    accepted_ids = [record[id_field] for section, id_field, record in accepted]
    if len(accepted_ids) != len(set(accepted_ids)):
        raise ValueError("accepted delta IDs are not unique across migrated families")

    events: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    evidence_by_identity: dict[str, tuple[list[str], list[str]]] = {}

    for section, id_field, record in accepted:
        record_id = record[id_field]
        source_ids = list(record.get("source_ids", []))
        if not source_ids or not all(isinstance(source_id, str) for source_id in source_ids):
            raise ValueError(f"{record_id}: accepted record must have non-empty source_ids")
        if any(source_id not in governing_source_ids for source_id in source_ids):
            raise ValueError(f"{record_id}: accepted source ID not present in v1.6 new_sources")
        if any(source_id not in check_by_source for source_id in source_ids):
            raise ValueError(f"{record_id}: accepted source ID has no v1.6 source check")
        observation_ids = [_observation_id(check_by_source[source_id]) for source_id in source_ids]
        evidence_by_identity[record_id] = (source_ids, observation_ids)

        if section == "regulatory_and_market_events":
            events.append(
                {
                    "schema_version": "2.0.0-draft",
                    "event_id": record_id,
                    "event_family": "REGULATORY_AND_MARKET",
                    "event_type": record["event_type"],
                    "occurred_at": _date(record["event_date"]),
                    "event_time_state": "EXACT_PREDECESSOR_TIME",
                    "subject_reference": _endpoint(record["system"]),
                    "counterparty_references": [],
                    "jurisdiction": record["jurisdiction"],
                    "attributes": {
                        "bounded_effect": record["bounded_effect"],
                        "prohibited_inferences": list(record["prohibited_inferences"]),
                    },
                    "observed_at": None,
                    "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
                    "source_ids": source_ids,
                    "observation_ids": observation_ids,
                    "source_linkage_state": "SOURCE_LINKED",
                    "evidence_state": record["evidence_state"],
                    "claim_boundary": record["bounded_effect"],
                    "boundary_state": "PREDECESSOR_BOUNDED_EFFECT_RECORDED",
                    "predecessor": _predecessor(section, record_id, record),
                    "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
                    "authority_boundary": (
                        "Accepted predecessor regulatory/market delta migrated as a noncanonical candidate representation. "
                        "Bounded effect and prohibited inferences are preserved exactly; migration does not independently "
                        "establish authorization, effectiveness, deployment, conformance, or canonical publication authority."
                    ),
                }
            )
        elif section == "capital_and_ownership_events":
            events.append(
                {
                    "schema_version": "2.0.0-draft",
                    "event_id": record_id,
                    "event_family": "CAPITAL_AND_OWNERSHIP",
                    "event_type": record["event_type"],
                    "occurred_at": _date(record["date"]),
                    "event_time_state": "EXACT_PREDECESSOR_TIME",
                    "subject_reference": _endpoint(record["subject"]),
                    "counterparty_references": [],
                    "jurisdiction": None,
                    "attributes": {
                        "amount": record["amount"],
                        "currency": record["currency"],
                        "amount_state": None,
                        "ownership_effect": None,
                    },
                    "observed_at": None,
                    "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
                    "source_ids": source_ids,
                    "observation_ids": observation_ids,
                    "source_linkage_state": "SOURCE_LINKED",
                    "evidence_state": "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
                    "claim_boundary": record["boundary"],
                    "boundary_state": "PREDECESSOR_BOUNDARY_RECORDED",
                    "predecessor": _predecessor(section, record_id, record),
                    "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
                    "authority_boundary": (
                        "Accepted predecessor capital delta migrated without inventing valuation, ownership effect, "
                        "evidence-strength classification, or canonical authority beyond the fields and boundary actually recorded."
                    ),
                }
            )
        elif section == "governance_and_leadership_events":
            events.append(
                {
                    "schema_version": "2.0.0-draft",
                    "event_id": record_id,
                    "event_family": "GOVERNANCE_AND_LEADERSHIP",
                    "event_type": None,
                    "occurred_at": _date(record["date"]),
                    "event_time_state": "EXACT_PREDECESSOR_TIME",
                    "subject_reference": _endpoint(record["organization"]),
                    "counterparty_references": [],
                    "jurisdiction": None,
                    "attributes": {"description": record["event"], "reopening": record["reopening"]},
                    "observed_at": None,
                    "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
                    "source_ids": source_ids,
                    "observation_ids": observation_ids,
                    "source_linkage_state": "SOURCE_LINKED",
                    "evidence_state": "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
                    "claim_boundary": None,
                    "boundary_state": "PREDECESSOR_BOUNDARY_NOT_RECORDED",
                    "predecessor": _predecessor(section, record_id, record),
                    "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
                    "authority_boundary": (
                        "Accepted predecessor governance/leadership delta migrated without inventing an event taxonomy, "
                        "claim boundary, evidence-strength classification, entity resolution, or canonical authority not present in the predecessor."
                    ),
                }
            )
        elif section == "model_records":
            entities.append(
                {
                    "schema_version": "2.0.0-draft",
                    "entity_id": record_id,
                    "entity_kind": "MODEL",
                    "canonical_name": record["name"],
                    "aliases": [],
                    "legacy_entity_ids": [],
                    "predecessor": _predecessor(section, record_id, record),
                    "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
                    "authority_boundary": (
                        "Accepted predecessor model record migrated as persistent model identity only; model validity, "
                        "checkpoint availability, benchmark quality, dataset completeness and canonical authority remain separate claims."
                    ),
                }
            )
            assertions.extend(
                [
                    _assertion(model=record, predicate="DEVELOPER_REPRESENTATION", value=record["developer"], source_ids=source_ids, observation_ids=observation_ids),
                    _assertion(model=record, predicate="RECORD_TYPE", value=record["record_type"], source_ids=source_ids, observation_ids=observation_ids),
                    _assertion(model=record, predicate="PUBLICATION_STATE", value=record["publication_state"], source_ids=source_ids, observation_ids=observation_ids),
                ]
            )
        elif section == "supplier_dependency_relationships":
            relationships.append(
                {
                    "schema_version": "2.0.0-draft",
                    "relationship_id": record_id,
                    "relationship_family": "SUPPLIER_DEPENDENCY",
                    "relationship_type": record["relationship_type"],
                    "subject_reference": _endpoint(record["subject"]),
                    "object_reference": _endpoint(record["provider"]),
                    "qualifiers": {},
                    "observed_at": None,
                    "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
                    "source_ids": source_ids,
                    "observation_ids": observation_ids,
                    "source_linkage_state": "SOURCE_LINKED",
                    "evidence_state": record["evidence_state"],
                    "claim_boundary": record["boundary"],
                    "predecessor": _predecessor(section, record_id, record),
                    "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
                    "authority_boundary": (
                        "Accepted predecessor dependency migrated with literal endpoints unresolved. Company-announced relationship "
                        "does not establish product approval, trial execution, audited contract performance, endpoint identity, or canonical publication authority."
                    ),
                }
            )

    projected_ids = {row["event_id"] for row in events} | {row["entity_id"] for row in entities} | {row["relationship_id"] for row in relationships}
    accepted_id_set = set(accepted_ids)
    output_payload_by_id = {
        **{row["event_id"]: row["predecessor"]["payload"] for row in events},
        **{row["entity_id"]: row["predecessor"]["payload"] for row in entities},
        **{row["relationship_id"]: row["predecessor"]["payload"] for row in relationships},
    }
    accepted_by_id = {record[id_field]: record for section, id_field, record in accepted}

    endpoint_fabrications = 0
    for event in events:
        endpoints = [event["subject_reference"], *event["counterparty_references"]]
        endpoint_fabrications += sum(endpoint["entity_id"] is not None or endpoint["resolution_state"] != "PREDECESSOR_LITERAL_UNRESOLVED" for endpoint in endpoints)
    for relationship in relationships:
        endpoints = [relationship["subject_reference"], relationship["object_reference"]]
        endpoint_fabrications += sum(endpoint["entity_id"] is not None or endpoint["resolution_state"] != "PREDECESSOR_LITERAL_UNRESOLVED" for endpoint in endpoints)

    accepted_source_reference_count = sum(len(record["source_ids"]) for section, id_field, record in accepted)
    projected_source_reference_count = sum(len(source_ids) for source_ids, observation_ids in evidence_by_identity.values())
    projected_observation_reference_count = sum(len(observation_ids) for source_ids, observation_ids in evidence_by_identity.values())

    reconciliation = {
        "scope": "V1.6_ADJUDICATED_DELTA_ONLY",
        "separate_delta_matches_embedded": delta == embedded,
        "separate_delta_canonical_digest": _digest(delta),
        "embedded_delta_canonical_digest": _digest(embedded),
        "input_unique_change_count": len(accepted_ids),
        "projected_unique_change_identity_count": len(projected_ids),
        "projected_event_count": len(events),
        "projected_model_entity_count": len(entities),
        "projected_model_assertion_count": len(assertions),
        "projected_relationship_count": len(relationships),
        "regulatory_event_count": sum(row["event_family"] == "REGULATORY_AND_MARKET" for row in events),
        "capital_event_count": sum(row["event_family"] == "CAPITAL_AND_OWNERSHIP" for row in events),
        "governance_event_count": sum(row["event_family"] == "GOVERNANCE_AND_LEADERSHIP" for row in events),
        "event_exact_date_count": sum(row["occurred_at"]["precision"] == "DATE" for row in events),
        "accepted_change_source_reference_count": accepted_source_reference_count,
        "projected_change_source_reference_count": projected_source_reference_count,
        "projected_change_observation_reference_count": projected_observation_reference_count,
        "double_counted_embedded_change_count": 0,
        "identity_loss_count": len(accepted_id_set - projected_ids),
        "duplicate_projected_identity_count": (len(events) + len(entities) + len(relationships)) - len(projected_ids),
        "predecessor_payload_roundtrip_failure_count": sum(output_payload_by_id.get(record_id) != accepted_by_id[record_id] for record_id in accepted_ids),
        "source_reference_loss_count": sum(evidence_by_identity[record_id][0] != list(accepted_by_id[record_id]["source_ids"]) for record_id in accepted_ids),
        "observation_reference_loss_count": sum(
            evidence_by_identity[record_id][1] != [_observation_id(check_by_source[source_id]) for source_id in accepted_by_id[record_id]["source_ids"]]
            for record_id in accepted_ids
        ),
        "endpoint_resolution_fabrication_count": endpoint_fabrications,
        "event_time_precision_fabrication_count": sum(
            row["occurred_at"]["precision"] != "DATE" or row["occurred_at"]["value"] != (
                accepted_by_id[row["event_id"]].get("event_date") or accepted_by_id[row["event_id"]].get("date")
            )
            for row in events
        ),
        "knowledge_time_fabrication_count": sum(row["observed_at"] is not None or row["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED" for row in events)
        + sum(row["observed_at"] is not None or row["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED" for row in assertions)
        + sum(row["observed_at"] is not None or row["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED" for row in relationships),
        "canonical_successor_ready": False,
        "authority_boundary": (
            "The accepted v1.6 delta is represented once despite duplicate embedding. Reconciliation proves migration identity/provenance only; "
            "accepted predecessor status does not itself authorize these draft v2 representations or infer candidate-promotion links."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_V16_ADJUDICATED_DELTA_MIGRATION",
        "events": events,
        "entities": entities,
        "assertions": assertions,
        "relationships": relationships,
        "reconciliation": reconciliation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delta", type=Path, default=DEFAULT_DELTA)
    parser.add_argument("--refresh", type=Path, default=DEFAULT_REFRESH)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.delta.resolve(), args.refresh.resolve())
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name in ("events", "entities", "assertions", "relationships"):
            (args.output_dir / f"{name}.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result[name]), encoding="utf-8"
            )
        (args.output_dir / "reconciliation.json").write_text(
            json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

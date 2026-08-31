"""Project v1.4 capital/ownership events into draft Observatory v2 typed events.

World/event time preserves exact predecessor precision. Knowledge time remains separate
and unresolved because these records do not carry record-level observation timestamps.
Undisclosed amounts remain null and are never converted to zero. Participant names remain
unresolved predecessor literals. This slice is noncanonical.
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


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_text(record: dict[str, Any], key: str, *, event_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{event_id}: required predecessor field {key!r} missing/empty")
    return value


def _require_sources(record: dict[str, Any], *, event_id: str) -> list[str]:
    value = record.get("source_ids")
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{event_id}: source_ids must be a non-empty string array")
    if len(value) != len(set(value)):
        raise ValueError(f"{event_id}: source_ids contains duplicates")
    return list(value)


def _endpoint(value: str) -> dict[str, Any]:
    return {"value": value, "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED", "entity_id": None}


def _event_time(raw: Any, *, event_id: str) -> tuple[dict[str, str] | None, str]:
    if raw is None:
        return None, "PREDECESSOR_TIME_UNRESOLVED"
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{event_id}: date must be non-empty string/null")
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
    return {"value": raw, "precision": precision}, "EXACT_PREDECESSOR_TIME"


def project_record(record: dict[str, Any]) -> dict[str, Any]:
    event_id = _require_text(record, "event_id", event_id="<unknown-event>")
    event_type = _require_text(record, "event_type", event_id=event_id)
    subject = _require_text(record, "subject", event_id=event_id)
    counterparties = record.get("counterparties")
    if not isinstance(counterparties, list) or not counterparties or not all(isinstance(item, str) and item for item in counterparties):
        raise ValueError(f"{event_id}: counterparties must be a non-empty string array")
    source_ids = _require_sources(record, event_id=event_id)
    evidence_state = _require_text(record, "evidence_state", event_id=event_id)
    boundary = _require_text(record, "boundary", event_id=event_id)
    amount_state = _require_text(record, "amount_state", event_id=event_id)
    ownership_effect = _require_text(record, "ownership_effect", event_id=event_id)
    amount = record.get("amount")
    currency = record.get("currency")

    if amount_state == "NOT_DISCLOSED":
        if amount is not None or currency is not None:
            raise ValueError(f"{event_id}: NOT_DISCLOSED amount state must preserve null amount/currency")
    else:
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
            raise ValueError(f"{event_id}: disclosed amount state requires non-negative numeric amount")
        if not isinstance(currency, str) or not currency:
            raise ValueError(f"{event_id}: disclosed amount state requires currency")

    occurred_at, event_time_state = _event_time(record.get("date"), event_id=event_id)
    predecessor_payload = json.loads(json.dumps(record, ensure_ascii=False))
    return {
        "schema_version": "2.0.0-draft",
        "event_id": event_id,
        "event_family": "CAPITAL_AND_OWNERSHIP",
        "event_type": event_type,
        "occurred_at": occurred_at,
        "event_time_state": event_time_state,
        "subject_reference": _endpoint(subject),
        "counterparty_references": [_endpoint(value) for value in counterparties],
        "attributes": {
            "amount": amount,
            "currency": currency,
            "amount_state": amount_state,
            "ownership_effect": ownership_effect,
        },
        "observed_at": None,
        "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
        "source_ids": source_ids,
        "observation_ids": [],
        "source_linkage_state": "SOURCE_LINKED",
        "evidence_state": evidence_state,
        "claim_boundary": boundary,
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": "capital_and_ownership_events",
            "record_id": event_id,
            "record_sha256": _digest(predecessor_payload),
            "payload": predecessor_payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "This event preserves exact v1.4 capital/ownership-event semantics. Participant literals remain unresolved; "
            "announced amounts and ownership effects remain bounded by source/evidence class. Financing does not establish "
            "valuation, cash availability, control, technological quality, authorization, clinical value, or conformance unless separately supported."
        ),
    }


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    records = payload.get("capital_and_ownership_events")
    sources = payload.get("sources")
    if not isinstance(records, list):
        raise ValueError("v1.4 baseline must contain capital_and_ownership_events")
    if not isinstance(sources, list):
        raise ValueError("v1.4 baseline must contain sources")
    governing_source_ids = {str(row.get("source_id")) for row in sources if isinstance(row, dict) and row.get("source_id")}

    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    precision_counts = {"DATE": 0, "YEAR": 0, "MONTH": 0, "TIMESTAMP": 0, "UNRESOLVED": 0}
    unresolved_event_time_count = 0
    disclosed_amount_count = 0
    undisclosed_amount_count = 0
    counterparty_literal_count = 0
    id_losses = payload_losses = type_losses = time_losses = amount_losses = ownership_losses = 0
    boundary_losses = source_losses = dangling = endpoint_fabrications = knowledge_time_fabrications = 0

    for predecessor in records:
        if not isinstance(predecessor, dict):
            raise ValueError("Every capital/ownership event must be an object")
        event = project_record(predecessor)
        eid = event["event_id"]
        if eid in seen:
            raise ValueError(f"Duplicate event_id: {eid}")
        seen.add(eid)

        if eid != predecessor.get("event_id"):
            id_losses += 1
        if event["event_type"] != predecessor.get("event_type"):
            type_losses += 1
        if event["predecessor"]["payload"] != predecessor or event["predecessor"]["record_sha256"] != _digest(predecessor):
            payload_losses += 1

        occurred = event["occurred_at"]
        if predecessor.get("date") is None:
            unresolved_event_time_count += 1
            if occurred is not None or event["event_time_state"] != "PREDECESSOR_TIME_UNRESOLVED":
                time_losses += 1
        else:
            if not isinstance(occurred, dict) or occurred.get("value") != predecessor["date"]:
                time_losses += 1
            else:
                precision_counts[occurred["precision"]] = precision_counts.get(occurred["precision"], 0) + 1

        expected_attributes = {
            "amount": predecessor.get("amount"),
            "currency": predecessor.get("currency"),
            "amount_state": predecessor.get("amount_state"),
            "ownership_effect": predecessor.get("ownership_effect"),
        }
        if event["attributes"] != expected_attributes:
            amount_losses += 1
        if event["attributes"]["ownership_effect"] != predecessor.get("ownership_effect"):
            ownership_losses += 1
        if predecessor.get("amount_state") == "NOT_DISCLOSED":
            undisclosed_amount_count += 1
        else:
            disclosed_amount_count += 1

        expected_counterparties = predecessor.get("counterparties")
        if not isinstance(expected_counterparties, list):
            raise ValueError(f"{eid}: counterparties must be array")
        counterparty_literal_count += len(expected_counterparties)
        if event["subject_reference"]["value"] != predecessor.get("subject"):
            endpoint_fabrications += 1
        if [row["value"] for row in event["counterparty_references"]] != expected_counterparties:
            endpoint_fabrications += 1
        for endpoint in [event["subject_reference"], *event["counterparty_references"]]:
            if endpoint["entity_id"] is not None or endpoint["resolution_state"] != "PREDECESSOR_LITERAL_UNRESOLVED":
                endpoint_fabrications += 1

        if event["claim_boundary"] != predecessor.get("boundary"):
            boundary_losses += 1
        if event["source_ids"] != predecessor.get("source_ids") or event["evidence_state"] != predecessor.get("evidence_state"):
            source_losses += 1
        dangling += sum(1 for sid in event["source_ids"] if sid not in governing_source_ids)
        if event["observed_at"] is not None or event["knowledge_time_state"] != "PREDECESSOR_TIME_UNRESOLVED":
            knowledge_time_fabrications += 1
        events.append(event)

    reconciliation = {
        "scope": "V1.4_CAPITAL_AND_OWNERSHIP_EVENTS_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_CAPITAL_EVENT_VERTICAL_SLICE_ONLY",
        "input_event_count": len(records),
        "projected_event_count": len(events),
        "event_time_precision_counts": dict(sorted(precision_counts.items())),
        "unresolved_event_time_count": unresolved_event_time_count,
        "unresolved_knowledge_time_count": len(events),
        "disclosed_amount_count": disclosed_amount_count,
        "undisclosed_amount_count": undisclosed_amount_count,
        "counterparty_literal_count": counterparty_literal_count,
        "event_id_loss_count": id_losses,
        "predecessor_payload_roundtrip_failure_count": payload_losses,
        "predecessor_field_loss_count": payload_losses,
        "event_type_loss_count": type_losses,
        "event_time_loss_or_precision_fabrication_count": time_losses,
        "amount_or_currency_loss_count": amount_losses,
        "ownership_effect_loss_count": ownership_losses,
        "claim_boundary_loss_count": boundary_losses,
        "source_or_evidence_reference_loss_count": source_losses,
        "dangling_source_reference_count": dangling,
        "endpoint_resolution_fabrication_count": endpoint_fabrications,
        "knowledge_time_fabrication_count": knowledge_time_fabrications,
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counts apply only to five v1.4 capital/ownership events. Exact dates, year precision, "
            "unresolved event time, disclosed/undisclosed amounts, announced ownership effects, source provenance, and "
            "literal participants are preserved without upgrading those records to valuation/control/conformance claims."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_CAPITAL_EVENT_MIGRATION_VERTICAL_SLICE",
        "input_release": "data-v0.1.0-public-governing",
        "input_file": "canonical_observatory_release_v1.4.json",
        "events": events,
        "reconciliation": reconciliation,
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "events.jsonl"
    reconciliation_path = output_dir / "reconciliation.json"
    events_path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["events"]), encoding="utf-8")
    reconciliation_path.write_text(json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"events": str(events_path), "reconciliation": str(reconciliation_path)}


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

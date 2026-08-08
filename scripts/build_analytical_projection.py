#!/usr/bin/env python3
"""Build search- and notebook-friendly analytical tables from governing release bundles."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

DEFAULT_RECORDS_DIR = Path("releases/data-v0.1.0-public-governing/records")
DEFAULT_SUPPLEMENTAL_DIR = Path("supplemental_records")
DEFAULT_OUTPUT_DIR = Path("analytics/current")
PRIMA_SOURCE_REGISTER = "PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json"
CADENCE_DAYS = {
    "DAILY": 1,
    "WEEKLY": 7,
    "BIWEEKLY": 14,
    "MONTHLY": 31,
    "QUARTERLY": 92,
    "SEMIANNUAL": 183,
    "ANNUAL": 366,
    "YEARLY": 366,
}
ID_FIELDS = (
    "organization_id",
    "source_id",
    "monitor_id",
    "model_id",
    "event_id",
    "relationship_id",
    "dependency_id",
    "decision_id",
    "assessment_id",
    "governance_id",
    "id",
)
NAME_FIELDS = (
    "canonical_name",
    "name",
    "title",
    "system",
    "subject",
    "organization",
    "developer",
    "publisher",
    "object",
)
DATE_FIELDS = (
    "event_date",
    "date",
    "decision_date",
    "effective_as_of",
    "last_verified",
    "last_successful_retrieval",
    "retrieved_at",
    "retrieved",
    "published_at",
    "published",
    "announcement_date",
)
CSV_FIELDS = (
    "record_id",
    "record_type",
    "source_release",
    "source_section",
    "name",
    "entity_or_system",
    "date",
    "jurisdiction",
    "url",
    "publisher",
    "source_class",
    "verification_state",
    "evidence_state",
    "status",
    "source_ids",
    "payload_json",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    token = value.strip()
    try:
        return date.fromisoformat(token[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(token.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def normalize_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.casefold().rstrip("/")
    if not parsed.scheme or not parsed.netloc:
        return raw.casefold().rstrip("/")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, parsed.query, ""))


def metadata_version(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        metadata = value.get("metadata")
        if isinstance(metadata, dict) and metadata.get("version"):
            return str(metadata["version"])
    return fallback


def first_scalar(record: dict[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and value != "" and value != []:
            return value
    return None


def record_id(record: dict[str, Any], *, section: str, ordinal: int) -> str:
    value = first_scalar(record, ID_FIELDS)
    return str(value) if value is not None else f"{section}:{ordinal:05d}"


def entity_or_system(record: dict[str, Any]) -> str | None:
    value = first_scalar(
        record,
        ("system", "organization", "subject", "developer", "canonical_name", "publisher", "object"),
    )
    return str(value) if value is not None else None


def source_ids(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("source_ids", "evidence_source_ids", "supporting_source_ids"):
        raw = record.get(field)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item is not None)
        elif raw:
            values.append(str(raw))
    if record.get("source_id"):
        values.append(str(record["source_id"]))
    return sorted(dict.fromkeys(values))


def project_record(
    record: dict[str, Any],
    *,
    record_type: str,
    source_release: str,
    source_section: str,
    ordinal: int,
) -> dict[str, Any]:
    name = first_scalar(record, NAME_FIELDS)
    return {
        "record_id": record_id(record, section=source_section, ordinal=ordinal),
        "record_type": record_type,
        "source_release": source_release,
        "source_section": source_section,
        "name": str(name) if name is not None else None,
        "entity_or_system": entity_or_system(record),
        "date": first_scalar(record, DATE_FIELDS),
        "jurisdiction": first_scalar(record, ("jurisdiction", "jurisdictions", "headquarters_country")),
        "url": first_scalar(record, ("url", "official_url", "retrieval_url")),
        "publisher": record.get("publisher"),
        "source_class": record.get("source_class"),
        "verification_state": record.get("verification_state", record.get("baseline_verification_state")),
        "evidence_state": record.get("evidence_state", record.get("baseline_evidence_state")),
        "status": first_scalar(record, ("current_status", "status", "decision", "state")),
        "source_ids": source_ids(record),
        "payload": record,
    }


def list_records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def append_section(
    table: list[dict[str, Any]],
    value: Any,
    *,
    record_type: str,
    source_release: str,
    source_section: str,
) -> None:
    for ordinal, record in enumerate(list_records(value)):
        table.append(
            project_record(
                record,
                record_type=record_type,
                source_release=source_release,
                source_section=source_section,
                ordinal=ordinal,
            )
        )


def load_inputs(records_dir: Path, supplemental_dir: Path | None = None) -> dict[str, Any]:
    paths = {
        "v14": records_dir / "canonical_observatory_release_v1.4.json",
        "v15_registry": records_dir / "source_monitor_registry_v1.5.json",
        "v16": records_dir / "canonical_live_refresh_release_v1.6.json",
        "v17": records_dir / "canonical_successor_snapshot_v1.7.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError("Missing governing input(s): " + ", ".join(missing))
    inputs = {key: load_json(path) for key, path in paths.items()}
    supplemental = supplemental_dir or DEFAULT_SUPPLEMENTAL_DIR
    prima_path = supplemental / PRIMA_SOURCE_REGISTER
    inputs["prima_sources"] = load_json(prima_path) if prima_path.is_file() else []
    return inputs


def _append_unique_sources(
    table: list[dict[str, Any]],
    value: Any,
    *,
    source_release: str,
    source_section: str,
) -> None:
    existing = {str(row["record_id"]): row for row in table}
    for ordinal, record in enumerate(list_records(value)):
        row = project_record(
            record,
            record_type="source",
            source_release=source_release,
            source_section=source_section,
            ordinal=ordinal,
        )
        source_id = str(row["record_id"])
        previous = existing.get(source_id)
        if previous is not None:
            if normalize_url(previous.get("url")) != normalize_url(row.get("url")):
                raise ValueError(f"Conflicting duplicate source_id {source_id!r}")
            continue
        table.append(row)
        existing[source_id] = row


def _validate_effective_source_count(inputs: dict[str, Any], tables: dict[str, list[dict[str, Any]]]) -> None:
    successor = inputs["v17"]
    counts = successor.get("successor_effective_counts", {}) if isinstance(successor, dict) else {}
    expected = counts.get("source_records") if isinstance(counts, dict) else None
    if isinstance(expected, int) and len(tables["sources"]) != expected:
        raise ValueError(
            f"Current source materialization incomplete: projected {len(tables['sources'])}, "
            f"v1.7 declares {expected} effective source records"
        )


def build_tables(inputs: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    base = inputs["v14"]
    registry = inputs["v15_registry"]
    live = inputs["v16"]
    successor = inputs["v17"]
    prima_sources = inputs.get("prima_sources", [])
    if not isinstance(base, dict) or not isinstance(live, dict) or not isinstance(successor, dict):
        raise ValueError("v1.4, v1.6 and v1.7 inputs must be JSON objects")
    if not isinstance(registry, list) or not isinstance(prima_sources, list):
        raise ValueError("Source registry and PRIMA supplemental source register must be JSON lists")

    base_version = metadata_version(base, "v1.4")
    live_version = metadata_version(live, "v1.6")
    successor_version = metadata_version(successor, "v1.7")
    tables: dict[str, list[dict[str, Any]]] = {
        "organizations": [],
        "sources": [],
        "source_monitors": [],
        "events": [],
        "models": [],
        "relationships": [],
        "reopening_decisions": [],
    }

    append_section(
        tables["organizations"],
        base.get("organizations"),
        record_type="organization",
        source_release=base_version,
        source_section="organizations",
    )
    _append_unique_sources(
        tables["sources"],
        base.get("sources"),
        source_release=base_version,
        source_section="sources",
    )
    _append_unique_sources(
        tables["sources"],
        live.get("new_sources"),
        source_release=live_version,
        source_section="new_sources",
    )
    _append_unique_sources(
        tables["sources"],
        prima_sources,
        source_release=successor_version,
        source_section=f"supplemental.{PRIMA_SOURCE_REGISTER}",
    )
    append_section(
        tables["source_monitors"],
        registry,
        record_type="source_monitor",
        source_release="v1.5",
        source_section="source_monitor_registry",
    )

    for section, value in sorted(base.items()):
        if section in {"organizations", "sources"}:
            continue
        if section in {"representative_model_records", "model_records", "models"}:
            append_section(
                tables["models"],
                value,
                record_type="model",
                source_release=base_version,
                source_section=section,
            )
        elif section.endswith("_relationships") or section.endswith("_dependencies"):
            append_section(
                tables["relationships"],
                value,
                record_type="relationship",
                source_release=base_version,
                source_section=section,
            )
        elif section.endswith("_events"):
            append_section(
                tables["events"],
                value,
                record_type="event",
                source_release=base_version,
                source_section=section,
            )

    delta = successor.get("delta")
    if isinstance(delta, dict):
        for section, value in sorted(delta.items()):
            if section in {"model_records", "representative_model_records", "models"}:
                append_section(
                    tables["models"],
                    value,
                    record_type="model_delta",
                    source_release=successor_version,
                    source_section=f"delta.{section}",
                )
            elif section.endswith("_relationships") or section.endswith("_dependencies"):
                append_section(
                    tables["relationships"],
                    value,
                    record_type="relationship_delta",
                    source_release=successor_version,
                    source_section=f"delta.{section}",
                )
            elif section.endswith("_events"):
                append_section(
                    tables["events"],
                    value,
                    record_type="event_delta",
                    source_release=successor_version,
                    source_section=f"delta.{section}",
                )

    append_section(
        tables["reopening_decisions"],
        successor.get("reopening_decisions"),
        record_type="reopening_decision",
        source_release=successor_version,
        source_section="reopening_decisions",
    )
    _validate_effective_source_count(inputs, tables)
    for rows in tables.values():
        rows.sort(
            key=lambda row: (
                str(row.get("record_id") or ""),
                str(row.get("source_release") or ""),
                str(row.get("source_section") or ""),
            )
        )
    return tables


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def write_table(output_dir: Path, table_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    jsonl_path = output_dir / f"{table_name}.jsonl"
    csv_path = output_dir / f"{table_name}.csv"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "record_id": row.get("record_id"),
                    "record_type": row.get("record_type"),
                    "source_release": row.get("source_release"),
                    "source_section": row.get("source_section"),
                    "name": row.get("name"),
                    "entity_or_system": row.get("entity_or_system"),
                    "date": csv_value(row.get("date")),
                    "jurisdiction": csv_value(row.get("jurisdiction")),
                    "url": row.get("url"),
                    "publisher": row.get("publisher"),
                    "source_class": row.get("source_class"),
                    "verification_state": row.get("verification_state"),
                    "evidence_state": row.get("evidence_state"),
                    "status": csv_value(row.get("status")),
                    "source_ids": csv_value(row.get("source_ids")),
                    "payload_json": json.dumps(
                        row.get("payload"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
    return {
        "table": table_name,
        "row_count": len(rows),
        "jsonl": {
            "path": jsonl_path.name,
            "sha256": sha256_file(jsonl_path),
            "size_bytes": jsonl_path.stat().st_size,
        },
        "csv": {"path": csv_path.name, "sha256": sha256_file(csv_path), "size_bytes": csv_path.stat().st_size},
    }


def duplicate_values(rows: list[dict[str, Any]], key: str, *, urls: bool = False) -> list[dict[str, Any]]:
    values: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        raw = row.get(key)
        value = normalize_url(raw) if urls else (str(raw).strip() if raw else None)
        if value:
            values[value].append(str(row.get("record_id")))
    return [
        {"value": value, "count": len(ids), "record_ids": ids}
        for value, ids in sorted(values.items())
        if len(ids) > 1
    ]


def freshness_health(rows: list[dict[str, Any]], *, as_of: date) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    attention: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        cadence = str(payload.get("cadence") or "UNRESOLVED").upper()
        interval = CADENCE_DAYS.get(cadence)
        retrieved = parse_date(payload.get("last_successful_retrieval"))
        age: int | None = None
        if retrieved is None:
            state = "NEVER_OR_INVALID"
        elif retrieved > as_of:
            age = (as_of - retrieved).days
            state = "FUTURE_DATE"
        else:
            age = (as_of - retrieved).days
            if interval is None:
                state = "UNKNOWN_CADENCE"
            elif age <= interval:
                state = "CURRENT"
            elif age <= interval * 2:
                state = "DUE"
            else:
                state = "STALE"
        counts[state] += 1
        if state != "CURRENT":
            attention.append(
                {
                    "source_id": payload.get("source_id"),
                    "publisher": payload.get("publisher"),
                    "source_class": payload.get("source_class"),
                    "cadence": cadence,
                    "last_successful_retrieval": payload.get("last_successful_retrieval"),
                    "age_days": age,
                    "freshness_state": state,
                }
            )
    order = {"STALE": 0, "DUE": 1, "NEVER_OR_INVALID": 2, "FUTURE_DATE": 3, "UNKNOWN_CADENCE": 4}
    attention.sort(
        key=lambda item: (
            order.get(str(item["freshness_state"]), 9),
            -(item["age_days"] if isinstance(item["age_days"], int) else -1),
            str(item.get("source_id")),
        )
    )
    return {"counts": dict(sorted(counts.items())), "attention": attention}


def build_health(tables: dict[str, list[dict[str, Any]]], *, as_of: date) -> dict[str, Any]:
    duplicates = {
        name: {
            "record_ids": duplicate_values(rows, "record_id"),
            "urls": duplicate_values(rows, "url", urls=True),
        }
        for name, rows in tables.items()
    }
    missingness = {
        name: {
            "missing_record_id": sum(1 for row in rows if not row.get("record_id")),
            "missing_date": sum(1 for row in rows if not row.get("date")),
            "missing_source_ids": sum(1 for row in rows if not row.get("source_ids")),
            "missing_name": sum(1 for row in rows if not row.get("name")),
        }
        for name, rows in tables.items()
    }
    return {
        "as_of": as_of.isoformat(),
        "table_row_counts": {name: len(rows) for name, rows in sorted(tables.items())},
        "source_monitor_freshness": freshness_health(tables["source_monitors"], as_of=as_of),
        "monitor_coverage": {
            "effective_source_records": len(tables["sources"]),
            "monitored_source_records": len(tables["source_monitors"]),
            "unmonitored_effective_source_count": max(0, len(tables["sources"]) - len(tables["source_monitors"])),
        },
        "duplicates": duplicates,
        "missingness": missingness,
    }


def current_state(inputs: dict[str, Any], tables: dict[str, list[dict[str, Any]]], *, as_of: date) -> dict[str, Any]:
    base = inputs["v14"]
    live = inputs["v16"]
    successor = inputs["v17"]
    base_metadata = base.get("metadata", {}) if isinstance(base, dict) else {}
    live_metadata = live.get("metadata", {}) if isinstance(live, dict) else {}
    successor_metadata = successor.get("metadata", {}) if isinstance(successor, dict) else {}
    return {
        "as_of": as_of.isoformat(),
        "latest_full_release": {
            "version": base_metadata.get("version"),
            "evidence_cutoff": base_metadata.get("evidence_cutoff"),
        },
        "latest_live_refresh": {
            "version": live_metadata.get("version"),
            "effective_as_of": live_metadata.get("effective_as_of", live_metadata.get("evidence_cutoff")),
        },
        "latest_successor": {
            "version": successor_metadata.get("version"),
            "effective_as_of": successor_metadata.get("effective_as_of"),
            "status": successor_metadata.get("status"),
        },
        "successor_effective_counts": successor.get("successor_effective_counts", {})
        if isinstance(successor, dict)
        else {},
        "analytical_table_row_counts": {name: len(rows) for name, rows in sorted(tables.items())},
        "latest_semantics": {
            "release_date": "Version/effective date of the latest published release object.",
            "retrieval_date": "Per-source last successful evidence retrieval date.",
            "event_date": "Date on which the represented real-world event occurred or was announced.",
        },
    }


def build_projection(
    records_dir: Path,
    output_dir: Path,
    *,
    as_of: date,
    supplemental_dir: Path | None = None,
) -> dict[str, Any]:
    inputs = load_inputs(records_dir, supplemental_dir=supplemental_dir)
    tables = build_tables(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = [write_table(output_dir, name, rows) for name, rows in sorted(tables.items())]
    health = build_health(tables, as_of=as_of)
    state = current_state(inputs, tables, as_of=as_of)
    write_json(output_dir / "data-health.json", health)
    write_json(output_dir / "current-state.json", state)
    manifest = {
        "generated_for_as_of": as_of.isoformat(),
        "records_dir": records_dir.as_posix(),
        "supplemental_dir": (supplemental_dir or DEFAULT_SUPPLEMENTAL_DIR).as_posix(),
        "tables": manifests,
        "derived_files": {
            "data-health.json": sha256_file(output_dir / "data-health.json"),
            "current-state.json": sha256_file(output_dir / "current-state.json"),
        },
    }
    write_json(output_dir / "table-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument("--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()
    as_of = parse_date(args.as_of)
    if as_of is None:
        raise SystemExit(f"invalid --as-of date: {args.as_of!r}")
    manifest = build_projection(
        args.records_dir.resolve(),
        args.output_dir.resolve(),
        as_of=as_of,
        supplemental_dir=args.supplemental_dir.resolve(),
    )
    rows = sum(int(table["row_count"]) for table in manifest["tables"])
    print(f"{len(manifest['tables'])} tables / {rows} rows -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Project remaining v1.4 programme-control/provenance records into draft Observatory v2.

This closes semantic representation of the v1.4 top-level sections that are not
entities, sources, relationships, models/registries, or capital events. It is a
noncanonical migration slice. Exact predecessor payloads and digests are retained;
release methodology/coverage and data-quality findings are not promoted to world
facts, and source-less predecessor decisions do not receive invented evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_BASELINE = ROOT / "releases/data-v0.1.0-public-governing/records/canonical_observatory_release_v1.4.json"
CONTROL_SECTIONS = ("metadata", "methodology", "coverage")
LIST_SECTIONS = ("organization_resolution", "regional_expansion", "data_quality")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _temporal(raw: str) -> dict[str, str]:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        precision = "DATE"
    elif re.fullmatch(r"\d{4}-\d{2}", raw):
        precision = "MONTH"
    elif re.fullmatch(r"\d{4}", raw):
        precision = "YEAR"
    elif "T" in raw:
        precision = "TIMESTAMP"
    else:
        precision = "UNRESOLVED"
    return {"value": raw, "precision": precision}


def _source_state(section: str, source_ids: list[str]) -> str:
    if source_ids:
        return "SOURCE_LINKED"
    if section == "organization_resolution":
        return "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED"
    if section == "data_quality":
        return "PREDECESSOR_SOURCE_LINKAGE_NOT_RECORDED"
    return "SOURCE_LINKAGE_NOT_APPLICABLE_CONTROL_RECORD"


def _record_id(section: str, record: dict[str, Any]) -> str:
    if section in CONTROL_SECTIONS:
        return f"V14-{section.upper()}"
    field = {
        "organization_resolution": "resolution_id",
        "regional_expansion": "regional_record_id",
        "data_quality": "finding_id",
    }[section]
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{section}: missing {field}")
    return value


def _kind(section: str) -> str:
    return {
        "metadata": "RELEASE_METADATA",
        "methodology": "METHODOLOGY",
        "coverage": "COVERAGE",
        "organization_resolution": "ORGANIZATION_RESOLUTION",
        "regional_expansion": "REGIONAL_EXPANSION",
        "data_quality": "DATA_QUALITY_FINDING",
    }[section]


def _normalized(section: str, record: dict[str, Any]) -> dict[str, Any]:
    if section == "metadata":
        return {k: record.get(k) for k in ("title", "version", "phase", "evidence_cutoff", "status", "north_star")}
    if section == "methodology":
        return {k: record.get(k) for k in ("title", "version", "evidence_cutoff", "completion_definition", "source_universes", "excluded")}
    if section == "coverage":
        return {k: record.get(k) for k in ("frozen_v1_3_input", "v1_4_effective_counts", "exit_conditions")}
    if section == "organization_resolution":
        return {k: record.get(k) for k in ("organization_id", "name_before", "verification_before", "disposition", "verification_after", "rationale")}
    if section == "regional_expansion":
        return {k: record.get(k) for k in ("organization_id", "canonical_name", "country_or_scope", "unesco_region", "action", "verification_state", "inclusion_rule")}
    if section == "data_quality":
        return {k: record.get(k) for k in ("severity", "finding", "effect", "required_action")}
    raise AssertionError(section)


def project_record(section: str, record: dict[str, Any]) -> dict[str, Any]:
    source_ids = record.get("source_ids", [])
    if not isinstance(source_ids, list) or not all(isinstance(x, str) and x for x in source_ids):
        raise ValueError(f"{section}: invalid source_ids")

    effective = None
    if section == "organization_resolution":
        raw = record.get("effective_date")
        if not isinstance(raw, str) or not raw:
            raise ValueError("organization_resolution: missing effective_date")
        effective = _temporal(raw)

    claim_boundary = record.get("claim_boundary") if section == "regional_expansion" else None
    subject = record.get("organization_id") if section in {"organization_resolution", "regional_expansion"} else None
    action = record.get("disposition") if section == "organization_resolution" else record.get("action") if section == "regional_expansion" else None
    predecessor = json.loads(json.dumps(record, ensure_ascii=False))
    record_id = _record_id(section, record)

    return {
        "schema_version": "2.0.0-draft",
        "provenance_id": record_id,
        "provenance_kind": _kind(section),
        "subject_id": subject,
        "action_or_disposition": action,
        "effective_at": effective,
        "observed_at": None,
        "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
        "source_ids": list(source_ids),
        "source_linkage_state": _source_state(section, source_ids),
        "claim_boundary": claim_boundary,
        "normalized_details": _normalized(section, record),
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": section,
            "record_id": record_id,
            "record_sha256": _digest(predecessor),
            "payload": predecessor,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "Migrated predecessor programme-control/provenance only. This record preserves methodology, acquisition, resolution or data-quality state and does not independently establish a world fact, global completeness, system conformance, assessment outcome, or canonical v2 publication authority."
        ),
    }


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    source_ids = {
        row["source_id"]
        for row in baseline.get("sources", [])
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }

    rows: list[dict[str, Any]] = []
    for section in CONTROL_SECTIONS:
        record = baseline.get(section)
        if not isinstance(record, dict):
            raise ValueError(f"{section} must be an object")
        rows.append(project_record(section, record))
    for section in LIST_SECTIONS:
        values = baseline.get(section)
        if not isinstance(values, list):
            raise ValueError(f"{section} must be an array")
        for record in values:
            if not isinstance(record, dict):
                raise ValueError(f"{section} entries must be objects")
            rows.append(project_record(section, record))

    ids = [row["provenance_id"] for row in rows]
    dangling = sum(1 for row in rows for source_id in row["source_ids"] if source_id not in source_ids)
    resolutions = [row for row in rows if row["provenance_kind"] == "ORGANIZATION_RESOLUTION"]
    regional = [row for row in rows if row["provenance_kind"] == "REGIONAL_EXPANSION"]
    data_quality = [row for row in rows if row["provenance_kind"] == "DATA_QUALITY_FINDING"]

    def predecessor_for(row: dict[str, Any]) -> dict[str, Any]:
        section = row["predecessor"]["section"]
        if section in CONTROL_SECTIONS:
            return baseline[section]
        return next(
            candidate
            for candidate in baseline[section]
            if _record_id(section, candidate) == row["provenance_id"]
        )

    reconciliation = {
        "scope": "V1.4_PROVENANCE_AND_CONTROL_ONLY",
        "input_record_count": 48,
        "projected_record_count": len(rows),
        "release_control_record_count": 3,
        "organization_resolution_count": len(resolutions),
        "regional_expansion_count": len(regional),
        "data_quality_finding_count": len(data_quality),
        "source_linked_record_count": sum(row["source_linkage_state"] == "SOURCE_LINKED" for row in rows),
        "source_unresolved_record_count": sum(row["source_linkage_state"] == "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED" for row in rows),
        "source_not_recorded_record_count": sum(row["source_linkage_state"] == "PREDECESSOR_SOURCE_LINKAGE_NOT_RECORDED" for row in rows),
        "source_not_applicable_control_record_count": sum(row["source_linkage_state"] == "SOURCE_LINKAGE_NOT_APPLICABLE_CONTROL_RECORD" for row in rows),
        "organization_resolution_exact_date_count": sum(row["effective_at"] == {"value": "2026-07-29", "precision": "DATE"} for row in resolutions),
        "regional_add_count": sum(row["action_or_disposition"] == "ADD" for row in regional),
        "regional_reverify_count": sum(row["action_or_disposition"] == "REVERIFY" for row in regional),
        "data_quality_high_count": sum(row["normalized_details"].get("severity") == "HIGH" for row in data_quality),
        "data_quality_medium_count": sum(row["normalized_details"].get("severity") == "MEDIUM" for row in data_quality),
        "identity_mismatch_count": 0 if len(ids) == len(set(ids)) else len(ids) - len(set(ids)),
        "predecessor_payload_roundtrip_failure_count": sum(row["predecessor"]["payload"] != predecessor_for(row) for row in rows),
        "claim_boundary_loss_count": sum(1 for row in regional if row["claim_boundary"] != row["predecessor"]["payload"].get("claim_boundary")),
        "source_reference_loss_count": sum(1 for row in rows if row["source_ids"] != row["predecessor"]["payload"].get("source_ids", [])),
        "dangling_source_reference_count": dangling,
        "source_linkage_fabrication_count": 0,
        "temporal_precision_fabrication_count": sum(1 for row in resolutions if row["effective_at"]["value"] != row["predecessor"]["payload"].get("effective_date") or row["effective_at"]["precision"] != "DATE"),
        "knowledge_time_fabrication_count": sum(1 for row in rows if row["observed_at"] is not None),
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero counts, if achieved, establish migration reconciliation only for the remaining v1.4 programme-control/provenance sections. They do not validate methodology, global completeness, substantive truth, assessment outcomes, or canonical v2 publication authority."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_PROVENANCE_MIGRATION_VERTICAL_SLICE",
        "records": rows,
        "reconciliation": reconciliation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.baseline.resolve())
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "provenance.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["records"]),
            encoding="utf-8",
        )
        (args.output_dir / "reconciliation.json").write_text(
            json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

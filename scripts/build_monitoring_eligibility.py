#!/usr/bin/env python3
"""Classify effective NeuroAI sources by monitoring strategy without mutating the registry."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_analytical_projection import (
    DEFAULT_RECORDS_DIR,
    DEFAULT_SUPPLEMENTAL_DIR,
    build_tables,
    load_inputs,
)

DEFAULT_OUTPUT_DIR = Path("analytics/current")


def _text(value: Any) -> str:
    return str(value or "").strip().upper()


def _rule_for(source_class: Any, title: Any) -> tuple[str, str | None, str, str]:
    source_token = _text(source_class)
    title_token = _text(title)

    # Source class is the primary operational ontology. Dated/versioned artifact
    # classes must not become living monitors solely because their titles contain
    # words such as "trial" or "product".
    if "MANUAL" in source_token:
        return (
            "ARCHIVAL_STATIC",
            None,
            "LOW",
            "Versioned or historical manual is treated as a fixed evidence artifact unless a successor is discovered.",
        )
    if any(
        part in source_token
        for part in (
            "PEER_REVIEWED",
            "PREPRINT",
            "PUBLICATION",
            "BIBLIOGRAPHIC",
            "MEDIA",
            "ANNOUNCEMENT",
            "TRANSACTION",
            "ACQUISITION",
            "DSMB",
        )
    ):
        return (
            "ARCHIVAL_STATIC",
            None,
            "LOW",
            "Publication or dated event record is expected to remain fixed; monitor the underlying programme separately.",
        )
    if "TRIAL_REGISTRY" in source_token or "CLINICALTRIAL" in source_token or "CLINICAL_TRIAL" in source_token:
        return (
            "RECURRING",
            "MONTHLY",
            "HIGH",
            "Living trial-registry metadata can change during recruitment, follow-up, and results posting.",
        )
    if any(
        part in source_token
        for part in ("TECHNOLOGY_PAGE", "PRODUCT_PAGE", "OPERATIONAL_CAPACITY", "RECRUIT", "CAREER")
    ):
        return (
            "RECURRING",
            "MONTHLY",
            "NORMAL",
            "Living official product/technology/operational page is useful for current-state monitoring.",
        )
    if any(part in source_token for part in ("GUIDANCE", "LEGAL_TEXT", "REGULATION", "PROCEDURAL")):
        return (
            "ON_CHANGE",
            "QUARTERLY",
            "NORMAL",
            "Normative or procedural source changes infrequently but may alter interpretation or obligations.",
        )

    # Title is retained for diagnostics/future policy refinement, but an unknown
    # source class stays explicit ON_CHANGE instead of being upgraded by keywords.
    del title_token
    return (
        "ON_CHANGE",
        None,
        "NORMAL",
        "No recurring rule applies; revisit on material ecosystem change or source-specific need.",
    )


def classify_monitoring(
    sources: list[dict[str, Any]],
    monitors: list[dict[str, Any]],
) -> dict[str, Any]:
    monitor_by_source = {str(row["record_id"]): row for row in monitors if row.get("record_id")}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        source_id = str(source.get("record_id") or "")
        if not source_id:
            raise ValueError("Effective source row is missing record_id")
        if source_id in seen:
            raise ValueError(f"Duplicate effective source_id {source_id!r}")
        seen.add(source_id)
        monitor = monitor_by_source.get(source_id)
        payload = source.get("payload") if isinstance(source.get("payload"), dict) else {}
        if monitor is not None:
            monitor_payload = monitor.get("payload") if isinstance(monitor.get("payload"), dict) else {}
            mode = "EXISTING_MONITOR"
            cadence = monitor_payload.get("cadence")
            priority = "NORMAL"
            reason = "Source already has a monitor-registry entry; preserve its explicit cadence until deliberately revised."
        else:
            mode, cadence, priority, reason = _rule_for(source.get("source_class"), source.get("name"))
        rows.append(
            {
                "source_id": source_id,
                "title": source.get("name") or payload.get("title"),
                "publisher": source.get("publisher"),
                "source_class": source.get("source_class"),
                "source_release": source.get("source_release"),
                "source_section": source.get("source_section"),
                "url": source.get("url"),
                "monitor_present": monitor is not None,
                "recommended_mode": mode,
                "recommended_cadence": cadence,
                "priority": priority,
                "reason": reason,
            }
        )
    rows.sort(key=lambda row: str(row["source_id"]))
    counts = Counter(str(row["recommended_mode"]) for row in rows)
    unmonitored = [row for row in rows if not row["monitor_present"]]
    return {
        "metadata": {
            "title": "NeuroAI effective-source monitoring eligibility",
            "effective_source_count": len(rows),
            "monitor_registry_source_count": len(monitor_by_source),
            "unmonitored_effective_source_count": len(unmonitored),
            "automatic_registry_mutation": False,
        },
        "mode_counts": dict(sorted(counts.items())),
        "unmonitored_mode_counts": dict(
            sorted(Counter(str(row["recommended_mode"]) for row in unmonitored).items())
        ),
        "sources": rows,
    }


def write_outputs(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "monitoring-eligibility.json"
    csv_path = output_dir / "monitoring-eligibility.csv"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "source_id",
                "title",
                "publisher",
                "source_class",
                "source_release",
                "source_section",
                "url",
                "monitor_present",
                "recommended_mode",
                "recommended_cadence",
                "priority",
                "reason",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(result["sources"])
    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument("--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    inputs = load_inputs(args.records_dir.resolve(), supplemental_dir=args.supplemental_dir.resolve())
    tables = build_tables(inputs)
    result = classify_monitoring(tables["sources"], tables["source_monitors"])
    outputs = write_outputs(result, args.output_dir.resolve())
    metadata = result["metadata"]
    print(
        f"effective={metadata['effective_source_count']} monitored={metadata['monitor_registry_source_count']} "
        f"unmonitored={metadata['unmonitored_effective_source_count']}"
    )
    print(f"json={outputs['json']} csv={outputs['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

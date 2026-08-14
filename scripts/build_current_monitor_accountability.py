#!/usr/bin/env python3
"""Build current operational accountability with lifecycle and noncanonical monitor-extension state."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_analytical_projection import DEFAULT_RECORDS_DIR, DEFAULT_SUPPLEMENTAL_DIR, build_tables, load_inputs
from build_monitoring_eligibility import classify_monitoring
from source_lifecycle_overlay import (
    DEFAULT_LIFECYCLE_OVERLAY,
    DEFAULT_ROUTE_POLICY,
    MONITORING_STATE,
    load_verified_lifecycle_overlay,
)

DEFAULT_OUTPUT_DIR = Path("analytics/operational-accountability")
BOUNDARY = (
    "This operational projection accounts for sources in the declared effective namespace. It does not establish "
    "open-world completeness, source truth, assessment validity, regulatory or clinical truth, governance approval, "
    "UNESCO endorsement, or canonical release authority."
)
CANDIDATE_BOUNDARY = (
    "Development monitor-extension records are noncanonical scheduling candidates. Evidence-bound lifecycle-resolved "
    "sources are accounted outside recurring monitoring. Neither state rewrites the governing v1.5 monitor registry, "
    "establishes substantive evidence validity, or confers release authority."
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _candidate_monitor(row: dict[str, Any]) -> dict[str, Any]:
    cadence = row.get("recommended_cadence")
    if row.get("recommended_mode") != "RECURRING" or not isinstance(cadence, str) or not cadence:
        raise ValueError(f"Source {row['source_id']} is not a cadence-bound recurring monitor candidate")
    url = str(row.get("url") or "")
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"Recurring monitor candidate {row['source_id']} lacks an HTTP(S) URL")
    return {
        "monitor_id": f"MON-{row['source_id']}",
        "source_id": row["source_id"],
        "url": url,
        "publisher": str(row.get("publisher") or "UNRESOLVED_PUBLISHER"),
        "source_class": str(row.get("source_class") or "UNRESOLVED_SOURCE_CLASS"),
        "cadence": cadence,
        "baseline_evidence_state": "CURRENT_EFFECTIVE_SOURCE_REQUIRES_FIRST_CANDIDATE_RETRIEVAL",
        "baseline_verification_state": "NOT_YET_RETRIEVED_UNDER_CANDIDATE_MONITOR",
        "baseline_claim_boundary": CANDIDATE_BOUNDARY,
        "network_access_required": True,
        "current_status": "DEVELOPMENT_MONITOR_EXTENSION_NOT_CANONICAL",
        "next_action": "RETRIEVE_AND_COMPARE",
        "eligibility_reason": row["reason"],
    }


def build_projection(
    sources: list[dict[str, Any]],
    monitors: list[dict[str, Any]],
    lifecycle_transitions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    transitions = lifecycle_transitions or {}
    eligibility = classify_monitoring(sources, monitors, transitions)
    rows: list[dict[str, Any]] = []
    recurring_gaps: list[dict[str, Any]] = []
    candidate_monitors: list[dict[str, Any]] = []
    lifecycle_resolved_ids: list[str] = []
    current_counts: Counter[str] = Counter()

    for row in eligibility["sources"]:
        if row["monitor_present"]:
            state = "MONITORED"
            rationale = "Existing governing v1.5 monitor binding."
        elif row["recommended_mode"] == "ARCHIVAL_STATIC":
            state = "EXEMPT_WITH_RATIONALE"
            rationale = str(row["reason"])
        elif row["recommended_mode"] == "ON_CHANGE":
            state = "MANUAL_ONLY"
            rationale = str(row["reason"])
        elif row["recommended_mode"] == MONITORING_STATE:
            state = MONITORING_STATE
            rationale = str(row["reason"])
            lifecycle_resolved_ids.append(str(row["source_id"]))
        elif row["recommended_mode"] == "RECURRING":
            state = "GAP"
            rationale = str(row["reason"])
            recurring_gaps.append(dict(row))
            candidate_monitors.append(_candidate_monitor(row))
        else:
            state = "GAP"
            rationale = f"Unsupported monitoring recommendation {row['recommended_mode']!r}."
        current_counts[state] += 1
        rows.append(
            {
                "source_id": row["source_id"],
                "accountability_state": state,
                "recommended_mode": row["recommended_mode"],
                "recommended_cadence": row["recommended_cadence"],
                "source_class": row["source_class"],
                "publisher": row["publisher"],
                "url": row["url"],
                "lifecycle_state": row.get("lifecycle_state"),
                "successor_discovery_watch_id": row.get("successor_discovery_watch_id"),
                "lifecycle_transition_sha256": row.get("lifecycle_transition_sha256"),
                "rationale": rationale,
            }
        )

    candidate_ids = {record["source_id"] for record in candidate_monitors}
    candidate_rows: list[dict[str, Any]] = []
    candidate_counts: Counter[str] = Counter()
    for row in rows:
        candidate_row = dict(row)
        if row["source_id"] in candidate_ids:
            candidate_row["accountability_state"] = "MONITORED_CANDIDATE"
            candidate_row["rationale"] = "Development recurring-monitor extension candidate generated from exact eligibility rule."
        candidate_counts[str(candidate_row["accountability_state"])] += 1
        candidate_rows.append(candidate_row)

    projection: dict[str, Any] = {
        "schema_version": "2",
        "status": "CURRENT_OPERATIONAL_ACCOUNTABILITY_WITH_LIFECYCLE_AND_NONCANONICAL_EXTENSION_CANDIDATE",
        "inputs": {
            "effective_sources_sha256": sha256(sources),
            "governing_monitor_registry_sha256": sha256(monitors),
            "eligibility_projection_sha256": sha256(eligibility),
            "lifecycle_transition_sha256s": sorted(
                str(item["transition_sha256"]) for item in transitions.values()
            ),
        },
        "current": {
            "effective_source_count": len(rows),
            "counts": dict(sorted(current_counts.items())),
            "coverage_fraction": (len(rows) - current_counts["GAP"]) / len(rows) if rows else 1.0,
            "gap_source_ids": sorted(row["source_id"] for row in recurring_gaps),
            "gap_mode_counts": dict(sorted(Counter(row["recommended_mode"] for row in recurring_gaps).items())),
            "lifecycle_resolved_source_ids": sorted(lifecycle_resolved_ids),
            "sources": rows,
        },
        "monitor_extension_candidate": {
            "status": "DEVELOPMENT_MONITOR_EXTENSION_NOT_CANONICAL",
            "predecessor_monitor_count": len(monitors),
            "candidate_record_count": len(candidate_monitors),
            "candidate_records": candidate_monitors,
            "lifecycle_resolved_source_ids": sorted(lifecycle_resolved_ids),
            "boundary": CANDIDATE_BOUNDARY,
        },
        "candidate_accountability": {
            "effective_source_count": len(candidate_rows),
            "counts": dict(sorted(candidate_counts.items())),
            "coverage_fraction": 1.0 if not any(row["accountability_state"] == "GAP" for row in candidate_rows) else 0.0,
            "gap_source_ids": sorted(
                row["source_id"] for row in candidate_rows if row["accountability_state"] == "GAP"
            ),
            "lifecycle_resolved_source_ids": sorted(lifecycle_resolved_ids),
            "sources": candidate_rows,
        },
        "boundary": BOUNDARY,
    }
    projection["projection_sha256"] = sha256(projection)
    return projection


def verify_expected_current_checkpoint(projection: dict[str, Any]) -> None:
    current = projection["current"]
    counts = current["counts"]
    if current["effective_source_count"] != 248:
        raise ValueError(f"Expected 248 effective sources, got {current['effective_source_count']}")
    expected = {
        "MONITORED": 224,
        "EXEMPT_WITH_RATIONALE": 15,
        "MANUAL_ONLY": 6,
        "GAP": 2,
        MONITORING_STATE: 1,
    }
    if {key: counts.get(key, 0) for key in expected} != expected:
        raise ValueError(f"Current accountability counts changed: {counts}")
    if current.get("lifecycle_resolved_source_ids") != ["SRC-PR-015"]:
        raise ValueError(f"Lifecycle-resolved source set changed: {current.get('lifecycle_resolved_source_ids')}")
    candidate = projection["monitor_extension_candidate"]
    if candidate["candidate_record_count"] != 2:
        raise ValueError(f"Expected two recurring monitor candidates, got {candidate['candidate_record_count']}")
    candidate_ids = {str(item["source_id"]) for item in candidate["candidate_records"]}
    if candidate_ids != {"SRC-PR-002", "SRC-PR-007"}:
        raise ValueError(f"Recurring monitor candidate set changed: {sorted(candidate_ids)}")
    candidate_accountability = projection["candidate_accountability"]
    if candidate_accountability["gap_source_ids"]:
        raise ValueError(f"Candidate accountability still contains gaps: {candidate_accountability['gap_source_ids']}")
    if candidate_accountability["coverage_fraction"] != 1.0:
        raise ValueError("Candidate accountability must reach 1.0")


def write_projection(projection: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "current-monitoring-accountability.json"
    path.write_bytes(json.dumps(projection, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n")
    candidate = projection["monitor_extension_candidate"]
    (output_dir / "monitor-extension-candidate.json").write_bytes(
        json.dumps(candidate, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument("--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR)
    parser.add_argument("--route-policy", type=Path, default=DEFAULT_ROUTE_POLICY)
    parser.add_argument("--lifecycle-overlay", type=Path, default=DEFAULT_LIFECYCLE_OVERLAY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    inputs = load_inputs(args.records_dir.resolve(), supplemental_dir=args.supplemental_dir.resolve())
    tables = build_tables(inputs)
    source_ids = {str(row["record_id"]) for row in tables["sources"] if row.get("record_id")}
    monitor_ids = {str(row["record_id"]) for row in tables["source_monitors"] if row.get("record_id")}
    _, _, transitions = load_verified_lifecycle_overlay(
        route_policy_path=args.route_policy,
        overlay_path=args.lifecycle_overlay,
        effective_source_ids=source_ids,
        governing_monitor_source_ids=monitor_ids,
    )
    projection = build_projection(tables["sources"], tables["source_monitors"], transitions)
    verify_expected_current_checkpoint(projection)
    path = write_projection(projection, args.output_dir.resolve())
    print(
        json.dumps(
            {
                "output": str(path),
                "current_counts": projection["current"]["counts"],
                "current_gap_source_ids": projection["current"]["gap_source_ids"],
                "lifecycle_resolved_source_ids": projection["current"]["lifecycle_resolved_source_ids"],
                "candidate_records": projection["monitor_extension_candidate"]["candidate_records"],
                "candidate_counts": projection["candidate_accountability"]["counts"],
                "projection_sha256": projection["projection_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

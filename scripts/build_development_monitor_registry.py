#!/usr/bin/env python3
"""Build a noncanonical 227-monitor development registry view over the exact current 248-source universe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_analytical_projection import DEFAULT_RECORDS_DIR, DEFAULT_SUPPLEMENTAL_DIR, build_tables, load_inputs
from build_current_monitor_accountability import build_projection, sha256

DEFAULT_OUTPUT = Path("analytics/operational-accountability/development-monitor-registry.json")
STATUS = "DEVELOPMENT_MONITOR_REGISTRY_VIEW_NOT_CANONICAL"
BOUNDARY = (
    "This development registry view combines the immutable 224-record v1.5 predecessor with exact recurring-monitor "
    "candidates needed for declared-source operational coverage. It is noncanonical, does not rewrite the predecessor, "
    "and does not establish source truth, assessment validity, governance approval, UNESCO endorsement, or release authority."
)
REQUIRED_MONITOR_FIELDS = frozenset(
    {
        "monitor_id",
        "source_id",
        "url",
        "publisher",
        "source_class",
        "cadence",
        "baseline_evidence_state",
        "baseline_verification_state",
        "baseline_claim_boundary",
        "network_access_required",
        "current_status",
        "next_action",
    }
)
SUPPORTED_CADENCES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL", "MANUAL"})


def _validate_monitor(record: dict[str, Any], *, candidate: bool) -> None:
    missing = sorted(REQUIRED_MONITOR_FIELDS - record.keys())
    if missing:
        raise ValueError(f"Monitor {record.get('monitor_id')!r} is missing fields: {', '.join(missing)}")
    if record["cadence"] not in SUPPORTED_CADENCES:
        raise ValueError(f"Monitor {record['monitor_id']!r} has unsupported cadence {record['cadence']!r}")
    if not isinstance(record["network_access_required"], bool):
        raise ValueError(f"Monitor {record['monitor_id']!r} network_access_required must be boolean")
    if candidate and record.get("current_status") != "DEVELOPMENT_MONITOR_EXTENSION_NOT_CANONICAL":
        raise ValueError(f"Candidate monitor {record['monitor_id']!r} lost its noncanonical state")


def build_development_registry(inputs: dict[str, Any]) -> dict[str, Any]:
    raw_predecessor = inputs["v15_registry"]
    if not isinstance(raw_predecessor, list) or not all(isinstance(item, dict) for item in raw_predecessor):
        raise ValueError("The governing v1.5 monitor registry must be a list of objects")

    tables = build_tables(inputs)
    accountability = build_projection(tables["sources"], tables["source_monitors"])
    candidate = accountability["monitor_extension_candidate"]
    candidate_records = candidate["candidate_records"]
    if accountability["candidate_accountability"]["coverage_fraction"] != 1.0:
        raise ValueError("Development registry cannot be built while candidate accountability contains a gap")
    if accountability["candidate_accountability"]["gap_source_ids"]:
        raise ValueError("Development registry cannot be built while candidate gap IDs remain")
    if len(raw_predecessor) != 224:
        raise ValueError(f"Expected immutable predecessor count 224, got {len(raw_predecessor)}")
    if len(candidate_records) != 3:
        raise ValueError(f"Expected exactly three recurring extension candidates, got {len(candidate_records)}")

    predecessor = [dict(record) for record in raw_predecessor]
    extension = [dict(record) for record in candidate_records]
    for record in predecessor:
        _validate_monitor(record, candidate=False)
    for record in extension:
        _validate_monitor(record, candidate=True)

    combined = predecessor + extension
    monitor_ids = [str(record["monitor_id"]) for record in combined]
    source_ids = [str(record["source_id"]) for record in combined]
    if len(set(monitor_ids)) != len(monitor_ids):
        raise ValueError("Development registry contains duplicate monitor_id values")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Development registry contains duplicate source_id bindings")

    expected_candidates = {"SRC-PR-002", "SRC-PR-007", "SRC-PR-015"}
    observed_candidates = {str(record["source_id"]) for record in extension}
    if observed_candidates != expected_candidates:
        raise ValueError(f"Recurring extension candidate set changed: {sorted(observed_candidates)}")

    registry: dict[str, Any] = {
        "metadata": {
            "title": "NeuroAI development monitor registry view",
            "version": "v2.3.0-dev-operational",
            "source_release": "v1.5-plus-v2.3.0-dev-extension-candidate",
            "status": STATUS,
            "record_count": len(combined),
            "predecessor_record_count": len(predecessor),
            "extension_record_count": len(extension),
            "predecessor_registry_sha256": sha256(predecessor),
            "extension_candidate_sha256": sha256(extension),
            "accountability_projection_sha256": accountability["projection_sha256"],
            "effective_source_count": accountability["current"]["effective_source_count"],
            "candidate_accountability_coverage_fraction": accountability["candidate_accountability"]["coverage_fraction"],
            "boundary": BOUNDARY,
        },
        "sources": combined,
    }
    registry["metadata"]["registry_view_sha256"] = sha256(registry)
    return registry


def verify_development_registry(registry: dict[str, Any]) -> None:
    metadata = registry.get("metadata", {})
    sources = registry.get("sources", [])
    if metadata.get("status") != STATUS:
        raise ValueError("Development registry lost its explicit noncanonical status")
    if metadata.get("record_count") != 227 or len(sources) != 227:
        raise ValueError(f"Development registry must contain exactly 227 monitors, got {len(sources)}")
    if metadata.get("predecessor_record_count") != 224 or metadata.get("extension_record_count") != 3:
        raise ValueError("Development registry predecessor/extension counts are invalid")
    if metadata.get("effective_source_count") != 248:
        raise ValueError("Development registry must remain bound to the 248-source effective namespace")
    if metadata.get("candidate_accountability_coverage_fraction") != 1.0:
        raise ValueError("Development registry accountability coverage must be 1.0")
    observed_hash = metadata.get("registry_view_sha256")
    candidate = json.loads(json.dumps(registry))
    candidate["metadata"].pop("registry_view_sha256", None)
    if observed_hash != sha256(candidate):
        raise ValueError("Development registry view hash mismatch")


def write_registry(registry: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument("--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inputs = load_inputs(args.records_dir.resolve(), supplemental_dir=args.supplemental_dir.resolve())
    registry = build_development_registry(inputs)
    verify_development_registry(registry)
    path = write_registry(registry, args.output.resolve())
    print(
        json.dumps(
            {
                "output": str(path),
                "monitor_count": registry["metadata"]["record_count"],
                "extension_count": registry["metadata"]["extension_record_count"],
                "effective_source_count": registry["metadata"]["effective_source_count"],
                "coverage_fraction": registry["metadata"]["candidate_accountability_coverage_fraction"],
                "registry_view_sha256": registry["metadata"]["registry_view_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the noncanonical active-monitor development registry over the 248-source universe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_analytical_projection import (
    DEFAULT_RECORDS_DIR,
    DEFAULT_SUPPLEMENTAL_DIR,
    build_tables,
    load_inputs,
)
from build_current_monitor_accountability import build_projection, sha256
from source_lifecycle_overlay import (
    DEFAULT_LIFECYCLE_OVERLAY,
    DEFAULT_ROUTE_POLICY,
    load_verified_lifecycle_overlay,
)

DEFAULT_OUTPUT = Path(
    "analytics/operational-accountability/development-monitor-registry.json"
)
STATUS = "DEVELOPMENT_MONITOR_REGISTRY_VIEW_NOT_CANONICAL"
BOUNDARY = (
    "This development registry view combines the immutable 224-record v1.5 predecessor with exact active recurring-monitor "
    "candidates needed for declared-source operational coverage. Evidence-bound lifecycle-resolved sources remain in the "
    "248-source accountability namespace without an active monitor record. This view is noncanonical, does not rewrite the "
    "predecessor, and does not establish source truth, assessment validity, governance approval, UNESCO endorsement, or release authority."
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
SUPPORTED_CADENCES = frozenset(
    {"DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL", "MANUAL"}
)


def _validate_monitor(record: dict[str, Any], *, candidate: bool) -> None:
    missing = sorted(REQUIRED_MONITOR_FIELDS - record.keys())
    if missing:
        raise ValueError(
            f"Monitor {record.get('monitor_id')!r} is missing fields: {', '.join(missing)}"
        )
    if record["cadence"] not in SUPPORTED_CADENCES:
        raise ValueError(
            f"Monitor {record['monitor_id']!r} has unsupported cadence {record['cadence']!r}"
        )
    if not isinstance(record["network_access_required"], bool):
        raise ValueError(
            f"Monitor {record['monitor_id']!r} network_access_required must be boolean"
        )
    if (
        candidate
        and record.get("current_status")
        != "DEVELOPMENT_MONITOR_EXTENSION_NOT_CANONICAL"
    ):
        raise ValueError(
            f"Candidate monitor {record['monitor_id']!r} lost its noncanonical state"
        )


def build_development_registry(
    inputs: dict[str, Any],
    lifecycle_transitions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    transitions = lifecycle_transitions or {}
    raw_predecessor = inputs["v15_registry"]
    if not isinstance(raw_predecessor, list) or not all(
        isinstance(item, dict) for item in raw_predecessor
    ):
        raise ValueError(
            "The governing v1.5 monitor registry must be a list of objects"
        )

    tables = build_tables(inputs)
    accountability = build_projection(
        tables["sources"], tables["source_monitors"], transitions
    )
    candidate = accountability["monitor_extension_candidate"]
    candidate_records = candidate["candidate_records"]
    if accountability["candidate_accountability"]["coverage_fraction"] != 1.0:
        raise ValueError(
            "Development registry cannot be built while candidate accountability contains a gap"
        )
    if accountability["candidate_accountability"]["gap_source_ids"]:
        raise ValueError(
            "Development registry cannot be built while candidate gap IDs remain"
        )
    if len(raw_predecessor) != 224:
        raise ValueError(
            f"Expected immutable predecessor count 224, got {len(raw_predecessor)}"
        )
    if len(candidate_records) != 2:
        raise ValueError(
            f"Expected exactly two active recurring extension candidates, got {len(candidate_records)}"
        )

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
    lifecycle_source_ids = sorted(transitions)
    if set(lifecycle_source_ids) & set(source_ids):
        raise ValueError(
            "Lifecycle-resolved source leaked into active development monitor registry"
        )

    expected_candidates = {"SRC-PR-002", "SRC-PR-007"}
    observed_candidates = {str(record["source_id"]) for record in extension}
    if observed_candidates != expected_candidates:
        raise ValueError(
            f"Recurring extension candidate set changed: {sorted(observed_candidates)}"
        )

    registry: dict[str, Any] = {
        "metadata": {
            "title": "NeuroAI active development monitor registry view",
            "version": "v2.3.0-dev-operational",
            "source_release": "v1.5-plus-v2.3.0-dev-active-extension-candidate",
            "status": STATUS,
            "record_count": len(combined),
            "predecessor_record_count": len(predecessor),
            "extension_record_count": len(extension),
            "lifecycle_resolved_source_count": len(lifecycle_source_ids),
            "lifecycle_resolved_source_ids": lifecycle_source_ids,
            "lifecycle_transition_sha256s": sorted(
                str(item["transition_sha256"]) for item in transitions.values()
            ),
            "predecessor_registry_sha256": sha256(predecessor),
            "extension_candidate_sha256": sha256(extension),
            "accountability_projection_sha256": accountability["projection_sha256"],
            "effective_source_count": accountability["current"][
                "effective_source_count"
            ],
            "candidate_accountability_coverage_fraction": accountability[
                "candidate_accountability"
            ]["coverage_fraction"],
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
    if metadata.get("record_count") != 226 or len(sources) != 226:
        raise ValueError(
            f"Development registry must contain exactly 226 active monitors, got {len(sources)}"
        )
    if (
        metadata.get("predecessor_record_count") != 224
        or metadata.get("extension_record_count") != 2
    ):
        raise ValueError(
            "Development registry predecessor/extension counts are invalid"
        )
    if metadata.get("lifecycle_resolved_source_count") != 1:
        raise ValueError(
            "Development registry must bind exactly one lifecycle-resolved source"
        )
    if metadata.get("lifecycle_resolved_source_ids") != ["SRC-PR-015"]:
        raise ValueError("Development registry lifecycle-resolved source set changed")
    if any(str(record.get("source_id")) == "SRC-PR-015" for record in sources):
        raise ValueError("Lifecycle-resolved source remains in active monitor registry")
    if metadata.get("effective_source_count") != 248:
        raise ValueError(
            "Development registry must remain bound to the 248-source effective namespace"
        )
    if metadata.get("candidate_accountability_coverage_fraction") != 1.0:
        raise ValueError("Development registry accountability coverage must be 1.0")
    observed_hash = metadata.get("registry_view_sha256")
    candidate = json.loads(json.dumps(registry))
    candidate["metadata"].pop("registry_view_sha256", None)
    if observed_hash != sha256(candidate):
        raise ValueError("Development registry view hash mismatch")


def write_registry(registry: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument(
        "--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR
    )
    parser.add_argument("--route-policy", type=Path, default=DEFAULT_ROUTE_POLICY)
    parser.add_argument(
        "--lifecycle-overlay", type=Path, default=DEFAULT_LIFECYCLE_OVERLAY
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inputs = load_inputs(
        args.records_dir.resolve(), supplemental_dir=args.supplemental_dir.resolve()
    )
    tables = build_tables(inputs)
    source_ids = {
        str(row["record_id"]) for row in tables["sources"] if row.get("record_id")
    }
    monitor_ids = {
        str(row["record_id"])
        for row in tables["source_monitors"]
        if row.get("record_id")
    }
    _, _, transitions = load_verified_lifecycle_overlay(
        route_policy_path=args.route_policy,
        overlay_path=args.lifecycle_overlay,
        effective_source_ids=source_ids,
        governing_monitor_source_ids=monitor_ids,
    )
    registry = build_development_registry(inputs, transitions)
    verify_development_registry(registry)
    path = write_registry(registry, args.output.resolve())
    print(
        json.dumps(
            {
                "output": str(path),
                "monitor_count": registry["metadata"]["record_count"],
                "extension_count": registry["metadata"]["extension_record_count"],
                "lifecycle_resolved_source_ids": registry["metadata"][
                    "lifecycle_resolved_source_ids"
                ],
                "effective_source_count": registry["metadata"][
                    "effective_source_count"
                ],
                "coverage_fraction": registry["metadata"][
                    "candidate_accountability_coverage_fraction"
                ],
                "registry_view_sha256": registry["metadata"]["registry_view_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

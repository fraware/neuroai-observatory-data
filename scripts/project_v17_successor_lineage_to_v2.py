#!/usr/bin/env python3
"""Project v1.7 compact successor lineage without duplicating v1.6 substantive state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
RECORDS = ROOT / "releases/data-v0.1.0-public-governing/records"
DEFAULT_V17 = RECORDS / "canonical_successor_snapshot_v1.7.json"
DEFAULT_V16 = RECORDS / "canonical_live_refresh_release_v1.6.json"
DEFAULT_DELTA = RECORDS / "adjudicated_delta_v1.6.json"
EXPECTED_TOP_LEVEL = {
    "metadata", "baseline_reference", "baseline_counts", "delta_counts", "successor_effective_counts",
    "delta", "reopening_decisions", "provenance", "predecessor_reference", "assessment_successor_delta",
}


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def project(v17_path: Path = DEFAULT_V17, v16_path: Path = DEFAULT_V16, delta_path: Path = DEFAULT_DELTA) -> dict[str, Any]:
    v17 = json.loads(v17_path.read_text(encoding="utf-8"))
    v16 = json.loads(v16_path.read_text(encoding="utf-8"))
    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    if not all(isinstance(v, dict) for v in (v17, v16, delta)):
        raise ValueError("v1.7/v1.6/delta inputs must be objects")
    actual = set(v17)
    unknown = sorted(actual - EXPECTED_TOP_LEVEL)
    missing = sorted(EXPECTED_TOP_LEVEL - actual)
    if unknown or missing:
        raise ValueError(f"v1.7 top-level mismatch unknown={unknown} missing={missing}")
    if v17["delta"] != delta:
        raise ValueError("v1.7 repeated delta differs from standalone v1.6 adjudicated delta")

    v16_reopen = {r["decision_id"]: r for r in v16.get("reopening_decisions", []) if isinstance(r, dict) and isinstance(r.get("decision_id"), str)}
    v17_reopen = {r["decision_id"]: r for r in v17.get("reopening_decisions", []) if isinstance(r, dict) and isinstance(r.get("decision_id"), str)}
    carried_ids = [f"ROP-16-00{i}" for i in range(2, 7)]
    carried_mismatch = [rid for rid in carried_ids if v17_reopen.get(rid) != v16_reopen.get(rid)]
    if carried_mismatch:
        raise ValueError(f"carried reopening decision mismatch: {carried_mismatch}")
    new_decision = v17_reopen.get("ROP-17-001")
    if not isinstance(new_decision, dict):
        raise ValueError("v1.7 ROP-17-001 missing")

    asd = v17.get("assessment_successor_delta")
    if not isinstance(asd, dict):
        raise ValueError("assessment_successor_delta missing")
    transition = asd.get("reopening_transition")
    assessment = asd.get("assessment_delta")
    bounded = asd.get("bounded_system_record")
    prohibited = asd.get("prohibited_inferences")
    source_delta = asd.get("source_delta")
    if not all(isinstance(v, dict) for v in (transition, assessment, bounded, source_delta)) or not isinstance(prohibited, list):
        raise ValueError("invalid assessment successor delta structure")
    if transition.get("predecessor_decision_id") != "ROP-16-001" or transition.get("successor_decision_id") != "ROP-17-001":
        raise ValueError("unexpected reopening transition IDs")

    record = {
        "schema_version": "2.0.0-draft",
        "successor_id": "OBSERVATORY-v1.7-MIGRATED-CANDIDATE",
        "predecessor_version": "v1.6",
        "effective_as_of": {"value": v17["metadata"]["effective_as_of"], "precision": "DATE"},
        "repeated_v16_delta_state": "VERIFIED_REFERENCE_NOT_REEMITTED",
        "repeated_v16_delta_digest": _digest(delta),
        "carried_reopening_decision_ids": carried_ids,
        "new_reopening_decision": json.loads(json.dumps(new_decision)),
        "reopening_transition": json.loads(json.dumps(transition)),
        "assessment_successor_state": json.loads(json.dumps(assessment)),
        "bounded_system_record": json.loads(json.dumps(bounded)),
        "prohibited_inferences": json.loads(json.dumps(prohibited)),
        "source_delta_provenance": json.loads(json.dumps(source_delta)),
        "count_summaries": {
            "baseline_counts": json.loads(json.dumps(v17["baseline_counts"])),
            "delta_counts": json.loads(json.dumps(v17["delta_counts"])),
            "successor_effective_counts": json.loads(json.dumps(v17["successor_effective_counts"])),
        },
        "predecessor_and_release_provenance": {
            "metadata": json.loads(json.dumps(v17["metadata"])),
            "baseline_reference": json.loads(json.dumps(v17["baseline_reference"])),
            "provenance": json.loads(json.dumps(v17["provenance"])),
            "predecessor_reference": json.loads(json.dumps(v17["predecessor_reference"])),
            "assessment_successor_metadata": json.loads(json.dumps(asd.get("metadata"))),
            "assessment_predecessor_reference": json.loads(json.dumps(asd.get("predecessor_reference"))),
            "event_delta": json.loads(json.dumps(asd.get("event_delta"))),
        },
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_successor_snapshot_v1.7.json",
            "record_sha256": _digest(v17),
            "payload": json.loads(json.dumps(v17)),
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": "Preserves compact v1.7 successor lineage. Repeated v1.6 state is referenced, not emitted as new change records; assessment state is not reinterpreted or recomputed.",
    }

    reconciliation = {
        "scope": "V1.7_COMPACT_SUCCESSOR_LINEAGE",
        "top_level_section_count": len(actual),
        "unknown_top_level_sections": unknown,
        "missing_expected_top_level_sections": missing,
        "repeated_v16_delta_equal": True,
        "repeated_v16_delta_new_identity_count": 0,
        "carried_reopening_decision_count": len(carried_ids),
        "carried_reopening_mismatch_count": len(carried_mismatch),
        "new_successor_reopening_decision_count": 1,
        "source_delta_new_unique_source_count_provenance_only": source_delta.get("new_unique_source_records_relative_to_v1_6"),
        "fabricated_source_record_count": 0,
        "assessment_reinterpretation_count": 0,
        "count_expansion_to_entities_count": 0,
        "predecessor_payload_roundtrip_failure_count": 0 if record["predecessor"]["payload"] == v17 else 1,
        "canonical_successor_ready": False,
        "authority_boundary": "This proves only compact-successor migration mechanics and predecessor-lineage preservation, not canonical v2 authority.",
    }
    return {"successor_lineage": record, "reconciliation": reconciliation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v17", type=Path, default=DEFAULT_V17)
    parser.add_argument("--v16", type=Path, default=DEFAULT_V16)
    parser.add_argument("--delta", type=Path, default=DEFAULT_DELTA)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = project(args.v17, args.v16, args.delta)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

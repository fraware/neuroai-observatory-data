#!/usr/bin/env python3
"""Materialize the effective public source namespace from actual migrated source records.

The count is derived from source identities, not summary arithmetic. This is a controlled
namespace reconciliation only and does not claim global completeness.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
V17 = ROOT / "releases/data-v0.1.0-public-governing/records/canonical_successor_snapshot_v1.7.json"
PROJECTORS = {
    "V1_4_BASELINE": "project_v14_sources_to_v2.py",
    "V1_6_REFRESH": "project_v16_sources_observations_to_v2.py",
    "V1_7_PRIMA_SUPPLEMENTAL": "project_v17_prima_sources_to_v2.py",
}


def _load(filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(filename.replace('.', '_'), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reconcile() -> dict[str, Any]:
    materialized: dict[str, dict[str, Any]] = {}
    family_counts: dict[str, int] = {}
    duplicate_ids: list[str] = []
    for family, filename in PROJECTORS.items():
        result = _load(filename).project()
        sources = result.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"{filename} did not return sources list")
        family_counts[family] = len(sources)
        for source in sources:
            sid = source.get("source_id") if isinstance(source, dict) else None
            if not isinstance(sid, str) or not sid:
                raise ValueError(f"{family}: invalid source identity")
            if sid in materialized:
                duplicate_ids.append(sid)
                continue
            materialized[sid] = {
                "source_id": sid,
                "lineage_family": family,
                "predecessor_file": source.get("predecessor", {}).get("file"),
                "predecessor_record_id": source.get("predecessor", {}).get("record_id"),
            }

    successor = json.loads(V17.read_text(encoding="utf-8"))
    declared = successor["successor_effective_counts"]["source_records"]
    materialized_count = len(materialized)
    expected_family_counts = {"V1_4_BASELINE": 224, "V1_6_REFRESH": 12, "V1_7_PRIMA_SUPPLEMENTAL": 12}
    family_mismatches = {
        family: {"expected": expected, "actual": family_counts.get(family)}
        for family, expected in expected_family_counts.items()
        if family_counts.get(family) != expected
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_EFFECTIVE_SOURCE_NAMESPACE_RECONCILIATION",
        "family_counts": family_counts,
        "expected_family_counts": expected_family_counts,
        "family_count_mismatches": family_mismatches,
        "materialized_unique_source_count": materialized_count,
        "v1_7_declared_effective_source_count": declared,
        "materialized_matches_declared": materialized_count == declared,
        "duplicate_source_ids": sorted(set(duplicate_ids)),
        "duplicate_source_id_count": len(set(duplicate_ids)),
        "source_namespace": [materialized[sid] for sid in sorted(materialized)],
        "global_completeness_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "The 248 count is the materialized effective controlled evidence namespace from actual predecessor records. "
            "It is not a claim that the observatory has discovered every NeuroAI source globally."
        ),
    }


def main() -> int:
    result = reconcile()
    print(json.dumps(result, indent=2, sort_keys=True))
    bad = bool(result["family_count_mismatches"] or result["duplicate_source_id_count"] or not result["materialized_matches_declared"])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

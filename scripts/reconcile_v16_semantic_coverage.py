#!/usr/bin/env python3
"""Aggregate all v1.6 migration slices into one noncanonical semantic-coverage report."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
SCRIPTS = {
    "source_observations": "project_v16_sources_observations_to_v2.py",
    "change_candidates": "project_v16_change_candidates_to_v2.py",
    "adjudicated_delta": "project_v16_adjudicated_delta_to_v2.py",
    "reopening_nochange": "project_v16_reopening_nochange_to_v2.py",
    "control_state": "project_v16_control_state_to_v2.py",
}


def _load_module(name: str, filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bad_counter(key: str, value: Any) -> bool:
    if not isinstance(value, int):
        return False
    tokens = ("loss_count", "failure_count", "fabrication_count", "unresolved_accepted_basis_reference_count", "embedded_double_count")
    return any(token in key for token in tokens) and value != 0


def reconcile() -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    blockers: list[dict[str, Any]] = []
    for name, filename in SCRIPTS.items():
        module = _load_module(f"v16_{name}", filename)
        result = module.project()
        rec = result.get("reconciliation")
        if not isinstance(rec, dict):
            raise ValueError(f"{filename} did not return reconciliation object")
        reports[name] = rec
        if rec.get("canonical_successor_ready") is not False:
            blockers.append({"slice": name, "key": "canonical_successor_ready", "value": rec.get("canonical_successor_ready")})
        for key, value in rec.items():
            if _bad_counter(key, value):
                blockers.append({"slice": name, "key": key, "value": value})

    coverage = reports["control_state"]
    if coverage.get("unknown_top_level_sections") != []:
        blockers.append({"slice": "control_state", "key": "unknown_top_level_sections", "value": coverage.get("unknown_top_level_sections")})
    if coverage.get("missing_expected_top_level_sections") != []:
        blockers.append({"slice": "control_state", "key": "missing_expected_top_level_sections", "value": coverage.get("missing_expected_top_level_sections")})

    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V16_SEMANTIC_RECONCILIATION",
        "slice_count": len(reports),
        "slices": reports,
        "mechanical_blocker_count": len(blockers),
        "mechanical_blockers": blockers,
        "all_known_v16_top_level_sections_accounted": not blockers and coverage.get("top_level_section_count") == coverage.get("accounted_top_level_section_count"),
        "canonical_successor_ready": False,
        "authority_boundary": (
            "This report proves only mechanical migration coverage for known v1.6 sections and encoded invariants. "
            "It does not prove scientific correctness, domain validity, institutional authority, or canonical successor readiness."
        ),
    }


def main() -> int:
    result = reconcile()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["mechanical_blocker_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Assemble the current public Observatory lineage into one noncanonical v2 candidate.

This is a migration/mechanical assembly only. It deliberately preserves baseline, refresh,
and successor lineage rather than flattening them into a new substantive truth state. A
mechanically clean result never authorizes canonical publication.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SLICE_MODULES = {
    "v14_sources": "project_v14_sources_to_v2",
    "v14_organizations": "project_v14_organizations_to_v2",
    "v14_models": "project_v14_models_to_v2",
    "v14_registries": "project_v14_model_dataset_registry_to_v2",
    "v14_relationships": "project_v14_relationships_to_v2",
    "v14_capital_events": "project_v14_capital_events_to_v2",
    "v14_provenance": "project_v14_provenance_to_v2",
    "v16_sources_observations": "project_v16_sources_observations_to_v2",
    "v16_change_candidates": "project_v16_change_candidates_to_v2",
    "v16_adjudicated_delta": "project_v16_adjudicated_delta_to_v2",
    "v16_reopening_nochange": "project_v16_reopening_nochange_to_v2",
    "v16_control": "project_v16_control_state_to_v2",
    "v17_successor_lineage": "project_v17_successor_lineage_to_v2",
    "v17_prima_sources": "project_v17_prima_sources_to_v2",
}

FAMILY_ID_FIELDS = {
    "sources": "source_id",
    "observations": "observation_id",
    "entities": "entity_id",
    "assertions": "assertion_id",
    "relationships": "relationship_id",
    "events": "event_id",
    "change_candidates": "candidate_id",
    "reopening_decisions": "decision_id",
}

BLOCKER_TOKENS = (
    "loss",
    "failure",
    "mismatch",
    "fabrication",
    "dangling",
    "duplicate",
    "double_count",
    "unknown_top_level",
    "missing_expected",
    "unresolved_accepted_basis",
    "conflict",
    "blocker",
)


def _canonical_line(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_slice(module_name: str) -> dict[str, Any]:
    module = importlib.import_module(module_name)
    project = getattr(module, "project", None)
    if not callable(project):
        raise RuntimeError(f"{module_name} does not expose callable project()")
    result = project()
    if not isinstance(result, dict) or not isinstance(result.get("reconciliation"), dict):
        raise RuntimeError(f"{module_name} returned no reconciliation object")
    return result


def _blocking_reconciliation_values(reconciliation: dict[str, Any]) -> dict[str, Any]:
    blockers: dict[str, Any] = {}
    for key, value in reconciliation.items():
        lower = key.lower()
        if not any(token in lower for token in BLOCKER_TOKENS):
            continue
        if isinstance(value, bool):
            if value:
                blockers[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if value != 0:
                blockers[key] = value
        elif isinstance(value, (list, dict, str)) and value:
            blockers[key] = value
    return blockers


def _extend_if_list(target: list[dict[str, Any]], value: Any, *, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise RuntimeError(f"{label} must be a list of objects")
    target.extend(value)


def _collect_references(value: Any, key: str) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key:
                if not isinstance(v, list) or not all(isinstance(item, str) and item for item in v):
                    raise RuntimeError(f"{key} must always be a string array when present")
                refs.extend(v)
            refs.extend(_collect_references(v, key))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_collect_references(item, key))
    return refs


def _dedupe_family(
    rows: list[dict[str, Any]], id_field: str
) -> tuple[list[dict[str, Any]], dict[str, list[str]], int]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rid = row.get(id_field)
        if not isinstance(rid, str) or not rid:
            raise RuntimeError(f"Family record missing {id_field}")
        by_id[rid].append(row)

    conflicts: dict[str, list[str]] = {}
    output: list[dict[str, Any]] = []
    identical_duplicate_count = 0
    for rid in sorted(by_id):
        variants = by_id[rid]
        digests = sorted({_sha256_bytes(_canonical_line(row)) for row in variants})
        if len(digests) > 1:
            conflicts[rid] = digests
            continue
        output.append(variants[0])
        identical_duplicate_count += max(0, len(variants) - 1)
    return output, conflicts, identical_duplicate_count


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> tuple[int, str]:
    payload = b"".join(_canonical_line(row) for row in rows)
    path.write_bytes(payload)
    return len(payload), _sha256_bytes(payload)


def _effective_state_reconciliation(
    families: dict[str, list[dict[str, Any]]], successor_lineage: list[dict[str, Any]]
) -> dict[str, Any]:
    if len(successor_lineage) != 1:
        return {
            "state": "UNRESOLVED",
            "mismatch_count": 1,
            "reason": f"Expected one v1.7 successor-lineage record, found {len(successor_lineage)}",
        }

    declared = successor_lineage[0]["count_summaries"]["successor_effective_counts"]

    active_orgs = 0
    current_verified_active = 0
    for entity in families["entities"]:
        if entity.get("entity_kind") != "ORGANIZATION":
            continue
        predecessor = entity.get("predecessor", {}).get("payload", {})
        if predecessor.get("current_status") == "ACTIVE_OR_CURRENTLY_REPRESENTED" and predecessor.get("verification_state") != "LEGACY_ONLY":
            active_orgs += 1
            if predecessor.get("verification_state") == "CURRENT_VERIFIED":
                current_verified_active += 1

    capital_events = sum(1 for row in families["events"] if row.get("event_family") == "CAPITAL_AND_OWNERSHIP")
    model_records = sum(1 for row in families["entities"] if row.get("entity_kind") == "MODEL")
    supplier_dependencies = sum(1 for row in families["relationships"] if row.get("relationship_family") == "SUPPLIER_DEPENDENCY")
    sources = len(families["sources"])

    materialized = {
        "organizations": active_orgs,
        "current_verified_organizations": current_verified_active,
        "capital_and_ownership_events": capital_events,
        "representative_model_records": model_records,
        "supplier_dependency_relationships": supplier_dependencies,
        "source_records": sources,
    }
    comparisons = {
        key: {"declared": declared.get(key), "materialized": materialized[key]}
        for key in materialized
    }
    mismatches = {key: value for key, value in comparisons.items() if value["declared"] != value["materialized"]}

    return {
        "state": "RECONCILED_FOR_MATERIALIZABLE_S2_EFFECTIVE_COUNTS" if not mismatches else "MISMATCH",
        "declared_completed_system_assessments": declared.get("completed_system_assessments"),
        "assessment_object_materialization_state": "NOT_EXPANDED_FROM_SUMMARY_COUNT",
        "materialized_counts": materialized,
        "comparisons": comparisons,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }


def build() -> dict[str, Any]:
    slice_results: dict[str, dict[str, Any]] = {}
    slice_blockers: dict[str, dict[str, Any]] = {}
    for label, module_name in SLICE_MODULES.items():
        result = _run_slice(module_name)
        slice_results[label] = result
        blockers = _blocking_reconciliation_values(result["reconciliation"])
        if blockers:
            slice_blockers[label] = blockers

    v16_coverage = importlib.import_module("reconcile_v16_semantic_coverage").reconcile()
    namespace_result = importlib.import_module("reconcile_v2_effective_source_namespace").reconcile()
    for label, gate in (
        ("v16_semantic_coverage", v16_coverage),
        ("effective_source_namespace", namespace_result),
    ):
        blockers = _blocking_reconciliation_values(gate)
        if blockers:
            slice_blockers[label] = blockers

    families: dict[str, list[dict[str, Any]]] = {key: [] for key in FAMILY_ID_FIELDS}
    comparison_provenance: list[dict[str, Any]] = []
    programme_control: list[dict[str, Any]] = []
    successor_lineage: list[dict[str, Any]] = []

    for label, result in slice_results.items():
        for family in FAMILY_ID_FIELDS:
            if family == "change_candidates":
                value = result.get("change_candidates", result.get("candidates"))
            else:
                value = result.get(family)
            _extend_if_list(families[family], value, label=f"{label}.{family}")
        _extend_if_list(comparison_provenance, result.get("comparison_provenance"), label=f"{label}.comparison_provenance")
        _extend_if_list(programme_control, result.get("records"), label=f"{label}.records")
        _extend_if_list(programme_control, result.get("control_records"), label=f"{label}.control_records")
        if isinstance(result.get("successor_lineage"), dict):
            successor_lineage.append(result["successor_lineage"])

    family_conflicts: dict[str, dict[str, list[str]]] = {}
    identical_duplicate_counts: dict[str, int] = {}
    for family, id_field in FAMILY_ID_FIELDS.items():
        unique, conflicts, identical_duplicates = _dedupe_family(families[family], id_field)
        if conflicts:
            family_conflicts[family] = conflicts
        families[family] = unique
        identical_duplicate_counts[family] = identical_duplicates

    source_ids = {row["source_id"] for row in families["sources"]}
    observation_ids = {row["observation_id"] for row in families["observations"]}

    reference_scan_root = {
        "families": families,
        "comparison_provenance": comparison_provenance,
        "programme_control": programme_control,
        "successor_lineage": successor_lineage,
    }
    source_refs = _collect_references(reference_scan_root, "source_ids")
    observation_refs = _collect_references(reference_scan_root, "observation_ids")
    unresolved_source_refs = sorted(set(source_refs) - source_ids)
    unresolved_observation_refs = sorted(set(observation_refs) - observation_ids)

    v17_recon = slice_results["v17_successor_lineage"]["reconciliation"]
    repeated_delta_double_count = int(v17_recon.get("repeated_v16_delta_new_identity_count", 0))

    expected_source_count = int(namespace_result.get("materialized_unique_source_count", -1))
    source_count_mismatch = 0 if len(source_ids) == expected_source_count == 248 else 1
    effective_state = _effective_state_reconciliation(families, successor_lineage)

    cross_blockers = {
        "slice_blocker_count": len(slice_blockers),
        "conflicting_duplicate_identity_count": sum(len(v) for v in family_conflicts.values()),
        "unresolved_source_reference_count": len(unresolved_source_refs),
        "unresolved_observation_reference_count": len(unresolved_observation_refs),
        "effective_source_count_mismatch_count": source_count_mismatch,
        "effective_state_mismatch_count": int(effective_state.get("mismatch_count", 1)),
        "repeated_delta_double_counting_count": repeated_delta_double_count,
    }

    mechanically_clean = all(value == 0 for value in cross_blockers.values())
    reconciliation = {
        "scope": "WHOLE_CURRENT_PUBLIC_OBSERVATORY_V2_MIGRATION_CANDIDATE",
        "semantic_reconciliation_state": "ASSEMBLED_MECHANICAL_CANDIDATE" if mechanically_clean else "ASSEMBLED_WITH_MECHANICAL_BLOCKERS",
        "slice_count": len(slice_results),
        "slice_blockers": slice_blockers,
        "family_counts": {family: len(rows) for family, rows in sorted(families.items())},
        "programme_control_record_count": len(programme_control),
        "comparison_provenance_record_count": len(comparison_provenance),
        "successor_lineage_record_count": len(successor_lineage),
        "identical_duplicate_representation_counts": identical_duplicate_counts,
        "family_identity_conflicts": family_conflicts,
        "materialized_source_count": len(source_ids),
        "materialized_observation_count": len(observation_ids),
        "source_reference_count": len(source_refs),
        "observation_reference_count": len(observation_refs),
        "unresolved_source_references": unresolved_source_refs,
        "unresolved_observation_references": unresolved_observation_refs,
        "effective_state_reconciliation": effective_state,
        **cross_blockers,
        "mechanically_clean": mechanically_clean,
        "global_completeness_claim": False,
        "scientific_validity_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "A mechanically clean assembly proves only deterministic migration/referential integrity over the current controlled public predecessor corpus. "
            "It does not establish scientific truth, global completeness, independent appraisal, assessment validity, institutional authority, or canonical publication."
        ),
    }
    return {
        "status": "NONCANONICAL_OBSERVATORY_V2_WHOLE_CURRENT_CANDIDATE",
        "families": families,
        "programme_control": programme_control,
        "comparison_provenance": comparison_provenance,
        "successor_lineage": successor_lineage,
        "slice_reconciliations": {label: result["reconciliation"] for label, result in slice_results.items()},
        "aggregate_gates": {
            "v16_semantic_coverage": v16_coverage,
            "effective_source_namespace": namespace_result,
        },
        "reconciliation": reconciliation,
    }


def write_candidate(result: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_files: list[dict[str, Any]] = []

    for family in sorted(result["families"]):
        rows = result["families"][family]
        path = output_dir / f"{family}.jsonl"
        size, digest = _write_jsonl(path, rows)
        manifest_files.append({"path": path.name, "sha256": digest, "bytes": size, "records": len(rows)})

    for name in ("programme_control", "comparison_provenance", "successor_lineage"):
        rows = result[name]
        path = output_dir / f"{name}.jsonl"
        size, digest = _write_jsonl(path, rows)
        manifest_files.append({"path": path.name, "sha256": digest, "bytes": size, "records": len(rows)})

    for name in ("slice_reconciliations", "aggregate_gates", "reconciliation"):
        path = output_dir / f"{name}.json"
        payload = json.dumps(result[name], indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
        path.write_bytes(payload)
        manifest_files.append({"path": path.name, "sha256": _sha256_bytes(payload), "bytes": len(payload), "records": 1})

    manifest = {
        "candidate_id": "observatory-v2-whole-current-noncanonical-candidate",
        "status": result["status"],
        "files": sorted(manifest_files, key=lambda row: row["path"]),
        "file_count": len(manifest_files),
        "canonical_successor_ready": False,
    }
    manifest_payload = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    (output_dir / "manifest.json").write_bytes(manifest_payload)
    manifest["manifest_sha256"] = _sha256_bytes(manifest_payload)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build()
    manifest = write_candidate(result, args.output_dir.resolve())
    print(json.dumps({"reconciliation": result["reconciliation"], "manifest": manifest}, indent=2, sort_keys=True))
    return 0 if result["reconciliation"]["mechanically_clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

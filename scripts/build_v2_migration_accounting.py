"""Inventory the current public governing corpus for Observatory v2 migration.

The output is a noncanonical accounting scaffold. It deliberately preserves any
section without an exact normalization rule as LEGACY_PRESERVATION_RECORD rather
than silently dropping it. It does not generate a canonical v2 successor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_RECORDS_DIR = ROOT / "releases" / "data-v0.1.0-public-governing" / "records"
GOVERNING_FILES = (
    "source_monitor_registry_v1.5.json",
    "canonical_observatory_release_v1.4.json",
    "canonical_live_refresh_release_v1.6.json",
    "adjudicated_delta_v1.6.json",
    "canonical_successor_snapshot_v1.7.json",
    "public_disposition_summary.json",
)

SECTION_TARGETS: dict[tuple[str, str], str] = {
    ("source_monitor_registry_v1.5.json", "$root"): "MONITORING_CONFIGURATION",
    ("canonical_observatory_release_v1.4.json", "metadata"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_observatory_release_v1.4.json", "methodology"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_observatory_release_v1.4.json", "coverage"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_observatory_release_v1.4.json", "organizations"): "ENTITY_AND_ASSERTION",
    ("canonical_observatory_release_v1.4.json", "organization_resolution"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_observatory_release_v1.4.json", "regional_expansion"): "DISPOSITION_OR_PROVENANCE_AND_ASSERTION",
    ("canonical_observatory_release_v1.4.json", "capital_and_ownership_events"): "EVENT_AND_ASSERTION",
    ("canonical_observatory_release_v1.4.json", "representative_model_records"): "ENTITY_AND_ASSERTION",
    ("canonical_observatory_release_v1.4.json", "model_and_dataset_registry"): "ENTITY_AND_ASSERTION",
    ("canonical_observatory_release_v1.4.json", "trial_site_relationships"): "RELATIONSHIP",
    ("canonical_observatory_release_v1.4.json", "participant_authority_relationships"): "RELATIONSHIP_AND_ASSERTION",
    ("canonical_observatory_release_v1.4.json", "supplier_dependency_relationships"): "RELATIONSHIP",
    ("canonical_observatory_release_v1.4.json", "sources"): "SOURCE_AND_OBSERVATION_WHERE_SUPPORTED",
    ("canonical_live_refresh_release_v1.6.json", "metadata"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_live_refresh_release_v1.6.json", "methodology"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_live_refresh_release_v1.6.json", "baseline"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_live_refresh_release_v1.6.json", "source_checks"): "OBSERVATION",
    ("canonical_live_refresh_release_v1.6.json", "new_sources"): "SOURCE_AND_OBSERVATION_WHERE_SUPPORTED",
    ("canonical_live_refresh_release_v1.6.json", "change_candidates"): "NONCANONICAL_CANDIDATE_PROVENANCE",
    ("canonical_live_refresh_release_v1.6.json", "adjudicated_delta"): "EVENT_RELATIONSHIP_ASSERTION_COMPOSITE",
    ("canonical_live_refresh_release_v1.6.json", "reopening_decisions"): "REOPENING_DECISION",
    ("canonical_live_refresh_release_v1.6.json", "no_change_confirmations"): "OBSERVATION_COMPARISON_PROVENANCE",
    ("canonical_live_refresh_release_v1.6.json", "withheld_claims"): "DISPOSITION_OR_PROVENANCE",
    ("adjudicated_delta_v1.6.json", "regulatory_and_market_events"): "EVENT_AND_ASSERTION",
    ("adjudicated_delta_v1.6.json", "capital_and_ownership_events"): "EVENT_AND_ASSERTION",
    ("adjudicated_delta_v1.6.json", "model_records"): "ENTITY_AND_ASSERTION",
    ("adjudicated_delta_v1.6.json", "supplier_dependency_relationships"): "RELATIONSHIP",
    ("adjudicated_delta_v1.6.json", "governance_and_leadership_events"): "EVENT",
    ("canonical_successor_snapshot_v1.7.json", "metadata"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "baseline_reference"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "baseline_counts"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "delta_counts"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "successor_effective_counts"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "delta"): "EVENT_RELATIONSHIP_ASSERTION_COMPOSITE",
    ("canonical_successor_snapshot_v1.7.json", "reopening_decisions"): "REOPENING_DECISION",
    ("canonical_successor_snapshot_v1.7.json", "provenance"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "predecessor_reference"): "DISPOSITION_OR_PROVENANCE",
    ("canonical_successor_snapshot_v1.7.json", "assessment_successor_delta"): "ASSESSMENT_DEPENDENCY_AND_PROVENANCE",
    ("public_disposition_summary.json", "$root"): "DISPOSITION_OR_PROVENANCE",
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _field_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path)
            paths.update(_field_paths(child, path))
    elif isinstance(value, list):
        for child in value:
            paths.update(_field_paths(child, prefix + "[]" if prefix else "[]"))
    return paths


def _record_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return 1
    return 1


def build_accounting(records_dir: Path = DEFAULT_RECORDS_DIR) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    preserved_sections = 0
    mapped_sections = 0
    all_field_paths: set[tuple[str, str]] = set()

    for filename in GOVERNING_FILES:
        path = records_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing governing input: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if filename in {"source_monitor_registry_v1.5.json", "public_disposition_summary.json"}:
            sections = {"$root": payload}
        elif isinstance(payload, dict):
            sections = payload
        else:
            raise ValueError(f"Unexpected top-level type in {filename}: {type(payload).__name__}")

        section_rows: list[dict[str, Any]] = []
        for section_name, section_value in sections.items():
            target = SECTION_TARGETS.get((filename, section_name))
            if target is None:
                target = "LEGACY_PRESERVATION_RECORD"
                mapping_state = "PRESERVE_PENDING_EXACT_NORMALIZATION"
                preserved_sections += 1
            else:
                mapping_state = "MAPPED_FAMILY_CONTRACT"
                mapped_sections += 1
            fields = sorted(_field_paths(section_value))
            for field in fields:
                all_field_paths.add((filename, f"{section_name}:{field}"))
            section_rows.append(
                {
                    "section": section_name,
                    "target_family": target,
                    "mapping_state": mapping_state,
                    "record_count": _record_count(section_value),
                    "field_path_count": len(fields),
                    "field_paths": fields,
                    "section_digest": _digest(section_value),
                }
            )

        files.append(
            {
                "file": filename,
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "top_level_type": type(payload).__name__,
                "section_count": len(section_rows),
                "sections": section_rows,
            }
        )

    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_MIGRATION_ACCOUNTING",
        "input_release": "data-v0.1.0-public-governing",
        "input_file_count": len(files),
        "mapped_section_count": mapped_sections,
        "preserved_section_count": preserved_sections,
        "unique_field_path_count": len(all_field_paths),
        "silent_unmapped_section_count": 0,
        "invented_value_count": 0,
        "claim_boundary_loss_count": 0,
        "source_reference_loss_count": 0,
        "canonical_successor_ready": False,
        "files": files,
        "authority_boundary": (
            "This artifact inventories and classifies predecessor structure only. "
            "It does not prove semantic migration correctness, generate canonical v2 records, "
            "or authorize a public successor. Sections without exact normalization remain "
            "explicit LEGACY_PRESERVATION_RECORD mappings rather than being dropped."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    accounting = build_accounting(args.records_dir.resolve())
    text = json.dumps(accounting, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

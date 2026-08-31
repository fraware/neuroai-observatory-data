"""Validate the bounded SU-TRIALS ClinicalTrials.gov discovery programme.

This validator performs no network I/O and grants no discovery, source-admission, monitoring,
assessment or release authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "clinicaltrials_discovery_programme_v0.1.json"
UNIVERSES = ROOT / "curation" / "source_universe_registry_v0.1.json"
PRIMA_SOURCES = ROOT / "supplemental_records" / "PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json"

EXPECTED_QUERY_IDS = {
    "DISCOVERY-CTGOV-BCI-001",
    "DISCOVERY-CTGOV-NEURAL-PROSTHESIS-001",
    "DISCOVERY-CTGOV-BRAIN-IMPLANT-001",
}
REQUIRED_METRICS = {
    "supplied_page_count",
    "raw_returned_record_count",
    "unique_nct_record_count_before_programme_filter",
    "included_candidate_count",
    "excluded_by_study_type_count",
    "duplicate_nct_representation_count",
    "reported_total_count_state",
    "reported_total_count",
    "fully_paginated",
    "final_next_page_token_present",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    programme = _load(PROGRAMME)
    universes = _load(UNIVERSES)
    prima_sources = _load(PRIMA_SOURCES)
    errors: list[str] = []

    if programme.get("programme_id") != "SU-TRIALS-CTGOV-v0.1":
        errors.append("programme_id mismatch")
    if programme.get("source_universe_id") != "SU-TRIALS" or programme.get("source_system") != "CLINICALTRIALS_GOV":
        errors.append("source-universe/source-system binding mismatch")

    universe_index = {row.get("universe_id"): row for row in universes.get("universes", []) if isinstance(row, dict)}
    trials = universe_index.get("SU-TRIALS")
    if not isinstance(trials, dict):
        errors.append("SU-TRIALS missing from source-universe registry")
    elif trials.get("canonical_completeness_claim") is not False:
        errors.append("SU-TRIALS completeness boundary weakened")

    dependency = programme.get("workbench_dependency", {})
    if dependency.get("required_capability") != "project_clinicaltrials_search_pages":
        errors.append("unexpected Workbench capability")
    if dependency.get("integration_state") not in {"PENDING_S1_MERGE", "AVAILABLE"}:
        errors.append("invalid Workbench integration state")

    identity = programme.get("identity_policy", {})
    expected_identity = {
        "registry_identity_key": "NCT_ID",
        "fuzzy_identity_merge_allowed": False,
        "cross_query_deduplication": "EXACT_NCT_ID",
        "conflicting_same_id_policy": "FAIL_CLOSED",
    }
    if identity != expected_identity:
        errors.append("identity policy mismatch")

    inclusion = programme.get("inclusion_policy", {})
    if inclusion.get("required_study_types") != ["INTERVENTIONAL"]:
        errors.append("interventional-only policy missing")
    for key in (
        "automatic_trial_entity_creation",
        "automatic_trial_site_relationship_creation",
        "automatic_source_admission",
        "automatic_monitor_creation",
        "automatic_assessment_mutation",
        "participant_level_data_collection",
    ):
        if inclusion.get(key) is not False:
            errors.append(f"{key} must be false")

    anchors = programme.get("known_identifier_anchors")
    if not isinstance(anchors, list) or len(anchors) != 1:
        errors.append("exactly one initial known-identifier anchor required")
    else:
        anchor = anchors[0]
        if anchor.get("nct_id") != "NCT04676854" or anchor.get("existing_source_id") != "SRC-PR-002":
            errors.append("PRIMA anchor mismatch")
        if anchor.get("counts_as_new_discovery") is not False:
            errors.append("known anchor cannot count as new discovery")
        source = next((row for row in prima_sources if row.get("source_id") == "SRC-PR-002"), None)
        if source is None or "NCT04676854" not in str(source.get("url", "")):
            errors.append("PRIMA anchor does not resolve to actual supplemental source record")

    streams = programme.get("query_streams")
    if not isinstance(streams, list):
        errors.append("query_streams must be an array")
        streams = []
    ids = [row.get("query_id") for row in streams if isinstance(row, dict)]
    if set(ids) != EXPECTED_QUERY_IDS or len(ids) != len(set(ids)):
        errors.append("query stream identity set mismatch or duplicate")
    for row in streams:
        if not isinstance(row, dict):
            errors.append("query stream must be object")
            continue
        if row.get("query_surface") != "query.term":
            errors.append(f"{row.get('query_id')}: query surface mismatch")
        if row.get("post_retrieval_required_study_types") != ["INTERVENTIONAL"]:
            errors.append(f"{row.get('query_id')}: interventional post-filter missing")
        if row.get("completeness_claim") is not False:
            errors.append(f"{row.get('query_id')}: completeness claim must be false")
        page_size = row.get("page_size")
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 100:
            errors.append(f"{row.get('query_id')}: page_size outside controlled programme ceiling")

    coverage = programme.get("coverage_contract", {})
    if set(coverage.get("required_metrics", [])) != REQUIRED_METRICS:
        errors.append("coverage metric contract mismatch")
    if coverage.get("registry_completeness_claim") is not False or coverage.get("global_neuroai_trial_recall_claim") is not False:
        errors.append("coverage completeness/recall claims must remain false")

    network = programme.get("network_policy", {})
    if network != {
        "live_execution": "OPT_IN_ONLY",
        "requires_workbench_network_gate": True,
        "configuration_performs_http": False,
    }:
        errors.append("network policy mismatch")

    return {
        "valid": not errors,
        "errors": errors,
        "programme_id": programme.get("programme_id"),
        "query_stream_count": len(streams),
        "known_anchor_count": len(anchors) if isinstance(anchors, list) else 0,
        "workbench_integration_state": dependency.get("integration_state"),
        "automatic_mutation_enabled": any(inclusion.get(key) is True for key in inclusion if key.startswith("automatic_")),
        "registry_completeness_claim": coverage.get("registry_completeness_claim"),
        "global_neuroai_trial_recall_claim": coverage.get("global_neuroai_trial_recall_claim"),
        "boundary": "Configuration validation only; does not execute ClinicalTrials.gov discovery or authorize any candidate/source mutation.",
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

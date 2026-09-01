"""Validate the bounded SU-GRANTS NIH RePORTER programme without network access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROGRAMME_PATH = Path("curation/nih_reporter_grants_discovery_programme_v0.1.json")
UNIVERSE_REGISTRY_PATH = Path("curation/source_universe_registry_v0.1.json")
EXPECTED_QUERY_IDS = {
    "DISCOVERY-REPORTER-BCI-001",
    "DISCOVERY-REPORTER-NEURAL-DECODING-AI-001",
    "DISCOVERY-REPORTER-CLOSED-LOOP-NEUROMODULATION-001",
    "DISCOVERY-REPORTER-EEG-MODELS-001",
    "DISCOVERY-REPORTER-SPEECH-NEUROPROSTHESIS-001",
    "DISCOVERY-REPORTER-VISUAL-NEUROPROSTHESIS-001",
    "DISCOVERY-REPORTER-GREY-MENTAL-STATE-001",
}
REQUIRED_CANDIDATE_FIELDS = {
    "appl_id", "project_num", "core_project_num", "subproject_id", "fiscal_year",
    "project_title", "abstract_text", "project_start_date", "project_end_date",
    "award_notice_date", "award_amount", "funding_mechanism", "agency_ic_admin",
    "organization", "principal_investigators", "query_memberships", "normalized_record_sha256",
}
REQUIRED_COVERAGE = {
    "supplied_page_count", "returned_record_count", "unique_appl_id_count", "reported_total_count",
    "reported_total_count_state", "offset_sequence_valid", "offset_coverage_state",
    "over_15000_limit", "partition_required", "known_controlled_duplicate_count",
    "new_candidate_count", "duplicate_representation_count", "unresolved_appl_id_count",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _universe(registry: dict[str, Any], universe_id: str) -> dict[str, Any]:
    rows = registry.get("universes")
    _require(isinstance(rows, list), "Source-universe registry must contain universes")
    matches = [row for row in rows if row.get("universe_id") == universe_id]
    _require(len(matches) == 1, f"Expected exactly one {universe_id} universe")
    return matches[0]


def validate_programme(programme: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    _require(programme.get("programme_id") == "SU-GRANTS-NIH-REPORTER-v0.1", "Unexpected programme_id")
    _require(programme.get("status") == "NONCANONICAL_PROGRAMME_CONTROL", "Programme must remain noncanonical")
    _require(programme.get("source_universe_id") == "SU-GRANTS", "Programme must bind SU-GRANTS")
    _require(programme.get("source_system") == "NIH_REPORTER_V2", "Unexpected source system")

    universe = _universe(registry, "SU-GRANTS")
    _require(universe.get("canonical_completeness_claim") is False, "SU-GRANTS must not claim completeness")
    _require(universe.get("implementation_state") in {"PLANNED", "PARTIAL", "CURRENT_BOUNDED"}, "Unexpected SU-GRANTS state")

    provider = programme.get("provider_contract") or {}
    _require(provider.get("provider") == "NIH RePORTER API", "Provider changed")
    _require(provider.get("endpoint") == "https://api.reporter.nih.gov/v2/projects/search", "Endpoint changed")
    _require(provider.get("method") == "POST", "RePORTER project search must use POST")
    _require(provider.get("reported_denominator_path") == "meta.total", "RePORTER denominator path changed")
    _require(provider.get("offset_path") == "meta.offset", "RePORTER offset path changed")
    _require(provider.get("limit_path") == "meta.limit", "RePORTER limit path changed")
    _require(provider.get("results_path") == "results", "RePORTER results path changed")
    _require(provider.get("primary_application_id_field") == "appl_id", "appl_id must remain primary provider identity")
    _require(provider.get("max_records_per_request") == 500, "RePORTER per-request limit changed")
    _require(provider.get("max_offset") == 14999, "RePORTER offset ceiling changed")
    _require(provider.get("recommended_max_requests_per_second") == 1, "RePORTER request-rate guidance changed")
    _require(provider.get("configuration_performs_http") is False, "Programme config must not perform HTTP")

    dependency = programme.get("workbench_dependency") or {}
    _require(dependency.get("required_capability") == "project_nih_reporter_search_pages", "Unexpected Workbench capability")
    _require(dependency.get("integration_state") == "PENDING_S1_MERGE", "Proposed RePORTER projector must remain PENDING_S1_MERGE until merged")

    identity = programme.get("identity_policy") or {}
    _require(identity.get("primary_identity") == "NIH_REPORTER_APPL_ID", "appl_id identity changed")
    for key in (
        "application_id_auto_merge", "project_number_auto_merge", "core_project_lineage_auto_merge",
        "subproject_auto_parent_merge", "pi_name_auto_entity_merge", "organization_name_auto_entity_merge",
    ):
        _require(identity.get(key) is False, f"{key} must remain false")
    _require(identity.get("conflicting_same_appl_id_policy") == "FAIL_CLOSED", "appl_id conflicts must fail closed")

    inclusion = programme.get("inclusion_policy") or {}
    for key in (
        "automatic_grant_source_admission", "automatic_project_entity_creation",
        "automatic_pi_or_organization_entity_creation", "automatic_system_or_model_relationship_creation",
        "automatic_funding_success_claim_creation", "automatic_assessment_mutation", "automatic_monitor_creation",
    ):
        _require(inclusion.get(key) is False, f"{key} must remain false")
    _require(inclusion.get("human_relevance_review_required") is True, "Human relevance review required")

    pagination = programme.get("pagination_partition_policy") or {}
    _require(pagination.get("page_limit") == 500, "Page limit changed")
    _require(pagination.get("initial_offset") == 0, "Initial offset changed")
    _require(pagination.get("max_offset") == 14999, "Maximum offset changed")
    _require(pagination.get("max_directly_pageable_result_count") == 15000, "Direct pageable ceiling changed")
    _require(pagination.get("over_limit_policy") == "PARTITION_BEFORE_MATERIALIZATION", "Over-limit strategy changed")
    _require(pagination.get("silent_truncation_allowed") is False, "Silent RePORTER truncation prohibited")
    _require(pagination.get("partial_over_limit_candidate_emission_allowed") is False, "Partial over-limit candidate emission prohibited")
    _require(pagination.get("partition_provenance_required") is True, "Partition provenance required")

    refresh = programme.get("incremental_refresh_policy") or {}
    _require(refresh.get("preferred_watermark") == "date_added", "Incremental watermark changed")
    _require(refresh.get("date_added_documented_from") == "2011-01-01", "date_added lower documentation boundary changed")
    _require(refresh.get("watermark_does_not_replace_historical_baseline") is True, "Incremental watermark cannot replace historical baseline")

    streams = programme.get("query_streams")
    _require(isinstance(streams, list), "query_streams must be list")
    ids = [str(row.get("query_id") or "") for row in streams]
    _require(len(ids) == len(set(ids)), "Duplicate RePORTER query_id")
    _require(set(ids) == EXPECTED_QUERY_IDS, "RePORTER query stream set changed")
    for row in streams:
        qid = str(row["query_id"])
        _require(row.get("status") == "ACTIVE", f"{qid} must remain active")
        _require(row.get("completeness_claim") is False, f"{qid} cannot claim completeness")
        tiers = set(row.get("scope_tiers") or [])
        _require(tiers and tiers <= {"A", "B", "C", "D"}, f"Invalid scope tiers for {qid}")
        if qid == "DISCOVERY-REPORTER-GREY-MENTAL-STATE-001":
            _require(tiers == {"C"}, "Grey grant stream must remain Tier C only")
        search = row.get("advanced_text_search") or {}
        _require(search.get("operator") in {"and", "or", "advanced"}, f"{qid}: invalid advanced search operator")
        _require(search.get("search_field") == "projecttitle,abstracttext,terms", f"{qid}: search field changed")
        _require(isinstance(search.get("search_text"), str) and search["search_text"].strip(), f"{qid}: search text required")

    projection = programme.get("candidate_projection") or {}
    _require(set(projection.get("required_fields") or []) == REQUIRED_CANDIDATE_FIELDS, "Grant candidate field contract changed")
    _require(projection.get("raw_api_pages_emitted_to_s2") is False, "Raw RePORTER pages must not be emitted")
    _require(projection.get("pi_or_org_entity_relationships_created_in_projection") is False, "Projection cannot create PI/org relationships")
    _require(projection.get("award_amount_interpreted_as_research_success") is False, "Award amount cannot proxy research success")

    coverage = programme.get("coverage_contract") or {}
    _require(set(coverage.get("required_metrics_per_leaf_query") or []) == REQUIRED_COVERAGE, "Grant coverage metrics changed")
    _require(coverage.get("mechanical_completion_requires") == {
        "reported_total_count_state": "CONSISTENT",
        "offset_sequence_valid": True,
        "offset_coverage_state": "MATCH",
        "over_15000_limit": False,
        "partition_required": False,
    }, "Grant mechanical completion contract changed")
    for key in ("reporter_database_completeness_claim", "global_neuroai_grant_recall_claim", "query_recall_claim", "funding_success_claim"):
        _require(coverage.get(key) is False, f"{key} must remain false")

    review = programme.get("human_review_contract") or {}
    _require(review.get("required_dispositions") == ["ACCEPT", "REJECT", "DEFER", "EXCLUDE"], "Grant dispositions changed")
    for key in ("automatic_acceptance", "award_is_research_success_evidence", "award_is_system_effectiveness_evidence", "award_is_commercial_strength_evidence"):
        _require(review.get(key) is False, f"{key} must remain false")

    network = programme.get("network_policy") or {}
    _require(network.get("live_execution") == "OPT_IN_ONLY", "Live execution must remain opt-in")
    _require(network.get("requires_workbench_network_gate") is True, "Workbench network gate required")
    _require(network.get("recommended_max_requests_per_second") == 1, "Request rate guidance changed")
    _require(network.get("large_job_schedule_guidance_preserved") is True, "Large-job scheduling guidance must be preserved")
    _require(network.get("configuration_performs_http") is False, "Configuration must not perform HTTP")
    _require(network.get("hosted_success_claim_allowed_without_runner_steps") is False, "Hosted success requires runner steps")

    return {
        "programme_id": programme["programme_id"],
        "source_universe_id": programme["source_universe_id"],
        "query_stream_count": len(streams),
        "grey_area_stream_count": sum(1 for row in streams if row["query_id"].startswith("DISCOVERY-REPORTER-GREY-")),
        "integration_state": dependency["integration_state"],
        "network_requests_performed": False,
        "canonical_mutation_performed": False,
        "global_recall_claim": False,
    }


def main() -> None:
    print(json.dumps(validate_programme(_load(PROGRAMME_PATH), _load(UNIVERSE_REGISTRY_PATH)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

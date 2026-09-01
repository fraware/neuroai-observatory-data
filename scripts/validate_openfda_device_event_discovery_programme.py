"""Validate bounded openFDA/MAUDE device-event discovery without network access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROGRAMME_PATH = Path("curation/openfda_device_event_discovery_programme_v0.1.json")
UNIVERSE_REGISTRY_PATH = Path("curation/source_universe_registry_v0.1.json")
EXPECTED_QUERY_IDS = {
    "DISCOVERY-OPENFDA-MAUDE-BCI-001",
    "DISCOVERY-OPENFDA-MAUDE-DBS-NEUROSTIM-001",
    "DISCOVERY-OPENFDA-MAUDE-NEUROPROSTHESIS-001",
    "DISCOVERY-OPENFDA-MAUDE-VISUAL-NEUROPROSTHESIS-001",
    "DISCOVERY-OPENFDA-MAUDE-IMPLANTED-NEURAL-RECORDING-001",
}
REQUIRED_FIELDS = {
    "mdr_report_key", "report_number", "date_received", "report_date", "event_type",
    "product_problems", "source_type", "remedial_action", "removal_correction_number",
    "devices", "query_memberships", "normalized_record_sha256",
}
REQUIRED_DEVICE_FIELDS = {
    "brand_name", "generic_name", "udi_di", "device_report_product_code", "model_number",
    "manufacturer_d_name", "implant_flag",
}
REQUIRED_COVERAGE = {
    "supplied_page_count", "returned_record_count", "unique_mdr_report_key_count", "reported_total_count",
    "reported_total_count_state", "skip_sequence_valid", "skip_coverage_state", "over_26000_limit",
    "search_after_or_partition_required", "known_controlled_duplicate_count", "new_candidate_count",
    "duplicate_representation_count", "unresolved_mdr_report_key_count",
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
    _require(programme.get("programme_id") == "SU-REGULATION-OPENFDA-DEVICE-EVENTS-v0.1", "Unexpected programme_id")
    _require(programme.get("status") == "NONCANONICAL_PROGRAMME_CONTROL", "Programme must remain noncanonical")
    _require(programme.get("source_universe_id") == "SU-REGULATION", "Programme must bind SU-REGULATION")
    _require(programme.get("source_system") == "OPENFDA_DEVICE_EVENT", "Unexpected source system")

    universe = _universe(registry, "SU-REGULATION")
    _require(universe.get("canonical_completeness_claim") is False, "SU-REGULATION must not claim completeness")

    provider = programme.get("provider_contract") or {}
    expected = {
        "provider": "U.S. FDA openFDA Device Adverse Event API",
        "endpoint": "https://api.fda.gov/device/event.json",
        "method": "GET",
        "response_media_type": "application/json",
        "source_dataset": "MAUDE",
        "reported_denominator_path": "meta.results.total",
        "skip_path": "meta.results.skip",
        "limit_path": "meta.results.limit",
        "results_path": "results",
        "primary_report_id_field": "mdr_report_key",
        "max_records_per_request": 1000,
        "max_skip": 25000,
        "max_direct_skip_limit_result_count": 26000,
        "provider_supports_search_after": True,
        "provider_supports_bulk_downloads": True,
        "api_key_required": False,
        "api_key_recommended_for_regular_use": True,
        "provider_update_frequency": "WEEKLY",
        "configuration_performs_http": False,
    }
    _require(provider == expected, "openFDA provider contract changed")

    dependency = programme.get("workbench_dependency") or {}
    _require(dependency.get("required_capability") == "project_openfda_device_event_pages", "Unexpected Workbench capability")
    _require(dependency.get("integration_state") == "PENDING_S1_MERGE", "Proposed openFDA projector must remain PENDING_S1_MERGE until merged")

    identity = programme.get("identity_policy") or {}
    _require(identity.get("primary_identity") == "MDR_REPORT_KEY", "MDR report identity changed")
    _require(identity.get("record_content_change_is_successor_observation_not_new_report_identity") is True, "Record changes must remain successor observations")
    for key in (
        "report_number_auto_merge", "followup_or_supplement_auto_new_identity", "device_brand_name_auto_system_merge",
        "manufacturer_name_auto_entity_merge", "udi_auto_system_merge", "product_code_auto_system_merge",
    ):
        _require(identity.get(key) is False, f"{key} must remain false")
    _require(identity.get("conflicting_same_mdr_report_key_policy") == "FAIL_CLOSED", "MDR conflicts must fail closed")

    inclusion = programme.get("inclusion_policy") or {}
    for key in (
        "automatic_source_admission", "automatic_system_or_device_entity_creation", "automatic_manufacturer_entity_creation",
        "automatic_safety_signal_creation", "automatic_causality_claim_creation", "automatic_incidence_or_rate_claim_creation",
        "automatic_regulatory_action_creation", "automatic_assessment_mutation", "automatic_monitor_creation",
    ):
        _require(inclusion.get(key) is False, f"{key} must remain false")
    _require(inclusion.get("human_relevance_review_required") is True, "Human relevance review required")

    paging = programme.get("paging_policy") or {}
    _require(paging.get("execution_mode_v0_1") == "SKIP_LIMIT_BOUNDED", "v0.1 paging mode changed")
    _require(paging.get("page_limit") == 1000, "openFDA page limit changed")
    _require(paging.get("initial_skip") == 0, "openFDA initial skip changed")
    _require(paging.get("max_skip") == 25000, "openFDA max skip changed")
    _require(paging.get("max_direct_result_count") == 26000, "openFDA direct result bound changed")
    _require(paging.get("over_limit_policy") == "SEARCH_AFTER_OR_DATE_PARTITION_REQUIRED_BEFORE_MATERIALIZATION", "openFDA over-limit policy changed")
    _require(paging.get("preferred_partition_field") == "date_received", "openFDA partition field changed")
    _require(paging.get("silent_truncation_allowed") is False, "Silent openFDA truncation prohibited")
    _require(paging.get("partial_over_limit_candidate_emission_allowed") is False, "Partial over-limit emission prohibited")
    _require(paging.get("search_after_not_yet_authorized_by_v0_1_projector") is True, "v0.1 must not silently use search-after")
    _require(paging.get("partition_provenance_required") is True, "Partition provenance required")

    streams = programme.get("query_streams")
    _require(isinstance(streams, list), "query_streams must be list")
    ids = [str(row.get("query_id") or "") for row in streams]
    _require(len(ids) == len(set(ids)), "Duplicate openFDA query_id")
    _require(set(ids) == EXPECTED_QUERY_IDS, "openFDA query stream set changed")
    for row in streams:
        qid = str(row["query_id"])
        _require(row.get("status") == "ACTIVE", f"{qid} must remain active")
        _require(row.get("cadence") == "WEEKLY", f"{qid} cadence changed")
        _require(row.get("completeness_claim") is False, f"{qid} cannot claim completeness")
        search = row.get("search")
        _require(isinstance(search, str) and search.strip(), f"{qid}: search required")
        _require("device.generic_name:" in search, f"{qid}: must stay generic-name scoped")
        _require("+OR+" in search, f"{qid}: Boolean OR must be explicit")
        _require("+AND+" not in search, f"{qid}: v0.1 synonym strata must not silently become intersection queries")

    projection = programme.get("candidate_projection") or {}
    _require(set(projection.get("required_fields") or []) == REQUIRED_FIELDS, "MAUDE candidate field contract changed")
    _require(set(projection.get("device_fields") or []) == REQUIRED_DEVICE_FIELDS, "MAUDE device field contract changed")
    _require(projection.get("patient_level_fields_in_discovery_layer") is False, "Patient fields prohibited in discovery projection")
    _require(projection.get("mdr_text_narrative_capture_in_discovery_layer") is False, "MDR narratives prohibited in discovery projection")
    _require(projection.get("raw_api_pages_emitted_to_s2") is False, "Raw openFDA pages prohibited in S2 output")

    coverage = programme.get("coverage_contract") or {}
    _require(set(coverage.get("required_metrics_per_leaf_query") or []) == REQUIRED_COVERAGE, "MAUDE coverage contract changed")
    _require(coverage.get("mechanical_completion_requires") == {
        "reported_total_count_state": "CONSISTENT",
        "skip_sequence_valid": True,
        "skip_coverage_state": "MATCH",
        "over_26000_limit": False,
        "search_after_or_partition_required": False,
    }, "MAUDE mechanical completion contract changed")
    for key in (
        "maude_database_completeness_claim", "global_neuroai_postmarket_recall_claim", "query_recall_claim",
        "causality_claim", "incidence_or_rate_claim", "comparative_safety_claim",
    ):
        _require(coverage.get(key) is False, f"{key} must remain false")

    review = programme.get("human_review_contract") or {}
    for key in (
        "automatic_acceptance", "mdr_report_is_causality_evidence", "mdr_count_is_incidence_evidence",
        "mdr_count_is_comparative_safety_evidence", "mdr_report_is_fda_conclusion",
        "mdr_report_is_recall_or_enforcement_action", "mdr_report_is_system_nonconformance_evidence_by_itself",
    ):
        _require(review.get(key) is False, f"{key} must remain false")

    network = programme.get("network_policy") or {}
    _require(network.get("live_execution") == "OPT_IN_ONLY", "Live execution must remain opt-in")
    _require(network.get("requires_workbench_network_gate") is True, "Workbench network gate required")
    _require(network.get("api_key_secret_may_be_committed") is False, "API key must not be committed")
    _require(network.get("configuration_performs_http") is False, "Configuration must not perform HTTP")
    _require(network.get("hosted_success_claim_allowed_without_runner_steps") is False, "Hosted success requires runner steps")

    return {
        "programme_id": programme["programme_id"],
        "source_universe_id": programme["source_universe_id"],
        "query_stream_count": len(streams),
        "integration_state": dependency["integration_state"],
        "network_requests_performed": False,
        "patient_level_fields_projected": False,
        "mdr_narratives_projected": False,
        "causality_claim": False,
        "canonical_mutation_performed": False,
    }


def main() -> None:
    print(json.dumps(validate_programme(_load(PROGRAMME_PATH), _load(UNIVERSE_REGISTRY_PATH)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

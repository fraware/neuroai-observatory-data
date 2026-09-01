"""Validate bounded openFDA device-recall discovery without network access."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

PROGRAMME_PATH = Path("curation/openfda_device_recall_discovery_programme_v0.1.json")
UNIVERSE_REGISTRY_PATH = Path("curation/source_universe_registry_v0.1.json")
EXPECTED_QUERY_IDS = {
    "DISCOVERY-OPENFDA-RECALL-BCI-001",
    "DISCOVERY-OPENFDA-RECALL-DBS-NEUROSTIM-001",
    "DISCOVERY-OPENFDA-RECALL-NEUROPROSTHESIS-001",
    "DISCOVERY-OPENFDA-RECALL-VISUAL-NEUROPROSTHESIS-001",
    "DISCOVERY-OPENFDA-RECALL-NEURAL-RECORDING-001",
}
REQUIRED_FIELDS = {
    "cfres_id","res_event_number","product_res_number","event_date_initiated","event_date_created",
    "event_date_posted","event_date_terminated","recall_status","recalling_firm","firm_fei_number",
    "reason_for_recall","root_cause_description","action","product_description","product_code",
    "k_numbers","pma_numbers","query_memberships","normalized_record_sha256",
}
REQUIRED_COVERAGE = {
    "supplied_page_count","returned_record_count","unique_cfres_id_count","reported_total_count",
    "reported_total_count_state","skip_sequence_valid","skip_coverage_state","over_26000_limit",
    "search_after_or_partition_required","known_controlled_duplicate_count","new_candidate_count",
    "duplicate_representation_count","unresolved_cfres_id_count",
}

def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def _universe(registry: dict[str, Any], uid: str) -> dict[str, Any]:
    rows = registry.get("universes")
    _require(isinstance(rows, list), "Source-universe registry must contain universes")
    matches = [row for row in rows if row.get("universe_id") == uid]
    _require(len(matches) == 1, f"Expected exactly one {uid} universe")
    return matches[0]

def validate_programme(programme: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    _require(programme.get("programme_id") == "SU-REGULATION-OPENFDA-DEVICE-RECALLS-v0.1", "Unexpected programme_id")
    _require(programme.get("status") == "NONCANONICAL_PROGRAMME_CONTROL", "Programme must remain noncanonical")
    _require(programme.get("source_universe_id") == "SU-REGULATION", "Programme must bind SU-REGULATION")
    _require(programme.get("source_system") == "OPENFDA_DEVICE_RECALL", "Unexpected source system")
    _require(_universe(registry, "SU-REGULATION").get("canonical_completeness_claim") is False, "SU-REGULATION must not claim completeness")

    provider = programme.get("provider_contract") or {}
    expected_provider = {
        "provider":"U.S. FDA openFDA Device Recall API","endpoint":"https://api.fda.gov/device/recall.json",
        "method":"GET","response_media_type":"application/json","source_dataset":"Medical Device Recalls",
        "time_period_start":"2002","provider_update_frequency":"WEEKLY","reported_denominator_path":"meta.results.total",
        "skip_path":"meta.results.skip","limit_path":"meta.results.limit","results_path":"results",
        "primary_recall_id_field":"cfres_id","event_lineage_field":"res_event_number","max_records_per_request":1000,
        "max_skip":25000,"max_direct_result_count":26000,"provider_supports_search_after":True,
        "provider_supports_bulk_downloads":True,"configuration_performs_http":False,
    }
    _require(provider == expected_provider, "openFDA recall provider contract changed")

    dep = programme.get("workbench_dependency") or {}
    _require(dep.get("required_capability") == "project_openfda_device_recall_pages", "Unexpected Workbench capability")
    _require(dep.get("integration_state") in {"NOT_IMPLEMENTED","PENDING_S1_MERGE"}, "Unmerged recall projector cannot be AVAILABLE")

    identity = programme.get("identity_policy") or {}
    _require(identity.get("primary_identity") == "CFRES_ID", "Recall identity changed")
    _require(identity.get("res_event_number_is_lineage_not_record_identity") is True, "res_event_number must remain lineage")
    _require(identity.get("record_content_change_is_successor_observation_not_new_recall_identity") is True, "Recall updates must remain successor observations")
    for key in ("same_event_number_auto_merge","k_number_auto_system_merge","pma_number_auto_system_merge","product_code_auto_system_merge","recalling_firm_auto_entity_merge"):
        _require(identity.get(key) is False, f"{key} must remain false")
    _require(identity.get("conflicting_same_cfres_id_policy") == "FAIL_CLOSED", "cfres_id conflicts must fail closed")

    inclusion = programme.get("inclusion_policy") or {}
    for key in ("automatic_source_admission","automatic_recall_event_entity_creation","automatic_system_or_device_entity_creation","automatic_firm_entity_creation","automatic_submission_relationship_creation","automatic_system_nonconformance_claim_creation","automatic_assessment_mutation","automatic_reopening_decision","automatic_monitor_creation"):
        _require(inclusion.get(key) is False, f"{key} must remain false")
    _require(inclusion.get("human_relevance_review_required") is True, "Human review required")

    paging = programme.get("paging_policy") or {}
    _require(paging.get("execution_mode_v0_1") == "SKIP_LIMIT_BOUNDED", "Recall paging mode changed")
    _require(paging.get("page_limit") == 1000 and paging.get("max_skip") == 25000 and paging.get("max_direct_result_count") == 26000, "Recall paging bounds changed")
    _require(paging.get("preferred_partition_field") == "event_date_posted", "Recall partition field changed")
    _require(paging.get("silent_truncation_allowed") is False, "Silent recall truncation prohibited")
    _require(paging.get("partial_over_limit_candidate_emission_allowed") is False, "Partial over-limit recall emission prohibited")
    _require(paging.get("search_after_not_yet_authorized_by_v0_1_projector") is True, "v0.1 must not silently use search-after")

    streams = programme.get("query_streams")
    _require(isinstance(streams, list), "query_streams must be list")
    ids = [str(row.get("query_id") or "") for row in streams]
    _require(len(ids) == len(set(ids)) and set(ids) == EXPECTED_QUERY_IDS, "Recall query stream set changed")
    for row in streams:
        qid = row["query_id"]
        _require(row.get("cadence") == "WEEKLY" and row.get("status") == "ACTIVE", f"{qid}: cadence/status changed")
        _require(row.get("completeness_claim") is False, f"{qid}: cannot claim completeness")
        search = row.get("search")
        _require(isinstance(search, str) and "product_description:" in search and "+OR+" in search, f"{qid}: explicit product-description OR search required")

    projection = programme.get("candidate_projection") or {}
    _require(set(projection.get("required_fields") or []) == REQUIRED_FIELDS, "Recall candidate fields changed")
    for key in ("address_or_contact_fields_in_discovery_layer","code_info_lot_serial_text_in_discovery_layer","distribution_pattern_in_discovery_layer","raw_api_pages_emitted_to_s2"):
        _require(projection.get(key) is False, f"{key} must remain false")

    coverage = programme.get("coverage_contract") or {}
    _require(set(coverage.get("required_metrics_per_leaf_query") or []) == REQUIRED_COVERAGE, "Recall coverage metrics changed")
    _require(coverage.get("mechanical_completion_requires") == {"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"search_after_or_partition_required":False}, "Recall mechanical completion contract changed")
    for key in ("device_recall_database_completeness_claim","global_neuroai_device_recall_claim","query_recall_claim","recall_status_is_complete_lifecycle_tracker","recall_record_establishes_broader_system_nonconformance"):
        _require(coverage.get(key) is False, f"{key} must remain false")

    review = programme.get("human_review_contract") or {}
    for key in ("automatic_acceptance","recall_record_is_global_product_unsafety_evidence","recall_record_is_all_configuration_nonconformance_evidence","recall_status_is_authoritative_live_lifecycle_state","recall_record_automatically_reopens_assessment"):
        _require(review.get(key) is False, f"{key} must remain false")

    network = programme.get("network_policy") or {}
    _require(network.get("live_execution") == "OPT_IN_ONLY" and network.get("requires_workbench_network_gate") is True, "Recall network boundary changed")
    _require(network.get("configuration_performs_http") is False and network.get("hosted_success_claim_allowed_without_runner_steps") is False, "Recall execution-status boundary changed")

    return {"programme_id":programme["programme_id"],"query_stream_count":len(streams),"integration_state":dep["integration_state"],"network_requests_performed":False,"automatic_reopening":False,"canonical_mutation_performed":False}

def main() -> None:
    print(json.dumps(validate_programme(_load(PROGRAMME_PATH), _load(UNIVERSE_REGISTRY_PATH)), indent=2, sort_keys=True))

if __name__ == "__main__":
    main()

"""Validate the bounded SU-PATENTS EPO OPS programme without network access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROGRAMME_PATH = Path("curation/epo_ops_patent_discovery_programme_v0.1.json")
UNIVERSE_REGISTRY_PATH = Path("curation/source_universe_registry_v0.1.json")

EXPECTED_QUERY_IDS = {
    "DISCOVERY-OPS-BCI-001",
    "DISCOVERY-OPS-INVASIVE-NEURAL-001",
    "DISCOVERY-OPS-CLOSED-LOOP-NEUROMODULATION-001",
    "DISCOVERY-OPS-NEURAL-DECODING-AI-001",
    "DISCOVERY-OPS-VISUAL-NEUROPROSTHESIS-001",
    "DISCOVERY-OPS-GREY-MENTAL-STATE-001",
    "DISCOVERY-OPS-GREY-NEURAL-BIOMETRIC-001",
    "DISCOVERY-OPS-GREY-WORKPLACE-ATTENTION-001",
    "DISCOVERY-OPS-KNOWN-APPLICANTS-001",
}
EXPECTED_APPLICANTS = {
    "Neuralink", "Synchron", "Paradromics", "Precision Neuroscience",
    "Science Corporation", "Blackrock Neurotech", "Kernel", "Emotiv",
}
REQUIRED_CANDIDATE_FIELDS = {
    "docdb_publication_reference", "country", "document_number", "kind_code", "title",
    "publication_date", "applicants", "inventors", "ipc_symbols", "cpc_symbols",
    "application_references", "priority_references", "query_memberships", "normalized_record_sha256",
}
REQUIRED_COVERAGE_METRICS = {
    "requested_range_count", "returned_publication_reference_count", "unique_docdb_publication_count",
    "reported_total_result_count", "reported_total_result_count_state", "range_sequence_valid",
    "range_coverage_state", "over_2000_limit", "partition_required",
    "known_controlled_duplicate_count", "new_candidate_count",
    "cross_query_duplicate_representation_count", "unresolved_docdb_identity_count",
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


def _balanced_cql(query: str) -> bool:
    depth = 0
    quoted = False
    escaped = False
    for char in query:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not quoted and not escaped


def validate_programme(programme: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    _require(programme.get("programme_id") == "SU-PATENTS-EPO-OPS-v0.1", "Unexpected programme_id")
    _require(programme.get("status") == "NONCANONICAL_PROGRAMME_CONTROL", "Programme must remain noncanonical")
    _require(programme.get("source_universe_id") == "SU-PATENTS", "Programme must bind SU-PATENTS")
    _require(programme.get("source_system") == "EPO_OPS", "Unexpected source system")

    universe = _universe(registry, "SU-PATENTS")
    _require(universe.get("canonical_completeness_claim") is False, "SU-PATENTS must not claim completeness")
    _require(universe.get("implementation_state") in {"PLANNED", "PARTIAL", "CURRENT_BOUNDED"}, "Unexpected SU-PATENTS implementation state")

    provider = programme.get("provider_contract") or {}
    expected_provider = {
        "provider": "European Patent Office Open Patent Services",
        "api_version": "3.2",
        "server": "https://ops.epo.org/3.2/rest-services",
        "search_endpoint": "/published-data/search/biblio",
        "search_constituent": "biblio",
        "query_language": "CQL",
        "query_parameter": "q",
        "response_media_type": "application/exchange+xml",
        "range_transport": "X-OPS-Range",
        "max_records_per_range": 100,
        "max_retrievable_results_per_search": 2000,
        "authentication": "OAUTH_2_REGISTERED_APPLICATION",
        "registration_required_for_programmatic_execution": True,
        "free_weekly_data_threshold_gb": 4,
        "configuration_performs_http": False,
    }
    _require(provider == expected_provider, "EPO OPS provider contract changed")

    dependency = programme.get("workbench_dependency") or {}
    _require(dependency.get("required_capability") == "project_epo_ops_search_pages", "Unexpected Workbench capability")
    _require(dependency.get("integration_state") == "PENDING_S1_MERGE", "Proposed EPO OPS projector must remain PENDING_S1_MERGE until merged")

    identity = programme.get("identity_policy") or {}
    _require(identity.get("primary_identity") == "DOCDB_PUBLICATION_REFERENCE", "DOCDB publication reference must be primary identity")
    _require(identity.get("required_identity_parts") == ["country", "document_number", "kind_code"], "DOCDB identity parts changed")
    for key in (
        "publication_step_auto_merge", "patent_family_auto_merge", "fuzzy_title_identity_merge_allowed",
        "applicant_name_auto_entity_merge", "inventor_name_auto_entity_merge",
    ):
        _require(identity.get(key) is False, f"{key} must remain false")
    _require(identity.get("conflicting_same_publication_policy") == "FAIL_CLOSED", "Publication conflicts must fail closed")
    _require(identity.get("family_relationship_requires_explicit_family_retrieval") is True, "Family relationships require explicit family retrieval")

    inclusion = programme.get("inclusion_policy") or {}
    for key in (
        "automatic_patent_source_admission", "automatic_patent_family_creation",
        "automatic_applicant_or_inventor_entity_creation", "automatic_product_or_system_relationship_creation",
        "automatic_capability_claim_creation", "automatic_assessment_mutation", "automatic_monitor_creation",
    ):
        _require(inclusion.get(key) is False, f"{key} must remain false")
    _require(inclusion.get("human_relevance_review_required") is True, "Human relevance review must remain required")

    partition = programme.get("search_partition_policy") or {}
    _require(partition.get("initial_range") == "1-100", "Initial OPS range changed")
    _require(partition.get("subsequent_range_size") == 100, "OPS range size must remain 100")
    _require(partition.get("total_result_count_attribute") == "total-result-count", "OPS denominator attribute changed")
    _require(partition.get("leaf_query_max_total_result_count") == 2000, "OPS leaf-query cap must remain 2000")
    _require(partition.get("over_limit_policy") == "SPLIT_QUERY_BEFORE_MATERIALIZATION", "Over-limit queries must split before materialization")
    _require(partition.get("silent_truncation_allowed") is False, "Silent OPS truncation is prohibited")
    _require(partition.get("partial_over_limit_candidate_emission_allowed") is False, "Over-limit partial candidate emission is prohibited")
    _require(partition.get("partition_provenance_required") is True, "Partition provenance is required")

    streams = programme.get("query_streams")
    _require(isinstance(streams, list), "query_streams must be a list")
    ids = [str(row.get("query_id") or "") for row in streams]
    _require(len(ids) == len(set(ids)), "Duplicate EPO OPS query_id")
    _require(set(ids) == EXPECTED_QUERY_IDS, "EPO OPS query stream set changed")
    for row in streams:
        qid = str(row["query_id"])
        _require(row.get("status") == "ACTIVE", f"{qid} must be ACTIVE")
        _require(row.get("completeness_claim") is False, f"{qid} cannot claim completeness")
        tiers = set(row.get("scope_tiers") or [])
        _require(tiers and tiers <= {"A", "B", "C", "D"}, f"Invalid scope tiers for {qid}")
        if qid.startswith("DISCOVERY-OPS-GREY-"):
            _require(tiers == {"C"}, f"{qid} must remain Tier C only")
        if qid == "DISCOVERY-OPS-KNOWN-APPLICANTS-001":
            _require(row.get("query_mode") == "APPLICANT_WATCH_SET", "Applicant watch mode changed")
            _require(set(row.get("applicant_terms") or []) == EXPECTED_APPLICANTS, "Applicant watch set changed")
            _require(row.get("cql_template") == 'pa="{applicant_term}"', "Applicant CQL template changed")
        else:
            cql = row.get("cql")
            _require(isinstance(cql, str) and cql.strip(), f"{qid} must contain CQL")
            _require(_balanced_cql(cql), f"{qid} has unbalanced CQL")
            _require("ta" in cql.lower(), f"{qid} must stay explicitly title/abstract scoped")

    projection = programme.get("candidate_projection") or {}
    _require(set(projection.get("required_fields") or []) == REQUIRED_CANDIDATE_FIELDS, "Patent candidate field contract changed")
    _require(projection.get("abstract_capture_allowed_for_relevance_review") is True, "Abstract metadata must remain available for relevance review")
    for key in ("claims_or_description_capture_in_discovery_layer", "facsimile_or_image_capture_in_discovery_layer", "raw_ops_xml_emitted_to_s2"):
        _require(projection.get(key) is False, f"{key} must remain false")

    coverage = programme.get("coverage_contract") or {}
    _require(set(coverage.get("required_metrics_per_leaf_query") or []) == REQUIRED_COVERAGE_METRICS, "Patent coverage metric contract changed")
    _require(coverage.get("mechanical_completion_requires") == {
        "reported_total_result_count_state": "CONSISTENT",
        "range_sequence_valid": True,
        "range_coverage_state": "MATCH",
        "over_2000_limit": False,
        "partition_required": False,
    }, "Patent mechanical completion contract changed")
    for key in ("epo_database_completeness_claim", "global_neuroai_patent_recall_claim", "query_recall_claim", "patent_family_completeness_claim"):
        _require(coverage.get(key) is False, f"{key} must remain false")

    review = programme.get("human_review_contract") or {}
    _require(review.get("required_dispositions") == ["ACCEPT", "REJECT", "DEFER", "EXCLUDE"], "Patent review dispositions changed")
    for key in (
        "automatic_acceptance", "patent_existence_is_capability_evidence",
        "patent_existence_is_product_implementation_evidence", "patent_existence_is_freedom_to_operate_evidence",
        "patent_existence_is_validity_or_enforceability_determination",
    ):
        _require(review.get(key) is False, f"{key} must remain false")

    network = programme.get("network_policy") or {}
    _require(network.get("live_execution") == "OPT_IN_CREDENTIALLED_ONLY", "EPO OPS live execution must remain credentialled opt-in")
    _require(network.get("requires_epo_ops_credentials") is True, "EPO OPS credentials are required")
    _require(network.get("requires_workbench_network_gate") is True, "Workbench network gate is required")
    _require(network.get("fair_use_policy_binding_required") is True, "EPO fair-use binding is required")
    _require(network.get("configuration_performs_http") is False, "Programme configuration must not perform HTTP")
    _require(network.get("credentials_or_tokens_may_be_committed") is False, "Credentials/tokens must never be committed")
    _require(network.get("hosted_success_claim_allowed_without_runner_steps") is False, "Hosted success cannot be claimed without runner steps")

    return {
        "programme_id": programme["programme_id"],
        "source_universe_id": programme["source_universe_id"],
        "query_stream_count": len(streams),
        "grey_area_stream_count": sum(1 for row in streams if str(row["query_id"]).startswith("DISCOVERY-OPS-GREY-")),
        "known_applicant_count": len(EXPECTED_APPLICANTS),
        "integration_state": dependency["integration_state"],
        "network_requests_performed": False,
        "credentials_accessed": False,
        "canonical_mutation_performed": False,
        "global_recall_claim": False,
    }


def main() -> None:
    print(json.dumps(validate_programme(_load(PROGRAMME_PATH), _load(UNIVERSE_REGISTRY_PATH)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

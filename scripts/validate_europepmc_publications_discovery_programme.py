"""Validate the bounded SU-PUBLICATIONS Europe PMC discovery programme.

This validator is intentionally offline. It validates programme control and authority
boundaries; it does not contact Europe PMC or claim that any query result exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROGRAMME_PATH = Path("curation/europepmc_publications_discovery_programme_v0.1.json")
UNIVERSE_REGISTRY_PATH = Path("curation/source_universe_registry_v0.1.json")

EXPECTED_QUERY_IDS = {
    "DISCOVERY-EPMC-BCI-001",
    "DISCOVERY-EPMC-NEURAL-DECODING-AI-001",
    "DISCOVERY-EPMC-INVASIVE-INTERFACE-AI-001",
    "DISCOVERY-EPMC-CLOSED-LOOP-NEUROMODULATION-001",
    "DISCOVERY-EPMC-EEG-FOUNDATION-001",
    "DISCOVERY-EPMC-SPEECH-COMMUNICATION-001",
    "DISCOVERY-EPMC-VISUAL-NEUROPROSTHESIS-COMPUTATION-001",
    "DISCOVERY-EPMC-GREY-MENTAL-STATE-001",
}

EXPECTED_ANCHORS = {
    "EPMC-ANCHOR-PRIMA-001": {
        "doi": "10.1056/nejmoa2501396",
        "pmid": "41124203",
    },
    "EPMC-ANCHOR-SPEECH-NEUROPROSTHESIS-001": {
        "doi": "10.1056/nejmoa2314132",
        "pmid": "39141853",
    },
}

REQUIRED_CANDIDATE_FIELDS = {
    "resolved_identity",
    "identity_type",
    "title",
    "publication_year",
    "author_string",
    "journal_or_source",
    "publication_type",
    "doi",
    "pmid",
    "pmcid",
    "source_plus_ext_id",
    "is_preprint",
    "query_memberships",
    "normalized_record_sha256",
}

REQUIRED_COVERAGE_METRICS = {
    "supplied_page_count",
    "raw_returned_record_count",
    "unique_resolved_identity_count",
    "reported_hit_count_state",
    "reported_hit_count",
    "cursor_sequence_valid",
    "terminal_cursor_state",
    "reported_total_reconciliation_state",
    "known_anchor_count",
    "known_controlled_source_duplicate_count",
    "new_candidate_count",
    "cross_query_duplicate_representation_count",
    "unresolved_identity_count",
    "preprint_count",
    "peer_reviewed_or_journal_count",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _balanced_query(query: str) -> bool:
    depth = 0
    in_quote = False
    escaped = False
    for char in query:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_quote and not escaped


def _universe(registry: dict[str, Any], universe_id: str) -> dict[str, Any]:
    universes = registry.get("universes")
    _require(isinstance(universes, list), "Source-universe registry must contain universes")
    matches = [row for row in universes if row.get("universe_id") == universe_id]
    _require(len(matches) == 1, f"Expected exactly one {universe_id} universe")
    return matches[0]


def validate_programme(
    programme: dict[str, Any], universe_registry: dict[str, Any]
) -> dict[str, Any]:
    _require(programme.get("programme_id") == "SU-PUBLICATIONS-EUROPEPMC-v0.1", "Unexpected programme_id")
    _require(programme.get("status") == "NONCANONICAL_PROGRAMME_CONTROL", "Programme must remain noncanonical")
    _require(programme.get("source_universe_id") == "SU-PUBLICATIONS", "Programme must bind SU-PUBLICATIONS")
    _require(programme.get("source_system") == "EUROPE_PMC", "Unexpected source system")

    publication_universe = _universe(universe_registry, "SU-PUBLICATIONS")
    _require(publication_universe.get("canonical_completeness_claim") is False, "SU-PUBLICATIONS must not claim completeness")
    _require(publication_universe.get("implementation_state") in {"PARTIAL", "PLANNED", "CURRENT_BOUNDED"}, "Unexpected SU-PUBLICATIONS implementation state")

    provider = programme.get("provider_contract") or {}
    _require(provider.get("provider") == "Europe PMC", "Provider must be Europe PMC")
    _require(provider.get("api_endpoint") == "https://www.ebi.ac.uk/europepmc/webservices/rest/search", "Unexpected Europe PMC endpoint")
    _require(provider.get("query_parameter") == "query", "Europe PMC query parameter must be query")
    _require(provider.get("format") == "json", "Discovery format must be JSON")
    _require(provider.get("result_type") == "lite", "Discovery result type must remain lite")
    _require(provider.get("pagination_mode") == "CURSOR_MARK", "Cursor pagination is required")
    _require(provider.get("first_cursor_mark") == "*", "First Europe PMC cursorMark must be *")
    _require(provider.get("next_cursor_field") == "nextCursorMark", "nextCursorMark must drive pagination")
    _require(provider.get("reported_denominator_field") == "hitCount", "hitCount must be the declared query denominator")
    _require(isinstance(provider.get("page_size"), int) and 1 <= provider["page_size"] <= 1000, "Europe PMC page_size must be within 1..1000")
    _require(provider.get("synonym_expansion") is False, "Synonym expansion must remain explicit/off for v0.1")
    _require(provider.get("configuration_performs_http") is False, "Programme configuration must not perform HTTP")

    dependency = programme.get("workbench_dependency") or {}
    _require(dependency.get("required_capability") == "project_europepmc_search_pages", "Unexpected Workbench capability name")
    _require(dependency.get("integration_state") in {"NOT_IMPLEMENTED", "PENDING_S1_MERGE", "AVAILABLE"}, "Invalid integration_state")

    identity = programme.get("identity_policy") or {}
    _require(identity.get("preferred_identity_order") == ["DOI", "PMID", "PMCID", "SOURCE_PLUS_EXT_ID"], "Identity precedence changed")
    _require(identity.get("fuzzy_title_identity_merge_allowed") is False, "Fuzzy title identity merge must remain disabled")
    _require(identity.get("preprint_journal_version_auto_merge") is False, "Preprint/journal versions must not auto-merge")
    _require(identity.get("conflicting_same_identity_policy") == "FAIL_CLOSED", "Identity conflicts must fail closed")

    anchors = programme.get("known_identifier_anchors")
    _require(isinstance(anchors, list), "known_identifier_anchors must be a list")
    by_anchor = {str(row.get("anchor_id")): row for row in anchors}
    _require(set(by_anchor) == set(EXPECTED_ANCHORS), "Known anchor set changed")
    for anchor_id, expected in EXPECTED_ANCHORS.items():
        row = by_anchor[anchor_id]
        _require(row.get("doi") == expected["doi"], f"Unexpected DOI for {anchor_id}")
        _require(row.get("pmid") == expected["pmid"], f"Unexpected PMID for {anchor_id}")
        _require(row.get("counts_as_new_discovery") is False, f"Anchor {anchor_id} cannot count as new discovery")

    streams = programme.get("query_streams")
    _require(isinstance(streams, list), "query_streams must be a list")
    ids = [str(row.get("query_id") or "") for row in streams]
    _require(len(ids) == len(set(ids)), "Duplicate Europe PMC query_id")
    _require(set(ids) == EXPECTED_QUERY_IDS, "Europe PMC query stream set changed")
    terms = [str(row.get("query_term") or "") for row in streams]
    _require(len(terms) == len(set(terms)), "Duplicate Europe PMC query_term")
    for row in streams:
        query_id = str(row["query_id"])
        query = str(row.get("query_term") or "")
        _require(query.startswith("TITLE_ABS:"), f"{query_id} must use explicit TITLE_ABS scope")
        _require(_balanced_query(query), f"{query_id} has unbalanced query syntax")
        _require(row.get("status") == "ACTIVE", f"{query_id} must be ACTIVE in v0.1")
        _require(row.get("completeness_claim") is False, f"{query_id} cannot claim completeness")
        scope_tiers = set(row.get("scope_tiers") or [])
        _require(scope_tiers and scope_tiers <= {"A", "B", "C", "D"}, f"Invalid scope tiers for {query_id}")
        if query_id == "DISCOVERY-EPMC-GREY-MENTAL-STATE-001":
            _require(scope_tiers == {"C"}, "Grey-area publication stream must remain Tier C only")

    inclusion = programme.get("inclusion_policy") or {}
    for key in (
        "automatic_publication_source_admission",
        "automatic_model_or_system_relationship_creation",
        "automatic_dataset_relationship_creation",
        "automatic_assessment_mutation",
        "automatic_monitor_creation",
    ):
        _require(inclusion.get(key) is False, f"{key} must remain false")
    _require(inclusion.get("human_relevance_review_required") is True, "Human relevance review is required")

    projection = programme.get("candidate_projection") or {}
    _require(set(projection.get("required_fields") or []) == REQUIRED_CANDIDATE_FIELDS, "Candidate projection field contract changed")
    _require(projection.get("raw_api_page_payloads_emitted_to_s2") is False, "Raw API pages must not be emitted to S2")
    _require(projection.get("full_text_emitted_to_s2") is False, "Full text must not be emitted to S2 by discovery")
    _require(projection.get("participant_level_data_emitted") is False, "Participant-level data must not be emitted")

    coverage = programme.get("coverage_contract") or {}
    _require(set(coverage.get("required_metrics_per_query") or []) == REQUIRED_COVERAGE_METRICS, "Coverage metric contract changed")
    completion = coverage.get("mechanical_completion_requires") or {}
    _require(completion == {
        "cursor_sequence_valid": True,
        "terminal_cursor_state": "TERMINAL",
        "reported_hit_count_state": "CONSISTENT",
        "reported_total_reconciliation_state": "MATCH",
    }, "Mechanical completion contract changed")
    for key in (
        "publication_database_completeness_claim",
        "global_neuroai_publication_recall_claim",
        "query_recall_claim",
    ):
        _require(coverage.get(key) is False, f"{key} must remain false")

    review = programme.get("human_review_contract") or {}
    _require(review.get("required_dispositions") == ["ACCEPT", "REJECT", "DEFER", "EXCLUDE"], "Review dispositions changed")
    _require(review.get("automatic_acceptance") is False, "Automatic acceptance is prohibited")

    network = programme.get("network_policy") or {}
    _require(network.get("live_execution") == "OPT_IN_ONLY", "Live execution must remain opt-in")
    _require(network.get("requires_workbench_network_gate") is True, "Workbench network gate is required")
    _require(network.get("configuration_performs_http") is False, "Config must not perform HTTP")
    _require(network.get("hosted_success_claim_allowed_without_runner_steps") is False, "Hosted success cannot be claimed without runner steps")

    return {
        "programme_id": programme["programme_id"],
        "source_universe_id": programme["source_universe_id"],
        "query_stream_count": len(streams),
        "anchor_count": len(anchors),
        "integration_state": dependency["integration_state"],
        "network_requests_performed": False,
        "canonical_mutation_performed": False,
        "global_recall_claim": False,
    }


def main() -> None:
    result = validate_programme(_load(PROGRAMME_PATH), _load(UNIVERSE_REGISTRY_PATH))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

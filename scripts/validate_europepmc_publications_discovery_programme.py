"""Validate bounded SU-PUBLICATIONS Europe PMC discovery without network access."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
PROGRAMME_PATH=Path("curation/europepmc_publications_discovery_programme_v0.1.json");UNIVERSE_REGISTRY_PATH=Path("curation/source_universe_registry_v0.1.json")
EXPECTED_QUERY_IDS={"DISCOVERY-EPMC-BCI-001","DISCOVERY-EPMC-NEURAL-DECODING-AI-001","DISCOVERY-EPMC-INVASIVE-INTERFACE-AI-001","DISCOVERY-EPMC-CLOSED-LOOP-NEUROMODULATION-001","DISCOVERY-EPMC-EEG-FOUNDATION-001","DISCOVERY-EPMC-SPEECH-COMMUNICATION-001","DISCOVERY-EPMC-VISUAL-NEUROPROSTHESIS-COMPUTATION-001","DISCOVERY-EPMC-GREY-MENTAL-STATE-001"}
EXPECTED_ANCHORS={"EPMC-ANCHOR-PRIMA-001":("10.1056/nejmoa2501396","41124203"),"EPMC-ANCHOR-SPEECH-NEUROPROSTHESIS-001":("10.1056/nejmoa2314132","39141853")}
REQUIRED_FIELDS={"resolved_identity","identity_type","title","publication_year","author_string","journal_or_source","publication_type","doi","pmid","pmcid","source_plus_ext_id","is_preprint","query_memberships","normalized_record_sha256"}
REQUIRED_COVERAGE={"supplied_page_count","raw_returned_record_count","unique_resolved_identity_count","reported_hit_count_state","reported_hit_count","cursor_sequence_valid","terminal_cursor_state","reported_total_reconciliation_state","known_anchor_count","known_controlled_source_duplicate_count","new_candidate_count","cross_query_duplicate_representation_count","unresolved_identity_count","preprint_count","non_preprint_record_count","publication_type_missing_count","source_distribution"}
def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))
def _require(c:bool,m:str)->None:
    if not c:raise ValueError(m)
def _universe(reg:dict[str,Any],uid:str)->dict[str,Any]:
    rows=reg.get("universes");_require(isinstance(rows,list),"Source-universe registry must contain universes");matches=[r for r in rows if r.get("universe_id")==uid];_require(len(matches)==1,f"Expected exactly one {uid} universe");return matches[0]
def _balanced(query:str)->bool:
    depth=0;quoted=False;escaped=False
    for ch in query:
        if escaped:escaped=False;continue
        if ch=="\\":escaped=True;continue
        if ch=='"':quoted=not quoted;continue
        if quoted:continue
        if ch=="(":depth+=1
        elif ch==")":
            depth-=1
            if depth<0:return False
    return depth==0 and not quoted and not escaped
def validate_programme(p:dict[str,Any],reg:dict[str,Any])->dict[str,Any]:
    _require(p.get("programme_id")=="SU-PUBLICATIONS-EUROPEPMC-v0.1","Unexpected programme_id");_require(p.get("status")=="NONCANONICAL_PROGRAMME_CONTROL","Programme must remain noncanonical");_require(p.get("source_universe_id")=="SU-PUBLICATIONS" and p.get("source_system")=="EUROPE_PMC","Programme universe/system changed");_require(_universe(reg,"SU-PUBLICATIONS").get("canonical_completeness_claim") is False,"SU-PUBLICATIONS must not claim completeness")
    provider=p.get("provider_contract") or {};_require(provider.get("provider")=="Europe PMC" and provider.get("api_endpoint")=="https://www.ebi.ac.uk/europepmc/webservices/rest/search","Provider contract changed");_require(provider.get("query_parameter")=="query" and provider.get("format")=="json" and provider.get("result_type")=="lite","Request contract changed");_require(provider.get("page_size")==1000 and provider.get("pagination_mode")=="CURSOR_MARK" and provider.get("first_cursor_mark")=="*" and provider.get("next_cursor_field")=="nextCursorMark" and provider.get("reported_denominator_field")=="hitCount","Pagination/denominator contract changed");_require(provider.get("synonym_expansion") is False and provider.get("configuration_performs_http") is False,"Provider execution boundary changed")
    dep=p.get("workbench_dependency") or {};_require(dep.get("required_capability")=="project_europepmc_search_pages","Unexpected Workbench capability");_require(dep.get("integration_state")=="AVAILABLE","Merged Europe PMC projector must be AVAILABLE")
    identity=p.get("identity_policy") or {};_require(identity.get("preferred_identity_order")==["DOI","PMID","PMCID","SOURCE_PLUS_EXT_ID"],"Identity precedence changed");_require(identity.get("fuzzy_title_identity_merge_allowed") is False and identity.get("preprint_journal_version_auto_merge") is False,"Automatic identity merge prohibited");_require(identity.get("conflicting_same_identity_policy")=="FAIL_CLOSED","Identity conflicts must fail closed")
    anchors=p.get("known_identifier_anchors");_require(isinstance(anchors,list),"known_identifier_anchors required");by={str(r.get("anchor_id")):r for r in anchors};_require(set(by)==set(EXPECTED_ANCHORS),"Known anchor set changed")
    for aid,(doi,pmid) in EXPECTED_ANCHORS.items():_require(by[aid].get("doi")==doi and by[aid].get("pmid")==pmid,f"Anchor {aid} changed");_require(by[aid].get("counts_as_new_discovery") is False,f"Anchor {aid} cannot count as new discovery")
    streams=p.get("query_streams");_require(isinstance(streams,list),"query_streams required");ids=[str(r.get("query_id") or "") for r in streams];terms=[str(r.get("query_term") or "") for r in streams];_require(len(ids)==len(set(ids)) and set(ids)==EXPECTED_QUERY_IDS,"Europe PMC query set changed");_require(len(terms)==len(set(terms)),"Duplicate Europe PMC query terms")
    for row in streams:
        qid=row["query_id"];query=str(row.get("query_term") or "");_require(query.startswith("TITLE_ABS:") and _balanced(query),f"{qid}: invalid explicit TITLE_ABS query");_require(row.get("status")=="ACTIVE" and row.get("completeness_claim") is False,f"{qid}: status/completeness changed");tiers=set(row.get("scope_tiers") or []);_require(tiers and tiers<={"A","B","C","D"},f"{qid}: invalid tiers");
        if qid=="DISCOVERY-EPMC-GREY-MENTAL-STATE-001":_require(tiers=={"C"},"Grey-area stream must remain Tier C")
    inc=p.get("inclusion_policy") or {}
    for key in ("automatic_publication_source_admission","automatic_model_or_system_relationship_creation","automatic_dataset_relationship_creation","automatic_assessment_mutation","automatic_monitor_creation"):_require(inc.get(key) is False,f"{key} must remain false")
    _require(inc.get("human_relevance_review_required") is True,"Human relevance review required")
    projection=p.get("candidate_projection") or {};_require(set(projection.get("required_fields") or [])==REQUIRED_FIELDS,"Candidate field contract changed");_require(projection.get("raw_api_page_payloads_emitted_to_s2") is False and projection.get("full_text_emitted_to_s2") is False and projection.get("participant_level_data_emitted") is False,"Projection minimization changed")
    cov=p.get("coverage_contract") or {};_require(set(cov.get("required_metrics_per_query") or [])==REQUIRED_COVERAGE,"Coverage metrics changed");_require("peer_reviewed_or_journal_count" not in set(cov.get("required_metrics_per_query") or []),"Non-preprint cannot imply peer review");_require(cov.get("mechanical_completion_requires")=={"cursor_sequence_valid":True,"terminal_cursor_state":"TERMINAL","reported_hit_count_state":"CONSISTENT","reported_total_reconciliation_state":"MATCH"},"Mechanical completion contract changed")
    for key in ("publication_database_completeness_claim","global_neuroai_publication_recall_claim","query_recall_claim"):_require(cov.get(key) is False,f"{key} must remain false")
    review=p.get("human_review_contract") or {};_require(review.get("required_dispositions")==["ACCEPT","REJECT","DEFER","EXCLUDE"] and review.get("automatic_acceptance") is False,"Human review boundary changed")
    net=p.get("network_policy") or {};_require(net.get("live_execution")=="OPT_IN_ONLY" and net.get("requires_workbench_network_gate") is True and net.get("configuration_performs_http") is False and net.get("hosted_success_claim_allowed_without_runner_steps") is False,"Network/CI boundary changed")
    return {"programme_id":p["programme_id"],"source_universe_id":p["source_universe_id"],"query_stream_count":len(streams),"anchor_count":len(anchors),"integration_state":dep["integration_state"],"network_requests_performed":False,"canonical_mutation_performed":False,"global_recall_claim":False}
def main()->None:print(json.dumps(validate_programme(_load(PROGRAMME_PATH),_load(UNIVERSE_REGISTRY_PATH)),indent=2,sort_keys=True))
if __name__=="__main__":main()

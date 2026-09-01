"""Validate bounded openFDA 510(k) discovery without network access."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

PROGRAMME_PATH=Path("curation/openfda_510k_discovery_programme_v0.1.json")
UNIVERSE_REGISTRY_PATH=Path("curation/source_universe_registry_v0.1.json")
EXPECTED_QUERY_IDS={"DISCOVERY-OPENFDA-510K-BCI-001","DISCOVERY-OPENFDA-510K-DBS-NEUROSTIM-001","DISCOVERY-OPENFDA-510K-NEUROPROSTHESIS-001","DISCOVERY-OPENFDA-510K-VISUAL-NEUROPROSTHESIS-001","DISCOVERY-OPENFDA-510K-NEURAL-RECORDING-001"}
EXPECTED_SE_CODES=["SEKD","SESD","SESE","SESK","SESP","SESU","SESR"]
REQUIRED_FIELDS={"k_number","device_name","applicant","date_received","decision_date","decision_code","decision_description","clearance_type","product_code","statement_or_summary","expedited_review_flag","third_party_flag","query_memberships","normalized_record_sha256"}
REQUIRED_COVERAGE={"supplied_page_count","returned_record_count","unique_k_number_count","reported_total_count","reported_total_count_state","skip_sequence_valid","skip_coverage_state","over_26000_limit","search_after_or_partition_required","out_of_scope_den_count","known_controlled_duplicate_count","new_candidate_count","duplicate_representation_count","unresolved_k_number_count"}

def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))
def _req(c:bool,m:str)->None:
    if not c: raise ValueError(m)
def _universe(reg:dict[str,Any],uid:str)->dict[str,Any]:
    rows=reg.get("universes"); _req(isinstance(rows,list),"Source-universe registry missing")
    m=[r for r in rows if r.get("universe_id")==uid]; _req(len(m)==1,f"Expected one {uid}"); return m[0]

def validate_programme(p:dict[str,Any],reg:dict[str,Any])->dict[str,Any]:
    _req(p.get("programme_id")=="SU-REGULATION-OPENFDA-510K-v0.1","Unexpected programme_id")
    _req(p.get("status")=="NONCANONICAL_PROGRAMME_CONTROL","Programme must remain noncanonical")
    _req(p.get("source_universe_id")=="SU-REGULATION" and p.get("source_system")=="OPENFDA_DEVICE_510K","Programme universe/system changed")
    _req(_universe(reg,"SU-REGULATION").get("canonical_completeness_claim") is False,"SU-REGULATION cannot claim completeness")
    provider=p.get("provider_contract") or {}
    expected={"provider":"U.S. FDA openFDA Device 510(k) API","endpoint":"https://api.fda.gov/device/510k.json","method":"GET","response_media_type":"application/json","source_dataset":"510(k) Clearances","time_period_start":"1976","provider_update_frequency":"MONTHLY","reported_denominator_path":"meta.results.total","skip_path":"meta.results.skip","limit_path":"meta.results.limit","results_path":"results","primary_submission_id_field":"k_number","max_records_per_request":1000,"max_skip":25000,"max_direct_result_count":26000,"provider_supports_search_after":True,"provider_supports_bulk_downloads":True,"configuration_performs_http":False}
    _req(provider==expected,"openFDA 510(k) provider contract changed")
    dep=p.get("workbench_dependency") or {}; _req(dep.get("required_capability")=="project_openfda_510k_pages","Unexpected Workbench capability"); _req(dep.get("integration_state")=="PENDING_S1_MERGE","Unmerged 510(k) projector must remain PENDING_S1_MERGE")
    ident=p.get("identity_policy") or {}; _req(ident.get("primary_identity")=="K_NUMBER","510(k) identity changed"); _req(ident.get("admitted_prefixes")==["K","BK"],"K/BK admission scope changed"); _req(ident.get("den_prefix_is_de_novo_and_out_of_scope_for_v0_1") is True,"DEN must remain out of 510(k) v0.1 scope")
    for k in ("same_device_name_auto_merge","same_applicant_auto_entity_merge","product_code_auto_system_merge","openfda_harmonized_fields_auto_identity_merge"):_req(ident.get(k) is False,f"{k} must remain false")
    _req(ident.get("record_content_change_is_successor_observation_not_new_submission_identity") is True,"Record changes must remain successor observations")
    decision=p.get("decision_semantics_policy") or {}
    _req(decision.get("recognized_substantial_equivalence_codes")==EXPECTED_SE_CODES,"FDA 510(k) SE decision-code allowlist changed")
    _req(decision.get("recognized_state")=="SUBSTANTIALLY_EQUIVALENT_RECORDED","Recognized decision state changed")
    _req(decision.get("unknown_or_missing_code_state")=="UNRESOLVED_DECISION_CODE","Unknown decision state changed")
    _req(decision.get("description_only_inference_allowed") is False,"Decision descriptions alone cannot create recognized SE semantics")
    _req(decision.get("device_name_or_record_presence_inference_allowed") is False,"Device name/record presence cannot create decision semantics")
    inc=p.get("inclusion_policy") or {}
    for k in ("automatic_source_admission","automatic_system_or_device_entity_creation","automatic_applicant_entity_creation","automatic_predicate_relationship_creation","automatic_clearance_claim_from_record_presence","automatic_global_authorization_claim_creation","automatic_safety_effectiveness_claim_creation","automatic_system_conformance_claim_creation","automatic_assessment_mutation","automatic_reopening_decision","automatic_monitor_creation"):_req(inc.get(k) is False,f"{k} must remain false")
    _req(inc.get("human_relevance_review_required") is True,"Human review required")
    paging=p.get("paging_policy") or {}; _req(paging.get("execution_mode_v0_1")=="SKIP_LIMIT_BOUNDED","Paging mode changed"); _req(paging.get("page_limit")==1000 and paging.get("max_skip")==25000 and paging.get("max_direct_result_count")==26000,"Paging bounds changed"); _req(paging.get("preferred_partition_field")=="decision_date","Partition field changed"); _req(paging.get("silent_truncation_allowed") is False and paging.get("partial_over_limit_candidate_emission_allowed") is False,"Truncation prohibited"); _req(paging.get("search_after_not_yet_authorized_by_v0_1_projector") is True,"v0.1 cannot silently use search-after")
    streams=p.get("query_streams"); _req(isinstance(streams,list),"query_streams required"); ids=[r.get("query_id") for r in streams]; _req(len(ids)==len(set(ids)) and set(ids)==EXPECTED_QUERY_IDS,"510(k) query set changed")
    for r in streams:
        q=r["query_id"]; _req(r.get("cadence")=="MONTHLY" and r.get("status")=="ACTIVE",f"{q}: cadence/status changed"); _req(r.get("completeness_claim") is False,f"{q}: cannot claim completeness"); s=r.get("search"); _req(isinstance(s,str) and "device_name:" in s and "+OR+" in s,f"{q}: explicit device_name OR search required")
    proj=p.get("candidate_projection") or {}; _req(set(proj.get("required_fields") or [])==REQUIRED_FIELDS,"510(k) candidate fields changed"); _req(proj.get("address_or_contact_fields_in_discovery_layer") is False and proj.get("raw_api_pages_emitted_to_s2") is False,"510(k) minimization changed"); _req(proj.get("den_records_emitted_as_510k_candidates") is False,"DEN cannot be emitted as 510(k) candidates"); _req(proj.get("substantial_equivalence_or_clearance_state_derived_only_from_decision_fields") is True,"Clearance semantics must derive from decision fields")
    cov=p.get("coverage_contract") or {}; _req(set(cov.get("required_metrics_per_leaf_query") or [])==REQUIRED_COVERAGE,"510(k) coverage metrics changed"); _req(cov.get("mechanical_completion_requires")=={"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"search_after_or_partition_required":False},"Mechanical completion contract changed")
    for k in ("device_510k_database_completeness_claim","global_neuroai_510k_coverage_claim","query_recall_claim","record_presence_is_clearance_claim","clearance_is_pma_approval_claim","clearance_is_global_authorization_claim","clearance_is_all_configuration_conformance_claim"):_req(cov.get(k) is False,f"{k} must remain false")
    review=p.get("human_review_contract") or {}
    for k in ("automatic_acceptance","record_presence_is_clearance_evidence","clearance_record_is_pma_approval","clearance_record_is_global_authorization","clearance_record_is_full_clinical_effectiveness_determination","clearance_record_is_all_configuration_conformance_evidence","clearance_record_automatically_reopens_assessment"):_req(review.get(k) is False,f"{k} must remain false")
    net=p.get("network_policy") or {}; _req(net.get("live_execution")=="OPT_IN_ONLY" and net.get("requires_workbench_network_gate") is True,"Network boundary changed"); _req(net.get("configuration_performs_http") is False and net.get("hosted_success_claim_allowed_without_runner_steps") is False,"Execution-status boundary changed")
    return {"programme_id":p["programme_id"],"query_stream_count":len(streams),"integration_state":dep["integration_state"],"recognized_se_code_count":len(EXPECTED_SE_CODES),"den_out_of_scope":True,"record_presence_is_clearance_claim":False,"network_requests_performed":False,"canonical_mutation_performed":False}

def main()->None: print(json.dumps(validate_programme(_load(PROGRAMME_PATH),_load(UNIVERSE_REGISTRY_PATH)),indent=2,sort_keys=True))
if __name__=="__main__":main()

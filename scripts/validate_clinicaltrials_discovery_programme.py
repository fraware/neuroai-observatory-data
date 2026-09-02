#!/usr/bin/env python3
"""Validate the current bounded SU-TRIALS ClinicalTrials.gov programme without network I/O."""
from __future__ import annotations
import json,re,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from current_source_namespace import materialize_effective_source_namespace
P=ROOT/"curation"/"clinicaltrials_discovery_programme_v0.1.json"
BACKLOG=ROOT/"curation"/"source_universe_expansion_backlog_v0.1.json"
EXPECTED_TERMS={
 "DISCOVERY-CTGOV-BCI-001":"(\"brain-computer interface\" OR \"brain computer interface\")",
 "DISCOVERY-CTGOV-NEURAL-PROSTHESIS-001":"\"neural prosthesis\"",
 "DISCOVERY-CTGOV-BRAIN-IMPLANT-001":"\"brain implant\" AND (interface OR prosthesis)",
 "DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001":"(\"retinal prosthesis\" OR \"visual prosthesis\" OR \"retina implant\")",
}
REQUIRED_METRICS={"supplied_page_count","raw_returned_record_count","unique_nct_record_count_before_programme_filter","included_candidate_count","known_nct_duplicate_count","new_candidate_count","excluded_by_study_type_count","duplicate_nct_representation_count","reported_total_count_state","reported_total_count","pagination_sequence_valid","fully_paginated","final_next_page_token_present","reported_total_reconciliation_state"}
MECH={"pagination_sequence_valid":True,"fully_paginated":True,"reported_total_count_state":"CONSISTENT","reported_total_reconciliation_state":"MATCH"}
NCT_RE=re.compile(r"NCT\d{8}",re.I)
def load(path:Path)->Any:return json.loads(path.read_text(encoding="utf-8"))
def req(ok:bool,msg:str)->None:
 if not ok:raise ValueError(msg)
def current_nct_index()->dict[str,str]:
 ns=materialize_effective_source_namespace();req(ns.get("materialized_source_count")==248,"Current Source namespace must contain 248 records")
 digest=ns.get("source_id_set_sha256");req(isinstance(digest,str) and len(digest)==64,"Current Source digest missing")
 out={}
 for s in ns["sources"]:
  loc=str(s.get("canonical_locator") or "");matches={m.group(0).upper() for m in NCT_RE.finditer(loc)}
  for nct in matches:
   prior=out.get(nct);sid=s["source_id"]
   req(prior in (None,sid),f"Conflicting controlled Sources for {nct}");out[nct]=sid
 return out
def validate_programme(p:dict[str,Any],backlog:dict[str,Any])->dict[str,Any]:
 req(p.get("programme_id")=="SU-TRIALS-CTGOV-v0.1","Unexpected programme_id")
 req(p.get("status")=="NONCANONICAL_PROGRAMME_CONTROL","Programme must remain noncanonical")
 req(p.get("source_universe_id")=="SU-TRIALS" and p.get("source_system")=="CLINICALTRIALS_GOV","Source-universe/system mismatch")
 streams=[r for r in backlog.get("streams",[]) if isinstance(r,dict) and r.get("stream_id")=="SU-TRIALS"]
 req(len(streams)==1,"Planning control must contain exactly one SU-TRIALS stream")
 req(backlog.get("status")=="NONCANONICAL_PLANNING_CONTROL","Expansion control must remain noncanonical")
 invariants=set(backlog.get("programme_invariants") or [])
 for token in ("DISCOVERY_RESULT_IS_NOT_CANONICAL_SOURCE","SOURCE_IDENTITY_ACCEPTANCE_REQUIRES_HUMAN_DISPOSITION","MECHANICAL_COMPLETION_IS_NOT_DOMAIN_COMPLETENESS","NO_AUTOMATIC_TRIAL_SYSTEM_RELATIONSHIP_OR_ASSESSMENT_MUTATION"):
  req(token in invariants,f"Missing expansion invariant {token}")
 dep=p.get("workbench_dependency") or {};req(dep=={"minimum_package_line":"0.3.0.dev0","required_capability":"project_clinicaltrials_search_pages","integration_state":"AVAILABLE"},"ClinicalTrials Workbench dependency must be AVAILABLE")
 req(p.get("identity_policy")=={"registry_identity_key":"NCT_ID","fuzzy_identity_merge_allowed":False,"cross_query_deduplication":"EXACT_NCT_ID","conflicting_same_id_policy":"FAIL_CLOSED","known_identifier_match":"EXACT_NCT_TO_CONTROLLED_SOURCE_ID"},"Identity policy drift")
 inc=p.get("inclusion_policy") or {};req(inc.get("required_study_types")==["INTERVENTIONAL"],"Interventional-only inclusion required");req(inc.get("human_relevance_review_required") is True,"Human relevance review required")
 for k in ("automatic_trial_entity_creation","automatic_trial_site_relationship_creation","automatic_source_admission","automatic_monitor_creation","automatic_assessment_mutation","participant_level_data_collection"):req(inc.get(k) is False,f"{k} must remain false")
 req(p.get("request_policy")=={"api_endpoint":"/api/v2/studies","query_parameter":"query.term","count_total_first_page":True,"count_total_later_pages":False,"pagination_mode":"OPAQUE_NEXT_PAGE_TOKEN","total_count_reconciliation_required_for_mechanical_completion":True},"Request/denominator policy drift")
 anchors=p.get("known_identifier_anchors");req(isinstance(anchors,list) and len(anchors)==1,"Exactly one continuity anchor required");a=anchors[0];req(a.get("nct_id")=="NCT04676854" and a.get("existing_source_id")=="SRC-PR-002" and a.get("counts_as_new_discovery") is False,"Continuity anchor drift")
 nct=current_nct_index();req(nct.get("NCT04676854")=="SRC-PR-002","Current controlled Source namespace does not resolve the PRIMA anchor exactly")
 qs=p.get("query_streams");req(isinstance(qs,list) and len(qs)==4,"Exactly four ClinicalTrials query streams required");ids=[str(r.get("query_id") or "") for r in qs];req(len(ids)==len(set(ids)) and set(ids)==set(EXPECTED_TERMS),"Query stream identity set drift")
 for r in qs:
  q=r["query_id"];req(r.get("query_term")==EXPECTED_TERMS[q],f"{q}: query term drift");req(r.get("query_surface")=="query.term",f"{q}: query surface drift");req(r.get("post_retrieval_required_study_types")==["INTERVENTIONAL"],f"{q}: study-type filter drift");req(r.get("page_size")==100 and r.get("cadence")=="MONTHLY" and r.get("status")=="ACTIVE",f"{q}: execution controls drift");req(r.get("completeness_claim") is False,f"{q}: completeness claim prohibited")
 cov=p.get("coverage_contract") or {};req(set(cov.get("required_metrics") or [])==REQUIRED_METRICS,"Coverage metrics drift");req(cov.get("mechanical_completion_requires")==MECH,"Mechanical completion contract drift");req(cov.get("registry_completeness_claim") is False and cov.get("global_neuroai_trial_recall_claim") is False,"Completeness/recall claim prohibited")
 net=p.get("network_policy") or {};req(net=={"live_execution":"OPT_IN_ONLY","requires_workbench_network_gate":True,"configuration_performs_http":False,"hosted_success_claim_allowed_without_runner_steps":False},"Network/runner-status policy drift")
 ns=materialize_effective_source_namespace()
 return {"programme_id":p["programme_id"],"query_stream_count":4,"workbench_integration_state":"AVAILABLE","materialized_source_count":248,"source_id_set_sha256":ns["source_id_set_sha256"],"known_nct_count":len(nct),"prima_anchor_resolved":True,"network_requests_performed":False,"automatic_mutation_performed":False,"registry_completeness_claim":False,"global_neuroai_trial_recall_claim":False}
def main()->int:
 try:r=validate_programme(load(P),load(BACKLOG));print(json.dumps(r,indent=2,sort_keys=True));return 0
 except Exception as e:print(json.dumps({"valid":False,"error":str(e)},indent=2,sort_keys=True));return 1
if __name__=="__main__":raise SystemExit(main())

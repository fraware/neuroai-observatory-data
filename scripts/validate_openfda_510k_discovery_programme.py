"""Validate current bounded openFDA 510(k) discovery without network access."""
import json
from pathlib import Path
P=Path('curation/openfda_510k_discovery_programme_v0.1.json');R=Path('curation/source_universe_registry_v0.1.json')
SE=['SEKD','SESD','SESE','SESK','SESP','SESU','SESR']
Q={'DISCOVERY-OPENFDA-510K-BCI-001','DISCOVERY-OPENFDA-510K-DBS-NEUROSTIM-001','DISCOVERY-OPENFDA-510K-NEUROPROSTHESIS-001','DISCOVERY-OPENFDA-510K-VISUAL-NEUROPROSTHESIS-001','DISCOVERY-OPENFDA-510K-NEURAL-RECORDING-001'}
def _load(p):return json.loads(p.read_text())
def req(c,m):
    if not c:raise ValueError(m)
def validate_programme(p,r):
    req(p.get('programme_id')=='SU-REGULATION-OPENFDA-510K-v0.1' and p.get('status')=='NONCANONICAL_PROGRAMME_CONTROL','programme identity/status changed')
    req(p.get('source_universe_id')=='SU-REGULATION' and p.get('source_system')=='OPENFDA_DEVICE_510K','source binding changed')
    u=[x for x in r.get('universes',[]) if x.get('universe_id')=='SU-REGULATION'];req(len(u)==1 and u[0].get('canonical_completeness_claim') is False,'SU-REGULATION completeness boundary changed')
    d=p['workbench_dependency'];req(d=={'minimum_package_line':'0.3.0.dev0','required_capability':'project_openfda_510k_pages','integration_state':'AVAILABLE'},'510(k) capability must remain AVAILABLE')
    i=p['identity_policy'];req(i['primary_identity']=='K_NUMBER' and i['admitted_prefixes']==['K','BK'] and i['den_prefix_is_de_novo_and_out_of_scope_for_v0_1'] is True,'510(k)/De Novo identity split changed')
    for k in ('same_device_name_auto_merge','same_applicant_auto_entity_merge','product_code_auto_system_merge','openfda_harmonized_fields_auto_identity_merge'):req(i[k] is False,k+' must remain false')
    s=p['decision_semantics_policy'];req(s['recognized_substantial_equivalence_codes']==SE,'SE decision-code allowlist changed');req(s['recognized_state']=='SUBSTANTIALLY_EQUIVALENT_RECORDED' and s['unknown_or_missing_code_state']=='UNRESOLVED_DECISION_CODE','decision states changed');req(s['description_only_inference_allowed'] is False and s['device_name_or_record_presence_inference_allowed'] is False,'decision inference boundary changed')
    inc=p['inclusion_policy']
    for k in ('automatic_source_admission','automatic_system_or_device_entity_creation','automatic_applicant_entity_creation','automatic_predicate_relationship_creation','automatic_clearance_claim_from_record_presence','automatic_global_authorization_claim_creation','automatic_safety_effectiveness_claim_creation','automatic_system_conformance_claim_creation','automatic_assessment_mutation','automatic_reopening_decision','automatic_monitor_creation'):req(inc[k] is False,k+' must remain false')
    pg=p['paging_policy'];req((pg['page_limit'],pg['initial_skip'],pg['max_skip'],pg['max_direct_result_count'])==(1000,0,25000,26000),'paging bounds changed');req(pg['preferred_partition_field']=='decision_date','partition field changed');req(pg['silent_truncation_allowed'] is False and pg['partial_over_limit_candidate_emission_allowed'] is False and pg['search_after_not_yet_authorized_by_v0_1_projector'] is True,'paging fail-closed boundary changed')
    qs=p['query_streams'];req({x['query_id'] for x in qs}==Q and len(qs)==5,'query set changed')
    for x in qs:req(x['status']=='ACTIVE' and x['cadence']=='MONTHLY' and x['completeness_claim'] is False and '+OR+' in x['search'],'query contract changed')
    cp=p['candidate_projection'];req(cp['den_records_emitted_as_510k_candidates'] is False and cp['substantial_equivalence_or_clearance_state_derived_only_from_decision_fields'] is True and cp['address_or_contact_fields_in_discovery_layer'] is False and cp['raw_api_pages_emitted_to_s2'] is False,'candidate/pathway boundary changed')
    cv=p['coverage_contract'];req(cv['record_presence_is_clearance_claim'] is False and cv['clearance_is_pma_approval_claim'] is False and cv['clearance_is_global_authorization_claim'] is False and cv['clearance_is_all_configuration_conformance_claim'] is False,'authority boundary changed')
    hr=p['human_review_contract'];req(hr['record_presence_is_clearance_evidence'] is False and hr['clearance_record_automatically_reopens_assessment'] is False,'human-review authority boundary changed')
    return {'programme_id':p['programme_id'],'query_stream_count':5,'integration_state':'AVAILABLE','network_requests_performed':False,'automatic_reopening':False,'canonical_mutation_performed':False}
def main():print(json.dumps(validate_programme(_load(P),_load(R)),indent=2,sort_keys=True))
if __name__=='__main__':main()

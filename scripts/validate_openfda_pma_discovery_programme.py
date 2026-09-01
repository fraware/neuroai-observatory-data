"""Validate current bounded openFDA PMA discovery without network access."""
import json
from pathlib import Path
P=Path('curation/openfda_pma_discovery_programme_v0.1.json');R=Path('curation/source_universe_registry_v0.1.json')
DEC={'APPR':'APPROVAL_RECORDED','WTDR':'WITHDRAWAL_RECORDED','DENY':'DENIAL_RECORDED','LE30':'THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED','APRL':'RECLASSIFICATION_AFTER_APPROVAL_RECORDED','APWD':'WITHDRAWAL_AFTER_APPROVAL_RECORDED','GT30':'NO_DECISION_WITHIN_30_DAYS_RECORDED','APCV':'CONVERSION_AFTER_APPROVAL_RECORDED'}
Q={'DISCOVERY-OPENFDA-PMA-BCI-001','DISCOVERY-OPENFDA-PMA-DBS-NEUROSTIM-001','DISCOVERY-OPENFDA-PMA-NEUROPROSTHESIS-001','DISCOVERY-OPENFDA-PMA-VISUAL-NEUROPROSTHESIS-001','DISCOVERY-OPENFDA-PMA-NEURAL-RECORDING-001'}
def load(x):return json.loads(x.read_text())
def req(c,m):
    if not c:raise ValueError(m)
def validate_programme(p,r):
    req(p.get('programme_id')=='SU-REGULATION-OPENFDA-PMA-v0.1' and p.get('status')=='NONCANONICAL_PROGRAMME_CONTROL','PMA programme identity/status changed')
    req(p.get('source_universe_id')=='SU-REGULATION' and p.get('source_system')=='OPENFDA_DEVICE_PMA','PMA source binding changed')
    u=[x for x in r.get('universes',[]) if x.get('universe_id')=='SU-REGULATION'];req(len(u)==1 and u[0].get('canonical_completeness_claim') is False,'SU-REGULATION completeness boundary changed')
    req(p['workbench_dependency']=={'minimum_package_line':'0.3.0.dev0','required_capability':'project_openfda_pma_pages','integration_state':'AVAILABLE'},'PMA capability must remain AVAILABLE')
    i=p['identity_policy'];req(i['record_identity']=='PMA_NUMBER_PLUS_SUPPLEMENT_NUMBER' and i['original_application_sentinel']=='ORIGINAL','PMA composite identity changed');req(i['admitted_pma_prefixes']==['P','BP','D'] and i['h_prefix_hde_out_of_scope_for_v0_1'] is True and i['n_prefix_legacy_nda_out_of_scope_for_v0_1'] is True,'PMA pathway split changed')
    req(i['same_pma_number_different_supplement_auto_merge'] is False and i['record_content_change_is_successor_observation_not_new_record_identity'] is True,'PMA history boundary changed')
    d=p['decision_semantics_policy'];req(d['exact_code_map']==DEC,'PMA decision map changed');req(d['unknown_or_missing_code_state']=='UNRESOLVED_DECISION_CODE' and d['approval_state_requires_exact_appr_code'] is True and d['supplement_approval_does_not_rewrite_original_application_record'] is True and d['record_presence_does_not_imply_approval'] is True,'PMA decision boundary changed')
    inc=p['inclusion_policy']
    for k in ('automatic_source_admission','automatic_device_or_system_entity_creation','automatic_applicant_entity_creation','automatic_original_supplement_lineage_relationship_creation','automatic_current_commercial_configuration_claim_creation','automatic_global_authorization_claim_creation','automatic_system_conformance_claim_creation','automatic_assessment_mutation','automatic_reopening_decision','automatic_monitor_creation'):req(inc[k] is False,k+' must remain false')
    pg=p['paging_policy'];req((pg['page_limit'],pg['initial_skip'],pg['max_skip'],pg['max_direct_result_count'])==(1000,0,25000,26000),'PMA paging bounds changed');req(pg['preferred_partition_field']=='decision_date' and pg['silent_truncation_allowed'] is False and pg['search_after_not_yet_authorized_by_v0_1_projector'] is True,'PMA paging boundary changed')
    qs=p['query_streams'];req(len(qs)==5 and {x['query_id'] for x in qs}==Q,'PMA query set changed')
    for x in qs:req(x['status']=='ACTIVE' and x['cadence']=='MONTHLY' and x['completeness_claim'] is False,'PMA query contract changed')
    cp=p['candidate_projection'];req(cp['hde_records_emitted_as_pma_candidates'] is False and cp['legacy_nda_records_emitted_as_pma_candidates'] is False and cp['decision_semantics_derived_only_from_exact_decision_code'] is True and cp['raw_api_pages_emitted_to_s2'] is False,'PMA candidate/pathway boundary changed')
    cv=p['coverage_contract'];req(cv['record_presence_is_approval_claim'] is False and cv['supplement_approval_is_original_application_approval_claim'] is False and cv['approval_is_global_authorization_claim'] is False and cv['approval_is_all_configuration_conformance_claim'] is False,'PMA authority boundary changed')
    h=p['human_review_contract'];req(h['record_presence_is_approval_evidence'] is False and h['supplement_record_automatically_changes_original_approval_scope'] is False and h['approval_record_automatically_reopens_assessment'] is False,'PMA review authority changed')
    return {'programme_id':p['programme_id'],'query_stream_count':5,'integration_state':'AVAILABLE','network_requests_performed':False,'automatic_reopening':False,'canonical_mutation_performed':False}
def main():print(json.dumps(validate_programme(load(P),load(R)),indent=2,sort_keys=True))
if __name__=='__main__':main()

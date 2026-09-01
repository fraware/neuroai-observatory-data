"""Validate current bounded openFDA HDE discovery without network access."""
import json
from pathlib import Path
P=Path('curation/openfda_hde_discovery_programme_v0.1.json');R=Path('curation/source_universe_registry_v0.1.json')
DEC={'APPR':'HDE_APPROVAL_RECORDED','WTDR':'WITHDRAWAL_RECORDED','DENY':'DENIAL_RECORDED','LE30':'THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED','APRL':'RECLASSIFICATION_AFTER_APPROVAL_RECORDED','APWD':'WITHDRAWAL_AFTER_APPROVAL_RECORDED','GT30':'NO_DECISION_WITHIN_30_DAYS_RECORDED','APCV':'CONVERSION_AFTER_APPROVAL_RECORDED'}
def load(x):return json.loads(x.read_text())
def req(c,m):
    if not c:raise ValueError(m)
def validate_programme(p,r):
    req(p.get('programme_id')=='SU-REGULATION-OPENFDA-HDE-v0.1' and p.get('status')=='NONCANONICAL_PROGRAMME_CONTROL','HDE programme identity/status changed')
    req(p.get('source_universe_id')=='SU-REGULATION' and p.get('source_system')=='OPENFDA_DEVICE_PMA_HDE_SUBSET','HDE source binding changed')
    req(p['workbench_dependency']=={'minimum_package_line':'0.3.0.dev0','required_capability':'project_openfda_hde_pages','integration_state':'AVAILABLE'},'HDE capability must remain AVAILABLE')
    i=p['identity_policy'];req(i['record_identity']=='HDE_NUMBER_PLUS_SUPPLEMENT_NUMBER' and i['original_application_sentinel']=='ORIGINAL' and i['required_hde_prefix']=='H' and i['non_h_prefix_records_out_of_scope'] is True,'HDE identity/pathway boundary changed');req(i['same_hde_number_different_supplement_auto_merge'] is False,'HDE supplements must remain distinct')
    d=p['decision_semantics_policy'];req(d['exact_code_map']==DEC and d['hde_approval_state_requires_exact_appr_code'] is True and d['record_presence_does_not_imply_hde_approval'] is True and d['supplement_approval_does_not_rewrite_original_hde_record'] is True,'HDE decision boundary changed')
    a=p['hde_authority_policy'];req(a['exact_appr_record_supports_scoped_hde_marketing_authorization'] is True,'APPR HDE marketing-authorization boundary changed')
    for k in ('hde_approval_does_not_establish_reasonable_assurance_of_effectiveness','hde_standard_uses_probable_benefit_risk_boundary','hde_approval_does_not_establish_facility_irb_approval','hde_approval_does_not_establish_global_authorization','hde_approval_does_not_establish_exact_current_commercial_configuration','hde_approval_does_not_establish_all_configuration_conformance'):req(a[k] is True,k+' must remain true')
    inc=p['inclusion_policy']
    for k in ('automatic_source_admission','automatic_device_or_system_entity_creation','automatic_applicant_entity_creation','automatic_original_supplement_lineage_relationship_creation','automatic_effectiveness_claim_creation','automatic_facility_irb_authorization_claim_creation','automatic_current_commercial_configuration_claim_creation','automatic_global_authorization_claim_creation','automatic_system_conformance_claim_creation','automatic_assessment_mutation','automatic_reopening_decision','automatic_monitor_creation'):req(inc[k] is False,k+' must remain false')
    pg=p['paging_policy'];req((pg['page_limit'],pg['initial_skip'],pg['max_skip'],pg['max_direct_result_count'])==(1000,0,25000,26000),'HDE paging bounds changed');req(pg['preferred_partition_field']=='decision_date' and pg['silent_truncation_allowed'] is False and pg['search_after_not_yet_authorized_by_v0_1_projector'] is True,'HDE paging boundary changed')
    qs=p['query_streams'];req(len(qs)==5,'HDE query count changed')
    for q in qs:req(q['status']=='ACTIVE' and q['cadence']=='MONTHLY' and q['completeness_claim'] is False and 'pma_number:H*' in q['search'],'HDE query must remain explicitly H-constrained')
    cp=p['candidate_projection'];req(cp['non_h_prefix_records_emitted_as_hde_candidates'] is False and cp['decision_semantics_derived_only_from_exact_decision_code'] is True and cp['effectiveness_claim_created_from_hde_approval'] is False and cp['facility_irb_claim_created_from_hde_record'] is False,'HDE candidate authority boundary changed')
    cv=p['coverage_contract'];req(cv['record_presence_is_hde_approval_claim'] is False and cv['hde_approval_is_reasonable_assurance_effectiveness_claim'] is False and cv['hde_approval_is_global_authorization_claim'] is False and cv['hde_approval_is_all_configuration_conformance_claim'] is False,'HDE coverage authority boundary changed')
    hr=p['human_review_contract'];req(hr['hde_approval_record_is_reasonable_assurance_effectiveness_evidence'] is False and hr['hde_approval_record_establishes_facility_irb_approval'] is False and hr['hde_approval_record_automatically_reopens_assessment'] is False,'HDE review authority changed')
    return {'programme_id':p['programme_id'],'query_stream_count':5,'integration_state':'AVAILABLE','network_requests_performed':False,'effectiveness_claim_created':False,'facility_irb_claim_created':False,'canonical_mutation_performed':False}
def main():print(json.dumps(validate_programme(load(P),load(R)),indent=2,sort_keys=True))
if __name__=='__main__':main()

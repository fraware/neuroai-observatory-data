import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_pma_discovery_programme import P,R,validate_programme
class T(unittest.TestCase):
 @classmethod
 def setUpClass(c):c.p=json.loads(P.read_text());c.r=json.loads(R.read_text())
 def test_current(c):x=validate_programme(c.p,c.r);c.assertEqual(x['integration_state'],'AVAILABLE');c.assertFalse(x['automatic_reopening'])
 def test_composite_identity(c):i=c.p['identity_policy'];c.assertEqual(i['record_identity'],'PMA_NUMBER_PLUS_SUPPLEMENT_NUMBER');c.assertFalse(i['same_pma_number_different_supplement_auto_merge'])
 def test_pathway_split(c):i=c.p['identity_policy'];c.assertEqual(i['admitted_pma_prefixes'],['P','BP','D']);c.assertTrue(i['h_prefix_hde_out_of_scope_for_v0_1']);c.assertTrue(i['n_prefix_legacy_nda_out_of_scope_for_v0_1'])
 def test_exact_decision_map(c):c.assertEqual(c.p['decision_semantics_policy']['exact_code_map']['APPR'],'APPROVAL_RECORDED');c.assertTrue(c.p['decision_semantics_policy']['approval_state_requires_exact_appr_code'])
 def test_dependency_regression_fails(c):
  p=copy.deepcopy(c.p);p['workbench_dependency']['integration_state']='PENDING_S1_MERGE'
  with c.assertRaisesRegex(ValueError,'AVAILABLE'):validate_programme(p,c.r)
 def test_supplement_rewrite_fails(c):
  p=copy.deepcopy(c.p);p['decision_semantics_policy']['supplement_approval_does_not_rewrite_original_application_record']=False
  with c.assertRaisesRegex(ValueError,'decision boundary'):validate_programme(p,c.r)
 def test_hde_candidate_emission_fails(c):
  p=copy.deepcopy(c.p);p['candidate_projection']['hde_records_emitted_as_pma_candidates']=True
  with c.assertRaisesRegex(ValueError,'candidate/pathway'):validate_programme(p,c.r)
 def test_auto_reopening_fails(c):
  p=copy.deepcopy(c.p);p['inclusion_policy']['automatic_reopening_decision']=True
  with c.assertRaisesRegex(ValueError,'automatic_reopening_decision'):validate_programme(p,c.r)
 def test_schema_available(c):s=json.loads(Path('schemas/openfda-pma-discovery-programme.schema.json').read_text());c.assertEqual(s['properties']['workbench_dependency']['properties']['integration_state']['const'],'AVAILABLE')
if __name__=='__main__':unittest.main()

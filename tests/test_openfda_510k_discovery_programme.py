import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_510k_discovery_programme import P,R,validate_programme
class T(unittest.TestCase):
 @classmethod
 def setUpClass(c):c.p=json.loads(P.read_text());c.r=json.loads(R.read_text())
 def test_current(c):x=validate_programme(c.p,c.r);c.assertEqual(x['integration_state'],'AVAILABLE');c.assertFalse(x['automatic_reopening'])
 def test_den_split(c):i=c.p['identity_policy'];c.assertTrue(i['den_prefix_is_de_novo_and_out_of_scope_for_v0_1']);c.assertEqual(i['admitted_prefixes'],['K','BK'])
 def test_decision_allowlist(c):c.assertEqual(c.p['decision_semantics_policy']['recognized_substantial_equivalence_codes'],['SEKD','SESD','SESE','SESK','SESP','SESU','SESR'])
 def test_record_presence_not_clearance(c):c.assertFalse(c.p['coverage_contract']['record_presence_is_clearance_claim']);c.assertFalse(c.p['human_review_contract']['record_presence_is_clearance_evidence'])
 def test_dependency_regression_fails(c):
  p=copy.deepcopy(c.p);p['workbench_dependency']['integration_state']='PENDING_S1_MERGE'
  with c.assertRaisesRegex(ValueError,'AVAILABLE'):validate_programme(p,c.r)
 def test_description_inference_fails(c):
  p=copy.deepcopy(c.p);p['decision_semantics_policy']['description_only_inference_allowed']=True
  with c.assertRaisesRegex(ValueError,'decision inference'):validate_programme(p,c.r)
 def test_den_candidate_emission_fails(c):
  p=copy.deepcopy(c.p);p['candidate_projection']['den_records_emitted_as_510k_candidates']=True
  with c.assertRaisesRegex(ValueError,'candidate/pathway'):validate_programme(p,c.r)
 def test_auto_reopening_fails(c):
  p=copy.deepcopy(c.p);p['inclusion_policy']['automatic_reopening_decision']=True
  with c.assertRaisesRegex(ValueError,'automatic_reopening_decision'):validate_programme(p,c.r)
 def test_schema_available(c):s=json.loads(Path('schemas/openfda-510k-discovery-programme.schema.json').read_text());c.assertEqual(s['properties']['workbench_dependency']['properties']['integration_state']['const'],'AVAILABLE')
if __name__=='__main__':unittest.main()

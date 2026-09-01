import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_hde_discovery_programme import P,R,validate_programme
class T(unittest.TestCase):
 @classmethod
 def setUpClass(c):c.p=json.loads(P.read_text());c.r=json.loads(R.read_text())
 def test_current(c):x=validate_programme(c.p,c.r);c.assertEqual(x['integration_state'],'AVAILABLE');c.assertFalse(x['effectiveness_claim_created']);c.assertFalse(x['facility_irb_claim_created'])
 def test_identity_and_h_constraint(c):i=c.p['identity_policy'];c.assertEqual(i['record_identity'],'HDE_NUMBER_PLUS_SUPPLEMENT_NUMBER');c.assertTrue(all('pma_number:H*' in q['search'] for q in c.p['query_streams']))
 def test_effectiveness_and_irb_separate(c):a=c.p['hde_authority_policy'];c.assertTrue(a['hde_approval_does_not_establish_reasonable_assurance_of_effectiveness']);c.assertTrue(a['hde_approval_does_not_establish_facility_irb_approval'])
 def test_dependency_regression_fails(c):
  p=copy.deepcopy(c.p);p['workbench_dependency']['integration_state']='PENDING_S1_MERGE'
  with c.assertRaisesRegex(ValueError,'AVAILABLE'):validate_programme(p,c.r)
 def test_effectiveness_escalation_fails(c):
  p=copy.deepcopy(c.p);p['candidate_projection']['effectiveness_claim_created_from_hde_approval']=True
  with c.assertRaisesRegex(ValueError,'candidate authority'):validate_programme(p,c.r)
 def test_irb_escalation_fails(c):
  p=copy.deepcopy(c.p);p['candidate_projection']['facility_irb_claim_created_from_hde_record']=True
  with c.assertRaisesRegex(ValueError,'candidate authority'):validate_programme(p,c.r)
 def test_auto_reopening_fails(c):
  p=copy.deepcopy(c.p);p['inclusion_policy']['automatic_reopening_decision']=True
  with c.assertRaisesRegex(ValueError,'automatic_reopening_decision'):validate_programme(p,c.r)
 def test_schema_available(c):s=json.loads(Path('schemas/openfda-hde-discovery-programme.schema.json').read_text());c.assertEqual(s['properties']['workbench_dependency']['properties']['integration_state']['const'],'AVAILABLE')
if __name__=='__main__':unittest.main()

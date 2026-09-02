import copy,json,unittest
from pathlib import Path
from scripts.validate_clinicaltrials_discovery_programme import P,BACKLOG,current_nct_index,validate_programme
class ClinicalTrialsProgrammeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.p=json.loads(P.read_text());cls.b=json.loads(BACKLOG.read_text())
 def test_current_programme(self):
  r=validate_programme(self.p,self.b);self.assertEqual(r['workbench_integration_state'],'AVAILABLE');self.assertEqual(r['materialized_source_count'],248);self.assertTrue(r['prima_anchor_resolved']);self.assertFalse(r['automatic_mutation_performed'])
 def test_current_nct_anchor(self):self.assertEqual(current_nct_index().get('NCT04676854'),'SRC-PR-002')
 def test_dependency_regression_fails(self):
  p=copy.deepcopy(self.p);p['workbench_dependency']['integration_state']='PENDING_S1_MERGE'
  with self.assertRaisesRegex(ValueError,'AVAILABLE'):validate_programme(p,self.b)
 def test_fuzzy_identity_fails(self):
  p=copy.deepcopy(self.p);p['identity_policy']['fuzzy_identity_merge_allowed']=True
  with self.assertRaisesRegex(ValueError,'Identity'):validate_programme(p,self.b)
 def test_interventional_filter_fails(self):
  p=copy.deepcopy(self.p);p['inclusion_policy']['required_study_types']=['OBSERVATIONAL']
  with self.assertRaisesRegex(ValueError,'Interventional'):validate_programme(p,self.b)
 def test_auto_source_admission_fails(self):
  p=copy.deepcopy(self.p);p['inclusion_policy']['automatic_source_admission']=True
  with self.assertRaisesRegex(ValueError,'automatic_source_admission'):validate_programme(p,self.b)
 def test_denominator_gate_fails(self):
  p=copy.deepcopy(self.p);p['coverage_contract']['mechanical_completion_requires']['reported_total_reconciliation_state']='PARTIAL_TRAVERSAL_NOT_RECONCILED'
  with self.assertRaisesRegex(ValueError,'Mechanical'):validate_programme(p,self.b)
 def test_query_term_drift_fails(self):
  p=copy.deepcopy(self.p);p['query_streams'][0]['query_term']='brain interface'
  with self.assertRaisesRegex(ValueError,'query term'):validate_programme(p,self.b)
 def test_hosted_success_without_steps_cannot_be_enabled(self):
  p=copy.deepcopy(self.p);p['network_policy']['hosted_success_claim_allowed_without_runner_steps']=True
  with self.assertRaisesRegex(ValueError,'Network'):validate_programme(p,self.b)
 def test_schema_requires_available(self):
  s=json.loads(Path('schemas/clinicaltrials-discovery-programme.schema.json').read_text());self.assertEqual(s['properties']['workbench_dependency']['properties']['integration_state']['const'],'AVAILABLE')
if __name__=='__main__':unittest.main()

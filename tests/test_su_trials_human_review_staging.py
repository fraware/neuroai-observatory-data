from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as stage
class FakeAPI:
 def __init__(self):self.query=None;self.calls=0
 def store_query(self,workspace,query):self.query=query;return query
 def execute_discovery_query(self,workspace,query_id,**kwargs):
  self.calls+=1;rows=kwargs['result_records'];props=[]
  for i,r in enumerate(rows):props.append({'proposal_id':f'DPROP-{i+1}','classification':'NEW','status':'PENDING_HUMAN_ACCEPTANCE','automatic_mutation_performed':False,'proposed_source':{'record_key':r['record_key']}})
  return {'run':{'run_id':'DRUN-TEST','query_id':query_id,'execution_mode':'OFFLINE_REPLAY','automatic_registry_mutation_performed':False,'result_counts':{'total':len(rows),'new':len(rows),'duplicate':0,'excluded':0}},'proposals':props}
def projection(root:Path,nct='NCT00000042'):
 idx=replay.build_known_nct_source_index();sd=idx['source_id_set_sha256'];candidate={'record_key':nct,'title':'Candidate trial','url':f'https://clinicaltrials.gov/study/{nct}','publisher':'ClinicalTrials.gov','source_class':'OFFICIAL_TRIAL_REGISTRY','suggested_source_id':f'SRC-CTGOV-{nct}','classification_hint':'NEW','duplicate_of_source_id':None,'query_ids':['DISCOVERY-CTGOV-BCI-001'],'normalized_aggregate_digest':'b'*64}
 result={'schema_version':'0.1.0','status':'NONCANONICAL_SU_TRIALS_RECORDED_REPLAY_PROJECTION','programme_id':'SU-TRIALS-CTGOV-v0.1','input_provenance':{'bundle_sha256':'c'*64,'captured_at':'2026-09-02T00:00:00Z','api_data_timestamp':'2026-09-02','controlled_source_id_set_sha256':sd,'known_nct_index_sha256':'d'*64,'raw_provider_pages_retained_in_output':False},'known_source_index_summary':{'materialized_source_count':248,'source_id_set_sha256':sd,'known_ctgov_nct_count':idx['known_ctgov_nct_count'],'global_completeness_claim':False},'query_reports':[],'normalized_studies':[],'known_duplicates':[],'new_candidate_inputs':[candidate],'reconciliation':{'scope':'FULL_PROGRAMME','configured_active_query_count':4,'executed_query_count':4,'all_active_queries_executed':True,'query_mechanical_blocker_count':0,'union_unique_nct_count':1,'known_controlled_duplicate_count':0,'new_candidate_input_count':1,'cross_query_repeat_membership_count':0,'materialized_source_namespace_count':248,'controlled_source_id_set_sha256':sd,'known_ctgov_nct_count_before_run':idx['known_ctgov_nct_count'],'raw_input_page_count':4,'raw_api_page_payloads_emitted':False,'participant_level_data_emitted':False,'automatic_source_admission':False,'automatic_trial_entity_creation':False,'automatic_trial_site_relationship_creation':False,'automatic_monitor_creation':False,'automatic_assessment_mutation':False,'human_adjudication_performed':False,'mechanically_complete':True,'global_neuroai_trial_recall_claim':False,'registry_completeness_claim':False,'canonical_successor_ready':False}}
 replay.write_projection(result,root);return idx
class StagingTests(unittest.TestCase):
 def test_stage_creates_pending_local_review_only(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   idx=projection(Path(pd));api=FakeAPI();r=stage.stage_projection(Path(pd),Path(wd),actor='reviewer',staged_at='2026-09-02T01:00:00Z',workbench_api=stage.WorkbenchAPI(api.store_query,api.execute_discovery_query));self.assertEqual(r['status'],'STAGED_FOR_HUMAN_ACCEPTANCE');self.assertEqual(r['candidate_count'],1);self.assertFalse(r['automatic_mutation_performed']);self.assertFalse(r['human_adjudication_performed']);self.assertFalse(r['canonical_successor_ready']);self.assertEqual(r['current_source_id_set_sha256'],idx['source_id_set_sha256']);data=json.loads(Path(r['review_index_path']).read_text());self.assertEqual(data['proposal_count'],1);self.assertFalse(data['automatic_mutation_performed']);self.assertEqual(data['workbench_run_id'],'DRUN-TEST')
 def test_stale_new_candidate_reclassification_fails(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   idx=projection(Path(pd));changed=dict(idx);changed['nct_to_source']=dict(idx['nct_to_source']);changed['nct_to_source']['NCT00000042']='SRC-NOW-CONTROLLED';changed['known_ctgov_nct_count']=len(changed['nct_to_source'])
   with patch.object(replay,'build_known_nct_source_index',return_value=changed):
    with self.assertRaisesRegex(ValueError,'STALE_PROJECTION_RECLASSIFICATION_REQUIRED'):stage.stage_projection(Path(pd),Path(wd),workbench_api=stage.WorkbenchAPI(FakeAPI().store_query,FakeAPI().execute_discovery_query))
 def test_source_namespace_drift_is_recorded_when_candidate_still_new(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   idx=projection(Path(pd));changed=dict(idx);changed['source_id_set_sha256']='e'*64
   api=FakeAPI()
   with patch.object(replay,'build_known_nct_source_index',return_value=changed):r=stage.stage_projection(Path(pd),Path(wd),workbench_api=stage.WorkbenchAPI(api.store_query,api.execute_discovery_query))
   self.assertTrue(r['source_namespace_changed_since_projection']);self.assertEqual(r['projection_source_id_set_sha256'],idx['source_id_set_sha256']);self.assertEqual(r['current_source_id_set_sha256'],'e'*64)
 def test_tampered_projection_file_fails(self):
  with tempfile.TemporaryDirectory() as pd:
   projection(Path(pd));p=Path(pd)/'new-candidate-inputs.jsonl';p.write_text(p.read_text()+'{}\n')
   with self.assertRaisesRegex(ValueError,'manifest verification failed'):stage.verify_projection(Path(pd))
 def test_noncomplete_projection_fails(self):
  with tempfile.TemporaryDirectory() as pd:
   projection(Path(pd));p=Path(pd)/'reconciliation.json';x=json.loads(p.read_text());x['mechanically_complete']=False;p.write_text(json.dumps(x)+'\n')
   # checksum fails first, which is the required fail-closed behavior
   with self.assertRaises(ValueError):stage.verify_projection(Path(pd))
if __name__=='__main__':unittest.main()

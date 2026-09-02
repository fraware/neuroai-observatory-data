from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import run_su_trials_recorded_replay as replay
def h(s:str)->str:return hashlib.sha256(s.encode()).hexdigest()
def known(extra=None):
 m={'NCT04676854':'SRC-PR-002'};m.update(extra or {})
 return {'materialized_source_count':248,'source_id_set_sha256':'a'*64,'known_ctgov_nct_count':len(m),'nct_to_source':m,'global_completeness_claim':False}
def norm(nct,title,kind='INTERVENTIONAL',extra=None):
 fields={k:h(f'{nct}|{k}') for k in replay.DIGEST_FIELDS};r={'record_kind':'NORMALIZED_CTGOV_STUDY','nct_id':nct,'brief_title':title,'overall_status':'RECRUITING','study_type':kind,'last_update_post_date':'2026-09-01','primary_completion_date':None,'enrollment_count':20,'phase':'NA','field_digests':fields,'aggregate_digest':h(nct+'|'+title),'boundary':'TEST'};r.update(extra or {});return r
def candidate(nct,title,dup=None):
 r={'record_key':nct,'title':title,'url':f'https://clinicaltrials.gov/study/{nct}','publisher':'ClinicalTrials.gov','source_class':'OFFICIAL_TRIAL_REGISTRY','suggested_source_id':f'SRC-CTGOV-{nct}','classification_hint':'DUPLICATE' if dup else 'NEW'}
 if dup:r['duplicate_of_source_id']=dup
 return r
def cov(q,term,total,known_count=0,new_count=None):
 if new_count is None:new_count=total-known_count
 return {'source_system':'CLINICALTRIALS_GOV','adapter_id':'clinicaltrials_gov','query_id':q,'query_text':term,'required_study_types':['INTERVENTIONAL'],'supplied_page_count':1,'raw_returned_record_count':total,'unique_nct_record_count_before_programme_filter':total,'included_candidate_count':total,'known_nct_duplicate_count':known_count,'known_nct_duplicates':[],'new_candidate_count':new_count,'excluded_by_study_type_count':0,'excluded_by_study_type':[],'duplicate_nct_representation_count':0,'reported_total_count_state':'CONSISTENT','reported_total_count':total,'reported_total_count_values':[total],'pagination_sequence_valid':True,'fully_paginated':True,'final_next_page_token_present':False,'reported_total_reconciliation_state':'MATCH','page_reports':[],'registry_completeness_claim':False,'neuroai_discovery_recall_claim':False,'automatic_registry_mutation_performed':False,'boundary':'TEST'}
def projection(q,term,rows):
 ns=[norm(n,t) for n,t,d in rows];rs=[candidate(n,t,d) for n,t,d in rows];kc=sum(d is not None for _,_,d in rows);return {'normalized_records':ns,'result_records':rs,'coverage':cov(q,term,len(rows),kc)}
def bundle(scope='FULL_PROGRAMME'):
 p=replay.programme();caps=[]
 for i,q in enumerate(p['query_streams']):caps.append({'query_id':q['query_id'],'query_term':q['query_term'],'count_total_first_page_requested':True,'count_total_later_pages_requested':False,'pages':[{'raw_contact':'MUST_NOT_EMIT','raw_location':'MUST_NOT_EMIT','slot':i}]})
 return {'schema_version':'0.1.0','programme_id':p['programme_id'],'capture_scope':scope,'captured_at':'2026-09-02T00:00:00Z','api_data_timestamp':'2026-09-02','query_captures':caps}
class ReplayTests(unittest.TestCase):
 def test_real_namespace_and_anchor(self):
  x=replay.build_known_nct_source_index();self.assertEqual(x['materialized_source_count'],248);self.assertEqual(x['nct_to_source'].get('NCT04676854'),'SRC-PR-002');self.assertEqual(len(x['source_id_set_sha256']),64)
 def test_full_programme_exact_union(self):
  b=bundle();p=replay.programme();shared='NCT00001001';outputs={}
  for q in p['query_streams']:
   qid=q['query_id'];term=q['query_term']
   if qid=='DISCOVERY-CTGOV-BCI-001':rows=[('NCT04676854','PRIMAvera','SRC-PR-002'),(shared,'Shared',None)]
   elif qid=='DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001':rows=[('NCT03333954','PRIMA feasibility',None),(shared,'Shared',None)]
   elif qid=='DISCOVERY-CTGOV-NEURAL-PROSTHESIS-001':rows=[('NCT00001002','Neural prosthesis',None)]
   else:rows=[('NCT00001003','Brain implant',None)]
   outputs[qid]=projection(qid,term,rows)
  r=replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:outputs[kw['query_id']],known_index=known());rec=r['reconciliation'];self.assertTrue(rec['mechanically_complete']);self.assertEqual(rec['known_controlled_duplicate_count'],1);self.assertEqual(rec['new_candidate_input_count'],4);self.assertEqual(rec['cross_query_repeat_membership_count'],1);self.assertEqual(rec['controlled_source_id_set_sha256'],'a'*64);self.assertFalse(rec['canonical_successor_ready'])
 def test_partial_never_complete(self):
  b=bundle('PARTIAL_VALIDATION');b['query_captures']=b['query_captures'][:1];q=replay.programme()['query_streams'][0];r=replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:projection(q['query_id'],q['query_term'],[('NCT04676854','Known','SRC-PR-002')]),known_index=known());self.assertFalse(r['reconciliation']['mechanically_complete'])
 def test_request_policy_mismatch_blocks_completion(self):
  b=bundle();b['query_captures'][0]['count_total_first_page_requested']=False;p=replay.programme();r=replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:projection(kw['query_id'],kw['query_text'],[]),known_index=known());self.assertGreater(r['reconciliation']['query_mechanical_blocker_count'],0);self.assertFalse(r['reconciliation']['mechanically_complete'])
 def test_classification_drift_fails(self):
  b=bundle('PARTIAL_VALIDATION');b['query_captures']=b['query_captures'][:1];q=replay.programme()['query_streams'][0];bad=projection(q['query_id'],q['query_term'],[('NCT04676854','Known',None)])
  with self.assertRaisesRegex(ValueError,'classification disagrees'):replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:bad,known_index=known())
 def test_unexpected_normalized_field_fails(self):
  b=bundle('PARTIAL_VALIDATION');b['query_captures']=b['query_captures'][:1];q=replay.programme()['query_streams'][0];bad=projection(q['query_id'],q['query_term'],[('NCT04676854','Known','SRC-PR-002')]);bad['normalized_records'][0]['contact']='MUST_NOT_EMIT'
  with self.assertRaisesRegex(ValueError,'Unexpected normalized'):replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:bad,known_index=known())
 def test_noninterventional_emitted_record_fails(self):
  b=bundle('PARTIAL_VALIDATION');b['query_captures']=b['query_captures'][:1];q=replay.programme()['query_streams'][0];bad=projection(q['query_id'],q['query_term'],[('NCT04676854','Known','SRC-PR-002')]);bad['normalized_records'][0]['study_type']='OBSERVATIONAL'
  with self.assertRaisesRegex(ValueError,'INTERVENTIONAL'):replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:bad,known_index=known())
 def test_cross_query_conflict_fails(self):
  b=bundle('PARTIAL_VALIDATION');b['query_captures']=b['query_captures'][:2];p=replay.programme();calls=[]
  for i,q in enumerate(p['query_streams'][:2]):calls.append(projection(q['query_id'],q['query_term'],[('NCT00001001','A' if i==0 else 'B',None)]))
  it=iter(calls)
  with self.assertRaisesRegex(ValueError,'Cross-query conflict'):replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:next(it),known_index=known())
 def test_raw_input_not_emitted_and_writer_deterministic(self):
  b=bundle('PARTIAL_VALIDATION');b['query_captures']=b['query_captures'][:1];q=replay.programme()['query_streams'][0];r=replay.build_replay(b,adapter=object(),projector=lambda _a,**kw:projection(q['query_id'],q['query_term'],[('NCT04676854','Known','SRC-PR-002')]),known_index=known());self.assertNotIn('MUST_NOT_EMIT',json.dumps(r))
  with tempfile.TemporaryDirectory() as td:
   out=Path(td);a=replay.write_projection(r,out);bb=replay.write_projection(r,out);self.assertEqual(a,bb);self.assertFalse((out/'raw-pages.json').exists())
if __name__=='__main__':unittest.main()

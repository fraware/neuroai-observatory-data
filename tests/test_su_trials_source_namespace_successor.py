from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import adjudicate_su_trials_source_namespace as adj
import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as stage
def study(nct,title):return {'protocolSection':{'identificationModule':{'nctId':nct,'briefTitle':title},'statusModule':{'overallStatus':'RECRUITING','lastUpdatePostDateStruct':{'date':'2026-09-02'}},'designModule':{'studyType':'INTERVENTIONAL','phases':['NA']}}}
def make_projection(path:Path):
 p=replay.programme();caps=[];ids=['NCT00000201','NCT00000202','NCT00000203','NCT00000204']
 for i,q in enumerate(p['query_streams']):caps.append({'query_id':q['query_id'],'query_term':q['query_term'],'count_total_first_page_requested':True,'count_total_later_pages_requested':False,'pages':[{'payload':{'studies':[study(ids[i],f'Candidate {i}')],'totalCount':1}}]})
 b={'schema_version':'0.1.0','programme_id':p['programme_id'],'capture_scope':'FULL_PROGRAMME','captured_at':'2026-09-02T00:00:00Z','api_data_timestamp':'2026-09-02','query_captures':caps};r=replay.build_replay(b);assert r['reconciliation']['mechanically_complete'];replay.write_projection(r,path)
def decision_packet(path:Path,review_path:Path,decisions_override=None):
 review=json.loads(review_path.read_text());review_sha=hashlib.sha256(review_path.read_bytes()).hexdigest();rows=[]
 for i,r in enumerate(review['proposals']):rows.append({'proposal_id':r['proposal_id'],'nct_id':r['nct_id'],'decision':'ACCEPT' if i==0 else 'REJECT','rationale':'Explicit test disposition'})
 if decisions_override is not None:rows=decisions_override
 packet={'schema_version':'0.1.0','artifact':'su_trials_human_decision_packet','status':'EXPLICIT_LOCAL_HUMAN_DECISION_PACKET','programme_id':'SU-TRIALS-CTGOV-v0.1','projection_manifest_sha256':review['projection_manifest_sha256'],'review_index_sha256':review_sha,'workbench_query_id':review['workbench_query_id'],'workbench_run_id':review['workbench_run_id'],'adjudicated_by':'test-reviewer','adjudicated_at':'2026-09-02T02:00:00Z','identity_boundary':'LOCAL_UNAUTHENTICATED_ATTRIBUTION','decisions':rows,'source_namespace_admission_only':True,'monitor_creation_authorized':False,'trial_entity_creation_authorized':False,'trial_site_relationship_creation_authorized':False,'assessment_mutation_authorized':False,'canonical_publication_authorized':False,'authority_boundary':'Synthetic explicit decisions for contract testing only.'};path.write_text(json.dumps(packet,indent=2,sort_keys=True)+'\n');return packet
class SuccessorTests(unittest.TestCase):
 def test_explicit_accept_creates_draft_source_namespace_only_and_is_resumable(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   pp=Path(pd);ww=Path(wd);make_projection(pp);staged=stage.stage_projection(pp,ww,actor='stager',staged_at='2026-09-02T01:00:00Z');rp=Path(staged['review_index_path']);dp=ww/'decisions.json';decision_packet(dp,rp);before=adj.registry_successor_files(ww);r=adj.adjudicate(pp,ww,rp,dp);self.assertEqual(r['accept_count'],1);self.assertFalse(r['monitor_creation_performed']);self.assertFalse(r['assessment_mutation_performed']);self.assertFalse(r['canonical_successor_ready']);self.assertEqual(adj.registry_successor_files(ww),before);sp=Path(r['source_namespace_successor_path']);s=json.loads(sp.read_text());self.assertEqual(s['status'],'DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR');self.assertEqual(s['base_source_namespace']['materialized_source_count'],248);self.assertEqual(len(s['base_source_namespace']['source_id_set_sha256']),64);self.assertEqual(s['accepted_sources'][0]['namespace_admission_state'],'PROPOSED_NOT_CANONICAL');self.assertFalse(s['source_namespace_publication_performed']);r2=adj.adjudicate(pp,ww,rp,dp);self.assertEqual(r2['source_namespace_successor_proposal_id'],r['source_namespace_successor_proposal_id']);self.assertEqual(adj.registry_successor_files(ww),before)
 def test_decision_packet_must_dispose_every_proposal(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   pp=Path(pd);ww=Path(wd);make_projection(pp);staged=stage.stage_projection(pp,ww);rp=Path(staged['review_index_path']);review=json.loads(rp.read_text());one=review['proposals'][0];dp=ww/'bad.json';decision_packet(dp,rp,[{'proposal_id':one['proposal_id'],'nct_id':one['nct_id'],'decision':'REJECT','rationale':'Only one'}])
   with self.assertRaisesRegex(ValueError,'dispose every'):adj.adjudicate(pp,ww,rp,dp)
 def test_packet_cannot_authorize_monitoring(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   pp=Path(pd);ww=Path(wd);make_projection(pp);staged=stage.stage_projection(pp,ww);rp=Path(staged['review_index_path']);dp=ww/'bad.json';packet=decision_packet(dp,rp);packet['monitor_creation_authorized']=True;dp.write_text(json.dumps(packet)+'\n')
   with self.assertRaisesRegex(ValueError,'authority boundary'):adj.adjudicate(pp,ww,rp,dp)
if __name__=='__main__':unittest.main()

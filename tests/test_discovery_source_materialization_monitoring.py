from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import adjudicate_su_trials_source_namespace as adj
import materialize_discovery_sources_monitoring as mat
import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as stage
def study(nct,title):return {'protocolSection':{'identificationModule':{'nctId':nct,'briefTitle':title},'statusModule':{'overallStatus':'RECRUITING','lastUpdatePostDateStruct':{'date':'2026-09-02'}},'designModule':{'studyType':'INTERVENTIONAL','phases':['NA']}}}
def build_successor(root:Path)->Path:
 pd=root/'projection';wd=root/'workspace';pd.mkdir();wd.mkdir();p=replay.programme();caps=[];ids=['NCT00000301','NCT00000302','NCT00000303','NCT00000304']
 for i,q in enumerate(p['query_streams']):caps.append({'query_id':q['query_id'],'query_term':q['query_term'],'count_total_first_page_requested':True,'count_total_later_pages_requested':False,'pages':[{'payload':{'studies':[study(ids[i],f'Candidate {i}')],'totalCount':1}}]})
 b={'schema_version':'0.1.0','programme_id':p['programme_id'],'capture_scope':'FULL_PROGRAMME','captured_at':'2026-09-02T00:00:00Z','api_data_timestamp':'2026-09-02','query_captures':caps};r=replay.build_replay(b);replay.write_projection(r,pd);st=stage.stage_projection(pd,wd,actor='stager',staged_at='2026-09-02T01:00:00Z');rp=Path(st['review_index_path']);review=json.loads(rp.read_text());rows=[]
 for i,x in enumerate(review['proposals']):rows.append({'proposal_id':x['proposal_id'],'nct_id':x['nct_id'],'decision':'ACCEPT' if i==0 else 'REJECT','rationale':'Explicit test disposition'})
 packet={'schema_version':'0.1.0','artifact':'su_trials_human_decision_packet','status':'EXPLICIT_LOCAL_HUMAN_DECISION_PACKET','programme_id':'SU-TRIALS-CTGOV-v0.1','projection_manifest_sha256':review['projection_manifest_sha256'],'review_index_sha256':hashlib.sha256(rp.read_bytes()).hexdigest(),'workbench_query_id':review['workbench_query_id'],'workbench_run_id':review['workbench_run_id'],'adjudicated_by':'reviewer','adjudicated_at':'2026-09-02T02:00:00Z','identity_boundary':'LOCAL_UNAUTHENTICATED_ATTRIBUTION','decisions':rows,'source_namespace_admission_only':True,'monitor_creation_authorized':False,'trial_entity_creation_authorized':False,'trial_site_relationship_creation_authorized':False,'assessment_mutation_authorized':False,'canonical_publication_authorized':False,'authority_boundary':'Synthetic explicit dispositions for contract testing.'};dp=wd/'decisions.json';dp.write_text(json.dumps(packet)+'\n');out=adj.adjudicate(pd,wd,rp,dp);return Path(out['source_namespace_successor_path'])
class MaterializationTests(unittest.TestCase):
 def test_materialization_remains_noncanonical_and_monitor_review_separate(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);sp=build_successor(root);r=mat.materialize(sp);self.assertEqual(r['status'],'NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION');self.assertEqual(len(r['sources']),1);s=r['sources'][0];self.assertEqual(s['record_state'],'NONCANONICAL_DISCOVERY_ADMITTED_CANDIDATE');self.assertEqual(s['source_origin'],'DISCOVERY_HUMAN_ACCEPTED_SOURCE_NAMESPACE_PROPOSAL');self.assertEqual(len(s['discovery_provenance']['projection_source_id_set_sha256']),64);self.assertEqual(len(s['discovery_provenance']['staging_source_id_set_sha256']),64);self.assertEqual(len(s['discovery_provenance']['adjudication_base_source_id_set_sha256']),64);m=r['monitoring'];self.assertEqual(m['status'],'NONCANONICAL_PENDING_MONITOR_REVIEW');self.assertEqual(m['proposals'][0]['recommended_mode'],'RECURRING');self.assertEqual(m['proposals'][0]['recommended_cadence'],'MONTHLY');self.assertEqual(m['proposals'][0]['priority'],'HIGH');self.assertFalse(m['proposals'][0]['monitor_present']);self.assertFalse(m['monitor_creation_performed']);self.assertFalse(r['reconciliation']['source_namespace_publication_performed']);self.assertFalse(r['reconciliation']['canonical_successor_ready'])
 def test_base_drift_requires_rebase(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);sp=build_successor(root);current=adj.current_namespace();changed=dict(current);changed['source_id_set_sha256']='f'*64
   with patch.object(adj,'current_namespace',return_value=changed):
    with self.assertRaisesRegex(ValueError,'SOURCE_NAMESPACE_BASE_DRIFT_REBASE_REQUIRED'):mat.materialize(sp)
 def test_writer_is_idempotent_and_refuses_collision(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);sp=build_successor(root);r=mat.materialize(sp);out=root/'out';a=mat.write_projection(r,out);b=mat.write_projection(r,out);self.assertEqual(a,b);self.assertFalse(a['monitor_creation_performed']);p=out/'reconciliation.json';p.write_text('{}\n')
   with self.assertRaisesRegex(ValueError,'OUTPUT_COLLISION_REFUSED'):mat.write_projection(r,out)
if __name__=='__main__':unittest.main()

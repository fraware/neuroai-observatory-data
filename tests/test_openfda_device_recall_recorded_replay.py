from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import run_su_regulation_openfda_device_recalls_recorded_replay as replay
SOURCE_DIGEST='a'*64

def _capture(stream,*,leaf=None,partition=None):
    search=stream['search'];path=[]
    if partition:
        lo,hi=partition;path=[{'dimension':'EVENT_DATE_POSTED','lower_bound':lo,'upper_bound':hi}];search=f"({search})+AND+event_date_posted:[{lo}+TO+{hi}]"
    return {'query_id':stream['query_id'],'leaf_query_id':leaf or stream['query_id']+'-root','effective_search':search,'partition_path':path,'pages':[{'meta':{'results':{'total':1,'skip':0,'limit':1000}},'results':[{'cfres_id':'1'}]}]}
def _bundle(captures,scope='PARTIAL_VALIDATION'):
    p=replay._programme();return {'schema_version':'0.1.0','programme_id':p['programme_id'],'provider':p['provider_contract']['provider'],'capture_scope':scope,'captured_at':'2026-09-02T00:00:00Z','leaf_query_captures':captures}
def _known(mapping=None):
    mapping=mapping or {};return {'materialized_source_count':248,'source_id_set_sha256':SOURCE_DIGEST,'recall_typed_source_count':len(mapping),'known_cfres_id_count':len(mapping),'cfres_to_source':mapping,'cfres_lineage':{},'global_recall_completeness_claim':False}
def _projection(rid='1',digest=None,duplicate=None):
    digest=digest or hashlib.sha256(('recall-'+rid).encode()).hexdigest()
    n={'record_kind':'NORMALIZED_OPENFDA_DEVICE_RECALL','cfres_id':rid,'res_event_number':'E1','product_res_number':'P1','event_date_initiated':'20260801','event_date_created':'20260801','event_date_posted':'20260802','event_date_terminated':None,'recall_status':'Open','recalling_firm':'Fixture Firm','firm_fei_number':['1'],'reason_for_recall':'Fixture','root_cause_description':'Fixture','action':'Fixture','product_description':'neural interface','product_code':'ABC','k_numbers':['K123456'],'pma_numbers':[],'query_memberships':['fixture'],'boundary':'fixture','normalized_record_sha256':digest}
    r={'record_key':f'OPENFDA_RECALL:{rid}','title':'Fixture recall','url':f'https://api.fda.gov/device/recall.json?search=cfres_id:%22{rid}%22','publisher':'U.S. FDA','source_class':'OFFICIAL_RECALL_OR_POSTMARKET_RECORD','suggested_source_id':f'SRC-OPENFDA-RECALL-{rid}','classification_hint':'DUPLICATE' if duplicate else 'NEW'}
    if duplicate:r['duplicate_of_source_id']=duplicate
    c={'supplied_page_count':1,'returned_record_count':1,'unique_cfres_id_count':1,'reported_total_count':1,'reported_total_count_state':'CONSISTENT','skip_sequence_valid':True,'skip_coverage_state':'MATCH','over_26000_limit':False,'search_after_or_partition_required':False,'known_controlled_duplicate_count':1 if duplicate else 0,'new_candidate_count':0 if duplicate else 1,'duplicate_representation_count':0,'unresolved_cfres_id_count':0,'address_or_contact_fields_projected':False,'code_info_lot_serial_text_projected':False,'distribution_pattern_projected':False}
    return {'result_records':[r],'normalized_records':[n],'coverage':c}

class RecallReplayTests(unittest.TestCase):
    def test_real_namespace_binds_248_and_digest(self):
        i=replay.build_known_cfres_source_index();self.assertEqual(i['materialized_source_count'],248);self.assertRegex(i['source_id_set_sha256'],r'^[0-9a-f]{64}$')
    def test_partial_noncanonical_and_no_auto_reopening(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known());q=r['reconciliation'];self.assertFalse(q['mechanically_complete']);self.assertFalse(q['automatic_reopening_decision']);self.assertFalse(q['recall_status_is_complete_lifecycle_tracker']);self.assertFalse(q['canonical_successor_ready'])
    def test_exact_duplicate_preserved(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection('77',duplicate='SRC-77'),known_index=_known({'77':'SRC-77'}));self.assertEqual(r['known_duplicates'][0]['duplicate_of_source_id'],'SRC-77')
    def test_cross_leaf_conflict_fails_closed(self):
        ss=replay._programme()['query_streams'][:2];calls=iter([_projection('1','a'*64),_projection('1','b'*64)])
        with self.assertRaisesRegex(ValueError,'Cross-leaf conflict'):replay.build_replay(_bundle([_capture(ss[0],leaf='a'),_capture(ss[1],leaf='b')]),projector=lambda **_:next(calls),known_index=_known())
    def test_partition_is_exact_and_never_completes(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s,partition=('20260101','20260902'))]),projector=lambda **_:_projection(),known_index=_known());self.assertTrue(r['reconciliation']['partition_reconciliation_required']);self.assertFalse(r['reconciliation']['mechanically_complete'])
    def test_invalid_calendar_date_fails_closed(self):
        s=replay._programme()['query_streams'][0]
        with self.assertRaisesRegex(ValueError,'valid YYYYMMDD'):replay.build_replay(_bundle([_capture(s,partition=('20260230','20260902'))]),projector=lambda **_:_projection(),known_index=_known())
    def test_unexpected_normalized_field_fails_closed(self):
        s=replay._programme()['query_streams'][0];bad=_projection();bad['normalized_records'][0]['address_1']='MUST-NOT-PROJECT'
        with self.assertRaisesRegex(ValueError,'prohibited/unexpected fields'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_full_clean_unpartitioned_programme_can_complete_mechanically_only(self):
        ss=replay._programme()['query_streams'];ids={s['query_id']:str(i+1) for i,s in enumerate(ss)};r=replay.build_replay(_bundle([_capture(s,leaf=f'l{i}') for i,s in enumerate(ss)],'FULL_PROGRAMME'),projector=lambda *,query_id,**_:_projection(ids[query_id]),known_index=_known());self.assertTrue(r['reconciliation']['mechanically_complete']);self.assertFalse(r['reconciliation']['global_neuroai_device_recall_claim']);self.assertFalse(r['reconciliation']['canonical_successor_ready'])
    def test_writer_deterministic_and_minimized(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);a=replay.write_projection(r,out);b={p.name:p.read_bytes() for p in out.iterdir()};c=replay.write_projection(r,out);d={p.name:p.read_bytes() for p in out.iterdir()};self.assertEqual(a,c);self.assertEqual(b,d);m=json.loads((out/'manifest.json').read_text());self.assertFalse(m['raw_openfda_pages_emitted']);self.assertFalse(m['address_or_contact_fields_emitted']);self.assertFalse(m['code_info_lot_serial_text_emitted']);self.assertFalse(m['distribution_pattern_emitted'])
if __name__=='__main__':unittest.main()

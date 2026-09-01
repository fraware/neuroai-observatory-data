from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import run_su_regulation_openfda_510k_recorded_replay as replay
SOURCE_DIGEST='a'*64

def _known(mapping=None):
    mapping=mapping or {};return {'materialized_source_count':248,'source_id_set_sha256':SOURCE_DIGEST,'regulatory_typed_source_count':len(mapping),'known_k_number_count':len(mapping),'k_to_source':mapping,'k_lineage':{},'global_510k_completeness_claim':False}
def _coverage(total=1,den=0,unresolved=0,duplicate=0):
    return {'supplied_page_count':1,'returned_record_count':total,'unique_k_number_count':max(0,total-den-unresolved),'reported_total_count':total,'reported_total_count_state':'CONSISTENT','skip_sequence_valid':True,'skip_coverage_state':'MATCH','over_26000_limit':False,'search_after_or_partition_required':False,'out_of_scope_den_count':den,'known_controlled_duplicate_count':duplicate,'new_candidate_count':max(0,total-den-unresolved-duplicate),'duplicate_representation_count':0,'unresolved_k_number_count':unresolved,'decision_semantics_derived_only_from_exact_decision_code':True,'record_presence_is_clearance_claim':False}
def _projection(k='K123456',code='SEKD',digest=None,duplicate=None):
    recognized=code in {'SEKD','SESD','SESE','SESK','SESP','SESU','SESR'};sem='SUBSTANTIALLY_EQUIVALENT_RECORDED' if recognized else 'UNRESOLVED_DECISION_CODE';digest=digest or hashlib.sha256((k+code).encode()).hexdigest()
    n={'record_kind':'NORMALIZED_OPENFDA_510K_SUBMISSION_DECISION','k_number':k,'device_name':'Fixture','applicant':'Fixture Applicant','date_received':'20260701','decision_date':'20260801','decision_code':code,'decision_description':'Fixture','clearance_type':None,'product_code':'ABC','statement_or_summary':None,'expedited_review_flag':None,'third_party_flag':None,'decision_semantics':sem,'decision_supports_substantial_equivalence':recognized,'decision_code_recognized':recognized,'query_memberships':['fixture'],'boundary':'fixture','normalized_record_sha256':digest}
    r={'record_key':f'OPENFDA_510K:{k}','title':'Fixture','url':'u','publisher':'U.S. FDA','source_class':'OFFICIAL_REGULATORY_RECORD','suggested_source_id':f'SRC-{k}','classification_hint':'DUPLICATE' if duplicate else 'NEW','decision_semantics':sem}
    if duplicate:r['duplicate_of_source_id']=duplicate
    c=_coverage(duplicate=1 if duplicate else 0);return {'result_records':[r],'normalized_records':[n],'coverage':c}
def _capture(stream,leaf='L1',partition=None):
    search=stream['search'];path=[]
    if partition:
        lo,hi=partition;path=[{'dimension':'DECISION_DATE','lower_bound':lo,'upper_bound':hi}];search=f"({search})+AND+decision_date:[{lo}+TO+{hi}]"
    return {'query_id':stream['query_id'],'leaf_query_id':leaf,'effective_search':search,'partition_path':path,'pages':[{'meta':{'results':{'total':1,'skip':0,'limit':1000}},'results':[]}]}
def _bundle(captures,scope='PARTIAL_VALIDATION'):
    p=replay._programme();return {'schema_version':'0.1.0','programme_id':p['programme_id'],'provider':p['provider_contract']['provider'],'capture_scope':scope,'captured_at':'2026-09-02T00:00:00Z','leaf_query_captures':captures}

class ReplayTests(unittest.TestCase):
    def test_real_namespace_binds_248_and_digest(self):
        i=replay.build_known_k_source_index();self.assertEqual(i['materialized_source_count'],248);self.assertRegex(i['source_id_set_sha256'],r'^[0-9a-f]{64}$')
    def test_partial_noncanonical_and_record_presence_not_clearance(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known());q=r['reconciliation'];self.assertFalse(q['mechanically_complete']);self.assertFalse(q['record_presence_is_clearance_claim']);self.assertFalse(q['canonical_successor_ready'])
    def test_exact_duplicate_preserved(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(duplicate='SRC-K'),known_index=_known({'K123456':'SRC-K'}));self.assertEqual(r['known_duplicates'][0]['duplicate_of_source_id'],'SRC-K')
    def test_den_accounted_but_never_enters_union(self):
        s=replay._programme()['query_streams'][0];proj={'result_records':[],'normalized_records':[],'coverage':_coverage(total=1,den=1)};r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:proj,known_index=_known());self.assertEqual(r['reconciliation']['out_of_scope_den_count'],1);self.assertEqual(r['reconciliation']['union_unique_k_number_count'],0)
    def test_den_normalized_identity_fails_closed(self):
        s=replay._programme()['query_streams'][0];bad=_projection(k='DEN123456')
        with self.assertRaisesRegex(ValueError,'exact K/BK'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_decision_semantics_are_recomputed_from_exact_code(self):
        s=replay._programme()['query_streams'][0];bad=_projection(code='XX');bad['normalized_records'][0]['decision_semantics']='SUBSTANTIALLY_EQUIVALENT_RECORDED';bad['normalized_records'][0]['decision_supports_substantial_equivalence']=True;bad['normalized_records'][0]['decision_code_recognized']=True;bad['result_records'][0]['decision_semantics']='SUBSTANTIALLY_EQUIVALENT_RECORDED'
        with self.assertRaisesRegex(ValueError,'decision semantics do not match'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_candidate_semantics_must_match_normalized(self):
        s=replay._programme()['query_streams'][0];bad=_projection();bad['result_records'][0]['decision_semantics']='UNRESOLVED_DECISION_CODE'
        with self.assertRaisesRegex(ValueError,'candidate decision semantics conflict'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_unexpected_normalized_field_fails_closed(self):
        s=replay._programme()['query_streams'][0];bad=_projection();bad['normalized_records'][0]['openfda']={'manufacturer_name':['MUST-NOT-PROJECT']}
        with self.assertRaisesRegex(ValueError,'prohibited/unexpected fields'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_partition_exact_calendar_and_never_complete(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s,partition=('20260101','20260902'))]),projector=lambda **_:_projection(),known_index=_known());self.assertTrue(r['reconciliation']['partition_reconciliation_required']);self.assertFalse(r['reconciliation']['mechanically_complete'])
        with self.assertRaisesRegex(ValueError,'valid YYYYMMDD'):replay.build_replay(_bundle([_capture(s,partition=('20260230','20260902'))]),projector=lambda **_:_projection(),known_index=_known())
    def test_cross_leaf_semantics_or_content_conflict_fails(self):
        ss=replay._programme()['query_streams'][:2];calls=iter([_projection(digest='a'*64),_projection(digest='b'*64)])
        with self.assertRaisesRegex(ValueError,'Cross-leaf conflict'):replay.build_replay(_bundle([_capture(ss[0],'a'),_capture(ss[1],'b')]),projector=lambda **_:next(calls),known_index=_known())
    def test_full_clean_programme_can_only_be_mechanically_complete(self):
        ss=replay._programme()['query_streams'];ids={s['query_id']:f'K{i+100000}' for i,s in enumerate(ss)};r=replay.build_replay(_bundle([_capture(s,f'L{i}') for i,s in enumerate(ss)],'FULL_PROGRAMME'),projector=lambda *,query_id,**_:_projection(k=ids[query_id]),known_index=_known());q=r['reconciliation'];self.assertTrue(q['mechanically_complete']);self.assertFalse(q['automatic_global_authorization_claim_creation']);self.assertFalse(q['automatic_safety_effectiveness_claim_creation']);self.assertFalse(q['canonical_successor_ready'])
    def test_writer_deterministic_and_noncanonical(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);a=replay.write_projection(r,out);before={p.name:p.read_bytes() for p in out.iterdir()};b=replay.write_projection(r,out);after={p.name:p.read_bytes() for p in out.iterdir()};self.assertEqual(a,b);self.assertEqual(before,after);m=json.loads((out/'manifest.json').read_text());self.assertFalse(m['raw_openfda_pages_emitted']);self.assertFalse(m['den_records_emitted_as_510k_candidates']);self.assertFalse(m['record_presence_is_clearance_claim'])
if __name__=='__main__':unittest.main()

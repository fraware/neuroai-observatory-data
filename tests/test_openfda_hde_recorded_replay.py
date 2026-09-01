from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import run_su_regulation_openfda_hde_recorded_replay as replay
SOURCE_DIGEST='a'*64
DEC={'APPR':'HDE_APPROVAL_RECORDED','WTDR':'WITHDRAWAL_RECORDED','DENY':'DENIAL_RECORDED','LE30':'THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED','APRL':'RECLASSIFICATION_AFTER_APPROVAL_RECORDED','APWD':'WITHDRAWAL_AFTER_APPROVAL_RECORDED','GT30':'NO_DECISION_WITHIN_30_DAYS_RECORDED','APCV':'CONVERSION_AFTER_APPROVAL_RECORDED'}
def _known(mapping=None):
    mapping=mapping or {};return {'materialized_source_count':248,'source_id_set_sha256':SOURCE_DIGEST,'regulatory_typed_source_count':len(mapping),'known_composite_hde_record_count':len(mapping),'record_to_source':mapping,'record_lineage':{},'global_hde_completeness_claim':False}
def _coverage(total=1,non_h=0,unresolved=0,duplicate=0):
    return {'supplied_page_count':1,'returned_record_count':total,'unique_composite_record_count':max(0,total-non_h-unresolved),'reported_total_count':total,'reported_total_count_state':'CONSISTENT','skip_sequence_valid':True,'skip_coverage_state':'MATCH','over_26000_limit':False,'search_after_or_partition_required':False,'out_of_scope_non_h_prefix_count':non_h,'known_controlled_duplicate_count':duplicate,'new_candidate_count':max(0,total-non_h-unresolved-duplicate),'duplicate_representation_count':0,'unresolved_hde_number_count':unresolved,'decision_semantics_derived_only_from_exact_decision_code':True,'record_presence_is_hde_approval_claim':False,'hde_approval_is_reasonable_assurance_effectiveness_claim':False,'hde_approval_establishes_facility_irb_approval':False}
def _projection(h='H123456',supp='ORIGINAL',code='APPR',digest=None,duplicate=None):
    sem=DEC.get(code,'UNRESOLVED_DECISION_CODE');recognized=code in DEC;approval=code=='APPR';identity=f'HDE:{h}:{supp}';role='ORIGINAL_APPLICATION' if supp=='ORIGINAL' else 'SUPPLEMENT';digest=digest or hashlib.sha256((identity+code).encode()).hexdigest()
    n={'record_kind':'NORMALIZED_OPENFDA_HDE_DECISION','hde_number':h,'supplement_number':supp,'record_identity':identity,'record_role':role,'trade_name':'Fixture','generic_name':'neural device','applicant':'Fixture Applicant','date_received':'20260701','decision_date':'20260801','decision_code':code,'decision_semantics':sem,'decision_code_recognized':recognized,'decision_supports_hde_approval':approval,'decision_supports_reasonable_assurance_of_effectiveness':False,'decision_establishes_facility_irb_approval':False,'product_code':'ABC','supplement_type':None,'supplement_reason':None,'ao_statement':None,'query_memberships':['fixture'],'boundary':'fixture','normalized_record_sha256':digest}
    r={'record_key':identity,'title':'Fixture','url':'u','publisher':'U.S. FDA','source_class':'OFFICIAL_REGULATORY_HDE_RECORD','suggested_source_id':f'SRC-{h}-{supp}','classification_hint':'DUPLICATE' if duplicate else 'NEW','decision_semantics':sem}
    if duplicate:r['duplicate_of_source_id']=duplicate
    return {'result_records':[r],'normalized_records':[n],'coverage':_coverage(duplicate=1 if duplicate else 0)}
def _capture(stream,leaf='L1',partition=None):
    search=stream['search'];path=[]
    if partition:
        lo,hi=partition;path=[{'dimension':'DECISION_DATE','lower_bound':lo,'upper_bound':hi}];search=f"({search})+AND+decision_date:[{lo}+TO+{hi}]"
    return {'query_id':stream['query_id'],'leaf_query_id':leaf,'effective_search':search,'partition_path':path,'pages':[{'meta':{'results':{'total':1,'skip':0,'limit':1000}},'results':[]}]}
def _bundle(captures,scope='PARTIAL_VALIDATION'):
    p=replay._programme();return {'schema_version':'0.1.0','programme_id':p['programme_id'],'provider':p['provider_contract']['provider'],'capture_scope':scope,'captured_at':'2026-09-02T00:00:00Z','leaf_query_captures':captures}
class ReplayTests(unittest.TestCase):
    def test_real_namespace_binds_248_and_digest(self):
        i=replay.build_known_record_source_index();self.assertEqual(i['materialized_source_count'],248);self.assertRegex(i['source_id_set_sha256'],r'^[0-9a-f]{64}$')
    def test_partial_preserves_effectiveness_and_irb_nonclaims(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known());q=r['reconciliation'];self.assertFalse(q['mechanically_complete']);self.assertFalse(q['hde_approval_is_reasonable_assurance_effectiveness_claim']);self.assertFalse(q['hde_approval_establishes_facility_irb_approval']);self.assertFalse(q['canonical_successor_ready'])
    def test_original_and_supplement_distinct(self):
        ss=replay._programme()['query_streams'][:2];calls=iter([_projection('H123456','ORIGINAL','APPR'),_projection('H123456','S001','WTDR')]);r=replay.build_replay(_bundle([_capture(ss[0],'a'),_capture(ss[1],'b')]),projector=lambda **_:next(calls),known_index=_known());self.assertEqual(r['reconciliation']['union_unique_composite_record_count'],2)
    def test_exact_duplicate_preserved(self):
        s=replay._programme()['query_streams'][0];identity='HDE:H123456:S001';r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection('H123456','S001','APPR',duplicate='SRC-HDE'),known_index=_known({identity:'SRC-HDE'}));self.assertEqual(r['known_duplicates'][0]['duplicate_of_source_id'],'SRC-HDE')
    def test_non_h_accounted_not_materialized(self):
        s=replay._programme()['query_streams'][0];proj={'result_records':[],'normalized_records':[],'coverage':_coverage(total=1,non_h=1)};r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:proj,known_index=_known());self.assertEqual(r['reconciliation']['out_of_scope_non_h_prefix_count'],1);self.assertEqual(r['reconciliation']['union_unique_composite_record_count'],0)
    def test_identity_and_role_recomputed(self):
        s=replay._programme()['query_streams'][0];bad=_projection('H123456','S001');bad['normalized_records'][0]['record_identity']='HDE:H123456:ORIGINAL'
        with self.assertRaisesRegex(ValueError,'record_identity mismatch'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_effectiveness_or_irb_escalation_fails_closed(self):
        s=replay._programme()['query_streams'][0];bad=_projection();bad['normalized_records'][0]['decision_supports_reasonable_assurance_of_effectiveness']=True
        with self.assertRaisesRegex(ValueError,'decision/authority semantics'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
        bad=_projection();bad['normalized_records'][0]['decision_establishes_facility_irb_approval']=True
        with self.assertRaisesRegex(ValueError,'decision/authority semantics'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_unknown_code_cannot_be_approval(self):
        s=replay._programme()['query_streams'][0];bad=_projection(code='XX');bad['normalized_records'][0]['decision_semantics']='HDE_APPROVAL_RECORDED';bad['normalized_records'][0]['decision_supports_hde_approval']=True;bad['result_records'][0]['decision_semantics']='HDE_APPROVAL_RECORDED'
        with self.assertRaisesRegex(ValueError,'decision/authority semantics'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_unexpected_field_fails_closed(self):
        s=replay._programme()['query_streams'][0];bad=_projection();bad['normalized_records'][0]['openfda']={'manufacturer_name':['MUST-NOT-PROJECT']}
        with self.assertRaisesRegex(ValueError,'prohibited/unexpected fields'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_partition_calendar_valid_and_never_complete(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s,partition=('20260101','20260902'))]),projector=lambda **_:_projection(),known_index=_known());self.assertTrue(r['reconciliation']['partition_reconciliation_required']);self.assertFalse(r['reconciliation']['mechanically_complete'])
        with self.assertRaisesRegex(ValueError,'valid YYYYMMDD'):replay.build_replay(_bundle([_capture(s,partition=('20260230','20260902'))]),projector=lambda **_:_projection(),known_index=_known())
    def test_cross_leaf_conflict_fails(self):
        ss=replay._programme()['query_streams'][:2];calls=iter([_projection(digest='a'*64),_projection(digest='b'*64)])
        with self.assertRaisesRegex(ValueError,'Cross-leaf conflict'):replay.build_replay(_bundle([_capture(ss[0],'a'),_capture(ss[1],'b')]),projector=lambda **_:next(calls),known_index=_known())
    def test_full_clean_programme_only_mechanically_complete(self):
        ss=replay._programme()['query_streams'];ids={s['query_id']:f'H{i+100000}' for i,s in enumerate(ss)};r=replay.build_replay(_bundle([_capture(s,f'L{i}') for i,s in enumerate(ss)],'FULL_PROGRAMME'),projector=lambda *,query_id,**_:_projection(h=ids[query_id]),known_index=_known());q=r['reconciliation'];self.assertTrue(q['mechanically_complete']);self.assertFalse(q['automatic_effectiveness_claim_creation']);self.assertFalse(q['automatic_facility_irb_authorization_claim_creation']);self.assertFalse(q['canonical_successor_ready'])
    def test_writer_deterministic(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);a=replay.write_projection(r,out);before={p.name:p.read_bytes() for p in out.iterdir()};b=replay.write_projection(r,out);after={p.name:p.read_bytes() for p in out.iterdir()};self.assertEqual(a,b);self.assertEqual(before,after);m=json.loads((out/'manifest.json').read_text());self.assertFalse(m['hde_approval_is_reasonable_assurance_effectiveness_claim']);self.assertFalse(m['hde_approval_establishes_facility_irb_approval'])
if __name__=='__main__':unittest.main()

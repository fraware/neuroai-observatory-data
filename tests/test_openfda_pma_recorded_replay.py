from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import run_su_regulation_openfda_pma_recorded_replay as replay
SOURCE_DIGEST='a'*64
DEC={'APPR':'APPROVAL_RECORDED','WTDR':'WITHDRAWAL_RECORDED','DENY':'DENIAL_RECORDED','LE30':'THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED','APRL':'RECLASSIFICATION_AFTER_APPROVAL_RECORDED','APWD':'WITHDRAWAL_AFTER_APPROVAL_RECORDED','GT30':'NO_DECISION_WITHIN_30_DAYS_RECORDED','APCV':'CONVERSION_AFTER_APPROVAL_RECORDED'}

def _known(mapping=None):
    mapping=mapping or {};return {'materialized_source_count':248,'source_id_set_sha256':SOURCE_DIGEST,'regulatory_typed_source_count':len(mapping),'known_composite_pma_record_count':len(mapping),'record_to_source':mapping,'record_lineage':{},'global_pma_completeness_claim':False}
def _coverage(total=1,hde=0,nda=0,unresolved=0,duplicate=0):
    return {'supplied_page_count':1,'returned_record_count':total,'unique_composite_record_count':max(0,total-hde-nda-unresolved),'reported_total_count':total,'reported_total_count_state':'CONSISTENT','skip_sequence_valid':True,'skip_coverage_state':'MATCH','over_26000_limit':False,'search_after_or_partition_required':False,'out_of_scope_hde_count':hde,'out_of_scope_legacy_nda_count':nda,'known_controlled_duplicate_count':duplicate,'new_candidate_count':max(0,total-hde-nda-unresolved-duplicate),'duplicate_representation_count':0,'unresolved_pma_number_count':unresolved,'decision_semantics_derived_only_from_exact_decision_code':True,'record_presence_is_approval_claim':False}
def _projection(pma='P123456',supp='ORIGINAL',code='APPR',digest=None,duplicate=None):
    sem=DEC.get(code,'UNRESOLVED_DECISION_CODE');recognized=code in DEC;approval=code=='APPR';identity=f'PMA:{pma}:{supp}';digest=digest or hashlib.sha256((identity+code).encode()).hexdigest();role='ORIGINAL_APPLICATION' if supp=='ORIGINAL' else 'SUPPLEMENT'
    n={'record_kind':'NORMALIZED_OPENFDA_PMA_DECISION','pma_number':pma,'supplement_number':supp,'record_identity':identity,'record_role':role,'trade_name':'Fixture','generic_name':'neural device','applicant':'Fixture Applicant','date_received':'20260701','decision_date':'20260801','decision_code':code,'decision_semantics':sem,'decision_code_recognized':recognized,'decision_supports_approval':approval,'product_code':'ABC','supplement_type':None,'supplement_reason':None,'ao_statement':None,'expedited_review_flag':None,'query_memberships':['fixture'],'boundary':'fixture','normalized_record_sha256':digest}
    r={'record_key':identity,'title':'Fixture','url':'u','publisher':'U.S. FDA','source_class':'OFFICIAL_REGULATORY_RECORD','suggested_source_id':f'SRC-{pma}-{supp}','classification_hint':'DUPLICATE' if duplicate else 'NEW','decision_semantics':sem}
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
    def test_partial_is_noncanonical_and_record_presence_not_approval(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known());q=r['reconciliation'];self.assertFalse(q['mechanically_complete']);self.assertFalse(q['record_presence_is_approval_claim']);self.assertFalse(q['canonical_successor_ready'])
    def test_original_and_supplement_are_distinct(self):
        ss=replay._programme()['query_streams'][:2];calls=iter([_projection('P123456','ORIGINAL','APPR'),_projection('P123456','S001','WTDR')]);r=replay.build_replay(_bundle([_capture(ss[0],'a'),_capture(ss[1],'b')]),projector=lambda **_:next(calls),known_index=_known());self.assertEqual(r['reconciliation']['union_unique_composite_record_count'],2);states={x['record_identity']:x['decision_semantics'] for x in r['normalized_pma_records']};self.assertEqual(states['PMA:P123456:ORIGINAL'],'APPROVAL_RECORDED');self.assertEqual(states['PMA:P123456:S001'],'WITHDRAWAL_RECORDED')
    def test_exact_composite_duplicate_preserved(self):
        s=replay._programme()['query_streams'][0];identity='PMA:P123456:S001';r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection('P123456','S001','APPR',duplicate='SRC-PMA'),known_index=_known({identity:'SRC-PMA'}));self.assertEqual(r['known_duplicates'][0]['duplicate_of_source_id'],'SRC-PMA')
    def test_hde_and_nda_are_accounted_but_not_materialized(self):
        s=replay._programme()['query_streams'][0];proj={'result_records':[],'normalized_records':[],'coverage':_coverage(total=2,hde=1,nda=1)};r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:proj,known_index=_known());self.assertEqual(r['reconciliation']['out_of_scope_hde_count'],1);self.assertEqual(r['reconciliation']['out_of_scope_legacy_nda_count'],1);self.assertEqual(r['reconciliation']['union_unique_composite_record_count'],0)
    def test_composite_identity_and_role_are_recomputed(self):
        s=replay._programme()['query_streams'][0];bad=_projection('P123456','S001');bad['normalized_records'][0]['record_identity']='PMA:P123456:ORIGINAL'
        with self.assertRaisesRegex(ValueError,'record_identity mismatch'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
        bad=_projection('P123456','S001');bad['normalized_records'][0]['record_role']='ORIGINAL_APPLICATION'
        with self.assertRaisesRegex(ValueError,'record_role'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_decision_semantics_recomputed_and_only_appr_supports_approval(self):
        s=replay._programme()['query_streams'][0];bad=_projection(code='WTDR');bad['normalized_records'][0]['decision_semantics']='APPROVAL_RECORDED';bad['normalized_records'][0]['decision_supports_approval']=True;bad['result_records'][0]['decision_semantics']='APPROVAL_RECORDED'
        with self.assertRaisesRegex(ValueError,'decision semantics do not match'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_unexpected_field_fails_closed(self):
        s=replay._programme()['query_streams'][0];bad=_projection();bad['normalized_records'][0]['openfda']={'manufacturer_name':['MUST-NOT-PROJECT']}
        with self.assertRaisesRegex(ValueError,'prohibited/unexpected fields'):replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:bad,known_index=_known())
    def test_partition_calendar_valid_and_never_completes(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s,partition=('20260101','20260902'))]),projector=lambda **_:_projection(),known_index=_known());self.assertTrue(r['reconciliation']['partition_reconciliation_required']);self.assertFalse(r['reconciliation']['mechanically_complete'])
        with self.assertRaisesRegex(ValueError,'valid YYYYMMDD'):replay.build_replay(_bundle([_capture(s,partition=('20260230','20260902'))]),projector=lambda **_:_projection(),known_index=_known())
    def test_cross_leaf_conflict_fails(self):
        ss=replay._programme()['query_streams'][:2];calls=iter([_projection(digest='a'*64),_projection(digest='b'*64)])
        with self.assertRaisesRegex(ValueError,'Cross-leaf conflict'):replay.build_replay(_bundle([_capture(ss[0],'a'),_capture(ss[1],'b')]),projector=lambda **_:next(calls),known_index=_known())
    def test_full_clean_programme_only_mechanically_complete(self):
        ss=replay._programme()['query_streams'];ids={s['query_id']:f'P{i+100000}' for i,s in enumerate(ss)};r=replay.build_replay(_bundle([_capture(s,f'L{i}') for i,s in enumerate(ss)],'FULL_PROGRAMME'),projector=lambda *,query_id,**_:_projection(pma=ids[query_id]),known_index=_known());q=r['reconciliation'];self.assertTrue(q['mechanically_complete']);self.assertFalse(q['automatic_global_authorization_claim_creation']);self.assertFalse(q['automatic_current_commercial_configuration_claim_creation']);self.assertFalse(q['canonical_successor_ready'])
    def test_writer_deterministic_and_noncanonical(self):
        s=replay._programme()['query_streams'][0];r=replay.build_replay(_bundle([_capture(s)]),projector=lambda **_:_projection(),known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);a=replay.write_projection(r,out);before={p.name:p.read_bytes() for p in out.iterdir()};b=replay.write_projection(r,out);after={p.name:p.read_bytes() for p in out.iterdir()};self.assertEqual(a,b);self.assertEqual(before,after);m=json.loads((out/'manifest.json').read_text());self.assertFalse(m['raw_openfda_pages_emitted']);self.assertFalse(m['hde_records_emitted_as_pma_candidates']);self.assertFalse(m['record_presence_is_approval_claim'])
if __name__=='__main__':unittest.main()

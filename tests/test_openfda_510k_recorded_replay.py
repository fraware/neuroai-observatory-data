from __future__ import annotations
import tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,"scripts")
import run_su_regulation_openfda_510k_recorded_replay as replay

def known(extra=None):return {"materialized_source_count":248,"regulatory_typed_source_count":0,"known_k_number_count":len(extra or {}),"k_to_source":extra or {},"global_510k_completeness_claim":False}
def cov(total=1,den=0,unresolved=0):return {"supplied_page_count":1,"returned_record_count":total,"unique_k_number_count":total-den-unresolved,"reported_total_count":total,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"search_after_or_partition_required":False,"out_of_scope_den_count":den,"known_controlled_duplicate_count":0,"new_candidate_count":total-den-unresolved,"duplicate_representation_count":0,"unresolved_k_number_count":unresolved,"decision_semantics_derived_only_from_exact_decision_code":True}
def projection(k="K123456",digest="a"*64,decision="SUBSTANTIALLY_EQUIVALENT_RECORDED",duplicate=None):
    n={"k_number":k,"normalized_record_sha256":digest,"decision_semantics":decision,"query_memberships":["Q"]};r={"record_key":f"OPENFDA_510K:{k}","title":"Device","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_REGULATORY_RECORD","suggested_source_id":f"SRC-{k}","classification_hint":"DUPLICATE" if duplicate else "NEW","decision_semantics":decision}
    if duplicate:r["duplicate_of_source_id"]=duplicate
    c=cov();c["known_controlled_duplicate_count"]=1 if duplicate else 0;c["new_candidate_count"]=0 if duplicate else 1
    return {"result_records":[r],"normalized_records":[n],"coverage":c}
def bundle(captures,scope="PARTIAL_VALIDATION"):
    p=replay._programme();return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":captures}
def cap(qid,search,leaf="L1",part=None):return {"query_id":qid,"leaf_query_id":leaf,"effective_search":search,"partition_path":part or [],"pages":[{"meta":{"results":{"total":1,"skip":0,"limit":1000}},"results":[]}]}

class ReplayTests(unittest.TestCase):
    def test_real_namespace_248(self):self.assertEqual(replay.build_known_k_source_index()["materialized_source_count"],248)
    def test_partial_noncanonical(self):
        p=replay._programme();q=p["query_streams"][0];r=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:projection(),known_index=known());self.assertFalse(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_exact_duplicate(self):
        p=replay._programme();q=p["query_streams"][0];r=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:projection(duplicate="SRC-K"),known_index=known({"K123456":"SRC-K"}));self.assertEqual(r["reconciliation"]["known_controlled_duplicate_count"],1);self.assertEqual(r["reconciliation"]["new_candidate_input_count"],0)
    def test_den_accounted_but_not_union(self):
        p=replay._programme();q=p["query_streams"][0];proj={"result_records":[],"normalized_records":[],"coverage":cov(total=1,den=1)};r=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:proj,known_index=known());self.assertEqual(r["reconciliation"]["out_of_scope_den_count"],1);self.assertEqual(r["reconciliation"]["union_unique_k_number_count"],0)
    def test_partition_never_complete(self):
        p=replay._programme();q=p["query_streams"][0];part=[{"dimension":"DECISION_DATE","lower_bound":"20260101","upper_bound":"20261231"}];s=f'({q["search"]})+AND+decision_date:[20260101+TO+20261231]';r=replay.build_replay(bundle([cap(q["query_id"],s,part=part)]),projector=lambda **_:projection(),known_index=known());self.assertTrue(r["reconciliation"]["partition_reconciliation_required"]);self.assertFalse(r["reconciliation"]["mechanically_complete"])
    def test_cross_query_semantics_conflict_fails(self):
        p=replay._programme();q1,q2=p["query_streams"][:2];calls=iter([projection(decision="SUBSTANTIALLY_EQUIVALENT_RECORDED"),projection(decision="UNRESOLVED_DECISION_CODE")])
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(bundle([cap(q1["query_id"],q1["search"],"L1"),cap(q2["query_id"],q2["search"],"L2")]),projector=lambda **_:next(calls),known_index=known())
    def test_full_programme_clean_mechanics_is_still_noncanonical(self):
        p=replay._programme();caps=[cap(q["query_id"],q["search"],f"L{i}") for i,q in enumerate(p["query_streams"])];empty={"result_records":[],"normalized_records":[],"coverage":cov(total=0)};r=replay.build_replay(bundle(caps,"FULL_PROGRAMME"),projector=lambda **_:empty,known_index=known());self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["automatic_global_authorization_claim_creation"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_writer_deterministic(self):
        p=replay._programme();q=p["query_streams"][0];result=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:projection(),known_index=known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);a=replay.write_projection(result,out);b=replay.write_projection(result,out);self.assertEqual(a,b)
if __name__=="__main__":unittest.main()

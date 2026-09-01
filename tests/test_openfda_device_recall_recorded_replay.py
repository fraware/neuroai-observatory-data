from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,"scripts")
import run_su_regulation_openfda_device_recalls_recorded_replay as replay

def projection(rid="R1",digest="a"*64,duplicate=None):
    n={"cfres_id":rid,"normalized_record_sha256":digest,"query_memberships":["Q"]}
    r={"record_key":f"OPENFDA_RECALL:{rid}","title":"Recall","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_RECALL_OR_POSTMARKET_RECORD","suggested_source_id":f"SRC-{rid}","classification_hint":"DUPLICATE" if duplicate else "NEW"}
    if duplicate:r["duplicate_of_source_id"]=duplicate
    return {"result_records":[r],"normalized_records":[n],"coverage":{"supplied_page_count":1,"returned_record_count":1,"unique_cfres_id_count":1,"reported_total_count":1,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"search_after_or_partition_required":False,"known_controlled_duplicate_count":1 if duplicate else 0,"new_candidate_count":0 if duplicate else 1,"duplicate_representation_count":0,"unresolved_cfres_id_count":0,"address_or_contact_fields_projected":False,"code_info_lot_serial_text_projected":False,"distribution_pattern_projected":False}}

def known(extra=None):
    return {"materialized_source_count":248,"recall_typed_source_count":0,"known_cfres_id_count":len(extra or {}),"cfres_to_source":extra or {},"global_recall_completeness_claim":False}

def bundle(captures,scope="PARTIAL_VALIDATION"):
    p=replay._programme(); return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":captures}

def cap(qid,search,leaf="L1",part=None): return {"query_id":qid,"leaf_query_id":leaf,"effective_search":search,"partition_path":part or [],"pages":[{"meta":{"results":{"total":1,"skip":0,"limit":1000}},"results":[]}]}

class RecallReplayTests(unittest.TestCase):
    def test_real_namespace_is_248(self): self.assertEqual(replay.build_known_cfres_source_index()["materialized_source_count"],248)
    def test_partial_replay_is_noncanonical(self):
        p=replay._programme(); q=p["query_streams"][0]; r=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:projection(),known_index=known())
        self.assertEqual(r["reconciliation"]["new_candidate_input_count"],1); self.assertFalse(r["reconciliation"]["mechanically_complete"]); self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_exact_known_duplicate_preserved(self):
        p=replay._programme(); q=p["query_streams"][0]; r=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:projection(duplicate="SRC-R1"),known_index=known({"R1":"SRC-R1"}))
        self.assertEqual(r["reconciliation"]["known_controlled_duplicate_count"],1); self.assertEqual(r["reconciliation"]["new_candidate_input_count"],0)
    def test_partitioned_leaf_never_implies_completion(self):
        p=replay._programme(); q=p["query_streams"][0]; part=[{"dimension":"EVENT_DATE_POSTED","lower_bound":"20260101","upper_bound":"20261231"}]; search=f'({q["search"]})+AND+event_date_posted:[20260101+TO+20261231]'
        r=replay.build_replay(bundle([cap(q["query_id"],search,part=part)]),projector=lambda **_:projection(),known_index=known())
        self.assertTrue(r["reconciliation"]["partition_reconciliation_required"]); self.assertFalse(r["reconciliation"]["mechanically_complete"])
    def test_cross_query_conflict_fails_closed(self):
        p=replay._programme(); q1,q2=p["query_streams"][:2]; calls=iter([projection(digest="a"*64),projection(digest="b"*64)])
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):
            replay.build_replay(bundle([cap(q1["query_id"],q1["search"],"L1"),cap(q2["query_id"],q2["search"],"L2")]),projector=lambda **_:next(calls),known_index=known())
    def test_full_programme_clean_mechanics_only(self):
        p=replay._programme(); captures=[cap(q["query_id"],q["search"],f"L{i}") for i,q in enumerate(p["query_streams"])]
        r=replay.build_replay(bundle(captures,"FULL_PROGRAMME"),projector=lambda **_: {"result_records":[],"normalized_records":[],"coverage":{"supplied_page_count":1,"returned_record_count":0,"unique_cfres_id_count":0,"reported_total_count":0,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"search_after_or_partition_required":False,"known_controlled_duplicate_count":0,"new_candidate_count":0,"duplicate_representation_count":0,"unresolved_cfres_id_count":0,"address_or_contact_fields_projected":False,"code_info_lot_serial_text_projected":False,"distribution_pattern_projected":False}},known_index=known())
        self.assertTrue(r["reconciliation"]["mechanically_complete"]); self.assertFalse(r["reconciliation"]["automatic_reopening_decision"]); self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_writer_is_deterministic_no_raw_pages(self):
        p=replay._programme(); q=p["query_streams"][0]; result=replay.build_replay(bundle([cap(q["query_id"],q["search"])]),projector=lambda **_:projection(),known_index=known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td); a=replay.write_projection(result,out); b=replay.write_projection(result,out); self.assertEqual(a,b); self.assertNotIn("raw", " ".join(a).lower())

if __name__=="__main__": unittest.main()

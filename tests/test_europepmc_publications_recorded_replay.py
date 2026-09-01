from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
import scripts.run_su_publications_europepmc_recorded_replay as replay

def _identity(query_id:str)->str:return "DOI:10.1234/"+hashlib.sha256(query_id.encode()).hexdigest()[:12]
def _coverage(query_id:str)->dict:
    return {"supplied_page_count":1,"raw_returned_record_count":1,"unique_resolved_identity_count":1,"reported_hit_count_state":"CONSISTENT","reported_hit_count":1,"cursor_sequence_valid":True,"terminal_cursor_state":"TERMINAL","reported_total_reconciliation_state":"MATCH","known_anchor_count":0,"known_controlled_source_duplicate_count":0,"new_candidate_count":1,"cross_query_duplicate_representation_count":0,"unresolved_identity_count":0,"preprint_count":0,"non_preprint_record_count":1,"publication_type_missing_count":0,"source_distribution":{"MED":1},"publication_database_completeness_claim":False,"query_recall_claim":False,"global_neuroai_publication_recall_claim":False,"automatic_source_admission_performed":False,"automatic_relationship_creation_performed":False,"automatic_assessment_mutation_performed":False,"query_id":query_id}
def _mock_projector(*,query_id,query_text,pages,known_publication_sources,known_anchor_identities):
    identity=_identity(query_id);doi=identity.removeprefix("DOI:");normalized={"resolved_identity":identity,"identity_type":"DOI","title":"Publication","publication_year":"2026","author_string":"A, B","journal_or_source":"Journal","publication_type":"Journal Article","doi":doi,"pmid":None,"pmcid":None,"source_plus_ext_id":"MED:1","is_preprint":False,"query_memberships":[query_id],"normalized_record_sha256":hashlib.sha256(identity.encode()).hexdigest()};duplicate=known_publication_sources.get(identity);record={"record_key":identity,"title":"Publication","url":"https://europepmc.org/article/MED/1","publisher":"Europe PMC","source_class":"OFFICIAL_BIBLIOGRAPHIC_METADATA","suggested_source_id":"SRC-CANDIDATE","classification_hint":"DUPLICATE" if duplicate else "NEW"}
    if duplicate:record["duplicate_of_source_id"]=duplicate
    coverage=_coverage(query_id);coverage["known_controlled_source_duplicate_count"]=1 if duplicate else 0;coverage["new_candidate_count"]=0 if duplicate else 1
    return {"result_records":[record],"normalized_records":[normalized],"coverage":coverage}
def _bundle(scope="PARTIAL_VALIDATION",count=1):
    p=replay._programme();provider=p["provider_contract"];streams=p["query_streams"][:count];request={"endpoint":provider["api_endpoint"],"format":provider["format"],"result_type":provider["result_type"],"page_size":provider["page_size"],"synonym_expansion":provider["synonym_expansion"],"first_cursor_mark":provider["first_cursor_mark"]}
    return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":"Europe PMC","capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","raw_input_contains_full_text":False,"participant_level_data_expected":False,"query_captures":[{"query_id":s["query_id"],"query_term":s["query_term"],"request":request,"pages":[{"hitCount":1,"resultList":{"result":[{}]}}]} for s in streams]}
def _known(mapping=None):return {"materialized_source_count":248,"source_id_set_sha256":"a"*64,"eligible_bibliographic_source_count":0,"known_publication_identity_count":len(mapping or {}),"identity_to_source":mapping or {},"source_admission_completeness_claim":False,"publication_universe_completeness_claim":False}
class EuropePmcReplayTests(unittest.TestCase):
    def test_real_controlled_namespace_and_prima_bibliographic_continuity(self):
        index=replay.build_known_publication_source_index();self.assertEqual(index["materialized_source_count"],248);self.assertEqual(len(index["source_id_set_sha256"]),64);self.assertEqual(index["identity_to_source"].get("PMID:41124203"),"SRC-PR-013");self.assertFalse(index["publication_universe_completeness_claim"])
    def test_source_class_boundary_is_bibliographic_only(self):
        self.assertTrue(replay._bibliographic({"source_class":"OFFICIAL_BIBLIOGRAPHIC_METADATA"}));self.assertFalse(replay._bibliographic({"source_class":"PRIMARY_JOURNAL_ARTICLE"}))
    def test_partial_replay_remains_noncanonical(self):
        r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known());self.assertFalse(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"]);self.assertEqual(r["reconciliation"]["union_unique_publication_count"],1)
    def test_full_programme_can_be_mechanically_complete_without_global_recall(self):
        count=len(replay._programme()["query_streams"]);r=replay.build_replay(_bundle("FULL_PROGRAMME",count),projector=_mock_projector,known_index=_known());self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["global_neuroai_publication_recall_claim"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_exact_known_identity_is_duplicate(self):
        qid=replay._programme()["query_streams"][0]["query_id"];identity=_identity(qid);r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known({identity:"SRC-EXACT"}));self.assertEqual(r["known_duplicates"][0]["duplicate_of_source_id"],"SRC-EXACT")
    def test_request_drift_fails_closed(self):
        b=_bundle();b["query_captures"][0]["request"]["synonym_expansion"]=True
        with self.assertRaisesRegex(ValueError,"capture does not match programme control"):replay.build_replay(b,projector=_mock_projector,known_index=_known())
    def test_cross_query_conflict_fails_closed(self):
        b=_bundle("PARTIAL_VALIDATION",2)
        def conflict(*,query_id,query_text,pages,known_publication_sources,known_anchor_identities):
            digest="A" if query_id==b["query_captures"][0]["query_id"] else "B";n={"resolved_identity":"DOI:10.1234/same","query_memberships":[query_id],"normalized_record_sha256":digest};r={"record_key":"DOI:10.1234/same","title":"P","url":"u","publisher":"Europe PMC","source_class":"OFFICIAL_BIBLIOGRAPHIC_METADATA","suggested_source_id":"SRC","classification_hint":"NEW"};return {"result_records":[r],"normalized_records":[n],"coverage":_coverage(query_id)}
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(b,projector=conflict,known_index=_known())
    def test_deterministic_minimized_output(self):
        r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known())
        with tempfile.TemporaryDirectory() as d:
            a=replay.write_projection(r,Path(d)/"a");b=replay.write_projection(r,Path(d)/"b");self.assertEqual(a,b);m=json.loads((Path(d)/"a/manifest.json").read_text());self.assertFalse(m["raw_api_pages_emitted"]);self.assertFalse(m["full_text_emitted"]);self.assertFalse(m["participant_level_data_emitted"]);self.assertFalse(m["canonical_successor_ready"])
if __name__=="__main__":unittest.main()

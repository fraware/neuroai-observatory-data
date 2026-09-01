from __future__ import annotations
import hashlib,tempfile,unittest
from pathlib import Path
import scripts.run_su_grants_nih_reporter_recorded_replay as replay


def _known(mapping=None):
    mapping=mapping or {};return {"materialized_source_count":248,"source_id_set_sha256":"a"*64,"grant_typed_source_count":len(set(mapping.values())),"known_reporter_appl_id_count":len(mapping),"appl_to_source":{str(k):v for k,v in mapping.items()},"appl_lineage":{},"global_grant_completeness_claim":False}

def _coverage(qid):return {"supplied_page_count":1,"returned_record_count":1,"unique_appl_id_count":1,"reported_total_count":1,"reported_total_count_state":"CONSISTENT","offset_sequence_valid":True,"offset_coverage_state":"MATCH","over_15000_limit":False,"partition_required":False,"known_controlled_duplicate_count":0,"new_candidate_count":1,"duplicate_representation_count":0,"unresolved_appl_id_count":0,"candidate_emission_refused_due_to_over_limit":False,"query_id":qid}

def _mock(*,query_id,query_payload,pages,known_appl_sources):
    appl=int(hashlib.sha256(query_id.encode()).hexdigest()[:7],16)+1;digest=hashlib.sha256(str(appl).encode()).hexdigest();dup=known_appl_sources.get(str(appl)) or known_appl_sources.get(appl)
    norm={"appl_id":appl,"project_num":f"R01-{appl}","core_project_num":f"R01-{appl}","subproject_id":None,"fiscal_year":2026,"project_title":"Synthetic grant","abstract_text":"Neural interface research","project_start_date":"2026-01-01","project_end_date":"2027-01-01","award_notice_date":"2026-01-15","award_amount":100000,"funding_mechanism":"RP","agency_ic_admin":{"code":"NS"},"organization":{"org_name":"Example"},"principal_investigators":[{"full_name":"Example PI"}],"query_memberships":[query_id],"normalized_record_sha256":digest}
    rec={"record_key":f"REPORTER:APPL:{appl}","title":"Synthetic grant","url":f"https://reporter.nih.gov/project-details/{appl}","publisher":"NIH RePORTER","source_class":"OFFICIAL_GRANT_DATABASE","suggested_source_id":f"SRC-REPORTER-APPL-{appl}","classification_hint":"DUPLICATE" if dup else "NEW"}
    if dup:rec["duplicate_of_source_id"]=dup
    cov=_coverage(query_id);cov["known_controlled_duplicate_count"]=1 if dup else 0;cov["new_candidate_count"]=0 if dup else 1
    return {"result_records":[rec],"normalized_records":[norm],"coverage":cov}

def _capture(stream,*,leaf="leaf",partition=None,extra_criteria=None):
    criteria={"advanced_text_search":stream["advanced_text_search"]};partition=partition or []
    for part in partition:
        if part["dimension"]=="FISCAL_YEAR":criteria["fiscal_years"]=[part["fiscal_year"]]
        else:criteria["award_notice_date"]={"from_date":part["from_date"],"to_date":part["to_date"]}
    if extra_criteria:criteria.update(extra_criteria)
    return {"query_id":stream["query_id"],"leaf_query_id":leaf,"query_payload":{"criteria":criteria,"offset":0,"limit":500},"partition_path":partition,"pages":[{"meta":{"total":1,"offset":0,"limit":500},"results":[]}]}
def _bundle(captures,scope="PARTIAL_VALIDATION"):return {"schema_version":"0.1.0","programme_id":"SU-GRANTS-NIH-REPORTER-v0.1","capture_scope":scope,"captured_at":"2026-09-02T00:00:00Z","provider":"NIH RePORTER API","leaf_query_captures":captures}

class NihReporterReplayTests(unittest.TestCase):
    def test_real_namespace_is_exact_248_and_digest_bound(self):
        i=replay.build_known_appl_source_index();self.assertEqual(i["materialized_source_count"],248);self.assertEqual(len(i["source_id_set_sha256"]),64);self.assertFalse(i["global_grant_completeness_claim"])
    def test_locator_requires_exact_reporter_project_details_url(self):
        self.assertEqual(replay._appl_from_locator("https://reporter.nih.gov/project-details/12345"),12345);self.assertIsNone(replay._appl_from_locator("https://example.invalid/?appl_id=12345"))
    def test_partial_replay_remains_noncanonical(self):
        s=replay._programme()["query_streams"][0];r=replay.build_replay(_bundle([_capture(s)]),projector=_mock,known_index=_known());self.assertEqual(r["reconciliation"]["materialized_source_namespace_count"],248);self.assertFalse(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_fiscal_year_partition_binds_actual_criteria(self):
        s=replay._programme()["query_streams"][0];part=[{"dimension":"FISCAL_YEAR","fiscal_year":2026}];r=replay.build_replay(_bundle([_capture(s,partition=part)]),projector=_mock,known_index=_known());self.assertTrue(r["reconciliation"]["partition_reconciliation_required"]);self.assertFalse(r["reconciliation"]["mechanically_complete"])
    def test_award_notice_partition_binds_actual_criteria(self):
        s=replay._programme()["query_streams"][0];part=[{"dimension":"AWARD_NOTICE_DATE","from_date":"2026-01-01","to_date":"2026-12-31"}];replay.build_replay(_bundle([_capture(s,partition=part)]),projector=_mock,known_index=_known())
    def test_declared_partition_without_matching_request_fails_closed(self):
        s=replay._programme()["query_streams"][0];part=[{"dimension":"FISCAL_YEAR","fiscal_year":2026}];c=_capture(s,partition=part);c["query_payload"]["criteria"].pop("fiscal_years")
        with self.assertRaisesRegex(ValueError,"exactly match governed"):replay.build_replay(_bundle([c]),projector=_mock,known_index=_known())
    def test_undeclared_extra_criteria_fails_closed(self):
        s=replay._programme()["query_streams"][0]
        with self.assertRaisesRegex(ValueError,"exactly match governed"):replay.build_replay(_bundle([_capture(s,extra_criteria={"fiscal_years":[2026]})]),projector=_mock,known_index=_known())
    def test_cross_leaf_content_conflict_fails_closed(self):
        streams=replay._programme()["query_streams"][:2];calls=0
        def conflicting(**kwargs):
            nonlocal calls;calls+=1;r=_mock(**kwargs);appl=777;r["normalized_records"][0]["appl_id"]=appl;r["normalized_records"][0]["normalized_record_sha256"]=("a" if calls==1 else "b")*64;r["result_records"][0]["record_key"]=f"REPORTER:APPL:{appl}";r["result_records"][0]["suggested_source_id"]="SRC-X";return r
        with self.assertRaisesRegex(ValueError,"Cross-leaf conflict"):replay.build_replay(_bundle([_capture(streams[0],leaf="a"),_capture(streams[1],leaf="b")]),projector=conflicting,known_index=_known())
    def test_clean_full_unpartitioned_programme_can_be_mechanically_complete(self):
        streams=replay._programme()["query_streams"];r=replay.build_replay(_bundle([_capture(s,leaf=f"leaf-{i}") for i,s in enumerate(streams)],"FULL_PROGRAMME"),projector=_mock,known_index=_known());self.assertTrue(r["reconciliation"]["all_logical_queries_represented"]);self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["global_neuroai_grant_recall_claim"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_deterministic_writer_never_emits_raw_pages(self):
        s=replay._programme()["query_streams"][0];r=replay.build_replay(_bundle([_capture(s)]),projector=_mock,known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);a=replay.write_projection(r,out);b=replay.write_projection(r,out);self.assertEqual(a["manifest_sha256"],b["manifest_sha256"]);self.assertFalse(a["raw_reporter_pages_emitted"]);self.assertFalse(any("raw" in p.name.lower() for p in out.iterdir()))
    def test_no_authority_escalation(self):
        s=replay._programme()["query_streams"][0];r=replay.build_replay(_bundle([_capture(s)]),projector=_mock,known_index=_known())["reconciliation"]
        for key in ("automatic_source_admission","automatic_project_entity_creation","automatic_pi_or_organization_entity_creation","automatic_system_or_model_relationship_creation","automatic_funding_success_claim_creation","automatic_assessment_mutation","reporter_database_completeness_claim","global_neuroai_grant_recall_claim","funding_success_claim","canonical_successor_ready"):self.assertFalse(r[key],key)

if __name__=="__main__":unittest.main()

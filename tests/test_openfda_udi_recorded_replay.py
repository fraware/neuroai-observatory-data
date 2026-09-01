from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
import scripts.run_su_regulation_openfda_udi_recorded_replay as replay

def _coverage(qid:str)->dict:
    return {"supplied_page_count":1,"returned_record_count":1,"unique_primary_di_record_count":1,"reported_total_count":1,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"bulk_download_or_partition_required":False,"known_controlled_duplicate_count":0,"new_candidate_count":1,"duplicate_representation_count":0,"unresolved_primary_di_count":0,"multiple_primary_di_count":0,"query_id":qid}

def _mock_projector(*,query_id,search,pages,known_udi_sources):
    identity=f"UDI:GS1:{hashlib.sha256(query_id.encode()).hexdigest()[:12].upper()}"
    n={"record_identity":identity,"primary_di":identity.split(":",2)[2],"primary_di_issuing_agency":"GS1","record_key":"RK","record_status":"Published","public_version_number":"1","public_version_date":"2026-08-31","public_version_status":"New","publish_date":"2026-01-01","brand_name":"Device","company_name":"Company","version_or_model_number":"M1","catalog_number":"C1","device_description":"Neural device","commercial_distribution_status":"In Commercial Distribution","commercial_distribution_end_date":None,"identifiers":[{"issuing_agency":"GS1","id":identity.split(":",2)[2],"type":"Primary"}],"premarket_submissions":[],"product_codes":[],"query_memberships":[query_id],"normalized_record_sha256":hashlib.sha256(identity.encode()).hexdigest()}
    dup=known_udi_sources.get(identity.upper());r={"record_key":identity,"title":"Device","url":"https://example.invalid/udi","publisher":"U.S. FDA","source_class":"OFFICIAL_DEVICE_IDENTIFICATION_RECORD","suggested_source_id":"SRC-CANDIDATE","classification_hint":"DUPLICATE" if dup else "NEW"}
    if dup:r["duplicate_of_source_id"]=dup
    c=_coverage(query_id);c["known_controlled_duplicate_count"]=1 if dup else 0;c["new_candidate_count"]=0 if dup else 1
    return {"result_records":[r],"normalized_records":[n],"coverage":c}

def _bundle(scope="PARTIAL_VALIDATION",count=1,partition=False):
    p=replay._programme();streams=p["query_streams"][:count];caps=[]
    for i,s in enumerate(streams):
        part=[];effective=s["search"]
        if partition:
            part=[{"dimension":"PUBLIC_VERSION_DATE","lower_bound":"20260101","upper_bound":"20261231"}];effective=f'({s["search"]})+AND+public_version_date:[20260101+TO+20261231]'
        caps.append({"query_id":s["query_id"],"leaf_query_id":f"leaf-{i}","effective_search":effective,"partition_path":part,"pages":[{"meta":{"results":{"total":1,"skip":0,"limit":1000}},"results":[{}]}]})
    return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":caps}

class OpenFdaUdiReplayTests(unittest.TestCase):
    def test_real_controlled_namespace_is_248_sources_and_digest_bound(self):
        idx=replay.build_known_udi_source_index();self.assertEqual(idx["materialized_source_count"],248);self.assertEqual(len(idx["source_id_set_sha256"]),64);self.assertFalse(idx["global_udi_completeness_claim"])
    def test_partial_replay_remains_noncanonical(self):
        known={"materialized_source_count":248,"udi_eligible_source_count":0,"known_exact_udi_identity_count":0,"udi_identity_to_source":{},"global_udi_completeness_claim":False}
        r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known);self.assertFalse(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"]);self.assertEqual(r["reconciliation"]["union_unique_udi_identity_count"],1)
    def test_exact_known_identity_is_preserved_as_duplicate(self):
        q=replay._programme()["query_streams"][0]["query_id"];identity=f"UDI:GS1:{hashlib.sha256(q.encode()).hexdigest()[:12].upper()}";known={"materialized_source_count":248,"udi_eligible_source_count":1,"known_exact_udi_identity_count":1,"udi_identity_to_source":{identity.upper():"SRC-EXACT"},"global_udi_completeness_claim":False}
        r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known);self.assertEqual(r["known_duplicates"][0]["duplicate_of_source_id"],"SRC-EXACT")
    def test_full_unpartitioned_programme_can_be_mechanically_complete(self):
        known={"materialized_source_count":248,"udi_eligible_source_count":0,"known_exact_udi_identity_count":0,"udi_identity_to_source":{},"global_udi_completeness_claim":False};count=len(replay._programme()["query_streams"])
        r=replay.build_replay(_bundle("FULL_PROGRAMME",count),projector=_mock_projector,known_index=known);self.assertTrue(r["reconciliation"]["all_logical_queries_represented"]);self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_partitioned_traversal_is_not_programme_complete(self):
        known={"materialized_source_count":248,"udi_eligible_source_count":0,"known_exact_udi_identity_count":0,"udi_identity_to_source":{},"global_udi_completeness_claim":False};count=len(replay._programme()["query_streams"])
        r=replay.build_replay(_bundle("FULL_PROGRAMME",count,True),projector=_mock_projector,known_index=known);self.assertGreater(r["reconciliation"]["partitioned_leaf_count"],0);self.assertTrue(r["reconciliation"]["partition_reconciliation_required"]);self.assertFalse(r["reconciliation"]["mechanically_complete"])
    def test_cross_query_content_conflict_fails_closed(self):
        p=replay._programme();b=_bundle("PARTIAL_VALIDATION",2)
        def conflicting(*,query_id,search,pages,known_udi_sources):
            identity="UDI:GS1:SAME";digest="A" if query_id==p["query_streams"][0]["query_id"] else "B";n={"record_identity":identity,"query_memberships":[query_id],"normalized_record_sha256":digest};r={"record_key":identity,"title":"Device","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_DEVICE_IDENTIFICATION_RECORD","suggested_source_id":"SRC","classification_hint":"NEW"};return {"result_records":[r],"normalized_records":[n],"coverage":_coverage(query_id)}
        known={"materialized_source_count":248,"udi_eligible_source_count":0,"known_exact_udi_identity_count":0,"udi_identity_to_source":{},"global_udi_completeness_claim":False}
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(b,projector=conflicting,known_index=known)
    def test_deterministic_output_never_emits_raw_pages(self):
        known={"materialized_source_count":248,"udi_eligible_source_count":0,"known_exact_udi_identity_count":0,"udi_identity_to_source":{},"global_udi_completeness_claim":False};r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known)
        with tempfile.TemporaryDirectory() as d:
            a=replay.write_projection(r,Path(d)/"a");b=replay.write_projection(r,Path(d)/"b");self.assertEqual(a,b);m=json.loads((Path(d)/"a/manifest.json").read_text());self.assertFalse(m["raw_openfda_pages_emitted"]);self.assertFalse(m["customer_contacts_emitted"]);self.assertFalse(m["labeler_duns_emitted"]);self.assertFalse(m["canonical_successor_ready"])
    def test_no_authority_escalation(self):
        known={"materialized_source_count":248,"udi_eligible_source_count":0,"known_exact_udi_identity_count":0,"udi_identity_to_source":{},"global_udi_completeness_claim":False};c=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known)["reconciliation"]
        for k in ("automatic_di_relationship_creation","automatic_premarket_authorization_relationship_creation","automatic_current_commercial_availability_claim_creation","automatic_marketing_authorization_claim_creation","automatic_effectiveness_claim_creation","automatic_system_conformance_claim_creation","automatic_reopening_decision","automatic_assessment_mutation","canonical_successor_ready","global_neuroai_udi_coverage_claim"):self.assertFalse(c[k])

if __name__=="__main__":unittest.main()

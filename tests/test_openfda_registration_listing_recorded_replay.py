from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
import scripts.run_su_regulation_openfda_registration_listing_recorded_replay as replay

def _coverage(qid:str)->dict:
    return {"supplied_page_count":1,"returned_provider_record_count":1,"expanded_representation_count":1,"unique_representation_count":1,"reported_total_count":1,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"bulk_download_or_partition_required":False,"known_controlled_duplicate_count":0,"new_candidate_count":1,"duplicate_representation_count":0,"unresolved_registration_number_count":0,"unresolved_owner_operator_number_count":0,"unresolved_product_code_count":0,"representation_is_exact_device_identity":False,"registration_or_listing_is_clearance_or_approval":False,"query_id":qid}
def _mock_projector(*,query_id,search,pages,known_representation_sources):
    token=hashlib.sha256(query_id.encode()).hexdigest()[:16].upper();identity=f"REGLIST:9610240:9051149:ABC:{token}";n={"representation_identity":identity,"query_memberships":[query_id],"normalized_record_sha256":hashlib.sha256(identity.encode()).hexdigest(),"registration_number":"9610240","owner_operator_number":"9051149","product_code":"ABC","representation_is_exact_device_identity":False,"registration_or_listing_establishes_authorization":False};dup=known_representation_sources.get(identity.upper());r={"record_key":identity,"title":"Device","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_REGULATORY_LISTING_REPRESENTATION","suggested_source_id":"SRC-CANDIDATE","classification_hint":"DUPLICATE" if dup else "NEW","exact_device_identity":False};
    if dup:r["duplicate_of_source_id"]=dup
    c=_coverage(query_id);c["known_controlled_duplicate_count"]=1 if dup else 0;c["new_candidate_count"]=0 if dup else 1
    return {"result_records":[r],"normalized_records":[n],"coverage":c}
def _bundle(scope="PARTIAL_VALIDATION",count=1):
    p=replay._programme();caps=[]
    for i,s in enumerate(p["query_streams"][:count]):caps.append({"query_id":s["query_id"],"leaf_query_id":f"leaf-{i}","effective_search":s["search"],"partition_path":[],"pages":[{"meta":{"results":{"total":1,"skip":0,"limit":1000}},"results":[{}]}]})
    return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":caps}
class RegistrationListingReplayTests(unittest.TestCase):
    def test_real_controlled_namespace_is_248_sources(self):
        idx=replay.build_known_representation_source_index();self.assertEqual(idx["materialized_source_count"],248);self.assertFalse(idx["global_registration_listing_completeness_claim"])
    def test_partial_replay_is_noncanonical(self):
        known={"materialized_source_count":248,"registration_listing_eligible_source_count":0,"known_exact_representation_count":0,"representation_to_source":{},"global_registration_listing_completeness_claim":False};r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known);self.assertFalse(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_exact_representation_duplicate_is_preserved(self):
        q=replay._programme()["query_streams"][0]["query_id"];token=hashlib.sha256(q.encode()).hexdigest()[:16].upper();identity=f"REGLIST:9610240:9051149:ABC:{token}";known={"materialized_source_count":248,"registration_listing_eligible_source_count":1,"known_exact_representation_count":1,"representation_to_source":{identity.upper():"SRC-EXACT"},"global_registration_listing_completeness_claim":False};r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known);self.assertEqual(r["known_duplicates"][0]["duplicate_of_source_id"],"SRC-EXACT")
    def test_full_unpartitioned_programme_can_be_mechanically_complete_but_not_authoritative(self):
        known={"materialized_source_count":248,"registration_listing_eligible_source_count":0,"known_exact_representation_count":0,"representation_to_source":{},"global_registration_listing_completeness_claim":False};count=len(replay._programme()["query_streams"]);r=replay.build_replay(_bundle("FULL_PROGRAMME",count),projector=_mock_projector,known_index=known);self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"]);self.assertFalse(r["reconciliation"]["representation_is_exact_device_identity"])
    def test_partitioned_capture_is_refused_in_v0_1(self):
        b=_bundle();b["leaf_query_captures"][0]["partition_path"]=[{"dimension":"YEAR"}]
        known={"materialized_source_count":248,"registration_listing_eligible_source_count":0,"known_exact_representation_count":0,"representation_to_source":{},"global_registration_listing_completeness_claim":False}
        with self.assertRaisesRegex(ValueError,"does not authorize partitioned"):replay.build_replay(b,projector=_mock_projector,known_index=known)
    def test_cross_query_conflict_fails_closed(self):
        p=replay._programme();b=_bundle("PARTIAL_VALIDATION",2)
        def conflicting(*,query_id,search,pages,known_representation_sources):
            identity="REGLIST:9610240:9051149:ABC:0123456789ABCDEF";d="A" if query_id==p["query_streams"][0]["query_id"] else "B";n={"representation_identity":identity,"query_memberships":[query_id],"normalized_record_sha256":d};r={"record_key":identity,"title":"D","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_REGULATORY_LISTING_REPRESENTATION","suggested_source_id":"S","classification_hint":"NEW","exact_device_identity":False};return {"result_records":[r],"normalized_records":[n],"coverage":_coverage(query_id)}
        known={"materialized_source_count":248,"registration_listing_eligible_source_count":0,"known_exact_representation_count":0,"representation_to_source":{},"global_registration_listing_completeness_claim":False}
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(b,projector=conflicting,known_index=known)
    def test_deterministic_output_excludes_raw_and_contact_categories(self):
        known={"materialized_source_count":248,"registration_listing_eligible_source_count":0,"known_exact_representation_count":0,"representation_to_source":{},"global_registration_listing_completeness_claim":False};r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known)
        with tempfile.TemporaryDirectory() as d:
            a=replay.write_projection(r,Path(d)/"a");b=replay.write_projection(r,Path(d)/"b");self.assertEqual(a,b);m=json.loads((Path(d)/"a/manifest.json").read_text());self.assertFalse(m["raw_openfda_pages_emitted"]);self.assertFalse(m["registration_addresses_emitted"]);self.assertFalse(m["owner_operator_contacts_emitted"]);self.assertFalse(m["us_agent_fields_emitted"]);self.assertFalse(m["official_correspondent_fields_emitted"])
    def test_no_authority_escalation(self):
        known={"materialized_source_count":248,"registration_listing_eligible_source_count":0,"known_exact_representation_count":0,"representation_to_source":{},"global_registration_listing_completeness_claim":False};c=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known)["reconciliation"]
        for k in ("representation_is_exact_device_identity","registration_or_listing_is_marketing_authorization","registration_or_listing_is_clearance_or_approval","k_or_pma_reference_establishes_exact_configuration_authorization","product_code_establishes_exact_device_identity","automatic_reopening_decision","automatic_assessment_mutation","canonical_successor_ready","global_neuroai_registration_listing_coverage_claim"):self.assertFalse(c[k])
if __name__=="__main__":unittest.main()

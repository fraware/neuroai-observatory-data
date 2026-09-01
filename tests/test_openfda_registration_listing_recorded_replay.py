from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
import scripts.run_su_regulation_openfda_registration_listing_recorded_replay as replay

def _coverage(qid:str)->dict:
    return {"supplied_page_count":1,"returned_provider_record_count":1,"expanded_representation_count":1,"unique_representation_count":1,"reported_total_count":1,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"bulk_download_or_partition_required":False,"known_controlled_duplicate_count":0,"new_candidate_count":1,"duplicate_representation_count":0,"unresolved_registration_number_count":0,"unresolved_owner_operator_number_count":0,"unresolved_product_code_count":0,"query_id":qid}

def _mock_projector(*,query_id,search,pages,known_representation_sources):
    suffix=hashlib.sha256(query_id.encode()).hexdigest()[:12].upper();identity=f"REGLIST:9610240:9051149:ABC:{hashlib.sha256(suffix.encode()).hexdigest().upper()}"
    n={"representation_identity":identity,"registration_number":"9610240","owner_operator_number":"9051149","product_code":"ABC","proprietary_names":["Device"],"query_memberships":[query_id],"normalized_record_sha256":hashlib.sha256(identity.encode()).hexdigest()}
    dup=known_representation_sources.get(identity.upper());r={"record_key":identity,"title":"Device","url":"https://example.invalid/registrationlisting","publisher":"U.S. FDA","source_class":"OFFICIAL_DEVICE_REGISTRATION_LISTING_RECORD","suggested_source_id":"SRC-CANDIDATE","classification_hint":"DUPLICATE" if dup else "NEW"}
    if dup:r["duplicate_of_source_id"]=dup
    c=_coverage(query_id);c["known_controlled_duplicate_count"]=1 if dup else 0;c["new_candidate_count"]=0 if dup else 1
    return {"result_records":[r],"normalized_records":[n],"coverage":c}

def _bundle(scope="PARTIAL_VALIDATION",count=1,partition=False):
    p=replay._programme();caps=[]
    for i,s in enumerate(p["query_streams"][:count]):
        caps.append({"query_id":s["query_id"],"leaf_query_id":f"leaf-{i}","effective_search":s["search"],"partition_path":[{"dimension":"DATE","lower_bound":"20260101","upper_bound":"20261231"}] if partition else [],"pages":[{"meta":{"results":{"total":1,"skip":0,"limit":1000}},"results":[{}]}]})
    return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":caps}

class OpenFdaRegistrationListingReplayTests(unittest.TestCase):
    def test_real_controlled_namespace_is_248_sources_and_digest_bound(self):
        idx=replay.build_known_representation_source_index();self.assertEqual(idx["materialized_source_count"],248);self.assertEqual(len(idx["source_id_set_sha256"]),64);self.assertFalse(idx["global_registration_listing_completeness_claim"])
    def test_partial_replay_remains_noncanonical(self):
        known={"materialized_source_count":248,"source_id_set_sha256":"a"*64,"registration_listing_eligible_source_count":0,"known_exact_representation_identity_count":0,"representation_identity_to_source":{},"global_registration_listing_completeness_claim":False}
        r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known);self.assertFalse(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"]);self.assertEqual(r["reconciliation"]["union_unique_representation_count"],1);self.assertEqual(r["reconciliation"]["controlled_source_id_set_sha256"],"a"*64)
    def test_exact_known_representation_is_preserved_as_duplicate(self):
        q=replay._programme()["query_streams"][0]["query_id"];suffix=hashlib.sha256(q.encode()).hexdigest()[:12].upper();identity=f"REGLIST:9610240:9051149:ABC:{hashlib.sha256(suffix.encode()).hexdigest().upper()}";known={"materialized_source_count":248,"source_id_set_sha256":"b"*64,"registration_listing_eligible_source_count":1,"known_exact_representation_identity_count":1,"representation_identity_to_source":{identity.upper():"SRC-EXACT"},"global_registration_listing_completeness_claim":False}
        r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known);self.assertEqual(r["known_duplicates"][0]["duplicate_of_source_id"],"SRC-EXACT")
    def test_full_unpartitioned_programme_can_be_mechanically_complete(self):
        known={"materialized_source_count":248,"source_id_set_sha256":"c"*64,"registration_listing_eligible_source_count":0,"known_exact_representation_identity_count":0,"representation_identity_to_source":{},"global_registration_listing_completeness_claim":False};count=len(replay._programme()["query_streams"])
        r=replay.build_replay(_bundle("FULL_PROGRAMME",count),projector=_mock_projector,known_index=known);self.assertTrue(r["reconciliation"]["all_logical_queries_represented"]);self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["partition_strategy_authorized"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"])
    def test_any_partition_path_is_refused_in_v0_1(self):
        with self.assertRaisesRegex(ValueError,"does not authorize partitioned traversals"):replay.build_replay(_bundle(partition=True),projector=_mock_projector,known_index={"materialized_source_count":248,"source_id_set_sha256":"d"*64,"known_exact_representation_identity_count":0,"representation_identity_to_source":{}})
    def test_cross_query_content_conflict_fails_closed(self):
        p=replay._programme();b=_bundle("PARTIAL_VALIDATION",2)
        def conflicting(*,query_id,search,pages,known_representation_sources):
            identity="REGLIST:9610240:9051149:ABC:"+"A"*64;digest="A" if query_id==p["query_streams"][0]["query_id"] else "B";n={"representation_identity":identity,"query_memberships":[query_id],"normalized_record_sha256":digest};r={"record_key":identity,"title":"Device","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_DEVICE_REGISTRATION_LISTING_RECORD","suggested_source_id":"SRC","classification_hint":"NEW"};return {"result_records":[r],"normalized_records":[n],"coverage":_coverage(query_id)}
        known={"materialized_source_count":248,"source_id_set_sha256":"e"*64,"known_exact_representation_identity_count":0,"representation_identity_to_source":{}}
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(b,projector=conflicting,known_index=known)
    def test_deterministic_output_never_emits_raw_or_contact_fields(self):
        known={"materialized_source_count":248,"source_id_set_sha256":"f"*64,"registration_listing_eligible_source_count":0,"known_exact_representation_identity_count":0,"representation_identity_to_source":{},"global_registration_listing_completeness_claim":False};r=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known)
        with tempfile.TemporaryDirectory() as d:
            a=replay.write_projection(r,Path(d)/"a");b=replay.write_projection(r,Path(d)/"b");self.assertEqual(a,b);m=json.loads((Path(d)/"a/manifest.json").read_text());self.assertFalse(m["raw_openfda_pages_emitted"]);self.assertFalse(m["registration_addresses_emitted"]);self.assertFalse(m["owner_operator_contacts_emitted"]);self.assertFalse(m["us_agent_fields_emitted"]);self.assertFalse(m["official_correspondent_fields_emitted"]);self.assertFalse(m["canonical_successor_ready"])
    def test_no_authority_escalation(self):
        known={"materialized_source_count":248,"source_id_set_sha256":"1"*64,"known_exact_representation_identity_count":0,"representation_identity_to_source":{}};c=replay.build_replay(_bundle(),projector=_mock_projector,known_index=known)["reconciliation"]
        for k in ("representation_identity_is_exact_device_identity","registration_or_listing_is_marketing_authorization_claim","registration_or_listing_is_clearance_or_approval_claim","k_or_pma_reference_is_exact_configuration_authorization_claim","product_code_is_exact_device_identity_claim","automatic_registration_relationship_creation","automatic_premarket_authorization_relationship_creation","automatic_current_commercial_availability_claim_creation","automatic_system_conformance_claim_creation","automatic_reopening_decision","automatic_assessment_mutation","canonical_successor_ready","global_neuroai_registration_listing_coverage_claim"):self.assertFalse(c[k])

if __name__=="__main__":unittest.main()

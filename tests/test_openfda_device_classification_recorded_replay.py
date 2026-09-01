from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
import scripts.run_su_regulation_openfda_device_classification_recorded_replay as replay

def _coverage(query_id:str,*,proposed:bool=False)->dict:
    return {"supplied_page_count":1,"returned_record_count":1,"unique_product_code_count":1,"reported_total_count":1,"reported_total_count_state":"CONSISTENT","skip_sequence_valid":True,"skip_coverage_state":"MATCH","over_26000_limit":False,"bulk_download_or_partition_required":False,"known_controlled_duplicate_count":0,"new_candidate_count":1,"duplicate_representation_count":0,"unresolved_product_code_count":0,"regulation_referenced_classification_count":0 if proposed else 1,"proposed_not_final_classification_count":1 if proposed else 0,"query_id":query_id,"product_code_is_exact_device_identity_claim":False,"classification_record_is_marketing_authorization_claim":False,"classification_record_is_clearance_or_approval_claim":False,"device_class_is_system_conformance_claim":False}

def _mock_projector(*,query_id,search,pages,known_product_code_sources):
    code=("A"+hashlib.sha256(query_id.encode()).hexdigest()[:2]).upper()
    finality="PROPOSED_CLASS_NOT_FINAL" if query_id.endswith("RECORDING-001") else "REGULATION_REFERENCED_CLASSIFICATION"
    normalized={"record_identity":code,"product_code":code,"device_name":"Device category","definition":"Generic category","device_class":"2","classification_finality":finality,"regulation_number":None if finality=="PROPOSED_CLASS_NOT_FINAL" else "882.9999","medical_specialty":"NE","medical_specialty_description":"Neurology","review_code":"N","implant_flag":"Y","life_sustain_support_flag":"N","gmp_exempt_flag":"N","query_memberships":[query_id],"normalized_record_sha256":hashlib.sha256((code+finality).encode()).hexdigest()}
    duplicate=known_product_code_sources.get(code)
    record={"record_key":code,"title":"Device category","url":f'https://api.fda.gov/device/classification.json?search=product_code:%22{code}%22',"publisher":"U.S. FDA","source_class":"OFFICIAL_DEVICE_CLASSIFICATION_RECORD","suggested_source_id":"SRC-CANDIDATE-"+code,"classification_hint":"DUPLICATE" if duplicate else "NEW"}
    if duplicate:record["duplicate_of_source_id"]=duplicate
    coverage=_coverage(query_id,proposed=finality=="PROPOSED_CLASS_NOT_FINAL");coverage["known_controlled_duplicate_count"]=1 if duplicate else 0;coverage["new_candidate_count"]=0 if duplicate else 1
    return {"result_records":[record],"normalized_records":[normalized],"coverage":coverage}

def _bundle(scope="PARTIAL_VALIDATION",count=1):
    programme=replay._programme();streams=programme["query_streams"][:count]
    return {"schema_version":"0.1.0","programme_id":programme["programme_id"],"provider":programme["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":[{"query_id":stream["query_id"],"leaf_query_id":f"leaf-{index}","effective_search":stream["search"],"partition_path":[],"pages":[{"meta":{"results":{"total":1,"skip":0,"limit":1000}},"results":[{}]}]} for index,stream in enumerate(streams)]}

def _known(mapping=None):return {"materialized_source_count":248,"source_id_set_sha256":"a"*64,"classification_eligible_source_count":0,"known_exact_product_code_count":len(mapping or {}),"product_code_to_source":mapping or {},"global_classification_completeness_claim":False}

class DeviceClassificationReplayTests(unittest.TestCase):
    def test_real_controlled_namespace_is_exact_248_sources(self):
        index=replay.build_known_product_code_source_index();self.assertEqual(index["materialized_source_count"],248);self.assertEqual(len(index["source_id_set_sha256"]),64);self.assertFalse(index["global_classification_completeness_claim"])
    def test_product_code_locator_extraction_is_explicit_only(self):
        self.assertEqual(replay._exact_product_codes_from_locator('https://api.fda.gov/device/classification.json?search=product_code:%22ABC%22'),{"ABC"});self.assertEqual(replay._exact_product_codes_from_locator('https://example.invalid/classification?ID=ABC'),set())
    def test_partial_replay_remains_noncanonical(self):
        result=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known());self.assertFalse(result["reconciliation"]["mechanically_complete"]);self.assertFalse(result["reconciliation"]["canonical_successor_ready"]);self.assertEqual(result["reconciliation"]["union_unique_product_code_count"],1)
    def test_full_unpartitioned_programme_can_be_mechanically_complete(self):
        count=len(replay._programme()["query_streams"]);result=replay.build_replay(_bundle("FULL_PROGRAMME",count),projector=_mock_projector,known_index=_known());self.assertTrue(result["reconciliation"]["all_logical_queries_represented"]);self.assertTrue(result["reconciliation"]["mechanically_complete"]);self.assertFalse(result["reconciliation"]["canonical_successor_ready"]);self.assertFalse(result["reconciliation"]["partition_strategy_authorized"])
    def test_partition_path_fails_closed(self):
        bundle=_bundle();bundle["leaf_query_captures"][0]["partition_path"]=[{"dimension":"UNAUTHORIZED"}]
        with self.assertRaisesRegex(ValueError,"does not authorize partitioned"):replay.build_replay(bundle,projector=_mock_projector,known_index=_known())
    def test_exact_known_product_code_is_preserved_as_duplicate(self):
        query_id=replay._programme()["query_streams"][0]["query_id"];code=("A"+hashlib.sha256(query_id.encode()).hexdigest()[:2]).upper();result=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known({code:"SRC-EXACT"}));self.assertEqual(result["known_duplicates"][0]["duplicate_of_source_id"],"SRC-EXACT")
    def test_cross_query_content_conflict_fails_closed(self):
        bundle=_bundle("PARTIAL_VALIDATION",2)
        def conflicting(*,query_id,search,pages,known_product_code_sources):
            digest="A" if query_id==bundle["leaf_query_captures"][0]["query_id"] else "B";normalized={"record_identity":"ABC","product_code":"ABC","query_memberships":[query_id],"normalized_record_sha256":digest};record={"record_key":"ABC","title":"Device","url":"u","publisher":"U.S. FDA","source_class":"OFFICIAL_DEVICE_CLASSIFICATION_RECORD","suggested_source_id":"SRC","classification_hint":"NEW"};return {"result_records":[record],"normalized_records":[normalized],"coverage":_coverage(query_id)}
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(bundle,projector=conflicting,known_index=_known())
    def test_deterministic_output_never_emits_raw_pages_or_authority(self):
        result=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known())
        with tempfile.TemporaryDirectory() as directory:
            a=replay.write_projection(result,Path(directory)/"a");b=replay.write_projection(result,Path(directory)/"b");self.assertEqual(a,b);manifest=json.loads((Path(directory)/"a/manifest.json").read_text());self.assertFalse(manifest["raw_openfda_pages_emitted"]);self.assertFalse(manifest["openfda_harmonized_identity_fields_emitted"]);self.assertFalse(manifest["exact_device_identity_claim_created"]);self.assertFalse(manifest["authorization_claim_created"]);self.assertFalse(manifest["canonical_successor_ready"])
    def test_no_authority_escalation(self):
        reconciliation=replay.build_replay(_bundle(),projector=_mock_projector,known_index=_known())["reconciliation"]
        for key in ("product_code_is_exact_device_identity_claim","classification_record_is_marketing_authorization_claim","classification_record_is_clearance_or_approval_claim","device_class_is_system_conformance_claim","automatic_product_code_relationship_creation","automatic_regulation_relationship_creation","automatic_marketing_authorization_claim_creation","automatic_clearance_or_approval_claim_creation","automatic_exact_device_identity_claim_creation","automatic_system_conformance_claim_creation","automatic_reopening_decision","automatic_assessment_mutation","canonical_successor_ready","global_neuroai_classification_coverage_claim"):self.assertFalse(reconciliation[key],key)

if __name__=="__main__":unittest.main()

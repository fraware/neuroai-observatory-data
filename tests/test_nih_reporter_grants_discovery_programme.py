from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_nih_reporter_grants_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme

class NihReporterGrantsDiscoveryProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["query_stream_count"],7);self.assertEqual(r["grey_area_stream_count"],1);self.assertEqual(r["integration_state"],"AVAILABLE");self.assertFalse(r["network_requests_performed"]);self.assertFalse(r["canonical_mutation_performed"])
    def test_exact_paging_bounds(self):
        p=self.programme["provider_contract"];policy=self.programme["pagination_partition_policy"];self.assertEqual((p["max_records_per_request"],p["max_offset"]),(500,14999));self.assertEqual(policy["max_directly_pageable_result_count"],15000);self.assertFalse(policy["silent_truncation_allowed"]);self.assertFalse(policy["partial_over_limit_candidate_emission_allowed"])
    def test_appl_id_lineage_boundaries(self):
        i=self.programme["identity_policy"];self.assertEqual(i["primary_identity"],"NIH_REPORTER_APPL_ID")
        for key in ("project_number_auto_merge","core_project_lineage_auto_merge","subproject_auto_parent_merge","pi_name_auto_entity_merge","organization_name_auto_entity_merge"):self.assertFalse(i[key],key)
    def test_grey_stream_is_tier_c_review_only(self):
        row=next(r for r in self.programme["query_streams"] if r["query_id"]=="DISCOVERY-REPORTER-GREY-MENTAL-STATE-001");self.assertEqual(row["scope_tiers"],["C"]);self.assertFalse(row["completeness_claim"]);self.assertTrue(self.programme["inclusion_policy"]["human_relevance_review_required"]);self.assertFalse(self.programme["human_review_contract"]["automatic_acceptance"])
    def test_award_amount_never_becomes_success_claim(self):
        self.assertFalse(self.programme["candidate_projection"]["award_amount_interpreted_as_research_success"])
        for key in ("award_is_research_success_evidence","award_is_system_effectiveness_evidence","award_is_commercial_strength_evidence"):self.assertFalse(self.programme["human_review_contract"][key],key)
    def test_available_dependency_is_required(self):
        m=copy.deepcopy(self.programme);m["workbench_dependency"]["integration_state"]="PENDING_S1_MERGE"
        with self.assertRaisesRegex(ValueError,"AVAILABLE"):validate_programme(m,self.registry)
    def test_silent_truncation_fails_closed(self):
        m=copy.deepcopy(self.programme);m["pagination_partition_policy"]["silent_truncation_allowed"]=True
        with self.assertRaisesRegex(ValueError,"truncation"):validate_programme(m,self.registry)
    def test_partition_dimension_drift_fails_closed(self):
        m=copy.deepcopy(self.programme);m["pagination_partition_policy"]["preferred_partition_dimensions"]=["FISCAL_YEAR"]
        with self.assertRaisesRegex(ValueError,"Partition dimensions"):validate_programme(m,self.registry)
    def test_incremental_watermark_cannot_replace_historical_baseline(self):
        m=copy.deepcopy(self.programme);m["incremental_refresh_policy"]["watermark_does_not_replace_historical_baseline"]=False
        with self.assertRaisesRegex(ValueError,"historical baseline"):validate_programme(m,self.registry)
    def test_automatic_funding_success_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_funding_success_claim_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_funding_success_claim_creation"):validate_programme(m,self.registry)
    def test_schema_requires_available(self):
        s=json.loads(Path("schemas/nih-reporter-grants-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"AVAILABLE")

if __name__=="__main__":unittest.main()

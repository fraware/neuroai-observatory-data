from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_europepmc_publications_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme
class EuropePmcPublicationsDiscoveryProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates_offline(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["programme_id"],"SU-PUBLICATIONS-EUROPEPMC-v0.1");self.assertEqual(r["source_universe_id"],"SU-PUBLICATIONS");self.assertEqual(r["query_stream_count"],8);self.assertEqual(r["anchor_count"],2);self.assertEqual(r["integration_state"],"AVAILABLE");self.assertFalse(r["network_requests_performed"]);self.assertFalse(r["canonical_mutation_performed"]);self.assertFalse(r["global_recall_claim"])
    def test_query_streams_are_unique_and_scoped(self):
        streams=self.programme["query_streams"];self.assertEqual(len({r["query_id"] for r in streams}),8);self.assertEqual(len({r["query_term"] for r in streams}),8)
        for row in streams:self.assertTrue(row["query_term"].startswith("TITLE_ABS:"));self.assertFalse(row["completeness_claim"])
    def test_grey_area_is_review_only_tier_c(self):
        grey=next(r for r in self.programme["query_streams"] if r["query_id"]=="DISCOVERY-EPMC-GREY-MENTAL-STATE-001");self.assertEqual(grey["scope_tiers"],["C"]);self.assertTrue(self.programme["inclusion_policy"]["human_relevance_review_required"]);self.assertFalse(self.programme["human_review_contract"]["automatic_acceptance"])
    def test_non_preprint_does_not_assert_peer_review(self):
        metrics=set(self.programme["coverage_contract"]["required_metrics_per_query"]);self.assertIn("non_preprint_record_count",metrics);self.assertIn("publication_type_missing_count",metrics);self.assertNotIn("peer_reviewed_or_journal_count",metrics)
    def test_anchor_cannot_count_as_new_discovery(self):
        m=copy.deepcopy(self.programme);m["known_identifier_anchors"][0]["counts_as_new_discovery"]=True
        with self.assertRaisesRegex(ValueError,"cannot count as new discovery"):validate_programme(m,self.registry)
    def test_automatic_source_admission_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_publication_source_admission"]=True
        with self.assertRaisesRegex(ValueError,"automatic_publication_source_admission"):validate_programme(m,self.registry)
    def test_fuzzy_identity_merge_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["fuzzy_title_identity_merge_allowed"]=True
        with self.assertRaisesRegex(ValueError,"Automatic identity merge"):validate_programme(m,self.registry)
    def test_unavailable_dependency_fails_closed(self):
        m=copy.deepcopy(self.programme);m["workbench_dependency"]["integration_state"]="PENDING_S1_MERGE"
        with self.assertRaisesRegex(ValueError,"must be AVAILABLE"):validate_programme(m,self.registry)
    def test_global_recall_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["coverage_contract"]["global_neuroai_publication_recall_claim"]=True
        with self.assertRaisesRegex(ValueError,"global_neuroai_publication_recall_claim"):validate_programme(m,self.registry)
    def test_schema_requires_available_capability(self):
        s=json.loads(Path("schemas/europepmc-publications-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"AVAILABLE")
if __name__=="__main__":unittest.main()

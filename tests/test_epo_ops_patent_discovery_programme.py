from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_epo_ops_patent_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme
class EpoOpsPatentProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["query_stream_count"],9);self.assertEqual(r["integration_state"],"AVAILABLE");self.assertFalse(r["network_requests_performed"]);self.assertFalse(r["canonical_mutation_performed"]);self.assertFalse(r["global_patent_recall_claim"])
    def test_docdb_identity_and_family_separation(self):
        i=self.programme["identity_policy"];self.assertEqual(i["primary_identity"],"DOCDB_PUBLICATION_REFERENCE");self.assertFalse(i["publication_step_auto_merge"]);self.assertFalse(i["patent_family_auto_merge"]);self.assertTrue(i["family_relationship_requires_explicit_family_retrieval"])
    def test_over_limit_requires_partition_before_materialization(self):
        p=self.programme["search_partition_policy"];self.assertEqual(p["leaf_query_max_total_result_count"],2000);self.assertEqual(p["over_limit_policy"],"SPLIT_QUERY_BEFORE_MATERIALIZATION");self.assertFalse(p["silent_truncation_allowed"]);self.assertFalse(p["partial_over_limit_candidate_emission_allowed"])
    def test_applicant_watch_is_not_entity_resolution(self):
        w=next(r for r in self.programme["query_streams"] if r["query_id"]=="DISCOVERY-OPS-KNOWN-APPLICANTS-001");self.assertEqual(w["query_mode"],"APPLICANT_WATCH_SET");self.assertEqual(len(w["applicant_terms"]),8);self.assertFalse(self.programme["identity_policy"]["applicant_name_auto_entity_merge"])
    def test_auto_product_relationship_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_product_or_system_relationship_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_product_or_system_relationship_creation"):validate_programme(m,self.registry)
    def test_family_auto_merge_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["patent_family_auto_merge"]=True
        with self.assertRaisesRegex(ValueError,"patent_family_auto_merge"):validate_programme(m,self.registry)
    def test_global_recall_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["coverage_contract"]["global_neuroai_patent_recall_claim"]=True
        with self.assertRaisesRegex(ValueError,"global_neuroai_patent_recall_claim"):validate_programme(m,self.registry)
    def test_unavailable_dependency_fails_closed(self):
        m=copy.deepcopy(self.programme);m["workbench_dependency"]["integration_state"]="PENDING_S1_MERGE"
        with self.assertRaisesRegex(ValueError,"must be AVAILABLE"):validate_programme(m,self.registry)
    def test_schema_requires_available_capability(self):
        s=json.loads(Path("schemas/epo-ops-patent-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"AVAILABLE")
if __name__=="__main__":unittest.main()

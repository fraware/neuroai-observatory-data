from __future__ import annotations
import copy, json, unittest
from pathlib import Path
from scripts.validate_openfda_510k_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme
class OpenFda510kProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8")); cls.r=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme(self):
        x=validate_programme(self.p,self.r); self.assertEqual(x["query_stream_count"],5); self.assertEqual(x["integration_state"],"NOT_IMPLEMENTED"); self.assertFalse(x["record_presence_is_clearance_claim"])
    def test_den_separated(self):
        self.assertTrue(self.p["identity_policy"]["den_prefix_is_de_novo_and_out_of_scope_for_v0_1"]); self.assertFalse(self.p["candidate_projection"]["den_records_emitted_as_510k_candidates"])
    def test_record_presence_not_clearance(self):
        self.assertFalse(self.p["coverage_contract"]["record_presence_is_clearance_claim"]); self.assertFalse(self.p["human_review_contract"]["record_presence_is_clearance_evidence"]); self.assertTrue(self.p["candidate_projection"]["substantial_equivalence_or_clearance_state_derived_only_from_decision_fields"])
    def test_no_pma_or_global_conflation(self):
        c=self.p["coverage_contract"]; self.assertFalse(c["clearance_is_pma_approval_claim"]); self.assertFalse(c["clearance_is_global_authorization_claim"]); self.assertFalse(c["clearance_is_all_configuration_conformance_claim"])
    def test_queries_explicit(self):
        for q in self.p["query_streams"]: self.assertIn("device_name:",q["search"]); self.assertIn("+OR+",q["search"])
    def test_available_before_merge_fails(self):
        m=copy.deepcopy(self.p); m["workbench_dependency"]["integration_state"]="AVAILABLE"
        with self.assertRaisesRegex(ValueError,"cannot be AVAILABLE"): validate_programme(m,self.r)
    def test_automatic_clearance_from_presence_fails(self):
        m=copy.deepcopy(self.p); m["inclusion_policy"]["automatic_clearance_claim_from_record_presence"]=True
        with self.assertRaisesRegex(ValueError,"automatic_clearance_claim_from_record_presence"): validate_programme(m,self.r)
    def test_schema_blocks_available(self):
        s=json.loads(Path("schemas/openfda-510k-discovery-programme.schema.json").read_text(encoding="utf-8")); self.assertNotIn("AVAILABLE",s["properties"]["workbench_dependency"]["properties"]["integration_state"]["enum"])
if __name__=="__main__":unittest.main()

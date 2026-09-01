from __future__ import annotations
import copy, json, unittest
from pathlib import Path
from scripts.validate_openfda_510k_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme
class OpenFda510kProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8")); cls.r=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme(self):
        x=validate_programme(self.p,self.r); self.assertEqual(x["query_stream_count"],5); self.assertEqual(x["integration_state"],"PENDING_S1_MERGE"); self.assertEqual(x["recognized_se_code_count"],7); self.assertFalse(x["record_presence_is_clearance_claim"])
    def test_exact_fda_se_allowlist(self):
        d=self.p["decision_semantics_policy"]; self.assertEqual(d["recognized_substantial_equivalence_codes"],["SEKD","SESD","SESE","SESK","SESP","SESU","SESR"]); self.assertEqual(d["recognized_state"],"SUBSTANTIALLY_EQUIVALENT_RECORDED"); self.assertEqual(d["unknown_or_missing_code_state"],"UNRESOLVED_DECISION_CODE"); self.assertFalse(d["description_only_inference_allowed"]); self.assertFalse(d["device_name_or_record_presence_inference_allowed"])
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
        with self.assertRaisesRegex(ValueError,"must remain PENDING_S1_MERGE"): validate_programme(m,self.r)
    def test_decision_allowlist_drift_fails(self):
        m=copy.deepcopy(self.p); m["decision_semantics_policy"]["recognized_substantial_equivalence_codes"].append("SEXX")
        with self.assertRaisesRegex(ValueError,"allowlist changed"): validate_programme(m,self.r)
    def test_automatic_clearance_from_presence_fails(self):
        m=copy.deepcopy(self.p); m["inclusion_policy"]["automatic_clearance_claim_from_record_presence"]=True
        with self.assertRaisesRegex(ValueError,"automatic_clearance_claim_from_record_presence"): validate_programme(m,self.r)
    def test_schema_requires_pending_state_and_exact_codes(self):
        s=json.loads(Path("schemas/openfda-510k-discovery-programme.schema.json").read_text(encoding="utf-8")); self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"PENDING_S1_MERGE"); self.assertEqual(s["properties"]["decision_semantics_policy"]["properties"]["recognized_substantial_equivalence_codes"]["const"],["SEKD","SESD","SESE","SESK","SESP","SESU","SESR"])
if __name__=="__main__":unittest.main()

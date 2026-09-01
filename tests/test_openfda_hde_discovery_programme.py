from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_hde_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme

class OpenFdaHdeProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates_offline(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["query_stream_count"],5);self.assertEqual(r["integration_state"],"NOT_IMPLEMENTED");self.assertFalse(r["network_requests_performed"]);self.assertFalse(r["effectiveness_claim_created"]);self.assertFalse(r["facility_irb_approval_claim_created"])
    def test_every_stream_is_h_prefix_bounded(self):
        for row in self.programme["query_streams"]:self.assertIn("+AND+pma_number:H*",row["search"])
    def test_exact_appr_is_only_hde_approval_state(self):
        d=self.programme["decision_semantics_policy"];self.assertEqual(d["exact_code_map"]["APPR"],"HDE_APPROVAL_RECORDED");self.assertTrue(d["hde_approval_state_requires_exact_appr_code"]);self.assertTrue(d["record_presence_does_not_imply_hde_approval"])
    def test_hde_approval_does_not_become_effectiveness_or_irb_claim(self):
        a=self.programme["hde_authority_policy"];self.assertTrue(a["hde_approval_does_not_establish_reasonable_assurance_of_effectiveness"]);self.assertTrue(a["hde_standard_uses_probable_benefit_risk_boundary"]);self.assertTrue(a["hde_approval_does_not_establish_facility_irb_approval"])
        h=self.programme["human_review_contract"];self.assertFalse(h["hde_approval_record_is_reasonable_assurance_effectiveness_evidence"]);self.assertFalse(h["hde_approval_record_establishes_facility_irb_approval"])
    def test_effectiveness_auto_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_effectiveness_claim_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_effectiveness_claim_creation"):validate_programme(m,self.registry)
    def test_facility_irb_auto_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_facility_irb_authorization_claim_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_facility_irb_authorization_claim_creation"):validate_programme(m,self.registry)
    def test_removing_h_prefix_filter_fails_closed(self):
        m=copy.deepcopy(self.programme);m["query_streams"][0]["search"]=m["query_streams"][0]["search"].replace("+AND+pma_number:H*","")
        with self.assertRaisesRegex(ValueError,"H-prefix filter"):validate_programme(m,self.registry)
    def test_global_authorization_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["coverage_contract"]["hde_approval_is_global_authorization_claim"]=True
        with self.assertRaisesRegex(ValueError,"hde_approval_is_global_authorization_claim"):validate_programme(m,self.registry)
    def test_automatic_reopening_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_reopening_decision"]=True
        with self.assertRaisesRegex(ValueError,"automatic_reopening_decision"):validate_programme(m,self.registry)
    def test_schema_keeps_workbench_unimplemented(self):
        s=json.loads(Path("schemas/openfda-hde-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"NOT_IMPLEMENTED")
if __name__=="__main__":unittest.main()

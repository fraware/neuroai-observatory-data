from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_pma_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme
class PmaProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.r=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current(self):
        x=validate_programme(self.p,self.r);self.assertEqual(x["query_stream_count"],5);self.assertEqual(x["decision_code_count"],8);self.assertEqual(x["integration_state"],"NOT_IMPLEMENTED")
    def test_composite_identity(self):
        i=self.p["identity_policy"];self.assertEqual(i["record_identity"],"PMA_NUMBER_PLUS_SUPPLEMENT_NUMBER");self.assertFalse(i["same_pma_number_different_supplement_auto_merge"])
    def test_pathway_separation(self):
        i=self.p["identity_policy"];self.assertTrue(i["h_prefix_hde_out_of_scope_for_v0_1"]);self.assertTrue(i["n_prefix_legacy_nda_out_of_scope_for_v0_1"]);self.assertFalse(self.p["candidate_projection"]["hde_records_emitted_as_pma_candidates"])
    def test_exact_decision_map(self):
        d=self.p["decision_semantics_policy"]["exact_code_map"];self.assertEqual(d["APPR"],"APPROVAL_RECORDED");self.assertEqual(d["DENY"],"DENIAL_RECORDED");self.assertEqual(d["LE30"],"THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED");self.assertTrue(self.p["decision_semantics_policy"]["approval_state_requires_exact_appr_code"])
    def test_supplement_does_not_overwrite_original(self):self.assertTrue(self.p["decision_semantics_policy"]["supplement_approval_does_not_rewrite_original_application_record"]);self.assertFalse(self.p["coverage_contract"]["supplement_approval_is_original_application_approval_claim"])
    def test_no_global_or_current_config_inference(self):
        r=self.p["human_review_contract"];self.assertFalse(r["approval_record_is_global_authorization"]);self.assertFalse(r["approval_record_establishes_exact_current_commercial_configuration"]);self.assertFalse(r["approval_record_is_all_configuration_conformance_evidence"])
    def test_decision_map_drift_fails(self):
        m=copy.deepcopy(self.p);m["decision_semantics_policy"]["exact_code_map"]["XXXX"]="APPROVAL_RECORDED"
        with self.assertRaisesRegex(ValueError,"decision-code map changed"):validate_programme(m,self.r)
    def test_auto_reopening_fails(self):
        m=copy.deepcopy(self.p);m["inclusion_policy"]["automatic_reopening_decision"]=True
        with self.assertRaisesRegex(ValueError,"automatic_reopening_decision"):validate_programme(m,self.r)
    def test_schema_exact_appr(self):
        s=json.loads(Path("schemas/openfda-pma-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["decision_semantics_policy"]["properties"]["exact_code_map"]["const"]["APPR"],"APPROVAL_RECORDED")
if __name__=="__main__":unittest.main()

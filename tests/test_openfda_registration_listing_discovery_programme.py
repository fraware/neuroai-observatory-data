from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_registration_listing_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme

class OpenFdaRegistrationListingProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates_offline(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["query_stream_count"],5);self.assertEqual(r["integration_state"],"AVAILABLE");self.assertFalse(r["network_requests_performed"]);self.assertFalse(r["exact_device_identity_claim_created"]);self.assertFalse(r["authorization_claim_created"])
    def test_representation_is_explicitly_not_exact_device_identity(self):
        i=self.programme["identity_policy"];self.assertTrue(i["provider_exposes_no_stable_listing_number_in_v0_1_surface"]);self.assertTrue(i["representation_identity_is_not_exact_device_identity"]);self.assertTrue(i["registration_number_is_establishment_registration_not_device_identity"])
    def test_registration_listing_never_becomes_authorization(self):
        c=self.programme["coverage_contract"];self.assertFalse(c["registration_or_listing_is_marketing_authorization_claim"]);self.assertFalse(c["registration_or_listing_is_clearance_or_approval_claim"])
        h=self.programme["human_review_contract"];self.assertFalse(h["registration_or_listing_is_marketing_authorization_evidence"]);self.assertFalse(h["registration_or_listing_is_clearance_or_approval_evidence"])
    def test_k_pma_and_product_code_remain_linkage_only(self):
        i=self.programme["identity_policy"];self.assertFalse(i["k_number_auto_authorization_relationship"]);self.assertFalse(i["pma_number_auto_authorization_relationship"]);self.assertFalse(i["product_code_auto_system_merge"])
        c=self.programme["coverage_contract"];self.assertFalse(c["k_or_pma_reference_is_exact_configuration_authorization_claim"]);self.assertFalse(c["product_code_is_exact_device_identity_claim"])
    def test_marketing_authorization_auto_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_marketing_authorization_claim_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_marketing_authorization_claim_creation"):validate_programme(m,self.registry)
    def test_exact_device_identity_upgrade_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["representation_identity_is_not_exact_device_identity"]=False
        with self.assertRaisesRegex(ValueError,"exact device identity"):validate_programme(m,self.registry)
    def test_product_code_auto_merge_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["product_code_auto_system_merge"]=True
        with self.assertRaisesRegex(ValueError,"product_code_auto_system_merge"):validate_programme(m,self.registry)
    def test_pii_projection_fails_closed(self):
        m=copy.deepcopy(self.programme);m["candidate_projection"]["us_agent_fields_in_discovery_layer"]=True
        with self.assertRaisesRegex(ValueError,"us_agent_fields_in_discovery_layer"):validate_programme(m,self.registry)
    def test_automatic_reopening_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_reopening_decision"]=True
        with self.assertRaisesRegex(ValueError,"automatic_reopening_decision"):validate_programme(m,self.registry)
    def test_pending_or_not_implemented_state_now_fails_closed(self):
        for state in ("PENDING_S1_MERGE","NOT_IMPLEMENTED"):
            m=copy.deepcopy(self.programme);m["workbench_dependency"]["integration_state"]=state
            with self.assertRaisesRegex(ValueError,"must be AVAILABLE"):validate_programme(m,self.registry)
    def test_schema_records_available_only(self):
        s=json.loads(Path("schemas/openfda-registration-listing-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"AVAILABLE")
if __name__=="__main__":unittest.main()

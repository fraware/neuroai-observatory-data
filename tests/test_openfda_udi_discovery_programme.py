from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_udi_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme

class OpenFdaUdiProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates_offline(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["query_stream_count"],5);self.assertEqual(r["integration_state"],"NOT_IMPLEMENTED");self.assertFalse(r["network_requests_performed"]);self.assertFalse(r["marketing_authorization_claim_created"]);self.assertFalse(r["current_availability_claim_created"])
    def test_primary_di_and_version_state_are_separate(self):
        i=self.programme["identity_policy"];self.assertEqual(i["device_record_identity"],"PRIMARY_DI_ISSUING_AGENCY_PLUS_ID");self.assertTrue(i["record_key_is_provider_tracking_key_not_device_identity"]);self.assertTrue(i["public_version_fields_track_record_updates"]);self.assertTrue(i["same_primary_di_changed_public_version_is_successor_observation"])
    def test_secondary_and_previous_identifiers_do_not_auto_merge(self):
        i=self.programme["identity_policy"]
        for k in ("secondary_di_auto_merge","previous_di_auto_merge","direct_marking_di_auto_merge","unit_of_use_di_auto_merge","package_di_auto_merge"):self.assertFalse(i[k])
    def test_premarket_link_does_not_create_authorization(self):
        self.assertFalse(self.programme["identity_policy"]["premarket_submission_auto_authorization_relationship"]);self.assertFalse(self.programme["coverage_contract"]["premarket_submission_link_is_exact_configuration_authorization_claim"]);self.assertFalse(self.programme["human_review_contract"]["premarket_submission_link_establishes_exact_assessed_configuration"])
    def test_commercial_distribution_state_does_not_prove_current_availability(self):
        self.assertFalse(self.programme["coverage_contract"]["commercial_distribution_status_is_independent_market_availability_proof"]);self.assertFalse(self.programme["human_review_contract"]["commercial_distribution_status_is_independent_current_availability_evidence"])
    def test_marketing_authorization_auto_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_marketing_authorization_claim_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_marketing_authorization_claim_creation"):validate_programme(m,self.registry)
    def test_secondary_di_auto_merge_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["secondary_di_auto_merge"]=True
        with self.assertRaisesRegex(ValueError,"secondary_di_auto_merge"):validate_programme(m,self.registry)
    def test_record_key_as_identity_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["record_key_is_provider_tracking_key_not_device_identity"]=False
        with self.assertRaisesRegex(ValueError,"record_key"):validate_programme(m,self.registry)
    def test_effectiveness_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["coverage_contract"]["primary_di_is_clinical_effectiveness_claim"]=True
        with self.assertRaisesRegex(ValueError,"primary_di_is_clinical_effectiveness_claim"):validate_programme(m,self.registry)
    def test_automatic_reopening_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_reopening_decision"]=True
        with self.assertRaisesRegex(ValueError,"automatic_reopening_decision"):validate_programme(m,self.registry)
    def test_schema_keeps_workbench_unimplemented(self):
        s=json.loads(Path("schemas/openfda-udi-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"NOT_IMPLEMENTED")
if __name__=="__main__":unittest.main()

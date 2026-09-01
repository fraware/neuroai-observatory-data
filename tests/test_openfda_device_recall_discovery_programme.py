from __future__ import annotations
import copy, json, unittest
from pathlib import Path
from scripts.validate_openfda_device_recall_discovery_programme import PROGRAMME_PATH, UNIVERSE_REGISTRY_PATH, validate_programme

class OpenFdaDeviceRecallProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8")); cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_current_programme_validates(self):
        result=validate_programme(self.programme,self.registry)
        self.assertEqual(result["query_stream_count"],5); self.assertEqual(result["integration_state"],"NOT_IMPLEMENTED")
        self.assertFalse(result["network_requests_performed"]); self.assertFalse(result["automatic_reopening"])

    def test_identity_is_cfres_and_event_is_lineage(self):
        p=self.programme["identity_policy"]
        self.assertEqual(p["primary_identity"],"CFRES_ID"); self.assertTrue(p["res_event_number_is_lineage_not_record_identity"])
        self.assertFalse(p["same_event_number_auto_merge"]); self.assertFalse(p["k_number_auto_system_merge"]); self.assertFalse(p["pma_number_auto_system_merge"])

    def test_recall_status_not_lifecycle_truth(self):
        self.assertFalse(self.programme["coverage_contract"]["recall_status_is_complete_lifecycle_tracker"])
        self.assertFalse(self.programme["human_review_contract"]["recall_status_is_authoritative_live_lifecycle_state"])

    def test_recall_never_auto_reopens(self):
        self.assertFalse(self.programme["inclusion_policy"]["automatic_reopening_decision"])
        self.assertFalse(self.programme["human_review_contract"]["recall_record_automatically_reopens_assessment"])

    def test_minimized_projection(self):
        p=self.programme["candidate_projection"]
        self.assertFalse(p["address_or_contact_fields_in_discovery_layer"]); self.assertFalse(p["code_info_lot_serial_text_in_discovery_layer"]); self.assertFalse(p["distribution_pattern_in_discovery_layer"])

    def test_explicit_or_queries(self):
        for row in self.programme["query_streams"]:
            self.assertIn("+OR+",row["search"]); self.assertIn("product_description:",row["search"])

    def test_available_before_merge_fails_closed(self):
        modified=copy.deepcopy(self.programme); modified["workbench_dependency"]["integration_state"]="AVAILABLE"
        with self.assertRaisesRegex(ValueError,"cannot be AVAILABLE"): validate_programme(modified,self.registry)

    def test_global_recall_claim_fails_closed(self):
        modified=copy.deepcopy(self.programme); modified["coverage_contract"]["global_neuroai_device_recall_claim"]=True
        with self.assertRaisesRegex(ValueError,"global_neuroai_device_recall_claim"): validate_programme(modified,self.registry)

    def test_auto_reopening_fails_closed(self):
        modified=copy.deepcopy(self.programme); modified["inclusion_policy"]["automatic_reopening_decision"]=True
        with self.assertRaisesRegex(ValueError,"automatic_reopening_decision"): validate_programme(modified,self.registry)

    def test_schema_control_surface(self):
        schema=json.loads(Path("schemas/openfda-device-recall-discovery-programme.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["provider_contract"]["properties"]["primary_recall_id_field"]["const"],"cfres_id")

if __name__ == "__main__": unittest.main()

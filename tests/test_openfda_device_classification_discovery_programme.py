from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_device_classification_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme
class DeviceClassificationProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["integration_state"],"AVAILABLE");self.assertEqual(r["query_stream_count"],5);self.assertFalse(r["exact_device_identity_claim_created"]);self.assertFalse(r["authorization_claim_created"])
    def test_product_code_is_generic_category_not_device_identity(self):self.assertTrue(self.programme["identity_policy"]["product_code_identifies_generic_device_category_not_exact_device"]);self.assertFalse(self.programme["coverage_contract"]["product_code_is_exact_device_identity_claim"])
    def test_missing_regulation_number_means_proposed_not_final(self):
        f=self.programme["classification_finality_policy"];self.assertEqual(f["regulation_number_absent_state"],"PROPOSED_CLASS_NOT_FINAL");self.assertTrue(f["device_class_without_regulation_number_must_not_be_presented_as_final"])
    def test_device_identity_upgrade_fails_closed(self):
        m=copy.deepcopy(self.programme);m["identity_policy"]["product_code_identifies_generic_device_category_not_exact_device"]=False
        with self.assertRaisesRegex(ValueError,"generic category"):validate_programme(m,self.registry)
    def test_proposed_class_upgrade_fails_closed(self):
        m=copy.deepcopy(self.programme);m["classification_finality_policy"]["device_class_without_regulation_number_must_not_be_presented_as_final"]=False
        with self.assertRaisesRegex(ValueError,"cannot be final"):validate_programme(m,self.registry)
    def test_authorization_auto_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_clearance_or_approval_claim_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_clearance_or_approval_claim_creation"):validate_programme(m,self.registry)
    def test_product_code_auto_relationship_fails_closed(self):
        m=copy.deepcopy(self.programme);m["inclusion_policy"]["automatic_product_code_relationship_creation"]=True
        with self.assertRaisesRegex(ValueError,"automatic_product_code_relationship_creation"):validate_programme(m,self.registry)
    def test_device_class_conformance_claim_fails_closed(self):
        m=copy.deepcopy(self.programme);m["coverage_contract"]["device_class_is_system_conformance_claim"]=True
        with self.assertRaisesRegex(ValueError,"device_class_is_system_conformance_claim"):validate_programme(m,self.registry)
    def test_unavailable_dependency_fails_closed(self):
        m=copy.deepcopy(self.programme);m["workbench_dependency"]["integration_state"]="NOT_IMPLEMENTED"
        with self.assertRaisesRegex(ValueError,"must be AVAILABLE"):validate_programme(m,self.registry)
    def test_schema_requires_available_capability(self):
        s=json.loads(Path("schemas/openfda-device-classification-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"AVAILABLE")
if __name__=="__main__":unittest.main()

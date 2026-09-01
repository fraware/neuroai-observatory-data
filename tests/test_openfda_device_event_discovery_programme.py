from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_device_event_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme

class MaudeProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"));cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
    def test_current_programme_validates(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r["query_stream_count"],5);self.assertEqual(r["integration_state"],"AVAILABLE");self.assertFalse(r["patient_fields_authorized"]);self.assertFalse(r["mdr_narrative_authorized"]);self.assertFalse(r["canonical_mutation_performed"])
    def test_minimization_is_hard_boundary(self):
        p=self.programme["candidate_projection"];self.assertFalse(p["patient_level_fields_in_discovery_layer"]);self.assertFalse(p["mdr_text_narrative_capture_in_discovery_layer"]);self.assertFalse(p["raw_api_pages_emitted_to_s2"])
    def test_exact_identity_does_not_auto_resolve_system_or_manufacturer(self):
        i=self.programme["identity_policy"];self.assertEqual(i["primary_identity"],"MDR_REPORT_KEY")
        for k in ("report_number_auto_merge","device_brand_name_auto_system_merge","manufacturer_name_auto_entity_merge","udi_auto_system_merge","product_code_auto_system_merge"):self.assertFalse(i[k],k)
    def test_available_dependency_required(self):
        m=copy.deepcopy(self.programme);m["workbench_dependency"]["integration_state"]="PENDING_S1_MERGE"
        with self.assertRaisesRegex(ValueError,"AVAILABLE"):validate_programme(m,self.registry)
    def test_silent_truncation_fails_closed(self):
        m=copy.deepcopy(self.programme);m["paging_policy"]["silent_truncation_allowed"]=True
        with self.assertRaisesRegex(ValueError,"Over-limit boundary"):validate_programme(m,self.registry)
    def test_search_after_cannot_silently_activate(self):
        m=copy.deepcopy(self.programme);m["paging_policy"]["search_after_not_yet_authorized_by_v0_1_projector"]=False
        with self.assertRaisesRegex(ValueError,"Over-limit boundary"):validate_programme(m,self.registry)
    def test_causality_and_incidence_claims_fail_closed(self):
        for key in ("causality_claim","incidence_or_rate_claim","comparative_safety_claim"):
            m=copy.deepcopy(self.programme);m["coverage_contract"][key]=True
            with self.assertRaisesRegex(ValueError,key):validate_programme(m,self.registry)
    def test_patient_projection_cannot_be_enabled(self):
        m=copy.deepcopy(self.programme);m["candidate_projection"]["patient_level_fields_in_discovery_layer"]=True
        with self.assertRaisesRegex(ValueError,"Minimization"):validate_programme(m,self.registry)
    def test_schema_requires_available(self):
        s=json.loads(Path("schemas/openfda-device-event-discovery-programme.schema.json").read_text(encoding="utf-8"));self.assertEqual(s["properties"]["workbench_dependency"]["properties"]["integration_state"]["const"],"AVAILABLE")

if __name__=="__main__":unittest.main()

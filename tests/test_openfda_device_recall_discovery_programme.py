from __future__ import annotations
import copy,json,unittest
from pathlib import Path
from scripts.validate_openfda_device_recall_discovery_programme import PROGRAMME_PATH,UNIVERSE_REGISTRY_PATH,validate_programme

class OpenFdaDeviceRecallProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme=json.loads(PROGRAMME_PATH.read_text(encoding='utf-8'))
        cls.registry=json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding='utf-8'))
    def test_current_programme_validates(self):
        r=validate_programme(self.programme,self.registry);self.assertEqual(r['query_stream_count'],5);self.assertEqual(r['integration_state'],'AVAILABLE');self.assertFalse(r['automatic_reopening'])
    def test_cfres_identity_and_lineage_boundary(self):
        i=self.programme['identity_policy'];self.assertEqual(i['primary_identity'],'CFRES_ID');self.assertTrue(i['res_event_number_is_lineage_not_record_identity']);self.assertFalse(i['k_number_auto_system_merge']);self.assertFalse(i['pma_number_auto_system_merge'])
    def test_minimization_and_authority_boundaries(self):
        p=self.programme['candidate_projection'];self.assertFalse(p['address_or_contact_fields_in_discovery_layer']);self.assertFalse(p['code_info_lot_serial_text_in_discovery_layer']);self.assertFalse(p['distribution_pattern_in_discovery_layer']);self.assertFalse(self.programme['human_review_contract']['recall_record_automatically_reopens_assessment'])
    def test_dependency_downgrade_fails_closed(self):
        p=copy.deepcopy(self.programme);p['workbench_dependency']['integration_state']='PENDING_S1_MERGE'
        with self.assertRaisesRegex(ValueError,'AVAILABLE'):validate_programme(p,self.registry)
    def test_silent_truncation_fails_closed(self):
        p=copy.deepcopy(self.programme);p['paging_policy']['silent_truncation_allowed']=True
        with self.assertRaisesRegex(ValueError,'silent_truncation_allowed'):validate_programme(p,self.registry)
    def test_search_after_cannot_be_silently_enabled(self):
        p=copy.deepcopy(self.programme);p['paging_policy']['search_after_not_yet_authorized_by_v0_1_projector']=False
        with self.assertRaisesRegex(ValueError,'search-after'):validate_programme(p,self.registry)
    def test_auto_reopening_fails_closed(self):
        p=copy.deepcopy(self.programme);p['inclusion_policy']['automatic_reopening_decision']=True
        with self.assertRaisesRegex(ValueError,'automatic_reopening_decision'):validate_programme(p,self.registry)
    def test_schema_requires_available_capability(self):
        s=json.loads(Path('schemas/openfda-device-recall-discovery-programme.schema.json').read_text());self.assertEqual(s['properties']['workbench_dependency']['properties']['integration_state']['const'],'AVAILABLE')

if __name__=='__main__':unittest.main()

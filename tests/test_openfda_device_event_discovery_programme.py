from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_openfda_device_event_discovery_programme import (
    PROGRAMME_PATH,
    UNIVERSE_REGISTRY_PATH,
    validate_programme,
)


class OpenFdaDeviceEventProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.programme = json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_current_programme_validates_offline(self) -> None:
        result = validate_programme(self.programme, self.registry)
        self.assertEqual(result["programme_id"], "SU-REGULATION-OPENFDA-DEVICE-EVENTS-v0.1")
        self.assertEqual(result["query_stream_count"], 5)
        self.assertEqual(result["integration_state"], "NOT_IMPLEMENTED")
        self.assertFalse(result["network_requests_performed"])
        self.assertFalse(result["patient_level_fields_projected"])
        self.assertFalse(result["mdr_narratives_projected"])
        self.assertFalse(result["causality_claim"])
        self.assertFalse(result["canonical_mutation_performed"])

    def test_queries_use_explicit_or_semantics(self) -> None:
        for row in self.programme["query_streams"]:
            self.assertIn("+OR+", row["search"])
            self.assertNotIn("+AND+", row["search"])
            self.assertIn("device.generic_name:", row["search"])

    def test_mdr_identity_and_successor_observation_boundary(self) -> None:
        identity = self.programme["identity_policy"]
        self.assertEqual(identity["primary_identity"], "MDR_REPORT_KEY")
        self.assertTrue(identity["record_content_change_is_successor_observation_not_new_report_identity"])
        self.assertFalse(identity["device_brand_name_auto_system_merge"])
        self.assertFalse(identity["manufacturer_name_auto_entity_merge"])
        self.assertFalse(identity["udi_auto_system_merge"])

    def test_no_patient_or_narrative_capture(self) -> None:
        projection = self.programme["candidate_projection"]
        self.assertFalse(projection["patient_level_fields_in_discovery_layer"])
        self.assertFalse(projection["mdr_text_narrative_capture_in_discovery_layer"])
        self.assertFalse(projection["raw_api_pages_emitted_to_s2"])

    def test_maude_report_never_becomes_causality_or_rate_claim(self) -> None:
        review = self.programme["human_review_contract"]
        self.assertFalse(review["mdr_report_is_causality_evidence"])
        self.assertFalse(review["mdr_count_is_incidence_evidence"])
        self.assertFalse(review["mdr_count_is_comparative_safety_evidence"])
        self.assertFalse(review["mdr_report_is_fda_conclusion"])
        self.assertFalse(review["mdr_report_is_recall_or_enforcement_action"])
        self.assertFalse(review["mdr_report_is_system_nonconformance_evidence_by_itself"])

    def test_skip_limit_boundary_is_explicit(self) -> None:
        provider = self.programme["provider_contract"]
        paging = self.programme["paging_policy"]
        self.assertEqual(provider["max_records_per_request"], 1000)
        self.assertEqual(provider["max_skip"], 25000)
        self.assertEqual(paging["max_direct_result_count"], 26000)
        self.assertTrue(paging["search_after_not_yet_authorized_by_v0_1_projector"])
        self.assertFalse(paging["silent_truncation_allowed"])
        self.assertFalse(paging["partial_over_limit_candidate_emission_allowed"])

    def test_implicit_boolean_search_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["query_streams"][0]["search"] = modified["query_streams"][0]["search"].replace("+OR+", "+")
        with self.assertRaisesRegex(ValueError, "Boolean OR must be explicit"):
            validate_programme(modified, self.registry)

    def test_patient_projection_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["candidate_projection"]["patient_level_fields_in_discovery_layer"] = True
        with self.assertRaisesRegex(ValueError, "Patient fields prohibited"):
            validate_programme(modified, self.registry)

    def test_causality_claim_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["coverage_contract"]["causality_claim"] = True
        with self.assertRaisesRegex(ValueError, "causality_claim"):
            validate_programme(modified, self.registry)

    def test_automatic_regulatory_action_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["inclusion_policy"]["automatic_regulatory_action_creation"] = True
        with self.assertRaisesRegex(ValueError, "automatic_regulatory_action_creation"):
            validate_programme(modified, self.registry)

    def test_schema_is_parseable_control_surface(self) -> None:
        schema = json.loads(Path("schemas/openfda-device-event-discovery-programme.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["programme_id"]["const"], "SU-REGULATION-OPENFDA-DEVICE-EVENTS-v0.1")
        self.assertEqual(schema["properties"]["provider_contract"]["properties"]["max_records_per_request"]["const"], 1000)


if __name__ == "__main__":
    unittest.main()

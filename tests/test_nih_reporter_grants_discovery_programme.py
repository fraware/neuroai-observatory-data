from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_nih_reporter_grants_discovery_programme import (
    PROGRAMME_PATH,
    UNIVERSE_REGISTRY_PATH,
    validate_programme,
)


class NihReporterGrantsDiscoveryProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.programme = json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_current_programme_validates_offline(self) -> None:
        result = validate_programme(self.programme, self.registry)
        self.assertEqual(result["programme_id"], "SU-GRANTS-NIH-REPORTER-v0.1")
        self.assertEqual(result["query_stream_count"], 7)
        self.assertEqual(result["grey_area_stream_count"], 1)
        self.assertEqual(result["integration_state"], "PENDING_S1_MERGE")
        self.assertFalse(result["network_requests_performed"])
        self.assertFalse(result["canonical_mutation_performed"])
        self.assertFalse(result["global_recall_claim"])

    def test_provider_pagination_limits_are_explicit(self) -> None:
        provider = self.programme["provider_contract"]
        self.assertEqual(provider["max_records_per_request"], 500)
        self.assertEqual(provider["max_offset"], 14999)
        policy = self.programme["pagination_partition_policy"]
        self.assertEqual(policy["max_directly_pageable_result_count"], 15000)
        self.assertFalse(policy["silent_truncation_allowed"])
        self.assertFalse(policy["partial_over_limit_candidate_emission_allowed"])

    def test_appl_id_is_identity_and_lineage_does_not_auto_merge(self) -> None:
        identity = self.programme["identity_policy"]
        self.assertEqual(identity["primary_identity"], "NIH_REPORTER_APPL_ID")
        self.assertFalse(identity["project_number_auto_merge"])
        self.assertFalse(identity["core_project_lineage_auto_merge"])
        self.assertFalse(identity["subproject_auto_parent_merge"])
        self.assertFalse(identity["pi_name_auto_entity_merge"])
        self.assertFalse(identity["organization_name_auto_entity_merge"])

    def test_grey_stream_is_review_only_tier_c(self) -> None:
        grey = next(row for row in self.programme["query_streams"] if row["query_id"] == "DISCOVERY-REPORTER-GREY-MENTAL-STATE-001")
        self.assertEqual(grey["scope_tiers"], ["C"])
        self.assertFalse(grey["completeness_claim"])
        self.assertTrue(self.programme["inclusion_policy"]["human_relevance_review_required"])
        self.assertFalse(self.programme["human_review_contract"]["automatic_acceptance"])

    def test_award_amount_never_becomes_success_or_quality_claim(self) -> None:
        projection = self.programme["candidate_projection"]
        review = self.programme["human_review_contract"]
        self.assertFalse(projection["award_amount_interpreted_as_research_success"])
        self.assertFalse(review["award_is_research_success_evidence"])
        self.assertFalse(review["award_is_system_effectiveness_evidence"])
        self.assertFalse(review["award_is_commercial_strength_evidence"])

    def test_unmerged_projector_cannot_be_called_available(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["workbench_dependency"]["integration_state"] = "AVAILABLE"
        with self.assertRaisesRegex(ValueError, "PENDING_S1_MERGE"):
            validate_programme(modified, self.registry)

    def test_silent_truncation_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["pagination_partition_policy"]["silent_truncation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "Silent RePORTER truncation"):
            validate_programme(modified, self.registry)

    def test_incremental_watermark_does_not_replace_baseline(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["incremental_refresh_policy"]["watermark_does_not_replace_historical_baseline"] = False
        with self.assertRaisesRegex(ValueError, "cannot replace historical baseline"):
            validate_programme(modified, self.registry)

    def test_automatic_funding_success_claim_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["inclusion_policy"]["automatic_funding_success_claim_creation"] = True
        with self.assertRaisesRegex(ValueError, "automatic_funding_success_claim_creation"):
            validate_programme(modified, self.registry)

    def test_schema_is_parseable_control_surface(self) -> None:
        schema = json.loads(Path("schemas/nih-reporter-grants-discovery-programme.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["programme_id"]["const"], "SU-GRANTS-NIH-REPORTER-v0.1")
        self.assertEqual(schema["properties"]["source_universe_id"]["const"], "SU-GRANTS")
        self.assertEqual(schema["properties"]["provider_contract"]["properties"]["max_records_per_request"]["const"], 500)


if __name__ == "__main__":
    unittest.main()

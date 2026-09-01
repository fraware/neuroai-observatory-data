from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_epo_ops_patent_discovery_programme import (
    PROGRAMME_PATH,
    UNIVERSE_REGISTRY_PATH,
    validate_programme,
)


class EpoOpsPatentDiscoveryProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.programme = json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_current_programme_validates_offline(self) -> None:
        result = validate_programme(self.programme, self.registry)
        self.assertEqual(result["programme_id"], "SU-PATENTS-EPO-OPS-v0.1")
        self.assertEqual(result["query_stream_count"], 9)
        self.assertEqual(result["grey_area_stream_count"], 3)
        self.assertEqual(result["known_applicant_count"], 8)
        self.assertEqual(result["integration_state"], "NOT_IMPLEMENTED")
        self.assertFalse(result["network_requests_performed"])
        self.assertFalse(result["credentials_accessed"])
        self.assertFalse(result["canonical_mutation_performed"])
        self.assertFalse(result["global_recall_claim"])

    def test_over_limit_queries_must_split_not_truncate(self) -> None:
        policy = self.programme["search_partition_policy"]
        self.assertEqual(policy["leaf_query_max_total_result_count"], 2000)
        self.assertEqual(policy["over_limit_policy"], "SPLIT_QUERY_BEFORE_MATERIALIZATION")
        self.assertFalse(policy["silent_truncation_allowed"])
        self.assertFalse(policy["partial_over_limit_candidate_emission_allowed"])
        self.assertTrue(policy["partition_provenance_required"])

    def test_grey_area_streams_are_tier_c_only(self) -> None:
        grey = [
            row for row in self.programme["query_streams"]
            if row["query_id"].startswith("DISCOVERY-OPS-GREY-")
        ]
        self.assertEqual(len(grey), 3)
        for row in grey:
            self.assertEqual(row["scope_tiers"], ["C"])
            self.assertFalse(row["completeness_claim"])

    def test_patent_existence_never_becomes_capability_or_implementation(self) -> None:
        review = self.programme["human_review_contract"]
        self.assertFalse(review["patent_existence_is_capability_evidence"])
        self.assertFalse(review["patent_existence_is_product_implementation_evidence"])
        self.assertFalse(review["patent_existence_is_freedom_to_operate_evidence"])
        self.assertFalse(review["patent_existence_is_validity_or_enforceability_determination"])

    def test_family_and_applicant_identity_do_not_auto_merge(self) -> None:
        identity = self.programme["identity_policy"]
        self.assertFalse(identity["patent_family_auto_merge"])
        self.assertFalse(identity["publication_step_auto_merge"])
        self.assertFalse(identity["applicant_name_auto_entity_merge"])
        self.assertTrue(identity["family_relationship_requires_explicit_family_retrieval"])

    def test_unimplemented_projector_cannot_be_called_available(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["workbench_dependency"]["integration_state"] = "AVAILABLE"
        with self.assertRaisesRegex(ValueError, "NOT_IMPLEMENTED"):
            validate_programme(modified, self.registry)

    def test_silent_truncation_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["search_partition_policy"]["silent_truncation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "Silent OPS truncation"):
            validate_programme(modified, self.registry)

    def test_automatic_capability_claim_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["inclusion_policy"]["automatic_capability_claim_creation"] = True
        with self.assertRaisesRegex(ValueError, "automatic_capability_claim_creation"):
            validate_programme(modified, self.registry)

    def test_credentials_may_not_be_committed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["network_policy"]["credentials_or_tokens_may_be_committed"] = True
        with self.assertRaisesRegex(ValueError, "Credentials/tokens"):
            validate_programme(modified, self.registry)

    def test_schema_is_parseable_control_surface(self) -> None:
        schema = json.loads(Path("schemas/epo-ops-patent-discovery-programme.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["programme_id"]["const"], "SU-PATENTS-EPO-OPS-v0.1")
        self.assertEqual(schema["properties"]["source_universe_id"]["const"], "SU-PATENTS")


if __name__ == "__main__":
    unittest.main()

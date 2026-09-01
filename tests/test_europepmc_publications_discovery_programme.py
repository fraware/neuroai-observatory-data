from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_europepmc_publications_discovery_programme import (
    PROGRAMME_PATH,
    UNIVERSE_REGISTRY_PATH,
    validate_programme,
)


class EuropePmcPublicationsDiscoveryProgrammeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.programme = json.loads(PROGRAMME_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_current_programme_validates_offline(self) -> None:
        result = validate_programme(self.programme, self.registry)
        self.assertEqual(result["programme_id"], "SU-PUBLICATIONS-EUROPEPMC-v0.1")
        self.assertEqual(result["source_universe_id"], "SU-PUBLICATIONS")
        self.assertEqual(result["query_stream_count"], 8)
        self.assertEqual(result["anchor_count"], 2)
        self.assertEqual(result["integration_state"], "NOT_IMPLEMENTED")
        self.assertFalse(result["network_requests_performed"])
        self.assertFalse(result["canonical_mutation_performed"])
        self.assertFalse(result["global_recall_claim"])

    def test_query_streams_are_unique_and_title_abstract_scoped(self) -> None:
        streams = self.programme["query_streams"]
        self.assertEqual(len({row["query_id"] for row in streams}), len(streams))
        self.assertEqual(len({row["query_term"] for row in streams}), len(streams))
        for row in streams:
            self.assertTrue(row["query_term"].startswith("TITLE_ABS:"))
            self.assertFalse(row["completeness_claim"])

    def test_grey_area_stream_is_review_only_tier_c(self) -> None:
        grey = next(
            row
            for row in self.programme["query_streams"]
            if row["query_id"] == "DISCOVERY-EPMC-GREY-MENTAL-STATE-001"
        )
        self.assertEqual(grey["scope_tiers"], ["C"])
        self.assertIn("review candidate only", grey["purpose"].lower())
        self.assertTrue(self.programme["inclusion_policy"]["human_relevance_review_required"])
        self.assertFalse(self.programme["human_review_contract"]["automatic_acceptance"])

    def test_preprint_and_journal_versions_do_not_auto_merge(self) -> None:
        self.assertFalse(self.programme["identity_policy"]["preprint_journal_version_auto_merge"])
        self.assertFalse(self.programme["identity_policy"]["fuzzy_title_identity_merge_allowed"])
        self.assertEqual(self.programme["identity_policy"]["conflicting_same_identity_policy"], "FAIL_CLOSED")

    def test_anchor_cannot_be_counted_as_new_discovery(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["known_identifier_anchors"][0]["counts_as_new_discovery"] = True
        with self.assertRaisesRegex(ValueError, "cannot count as new discovery"):
            validate_programme(modified, self.registry)

    def test_automatic_source_admission_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["inclusion_policy"]["automatic_publication_source_admission"] = True
        with self.assertRaisesRegex(ValueError, "automatic_publication_source_admission"):
            validate_programme(modified, self.registry)

    def test_fuzzy_identity_merge_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["identity_policy"]["fuzzy_title_identity_merge_allowed"] = True
        with self.assertRaisesRegex(ValueError, "Fuzzy title identity merge"):
            validate_programme(modified, self.registry)

    def test_completeness_claim_fails_closed(self) -> None:
        modified = copy.deepcopy(self.programme)
        modified["coverage_contract"]["global_neuroai_publication_recall_claim"] = True
        with self.assertRaisesRegex(ValueError, "global_neuroai_publication_recall_claim"):
            validate_programme(modified, self.registry)

    def test_schema_is_valid_json_control_surface(self) -> None:
        schema_path = Path("schemas/europepmc-publications-discovery-programme.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["programme_id"]["const"], "SU-PUBLICATIONS-EUROPEPMC-v0.1")


if __name__ == "__main__":
    unittest.main()

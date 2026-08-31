from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v16_adjudicated_delta_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v16_adjudicated_delta_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V16AdjudicatedDeltaProjectionTests(unittest.TestCase):
    def test_exact_reconciliation_without_double_counting(self) -> None:
        result = module.project()["reconciliation"]
        self.assertTrue(result["separate_delta_matches_embedded"])
        self.assertEqual(
            result["separate_delta_canonical_digest"],
            "658a0a169e1e67a4476ad305f0ff489e4ba664a2fd1a774ea59922a420c6d03d",
        )
        self.assertEqual(result["separate_delta_canonical_digest"], result["embedded_delta_canonical_digest"])
        self.assertEqual(result["input_unique_change_count"], 9)
        self.assertEqual(result["projected_unique_change_identity_count"], 9)
        self.assertEqual(result["projected_event_count"], 6)
        self.assertEqual(result["projected_model_entity_count"], 2)
        self.assertEqual(result["projected_model_assertion_count"], 6)
        self.assertEqual(result["projected_relationship_count"], 1)
        self.assertEqual(
            (result["regulatory_event_count"], result["capital_event_count"], result["governance_event_count"]),
            (2, 2, 2),
        )
        self.assertEqual(result["event_exact_date_count"], 6)
        self.assertEqual(result["accepted_change_source_reference_count"], 10)
        self.assertEqual(result["projected_change_source_reference_count"], 10)
        self.assertEqual(result["projected_change_observation_reference_count"], 10)
        for key in (
            "double_counted_embedded_change_count",
            "identity_loss_count",
            "duplicate_projected_identity_count",
            "predecessor_payload_roundtrip_failure_count",
            "source_reference_loss_count",
            "observation_reference_loss_count",
            "endpoint_resolution_fabrication_count",
            "event_time_precision_fabrication_count",
            "knowledge_time_fabrication_count",
        ):
            self.assertEqual(result[key], 0, (key, result[key]))
        self.assertFalse(result["canonical_successor_ready"])

    def test_regulatory_bounded_effects_and_prohibited_inferences_survive(self) -> None:
        events = [
            row
            for row in module.project()["events"]
            if row["event_family"] == "REGULATORY_AND_MARKET"
        ]
        self.assertEqual(len(events), 2)
        for event in events:
            predecessor = event["predecessor"]["payload"]
            self.assertEqual(event["claim_boundary"], predecessor["bounded_effect"])
            self.assertEqual(event["attributes"]["bounded_effect"], predecessor["bounded_effect"])
            self.assertEqual(event["attributes"]["prohibited_inferences"], predecessor["prohibited_inferences"])
            self.assertEqual(event["boundary_state"], "PREDECESSOR_BOUNDED_EFFECT_RECORDED")

    def test_governance_does_not_invent_boundary_or_evidence_strength(self) -> None:
        events = [
            row
            for row in module.project()["events"]
            if row["event_family"] == "GOVERNANCE_AND_LEADERSHIP"
        ]
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertIsNone(event["event_type"])
            self.assertIsNone(event["claim_boundary"])
            self.assertEqual(event["boundary_state"], "PREDECESSOR_BOUNDARY_NOT_RECORDED")
            self.assertEqual(
                event["evidence_state"],
                "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
            )

    def test_models_separate_identity_from_bounded_attributes(self) -> None:
        result = module.project()
        self.assertEqual({row["entity_kind"] for row in result["entities"]}, {"MODEL"})
        by_model: dict[str, list[dict]] = {}
        for assertion in result["assertions"]:
            by_model.setdefault(assertion["subject_id"], []).append(assertion)
            self.assertEqual(assertion["review_state"], "MIGRATED_PREDECESSOR_STATE")
            self.assertEqual(assertion["record_state"], "NONCANONICAL_CANDIDATE")
            self.assertEqual(
                assertion["evidence_state"],
                "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
            )
        self.assertEqual(set(by_model), {"MDL-16-001", "MDL-16-002"})
        self.assertTrue(all(len(rows) == 3 for rows in by_model.values()))

    def test_all_literal_endpoints_remain_unresolved(self) -> None:
        result = module.project()
        endpoints = []
        for event in result["events"]:
            endpoints.extend([event["subject_reference"], *event["counterparty_references"]])
        for relationship in result["relationships"]:
            endpoints.extend([relationship["subject_reference"], relationship["object_reference"]])
        self.assertTrue(endpoints)
        self.assertTrue(all(endpoint["entity_id"] is None for endpoint in endpoints))
        self.assertTrue(
            all(endpoint["resolution_state"] == "PREDECESSOR_LITERAL_UNRESOLVED" for endpoint in endpoints)
        )


if __name__ == "__main__":
    unittest.main()

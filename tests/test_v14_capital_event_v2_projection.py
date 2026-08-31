from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "project_v14_capital_events_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_capital_events_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
BASELINE = (
    ROOT
    / "releases"
    / "data-v0.1.0-public-governing"
    / "records"
    / "canonical_observatory_release_v1.4.json"
)


class V14CapitalEventV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.result = module.project(BASELINE)
        cls.predecessors = {row["event_id"]: row for row in cls.baseline["capital_and_ownership_events"]}
        cls.events = {row["event_id"]: row for row in cls.result["events"]}

    def test_exact_event_population_and_temporal_distribution(self) -> None:
        reconciliation = self.result["reconciliation"]
        self.assertEqual(reconciliation["input_event_count"], 5)
        self.assertEqual(reconciliation["projected_event_count"], 5)
        self.assertEqual(
            reconciliation["event_time_precision_counts"],
            {"DATE": 3, "MONTH": 0, "TIMESTAMP": 0, "UNRESOLVED": 0, "YEAR": 1},
        )
        self.assertEqual(reconciliation["unresolved_event_time_count"], 1)
        self.assertEqual(reconciliation["unresolved_knowledge_time_count"], 5)
        self.assertEqual(reconciliation["disclosed_amount_count"], 3)
        self.assertEqual(reconciliation["undisclosed_amount_count"], 2)
        self.assertEqual(reconciliation["counterparty_literal_count"], 16)
        self.assertFalse(reconciliation["canonical_successor_ready"])

    def test_event_world_time_preserves_exact_predecessor_precision(self) -> None:
        for event_id, predecessor in self.predecessors.items():
            event = self.events[event_id]
            raw = predecessor["date"]
            if raw is None:
                self.assertIsNone(event["occurred_at"])
                self.assertEqual(event["event_time_state"], "PREDECESSOR_TIME_UNRESOLVED")
            elif raw == "2026":
                self.assertEqual(event["occurred_at"], {"value": "2026", "precision": "YEAR"})
                self.assertEqual(event["event_time_state"], "EXACT_PREDECESSOR_TIME")
            else:
                self.assertEqual(event["occurred_at"], {"value": raw, "precision": "DATE"})
                self.assertEqual(event["event_time_state"], "EXACT_PREDECESSOR_TIME")

    def test_knowledge_time_remains_separate_and_unresolved(self) -> None:
        for event in self.events.values():
            self.assertIsNone(event["observed_at"])
            self.assertEqual(event["knowledge_time_state"], "PREDECESSOR_TIME_UNRESOLVED")
            self.assertEqual(event["observation_ids"], [])

    def test_amount_and_currency_null_semantics_are_exact(self) -> None:
        for event_id, predecessor in self.predecessors.items():
            event = self.events[event_id]
            self.assertEqual(
                event["attributes"],
                {
                    "amount": predecessor["amount"],
                    "currency": predecessor["currency"],
                    "amount_state": predecessor["amount_state"],
                    "ownership_effect": predecessor["ownership_effect"],
                },
            )
            if predecessor["amount_state"] == "NOT_DISCLOSED":
                self.assertIsNone(event["attributes"]["amount"])
                self.assertIsNone(event["attributes"]["currency"])

    def test_subject_and_counterparties_remain_unresolved_literals(self) -> None:
        for event_id, predecessor in self.predecessors.items():
            event = self.events[event_id]
            self.assertEqual(event["subject_reference"]["value"], predecessor["subject"])
            self.assertEqual(
                [row["value"] for row in event["counterparty_references"]], predecessor["counterparties"]
            )
            for endpoint in [event["subject_reference"], *event["counterparty_references"]]:
                self.assertEqual(endpoint["resolution_state"], "PREDECESSOR_LITERAL_UNRESOLVED")
                self.assertIsNone(endpoint["entity_id"])

    def test_source_evidence_boundary_and_payload_are_preserved(self) -> None:
        governing_source_ids = {row["source_id"] for row in self.baseline["sources"]}
        for event_id, predecessor in self.predecessors.items():
            event = self.events[event_id]
            self.assertEqual(event["source_ids"], predecessor["source_ids"])
            self.assertTrue(set(event["source_ids"]).issubset(governing_source_ids))
            self.assertEqual(event["evidence_state"], predecessor["evidence_state"])
            self.assertEqual(event["claim_boundary"], predecessor["boundary"])
            self.assertEqual(event["predecessor"]["payload"], predecessor)
            self.assertEqual(event["predecessor"]["record_sha256"], module._digest(predecessor))

    def test_announced_majority_stake_is_not_strengthened(self) -> None:
        event = self.events["CAP-14-002"]
        self.assertEqual(event["attributes"]["ownership_effect"], "MAJORITY_STAKE_ANNOUNCED")
        self.assertIn("announced", event["claim_boundary"].lower())

    def test_reconciliation_has_no_loss_or_fabrication_in_this_slice(self) -> None:
        reconciliation = self.result["reconciliation"]
        for key in (
            "event_id_loss_count",
            "predecessor_payload_roundtrip_failure_count",
            "predecessor_field_loss_count",
            "event_type_loss_count",
            "event_time_loss_or_precision_fabrication_count",
            "amount_or_currency_loss_count",
            "ownership_effect_loss_count",
            "claim_boundary_loss_count",
            "source_or_evidence_reference_loss_count",
            "dangling_source_reference_count",
            "endpoint_resolution_fabrication_count",
            "knowledge_time_fabrication_count",
            "invented_predecessor_field_value_count",
        ):
            self.assertEqual(reconciliation[key], 0, key)


if __name__ == "__main__":
    unittest.main()

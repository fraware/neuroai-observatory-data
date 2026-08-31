from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "project_v14_model_dataset_registry_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_model_dataset_registry_to_v2", SCRIPT)
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


class V14ModelDatasetRegistryV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.result = module.project(BASELINE)
        cls.predecessors = {
            row["registry_id"]: row for row in cls.baseline["model_and_dataset_registry"]
        }
        cls.entities = {row["entity_id"]: row for row in cls.result["entities"]}
        cls.assertions_by_subject: dict[str, list[dict[str, object]]] = {}
        for assertion in cls.result["assertions"]:
            cls.assertions_by_subject.setdefault(str(assertion["subject_id"]), []).append(assertion)

    def test_exact_registry_population_and_aggregate_totals_are_preserved(self) -> None:
        reconciliation = self.result["reconciliation"]
        self.assertEqual(len(self.predecessors), 5)
        self.assertEqual(reconciliation["input_registry_count"], 5)
        self.assertEqual(reconciliation["projected_registry_entity_count"], 5)
        self.assertEqual(reconciliation["projected_assertion_count"], 25)
        self.assertEqual(reconciliation["source_linked_registry_count"], 5)
        self.assertEqual(reconciliation["unresolved_knowledge_time_count"], 5)
        self.assertEqual(reconciliation["source_reported_record_count_total"], 1716)
        self.assertEqual(reconciliation["source_reported_subcount_value_total"], 385872.0)
        self.assertEqual(reconciliation["expanded_child_entity_count"], 0)
        self.assertFalse(reconciliation["canonical_successor_ready"])

    def test_registry_identity_and_predecessor_payload_round_trip(self) -> None:
        self.assertEqual(set(self.predecessors), set(self.entities))
        for registry_id, predecessor in self.predecessors.items():
            entity = self.entities[registry_id]
            self.assertEqual(entity["entity_kind"], "REGISTRY_OR_BENCHMARK")
            self.assertEqual(entity["canonical_name"], predecessor["name"])
            self.assertEqual(entity["predecessor"]["payload"], predecessor)
            self.assertEqual(
                entity["predecessor"]["record_sha256"], module._digest(predecessor)
            )

    def test_aggregate_counts_remain_assertions_not_child_entities(self) -> None:
        self.assertEqual(len(self.entities), 5)
        for registry_id, predecessor in self.predecessors.items():
            assertions = self.assertions_by_subject[registry_id]
            count_assertions = [
                row for row in assertions if row["predicate"] == "SOURCE_REPORTED_RECORD_COUNT"
            ]
            subcount_assertions = [
                row for row in assertions if row["predicate"] == "SOURCE_REPORTED_SUBCOUNTS"
            ]
            self.assertEqual(len(count_assertions), 1)
            self.assertEqual(len(subcount_assertions), 1)
            self.assertEqual(count_assertions[0]["value"], predecessor["record_count"])
            self.assertEqual(subcount_assertions[0]["value"], predecessor["subcounts"])
            self.assertNotIn("object_id", count_assertions[0])
            self.assertNotIn("object_id", subcount_assertions[0])

    def test_source_and_boundary_semantics_are_exact(self) -> None:
        governing_source_ids = {row["source_id"] for row in self.baseline["sources"]}
        for registry_id, predecessor in self.predecessors.items():
            self.assertEqual(len(predecessor["source_ids"]), 1)
            self.assertTrue(set(predecessor["source_ids"]).issubset(governing_source_ids))
            for assertion in self.assertions_by_subject[registry_id]:
                self.assertEqual(assertion["source_ids"], predecessor["source_ids"])
                self.assertEqual(assertion["source_linkage_state"], "SOURCE_LINKED")
                self.assertEqual(assertion["claim_boundary"], predecessor["boundary"])
                self.assertEqual(
                    assertion["evidence_state"],
                    "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
                )
                self.assertEqual(
                    assertion["verification_state"],
                    "PREDECESSOR_VERIFICATION_STATE_UNSPECIFIED",
                )

    def test_registry_knowledge_time_is_not_inferred_from_release_cutoff(self) -> None:
        for assertions in self.assertions_by_subject.values():
            for assertion in assertions:
                self.assertIsNone(assertion["observed_at"])
                self.assertEqual(
                    assertion["knowledge_time_state"], "PREDECESSOR_TIME_UNRESOLVED"
                )

    def test_reconciliation_has_no_loss_fabrication_or_count_expansion(self) -> None:
        reconciliation = self.result["reconciliation"]
        for key in (
            "identity_mismatch_count",
            "predecessor_payload_roundtrip_failure_count",
            "predecessor_field_loss_count",
            "claim_boundary_loss_count",
            "source_reference_loss_count",
            "dangling_source_reference_count",
            "temporal_precision_fabrication_count",
            "invented_predecessor_field_value_count",
            "expanded_child_entity_count",
        ):
            self.assertEqual(reconciliation[key], 0, key)


if __name__ == "__main__":
    unittest.main()

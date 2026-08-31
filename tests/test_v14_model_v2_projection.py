from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "project_v14_models_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_models_to_v2", SCRIPT)
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


class V14ModelV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.result = module.project(BASELINE)
        cls.predecessors = {
            row["model_id"]: row for row in cls.baseline["representative_model_records"]
        }
        cls.entities = {row["entity_id"]: row for row in cls.result["entities"]}
        cls.assertions_by_subject: dict[str, list[dict[str, object]]] = {}
        for assertion in cls.result["assertions"]:
            cls.assertions_by_subject.setdefault(str(assertion["subject_id"]), []).append(assertion)

    def test_exact_model_population_is_preserved(self) -> None:
        reconciliation = self.result["reconciliation"]
        self.assertEqual(len(self.predecessors), 13)
        self.assertEqual(reconciliation["input_model_count"], 13)
        self.assertEqual(reconciliation["projected_model_entity_count"], 13)
        self.assertEqual(reconciliation["projected_assertion_count"], 151)
        self.assertEqual(reconciliation["source_linked_model_count"], 13)
        self.assertEqual(reconciliation["exact_knowledge_time_count"], 10)
        self.assertEqual(reconciliation["unresolved_knowledge_time_count"], 3)
        self.assertEqual(reconciliation["source_system_reference_count"], 9)
        self.assertFalse(reconciliation["canonical_successor_ready"])

    def test_model_identity_and_predecessor_payload_round_trip(self) -> None:
        self.assertEqual(set(self.predecessors), set(self.entities))
        for model_id, predecessor in self.predecessors.items():
            entity = self.entities[model_id]
            self.assertEqual(entity["entity_kind"], "MODEL")
            self.assertEqual(entity["canonical_name"], predecessor["name"])
            self.assertEqual(entity["aliases"], [])
            self.assertEqual(entity["predecessor"]["payload"], predecessor)
            self.assertEqual(
                entity["predecessor"]["record_sha256"], module._digest(predecessor)
            )

    def test_all_model_assertions_preserve_sources_and_claim_boundary(self) -> None:
        governing_source_ids = {row["source_id"] for row in self.baseline["sources"]}
        for model_id, predecessor in self.predecessors.items():
            self.assertTrue(predecessor["source_ids"])
            self.assertTrue(set(predecessor["source_ids"]).issubset(governing_source_ids))
            for assertion in self.assertions_by_subject[model_id]:
                self.assertEqual(assertion["source_ids"], predecessor["source_ids"])
                self.assertEqual(assertion["source_linkage_state"], "SOURCE_LINKED")
                self.assertEqual(assertion["claim_boundary"], predecessor["claim_boundary"])
                self.assertEqual(
                    assertion["evidence_state"],
                    "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
                )
                self.assertEqual(assertion["verification_state"], predecessor["verification_state"])

    def test_model_knowledge_time_is_preserved_without_timestamp_fabrication(self) -> None:
        for model_id, predecessor in self.predecessors.items():
            for assertion in self.assertions_by_subject[model_id]:
                if predecessor["last_verified"] is None:
                    self.assertIsNone(assertion["observed_at"])
                    self.assertEqual(
                        assertion["knowledge_time_state"], "PREDECESSOR_TIME_UNRESOLVED"
                    )
                else:
                    self.assertEqual(predecessor["last_verified"], "2026-07-29")
                    self.assertEqual(
                        assertion["observed_at"],
                        {"value": "2026-07-29", "precision": "DATE"},
                    )
                    self.assertEqual(
                        assertion["knowledge_time_state"], "EXACT_PREDECESSOR_TIME"
                    )

    def test_source_system_reference_is_preserved_but_not_promoted_to_relationship(self) -> None:
        with_system = [row for row in self.predecessors.values() if row["source_system_id"]]
        self.assertEqual(len(with_system), 9)
        for predecessor in with_system:
            refs = [
                row
                for row in self.assertions_by_subject[predecessor["model_id"]]
                if row["predicate"] == "SOURCE_SYSTEM_REFERENCE"
            ]
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["value"], predecessor["source_system_id"])
            self.assertNotIn("object_id", refs[0])

    def test_reconciliation_has_no_claimed_loss_or_fabrication_in_this_slice(self) -> None:
        reconciliation = self.result["reconciliation"]
        for key in (
            "identity_mismatch_count",
            "predecessor_payload_roundtrip_failure_count",
            "predecessor_field_loss_count",
            "claim_boundary_loss_count",
            "source_reference_loss_count",
            "dangling_source_reference_count",
            "source_system_reference_loss_count",
            "temporal_precision_fabrication_count",
            "invented_predecessor_field_value_count",
        ):
            self.assertEqual(reconciliation[key], 0, key)


if __name__ == "__main__":
    unittest.main()
